"""Portland plan districts, the map-sheet figures (FOLLOWUPS 109 pd2c, 2026-11-04).

Gateway (33.526.220.C) and East Corridor (33.521.220.C) set a minimum floor
area ratio for new development "shown on Map 526-3" and "shown on Map 521-3",
and print it only on the map: (.25:1) under the 4:1 maximum across Gateway,
(.5:1) and (1:1) in six East Corridor areas. Batches A and B held those areas
whole in ``pdx_plan_district_unmeasured`` because no stored line carried the
figures. With Steph's go (2026-11-04) the adopted 11/1/26 sheets were fetched
and read, and the figures are now drawn variants of ``min_far`` behind three
drawn facts copied from the City's own layer (BPS Zoning Code Layers 50):

* a lot nine tenths inside takes the figure, and the pod's 4,032 sq ft of
  floor is measured against it -- a miss is YELLOW with the FAR-MIN flag,
  never a bind (SOFT_FLOOR_CHECKS, 2026-10-29);
* a lot the line cuts is unanswered, and YELLOW wherever the figure would
  decide its colour;
* the areas left the hold, except the lots a traced street rule still holds.

Glendoveer (33.530.020) was checked the same day: Map 530-1 draws the plan
district boundary and nothing inside it, so ``pdx_glendoveer_lr75`` stays the
whole outline.
"""

from __future__ import annotations

import dataclasses
import json

import pytest
from shapely.geometry import box, shape
from shapely.ops import unary_union

from flats.geom.drawn import load_area
from flats.rules import loader
from flats.rules.conditions import CONDITIONS, DRAWN_CONDITIONS
from flats.rules.resolver import RuleSet
from flats.score import flags as flag_plan
from flats.score.flags import fact_code
from flats.tests.test_portland_plan_districts_2 import (
    FILES,
    GLENDOVEER,
    HOLD,
    MIN_FAR,
    _clear,
    _facts,
    _screen,
)

pytestmark = pytest.mark.unit

PORTLAND = "or/multnomah/portland"
GATEWAY, EC_HALF, EC_ONE = MIN_FAR
AREA = {
    GATEWAY: "or/multnomah/portland/gateway-min-far.geojson",
    EC_HALF: "or/multnomah/portland/east-corridor-min-far-half.geojson",
    EC_ONE: "or/multnomah/portland/east-corridor-min-far-one.geojson",
}
FIGURE = {GATEWAY: 0.25, EC_HALF: 0.5, EC_ONE: 1.0}
FEATURES = {GATEWAY: 12, EC_HALF: 5, EC_ONE: 1}
#: The zones of every lot inside the three areas on run 113 that can hold the pod.
ZONES = {"R7", "R5", "R2.5", "RM1", "RM2", "RM3", "RX", "CM1", "CM2", "CM3", "CX", "EX", "CI2", "IR"}
#: A lot the pod's floor clears at each figure, and one too big for it, in a
#: zone each area's greens stood in.
SMALL = {GATEWAY: ("RM2", 100.0, 160.0), EC_HALF: ("RM2", 80.0, 100.0), EC_ONE: ("RM3", 60.0, 67.0)}
LARGE = {GATEWAY: ("RM2", 100.0, 200.0), EC_HALF: ("RM2", 100.0, 200.0), EC_ONE: ("RM3", 100.0, 200.0)}
FLOOR = 56 * 36 * 2


@pytest.fixture(scope="module")
def portland():
    return loader.load_rules()[PORTLAND]


@pytest.fixture(scope="module")
def corpus():
    from flats.encode.load import load_trusted

    return load_trusted(strict=False).rules


def _data(fact: str) -> dict:
    return json.loads((loader.AREAS_ROOT / AREA[fact]).read_text(encoding="utf-8"))


def _unanswered(lot, fact: str):
    """The lot the map's line cuts: the bridge leaves the fact out, not False."""
    return dataclasses.replace(lot, observed={k: v for k, v in lot.observed.items() if k != fact})


def _far(screened):
    return [c for c in screened.checks if c.check == "min_far"]


# --- the encoding -----------------------------------------------------------------


@pytest.mark.parametrize("fact", MIN_FAR)
def test_the_facts_are_drawn_site_facts_never_assumed(fact: str) -> None:
    assert CONDITIONS[fact].kind == "site_fact"
    assert CONDITIONS[fact].assume is None
    assert fact in DRAWN_CONDITIONS
    assert fact_code(fact) in flag_plan.registry()


