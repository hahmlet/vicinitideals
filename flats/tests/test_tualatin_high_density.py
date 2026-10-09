"""Tualatin's four high-density codes: RMH, RH, RH/HR and MUC (2026-10-08).

All four permit the pod only as townhouses on individual lots: each housing
table lists Single-Family Dwelling N, Townhouse (or Rowhouse) P and a
Multi-Family Structure P (five or more units on one lot, TDC 31.060), and none
has a Quadplex row. The use answer is therefore false with a ``unit_lots``
variant that is the Townhouse row. These tests pin that answer and the numbers
each zone's table states, each against the code's own words.

Two rulings the layer's header records and these tests rely on:

- "Architectural Review" that settles a number inside a stated range on a
  permitted housing type is not a discretionary gate; the range is held at its
  top. Nothing in these four chapters is a conditional use for the pod.
- The setback ladders run on structure height; the pod is 26 ft, so its row is
  "25+ feet" (RH-HR: "25-30 feet" for the front, "25-<30" for side and rear).
"""

from __future__ import annotations

import pytest

from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer

pytestmark = pytest.mark.unit

TUALATIN = "or/clackamas/tualatin"
ZONES = ("RMH", "RH", "RH/HR", "MUC")


@pytest.fixture(scope="module")
def tualatin() -> Layer:
    return load_rules()[TUALATIN]


def _text(quote: str) -> str:
    return " ".join(ProvenanceStore().quote(quote).split())


def _field(layer: Layer, zone: str, field: str):
    return layer.zones[zone].values[field]


def _variant(layer: Layer, zone: str, field: str):
    (variant,) = _field(layer, zone, field).variants
    assert variant.when == ("unit_lots",), (zone, field)
    return variant


def test_the_four_are_blocks_not_rulings(tualatin: Layer) -> None:
    """The loader refuses a ruling whose code is also a block; the four to_read
    entries are gone and none came back as a ruling of any kind."""
    for zone in ZONES:
        assert zone in tualatin.zones, zone
        assert zone not in tualatin.zone_rulings, zone


@pytest.mark.parametrize("zone", ZONES)
def test_the_pod_is_refused_on_one_lot_and_permitted_on_unit_lots(
    tualatin: Layer, zone: str
) -> None:
    use = _field(tualatin, zone, "quadplex_allowed")
    assert use.value is False
    table = _text(use.prov.quote)
    assert "Single-Family Dwelling N" in table
    assert "Multi-Family Structure P" in table
    assert "Quadplex" not in table
    townhouse = _variant(tualatin, zone, "quadplex_allowed")
    assert townhouse.value is True
    assert "Townhouse (or Rowhouse) P" in _text(townhouse.prov.quote)


@pytest.mark.parametrize("zone", ZONES)
def test_no_zone_is_marked_red_by_ruling(tualatin: Layer, zone: str) -> None:
    """Architectural Review here applies standards to a permitted use; it is
    not a design review that can say no, so the by-right ruling does not make
    these zones red outright (the base answer is false for the one-lot reason
    in the use table, and the notes must not claim a ruling)."""
    note = " ".join(tualatin.zones[zone].notes.split())
    assert "RED BY RULING" not in note


