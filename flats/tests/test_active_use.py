"""South Hillsboro's Active Use Streets, traced off Figure 12.65.930-A
(flats.geom.active_use; FOLLOWUPS 147).

Steph 2026-11-04 (rulings.yaml 2026-11-04-south-hillsboro-active-use-streets-traced):
trace the sketch, green with a flag. The mechanism on a toy map, then the
traced file, then the screen: the 70% coverage on an Active Use 2 frontage
(Table 12.65.850-1) is never GREEN below 70, GREEN at 70 or more with the
illustrative-map flag; the base zone's maximum front setback is what it was
(12.65.130.A's either/or); lots off the traced streets are answered False.
"""

from __future__ import annotations

import json

import pytest
from shapely.geometry import LineString, box

from flats.geom.active_use import (
    ACTIVE_USE_1,
    ACTIVE_USE_2,
    CLEAR_FT,
    SERVES,
    TOUCHES,
    TRACED,
    TYPES,
    ActiveUse,
    load_active_use,
    observed_active_use,
)
from flats.rules.loader import AREAS_ROOT, load_rules
from flats.rules.resolver import RuleSet
from flats.score import relief, slack
from flats.score.configure import Configuration
from flats.score.flags import Colour, colour_rules, load_registry
from flats.score.screen import AREA_FLAGS, BUILDING_SHARE, screen
from flats.tests.test_round2_rulings import DESIGN, check, facts, fit, rules

pytestmark = pytest.mark.unit

HILLSBORO = "or/washington/hillsboro"
FLAG = "HILLSBORO-ACTIVE-USE-MAP-ILLUSTRATIVE"

#: A toy map: an east-west street at y=0 and one at y=400, a north-south
#: one at x=0.
EW_SOUTH = LineString([(-1000, 0), (1000, 0)])
EW_NORTH = LineString([(-1000, 400), (1000, 400)])
NS_WEST = LineString([(0, -1000), (0, 1000)])

#: A lot 100 x 340 between the two east-west streets, 30 ft back from each
#: centreline, 200 ft east of the north-south one.
FRONT = [200.0, 30.0, 300.0, 30.0, "F"]
SIDE_E = [300.0, 30.0, 300.0, 370.0, "S"]
REAR = [300.0, 370.0, 200.0, 370.0, "R"]
SIDE_W = [200.0, 370.0, 200.0, 30.0, "S"]
BACK_STREET = [300.0, 370.0, 200.0, 370.0, "F"]
#: The same lot on the corner with the north-south street.
CORNER_SIDE = [30.0, 370.0, 30.0, 30.0, "F"]
CORNER_FRONT = [30.0, 30.0, 300.0, 30.0, "F"]


def toy(south: str, north: str = "none", west: str = "none") -> ActiveUse:
    return ActiveUse.build(
        [EW_SOUTH, EW_NORTH, NS_WEST], ["SOUTH ST", "NORTH ST", "WEST AVE"], [south, north, west]
    )


def lot(*edges):
    return [list(e) for e in edges]


# --- the mechanism -----------------------------------------------------------


def test_a_lot_on_one_active_use_street_alone_takes_its_type() -> None:
    assert toy("au2").facts(lot(FRONT, SIDE_E, REAR, SIDE_W)) == {
        TOUCHES: True, ACTIVE_USE_1: False, ACTIVE_USE_2: True,
    }
    assert toy("au1").facts(lot(FRONT, SIDE_E, REAR, SIDE_W)) == {
        TOUCHES: True, ACTIVE_USE_1: True, ACTIVE_USE_2: False,
    }


def test_a_lot_on_ordinary_streets_is_answered_false() -> None:
    assert toy("none").facts(lot(FRONT, SIDE_E, REAR, SIDE_W)) == {
        TOUCHES: False, ACTIVE_USE_1: False, ACTIVE_USE_2: False,
    }


def test_a_mixed_lot_is_flagged_but_held_unanswered() -> None:
    # An Active Use corner with an ordinary street: the coverage is owed on
    # the Active Use frontage alone, which one share for every street line
    # cannot say (coordinator 2026-11-04: hold it YELLOW, with the flag).
    corner = lot(CORNER_FRONT, SIDE_E, REAR, CORNER_SIDE)
    assert toy("au2", west="none").facts(corner) == {TOUCHES: True}
    # Two Active Use types on one lot (a through lot, AU1 behind AU2).
    through = lot(FRONT, SIDE_E, BACK_STREET, SIDE_W)
    assert toy("au2", north="au1").facts(through) == {TOUCHES: True}
    # The same type on both streets is the type.
    assert toy("au2", north="au2").facts(through)[ACTIVE_USE_2] is True


