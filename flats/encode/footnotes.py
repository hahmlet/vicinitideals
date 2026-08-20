"""Every footnote in every stored document, captured before anyone judges it.

A footnote is the cheapest way for a code to make a number mean something
other than what it says, and the most expensive thing for us to miss. Gresham
prints a maximum front setback of 30 feet on an arterial and 5 feet on a local
street as a note under the table; read the cell alone and the screen passes
lots the code would refuse. That failure is silent by construction -- the
citation resolves, the number is transcribed correctly, and nothing in the
value records that a marker was sitting next to it.

The reader in ``tables.py`` already sees markers, but only inside a table it
managed to parse, and only in service of extracting a candidate value. So a
footnote in a document whose grid defeated the parser is invisible, and a
footnote block whose numbering style the parser does not recognise degrades
into the placeholder "footnote 3 (text not captured)" -- which is honest and
still leaves nobody to tell.

This module does the other job: a census of the whole store. Every marker
occurrence and every footnote body in every stored document, captured
mechanically, with no judgement about relevance. Judgement comes later and is
recorded; capture is exhaustive and dumb, because anything not pulled here can
only ever be caught by a human reading that exact page, and humans read a
small fraction of encoded rules.

Capture that claims to be complete has to prove it, so the census reconciles
in both directions:

* a body nobody points at (``unmarked``) means the marker was lost in
  extraction -- a superscript that collapsed into the number beside it, or a
  cell the layout reader never emitted;
* a marker nothing defines (``unbodied``) means the block was lost, or sits in
  a document we do not hold.

Either way the document is *not reconciled*, and it is named. That turns "we
captured the footnotes" into "we captured them or the document is on a list",
which is a weaker claim and a checkable one. The residual risk -- a footnote
rendered in a way the extractor cannot see at all -- does not vanish, but it
stops being able to pass as complete.

Numbers restart at 1 under every table, so reconciliation is scoped to the
region a block governs: the run of lines between the previous block and this
one's heading. Reconciling per document instead would let table B's marker 1
be answered by table A's note 1, which under-reports orphans -- the unsafe
direction.

Run it::

    uv run python -m flats.encode.footnotes            # the whole store
    uv run python -m flats.encode.footnotes --layer or/multnomah/gresham
    uv run python -m flats.encode.footnotes --unreconciled
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

DOCS = Path(__file__).resolve().parents[1] / "provenance" / "docs"

#: A notes block announces itself. Tolerates the colspan repeat a caption cell
#: makes when it spans the grid -- "NOTES:  NOTES:" -- and the identifier
#: Gresham puts in front, "Table 4.0130 Notes:".
NOTES_HEAD = re.compile(
    r"^(?:table\s+[\w.-]+\s+)?(?:table\s+)?notes?\s*[:.]?"
    r"(?:\s+(?:table\s+[\w.-]+\s+)?(?:table\s+)?notes?\s*[:.]?)*$",
    re.I,
)

#: One numbered note *inside* a block, in any of the spellings codifiers use:
#: "1 Density calculations...", "2. Zero lot line dwellings...", "[3] Additional
#: height...", "(4) Townhomes are exempt...".
#:
#: A single space is enough here and is not enough outside a block. Happy
#: Valley writes "1 Density calculations shall be made pursuant to Section
#: 16.63.020(F)." with no period and no column gap, which the table reader's
#: stricter rule declines -- correctly, since outside a block that pattern
#: matches every numbered paragraph in the code. Being inside a block is what
#: earns the looser rule.
BLOCK_NOTE = re.compile(r"^\[?\(?(?P<n>\d{1,2})\)?\]?[.):]?\s+(?P<text>\S.*)$")

#: The lettered form, inside a block: Wilsonville's Table 8A runs A through P.
#: A letter earns far less benefit of the doubt than a digit does, because
#: every code in the corpus letters its ordinary subsections -- so this one
#: demands the punctuation a digit may omit. "A. Minimum lot size may be
#: reduced" is a note; "A minimum lot size of 5,000 square feet" is a
#: sentence, and only the period tells them apart. The space before it is
#: extraction's, not the codifier's: Wilsonville prints "F . Front porches".
LETTER_NOTE = re.compile(r"^\(?(?P<n>[A-Z])\)?\s?[.)]\s+(?P<text>\S.*)$")

#: A self-identifying note, which needs no block: Portland prints "[3] Additional
#: FAR and height may be allowed. See 33.110.265.F." under the table with no
#: heading over it.
BRACKET_NOTE = re.compile(r"^\[(?P<n>\d{1,2})\]\s+(?P<text>\S.*)$")

#: A headless run: the number, a column gap, and the text, with nothing
#: announcing it. Milwaukie prints its table notes this way. The gap is what
#: earns the reading -- an ordinary numbered paragraph is "1. The applicant
#: shall", one space and a period -- and the run is only believed where it
#: starts at 1 and ascends, which is checked in `_blocks` rather than here.
HEADLESS_NOTE = re.compile(r"^(?P<n>\d{1,2})\s{2,}(?P<text>\S.*)$")

#: The same run, parenthesised and glued: "(1)For commercial or residential
#: uses there is no minimum lot area, lot width or lot depth." Municode's HTML
#: renders a table's notes this way -- no heading over them, and the marker
#: welded to the first word.
#:
#: The weld is the whole discriminator, and it is a strong one. A codifier
#: writes its ordinary subsections with a space after the bracket -- "(1) Mixed
#: Use Development Requirement." -- so demanding *no* whitespace separates a
#: footnote body from every numbered paragraph in the code. Across the corpus
#: this shape appears on twenty lines in eight documents, and the run rule in
#: `_glued_paren_run` keeps all four of the stragglers out.
#:
#: Missing it cost real rules. Wood Village prints the whole townhouse standard
#: as note (2) under Table 210-3 -- 1,500 square feet, 20 feet of width, no
#: minimum depth -- and it was invisible while this shape was.
GLUED_PAREN_NOTE = re.compile(r"^\((?P<n>\d{1,2})\)(?!\s)(?P<text>\S.*)$")

#: The number on its own line, with the text beneath it. An HTML table renders
#: each cell as its own line, so a block that reads "1  Density calculations
#: shall be..." on the page arrives as "1", newline, "Density calculations
#: shall be...". Happy Valley's largest block is written this way and was
#: invisible until the shape was allowed -- twelve notes including one that
#: reduces a corner lot's front setback to eight feet on a local street, which
#: is precisely the kind of qualifier a screen must not miss.
STACKED_NOTE = re.compile(r"^\[?\(?(?P<n>\d{1,2})\)?\]?[.):]?$")

#: The same, lettered and on its own line. Punctuation is required here for
#: the same reason: a bare "A" on a line is a table cell in half the corpus.
STACKED_LETTER = re.compile(r"^\(?(?P<n>[A-Z])\)?\s?[.)]$")

#: What ends a block. A note runs onto the next line often enough that an
#: unrecognised line has to be read as continuation, so the block needs an
#: explicit floor: the codifier's amendment history, the next section, the next
#: table, or the running header.
ENDS_BLOCK = re.compile(
    r"^(?:\(Ord[.\s]|\(Added|§|Section\s+\d|Chapter\s+\d|Table\s+[\w.-]+"
    r"|\d{1,3}\.\d{2,4}(?:\.\d{1,4})?\s+[A-Z])",
    re.I,
)

#: A block cannot run forever. Past this the "unrecognised line continues the
#: previous note" rule is doing more harm than good, and whatever we are
#: reading is not a notes block any more.
BLOCK_LIMIT = 80

#: A marker glued to the unit, which is what a PDF superscript becomes when
#: extraction loses its baseline: "45 feet2", "35 ft.12", "20,000 sq. ft.1".
#: Codes write runs of them -- "20 feet7,8,9,10,11" -- and each number in the
#: run is its own marker.
#:
#: Anchored to the end of the cell, which is not fussiness. Extraction
#: sometimes leaves a row's cells separated by a single space -- Oregon City's
#: height row arrives as "All 65 feet 60 feet 50 feet" -- and an unanchored
#: rule reads each cell's number as a marker on the cell before it. That one
#: relaxation invented 76 markers in a single document.
GLUED_MARKER = re.compile(
    r"(?:sq\.?\s*ft\.?|sf|ft\.|feet|percent|%)\s?(?P<n>\d{1,2}(?:,\s?\d{1,2})*)$",
    re.I,
)

#: The parenthesised form, as Wood Village prints it: "10 ft(1)".
PAREN_MARKER = re.compile(
    r"(?:sq\.?\s*ft\.?|sf|ft\.?|feet|percent|%)\s?\((?P<n>\d{1,2})\)$", re.I
)

#: The parenthesised form with no unit in front of it, which is what a marker
#: on a row *label* or on a wordless cell looks like: "Minimum Lot Size(1)",
#: "None(2)", "Minimum Landscape Required(2)". `PAREN_MARKER` cannot see these
#: because it is anchored to a unit, and half of Wood Village's Table 230-2 is
#: written without one.
#:
#: Narrow the same way `LABEL_MARKER` is: the bracket must be welded to the
#: cell's last character. What that still lets through is a code citation --
#: "Subject to TDC 40.300(4)" -- so `PAREN_CITATION` is subtracted first.
PAREN_LABEL_MARKER = re.compile(r"(?<=[0-9a-z%)])\((?P<n>\d{1,2})\)\s*$", re.I)

#: A parenthesised subsection on the end of a cross-reference: "TDC 40.300(4)",
#: "ORS 455.315(2)", "Section 8.0117(C)(3)", "Figure 4.0420(  I)(1)". The
#: dotted section number is what tells them from a marker; the whitespace
#: inside the brackets is extraction's, not the codifier's.
PAREN_CITATION = re.compile(
    r"\d{1,3}\.\d{2,4}(?:\.\d{1,4})?(?:\(\s*[A-Za-z0-9]{1,3}\s*\))+"
)

#: The bracketed form, anywhere on a line: "30 ft. [3]".
BRACKET_MARKER = re.compile(r"\[(?P<n>\d{1,2})\]")

#: Markers on a row *label* rather than a cell: "Minimum lot area1,2". Only
#: read on a line that is laid out as a table row, because in prose a trailing
#: digit is a cross-reference, a year, or the number of the paragraph.
LABEL_MARKER = re.compile(r"(?:(?<=[a-z])|(?<=\)))(?P<n>\d{1,2}(?:,\d{1,2})*)\s*$")

#: A marker on a use-table cell: "P3", "L9", "L/SUR11", "P/L2". The letters are
#: the permission vocabulary and nothing else, because a bare letter-then-digit
#: rule would read the zone code "R5" as a footnoted "R". Use tables are where
#: the qualifier most often lives -- "permitted only as an accessory use" is a
#: footnote, not a column -- and Gresham writes a whole row of them per line,
#: single-spaced, so this one is read anywhere on the line rather than as a
#: whole cell.
#:
#: "A", "N" and "S" are deliberately absent from the vocabulary even though
#: codes use them, because they are also English: Gresham's flood definitions
#: name "Zones A, AO, AH, A1-30" and its design chapter labels a guideline
#: "G5" against a standard "S5". Those three letters alone invented 268
#: markers in one document. A code that permits with "A" loses its markers
#: here and gains them back as unmarked bodies, which is the honest direction
#: to fail in.
CELL_MARKER = re.compile(
    r"(?<![A-Za-z0-9/])(?:P/L|L/SUR|L/P|C/L|NP|SUR|CU|PC|P|C|X|L)"
    r"(?P<n>\d{1,2})(?![\d])"
)

#: A use row states several permissions, so one lonely match on a line of
#: prose is not a row. Either the line is laid out with column gaps or it
#: carries more than one of these codes.
CELL_VOCAB = re.compile(
    r"(?<![A-Za-z0-9/])(?:P/L|L/SUR|L/P|C/L|NP|SUR|CU|PC|P|C|X|L)"
    r"\d{0,2}(?![A-Za-z0-9])"
)

#: Page furniture printed inside a block: the codifier's page stamp
#: "[4.0400]-5" and the running header it sits under. Read as note text it
#: would be harmless; read as the end of the block it loses every note after
#: the page break.
#: Municode's is the section mark, the section number and the publication it
#: is running: "§ 4.127 WILSONVILLE CODE", "§ 4.127PLANNING AND LAND
#: DEVELOPMENT", with the page stamp "CD4:178.3Supp. No. 5" under it. Both
#: land in the middle of a notes list every time a list crosses a page, and
#: the section mark is what tells them from the heading of the next section --
#: a codifier prints it on the header and not on the heading. The replacement
#: character is there because extraction loses the glyph about half the time.
FURNITURE = re.compile(
    r"^\[[^\]]+\]-\d+$|Development Code\s+\(\d|^Page \d+$"
    r"|^(?:§|\ufffd)\s*\d{1,3}\.\d{2,4}"
    r"|^[A-Z]{1,3}\d+:\d+",
    re.I,
)

#: Two or more spaces: the column gap that tells a table row from a sentence.
GAP = re.compile(r"\s{2,}")

#: A bracket that belongs to a figure or section number rather than to a cell:
#: "See Figure 50.04.001-11[5]", where the figure is named after the note that
#: sends you to it. Read as a marker it ends the block a note early, which is
#: how Lake Oswego lost the sentence putting every R-0 and R-3 standard under
#: a per-parcel check. Glued to a bare number -- "28 - 32[5]" -- it is still a
#: marker, so only the citation shapes are forgiven.
CROSS_REFERENCE = re.compile(
    r"(?:figure|table|section|§|�)\s*[\w.\-]*\[\d{1,2}\]", re.I
)


@dataclass(frozen=True, slots=True)
class Marker:
    """One footnote reference, where it sits and how it was written."""

    doc: str
    line: int
    #: As the codifier printed it: "1", "12", "A". A string because a code
    #: that letters its notes is not a code with unnumbered notes, and
    #: renumbering them to suit the type would lose which note a reviewer is
    #: being sent to read.
    mark: str
    kind: str
    text: str

    @property
    def quote(self) -> str:
        return f"{self.doc}#L{self.line}"


@dataclass(frozen=True, slots=True)
class Body:
    """One footnote's text, and the line a reviewer can open to read it."""

    doc: str
    line: int
    #: As printed -- see `Marker.mark`.
    mark: str
    text: str

    @property
    def quote(self) -> str:
        return f"{self.doc}#L{self.line}"


