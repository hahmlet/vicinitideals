"""Portland plan districts, part 1 (FOLLOWUPS 109, 2026-11-01).

A plan district's rules control where they conflict with a base or overlay
zone (PCC 33.500.040). Part 1 reads the two districts that held about half of
the plan-district GREEN lots on run 109:

* Johnson Creek Basin (33.537). South subdistrict and flood-hazard sites take
  a 50 percent impervious-surface cap (140.D, 150.E), and the Springwater
  Corridor buffer (130), South land-class density (140.E) and Flood Risk Area
  (160) reach lots nothing measures, so those lots are held. The tree limits
  (125) no longer hold a lot (ruling 2026-11-01-trees-ignored-entered-per-lot,
  FOLLOWUPS 140): the lots only they reached were taken out of the tracing.
* Laurelhurst/Eastmoreland (33.540). Its setbacks are only on maps held at the
  Development Services Center, so every lot inside is held.

What is guarded: the three facts are registered and never assumed; each
traced area answers exactly the zone blocks that carry its rule; the cap and
the holds sit where the code puts them and nowhere else; a lot inside reads
true and one outside false; and a held lot cannot be GREEN.
"""

from __future__ import annotations

import dataclasses
import json

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
from flats.tests.test_quadfit_bridge import row

pytestmark = pytest.mark.unit

PORTLAND = "or/multnomah/portland"
IMPERVIOUS = "pdx_johnson_creek_impervious"
UNMEASURED = "pdx_johnson_creek_unmeasured"
SETBACK = "pdx_special_building_setback"
FACTS = (IMPERVIOUS, UNMEASURED, SETBACK)
JC_ZONES = {"R20", "R10", "R7", "R5", "R2.5", "RM1", "RM2", "CR", "CM1", "CM2", "CM3", "CE"}
LE_ZONES = {"R7", "R5", "RM1", "CM1", "CM3"}
FILES = {
    IMPERVIOUS: "or/multnomah/portland/johnson-creek-impervious-lots.geojson",
    UNMEASURED: "or/multnomah/portland/johnson-creek-unmeasured-lots.geojson",
    SETBACK: "or/multnomah/portland/laurelhurst-eastmoreland.geojson",
}
POD = ("multi_story", "attached_wall")


@pytest.fixture(scope="module")
def portland():
    return load_rules()[PORTLAND]


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


# --- the facts and the areas ------------------------------------------------------


@pytest.mark.parametrize("name", FACTS)
def test_the_facts_are_drawn_site_facts_never_assumed(name: str) -> None:
    assert name in DRAWN_CONDITIONS
    defn = CONDITIONS[name]
    assert defn.kind == "site_fact"
    assert defn.assume is None


def test_each_area_answers_the_zones_that_carry_its_rule(portland) -> None:
    by_fact = {a.condition: a for a in portland.drawn_areas.values()}
    # Part 2's areas (test_portland_plan_districts_2.py) sit beside these.
    assert set(FACTS) <= set(by_fact)
    for fact in FACTS:
        assert by_fact[fact].file == FILES[fact]
    # CI1 because RICAP 11 builds a CI1 home to RM1's standards, holds included.
    assert set(by_fact[IMPERVIOUS].zones) == JC_ZONES | {"CI1"}
    assert set(by_fact[UNMEASURED].zones) == JC_ZONES | {"CI1"}
    assert set(by_fact[SETBACK].zones) == LE_ZONES | {"CI1"}


def test_the_cap_and_the_holds_sit_where_the_code_puts_them(portland) -> None:
    for name, zone in portland.zones.items():
        if name == "CI1":
            continue  # RM1's, imported whole from 2026-11-01 (RICAP 11)
        cap = zone.values.get("max_impervious_pct")
        rear = zone.values.get("setback_rear_ft")
        front = zone.values.get("setback_front_ft")
        if name in JC_ZONES:
            assert cap is not None and cap.exempt, name
            assert [(v.value, v.when) for v in cap.variants] == [(50, (IMPERVIOUS,))], name
            assert rear.qualified_by == UNMEASURED, name
        else:
            assert cap is None, name
            assert rear is None or rear.qualified_by is None, name
        if name in LE_ZONES:
            assert front.qualified_by == SETBACK, name
        else:
            assert front is None or front.qualified_by is None, name


