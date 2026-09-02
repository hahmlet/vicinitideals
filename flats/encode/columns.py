"""Every citation into an aligned table, checked against its own column.

A dimensional table prints one row per housing type and one column per zoning
district, and an encoded value quotes the row. Nothing so far checked that it
took the number from the *right cell of that row* -- the reader can confirm the
number appears on the cited line, which is true of every zone in the row that
happens to share it.

Gresham Table 4.0130 G.1 is the case that produced this module. Its townhouse
row reads ``16 ft. / 16 ft. / 16 ft. / None / None / 16 ft. / None`` across
LDR-5, LDR-7, TR, TLDR, MDR-12, MDR-24 and OFR, and 16 had been carried onto
all six encoded districts. Two of them print None -- no street frontage minimum
at all. Every existing check passed: the quoted line contains "16 ft." three
times over, so the number *is* on the line the citation names. It is simply in
somebody else's column.

The check counts cells. A row is split on runs of whitespace and the district's
cell is taken by position in that row, with the nearest header above giving the
order. Reading by character offset was tried and does not work on these
extractions: they align body rows with each other but not with the header, and
Gresham prints its district codes thirty characters right of the values beneath
them.

It follows a citation onto every line the citation names, and asks agreement of
one of them rather than all -- the other lines are context by design, a header
row quoted to pin a column or a footnote quoted beside the cell it governs. A
citation that names its own header, or the table's caption, is being careful
rather than reaching past the table, so neither line counts against it; before
that was true Troutdale, Happy Valley and all of Wood Village were almost
entirely unjudged, because quoting the header is exactly how those cities say
which of six columns a number came from.

What it will not do is judge a cell it cannot turn into the same kind of thing
as the encoded value. A number against a number, "None" or "NA" against an
exemption, and nothing else: a cell reading "Varies depending on access" hands
its number to a footnote and belongs to :mod:`flats.encode.footnotes`, a cell
reading "see 3.235.B" belongs to :mod:`flats.encode.routing`. Judging those
here would produce confident nonsense in the one place that is meant to be
arithmetic.

Three counts, reported separately because they are different work:

``mismatches``
    The cell states a number and the encoded value is a different number. This
    is the reading error the module exists for.

``vacancies``
    The cell states no standard -- "None", "NA" -- and a number was encoded
    against it, on a field where that is a different claim. Gresham's townhouse
    frontage was one of these. Portland's commercial setbacks are not, though
    they read the same on the page: ``0`` where Table 130-2 says "none". A
    setback is subtracted rather than tested, so both readings let the building
    stand on the line and the number is the one that stays in the arithmetic.
    A minimum lot size of zero is a claim the table does not make. The split is
    ``_ZERO_IS_THE_SAME_AS_NONE``, and it is per field rather than per city.

``reach``
    How many citations the check could read at all. A reader that has stopped
    seeing rows reports a clean corpus in exactly the words of a corpus that is
    clean, so this is pinned by a test.

What it cannot see, so a clean report is read for what it is. Of 2,142 cited
values it reads 751. A little over a third of the remainder name lines in a
document with no table this check recognises. The rest name lines in a document
that has one but outside it; or in a table whose header does not carry that
district; or in a row whose label wraps across several lines, so that no single
line carries a full set of cells -- Gresham's downtown Table 4.1130 spends five
lines on "Minimum Residential Net Density for all residential projects (not
mixed-use) (units per acre)7 (See definition of Net Density in Article 3)", and
a row that is mostly its own title cannot be counted across. The
documents with no recognised table fall into five shapes. The first three are
nothing to check. The last two were the gaps, and both are now read where the
shape can be confirmed and refused whole where it cannot:

*   No table on the cited lines at all -- prose, definitions, a numbered list
    of standards. Wilsonville's planning chapter is the largest single block of
    these at 191 citations, Gresham's Pleasant Valley and Springwater plans
    another 122. There is no column to take a number from.

*   One district per table, or per document. Gladstone gives each district its
    own chapter; Milwaukie's base-zone tables print ``Standard | R-HD |
    Additional Provisions``. A table with one district cannot hand its value to
    another one.

*   A header whose cells do not name districts. Wood Village Table 220-3 reads
    ``Standard | MR4 and MR2 | MR4 and MR2 | MR4 and MR2``: the columns are
    housing types and the district repeats across them, so the header says
    nothing about which column belongs to whom.

*   **A table extracted one cell per line.** Fairview Table 19.30.030.A,
    Clackamas Tables 315-2 and 315-4, Happy Valley Table 16.22.050-2 and every
    table in Lake Oswego's dimensional chapter print their district codes down
    the page rather than across it, with each cell beneath them on its own
    line. This was the largest gap of the five, and Happy Valley's was the
    dangerous one: its attached districts were being looked up in the nearest
    header ABOVE the line, which in that file belongs to the single-family
    table, so 78 citations came back the same way a clean table does.

    ``_vertical`` reads them, and what it has to recover is the one thing the
    horizontal form gives away for free -- where a row ends. It takes the run
    of district codes under the caption as the header and then refuses to trust
    it: at least two rows below must come out that many lines long, or the run
    was not a header. No row may come out LONGER, because a run past the
    district count means the boundary between two rows has been lost, and once
    it is lost anywhere in the table a run of exactly the right length has
    stopped being evidence. And a row that comes out SHORT is skipped where it
    sits, the rest of the table still read.

    That is what divides the three that are read from the one that is not.
    Fairview numbers its row labels -- "1. Minimum Lot Size (sq. ft.)" -- so
    every label reads as a value, its rows run together eighteen lines at a
    stretch under a header of three, and somewhere in eighteen lines there is
    always a run of three that would be read with confidence and no reason. Its
    minimum lot width is nine lines under five districts anyway, because three
    of the five carry a second line reading "20 feet for townhouses" and
    nothing marks that as a continuation rather than a sixth column. So
    Fairview is refused whole and stays hand-read below, and Lake Oswego is a
    jurisdiction currently switched off.

*   **A table whose columns are separated by a single space**, which is read
    by grammar rather than by whitespace and is no longer blind. Cells are
    normally found by splitting on runs of two spaces or more, the only
    separator these extractions offer that a word does not also contain, and
    where a table comes out single-spaced that split returns the whole row as
    one cell.

    ``sparse_cells`` reads those rows by what the words are instead: a cell
    opens on a figure or on a word meaning no standard, runs through the units
    behind it, and the reading stops dead at a word that is neither. Gresham's
    Pleasant Valley and Springwater plan districts come out whole this way --
    ``5,000 sq. ft. 3,000 sq. ft. None`` under a header reading ``LDR-PV
    MDR-PV HDR-PV`` -- and so do the cleanly extracted rows of Oregon City's
    chapter.

    Two guards keep this from producing the error the module exists to catch.
    Every cell of a row has to state the same KIND of quantity, because a row
    of a dimensional table does: without it a row label carrying a measurement,
    "Lots over 5,000 sq. ft.", hands its own number to the first district and
    shifts the whole row one column left. And a single-space header is accepted
    only once some line below it reads as a row of that many values, because
    nothing in the shape separates ``USES LDR-PV MDR-PV HDR-PV`` from
    ``Schools P/SUR15 SUR L/SUR15``, which is a row of a use table three
    hundred lines above the dimensional one. A candidate promoted without that
    evidence does not fail to find a row -- it finds one belonging to a
    different table.

    What still refuses is the rest of Oregon City, which is a scan: there the
    same single space separates the columns and the halves of the broken words
    -- ``Quad pl ex a nd co t tage 1 0 , 000 squ are 8 , 000 squ are 7 , 000 s
    qu are`` -- and "pl" is not a unit, so the reading stops where the
    extraction did. So does Gresham's Table 4.1414, whose eleven columns are
    setback positions rather than districts and whose header is printed down
    the page.

So the gaps were read by hand on 2026-09-02, every dimensional value against
its own column. All but Fairview are since machine-read on every run, by the
two readings above; they are kept here because a hand audit is what those
readings were measured against, and because Fairview, Lake Oswego and the
scanned half of Oregon City are still only this:

*   Fairview's twelve rows across R-6 and R-7.5. The vertical form is checkable
    by eye because the corpus resolved the wraps when it encoded: R-7.5's lot
    width cites L345 and not L344, which is R-6's second line.
*   Oregon City's full set across R-10, R-8, R-6, R-5 and R-3.5, including the
    quadplex lot-size row that is the one this screen builds on.
*   Lake Oswego's low-density table across R-7.5, R-10 and R-15, and the
    per-zone tables for R-6, R-5, R-3, R-2 and R-0 -- which are one district
    each, so what was checked there is the row rather than the column, the
    quadplex line of R-2's Table 50.04.001-13 rather than the duplex above it.
*   Gresham's two plan districts. LDR-PV for lot size, frontage, density and
    the eleven-column setback row, where the encoding correctly separates the
    Interior Side cell from the Common Wall cell beside it -- 5 ft and 0 ft,
    base and ``attached_wall`` variant. LDR-SW and THR-SW for the four rows
    they share, each reading the second and third of three columns: widths 45
    and 20, corner widths 45 and 25, depths 80 and 65, heights 35 and 45.
*   Unincorporated Clackamas across all seven R zones and both VR zones, where
    the citations run in step -- lot coverage L1162 to L1168 in zone order --
    so an off-by-one would show as a repeat or a skip and there is neither.
    R-2.5, the one column of Table 315-1 reading X rather than P for
    quadplexes, is not encoded at all, so nothing reads it as permitted.

All correct. That is a reading of a corpus at a moment, not a check that will
notice if it moves.

Run it::

    uv run python -m flats.encode.columns
    uv run python -m flats.encode.columns or/multnomah/gresham
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

DOCROOT = Path("flats/provenance/docs")
CONFIGROOT = Path("flats/config/jurisdictions")

#: A header cell is a district code: short, starts upper-case, no prose.
_ZONE = re.compile(
    r"^[A-Z][A-Za-z0-9/. \-]{0,14}$|^\([A-Z][A-Za-z0-9/. \-]{0,12}\)$"
)

#: Cells are separated by runs of two or more spaces in the extracted text.
_SPLIT = re.compile(r"\s{2,}")

#: ``quote: "or/multnomah/gresham/4.0100.residential.txt#L313"``, and the
#: multi-line forms beside it: ``#L315,L319``, ``#L316-L318,L385``.
_QUOTE = re.compile(
    r'^(\s+)quote:\s*"([^"#]+)#(L\d+(?:-L?\d+)?(?:,L\d+(?:-L?\d+)?)*)"\s*$'
)

_PART = re.compile(r"^L(\d+)(?:-L?(\d+))?$")

#: How long a cited range may be before it is read as prose rather than rows.
_MAX_RANGE = 12

#: How far a wrapped value may run past the line its row starts on.
_MAX_WRAP = 3

#: Wood Village keys four of its zones with a space in the name -- ``LR 7.5``,
#: ``MR 2`` -- and a pattern that stopped at the space did not merely skip
#: them: it went on attributing their fields to whichever zone was declared
#: above, so every value in those four was checked against another zone's
#: columns and quietly found nothing. ``norm`` strips the space back out, so
#: the key still matches a header cell reading ``LR7.5``.
#:
#: The pattern matches on indent alone, so a jurisdiction-level field under
#: ``defaults:`` -- ``parking_stall_width_ft`` -- is read as though it were a
#: zone. That is harmless and it is worth knowing why, because it is the kind
#: of thing that stops being harmless quietly. Nearly all of them are dropped
#: one line later: their figure sits at the depth this pattern expects a FIELD
#: name at, so no field is ever pending and no citation is yielded. Four
#: survive that, the ones carrying a ``variants:`` block, and those are dropped
#: instead at lookup, because no table header anywhere has a column headed
#: "parking stall width". A field name is safe here only for as long as it does
#: not collide with a district code.
_ZONE_KEY = re.compile(r"^  ([A-Za-z0-9/_.\-]+(?: [A-Za-z0-9/_.\-]+)*):\s*$")
_FIELD_KEY = re.compile(r"^    ([a-z0-9_]+):\s*$")
_EXEMPT = re.compile(r"^(\s+-?\s*)exempt:\s*true\s*$")
_WHEN = re.compile(r"^\s+when:\s*\[(.*)\]\s*$")
_ANY_KEY = re.compile(r"^(\s+-?\s*)([a-z0-9_]+):\s*(\S.*?)\s*$")

#: Forms that state a figure the table also prints, so the two can be compared.
#: ``per_dwelling`` is here because the corpus deliberately encodes the printed
#: per-unit number rather than the multiplied one, for exactly this reason.
_NUMERIC_FORMS = frozenset({"value", "per_dwelling", "sqft_per_unit"})

#: Keys that carry no figure. Everything not on either list is a value form
#: this check cannot compare -- ``same_as``, ``spaces_total``, a height ratio --
#: and seeing one has to CLEAR the pending figure rather than leave the last
#: one standing. Leaving it standing is how a base number gets reported against
#: a variant's quote, which is a finding invented out of a parser.
_NOT_A_VALUE = frozenset(
    {
        "quote", "cite", "url", "when", "retrieved", "notes", "title", "note",
        "section", "id", "outcome", "fact", "band", "start", "end", "unless",
        "extraction", "status", "definitions_at", "zone", "test", "wins",
        "reviewer", "reviewed", "allow_thin", "zoning_layer", "zone_field",
        "strip_lowercase_suffix", "geoid", "acres", "count", "measured_on",
        "max_intersection_angle_deg", "variants", "like", "eligible",
    }
)

#: A cell that states the standard does not apply. "0 ft." is not on this list:
#: zero is a standard that a lot can fail to meet, and an exemption is not.
_NOTHING = frozenset({"none", "none.", "na", "n/a", "not applicable", "no maximum"})

#: A cell that hands its number somewhere else. The value is not in it.
_ELSEWHERE = re.compile(r"\b(see|varies|table note|per section)\b", re.I)

#: A cell ending in a connective is a value that wraps onto the next line.
#: Portland prints a density as "1 unit per" / "1,450 sq. ft. of" / "site area"
#: down three lines, and the figure is not on the row the citation names.
_WRAPPED = re.compile(r"\b(per|of|and|or|to|from|than|for)\s*$", re.I)

#: The trailing alternative is for a decimal printed without its leading
#: zero. Wood Village's Table 210-3 states LR12's density floor as
#: ".9 (25%)", and read as a whole number that is a density nine times the
#: real one disagreeing with an encoding that is correct.
_FIGURES = re.compile(r"\d[\d,]*(?:\.\d+)?|\.\d+")

#: Fields where a cell reading "none" and an encoded ``0`` state the same
#: requirement, so the corpus writes the number and this check does not report
#: it. These are the standards the screen SUBTRACTS with: a setback of zero and
#: no setback both let the building stand on the line, and writing the number
#: keeps it in the arithmetic instead of in a list of things that do not apply.
#:
#: The fields not on this list are the ones the screen TESTS the lot against --
#: a minimum lot size, width or frontage. There a floor of zero is a claim the
#: table does not make, and the difference is what the Gresham townhouse row
#: turned on. A MAXIMUM is not on this list either, and for the opposite
#: reason: a maximum setback of "none" is no constraint at all, while a maximum
#: setback of zero would demand the building stand exactly on the line.
_ZERO_IS_THE_SAME_AS_NONE = frozenset(
    {
        "setback_front_ft",
        "setback_side_ft",
        "setback_rear_ft",
        "setback_street_side_ft",
        "setback_side_total_ft",
        "setback_garage_entrance_ft",
        "min_landscaped_pct",
    }
)

#: A cited line that is the table's own caption. Wood Village quotes
#: ``Table 220-3. Housing Types Allowed`` beside the row, the way other cities
#: quote the header, and counting it as a line the check failed to read put
#: every value in that city into the "reaches past the table" bucket. A
#: footnote never opens with the word Table, so this does not silence the
#: overrides the bucket exists for.
_CAPTION = re.compile(r"^\s*Table\s")

#: Words that belong to the figure in front of them instead of opening a cell
#: of their own, used only where cells are separated by a single space and the
#: split has to be made on grammar rather than on whitespace. A trailing digit
#: is a footnote marker -- Gresham prints a maximum height as "45 ft.5" -- and
#: comes off before the word is looked up.
_UNIT_WORDS = frozenset(
    {
        "sq", "sq.ft", "sf", "square", "ft", "feet", "foot", "in", "inch",
        "inches", "%", "percent", "unit", "units", "du", "dus", "per", "acre",
        "acres", "story", "stories",
    }
)

#: How far below a candidate single-space header a row that reads as one may
#: be. A header is only accepted on that evidence, so this is the width of the
#: window in which the evidence has to appear.
_CONFIRM = 20

_EXEMPT_TOKEN = "EXEMPT"

_VACANT = "vacant"


@dataclass(frozen=True)
class Mismatch:
    """One encoded value that disagrees with the cell in its own column."""

    layer: str
    zone: str
    field: str
    when: str
    encoded: str
    cell: str
    doc: str
    line: int

    def __str__(self) -> str:
        when = f" [{self.when}]" if self.when else ""
        return (
            f"{self.layer}/{self.zone} {self.field}{when}: encoded {self.encoded}, "
            f"its own column reads {self.cell!r} ({self.doc}#L{self.line})"
        )


@dataclass(frozen=True)
class Survey:
    """What the check reached, and what it found there."""

    #: The cell states a number, and a different number was encoded.
    mismatches: tuple[Mismatch, ...]
    #: The cell states no standard, and a number was encoded against it.
    vacancies: tuple[Mismatch, ...]
    #: Citations that landed on a table this check can read by column.
    reached: int
    #: Of those, the ones whose cell could be compared with the encoded value.
    judged: int


def cells(line: str) -> list[str]:
    return [c.strip() for c in _SPLIT.split(line.strip()) if c.strip()]


def _unit(tok: str) -> str | None:
    """The unit this token names, or ``None`` if it names something else."""
    word = tok.lower().rstrip("0123456789").rstrip(".,;:")
    return word if word in _UNIT_WORDS else None


def _opens_cell(tok: str) -> bool:
    if tok.lower().rstrip(".,;:") in _NOTHING:
        return True
    return tok[:1].isdigit() or (tok[:1] == "." and tok[1:2].isdigit())


def sparse_cells(line: str, want: int) -> list[str] | None:
    """The ``want`` values on a row whose columns are one space apart.

    Two spaces is the only separator these extractions offer that a word does
    not also contain, so where a table comes out single-spaced there is no
    split that recovers cells rather than words. This reads the row by grammar
    instead: a cell opens on a figure or on a word meaning no standard, and
    runs through the units behind it. Anything else, once a cell has opened,
    ends the reading -- ``5 ft. N/A 6 in. on`` is a row that wrapped, and half
    of somebody's cell is worse than none of it.

    The last guard is the one that matters. Every cell has to state the same
    KIND of quantity, because a row of a dimensional table does. Without it a
    row label carrying a measurement -- "Lots over 5,000 sq. ft." -- hands its
    own number to the first district and shifts the whole row one column left,
    which is the exact error this module exists to catch, produced by the
    module.
    """
    groups: list[list[str]] = []
    for tok in line.split():
        if _opens_cell(tok):
            groups.append([tok])
        elif groups:
            if _unit(tok) is None:
                return None
            groups[-1].append(tok)
        # Before the first cell opens, the tokens are the row's label.
    if len(groups) != want:
        return None
    shapes = {
        tuple(_unit(t) for t in g[1:])
        for g in groups
        if g[0].lower().rstrip(".,;:") not in _NOTHING
    }
    if len(shapes) > 1:
        return None
    return [" ".join(g) for g in groups]


def one_cell(line: str) -> str | None:
    """The whole of this line as a single cell, if that is what it is."""
    got = cells(line)
    return got[0] if len(got) == 1 else None


def is_value_line(line: str) -> bool:
    """Does this line hold a value rather than name the row it belongs to?

    In a table printed down the page there is no question where a cell ends --
    the line is the cell -- and the only question left is how many lines belong
    to one row. A cell opens on a figure or on a word meaning no standard, the
    same test the single-space reading uses; anything else is the next row's
    name. It is a narrow test on purpose. A cell reading "See Table
    19.30.030.A.4" or "Townhomes and cottage clusters none" is indistinguishable
    from a row label, and a row holding one comes out the wrong length and is
    declined whole rather than read short.
    """
    got = one_cell(line)
    if not got:
        return False
    if got.lower().rstrip(".,;:") in _NOTHING:
        return True
    return got[:1].isdigit() or (got[:1] == "." and got[1:2].isdigit())


def norm(code: str) -> str:
    """A district code as the two files spell it differently.

    Happy Valley's tables print ``R-40`` and its layer keys it ``R40``. The
    hyphen is typography, not identity, and without this the check walks past
    a whole jurisdiction reporting nothing wrong with it.
    """
    return code.strip().lower().replace("-", "").replace(" ", "")


def is_code(cell: str) -> bool:
    """Does this header cell name a district rather than label the rows?

    Happy Valley heads its column of row names "Standard"; Gresham heads its
    with nothing at all. District codes carry a digit (R-40, LDR-5) or are
    written in capitals (TR, TLDR, MUR-S); a word in sentence case is a
    heading, and the difference decides where the first district's column
    starts.
    """
    return any(ch.isdigit() for ch in cell) or cell.upper() == cell


class _Doc:
    """One extracted document, with its header rows located once.

    Cells are read in order, not by character offset. These extractions align
    body rows with each other but not with the header above them -- Gresham
    prints its district codes thirty characters right of the values beneath
    them -- so counting cells is the only reading that holds.
    """

    def __init__(self, lines: Sequence[str]) -> None:
        self.lines = list(lines)
        self.headers: dict[int, list[str]] = {}
        #: Line number -> whether that header's first cell labels the rows.
        self.labelled: dict[int, bool] = {}
        #: Line number -> whether its rows are one space apart, not two.
        self.sparse: dict[int, bool] = {}
        for i, line in enumerate(self.lines):
            got = cells(line)
            if len(got) < 3:
                self._maybe_sparse(i, line)
                continue
            # The first cell may head the column of row names -- "Standard",
            # "Residential Uses" -- and is allowed to be a phrase. Every cell
            # after it has to be a district code, and they have to be distinct:
            # a row of four cells all reading "REAR" is a spanning sub-heading,
            # and taking it for a column order puts every row beneath it
            # against the wrong district.
            codes = got[1:]
            if not all(_ZONE.match(c) and is_code(c) for c in codes):
                continue
            # Every column reading the same thing is a spanning sub-heading
            # -- a row of four cells all saying "REAR", or Wood Village Table
            # 220-3 heading four housing-type columns "MR4 and MR2" -- and
            # taking it for a column order puts every row beneath it against
            # the wrong district. A header that repeats only SOME of its
            # labels is a different thing and still readable: Troutdale heads
            # six columns LDR-1, LDR-2, MDR, (TC), HDR, (TC), and the
            # ambiguity is confined to the label that repeats. Which district
            # may be read from it is settled in ``cell``.
            if len({norm(c) for c in codes}) == 1:
                continue
            first_is_code = bool(_ZONE.match(got[0])) and is_code(got[0])
            if first_is_code and norm(got[0]) in {norm(c) for c in codes}:
                continue
            if not first_is_code and len(got[0]) > 40:
                continue
            self.headers[i] = got
            self.labelled[i] = not first_is_code
            self.sparse[i] = False
        self._order = sorted(self.headers)
        self.vtables = _vertical(self.lines)

    def _maybe_sparse(self, i: int, line: str) -> None:
        """A header whose district codes are one space apart, if a row says so.

        Nothing about the shape of ``USES LDR-PV MDR-PV HDR-PV`` distinguishes
        it from ``Schools P/SUR15 SUR L/SUR15``, which is a row of a use table
        four hundred lines further on, or from a chapter title in capitals. So
        the shape is not what decides it: a candidate becomes a header only
        when some line below it reads as a row of exactly that many values.
        A header with nothing under it to read is not a header this check has
        any use for, and the two that would have been wrong have nothing under
        them at all.
        """
        toks = line.split()
        if len(toks) < 3:
            return
        first_is_code = bool(_ZONE.match(toks[0])) and is_code(toks[0])
        codes = toks if first_is_code else toks[1:]
        if len(codes) < 2:
            return
        if not all(_ZONE.match(c) and is_code(c) for c in codes):
            return
        if len({norm(c) for c in codes}) != len(codes):
            return
        # A district code is written with a digit or a hyphen far more often
        # than a word in capitals is, and this is the cheap half of the guard.
        if sum(1 for c in codes if any(ch.isdigit() for ch in c) or "-" in c) < 2:
            return
        window = self.lines[i + 1 : i + 1 + _CONFIRM]
        if not any(sparse_cells(row, len(codes)) for row in window):
            return
        self.headers[i] = codes
        self.labelled[i] = True
        self.sparse[i] = True

    def is_header(self, line_no: int) -> bool:
        """Is this line itself a column heading, or a row's name?

        Citations name one deliberately: a header row is how the corpus pins
        which of three districts a number on the next line belongs to. Reading
        it as a row of values compares an exemption against the word "R-40".

        In a table printed down the page the row's NAME does that job for the
        other axis, and citations there name it for the same reason -- Happy
        Valley's side setback quotes "Interior side" and then the one line
        under it that is its own. So a label line inside such a table is the
        corpus being careful too, not a line this check failed to read.

        A row label is a line with a full row under it, not merely a line that
        holds no figure. The footnotes print inside the same span -- Happy
        Valley's note 5, the one that reduces a party-wall setback to zero,
        sits four hundred lines below the row it governs and holds no figure
        either. Forgiving that line as a label would take the override out of
        the citation and leave a variant to be judged against the cell it was
        written to replace, which is a finding manufactured out of a reader.
        """
        if (line_no - 1) in self.headers:
            return True
        got = self.vtable_at(line_no)
        if not got:
            return False
        start, end, codes = got
        i = line_no - 1
        if is_value_line(self.lines[i]):
            return False
        run = 0
        while i + 1 + run < end and is_value_line(self.lines[i + 1 + run]):
            run += 1
        return run == len(codes)

    def vtable_at(self, line_no: int) -> tuple[int, int, list[str]] | None:
        """The down-the-page table this line sits in, if any."""
        i = line_no - 1
        for start, end, codes in self.vtables:
            if start <= i < end:
                return (start, end, codes)
        return None

    def _vcell(self, line_no: int, zone: str) -> str | None:
        """This district's line of the row the cited line belongs to."""
        got = self.vtable_at(line_no)
        if got is None:
            return None
        start, end, codes = got
        spelled = [norm(c) for c in codes]
        if spelled.count(norm(zone)) != 1:
            return None
        i = line_no - 1
        if not is_value_line(self.lines[i]):
            return None
        first = i
        while first - 1 >= start and is_value_line(self.lines[first - 1]):
            first -= 1
        last = i
        while last + 1 < end and is_value_line(self.lines[last + 1]):
            last += 1
        # A row that came out the wrong length is a row where a cell wrapped or
        # a cell was prose, and which line belongs to whom is then a guess.
        # Fairview's minimum lot width runs to nine lines under five districts,
        # because three of the five add "20 feet for townhouses".
        if last - first + 1 != len(codes):
            return None
        return one_cell(self.lines[first + spelled.index(norm(zone))])

    def header_for(self, line_no: int) -> tuple[list[str], bool, bool] | None:
        """The column order in force at a line, whether it labels its rows, and
        whether its rows are one space apart.

        The nearest header above the line.
        """
        best = None
        for i in self._order:
            if i >= line_no:
                break
            best = (self.headers[i], self.labelled[i], self.sparse[i])
        return best

    def cell(self, line_no: int, zone: str) -> str | None:
        """This district's cell on this row, or ``None`` if it cannot be read."""
        if self.vtable_at(line_no):
            # Exclusive: the nearest header ABOVE a line printed down the page
            # belongs to some other table entirely, and reading against it is
            # how Happy Valley's attached districts were being looked up in the
            # single-family table's columns.
            return self._vcell(line_no, zone)
        got = self.header_for(line_no)
        if got is None:
            return None
        header, labelled, sparse = got
        spelled = [norm(c) for c in header]
        # Exactly one, not the first of several. A district heading two columns
        # of the same table is a question this check cannot answer -- which of
        # the two the value came from is the whole point -- so it declines.
        matching = [i for i, c in enumerate(spelled) if c == norm(zone)]
        if len(matching) != 1:
            return None
        column = matching[0]
        if sparse:
            # No label cell to skip: the row's label is however many words come
            # before the first figure, and what comes back is the values alone.
            found = sparse_cells(self.lines[line_no - 1], len(header))
            return found[column] if found else None
        row = cells(self.lines[line_no - 1])
        # Two shapes, and which one applies is settled by the header rather
        # than by the row's length. A header that labels its own rows
        # ("Standard") lines up one for one with the row beneath it; a header
        # of districts only sits over rows that carry a label in front.
        # Deciding from the row's length instead would read a row that had
        # dropped one blank cell as a row of the other shape, and then report
        # every value one column to the side, confidently.
        want = len(header) if labelled else len(header) + 1
        if len(row) != want:
            return None
        return row[column] if labelled else row[1 + column]


