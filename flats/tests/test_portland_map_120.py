"""Portland Maps 120-2 and 120-3 (FOLLOWUPS 68, 2026-11-01).

Two multi-dwelling rules that reach only a mapped part of the city, left out
until the maps were held:

* PCC 33.120.206, on the sites shown on Map 120-2 (four Eastern Portland
  centres): a site more than 160 ft deep may take new homes only with at
  least 90 ft of frontage on a street. The C.2.b neighbour exception is not
  read, so a short lot is held, never refused and never GREEN.
* PCC 33.120.220.B.2, in the Eastern Pattern Area of Map 120-3: the rear
  setback is 25 percent of the site's depth, and vehicle area may cover no
  more than half the setback's area; corner lots and lots up to 100 ft deep
  are exempt.

Every test rules both ways: the lot the rule reaches and the lot it leaves.
"""

from __future__ import annotations

import dataclasses
import json
import math

import pytest
import shapely
from shapely.geometry import Polygon, box

from flats.designs.model import load_catalog
from flats.encode.load import load_trusted
from flats.geom.drawn import load_area
from flats.geom.edges import Edge, EdgeClass, LotEdges, Tier
from flats.geom.envelope import Setbacks, buildable
from flats.ingest.quadfit import lot_from_row, observed_facts, screen_lot, setbacks_for
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


def test_the_depth_setback_keeps_the_ordinary_rear_yard_for_other_edges(
    rules: RuleSet,
) -> None:
    base = rules.resolve(PORTLAND, "RM1", POD, lot={"lot_depth_ft": 200})
    eastern = rules.resolve(PORTLAND, "RM1", (*POD, EASTERN), lot={"lot_depth_ft": 200})
    setbacks = setbacks_for(
        base, depth_rear_ft=eastern.values["setback_rear_ft"].value
    )
    assert setbacks is not None
    assert setbacks.rear_ft == 5
    assert setbacks.depth_rear_ft == 50


@pytest.mark.parametrize("zone", ["RM1", "RM2", "RM3", "RM4"])
def test_corner_lots_and_lots_up_to_100_ft_take_the_table(rules: RuleSet, zone: str) -> None:
    base = rules.resolve(PORTLAND, zone, POD, lot={"lot_depth_ft": 200}).values["setback_rear_ft"].value
    corner = rules.resolve(PORTLAND, zone, (*POD, EASTERN, "corner_lot"), lot={"lot_depth_ft": 200})
    shallow = rules.resolve(PORTLAND, zone, (*POD, EASTERN), lot={"lot_depth_ft": 100})
    assert corner.values["setback_rear_ft"].value == base == 5
    assert shallow.values["setback_rear_ft"].value == base
    assert "parking_rear_yard_max_pct" not in corner.values
    assert "parking_rear_yard_max_pct" not in shallow.values


@pytest.mark.parametrize("zone", ["RM1", "RM2", "RM3", "RM4"])
def test_an_eastern_corner_needs_no_depth_measure_for_its_rear_setback(
    rules: RuleSet, zone: str
) -> None:
    got = rules.resolve(PORTLAND, zone, (*POD, EASTERN, "corner_lot"), lot={})
    assert got.values["setback_rear_ft"].value in {5, 10}
    assert "setback_rear_ft" not in got.ambiguous


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
    assert behind_wall_ft(42.0, 50.0, capped, court_width_ft=100, lot_width_ft=100) == 67.0
    assert behind_wall_ft(10.0, 50.0, capped) == 50.0
    assert behind_wall_ft(42.0, 50.0, capped, court_width_ft=40, lot_width_ft=100) == 50.0


def test_a_depth_setback_is_only_taken_from_the_farthest_rear_edge() -> None:
    lot = Polygon(
        [(0, 0), (100, 0), (100, 25), (35, 25), (35, 50), (100, 50), (100, 200), (0, 200)]
    )
    edges = LotEdges(
        Tier.clean,
        (
            Edge(0, 0, 100, 0, 100, 0, EdgeClass.front),
            Edge(100, 0, 100, 25, 25, 90, EdgeClass.side),
            Edge(100, 25, 35, 25, 65, 0, EdgeClass.rear),
            Edge(35, 25, 35, 50, 25, 90, EdgeClass.side),
            Edge(35, 50, 100, 50, 65, 0, EdgeClass.rear),
            Edge(100, 50, 100, 200, 150, 90, EdgeClass.side),
            Edge(100, 200, 0, 200, 100, 0, EdgeClass.rear),
            Edge(0, 200, 0, 0, 200, 90, EdgeClass.side),
        ),
        (0.0,),
        100.0,
        lot.area / lot.convex_hull.area,
    )
    env = buildable(lot, edges, Setbacks(front_ft=5, side_ft=5, rear_ft=5, depth_rear_ft=50))
    # rel6 2026-11-09 (flats/envelope-caps, FOLLOWUPS 157, with this lane's FOLLOWUPS 68):
    # setback strips now end in round caps, so the 5 x 5 ft square each square cap took
    # past the notch's two inward corners comes back less its quarter disc --
    # 2 * (25 - 25 pi / 4) = 10.73 sq ft. The depth yard is still the farthest rear edge's.
    assert env.area == pytest.approx(10_775.0 + 2 * (25 - 25 * math.pi / 4), abs=0.1)


