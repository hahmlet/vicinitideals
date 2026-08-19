"""Gresham states two numbers for width and frontage, and only one was encoded.

Table 4.0130 runs every dimension twice -- interior lot, then corner lot --
and the corner row is routinely the larger number: 40 feet of width in LDR-5
where the interior row asks 35, 70 in MDR-12 where it asks 16. Encoding only
the interior row measured every corner lot in the city against a standard the
code does not state for it, in the direction that certifies lots.

The MDR-24 townhouse cells state nothing at all and hand the number to notes 8
and 10, which state three each, by access.
"""

from __future__ import annotations

import pytest

from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

GRESHAM = "or/multnomah/gresham"
ZONES = ("LDR-5", "LDR-7", "TR", "TLDR", "MDR-12", "MDR-24")


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


def width(rules: RuleSet, zone: str, *conditions: str) -> int | None:
    got = rules.resolve(GRESHAM, zone, conditions).values.get("min_lot_width_ft")
    return None if got is None else got.value


def frontage(rules: RuleSet, zone: str, *conditions: str) -> int | None:
    got = rules.resolve(GRESHAM, zone, conditions).values.get("min_frontage_ft")
    return None if got is None else got.value


def test_a_corner_lot_gets_the_corner_row(rules: RuleSet) -> None:
    assert width(rules, "LDR-5") == 35
    assert width(rules, "LDR-5", "corner_lot") == 40
    assert width(rules, "MDR-12", "corner_lot") == 70
    assert frontage(rules, "LDR-5", "corner_lot") == 40


def test_every_residential_zone_answers_for_a_corner(rules: RuleSet) -> None:
    # The failure this guards is silence: a zone with no corner variant hands
    # back the interior number and looks exactly like one that has been read.
    for zone in ZONES:
        assert "corner_lot" in rules.resolve(GRESHAM, zone).levers, zone


def test_mdr_24_had_no_width_standard_at_all(rules: RuleSet) -> None:
    # It was missing, not zero: no width test ran in MDR-24, so a lot too
    # narrow for the pod read as unconstrained.
    assert width(rules, "MDR-24") == 16


def test_note_8_states_the_corner_townhouse_width_by_access(rules: RuleSet) -> None:
    assert width(rules, "MDR-24", "unit_lots", "corner_lot") == 42
    assert width(rules, "MDR-24", "unit_lots", "corner_lot", "abuts_alley") == 16


def test_note_10_states_the_corner_townhouse_frontage_by_access(rules: RuleSet) -> None:
    assert frontage(rules, "MDR-24", "unit_lots", "corner_lot") == 32
    assert frontage(rules, "MDR-24", "unit_lots", "corner_lot", "abuts_alley") == 25


def test_a_corner_townhouse_lot_owes_no_frontage_where_the_table_says_none(
    rules: RuleSet,
) -> None:
    # "None" in the cell is a standard that does not apply, which is a
    # different answer from a number nobody encoded -- and it has to be stated,
    # or the interior 16 ft carries over onto a corner it was never written for.
    got = rules.resolve(GRESHAM, "LDR-5", ("unit_lots", "corner_lot"))
    assert "min_frontage_ft" in got.exempted
    assert "min_frontage_ft" not in got.values


def test_no_corner_configuration_resolves_two_variants_at_once(rules: RuleSet) -> None:
    # unit_lots and corner_lot both select a variant, so every zone needs the
    # pair stated too. Without it the resolver ties, carries the base, and
    # reports ambiguity -- which is honest, and useless.
    for zone in ZONES:
        for conditions in (
            ("corner_lot",),
            ("unit_lots",),
            ("unit_lots", "corner_lot"),
            ("unit_lots", "corner_lot", "abuts_alley"),
        ):
            got = rules.resolve(GRESHAM, zone, conditions)
            assert not got.ambiguous, f"{zone} {conditions}: {got.ambiguous}"


