"""The Gladstone Town Center, traced from the map Ordinance 1539 adopts
(FOLLOWUPS 109 chunk 5, 2026-10-29).

Ordinance 1539 (2025) adopts the Town Center "as set forth in the attached
Exhibit A", whose Appendix A is a map and the boundary's only statement; the
city publishes no layer. The line is traced from that map and registered to
the city zoning layer, and three rules read it:

* R-5 takes a 10 ft front and street-side setback inside it, against 20
  (GMC 17.12.050);
* C-2 inside it is the Downtown Core Overlay (17.21.010), whose 17.21.060(2)
  puts the building along half of every street frontage at the street line;
* no off-street parking is required inside it or within a quarter mile of
  it, measured in a straight line (17.48.010(1)(a)-(b), (2)).

What is guarded: the tracings carry their drawn provenance and the stored
text says what they cite; a lot clearly inside reads True, one clearly
outside reads False, and one the line cuts is unanswered (the "Town Center
edge unconfirmed" flag), never inside; each rule turns on its fact and
nothing else, and the parking waiver never ties with a lot-size band.
"""

from __future__ import annotations

import itertools
import json

import pytest
import shapely
from shapely.geometry import box

from flats.encode.load import load_trusted
from flats.geom.drawn import load_area
from flats.ingest.quadfit import observed_facts
from flats.provenance.store import STORE_ROOT as DOCS_ROOT
from flats.rules.conditions import CONDITIONS, DRAWN_CONDITIONS
from flats.rules.loader import AREAS_ROOT, load_rules
from flats.rules.resolver import RuleSet
from flats.score.flags import fact_code
from flats.tests.test_quadfit_bridge import row as plain_row

pytestmark = pytest.mark.unit

GLADSTONE = "or/clackamas/gladstone"
TOWN_CENTER = "or/clackamas/gladstone/town-center.geojson"
RING = "or/clackamas/gladstone/parking-exception-area.geojson"
TC = "gladstone_town_center"
PARKING = "gladstone_parking_exception_area"
QUARTER_MILE_FT = 1320


@pytest.fixture(scope="module")
def layers():
    return load_trusted(strict=False).rules.layers


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


def _line(quote_path: str, n: int) -> str:
    lines = (DOCS_ROOT / quote_path).read_text(encoding="utf-8").splitlines()
    return lines[n - 1]


# --- the tracings ---------------------------------------------------------------


def test_the_town_center_is_traced_from_the_ordinance_map() -> None:
    source = json.loads((AREAS_ROOT / TOWN_CENTER).read_text(encoding="utf-8"))["source"]
    assert source["drawn"] is True
    assert source["quote"] == "or/clackamas/gladstone/amended/ord1539.txt#L35-L36,L475-L478"
    assert "media/26186" in source["map"]
    ord1539 = "or/clackamas/gladstone/amended/ord1539.txt"
    assert "Gladstone Town Center" in _line(ord1539, 35)
    assert source["says"] in _line(ord1539, 36)
    assert _line(ord1539, 478).strip() == "LADSTONE TOWN CENTER BOUNDARY"


def test_the_ring_is_the_town_center_grown_a_quarter_mile() -> None:
    ring, tc = load_area(RING), load_area(TOWN_CENTER)
    assert ring.contains(tc.buffer(-1))
    # Drawn with 32 segments to the quarter circle; compared at the same.
    assert tc.buffer(QUARTER_MILE_FT + 1, quad_segs=32).contains(ring)
    assert ring.buffer(1).contains(tc.buffer(QUARTER_MILE_FT - 1, quad_segs=32))
    source = json.loads((AREAS_ROOT / RING).read_text(encoding="utf-8"))["source"]
    assert source["drawn"] is True
    assert "measured using a straight line" in _line("or/clackamas/gladstone/17.48/17.48.010.txt", 13)
    assert source["says"] in _line("or/clackamas/gladstone/17.48/17.48.010.txt", 13)


def test_both_areas_are_declared_with_a_flag_for_the_unanswered_lot() -> None:
    areas = {a.condition: a for a in load_rules()[GLADSTONE].drawn_areas.values()}
    assert (areas[TC].file, set(areas[TC].zones)) == (TOWN_CENTER, {"R5", "C2"})
    assert areas[PARKING].file == RING
    assert {"R7.2", "R5", "R10", "MR", "C2", "C3"} <= set(areas[PARKING].zones)
    assert {TC, PARKING} <= set(DRAWN_CONDITIONS)
    for fact in (TC, PARKING):
        assert CONDITIONS[fact].assume is None
    flags = (AREAS_ROOT.parent / "flags.yaml").read_text(encoding="utf-8")
    assert f"  {fact_code(TC)}:\n    description: \"Town Center edge unconfirmed" in flags


# --- the share -------------------------------------------------------------------


def _facts(layers, lot, zone="R5") -> dict:
    return observed_facts(
        plain_row(jurisdiction="gladstone", zone=zone, lot_wkb=shapely.to_wkb(lot)), layers
    )


def _edge_lot(area):
    """A 60 x 100 ft lot the outline cuts roughly in half."""
    p = area.exterior.coords[0] if hasattr(area, "exterior") else area.geoms[0].exterior.coords[0]
    return box(p[0] - 30, p[1] - 50, p[0] + 30, p[1] + 50)


