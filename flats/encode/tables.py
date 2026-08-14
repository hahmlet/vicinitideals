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
from dataclasses import replace
from typing import Container, Iterable, Sequence

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
    r"(?P<unit>sq\.?\s*ft\.?|square feet|s\.?f\.?|ft\.?|feet|foot|percent|%)(?![A-Za-z0-9])",
    re.I,
)
#: Footnote markers travel with the value. They are not part of the number and
#: they are not noise either: "30 ft. [3]" and "[3] Additional height may be
#: allowed" together say the standard has an exit. Reading the number and
#: dropping the marker encodes a ceiling the code does not actually impose.
_FOOTNOTE = re.compile(r"\s*\[(?P<n>\d+)\]\s*$")
#: "[3] Additional FAR and height may be allowed. See 33.110.265.F."
_NOTE = re.compile(r"^\[(?P<n>\d+)\]\s+(?P<text>.+)$")
#: A table's own caption and the number that identifies it — "Table 220-4.
#: Development Standards ...". Two tables under one section heading run
#: together otherwise, and the second one's rows read under the first one's
#: columns: Wood Village's unit-count table put "60 ft" under the townhouse
#: column of the table above it. Only a *different* number ends the table:
#: a chapter PDF reprints the same caption at every page break, and treating
#: that as a new table cuts the grid off at the first page boundary.
_TABLE_CAPTION = re.compile(r"^Table\s+(?P<id>[\w.-]+)", re.I)
#: The heading over a footnote block that numbers its definitions without
#: brackets. Written to survive a colspan repeat — a caption cell spanning the
#: whole table prints "NOTES:  NOTES:" once per column it covers.
#: The identifier is allowed because Gresham heads its block "Table 4.0130
#: Notes:" — which the caption rule would otherwise swallow, taking the whole
#: block with it.
_NOTES_HEAD = re.compile(
    r"^(?:table\s+[\w.-]+\s+|table\s+)?notes?\s*[:.]?"
    r"(?:\s+(?:table\s+[\w.-]+\s+|table\s+)?notes?\s*[:.]?)*$",
    re.I,
)
#: One such definition, in either spelling: "2<gap>Townhomes are exempt from
#: the lot width requirements." or "2. Zero lot line dwellings shall have...".
#: A number alone is not enough — either the period or the column gap has to
#: be there, or "3.130 TROUTDALE DEVELOPMENT CODE" defines footnote 3.
_BARE_NOTE = re.compile(r"^(?P<n>\d{1,2})(?:\.\s+|\s{2,})(?P<text>\S.*)$")
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


def zone_key(zone: str) -> str:
    """A zone name reduced to what identifies it.

    Spacing, hyphens and case are typography: the GIS layer writes "LR 7.5",
    the table header prints "LR7.5", and the code writes "R-7.2" where the
    layer says "R7.2". Everything else has to match exactly — R5 and R7 are
    not the same district however similar they look.
    """
    return zone.replace(" ", "").replace("-", "").lower()


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

    def _key(self, mapping, zone: str, default):
        """One zone's entry, matched loosely on spelling.

        The GIS layer writes "LR 7.5" and the table header prints "LR7.5";
        the code writes "R-7.2" where the layer says "R7.2". Spacing and
        hyphens are typography, not identity — everything else has to match
        exactly. The stacked reader has always matched this way; the column
        reader got the same rule the day a table's header stopped being one
        zone code per line and started being a real grid.
        """
        if zone in mapping:
            return mapping[zone]
        want = zone_key(zone)
        for name, value in mapping.items():
            if zone_key(name) == want:
                return value
        return default

    def marks_for(self, zone: str) -> tuple[int, ...]:
        return self._key(self.marks, zone, ())

    def value_for(self, zone: str) -> str:
        if any(zone_key(z) == zone_key(zone) for z in self.contested):
            return ""
        return self._key(self.cells, zone, "")

    def line_for(self, zone: str) -> int:
        return self._key(self.lines, zone, self.line)


@dataclass(frozen=True, slots=True)
class Table:
    """The rows of one table and the footnotes printed beneath it."""

    rows: tuple[Row, ...] = ()
    #: True when the columns are housing types rather than zones — Wood
    #: Village's Table 220-3 states one column per type for the whole MR
    #: family. Which zones such a table speaks for is not in the table; it
    #: comes from the section it is printed under, so these rows are read
    #: zone-blind and gated by the declared section, like prose.
    typed: bool = False
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
        # label cell at all. All cells must be zone codes, and none may read
        # as an empty value: "NA  NA  NA" is a row of empty cells whose label
        # wrapped onto another line, and _ZONE cannot tell it from a district.
        # Digit-less families — Springwater's VLDR-SW / LDR-SW / THR-SW —
        # are real headers too, but only when the names differ: a wrapped
        # label row repeats one token, a header names distinct districts.
        zones = [
            Column(text, offset)
            for offset, text in found
            if _ZONE.match(text) and not _NOT_A_NUMBER.match(text)
        ]
        if (
            len(zones) >= 2
            and len(zones) == len(found)
            and (
                any(any(ch.isdigit() for ch in c.zone) for c in zones)
                or len({c.zone for c in zones}) > 1
            )
        ):
            return ZONES_ACROSS, tuple(zones)
        return None
    rest = found[1:]
    zones = [Column(text, offset) for offset, text in rest if _ZONE.match(text)]
    if len(zones) >= 2:
        return ZONES_ACROSS, tuple(zones)
    # Columns naming housing types rather than districts — "Townhouse |
    # Detached Single Dwelling | Duplex Triplex Quadplex". Every cell must
    # name a type: one type column beside three zone columns is a zone table
    # with a stray label, and reading it as typed would drop the zones.
    types = [
        Column(found_type, offset)
        for offset, text in rest
        if (found_type := _housing_type(text)) is not None
    ]
    if len(types) >= 2 and len(types) == len(rest):
        return TYPES_ACROSS, tuple(types)
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
#: Housing types across the top, standards down the side, and no zone named
#: anywhere in the table.
TYPES_ACROSS = "types-across"


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
        if first is not None and _NOTES_HEAD.match(line.strip()):
            # A headed footnote block reads as prose to the sentence rule
            # below, which would end the span on the first definition long
            # enough to close like a sentence — and Troutdale's do.
            return first, _end_of_bare_notes(lines, i)
        if first is not None and _ends_table(line.strip()):
            if _NOTE.match(line.strip()):
                # The footnote block belongs to the table. It ends the rows and
                # begins the conditions attached to them, which are the half of
                # the standard a reader that stops here never sees.
                return first, _end_of_notes(lines, i)
            return first, i
    return first, len(lines)


#: How far past a notes heading the span may run. The reader inside the span
#: refuses anything that is not a definition or the wrap of one, so an
#: over-long span costs nothing; the cap is only here so a document with no
#: heading after its notes cannot swallow the rest of the chapter.
_NOTES_REACH = 120


