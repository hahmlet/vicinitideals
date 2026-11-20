"""The fire route on a lot line that faces a wide road (rel10d move read,
2026-11-19).

quadfit s4 calls a lot line a street's across a right-of-way up to 150 ft
wide since 2026-11-18, and the plan is laid out fronting that line. The fire
route stands a truck only within 50 ft of a road's centre line
(:data:`flats.fit.fire.MAX_GAP_FT`), so on such a line no truck stood, the
hose was walked from the lot's other street, and 74 lots went YELLOW to RED.
The real lot here is Beaverton 1S126BC01501 on Scholls Ferry Rd, its centre
line 53.5 ft from the lot line.

Steph ruled 2026-11-19 that an engine standing on a wide main road counts
("wide main road, I'm good with green"), and the same of a state highway
("The fire chief makes the call, but I'd say it's green"): where the route
reaches with the engine on the wide road the fire check is made on that
route, and FIRE-WIDE-ROAD -- a note below the yellow line -- says how far out
the road runs. Never from a line on a freeway, a ramp or a railroad; a road
with a second carriageway or a frontage road close beyond it cannot be told
from a freeway and is held YELLOW (FIRE-ROAD-UNCLEAR); a route that misses
from the wide road too is RED.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("shapely")

import shapely  # noqa: E402
from shapely import affinity  # noqa: E402

from flats.encode.load import load_trusted  # noqa: E402
from flats.fit import fire  # noqa: E402
from flats.ingest.quadfit import FIRE_WIDE_ROAD_REACH_FT, lot_from_row, screen_lot  # noqa: E402
from flats.score import relief, slack  # noqa: E402
from flats.score.flags import registry  # noqa: E402
from flats.score.screen import FACT_UNOBSERVED, FIRE_WIDE_ROAD, Triage  # noqa: E402
from flats.score.slack import Verdict  # noqa: E402
from flats.tests.test_fire import check, facts, pod, run  # noqa: E402

FX = json.loads((Path(__file__).parent / "fixtures" / "fire_wide_road_lot.json").read_text(encoding="utf-8"))
OX, OY = FX["origin"]


def _world(wkt: str):
    return affinity.translate(shapely.from_wkt(wkt), OX, OY)


def _row(which: str, *, kinds: list[str | None] | None = None) -> dict[str, object]:
    """The lot as quadfit s4 cut it before (``base``) and after (``new``)
    the wide-road test."""
    cut = FX[which]
    edges = [[x1 + OX, y1 + OY, x2 + OX, y2 + OY, cls] for x1, y1, x2, y2, cls in cut["edges"]]
    return {
        "TLID": FX["tlid"],
        "jurisdiction": FX["jurisdiction"],
        "zone": FX["zone"],
        "tier": cut["tier"],
        "area_sqft": FX["area_sqft"],
        "frontage_ft": cut["frontage_ft"],
        "lot_width_ft": None,
        "lot_depth_ft": None,
        "edges_json": json.dumps(edges),
        "front_bearings_json": json.dumps(cut["fb"]),
        "street_kind_json": json.dumps(cut["kinds"] if kinds is None else kinds),
        "fronts_cul_de_sac": False,
        "split_zone": False,
        "ovl_fema_sfha": False,
        "ovl_fema_floodway": False,
        "sewer_main_dist_ft": 12.0,
        "in_sewer_district": None,
        "wkb": shapely.to_wkb(_world(FX["env"])),
        "lot_wkb": shapely.to_wkb(_world(FX["lot"])),
    }


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


@pytest.fixture(scope="module")
def roads():
    """The roads a truck can use near the lot: Scholls Ferry Rd, Hall Blvd
    and Washington Square Rd; never the Highway 217 ramp."""
    lines = [_world(wkt) for _, kind, _, wkt in FX["streets"] if kind in fire.TRUCK_TYPES]
    assert len(lines) == len(FX["streets"]) - 1
    return shapely.STRtree(lines), np.array(lines, dtype=object)


def _flags(result) -> dict[str, object]:
    return {f.code: f for f in result.flags}


def _divided(roads, name: str = "SCHOLLS FERRY", beyond_ft: float = 40.0):
    """``roads`` with a second carriageway drawn ``beyond_ft`` past each
    piece of ``name``, on the side away from the lot."""
    lot = _world(FX["lot"])
    lines = list(roads[1])
    for street, kind, _, wkt in FX["streets"]:
        if street != name or kind not in fire.TRUCK_TYPES:
            continue
        line = _world(wkt)
        (fx, fy), (tx, ty) = shapely.shortest_line(lot.centroid, line).coords
        gap = np.hypot(tx - fx, ty - fy)
        lines.append(affinity.translate(line, (tx - fx) / gap * beyond_ft, (ty - fy) / gap * beyond_ft))
    return shapely.STRtree(lines), np.array(lines, dtype=object)


def _screened(corpus, policies, roads, which: str, **over):
    lot = lot_from_row(_row(which, **over), corpus.layers)
    (s,) = screen_lot(
        lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0, roads=roads
    )
    return s


def test_the_wide_road_line_is_past_the_reach_a_truck_is_stood_within(roads) -> None:
    """Scholls Ferry Rd's centre line runs 53.5 ft from the lot's long line:
    no truck on the reading the screen clears a lot on, one on the wide
    reading, its hose from the road's middle less the half road."""
    x1, y1, x2, y2, cls = FX["new"]["edges"][-1]
    assert cls == "F" and FX["base"]["edges"][-1][4] == "S"
    mid = np.array([[(x1 + x2) / 2 + OX, (y1 + y2) / 2 + OY]])
    assert not np.isfinite(fire.street_offsets(mid, *roads)).any()
    (wide,) = fire.street_offsets(mid, *roads, max_gap_ft=FIRE_WIDE_ROAD_REACH_FT)
    assert wide == pytest.approx(53.5 - fire.HALF_ROAD_FT, abs=0.5)
    strict = fire.point_offset(*roads, max_gap_ft=FIRE_WIDE_ROAD_REACH_FT)(mid)
    assert strict[0] == pytest.approx(53.5, abs=0.5)
    assert not np.isfinite(fire.point_offset(*roads)(mid)).any()