def test_no_other_layer_carries_the_facts() -> None:
    for jid, layer in load_rules().items():
        if jid == PORTLAND:
            continue
        held = list(layer.defaults.values()) + [v for z in layer.zones.values() for v in z.values.values()]
        for v in held:
            assert v.qualified_by not in FACTS, jid
            assert not {c for var in v.variants for c in var.when} & set(FACTS), jid


def test_r5_resolves_both_holds() -> None:
    res = RuleSet(load_rules()).resolve(PORTLAND, "R5", POD)
    assert {UNMEASURED, SETBACK} <= res.unencoded


def test_the_quotes_say_what_the_rules_say() -> None:
    store = ProvenanceStore()
    cap = store.quote("or/multnomah/portland/33.537.txt#L272-L273,L324-L325")
    assert cap.count("No more than 50 percent of any site") == 2
    assert "eaves are included" in cap
    maps = store.quote("or/multnomah/portland/33.540.txt#L22-L24")
    assert "Special Building Setbacks maps" in maps and "Development Services Center" in maps
    control = store.quote("or/multnomah/portland/33.500.txt#L32-L35")
    assert "plan district regulations control" in control


# --- the tracings ---------------------------------------------------------------


@pytest.mark.parametrize("fact", FACTS)
def test_the_tracing_is_in_quadfits_coordinates(fact: str) -> None:
    from flats.rules import loader

    data = json.loads((loader.AREAS_ROOT / FILES[fact]).read_text(encoding="utf-8"))
    assert data["crs"]["properties"]["name"].endswith("EPSG::2913")
    assert data["source"]["quote"].startswith("or/multnomah/portland/33.5")


def _subdistrict(name: str):
    from flats.rules import loader

    path = loader.AREAS_ROOT / PORTLAND / "plan-subdistricts.geojson"
    data = json.loads(path.read_text(encoding="utf-8"))
    return shapely.union_all(
        [
            shapely.geometry.shape(f["geometry"])
            for f in data["features"]
            if f["properties"]["PLDIST"] == "JC" and f["properties"]["SUBDIST"] == name
        ]
    )


@pytest.mark.parametrize("name", ["SOUTH", "FLOOD RISK"])
def test_the_hold_still_covers_south_and_the_flood_risk_area(name: str) -> None:
    # 140.E (South density) and 160 (Flood Risk Area) still hold their lots.
    sub, held = _subdistrict(name), load_area(FILES[UNMEASURED])
    assert not sub.is_empty
    assert sub.difference(held).area < 0.001 * sub.area


def _tree_only():
    """Where only 33.537.125 reached: the cap's flood-hazard lots outside
    South, the Flood Risk Area and the corridor reach."""
    cap, held = load_area(FILES[IMPERVIOUS]), load_area(FILES[UNMEASURED])
    reach = shapely.union_all([_subdistrict("SOUTH"), _subdistrict("FLOOD RISK")]).buffer(5)
    return cap.difference(held).difference(reach)


def test_trees_alone_no_longer_hold_a_lot() -> None:
    # Ruling 2026-11-01-trees-ignored-entered-per-lot (FOLLOWUPS 140): about
    # a thousand flood-hazard lots the tree limits alone held were taken out.
    gone = _tree_only()
    assert gone.area / 43_560 > 300
    # What is left of the hold is the three other reaches, not a new one.
    held, cap = load_area(FILES[UNMEASURED]), load_area(FILES[IMPERVIOUS])
    assert held.area < cap.union(_subdistrict("FLOOD RISK")).area + 2_000 * 43_560


def test_a_tree_only_lot_keeps_the_cap_but_not_the_hold() -> None:
    gone = _tree_only()
    piece = max(getattr(gone, "geoms", [gone]), key=lambda g: g.area).buffer(-10)
    lot = max(getattr(piece, "geoms", [piece]), key=lambda g: g.area).representative_point().buffer(5)
    facts = _facts("R5", lot)
    assert facts[IMPERVIOUS] is True
    assert facts[UNMEASURED] is False