@dataclass(frozen=True, slots=True)
class Block:
    """A run of numbered notes, and the lines whose markers it answers.

    ``region`` is where this block's markers are allowed to be: after the
    previous block ended and before this one's heading. A marker below the
    block belongs to the next one, not this.
    """

    head: int
    end: int
    region: tuple[int, int]
    bodies: tuple[Body, ...]

    @property
    def marks(self) -> frozenset[str]:
        return frozenset(b.mark for b in self.bodies)


@dataclass(frozen=True, slots=True)
class Census:
    """What one document says about its own footnotes, both directions."""

    layer: str
    doc: str
    blocks: tuple[Block, ...]
    markers: tuple[Marker, ...]
    #: Markers whose number no block in their region defines.
    unbodied: tuple[Marker, ...]
    #: Bodies no marker in their region points at.
    unmarked: tuple[Body, ...]

    @property
    def bodies(self) -> tuple[Body, ...]:
        return tuple(b for block in self.blocks for b in block.bodies)

    @property
    def reconciled(self) -> bool:
        return not self.unbodied and not self.unmarked

    @property
    def total(self) -> int:
        return len(self.markers) + len(self.bodies)


def _blocks(lines: Sequence[str]) -> list[Block]:
    """Every notes block in the document, in order.

    Three shapes: a headed block, which is a "NOTES:" line followed by numbered
    entries; a bracket run, which numbers itself and needs no heading; and a
    headless run, which is a codifier printing "1", a column gap and the note
    under a table it has just finished.
    """
    found: list[Block] = []
    i = 0
    previous_end = 0
    while i < len(lines):
        stripped = lines[i].strip()
        headed = bool(stripped) and NOTES_HEAD.match(stripped) is not None
        bracketed = BRACKET_NOTE.match(stripped) is not None
        headless = _headless_run(lines, i) or _glued_paren_run(lines, i)
        if not headed and not bracketed and not headless:
            i += 1
            continue
        head = i
        start = i + 1 if headed else i
        # A caption cell spanning the grid prints its heading once per column,
        # and an HTML extraction puts each of those on its own line.
        while start < len(lines) and NOTES_HEAD.match(lines[start].strip()):
            start += 1
        bodies, end = _bodies(lines, start)
        if not bodies:
            # A heading with nothing numbered under it is a caption for prose,
            # or a cross-reference to another table's notes. Not a block.
            i += 1
            continue
        found.append(
            Block(
                head=head + 1,
                end=end,
                region=(previous_end, head),
                bodies=tuple(bodies),
            )
        )
        previous_end = end
        i = max(end, i + 1)
    return found


