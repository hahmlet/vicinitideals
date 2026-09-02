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
citation that names its own header is being careful rather than reaching past
the table, so the header line does not count against it; before that was true
Troutdale and Happy Valley were almost entirely unjudged, because quoting the
header is exactly how those two say which of six columns a number came from.

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

What it cannot see, so a clean report is read for what it is. Of 2,249 cited
values it reads 555. Roughly half the remainder name lines in a document with
no table this check recognises. The rest name lines in a document that has one
but outside it; or in a table whose header does not carry that district; or in
a row whose label wraps across several lines, so that no single line carries a
full set of cells -- Gresham's downtown Table 4.1130 spends five lines on
"Minimum Residential Net Density for all residential projects (not mixed-use)
(units per acre)7 (See definition of Net Density in Article 3)", and a row that
is mostly its own title cannot be counted across. The
documents with no recognised table fall into five shapes, and the last two are
the only real gaps:

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
    Clackamas Table 315-1 and every table in Lake Oswego's dimensional chapter
    print their district codes down the page rather than across it, with each
    cell beneath them on its own line. All three are genuine multi-district
    dimensional tables and this is the largest gap by far -- though Lake
    Oswego is a jurisdiction currently switched off, so only two of the three
    are load-bearing today.

    This one stays blind on purpose. The vertical form loses the thing the
    horizontal form keeps, which is where a cell ends. Fairview's minimum lot
    width prints nine lines under five districts, because three of the five
    carry a second line reading "20 feet for townhouses" and nothing marks that
    as a continuation rather than a sixth column. Counting down the block would
    produce a confident finding out of a coin flip -- the same thing this
    module already refuses to do when a horizontal row has dropped a blank.

*   **A table the OCR has shattered.** Oregon City's zoning chapter is a scan,
    and its dimensional tables come out as ``Quad pl ex a nd co t tage 1 0 ,
    000 squ are 8 , 000 squ are 7 , 000 s qu are`` -- 68 citations. The columns
    are separated by single spaces, and so are the halves of the broken words,
    so there is no split that recovers cells rather than word fragments.

So the gaps were read by hand on 2026-09-02 instead, every dimensional value
against its own column:

*   Fairview's twelve rows across R-6 and R-7.5. The vertical form is checkable
    by eye because the corpus resolved the wraps when it encoded: R-7.5's lot
    width cites L345 and not L344, which is R-6's second line.
*   Oregon City's full set across R-10, R-8, R-6, R-5 and R-3.5, including the
    quadplex lot-size row that is the one this screen builds on.
*   Lake Oswego's low-density table across R-7.5, R-10 and R-15, and the
    per-zone tables for R-6, R-5, R-3, R-2 and R-0 -- which are one district
    each, so what was checked there is the row rather than the column, the
    quadplex line of R-2's Table 50.04.001-13 rather than the duplex above it.
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
    r'^\s+quote:\s*"([^"#]+)#(L\d+(?:-L?\d+)?(?:,L\d+(?:-L?\d+)?)*)"\s*$'
)

_PART = re.compile(r"^L(\d+)(?:-L?(\d+))?$")

#: How long a cited range may be before it is read as prose rather than rows.
_MAX_RANGE = 12

#: How far a wrapped value may run past the line its row starts on.
_MAX_WRAP = 3

_ZONE_KEY = re.compile(r"^  ([A-Za-z0-9/_.\-]+):\s*$")
_FIELD_KEY = re.compile(r"^    ([a-z0-9_]+):\s*$")
_EXEMPT = re.compile(r"^\s+-?\s*exempt:\s*true\s*$")
_WHEN = re.compile(r"^\s+when:\s*\[(.*)\]\s*$")
_ANY_KEY = re.compile(r"^\s+-?\s*([a-z0-9_]+):\s*(\S.*?)\s*$")

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

_FIGURES = re.compile(r"\d[\d,]*(?:\.\d+)?")

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
        for i, line in enumerate(self.lines):
            got = cells(line)
            if len(got) < 3:
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
        self._order = sorted(self.headers)

    def is_header(self, line_no: int) -> bool:
        """Is this line itself a column heading?

        Citations name one deliberately: a header row is how the corpus pins
        which of three districts a number on the next line belongs to. Reading
        it as a row of values compares an exemption against the word "R-40".
        """
        return (line_no - 1) in self.headers

    def header_for(self, line_no: int) -> tuple[list[str], bool] | None:
        """The column order in force at a line, and whether it labels its rows.

        The nearest header above the line.
        """
        best = None
        for i in self._order:
            if i >= line_no:
                break
            best = (self.headers[i], self.labelled[i])
        return best

    def cell(self, line_no: int, zone: str) -> str | None:
        """This district's cell on this row, or ``None`` if it cannot be read."""
        got = self.header_for(line_no)
        if got is None:
            return None
        header, labelled = got
        spelled = [norm(c) for c in header]
        # Exactly one, not the first of several. A district heading two columns
        # of the same table is a question this check cannot answer -- which of
        # the two the value came from is the whole point -- so it declines.
        matching = [i for i, c in enumerate(spelled) if c == norm(zone)]
        if len(matching) != 1:
            return None
        column = matching[0]
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
    for line in path.read_text(encoding="utf-8").splitlines():
        got = _ZONE_KEY.match(line)
        if got:
            zone, field, encoded, when = got.group(1), None, None, None
            continue
        got = _FIELD_KEY.match(line)
        if got:
            field, encoded, when = got.group(1), None, None
            continue
        if _EXEMPT.match(line):
            encoded, when = _EXEMPT_TOKEN, None
            continue
        got = _WHEN.match(line)
        if got:
            when = got.group(1)
            continue
        got = _QUOTE.match(line)
        if got and zone and field and encoded is not None:
            yield zone, field, when or "", encoded, got.group(1), cited(got.group(2))
            continue
        got = _ANY_KEY.match(line)
        if got:
            key = got.group(1)
            if key in _NUMERIC_FORMS:
                encoded, when = got.group(2), None
            elif key not in _NOT_A_VALUE:
                encoded, when = None, None


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
            rows = [n for n in line_nos if not doc.is_header(n)]
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
