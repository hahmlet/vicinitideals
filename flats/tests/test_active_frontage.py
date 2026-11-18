"""Beaverton's Active Frontage Design Map, traced off Figure 70.20.10.6.2
(flats.geom.active_frontage; FOLLOWUPS 105 item 1).

70.20.10.6.D: a facade fronting a mapped street meets the Active Ground
Floor Design -- Type A the Non-residential design (16 ft floor to floor,
S1.a), Type B that or the Residential design (12 ft, S2.c) -- and every
other facade is exempt. The mechanism on a toy map (a lot on a Type A
street, one off it, one within doubt of a traced end), then the traced
file, then the screen: the screened pod's 9 ft 2 in ground floor fails on
a mapped street, and the standard is gone off it.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from shapely.geometry import LineString, box, shape

from flats.designs.model import load_catalog
from flats.geom.active_frontage import (
    AREA_C,
    AREA_D,
    CLEAR_FT,
    DOUBT_FT,
    ON_MAP,
    SERVES,
    TRACED,
    TYPE_A,
    TYPES,
    ActiveFrontage,
    load_active_frontage,
    observed_active_frontage,
)
from flats.ingest.quadfit import OBSERVABLE
from flats.rules.conditions import CONDITIONS
from flats.rules.loader import AREAS_ROOT, load_rules
from flats.rules.resolver import RuleSet, Verdict as RuleVerdict
from flats.score import relief, slack
from flats.score.flags import Colour
from flats.score.screen import screen
from flats.tests.test_round2_rulings import check, facts, fit

pytestmark = pytest.mark.unit

OFF = {ON_MAP: False, TYPE_A: False}
DOWNTOWN = ("RC-BC", "RC-OT", "RC-MU", "RC-DT")

#: A toy map: an east-west street at y=0, Type A west of x=0 and unmapped
#: east of it (a line that ends mid-block); an east-west street at y=400;
#: a north-south street at x=-600.
SOUTH_A = LineString([(-1000, 0), (0, 0)])
SOUTH_NONE = LineString([(0, 0), (1000, 0)])
NORTH = LineString([(-1000, 400), (1000, 400)])
WEST = LineString([(-600, -1000), (-600, 1000)])


def toy(south_a: str = "a", north: str = "none", west: str = "none", drawn=()) -> ActiveFrontage:
    lines = [SOUTH_A, SOUTH_NONE, NORTH, WEST, *(g for g, _ in drawn)]
    kinds = [south_a, "none", north, west, *(k for _, k in drawn)]
    only = [False] * 4 + [True] * len(drawn)
    return ActiveFrontage.build(lines, ["SOUTH ST", "SOUTH ST", "NORTH ST", "WEST AVE", *("" for _ in drawn)], kinds, only)


def street(x1, y1, x2, y2):
    return [float(x1), float(y1), float(x2), float(y2), "F"]


def side(x1, y1, x2, y2):
    return [float(x1), float(y1), float(x2), float(y2), "S"]


def lot_at(x0: float, x1: float, front_y: float = 30.0, back_y: float = 370.0, back_street: bool = False):
    """A lot from x0 to x1 between the two east-west streets."""
    back = street if back_street else side
    edges = [
        street(x0, front_y, x1, front_y),
        side(x1, front_y, x1, back_y),
        back(x1, back_y, x0, back_y),
        side(x0, back_y, x0, front_y),
    ]
    return edges, box(x0, front_y, x1, back_y)


# --- the mechanism -----------------------------------------------------------


def test_a_lot_on_a_type_a_street_owes_the_type_a_floor() -> None:
    edges, outline = lot_at(-400, -300)
    assert toy().facts(edges, outline) == {ON_MAP: True, TYPE_A: True}


def test_a_lot_on_a_type_b_street_owes_the_residential_floor() -> None:
    edges, outline = lot_at(-400, -300)
    assert toy(south_a="b").facts(edges, outline) == {ON_MAP: True, TYPE_A: False}


def test_a_lot_off_every_mapped_street_is_exempt() -> None:
    # 300 ft east of where the Type A line ends.
    edges, outline = lot_at(300, 400)
    assert toy().facts(edges, outline) == OFF
    # Without an outline it reads from its lines alone.
    assert toy().facts(edges) == OFF


def test_a_lot_within_doubt_of_a_traced_end_is_held() -> None:
    # The lot's frontage begins 20 ft past the traced end of the Type A line:
    # inside DOUBT_FT, so the drawn line may run on in front of it.
    edges, outline = lot_at(20, 120)
    assert toy().facts(edges, outline) == {}
    # Just past the band it is answered.
    clear = DOUBT_FT + 40
    edges, outline = lot_at(clear, clear + 100)
    assert toy().facts(edges, outline) == OFF


def test_a_mapped_and_an_unmapped_street_is_held() -> None:
    # A through lot: Type A in front, an unmapped street behind.
    edges, outline = lot_at(-400, -300, back_street=True)
    assert toy().facts(edges, outline) == {}
    # Type A in front, Type B behind: on the map, with a Type A line.
    assert toy(north="b").facts(edges, outline) == {ON_MAP: True, TYPE_A: True}
    assert toy(south_a="b", north="b").facts(edges, outline) == {ON_MAP: True, TYPE_A: False}


def test_a_doubtful_run_is_held() -> None:
    edges, outline = lot_at(-400, -300)
    assert toy(south_a="doubt").facts(edges, outline) == {}


def test_a_street_line_nothing_explains_near_a_mapped_line_is_held() -> None:
    stray = [street(-300, 100, -300, 200)]
    assert toy().facts(stray, box(-310, 100, -300, 200)) == {}
    # Well clear of every mapped line it is an ordinary lot.
    far = [street(400, 600, 400, 700)]
    assert toy().facts(far, box(400, 600, 410, 700)) == OFF
    assert CLEAR_FT >= 120.0


def test_an_outline_near_a_drawn_only_line_is_held() -> None:
    # The figure draws a Type B frontage where no street runs (x=300, y 100-300).
    drawn = [(LineString([(300, 100), (300, 300)]), "b")]
    edges, outline = lot_at(320, 420)
    assert toy(drawn=drawn).facts(edges, outline) == {}
    assert toy().facts(edges, outline) == OFF


def test_a_lot_without_street_lines_is_read_from_its_outline() -> None:
    near = box(-400, 30, -300, 130)
    far = box(400, 600, 500, 700)
    assert toy().facts([], near) == {}
    assert toy().facts([], far) == OFF
    assert toy().facts([]) == {}


def test_unknown_or_drawn_only_none_types_are_refused() -> None:
    with pytest.raises(ValueError, match="unknown frontage type"):
        ActiveFrontage.build([SOUTH_A], ["SOUTH ST"], ["type_c"])
    with pytest.raises(ValueError, match="drawn-only line must be Type A or B"):
        ActiveFrontage.build([SOUTH_A], ["SOUTH ST"], ["none"], [True])


# --- the named tax lots and the layer ------------------------------------------


def test_area_c_takes_type_a_and_area_d_is_held() -> None:
    far = box(7_605_000, 668_000, 7_605_100, 668_100).wkb
    for tlid in AREA_C:
        assert observed_active_frontage([], SERVES, far, tlid) == {ON_MAP: True, TYPE_A: True}
    for tlid in AREA_D:
        assert observed_active_frontage([], SERVES, far, tlid) == {}
    # TLIDs are matched with their spaces taken out (TLIDs can carry spaces).
    assert observed_active_frontage([], SERVES, far, "1S110CC 00400") == {ON_MAP: True, TYPE_A: True}
    assert observed_active_frontage([], SERVES, far, "1S110CC00500") == OFF


def test_only_beaverton_is_answered() -> None:
    edges, outline = lot_at(300, 400)
    assert observed_active_frontage(edges, "or/washington/hillsboro", outline.wkb) == {}
    assert observed_active_frontage([], SERVES, None) == {}


def test_the_facts_are_registered_and_observed() -> None:
    for name in (ON_MAP, TYPE_A):
        assert name in CONDITIONS
        assert name in OBSERVABLE


# --- the traced file ---------------------------------------------------------


def _traced():
    return json.loads((AREAS_ROOT / TRACED).read_text(encoding="utf-8"))


def test_the_traced_figure_says_what_it_is_drawn_from() -> None:
    src = _traced()["source"]
    assert src["drawn"] is True
    assert "70.20.10.6.2" in src["map"]
    assert src["sha256"] == "f7af69342c4bf44571d9ea319d7aee994d0713d252da891aff49eb69a3f522a9"
    assert src["retrieved"] == "2026-11-13"
    assert src["doubt_band_ft"] == DOUBT_FT


def test_every_traced_line_is_typed_and_both_types_are_drawn() -> None:
    feats = _traced()["features"]
    kinds = [f["properties"]["frontage"] for f in feats]
    assert set(kinds) <= TYPES
    assert {"a", "b", "none"} <= set(kinds)
    only = [f for f in feats if f["properties"].get("drawn_only")]
    assert len(only) == 3 and all(f["properties"]["frontage"] in ("a", "b") for f in only)


def _run_of(kind: str, name: str) -> LineString:
    """The longest straight-ish traced run of ``kind`` on ``name``."""
    runs = [
        shape(f["geometry"])
        for f in _traced()["features"]
        if f["properties"]["frontage"] == kind and f["properties"]["name"] == name
    ]
    return max(runs, key=lambda g: g.length)


def _lot_beside(run: LineString, at: float, width: float = 50.0, depth: float = 100.0, off: float = 30.0):
    """A lot fronting ``run`` at ``at`` ft along it, ``off`` ft from the centreline."""
    a = run.interpolate(at)
    b = run.interpolate(at + width)
    dx, dy = b.x - a.x, b.y - a.y
    n = (dx * dx + dy * dy) ** 0.5
    nx, ny = -dy / n * off, dx / n * off
    fx1, fy1, fx2, fy2 = a.x + nx, a.y + ny, b.x + nx, b.y + ny
    kx, ky = nx / off * depth, ny / off * depth
    edges = [
        street(fx1, fy1, fx2, fy2),
        side(fx2, fy2, fx2 + kx, fy2 + ky),
        side(fx2 + kx, fy2 + ky, fx1 + kx, fy1 + ky),
        side(fx1 + kx, fy1 + ky, fx1, fy1),
    ]
    from shapely.geometry import Polygon

    return edges, Polygon([(fx1, fy1), (fx2, fy2), (fx2 + kx, fy2 + ky), (fx1 + kx, fy1 + ky)])


def test_a_lot_on_traced_hall_boulevard_north_is_type_a() -> None:
    run = _run_of("a", "SW HALL BLVD")
    assert run.length > 400
    edges, outline = _lot_beside(run, run.length / 2 - 25)
    assert observed_active_frontage(edges, SERVES, outline.wkb, "1S1TEST00100") == {ON_MAP: True, TYPE_A: True}


def test_a_lot_on_a_traced_type_b_street_is_type_b() -> None:
    feats = [
        f for f in _traced()["features"]
        if f["properties"]["frontage"] == "b" and not f["properties"].get("drawn_only")
    ]
    run = shape(max(feats, key=lambda f: shape(f["geometry"]).length)["geometry"])
    assert run.length > 200
    edges, outline = _lot_beside(run, run.length / 2 - 25)
    assert observed_active_frontage(edges, SERVES, outline.wkb) == {ON_MAP: True, TYPE_A: False}


def test_a_lot_far_from_downtown_is_exempt() -> None:
    lot = box(7_605_000, 668_000, 7_605_100, 668_100)
    edges = [street(7_605_000, 668_000, 7_605_100, 668_000)]
    assert observed_active_frontage(edges, SERVES, lot.wkb) == OFF


def test_the_trace_loads() -> None:
    traced = load_active_frontage()
    assert traced.mapped and traced.marked
    assert len(traced.types) == len(traced.streets.lines)


# --- the screen --------------------------------------------------------------


@pytest.fixture(scope="module")
def corpus() -> RuleSet:
    return RuleSet(load_rules(strict=True))


def _screen(corpus: RuleSet, zone: str, held: tuple[str, ...]):
    resolved = replace(corpus.resolve(SERVES, zone, held), verdict=RuleVerdict.trusted)
    pod = load_catalog().latest("pod80x25")
    return screen(
        resolved,
        facts(street_lines_ft=(80.0,)),
        pod,
        fit(),
        policy=slack.SlackPolicy(tolerance={"fit_ft": 0.5}),
        relief=relief.load_policy(),
    )


@pytest.mark.parametrize("zone", DOWNTOWN)
def test_the_screened_pod_fails_on_a_type_b_street(corpus: RuleSet, zone: str) -> None:
    pod = load_catalog().latest("pod80x25")
    assert pod.ground_story_ft is not None and pod.ground_story_ft < 12
    got = _screen(corpus, zone, (ON_MAP,))
    assert check(got, "min_ground_story_ft").verdict is slack.Verdict.fails
    assert got.colour is Colour.red


@pytest.mark.parametrize("zone", DOWNTOWN)
def test_off_the_map_the_ground_floor_is_not_asked(corpus: RuleSet, zone: str) -> None:
    got = _screen(corpus, zone, ())
    assert check(got, "min_ground_story_ft") is None
