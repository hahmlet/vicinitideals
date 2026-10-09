"""Milwaukie's four mixed-use zones -- DMU, NMU, GMU, SMU (2026-10-08).

They were `zone_rulings` waiting on their dimensions: 218 lots between them.
Read now, and the answer is mostly "not by right":

* NMU and SMU: every dwelling row of Table 19.303.2 reads CU in their
  columns, and a conditional use is a Type III hearing. RED BY RULING (Steph,
  2026-10-08, by right only) -- `quadplex_allowed` false with no variant, so
  nothing can reopen it.
* GMU: Townhouses P, Duplex/Triplex/Quadplex CU. A four-unit building on one
  lot is the CU row; split onto unit lots it is townhouses. So `false` with a
  `unit_lots` variant and no hearing variant.
* DMU: no duplex/triplex/quadplex row at all (not listed = prohibited,
  19.304.2.D); townhouses P except on Main Street and south of Scott Street,
  which are drawn on Figure 19.304-2, an image. The townhouse variant waits
  on `inside_mapped_use_area`, which nothing measures, so no DMU lot is GREEN
  until that figure is traced.
"""

from __future__ import annotations

import pytest

from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

MILWAUKIE = "or/clackamas/milwaukie"
BASE = "or/clackamas/milwaukie/19.300.base-zones.txt"
POD = ("multi_story", "attached_wall")
FOUR = ("DMU", "NMU", "GMU", "SMU")


@pytest.fixture(scope="module")
def milwaukie() -> Layer:
    return load_rules()[MILWAUKIE]


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


def _use(rules: RuleSet, zone: str, *conditions: str):
    return rules.resolve(MILWAUKIE, zone, (*POD, *conditions)).values[
        "quadplex_allowed"
    ]


def _value(milwaukie: Layer, zone: str, field: str):
    return milwaukie.zones[zone].values[field]


def test_the_four_codes_are_zones_now_and_no_longer_rulings(
    milwaukie: Layer,
) -> None:
    """A code is a zone or a ruling, never both."""
    for code in FOUR:
        assert code in milwaukie.zones
        assert code not in milwaukie.zone_rulings


@pytest.mark.parametrize("zone", ["NMU", "SMU"])
def test_the_conditional_use_columns_are_red_by_ruling(
    milwaukie: Layer, rules: RuleSet, zone: str
) -> None:
    held = _value(milwaukie, zone, "quadplex_allowed")
    assert held.value is False
    assert held.variants == ()
    assert (milwaukie.zones[zone].notes or "").startswith(
        "RED BY RULING (Steph, 2026-10-08)"
    )
    for extra in ((), ("unit_lots",), ("unit_lots", "inside_mapped_use_area"),
                  ("conditional_use",), ("mixed_use",)):
        use = _use(rules, zone, *extra)
        assert use.value is False
        assert not use.levers
    resolved = rules.resolve(MILWAUKIE, zone, (*POD, "unit_lots"))
    # A settled refusal does not demand the standards it will never use.
    assert resolved.missing_required == ()


def test_gmu_is_by_right_only_as_townhouses_on_unit_lots(
    milwaukie: Layer, rules: RuleSet
) -> None:
    held = _value(milwaukie, "GMU", "quadplex_allowed")
    assert held.value is False
    assert {v.when for v in held.variants} == {
        ("unit_lots",),
        ("unit_lots", "willamette_greenway_zone"),
    }
    assert _use(rules, "GMU").value is False
    assert _use(rules, "GMU", "unit_lots").value is True
    # Never a conditional-use path: that is a hearing.
    assert _use(rules, "GMU", "conditional_use").value is False
    # The greenway turns every development into a conditional use.
    assert _use(rules, "GMU", "unit_lots", "willamette_greenway_zone").value is False


def test_dmu_townhouses_wait_on_a_figure_nothing_measures(
    milwaukie: Layer, rules: RuleSet
) -> None:
    held = _value(milwaukie, "DMU", "quadplex_allowed")
    assert held.value is False
    assert _use(rules, "DMU").value is False
    # Unit lots alone is not enough: Main Street and south of Scott Street.
    assert _use(rules, "DMU", "unit_lots").value is False
    assert _use(rules, "DMU", "unit_lots", "inside_mapped_use_area").value is True
    assert (
        _use(
            rules,
            "DMU",
            "unit_lots",
            "inside_mapped_use_area",
            "willamette_greenway_zone",
        ).value
        is False
    )
    assert _use(rules, "DMU", "conditional_use").value is False


def test_the_use_citations_carry_the_controlling_sentences(
    milwaukie: Layer, store: ProvenanceStore
) -> None:
    nmu = store.quote(_value(milwaukie, "NMU", "quadplex_allowed").prov.quote)
    assert "Duplex, Triplex, Quadplex" in nmu
    assert "CU" in nmu
    gmu = store.quote(_value(milwaukie, "GMU", "quadplex_allowed").prov.quote)
    assert "Quadplex" in gmu
    variant = _value(milwaukie, "GMU", "quadplex_allowed").variants[0]
    assert "Townhouses" in store.quote(variant.prov.quote)
    dmu = _value(milwaukie, "DMU", "quadplex_allowed").variants[0]
    text = store.quote(dmu.prov.quote)
    assert "Townhouse" in text
    assert "Live/work units and townhouses are not permitted on Main Street" in text


