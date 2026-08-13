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

A jurisdiction declares the documents its rules are read from, so the usual
form takes no arguments beyond the jurisdiction::

    python -m flats.provenance.fetch --layer or/multnomah/fairview
    python -m flats.provenance.fetch --all --check     # sweep the corpus for drift

Which URL serves the ordinance text rather than a landing page is knowledge
somebody worked out once by trying four of them; kept in a shell history it is
lost, and nothing can re-fetch the corpus to watch it for amendments.

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
from dataclasses import dataclass
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
from flats.rules.model import CodeDocument, Layer

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


def fetch_one(
    path: str,
    url: str,
    *,
    store: ProvenanceStore,
    start: str = "",
    end: str = "",
    nth: int = 1,
    refresh: bool = False,
    check: bool = False,
    allow_thin: bool = False,
    retrieved: date | None = None,
    rules: Path | None = None,
    log: Path | None = None,
    get: Callable[[str], bytes | str] | None = None,
) -> int:
    """Store one document, or report why it was not stored.

    Returns 0 when the store now holds what the source serves, 1 otherwise —
    including the case where the source changed and nobody has accepted it,
    which is the point of the command rather than a failure of it.
    """
    strategy = ""
    if get is None:
        try:
            got = fetch_source(url)
        except FetchFailed as exc:
            print(f"{path}: {exc}", file=sys.stderr)
            return 1
        strategy = got.strategy

        def get(_url: str, _content: bytes = got.content) -> bytes:
            return _content

    try:
        text = fetch_text(url, get=get, start=start, end=end, nth=nth)
    except ProvenanceError as exc:
        print(f"{path}: {exc}", file=sys.stderr)
        return 1

    problem = implausible(text)
    if problem and not allow_thin:
        # Refusing costs one re-run with a better URL. Storing costs a reviewer
        # signing a nav bar, and nothing downstream would ever notice.
        print(f"{path}: refused — {problem}", file=sys.stderr)
        print("  Nothing was stored. Check that the URL serves the chapter text", file=sys.stderr)
        print("  itself rather than a landing page; --allow-thin overrides this,", file=sys.stderr)
        print("  but only after somebody has read the document.", file=sys.stderr)
        return 1

    authority = authority_for(url)
    if authority is not Authority.official:
        print(
            f"note: {authority.value} source — a lead, not evidence. No value citing "
            f"this may be verified.",
            file=sys.stderr,
        )
    if strategy and strategy != "plain":
        print(f"note: needed browser impersonation ({strategy})", file=sys.stderr)

    retrieved = retrieved or date.today()
    lines = len(text.splitlines())
    if start and lines < SHORT_SLICE:
        # Almost always a marker that matched the table of contents instead of
        # the section. Storing it would give every quote into this document
        # line numbers that point at an index entry.
        print(f"warning: {path} sliced to {lines} line(s) — check --start/--nth", file=sys.stderr)

    if not store.exists(path):
        if check:
            print(f"MISSING {path} — declared but never fetched", file=sys.stderr)
            return 1
        store_document(store, path, url, text, retrieved=retrieved)
        print(f"stored {path} ({lines} lines, {EXTRACTOR})")
        return 0

    if sha256(text) == store.load(path).sha256:
        print(f"unchanged {path} ({lines} lines)")
        return 0

    if not refresh:
        print(
            f"CHANGED {path} — the source no longer matches what is stored.\n"
            f"  Re-run with --refresh to accept it. Doing so withdraws the reviews\n"
            f"  that were made against the old text.",
            file=sys.stderr,
        )
        return 1

    layers = load_rules(rules or CONFIG_ROOT, strict=False)
    withdrawn = withdraw_reviews(
        path,
        layers=layers,
        log_path=log or LOG_PATH,
        note=f"source text refreshed {retrieved.isoformat()}",
    )
    store_document(store, path, url, text, retrieved=retrieved)
    print(f"refreshed {path} ({lines} lines)")
    for entry in withdrawn:
        print(f"  withdrew {entry.layer} {entry.zone} {entry.label} (was {entry.reviewer})")
    if withdrawn:
        print(f"  {len(withdrawn)} value(s) need re-reading against the new text")
    return 0


def declared(layers: dict[str, Layer], only: str = "") -> list[tuple[Layer, str, CodeDocument]]:
    """Every declared document, as (layer, store path, document).

    ``only`` filters by layer id prefix, so a county and its cities come back
    together — which is how encoding work is actually scoped.
    """
    out = []
    for layer_id in sorted(layers):
        if only and not layer_id.startswith(only):
            continue
        layer = layers[layer_id]
        for path, doc in sorted(layer.documents().items()):
            out.append((layer, path, doc))
    return out


