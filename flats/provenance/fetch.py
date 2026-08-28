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
import logging
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
#:
#: /7 separates a superscript footnote marker from the value it sits on. See
#: `_SUP_RUN`.
EXTRACTOR = "flats-html-text/7"
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

#: What an <ol> is called when it is a trail of links rather than a list of
#: provisions. Numbering one puts "1 OAR", "2 Chap. 660" above the text of a
#: rule and pushes every line under it down, so the shape has to be recognised
#: on the way past -- once the tags are gone there is nothing left to tell a
#: breadcrumb from a list.
_NAV_HINT = re.compile(r"breadcrumb|navigation|\bnav\b|\bmenu\b|\btoc\b|pagination|pager")


def _navigation(attrs: Sequence[tuple[str, str | None]]) -> bool:
    return any(
        name in ("class", "id", "role") and value and _NAV_HINT.search(value.lower())
        for name, value in attrs
    )

#: eCode360 stamps the day you printed the page into the page. Seven documents
#: in this corpus come from it, and every one of them reported CHANGED against
#: the store on any day but the day it was fetched — a watch that cries wolf
#: daily is a watch nobody reads, and accepting those refreshes would have
#: withdrawn real reviews over a date.
#:
#: Replaced rather than removed, because every citation in this system is a
#: line number. Dropping the line lifts 4,700 lines by one in a single document
#: and silently re-points every quote below it.
_PRINT_DATE = re.compile(
    r"^(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day, "
    r"(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December) \d{1,2}, \d{4}$"
)
#: Where the codifier's furniture lives — print controls, masthead, date. A
#: standards page whose first twenty lines are a bare date does not exist, and
#: confining the rule to the header keeps it from ever eating an effective date
#: printed inside a section.
HEADER_LINES = 20
#: What stands in its place. Says what was there, so a reviewer wondering where
#: the date went is not left to guess.
PRINT_DATE_MARK = "[print date]"


#: Newlines inside a block are HTML formatting, not text, and the two markers
#: this module writes into the stream are its own — a page that shipped either
#: one as content would rewrite the geometry it claims to describe.
_CONTROL = re.compile(r"[\r\n\x00\x01]")

#: What a superscript footnote marker holds: one number, or a run of them.
#:
#: `<sup>` is inline, so until /7 its digits were concatenated straight onto
#: the text in front of them and the boundary the codifier drew was gone.
#: Clackamas County's Table 1015-2 requires `1` parking space per quadplex
#: dwelling under footnote 3, and the store held `13`. Happy Valley's parking
#: maximums, `1.2` and `2.0` under footnote 4, were held as `1.24` and `2.04`.
#: A reader cannot recover the boundary from those, and nothing downstream
#: knew it was missing: the marker readers in `flats/encode/footnotes.py` are
#: anchored to a unit ("45 feet2") or to a permission code ("P7,8"), so a bare
#: numeric cell lost its value AND its marker in one move.
#:
#: Brackets, because `BRACKET_MARKER` already reads them, they are inline so
#: no citation's line number moves, and `1[3]` cannot be read as thirteen.
#: Only a bare run of digits is bracketed -- Wood Village writes its markers
#: as `<sup>(2)</sup>` and those already survive as `(2)`. Nothing in this
#: corpus uses a superscript for an exponent; 624 of them are footnotes.
_SUP_RUN = re.compile(r"\s*\d{1,2}(?:\s*,\s*\d{1,2})*\s*")

#: A block boundary *inside* a table cell — Gladstone's requirement cells hold
#: two paragraphs, "20 ft" and "10 ft within Gladstone Town Center". Joined
#: with a space the cell states two numbers on one line and the pair reader
#: refuses it, which loses the base standard entirely. The mark is a space
#: everywhere the geometry is kept and a line break where it is given up.
_CELL_BLOCK = "\x01"

#: Widest a rendered table line may run. A zoning table is a dozen short
#: cells; a "table" wider than this is page layout wearing table markup, and
#: gridding it would weld navigation junk into kilometer lines.
_GRID_LINE_MAX = 400


