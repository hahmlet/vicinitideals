"""Portland's multi-dwelling zones, and the split cells inside them.

Portland is the largest market FLATS screens and Chapter 33.120 is where its
fourplex-eligible land actually is — RM1 through RM4 and RX all permit a
fourplex outright, and until this encoding every lot in them resolved as an
un-encoded zone.

Table 120-4 states four standards as two numbers separated by a slash. A slash
is not a value. Each one is resolved in the prose of the section the table
points at, and each is encoded with the *binding* half as the base and the
permissive half behind a registered condition, so that a lot nobody has
gathered the condition for cannot come back GREEN on the strength of the
permissive half.

These tests are the guard on that direction. They would all still pass if the
two halves were swapped — which is exactly the mistake they exist to catch —
so each one asserts the number, not merely that a variant exists.
"""

from __future__ import annotations

import pytest

from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet, Verdict

pytestmark = pytest.mark.unit

PDX = "or/multnomah/portland"


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


# --- the zones exist at all ----------------------------------------------


@pytest.mark.parametrize("zone", ["RM1", "RM2", "RM3", "RM4", "RX", "RMP"])
def test_every_multi_dwelling_zone_resolves(rules: RuleSet, zone: str) -> None:
    assert rules.resolve(PDX, zone).verdict is not Verdict.zone_not_encoded


@pytest.mark.parametrize(
    "zone,allowed",
    [("RM1", True), ("RM2", True), ("RM3", True), ("RM4", True), ("RX", True), ("RMP", False)],
)
def test_fourplex_permission_follows_table_120_2(rules: RuleSet, zone: str, allowed: bool) -> None:
    """RMP is the one "No" in the fourplex row. A manufactured dwelling park
    zone that screened as buildable would put the pod somewhere it is barred
    outright, which no amount of lot geometry rescues."""
    assert rules.resolve(PDX, zone).values["quadplex_allowed"].value is allowed


# --- the split cells, in the safe direction ------------------------------


@pytest.mark.parametrize("zone", ["RM3", "RM4"])
def test_the_deeper_half_of_the_5_10_setback_binds_by_default(rules: RuleSet, zone: str) -> None:
    """Table 120-4 prints "5/10 ft.". 33.120.220.B.1 gives 5 ft to buildings up
    to 55 feet tall and 10 ft above that. A pod whose height nobody has stated
    gets 10."""
    res = rules.resolve(PDX, zone)

    assert res.values["setback_side_ft"].value == 10
    assert res.values["setback_rear_ft"].value == 10


@pytest.mark.parametrize("zone", ["RM3", "RM4"])
def test_a_low_rise_pod_earns_the_five(rules: RuleSet, zone: str) -> None:
    res = rules.resolve(PDX, zone, conditions=["low_rise"])

    assert res.values["setback_side_ft"].value == 5
    assert res.values["setback_rear_ft"].value == 5


@pytest.mark.parametrize("zone", ["RM3", "RM4"])
def test_a_street_side_line_keeps_five_whatever_the_height(rules: RuleSet, zone: str) -> None:
    """The 10 ft applies only to a side or rear line that is NOT a street lot
    line. Folding that into the side setback would take five feet off the
    buildable width of every corner lot in two zones."""
    assert rules.resolve(PDX, zone).values["setback_street_side_ft"].value == 5


def test_rm2_coverage_takes_the_sixty_until_the_corridor_map_says_otherwise(
    rules: RuleSet,
) -> None:
    """Table 120-4 prints "60/70%". 33.120.225.B gives 70 percent to sites on a
    Civic or Neighborhood Corridor. We do not hold Map 120-1, so 60 binds — the
    ten points of coverage are real buildable area and claiming them on a site
    that has not earned them is a false GREEN."""
    assert rules.resolve(PDX, "RM2").values["max_coverage_pct"].value == 60
    on_a_corridor = rules.resolve(PDX, "RM2", conditions=["civic_corridor"])
    assert on_a_corridor.values["max_coverage_pct"].value == 70


def test_rm4_takes_the_tighter_half_of_both_its_split_cells(rules: RuleSet) -> None:
    """FAR "4 to 1 or 3 to 1" and height "75/100 ft." Neither binds a
    two-storey pod, which is exactly why they would go unnoticed if they were
    encoded the permissive way round."""
    res = rules.resolve(PDX, "RM4")

    assert res.values["max_far"].value == 3.0
    assert res.values["max_height_ft"].value == 75


# --- the standards that are absent on purpose ----------------------------


@pytest.mark.parametrize("zone", ["RM1", "RM2", "RM3", "RM4", "RX"])
def test_no_maximum_front_setback_is_asserted(rules: RuleSet, zone: str) -> None:
    """Table 120-4 states one, but 33.120.220.C.1 applies it only on a transit
    street or in a Pedestrian District. A base value carries no condition, so
    encoding it would push every building in the zone toward the street on the
    strength of a standard most sites never see. Absent, and said so in the
    notes, beats present and wrong."""
    assert "setback_front_max_ft" not in rules.resolve(PDX, zone).values


def test_rx_states_a_frontage_and_no_lot_area(rules: RuleSet) -> None:
    """Table 120-3 gives RX a 10-foot front lot line and no area minimum at
    all. The zero is read off the table rather than standing in for a value
    nobody looked up — which is the difference between a zone that is encoded
    and a zone that is blank."""
    res = rules.resolve(PDX, "RX")

    assert res.values["min_lot_sqft"].value == 0
    assert res.values["min_frontage_ft"].value == 10


# --- the single-dwelling chapter is untouched ----------------------------


def test_the_single_dwelling_zones_still_resolve_as_they_did(rules: RuleSet) -> None:
    """33.110 and 33.120 are separate chapters in one layer file. Appending six
    zones must not disturb the six already there."""
    res = rules.resolve(PDX, "R5")

    assert res.values["min_lot_sqft"].value == 3000
    assert res.values["setback_front_ft"].value == 10