@dataclass(frozen=True, slots=True)
class Evidence:
    """Three sets that ought to agree, and the ways they do not.

    *Declared* is what a jurisdiction says its rules come from. *Stored* is what
    is on disk. *Cited* is what values actually point at. Each mismatch is a
    different job, and lumping them into one "coverage" number would hide which:

    ``undeclared``
        A value cites a document nobody declared, so nothing will ever re-fetch
        it and an amendment to it will pass unnoticed. The worst of the three,
        because everything looks fine.
    ``unfetched``
        Declared and never stored. Ordinary work: run the fetch.
    ``uncited``
        Stored and cited by nothing. Usually a chapter fetched ahead of the
        encoding, occasionally a document whose values were deleted.
    """

    declared: frozenset[str] = frozenset()
    stored: frozenset[str] = frozenset()
    cited: frozenset[str] = frozenset()

    @property
    def undeclared(self) -> tuple[str, ...]:
        return tuple(sorted(self.cited - self.declared))

    @property
    def unfetched(self) -> tuple[str, ...]:
        return tuple(sorted(self.declared - self.stored))

    @property
    def uncited(self) -> tuple[str, ...]:
        return tuple(sorted(self.stored - self.cited))

    @property
    def clean(self) -> bool:
        return not (self.undeclared or self.unfetched)

    def lines(self) -> list[str]:
        out = [
            f"evidence: {len(self.declared)} declared, "
            f"{len(self.stored)} stored, {len(self.cited)} cited"
        ]
        for path in self.undeclared:
            out.append(f"  UNDECLARED {path} — cited by a value, watched by nothing")
        for path in self.unfetched:
            out.append(f"  UNFETCHED  {path} — declared, never stored")
        for path in self.uncited:
            out.append(f"  uncited    {path} — stored, no value points at it")
        return out


def evidence(layers: dict[str, Layer], store: ProvenanceStore) -> Evidence:
    """Reconcile declared, stored and cited documents across the hierarchy."""
    declared_paths = {path for _, path, _ in declared(layers)}
    stored = {p for p in store.documents() if p.endswith('.txt')}
    cited = set()
    for layer in layers.values():
        blocks = [layer.defaults, *(z.values for z in layer.zones.values())]
        for values in blocks:
            for value in values.values():
                for part in (value, *value.variants):
                    quote = part.prov.quote or ""
                    if quote:
                        cited.add(quote.split("#", 1)[0])
        for zone in layer.zones.values():
            if zone.like is not None and zone.like.prov.quote:
                cited.add(zone.like.prov.quote.split("#", 1)[0])
    return Evidence(frozenset(declared_paths), frozenset(stored), frozenset(cited))


def main(argv: Sequence[str] | None = None, *, get: Callable[[str], bytes | str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="flats-fetch", description="Store the code text a rule value will cite."
    )
    parser.add_argument(
        "path", nargs="?", help="store path, e.g. or/multnomah/portland/33.110.txt"
    )
    parser.add_argument("url", nargs="?")
    parser.add_argument(
        "--layer",
        default="",
        help="fetch everything this jurisdiction declares under `code:` "
        "(a prefix, so a county brings its cities)",
    )
    parser.add_argument(
        "--all", action="store_true", help="fetch every declared document in the hierarchy"
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="reconcile declared, stored and cited documents without fetching anything",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="report drift without storing anything — the corpus watch",
    )
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
    retrieved = date.fromisoformat(args.retrieved) if args.retrieved else date.today()

    if args.audit:
        report = evidence(load_rules(args.rules, strict=False), store)
        for line in report.lines():
            print(line)
        return 0 if report.clean else 1

    if args.layer or args.all:
        if args.path or args.url:
            parser.error("give a path and url, or --layer/--all — not both")
        return _fetch_declared(args, store=store, retrieved=retrieved, get=get)
    if not (args.path and args.url):
        parser.error("give a path and url, or --layer/--all")

    return fetch_one(
        args.path,
        args.url,
        store=store,
        start=args.start,
        end=args.end,
        nth=args.nth,
        refresh=args.refresh,
        check=args.check,
        allow_thin=args.allow_thin,
        retrieved=retrieved,
        rules=args.rules,
        log=args.log,
        get=get,
    )


def _fetch_declared(args, *, store: ProvenanceStore, retrieved: date, get) -> int:
    """Work through what the jurisdictions declare.

    One bad document does not stop the sweep. The whole point of a corpus watch
    is the report at the end, and a run that halts on the first 403 tells you
    about one city instead of eighty.
    """
    layers = load_rules(args.rules, strict=False)
    targets = declared(layers, "" if args.all else args.layer)
    if not targets:
        scope = "the hierarchy" if args.all else f"{args.layer!r}"
        print(f"no documents declared under {scope} — add a `code:` block", file=sys.stderr)
        return 1

    failed = []
    for layer, path, doc in targets:
        code = fetch_one(
            path,
            doc.url,
            store=store,
            start=doc.start,
            end=doc.end,
            nth=doc.nth,
            refresh=args.refresh,
            check=args.check,
            allow_thin=doc.allow_thin or args.allow_thin,
            retrieved=retrieved,
            rules=args.rules,
            log=args.log,
            get=get,
        )
        if code:
            failed.append(path)

    print(f"\n{len(targets) - len(failed)}/{len(targets)} document(s) current")
    for path in failed:
        print(f"  needs attention: {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