class _Table:
    """One <table>'s cells, collected and rendered as an aligned grid.

    Text extraction is where table geometry dies: Wood Village's Table 220-3
    linearises into type labels over ragged value runs no reader can
    attribute, and ZDO 315-2's one merged setback cell speaks for nine zones
    the flat text no longer names. Rendering rows as aligned columns — with a
    spanned cell's text repeated in every column it covers — keeps the
    geometry in plain text, where the column-aware readers and a human
    reviewer see the same thing.
    """

    def __init__(self) -> None:
        self.rows: list[list[tuple[str, int, int]]] = []
        self.caption: list[str] = []
        self._row: list[tuple[str, int, int]] | None = None
        self._cell: list[str] | None = None
        self._colspan = 1
        self._rowspan = 1

    def open_row(self) -> None:
        self.close_row()
        self._row = []

    def open_cell(self, attrs) -> None:
        self.close_cell()
        if self._row is None:
            self._row = []
        got = {name: value for name, value in attrs if value is not None}

        def span(name: str) -> int:
            try:
                return max(1, min(int(got.get(name, "1")), 30))
            except ValueError:
                return 1

        self._colspan = span("colspan")
        self._rowspan = span("rowspan")
        self._cell = []

    def data(self, text: str) -> None:
        if self._cell is not None:
            self._cell.append(text)
        elif text.strip():
            # Text inside the table but outside any cell — a <caption>,
            # which usually carries the table's number and name.
            self.caption.append(text)

    def close_cell(self) -> None:
        if self._cell is not None and self._row is not None:
            blocks = [
                " ".join(part.split())
                for part in "".join(self._cell).split(_CELL_BLOCK)
            ]
            text = _CELL_BLOCK.join(part for part in blocks if part)
            self._row.append((text, self._colspan, self._rowspan))
        self._cell = None

    def close_row(self) -> None:
        self.close_cell()
        if self._row is not None:
            self.rows.append(self._row)
        self._row = None

    def render(self) -> str:
        self.close_row()
        grid: list[list[str]] = []
        carry: dict[int, tuple[str, int]] = {}
        for cells in self.rows:
            row: dict[int, str] = {c: t for c, (t, _n) in carry.items()}
            carry = {c: (t, n - 1) for c, (t, n) in carry.items() if n > 1}
            col = 0
            for text, colspan, rowspan in cells:
                while col in row:
                    col += 1
                for i in range(colspan):
                    row[col + i] = text
                    if rowspan > 1:
                        carry[col + i] = (text, rowspan - 1)
                col += colspan
            width = max(row) + 1 if row else 0
            grid.append([row.get(i, "") for i in range(width)])
        caption = " ".join(" ".join(self.caption).replace(_CELL_BLOCK, " ").split())
        cols = max((len(r) for r in grid), default=0)
        flat = [[c.replace(_CELL_BLOCK, " ") for c in r] for r in grid]
        widths = [max((len(r[i]) for r in flat if i < len(r)), default=0) for i in range(cols)]
        if len(grid) < 2 or cols < 2 or sum(widths) + 2 * cols > _GRID_LINE_MAX:
            # Not tabular (or too wide to be) — flow the cells as block
            # lines, which is what the extractor always did with them. Nothing
            # here is aligned any more, so a cell's own paragraphs become
            # lines too rather than one run-on line.
            body = "\n".join(
                part for r in grid for c in r for part in c.split(_CELL_BLOCK) if part
            )
        else:
            body = "\n".join(
                "  ".join(
                    (r[i] if i < len(r) else "").ljust(widths[i]) for i in range(cols)
                ).rstrip()
                for r in flat
            )
        return f"{caption}\n{body}" if caption else body