def test_the_downtown_numbers(milwaukie: Layer) -> None:
    assert _value(milwaukie, "DMU", "min_lot_sqft").value == 750
    assert _value(milwaukie, "DMU", "min_frontage_ft").value == 15
    assert _value(milwaukie, "DMU", "max_height_ft").value == 45
    assert _value(milwaukie, "DMU", "min_building_height_ft").value == 25
    assert _value(milwaukie, "DMU", "setback_front_ft").value == 0
    assert _value(milwaukie, "DMU", "setback_front_max_ft").value == 10
    assert _value(milwaukie, "DMU", "min_density_du_per_acre").value == 25
    assert _value(milwaukie, "DMU", "parking_front_prohibited").value is True
    # No coverage row anywhere in the chapter: silence is none.
    assert _value(milwaukie, "DMU", "max_coverage_pct").exempt is True
    # Townhouses carry the larger 19.505.5 lot size.
    lot = _value(milwaukie, "DMU", "min_lot_sqft")
    assert {(v.when, v.value) for v in lot.variants} == {(("unit_lots",), 1500)}


def test_the_commercial_mixed_use_numbers(milwaukie: Layer) -> None:
    for zone in ("GMU", "NMU", "SMU"):
        assert _value(milwaukie, zone, "min_lot_sqft").value == 1500
        assert _value(milwaukie, zone, "min_frontage_ft").value == 25
        assert _value(milwaukie, zone, "max_coverage_pct").value == 85
        assert _value(milwaukie, zone, "min_landscaped_pct").value == 15
    assert _value(milwaukie, "GMU", "max_height_ft").value == 45
    assert _value(milwaukie, "NMU", "max_height_ft").value == 45
    assert _value(milwaukie, "SMU", "max_height_ft").value == 35
    assert _value(milwaukie, "GMU", "min_density_du_per_acre").value == 25
    assert _value(milwaukie, "GMU", "max_density_du_per_acre").value == 50
    assert _value(milwaukie, "NMU", "min_density_du_per_acre").value == 11.6
    assert _value(milwaukie, "NMU", "max_density_du_per_acre").value == 14.5
    assert _value(milwaukie, "SMU", "min_density_du_per_acre").value == 7
    assert _value(milwaukie, "SMU", "setback_front_ft").value == 10
    assert _value(milwaukie, "SMU", "setback_front_max_ft").value == 15
    assert _value(milwaukie, "NMU", "setback_front_max_ft").value == 10
    assert _value(milwaukie, "GMU", "setback_front_max_ft").value == 20
    assert _value(milwaukie, "GMU", "setback_front_ft").value == 15


def test_gmu_yards_toward_a_residential_neighbour_are_the_r_md_front_yard(
    milwaukie: Layer, store: ProvenanceStore
) -> None:
    for zone in ("GMU", "DMU"):
        for field in ("setback_front_ft", "setback_side_ft", "setback_rear_ft"):
            held = _value(milwaukie, zone, field)
            assert {(v.when, v.value) for v in held.variants} == {
                (("abuts_residential_zone",), 20)
            }
            assert "19.504.4.A" in held.variants[0].prov.cite


def test_smu_side_and_rear_are_left_unfilled(milwaukie: Layer) -> None:
    """The table prints one cell, "5/10", and no sentence says which is which."""
    values = milwaukie.zones["SMU"].values
    assert "setback_side_ft" not in values
    assert "setback_rear_ft" not in values
    assert "5/10" in (milwaukie.zones["SMU"].notes or "")


def test_density_is_measured_on_the_city_s_net_acre(milwaukie: Layer) -> None:
    for zone, field in (
        ("DMU", "min_density_du_per_acre"),
        ("GMU", "min_density_du_per_acre"),
        ("GMU", "max_density_du_per_acre"),
    ):
        held = _value(milwaukie, zone, field)
        assert held.measured_on == "net_developable_area"
        assert (held.measured_on_quote or "").endswith("19.200.definitions.txt#L529-L530")


def test_every_number_is_quoted_from_a_line_that_states_it(
    milwaukie: Layer, store: ProvenanceStore
) -> None:
    from flats.encode.readiness import readiness_for

    misquoted = [
        (zone, field)
        for zone, field in readiness_for(milwaukie, store=store).misquoted
        if zone in FOUR
    ]
    assert misquoted == []


def test_everything_stays_draft(milwaukie: Layer) -> None:
    for zone in FOUR:
        for name, held in milwaukie.zones[zone].values.items():
            assert held.status.value == "draft", (zone, name)
