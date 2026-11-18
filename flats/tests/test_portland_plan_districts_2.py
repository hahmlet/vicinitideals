"""Portland plan districts, part 2 batch A (FOLLOWUPS 109, 2026-11-03).

A plan district's rules control where they conflict with a base or overlay
zone (PCC 33.500.040). Batch A reads sixteen neighbourhood chapters and
encodes what reaches the pod:

* Glendoveer (33.530). On R7 land the county zoned LR7.5 the setbacks are
  30 ft front, 10 ft side and 15 ft rear, with no alley relief. Its
  flag-lot standards (15 ft on every line, 25 ft height) ride the hold
  instead of a variant: no lot is read as a flag lot, so the Glendoveer R7
  lots whose shape could be one sit in the hold below.
* One hold for the rules nothing measures -- East Corridor, Glendoveer flag
  lots, Hollywood, Kenton, Lombard, Macadam, North Interstate, Northwest
  Hills (Linnton Hillside) and West Portland Multicultural -- on the lots
  they reach. East Corridor's Map 521-3 minimum floor area ratios (0.5 to 1
  and 1 to 1) are in it whole: the figures are printed on the map, not in
  the chapter text, so no stored line carries a number to check against.

What is guarded: the two facts are registered and never assumed; each
traced area answers exactly the zone blocks that carry its rule; the numbers
sit where the code puts them and nowhere else; a lot inside reads true and
one outside false; and a held lot cannot be GREEN.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
import shapely
from shapely.geometry import box

from flats.designs.model import load_catalog
from flats.encode.load import load_trusted
from flats.geom.drawn import load_area
from flats.ingest.quadfit import lot_from_row, observed_facts, screen_lot
from flats.provenance.store import ProvenanceStore
from flats.rules.conditions import CONDITIONS, DRAWN_CONDITIONS
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.score import flags as flag_plan
from flats.score import relief, slack
from flats.score.flags import fact_code
from flats.tests.test_portland_plan_districts import FACTS as PART_1
from flats.tests.test_quadfit_bridge import row

pytestmark = pytest.mark.unit

PORTLAND = "or/multnomah/portland"
GLENDOVEER = "pdx_glendoveer_lr75"
HOLD = "pdx_plan_district_unmeasured"
FACTS = (GLENDOVEER, HOLD)
#: The Gateway and East Corridor minimum-FAR map areas (pd2c, 2026-11-04),
#: read off Maps 526-3 and 521-3; see test_portland_plan_districts_4.
MIN_FAR = ("pdx_gateway_min_far", "pdx_east_corridor_min_far_half", "pdx_east_corridor_min_far_one")
FILES = {
    GLENDOVEER: "or/multnomah/portland/glendoveer-lr75.geojson",
    HOLD: "or/multnomah/portland/plan-district-unmeasured-lots.geojson",
}
HOLD_ZONES = {
    "RF", "R20", "R10", "R7", "R5", "R2.5", "RM1", "RM2", "RM3", "CM1", "CM2", "CM3", "CE", "CI2",
    # Batch B (2026-11-04): Gateway, Northwest and Central City greens stand in these.
    "RM4", "RX", "CX", "EX",
}
#: The zone each area is probed in.
PROBE = {GLENDOVEER: "R7", HOLD: "R5"}
POD = ("multi_story", "attached_wall")


@pytest.fixture(scope="module")
def portland():
    return load_rules()[PORTLAND]


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


def _resolve(zone: str, *facts: str):
    return RuleSet(load_rules()).resolve(PORTLAND, zone, POD + facts)


# --- the facts and the areas ------------------------------------------------------


@pytest.mark.parametrize("name", FACTS)
def test_the_facts_are_drawn_site_facts_never_assumed(name: str) -> None:
    assert name in DRAWN_CONDITIONS
    defn = CONDITIONS[name]
    assert defn.kind == "site_fact"
    assert defn.assume is None


def test_each_area_answers_the_zones_that_carry_its_rule(portland) -> None:
    by_fact = {a.condition: a for a in portland.drawn_areas.values()}
    # Batch B (2026-11-04) adds Northwest Map 562-2, test_portland_plan_districts_3;
    # FOLLOWUPS 153 round 2 (2026-11-08) the Hayden Island and Lombard Subdistrict A
    # main-entrance outlines, test_entrance_orientation.
    # Maps 120-2 and 120-3 (FOLLOWUPS 68) are base-zone maps held beside them.
    assert set(by_fact) == set(FACTS) | set(PART_1) | set(MIN_FAR) | {
        "pdx_nw_residential_limited",
        "pdx_hayden_island",
        "pdx_lombard_subdistrict_a",
        "pdx_eastern_pattern_area",
        "pdx_min_site_frontage_area",
        # Kenton Map 538-4 (FOLLOWUPS 185, 2026-11-13), test_portland_kenton_538.
        "pdx_kenton_building_line",
    }
    for fact in FACTS:
        assert by_fact[fact].file == FILES[fact]
    assert set(by_fact[GLENDOVEER].zones) == {"R7"}
    # CI1 because RICAP 11 builds a CI1 home to RM1's standards, holds included.
    assert set(by_fact[HOLD].zones) == HOLD_ZONES | {"CI1"}


def test_the_numbers_and_the_hold_sit_where_the_code_puts_them(portland) -> None:
    for name, zone in portland.zones.items():
        if name == "CI1":
            continue  # RM1's, imported whole from 2026-11-01 (RICAP 11)
        quad = zone.values.get("quadplex_allowed")
        if name in HOLD_ZONES:
            assert quad.qualified_by == HOLD, name
        else:
            assert quad is None or quad.qualified_by != HOLD, name
        # Map 521-3's and 526-3's figures are not in stored text, so no zone
        # carries them as a quoted number: the base is exempt and every figure
        # is a drawn variant (pd2c, 2026-11-04).
        floor = zone.values.get("min_far")
        assert floor is None or (
            floor.exempt and all(v.prov.drawn and not v.prov.quote for v in floor.variants)
        ), name
        held = [c for v in zone.values.values() for var in v.variants for c in var.when]
        if name != "R7":
            assert GLENDOVEER not in held, name


#: Layers that hold the plan-district HOLD on their own drawn area: the
#: Multnomah pockets (2026-11-09, FOLLOWUPS 112(b)) are on Title 33 under the
#: county/city planning IGA, so Portland's plan districts reach them, held whole
#: off plan-districts.geojson (test_multnomah_pockets_title33). Glendoveer stays
#: Portland's alone.
HOLD_ALSO = {"or/multnomah/_unincorporated"}


def test_no_other_layer_carries_the_facts() -> None:
    for jid, layer in load_rules().items():
        if jid == PORTLAND:
            continue
        held = list(layer.defaults.values()) + [v for z in layer.zones.values() for v in z.values.values()]
        allowed = {HOLD} if jid in HOLD_ALSO else set()
        for v in held:
            assert v.qualified_by not in set(FACTS) - allowed, jid
            assert not {c for var in v.variants for c in var.when} & set(FACTS), jid


# --- Glendoveer -----------------------------------------------------------------


def test_r7_outside_glendoveer_keeps_the_base_setbacks() -> None:
    res = _resolve("R7")
    assert (res.get("setback_front_ft"), res.get("setback_side_ft"), res.get("setback_rear_ft")) == (15, 5, 5)
    assert res.get("max_height_ft") == 30


def test_r7_in_glendoveer_takes_the_plan_districts_setbacks() -> None:
    res = _resolve("R7", GLENDOVEER)
    assert (res.get("setback_front_ft"), res.get("setback_side_ft"), res.get("setback_rear_ft")) == (30, 10, 15)
    assert res.get("setback_alley_side_ft") == 10
    assert res.get("max_height_ft") == 30


def test_an_alley_does_not_waive_the_glendoveer_rear_setback() -> None:
    assert _resolve("R7", "alley_at_rear").values.get("setback_rear_ft") is None  # base exempt
    res = _resolve("R7", GLENDOVEER, "alley_at_rear")
    assert res.get("setback_rear_ft") == 15
    assert not res.values["setback_rear_ft"].ambiguous


def test_no_r7_figure_turns_on_the_flag_lot_fact() -> None:
    # flag_lot is never observed, so a variant on it would turn every
    # Glendoveer lot YELLOW on an assumed fact; 33.530.050 rides the hold.
    text = (Path(__file__).parents[1] / "config/jurisdictions" / f"{PORTLAND}.yaml").read_text(encoding="utf-8")
    assert "[pdx_glendoveer_lr75, flag_lot" not in text
    assert "flag-lot" in CONDITIONS[HOLD].describe


def test_the_quotes_say_what_the_rules_say() -> None:
    store = ProvenanceStore()
    gl = store.quote("or/multnomah/portland/33.530.txt#L32,L34")
    assert "Front setback 30 feet" in gl
    assert "Side setback 10 feet" in store.quote("or/multnomah/portland/33.530.txt#L32,L35,L37-L40")
    assert "Rear setback 15 feet" in store.quote("or/multnomah/portland/33.530.txt#L32,L36")
    assert "required setbacks are 15 feet" in store.quote("or/multnomah/portland/33.530.txt#L61-L62")
    assert "flag lots is 25 feet" in store.quote("or/multnomah/portland/33.530.txt#L63")
    assert "formerly zoned LR7.5" in store.quote("or/multnomah/portland/33.530.txt#L21-L24")
    far = store.quote("or/multnomah/portland/33.521.txt#L126-L127")
    assert "minimum floor area ratios (FAR) for all new development" in far and "Map 521-3" in far
    hold = store.quote("or/multnomah/portland/33.595.txt#L89,L171-L174,L393-L397,L438-L449")
    assert "Residential uses are prohibited in the Employment Focus Area" in hold
    assert "1.5 to 1" in hold and "30 percent" in hold and "25 percent of the total depth" in hold


# --- the tracings ---------------------------------------------------------------


@pytest.mark.parametrize("fact", FACTS)
def test_the_tracing_is_in_quadfits_coordinates(fact: str) -> None:
    from flats.rules import loader

    data = json.loads((loader.AREAS_ROOT / FILES[fact]).read_text(encoding="utf-8"))
    assert data["crs"]["properties"]["name"].endswith("EPSG::2913")
    assert data["source"]["quote"].startswith("or/multnomah/portland/33.5")
    assert {"map", "says", "inputs", "method"} <= set(data["source"])


def test_the_hold_says_east_corridors_minimum_far_areas_left_it() -> None:
    # Held whole in batch A; read off Map 521-3 and cut out in pd2c.
    from flats.rules import loader

    data = json.loads((loader.AREAS_ROOT / FILES[HOLD]).read_text(encoding="utf-8"))
    assert "Map 521-3" in data["source"]["inputs"]["far"]
    assert "until pd2c" in data["source"]["inputs"]["far"]
    assert "EC Map 521-3 .5:1 and 1:1 minimum-FAR polygons" in data["source"]["method"]
    assert "GL R7 lots of geometry tier C" in data["source"]["method"]


def _facts(zone: str, lot) -> dict:
    layers = load_trusted(strict=False).rules.layers
    return observed_facts(row(jurisdiction="portland", zone=zone, lot_wkb=shapely.to_wkb(lot)), layers)


@pytest.mark.parametrize("fact", FACTS)
def test_a_lot_inside_reads_true_and_one_far_away_false(fact: str) -> None:
    area = load_area(FILES[fact])
    inside = max(getattr(area, "geoms", [area]), key=lambda g: g.area).representative_point().buffer(5)
    minx, miny, _, _ = area.bounds
    outside = box(minx - 3000, miny - 3000, minx - 2900, miny - 2900)
    assert _facts(PROBE[fact], inside)[fact] is True
    assert _facts(PROBE[fact], outside)[fact] is False


def test_glendoveer_does_not_ask_an_r10_lot() -> None:
    area = load_area(FILES[GLENDOVEER])
    inside = area.representative_point().buffer(5)
    assert GLENDOVEER not in _facts("R10", inside)


# --- through the screen ---------------------------------------------------------


def _lot(corpus, zone: str, w: float = 100.0, d: float = 200.0):
    x0, y0 = 7_670_000.0, 660_000.0
    edges = [
        [x0, y0, x0 + w, y0, "F"],
        [x0 + w, y0, x0 + w, y0 + d, "S"],
        [x0 + w, y0 + d, x0, y0 + d, "R"],
        [x0, y0 + d, x0, y0, "S"],
    ]
    r = {
        "TLID": "1S2E00AA  -00100",
        "jurisdiction": "portland",
        "zone": zone,
        "tier": "A",
        "area_sqft": w * d,
        "frontage_ft": w,
        "lot_width_ft": w,
        "lot_depth_ft": d,
        "edges_json": json.dumps(edges),
        "front_bearings_json": "[0.0]",
        "fronts_cul_de_sac": False,
        "split_zone": False,
        "ovl_fema_sfha": False,
        "ovl_fema_floodway": False,
        "sewer_main_dist_ft": 12.0,
        "in_sewer_district": None,
        "wkb": shapely.to_wkb(box(x0 + 5, y0 + 10, x0 + w - 5, y0 + d - 15)),
        "lot_wkb": shapely.to_wkb(box(x0, y0, x0 + w, y0 + d)),
    }
    return lot_from_row(r, corpus.layers)


def _screen(corpus, lot):
    (s,) = screen_lot(
        lot,
        [load_catalog().latest("pod56x36")],
        rules=corpus,
        policy=slack.load_policy(),
        relief=relief.load_policy(),
        step_deg=30.0,
    )
    return s.signed


def _answered(lot, **facts):
    return dataclasses.replace(lot, observed={**lot.observed, **facts})


def _clear(corpus, zone: str = "R5", **kw):
    """A lot every other fact answers, so it is GREEN on its own."""
    off = {f: False for f in FACTS + PART_1 + MIN_FAR}
    return _answered(_lot(corpus, zone, **kw), constrained_sites_overlay=False, **off)


def test_a_held_lot_cannot_be_green_and_says_why(corpus) -> None:
    lot = _clear(corpus)
    clear = _screen(corpus, lot)
    held = _screen(corpus, _answered(lot, **{HOLD: True}))
    assert clear.colour is flag_plan.Colour.green
    assert fact_code(HOLD) not in {f.code for f in clear.flags}
    # The hold is the only thing between the two.
    assert held.colour is flag_plan.Colour.yellow
    assert fact_code(HOLD) in {f.code for f in held.flags}


def test_a_roomy_glendoveer_lot_still_fits(corpus) -> None:
    lot = _clear(corpus, "R7")
    assert _screen(corpus, lot).colour is flag_plan.Colour.green
    assert _screen(corpus, _answered(lot, **{GLENDOVEER: True})).colour is flag_plan.Colour.green


def test_an_east_corridor_multi_dwelling_lot_in_the_hold_is_not_green(corpus) -> None:
    lot = _clear(corpus, "RM2")
    assert _screen(corpus, lot).colour is flag_plan.Colour.green
    assert _screen(corpus, _answered(lot, **{HOLD: True})).colour is flag_plan.Colour.yellow


def test_the_flags_read_in_plain_english() -> None:
    types = flag_plan.registry().types
    assert "33.530.040" in types[fact_code(GLENDOVEER)].description
    assert "East Corridor" in types[fact_code(HOLD)].description
    assert "Linnton Hillside" in types[fact_code(HOLD)].description
    for fact in FACTS:
        assert types[fact_code(fact)].severity >= flag_plan.colour_rules().yellow_at_severity


# --- Kenton 33.538.230, the 25 ft walls (FOLLOWUPS 185) -------------------------
#
# Held whole on 2026-11-12; Map 538-4 traced 2026-11-13 -- the lots on, off
# and in doubt are tested in test_portland_kenton_538.


def test_kentons_wall_rule_asks_more_height_than_the_pod_has() -> None:
    text = ProvenanceStore().quote("or/multnomah/portland/33.538.txt#L110-L114")
    assert "Map 538-4" in text and "must be at least 25 feet high" in text
    assert "Multi-dwelling zoned sites are exempt" in text
    assert all(d.height_ft < 25 for d in load_catalog().active())