def _order(mark: str) -> tuple[int, int]:
    """A sort key over mixed marks: digits first, then letters.

    Only ever used to ask whether the numbering restarted, which is how a
    block knows it has ended. A block that runs 1, 2, 3 then A, B is two
    lists in one, and reading them as one list is closer to the truth than
    cutting the second one off unread.
    """
    return (0, int(mark)) if mark.isdigit() else (1, ord(mark))


def _headless_run(lines: Sequence[str], i: int) -> bool:
    """Whether a numbered notes run starts here with nothing announcing it.

    Believed only from its first note, and only where a second follows it: a
    lone "1  something" is a table cell about as often as it is a footnote,
    and two in sequence is a list.
    """
    first = HEADLESS_NOTE.match(lines[i].strip())
    if first is None or first.group("n") != "1":
        return False
    for raw in lines[i + 1 : i + 12]:
        stripped = raw.strip()
        if not stripped:
            continue
        if ENDS_BLOCK.match(stripped) or NOTES_HEAD.match(stripped):
            return False
        following = HEADLESS_NOTE.match(stripped)
        if following is not None:
            return following.group("n") == "2"
    return False


def _glued_paren_run(lines: Sequence[str], i: int) -> bool:
    """Whether a parenthesised, glued notes run starts here.

    Same standard of proof as `_headless_run`: believed only from its own note
    1, and only where note 2 follows before anything ends the block. A lone
    "(2)See 250.200 D. Limited Uses per Title 4" is a note whose siblings the
    extraction lost, and reading it alone would let the census claim a block it
    cannot show -- so it stays an unbodied marker, which is the direction that
    reports a problem rather than hiding one.
    """
    first = GLUED_PAREN_NOTE.match(lines[i].strip())
    if first is None or first.group("n") != "1":
        return False
    for raw in lines[i + 1 : i + 12]:
        stripped = raw.strip()
        if not stripped:
            continue
        if ENDS_BLOCK.match(stripped) or NOTES_HEAD.match(stripped):
            return False
        following = GLUED_PAREN_NOTE.match(stripped)
        if following is not None:
            return following.group("n") == "2"
    return False


