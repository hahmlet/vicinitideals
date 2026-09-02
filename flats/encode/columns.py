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

The check is arithmetic on whitespace. Where a document prints one aligned cell
per column, the row can be split into cells, the nearest preceding header line
gives the column order, and the zone's own cell can be read by position and
compared with what was encoded.

Two things it deliberately will not do:

*It only reads rows that print a cell for every column.* Extractors that drop
empty cells produce a short row, and a short row cannot be indexed -- the
missing cells are exactly the ones that would shift every column after them.
Those rows are skipped rather than guessed at, which is why the count of what
this reads is small and is reported next to the count of what it found.

*It only judges cells it can turn into the same kind of thing as the encoded
value.* A number against a number, and "None" or "NA" against an exemption.
A cell reading "Varies depending on access" is a footnote pointer and belongs
to :mod:`flats.encode.footnotes`; a cell of prose is a refusal or a condition
and belongs to the ledgers that count those. Judging them here would produce
confident nonsense in the one place that is meant to be arithmetic.

So a clean result from this module means one narrow thing -- no encoded number
sits in the wrong column of a row we can count columns on -- and the module
reports how narrow. The blindness worth guarding against is the reader that
stops seeing rows at all and reports the corpus clean; ``reach()`` is the
number a test pins so that failure is loud.

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
_ZONE = re.compile(r"^[A-Z][A-Za-z0-9/. \-]{0,14}$")

#: Cells are separated by runs of two or more spaces in the extracted text.
_SPLIT = re.compile(r"\s{2,}")

#: ``quote: "or/multnomah/gresham/4.0100.residential.txt#L313"`` -- one line
#: only. A range spans rows and cannot be indexed by column.
_QUOTE = re.compile(r'^\s+quote:\s*"([^"#]+)#L(\d+)"\s*$')

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

_NUMBER = re.compile(r"^([\d.,]+)\s*(?:ft\.?|sq|units?|%|$)")

_EXEMPT_TOKEN = "EXEMPT"


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

    mismatches: tuple[Mismatch, ...]
    #: Citations that landed on a full-width row carrying this zone's column.
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
    with nothing at all. The difference decides whether a row of N cells is N
    districts with a label in front or a label plus N-1 districts, and getting
    it wrong reads every value one column to the side. District codes carry a
    digit (R-40, LDR-5) or are written in capitals (TR, TLDR, MUR-S); a word in
    sentence case is a heading.
    """
    return any(ch.isdigit() for ch in cell) or cell.upper() == cell


class _Doc:
    """One extracted document, with its header rows located once."""

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
            if len({norm(c) for c in codes}) != len(codes):
                continue
            first_is_code = bool(_ZONE.match(got[0])) and is_code(got[0])
            if first_is_code and norm(got[0]) in {norm(c) for c in codes}:
                continue
            if not first_is_code and len(got[0]) > 40:
                continue
            self.headers[i] = got
            self.labelled[i] = not first_is_code
        self._order = sorted(self.headers)

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


def _doc(cache: dict[str, _Doc | None], rel: str, root: Path) -> _Doc | None:
    if rel not in cache:
        path = root / rel
        if path.exists():
            text = path.read_text(encoding="utf-8", errors="replace")
            cache[rel] = _Doc(text.splitlines())
        else:
            cache[rel] = None
    return cache[rel]


def _judge(encoded: str, cell: str) -> bool | None:
    """``True``/``False`` where the two are comparable, ``None`` where not."""
    text = cell.strip().lower()
    if not text:
        return None
    nothing = text in _NOTHING
    if encoded == _EXEMPT_TOKEN:
        return nothing
    if nothing:
        # A number encoded where the cell states no standard. This is the
        # Gresham case exactly, and it has to be judged rather than skipped:
        # "None" is not a number, so a check that only compares numbers would
        # step straight past the misread it was written for.
        return False
    got = _NUMBER.match(cell)
    if got is None:
        return None
    try:
        return float(got.group(1).replace(",", "")) == float(encoded)
    except ValueError:
        return None


def _citations(path: Path) -> Iterator[tuple[str, str, str, str, str, int]]:
    """``(zone, field, when, encoded, doc, line)`` for every single-line quote."""
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
            yield zone, field, when or "", encoded, got.group(1), int(got.group(2))
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
    """Read every aligned citation in the corpus against its own column."""
    cache: dict[str, _Doc | None] = {}
    found: list[Mismatch] = []
    reached = judged = 0

    for path in sorted(configroot.rglob("*.yaml")):
        layer = path.relative_to(configroot).with_suffix("").as_posix()
        if layers and not any(layer.startswith(want.strip("/")) for want in layers):
            continue
        for zone, field, when, encoded, rel, line_no in _citations(path):
            doc = _doc(cache, rel, docroot)
            if doc is None or line_no > len(doc.lines):
                continue
            heading = doc.header_for(line_no)
            if heading is None:
                continue
            header, labelled = heading
            spelled = [norm(c) for c in header]
            if norm(zone) not in spelled:
                continue
            column = spelled.index(norm(zone))
            row = cells(doc.lines[line_no - 1])
            # Two shapes, and which one applies is settled by the header
            # rather than by the row's length. A header that labels its own
            # rows ("Standard") lines up one for one with the row beneath it; a
            # header of districts only sits over rows that carry a label in
            # front. Deciding from the row's length instead would read a row
            # that had dropped one blank cell as a row of the other shape, and
            # then confidently report every value one column to the side.
            want = len(header) if labelled else len(header) + 1
            if len(row) != want:
                continue
            cell = row[column] if labelled else row[1 + column]
            reached += 1
            verdict = _judge(encoded, cell)
            if verdict is None:
                continue
            judged += 1
            if not verdict:
                found.append(
                    Mismatch(layer, zone, field, when, encoded, cell, rel, line_no)
                )

    return Survey(tuple(found), reached, judged)


def reach(**kwargs) -> int:
    """How many citations the check could actually read. Pinned by a test."""
    return survey(**kwargs).reached


def render(got: Survey) -> Iterator[str]:
    yield (
        f"{got.reached} citation(s) landed on a row printing one cell per column"
        f" and carrying this zone's own column"
    )
    yield f"{got.judged} of them could be compared with what was encoded"
    yield f"{len(got.mismatches)} disagree"
    if got.mismatches:
        yield ""
    for row in got.mismatches:
        yield f"  {row}"
    if not got.mismatches:
        yield ""
        yield (
            "  Clean means one narrow thing: no encoded number sits in another"
            " district's column of a row this check can count columns on."
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