class _Extractor(html.parser.HTMLParser):
    """Tags out, text kept, block elements broken onto their own lines."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0
        self._tables: list[_Table] = []
        #: One counter per open <ol>, so a nested list restarts and its parent
        #: resumes. ``None`` where the list is site navigation rather than a
        #: list of provisions. See `handle_starttag`.
        self._ordinals: list[int | None] = []
        #: Depth of open <nav> elements. A breadcrumb is an <ol> and reads
        #: exactly like one; what tells them apart is where it sits.
        self._nav = 0
        #: Text collected inside an open <sup>, held back until the tag
        #: closes because whether it is a footnote marker or ordinary
        #: superscript text is not knowable until it has all arrived.
        self._sup: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "sup":
            if not self._skip and self._sup is None:
                self._sup = []
            return
        if self._sup is not None and (tag in _BLOCK or tag in _DROP):
            # A <sup> that never closed. Give back what it collected rather
            # than swallowing the rest of the document into a marker.
            self._end_sup(marker=False)
        self._open(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag == "sup":
            if self._sup is not None:
                self._end_sup(marker=True)
            return
        if self._sup is not None and (tag in _BLOCK or tag in _DROP):
            self._end_sup(marker=False)
        self._close(tag)

    def _end_sup(self, *, marker: bool) -> None:
        text = "".join(self._sup or ())
        self._sup = None
        if marker and _SUP_RUN.fullmatch(text):
            text = "[" + ",".join(p.strip() for p in text.split(",") if p.strip()) + "]"
        self._emit(text)

    def _emit(self, text: str) -> None:
        if self._tables:
            self._tables[-1].data(text)
        else:
            self.parts.append(text)

    def _open(self, tag: str, attrs) -> None:
        if tag in _DROP:
            self._skip += 1
        elif tag == "table":
            self._tables.append(_Table())
        elif self._tables:
            table = self._tables[-1]
            if tag == "tr":
                table.open_row()
            elif tag in ("td", "th"):
                table.open_cell(attrs)
            elif tag in _BLOCK:
                table.data(_CELL_BLOCK)
        elif tag == "nav":
            self._nav += 1
            self.parts.append("\n")
        elif tag == "ol":
            # A breadcrumb trail is an <ol>. The Oregon Legislature and the
            # Secretary of State both publish one at the top of every rule --
            # "OAR / Chap. 660 / Division 46 / Rule 660-046-0220" -- and
            # numbering it invents provisions 1 through 5 above the text of
            # the law and pushes every line below it down by two. That is the
            # same silent re-pointing the prefix rule below exists to avoid,
            # arriving through a different door.
            self._ordinals.append(None if self._nav or _navigation(attrs) else 0)
            self.parts.append("\n")
        elif tag == "li" and self._ordinals and None not in self._ordinals:
            # An ordered list keeps its numbers in the browser, not in the
            # text: <ol><li>The minimum lot size standards apply...</li> shows
            # as "1." on the page and arrives here with nothing to say which
            # note it is. Clackamas County writes every Table 315-2 footnote
            # that way -- 305 markers in ZDO 315 pointed at bodies that had
            # been stripped of the only thing tying them to a marker.
            #
            # Written as a prefix on the line the item already occupies rather
            # than a line of its own, because every citation in this system is
            # a line number: a new line here would lift every quote below it in
            # the document and silently re-point them.
            #
            # Only outside a table. A <td> holding a list collapses to one
            # cell line, so numbering there would inject "1 2 3" into a grid
            # row and cost more than the omission does.
            count = self._ordinals[-1]
            assert count is not None
            self._ordinals[-1] = count + 1
            self.parts.append(f"\n{count + 1} ")
        elif tag in _BLOCK:
            self.parts.append("\n")

    def _close(self, tag: str) -> None:
        if tag in _DROP:
            self._skip = max(0, self._skip - 1)
        elif tag == "table" and self._tables:
            rendered = self._tables.pop().render()
            if self._tables:
                # A nested table is layout, not data — flatten it into the
                # enclosing cell so the outer grid stays one line per row.
                self._tables[-1].data(" " + " ".join(rendered.split()) + " ")
            else:
                # Sentinel-prefix each grid line so the whitespace collapse
                # below leaves column alignment alone — the runs of spaces
                # ARE the geometry.
                marked = "\n".join("\x00" + line for line in rendered.split("\n"))
                self.parts.append("\n" + marked + "\n")
        elif self._tables:
            table = self._tables[-1]
            if tag in ("td", "th"):
                table.close_cell()
            elif tag == "tr":
                table.close_row()
            elif tag in _BLOCK:
                table.data(_CELL_BLOCK)
        elif tag == "nav":
            self._nav = max(0, self._nav - 1)
            self.parts.append("\n")
        elif tag == "ol":
            if self._ordinals:
                self._ordinals.pop()
            self.parts.append("\n")
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        # Newlines inside a block are HTML formatting, not text. Keeping
        # them would let a reflow of the markup renumber every quote line
        # in the document without a word of the law changing.
        clean = _CONTROL.sub(" ", data)
        if self._sup is not None:
            self._sup.append(clean)
            return
        self._emit(clean)


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
    lines = [
        # A grid line carries its geometry in its spaces — collapse them and
        # the columns the readers align on are gone. Everything else is prose,
        # where a run of whitespace is markup indentation.
        line[1:].rstrip() if line.startswith("\x00") else _SPACES.sub(" ", line).strip()
        for line in text.split("\n")
    ]
    for i, line in enumerate(lines[:HEADER_LINES]):
        if _PRINT_DATE.match(line):
            lines[i] = PRINT_DATE_MARK
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


#: What pypdf says, on a logger nobody was listening to, when layout mode
#: meets text the page rotates. It does not fail; it drops the text. Gresham
#: prints the column headers of its plan-district setback tables sideways, so
#: eleven columns of numbers reached the store with nothing naming them and no
#: error anywhere. Plain mode reads them.
_ROTATED = "rotated text"


class _Dropped(logging.Handler):
    """Counts the pages an extraction admitted it could not fully read."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.rotated = 0

    def emit(self, record: logging.LogRecord) -> None:
        if _ROTATED in record.getMessage().lower():
            self.rotated += 1


