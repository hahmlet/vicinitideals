"""Clackamas unincorporated SCMU and PMU1-3, red by ruling.

All four were ``to_read`` rulings until 2026-10-08. Table 510-1 permits a
quadplex outright in both districts, but development in a commercial district
goes through Type II design review (ZDO 1102.01(A)) and a PMU site also needs a
master plan (1102.03(B)), so Steph's by-right rule (2026-10-08) makes them RED.
These tests pin the use answer (false, no variants), the numbers kept for a
reversal, and the quote behind each, so a later edit that moves a number has to
move its citation too.
"""

from __future__ import annotations

import pytest

from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer

pytestmark = pytest.mark.unit

LAYER = "or/clackamas/_unincorporated"
RED_ZONES = ["SCMU", "PMU1", "PMU2", "PMU3"]

#: zone -> field -> (value, a phrase the quoted lines must contain)
EXPECTED = {
    "SCMU": {
        "min_lot_sqft": (7000, "quadplex"),
        "setback_side_ft": (5, "Minimum Side and Rear Setbacks"),
        "setback_rear_ft": (5, "Minimum Side and Rear Setbacks"),
        "min_building_height_ft": (20, "Minimum Building Height"),
    },
    "PMU1": {
        "min_lot_sqft": (7000, "quadplex"),
        "setback_front_ft": (0, "Minimum Front Setback"),
        "setback_side_ft": (15, "abuts a residential zoning district"),
        "setback_rear_ft": (15, "abuts a residential zoning district"),
    },
    "PMU2": {
        "min_lot_sqft": (2, "PMU2: 2 acres"),
    },
    "PMU3": {
        "min_lot_sqft": (3, "PMU3: 3 acres"),
    },
}


@pytest.fixture(scope="module")
def layer() -> Layer:
    return load_rules()[LAYER]


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


@pytest.mark.parametrize("zone", RED_ZONES)
def test_zone_is_a_block_and_no_longer_a_to_read_ruling(layer: Layer, zone: str) -> None:
    assert zone in layer.zones
    assert zone not in (layer.zone_rulings or {})


@pytest.mark.parametrize("zone", RED_ZONES)
def test_a_quadplex_is_refused_with_no_way_back_in(layer: Layer, store: ProvenanceStore, zone: str) -> None:
    held = layer.zones[zone].values["quadplex_allowed"]
    assert held.value is False
    assert not held.variants  # by right only: no conditional path to green
    text = store.quote(held.prov.quote)
    assert "Quadplexes" in text  # the Table 510-1 row the ruling rests on
    assert zone[:3] in text  # and the column head: SCMU or PMU


@pytest.mark.parametrize("zone", RED_ZONES)
def test_the_notes_carry_the_ruling(layer: Layer, zone: str) -> None:
    notes = layer.zones[zone].notes or ""
    assert "RED BY RULING (Steph, 2026-10-08)" in notes


@pytest.mark.parametrize(
    "zone,field",
    [(z, f) for z, fields in EXPECTED.items() for f in fields],
)
def test_each_kept_number_matches_the_line_it_cites(
    layer: Layer, store: ProvenanceStore, zone: str, field: str
) -> None:
    value, phrase = EXPECTED[zone][field]
    held = layer.zones[zone].values[field]
    # PMU2 and PMU3 state their minimum in acres, the unit the table prints.
    stated = held.acres if held.acres is not None else held.value
    assert stated == value, (zone, field)
    assert phrase in store.quote(held.prov.quote), (zone, field)


def test_scmu_front_setback_is_left_unfilled(layer: Layer) -> None:
    """1005.09 keys the front line to street type on a map; no lot carries that."""
    assert "setback_front_ft" not in layer.zones["SCMU"].values


def test_pmu_sites_share_the_one_table_510_2_column(layer: Layer) -> None:
    """PMU2 and PMU3 inherit PMU1's setbacks (the table has a single PMU column)."""
    for zone in ("PMU2", "PMU3"):
        assert layer.zones[zone].like.zone == "PMU1"


@pytest.mark.parametrize("zone", RED_ZONES)
def test_everything_is_draft(layer: Layer, zone: str) -> None:
    for name, held in layer.zones[zone].values.items():
        assert str(getattr(held, "confidence", "draft")).endswith("draft"), (zone, name)
