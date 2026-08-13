"""Getting the code text into the store, deterministically.

Nothing can be verified until the words a value claims to come from are on
disk, so this is the first step of every encoding pass::

    python -m flats.provenance.fetch or/multnomah/portland/33.110.txt \\
        https://www.portland.gov/code/33/100s/110 --start "33.110.220"

Two things make this harder than downloading a page.

*The text has to be stable.* Everything downstream compares hashes, so the
same page fetched twice must produce identical bytes or every value on it flips
to stale for nothing. The extractor is therefore dumb on purpose — tags out,
whitespace collapsed, entities resolved, one line per block — and versioned, so
a change to the algorithm is visible rather than looking like an amendment.

*Refreshing evidence is not free.* A codifier's boilerplate churns constantly;
the ordinance text rarely does. ``--start``/``--end`` slice the stored document
down to the section that was actually read, which is both what a reviewer
looked at and the smallest thing that can drift. And when a refresh does change
the text, the verifications that relied on the old words are withdrawn in the
same command — otherwise a re-fetch would quietly repair the hash and leave
signatures standing over sentences nobody has read.
"""

from __future__ import annotations

import argparse
import html.parser
import re
import sys
from datetime import date
from pathlib import Path
from typing import Callable, Sequence

from flats.encode.verify import LOG_PATH, VerKey, Verification, VerificationLog
from flats.provenance.sources import (
    Authority,
    FetchFailed,
    authority_for,
    fetch as fetch_source,
)
from flats.provenance.store import Document, ProvenanceError, ProvenanceStore, sha256
from flats.rules.loader import CONFIG_ROOT, load_rules
from flats.rules.model import Layer

#: Bumped when the extraction algorithm changes. A hash that moves because the
#: extractor changed is not an amendment, and the two must be tellable apart.
EXTRACTOR = "flats-html-text/1"
#: A slice shorter than this is reported. Legitimate one-line sections exist;
#: a marker that hit the table of contents is far more common.
SHORT_SLICE = 3

#: A floor for truncated and error responses only. Deliberately low: single
#: sections are genuinely short — Fairview's whole VSF chapter is about 4 KB —
#: and a floor high enough to catch a nav bar would refuse real ones, which
#: teaches everybody to pass --allow-thin and kills the guard. The count and
#: ratio below are what actually separate a chapter from a web page.
MIN_CHARS = 600
#: Lines that read like regulation — a section number or a dimensioned
#: standard. Absolute count and share are both checked: a long page of site
#: chrome clears the first, a three-line fragment clears the second.
MIN_CODE_LINES = 10
MIN_CODE_RATIO = 0.05

#: `33.110.220`, `4.0100`, `19.115.030` — a numbered provision.
_SECTION_NO = re.compile(r"\b\d{1,3}\.\d{2,4}(?:\.\d+)?\b")
#: `20 ft.`, `1,500 square feet`, `45 percent`, `4 units` — a standard with a
#: number on it, which is what this project is here to read.
_STANDARD = re.compile(
    r"\b\d[\d,]*(?:\.\d+)?\s*"
    r"(?:ft\.?|feet|foot|sq\.?\s*ft|square feet|percent|%|acres?|units?|stories|dwelling)\b",
    re.I,
)

#: Elements whose contents are never prose.
_DROP = frozenset({"script", "style", "noscript", "svg", "head", "template", "iframe"})
#: Elements that end a line.
_BLOCK = frozenset(
    {
        "p", "div", "section", "article", "header", "footer", "nav", "main", "aside",
        "h1", "h2", "h3", "h4", "h5", "h6", "li", "ul", "ol", "dl", "dt", "dd",
        "table", "thead", "tbody", "tr", "th", "td", "br", "hr", "blockquote", "pre",
    }
)

_SPACES = re.compile(r"[ \t   ]+")
_BLANKS = re.compile(r"\n{3,}")


