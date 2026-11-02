"""Portland Maps 120-2 and 120-3 (FOLLOWUPS 68, 2026-11-01).

Two multi-dwelling rules that reach only a mapped part of the city, left out
until the maps were held:

* PCC 33.120.206, on the sites shown on Map 120-2 (four Eastern Portland
  centres): a site more than 160 ft deep may take new homes only with at
  least 90 ft of frontage on a street. The C.2.b neighbour exception is not
  read, so a short lot is held, never refused and never GREEN.
* PCC 33.120.220.B.2, in the Eastern Pattern Area of Map 120-3: the rear
  setback is 25 percent of the site's depth, no more than half of it vehicle
  area; corner lots and lots up to 100 ft deep are exempt.

Every test rules both ways: the lot the rule reaches and the lot it leaves.
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
from flats.rules import loader
from flats.rules.conditions import CONDITIONS, DRAWN_CONDITIONS
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet, Verdict
from flats.score import flags as flag_plan
from flats.score import relief, slack
from flats.score.flags import fact_code
from flats.score.paper import behind_wall_ft
from flats.tests.test_quadfit_bridge import row

pytestmark = pytest.mark.unit

PORTLAND = "or/multnomah/portland"
FRONTAGE = "pdx_min_site_frontage_area"
NEIGHBOURS = "pdx_site_frontage_neighbour_exception"
EASTERN = "pdx_eastern_pattern_area"
FILES = {
    FRONTAGE: "or/multnomah/portland/map-120-2-site-frontage-areas.geojson",
    EASTERN: "or/multnomah/portland/eastern-pattern-area.geojson",
}
POD = ("multi_story", "attached_wall", "low_rise")


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


# --- the facts and the maps ----------------------------------------------


@pytest.mark.parametrize("name", [FRONTAGE, EASTERN])
def test_the_map_facts_are_drawn_site_facts_never_assumed(name: str) -> None:
    assert name in DRAWN_CONDITIONS
    assert CONDITIONS[name].kind == "site_fact"
    assert CONDITIONS[name].assume is None


def test_the_neighbour_exception_is_never_assumed_and_never_drawn() -> None:
    assert NEIGHBOURS not in DRAWN_CONDITIONS
    assert CONDITIONS[NEIGHBOURS].kind == "site_fact"
    assert CONDITIONS[NEIGHBOURS].assume is None


def test_each_map_answers_the_zones_its_sentence_names() -> None:
    by_fact = {a.condition: a for a in load_rules()[PORTLAND].drawn_areas.values()}
    assert by_fact[FRONTAGE].file == FILES[FRONTAGE]
    assert by_fact[EASTERN].file == FILES[EASTERN]
    # "in the multi-dwelling zones" (RMP refuses the fourplex outright).
    assert set(by_fact[FRONTAGE].zones) == {"RM1", "RM2", "RM3", "RM4", "RX", "CI1"}
    # "In the RM1, RM2, RM3 and RM4 zones".
    assert set(by_fact[EASTERN].zones) == {"RM1", "RM2", "RM3", "RM4", "CI1"}


def test_map_120_2_is_the_four_centres() -> None:
    data = json.loads((loader.AREAS_ROOT / FILES[FRONTAGE]).read_text(encoding="utf-8"))
    assert data["crs"]["properties"]["name"].endswith("EPSG::2913")
    assert "120-2" in data["source"]["note"]
    assert sorted(f["properties"]["NAME"] for f in data["features"]) == [
        "122nd/Hazelwood", "Jade District", "Midway", "Rosewood/Glenfair",
    ]


def test_the_eastern_area_is_the_one_eastern_polygon_and_nothing_else() -> None:
    data = json.loads((loader.AREAS_ROOT / FILES[EASTERN]).read_text(encoding="utf-8"))
    assert data["crs"]["properties"]["name"].endswith("EPSG::2913")
    assert [f["properties"]["TYPE"] for f in data["features"]] == ["Eastern Neighborhoods"]
    source = json.loads(
        (loader.AREAS_ROOT / "or/multnomah/portland/map-120-3-pattern-areas.geojson").read_text(
            encoding="utf-8"
        )
    )
    eastern = [f for f in source["features"] if f["properties"]["TYPE"] == "Eastern Neighborhoods"]
    assert data["features"] == eastern
    # East Portland is tens of square miles, and the frontage centres sit
    # mostly inside it (the Jade District reaches west of the line along 82nd).
    area = load_area(FILES[EASTERN])
    assert 15 < area.area / 27_878_400 < 40
    centres = load_area(FILES[FRONTAGE])
    assert centres.difference(area).area < 0.1 * centres.area


def _facts(zone: str, lot) -> dict:
    layers = load_trusted(strict=False).rules.layers
    return observed_facts(row(jurisdiction="portland", zone=zone, lot_wkb=shapely.to_wkb(lot)), layers)


@pytest.mark.parametrize("fact", [FRONTAGE, EASTERN])
def test_a_lot_inside_reads_true_one_far_away_false_and_rmp_is_not_asked(fact: str) -> None:
    area = load_area(FILES[fact])
    inside = max(getattr(area, "geoms", [area]), key=lambda g: g.area).representative_point().buffer(5)
    minx, miny, _, _ = area.bounds
    outside = box(minx - 3000, miny - 3000, minx - 2900, miny - 2900)
    assert _facts("RM1", inside)[fact] is True
    assert _facts("RM1", outside)[fact] is False
    assert fact not in _facts("RMP", inside)
    assert fact not in _facts("R5", inside)


# --- 33.120.206: the frontage rule ------------------------------------------


def test_a_deep_site_on_the_map_owes_ninety_feet_on_one_street(rules: RuleSet) -> None:
    # CI1 takes RM1's standards whole only on runs from 2026-11-01 (RICAP 11);
    # undated it reads its own table, so it is not asked here.
    for zone in ("RM1", "RM2", "RM3", "RM4", "RX"):
        got = rules.resolve(PORTLAND, zone, (*POD, FRONTAGE), lot={"lot_depth_ft": 200})
        assert got.values["min_frontage_ft"].value == 90, zone
        assert got.values["min_frontage_one_street"].value is True, zone


def test_a_site_up_to_160_ft_deep_or_off_the_map_owes_nothing_new(rules: RuleSet) -> None:
    shallow = rules.resolve(PORTLAND, "RM1", (*POD, FRONTAGE), lot={"lot_depth_ft": 160})
    off = rules.resolve(PORTLAND, "RM1", POD, lot={"lot_depth_ft": 200})
    assert "min_frontage_ft" not in shallow.values
    assert "min_frontage_ft" not in off.values
    # RX keeps Table 120-3's 10 ft front lot line either way.
    assert rules.resolve(PORTLAND, "RX", (*POD, FRONTAGE), lot={"lot_depth_ft": 160}).values[
        "min_frontage_ft"
    ].value == 10


def test_the_neighbour_exception_lets_the_site_through(rules: RuleSet) -> None:
    got = rules.resolve(PORTLAND, "RM1", (*POD, FRONTAGE, NEIGHBOURS), lot={"lot_depth_ft": 200})
    assert "min_frontage_ft" not in got.values


def test_a_deep_site_on_the_map_with_no_measured_depth_is_refused(rules: RuleSet) -> None:
    got = rules.resolve(PORTLAND, "RM1", (*POD, FRONTAGE), lot={})
    assert got.verdict is Verdict.ambiguous
    assert "min_frontage_ft" in got.ambiguous


# --- 33.120.220.B.2: the Eastern Pattern Area rear setback ------------------


@pytest.mark.parametrize("zone", ["RM1", "RM2", "RM3", "RM4"])
def test_the_eastern_rear_setback_is_a_quarter_of_the_depth(rules: RuleSet, zone: str) -> None:
    got = rules.resolve(PORTLAND, zone, (*POD, EASTERN), lot={"lot_depth_ft": 200})
    assert got.values["setback_rear_ft"].value == 50
    assert got.values["parking_rear_yard_max_pct"].value == 50


@pytest.mark.parametrize("zone", ["RM1", "RM2", "RM3", "RM4"])
def test_corner_lots_and_lots_up_to_100_ft_take_the_table(rules: RuleSet, zone: str) -> None:
    base = rules.resolve(PORTLAND, zone, POD, lot={"lot_depth_ft": 200}).values["setback_rear_ft"].value
    corner = rules.resolve(PORTLAND, zone, (*POD, EASTERN, "corner_lot"), lot={"lot_depth_ft": 200})
    shallow = rules.resolve(PORTLAND, zone, (*POD, EASTERN), lot={"lot_depth_ft": 100})
    assert corner.values["setback_rear_ft"].value == base == 5
    assert shallow.values["setback_rear_ft"].value == base
    assert "parking_rear_yard_max_pct" not in corner.values
    assert "parking_rear_yard_max_pct" not in shallow.values


def test_rm3_above_55_ft_keeps_its_ten_on_a_corner(rules: RuleSet) -> None:
    tall = ("multi_story", "attached_wall")
    got = rules.resolve(PORTLAND, "RM3", (*tall, EASTERN, "corner_lot"), lot={"lot_depth_ft": 200})
    assert got.values["setback_rear_ft"].value == 10


def test_the_eastern_setback_outranks_the_alley(rules: RuleSet) -> None:
    for zone in ("RM1", "RM3"):
        got = rules.resolve(PORTLAND, zone, (*POD, EASTERN, "alley_at_rear"), lot={"lot_depth_ft": 160})
        assert got.values["setback_rear_ft"].value == 40, zone


def test_outside_the_area_nothing_changes(rules: RuleSet) -> None:
    got = rules.resolve(PORTLAND, "RM1", POD, lot={"lot_depth_ft": 200})
    assert got.values["setback_rear_ft"].value == 5
    assert "parking_rear_yard_max_pct" not in got.values


def test_an_eastern_lot_with_no_measured_depth_is_refused(rules: RuleSet) -> None:
    got = rules.resolve(PORTLAND, "RM1", (*POD, EASTERN), lot={})
    assert got.verdict is Verdict.ambiguous
    assert "setback_rear_ft" in got.ambiguous


def test_the_court_may_use_only_half_the_eastern_yard() -> None:
    class Rules(dict):
        def get(self, name, default=None):  # noqa: D401 - a ZoneResolution stand-in
            return super().get(name, default)

    capped = Rules(parking_rear_yard_max_pct=50)
    assert behind_wall_ft(42.0, 50.0, Rules()) == 50.0
    assert behind_wall_ft(42.0, 50.0, capped) == 67.0
    assert behind_wall_ft(10.0, 50.0, capped) == 50.0


def test_the_quotes_say_what_the_rules_say() -> None:
    store = ProvenanceStore()
    s = "or/multnomah/portland/33.120/"
    assert "sites shown on Map 120-2" in store.quote(s + "33.120.206.txt#L8")
    rule = store.quote(s + "33.120.206.txt#L10")
    assert "more than 160 feet deep" in rule and "90 feet of frontage on a street" in rule
    assert "share a side lot line" in store.quote(s + "33.120.206.txt#L15-L18")
    eastern = store.quote(s + "33.120.220.txt#L23,L25")
    assert "25 percent of the total depth of the site" in eastern and "Map 120-3" in eastern
    assert "No more than 50 percent" in store.quote(s + "33.120.220.txt#L24")
    assert "Corner lots and lots that are up to 100 feet deep" in store.quote(s + "33.120.220.txt#L28")


# --- the screen ---------------------------------------------------------------


def _lot(corpus, zone: str, w: float, d: float, *, through: bool = False):
    x0, y0 = 7_690_000.0, 680_000.0
    edges = [
        [x0, y0, x0 + w, y0, "F"],
        [x0 + w, y0, x0 + w, y0 + d, "S"],
        [x0 + w, y0 + d, x0, y0 + d, "F" if through else "R"],
        [x0, y0 + d, x0, y0, "S"],
    ]
    r = {
        "TLID": "1N2E21AD  -06200",
        "jurisdiction": "portland",
        "zone": zone,
        "tier": "A",
        "area_sqft": w * d,
        "frontage_ft": 2 * w if through else w,
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


QUIET = {
    "constrained_sites_overlay": False,
    "pdx_johnson_creek_impervious": False,
    "pdx_johnson_creek_unmeasured": False,
    "pdx_special_building_setback": False,
}


def _answered(lot, **facts):
    return dataclasses.replace(lot, observed={**lot.observed, **QUIET, **facts})


def _fit(s):
    (got,) = [c for c in s.checks if c.check == "fit_ft"]
    return got


# Lots under 10,000 sq ft: RM1's minimum density (1 home per 2,500 sq ft)
# holds anything bigger at a closer look, which would hide the colour asked.


def test_a_deep_narrow_lot_on_map_120_2_is_held_never_green(corpus) -> None:
    lot = _lot(corpus, "RM1", 60, 166)
    off = _screen(corpus, _answered(lot, **{FRONTAGE: False, EASTERN: False}))
    on = _screen(corpus, _answered(lot, **{FRONTAGE: True, EASTERN: False}))
    assert off.colour is flag_plan.Colour.green
    # 60 ft of frontage against 90, and the neighbour exception unread: a
    # closer look, never the RED a certain miss would be.
    assert on.colour is flag_plan.Colour.yellow
    assert fact_code(NEIGHBOURS) in {f.code for f in on.flags}
    assert "min_frontage_ft" not in {c.check for c in on.checks}


def test_the_neighbours_answered_settle_the_lot_either_way(corpus) -> None:
    lot = _lot(corpus, "RM1", 60, 166)
    built = _screen(corpus, _answered(lot, **{FRONTAGE: True, EASTERN: False, NEIGHBOURS: True}))
    bare = _screen(corpus, _answered(lot, **{FRONTAGE: True, EASTERN: False, NEIGHBOURS: False}))
    assert built.colour is flag_plan.Colour.green
    assert bare.colour is flag_plan.Colour.red


def test_a_shallow_lot_on_map_120_2_owes_no_closer_look(corpus) -> None:
    shallow = _screen(corpus, _answered(_lot(corpus, "RM1", 60, 160), **{FRONTAGE: True, EASTERN: False}))
    # The neighbours are asked about, and either answer clears the lot: the
    # flag rides along below the yellow line.
    assert shallow.colour is flag_plan.Colour.green
    line = flag_plan.colour_rules().yellow_at_severity
    assert all(
        flag_plan.severity_of(f) < line for f in shallow.flags if f.code == fact_code(NEIGHBOURS)
    )
    assert "min_frontage_ft" not in {c.check for c in shallow.checks}


def test_a_through_lot_is_measured_on_one_street(corpus) -> None:
    lot = _lot(corpus, "RM1", 60, 166, through=True)
    assert lot.facts.frontage_ft == 120
    got = _screen(corpus, _answered(lot, **{FRONTAGE: True, EASTERN: False, NEIGHBOURS: False}))
    assert got.colour is flag_plan.Colour.red
    (front,) = [c for c in got.checks if c.check == "min_frontage_ft"]
    assert front.observed == 60


def test_an_eastern_lot_is_charged_the_quarter_depth_yard(corpus) -> None:
    lot = _lot(corpus, "RM1", 60, 166)
    west = _screen(corpus, _answered(lot, **{FRONTAGE: False, EASTERN: False, "corner_lot": False}))
    east = _screen(corpus, _answered(lot, **{FRONTAGE: False, EASTERN: True, "corner_lot": False}))
    corner = _screen(corpus, _answered(lot, **{FRONTAGE: False, EASTERN: True, "corner_lot": True}))
    # 25% of 166 ft is 41.5 ft of rear yard against Table 120-4's 5 ft ...
    assert _fit(west).observed - _fit(east).observed == pytest.approx(36.5)
    # ... and the court may take up half of it (B.2.a), so the need shrinks.
    assert _fit(east).threshold < _fit(west).threshold
    assert _fit(corner).observed == _fit(west).observed
    assert east.colour is flag_plan.Colour.green


def test_the_flags_read_in_plain_english() -> None:
    types = flag_plan.registry().types
    assert "Map 120-2" in types[fact_code(FRONTAGE)].description
    assert "33.120.206.C.2.b" in types[fact_code(NEIGHBOURS)].description
    assert "Map 120-3" in types[fact_code(EASTERN)].description
    for fact in (FRONTAGE, NEIGHBOURS, EASTERN):
        assert types[fact_code(fact)].severity >= flag_plan.colour_rules().yellow_at_severity


# --- the bound of 2026-11-01: a depth nobody measured -----------------------
# 658 lots went RED -> YELLOW on RULE-AMBIGUOUS: no depth on the row, so the
# 100 ft and 160 ft bands refused the rule set, and a rule set nobody trusts
# binds nothing. A lot that misses at every depth it could have stays RED.


def _undepthed(lot):
    return dataclasses.replace(lot, facts=dataclasses.replace(lot.facts, lot_depth_ft=None))


@pytest.mark.parametrize("corner", [True, False, None])
def test_a_lot_that_fails_the_fit_at_every_depth_stays_red(corpus, corner) -> None:
    facts = {FRONTAGE: True, EASTERN: True}
    if corner is not None:
        facts["corner_lot"] = corner
    lot = _answered(_undepthed(_lot(corpus, "RM1", 60, 45)), **facts)
    if corner is None:
        lot = dataclasses.replace(
            lot, observed={k: v for k, v in lot.observed.items() if k != "corner_lot"}
        )
    got = _screen(corpus, lot)
    assert got.colour is flag_plan.Colour.red
    assert got.binds


def test_a_lot_that_clears_at_some_depth_is_held_for_it(corpus) -> None:
    lot = _answered(
        _undepthed(_lot(corpus, "RM1", 60, 166)), **{FRONTAGE: True, EASTERN: True, "corner_lot": False}
    )
    got = _screen(corpus, lot)
    assert got.colour is flag_plan.Colour.yellow
    assert "RULE-AMBIGUOUS" in {f.code for f in got.flags}


def test_the_depth_readings_cover_every_band_edge(corpus) -> None:
    from flats.ingest.quadfit import depth_readings

    got = depth_readings(corpus)
    assert {100.0, 100.01, 160.0, 160.01} <= set(got)
    assert min(got) == 1.0


def test_a_reading_is_never_measured_against(corpus) -> None:
    # The minimum lot depth and depth ratios check the measured depth only;
    # a reading selects bands and nothing else.
    lot = _undepthed(_lot(corpus, "RM1", 60, 166))
    read = dataclasses.replace(lot.facts, depth_reading_ft=1.0)
    assert read.lot_depth_ft is None
