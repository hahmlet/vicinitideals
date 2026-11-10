"""Portland plan districts, part 2 batch B (FOLLOWUPS 109, 2026-11-04).

The last of Portland's plan districts with lots the screen opens: Central
City (33.510), Columbia South Shore (33.515), Gateway (33.526), Hayden
Island (33.532), Marquam Hill (33.555), Northwest (33.562), Powell
Boulevard (33.567), Sandy Boulevard (33.575) and South Auditorium
(33.580). Portland International Airport (33.565) was read and left out:
its one site standard binds IG2 only.

Nothing new is measured. Every rule that reaches the pod rides batch A's
one hold, ``pdx_plan_district_unmeasured``, on the lots it reaches:

* Gateway: lots with two or more street faces (no vehicle area between the
  building and any street, 340.C.1), lots near a MAX line (C.2), and the
  Map 526-3 minimum-FAR areas whole (the .25 to 1 is printed on the map
  only; read off the sheet and cut out in pd2c, test_portland_plan_districts_4).
* Northwest: CM2 lots and CM3 lots near a Map 562-7 main street or the
  streetcar (1.5 to 1 minimum FAR), CM3 lots in the residential-limited
  area of Map 562-2, main-street lots with two street faces or over 10,000
  sq ft, and the Map 562-4 0 ft height area.
* Sandy: lots on NE Sandy Blvd (walls parallel to Sandy).
* Northwest Map 562-2 is not a hold: "More than 20 percent [Residential] is
  prohibited" on CM3 there, so its own drawn fact, pdx_nw_residential_limited,
  turns quadplex_allowed off -- RED inside, YELLOW where the line cuts.
* Hayden Island: commercial lots. Powell, South Auditorium, Columbia South
  Shore, Central City and Marquam Hill: every lot.

What is guarded: the hold now answers RM4, RX, CX and EX too; each
district's land is in the tracing and a Northwest or Sandy lot away from
the street rules is not; a held lot in each zone the batch B greens stand
in is YELLOW where the same lot unheld is GREEN; and the hold never lifts a
RED.
"""

from __future__ import annotations

import dataclasses
import json

import pytest
import shapely
from shapely.geometry import box, shape
from shapely.ops import unary_union

from flats.geom.drawn import load_area
from flats.provenance.store import ProvenanceStore
from flats.rules import loader
from flats.rules.conditions import CONDITIONS
from flats.score import flags as flag_plan
from flats.score.flags import fact_code
from flats.tests.test_portland_plan_districts_2 import (
    FILES,
    HOLD,
    HOLD_ZONES,
    _answered,
    _clear,
    _facts,
    _screen,
)
from flats.tests.test_portland_plan_districts_2 import _lot as _plain_lot

pytestmark = pytest.mark.unit

PORTLAND = "or/multnomah/portland"
#: Each batch B district and a zone its green lots stood in on run 113.
DISTRICTS = {
    "GA": "CX",
    "NP": "CM3",
    "SD": "CM3",
    "HI": "CE",
    "PB": "CM2",
    "SS": "CE",
    "CC": "RM2",
    "SA": "CM3",
    "MH": "RM2",
}
#: The zones batch B adds to the hold, and the ones its greens stand in.
NEW_ZONES = {"RM4", "RX", "CX", "EX"}
GREEN_ZONES = ("CX", "RX", "RM4", "RM1", "RM2", "RM3", "CM1", "CM2", "CM3", "CE")


@pytest.fixture(scope="module")
def corpus():
    from flats.encode.load import load_trusted

    return load_trusted(strict=False).rules


def _outline(code: str):
    data = json.loads((loader.AREAS_ROOT / f"{PORTLAND}/plan-districts.geojson").read_text(encoding="utf-8"))
    return unary_union([shape(f["geometry"]) for f in data["features"] if f["properties"]["PLDIST"] == code])


def _source() -> dict:
    return json.loads((loader.AREAS_ROOT / FILES[HOLD]).read_text(encoding="utf-8"))["source"]