# (zone, field, value, words the cited code line must contain)
NUMBERS = [
    ("RMH", "min_lot_sqft", 10000, "All Other Permitted Uses 10,000 square feet"),
    ("RMH", "min_lot_width_ft", 75, "All Other Permitted Uses 75 feet"),
    ("RMH", "setback_front_ft", 15, "25+ feet 15 feet"),
    ("RMH", "setback_street_side_ft", 15, "same as the front yard set- back"),
    ("RMH", "setback_garage_entrance_ft", 20, "garage door must be 20 feet"),
    ("RMH", "setback_side_ft", 12, "25+ feet 12 feet"),
    ("RMH", "setback_rear_ft", 12, "25+ feet 12 feet"),
    ("RMH", "parking_street_setback_ft", 10, "Vehicle Circulation Areas 10 feet"),
    ("RMH", "parking_lot_line_buffer_ft", 10, "Vehicle Circulation Areas 10 feet"),
    ("RMH", "max_height_ft", 35, "All Uses 35 feet"),
    ("RMH", "max_coverage_pct", 40, "All Other Permitted Uses 40%"),
    ("RMH", "max_density_du_per_acre", 15, "Maximum: 15 units per acre"),
    ("RMH", "min_density_du_per_acre", 11, "Minimum: 11 units per acre"),
    ("RH", "min_lot_sqft", 10000, "All Other Permitted Uses 10,000 square feet"),
    ("RH", "min_lot_width_ft", 75, "All Other Permitted Uses 75 feet"),
    ("RH", "setback_front_ft", 15, "25+ feet 15 feet"),
    ("RH", "setback_street_side_ft", 15, "same as the front yard setback"),
    ("RH", "setback_garage_entrance_ft", 20, "garage door must be 20 feet"),
    ("RH", "setback_side_ft", 12, "25+ feet 12 feet"),
    ("RH", "setback_rear_ft", 12, "25+ feet 12 feet"),
    ("RH", "parking_street_setback_ft", 10, "Vehicle Circulation Areas 10 feet"),
    ("RH", "parking_lot_line_buffer_ft", 10, "Vehicle Circulation Areas 10 feet"),
    ("RH", "max_height_ft", 35, "All Uses 35 feet"),
    ("RH", "max_coverage_pct", 45, "All Other Permitted Uses 45%"),
    ("RH", "max_density_du_per_acre", 25, "Maximum: 25 units per acre"),
    ("RH", "min_density_du_per_acre", 16, "Minimum: 16 units per acre"),
    ("RH/HR", "min_lot_sqft", 10000, "All Other Permitted Uses 10,000 square feet"),
    ("RH/HR", "min_lot_width_ft", 75, "All Other Permitted Uses 75 feet"),
    ("RH/HR", "setback_front_ft", 15, "25"),
    ("RH/HR", "setback_street_side_ft", 15, "same as the front yard setback"),
    ("RH/HR", "setback_garage_entrance_ft", 20, "garage door must be 20 feet"),
    ("RH/HR", "setback_front_max_ft", 20, "Front Setback 20 feet"),
    ("RH/HR", "setback_side_ft", 12, "12 feet"),
    ("RH/HR", "setback_rear_ft", 12, "12 feet"),
    ("RH/HR", "parking_street_setback_ft", 10, "Vehicle Circulation Areas 10 feet"),
    ("RH/HR", "parking_lot_line_buffer_ft", 10, "Vehicle Circulation Areas 10 feet"),
    ("RH/HR", "max_height_ft", 64, "Maximum Height 64 feet"),
    ("RH/HR", "max_coverage_pct", 45, "All Uses 45%"),
    ("RH/HR", "max_density_du_per_acre", 30, "Maximum: 30 units per acre"),
    ("RH/HR", "min_density_du_per_acre", 26, "Minimum: 26 units per acre"),
    ("MUC", "setback_front_ft", 0, "Front None"),
    ("MUC", "setback_front_max_ft", 20, "Residential Uses Front/Corner 20 feet"),
    ("MUC", "setback_street_side_ft", 0, "Corner None"),
    ("MUC", "setback_side_ft", 20, "Setbacks are 20 feet where the site abuts"),
    ("MUC", "setback_rear_ft", 20, "Setbacks are 20 feet where the site abuts"),
    ("MUC", "min_building_height_ft", 20, "All uses 20 feet"),
    ("MUC", "max_height_ft", 70, "All uses 70 feet"),
    ("MUC", "max_coverage_pct", 90, "All uses 90%"),
    ("MUC", "max_density_du_per_acre", 50, "25-50 units per acre"),
    ("MUC", "min_density_du_per_acre", 25, "25-50 units per acre"),
]