def _end_of_bare_notes(lines: Sequence[str], start: int) -> int:
    """Index just past a footnote block that heads itself.

    Generous on purpose. Such a block survives page breaks, running headers
    and a reprinted column header — Troutdale's notes 3 through 5 are printed
    on the page after notes 1 and 2, with the table's own header line between
    them. What genuinely ends it is a heading: a lettered one, or the next
    section number, or the caption of the next table.
    """
    seen = False
    for i, line in enumerate(lines[start : start + _NOTES_REACH], start=start):
        stripped = line.strip()
        if i == start:
            continue
        if _BARE_NOTE.match(stripped):
            seen = True
            continue
        if (
            _GROUP_HEAD.match(stripped)
            or _ENDS_TABLE.match(stripped)
            or _TABLE_CAPTION.match(stripped)
        ):
            return i
        if seen and header(line) is not None:
            # A header inside the block is a page reprint only if the block
            # carries on beneath it. When the next thing printed is a row, the
            # notes are over and the next table has started.
            following = next((n.strip() for n in lines[i + 1 : i + 4] if n.strip()), "")
            if not _BARE_NOTE.match(following):
                return i
    return min(len(lines), start + _NOTES_REACH)


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
    # The caption in force. Seeded from just above the header, because that is
    # where a table's own title is printed — anything found later that names a
    # different table ends this one.
    caption = ""
    for prev in reversed(lines[max(0, first - 6) : first]):
        found_caption = _TABLE_CAPTION.match(prev.strip())
        if found_caption:
            caption = found_caption.group("id").strip(".:")
            break
    reach = _MIN_REACH
    rows: list[Row] = []
    down: dict[str, dict[str, tuple[str, int, tuple[int, ...]]]] = {}
    notes: dict[int, str] = {}
    note_lines: dict[int, int] = {}
    in_notes = False
    last_note: int | None = None
    wrap_ok = False

    for n, line in enumerate(lines[first:last], start=start_line + first):
        stripped = line.strip()
        if stripped.endswith(":") or _NOTES_HEAD.match(stripped):
            # Exempt from the furniture check below: "Setbacks (ft):" repeats
            # in every housing-type table of the chapter, which reads as page
            # decoration by frequency — but it is the heading that says the
            # rows under it are setbacks at all. Running headers and revision
            # stamps do not end with a colon. "Table Notes" earns the same
            # exemption for the same reason: every table in the chapter prints
            # one, which is precisely what makes frequency mistake it for
            # decoration and drop the whole footnote block with it.
            pass
        elif not stripped or stripped in junk or _PAGE_NUMBER.match(stripped):
            # Page furniture interrupts a table without ending it: a chapter
            # PDF stamps its title and revision date between the last row of
            # one page and the first row of the next.
            wrap_ok = False
            continue

        head = header(line)
        if head and in_notes:
            # A page break inside the footnote block reprints the column
            # header, sometimes only its second row. That is not a new table
            # and it does not end this one — Troutdale's notes 3 through 5
            # are printed after exactly such a reprint.
            wrap_ok = False
            continue
        if head:
            if cols and (head[0], tuple(c.zone for c in head[1])) != (
                kind,
                tuple(c.zone for c in cols),
            ):
                break  # a different table has started
            # Re-anchored on every header: a table continued onto a new page
            # is the same table, but its columns rarely land on the same offsets.
            kind, cols = head[0], head[1]
            if kind == ZONES_ACROSS:
                slots = _slots(line)
            elif kind == TYPES_ACROSS:
                # Every header cell after the label is a type column — the
                # shape was only accepted when they all were — so print order
                # places a structurally complete row without offsets.
                slots = tuple(c.zone for c in cols)
            else:
                slots = ()
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
        if _NOTES_HEAD.match(stripped):
            # Happy Valley and Gresham head the footnote block instead of
            # bracketing each definition. Without the heading there is nothing
            # to tell "2  Townhomes are exempt..." from a row, and every
            # condition under it reads as a placeholder — which makes the
            # value it qualifies unquotable and the standard unreviewable.
            in_notes = True
            continue
        if in_notes:
            found_bare = _BARE_NOTE.match(stripped)
            if found_bare is not None:
                last_note = int(found_bare.group("n"))
                notes[last_note] = found_bare.group("text").strip()
                note_lines[last_note] = n
                wrap_ok = True
                continue
            if _GROUP_HEAD.match(stripped) or _ENDS_TABLE.match(stripped):
                break  # a heading: the block is over, and so is the table
            # A definition wraps — Troutdale's note 1 runs onto a second line,
            # and a condition cut in half reads as a different condition. Only
            # the line *immediately* after a definition can be its wrap: a page
            # stamp or a reprinted header between the two means whatever comes
            # next is on the far side of a page break and belongs to nothing.
            broken = last_note is not None and notes[last_note].endswith("-")
            if (
                wrap_ok
                and last_note is not None
                and len(_cells(stripped)) == 1
                and (len(stripped.split()) > 1 or broken)
            ):
                # A word split across the line break is rejoined without its
                # hyphen — "abutting zoning dis-" / "trict." is one word, and
                # a one-word wrap is only credible when something is waiting
                # for it.
                notes[last_note] = (
                    notes[last_note][:-1] + stripped
                    if broken
                    else f"{notes[last_note]} {stripped}".strip()
                )
            else:
                wrap_ok = False
            continue
        found_caption = _TABLE_CAPTION.match(stripped)
        if found_caption:
            name = found_caption.group("id").strip(".:")
            if caption and name != caption:
                break  # a different table's caption
            caption = caption or name
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
        if (
            joined
            and not values
            and joined[0].isupper()
            and (_subject(joined) is not None or _PAIR_GROUP.search(joined))
            and len(joined.split()) <= _GROUP_WORDS
            and not joined.endswith(".")
        ):
            # "Building setbacks (minimum)8", "Lot coverage (maximum)5,8,9" —
            # Happy Valley's HTML grid heads each block with a label row whose
            # cells are empty. No leading letter and no colon, so neither
            # heading rule above catches it, and without this one the line
            # glues onto the row above as a continuation: the block boundary
            # vanishes and every sub-row under it ("Rear", "Interior side")
            # loses the heading that says which standard it states.
            #
            # The capital is what separates the two: Portland wraps "- Front
            # building setback" across lines, and its tail — " setback" — says
            # "setback" as loudly as any heading does. A heading is written as
            # one; the back half of a wrapped label is not.
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
    return Table(
        rows=tuple(rows), notes=notes, note_lines=note_lines, typed=kind == TYPES_ACROSS
    )


