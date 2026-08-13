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

from flats.encode.extract import _PAGE_NUMBER, Candidate, _furniture, _subject
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
        """The footnote texts attached to one zone's cell in one row."""
        return tuple(self.notes[n] for n in row.marks_for(zone) if n in self.notes)

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
    if not found or not _HEADER_HINT.search(found[0][1]):
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
                    _FOOTNOTE.sub("", cell),
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
            value = _FOOTNOTE.sub("", cell)
            if _marks(cell):
                marks[zone] = _marks(cell)
            if zone in values and values[zone] != value:
                # Two cells, one column. The layout cannot say which is this
                # zone's standard, and picking either is how a number ends up
                # under a zone it was never written for.
                contested.add(zone)
            values[zone] = value

        joined = " ".join(label_parts).strip()
        if joined.endswith(":"):
            # "Setbacks (ft):" — a heading, not a row, whatever stray cells
            # sit beside it. It scopes every row after it (across page breaks,
            # which is why a header re-anchor does not clear it) until the
            # next heading takes over.
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


def _marks(cell: str) -> tuple[int, ...]:
    """Footnote numbers on a cell, in the order they appear."""
    return tuple(int(m.group("n")) for m in _FOOTNOTE.finditer(cell))


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
        name = _subject(row.label)
        if name is None and "setback" in row.group.lower():
            # "Front yard" under "Setbacks (ft.):" — the group heading, not
            # the row label, is what says these are setbacks at all.
            name = _GROUPED_SUBJECTS.get(row.label.strip(" .").lower())
        if name is None:
            continue
        parsed = measure(row.value_for(zone)) or _measure_bare(
            row.value_for(zone), row.label, row.group
        )
        if parsed is None:
            continue
        number, kind = parsed
        if FIELDS[name].kind != kind:
            continue
        value = int(number) if number.is_integer() else number
        out.append(
            Candidate(
                field=name,
                value=value,
                line=row.line_for(zone),
                text=f"{row.label}: {row.value_for(zone)} ({zone})",
                quote=f"{path}#L{row.line_for(zone)}",
                source="table",
                notes=table.notes_for(row, zone),
            )
        )
    return out