def test_a_street_line_nothing_explains_near_an_active_use_street_answers_nothing() -> None:
    # A street line 200 ft east of WEST AVE with no centreline beside it,
    # inside CLEAR_FT of the Active Use street to the south.
    stray = [400.0, 100.0, 400.0, 200.0, "F"]
    assert toy("au2").facts(lot(stray)) == {}
    # Well clear of every Active Use line it is an ordinary lot.
    far = [400.0, 600.0, 400.0, 700.0, "F"]
    assert toy("au2").facts(lot(far)) == {TOUCHES: False, ACTIVE_USE_1: False, ACTIVE_USE_2: False}
    assert CLEAR_FT >= 120.0


def test_a_lot_without_street_lines_is_read_from_its_outline() -> None:
    traced = load_active_use()
    (x0, y0, _, _) = traced.active[0].bounds
    near = box(x0 + 20, y0 + 20, x0 + 80, y0 + 120)
    far = box(7_570_000, 690_000, 7_570_100, 690_100)
    assert observed_active_use([], SERVES, far.wkb) == {
        TOUCHES: False, ACTIVE_USE_1: False, ACTIVE_USE_2: False,
    }
    assert observed_active_use([], SERVES, near.wkb) == {}
    assert observed_active_use([], SERVES, None) == {}
    assert observed_active_use(lot(FRONT), "or/multnomah/gresham", far.wkb) == {}


def test_an_unknown_type_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown Active Use type"):
        ActiveUse.build([EW_SOUTH], ["SOUTH ST"], ["active_use_2a"])


# --- the traced file ---------------------------------------------------------


def test_the_traced_figure_says_what_it_is_drawn_from() -> None:
    data = json.loads((AREAS_ROOT / TRACED).read_text(encoding="utf-8"))
    src = data["source"]
    assert src["drawn"] is True
    assert "12.65.930-A" in src["map"]
    assert src["sha256"] == "eba9a00705456447d1cc5a45f18377886ccd128c17fa0b2c304f78b8ad2818b0"
    assert "PDF page 889" in src["page"]
    assert "2A" in src["how"] and "Active Use 2" in src["how"]
    kinds = [f["properties"]["active_use"] for f in data["features"]]
    assert set(kinds) <= TYPES
    assert src["counts"] == {k: kinds.count(k) for k in sorted(set(kinds))}
    # The two stretches the figure draws where RLIS has no street.
    drawn_only = [f for f in data["features"] if f["properties"]["rlis_localid"] is None]
    assert len(drawn_only) == 2
    assert all("drawn only" in f["properties"]["note"] for f in drawn_only)


def _beside(line: LineString, side: str, gap: float = 30.0) -> list[object]:
    """A street line ``gap`` ft off ``line`` to one side, as s4 writes it."""
    off = line.parallel_offset(gap, side)
    (x1, y1), (x2, y2) = off.coords[0], off.coords[-1]
    return [x1, y1, x2, y2, "F"]


def _feature(localid: int) -> LineString:
    data = json.loads((AREAS_ROOT / TRACED).read_text(encoding="utf-8"))
    (f,) = [f for f in data["features"] if f["properties"]["rlis_localid"] == localid]
    return LineString(f["geometry"]["coordinates"])


def test_real_lot_lines_read_the_type_the_figure_draws() -> None:
    traced = load_active_use()
    # SE 77th Ave between Deline and Butternut Creek: Active Use 2.
    on_77th = _feature(250901)
    for side in ("left", "right"):
        assert traced.edge_type(_beside(on_77th, side)) == "au2"
    # SE Deline St east of Cornelius Pass Rd: Active Use 1.
    assert traced.edge_type(_beside(_feature(251680), "left")) == "au1"
    # SE Blanton St west of Reed Dr (the figure's 2A): Active Use 2.
    assert traced.edge_type(_beside(_feature(248692), "right")) == "au2"
    # A lot line on 77th alone is an Active Use 2 lot.
    got = observed_active_use([_beside(on_77th, "left")], SERVES)
    assert got == {TOUCHES: True, ACTIVE_USE_1: False, ACTIVE_USE_2: True}


def test_a_hillsboro_lot_far_from_south_hillsboro_is_answered_false() -> None:
    # A street line in north Hillsboro, miles from either core.
    edges = [[7_560_000.0, 700_000.0, 7_560_100.0, 700_000.0, "F"]]
    assert observed_active_use(edges, SERVES) == {
        TOUCHES: False, ACTIVE_USE_1: False, ACTIVE_USE_2: False,
    }