# --- CMF, where the townhouse standards live in the notes --------------
#
# Table 4.0430 states one residential row and hands the townhouse numbers to
# notes 1, 6 and 17. Encoding only the row measured a unit-lots pod against a
# multi-family site's 10,000 square feet and 100 feet of frontage, and let it
# off the 5-foot side yard the note asks for on any wall that is not shared.


def test_a_unit_lots_pod_is_not_measured_against_a_multi_family_site(
    rules: RuleSet,
) -> None:
    base = rules.resolve(GRESHAM, "CMF")
    assert base.values["min_lot_sqft"].value == 10000
    assert base.values["min_frontage_ft"].value == 100

    town = rules.resolve(GRESHAM, "CMF", ("unit_lots",))
    assert "min_lot_sqft" in town.exempted, "note 6 switches the site minimum off"
    assert town.values["min_frontage_ft"].value == 16


def test_the_townhouse_side_yard_is_tighter_than_the_row_above_it(rules: RuleSet) -> None:
    # The direction that matters: the base row owes no side yard at all, so
    # reading it for a townhouse gives away 5 feet the code asks for.
    assert rules.resolve(GRESHAM, "CMF").values["setback_side_ft"].value == 0
    town = rules.resolve(GRESHAM, "CMF", ("unit_lots",))
    assert town.values["setback_side_ft"].value == 5
    shared = rules.resolve(GRESHAM, "CMF", ("unit_lots", "attached_wall"))
    assert shared.values["setback_side_ft"].value == 0


def test_the_cmf_rear_yard_follows_the_alley(rules: RuleSet) -> None:
    assert rules.resolve(GRESHAM, "CMF", ("unit_lots",)).values["setback_rear_ft"].value == 10
    alley = rules.resolve(GRESHAM, "CMF", ("unit_lots", "abuts_alley"))
    assert alley.values["setback_rear_ft"].value == 5


def test_cmf_corner_frontage_binds_at_the_number_without_an_alley(rules: RuleSet) -> None:
    assert rules.resolve(GRESHAM, "CMF", ("unit_lots", "corner_lot")).values[
        "min_frontage_ft"
    ].value == 32
    assert rules.resolve(GRESHAM, "CMF", ("unit_lots", "corner_lot", "abuts_alley")).values[
        "min_frontage_ft"
    ].value == 25


# --- the plan districts, where the same row prints twice ---------------
#
# Downtown, Springwater and Pleasant Valley each run an interior row and a
# corner row, and each hands the townhouse its own pair. Two of the three
# were also missing whole standards: Springwater had no frontage and no
# depth encoded, Pleasant Valley no frontage and no garage setback -- a
# standard nobody encoded never runs, and never running certifies.

PLAN_ZONES = ("DRL-1", "DRL-2", "LDR-SW", "THR-SW", "LDR-PV")


def test_every_plan_district_answers_for_a_corner(rules: RuleSet) -> None:
    for zone in PLAN_ZONES:
        assert "corner_lot" in rules.resolve(GRESHAM, zone).levers, zone


def test_downtown_corner_rows(rules: RuleSet) -> None:
    for zone in ("DRL-1", "DRL-2"):
        assert width(rules, zone, "corner_lot") == 40
        assert width(rules, zone, "unit_lots", "corner_lot") == 20
        assert frontage(rules, zone, "corner_lot") == 40
        assert frontage(rules, zone, "unit_lots") == 16
        assert frontage(rules, zone, "unit_lots", "corner_lot") == 20
        got = rules.resolve(GRESHAM, zone, ("unit_lots",))
        assert "min_lot_sqft" in got.exempted, "Table 4.1130 reads Townhouse: None"


def test_springwater_had_no_frontage_and_no_depth_at_all(rules: RuleSet) -> None:
    got = rules.resolve(GRESHAM, "LDR-SW")
    assert got.values["min_frontage_ft"].value == 35
    assert got.values["min_lot_depth_ft"].value == 80
    assert frontage(rules, "LDR-SW", "corner_lot") == 40
    # F reads "None" for a townhouse lot on both rows, which is a standard
    # that does not apply rather than 35 feet carried over.
    town = rules.resolve(GRESHAM, "LDR-SW", ("unit_lots",))
    assert "min_frontage_ft" in town.exempted
    assert width(rules, "LDR-SW", "unit_lots", "corner_lot") == 20


