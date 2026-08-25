"""A `false` a footnote might lift is not a `false` you can stop reading at.

Four zones say the quadplex is not permitted and four zones still owe every
dimensional standard behind that answer. Gresham RTC, MC and CC read NP in
Table 4.0420; Portland CI1 reads N for Household Living in Table 150-1. None of
the four cells carries a marker of its own -- but each sits inside a region a
footnote block governs, and in each case one of that block's notes is ruled
``unmeasured``: read, understood, waiting on data nobody holds. Gresham's is
note 2, middle housing land divisions along the NE Glisan and NE 162nd corridors.
Portland's is note [3], the PCC Sylvania FAR boundary on Map 150-5.

Neither note can plausibly turn a Quadplex NP into a P. That is not the point.
The census scopes a footnote to its whole region on purpose, because telling a
cell marker from a row marker from a column marker in extracted text is exactly
the judgement that gets made wrong silently, and an over-scoped footnote costs
a review while an under-scoped one costs a false GREEN. So the `false` is not
*settled*, the resolver keeps asking for the standards behind it, and the
recorded way out is to encode them rather than to narrow the note.

809 lots, and they were invisible for a fortnight because the shipped coverage
ledger was stale. The last test here is the guard against that recurring.
"""

from __future__ import annotations

import pytest

from flats.rules.caps import caps_for
from flats.rules.ledger import read_coverage
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

#: The four, and the unmeasured fact whose footnote keeps each gate unsettled.
UNSETTLED = {
    ("or/multnomah/gresham", "RTC"): "civic_corridor",
    ("or/multnomah/gresham", "MC"): "civic_corridor",
    ("or/multnomah/gresham", "CC"): "civic_corridor",
    ("or/multnomah/portland", "CI1"): "site_specific_limitation",
}


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


@pytest.mark.parametrize(("key", "fact"), sorted(UNSETTLED.items()))
def test_the_use_gate_is_shut_but_not_settled(
    rules: RuleSet, key: tuple[str, str], fact: str
) -> None:
    """Both halves, together. Either alone is a different zone.

    A zone whose `quadplex_allowed` is false and *uncapped* owes nothing: the
    screen returns RED at the use gate and never reads a setback. A zone whose
    false is capped owes everything, because the cap is the admission that we
    cannot say the gate stays shut."""
    layer, zone = key
    resolved = rules.resolve(layer, zone)

    assert resolved.values["quadplex_allowed"].value is False
    assert caps_for(layer, zone)["quadplex_allowed"] == (fact,)


@pytest.mark.parametrize("key", sorted(UNSETTLED))
def test_and_so_it_owes_the_standards_behind_it(
    rules: RuleSet, key: tuple[str, str]
) -> None:
    layer, zone = key

    assert rules.resolve(layer, zone).missing_required == ()


def test_gresham_cc_and_mc_are_one_column_printed_twice(rules: RuleSet) -> None:
    """Every cell of Table 4.0430 reads alike in both districts, so any drift
    between these two is a transcription error rather than a code difference.
    The one thing that legitimately differs is where the extraction wrapped."""
    cc = rules.resolve("or/multnomah/gresham", "CC").values
    mc = rules.resolve("or/multnomah/gresham", "MC").values

    assert {k: v.value for k, v in cc.items()} == {k: v.value for k, v in mc.items()}

    # Only what the zone rows themselves carry. A citywide standard reaches
    # every Gresham zone identically by construction, so it can say nothing
    # about whether two table columns were transcribed alike -- and pinning it
    # here means the next citywide standard anyone encodes fails this test
    # while the columns it guards are still perfectly in agreement. That is the
    # shape of a test that goes red for doing the work right.
    citywide = {k for layer in rules.chain_for("or/multnomah/gresham")
                for k in layer.defaults}
    assert {"parking_min_per_unit", "land_division_parent_standards"} <= citywide
    assert cc["parking_min_per_unit"].value == 0
    assert cc["land_division_parent_standards"].value is True
    assert {k: v.value for k, v in cc.items() if k not in citywide} == {
        "quadplex_allowed": False,
        "max_height_ft": 45,
        "min_density_du_per_acre": 12,
        "setback_front_ft": 0,
        "setback_side_ft": 0,
        "setback_rear_ft": 0,
        "setback_street_side_ft": 0,
        # Row H prints 10 feet. Note 3c drops it to five on a Collector,
        # Community or Local street, for any building, and street class is not
        # read here. This is a MAXIMUM, so the small number is the strict one --
        # the opposite of every minimum setback in the corpus, and the reason
        # this line is pinned rather than left to a reviewer's eye.
        "setback_front_max_ft": 5,
    }