#: A footnote number glued straight onto the unit — "35 ft.12", "16 ft.7",
#: "20,000 sq. ft.1". A PDF superscript loses its baseline in extraction and
#: lands inline; reading the prefix and dropping the digits would encode the
#: base case of a conditional standard as if the condition did not exist.
#: Anchored on the unit so a decimal never donates its fraction: "7.5 ft"
#: has no digits after the unit, and "35 ft.12" cannot be 35.12 because the
#: number a unit follows is already complete.
_GLUED_NOTE = re.compile(r"^(?P<body>.*?(?:sq\.?\s*ft\.?|sf|ft\.|feet|%))\s?(?P<n>\d{1,2})$")


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
    if unit in ("sqft", "squarefeet", "sf"):
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
#: Happy Valley's stacked grid drops the word "yard": "Front", "Interior
#: side", "Street side (corner lot)". Bare directions are trusted only where
#: column geometry pins the zone — the stacked reader. A bare "Front" /
#: "10 ft." pair has no such anchor: Lake Oswego's WLG R-2.5 structure-type
#: table pairs exactly that way, and reading it as zone evidence lands one
#: sub-zone's setbacks on every zone that declares the section.
_BARE_GROUPED = {
    "front": "setback_front_ft",
    "side": "setback_side_ft",
    "interior side": "setback_side_ft",
    "street side": "setback_street_side_ft",
    "rear": "setback_rear_ft",
}
#: A heading naming the lot itself, scoping rows that name only an axis.
#: Lake Oswego prints "MIN. LOT DIMENSIONS" over "Area (sq. ft.)", "Width
#: (ft.)" and "Depth (ft.)" — the same division of labour the setback
#: headings make, one standard split across its own dimensions.
_LOT_BLOCK = re.compile(r"\blot\b.*\b(?:dimensions?|standards?|sizes?|areas?)\b", re.I)
_LOT_GROUPED = {
    "area": "min_lot_sqft",
    "size": "min_lot_sqft",
    "lot area": "min_lot_sqft",
    "width": "min_lot_width_ft",
    "lot width": "min_lot_width_ft",
    "frontage": "min_frontage_ft",
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
    # "Uses" is required on purpose: Happy Valley's frontage rows sub-label
    # by lot context ("All other lots"), and a bare "all others" pattern
    # would read a cul-de-sac tier as the pod's default row.
    (re.compile(r"\ball other uses?\b|\bother uses\b", re.I), "default"),
    (re.compile(r"\ball (?:residential )?uses\b", re.I), "all"),
    # Wood Village writes the same type "Detached Single Dwelling".
    (
        re.compile(r"\bsingle[ -](?:family[ -])?detached\b|\bdetached single\b", re.I),
        "single_detached",
    ),
    (re.compile(r"\bduplex(?:es)?\b", re.I), "duplex"),
    (re.compile(r"\btriplex(?:es)?\b", re.I), "triplex"),
    (re.compile(r"\b(?:quad|four)-?plex(?:es)?\b", re.I), "quadplex"),
    (re.compile(r"\bcottage\s+(?:clusters?|housing)\b", re.I), "cottage_cluster"),
    # Oregon's statutory umbrella (ORS 197.758): duplexes, triplexes,
    # quadplexes, townhouses and cottage clusters, named as one class. A
    # city that reduces a standard for middle housing has reduced it for
    # the pod — Gladstone's R-7.2 minimum lot area is 7,200 sf detached
    # and 3,600 sf middle housing, and only the second is the pod's.
    (re.compile(r"\bmiddle\s+housing\b", re.I), "middle_housing"),
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


def _after(lines: Sequence[str], n: int, junk: Container[str]) -> str:
    """The next line that carries anything, or ``""`` at the end.

    ``n`` is 1-based, matching the enumeration the readers walk in, so this
    starts at the line after it.
    """
    for raw in lines[n:]:
        stripped = raw.strip()
        if stripped and stripped not in junk and not _PAGE_NUMBER.match(stripped):
            return stripped
    return ""


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
    #: Consecutive lines that are nothing but a housing-type name. Two in a
    #: row is a type-column header — Wood Village's Table 220-3 linearises
    #: "Townhouse / Detached Single Dwelling / Duplex / ..." then prints each
    #: label over a ragged run of values whose empties vanished with the
    #: geometry. Nothing after that header can say which type a value
    #: belongs to, so nothing after it is read — a wrong-column number that
    #: happens to agree is a coincidence detector, not corroboration.
    type_run = 0
    types_across = False
    #: The housing type the next measurement answers for, and whether the
    #: label above is being answered type by type. Once a stack is typed,
    #: an untyped measurement under it is not the zone's standard — it is a
    #: row whose type line this reader failed to recognise — and filing it
    #: as one would put some other housing type's number under the pod's.
    pending_type = ""
    typed_stack = False

    for n, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if not stripped or stripped in junk or _PAGE_NUMBER.match(stripped):
            continue
        found = _SECTION.match(stripped)
        if found:
            section = found.group("sec")
            group = ""
            label = None
            type_run = 0
            types_across = False
            pending_type = ""
            typed_stack = False
            continue
        if (
            _housing_type(stripped) is not None
            and not any(ch.isdigit() for ch in stripped)
            and len(stripped.split()) <= _GROUP_WORDS
            and not stripped.endswith(".")
        ):
            if label is not None and _measure_line(_after(lines, n, junk)) is not None:
                # A type sub-row of the standard above it: "Minimum Lot Area"
                # over "Detached single household" over "7,200 sf" over
                # "Middle housing" over "3,600 sf". The label survives — every
                # sub-row answers the same standard — and what changes is
                # whose answer it is. Refusing these read Gladstone's R-7.2 as
                # a 7,200 sq ft minimum with no middle-housing row at all,
                # which is double the lot a quadplex there actually needs.
                pending_type = _housing_type(stripped)
                continue
            type_run += 1
            if type_run >= 2:
                types_across = True
            label = None
            pending_type = ""
            continue
        type_run = 0
        if types_across:
            continue
        if label is not None:
            parsed = _measure_line(stripped)
            if pending_type and _measure_line(_after(lines, n, junk)) is not None:
                # Two measurements in a row under two labels is not a stack,
                # it is a two-column header that lost its columns: West Linn
                # prints "Street side yard / Townhouse street side yard / 30
                # ft / 15 ft", and reading it as a stack files the first
                # column's number under the second column's type. It agreed
                # with the encoded value, which is the worst way to be wrong.
                label = None
                pending_type = ""
                typed_stack = False
                continue
            if parsed is not None and (pending_type or not typed_stack):
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
                            housing_type=pending_type,
                        )
                    )
                if pending_type:
                    # The stack continues: the next type line answers the same
                    # standard. Only a new label or a heading ends it.
                    typed_stack = True
                    pending_type = ""
                    continue
                label = None
                continue
            pending_type = ""
            if not typed_stack:
                label = None
            # Otherwise the stack survives the line. Gladstone prints
            # "2,500 sf within Gladstone Town Center" under the detached row
            # and then goes on to duplex, quadplex and cottage cluster;
            # ending the stack on the qualifier lost the quadplex row, which
            # is the only row of the six written for the pod. Nothing can be
            # filed from an untyped line while a stack is live, so keeping
            # the label costs no attribution.
        has_digit = any(ch.isdigit() for ch in stripped)
        words = len(stripped.split())
        if not has_digit and words <= _PAIR_WORDS and not stripped.endswith("."):
            if _subject(stripped) or (
                group and stripped.strip(" .:").lower() in _GROUPED_SUBJECTS
            ):
                label = stripped
                # A new standard, so whatever the last one was answered type
                # by type stops applying: the next measurement under this
                # label is its own, untyped, and belongs to the zone.
                typed_stack = False
                pending_type = ""
        if not has_digit and words <= _PAIR_WORDS + 2 and _PAIR_GROUP.search(stripped):
            group = stripped
            typed_stack = False
            pending_type = ""
    return out