def test_the_lot_reached_the_building_before_the_wide_road_line_was_a_street_line(
    corpus, policies, roads
) -> None:
    s = _screened(corpus, policies, roads, "base")
    assert s.facts.fire_route_tried and s.facts.fire_route_ft <= 150.0
    assert s.facts.fire_route_wide_ft is None
    assert check(s.screening, "fire_access_ft").verdict is Verdict.passes


def test_a_plan_the_hose_reaches_with_the_engine_on_the_wide_road_passes(corpus, policies, roads) -> None:
    """The plan fronting Scholls Ferry Rd: the hose from the lot's other
    street misses, the hose from Scholls Ferry reaches. The fire check is
    made on that route and passes; a note says which road it rests on."""
    s = _screened(corpus, policies, roads, "new")
    assert s.facts.fire_route_tried and s.facts.fire_route_ft > 150.0
    wide = s.facts.fire_route_wide_ft
    assert wide is not None and wide <= 150.0
    assert s.facts.fire_wide_gap_ft == pytest.approx(53.5, abs=1.0)
    assert not s.facts.fire_on_state_road and not s.facts.fire_road_unclear
    for result in (s.screening, s.signed):
        made = check(result, "fire_access_ft")
        assert made.verdict is Verdict.passes and made.observed == wide
        assert "fire_access_ft" not in result.unchecked
    note = _flags(s.signed)["FIRE-WIDE-ROAD"]
    assert note.by == FIRE_WIDE_ROAD and note.bounds == (wide, 150.0)
    assert "wide road" in note.source and "53 ft" in note.source
    # Below the yellow line: it marks the answer, and holds nothing.
    assert registry()["FIRE-WIDE-ROAD"].severity == 1
    assert "FIRE-ROAD-UNCLEAR" not in _flags(s.signed)


def test_the_hose_starts_on_the_wide_road_where_the_codes_reading_starts_it(corpus, policies, roads) -> None:
    """Steph 2026-10-05 stands: with no curb and no width measured the hose
    starts at the road's middle -- the 53.5 ft is all in the route."""
    s = _screened(corpus, policies, roads, "new")
    x1, y1, x2, y2, _ = FX["new"]["edges"][-1]
    line = [(x1 + OX, y1 + OY, x2 + OX, y2 + OY)]
    from shapely.geometry import Polygon

    building = Polygon(s.drawing["building"])
    lot = _world(FX["lot"])
    middle = fire.route_ft(building, lot, line, fire.point_offset(*roads, max_gap_ft=FIRE_WIDE_ROAD_REACH_FT))
    at_line = fire.route_ft(building, lot, line, None)
    assert s.facts.fire_route_wide_ft <= middle + 1e-6
    assert middle - at_line == pytest.approx(53.5, abs=3.0)