def test_the_hold_answers_the_zones_batch_b_greens_stand_in(corpus) -> None:
    assert NEW_ZONES <= HOLD_ZONES
    portland = loader.load_rules()[PORTLAND]
    (area,) = [a for a in portland.drawn_areas.values() if a.condition == HOLD]
    assert NEW_ZONES <= set(area.zones)
    for zone in NEW_ZONES:
        assert portland.zones[zone].values["quadplex_allowed"].qualified_by == HOLD, zone


@pytest.mark.parametrize("code", sorted(DISTRICTS))
def test_each_districts_held_land_reads_true(code: str) -> None:
    held = _outline(code).intersection(load_area(FILES[HOLD]))
    assert held.area > 0, code
    piece = max(getattr(held, "geoms", [held]), key=lambda g: g.area)
    assert _facts(DISTRICTS[code], piece.representative_point().buffer(5))[HOLD] is True


@pytest.mark.parametrize("code", ["NP", "SD"])
def test_land_the_street_rules_do_not_reach_is_left_open(code: str) -> None:
    # Northwest CM3 away from the main streets and Sandy away from Sandy
    # Blvd: inside the outline, outside the tracing, so the lot is answered.
    free = _outline(code).difference(load_area(FILES[HOLD]).buffer(10))
    piece = max(getattr(free, "geoms", [free]), key=lambda g: g.area)
    assert _facts(DISTRICTS[code], piece.representative_point().buffer(5))[HOLD] is False


def test_a_lot_far_from_every_district_reads_false() -> None:
    minx, miny, _, _ = load_area(FILES[HOLD]).bounds
    assert _facts("CX", box(minx - 3000, miny - 3000, minx - 2900, miny - 2900))[HOLD] is False


@pytest.mark.parametrize("zone", GREEN_ZONES)
def test_a_held_lot_is_yellow_where_the_same_lot_is_green(corpus, zone: str) -> None:
    lot = _clear(corpus, zone)
    clear = _screen(corpus, lot)
    held = _screen(corpus, _answered(lot, **{HOLD: True}))
    assert clear.colour is flag_plan.Colour.green, zone
    assert held.colour is flag_plan.Colour.yellow, zone
    assert fact_code(HOLD) in {f.code for f in held.flags}


@pytest.mark.parametrize("zone", ["CX", "CM3"])
def test_the_hold_never_lifts_a_red(corpus, zone: str) -> None:
    lot = _answered(_plain_lot(corpus, zone, w=20.0, d=60.0), **{HOLD: True})
    assert _screen(corpus, lot).colour is flag_plan.Colour.red


def test_the_tracing_says_what_batch_b_added() -> None:
    src = _source()
    assert "batch B" in src["traced_by"]
    assert "Map 526-3" in src["inputs"]["far_b"] and "MINFAR" in src["inputs"]["far_b"]
    assert "Map 562-7" in src["inputs"]["streets_b"]
    for name in ("Gateway (33.526)", "Northwest (33.562)", "Central City (33.510)", "Sandy Boulevard (33.575)"):
        assert name in src["map"], name
    # Held whole in batch B; read off the sheet and cut out in pd2c (2026-11-04).
    assert "GA Map 526-3 .25 and EC Map 521-3 .5:1 and 1:1 minimum-FAR polygons" in src["method"]


def test_the_quotes_say_what_the_rules_say() -> None:
    store = ProvenanceStore()
    q = store.quote
    nw_far = q("or/multnomah/portland/33.562.txt#L180-L186")
    assert "1.5 to 1" in nw_far and "Map 562-7" in nw_far
    assert "20 percent" in q("or/multnomah/portland/33.562.txt#L62-L63")
    nw_e = q("or/multnomah/portland/33.562.txt#L310-L313")
    assert "10,000 square feet" in nw_e
    ga = q("or/multnomah/portland/33.526.txt#L714-L726")
    assert "between a primary structure and any street" in ga and "light rail alignment" in ga
    assert "Map 526-3" in q("or/multnomah/portland/33.526.txt#L173-L180")
    assert "Parallel to Sandy Boulevard" in q("or/multnomah/portland/33.575.txt#L62-L69")
    pb = q("or/multnomah/portland/33.567.txt#L23-L38")
    assert "minimum of 8 feet high" in pb
    assert "15 foot deep area" in q("or/multnomah/portland/33.580.txt#L47-L58")
    cc = q("or/multnomah/portland/33.510.txt#L678-L684")
    assert "the minimum FAR is 1 to 1" in cc
    hi = q("or/multnomah/portland/33.532.txt#L182-L189")
    assert "maximum building height is 25 feet" in hi
    assert "Map 515-3" in q("or/multnomah/portland/33.515.txt#L472-L476")