def _vertical(lines: Sequence[str]) -> list[tuple[int, int, list[str]]]:
    """Every table printed down the page, as ``(start, end, districts)``.

    The header is the run of district codes on their own lines beneath the
    caption, after an optional line naming the column of row names -- Happy
    Valley writes "Standard", unincorporated Clackamas writes it too. Rows
    start where that run ends and the table ends at the next caption.

    The count of districts is then checked against the table rather than
    trusted. Fairview heads six columns and only the first three are written as
    codes: "Townhouse Overlay", "Residential Medium (RM)" and "Additional
    Standards and Exceptions" are districts and a notes column that no pattern
    tells apart, and reading its rows three at a time would take R-10's number
    for R-7.5's. So the run has to agree with the rows beneath it: the most
    common row length in the table IS the number of districts, or the header
    was read wrong and the table is left alone.
    """
    out: list[tuple[int, int, list[str]]] = []
    for i, line in enumerate(lines):
        if not _CAPTION.match(line):
            continue
        j = i + 1
        while j < len(lines) and (not lines[j].strip() or _CAPTION.match(lines[j])):
            j += 1
        got = one_cell(lines[j]) if j < len(lines) else None
        if got and not (_ZONE.match(got) and is_code(got)):
            j += 1
        codes: list[str] = []
        while j < len(lines):
            got = one_cell(lines[j])
            if not got or not (_ZONE.match(got) and is_code(got)):
                break
            codes.append(got)
            j += 1
        if len(codes) < 2 or len({norm(c) for c in codes}) != len(codes):
            continue
        end = next(
            (k for k in range(j, len(lines)) if _CAPTION.match(lines[k])), len(lines)
        )
        sizes: dict[int, int] = {}
        run = 0
        for k in range(j, end):
            if is_value_line(lines[k]):
                run += 1
                continue
            if run:
                sizes[run] = sizes.get(run, 0) + 1
            run = 0
        if run:
            sizes[run] = sizes.get(run, 0) + 1
        # Two conditions, and the second is the one that saves it. At least two
        # rows have to come out the length of the header, or the run of codes
        # was not the header. And no row may come out LONGER: a run past the
        # district count means the boundary between rows has been lost, and
        # once it is lost anywhere in the table a run of exactly the right
        # length is no longer evidence of anything. Fairview numbers its row
        # labels -- "1. Minimum Lot Size (sq. ft.)" -- so its labels read as
        # values and its rows run together eighteen lines at a stretch under a
        # header of three, which is what the whole-table refusal is for.
        if sizes.get(len(codes), 0) < 2:
            continue
        if any(n > len(codes) for n in sizes):
            continue
        # Happy Valley's extractor repeats the caption on four consecutive
        # lines, and each one finds the same table.
        if (j, end, codes) not in out:
            out.append((j, end, codes))
    return out