def test_a_wide_road_with_a_second_carriageway_beyond_it_is_held_yellow(corpus, policies, roads) -> None:
    """Scholls Ferry Rd drawn as two carriageways 40 ft apart: not told from
    a freeway, so no engine is stood across the line and the lot is held --
    never GREEN, never RED on the fire route."""
    s = _screened(corpus, policies, _divided(roads), "new")
    assert s.facts.fire_route_ft > 150.0
    assert s.facts.fire_route_wide_ft is None and s.facts.fire_road_unclear
    for result in (s.screening, s.signed):
        assert check(result, "fire_access_ft") is None
        assert "fire_access_ft" in result.unchecked
        assert result.triage is not Triage.green
    assert FACT_UNOBSERVED in s.signed.reasons
    codes = set(_flags(s.signed))
    assert "FIRE-ROAD-UNCLEAR" in codes and "FIRE-WIDE-ROAD" not in codes
    # A second line 300 ft beyond is the next street over: the road is clear.
    s = _screened(corpus, policies, _divided(roads, beyond_ft=300.0), "new")
    assert s.facts.fire_route_wide_ft is not None and not s.facts.fire_road_unclear


def test_a_route_that_misses_from_the_wide_road_too_stays_red(corpus, policies, roads) -> None:
    """Scholls Ferry Rd gone from the roads: Hall Blvd and Washington Square
    Rd are not the road the line faces, or lie past 150 ft. The miss stands."""
    lines = [_world(wkt) for name, kind, _, wkt in FX["streets"] if kind in fire.TRUCK_TYPES and name != "SCHOLLS FERRY"]
    s = _screened(corpus, policies, (shapely.STRtree(lines), np.array(lines, dtype=object)), "new")
    assert s.facts.fire_route_wide_ft is None and not s.facts.fire_road_unclear
    if s.facts.fire_route_tried:
        assert check(s.signed, "fire_access_ft").verdict is Verdict.fails
        assert s.signed.triage is Triage.red
    assert "FIRE-WIDE-ROAD" not in _flags(s.signed)


def test_an_ordinary_lots_fire_reading_is_what_it_was(corpus, policies, roads, monkeypatch) -> None:
    """The lot before the wide-road line was a street line, and a lot that
    fronts a state highway in the ordinary way: screened with the wide-road
    reading and with it taken out, the answers are the same to the byte."""
    from flats.ingest import quadfit

    def both(make):
        with_reading = make()
        with monkeypatch.context() as patch:
            patch.setattr(quadfit, "_wide_road_read", lambda out, *a, **k: out)
            return with_reading, make()

    for make in (
        lambda: _screened(corpus, policies, roads, "base"),
        lambda: _state_case(corpus, policies, "32E16BB06000", nearer_ft=5.0),
        lambda: _state_case(corpus, policies, "22E19DD02700"),
    ):
        one, two = both(make)
        assert one.facts.fire_route_tried and one.facts.fire_route_ft <= 150.0
        for name in ("facts", "screening", "signed"):
            assert repr(getattr(one, name)) == repr(getattr(two, name)), name
        assert "FIRE-WIDE-ROAD" not in _flags(one.signed)


@pytest.mark.parametrize("kind", ["freeway", "limited", "rail", "drive_off_lot", None])
def test_no_truck_is_stood_off_a_line_that_is_not_a_public_street(corpus, policies, roads, kind) -> None:
    """The same line facing a freeway, a ramp, a railroad or a drive: the
    wide reading is not taken, and the miss stands."""
    kinds = [*FX["new"]["kinds"][:-1], kind]
    s = _screened(corpus, policies, roads, "new", kinds=kinds)
    assert s.facts.fire_route_wide_ft is None
    assert not s.facts.fire_on_state_road and not s.facts.fire_road_unclear
    if s.facts.fire_route_tried:
        assert s.facts.fire_route_ft is None or s.facts.fire_route_ft > 150.0
    assert not {"FIRE-WIDE-ROAD", "FIRE-ROAD-UNCLEAR"} & set(_flags(s.signed))
    assert s.signed.triage is not Triage.green