def test_a_lot_deep_inside_reads_inside_both(layers) -> None:
    tc = load_area(TOWN_CENTER)
    lot = tc.buffer(-60).representative_point().buffer(25)
    got = _facts(layers, lot)
    assert got[TC] is True
    assert got[PARKING] is True


def test_a_lot_in_the_quarter_mile_owes_no_parking_but_is_not_in_the_town_center(layers) -> None:
    tc = load_area(TOWN_CENTER)
    band = load_area(RING).difference(tc.buffer(200)).buffer(-200)
    got = _facts(layers, band.representative_point().buffer(30))
    assert got[PARKING] is True
    assert got[TC] is False


def test_a_lot_a_mile_off_is_outside_both(layers) -> None:
    minx, miny, _, _ = load_area(RING).bounds
    got = _facts(layers, box(minx - 5300, miny - 5300, minx - 5200, miny - 5200))
    assert got[TC] is False
    assert got[PARKING] is False


def test_a_lot_the_traced_line_cuts_is_unanswered(layers) -> None:
    tc = load_area(TOWN_CENTER)
    lot = _edge_lot(tc)
    share = lot.intersection(tc).area / lot.area
    assert 0.1 < share < 0.9
    assert TC not in _facts(layers, lot)


def test_the_town_center_is_not_asked_of_a_zone_it_does_not_change(layers) -> None:
    lot = load_area(TOWN_CENTER).buffer(-60).representative_point().buffer(25)
    got = _facts(layers, lot, zone="R7.2")
    assert TC not in got
    assert got[PARKING] is True


# --- the rules -------------------------------------------------------------------


def test_r5_takes_ten_feet_at_the_street_inside_the_town_center(rules) -> None:
    out = rules.resolve(GLADSTONE, "R5", ())
    inside = rules.resolve(GLADSTONE, "R5", (TC,))
    assert (out.get("setback_front_ft"), out.get("setback_street_side_ft")) == (20, 20)
    assert (inside.get("setback_front_ft"), inside.get("setback_street_side_ft")) == (10, 10)
    # The rear, the sides and the quadplex's 7,000 sq ft are the same inside.
    for name in ("setback_rear_ft", "setback_side_ft", "min_lot_sqft", "quadplex_allowed"):
        assert inside.get(name) == out.get(name), name
    r5 = "or/clackamas/gladstone/17.12/17.12.050.txt"
    assert _line(r5, 27) == "10 ft within Gladstone Town Center"
    assert _line(r5, 42) == "10 ft within Gladstone Town Center"


def test_c2_inside_the_town_center_owes_half_of_every_frontage_at_the_street_line(rules) -> None:
    out = rules.resolve(GLADSTONE, "C2", ())
    inside = rules.resolve(GLADSTONE, "C2", (TC,))
    for name in ("building_frontage_min_pct", "building_frontage_other_pct", "building_frontage_band_ft"):
        assert out.get(name) is None and name in out.exempted, name
    assert inside.get("building_frontage_min_pct") == 50
    assert inside.get("building_frontage_other_pct") == 50
    assert inside.get("building_frontage_band_ft") == 0
    # 17.18's five-foot maximum still bounds the rest of the frontage.
    assert inside.get("setback_front_max_ft") == out.get("setback_front_max_ft") == 5
    assert "at least 50 percent of the lot" in _line("or/clackamas/gladstone/17.21.dco.txt", 83)
    assert "C-2 within the Gladstone Town Center" in _line("or/clackamas/gladstone/17.21.dco.txt", 25)


def test_the_town_center_does_not_lift_the_portland_avenue_hold(rules) -> None:
    """Steph's 2026-10-09 ruling holds a C-2 lot along the avenue open,
    inside the Town Center as outside it."""
    held = load_rules()[GLADSTONE].zones["C2"].values["quadplex_allowed"]
    assert held.qualified_by == "along_portland_avenue"
    assert all(TC not in v.when for v in held.variants)
    assert rules.resolve(GLADSTONE, "C2", (TC,)).get("quadplex_allowed") is True


@pytest.mark.parametrize("zone", ["R7.2", "R5", "R10", "MR", "C2", "C3"])
@pytest.mark.parametrize("lot_sqft", [2000.0, 2500.0, 4000.0, 6000.0, 8000.0, 20000.0])
def test_the_parking_waiver_turns_on_the_ring_and_never_ties(rules, zone, lot_sqft) -> None:
    for extra in itertools.chain.from_iterable(
        itertools.combinations((TC, "unit_lots", "conditional_use"), n) for n in range(4)
    ):
        out = rules.resolve(GLADSTONE, zone, extra, {"lot_sqft": lot_sqft})
        inside = rules.resolve(GLADSTONE, zone, (PARKING, *extra), {"lot_sqft": lot_sqft})
        assert not inside.ambiguous, (zone, extra, inside.ambiguous)
        assert "parking_min_per_unit" in inside.exempted, (zone, extra)
        # The Town Center alone never waives: the ring is the waiver's ground.
        assert "parking_min_per_unit" not in out.exempted, (zone, extra)
