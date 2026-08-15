"""Which page of the book a stored line came from.

A citation is evidence only if somebody outside this system can check it. The
store already keeps the text verbatim and quotes it by line, which is enough to
audit an encoding against its source — but a line number is an artefact of our
extraction. Nobody can take "line 3,041 of 4.0100.residential.txt" to a planner,
an architect or opposing counsel. They can take "page 4-12 of the Gresham
Development Code", and read the same sentence off the same sheet.

So each PDF-backed document gets a sidecar mapping line numbers to pages: the
PDF page, which is what a viewer's ``#page=`` fragment opens, and the printed
page label where the sheet carries one, which is what a citation says out loud.

The map is *derived*, never guessed. The document is fetched again and extracted
page by page with the same extractor that produced the stored text, and the two
line sequences are walked in lockstep. Where they diverge the map is refused
rather than approximated: a page number that is off by one is worse than none,
because it sends somebody to the wrong sheet with our name on it.

HTML sources have no pages and get no sidecar. Their addressable unit is the
section anchor, which their citations already carry.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from flats.provenance.store import ProvenanceError, ProvenanceStore

#: How the four codifiers in this corpus print a page number, measured from
#: their own footers rather than guessed:
#:
#:   Gresham       ``[4.0100]-2``        section in brackets, then the page
#:   Oregon City   ``(Oregon City 1/07) 232 - 12``   chapter and page, spaced
#:   Tualatin      ``TDC49:1Supp. No. 4``            Municode chapter:page
#:   Rivergrove    ``22``                            a bare number
#:
#: Only ever read from the first and last few lines of a page, which is where
#: furniture lives. A bare number in the body of a table is a standard, and
#: reading it as a page would be the exact failure this module exists to avoid.
_LABELS = (
    # A Municode chapter:page stamp, which runs into the supplement note.
    re.compile(r"^(?P<label>[A-Z]{2,6}[0-9]{1,4}:[0-9]{1,4})"),
    # A dashed or bracketed page, at either end of the line.
    re.compile(r"(?P<label>\[?[0-9A-Z.]{1,10}\]?\s*-\s*[0-9]{1,4})\s*$"),
    # A bare page, alone on its line.
    re.compile(r"^(?:page\s+)?(?P<label>[0-9]{1,4})$", re.I),
    # "Page 3 of 44" — the page is the first of the two.
    re.compile(r"^page\s+(?P<label>[0-9]{1,4})\s+of\s+[0-9]{1,4}$", re.I),
    # "28-5 (Oregon City 4/01)" — page first, then the supplement stamp.
    re.compile(r"^(?P<label>[0-9A-Z.]{1,10}-[0-9]{1,4})\s*\("),
    # "9 Oregon City Supp. No. 31" — the same book, numbered the other way on
    # the pages a supplement replaced. Both are printed; both are quotable.
    re.compile(r"^(?P<label>[0-9]{1,4})\s+[A-Z][A-Za-z ]{2,30}Supp"),
)

#: Runs of whitespace inside a label. Several of these documents are
#: letter-spaced, so the printed "232-12" arrives as "232 - 12".
_SPACING = re.compile(r"\s+")

#: How many lines at each end of a page to read as furniture.
_FURNITURE = 3


@dataclass(frozen=True, slots=True)
class Page:
    """One page of the source document, and where it starts in the stored text."""

    n: int
    line: int
    label: str = ""

    @property
    def cite(self) -> str:
        """How to say this page to somebody holding the document.

        The printed label when the sheet carries one — that is what a code
        cites and what a planner will look for — and the PDF page otherwise.
        """
        return f"p. {self.label}" if self.label else f"PDF page {self.n}"


@dataclass(frozen=True, slots=True)
class PageIndex:
    """The pages of one stored document, in line order."""

    path: str
    sha256: str
    extractor: str
    pages: tuple[Page, ...]
    #: SHA-256 of the PDF the map was built from. What lets a viewer prove the
    #: book it is about to show page 239 of is the book page 239 was counted in.
    source_sha256: str = ""

    def at(self, line: int) -> Page | None:
        """The page a line sits on.

        Linear from the back rather than bisected: a chapter is a few hundred
        pages and this runs once per review card. Clarity is worth more here
        than the microseconds.
        """
        found = None
        for page in self.pages:
            if page.line > line:
                break
            found = page
        return found

    def span(self, start: int, end: int) -> list[Page]:
        """Every page a quoted span touches.

        A table that straddles a page break is the normal case, not an edge
        one, and a citation naming only the first page sends a reader to a
        sheet that does not carry half the numbers.
        """
        out = [p for p in self.pages if start <= p.line <= end]
        first = self.at(start)
        if first and (not out or out[0].n != first.n):
            out.insert(0, first)
        return out


def _label(lines: Sequence[str]) -> str:
    """The printed page label, from the furniture at either end of a page.

    Footers first. A header often repeats the chapter number, which matches the
    same shapes and would put "4.0100" where the page belongs.
    """
    edges = [line.strip() for line in lines[-_FURNITURE:] + lines[:_FURNITURE]]
    for line in edges:
        # Letter-spaced scans print "232 - 12" as "2 3 2 - 1 2", so the
        # de-spaced form is tried as well as the literal one. Oregon City's
        # whole code is such a scan: on the literal line alone, 463 of its 466
        # pages come back unlabelled.
        for text in (line, _SPACING.sub("", line)):
            for pattern in _LABELS:
                if found := pattern.search(text):
                    return _SPACING.sub("", found.group("label"))
    return ""


def _pages_of(data: bytes, *, extraction: str) -> list[list[str]]:
    """The document's text, one list of lines per page.

    Deliberately the same call the store's extraction makes, page by page
    instead of joined: a map built by a second implementation would be a map of
    a document nobody stored.
    """
    from io import BytesIO

    from pypdf import PdfReader

    mode = {} if extraction == "plain" else {"extraction_mode": "layout"}
    out = []
    for page in PdfReader(BytesIO(data)).pages:
        if "/Contents" not in page:
            out.append([])
            continue
        text = (page.extract_text(**mode) or "").replace("\r\n", "\n")
        out.append([line.rstrip() for line in text.split("\n")])
    return out


def index(path: str, data: bytes, text: str, *, extraction: str = "layout") -> PageIndex:
    """Map a stored document's lines onto the pages of its source.

    The stored text is the extraction with blank runs collapsed, page furniture
    kept and — where a document is declared with markers — sliced to a chapter.
    None of that touches the *sequence of non-empty lines*, which is why the two
    can be walked together: every non-empty line of the store appears in the
    per-page extraction, in order, once.

    Raises when they diverge. That means the source has been amended since the
    document was stored, and the honest response is to re-fetch it — which the
    store's own drift watch will already be saying — rather than to publish a
    map of a document that no longer exists.
    """
    stored = [(n, line) for n, line in enumerate(text.split("\n"), 1) if line.strip()]
    from_pdf: list[tuple[int, str]] = []
    furniture: dict[int, str] = {}
    for number, lines in enumerate(_pages_of(data, extraction=extraction), 1):
        kept = [line for line in lines if line.strip()]
        if not kept:
            continue
        furniture[number] = _label(kept)
        from_pdf += [(number, line) for line in kept]

    if not stored:
        raise ProvenanceError(f"{path}: the stored document is empty")

    # A declared slice means the store holds a chapter out of the middle of a
    # book, so the walk starts wherever that chapter starts. The markers cut at
    # a phrase rather than at a line break — Multnomah County's LR-7 chapter
    # starts at "39.4848  PURPOSE", mid-line — so the two ends of the slice are
    # matched as fragments and everything between them exactly.
    first = stored[0][1].strip()
    last = len(stored) - 1
    starts = [i for i, (_n, line) in enumerate(from_pdf) if first in line.strip()]
    for offset in starts:
        pages: list[Page] = []
        seen: set[int] = set()
        for step, (line_no, line) in enumerate(stored):
            if offset + step >= len(from_pdf):
                break
            page, source = from_pdf[offset + step]
            edge = step in (0, last)
            matched = (
                line.strip() in source.strip() if edge else source.strip() == line.strip()
            )
            if not matched:
                break
            if page not in seen:
                seen.add(page)
                pages.append(Page(n=page, line=line_no, label=furniture.get(page, "")))
        else:
            from flats.provenance.books import fingerprint
            from flats.provenance.store import sha256

            return PageIndex(
                path=path,
                sha256=sha256(text),
                extractor="",
                pages=tuple(pages),
                source_sha256=fingerprint(data),
            )
    raise ProvenanceError(
        f"{path}: the stored text no longer matches what the source serves — "
        "re-fetch the document before mapping its pages"
    )


# --- the sidecar ---------------------------------------------------------


#: Codifiers that serve HTML. Named rather than inferred from the URL suffix,
#: because Municode's PDF download endpoint is
#: "api.municode.com/PublicationPdfDownload/1818" — no suffix at all — and
#: filtering on ".pdf" would silently drop two of the corpus's ten books.
_HTML_HOSTS = ("ecode360.com", "codepublishing.com", "public.law", "clackamas.us")


def _is_html(url: str) -> bool:
    return any(host in url.lower() for host in _HTML_HOSTS)


def sidecar(store: ProvenanceStore, path: str) -> Path:
    return store.text_path(f"{path}.pages.json")


def write(store: ProvenanceStore, page_index: PageIndex, *, extractor: str) -> None:
    """Write a document's page map beside it."""
    sidecar(store, page_index.path).write_text(
        json.dumps(
            {
                "sha256": page_index.sha256,
                "extractor": extractor,
                **(
                    {"source_sha256": page_index.source_sha256}
                    if page_index.source_sha256
                    else {}
                ),
                "pages": [
                    {"n": p.n, "line": p.line, **({"label": p.label} if p.label else {})}
                    for p in page_index.pages
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="",
    )


def read(store: ProvenanceStore, path: str) -> PageIndex | None:
    """A document's page map, or None where it has none or has moved on.

    A map is bound to the exact text it was built from. If the document has
    been re-fetched since, the line numbers in the map are numbers in a text
    that no longer exists, and returning them would put a confident page number
    against the wrong sentence. Silence is the correct answer until somebody
    re-runs the mapper.
    """
    file = sidecar(store, path)
    if not file.is_file():
        return None
    try:
        raw = json.loads(file.read_text(encoding="utf-8"))
        document = store.load(path)
    except (json.JSONDecodeError, OSError, ProvenanceError):
        return None
    if raw.get("sha256") != document.sha256:
        return None
    return PageIndex(
        path=path,
        sha256=raw["sha256"],
        extractor=raw.get("extractor", ""),
        source_sha256=raw.get("source_sha256", ""),
        pages=tuple(
            Page(n=p["n"], line=p["line"], label=p.get("label", "")) for p in raw["pages"]
        ),
    )


# --- the command ---------------------------------------------------------


def main(argv: Sequence[str] | None = None, *, get: Callable[[str], bytes] | None = None) -> int:
    """Build the page map for every declared PDF document.

    Run after a fetch. Nothing else depends on it: a document with no map keeps
    working exactly as before, quoting by line and linking to its URL, and the
    review pages simply do not offer a page number for it.
    """
    import argparse

    from flats.provenance.fetch import declared, fetch_source
    from flats.rules.loader import load_rules

    parser = argparse.ArgumentParser(prog="python -m flats.provenance.pages")
    parser.add_argument("--only", default="", help="layer id prefix, e.g. or/multnomah")
    parser.add_argument("--check", action="store_true", help="report, write nothing")
    args = parser.parse_args(argv)

    store = ProvenanceStore()
    mapped = skipped = failed = 0
    for layer, path, document in declared(load_rules(strict=False), only=args.only):
        if not store.exists(path):
            continue
        if _is_html(document.url):
            # Decided before fetching, not after. Half this corpus is served by
            # three HTML codifiers that rate-limit, and pulling a chapter from
            # them to conclude it has no pages spends their patience to learn
            # something the URL already said.
            skipped += 1
            continue
        try:
            data = get(document.url) if get else fetch_source(document.url).content
        except Exception as exc:  # noqa: BLE001 — every fetch failure reads the same here
            print(f"{path}: could not fetch — {exc}", file=sys.stderr)
            failed += 1
            continue
        if data[:5] != b"%PDF-":
            skipped += 1
            continue
        try:
            built = index(
                path, data, store.load(path).text, extraction=document.extraction
            )
        except ProvenanceError as exc:
            print(str(exc), file=sys.stderr)
            failed += 1
            continue
        labelled = sum(1 for p in built.pages if p.label)
        print(
            f"{path}: {len(built.pages)} page(s), {labelled} with a printed label"
            + ("" if not args.check else " (not written)")
        )
        if not args.check:
            write(store, built, extractor=store.load(path).extractor)
            # The bytes are already here and the review pages will want them.
            # Fetching a 40 MB book a second time to show a page out of it is
            # a rude thing to do to a city's web server.
            from flats.provenance.books import save as cache_book

            cache_book(document.url, data)
        mapped += 1
    print(f"{mapped} mapped, {skipped} not a PDF, {failed} unmapped")
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