def test_the_screen_passes_a_lot_reached_from_a_wide_road() -> None:
    result = run(facts(fire_route_ft=208.0, fire_route_tried=True, fire_route_wide_ft=130.0, fire_wide_gap_ft=61.0))
    made = check(result, "fire_access_ft")
    assert made.verdict is Verdict.passes and made.observed == 130.0
    assert result.triage is Triage.green
    note = _flags(result)["FIRE-WIDE-ROAD"]
    assert note.bounds == (130.0, 150.0) and "wide road" in note.source and "61 ft" in note.source
    # Missed from the wide road too: RED, as before.
    result = run(facts(fire_route_ft=208.0, fire_route_tried=True, fire_route_wide_ft=170.0))
    assert result.triage is Triage.red
    made = check(result, "fire_access_ft")
    assert made.verdict is Verdict.fails and made.observed == 208.0
    assert "FIRE-WIDE-ROAD" not in _flags(result)
    # Reached on the code's reading: the wide reading is never read.
    result = run(facts(fire_route_ft=120.0, fire_route_tried=True, fire_route_wide_ft=100.0))
    assert result.triage is Triage.green
    assert check(result, "fire_access_ft").observed == 120.0
    assert "FIRE-WIDE-ROAD" not in _flags(result)
    # No route from any ordinary street, one from the wide road.
    result = run(facts(fire_route_ft=None, fire_route_tried=True, fire_route_wide_ft=120.0))
    assert result.triage is Triage.green and "FIRE-WIDE-ROAD" in _flags(result)
    # A route nobody looked for is not made by a number.
    result = run(facts(fire_route_ft=None, fire_route_tried=False, fire_route_wide_ft=120.0))
    assert check(result, "fire_access_ft") is None and "FIRE-WIDE-ROAD" not in _flags(result)
    # The dead end's and the narrow street's questions come first.
    for held, code in (("fire_route_freed_ft", "FIRE-DEAD-END"), ("fire_route_row_ft", "FIRE-NARROW-STREET")):
        result = run(facts(fire_route_ft=208.0, fire_route_tried=True, fire_route_wide_ft=110.0, **{held: 120.0}))
        codes = set(_flags(result))
        assert code in codes and "FIRE-WIDE-ROAD" not in codes
        assert result.triage not in (Triage.green, Triage.red)


def test_the_screen_holds_a_road_not_told_from_a_freeway_yellow() -> None:
    for route in (208.0, 134.0, None):
        result = run(facts(fire_route_ft=route, fire_route_tried=True, fire_road_unclear=True))
        assert check(result, "fire_access_ft") is None
        assert FACT_UNOBSERVED in result.reasons
        assert result.triage not in (Triage.green, Triage.red)
        codes = set(_flags(result))
        assert "FIRE-ROAD-UNCLEAR" in codes and "FIRE-WIDE-ROAD" not in codes
    # Yellow-level: a severity that holds a lot.
    assert registry()["FIRE-ROAD-UNCLEAR"].severity >= 5
    # A wide reading beside it is not a pass.
    result = run(
        facts(fire_route_ft=208.0, fire_route_tried=True, fire_route_wide_ft=120.0, fire_road_unclear=True)
    )
    assert result.triage not in (Triage.green, Triage.red)


# -- a route that stands the engine on a state highway across a wide road ----
#
# rel10d move read item 6 (2026-11-19). A wide-road line can still have
# points inside the 50 ft a truck is stood within, where the road bends
# toward the lot: Oregon City 32E16BB06000's long line has its midpoint
# 50.01 ft from Highway 213's centre line and 20 of its 40 points inside
# 50 ft, and the lot went RED to GREEN on a 134 ft route from the highway.
# The buildings are the ones the rel10d bound drew.

STATE = json.loads(
    (Path(__file__).parent / "fixtures" / "fire_state_road_lots.json").read_text(encoding="utf-8")
)