def _bears_a_marker(raw: str) -> bool:
    """Whether this line carries a footnote reference of any shape.

    Cross-references come out first: a note that ends "See Figure
    50.04.001-11[5]" is still the note, and reading its own figure number as a
    marker ends the block on the note that cites a figure.
    """
    stripped = PAREN_CITATION.sub("", CROSS_REFERENCE.sub("", raw.strip()))
    cells = [stripped, *(GAP.split(stripped) if GAP.search(stripped) else [])]
    if any(
        GLUED_MARKER.search(c.strip())
        or PAREN_MARKER.search(c.strip())
        or PAREN_LABEL_MARKER.search(c.strip())
        for c in cells
    ):
        return True
    if BRACKET_MARKER.search(stripped):
        return True
    return bool(
        CELL_MARKER.search(stripped)
        and (GAP.search(raw) or len(CELL_VOCAB.findall(stripped)) > 1)
    )


def _bodies(lines: Sequence[str], start: int) -> tuple[list[Body], int]:
    """The numbered notes beginning at ``start``, and where they stop.

    What ends a block is the numbering, not the whitespace. A note wraps, and
    a chapter PDF breaks pages in the middle of one -- Gresham's corridor
    notes run "1. Temporary health hardship dwellings...", blank, page
    furniture, "2. Permitted only along the NE Glisan and NE 162nd Avenue
    corridors...". Ending at the blank loses that note, which happens to be
    one of the open questions in the corpus.

    So blanks and furniture are read through, and the block ends when the
    numbering restarts: the next table's note 1 cannot belong to this table's
    list. That is also what keeps two blocks from merging into one whose
    region covers neither table.
    """
    bodies: list[Body] = []
    texts: list[list[str]] = []
    highest = (-1, -1)
    i = start
    while i < len(lines) and i - start < BLOCK_LIMIT:
        stripped = lines[i].strip()
        if not stripped or FURNITURE.search(stripped):
            i += 1
            continue
        if ENDS_BLOCK.match(stripped) or (bodies and NOTES_HEAD.match(stripped)):
            break
        opening = (
            STACKED_NOTE.match(stripped)
            or HEADLESS_NOTE.match(stripped)
            or GLUED_PAREN_NOTE.match(stripped)
            or BLOCK_NOTE.match(stripped)
            or STACKED_LETTER.match(stripped)
            or LETTER_NOTE.match(stripped)
        )
        if opening is not None:
            mark = opening.group("n")
            if bodies and mark.isalpha() != bodies[0].mark.isalpha():
                if bodies[0].mark.isalpha():
                    # Digits under letters are the lettered note's own
                    # sub-parts -- "E. Setbacks for residential garages are as
                    # follows: 1. Front loaded: minimum 20 feet." -- so they
                    # are read as more of E rather than as note 1 of a new
                    # list. Ending here lost every letter after E.
                    texts[-1].append(stripped)
                    i += 1
                    continue
                # Letters under digits are the next subsection. Troutdale's
                # "C. Townhouse dwellings:" heads the following table, and
                # swallowing it would both invent a note and cut the real one
                # above it short.
                break
            if bodies and _order(mark) <= highest:
                break
            text = opening.groupdict().get("text") or ""
            bodies.append(Body(doc="", line=i + 1, mark=mark, text=text))
            texts.append([text] if text else [])
            highest = _order(mark)
            i += 1
            continue
        if not bodies:
            # The first line under the heading is not numbered, so whatever
            # this heading announces, it is not a numbered notes block.
            break
        if _bears_a_marker(lines[i]):
            # A note wraps into prose, not into a footnoted table cell. This
            # is the next table starting, and reading it as the tail of the
            # last note would swallow its markers -- they sit inside a block
            # and blocks are where markers are not counted.
            break
        texts[-1].append(stripped)
        i += 1
    joined = [
        Body(doc=b.doc, line=b.line, mark=b.mark, text=" ".join(t))
        for b, t in zip(bodies, texts)
    ]
    return joined, i


