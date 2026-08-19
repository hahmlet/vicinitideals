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

#: A self-identifying note, which needs no block: Portland prints "[3] Additional
#: FAR and height may be allowed. See 33.110.265.F." under the table with no
#: heading over it.
BRACKET_NOTE = re.compile(r"^\[(?P<n>\d{1,2})\]\s+(?P<text>\S.*)$")

#: The number on its own line, with the text beneath it. An HTML table renders
#: each cell as its own line, so a block that reads "1  Density calculations
#: shall be..." on the page arrives as "1", newline, "Density calculations
#: shall be...". Happy Valley's largest block is written this way and was
#: invisible until the shape was allowed -- twelve notes including one that
#: reduces a corner lot's front setback to eight feet on a local street, which
#: is precisely the kind of qualifier a screen must not miss.
STACKED_NOTE = re.compile(r"^\[?\(?(?P<n>\d{1,2})\)?\]?[.):]?$")

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
FURNITURE = re.compile(r"^\[[^\]]+\]-\d+$|Development Code\s+\(\d|^Page \d+$", re.I)

#: Two or more spaces: the column gap that tells a table row from a sentence.
GAP = re.compile(r"\s{2,}")


@dataclass(frozen=True, slots=True)
class Marker:
    """One footnote reference, where it sits and how it was written."""

    doc: str
    line: int
    number: int
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
    number: int
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
    def numbers(self) -> frozenset[int]:
        return frozenset(b.number for b in self.bodies)


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

    Two shapes: a headed block, which is a "NOTES:" line followed by numbered
    entries, and a bracket run, which numbers itself and needs no heading.
    """
    found: list[Block] = []
    i = 0
    previous_end = 0
    while i < len(lines):
        stripped = lines[i].strip()
        headed = bool(stripped) and NOTES_HEAD.match(stripped) is not None
        bracketed = BRACKET_NOTE.match(stripped) is not None
        if not headed and not bracketed:
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


def _bears_a_marker(raw: str) -> bool:
    """Whether this line carries a footnote reference of any shape."""
    stripped = raw.strip()
    cells = [stripped, *(GAP.split(stripped) if GAP.search(raw) else [])]
    if any(GLUED_MARKER.search(c.strip()) or PAREN_MARKER.search(c.strip()) for c in cells):
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
    highest = 0
    i = start
    while i < len(lines) and i - start < BLOCK_LIMIT:
        stripped = lines[i].strip()
        if not stripped or FURNITURE.search(stripped):
            i += 1
            continue
        if ENDS_BLOCK.match(stripped) or (bodies and NOTES_HEAD.match(stripped)):
            break
        opening = STACKED_NOTE.match(stripped) or BLOCK_NOTE.match(stripped)
        if opening is not None:
            number = int(opening.group("n"))
            if bodies and number <= highest:
                break
            text = opening.groupdict().get("text") or ""
            bodies.append(Body(doc="", line=i + 1, number=number, text=text))
            texts.append([text] if text else [])
            highest = number
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
        Body(doc=b.doc, line=b.line, number=b.number, text=" ".join(t))
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
        seen: set[int] = set()

        def add(number: int, kind: str) -> None:
            if number in seen:
                return
            seen.add(number)
            out.append(Marker(doc="", line=i + 1, number=number, kind=kind, text=stripped))

        # Brackets identify themselves and are read anywhere on the line. The
        # rest are read per cell, because every one of them is a rule about
        # what a cell *ends* with.
        for m in BRACKET_MARKER.finditer(stripped):
            add(int(m.group("n")), "bracket")
        marked_cells = list(CELL_MARKER.finditer(stripped))
        if GAP.search(raw) or len(CELL_VOCAB.findall(stripped)) > 1:
            for m in marked_cells:
                add(int(m.group("n")), "cell")

        # A label carries markers too -- "Residential density (maximum)1" --
        # and in an HTML extraction it has no column gap to be found by, since
        # every cell is its own line. So the whole line is read as a cell as
        # well as being split into them. The label rule earns that reach from
        # its own narrowness: the digits must follow a lowercase letter or a
        # closing parenthesis with nothing between. "Table 16.22.020-2" and
        # "MUR-M3" end in digits and match neither.
        cells = [stripped, *(GAP.split(stripped) if GAP.search(raw) else [])]
        for cell in cells:
            cell = cell.strip()
            for kind, pattern in (
                ("glued", GLUED_MARKER),
                ("paren", PAREN_MARKER),
                ("label", LABEL_MARKER),
            ):
                found = pattern.search(cell)
                if found is None:
                    continue
                for part in found.group("n").split(","):
                    add(int(part.strip()), kind)
    return out


def census(text: str, *, layer: str = "", doc: str = "") -> Census:
    """The footnote census of one document."""
    lines = text.splitlines()
    blocks = _blocks(lines)
    inside = tuple((b.head - 1, b.end) for b in blocks)
    markers = [
        Marker(doc=doc, line=m.line, number=m.number, kind=m.kind, text=m.text)
        for m in _markers(lines, inside)
    ]
    blocks = tuple(
        Block(
            head=b.head,
            end=b.end,
            region=b.region,
            bodies=tuple(
                Body(doc=doc, line=body.line, number=body.number, text=body.text)
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
        pointing = {m.number for m in markers if low <= m.line - 1 < high}
        for body in block.bodies:
            if body.number not in pointing:
                unmarked.append(body)
        claimed.update(range(low, high))
    for marker in markers:
        block = _governing(blocks, marker.line - 1)
        if block is None or marker.number not in block.numbers:
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