@pytest.mark.parametrize("fact", MIN_FAR)
def test_each_area_is_the_citys_layer_with_the_sheet_named(portland, fact: str) -> None:
    (area,) = [a for a in portland.drawn_areas.values() if a.condition == fact]
    assert area.file == AREA[fact]
    # CI1 too: RICAP 11 builds a CI1 home to RM1's standards, min_far included.
    assert set(area.zones) == ZONES | {"CI1"}
    data = _data(fact)
    assert data["crs"]["properties"]["name"].endswith("EPSG::2913")
    assert len(data["features"]) == FEATURES[fact]
    src = data["source"]
    assert {"map", "quote", "says", "sheet", "method", "read_by", "read_on"} <= set(src)
    assert "MapServer/50" in src["map"] and "sha256" in src["sheet"]
    assert src["sheet"].startswith("https://www.portland.gov/sites/default/files/code/52")
    assert src["read_on"] == "2026-11-04"


def test_every_zone_carrying_the_figures_is_answered_by_all_three_areas(portland) -> None:
    carrying = {name for name, z in portland.zones.items() if "min_far" in z.values}
    assert carrying == ZONES
    for fact in MIN_FAR:
        (area,) = [a for a in portland.drawn_areas.values() if a.condition == fact]
        # A zone whose lever fact is never asked would be YELLOW everywhere.
        assert carrying <= set(area.zones), fact


@pytest.mark.parametrize("zone", sorted(ZONES))
def test_the_figures_are_drawn_read_and_unquoted(portland, zone: str) -> None:
    floor = portland.zones[zone].values["min_far"]
    assert floor.exempt
    assert floor.prov.quote in (
        "or/multnomah/portland/33.526.txt#L196-L197",
        "or/multnomah/portland/33.521.txt#L127-L128",
    )
    by_fact = {var.when: var for var in floor.variants}
    assert set(by_fact) == {(f,) for f in MIN_FAR}
    for fact in MIN_FAR:
        var = by_fact[(fact,)]
        assert float(var.value) == FIGURE[fact]
        assert var.prov.drawn and var.prov.quote is None
        assert var.prov.read_by and str(var.prov.read_on) == "2026-11-04"
        assert var.prov.url.endswith(("526-gateway-pd_2.pdf", "521-east-corridor-pd_1.pdf"))


def test_the_quoted_sentences_send_the_figure_to_the_map() -> None:
    from flats.provenance.store import ProvenanceStore

    store = ProvenanceStore()
    gateway = " ".join(store.quote("or/multnomah/portland/33.526.txt#L196-L197").split())
    corridor = " ".join(store.quote("or/multnomah/portland/33.521.txt#L127-L128").split())
    assert "minimum floor area ratio (FAR) for new development is shown on Map 526-3" in gateway
    assert "for all new development are shown on Map 521-3" in corridor


@pytest.mark.parametrize("fact", MIN_FAR)
def test_the_figure_resolves_only_inside_its_area(fact: str) -> None:
    rs = RuleSet(loader.load_rules())
    inside = rs.resolve(PORTLAND, "RM2", (fact,))
    outside = rs.resolve(PORTLAND, "RM2", ())
    assert float(inside.values["min_far"].value) == FIGURE[fact]
    assert "min_far" not in outside.values
    assert fact in outside.levers


# --- the map, through the bridge ----------------------------------------------------


@pytest.mark.parametrize("fact", MIN_FAR)
def test_a_lot_inside_reads_true_and_is_out_of_the_hold(fact: str) -> None:
    free = load_area(AREA[fact]).difference(load_area(FILES[HOLD]).buffer(10))
    piece = max(getattr(free, "geoms", [free]), key=lambda g: g.area)
    got = _facts("RM2", piece.representative_point().buffer(5))
    assert got[fact] is True
    assert got[HOLD] is False
    assert all(got[other] is False for other in MIN_FAR if other != fact)