def test_a_150_ft_map_120_2_lot_has_no_frontage_exception_flag(corpus) -> None:
    lot = _lot(corpus, "RM1", 60, 150)
    got = _screen(corpus, _answered(lot, **{FRONTAGE: True, EASTERN: False}))
    assert fact_code(NEIGHBOURS) not in {f.code for f in got.flags}


def test_assumed_corner_is_held_but_measured_noncorner_still_fails(corpus) -> None:
    lot = _lot(corpus, "RM1", 60, 112)
    observed = {**lot.observed, FRONTAGE: False, EASTERN: True}
    observed.pop("corner_lot", None)
    assumed = _screen(corpus, dataclasses.replace(lot, observed=observed))
    measured = _screen(
        corpus,
        _answered(lot, **{FRONTAGE: False, EASTERN: True, "corner_lot": False})
    )
    assert assumed.colour is flag_plan.Colour.yellow
    assert fact_code("corner_lot") in {f.code for f in assumed.flags}
    # rel6 2026-11-09: on flats/pdx-map-120 alone the measured lot missed by 1.67 ft (74 vs
    # 75.67) and was RED. On rel6 the pod stands depth-facing (inferred cause: flats/rel4-fixes,
    # doors may face the street with the long face either way round) and misses by 0.29 ft (74 vs
    # 74.29): inside the drawing slack, so FIT-TIGHT YELLOW. Never GREEN either way.
    assert measured.colour is not flag_plan.Colour.green
    (fit,) = [c for c in measured.checks if c.check == "fit_ft"]
    assert fit.observed < fit.threshold


def test_the_quotes_say_what_the_rules_say() -> None:
    store = ProvenanceStore()
    s = "or/multnomah/portland/33.120/"
    rear_line = store.quote("or/multnomah/portland/33.910/33.910.030.txt#L549-L551")
    assert (
        "For other irregularly shaped lots, the rear lot line is all lot lines that are "
        "most nearly opposite the front lot line."
    ) in rear_line
    assert "sites shown on Map 120-2" in store.quote(s + "33.120.206.txt#L8")
    rule = store.quote(s + "33.120.206.txt#L10")
    assert "more than 160 feet deep" in rule and "90 feet of frontage on a street" in rule
    assert "share a side lot line" in store.quote(s + "33.120.206.txt#L15-L18")
    eastern = store.quote(s + "33.120.220.txt#L26,L28")
    assert "25 percent of the total depth of the site" in eastern and "Map 120-3" in eastern
    assert "No more than 50 percent" in store.quote(s + "33.120.220.txt#L27")
    assert (
        "Corner lots and lots that are up to 100 feet deep are exempt from the Eastern Pattern "
        "Area minimum rear building setback"
    ) in store.quote(s + "33.120.220.txt#L31")


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
    assert shallow.colour is flag_plan.Colour.green
    assert fact_code(NEIGHBOURS) not in {f.code for f in shallow.flags}
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
    # 25% of 166 ft is 41.5 ft of rear yard against Table 120-4's 5 ft.
    # The winning fit orientation can change when that yard changes.
    assert _fit(east).threshold < _fit(west).threshold
    assert _fit(corner).observed == _fit(west).observed
    assert east.colour is flag_plan.Colour.green


