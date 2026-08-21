"""Nine more zones that let you build and never said how tall.

The other half of the gap Wilsonville's seven were the first half of. Same
cause: the coverage ledger was clean on 19 August, zones landed after it, and
nobody re-ran it. Nine Happy Valley zones permitted a quadplex and stated no
height, so the screen was placing a 26 ft building against no ceiling.

Three tables answer all nine. Very low density (R-40, R-20, R-15) and low
density (R-10, R-8.5, R-7) both print 45 feet in every column. Medium density
prints 45 for R-5 and 65 for MUR-S. R-20CC needs nothing of its own -- it adopts
R-20 by reference, which is what that reference is for.

The finding worth keeping is a footnote marker that points at the wrong note.
Every dimensional table in this chapter marks its height row with its own
single-family height relief -- except Table 16.22.040-2, which marks it 6, and
note 6 there is about usable open space. The height note is 7, one line below.
Confirmed in the source rather than blamed on the extraction: the document was
fetched twice and both copies print 6.

It moves nothing. Note 6 is a different standard and note 7 relieves
single-family only, which four attached dwellings are not. But a reviewer who
follows the marker lands on a note about open space with no way to tell whether
anyone read the height.
"""

from __future__ import annotations

import pytest

from flats.designs.model import load_catalog
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

HAPPY_VALLEY = "or/clackamas/happy-valley"
CHAPTER = f"{HAPPY_VALLEY}/16.22.residential.txt"

#: zone -> the figure its column prints.
FILLED = {
    "R40": 45,
    "R20": 45,
    "R15": 45,
    "R10": 45,
    "R8.5": 45,
    "R7": 45,
    "R5": 45,
    "MURS": 65,
}


@pytest.fixture(scope="module")
def happy_valley() -> Layer:
    return load_rules()[HAPPY_VALLEY]


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


# -- the three tables --------------------------------------------------------


def test_every_zone_that_was_silent_now_states_its_column(
    happy_valley: Layer, store: ProvenanceStore
) -> None:
    for zone, figure in FILLED.items():
        held = happy_valley.zones[zone].values["max_height_ft"]
        assert held.value == figure, zone
        quoted = store.quote(held.prov.quote)
        assert "Building height (maximum)" in quoted, zone
        assert str(figure) in quoted, zone


def test_the_quote_carries_the_header_because_the_row_prints_one_figure_thrice(
    happy_valley: Layer, store: ProvenanceStore
) -> None:
    """R-40, R-20 and R-15 all read 45. The row alone evidences the number and
    not the column, so the quote takes the header line with it."""
    quoted = store.quote(happy_valley.zones["R20"].values["max_height_ft"].prov.quote)
    assert "R-40" in quoted and "R-20" in quoted and "R-15" in quoted
    assert quoted.count("45 feet") == 3


def test_the_two_columns_of_the_medium_density_table_disagree(
    happy_valley: Layer, store: ProvenanceStore
) -> None:
    """Which is why that one is quoted per zone rather than shared: 45 and 65
    on the same row."""
    r5 = happy_valley.zones["R5"].values["max_height_ft"]
    murs = happy_valley.zones["MURS"].values["max_height_ft"]
    assert (r5.value, murs.value) == (45, 65)
    assert r5.prov.quote == murs.prov.quote
    quoted = store.quote(r5.prov.quote)
    assert "R-5" in quoted and "MUR-S" in quoted
    assert "45 feet" in quoted and "65 feet" in quoted


def test_the_borrowed_zone_needs_nothing_of_its_own(
    rules: RuleSet, happy_valley: Layer
) -> None:
    """R-20CC is a zoning-layer code with no chapter of its own and adopts R-20
    by reference. A height it gains from that reference is the reference doing
    its job -- unlike a pointer at one row, which is what made Wood Village's
    Town Center have to state its own answer."""
    assert "max_height_ft" not in happy_valley.zones["R20CC"].values
    assert happy_valley.zones["R20CC"].like.zone == "R20"
    assert rules.resolve(HAPPY_VALLEY, "R20CC").values["max_height_ft"].value == 45