@pytest.mark.parametrize("fact", MIN_FAR)
def test_a_lot_far_away_reads_false_and_one_the_line_cuts_is_unanswered(fact: str) -> None:
    area = load_area(AREA[fact])
    minx, miny, _, _ = area.bounds
    assert _facts("RM2", box(minx - 3000, miny - 3000, minx - 2900, miny - 2900))[fact] is False
    biggest = max(getattr(area, "geoms", [area]), key=lambda g: g.area)
    # Straddle the area's westmost point: half in, half out.
    west = min(biggest.exterior.coords, key=lambda c: c[0])
    cut = box(west[0] - 20, west[1] - 20, west[0] + 20, west[1] + 20)
    share = cut.intersection(area).area / cut.area
    assert 0.1 < share < 0.9
    assert fact not in _facts("RM2", cut)


def test_the_hold_kept_the_lots_a_street_rule_still_holds() -> None:
    hold = load_area(FILES[HOLD])
    for fact in MIN_FAR:
        area = load_area(AREA[fact])
        kept = area.intersection(hold).area / area.area
        assert 0 < kept < 0.9, fact
    src = json.loads((loader.AREAS_ROOT / FILES[HOLD]).read_text(encoding="utf-8"))["source"]
    assert "pd2c" in src["traced_by"] and "pd2c" in src["method"]
    assert "until pd2c" in src["inputs"]["far_b"]


# --- through the screen -------------------------------------------------------------


@pytest.mark.parametrize("fact", MIN_FAR)
def test_a_small_lot_meets_the_figure(corpus, fact: str) -> None:
    zone, w, d = SMALL[fact]
    assert FLOOR / (w * d) >= FIGURE[fact]
    lot = _clear(corpus, zone, w=w, d=d)
    s = _screen(corpus, dataclasses.replace(lot, observed={**lot.observed, fact: True}))
    (check,) = _far(s)
    assert check.verdict.name == "passes" and check.threshold == FIGURE[fact]
    assert "FAR-MIN" not in {f.code for f in s.flags}
    if fact != EC_ONE:
        # 4,032 sq ft of lot is too small for the pod and its court, so the
        # 1 to 1 area opens nothing; the others open a lot this size.
        assert s.colour is flag_plan.Colour.green


@pytest.mark.parametrize("fact", MIN_FAR)
def test_a_large_lot_misses_the_figure_and_is_yellow_never_red(corpus, fact: str) -> None:
    zone, w, d = LARGE[fact]
    lot = _clear(corpus, zone, w=w, d=d)
    assert _screen(corpus, lot).colour is flag_plan.Colour.green
    s = _screen(corpus, dataclasses.replace(lot, observed={**lot.observed, fact: True}))
    (check,) = _far(s)
    assert check.verdict.name == "fails"
    assert "FAR-MIN" in {f.code for f in s.flags}
    assert s.colour is flag_plan.Colour.yellow


@pytest.mark.parametrize("fact", MIN_FAR)
def test_a_large_lot_the_line_cuts_stays_yellow(corpus, fact: str) -> None:
    zone, w, d = LARGE[fact]
    s = _screen(corpus, _unanswered(_clear(corpus, zone, w=w, d=d), fact))
    assert s.colour is flag_plan.Colour.yellow
    assert fact_code(fact) in {f.code for f in s.flags}


def test_outside_every_area_there_is_no_minimum(corpus) -> None:
    zone, w, d = LARGE[GATEWAY]
    s = _screen(corpus, _clear(corpus, zone, w=w, d=d))
    assert not _far(s) and s.colour is flag_plan.Colour.green


# --- Glendoveer -------------------------------------------------------------------


def test_glendoveer_stays_the_whole_outline_because_map_530_1_draws_nothing_inside(portland) -> None:
    # Map 530-1 (530-glendoveer-pd_0.pdf p. 3, rev. July 8, 2016, fetched
    # 2026-11-04) has one legend entry, "Plan District Boundary": it does not
    # mark the land the County zoned LR7.5, so there is nothing to trace and
    # every R7 lot inside keeps the deeper setbacks.
    (area,) = [a for a in portland.drawn_areas.values() if a.condition == GLENDOVEER]
    assert set(area.zones) == {"R7"}
    outline = json.loads((loader.AREAS_ROOT / f"{PORTLAND}/plan-districts.geojson").read_text(encoding="utf-8"))
    gl = unary_union([shape(f["geometry"]) for f in outline["features"] if f["properties"]["PLDIST"] == "GL"])
    traced = load_area(FILES[GLENDOVEER])
    assert abs(traced.symmetric_difference(gl).area) < 1e-6 * gl.area