def _markers(lines: Sequence[str], inside: Sequence[tuple[int, int]]) -> list[Marker]:
    """Every marker occurrence outside the notes blocks themselves.

    A note body carries its own number and would otherwise register as a
    marker for itself, which reconciles every block with itself and reports
    nothing.
    """
    out: list[Marker] = []
    for i, raw in enumerate(lines):
        if any(low <= i < high for low, high in inside):
            continue
        stripped = raw.strip()
        if not stripped:
            continue
        seen: set[str] = set()

        def add(mark: str, kind: str) -> None:
            if mark in seen:
                return
            seen.add(mark)
            out.append(Marker(doc="", line=i + 1, mark=mark, kind=kind, text=stripped))

        # Brackets identify themselves and are read anywhere on the line. The
        # rest are read per cell, because every one of them is a rule about
        # what a cell *ends* with.
        for m in BRACKET_MARKER.finditer(stripped):
            add(m.group("n"), "bracket")
        marked_cells = list(CELL_MARKER.finditer(stripped))
        if GAP.search(raw) or len(CELL_VOCAB.findall(stripped)) > 1:
            for m in marked_cells:
                add(m.group("n"), "cell")

        # A label carries markers too -- "Residential density (maximum)1" --
        # and in an HTML extraction it has no column gap to be found by, since
        # every cell is its own line. So the whole line is read as a cell as
        # well as being split into them. The label rule earns that reach from
        # its own narrowness: the digits must follow a lowercase letter or a
        # closing parenthesis with nothing between. "Table 16.22.020-2" and
        # "MUR-M3" end in digits and match neither.
        cited = PAREN_CITATION.sub("", stripped)
        cells = [cited, *(GAP.split(cited) if GAP.search(raw) else [])]
        for cell in cells:
            cell = cell.strip()
            for kind, pattern in (
                ("glued", GLUED_MARKER),
                ("paren", PAREN_MARKER),
                ("paren", PAREN_LABEL_MARKER),
                ("label", LABEL_MARKER),
            ):
                found = pattern.search(cell)
                if found is None:
                    continue
                for part in found.group("n").split(","):
                    add(part.strip(), kind)
    return out