def pdf_to_text(
    data: bytes, *, extraction: str = "layout", lost: list[str] | None = None
) -> str:
    """Text out of a PDF, in reading order, one page after another.

    Oregon codifiers publish chapters as PDF — Portland's Title 33 among them —
    so this is not an edge case but the main path for the biggest jurisdiction
    in the state. Page furniture is left in: the running header carries the
    revision date, which is exactly the kind of change a hash should catch.

    ``extraction`` is declared per document (see CodeDocument): ``layout``
    keeps the horizontal geometry tables need; ``plain`` is for the PDFs whose
    font metrics make layout mode fuse words together — Tualatin's whole code
    reads "areasintheCity..." in layout mode and cleanly in plain.
    """
    from io import BytesIO

    from pypdf import PdfReader

    mode = {} if extraction == "plain" else {"extraction_mode": "layout"}
    reader = PdfReader(BytesIO(data))
    pages = []
    dropped = _Dropped()
    logger = logging.getLogger("pypdf")
    logger.addHandler(dropped)
    for page in reader.pages:
        if "/Contents" not in page:
            # A page with no content stream is a legal, genuinely blank page —
            # Tualatin's Development Code carries one. pypdf's layout mode
            # raises KeyError on it, which reads as a broken document when
            # nothing is actually missing. Only this measured case is skipped;
            # any other extraction failure still fails loud.
            pages.append("")
            continue
        pages.append((page.extract_text(**mode) or "").replace("\r\n", "\n"))
    logger.removeHandler(dropped)
    if lost is not None and dropped.rotated:
        lost.append(
            f"{dropped.rotated} page(s) carry rotated text that layout mode drops"
        )
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


def _to_text(
    raw: bytes | str, *, extraction: str = "layout", lost: list[str] | None = None
) -> str:
    """Whatever came back, reduced to the stored form."""
    if isinstance(raw, bytes):
        if raw[:5] == b"%PDF-":
            return pdf_to_text(raw, extraction=extraction, lost=lost)
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
    extraction: str = "layout",
    lost: list[str] | None = None,
) -> str:
    """Fetch a URL and reduce it to the stored form.

    ``lost`` collects what the extraction is known to have thrown away, so
    the caller can say so. Silence here is the failure it exists to prevent.
    """
    return slice_between(
        _to_text((get or _http_get)(url), extraction=extraction, lost=lost),
        start,
        end,
        nth=nth,
    )


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
    return store.save(
        path, url=url, text=text, retrieved=retrieved or date.today(), extractor=EXTRACTOR
    )


