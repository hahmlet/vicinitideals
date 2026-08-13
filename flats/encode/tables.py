"""Reading a standards table without losing which zone a number belongs to.

Portland states almost nothing in sentences. Chapter 33.110 says the setbacks
"are stated in Table 110-4", and that table is a grid: one row per standard,
one column per zone, six zones wide. Flattened to prose it reads

    - Front building 20 ft. 20 ft. 20 ft. 15 ft. 10 ft. 10 ft.

which is six different front setbacks with nothing to say which is R5's. Guess
wrong and every lot in the zone is screened against another zone's rule, with a
citation beside it that looks entirely correct. That is the most expensive kind
of encoding error this system can make, because nothing about the output looks
wrong.

So the geometry is kept. Stored PDF text is extracted in layout mode, which
preserves the horizontal gaps, and a value is claimed for a zone only when it
sits under that zone's column. A cell that cannot be placed produces nothing.

What it deliberately does not do is interpret. "See Table 110-5", "no limit"
and "NA" are not numbers, and each is left for a person: a tiered coverage
curve is a different encoding job, and "no limit" means the field does not
apply here rather than that it is large.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Iterable, Sequence

from flats.encode.extract import _PAGE_NUMBER, _SECTION, Candidate, _furniture, _subject
from flats.rules.fields import FIELDS

#: Bumped when the reader changes.
READER = "flats-table/1"

#: Two or more spaces separate cells; one space is inside a phrase.
_GAP = re.compile(r"\s{2,}")
#: A zone code as it appears in a header: R5, R2.5, RM1, RF, MDR-PV — and the
#: hyphen-digit shape, R-10, R-3.5, LDR-1, which is how Oregon City and
#: Troutdale write theirs. Before the second alternative, every column in
#: Troutdale's dimensional-standards table failed to read as a zone and the
#: whole grid was invisible to this reader.
_ZONE = re.compile(r"^[A-Z]{1,4}[0-9]{0,2}(?:\.[0-9])?(?:-(?:[A-Z]{1,3}|[0-9]{1,2}(?:\.[0-9])?))?$")
#: A row's label column has to name a standard before anything is read from it.
_HEADER_HINT = re.compile(r"\bstandard\b|\bzone\b", re.I)
#: Values that are not measurements. Each means something a number cannot say.
_NOT_A_NUMBER = re.compile(r"^(?:na|n/a|no limit|none|see\b.*)$", re.I)
#: "20 ft.", "3,000 sq. ft.", "45 percent", "12 ft. x 12 ft." (which is not one number).
_MEASURE = re.compile(
    r"^(?P<n>\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*"
    # A trailing \b would reject "45%", because there is no word character
    # after the sign — and a percentage sign is how a coverage table writes it.
    r"(?P<unit>sq\.?\s*ft\.?|square feet|ft\.?|feet|foot|percent|%)(?![A-Za-z0-9])",
    re.I,
)
#: Footnote markers travel with the value. They are not part of the number and
#: they are not noise either: "30 ft. [3]" and "[3] Additional height may be
#: allowed" together say the standard has an exit. Reading the number and
#: dropping the marker encodes a ceiling the code does not actually impose.
_FOOTNOTE = re.compile(r"\s*\[(?P<n>\d+)\]\s*$")
#: "[3] Additional FAR and height may be allowed. See 33.110.265.F."
_NOTE = re.compile(r"^\[(?P<n>\d+)\]\s+(?P<text>.+)$")
#: What follows the last row: the footnote block, or the next section heading.
#: A section *number* is not enough — rows carry wrapped cross-references like
#: "33.110.265)", and treating one as the end truncates the table mid-grid.
_ENDS_TABLE = re.compile(r"^(?:\[\d+\]\s|\d{2,3}\.\d{3}\.\d{3}\s+[A-Z])")

_UNIT_KIND = {
    "sqft": "area_sqft",
    "ft": "length_ft",
    "pct": "percent",
}


@dataclass(frozen=True, slots=True)
class Column:
    """One column and where it starts.

    ``zone`` holds a zone code in the usual layout and a standard's label in
    the transposed one, because which of the two runs across the top is a
    property of the table, not of the code.
    """

    zone: str
    offset: int


@dataclass(frozen=True, slots=True)
class Row:
    """One standard, its cells by zone, and the line each was read from.

    ``contested`` names zones two cells both landed on. Which of the two is
    that zone's standard is not knowable from the layout, so neither is
    offered — an ambiguous row is review work, not a value.

    ``lines`` exists for transposed tables, where one standard's values are
    spread down a column and each zone's number sits on its own line. A quote
    has to open the line the number is actually on.
    """

    label: str
    line: int
    cells: dict[str, str]
    contested: frozenset[str] = frozenset()
    lines: dict[str, int] = dc_field(default_factory=dict)
    #: The heading this row sits under — "Setbacks (ft):". Load-bearing twice:
    #: Troutdale's rows are labelled "Front yard" with no setback word in
    #: sight, and the unit its bare-digit cells are measured in is printed
    #: here rather than beside the numbers.
    group: str = ""
    #: Footnote numbers on each zone's cell. "30 ft. [3]" means this zone's
    #: standard has an exit written under the table, and a screen that reads
    #: the 30 and drops the 3 applies a ceiling the code does not impose.
    marks: dict[str, tuple[int, ...]] = dc_field(default_factory=dict)
    #: The housing-type context the row sits in — Troutdale prints one whole
    #: grid per type under headings like "C. Townhouse dwellings:", so the
    #: type lives two headings up from the row, not in its label. "+"-joined
    #: canonical types, empty when no type heading is in scope.
    block: str = ""

    def marks_for(self, zone: str) -> tuple[int, ...]:
        return self.marks.get(zone, ())

    def value_for(self, zone: str) -> str:
        if zone in self.contested:
            return ""
        return self.cells.get(zone, "")

    def line_for(self, zone: str) -> int:
        return self.lines.get(zone, self.line)


@dataclass(frozen=True, slots=True)
class Table:
    """The rows of one table and the footnotes printed beneath it."""

    rows: tuple[Row, ...] = ()
    notes: dict[int, str] = dc_field(default_factory=dict)
    #: Line each note was read from, so a condition can be quoted like a value.
    note_lines: dict[int, int] = dc_field(default_factory=dict)

    def notes_for(self, row: Row, zone: str) -> tuple[str, ...]:
        """The footnote texts attached to one zone's cell in one row.

        A mark whose definition was not captured still yields a note — a
        placeholder naming the number. The mark is the table saying this cell
        has a condition; losing the text is a reading failure, and quietly
        promoting the number to unconditional would encode a standard the
        code does not state.
        """
        return tuple(
            self.notes.get(n, f"footnote {n} (text not captured)")
            for n in row.marks_for(zone)
        )

    def __iter__(self):
        return iter(self.rows)

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, i):
        return self.rows[i]


def _cells(line: str) -> list[tuple[int, str]]:
    """Split a layout line into (offset, text), one per gap-separated cell.

    The middle group is lazy at both levels (``??``), and that is the fix for
    a real bug: with a greedy ``?`` a single-character cell reached across its
    own gap and glued itself to the next cell, so Troutdale's grid of bare
    digits ("5      5      5") read as pairs. Portland never showed it because
    its cells carry units — "20 ft." stops at its own word end either way.
    """
    out: list[tuple[int, str]] = []
    for m in re.finditer(r"\S(?:.*?\S)??(?=\s{2,}|$)", line):
        text = m.group(0).strip()
        if text:
            out.append((m.start(), text))
    return out


def columns(line: str) -> tuple[Column, ...]:
    """Zone columns from a header line, or empty when this is not one."""
    head = header(line)
    return head[1] if head and head[0] == ZONES_ACROSS else ()


def _slots(line: str) -> tuple[str | None, ...]:
    """Every header cell after the label — zone code or None — in print order.

    The None entries are real columns. Troutdale prints "(TC)" town-center
    sub-columns between its zones, and counting those cells is what lets a
    data row be read by *position* when its numbers drift off the header
    offsets — without them the fifth cell looks like the fifth zone.
    """
    found = _cells(line)
    if found and _ZONE.match(found[0][1]):
        # A bare header has no label cell: its first cell is the first zone's
        # column, and dropping it would shift every row one zone left.
        return tuple(text if _ZONE.match(text) else None for _, text in found)
    return tuple(text if _ZONE.match(text) else None for _, text in found[1:])


def header(line: str) -> tuple[str, tuple[Column, ...]] | None:
    """What this line is the header of, and its columns.

    Two layouts, both real and both in the same chapter. Portland's Table 110-4
    runs zones across the top, one column each. Table 110-7 — the fourplex
    minimum lot area, which decides whether a pod is permitted at all — runs
    zones down the side instead, with the standard across the top. Reading only
    the first layout leaves that gate unencoded, and a gate nobody encoded is a
    gate nobody applies.
    """
    found = _cells(line)
    if not found:
        return None
    if not _HEADER_HINT.search(found[0][1]):
        # Gresham's header is nothing but district names — no "Standard", no
        # label cell at all. All cells must be zone codes, and at least one
        # must carry a digit: "NA  NA  NA" is a row of empty cells whose label
        # wrapped onto another line, and _ZONE cannot tell it from a district.
        zones = [Column(text, offset) for offset, text in found if _ZONE.match(text)]
        if (
            len(zones) >= 2
            and len(zones) == len(found)
            and any(any(ch.isdigit() for ch in c.zone) for c in zones)
        ):
            return ZONES_ACROSS, tuple(zones)
        return None
    rest = found[1:]
    zones = [Column(text, offset) for offset, text in rest if _ZONE.match(text)]
    if len(zones) >= 2:
        return ZONES_ACROSS, tuple(zones)
    # A heading is only taken as a standard when it names a field this system
    # has — otherwise any two-column list with the word "zone" in it becomes a
    # table of values.
    labels = [Column(text, offset) for offset, text in rest if _subject(text)]
    if labels:
        return ZONES_DOWN, tuple(labels)
    return None


#: Zones across the top, one column each — the usual layout.
ZONES_ACROSS = "zones-across"
#: Zones down the side, standards across the top.
ZONES_DOWN = "zones-down"


def _pitch(cols: Sequence[Column]) -> int:
    """Half the narrowest gap between columns — the furthest a cell may drift.

    Derived rather than fixed, because column spacing differs per table and a
    constant that is too generous silently pulls a cell into its neighbour.
    """
    if len(cols) < 2:
        return _MIN_REACH
    gaps = [b.offset - a.offset for a, b in zip(cols, cols[1:])]
    return max(_MIN_REACH, min(gaps) // 2)


def _column_for(offset: int, cols: Sequence[Column], reach: int) -> str | None:
    """The zone whose column this cell belongs to, by nearest header.

    Nearest, not "the last one it is past". Headers and values are centred
    differently, so Portland's R2.5 column starts at 331 while its values start
    at 319 — reading left-to-right claims that cell for R5 and quietly
    overwrites R5's own value with the neighbouring zone's number. The output
    still looks like a table.
    """
    if not cols:
        return None
    nearest = min(cols, key=lambda c: abs(offset - c.offset))
    return nearest.zone if abs(offset - nearest.offset) <= reach else None


#: A cell further than this from any column header belongs to no column.
_MIN_REACH = 8


def _span(lines: Sequence[str], start: int = 0) -> tuple[int | None, int]:
    """Where the first table starts and ends, as indexes into ``lines``.

    Found before anything is read, because what counts as page furniture
    depends on where the table is: a line repeated across fifty pages is
    decoration, and the same line repeated four times inside one grid is a
    column of labels.
    """
    first: int | None = None
    shape: tuple[str, tuple[str, ...]] = ("", ())
    for i, line in enumerate(lines[start:], start=start):
        head = header(line)
        if head:
            found = (head[0], tuple(c.zone for c in head[1]))
            if first is None:
                first, shape = i, found
            elif found != shape:
                return first, i
            continue
        if first is not None and _ends_table(line.strip()):
            if _NOTE.match(line.strip()):
                # The footnote block belongs to the table. It ends the rows and
                # begins the conditions attached to them, which are the half of
                # the standard a reader that stops here never sees.
                return first, _end_of_notes(lines, i)
            return first, i
    return first, len(lines)


def _end_of_notes(lines: Sequence[str], start: int) -> int:
    """Index just past the run of footnote definitions beginning at ``start``."""
    last = start
    for i, line in enumerate(lines[start:], start=start):
        stripped = line.strip()
        if not stripped:
            continue
        if _NOTE.match(stripped):
            last = i
            continue
        if i > last:
            break
    return last + 1


def _ends_table(stripped: str) -> bool:
    """Whether this line is past the last row.

    Three things end a grid: the footnote block, the next section heading, and
    a sentence. The last one matters most — a table is often the final thing on
    a page, and without it the span runs on into the prose, where flattened
    rows and real sentences become indistinguishable.
    """
    if not stripped:
        return False
    if _ENDS_TABLE.match(stripped):
        return True
    if len(_cells(stripped)) > 1:
        return False  # gaps between cells: a row, however wordy
    words = stripped.split()
    return len(words) >= _SENTENCE_WORDS and stripped.endswith((".", ":", ";"))


#: A gapless line this long that closes like a sentence is prose, not a label.
_SENTENCE_WORDS = 6


def _furniture_outside(lines: Sequence[str], first: int, last: int) -> set[str]:
    """Page decoration, judged by what repeats *away* from the table.

    Counting repeats over the whole document classifies "setback" — the second
    half of "- Front building / setback", four rows of it — as furniture, and
    dropping it leaves three labels that name no field. Every setback in the
    zone then goes unencoded, which is the quiet half of a recall failure: no
    error, no value, no lot screened.
    """
    outside = [line.strip() for line in (*lines[:first], *lines[last:])]
    return _furniture(outside)


def read_table(text: str, *, start_line: int = 1) -> Table:
    """The first standards table in this text, with its footnotes.

    Label continuation lines ("- Front building" then " setback") are folded
    into the row they belong to, because the label is what names the field and
    half a label names nothing.
    """
    lines = text.splitlines()
    first, last = _span(lines)
    if first is None:
        return Table()
    return _read_span(lines, first, last, start_line)


def read_tables(text: str, *, start_line: int = 1) -> tuple[Table, ...]:
    """Every zone table in the document, in the order they appear.

    A chapter states its standards in more than one grid, and which grid holds
    which standard is not knowable in advance — Portland puts setbacks and
    height in Table 110-4 and sends building coverage to another table
    entirely. Reading only the first would drop the rest without saying so.
    """
    lines = text.splitlines()
    out: list[Table] = []
    at = 0
    while at < len(lines):
        first, last = _span(lines, at)
        if first is None:
            break
        table = _read_span(lines, first, last, start_line)
        if table.rows:
            out.append(table)
        at = max(last, first + 1)
    return tuple(out)


def blank_tables(text: str) -> str:
    """The document with every grid blanked out, line numbering untouched.

    The prose reader has to be kept off the tables. Flattened, a row reads as a
    sentence with six numbers in it and one subject, and the reader takes the
    nearest — which is the first column, not this zone's. Blanking rather than
    deleting keeps every quote line pointing where it did.
    """
    lines = text.splitlines()
    kept = list(lines)
    at = 0
    while at < len(lines):
        first, last = _span(lines, at)
        if first is None:
            break
        for i in range(first, min(last, len(kept))):
            kept[i] = ""
        at = max(last, first + 1)
    return "\n".join(kept) + ("\n" if text.endswith("\n") else "")


def _read_span(lines: Sequence[str], first: int, last: int, start_line: int) -> Table:
    junk = _furniture_outside(lines, first, last)
    kind = ""
    cols: tuple[Column, ...] = ()
    slots: tuple[str | None, ...] = ()
    group = ""
    block = ""
    # The heading that names who a grid is for is printed *above* its header
    # line — "C. Townhouse dwellings:" then the zone columns — which puts it
    # just outside the span. Look back a few lines for a heading-shaped line
    # that names a housing type; footnote sentences that mention a type
    # ("Rear yard setbacks for duplexes are 15 feet unless...") are excluded
    # by the same word cap that keeps them from being group headings.
    for prev in reversed(lines[max(0, first - 6) : first]):
        stripped_prev = prev.strip()
        if not stripped_prev:
            continue
        if len(stripped_prev.split()) <= _GROUP_WORDS and (
            stripped_prev.endswith(":") or _GROUP_HEAD.match(stripped_prev)
        ):
            found_type = _housing_type(stripped_prev)
            if found_type:
                block = found_type
                break
    reach = _MIN_REACH
    rows: list[Row] = []
    down: dict[str, dict[str, tuple[str, int, tuple[int, ...]]]] = {}
    notes: dict[int, str] = {}
    note_lines: dict[int, int] = {}

    for n, line in enumerate(lines[first:last], start=start_line + first):
        stripped = line.strip()
        if stripped.endswith(":"):
            # Exempt from the furniture check below: "Setbacks (ft):" repeats
            # in every housing-type table of the chapter, which reads as page
            # decoration by frequency — but it is the heading that says the
            # rows under it are setbacks at all. Running headers and revision
            # stamps do not end with a colon.
            pass
        elif not stripped or stripped in junk or _PAGE_NUMBER.match(stripped):
            # Page furniture interrupts a table without ending it: a chapter
            # PDF stamps its title and revision date between the last row of
            # one page and the first row of the next.
            continue

        head = header(line)
        if head:
            if cols and (head[0], tuple(c.zone for c in head[1])) != (
                kind,
                tuple(c.zone for c in cols),
            ):
                break  # a different table has started
            # Re-anchored on every header: a table continued onto a new page
            # is the same table, but its columns rarely land on the same offsets.
            kind, cols = head[0], head[1]
            slots = _slots(line) if kind == ZONES_ACROSS else ()
            reach = _pitch(cols)
            continue
        if not cols:
            continue
        found_note = _NOTE.match(stripped)
        if found_note:
            num = int(found_note.group("n"))
            notes[num] = found_note.group("text").strip()
            note_lines[num] = n
            continue
        if _ENDS_TABLE.match(stripped):
            # The next section number is outside the grid. Without this the
            # reader runs to the end of the chapter and reads prose as rows.
            break
        if notes:
            break  # past the footnote block, whatever this is

        found = _cells(line)
        if kind == ZONES_DOWN:
            # The first cell names the zone; the rest are its values, one per
            # standard column.
            zone_code = found[0][1] if found else ""
            if not _ZONE.match(zone_code):
                continue
            for offset, cell in found[1:]:
                label = _column_for(offset, cols, reach)
                if label is None:
                    continue
                down.setdefault(label, {})[zone_code] = (
                    _unglue(_FOOTNOTE.sub("", cell))[0],
                    n,
                    _marks(cell),
                )
            continue

        label_parts: list[str] = []
        values: dict[str, str] = {}
        marks: dict[str, tuple[int, ...]] = {}
        contested: set[str] = set()
        if slots and len(found) == len(slots) + 1:
            # One cell per header slot plus the label: the row is structurally
            # complete, so position places every cell. Offsets cannot — this
            # grid right-aligns each number to its own width, drifting further
            # than the column pitch, which is how LDR-1's 70 was read as
            # LDR-2's and the neighbouring zone's number wore its citation.
            label_parts.append(found[0][1])
            placed = [(z, c) for (_, c), z in zip(found[1:], slots) if z is not None]
        else:
            placed = []
            for offset, cell in found:
                zone = _column_for(offset, cols, reach)
                if zone is None:
                    label_parts.append(cell)
                    continue
                placed.append((zone, cell))
        for zone, cell in placed:
            value = _unglue(_FOOTNOTE.sub("", cell))[0]
            if _marks(cell):
                marks[zone] = _marks(cell)
            if zone in values and values[zone] != value:
                # Two cells, one column. The layout cannot say which is this
                # zone's standard, and picking either is how a number ends up
                # under a zone it was never written for.
                contested.add(zone)
            values[zone] = value

        joined = " ".join(label_parts).strip()
        if (
            not values
            and _GROUP_HEAD.match(joined)
            and len(joined.split()) <= _GROUP_WORDS
            and not joined.endswith(".")
        ):
            # "B. Minimum Lot Size2" — Gresham letters its group headings down
            # the table with no colon in sight. Without this branch the heading
            # glues onto the previous row's label as a continuation, and every
            # housing-type row after it keeps the wrong group. The word cap and
            # the no-period rule keep footnote text out: "8. Abuts an alley:
            # 16 feet; ..." is a condition, not a heading.
            found_type = _housing_type(joined)
            if found_type:
                # "A. Single-family detached and duplex dwellings:" — the
                # heading names who the whole grid below it is for, not a
                # standard. Troutdale prints one grid per type this way. The
                # stale group is cleared: whatever heading was open belonged
                # to the previous type's grid.
                block, group = found_type, ""
            else:
                group = joined
            continue
        if joined.endswith(":"):
            # "Setbacks (ft):" — a heading, not a row, whatever stray cells
            # sit beside it. It scopes every row after it (across page breaks,
            # which is why a header re-anchor does not clear it) until the
            # next heading takes over.
            found_type = _housing_type(joined)
            if found_type:
                block, group = found_type, ""
            else:
                group = joined
            continue
        if values:
            rows.append(
                Row(
                    label=joined,
                    line=n,
                    cells=values,
                    contested=frozenset(contested),
                    marks=marks,
                    group=group,
                    block=block,
                )
            )
        elif label_parts and rows:
            # A continuation of the row above: "- Front building" / " setback".
            previous = rows[-1]
            rows[-1] = Row(
                label=f"{previous.label} {' '.join(label_parts)}".strip(),
                line=previous.line,
                cells=previous.cells,
                contested=previous.contested,
                lines=previous.lines,
                marks=previous.marks,
                group=previous.group,
                block=previous.block,
            )

    for label, per_zone in down.items():
        rows.append(
            Row(
                label=label,
                line=min(line for _, line, _ in per_zone.values()),
                cells={zone: text for zone, (text, _, _) in per_zone.items()},
                lines={zone: line for zone, (_, line, _) in per_zone.items()},
                marks={zone: seen for zone, (_, _, seen) in per_zone.items() if seen},
            )
        )
    return Table(rows=tuple(rows), notes=notes, note_lines=note_lines)


#: A footnote number glued straight onto the unit — "35 ft.12", "16 ft.7",
#: "20,000 sq. ft.1". A PDF superscript loses its baseline in extraction and
#: lands inline; reading the prefix and dropping the digits would encode the
#: base case of a conditional standard as if the condition did not exist.
#: Anchored on the unit so a decimal never donates its fraction: "7.5 ft"
#: has no digits after the unit, and "35 ft.12" cannot be 35.12 because the
#: number a unit follows is already complete.
_GLUED_NOTE = re.compile(r"^(?P<body>.*?(?:sq\.?\s*ft\.?|ft\.|feet|%))\s?(?P<n>\d{1,2})$")


def _unglue(cell: str) -> tuple[str, tuple[int, ...]]:
    """A cell with any glued footnote split off: ("35 ft.", (12,))."""
    m = _GLUED_NOTE.match(cell.strip())
    if m:
        return m.group("body"), (int(m.group("n")),)
    return cell, ()


def _marks(cell: str) -> tuple[int, ...]:
    """Footnote numbers on a cell, in the order they appear."""
    bracketed = tuple(int(m.group("n")) for m in _FOOTNOTE.finditer(cell))
    return bracketed or _unglue(cell)[1]


def measure(raw: str) -> tuple[float, str] | None:
    """A cell as (number, unit kind), or None when it is not a measurement.

    "no limit" and "See Table 110-5" are refused on purpose. Both state
    something real that a number cannot carry, and turning either into a value
    would encode a fact nobody wrote.
    """
    cell = _FOOTNOTE.sub("", raw).strip()
    if not cell or _NOT_A_NUMBER.match(cell):
        return None
    if re.search(r"\bx\b", cell, re.I):
        # "12 ft. x 12 ft." is a dimension pair, not a quantity.
        return None
    m = _MEASURE.match(cell)
    if not m:
        return None
    unit = m.group("unit").lower().replace(" ", "").replace(".", "")
    if unit in ("sqft", "squarefeet"):
        kind = "sqft"
    elif unit in ("percent", "%"):
        kind = "pct"
    else:
        kind = "ft"
    return float(m.group("n").replace(",", "")), _UNIT_KIND[kind]


#: Row labels as a setbacks group prints them, exact after normalisation.
#: Exact on purpose: "Building side" is the attached party wall, which has no
#: field here, and a fuzzy match would hand its zero to one of these.
_GROUPED_SUBJECTS = {
    "front yard": "setback_front_ft",
    "side yard": "setback_side_ft",
    "interior side yard": "setback_side_ft",
    "street side yard": "setback_street_side_ft",
    "rear yard": "setback_rear_ft",
}
#: The unit when it is printed in the label — "Minimum lot width (ft.)" over
#: cells that are bare digits — rather than beside each number.
_LABEL_UNIT = re.compile(r"\((?P<u>sq\.?\s*ft\.?|square feet|ft\.?|feet|%|percent)\.?\)", re.I)
_BARE_NUMBER = re.compile(r"^(?P<n>\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)$")


def _measure_bare(cell: str, label: str, group: str) -> tuple[float, str] | None:
    """A bare-digit cell, measured in the unit its label or group declares.

    Troutdale's grid prints "70" under "Minimum lot width (ft.)" and "5" under
    "Setbacks (ft.):" — the unit is stated once, in the heading. A bare number
    with no declared unit anywhere still produces nothing: guessing feet is
    how an acreage becomes a setback.
    """
    m = _BARE_NUMBER.match(cell.strip())
    if not m:
        return None
    unit = _LABEL_UNIT.search(label) or _LABEL_UNIT.search(group)
    if not unit:
        return None
    u = unit.group("u").lower().replace(" ", "").rstrip(".")
    kind = "sqft" if u.startswith("sq") else "pct" if u in ("%", "percent") else "ft"
    return float(m.group("n").replace(",", "")), _UNIT_KIND[kind]


#: A lettered or numbered heading with no cells beside it — "B. Minimum Lot
#: Size2", "2. Section 7.0400 Rear Height Limits". The letter is the giveaway;
#: rows never print one.
_GROUP_HEAD = re.compile(r"^(?:[A-Z]|\d{1,2})\.\s+\S")
#: Longest a group heading may run. Gresham's wordiest is eleven words
#: ("C. Minimum Net Density3 (See definition of Net Density in Article 3)");
#: its footnotes run longer, and a footnote taken as a heading scopes every
#: row after it to a sentence.
_GROUP_WORDS = 12

#: Row labels that name who a standard is for rather than what it is —
#: "Townhouse", "Duplex", "All other uses" under a heading like "B. Minimum
#: Lot Size". A compound label ("Duplex, Triplex, Quadplex, and Cottage
#: Cluster") is tagged with every type it names, "+"-joined, because which
#: member matters is selection's question — a row that includes quadplexes
#: is the pod's row no matter what it is listed alongside. A label with
#: "except" in it is refused outright — "All uses except X" applies to the
#: pod only if X is not the pod, and deciding that from a row label is how a
#: standard gets applied to the exact type it excludes.
_HOUSING_TYPES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\btown\s?(?:house|home)s?\b|\brow\s?houses?\b", re.I), "townhouse"),
    (re.compile(r"\ball other uses?\b|\ball others?\b|\bother uses\b", re.I), "default"),
    (re.compile(r"\ball (?:residential )?uses\b", re.I), "all"),
    (re.compile(r"\bsingle[ -](?:family[ -])?detached\b", re.I), "single_detached"),
    (re.compile(r"\bduplex(?:es)?\b", re.I), "duplex"),
    (re.compile(r"\btriplex(?:es)?\b", re.I), "triplex"),
    (re.compile(r"\b(?:quad|four)-?plex(?:es)?\b", re.I), "quadplex"),
    (re.compile(r"\bcottage\s+clusters?\b", re.I), "cottage_cluster"),
    (re.compile(r"\bmulti-?family\b|\bapartments?\b", re.I), "multifamily"),
    (re.compile(r"\bmanufactured\b|\bmobile\s+home\b", re.I), "manufactured"),
)

_EXCEPT = re.compile(r"\bexcept\b", re.I)

#: A note reference that lost its cell: "Front yard see note 1 see note 1" is
#: a row label with two columns' worth of note pointers glued on, because the
#: wrapped "see note 1" lines under specific columns drifted off their offsets
#: and were read as label continuations. The refs cannot be re-attributed to
#: their columns, so they condition the whole row instead — the conservative
#: direction: a value that was unconditional gains a note and attach refuses
#: it, rather than a conditional one being quoted clean.
_SEE_NOTE = re.compile(r"\bsee note (\d+)\b", re.I)


def _housing_type(label: str) -> str | None:
    """Every canonical housing type a row label names, "+"-joined, or None."""
    if _EXCEPT.search(label):
        return None
    found = [name for pattern, name in _HOUSING_TYPES if pattern.search(label)]
    return "+".join(found) if found else None


#: A pair group heading mentions setbacks and carries no number of its own —
#: "Minimum Setbacks", "Minimum yard dimensions or minimum building setbacks".
_PAIR_GROUP = re.compile(r"\bsetbacks?\b", re.I)
#: Longest a label or group line may run. A sentence is not a label.
_PAIR_WORDS = 8


def _measure_line(line: str) -> tuple[float, str] | None:
    """A line that is one measurement and nothing else.

    ``measure()`` reads a prefix, which is right for a table cell and wrong
    here: "7.5 ft or 5 ft due to irregular shaped lots" starts with a
    measurement and does not state one. A pair's value line must be consumed
    whole — that refusal is what keeps a two-tier standard out of the file.
    """
    cell = _FOOTNOTE.sub("", line).strip()
    if not cell or _NOT_A_NUMBER.match(cell):
        return None
    m = _MEASURE.match(cell)
    if not m or m.end() != len(cell):
        return None
    return measure(cell)


def read_pairs(text: str, *, path: str) -> list[Candidate]:
    """Values stated as stacked label/value line pairs.

    The fourth table shape, and the one every Code Publishing HTML chapter is
    written in: the codifier renders the dimensional grid as an HTML table,
    and ``html_to_text`` linearises it one cell per line —

        Front yard

        20 ft

        Except for steeply sloped lots ...

    The prose reader cannot see this. ``paragraphs()`` joins the stack into
    one clause, where the note's "Except" tags the whole thing an exception
    (Gladstone) or the run of cells reads as one sentence stating five side
    setbacks (the L193 glue). The pair reader works on the unjoined lines: a
    line that is exactly a standard's label, whose next non-blank line is
    exactly one measurement, is a table row that lost its geometry.

    A label with no direct subject match may still read through a group
    heading — "Front yard" under "Minimum Setbacks" — mirroring the grouped
    rows of the spatial reader. Sub-labelled stacks ("Minimum Lot Area" over
    "Detached single household" over "7,200 sf") produce nothing: the value
    line under the label is not a measurement, and the housing-type row it
    belongs to is a dimension this reader does not decide.

    Pairs are near-cell evidence, not cell evidence: nothing in the stack
    names a zone, so a pair counts only where the document or a declared
    section binds it to one — the same rule prose lives under.
    """
    lines = text.splitlines()
    # Frequency-based furniture detection assumes a repeated line is a page
    # header. In a linearised grid the repetition IS the data: "35 ft" prints
    # once per row it governs and "Front yard" once per sibling table, so a
    # line that reads as a measurement or a label is never furniture here.
    junk = {
        j
        for j in _furniture([line.strip() for line in lines])
        if _measure_line(j) is None
        and _subject(j) is None
        and j.strip(" .:").lower() not in _GROUPED_SUBJECTS
    }
    out: list[Candidate] = []
    section = ""
    group = ""
    label: str | None = None

    for n, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if not stripped or stripped in junk or _PAGE_NUMBER.match(stripped):
            continue
        found = _SECTION.match(stripped)
        if found:
            section = found.group("sec")
            group = ""
            label = None
            continue
        if label is not None:
            parsed = _measure_line(stripped)
            if parsed is not None:
                number, kind = parsed
                name = _subject(label)
                if name is None and group:
                    name = _GROUPED_SUBJECTS.get(label.strip(" .:").lower())
                if name is not None and FIELDS[name].kind == kind:
                    value = int(number) if number.is_integer() else number
                    out.append(
                        Candidate(
                            field=name,
                            value=value,
                            line=n,
                            text=f"{label}: {stripped}",
                            quote=f"{path}#L{n}",
                            source="pair",
                            section=section,
                        )
                    )
                label = None
                continue
            label = None
        has_digit = any(ch.isdigit() for ch in stripped)
        words = len(stripped.split())
        if not has_digit and words <= _PAIR_WORDS and not stripped.endswith("."):
            if _subject(stripped) or (
                group and stripped.strip(" .:").lower() in _GROUPED_SUBJECTS
            ):
                label = stripped
        if not has_digit and words <= _PAIR_WORDS + 2 and _PAIR_GROUP.search(stripped):
            group = stripped
    return out


#: A footnote as Wood Village prints one — "10 ft(1)" — rather than the
#: bracketed form. Digits only: "(See 210.320)" is a cross-reference cell.
_PAREN_NOTE = re.compile(r"\((?P<n>\d{1,2})\)")
#: A line that is only a cross-reference or comment cell — "(See 210.340)".
_PAREN_LINE = re.compile(r"^\(.*\)$")
#: A cell stating the standard does not apply in this column.
_DASH = re.compile(r"^[—–-]$")
#: A row label may open with a list dash: "– Min. lot area(2)".
_LABEL_DASH = re.compile(r"^[—–-]\s+")
#: A block of rows scoped to corner lots. The street-side setback's natural
#: home — the standard only exists on a corner — but every other field there
#: is a corner *variant* of the base standard above it, and reading one as
#: the base is how 5 ft becomes 10.
_CORNER_BLOCK = re.compile(r"\bcorner\b", re.I)


def _grid_value(line: str, label: str) -> tuple[float, str, tuple[str, ...]] | None:
    """One stacked-grid cell as (number, kind, notes), or None.

    Whole-line like a pair's value, after setting aside paren footnotes —
    which are kept: "10 ft(1)" is a base case with an exit, and the marker is
    what says so.
    """
    marks = tuple(f"footnote ({m.group('n')})" for m in _PAREN_NOTE.finditer(line))
    cell = _PAREN_NOTE.sub("", line).strip()
    parsed = _measure_line(cell) or _measure_bare(cell, label, "")
    if parsed is None:
        return None
    number, kind = parsed
    return number, kind, marks


def read_stacked_grids(text: str, *, path: str) -> dict[str, list[Candidate]]:
    """Zone-keyed values from a stacked grid, the fifth table shape.

    eCode360 and municipal.codes render the dimensional table as an HTML
    grid, and ``html_to_text`` linearises it column-run by column-run: a
    header block of one zone code per line, then each row as its label
    followed by one value line per zone, in header order —

        Standard
        LR12
        LR7.5
        – Min. lot area(2)
        12,000 sq ft
        7,500 sq ft

    Unlike a pair, these ARE written for a zone — the position in the run
    says whose column it is — so what reads here is cell evidence.

    Three refusals keep the positional claim honest. A header of one zone is
    not read at all: Milwaukie prints lot-size *tiers* under a single zone
    code, and n positional values under 1 zone is exactly what a tier row
    looks like. A row is read only when every one of its n lines is a
    measurement, a dash, or a footnoted measurement — one prose cell and the
    whole row is refused rather than shifted. And after the n values the next
    line must not be another measurement: more values than columns means the
    geometry is not what this reader assumes, and nothing positional survives
    that.

    Labels must name their standard outright ("– Front setback"). Grouped
    and nested labels — Lake Oswego's "Front (ft.)" under "Primary
    Structure" under "YARD SETBACKS", printed again under "Accessory
    Structure" — are deliberately unread: position inside a nested block is
    a context this reader does not track, and an accessory-structure setback
    wearing the zone's citation is the expensive kind of wrong.
    """
    lines = text.splitlines()
    junk = {
        j
        for j in _furniture([line.strip() for line in lines])
        if _measure_line(j) is None and _subject(j) is None and not _ZONE.match(j)
    }
    live = [
        (n, line.strip())
        for n, line in enumerate(lines, start=1)
        if line.strip() and line.strip() not in junk and not _PAGE_NUMBER.match(line.strip())
    ]

    out: dict[str, list[Candidate]] = {}
    zones: tuple[str, ...] = ()
    section = ""
    block = ""
    i = 0
    while i < len(live):
        n, stripped = live[i]
        found = _SECTION.match(stripped)
        if found:
            section = found.group("sec")
            zones = ()
            block = ""
            i += 1
            continue
        run = []
        while i + len(run) < len(live) and _ZONE.match(live[i + len(run)][1]):
            run.append(live[i + len(run)][1])
        if len(run) >= 2:
            zones = tuple(run)
            block = ""
            i += len(run)
            continue
        label = _LABEL_DASH.sub("", _PAREN_NOTE.sub("", stripped)).strip()
        name = _subject(label)
        if (
            zones
            and name is None
            and not any(ch.isdigit() for ch in label)
            and len(label.split()) <= 4
            and not _PAREN_LINE.match(stripped)
            and _measure_line(stripped) is None
        ):
            # "Minimum Setbacks", "Corner Lots" — a heading scoping the rows
            # under it, until the next heading or header.
            block = label
        if zones and name is not None and not any(ch.isdigit() for ch in label):
            if (
                _CORNER_BLOCK.search(block)
                and name.startswith("setback_")
                and name != "setback_street_side_ft"
            ):
                # Where the block ends is not printed, so the guard is scoped
                # by field instead: only setbacks have corner variants, and a
                # coverage row after the corner rows is a sibling, not a member.
                i += 1
                continue
            cells: list[tuple[int, tuple[float, str, tuple[str, ...]]] | None] = []
            j = i + 1
            # A comment cell may sit between label and values or after them;
            # only fully parenthesised lines are stepped over.
            while j < len(live) and len(cells) < len(zones):
                cell_no, cell_line = live[j]
                if _PAREN_LINE.match(cell_line):
                    j += 1
                    continue
                if _DASH.match(cell_line):
                    cells.append(None)
                    j += 1
                    continue
                parsed = _grid_value(cell_line, label)
                if parsed is None:
                    break
                cells.append((cell_no, parsed))
                j += 1
            overrun = (
                j < len(live)
                and not _PAREN_LINE.match(live[j][1])
                and _grid_value(live[j][1], label) is not None
            )
            if len(cells) == len(zones) and not overrun:
                for zone, cell in zip(zones, cells):
                    if cell is None:
                        continue
                    cell_no, (number, kind, marks) = cell
                    if FIELDS[name].kind != kind:
                        continue
                    value = int(number) if number.is_integer() else number
                    out.setdefault(zone, []).append(
                        Candidate(
                            field=name,
                            value=value,
                            line=cell_no,
                            text=f"{stripped} ({zone})",
                            quote=f"{path}#L{cell_no}",
                            source="table",
                            notes=marks,
                            section=section,
                        )
                    )
                i = j
                continue
        i += 1
    return out


def stacked_candidates_for(
    grids: dict[str, list[Candidate]], zone: str
) -> list[Candidate]:
    """One zone's candidates from a stacked grid, matched loosely on spelling.

    The GIS layer writes "LR 7.5" and the table header prints "LR7.5"; the
    code writes "R-7.2" where the layer says "R7.2". Spacing and hyphens are
    typography, not identity — everything else has to match exactly.
    """

    def norm(z: str) -> str:
        return z.replace(" ", "").replace("-", "").lower()

    return [c for header, cs in grids.items() if norm(header) == norm(zone) for c in cs]


def candidates_for(table: Table | Iterable[Row], zone: str, *, path: str) -> list[Candidate]:
    """Values this table states for one zone.

    A row is only read when its label names a standard this system has a field
    for and the units in the cell match that field's kind. Everything else —
    FAR bonus tiers, outdoor-area dimensions, coverage curves — is left alone
    rather than forced into the nearest field.

    A cell carrying a footnote marker produces a *conditional* candidate: the
    number, plus the note that qualifies it. "30 ft. [3]" with "[3] Additional
    height may be allowed" is not a 30 ft. ceiling, and encoding it as one
    turns a lot that could be built taller into a red that nobody revisits.
    """
    table = table if isinstance(table, Table) else Table(rows=tuple(table))
    out: list[Candidate] = []
    for row in table.rows:
        htype = ""
        name = _subject(row.label)
        if name is None and "setback" in row.group.lower():
            # "Front yard" under "Setbacks (ft.):" — the group heading, not
            # the row label, is what says these are setbacks at all. Glued
            # note refs are stripped before the exact match: "Front yard see
            # note 1 see note 1" is still the front yard row.
            clean = " ".join(_SEE_NOTE.sub("", row.label).split())
            name = _GROUPED_SUBJECTS.get(clean.strip(" .").lower())
        if name is None:
            # "Townhouse" under "B. Minimum Lot Size2" — the row names who the
            # standard is for and the group heading names the standard. The
            # candidate is tagged with the type; whether that type speaks for
            # the pod is selection's decision, not the reader's.
            found_type = _housing_type(row.label)
            if found_type:
                name = _subject(row.group)
                htype = found_type if name else ""
        if name is None:
            continue
        if _CORNER_BLOCK.search(row.group) and name != "setback_street_side_ft":
            # "2. Width at building line: Corner lot" — the corner variant of
            # a standard this system states once. Same rule as the stacked
            # reader: inside a corner block only the street-side setback is
            # at home; everything else is a variant that would sit beside the
            # interior value as a bogus second reading.
            continue
        if not htype:
            # A row with no type of its own inherits its grid's: Troutdale's
            # "Front yard" under "Setbacks (ft):" inside "C. Townhouse
            # dwellings:" is the townhouse front setback, and reading it
            # untyped would let it corroborate every other type's.
            htype = row.block
        parsed = measure(row.value_for(zone)) or _measure_bare(
            row.value_for(zone), row.label, row.group
        )
        if parsed is None:
            continue
        number, kind = parsed
        if FIELDS[name].kind != kind:
            continue
        value = int(number) if number.is_integer() else number
        refs = tuple(dict.fromkeys(_SEE_NOTE.findall(row.label)))
        glued = tuple(f"see note {n} (text not captured)" for n in refs)
        out.append(
            Candidate(
                field=name,
                value=value,
                line=row.line_for(zone),
                text=f"{row.label}: {row.value_for(zone)} ({zone})",
                quote=f"{path}#L{row.line_for(zone)}",
                source="table",
                notes=table.notes_for(row, zone) + glued,
                housing_type=htype,
            )
        )
    return out