def test_springwater_lot_size_is_exempt_not_zero(rules: RuleSet) -> None:
    # The Townhouse row reads "None". A 0 passes every lot; an exemption says
    # the standard is not the one being applied.
    got = rules.resolve(GRESHAM, "LDR-SW", ("unit_lots",))
    assert "min_lot_sqft" in got.exempted
    assert "min_lot_sqft" not in got.values


def test_pleasant_valley_garage_setback_now_runs(rules: RuleSet) -> None:
    # 20 feet, twice the facade setback, and it is what a street-facing
    # garage door fails on first.
    got = rules.resolve(GRESHAM, "LDR-PV")
    assert got.values["setback_garage_entrance_ft"].value == 20
    assert got.values["min_frontage_ft"].value == 35
    assert frontage(rules, "LDR-PV", "corner_lot") == 40
    assert frontage(rules, "LDR-PV", "unit_lots") == 18
    assert frontage(rules, "LDR-PV", "unit_lots", "corner_lot") == 20


def test_pleasant_valley_reads_its_last_three_columns(rules: RuleSet) -> None:
    shared = rules.resolve(GRESHAM, "LDR-PV", ("attached_wall",))
    assert shared.values["setback_side_ft"].value == 0
    alley = rules.resolve(GRESHAM, "LDR-PV", ("abuts_alley",))
    assert alley.values["setback_rear_ft"].value == 8


def test_no_plan_district_configuration_is_ambiguous(rules: RuleSet) -> None:
    for zone in PLAN_ZONES:
        for conditions in (
            ("corner_lot",),
            ("unit_lots",),
            ("unit_lots", "corner_lot"),
            ("unit_lots", "corner_lot", "abuts_alley"),
            ("attached_wall",),
        ):
            got = rules.resolve(GRESHAM, zone, conditions)
            assert not got.ambiguous, f"{zone} {conditions}: {got.ambiguous}"


# --- floor area ratio, which none of the three plan districts had ------
#
# A 4-unit two-storey pod is roughly 4,000 square feet of floor, so a 1.0
# cap asks for 4,000 square feet of lot before any setback is measured --
# and Downtown's own minimum lot size is 4,000. Not encoding it meant the
# standard closest to binding never ran.


def far(rules: RuleSet, zone: str, *conditions: str) -> float | None:
    got = rules.resolve(GRESHAM, zone, conditions).values.get("max_far")
    return None if got is None else got.value


def test_the_plan_districts_state_a_floor_area_ratio(rules: RuleSet) -> None:
    for zone in ("DRL-1", "DRL-2", "LDR-SW", "LDR-PV"):
        assert far(rules, zone) == 1.0, zone


def test_the_far_row_does_not_reach_a_townhouse_in_springwater_or_pv(
    rules: RuleSet,
) -> None:
    # The row is headed "Single Detached, Duplex, Triplex, Quadplex" and the
    # row under it reads N/A for all other uses, so the cap governs the pod
    # built as a quadplex and not the same pod on unit lots.
    for zone in ("LDR-SW", "LDR-PV"):
        assert "max_far" in rules.resolve(GRESHAM, zone, ("unit_lots",)).exempted, zone
    # Downtown's row is per sub-district and splits by no use at all.
    assert far(rules, "DRL-1", "unit_lots") == 1.0


def test_downtown_now_states_a_height(rules: RuleSet) -> None:
    # It does not bind a two-storey pod. A zone that answers "no height
    # standard" reads the same as one nobody has read, which is the failure.
    assert rules.resolve(GRESHAM, "DRL-1").values["max_height_ft"].value == 35
    assert rules.resolve(GRESHAM, "DRL-2").values["max_height_ft"].value == 50