@pytest.mark.parametrize(("zone", "field", "value", "words"), NUMBERS)
def test_each_stated_number_matches_its_cited_line(
    tualatin: Layer, zone: str, field: str, value: float, words: str
) -> None:
    held = _field(tualatin, zone, field)
    assert held.value == value, (zone, field)
    assert words in _text(held.prov.quote), (zone, field, words)


# (zone, field, value, words) for the Townhouse rows, reached on unit_lots
TOWNHOUSE_ROWS = [
    ("RMH", "min_lot_sqft", 1400, "Townhouse (or Rowhouse) 1,400 square feet"),
    ("RMH", "min_lot_width_ft", 14, "Townhouse (or Rowhouse) 14 feet"),
    ("RMH", "setback_front_ft", 10, "Townhouse (or Rowhouse) 0"),
    ("RMH", "setback_street_side_ft", 10, "Townhouse (or Rowhouse) 0"),
    ("RMH", "max_coverage_pct", 90, "Townhouse (or Rowhouse) 90%"),
    ("RH", "min_lot_sqft", 1400, "Townhouse, or Rowhouse 1,400 square feet"),
    ("RH", "min_lot_width_ft", 14, "Townhouses (or Rowhouses) 14 feet"),
    ("RH", "setback_front_ft", 10, "Townhouse (or Rowhouses) 0"),
    ("RH", "setback_street_side_ft", 10, "Townhouse (or Rowhouses) 0"),
    ("RH", "max_coverage_pct", 90, "Townhouse (or Rowhouse) 90%"),
    ("RH/HR", "min_lot_width_ft", 14, "Townhouses (Rowhouses) 14 feet"),
]


@pytest.mark.parametrize(("zone", "field", "value", "words"), TOWNHOUSE_ROWS)
def test_townhouse_rows_apply_only_on_unit_lots(
    tualatin: Layer, zone: str, field: str, value: float, words: str
) -> None:
    townhouse = _variant(tualatin, zone, field)
    assert townhouse.value == value, (zone, field)
    assert words in _text(townhouse.prov.quote), (zone, field, words)


def test_rh_hr_townhouse_lot_size_is_the_all_other_row(tualatin: Layer) -> None:
    """Table 44-3 prints no Townhouse lot size; Steph ruled 2026-10-02 that
    townhouses take the 'All Other Permitted Uses' row. One number, no variant."""
    lot = _field(tualatin, "RH/HR", "min_lot_sqft")
    assert lot.value == 10000
    assert lot.variants == ()
    table = _text("or/clackamas/tualatin/44.rh-hr.txt#L128-L145")
    assert "Townhouse" not in table.split("MINIMUM LOT SIZE")[1].split("MINIMUM")[0]


def test_rh_hr_minimum_height_row_is_scoped_to_multifamily() -> None:
    """The 45 ft minimum is not applied to the pod: the table scopes it to
    Multi-Family and Condominium Developments."""
    text = _text("or/clackamas/tualatin/44.rh-hr.txt#L205-L211")
    assert "Multi-Family" in text and "45 feet" in text


def test_muc_has_no_lot_size_and_holds_the_abutting_side_rear(tualatin: Layer) -> None:
    lot = _field(tualatin, "MUC", "min_lot_sqft")
    assert lot.exempt is True
    assert "All Uses None" in _text(lot.prov.quote)
    for field in ("min_lot_width_ft", "parking_street_setback_ft"):
        assert field not in tualatin.zones["MUC"].values, field
    # 0-20 ft, and 20 where the site abuts a residential district: held at 20
    # for every lot because this layer measures no neighbour zoning.
    assert _field(tualatin, "MUC", "setback_side_ft").value == 20
    assert _field(tualatin, "MUC", "setback_rear_ft").value == 20


def test_rh_and_rh_hr_density_floors_are_lower_than_the_ceilings(
    tualatin: Layer,
) -> None:
    for zone in ("RMH", "RH", "RH/HR", "MUC"):
        high = _field(tualatin, zone, "max_density_du_per_acre").value
        low = _field(tualatin, zone, "min_density_du_per_acre").value
        assert low < high, zone