def census(text: str, *, layer: str = "", doc: str = "") -> Census:
    """The footnote census of one document."""
    lines = text.splitlines()
    blocks = _blocks(lines)
    inside = tuple((b.head - 1, b.end) for b in blocks)
    markers = [
        Marker(doc=doc, line=m.line, mark=m.mark, kind=m.kind, text=m.text)
        for m in _markers(lines, inside)
    ]
    blocks = tuple(
        Block(
            head=b.head,
            end=b.end,
            region=b.region,
            bodies=tuple(
                Body(doc=doc, line=body.line, mark=body.mark, text=body.text)
                for body in b.bodies
            ),
        )
        for b in blocks
    )

    unbodied: list[Marker] = []
    unmarked: list[Body] = []
    claimed: set[int] = set()
    for block in blocks:
        low, high = block.region
        pointing = {m.mark for m in markers if low <= m.line - 1 < high}
        for body in block.bodies:
            if body.mark not in pointing:
                unmarked.append(body)
        claimed.update(range(low, high))
    for marker in markers:
        block = _governing(blocks, marker.line - 1)
        if block is None or marker.mark not in block.marks:
            unbodied.append(marker)

    return Census(
        layer=layer,
        doc=doc,
        blocks=blocks,
        markers=tuple(markers),
        unbodied=tuple(unbodied),
        unmarked=tuple(unmarked),
    )