def _state_case(
    corpus,
    policies,
    tlid: str,
    *,
    retype: dict[int, int] | None = None,
    nearer_ft: float = 0.0,
    second_ft: float = 0.0,
    kinds: dict[str, str] | None = None,
):
    """The lot fire-checked on the building the bound drew, its roads typed
    as filed (``retype``: one RLIS TYPE read as another; ``nearer_ft``: the
    state highway moved that far toward the lot's wide-road line;
    ``second_ft``: a second carriageway drawn that far beyond it; ``kinds``:
    s4's ``street`` kind read as another)."""
    import dataclasses

    from flats.ingest.quadfit import fire_checked

    fx = STATE[tlid]
    ox, oy = fx["origin"]

    def world(wkt: str):
        return affinity.translate(shapely.from_wkt(wkt), ox, oy)

    cut = fx["new"]
    edges = [[x1 + ox, y1 + oy, x2 + ox, y2 + oy, cls] for x1, y1, x2, y2, cls in cut["edges"]]
    row = {
        "TLID": fx["tlid"],
        "jurisdiction": fx["jurisdiction"],
        "zone": fx["zone"],
        "tier": cut["tier"],
        "area_sqft": fx["area_sqft"],
        "frontage_ft": cut["frontage_ft"],
        "lot_width_ft": cut["w"],
        "lot_depth_ft": cut["d"],
        "edges_json": json.dumps(edges),
        "front_bearings_json": json.dumps(cut["fb"]),
        "street_kind_json": json.dumps([(kinds or {}).get(k, k) for k in cut["kinds"]]),
        "fronts_cul_de_sac": False,
        "split_zone": False,
        "ovl_fema_sfha": False,
        "ovl_fema_floodway": False,
        "sewer_main_dist_ft": 12.0,
        "in_sewer_district": None,
        "wkb": shapely.to_wkb(world(fx["env"])),
        "lot_wkb": shapely.to_wkb(world(fx["lot"])),
    }
    types = [(retype or {}).get(kind, kind) for _, kind, _, _, _ in fx["streets"]]
    lines = [world(street[4]) for street in fx["streets"]]
    if nearer_ft or second_ft:
        x1, y1, x2, y2, _ = max(edges, key=lambda e: (e[4] == "F") * np.hypot(e[2] - e[0], e[3] - e[1]))
        mid = shapely.Point((x1 + x2) / 2, (y1 + y2) / 2)
        highway = shapely.union_all([g for g, t in zip(lines, types) if t == fire.STATE_ROAD_TYPE])
        (fx_, fy_), (tx, ty) = shapely.shortest_line(highway, mid).coords
        gap = np.hypot(tx - fx_, ty - fy_)
        dx, dy = (tx - fx_) / gap * nearer_ft, (ty - fy_) / gap * nearer_ft
        lines = [
            affinity.translate(g, dx, dy) if t == fire.STATE_ROAD_TYPE else g for g, t in zip(lines, types)
        ]
        if second_ft:
            ax, ay = -(tx - fx_) / gap * second_ft, -(ty - fy_) / gap * second_ft
            more = [affinity.translate(g, ax, ay) for g, t in zip(lines, types) if t == fire.STATE_ROAD_TYPE]
            lines, types = [*lines, *more], [*types, *([fire.STATE_ROAD_TYPE] * len(more))]
    truck = [(g, t) for g, t in zip(lines, types) if t in fire.TRUCK_TYPES]
    geoms = np.array([g for g, _ in truck], dtype=object)
    roads = fire.TruckRoads((shapely.STRtree(geoms), geoms))
    state = np.array([g for g, t in truck if t == fire.STATE_ROAD_TYPE], dtype=object)
    roads.state_roads = (shapely.STRtree(state), state) if len(state) else None
    lot = lot_from_row(row, corpus.layers)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    drawn = [[x + ox, y + oy] for x, y in fx["drawn"]]
    s = dataclasses.replace(s, drawing={**(s.drawing or {}), "fits": True, "building": drawn})
    return fire_checked(s, lot, roads, policy=policies[0], relief=policies[1])


def test_a_route_from_a_state_highway_across_a_wide_road_stands(corpus, policies) -> None:
    """Oregon City 32E16BB06000: 134 ft with the engine on Highway 213,
    past the limit from Conway Dr alone. Steph looked at it 2026-11-19 ("a
    1 lane highway with generous margins ... I'd say it's green"): the
    route stands as on any road, and the note names the highway."""
    s = _state_case(corpus, policies, "32E16BB06000")
    assert s.facts.fire_route_tried
    assert s.facts.fire_route_ft == pytest.approx(133.9, abs=0.5)
    assert s.facts.fire_on_state_road and not s.facts.fire_road_unclear
    assert s.facts.fire_route_wide_ft is None
    for result in (s.screening, s.signed):
        made = check(result, "fire_access_ft")
        assert made.verdict is Verdict.passes and made.observed == s.facts.fire_route_ft
        assert "fire_access_ft" not in result.unchecked
    note = _flags(s.signed)["FIRE-WIDE-ROAD"]
    assert "state highway" in note.source and "50 ft" in note.source
    assert "FIRE-ROAD-UNCLEAR" not in _flags(s.signed)