def _doc(cache: dict[str, _Doc | None], rel: str, root: Path) -> _Doc | None:
    if rel not in cache:
        path = root / rel
        if path.exists():
            text = path.read_text(encoding="utf-8", errors="replace")
            cache[rel] = _Doc(text.splitlines())
        else:
            cache[rel] = None
    return cache[rel]


def _figure(text: str) -> float | None:
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def _judge(encoded: str, cell: str, field: str = "") -> bool | str | None:
    """``True``, ``False``, ``"vacant"``, or ``None`` where not comparable."""
    text = cell.strip().lower()
    if not text:
        return None
    nothing = text in _NOTHING
    if encoded == _EXEMPT_TOKEN:
        # An exemption carries no number, so there is no number for this check
        # to have taken from the wrong column. Where the cell prints a figure
        # and the value is exempt, the question is whether the cited text
        # supports the exemption -- and that is :mod:`flats.encode.exemptions`,
        # which reads the words rather than counting the cells. It has to be:
        # Happy Valley's density row prints "4.4 du/net acre" and the value is
        # exempt because the row is headed "Townhome maximum density" and a
        # quadplex is not a townhome. No count of columns can see that.
        return True if nothing else None
    if nothing:
        # A number encoded where the cell states no standard. Judged rather
        # than skipped -- "None" is not a number, so a check that only compares
        # numbers would step straight past the misread it was written for --
        # but only for the fields the screen tests a lot against. See
        # ``_ZERO_IS_THE_SAME_AS_NONE``.
        return None if field in _ZERO_IS_THE_SAME_AS_NONE else _VACANT
    if _ELSEWHERE.search(cell) or _WRAPPED.search(cell):
        return None
    if text[0].islower():
        # A cell opening in lower case is the tail of the line above it:
        # Gresham breaks "6.22 units per" and "acre4" across two lines, and
        # the fragment carries the footnote marker as though it were a
        # number. Rows start with a figure or a capital; fragments do not.
        return None
    try:
        want = float(encoded)
    except ValueError:
        return None
    # Any number in the cell, not only the one it opens with. Portland writes
    # a density as "1 unit per 2,500 sq. ft." and encodes the 2,500; reading
    # only the leading figure would report every density in the city wrong.
    figures = [f for f in (_figure(m) for m in _FIGURES.findall(cell)) if f is not None]
    if not figures:
        return None
    return any(f == want for f in figures)