def fetch_one(
    path: str,
    url: str,
    *,
    store: ProvenanceStore,
    start: str = "",
    end: str = "",
    nth: int = 1,
    extraction: str = "layout",
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

    lost: list[str] = []
    try:
        text = fetch_text(
            url, get=get, start=start, end=end, nth=nth, extraction=extraction, lost=lost
        )
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

    bulky = _bulky(text, start, end)
    if bulky:
        print(f"note: {path} — {bulky}", file=sys.stderr)

    for note in lost:
        # Not a warning about formatting. Text the extraction dropped is text no
        # reviewer will ever see and no value can ever cite, and the drop is
        # silent: pypdf logs it and returns a document that looks complete.
        print(
            f"note: {path} — {note}. Declare `extraction: plain` on the `code:` "
            "entry if the rotated text is a table's column headers, which is what "
            "it usually is.",
            file=sys.stderr,
        )

    if extraction == "layout" and fused(text):
        print(
            f"note: {path} — extraction looks fused (words run together, "
            '"areasintheCity..."). No subject phrase can match fused text, so this '
            "document will corroborate nothing. Declare `extraction: plain` on the "
            "`code:` entry unless the chapter's tables matter more than its prose.",
            file=sys.stderr,
        )

    if not store.exists(path):
        if check:
            print(f"MISSING {path} — declared but never fetched", file=sys.stderr)
            return 1
        store_document(store, path, url, text, retrieved=retrieved)
        print(f"stored {path} ({lines} lines, {EXTRACTOR})")
        return 0

    stored = store.load(path)
    if sha256(text) == stored.sha256:
        if stored.extractor != EXTRACTOR and not check:
            # Same bytes, newer algorithm. Recording that is the whole point
            # of versioning the extractor: without it the document stays on
            # the re-extract list forever and the list stops being read.
            store_document(store, path, url, text, retrieved=retrieved)
            print(f"unchanged {path} ({lines} lines, re-stamped {EXTRACTOR})")
            return 0
        print(f"unchanged {path} ({lines} lines)")
        return 0

    if not refresh:
        # The line delta is the first thing a reviewer needs and the message
        # never said it. Every citation in this system is a line number, so
        # "same length" and "shifted by nine" are different sizes of problem:
        # the first can only have changed words, the second re-points quotes.
        was = len(stored.text.splitlines())
        moved = "same length" if was == lines else f"was {was} lines, now {lines}"
        print(
            f"CHANGED {path} — the source no longer matches what is stored ({moved}).\n"
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


#: Above this, a stored document is almost certainly a whole code rather than a
#: chapter. Not refused — a whole code is a real document and slicing it wrong
#: is worse than storing it — but said out loud, because the alternative is a
#: repository that quietly grows by several megabytes per jurisdiction and a
#: reviewer scrolling a thousand pages to check one setback.
BULKY_CHARS = 400_000


#: Alpha runs this long are almost never words; they are words fused together
#: by a layout-mode extraction that lost its spaces. Measured across the
#: corpus: clean documents sit at or under 0.003% of words, damaged ones at
#: 2.2% (Wilsonville) and 6.5% (Tualatin). The threshold splits that gap.
FUSED_RUN = 18
FUSED_RATIO = 0.005


def fused(text: str) -> bool:
    """Whether this extraction fused words together.

    The failure this catches is silent in the worst way: a fused document
    still carries its section numbers, so scope works, candidates simply never
    appear — which reads as "the code states nothing here" when the truth is
    "nothing could read it". Opposite conclusions, §15's distinction again.
    """
    words = re.findall(r"[A-Za-z]+", text)
    if not words:
        return False
    runs = sum(1 for w in words if len(w) >= FUSED_RUN)
    return runs / len(words) >= FUSED_RATIO


def _bulky(text: str, start: str, end: str) -> str:
    if len(text) < BULKY_CHARS or (start or end):
        return ""
    return (
        f"stored {len(text) // 1000:,}k characters unsliced — this looks like a whole "
        "code. `start:`/`end:` in the `code:` entry narrows it to the chapter, which "
        "keeps quotes readable and the store small."
    )


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
    #: Stored documents whose text came out of an older extraction algorithm.
    #: Not wrong — just not what today's reader would produce, so their line
    #: numbers and table shapes may differ from a fresh fetch of the same
    #: unamended page. Refetching one moves every quote into it, which is why
    #: this is reported rather than done.
    stale_extraction: frozenset[str] = frozenset()

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
    def outdated(self) -> tuple[str, ...]:
        return tuple(sorted(self.stale_extraction))

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
        for path in self.outdated:
            out.append(f"  re-extract {path} — stored by an older extractor than {EXTRACTOR}")
        return out


def evidence(layers: dict[str, Layer], store: ProvenanceStore) -> Evidence:
    """Reconcile declared, stored and cited documents across the hierarchy."""
    declared_paths = {path for _, path, _ in declared(layers)}
    stored = {p for p in store.documents() if p.endswith('.txt')}
    outdated = set()
    for path in stored:
        try:
            if store.load(path).extractor != EXTRACTOR:
                outdated.add(path)
        except ProvenanceError:
            continue
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
    return Evidence(
        frozenset(declared_paths), frozenset(stored), frozenset(cited), frozenset(outdated)
    )


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
    parser.add_argument(
        "--extraction",
        choices=("layout", "plain"),
        default="layout",
        help="layout keeps table geometry; plain is for PDFs whose layout "
        "extraction fuses words together",
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
        extraction=args.extraction,
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
            extraction=doc.extraction,
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