def test_the_court_may_run_into_the_eastern_yard_it_is_charged_for(corpus) -> None:
    # 1S2E21CB -00600 (held bound pdx_map_120c, 2026-11-05): RM1, 60.04 x
    # 150.1 ft, Eastern Pattern Area, not a corner. Its rear yard is 25% of
    # 150.1 = 37.5 ft, half of whose area the court may use: 49 ft of court
    # across a 60 ft lot may run 37.5 x 0.5 x 60.04 / 49 = 23 ft into it, so
    # the building and the rest of the court need 80.01 ft of the ~102.6 ft
    # envelope (the bridge's 1-degree search; this one's 30-degree search may
    # pick another court). The court's ground was cut with the same 37.5 ft yard, so it
    # could not run into the yard at all and the fit found 78 ft: RED on a lot
    # whose live layout keeps ~290 sq ft of parking in a 1,125 sq ft cap.
    lot = _lot(corpus, "RM1", 60.04, 150.1)
    got = _screen(corpus, _answered(lot, **{FRONTAGE: False, EASTERN: True, "corner_lot": False}))
    fit = _fit(got)
    # The window reaches the envelope's rear (the court runs on into the
    # yard); before the fix it stopped ~23 ft short (79.5 ft here, 78 ft on
    # the real lot's 2-degree tilt).
    assert fit.observed == pytest.approx(150.1 - 10 - 0.25 * 150.1, abs=1.0)
    assert fit.observed >= fit.threshold
    assert got.colour is flag_plan.Colour.green


def test_the_eastern_court_ground_keeps_the_yard_only_off_the_cap(corpus, rules: RuleSet) -> None:
    # The ground the court may stand on is the lot less the front and side
    # yards: the EPA yard comes off the envelope, never off the ground (the
    # cap is charged in behind_wall_ft instead), or the overlap the cap
    # allows is charged twice.
    from flats.ingest.quadfit import envelope_for

    lot = _answered(_lot(corpus, "RM1", 60.04, 150.1), **{FRONTAGE: False, EASTERN: True, "corner_lot": False})
    ordinary = rules.resolve(PORTLAND, "RM1", POD, lot={"lot_depth_ft": 150.1})
    env = envelope_for(lot, ordinary, depth_rear_ft=0.25 * 150.1)
    front = ordinary.values["setback_front_ft"].value
    assert env.source == "flats"
    _, gy0, _, gy1 = env.ground.bounds
    _, ey0, _, ey1 = env.geom.bounds
    assert ey1 - ey0 == pytest.approx(150.1 - front - 0.25 * 150.1, abs=0.1)
    assert gy1 - gy0 == pytest.approx(150.1 - front, abs=0.1)


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


def test_an_eastern_corner_with_unmeasured_depth_is_not_held_for_the_rear_setback(corpus) -> None:
    lot = _answered(
        _undepthed(_lot(corpus, "RM1", 60, 166)),
        **{FRONTAGE: False, EASTERN: True, "corner_lot": True},
    )
    got = _screen(corpus, lot)
    assert got.colour is flag_plan.Colour.green
    assert "RULE-AMBIGUOUS" not in {f.code for f in got.flags}


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


# FOLLOWUPS 167 item 3 (2026-11-09): 33.120.205 C.3 lets a lot of record off
# Table 120-3 only. RX's row there is the 10 ft front lot line; the 90 ft is
# 33.120.206's, so a lot of record owes it like any other lot (as rel6 did for
# RM1-RM4 by narrowing their relief).


def test_rx_relief_reaches_table_120_3_only(rules: RuleSet) -> None:
    deep = rules.resolve(PORTLAND, "RX", (*POD, FRONTAGE), lot={"lot_depth_ft": 166})
    shallow = rules.resolve(PORTLAND, "RX", (*POD, FRONTAGE), lot={"lot_depth_ft": 160})
    assert deep.get("lot_of_record_relief_base_only") is True
    # the 90 ft arrives by a variant, the 10 ft is the table's own number
    assert deep.values["min_frontage_ft"].value == 90 and deep.values["min_frontage_ft"].when
    assert shallow.values["min_frontage_ft"].value == 10 and not shallow.values["min_frontage_ft"].when


def test_an_rx_lot_of_record_owes_the_ninety_feet(corpus) -> None:
    lot = _lot(corpus, "RX", 60, 166)
    bare = _screen(corpus, _answered(lot, **{FRONTAGE: True, EASTERN: False, NEIGHBOURS: False}))
    held = _screen(corpus, _answered(lot, **{FRONTAGE: True, EASTERN: False}))
    # Before: the lot-of-record relief let the 60 ft off and held it YELLOW.
    assert bare.colour is flag_plan.Colour.red
    (front,) = [c for c in bare.checks if c.check == "min_frontage_ft"]
    assert front.observed == 60 and front.threshold == 90
    assert held.colour is not flag_plan.Colour.green