#: A footnote as Wood Village prints one — "10 ft(1)" — rather than the
#: bracketed form. Digits only: "(See 210.320)" is a cross-reference cell.
_PAREN_NOTE = re.compile(r"\((?P<n>\d{1,2})\)")
#: A line that is only a cross-reference or comment cell — "(See 210.340)".
_PAREN_LINE = re.compile(r"^\(.*\)$")
#: What is left of a line after its section number and any subsection it
#: names. A heading has a title here; a cross-reference has nothing.
_SUBSECTIONS = re.compile(r"^(?:\s*\([A-Za-z0-9]{1,4}\))*\s*[.,;]?\s*$")
#: A cell stating the standard does not apply in this column.
_DASH = re.compile(r"^[—–-]$")
#: A row label may open with a list dash: "– Min. lot area(2)".
_LABEL_DASH = re.compile(r"^[—–-]\s+")
#: A block of rows scoped to corner lots. The street-side setback's natural
#: home — the standard only exists on a corner — but every other field there
#: is a corner *variant* of the base standard above it, and reading one as
#: the base is how 5 ft becomes 10.
_CORNER_BLOCK = re.compile(r"\bcorner\b", re.I)
#: Footnote refs glued straight onto a row label — "Lot width (minimum)2,6",
#: "… cottage cluster1,6". Superscripts lose their baseline in a stacked grid
#: the same way they do in cells; left in place they make every such label
#: fail the no-digit rule and the whole row goes unread. Anchored after a
#: letter or a closing paren so a number that is part of a name ("R-2.5")
#: never sheds its digits.
_LABEL_REFS = re.compile(r"(?:(?<=[a-z])|(?<=\)))(?P<refs>\d{1,2}(?:,\d{1,2})*)$")
#: Parenthesised context on a grouped row label — "Street side (corner lot)".
_PAREN_CTX = re.compile(r"\([^)]*\)")
#: A cell stating the standard is set case-by-case rather than as a number —
#: Happy Valley prints "Variable4" down the whole MUR-S column.
_VARIABLE = re.compile(r"^variable$", re.I)


def _grid_value(line: str, label: str, group: str = "") -> tuple[float, str, tuple[str, ...]] | None:
    """One stacked-grid cell as (number, kind, notes), or None.

    Whole-line like a pair's value, after setting aside paren and glued
    footnotes — which are kept: "10 ft(1)" and "45 feet5" are base cases
    with an exit, and the marker is what says so.
    """
    marks = tuple(f"footnote ({m.group('n')})" for m in _PAREN_NOTE.finditer(line))
    cell = _PAREN_NOTE.sub("", line).strip()
    cell, glued = _unglue(cell)
    marks += tuple(f"footnote {n} (text not captured)" for n in glued)
    parsed = _measure_line(cell) or _measure_bare(cell, label, group)
    if parsed is None:
        return None
    number, kind = parsed
    return number, kind, marks


def _grid_vocab(line: str) -> bool:
    """Whether a repeated line is grid vocabulary rather than page decoration.

    The sibling tables of a district family print the same row labels and
    block headings — Happy Valley's 020-2, 030-2 and 040-2 all say "Front"
    and "Lot depth (minimum)" — and frequency alone would junk them. Dropping
    a label deletes a row boundary, which merges neighbouring value runs and
    the overrun refusal then silently eats both rows. Anything the grid could
    consume as a label or heading is exempt from the junk set.
    """
    label = _FOOTNOTE.sub("", _LABEL_DASH.sub("", _PAREN_NOTE.sub("", line))).strip()
    refs = _LABEL_REFS.search(label)
    if refs:
        label = label[: refs.start()].strip()
    if _subject(label) is not None:
        return True
    bare = " ".join(_PAREN_CTX.sub("", label).split()).strip(" .:").lower()
    if bare in _GROUPED_SUBJECTS:
        return True
    return not any(ch.isdigit() for ch in label) and 0 < len(label.split()) <= 4


#: A zone code named inside a column heading — "Residential Medium (RM)".
_PARENTHESISED_ZONE = re.compile(r"\(([A-Z][A-Z0-9./-]{0,7})\)")

#: The number or letter a printed table uses to order its rows.
_ENUMERATOR = re.compile(r"^(?:\d{1,2}|[a-z])\.\s+")

#: A numbered standard — the level Code Publishing numbers, with lettered
#: housing-type rows beneath it.
_NUMBERED_HEAD = re.compile(r"^\d{1,2}\.\s+\S")

#: A column of commentary rather than of standards. Present in most rows and
#: absent from the rest, so counting it makes every sparse row look short.
#: A heading that declares the unit its rows are measured in — "1. Minimum
#: yard requirements for primary structures (ft)". Longer than a heading is
#: normally allowed to be, and doing a job only a heading can do: the rows
#: under it are "Front yard" and a bare "20", and without the unit the cell is
#: a number of nothing.
_UNIT_HEAD = re.compile(r"\((?:ft\.?|feet|sq\.?\s*ft\.?|square feet|percent|%)\)\s*$", re.I)

_COMMENTARY = re.compile(r"\b(?:additional standards?|exceptions?|notes?|cross.references?)\b", re.I)

#: Any of the dashes a code uses to write a range. The en dash is the common
#: one and the hyphen and the minus sign both turn up in the same table.
_DASHES = "\\-\u2010\u2011\u2012\u2013\u2014\u2015\u2212"
#: "1,500 – 2,999" — a closed band. The high bound absorbs a glued footnote
#: marker ("5,000-6,9992"), which is stripped by comma grouping below.
_BAND_CLOSED = re.compile(
    r"^(?P<low>\d{1,3}(?:,\d{3})*)\s*(?:[" + _DASHES + r"]|to)\s*(?P<high>[\d,]+)$",
    re.I,
)
#: "7,000 and up" — the residual column, which has no ceiling.
_BAND_OPEN = re.compile(
    r"^(?P<low>\d{1,3}(?:,\d{3})*)\s*(?:and (?:up|over|above|greater)|or (?:more|greater)|\+)$",
    re.I,
)
#: What the row of bands is measuring, named by the label above it. Required:
#: a run of ranges with no axis is a column of lot sizes or a column of widths
#: and nothing in the text says which.
_BAND_MEASURES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\blot\s+(?:size|area)\b", re.I), "lot_sqft"),
    (re.compile(r"\blot\s+width\b", re.I), "lot_width_ft"),
    (re.compile(r"\blot\s+depth\b", re.I), "lot_depth_ft"),
)