def test_a_divided_state_highway_across_a_wide_road_is_held_yellow(corpus, policies) -> None:
    """Highway 213 drawn as two carriageways 40 ft apart: not told from a
    freeway. The route that needs the engine on it is held, never GREEN."""
    s = _state_case(corpus, policies, "32E16BB06000", second_ft=40.0)
    assert s.facts.fire_route_ft == pytest.approx(133.9, abs=0.5)
    assert s.facts.fire_road_unclear and not s.facts.fire_on_state_road
    for result in (s.screening, s.signed):
        assert check(result, "fire_access_ft") is None
        assert "fire_access_ft" in result.unchecked
        assert result.triage is not Triage.green
    assert FACT_UNOBSERVED in s.signed.reasons
    codes = set(_flags(s.signed))
    assert "FIRE-ROAD-UNCLEAR" in codes and "FIRE-WIDE-ROAD" not in codes


@pytest.mark.parametrize("kind", ["freeway", "limited", "rail"])
def test_a_line_on_a_freeway_a_ramp_or_a_railroad_gives_no_engine(corpus, policies, kind) -> None:
    """The same lot with its street lines marked a freeway's, a ramp's or
    beyond a railroad: no wide-road reading, no note, never GREEN."""
    s = _state_case(corpus, policies, "32E16BB06000", kinds={"street": kind})
    assert s.facts.fire_route_wide_ft is None
    assert not s.facts.fire_on_state_road and not s.facts.fire_road_unclear
    assert "FIRE-WIDE-ROAD" not in _flags(s.signed)
    assert s.signed.triage is not Triage.green


def test_a_wide_arterial_inside_the_reach_keeps_its_truck(corpus, policies) -> None:
    """The note is the state highways' (RLIS TYPE 1200) alone: the same
    road typed an arterial stands the truck as before, and says nothing."""
    s = _state_case(corpus, policies, "32E16BB06000", retype={1200: 1400})
    assert s.facts.fire_route_ft == pytest.approx(133.9, abs=0.5)
    assert not s.facts.fire_on_state_road
    assert check(s.signed, "fire_access_ft").verdict is Verdict.passes
    assert "FIRE-WIDE-ROAD" not in {f.code for f in s.signed.flags}


def test_a_lot_that_fronts_a_state_highway_in_the_ordinary_way_keeps_its_truck(corpus, policies) -> None:
    """The highway 5 ft nearer: the line's midpoint is inside the 50 ft
    midpoint test, an ordinary frontage (McLoughlin, TV Highway), and
    nothing is said."""
    s = _state_case(corpus, policies, "32E16BB06000", nearer_ft=5.0)
    assert s.facts.fire_route_tried and s.facts.fire_route_ft <= 150.0
    assert not s.facts.fire_on_state_road
    assert check(s.signed, "fire_access_ft").verdict is Verdict.passes
    assert "FIRE-WIDE-ROAD" not in {f.code for f in s.signed.flags}


def test_a_route_that_reaches_without_the_state_highway_is_left_alone(corpus, policies) -> None:
    """Gladstone 22E19DD02700 on McLoughlin Blvd, a wide-road line with 14
    points inside 50 ft: its 149 ft route comes on from River Rd, and
    stands without the highway."""
    s = _state_case(corpus, policies, "22E19DD02700")
    assert s.facts.fire_route_ft == pytest.approx(148.9, abs=0.5)
    assert not s.facts.fire_on_state_road
    assert check(s.signed, "fire_access_ft").verdict is Verdict.passes
    assert "FIRE-WIDE-ROAD" not in {f.code for f in s.signed.flags}
    # The same route with McLoughlin no truck road at all.
    s = _state_case(corpus, policies, "22E19DD02700", retype={1200: 1110})
    assert s.facts.fire_route_ft == pytest.approx(148.9, abs=0.5)


def test_the_screen_passes_a_route_stood_on_a_state_highway() -> None:
    result = run(facts(fire_route_ft=134.0, fire_route_tried=True, fire_on_state_road=True, fire_wide_gap_ft=50.0))
    made = check(result, "fire_access_ft")
    assert made.verdict is Verdict.passes and made.observed == 134.0
    assert result.triage is Triage.green
    note = _flags(result)["FIRE-WIDE-ROAD"]
    assert note.bounds == (134.0, 150.0) and "state highway" in note.source
    # A route that misses is a miss whatever it stood on, and nothing marks it.
    result = run(facts(fire_route_ft=170.0, fire_route_tried=True, fire_on_state_road=True))
    assert result.triage is Triage.red
    assert check(result, "fire_access_ft").verdict is Verdict.fails
    assert "FIRE-WIDE-ROAD" not in _flags(result)