def test_gresham_cc_is_a_window_rather_than_a_floor(rules: RuleSet) -> None:
    """The density pair is what binds here, and only together. Neither row says
    so on its own, which is why the zone notes say it and this test holds it:
    twelve units per net acre puts four units on no more than about 14,520 sq
    ft, forty per acre puts them on no less than about 4,356, and the lot-size
    row is None."""
    values = rules.resolve("or/multnomah/gresham", "CC").values
    layer = load_rules()["or/multnomah/gresham"]

    assert values["min_density_du_per_acre"].value == 12
    assert layer.zones["CC"].values["max_density_du_per_acre"].value == 40
    assert layer.zones["CC"].values["min_lot_sqft"].exempt is True
    assert layer.zones["CC"].values["min_frontage_ft"].exempt is True


def test_gresham_rtc_answers_the_height_question_in_storeys(rules: RuleSet) -> None:
    """Six storeys inside the Stark/Burnside/181st Triangle for exclusively
    commercial or institutional buildings, four inside it for buildings that
    include any other use, ten outside it. A building with dwellings in it is
    never the six-storey case; whether a lot is inside the Triangle is a map
    nothing here reads. Four is taken, and it cannot bind a 26 ft pod either
    way -- what this pins is that the field is answered at all, since
    `max_height_stories` stands in for `max_height_ft` in the required check."""
    values = rules.resolve("or/multnomah/gresham", "RTC").values

    assert values["max_height_stories"].value == 4
    assert "max_height_ft" not in values
    assert values["setback_front_ft"].value == 5
    assert values["setback_side_ft"].value == 0
    assert values["setback_rear_ft"].value == 15


def test_portland_ci1_takes_the_neighbours_setback_on_every_line(
    rules: RuleSet,
) -> None:
    """Table 150-2 gives CI1 three minimums by what the lot line faces -- 15 ft
    against OS or RF-R2.5, 10 against RM1-RMP or IR, 0 against a C, CI, E or I
    lot -- and no residual. Every line takes one of the three, and which one is
    the neighbour's zoning rather than this lot's, which nothing here reads. So
    15 on all four sides: the figure that cannot turn a RED lot green.

    IR one column over escapes this entirely; its column is a single merged
    cell measured off the building. See that zone's notes."""
    values = rules.resolve("or/multnomah/portland", "CI1").values

    assert values["setback_front_ft"].value == 15
    assert values["setback_side_ft"].value == 15
    assert values["setback_rear_ft"].value == 15
    # CI1's maximum building setback reads None, so note [5] -- no minimum
    # setback where a maximum applies -- never fires here. CI2 and IR both get
    # that relief on a transit street or in a Pedestrian District; CI1 does not.
    assert "setback_front_max_ft" not in values


def test_portland_ci1_gets_its_lot_minimum_from_the_far(rules: RuleSet) -> None:
    """33.150.200 states no minimum lot size anywhere in the campus zones, and
    then Table 150-2 sets CI1's floor area ratio at 0.5 to 1, the tightest in
    the corpus. Four units of a 56 by 36 ft pod over two floors is roughly
    4,000 sq ft of floor area, which at 0.5 asks for roughly 8,000 sq ft of
    site. The lot minimum arrives by the back door."""
    layer = load_rules()["or/multnomah/portland"]
    values = rules.resolve("or/multnomah/portland", "CI1").values

    assert layer.zones["CI1"].values["min_lot_sqft"].exempt is True
    assert values["max_far"].value == 0.5
    assert values["max_coverage_pct"].value == 50
    assert values["min_landscaped_pct"].value == 25


def test_no_observed_zone_owes_a_required_field() -> None:
    """The guard, and the reason this file exists at all.

    These four sat in the ledger owing five standards apiece and nobody saw it,
    because the committed `coverage.csv` predated the resolver change that
    started asking. A ledger is only a report of the run that wrote it, so the
    invariant has to be asserted somewhere that runs every time.

    A failure here means one of two things and both are worth stopping for: a
    zone was encoded without its required standards, or a footnote ruling moved
    and unsettled a gate that used to be settled."""
    owing = [
        (row.jurisdiction, row.zone, row.missing_required)
        for row in read_coverage()
        if row.missing_required
    ]

    assert owing == []