# --- the rules ---------------------------------------------------------------


@pytest.fixture(scope="module")
def corpus() -> RuleSet:
    return RuleSet(load_rules(strict=True))


@pytest.mark.parametrize("zone", ["R-4.5", "MR-1", "MR-2", "MR-3"])
def test_the_coverage_binds_only_on_the_active_use_frontage(corpus: RuleSet, zone: str) -> None:
    off = corpus.resolve(HILLSBORO, zone, ())
    assert off.get("building_frontage_min_pct") is None
    assert off.get("min_ground_story_ft") is None
    au2 = corpus.resolve(HILLSBORO, zone, (ACTIVE_USE_2,))
    assert (au2.get("building_frontage_min_pct"), au2.get("building_frontage_band_ft")) == (70, 15)
    assert au2.get("min_ground_story_ft") is None
    au1 = corpus.resolve(HILLSBORO, zone, (ACTIVE_USE_1,))
    assert (au1.get("building_frontage_min_pct"), au1.get("building_frontage_band_ft")) == (75, 10)
    # 12.65.850.D.6: 15 ft floor to ceiling on an Active Use 1 frontage.
    assert au1.get("min_ground_story_ft") == 15
    # 12.65.130.A: the maximum setback is the base zone's, as it was -- none.
    for got in (off, au1, au2):
        assert got.get("setback_front_max_ft") is None
    # The facts are levers, so an unanswered one holds the lot out of GREEN.
    field = corpus.layers[HILLSBORO].zones[zone].values["building_frontage_min_pct"]
    assert {ACTIVE_USE_1, ACTIVE_USE_2} <= field.levers


def test_the_base_maximum_elsewhere_is_unchanged(corpus: RuleSet) -> None:
    for conds in ((), (ACTIVE_USE_2,), (ACTIVE_USE_1,)):
        assert corpus.resolve(HILLSBORO, "SCR-MD", conds).get("setback_front_max_ft") == 13


# --- the screen --------------------------------------------------------------

#: Table 12.65.850-1's Active Use 2 row, in a zone with no maximum front
#: setback (the South Hillsboro multi-dwelling zones).
AU2 = {"building_frontage_min_pct": 70, "building_frontage_band_ft": 15, "setback_side_ft": 10}


def _run(lot_facts, rule_set, conditions=()):
    return screen(
        rule_set,
        lot_facts,
        DESIGN,
        fit(),
        policy=slack.SlackPolicy(tolerance={"fit_ft": 0.5}),
        relief=relief.load_policy(),
        config=Configuration(conditions=tuple(sorted(conditions))),
    )


def test_coverage_below_seventy_on_an_active_use_2_frontage_is_not_green() -> None:
    # Drawn at 65 on an 80 ft street: one pod could fill 70, so held.
    short = _run(facts(street_lines_ft=(80.0,), building_frontage_pct=(65.0,)), rules(**AU2), (TOUCHES,))
    assert short.colour is not Colour.green
    assert BUILDING_SHARE in short.unchecked
    # 100 ft of street inside 10 ft side yards: one pod fills 56, two do
    # not stand -- a measured miss, RED.
    wide = _run(facts(street_lines_ft=(100.0,)), rules(**AU2), (TOUCHES,))
    assert wide.colour is Colour.red
    assert check(wide, BUILDING_SHARE).verdict is not slack.Verdict.passes


def test_seventy_or_more_is_green_with_the_flag() -> None:
    entry = load_registry()[FLAG]
    assert entry.severity < colour_rules().yellow_at_severity
    assert AREA_FLAGS[TOUCHES][0] == FLAG
    got = _run(facts(street_lines_ft=(80.0,), building_frontage_pct=(72.0,)), rules(**AU2), (TOUCHES,))
    assert check(got, BUILDING_SHARE).verdict is slack.Verdict.passes
    assert got.colour is Colour.green
    (flag,) = [f for f in got.flags if f.code == FLAG]
    assert flag.by == "ACTIVE_USE_ILLUSTRATIVE"


def test_a_lot_off_the_traced_streets_is_unchanged() -> None:
    plain = _run(facts(street_lines_ft=(80.0,)), rules(setback_side_ft=10))
    off = _run(facts(street_lines_ft=(80.0,)), rules(setback_side_ft=10), ())
    assert plain.colour is off.colour is Colour.green
    assert not [f for f in off.flags if f.code == FLAG]