# -- the marker that lands one short -----------------------------------------


def test_three_tables_mark_their_height_row_with_their_own_height_note(
    store: ProvenanceStore,
) -> None:
    lines = store.load(CHAPTER).text.splitlines()

    for row, marker in ((114, "2"), (298, "5"), (488, "5")):
        assert "Building height (maximum)" in lines[row - 1]
        assert f"45 feet{marker}" in lines[row - 1]

    # And in each of those tables the note that marker names is about height.
    for note_line, marker in ((118, "2"), (306, "5"), (496, "5")):
        text = lines[note_line - 1]
        assert text.lstrip().startswith(marker)
        assert "building height maximum is 45 feet at the front elevation" in text


def test_but_the_fourth_marks_it_with_the_open_space_note(
    store: ProvenanceStore,
) -> None:
    """Table 16.22.040-2, alone in the chapter. Marker 6, and note 6 is about
    usable open space; the height note is 7, printed on the next line."""
    lines = store.load(CHAPTER).text.splitlines()
    assert "Building height (maximum)" in lines[669]
    assert "45 feet6" in lines[669] and "65 feet6" in lines[669]

    note_6 = lines[678]
    note_7 = lines[679]
    assert note_6.lstrip().startswith("6")
    assert "20% of the net developable area must be usable open space" in note_6
    assert note_7.lstrip().startswith("7")
    assert "building height maximum is 45 feet at the front elevation" in note_7


def test_and_neither_reading_moves_the_number(
    happy_valley: Layer, store: ProvenanceStore
) -> None:
    """The reason it is recorded rather than repaired. Note 6 is a separate
    standard, not a qualifier on height. Note 7 relieves "single-family
    residential" -- four extra feet at the side and rear -- and this building is
    four attached dwellings, so it cannot take the relief. The cell stands
    either way, and the reviewer is told why the marker misleads."""
    assert happy_valley.zones["R5"].values["max_height_ft"].value == 45
    body = happy_valley.zones["R5"].values["max_height_ft"]
    assert body.qualified_by is None

    text = store.load(CHAPTER).text
    assert "The single-family residential building height maximum is 45 feet" in text


def test_the_discrepancy_is_written_down_where_the_next_reader_meets_it() -> None:
    """In the YAML beside the value, because that is where somebody checking
    this number will be standing. A finding recorded only in a commit message
    is a finding nobody reads twice."""
    from pathlib import Path

    yaml = Path("flats/config/jurisdictions/or/clackamas/happy-valley.yaml").read_text(
        encoding="utf-8"
    )
    assert "note 6 in this table is not about" in yaml
    assert "the only one that lands one short" in yaml
    assert "fetched twice, and both copies" in yaml


# -- what the lot comes back as ----------------------------------------------


def test_no_happy_valley_zone_that_permits_the_building_is_silent(
    rules: RuleSet, happy_valley: Layer
) -> None:
    for zone in happy_valley.zones:
        got = rules.resolve(HAPPY_VALLEY, zone)
        allowed = got.values.get("quadplex_allowed")
        if allowed and allowed.value:
            assert "max_height_ft" not in got.missing_required, zone


def test_the_pod_clears_every_one(rules: RuleSet) -> None:
    pod = next(d for d in load_catalog() if d.id == "pod56x36")
    assert pod.height_ft == 26
    for zone, figure in FILLED.items():
        assert rules.resolve(HAPPY_VALLEY, zone).values["max_height_ft"].value == figure


def test_and_no_footnote_is_left_asking(happy_valley: Layer) -> None:
    """Every note in these three tables was ruled in an earlier pass, so the
    new values arrive already answered rather than blocked. Asserted because
    the opposite -- a value that certifies under a note nobody read -- is the
    exact fault this project exists to avoid."""
    from flats.encode.qualified import qualified

    rows = [
        r
        for r in qualified()
        if r.layer == HAPPY_VALLEY and r.field == "max_height_ft" and r.zone in FILLED
    ]
    assert len(rows) == len(FILLED)
    assert not any(r.blocking for r in rows)
    assert not any(n.state == "unread" for r in rows for n in r.governing)
