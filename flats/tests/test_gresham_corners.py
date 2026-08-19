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