def cited(spec: str) -> list[int]:
    """The lines a citation names, as line numbers a row can be read from.

    A citation is routinely more than one line, and the extra lines are how the
    corpus pins a column: Happy Valley quotes ``L278,L281`` because the header
    row is what says which of three districts the number on L281 belongs to.
    """
    out: list[int] = []
    for part in spec.split(","):
        got = _PART.match(part.strip())
        if not got:
            continue
        start = int(got.group(1))
        end = int(got.group(2)) if got.group(2) else start
        # A range is normally a row and its wrapped continuation, or the two
        # rows of a standard the corpus had to choose between. Long ones are a
        # passage of prose, not a table, and expanding those would compare a
        # value against every line of an argument.
        if end < start or end - start > _MAX_RANGE:
            out.append(start)
            continue
        out.extend(range(start, end + 1))
    return out


def _citations(path: Path) -> Iterator[tuple[str, str, str, str, str, list[int]]]:
    """``(zone, field, when, encoded, doc, lines)`` for every quoted value."""
    zone = field = None
    encoded = when = None
    # Where the pending value was declared. A quote is the citation for that
    # value only if it sits at the same indent -- ``measured_on`` opens a block
    # one level deeper holding its own cite, and that one names the DENOMINATOR
    # rather than the standard. Happy Valley's density quotes 16.63 there for
    # what a net acre is, and reading it as the density's own citation compares
    # a number against a land-division definition. 103 citations in the corpus
    # sit inside such a block.
    depth = -1
    for line in path.read_text(encoding="utf-8").splitlines():
        got = _ZONE_KEY.match(line)
        if got:
            zone, field, encoded, when, depth = got.group(1), None, None, None, -1
            continue
        got = _FIELD_KEY.match(line)
        if got:
            field, encoded, when, depth = got.group(1), None, None, -1
            continue
        got = _EXEMPT.match(line)
        if got:
            encoded, when, depth = _EXEMPT_TOKEN, None, len(got.group(1))
            continue
        got = _WHEN.match(line)
        if got:
            when = got.group(1)
            continue
        got = _QUOTE.match(line)
        if got and zone and field and encoded is not None:
            if len(got.group(1)) == depth:
                yield zone, field, when or "", encoded, got.group(2), cited(
                    got.group(3)
                )
            continue
        got = _ANY_KEY.match(line)
        if got:
            key = got.group(2)
            if key in _NUMERIC_FORMS:
                encoded, when, depth = got.group(3), None, len(got.group(1))
            elif key not in _NOT_A_VALUE:
                encoded, when, depth = None, None, -1


