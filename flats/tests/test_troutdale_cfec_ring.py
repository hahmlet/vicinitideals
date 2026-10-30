"""Troutdale's CFEC parking waiver reaches a quarter mile past the Town
Center (FOLLOWUPS 109 chunk 5, 2026-10-29).

TDC 9.035: "no off-street parking is required for developments on a lot or
parcel within the Town Center Overlay District, including lands within
one-quarter (1/4) mile from the district boundary line." Until this chunk
only the Town Center itself was drawn, so a lot in the quarter mile kept
Table 1's stalls. The ring is now drawn -- the city's Town Center layer
grown 1,320 ft, straight line, because the code measures from the boundary
line and names no walking route -- and answers
``troutdale_cfec_parking_area`` from each lot's share inside it.

What is guarded: the tracing is the Town Center grown a quarter mile and
carries its drawn provenance; it is asked of every zone that admits the
pod; a lot in the ring and outside the Town Center is inside, one a mile
off is not; the waiver turns on the ring and nothing else, and no lot size
leaves a banded variant tying with it.
"""

from __future__ import annotations

import itertools
import json

import pytest
import shapely

from flats.encode.load import load_trusted
from flats.geom.drawn import load_area
from flats.ingest.quadfit import observed_facts
from flats.rules.conditions import DRAWN_CONDITIONS
from flats.rules.loader import AREAS_ROOT, load_rules
from flats.rules.resolver import RuleSet
from flats.tests.test_quadfit_bridge import row as plain_row

pytestmark = pytest.mark.unit

TROUTDALE = "or/multnomah/troutdale"
RING = "or/multnomah/troutdale/cfec-parking-area.geojson"
TOWN_CENTER = "or/multnomah/troutdale/town-center.geojson"
CFEC = "troutdale_cfec_parking_area"
TC = "troutdale_town_center"
QUARTER_MILE_FT = 1320
ZONES = ("LDR-1", "LDR-2", "MDR", "HDR", "MU-1", "MU-2")


@pytest.fixture(scope="module")
def layers():
    return load_trusted(strict=False).rules.layers


def test_the_ring_is_the_town_center_grown_a_quarter_mile() -> None:
    ring, tc = load_area(RING), load_area(TOWN_CENTER)
    assert ring.contains(tc.buffer(-1))
    # Every point of the ring is within a quarter mile of the Town Center ...
    assert tc.buffer(QUARTER_MILE_FT + 1).contains(ring)
    # ... and every point within a quarter mile is in the ring.
    assert ring.buffer(1).contains(tc.buffer(QUARTER_MILE_FT - 1))


def test_the_ring_carries_its_drawn_provenance() -> None:
    source = json.loads((AREAS_ROOT / RING).read_text(encoding="utf-8"))["source"]
    assert source["drawn"] is True
    assert source["quote"] == "or/multnomah/troutdale/9/9.035.txt#L1,L4"
    assert "one-quarter (1/4) mile from the district boundary line" in source["says"]


def test_the_ring_is_asked_of_every_zone_that_admits_the_pod() -> None:
    assert CFEC in DRAWN_CONDITIONS
    (area,) = [a for a in load_rules()[TROUTDALE].drawn_areas.values() if a.condition == CFEC]
    assert area.file == RING
    assert set(ZONES) <= set(area.zones)


def _facts(layers, lot, zone="MDR") -> dict:
    return observed_facts(
        plain_row(jurisdiction="troutdale", zone=zone, lot_wkb=shapely.to_wkb(lot)), layers
    )


def test_a_lot_in_the_quarter_mile_is_in_the_ring_and_not_the_town_center(layers) -> None:
    tc = load_area(TOWN_CENTER)
    band = load_area(RING).difference(tc.buffer(200)).buffer(-200)
    lot = band.representative_point().buffer(30)
    got = _facts(layers, lot)
    assert got[CFEC] is True
    assert got[TC] is False


def test_a_lot_a_mile_off_is_outside_the_ring(layers) -> None:
    tc = load_area(TOWN_CENTER)
    minx, miny, _, _ = tc.bounds
    lot = shapely.geometry.box(minx - 5300, miny - 5300, minx - 5200, miny - 5200)
    assert _facts(layers, lot)[CFEC] is False


@pytest.mark.parametrize("zone", ZONES)
@pytest.mark.parametrize("lot_sqft", [2500.0, 4000.0, 6000.0, 8000.0, 20000.0])
def test_the_waiver_turns_on_the_ring_and_never_ties(zone, lot_sqft) -> None:
    rules = RuleSet(load_rules())
    for extra in itertools.chain.from_iterable(
        itertools.combinations((TC, "unit_lots"), n) for n in range(3)
    ):
        out = rules.resolve(TROUTDALE, zone, extra, {"lot_sqft": lot_sqft})
        inside = rules.resolve(TROUTDALE, zone, (CFEC, *extra), {"lot_sqft": lot_sqft})
        assert not inside.ambiguous, (zone, extra, inside.ambiguous)
        assert "parking_min_per_unit" in inside.exempted, (zone, extra)
        if TC not in extra:
            # Off the ring the Town Center alone never waives: the ring is
            # the waiver's whole ground, and the Town Center lies inside it.
            assert "parking_min_per_unit" not in out.exempted, (zone, extra)
