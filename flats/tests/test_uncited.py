"""Counting the reading nobody did, without counting the poultry.

The cross-reference ledger asks which chapters our documents point at and we
cannot open. This asks the nearer question: in the chapters we did open, which
measured statements has no encoded value ever quoted?

Milwaukie is why it exists. Table 19.301.4 prints a 5 ft side yard, which was
encoded on 13 August, and four rows below prints the height plane that makes
the real side yard 11 ft, which was not. Both lines were in the same held
document. The coverage ledger counts fields and there is no field for the slope
of a plane; the citation checker verifies lines that are cited; the
cross-reference ledger looks for absent chapters. A rule four rows below one we
read was invisible to all three.

The tests here are mostly about the subtraction being worth reading. A census
that reports every number in a code chapter is a census nobody opens, so what
it declines to report matters as much as what it finds: definitions have their
own subsystem, a standard reprinted once per column is one standard, and a long
sentence with a number in it and no field behind it is almost always about
livestock.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from flats.encode.uncited import (
    MEASURE,
    PROSE_CHARS,
    READ_WINDOW,
    Uncited,
    _sections,
    by_field,
    render,
    uncited,
    write,
)
from flats.rules.loader import load_rules
from flats.rules.model import Layer

pytestmark = pytest.mark.unit

MILWAUKIE = "or/clackamas/milwaukie"
BASE_ZONES = f"{MILWAUKIE}/19.300.base-zones.txt"
DEFINITIONS = f"{MILWAUKIE}/19.200.definitions.txt"


@pytest.fixture(scope="module")
def layers() -> dict[str, Layer]:
    return load_rules()


@pytest.fixture(scope="module")
def milwaukie(layers: dict[str, Layer]) -> list[Uncited]:
    return uncited(layers[MILWAUKIE])


def _at(rows: list[Uncited], path: str, line: int) -> Uncited | None:
    return next((r for r in rows if r.path == path and r.line == line), None)


# -- the finding ------------------------------------------------------------


def test_the_plane_is_no_longer_uncited(milwaukie: list[Uncited]) -> None:
    """The regression on the fix, not on the tool.

    Lines 231 and 236 are the two cells of R-MD's side yard height plane. They
    are quoted now, and if a re-encoding ever drops that citation the side
    yards of a whole zone silently lose six feet.
    """
    assert _at(milwaukie, BASE_ZONES, 231) is None
    assert _at(milwaukie, BASE_ZONES, 236) is None


def test_a_bonus_beside_a_number_we_did_read(milwaukie: list[Uncited]) -> None:
    """"The maximum lot coverage percentage in Subsection 19.301.4.C.4 is
    increased by 10 percentage points" -- a field this system screens against,
    a sentence no value quotes, printed under the table the coverage figure
    came from. This is the shape the `unread` bucket is for."""
    row = _at(milwaukie, BASE_ZONES, 305)

    assert row is not None
    assert row.bucket == "unread"
    assert row.field == "max_coverage_pct"
    assert "increased by 10 percentage points" in row.text


def test_the_two_buckets_are_different_work(milwaukie: list[Uncited]) -> None:
    """A statement naming a field can be encoded today. One naming no field is
    a modelling decision first -- the height plane needed a new value form
    before it could be written down -- so they are counted apart."""
    assert {r.bucket for r in milwaukie} == {"unread", "unfielded"}
    assert all(bool(r.field) == (r.bucket == "unread") for r in milwaukie)


def test_every_jurisdiction_is_asked(layers: dict[str, Layer]) -> None:
    from flats.encode.uncited import survey

    rows = survey(list(layers.values()))
    assert {r.layer for r in rows} <= set(layers)
    assert len({r.layer for r in rows}) > 10


def test_the_debt_is_reported_by_field(milwaukie: list[Uncited]) -> None:
    """Which standards this corpus talks about constantly and quotes rarely.
    Not a list of errors -- a list of where an exception would be hiding."""
    counts = by_field(milwaukie)

    assert "max_coverage_pct" in counts
    assert all(counts[a] >= counts[b] for a, b in zip(counts, list(counts)[1:]))
    assert 0 not in counts.values()


# -- what it declines to report ---------------------------------------------


def test_a_glossary_body_is_somebody_else_s_job(milwaukie: list[Uncited]) -> None:
    """"Existing trees are measured at a height 4.5 ft above the mean ground
    level" is a definition of how to measure a tree, and it reads as an unread
    height standard. Definitions have their own reader and their own citation
    form; counting them here would bury the standards under the glossary."""
    assert not [
        r
        for r in milwaukie
        if r.path == DEFINITIONS and r.text.lower().startswith("means")
    ]


def test_a_standard_reprinted_per_column_is_one_standard(
    milwaukie: list[Uncited]
) -> None:
    """Table 19.301.4 runs four lot-size columns and prints "35 ft" on four
    consecutive lines. The encoding quotes the first. Reporting the other
    three as unread is how a ledger becomes furniture."""
    assert not [
        r for r in milwaukie if r.path == BASE_ZONES and 224 <= r.line <= 227
    ]


def test_prose_with_no_field_behind_it_stays_out() -> None:
    """"Livestock, other than usual household pets, are not housed or kept
    within 100 ft of any dwelling" states a measure and names no field, and it
    will be true of this corpus forever. A field vouches for a long sentence;
    nothing vouches for that one."""
    livestock = (
        "Livestock, other than usual household pets, are not housed or kept "
        "within 100 ft of any dwelling not on the same lot."
    )
    assert MEASURE.search(livestock)
    assert len(livestock) > PROSE_CHARS


def test_a_label_naming_its_unit_still_counts() -> None:
    """eCode360 linearises every table in four of these jurisdictions: the
    label carries "(ft)" and the cells below it are bare digits. A census that
    wanted a number and a unit on one line would see none of those tables --
    including the one this module was written for."""
    assert MEASURE.search("b. Slope of plane (degrees)")
    assert MEASURE.search("a. Height above ground at minimum required side yard depth (ft)")
    assert not MEASURE.search("3. Side yard height plane limit")


def test_read_means_beside_and_not_nearby() -> None:
    """Milwaukie's plane sits four rows below a setback that was encoded. A
    window generous enough to call that read would have hidden the finding."""
    assert READ_WINDOW <= 2


# -- the ledger -------------------------------------------------------------


def test_a_section_heading_has_to_belong_to_its_document() -> None:
    """Same ownership rule the cross-reference ledger uses. A wrapped citation
    at the start of a line would otherwise rename every statement under it."""
    lines = [
        "§ 19.301.4. Development Standards.",
        "Front yard 20 ft",
        "MMC 36.410. Something Elsewhere.",
        "Rear yard 15 ft",
    ]
    assert _sections(lines, {"19"}) == ["19.301.4"] * 4


def test_the_ledger_round_trips(tmp_path: Path, milwaukie: list[Uncited]) -> None:
    path = write(milwaukie, tmp_path / "uncited.csv")
    back = list(csv.DictReader(path.open(encoding="utf-8")))

    assert len(back) == len(milwaukie)
    assert {r["bucket"] for r in back} == {"unread", "unfielded"}
    assert all(int(r["repeats"]) >= 1 for r in back)


def test_an_empty_answer_says_so_rather_than_printing_nothing() -> None:
    assert "no unread statements" in "\n".join(render(()))
    assert "no unfielded statements" in "\n".join(render((), unfielded=True))


def test_a_number_written_twice_is_still_a_number() -> None:
    """Ordinance drafters write the figure out and then repeat it in brackets:
    "a minimum driveway apron width of twelve (12) feet". The closing bracket
    stood between the digits and the unit, so the census saw no measurement --
    and Milwaukie's access-management chapter, 328 lines that had just answered
    a standing question about driveway width, was reported as stating nothing
    measurable at all. A zero is the one answer this ledger must never give
    cheaply.

    Troutdale is why it is not a local repair: it drafts this way throughout.
    """
    assert MEASURE.search("a minimum driveway apron width of twelve (12) feet")
    assert MEASURE.search("Maximum Building Height: Three (3) stories or forty (40) feet")
    assert MEASURE.search("shall not be located within ten (10) feet of any other")
    # Still a number and a unit, not a paragraph number followed by a word.
    assert not MEASURE.search("3. Side yard height plane limit")
    assert not MEASURE.search("(a) On the portion of the site")


def test_the_chapter_that_prompted_the_repair_reports_its_statements(
    milwaukie: list[Uncited],
) -> None:
    """The corpus half of the test above. A pattern fixed in isolation is a
    pattern that can be fixed against a string nobody holds."""
    access = f"{MILWAUKIE}/12.16.access-management.txt"
    assert [r for r in milwaukie if r.path == access]


def test_the_state_does_not_survey_a_city_s_code(layers: dict[str, Layer]) -> None:
    """A layer owns the documents in its own directory and no others.

    The ownership test was ``path.startswith(layer + "/")``, which is true of
    every document in the corpus when the layer is ``or``. So Oregon was
    surveyed against Milwaukie's zoning code, found almost nothing cited there,
    and filed a second copy of nearly every unread line under the state's name
    -- 4,686 of 10,018 rows, each one blaming the wrong jurisdiction. A census
    half of which is a shadow of the other half cannot be counted.
    """
    from flats.provenance.store import ProvenanceStore

    store = ProvenanceStore()
    held = {p for p in store.documents() if p.rsplit("/", 1)[0] == "or"}

    assert held, "the state layer does hold documents of its own"
    assert {r.path for r in uncited(layers["or"])} <= held