def _governing(blocks: Sequence[Block], index: int) -> Block | None:
    """The block whose region contains this line, if any.

    A marker below the last block has no block at all -- its notes are in a
    document we do not hold, or in one the extractor lost.
    """
    for block in blocks:
        low, high = block.region
        if low <= index < high:
            return block
    return None


def _stored(layer_id: str) -> list[Path]:
    """Documents on disk for a layer. Not what it declared -- what we have."""
    directory = DOCS / layer_id
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.glob("*.txt") if p.is_file())


def _layers() -> list[str]:
    """Every layer with stored documents, as ``or/county/city``."""
    out = []
    for path in sorted(DOCS.rglob("*.txt")):
        layer = path.parent.relative_to(DOCS).as_posix()
        if layer not in out:
            out.append(layer)
    return out


def survey(layer: str | None = None) -> list[Census]:
    """The census of every stored document, or of one layer's."""
    layers = [layer] if layer else _layers()
    out: list[Census] = []
    for layer_id in layers:
        for path in _stored(layer_id):
            doc = f"{layer_id}/{path.name}"
            text = path.read_text(encoding="utf-8", errors="replace")
            out.append(census(text, layer=layer_id, doc=doc))
    return out


def render(rows: Sequence[Census], *, only_unreconciled: bool = False) -> str:
    """The census as text, for a terminal or a commit message."""
    shown = [r for r in rows if not only_unreconciled or not r.reconciled]
    width = max((len(r.doc) for r in shown), default=20)
    lines = []
    for row in shown:
        flag = "" if row.reconciled else "  UNRECONCILED"
        lines.append(
            f"{row.doc:<{width}}  {len(row.blocks):>2} blocks  "
            f"{len(row.markers):>3} markers  {len(row.bodies):>3} bodies  "
            f"{len(row.unbodied):>3} unbodied  {len(row.unmarked):>3} unmarked{flag}"
        )
    documents = len(rows)
    reconciled = sum(1 for r in rows if r.reconciled)
    with_notes = sum(1 for r in rows if r.total)
    lines.append("")
    lines.append(
        f"documents={documents}  with_footnotes={with_notes}  "
        f"reconciled={reconciled}  unreconciled={documents - reconciled}  "
        f"markers={sum(len(r.markers) for r in rows)}  "
        f"bodies={sum(len(r.bodies) for r in rows)}"
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    layer = None
    if "--layer" in args:
        layer = args[args.index("--layer") + 1]
    rows = survey(layer)
    print(render(rows, only_unreconciled="--unreconciled" in args))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "Block",
    "Body",
    "Census",
    "Marker",
    "census",
    "render",
    "survey",
]