def _band_bounds(cell: str) -> tuple[float, float | None] | None:
    """One banded column's range, or ``None`` when this is not one."""
    open_ended = _BAND_OPEN.match(cell)
    if open_ended:
        return float(open_ended.group("low").replace(",", "")), None
    closed = _BAND_CLOSED.match(cell)
    if not closed:
        return None
    high = closed.group("high")
    if "," in high:
        # "6,9992" — the footnote marker glued to the last cell of the row,
        # the same way _LABEL_REFS takes one off a label. A comma group is
        # exactly three digits, so anything past the third is not the number.
        head, _, tail = high.rpartition(",")
        high = f"{head},{tail[:3]}"
    return (
        float(closed.group("low").replace(",", "")),
        float(high.replace(",", "")),
    )


def _band_measure(lines: Sequence[tuple[int, str]], upto: int) -> str:
    """The axis the bands above this point are measured on, if one is named."""
    for _, line in reversed(lines[max(0, upto - 6) : upto]):
        for pattern, measure in _BAND_MEASURES:
            if pattern.search(line):
                return measure
    return ""


def _banded_header(
    live: Sequence[tuple[int, str]], start: int, count: int
) -> tuple[tuple[str, ...], int] | None:
    """The lot-size bands of a one-zone table, and where its rows begin.

    Milwaukie's Table 19.301.4 is one zone printed n times — R-MD, R-MD,
    R-MD, R-MD — over four columns split by how big the lot already is. The
    zone name repeated is not evidence of anything on its own; a wrapped
    label row repeats a token too. The band row is the evidence: n ranges in
    a row, under a label naming what is being ranged.

    Without this the table reads as one zone and one column, so every row of
    it is n values under 1 header and refused — which is the right refusal,
    and the reason this shape was invisible rather than wrong.
    """
    for k in range(start + 1, min(start + 14, len(live))):
        bounds = _band_bounds(live[k][1])
        if bounds is None:
            continue
        run = []
        while k + len(run) < len(live):
            got = _band_bounds(live[k + len(run)][1])
            if got is None:
                break
            run.append(got)
        if len(run) != count:
            return None
        measure = _band_measure(live, k)
        if not measure:
            # The ranges are there and the axis is not. Reading them as square
            # feet because square feet is the common case would silently
            # mis-scale a table banded on width by a factor of a hundred.
            return None
        return tuple(_band_token(measure, low, high) for low, high in run), k + len(run)
    return None


def _band_token(measure: str, low: float, high: float | None) -> str:
    """``lot_sqft:3000-4999`` — how the model names one band."""
    lo = str(int(low)) if float(low).is_integer() else str(low)
    if high is None:
        return f"{measure}:{lo}+"
    hi = str(int(high)) if float(high).is_integer() else str(high)
    return f"{measure}:{lo}-{hi}"


def _looks_like_label(line: str) -> bool:
    """Whether this line could open a row — the thing a heading is followed by."""
    label = _LABEL_DASH.sub("", _PAREN_NOTE.sub("", line)).strip()
    # Both enumerator cases: "1. Minimum Lot Size" numbers the standards and
    # "a. Single Unit" letters the housing types under it, in the same table.
    if _ENUMERATOR.match(label) or _GROUP_HEAD.match(label):
        return True
    if _housing_type(label) or _subject(label):
        return True
    bare = " ".join(_PAREN_CTX.sub("", label).split()).strip(" .:").lower()
    return bare in _GROUPED_SUBJECTS or bare in _BARE_GROUPED or bare in _LOT_GROUPED


#: A cell that is only a pointer — "§ 50.04.001.1.c", "(See 210.340)". It
#: holds a comment column, and a heading is often followed by one before the
#: rows it scopes begin.
_POINTER_CELL = re.compile(r"^[^\w\s]?\s*(?:See\s+)?\d{1,3}\.\d{2,4}(?:\.\d{1,4})*\b", re.I)


def _pointer_cell(line: str) -> bool:
    return bool(_PAREN_LINE.match(line) or _POINTER_CELL.match(line))


def _reprinted(line: str) -> bool:
    """Whether a line repeated immediately above is the same cell twice.

    A cell spanning two rows comes back from the HTML with its text printed
    once per row it spans, so Lake Oswego's table reads "MIN. LOT DIMENSIONS"
    twice, then "Area (sq. ft.)" twice, then its three values. Taking the
    second copy for the row's first cell refused every row in the table.

    Only headings and labels qualify. Cells repeat legitimately — three zones
    stating "15" or "NA" is three cells, not one printed three times — and
    collapsing those would shorten the row and shift every value in it.
    """
    return (
        _grid_vocab(line)
        and _measure_line(line) is None
        and not _BARE_NUMBER.match(line)
        and not _DASH.match(line)
        and not _NOT_A_NUMBER.match(line)
    )


def _scoped_cell(cell: str) -> bool:
    """A cell stating a number on some other basis than the row's.

    "2,500 per unit" under minimum lot size, "10,000 for single unit detached"
    under maximum lot size: the column answers, and its answer is not this
    row's standard for this zone. Nothing may be filed from it — but it holds
    a column, and treating it as a broken row discards the plain numbers
    printed beside it.
    """
    words = cell.split()
    return len(words) > 1 and len(words) <= 5 and words[0][:1].isdigit()


def _labelish(label: str) -> bool:
    """Whether a line could be a row label rather than one of the cells.

    A digit anywhere used to disqualify it, which is right for cells and wrong
    for the tables that number their rows: "7. Front Yard Setback Minimum" is a
    label with an enumerator, and Code Publishing prints every Oregon chapter
    that way. The enumerator comes off before the question is asked; what is
    left has to read like prose.
    """
    return not any(ch.isdigit() for ch in _ENUMERATOR.sub("", label, count=1))


def _column_heading(line: str, following: str) -> bool:
    """Whether this line is one more column of a header run, not the first row.

    A dimensional table's columns are not all zones. Fairview's is five zone
    columns wide plus "Townhouse Overlay" and "Additional Standards and
    Exceptions"; counting only the zone codes makes every row look three cells
    wide, and a five-value row read three-wide either mis-attributes two
    columns or — because of the overrun refusal — reads nothing at all. It read
    nothing, which is why thirty-six Fairview values had no evidence behind a
    chapter that states all of them.

    The line after is what separates a column from a row: a row label is
    followed by its values, a column heading by another heading or by the first
    row. So "Min. lot area" over "12,000 sq ft" is a row, and "Townhouse
    Overlay" over "Residential Medium (RM)" is a column.
    """
    label = " ".join(line.split())
    return (
        len(label.split()) >= 2
        and label[0].isupper()
        and not any(ch.isdigit() for ch in label)
        and not _GROUP_HEAD.match(label)
        and _subject(label) is None
        and _measure_line(label) is None
        and not _NOT_A_NUMBER.match(label)
        and not _DASH.match(following)
        and _grid_value(following, label) is None
    )