def test_the_flag_names_the_batch_b_rules() -> None:
    desc = flag_plan.registry().types[fact_code(HOLD)].description
    for word in ("Gateway", "Northwest", "Sandy Boulevard", "Powell Boulevard", "Hayden Island"):
        assert word in desc, word
    assert "Gateway" in CONDITIONS[HOLD].describe


def test_quadplex_cite_names_every_batch_b_section() -> None:
    import yaml

    raw = yaml.safe_load((loader.CONFIG_ROOT / f"{PORTLAND}.yaml").read_text(encoding="utf-8"))
    for zone in sorted(HOLD_ZONES):
        cite = raw["zones"][zone]["quadplex_allowed"]["qualified_by"]["cite"]
        for sec in ("33.510.200.C.3", "33.526.340.C", "33.562.220.B", "33.567.040", "33.575.110", "33.580.110"):
            assert sec in cite, (zone, sec)


def test_shapely_reads_the_tracing_as_valid() -> None:
    assert shapely.is_valid(load_area(FILES[HOLD]))


# --- Northwest Map 562-2: a flat prohibition, RED ---------------------------------

NW = "pdx_nw_residential_limited"
NW_FILE = "or/multnomah/portland/northwest-residential-limited.geojson"


def test_the_map_562_2_area_is_the_citys_own_layer_copied_unchanged() -> None:
    data = json.loads((loader.AREAS_ROOT / NW_FILE).read_text(encoding="utf-8"))
    assert "COP_OpenData_ZoningCode/MapServer/157" in data["source"]["map"]
    assert data["source"]["quote"] == "or/multnomah/portland/33.562.txt#L62-L63"
    src = json.loads((loader.AREAS_ROOT / f"{PORTLAND}/limited-use-areas.geojson").read_text(encoding="utf-8"))
    (city,) = [f for f in src["features"] if f["properties"]["PLDIST"] == "NP" and f["properties"]["RESLIMIT"] == "YES"]
    assert shape(city["geometry"]).equals(load_area(NW_FILE))
    assert "More than 20 percent is prohibited" in ProvenanceStore().quote(data["source"]["quote"])


def test_only_cm3_is_asked_and_it_reads_inside_cut_and_outside() -> None:
    area = load_area(NW_FILE)
    inside = area.representative_point().buffer(5)
    assert _facts("CM3", inside)[NW] is True
    assert NW not in _facts("CM2", inside)
    minx, miny, maxx, maxy = area.bounds
    edge = area.exterior.coords[0] if hasattr(area, "exterior") else area.geoms[0].exterior.coords[0]
    cut = shapely.Point(edge).buffer(40)
    assert 0.1 < cut.intersection(area).area / cut.area < 0.9
    assert _facts("CM3", cut).get(NW) is None
    assert _facts("CM3", box(minx - 3000, miny - 3000, minx - 2900, miny - 2900))[NW] is False


def _without(lot, fact: str):
    return dataclasses.replace(lot, observed={k: v for k, v in lot.observed.items() if k != fact})


def test_a_cm3_lot_inside_is_red_cut_yellow_and_outside_green(corpus) -> None:
    lot = _clear(corpus, "CM3")
    assert _screen(corpus, _answered(lot, **{NW: False})).colour is flag_plan.Colour.green
    assert _screen(corpus, _answered(lot, **{NW: True})).colour is flag_plan.Colour.red
    assert _screen(corpus, _without(lot, NW)).colour is flag_plan.Colour.yellow


def test_the_prohibition_does_not_reach_another_zone(corpus) -> None:
    lot = _clear(corpus, "CM2")
    assert _screen(corpus, _answered(lot, **{NW: True})).colour is flag_plan.Colour.green