def survey(
    layers: Sequence[str] = (),
    *,
    configroot: Path = CONFIGROOT,
    docroot: Path = DOCROOT,
) -> Survey:
    """Read every citation into a readable table against its own column."""
    cache: dict[str, _Doc | None] = {}
    wrong: list[Mismatch] = []
    vacant: list[Mismatch] = []
    reached = judged = 0

    for path in sorted(configroot.rglob("*.yaml")):
        layer = path.relative_to(configroot).with_suffix("").as_posix()
        if layers and not any(layer.startswith(want.strip("/")) for want in layers):
            continue
        for zone, field, when, encoded, rel, line_nos in _citations(path):
            doc = _doc(cache, rel, docroot)
            if doc is None:
                continue
            candidates: list[tuple[str, int]] = []
            # A citation that names its own header row is the corpus being
            # careful, not reaching for something else: it is how Happy Valley
            # and Troutdale pin which of six columns a number came from. So a
            # header line is not a line this check failed to read, and it does
            # not count against the citation below.
            rows = [
                n
                for n in line_nos
                if not doc.is_header(n)
                and not (n <= len(doc.lines) and _CAPTION.match(doc.lines[n - 1]))
            ]
            for line_no in rows:
                if line_no > len(doc.lines):
                    continue
                cell = doc.cell(line_no, zone)
                if cell:
                    candidates.append((cell, line_no))
            if not candidates:
                continue
            reached += 1
            if len(candidates) != len(rows):
                # The citation reaches past the table, and what it reaches is
                # routinely the thing that replaces the cell. Happy Valley's
                # lot width is "100 feet" in the cell and exempt by note 2 four
                # hundred lines down; Gresham CC's maximum front setback is
                # "10 feet" in the cell and five by note 3c on every street
                # class this screen cannot read. Both encodings are right and
                # neither matches its own cell, so a citation that quotes the
                # override is left alone. What stays judged is the citation
                # that names the row and nothing else -- which is the shape
                # the townhouse frontage misread had.
                continue
            verdicts = [
                (_judge(encoded, cell, field), cell, line_no)
                for cell, line_no in candidates
            ]
            comparable = [v for v in verdicts if v[0] is not None]
            if not comparable:
                continue
            judged += 1
            # A citation naming several lines has to agree with ONE of them,
            # not all. The others are context by design -- a header row quoted
            # to pin the column, the second of two rows the corpus chose
            # between, a footnote quoted beside the cell it governs.
            if any(v[0] is True for v in comparable):
                continue
            verdict, cell, line_no = comparable[0]
            row = Mismatch(layer, zone, field, when, encoded, cell, rel, line_no)
            (vacant if verdict == _VACANT else wrong).append(row)

    return Survey(tuple(wrong), tuple(vacant), reached, judged)


def reach(**kwargs) -> int:
    """How many citations the check could actually read. Pinned by a test."""
    return survey(**kwargs).reached


def render(got: Survey) -> Iterator[str]:
    yield f"{got.reached} citation(s) landed on a table readable by column"
    yield f"{got.judged} of them could be compared with what was encoded"
    yield f"{len(got.mismatches)} state a different number than was encoded"
    yield f"{len(got.vacancies)} state no standard where a number was encoded"
    if got.mismatches:
        yield ""
        yield "  --- a different number ---"
    for row in got.mismatches:
        yield f"  {row}"
    if got.vacancies:
        yield ""
        yield "  --- the cell states no standard ---"
    for row in got.vacancies:
        yield f"  {row}"
    if not got.mismatches and not got.vacancies:
        yield ""
        yield (
            "  Clean means one narrow thing: no encoded number sits in another"
            " district's column of a table this check can read."
        )


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):  # pragma: no cover
        sys.stdout.reconfigure(errors="replace")
    args = list(sys.argv[1:] if argv is None else argv)
    got = survey([a for a in args if not a.startswith("--")])
    for line in render(got):
        print(line)
    return 1 if got.mismatches else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
