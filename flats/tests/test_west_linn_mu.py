"""West Linn MU, the Willamette Neighborhood Mixed Use Transitional Zone.

25 lots. CDC 59.030 lists a quadplex among the uses permitted outright and
59.070(A) holds the dimensional table. The zone was a ``to_read`` ruling until
2026-10-08. These tests pin the use answer, the numbers and the quotes behind
them, so a later edit that moves a number has to move its citation too.
"""

from __future__ import annotations

import pytest

from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer

pytestmark = pytest.mark.unit

WEST_LINN = "or/clackamas/west-linn"
DOC = "or/clackamas/west-linn/59.mu.txt"

#: field -> (value, a phrase the quoted lines must contain)
EXPECTED = {
    "setback_front_ft": (12, "Front yard"),
    "setback_front_max_ft": (20, "Maximum"),
    "setback_side_ft": (7.5, "Interior side yard"),
    "setback_street_side_ft": (12, "Street side yard"),
    "setback_rear_ft": (20, "Rear yard"),
    "min_lot_sqft": (4500, "Minimum lot size"),
    "min_lot_width_ft": (35, "Minimum lot width at front lot line"),
    "min_average_lot_width_ft": (50, "Average minimum lot width"),
    "min_lot_depth_ft": (90, "Average minimum lot depth"),
    "max_height_ft": (35, "35 ft or 2 stories"),
    "max_height_stories": (2, "35 ft or 2 stories"),
    "max_far": (0.40, "Maximum floor area ratio"),
}


@pytest.fixture(scope="module")
def mu():
    layer: Layer = load_rules()[WEST_LINN]
    return layer.zones["MU"]


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


def test_mu_is_a_zone_block_and_no_longer_a_ruling() -> None:
    layer = load_rules()[WEST_LINN]
    assert "MU" in layer.zones
    assert "MU" not in (layer.zone_rulings or {})


def test_a_quadplex_is_permitted_outright_in_mu(mu, store: ProvenanceStore) -> None:
    held = mu.values["quadplex_allowed"]
    assert held.value is True
    assert not held.variants  # by right: no variant, no conditional path
    text = store.quote(held.prov.quote)
    assert "Quadplex residential units" in text
    assert "all uses require design review" in text


@pytest.mark.parametrize("field", sorted(EXPECTED))
def test_each_mu_number_matches_the_line_it_cites(mu, store: ProvenanceStore, field: str) -> None:
    value, phrase = EXPECTED[field]
    held = mu.values[field]
    assert held.value == value, field
    assert held.prov.quote.startswith(DOC), field
    assert phrase in store.quote(held.prov.quote), field


def test_mu_parking_stays_off_the_street_side(mu, store: ProvenanceStore) -> None:
    held = mu.values["parking_front_prohibited"]
    assert held.value is True
    assert "between the building and a public or private street" in store.quote(
        held.prov.quote
    )


def test_mu_floor_area_is_measured_on_net_land(mu) -> None:
    measured = mu.values["max_far"].measured_on
    assert measured is not None
    assert measured == "net_developable_area"


def test_mu_is_all_draft(mu) -> None:
    for name, held in mu.values.items():
        assert str(getattr(held, "confidence", "draft")).endswith("draft"), name