class _Extractor(html.parser.HTMLParser):
    """Tags out, text kept, block elements broken onto their own lines."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _DROP:
            self._skip += 1
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _DROP:
            self._skip = max(0, self._skip - 1)
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            # Newlines inside a block are HTML formatting, not text. Keeping
            # them would let a reflow of the markup renumber every quote line
            # in the document without a word of the law changing.
            self.parts.append(data.replace("\r", " ").replace("\n", " "))


def html_to_text(source: str) -> str:
    """Deterministic plain text from an HTML page.

    Not a renderer. The goal is a stable byte sequence a person can read and a
    hash can watch, which means no cleverness that could produce a different
    result on the same input tomorrow.
    """
    parser = _Extractor()
    parser.feed(source)
    parser.close()
    text = "".join(parser.parts).replace("\r\n", "\n").replace("\r", "\n")
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    return _BLANKS.sub("\n\n", "\n".join(lines)).strip() + "\n"


def slice_between(text: str, start: str = "", end: str = "", *, nth: int = 1) -> str:
    """The span between two literal markers, inclusive of ``start``.

    Markers are literal text a reviewer can see on the page — a section number
    is the usual choice. Failing loudly when one is absent matters: silently
    storing the whole page instead would put a reviewer's quote line numbers
    somewhere else entirely.

    ``nth`` picks which occurrence starts the slice, and it is needed more often
    than it sounds: a chapter PDF lists every section number in its table of
    contents first, so the obvious marker matches a line of the index rather
    than the standards. Getting this wrong stores a one-line document, which is
    why a short result is called out rather than accepted quietly.
    """
    out = text
    if start:
        i, found = -1, 0
        while found < max(1, nth):
            i = out.find(start, i + 1)
            if i < 0:
                where = f" (occurrence {nth})" if nth > 1 else ""
                raise ProvenanceError(f"start marker {start!r} not found in the fetched text{where}")
            found += 1
        out = out[i:]
    if end:
        j = out.find(end, len(start) if start else 0)
        if j < 0:
            raise ProvenanceError(f"end marker {end!r} not found after the start marker")
        out = out[:j]
    return out.strip() + "\n"


def pdf_to_text(data: bytes) -> str:
    """Text out of a PDF, in reading order, one page after another.

    Oregon codifiers publish chapters as PDF — Portland's Title 33 among them —
    so this is not an edge case but the main path for the biggest jurisdiction
    in the state. Page furniture is left in: the running header carries the
    revision date, which is exactly the kind of change a hash should catch.
    """
    from io import BytesIO

    from pypdf import PdfReader

    reader = PdfReader(BytesIO(data))
    pages = [
        (page.extract_text(extraction_mode="layout") or "").replace("\r\n", "\n")
        for page in reader.pages
    ]
    # Internal spacing is kept, unlike the HTML path. Portland states its
    # standards in a grid with one column per zone, and the gaps between
    # columns are the only thing that says which number belongs to which zone.
    # Collapsing them would make R5's 10 ft indistinguishable from RF's 20 ft.
    lines = [line.rstrip() for line in "\n".join(pages).split("\n")]
    return _BLANKS.sub("\n\n", "\n".join(lines)).strip() + "\n"


def _http_get(url: str) -> bytes:
    import httpx

    response = httpx.get(url, follow_redirects=True, timeout=60.0)
    response.raise_for_status()
    return response.content


def _to_text(raw: bytes | str) -> str:
    """Whatever came back, reduced to the stored form."""
    if isinstance(raw, bytes):
        if raw[:5] == b"%PDF-":
            return pdf_to_text(raw)
        raw = raw.decode("utf-8", errors="replace")
    return html_to_text(raw) if "<" in raw[:2048] else raw.replace("\r\n", "\n")


def implausible(text: str) -> str | None:
    """Why this text cannot be code, or None if it might be.

    The provenance store exists to make evidence checkable, and it will hold
    whatever it is handed. Six real fetches across five codifiers produced one
    document of code text, three of site furniture, and one empty file — and
    every one of them was stored as evidence a value could cite. A signature
    over a nav bar is worse than no signature, because it looks like diligence.

    Deliberately coarse. This is not a judgement about whether the right
    chapter was fetched; it is the difference between a document and a web
    page, and it only has to catch what a person would catch at a glance.
    """
    stripped = text.strip()
    if not stripped:
        return "the response was empty"
    if len(stripped) < MIN_CHARS:
        return f"only {len(stripped)} characters — a landing page, not a chapter"
    lines = stripped.splitlines()
    coded = sum(1 for line in lines if _SECTION_NO.search(line) or _STANDARD.search(line))
    ratio = coded / len(lines)
    if coded < MIN_CODE_LINES or ratio < MIN_CODE_RATIO:
        return (
            f"no regulatory text found — {coded} of {len(lines)} lines carry a "
            f"section number or a dimensioned standard"
        )
    return None


def fetch_text(
    url: str,
    *,
    get: Callable[[str], bytes | str] | None = None,
    start: str = "",
    end: str = "",
    nth: int = 1,
) -> str:
    """Fetch a URL and reduce it to the stored form."""
    return slice_between(_to_text((get or _http_get)(url)), start, end, nth=nth)


def citing(layers: dict[str, Layer], doc_path: str) -> list[VerKey]:
    """Every verification key whose quote points into this document.

    Variants are listed separately from the value they hang off. An exception
    commonly cites a different chapter from its base, so amending one document
    should withdraw the signatures that read *it* and leave the rest standing.
    """
    found: list[VerKey] = []
    for layer_id, layer in layers.items():
        blocks = [("defaults", layer.defaults)]
        blocks += [(code, zone.values) for code, zone in layer.zones.items()]
        for zone_name, values in blocks:
            for name, value in values.items():
                for part in (value, *value.variants):
                    quote = part.prov.quote or ""
                    if quote.split("#", 1)[0] == doc_path:
                        found.append(
                            (layer_id, zone_name, name, tuple(sorted(getattr(part, "when", ()))))
                        )
    return sorted(found)


def withdraw_reviews(
    doc_path: str, *, layers: dict[str, Layer], log_path: Path, note: str
) -> list[Verification]:
    """Withdraw every verification standing on this document's old text.

    Called when a refresh changes the words. A re-fetch repairs the stored hash,
    which would otherwise leave signatures in place over sentences that have
    since been amended — the exact silent-false-certification this system is
    built to make impossible.
    """
    log = VerificationLog.load(log_path)
    active = log.active()
    withdrawn: list[Verification] = []
    for key in citing(layers, doc_path):
        prior = active.get(key)
        if prior is None:
            continue
        entry = Verification(
            layer=key[0],
            zone=key[1],
            field=key[2],
            when=key[3],
            fingerprint=prior.fingerprint,
            reviewer=prior.reviewer,
            reviewed=prior.reviewed,
            note=note,
            revoked=True,
        )
        log.append(entry, log_path)
        withdrawn.append(entry)
    return withdrawn


def store_document(
    store: ProvenanceStore,
    path: str,
    url: str,
    text: str,
    *,
    retrieved: date | None = None,
) -> Document:
    return store.save(path, url=url, text=text, retrieved=retrieved or date.today())


def main(argv: Sequence[str] | None = None, *, get: Callable[[str], bytes | str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="flats-fetch", description="Store the code text a rule value will cite."
    )
    parser.add_argument("path", help="store path, e.g. or/multnomah/portland/33.110.txt")
    parser.add_argument("url")
    parser.add_argument("--start", default="", help="literal marker where the stored text begins")
    parser.add_argument("--end", default="", help="literal marker where it ends")
    parser.add_argument(
        "--nth",
        type=int,
        default=1,
        help="which occurrence of --start begins the slice; a chapter PDF lists "
        "every section in its contents before the standards, so this is often 2",
    )
    parser.add_argument("--docs", type=Path, default=None, help="provenance store root")
    parser.add_argument("--rules", type=Path, default=CONFIG_ROOT)
    parser.add_argument("--log", type=Path, default=LOG_PATH)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="accept changed text, withdrawing the reviews that relied on the old words",
    )
    parser.add_argument("--retrieved", default="", help="ISO date, defaults to today")
    parser.add_argument(
        "--allow-thin",
        action="store_true",
        help="store a document that does not read like code — for the rare "
        "genuinely short section, never to silence a bad URL",
    )
    args = parser.parse_args(argv)

    store = ProvenanceStore(args.docs)
    strategy = ""
    if get is None:
        try:
            got = fetch_source(args.url)
        except FetchFailed as exc:
            print(f"{args.path}: {exc}", file=sys.stderr)
            return 1
        strategy = got.strategy

        def get(_url: str, _content: bytes = got.content) -> bytes:
            return _content

    try:
        text = fetch_text(args.url, get=get, start=args.start, end=args.end, nth=args.nth)
    except ProvenanceError as exc:
        print(f"{args.path}: {exc}", file=sys.stderr)
        return 1

    problem = implausible(text)
    if problem and not args.allow_thin:
        # Refusing costs one re-run with a better URL. Storing costs a reviewer
        # signing a nav bar, and nothing downstream would ever notice.
        print(f"{args.path}: refused — {problem}", file=sys.stderr)
        print("  Nothing was stored. Check that the URL serves the chapter text", file=sys.stderr)
        print("  itself rather than a landing page; --allow-thin overrides this,", file=sys.stderr)
        print("  but only after somebody has read the document.", file=sys.stderr)
        return 1

    authority = authority_for(args.url)
    if authority is not Authority.official:
        print(
            f"note: {authority.value} source — a lead, not evidence. No value citing "
            f"this may be verified.",
            file=sys.stderr,
        )
    if strategy and strategy != "plain":
        print(f"note: needed browser impersonation ({strategy})", file=sys.stderr)

    retrieved = date.fromisoformat(args.retrieved) if args.retrieved else date.today()
    lines = len(text.splitlines())
    if args.start and lines < SHORT_SLICE:
        # Almost always a marker that matched the table of contents instead of
        # the section. Storing it would give every quote into this document
        # line numbers that point at an index entry.
        print(
            f"warning: {args.path} sliced to {lines} line(s) — check --start/--nth",
            file=sys.stderr,
        )

    if not store.exists(args.path):
        store_document(store, args.path, args.url, text, retrieved=retrieved)
        print(f"stored {args.path} ({lines} lines, {EXTRACTOR})")
        return 0

    if sha256(text) == store.load(args.path).sha256:
        print(f"unchanged {args.path} ({lines} lines)")
        return 0

    if not args.refresh:
        print(
            f"CHANGED {args.path} — the source no longer matches what is stored.\n"
            f"  Re-run with --refresh to accept it. Doing so withdraws the reviews\n"
            f"  that were made against the old text.",
            file=sys.stderr,
        )
        return 1

    layers = load_rules(args.rules, strict=False)
    withdrawn = withdraw_reviews(
        args.path,
        layers=layers,
        log_path=args.log,
        note=f"source text refreshed {retrieved.isoformat()}",
    )
    store_document(store, args.path, args.url, text, retrieved=retrieved)
    print(f"refreshed {args.path} ({lines} lines)")
    for entry in withdrawn:
        print(f"  withdrew {entry.layer} {entry.zone} {entry.field} (was {entry.reviewer})")
    if withdrawn:
        print(f"  {len(withdrawn)} value(s) need re-reading against the new text")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