def test_the_held_reason_names_no_trees() -> None:
    import yaml

    from flats.rules import loader

    texts = [
        CONDITIONS[UNMEASURED].describe,
        CONDITIONS[UNMEASURED].evidence,
        flag_plan.registry().types[fact_code(UNMEASURED)].description,
    ]
    area = json.loads((loader.AREAS_ROOT / FILES[UNMEASURED]).read_text(encoding="utf-8"))
    texts.append(area["source"]["says"])

    def walk(node):
        if isinstance(node, dict):
            q = node.get("qualified_by")
            if isinstance(q, dict) and q.get("fact") == UNMEASURED:
                texts.append(q["cite"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    layer = loader.CONFIG_ROOT / f"{PORTLAND}.yaml"
    walk(yaml.safe_load(layer.read_text(encoding="utf-8")))
    assert len(texts) > 10
    for text in texts:
        assert "tree" not in text.lower(), text


def test_the_two_districts_are_the_two_outlines() -> None:
    area = load_area(FILES[SETBACK])
    acres = area.area / 43_560
    assert 600 < acres < 1_500


def _facts(zone: str, lot) -> dict:
    layers = load_trusted(strict=False).rules.layers
    return observed_facts(row(jurisdiction="portland", zone=zone, lot_wkb=shapely.to_wkb(lot)), layers)


@pytest.mark.parametrize("fact", FACTS)
def test_a_lot_inside_reads_true_and_one_far_away_false(fact: str) -> None:
    area = load_area(FILES[fact])
    inside = max(getattr(area, "geoms", [area]), key=lambda g: g.area).representative_point().buffer(5)
    minx, miny, _, _ = area.bounds
    outside = box(minx - 3000, miny - 3000, minx - 2900, miny - 2900)
    assert _facts("R5", inside)[fact] is True
    assert _facts("R5", outside)[fact] is False


def test_a_zone_the_rule_does_not_reach_is_not_asked() -> None:
    area = load_area(FILES[SETBACK])
    inside = area.representative_point().buffer(5)
    assert SETBACK not in _facts("R2.5", inside)


# --- through the screen ---------------------------------------------------------


def _lot(corpus, w: float = 100.0, d: float = 200.0):
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
        "zone": "R5",
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


def _clear(corpus):
    """A roomy R5 lot every other fact answers, so it is GREEN on its own."""
    return _answered(_lot(corpus), constrained_sites_overlay=False, **{f: False for f in FACTS})


@pytest.mark.parametrize("fact", [UNMEASURED, SETBACK])
def test_a_held_lot_cannot_be_green_and_says_why(corpus, fact: str) -> None:
    lot = _clear(corpus)
    clear = _screen(corpus, lot)
    held = _screen(corpus, _answered(lot, **{fact: True}))
    assert clear.colour is flag_plan.Colour.green
    assert fact_code(fact) not in {f.code for f in clear.flags}
    # The hold is the only thing between the two.
    assert held.colour is flag_plan.Colour.yellow
    assert fact_code(fact) in {f.code for f in held.flags}


def test_the_cap_is_checked_only_where_it_reaches(corpus) -> None:
    lot = _clear(corpus)
    off = [c for c in _screen(corpus, lot).checks if c.check == "impervious_pct"]
    on = _screen(corpus, _answered(lot, **{IMPERVIOUS: True}))
    (cap,) = [c for c in on.checks if c.check == "impervious_pct"]
    assert off == []
    assert cap.threshold == 50.0 and cap.is_maximum
    # A 100 x 200 lot carries the pod and its court well under half.
    assert on.colour is flag_plan.Colour.green


def test_the_flags_read_in_plain_english() -> None:
    types = flag_plan.registry().types
    assert "33.537.140.D" in types[fact_code(IMPERVIOUS)].description
    assert "Springwater" in types[fact_code(UNMEASURED)].description
    assert "Development Services Center" in types[fact_code(SETBACK)].description
    for fact in FACTS:
        assert types[fact_code(fact)].severity >= flag_plan.colour_rules().yellow_at_severity