def _column_zone(line: str) -> str:
    """The zone a column heading names, or "" for a column that names none.

    An unnamed column still has to be counted — it is what makes the row's
    arity right — but nothing may be filed under it. "" is that column: it
    holds a place and takes no value.
    """
    found = _PARENTHESISED_ZONE.search(line)
    return found.group(1) if found and _ZONE.match(found.group(1)) else ""


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

    Labels must name their standard, either outright ("– Front setback") or
    through the one block heading above them that does — "Front" under
    "Building setbacks (minimum)" reads, because the heading names the
    standard and the row the direction. Nested blocks — Lake Oswego's
    "Front (ft.)" under "Primary Structure" under "YARD SETBACKS", printed
    again under "Accessory Structure" — still produce nothing: the nearest
    heading there names a structure, not a standard, and an
    accessory-structure setback wearing the zone's citation is the
    expensive kind of wrong.
    """
    lines = text.splitlines()
    junk = {
        j
        for j in _furniture([line.strip() for line in lines])
        if _measure_line(j) is None
        and not _ZONE.match(j)
        and not _grid_vocab(j)
        # A cell whose unit is in the row label rather than in the cell —
        # "6,000" under "Minimum Lot Size (sq. ft.)" — is a bare number, and
        # bare numbers repeat: Fairview's three zones state the same lot size
        # for six housing types apiece. Frequency junked them, which deleted
        # the cells and left every row one value short of its header.
        and not _BARE_NUMBER.match(j)
    }
    live = [
        (n, line.strip())
        for n, line in enumerate(lines, start=1)
        if line.strip() and line.strip() not in junk and not _PAGE_NUMBER.match(line.strip())
    ]
    kept: list[tuple[int, str]] = []
    #: How many identical copies of a surviving line were collapsed into it,
    #: by index into `kept`. A rowspan reprint is noise everywhere except in a
    #: header, where the count is the number of columns that zone was printed
    #: over — which is the only thing that distinguishes a banded table from a
    #: table with one column.
    repeats: dict[int, int] = {}
    for k, pair in enumerate(live):
        if kept and pair[1] == live[k - 1][1] and _reprinted(pair[1]):
            repeats[len(kept) - 1] = repeats.get(len(kept) - 1, 1) + 1
            continue
        kept.append(pair)
    live = kept

    out: dict[str, list[Candidate]] = {}
    zones: tuple[str, ...] = ()
    #: One band token per column, where the table states its standards per lot
    #: size rather than per zone. Empty strings elsewhere — most tables.
    bands: tuple[str, ...] = ()
    #: Columns the header declared and this reader does not count — the
    #: "Comments/Additional Standards" column. Their cells still print, after
    #: the cells that were counted.
    spare = 0
    section = ""
    block = ""
    block_refs: tuple[str, ...] = ()
    block_field = ""
    #: A heading naming who the rows under it are for rather than what they
    #: state — "Townhouses (one per lot)" over an area row and a width row.
    #: Without it those rows read as the zone's own minimum, and a townhouse
    #: unit lot is a tenth of one.
    block_type = ""
    i = 0
    while i < len(live):
        n, stripped = live[i]
        found = _SECTION.match(stripped)
        if found and zones and _SUBSECTIONS.match(stripped[found.end() :]):
            # A cross-reference in the table's own commentary column, not a
            # heading: Fairview's "Additional Standards and Exceptions" prints
            # "19.30.030(B)(1)(b)" beside the front setback row, and treating
            # that as the start of a new section cleared the zone header — so
            # every row below it, rear and side setbacks and coverage
            # included, went unread inside a table already being read.
            found = None
        if found:
            section = found.group("sec")
            zones = ()
            bands = ()
            block = ""
            block_refs = ()
            block_field = ""
            block_type = ""
            i += 1
            continue
        run = []
        while i + len(run) < len(live) and _ZONE.match(live[i + len(run)][1]):
            run.append(live[i + len(run)][1])
        if len(run) == 1 and repeats.get(i, 1) >= 2 and _ZONE.match(stripped):
            banded = _banded_header(live, i, repeats[i])
            if banded is not None:
                # One zone over n columns, split by lot size. The rows below
                # are read positionally exactly as a zone header's are — what
                # differs is that every cell is one column's standard and none
                # of them is the zone's, so each carries the band it was
                # written for and nothing may encode one as unconditional.
                bands, i = banded
                zones = (stripped,) * len(bands)
                spare = 1
                block = ""
                block_refs = ()
                block_field = ""
                block_type = ""
                continue
        if len(run) >= 2 and any(ch.isdigit() for z in run for ch in z):
            # A run of bare letters is not a header: lettered subsection
            # fragments match _ZONE too, and a real district run carries a
            # digit somewhere (R-40, LR7.5, MUR-S beside R-5).
            j = i + len(run)
            named: list[str] = []
            while j + 1 < len(live) and _column_heading(live[j][1], live[j + 1][1]):
                # A commentary column is consumed and not counted. "Additional
                # Standards and Exceptions" holds a cross-reference in three
                # rows of fifteen and nothing in the rest, so counting it makes
                # every other row one cell short of its header.
                if not _COMMENTARY.search(live[j][1]):
                    named.append(_column_zone(live[j][1]))
                j += 1
            zones = tuple(run) + tuple(named)
            bands = ()
            spare = j - (i + len(run)) - len(named)
            block = ""
            block_refs = ()
            block_field = ""
            block_type = ""
            i = j
            continue
        label = _LABEL_DASH.sub("", _PAREN_NOTE.sub("", stripped)).strip()
        # "a. Front yard" — the enumerator is the table's numbering, not part
        # of what the row states, and the labels that name a yard rather than
        # a setback are matched whole.
        label = _ENUMERATOR.sub("", label, count=1)
        refs: tuple[str, ...] = ()
        bracketed = _FOOTNOTE.search(label)
        if bracketed:
            # "MIN. LOT DIMENSIONS [3]" — the bracketed form of the same
            # superscript _LABEL_REFS takes off the glued form. Left on, its
            # digit fails the no-digit rule and the heading never scopes the
            # rows under it.
            refs = (bracketed.group("n"),)
            label = label[: bracketed.start()].strip()
        glued = _LABEL_REFS.search(label)
        if glued:
            refs = tuple(glued.group("refs").split(","))
            label = label[: glued.start()].strip()
        name = _subject(label)
        ctx_notes: tuple[str, ...] = ()
        if name is None and "setback" in block.lower():
            # "Front" under "Building setbacks (minimum)" — the heading names
            # the standard and the row the direction. Parenthesised context —
            # "Front (street access garage)" — is dropped for the lookup and
            # kept as a note: the 10 ft alley variant beside the 20 ft street
            # variant is a conditional pair, not two clean readings. "(corner
            # lot)" on the street side is the one context that conditions
            # nothing: that standard only exists on a corner.
            bare = " ".join(_PAREN_CTX.sub("", label).split()).strip(" .:").lower()
            name = _GROUPED_SUBJECTS.get(bare) or _BARE_GROUPED.get(bare)
            if name is not None:
                ctx_notes = tuple(
                    f"{m} (row context)"
                    for m in _PAREN_CTX.findall(label)
                    if not (
                        name == "setback_street_side_ft" and _CORNER_BLOCK.search(m)
                    )
                )
        if name is None and _LOT_BLOCK.search(block):
            # "Area (sq. ft.)" under "MIN. LOT DIMENSIONS": the heading names
            # the lot, the row names which of its dimensions. Kept separate
            # from the setback lookup because the two vocabularies collide —
            # "width" under a setback heading is not a lot width.
            bare = " ".join(_PAREN_CTX.sub("", label).split()).strip(" .:").lower()
            name = _LOT_GROUPED.get(bare)
        if _NUMBERED_HEAD.match(label):
            # A numbered standard ends the one above it, whether or not this
            # reader knows what it is. Fairview prints "3. Minimum Net Density
            # (units/acre)" under the lot-size table's numbering, and letting
            # the previous block survive read 5.8 units per acre as a 5.8
            # square foot minimum lot — a standard nobody could satisfy,
            # attached to the right zone with the right citation.
            block = label
            block_field = _subject(label) or ""
            block_refs = refs
            block_type = ""
        if name is None and block_field and len(label.split()) <= _GROUP_WORDS:
            if _housing_type(label):
                # "Duplex, triplex, quadplex, townhome" under a heading whose
                # own row-read failed ("Lot coverage (maximum)") — the heading
                # names the standard and the row names who. Gresham's
                # row-level housing pattern in stacked geometry.
                name = block_field
        next_is_cell = i + 1 < len(live) and (
            bool(_DASH.match(live[i + 1][1]))
            or _grid_value(live[i + 1][1], label, block) is not None
        )
        # A heading may be separated from the rows it scopes by the comment
        # column's cross-reference — Lake Oswego prints "§ 50.04.001.1.c"
        # between "MIN. LOT DIMENSIONS" and "Area (sq. ft.)" — so the test
        # for what follows a heading steps over pointer cells.
        ahead = next(
            (k for k in range(i + 1, min(i + 4, len(live))) if not _pointer_cell(live[k][1])),
            None,
        )
        scopes_a_row = ahead is not None and _looks_like_label(live[ahead][1])
        if (
            zones
            and name is None
            and not block_field
            and _housing_type(label) is not None
            and not next_is_cell
            and scopes_a_row
            and len(label.split()) <= _GROUP_WORDS
            and not any(ch.isdigit() for ch in label)
        ):
            # "Townhouses (one per lot)" over "Area (sq. ft.)" — the heading
            # says whose standard the rows beneath it state, the way a
            # setback heading says which standard. Lake Oswego prints the
            # townhouse unit-lot minimum this way, four lines under the
            # minimum for everything else, in the same column.
            block_type = _housing_type(label) or ""
        if (
            zones
            and name is None
            and not next_is_cell
            # A heading is followed by the row it scopes. "Existing only",
            # stranded mid-row when its row was refused, is followed by
            # "NA" — another orphaned cell — and taking it for a heading
            # cleared the block that grouped the housing-type rows above it,
            # which is how Fairview's lot sizes went unread.
            and scopes_a_row
            and not any(ch.isdigit() for ch in label)
            and (len(label.split()) <= 4 or _UNIT_HEAD.search(label))
            and _housing_type(label) is None
            and not _VARIABLE.match(label)
            and not _NOT_A_NUMBER.match(label)
            and not _PAREN_LINE.match(stripped)
            and _measure_line(stripped) is None
        ):
            # "Minimum Setbacks", "Corner Lots" — a heading scoping the rows
            # under it, until the next heading or header. A heading is never
            # followed by a value line — "Garage and carport entrances" over
            # "22 feet" is an unmatched row, not a new block, and must not
            # end the setbacks block above it — and cell words ("Variable",
            # "None") stranded by a refused row are cells, not headings.
            # Refs glued to a heading ("Building setbacks (minimum)6")
            # condition every row scoped by it.
            block = label
            block_refs = refs
            block_field = ""
            block_type = ""
        if zones and name is not None and _labelish(label):
            in_corner_block = _CORNER_BLOCK.search(block) and name.startswith("setback_")
            if (
                in_corner_block or _CORNER_BLOCK.search(label)
            ) and name != "setback_street_side_ft":
                # Where the block ends is not printed, so the block guard is
                # scoped by field: only setbacks have corner variants, and a
                # coverage row after the corner rows is a sibling, not a
                # member. Corner named on the row itself is exact and guards
                # every field.
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
                bare_cell = _PAREN_NOTE.sub("", cell_line).strip()
                trail = _LABEL_REFS.search(bare_cell)
                if trail:
                    bare_cell = bare_cell[: trail.start()].strip()
                if _VARIABLE.match(bare_cell):
                    # "Variable4" — the standard exists and is not a number;
                    # like a dash it yields this zone no candidate.
                    cells.append(None)
                    j += 1
                    continue
                if _NOT_A_NUMBER.match(bare_cell):
                    # "NA", "None", "No maximum" — the table answers for this
                    # column and the answer is not a number. Breaking here
                    # threw away every row of a table that has an NA in it,
                    # which in a housing-type grid is most of them.
                    cells.append(None)
                    j += 1
                    continue
                parsed = _grid_value(cell_line, label, block)
                if parsed is None:
                    if _scoped_cell(bare_cell):
                        # "2,500 per unit" beside three plain lot sizes: the
                        # column states a standard on a different basis, so it
                        # yields no candidate — but it is a cell, and breaking
                        # on it would throw away the three columns that are
                        # exactly what was being read.
                        cells.append(None)
                        j += 1
                        continue
                    if zones[len(cells)]:
                        break
                    # Prose in a column that names no zone — "Existing only"
                    # under "Townhouse Overlay". Nothing can be filed under it
                    # either way, and stopping would refuse the named columns
                    # beside it over a cell that was never going to be read.
                    cells.append(None)
                    j += 1
                    continue
                cells.append((cell_no, parsed))
                j += 1
            overrun = (
                j < len(live)
                and not _PAREN_LINE.match(live[j][1])
                and _grid_value(live[j][1], label, block) is not None
            )
            if len(cells) == len(zones) and not overrun:
                htype = _housing_type(label) or block_type
                placeholders = ctx_notes + tuple(
                    f"footnote {r} (text not captured)" for r in (*refs, *block_refs)
                )
                for pos, (zone, cell) in enumerate(zip(zones, cells)):
                    if cell is None or not zone:
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
                            notes=marks + placeholders,
                            housing_type=htype,
                            band=bands[pos] if bands else "",
                            section=section,
                        )
                    )
                i = j
                skipped = 0
                while (
                    skipped < spare
                    and i < len(live)
                    and not _looks_like_label(live[i][1])
                    and not _ZONE.match(live[i][1])
                    and _grid_value(live[i][1], label, block) is None
                ):
                    # The commentary column's cell for the row just read.
                    # Left in place it becomes the next line the reader sees,
                    # and Lake Oswego's "Except PD [3]" was then taken for a
                    # block heading — which replaced "MIN. LOT DIMENSIONS"
                    # and cost every row under it its field.
                    i += 1
                    skipped += 1
                continue
            if _subject(label) is not None and _labelish(label):
                # The walk failed under a label that names a standard outright
                # — "Lot coverage (maximum)" over typed sub-rows. The label
                # becomes the block and its field scopes the typed rows under
                # it. Grouped labels ("Interior side") whose rows refuse do
                # not: their standard came from the block they are already in.
                block_field = name
                block_refs = refs
                if _UNIT_HEAD.search(label) or not _UNIT_HEAD.search(block):
                    # ...and a label that declares no unit does not replace a
                    # heading that does. Milwaukie's side yard row refuses on
                    # its "5/10" cell, and "Side yard" taking the block from
                    # "Minimum yard requirements ... (ft)" left every bare
                    # number under it measured in nothing — so one asymmetric
                    # cell cost the street side and rear rows too.
                    block = label
        i += 1
    blocks = _stacked_notes(lines)
    return {zone: [_defined(c, blocks) for c in cands] for zone, cands in out.items()}


#: A note this reader could not define. Written once, matched here, so a later
#: pass can fill in the text without the reader that made it holding the block.
_PLACEHOLDER = re.compile(r"^(?:footnote|see note) (?P<n>\d{1,2}) \(text not captured\)$")
#: A marker on its own line — how a footnote block linearises when the grid
#: was too wide to align and each cell became a line of its own.
_MARKER_LINE = re.compile(r"^\d{1,2}$")


def _stacked_notes(lines: Sequence[str]) -> list[tuple[int, dict[int, str]]]:
    """Footnote blocks in a linearised grid, each with the line it opens on.

    The flowed form prints a marker and its definition on separate lines, and
    the numbering restarts with every table: Happy Valley's note 3 exempts
    cottage clusters from lot coverage under one table and sets a townhouse
    side setback under the next. So a block is kept with its position rather
    than merged into one dictionary, and a value takes the first block printed
    *below* it — which is where a table's own footnotes are.
    """
    blocks: list[tuple[int, dict[int, str]]] = []
    current: dict[int, str] | None = None
    pending: int | None = None
    for n, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        if _NOTES_HEAD.match(stripped):
            if current is None:
                current = {}
                blocks.append((n, current))
            pending = None
            continue
        if current is None:
            continue
        if _MARKER_LINE.match(stripped):
            pending = int(stripped)
            continue
        if pending is not None:
            current[pending] = stripped
            pending = None
            continue
        current = None  # past the definitions
    return blocks


def _defined(candidate: Candidate, blocks: Sequence[tuple[int, dict[int, str]]]) -> Candidate:
    """The same candidate with any placeholder note replaced by its text."""
    if not any(_PLACEHOLDER.match(note) for note in candidate.notes):
        return candidate
    found: dict[int, str] = next(
        (defs for start, defs in blocks if start > candidate.line), {}
    )
    return replace(
        candidate,
        notes=tuple(
            found.get(int(m.group("n")), note)
            if (m := _PLACEHOLDER.match(note))
            else note
            for note in candidate.notes
        ),
    )


def stacked_candidates_for(
    grids: dict[str, list[Candidate]], zone: str
) -> list[Candidate]:
    """One zone's candidates from a stacked grid, matched loosely on spelling.

    The GIS layer writes "LR 7.5" and the table header prints "LR7.5"; the
    code writes "R-7.2" where the layer says "R7.2". Spacing and hyphens are
    typography, not identity — everything else has to match exactly.
    """

    return [
        c for header, cs in grids.items() if zone_key(header) == zone_key(zone) for c in cs
    ]


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
    if table.typed:
        return _typed_candidates(table, path=path)
    out: list[Candidate] = []
    for row in table.rows:
        htype = ""
        ctx_notes: tuple[str, ...] = ()
        name = _subject(row.label)
        if name is None and "setback" in row.group.lower():
            # "Front yard" under "Setbacks (ft.):" — the group heading, not
            # the row label, is what says these are setbacks at all. Glued
            # note refs are stripped before the exact match: "Front yard see
            # note 1 see note 1" is still the front yard row. Parenthesised
            # context — "Front (street access garage)" — is dropped for the
            # lookup and kept as a note, the reading the stacked grid already
            # gives it: the 10 ft alley variant beside the 20 ft street
            # variant is a conditional pair, not two clean readings. Bare
            # directions are safe here for the same reason they are there —
            # the column the cell sits in names the zone.
            clean = " ".join(_SEE_NOTE.sub("", row.label).split())
            bare = " ".join(_PAREN_CTX.sub("", clean).split()).strip(" .:").lower()
            name = _GROUPED_SUBJECTS.get(bare) or _BARE_GROUPED.get(bare)
            if name is not None:
                ctx_notes = tuple(
                    f"{m} (row context)"
                    for m in _PAREN_CTX.findall(clean)
                    if not (
                        name == "setback_street_side_ft" and _CORNER_BLOCK.search(m)
                    )
                )
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
        glued = tuple(
            table.notes.get(int(n), f"see note {n} (text not captured)") for n in refs
        )
        out.append(
            Candidate(
                field=name,
                value=value,
                line=row.line_for(zone),
                text=f"{row.label}: {row.value_for(zone)} ({zone})",
                quote=f"{path}#L{row.line_for(zone)}",
                source="table",
                notes=table.notes_for(row, zone) + glued + ctx_notes,
                housing_type=htype,
            )
        )
    return out


def _typed_candidates(table: Table, *, path: str) -> list[Candidate]:
    """Values a housing-type table states, one reading per type column.

    The table names no zone, so nothing here is zone-keyed: these candidates
    carry the type they were written for and are gated by the section the
    table sits under, exactly as prose is. Which type speaks for the pod is
    selection's decision downstream — a quadplex column and a townhouse
    column are different standards, and reading only one of them here would
    make that choice silently, in the reader, where nobody can see it.
    """
    columns = list(dict.fromkeys(name for row in table.rows for name in row.cells))
    plain = Table(rows=table.rows, notes=table.notes, note_lines=table.note_lines)
    out: list[Candidate] = []
    for htype in columns:
        for candidate in candidates_for(plain, htype, path=path):
            out.append(
                replace(
                    candidate,
                    source="typed-table",
                    housing_type=candidate.housing_type or htype,
                )
            )
    return out
