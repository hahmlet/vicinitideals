"""The fire hose's route from the street to the farthest wall (FOLLOWUPS 28).

OFC 2022 503.1.1 wants a fire apparatus road within 150 feet of every part of
the first storey's walls, "as measured by an approved route around the
exterior of the building". Steph, 2026-10-01, on the lots past it: "Red" --
no sprinkler relief is assumed, so the check is one no zoning relief reaches.

Three things are pinned here:

* :func:`flats.fit.fire.route_ft` returns the length of a route that exists,
  never a shortcut: round the building, on the lot, in over a street line;
* the screen turns a route past the limit into RED that no relief path
  softens, and a route tried and not found into an unmeasured fact, never a
  pass;
* every zone in the corpus resolves the limit, which is why the field may be
  OPTIONAL in the registry without a zone silently skipping it.
"""

from __future__ import annotations

import json
import math
from datetime import date

import numpy as np
import pytest

pytest.importorskip("shapely")

import shapely  # noqa: E402
from shapely.geometry import Polygon, box  # noqa: E402

from flats.designs.model import load_catalog  # noqa: E402
from flats.encode.load import load_trusted  # noqa: E402
from flats.fit import fire  # noqa: E402
from flats.fit.rectangle import Fit  # noqa: E402
from flats.ingest.quadfit import fire_checked, lot_from_row, screen_lot  # noqa: E402
from flats.rules.fields import FIELDS, OPTIONAL_FIELDS  # noqa: E402
from flats.rules.model import Provenance, Status  # noqa: E402
from flats.rules.resolver import Resolved, Verdict as RuleVerdict, ZoneResolution  # noqa: E402
from flats.score import relief, slack  # noqa: E402
from flats.score.relief import NO_ZONING_RELIEF  # noqa: E402
from flats.score.screen import (  # noqa: E402
    CHECK_FIELD,
    FACT_UNOBSERVED,
    LotFacts,
    Triage,
    screen,
)
from flats.score.slack import Verdict  # noqa: E402

pytestmark = pytest.mark.unit


# --- the route ------------------------------------------------------------

STREET = ((0.0, 0.0, 60.0, 0.0),)
LOT = box(0, 0, 60, 200)
BUILDING = box(10, 20, 46, 76)

#: A flag lot: a 16-ft pole off the street, the building on the flag.
FLAG = Polygon([(0, 0), (16, 0), (16, 150), (100, 150), (100, 250), (0, 250)])
FLAG_BUILDING = box(20, 170, 76, 206)


def test_the_far_wall_is_reached_round_either_side() -> None:
    """Straight up beside the building to a back corner (76 ft), then along
    the back wall to the point equally far both ways: (76 + 76 + 36) / 2."""
    assert fire.route_ft(BUILDING, LOT, STREET) == pytest.approx(94.0)


def test_the_route_is_never_shorter_than_the_crow_flies() -> None:
    """A route that existed could not be shorter than the straight distance
    from the street to the building's farthest corner."""
    far = max(y for _, y in BUILDING.exterior.coords)
    assert fire.route_ft(BUILDING, LOT, STREET) >= far


def test_a_flag_lot_is_walked_up_the_pole_and_round_the_bend() -> None:
    """The hose cannot cut across the neighbour's yard to the flag: it goes up
    the pole and bends at its inside corner, which is how a lot 175 feet
    deep at the building puts the far wall 256 feet away."""
    got = fire.route_ft(FLAG_BUILDING, FLAG, ((0.0, 0.0, 16.0, 0.0),))
    assert got == pytest.approx(255.69, abs=0.05)
    assert got > 150


def test_no_street_line_is_no_route() -> None:
    assert fire.route_ft(BUILDING, LOT, ()) is None


def test_a_building_cut_off_from_the_street_is_no_route() -> None:
    """One tax lot in two pieces three feet apart: the building on the far
    piece is unreachable on the lot (the route's slack on the lot line is a
    foot), and an unreachable building is an answer nobody measured."""
    lot = shapely.union(box(0, 0, 20, 20), box(23, 23, 80, 80))
    assert fire.route_ft(box(40, 40, 60, 60), lot, ((0.0, 0.0, 20.0, 0.0),)) is None


def test_the_truck_stands_back_from_the_lot_line_by_the_offset() -> None:
    offset = lambda pts: np.full(len(pts), 12.0)  # noqa: E731
    assert fire.route_ft(BUILDING, LOT, STREET, offset) == pytest.approx(106.0)


def test_a_street_line_the_truck_cannot_stand_near_is_no_way_in() -> None:
    """Every point of the only street line is past MAX_GAP_FT from a road."""
    offset = lambda pts: np.full(len(pts), math.inf)  # noqa: E731
    assert fire.route_ft(BUILDING, LOT, STREET, offset) is None


def test_the_offset_is_half_a_fire_road_short_of_the_centreline() -> None:
    road = shapely.LineString([(-100, -30), (200, -30)])
    tree, geoms = shapely.STRtree([road]), np.asarray([road], dtype=object)
    pts = np.array([[0.0, 0.0], [0.0, -25.0], [0.0, 25.0]])
    got = fire.street_offsets(pts, tree, geoms)
    # 30 ft to the centreline -> 20; 5 ft -> 0 (never negative); 55 ft -> none.
    assert got[0] == pytest.approx(20.0)
    assert got[1] == 0.0
    assert math.isinf(got[2])


def test_without_centrelines_the_offset_is_zero() -> None:
    assert fire.street_offsets(np.zeros((3, 2)), None, ()).tolist() == [0.0, 0.0, 0.0]


def test_only_roads_a_truck_can_use_are_loaded(tmp_path) -> None:
    import pandas as pd

    line = lambda y: shapely.to_wkb(shapely.LineString([(0, y), (10, y)]))  # noqa: E731
    pd.DataFrame(
        {
            "type": ["1400", "1600", "1800", "1110", "1700", "1500", "5501", "5402", "2000"],
            "alley": [False, True, False, False, False, True, False, False, False],
            "wkb": [line(y) for y in range(9)],
        }
    ).to_parquet(tmp_path / "s1_streets.parquet")
    _, geoms = fire.load_truck_roads(tmp_path / "s1_streets.parquet")
    # An arterial, a named private road and a street with MAX in it (SW 5th:
    # 1S1E03BC -04000, a downtown block read as reachable from nowhere);
    # not an alley, an unnamed drive, a freeway, a street the stage file
    # marked an alley, Tilikum Crossing or an unimproved road.
    assert sorted(g.coords[0][1] for g in geoms) == [0.0, 4.0, 6.0]


def test_an_unimproved_road_with_recorded_pavement_is_one_a_truck_can_use(tmp_path) -> None:
    import pandas as pd

    from flats.geom.curbs import StreetEdges

    line = lambda y: shapely.to_wkb(shapely.LineString([(0, y), (100, y)]))  # noqa: E731
    path = tmp_path / "s1_streets.parquet"
    pd.DataFrame(
        {
            "type": ["2000", "2000", "2000", "1800"],
            "alley": [False] * 4,
            "wkb": [line(0), line(100), line(200), line(300)],
        }
    ).to_parquet(path)
    # Paved 30 ft beside the first, 12 ft (a path) beside the second, nothing
    # beside the third; an unnamed drive stays out however wide.
    edges = StreetEdges.build(
        widths=[
            (shapely.LineString([(0, 2), (100, 2)]), 30.0),
            (shapely.LineString([(0, 102), (100, 102)]), 12.0),
            (shapely.LineString([(0, 302), (100, 302)]), 30.0),
        ]
    )
    _, geoms = fire.load_truck_roads(path, edges)
    assert sorted(g.coords[0][1] for g in geoms) == [0.0]
    _, bare = fire.load_truck_roads(path)
    assert len(bare) == 0


# --- the screen -----------------------------------------------------------

WHERE = "or/multnomah/portland"
PROV = Provenance(
    cite="OFC 2022 503.1.1",
    url="https://clackamasfire.com/wp-content/uploads/2023/08/Oregon-Fire-Code-Applications-Guide-2022.pdf",
    retrieved=date(2026, 10, 1),
)
DESIGN = load_catalog().latest("pod56x36")

CLEAR = {
    "quadplex_allowed": True,
    "min_lot_sqft": 3000,
    "min_frontage_ft": 25,
    "min_lot_width_ft": 25,
    "max_coverage_pct": 60,
    "max_far": 2.0,
    "max_height_ft": 60,
    "max_units": 4,
    "parking_min_per_unit": 1.0,
    "fire_access_max_ft": 150,
}


def rules(**overrides) -> ZoneResolution:
    values = {**CLEAR, **overrides}
    return ZoneResolution(
        jurisdiction=WHERE,
        zone="R5",
        verdict=RuleVerdict.trusted,
        values={
            name: Resolved(
                name=name,
                value=value,
                status=Status.verified,
                prov=PROV,
                layer=WHERE,
                origin="zone",
            )
            for name, value in values.items()
            if value is not None
        },
    )


def fit() -> Fit:
    depth_ft = 36.0
    best = depth_ft + DESIGN.parking.court_depth_ft + 4.0
    return Fit(
        fits=True,
        width_ft=56.0,
        depth_ft=depth_ft,
        best_depth_ft=best,
        slack_ft=best - depth_ft,
        across_ft=max(56.0 + DESIGN.parking.lane_width_ft, DESIGN.court_width_ft),
    )


def run(lot: LotFacts, rule_set: ZoneResolution | None = None):
    return screen(
        rule_set or rules(),
        lot,
        DESIGN,
        fit(),
        policy=slack.SlackPolicy(tolerance={"fit_ft": 0.5}),
        relief=relief.load_policy(),
    )


def facts(**over) -> LotFacts:
    return LotFacts(lot_sqft=6000, frontage_ft=60, lot_width_ft=60, **over)


def check(result, name: str):
    return next((c for c in result.checks if c.check == name), None)


def test_a_route_inside_the_limit_passes() -> None:
    result = run(facts(fire_route_ft=140.0, fire_route_tried=True))
    assert check(result, "fire_access_ft").verdict is Verdict.passes
    assert result.triage is Triage.green


def test_a_route_past_the_limit_is_red_and_no_relief_softens_it() -> None:
    """Steph 2026-10-01: "Red". A variance is a zoning remedy; the fire code
    is not zoning, and the sprinkler exception is not assumed."""
    result = run(facts(fire_route_ft=160.0, fire_route_tried=True))
    assert check(result, "fire_access_ft").verdict is not Verdict.passes
    assert result.triage is Triage.red
    assert any(c.check == "fire_access_ft" for c in result.binding)


def test_every_relief_policy_answers_unavailable_for_the_fire_check() -> None:
    policy = relief.load_policy()
    assert "fire_access_ft" in NO_ZONING_RELIEF
    for shortfall in (0.1, 5.0, 100.0):
        got = policy.for_check(
            "fire_access_ft", shortfall=shortfall, threshold=150.0, jurisdiction=WHERE
        )
        assert got.tier is relief.Tier.unavailable


def test_a_route_tried_and_not_found_is_unmeasured_not_passed() -> None:
    result = run(facts(fire_route_tried=True))
    assert check(result, "fire_access_ft") is None
    assert "fire_access_ft" in result.unchecked
    assert FACT_UNOBSERVED in result.reasons
    assert result.triage is not Triage.green


def test_a_screen_with_no_route_asked_is_unchanged() -> None:
    """A caller that never measured (a lot screened without a drawing) is
    not charged a fact it was never asked for."""
    result = run(facts())
    assert "fire_access_ft" in result.unchecked
    assert FACT_UNOBSERVED not in result.reasons


def test_the_check_reads_the_registered_field() -> None:
    assert CHECK_FIELD["fire_access_ft"] == "fire_access_max_ft"
    assert FIELDS["fire_access_max_ft"].kind == "length_ft"
    assert FIELDS["fire_access_max_ft"].is_maximum is True


# --- the corpus -----------------------------------------------------------


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


def test_every_zone_in_the_corpus_resolves_the_fire_limit(corpus) -> None:
    """The field is OPTIONAL only because the state layer states it for every
    zone. A zone resolving anything else -- or nothing -- would be screened
    without the check and never know it."""
    assert "fire_access_max_ft" in OPTIONAL_FIELDS
    wrong = []
    for name, layer in sorted(corpus.layers.items()):
        for zone in sorted(layer.zones):
            got = corpus.resolve(name, zone).get("fire_access_max_ft")
            if got != 150:
                wrong.append((name, zone, got))
    assert not wrong, wrong[:10]


# --- the bridge -----------------------------------------------------------

# 200 ft east of where it stood until 2026-11-04: the old spot is Central
# City, where FOLLOWUPS 109 batch B holds every lot (plan_district_unmeasured).
X0, Y0 = 7_650_200.0, 680_000.0


def bridge_row(**over) -> dict[str, object]:
    edges = [
        [X0, Y0, X0 + 80, Y0, "F"],
        [X0 + 80, Y0, X0 + 80, Y0 + 120, "S"],
        [X0 + 80, Y0 + 120, X0, Y0 + 120, "R"],
        [X0, Y0 + 120, X0, Y0, "S"],
    ]
    base: dict[str, object] = {
        "TLID": "1S2E20AA  -99999",
        "jurisdiction": "portland",
        "zone": "RM1",
        "tier": "A",
        "area_sqft": 9600.0,
        "frontage_ft": 80.0,
        "lot_width_ft": 80.0,
        "lot_depth_ft": 120.0,
        "edges_json": json.dumps(edges),
        "front_bearings_json": "[0.0]",
        "fronts_cul_de_sac": False,
        "split_zone": False,
        "ovl_fema_sfha": False,
        "ovl_fema_floodway": False,
        "sewer_main_dist_ft": 12.0,
        "in_sewer_district": None,
        "wkb": shapely.to_wkb(box(X0 + 5, Y0 + 10, X0 + 75, Y0 + 115)),
        "lot_wkb": shapely.to_wkb(box(X0, Y0, X0 + 80, Y0 + 120)),
    }
    base.update(over)
    return base


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


def pod():
    return load_catalog().latest("pod56x36")


def test_the_bridge_measures_the_route_on_the_drawn_plan(corpus, policies) -> None:
    lot = lot_from_row(bridge_row(), corpus.layers)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    assert s.drawing and s.drawing.get("building")
    assert s.facts is not None and s.facts.fire_route_tried
    # A 120-ft lot: the far wall is no farther than walking its whole edge.
    assert 36.0 <= s.facts.fire_route_ft <= 120.0 + 80.0
    assert check(s.screening, "fire_access_ft").verdict is Verdict.passes


def tight_row(**over) -> dict[str, object]:
    """:func:`bridge_row` 88.5 ft deep: the pod's court misses by half a
    foot, inside the fit's tolerance -- GREEN with FIT-TIGHT."""
    d = 88.5
    edges = [
        [X0, Y0, X0 + 80, Y0, "F"],
        [X0 + 80, Y0, X0 + 80, Y0 + d, "S"],
        [X0 + 80, Y0 + d, X0, Y0 + d, "R"],
        [X0, Y0 + d, X0, Y0, "S"],
    ]
    return bridge_row(
        edges_json=json.dumps(edges),
        lot_depth_ft=d,
        area_sqft=80 * d,
        wkb=shapely.to_wkb(box(X0 + 5, Y0 + 10, X0 + 75, Y0 + d - 5)),
        lot_wkb=shapely.to_wkb(box(X0, Y0, X0 + 80, Y0 + d)),
        **over,
    )


def _coloured(s, triage: Triage, *, map_too: bool = True):
    """``s`` read ``triage``; with ``map_too``, short of GREEN on the flag
    plan's map as well (a flag at the line, or a bind for RED) -- else the
    map keeps the colour its binds and flags give it."""
    import dataclasses

    from flats.score.flags import Bind, Flag

    extra: dict[str, object] = {}
    if map_too and triage is Triage.red:
        extra = {"binds": (Bind(check="fit_ft", observed=1.0, threshold=2.0, shortfall=1.0),)}
    elif map_too and triage is not Triage.green:
        extra = {"flags": (Flag(code="TEST", key="", by="test", severity=9),)}
    return dataclasses.replace(
        s,
        screening=dataclasses.replace(s.screening, triage=triage, **extra),
        signed=dataclasses.replace(s.signed, triage=triage, **extra),
        facts=dataclasses.replace(s.facts, fire_route_ft=None, fire_route_tried=False),
    )


def test_a_green_plan_with_no_route_is_tried_and_unobserved(corpus, policies) -> None:
    lot = lot_from_row(bridge_row(), corpus.layers)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    bare = lot_from_row(bridge_row(lot_wkb=None), corpus.layers)
    got = fire_checked(_coloured(s, Triage.green), bare, None, policy=policies[0], relief=policies[1])
    assert got.facts.fire_route_tried and got.facts.fire_route_ft is None
    assert got.signed.triage is not Triage.green
    assert FACT_UNOBSERVED in got.signed.reasons


def test_a_plan_short_of_green_with_no_route_is_left_as_it_was(corpus, policies) -> None:
    # A yellow plan whose drawing stands past the lot line (the fit fell
    # short) finds no route; marking it unmeasured would move a lot that is
    # already short of GREEN for another reason (2026-10-01: 133k rows).
    lot = lot_from_row(bridge_row(), corpus.layers)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    bare = lot_from_row(bridge_row(lot_wkb=None), corpus.layers)
    yellow = _coloured(s, Triage.yellow)
    assert fire_checked(yellow, bare, None, policy=policies[0], relief=policies[1]) is yellow


def test_a_plan_green_on_the_map_with_no_route_is_tried_and_unobserved(corpus, policies) -> None:
    # FOLLOWUPS 49(a), run 65: 78 lots shown green on the map with no fire
    # check -- their triage read yellow on a missed minimum density, a flag
    # below the map's line, so the "short of GREEN" skip let them by.
    from flats.score.flags import Colour

    lot = lot_from_row(bridge_row(), corpus.layers)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    bare = lot_from_row(bridge_row(lot_wkb=None), corpus.layers)
    yellow = _coloured(s, Triage.yellow, map_too=False)
    assert yellow.signed.colour is Colour.green
    got = fire_checked(yellow, bare, None, policy=policies[0], relief=policies[1])
    assert got.facts.fire_route_tried and got.facts.fire_route_ft is None
    assert got.signed.colour is not Colour.green
    assert FACT_UNOBSERVED in got.signed.reasons


def test_a_plan_red_on_triage_and_green_on_the_map_is_measured(corpus, policies) -> None:
    from flats.score.flags import Colour

    lot = lot_from_row(bridge_row(), corpus.layers)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    red = _coloured(s, Triage.red, map_too=False)
    assert red.signed.colour is Colour.green
    got = fire_checked(red, lot, None, policy=policies[0], relief=policies[1])
    assert got.facts.fire_route_tried and got.facts.fire_route_ft is not None


def test_a_tight_fit_is_drawn_and_its_route_measured(corpus, policies) -> None:
    # FOLLOWUPS 49(d), run 65: 1,634 tight fits read UNKNOWN for want of a
    # route -- the fit passed on its tolerance and the drawing, asked for
    # the whole window, drew the shortfall and stood no building.
    lot = lot_from_row(tight_row(), corpus.layers)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    assert s.screening.tight_fit
    assert s.drawing["fits"] and s.drawing["tight"]
    assert s.facts.fire_route_tried and s.facts.fire_route_ft is not None
    assert s.signed.triage is Triage.green


def test_a_plan_short_of_green_with_a_route_is_still_measured(corpus, policies) -> None:
    lot = lot_from_row(bridge_row(), corpus.layers)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    got = fire_checked(_coloured(s, Triage.yellow), lot, None, policy=policies[0], relief=policies[1])
    assert got.facts.fire_route_tried and got.facts.fire_route_ft is not None


def test_a_fit_that_fell_short_is_not_measured(corpus, policies) -> None:
    # Run 54 (2026-10-02): 14,419 yellow answers went RED off routes to
    # buildings drawn where the fit fell short -- 1S1E08DB -05602, short by
    # 30 ft, walked 344 ft. A drawing that shows the shortfall stands no
    # building, so it proves no route.
    import dataclasses

    lot = lot_from_row(bridge_row(), corpus.layers)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    assert s.drawing["fits"]
    short = dataclasses.replace(
        _coloured(s, Triage.yellow), drawing={**s.drawing, "fits": False}
    )
    got = fire_checked(short, lot, None, policy=policies[0], relief=policies[1])
    assert got is short


def test_a_plan_red_both_ways_is_not_measured(corpus, policies) -> None:
    lot = lot_from_row(bridge_row(), corpus.layers)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)

    red = _coloured(s, Triage.red)
    got = fire_checked(red, lot, None, policy=policies[0], relief=policies[1])
    assert got is red


def test_a_private_road_the_yards_do_not_count_is_still_a_way_in(corpus, policies) -> None:
    # 1S1E34DB -00103 (2026-10-01): a lot on a named private road, read as
    # an ordinary lot line for the yards, was walked round from the far
    # street -- 454 ft for a building 92 ft from the road it stands on.
    import dataclasses

    lot = lot_from_row(bridge_row(), corpus.layers)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    front = (X0, Y0, X0 + 80, Y0)
    private = dataclasses.replace(lot, edges=None, access=(front,), access_bearings=(0.0,))
    got = fire_checked(_coloured(s, Triage.green), private, None, policy=policies[0], relief=policies[1])
    assert got.facts.fire_route_ft == pytest.approx(s.facts.fire_route_ft)


def test_reachable_keeps_the_lines_a_truck_can_stand_off() -> None:
    near = (0.0, 0.0, 60.0, 0.0)
    far = (0.0, 200.0, 60.0, 200.0)
    road = shapely.LineString([(-50, -20), (110, -20)])
    off = fire.point_offset(shapely.STRtree([road]), np.array([road]))
    assert fire.reachable((near, far), off) == (near,)
    assert fire.reachable((near, far), None) == (near, far)


@pytest.mark.parametrize("served_end", ["low", "high"])
def test_a_through_lot_is_drawn_at_the_end_the_truck_reaches(corpus, policies, served_end) -> None:
    # 1N2E26AD -02900 (2026-10-01): a through lot between a local street and
    # I-84 was drawn at the freeway end, and the hose walked the lot's whole
    # depth from the street: 158 ft for a building 75 ft from it.
    depth = 240.0
    edges = [
        [X0, Y0, X0 + 80, Y0, "F"],
        [X0 + 80, Y0, X0 + 80, Y0 + depth, "S"],
        [X0 + 80, Y0 + depth, X0, Y0 + depth, "F"],
        [X0, Y0 + depth, X0, Y0, "S"],
    ]
    row = bridge_row(
        edges_json=json.dumps(edges),
        front_bearings_json="[0.0, 180.0]",
        lot_depth_ft=depth,
        area_sqft=80 * depth,
        wkb=shapely.to_wkb(box(X0 + 5, Y0 + 10, X0 + 75, Y0 + depth - 10)),
        lot_wkb=shapely.to_wkb(box(X0, Y0, X0 + 80, Y0 + depth)),
    )
    lot = lot_from_row(row, corpus.layers)
    y = Y0 - 20 if served_end == "low" else Y0 + depth + 20
    road = shapely.LineString([(X0 - 100, y), (X0 + 180, y)])
    roads = (shapely.STRtree([road]), np.array([road]))
    (s,) = screen_lot(
        lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0, roads=roads
    )
    if s.screening.triage is Triage.red and s.signed.triage is Triage.red:
        pytest.skip("red both ways: not measured, by design")
    assert s.facts.fire_route_ft is not None and s.facts.fire_route_ft <= 150.0
    ys = [p[1] for p in s.drawing["building"]]
    middle = Y0 + depth / 2
    assert (max(ys) < middle) if served_end == "low" else (min(ys) > middle)


def _deep_lot(width: float, depth: float):
    edges = [
        [X0, Y0, X0 + width, Y0, "F"],
        [X0 + width, Y0, X0 + width, Y0 + depth, "S"],
        [X0 + width, Y0 + depth, X0, Y0 + depth, "R"],
        [X0, Y0 + depth, X0, Y0, "S"],
    ]
    return bridge_row(
        edges_json=json.dumps(edges),
        frontage_ft=width,
        lot_width_ft=width,
        lot_depth_ft=depth,
        area_sqft=width * depth,
        wkb=shapely.to_wkb(box(X0 + 5, Y0 + 10, X0 + width - 5, Y0 + depth - 10)),
        lot_wkb=shapely.to_wkb(box(X0, Y0, X0 + width, Y0 + depth)),
    )


def _sunk(s, to_y: float):
    """``s`` with its building drawn ``to_y`` ft deeper into the lot."""
    import dataclasses

    ring = [[x, y + to_y] for x, y in s.drawing["building"]]
    return dataclasses.replace(
        _coloured(s, Triage.green), drawing={**s.drawing, "building": ring, "fits": True}
    )


@pytest.mark.parametrize("width, lifted", [(200.0, True), (80.0, False)])
def test_a_building_drawn_out_of_reach_is_turned_where_the_hose_reaches(
    corpus, policies, width, lifted
) -> None:
    """FOLLOWUPS 39 (Steph 2026-10-04): the drawing stands the building at
    the fit's angle, and on a lot with room the hose may miss it there
    while the same plan at another angle stands within reach (Hillsboro
    1N230BA00800: 201 ft at 140 degrees, 107 ft at 1 degree). The other
    angles are drawn and the reach kept; where no other angle holds the
    plan, the miss stands."""
    from flats.fit.angles import angles_for
    from flats.fit.rectangle import Fitter

    lot = lot_from_row(_deep_lot(width, 240.0), corpus.layers)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    assert s.drawing and s.drawing["fits"]
    angles = angles_for(lot.front_bearings, step_deg=30.0)
    fitter = Fitter(s.envelope.geom, angles, ground=s.envelope.ground)
    sunk = _sunk(s, 240.0 - 50.0 - max(p[1] - Y0 for p in s.drawing["building"]))
    got = fire_checked(sunk, lot, None, policy=policies[0], relief=policies[1], fitter=fitter)
    if lifted:
        assert got.facts.fire_route_ft <= 150.0
        assert got.drawing["fits"]
        assert max(p[1] for p in got.drawing["building"]) < Y0 + 120.0
        assert check(got.screening, "fire_access_ft").verdict is Verdict.passes
    else:
        assert got.facts.fire_route_ft > 150.0
        assert got.drawing["building"] == sunk.drawing["building"]
        assert check(got.screening, "fire_access_ft").verdict is Verdict.fails


def test_a_probe_that_reads_only_the_fit_draws_nothing_and_walks_no_hose(corpus, policies) -> None:
    """The slope's probe of the lot with its steep ground left on asks one
    thing, whether the fit misses: it is not drawn, its fire route is not
    walked or turned for, and the fit it reads is the full screen's."""
    from flats.ingest.quadfit import _screen_lot_once

    lot = lot_from_row(_deep_lot(200.0, 240.0), corpus.layers)
    kw = dict(rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0, bound=False)
    (full,) = _screen_lot_once(lot, [pod()], **kw)
    (probe,) = _screen_lot_once(lot, [pod()], fit_only=True, **kw)
    assert full.drawing and full.facts.fire_route_tried
    assert probe.drawing is None
    assert not probe.facts.fire_route_tried
    assert check(probe.screening, "fit_ft").verdict is check(full.screening, "fit_ft").verdict


def _placement_retry_case(corpus, policies):
    from flats.fit.rectangle import Fitter

    row = _deep_lot(200.0, 240.0)
    row.update(jurisdiction="portland", zone="CE")
    lot = lot_from_row(row, corpus.layers)
    (s,) = screen_lot(
        lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0
    )
    assert s.drawing and s.drawing["fits"] and s.fit.angle_deg is not None
    assert s.envelope is not None
    fitter = Fitter(s.envelope.geom, (s.fit.angle_deg,), ground=s.envelope.ground)
    return lot, s, fitter


@pytest.mark.parametrize("square", [True, False])
def test_fire_only_red_uses_the_next_fitting_placement_within_reach(
    corpus, policies, monkeypatch, square
) -> None:
    """A big lot's preferred drawing is red only on hose reach; the first
    other fitting placement within reach is kept and moves the colour.

    The retry lists placements at the fit's angle. This fixture's fit stands
    30 degrees off the street and its drawing square to it (the front-max
    search turned it). Listed at 30 degrees, every placement stands the far
    end of its street wall some 35 ft back against Portland CE's 10 ft
    maximum: measured where it stands (FOLLOWUPS 160), none is taken and the
    plan stays RED on the hose -- before, the first was kept YELLOW and the
    screen's later re-measure turned it RED on the maximum. With the fit
    square to the street, the next placement within the maximum is kept.
    (This fitter holds the fit's angle alone; one that holds the drawing's
    angle lists there first: FOLLOWUPS 163,
    :func:`test_fire_retry_lists_placements_at_the_drawing_angle`.)"""
    import dataclasses

    from flats.fit.rectangle import Fitter
    from flats.score.flags import Colour

    lot, s, fitter = _placement_retry_case(corpus, policies)
    # The fixture's own fit used to stand at 30 degrees; since pdx-cm-buffer
    # (FOLLOWUPS 171) CE's parking buffer reshapes the envelope and the fit comes
    # out square, so both cases now set the angle they test (rel7 assembly, 2026-11-10).
    angle = 0.0 if square else 30.0
    s = dataclasses.replace(s, fit=dataclasses.replace(s.fit, angle_deg=angle))
    fitter = Fitter(s.envelope.geom, (angle,), ground=s.envelope.ground)
    first = Polygon(s.drawing["building"])

    def route(building, *_args, **_kwargs):
        return 190.0 if building.equals(first) else 120.0

    monkeypatch.setattr(fire, "route_ft", route)
    base = _coloured(s, Triage.green)
    today = fire_checked(base, lot, None, policy=policies[0], relief=policies[1])
    assert today.signed.colour is Colour.red
    assert check(today.screening, "fire_access_ft").verdict is Verdict.fails
    assert all(
        c.verdict is Verdict.passes
        for c in today.signed.checks
        if c.check != "fire_access_ft"
    ), [
        (c.check, c.verdict)
        for c in today.signed.checks
        if c.check != "fire_access_ft" and c.verdict is not Verdict.passes
    ]

    got = fire_checked(
        base, lot, None, policy=policies[0], relief=policies[1], fitter=fitter
    )

    if not square:
        assert got.drawing == base.drawing
        assert got.signed.colour is Colour.red
        assert check(got.screening, "fire_access_ft").verdict is Verdict.fails
        return
    assert got.signed.colour is Colour.yellow
    assert got.drawing["building"] != s.drawing["building"]
    assert got.facts.fire_route_ft == 120.0
    assert check(got.screening, "fire_access_ft").verdict is Verdict.passes
    assert all(
        c.verdict is Verdict.passes
        for c in got.screening.checks
        if c.check != "fire_access_ft"
    )


def test_fire_retry_draws_at_most_its_placement_cap(corpus, policies, monkeypatch) -> None:
    from flats.ingest import quadfit

    lot, s, fitter = _placement_retry_case(corpus, policies)
    base = _coloured(s, Triage.green)
    ring = base.drawing["building"]
    candidate = {
        **base.drawing,
        "building": [[x + 1.0, y] for x, y in ring],
    }
    drawn: list[object] = []
    real_drawing_for = quadfit.drawing_for

    def drawing_for(screened, fitter, *, listing=None, where=None, **kwargs):
        if listing is not None:
            listing.extend(range(200))
            return None
        if where is not None:
            drawn.append(where)
            return candidate
        return real_drawing_for(screened, fitter, where=where, **kwargs)

    monkeypatch.setattr(quadfit, "drawing_for", drawing_for)
    monkeypatch.setattr(fire, "route_ft", lambda *_args, **_kwargs: 190.0)
    monkeypatch.setattr(
        quadfit, "_turned_for_fire", lambda current, *_args, **_kwargs: (current, 190.0)
    )

    got = fire_checked(
        base, lot, None, policy=policies[0], relief=policies[1], fitter=fitter
    )

    assert len(drawn) == quadfit.FIRE_RETRY_MAX_PLACEMENTS == 24
    assert got.drawing == base.drawing


def test_fire_retry_skips_lots_over_its_acreage_limit(corpus, policies, monkeypatch) -> None:
    import dataclasses

    from flats.ingest import quadfit

    lot, s, fitter = _placement_retry_case(corpus, policies)
    large = dataclasses.replace(
        s,
        facts=dataclasses.replace(
            s.facts, lot_sqft=quadfit.FIRE_RETRY_MAX_ACRES * 43_560 + 1
        ),
    )
    base = _coloured(large, Triage.green)
    monkeypatch.setattr(fire, "route_ft", lambda *_args, **_kwargs: 190.0)
    monkeypatch.setattr(
        quadfit, "_turned_for_fire", lambda current, *_args, **_kwargs: (current, 190.0)
    )
    no_retry = fire_checked(
        base, lot, None, policy=policies[0], relief=policies[1]
    )

    listings = 0
    draws = 0
    real_drawing_for = quadfit.drawing_for

    def drawing_for(screened, fitter, *, listing=None, where=None, **kwargs):
        nonlocal listings, draws
        if listing is not None:
            listings += 1
            return None
        if where is not None:
            draws += 1
        return real_drawing_for(screened, fitter, where=where, **kwargs)

    monkeypatch.setattr(quadfit, "drawing_for", drawing_for)
    got = fire_checked(
        base, lot, None, policy=policies[0], relief=policies[1], fitter=fitter
    )

    assert listings == 0
    assert draws == 0
    assert got == no_retry


@pytest.mark.parametrize(
    "candidate_front_ft, moved",
    [(30.0, False), (8.0, True)],
)
def test_fire_retry_respects_the_maximum_front_setback(
    corpus, policies, monkeypatch, candidate_front_ft, moved
) -> None:
    from flats.ingest import flatter, quadfit
    from flats.score.flags import Colour

    lot, s, fitter = _placement_retry_case(corpus, policies)
    base = _coloured(s, Triage.green)
    ring = base.drawing["building"]
    front = min(y for _, y in ring)
    candidate = {
        **base.drawing,
        "building": [
            [x, y + candidate_front_ft - (front - Y0)] for x, y in ring
        ],
    }
    candidate_polygon = Polygon(candidate["building"])
    monkeypatch.setattr(flatter, "_max_front_ft", lambda *_args: 10.0)

    listed_caps: list[float | None] = []
    real_drawing_for = quadfit.drawing_for

    def drawing_for(screened, fitter, *, listing=None, where=None, **kwargs):
        if listing is not None:
            cap = kwargs.get("max_front_ft")
            listed_caps.append(cap)
            if cap is not None and candidate_front_ft <= cap:
                listing.append("candidate")
            return None
        if where == "candidate":
            return candidate
        return real_drawing_for(screened, fitter, where=where, **kwargs)

    monkeypatch.setattr(quadfit, "drawing_for", drawing_for)

    def route(building, *_args, **_kwargs):
        if building.equals(candidate_polygon):
            return 120.0
        return 190.0

    monkeypatch.setattr(fire, "route_ft", route)
    monkeypatch.setattr(
        quadfit, "_turned_for_fire", lambda current, *_args, **_kwargs: (current, 190.0)
    )

    got = fire_checked(
        base, lot, None, policy=policies[0], relief=policies[1], fitter=fitter
    )

    assert listed_caps == [10.0]
    if moved:
        assert got.drawing["building"] == candidate["building"]
        assert got.facts.fire_route_ft == 120.0
        assert got.signed.colour is Colour.yellow
    else:
        assert got.drawing == base.drawing
        assert got.facts.fire_route_ft == 190.0
        assert got.signed.colour is Colour.red


def test_fire_retry_skips_a_drawing_with_a_measured_parking_share(
    corpus, policies, monkeypatch
) -> None:
    import dataclasses

    from flats.ingest import quadfit

    lot, s, fitter = _placement_retry_case(corpus, policies)
    facts = dataclasses.replace(
        s.facts, parking_frontage_share_pct=0.0, parking_frontage_run_ft=0.0
    )
    base = _coloured(dataclasses.replace(s, facts=facts), Triage.green)
    listing_calls = 0
    angle_retry_calls = 0
    real_drawing_for = quadfit.drawing_for

    def drawing_for(screened, fitter, *, listing=None, **kwargs):
        nonlocal listing_calls
        if listing is not None:
            listing_calls += 1
            return None
        return real_drawing_for(screened, fitter, **kwargs)

    def other_angle(current, *_args, **_kwargs):
        nonlocal angle_retry_calls
        angle_retry_calls += 1
        return current, 190.0

    monkeypatch.setattr(quadfit, "drawing_for", drawing_for)
    monkeypatch.setattr(fire, "route_ft", lambda *_args, **_kwargs: 190.0)
    monkeypatch.setattr(quadfit, "_turned_for_fire", other_angle)

    got = fire_checked(
        base, lot, None, policy=policies[0], relief=policies[1], fitter=fitter
    )

    assert listing_calls == 0
    assert angle_retry_calls == 1
    assert got.drawing == base.drawing
    assert got.facts.parking_frontage_share_pct == 0.0
    assert check(got.screening, "fire_access_ft").verdict is Verdict.fails


def test_fire_only_red_keeps_today_result_when_no_placement_is_within_reach(
    corpus, policies, monkeypatch
) -> None:
    lot, s, fitter = _placement_retry_case(corpus, policies)

    monkeypatch.setattr(fire, "route_ft", lambda *_args, **_kwargs: 190.0)
    base = _coloured(s, Triage.green)
    today = fire_checked(base, lot, None, policy=policies[0], relief=policies[1])

    got = fire_checked(
        base, lot, None, policy=policies[0], relief=policies[1], fitter=fitter
    )

    assert got.drawing == today.drawing
    assert got.facts == today.facts
    assert got.screening == today.screening
    assert got.signed == today.signed


def test_fire_retry_does_not_move_a_placement_with_another_failing_check(
    corpus, policies, monkeypatch
) -> None:
    import dataclasses

    from flats.ingest import quadfit

    lot, s, fitter = _placement_retry_case(corpus, policies)
    original_screen = quadfit.screen

    def fit_fails(*args, **kwargs):
        result = original_screen(*args, **kwargs)
        checks = tuple(
            dataclasses.replace(c, verdict=Verdict.fails) if c.check == "fit_ft" else c
            for c in result.checks
        )
        return dataclasses.replace(result, triage=Triage.red, checks=checks)

    monkeypatch.setattr(quadfit, "screen", fit_fails)
    monkeypatch.setattr(fire, "route_ft", lambda *_args, **_kwargs: 190.0)
    base = _coloured(s, Triage.green)

    got = fire_checked(
        base, lot, None, policy=policies[0], relief=policies[1], fitter=fitter
    )

    assert got.drawing == base.drawing
    assert check(got.screening, "fit_ft").verdict is Verdict.fails
    assert check(got.screening, "fire_access_ft").verdict is Verdict.fails


def _box_ring(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]


FRONT = (0.0, 0.0, 200.0, 0.0)
FAR_FRONT = (200.0, 240.0, 0.0, 240.0)
SIDE_STREET = (200.0, 0.0, 200.0, 240.0)


@pytest.mark.parametrize(
    "court, streets, between",
    [
        # Behind the building on an interior lot: the plan every green draws.
        (_box_ring(20, 80, 100, 120), (FRONT,), False),
        # Beside it, starting at its own face.
        (_box_ring(80, 20, 120, 70), (FRONT,), False),
        # In front of it, in the front yard.
        (_box_ring(20, 2, 100, 18), (FRONT,), True),
        # Behind it on a through lot: the far street's front yard.
        (_box_ring(20, 80, 100, 120), (FRONT, FAR_FRONT), True),
        # Behind it and wider, reaching toward a corner's side street: not
        # between the building and that street.
        (_box_ring(20, 80, 190, 120), (FRONT, SIDE_STREET), False),
        # Beside it, toward the corner's side street.
        (_box_ring(80, 20, 190, 70), (FRONT, SIDE_STREET), True),
        # No court drawn.
        (None, (FRONT,), False),
    ],
)
def test_court_street_side_reads_the_court_between_building_and_street(
    court, streets, between
) -> None:
    from flats.ingest.quadfit import _court_street_side

    drawing = {"building": _box_ring(20, 20, 80, 70), "court": court}
    assert _court_street_side(drawing, streets) is between


def test_court_street_side_holds_at_an_angle() -> None:
    """A plan turned 10 degrees to the street reads the same."""
    from shapely import affinity

    from flats.ingest.quadfit import _court_street_side

    def turned(ring):
        return [list(p) for p in affinity.rotate(Polygon(ring), 10.0, origin=(50, 45)).exterior.coords]

    building = turned(_box_ring(20, 20, 80, 70))
    behind = turned(_box_ring(20, 80, 100, 120))
    ahead = turned(_box_ring(20, 2, 80, 16))
    assert not _court_street_side({"building": building, "court": behind}, (FRONT,))
    assert _court_street_side({"building": building, "court": ahead}, (FRONT,))


@pytest.mark.parametrize("court_ahead", [True, False])
def test_fire_retry_never_moves_the_court_toward_the_street(
    corpus, policies, monkeypatch, court_ahead
) -> None:
    """Milwaukie 12E30CD04700 (fire_rp5): the only placement the hose
    reaches stands the court between the building and the street. The
    retry refuses it and the lot stays RED; the same move with the court
    kept behind the building is taken (the pattern of the three right
    greens, Portland 1S2E12AB06900, 1S3E07AC09706, West Linn
    21E35BC03000)."""
    from flats.ingest import quadfit
    from flats.score.flags import Colour

    lot, s, fitter = _placement_retry_case(corpus, policies)
    base = _coloured(s, Triage.green)
    ring, court = base.drawing["building"], base.drawing.get("court")
    assert court and len(court) >= 4
    b_front = min(y for _, y in ring)
    c_front, c_back = min(y for _, y in court), max(y for _, y in court)
    assert c_front >= max(y for _, y in ring) - 0.5, "the fixture's court stands behind"
    depth = c_back - c_front
    # Ahead, the court needs the building lifted past it; behind, the move
    # stays within CE's 10 ft maximum front setback (FOLLOWUPS 160).
    lift = depth + 5.0 if court_ahead else 3.0
    moved = [[x, y + lift] for x, y in ring]
    if court_ahead:
        court_to = [[x, y - c_front + b_front] for x, y in court]
    else:
        court_to = [[x, y + lift] for x, y in court]
    candidate = {**base.drawing, "building": moved, "court": court_to}
    candidate_polygon = Polygon(moved)
    streets = tuple((e.x1, e.y1, e.x2, e.y2) for e in lot.edges.edges if e.cls.value == "front")
    assert not quadfit._court_street_side(base.drawing, streets)
    assert quadfit._court_street_side(candidate, streets) is court_ahead

    real_drawing_for = quadfit.drawing_for

    def drawing_for(screened, fitter, *, listing=None, where=None, **kwargs):
        if listing is not None:
            listing.append("candidate")
            return None
        if where == "candidate":
            return candidate
        return real_drawing_for(screened, fitter, where=where, **kwargs)

    monkeypatch.setattr(quadfit, "drawing_for", drawing_for)
    monkeypatch.setattr(
        fire, "route_ft", lambda building, *_a, **_k: 120.0 if building.equals(candidate_polygon) else 190.0
    )
    monkeypatch.setattr(
        quadfit, "_turned_for_fire", lambda current, *_args, **_kwargs: (current, 190.0)
    )

    got = fire_checked(base, lot, None, policy=policies[0], relief=policies[1], fitter=fitter)

    if court_ahead:
        assert got.drawing == base.drawing
        assert got.facts.fire_route_ft == 190.0
        assert got.signed.colour is Colour.red
    else:
        assert got.drawing["building"] == moved
        assert got.facts.fire_route_ft == 120.0
        assert got.signed.colour is Colour.yellow


# --- FOLLOWUPS 160: a moved plan is measured again where it stands ------------


def _lifted(drawing, front_ft: float):
    """``drawing`` with its building and court moved so the building's front
    stands ``front_ft`` from the front lot line."""
    ring = drawing["building"]
    dy = Y0 + front_ft - min(y for _, y in ring)
    return {
        **drawing,
        "building": [[x, y + dy] for x, y in ring],
        "court": [[x, y + dy] for x, y in drawing["court"]],
    }


@pytest.mark.parametrize("near_listed", [True, False])
def test_fire_retry_measures_each_placement_against_the_front_maximum(
    corpus, policies, monkeypatch, near_listed
) -> None:
    """FOLLOWUPS 160 (fire-reds-158, Portland 1S2E07BC  -12600): the
    same-angle retry kept the first drawing's front-max answer for a building
    standing elsewhere. Its listing bounds the distance from the nearest
    street only, so a placement past the maximum on the street the screen
    holds it to was taken, and the screen's later re-measure turned the lot
    RED where a nearer placement reached as well. Each placement is measured
    where it stands: the far one is refused and the near one kept, and the
    later re-measure changes nothing."""
    from flats.ingest import quadfit
    from flats.score.flags import Colour

    lot, s, fitter = _placement_retry_case(corpus, policies)
    assert s.rules.get("setback_front_max_ft") == 10
    base = _coloured(s, Triage.green)
    listed = {"far": _lifted(base.drawing, 30.0), "near": _lifted(base.drawing, 8.0)}
    order = ["far", "near"] if near_listed else ["far"]
    reach = [Polygon(d["building"]) for d in listed.values()]
    real_drawing_for = quadfit.drawing_for

    def drawing_for(screened, fitter, *, listing=None, where=None, **kwargs):
        if listing is not None:
            listing.extend(order)
            return None
        if where in listed:
            return listed[where]
        return real_drawing_for(screened, fitter, where=where, **kwargs)

    monkeypatch.setattr(quadfit, "drawing_for", drawing_for)
    monkeypatch.setattr(
        fire, "route_ft", lambda b, *_a, **_k: 120.0 if any(b.equals(r) for r in reach) else 190.0
    )
    monkeypatch.setattr(
        quadfit, "_turned_for_fire", lambda current, *_args, **_kwargs: (current, 190.0)
    )

    got = fire_checked(base, lot, None, policy=policies[0], relief=policies[1], fitter=fitter)
    again = quadfit.front_max_checked(got, None, policy=policies[0], relief=policies[1])

    assert again.signed.colour is got.signed.colour
    assert again.screening.colour is got.screening.colour
    if near_listed:
        assert got.drawing["building"] == listed["near"]["building"]
        assert got.facts.fire_route_ft == 120.0
        assert got.signed.colour is Colour.yellow
    else:
        assert got.drawing == base.drawing
        assert got.facts.fire_route_ft == 190.0
        assert got.signed.colour is Colour.red


def test_fire_turn_refuses_an_angle_past_the_front_maximum(corpus, policies, monkeypatch) -> None:
    """FOLLOWUPS 160: the other-angle retry (:func:`_turned_for_fire`) is held
    to the same measure. A turned drawing the hose reaches but that stands
    past the maximum is not taken: the plan stays where it was, RED on the
    hose, rather than RED on the maximum behind a reach it never kept."""
    from flats.fit.angles import normalize
    from flats.fit.rectangle import Fitter
    from flats.ingest import quadfit
    from flats.score.flags import Colour

    lot, s, _ = _placement_retry_case(corpus, policies)
    other = normalize(s.fit.angle_deg + 90.0)
    fitter = Fitter(s.envelope.geom, (s.fit.angle_deg, other), ground=s.envelope.ground)
    base = _coloured(s, Triage.green)
    far = _lifted(base.drawing, 30.0)
    far_polygon = Polygon(far["building"])
    real_drawing_for = quadfit.drawing_for

    def drawing_for(screened, fitter, *, listing=None, where=None, **kwargs):
        if listing is not None:
            return None
        if where is None and math.isclose(screened.fit.angle_deg, other, abs_tol=1e-6):
            return far
        return real_drawing_for(screened, fitter, where=where, **kwargs)

    monkeypatch.setattr(quadfit, "drawing_for", drawing_for)
    monkeypatch.setattr(
        fire, "route_ft", lambda b, *_a, **_k: 120.0 if b.equals(far_polygon) else 190.0
    )

    got = fire_checked(base, lot, None, policy=policies[0], relief=policies[1], fitter=fitter)

    assert got.drawing == base.drawing
    assert got.facts.fire_route_ft == 190.0
    assert got.signed.colour is Colour.red
    assert check(got.screening, "fire_access_ft").verdict is Verdict.fails


def test_a_moved_plan_holds_no_more_frontage_than_where_it_stands(corpus, policies) -> None:
    """FOLLOWUPS 160: the building's share of the frontage was measured on
    the fit's first placement and kept when the fire route or a flatter spot
    moved the building; it is measured again where the building stands, and
    never read higher than it was."""
    import dataclasses

    from flats.ingest import quadfit

    lot, s, _ = _placement_retry_case(corpus, policies)
    held = dataclasses.replace(s, facts=dataclasses.replace(s.facts, building_frontage_pct=(90.0,)))
    placed = held.drawing
    stays = quadfit.moved_checked(held, placed, policy=policies[0], relief=policies[1])
    assert stays is held
    near = quadfit.moved_checked(
        dataclasses.replace(held, drawing=_lifted(placed, 6.0)), placed,
        policy=policies[0], relief=policies[1],
    )
    (share,) = near.facts.building_frontage_pct
    assert 0.0 < share < 90.0  # the building's own width of the street, not more
    far = quadfit.moved_checked(
        dataclasses.replace(held, drawing=_lifted(placed, 30.0)), placed,
        policy=policies[0], relief=policies[1],
    )
    assert far.facts.building_frontage_pct == (0.0,)


def _held_share(corpus, policies, share: float = 90.0):
    """The retry fixture holding ``share`` percent of its street, more than
    its 56 ft building can fill of 200 ft: any re-measure reads less."""
    import dataclasses

    lot, s, fitter = _placement_retry_case(corpus, policies)
    facts = dataclasses.replace(s.facts, building_frontage_pct=(share,))
    return lot, dataclasses.replace(s, facts=facts), fitter


def test_a_turned_court_holds_no_more_frontage_than_where_it_stands(
    corpus, policies, monkeypatch
) -> None:
    """FOLLOWUPS 160: :func:`court_turned` stands the building at another
    angle where its first drawing put the court in a front yard. The share of
    the frontage read on the fit's first placement is measured again where
    the turned building stands, and never read higher."""
    from flats.ingest import quadfit

    lot, s, fitter = _held_share(corpus, policies)
    turned = {**_lifted(s.drawing, 6.0), "lane": s.drawing.get("lane") or [[0, 0]] * 4}
    monkeypatch.setattr(quadfit, "court_in_front_yard", lambda _s, drawn=None: drawn is None)
    monkeypatch.setattr(quadfit, "_lane_in_from_street", lambda _s: True)
    monkeypatch.setattr(quadfit, "_drive_clear", lambda *_a: True)
    monkeypatch.setattr(quadfit, "drawn_door_turned", lambda *_a: False)
    monkeypatch.setattr(quadfit, "_flatter_angles", lambda *_a: [s.fit.angle_deg, 0.0])
    monkeypatch.setattr(quadfit, "drawing_for", lambda *_a, **_k: turned)
    s = _with_drawing(s, {**s.drawing, "lane": turned["lane"]})

    got = quadfit.court_turned(s, fitter, policy=policies[0], relief=policies[1])

    assert got.drawing is turned
    (share,) = got.facts.building_frontage_pct
    assert 0.0 < share < 90.0


def test_a_front_max_slide_holds_no_more_frontage_than_where_it_stands(
    corpus, policies, monkeypatch
) -> None:
    """FOLLOWUPS 160: :func:`front_max_checked` slides or redraws a building
    standing past the maximum; the slid plan is measured again on every
    drawn-plan check, its share of the frontage too, never read higher."""
    from flats.ingest import quadfit
    from flats.score.screen import FRONT_MAX

    lot, s, fitter = _held_share(corpus, policies)
    past = _with_drawing(s, {**_lifted(s.drawing, 14.0), "lane": None})
    slid = {**_lifted(s.drawing, 6.0), "lane": None}
    monkeypatch.setattr(quadfit, "_front_max_flush", lambda *_a, **_k: slid)
    before = quadfit._front_max_screened(past, policy=policies[0], relief=policies[1])
    assert any(c.check == FRONT_MAX for c in before.signed.binds)

    got = quadfit.front_max_checked(past, fitter, policy=policies[0], relief=policies[1])

    assert got.drawing is slid
    assert quadfit._front_max_clear(got)
    (share,) = got.facts.building_frontage_pct
    assert 0.0 < share < 90.0


def _with_drawing(s, drawing):
    import dataclasses

    return dataclasses.replace(s, drawing=drawing)


# --- FOLLOWUPS 163: the retry lists placements at the drawing's own angle ------


def _turned_case(corpus, policies):
    """The retry fixture with a fitter that holds, beside the fit's own 30
    degrees, the angle its drawing stands at (square to the street: the
    maximum front setback's search turned it), as the screen's fitter does."""
    from flats.fit.rectangle import Fitter
    from flats.ingest import quadfit

    lot, s, _ = _placement_retry_case(corpus, policies)
    assert not math.isclose(s.fit.angle_deg, 0.0, abs_tol=1e-6)
    fitter = Fitter(s.envelope.geom, (s.fit.angle_deg, 0.0), ground=s.envelope.ground)
    assert quadfit._drawn_angle(s, fitter) == 0.0
    return lot, s, fitter


def test_the_drawn_angle_is_read_off_the_drawn_building(corpus, policies) -> None:
    """:func:`_drawn_angle` names the fitter's angle the drawn building
    stands at, and nothing where that is the fit's own, the fitter does not
    hold it, or nothing is drawn."""
    from flats.fit.rectangle import Fitter
    from flats.ingest import quadfit

    lot, s, fitter = _turned_case(corpus, policies)
    at_fit = quadfit.drawing_for(s, fitter)
    assert at_fit and at_fit["fits"]
    assert quadfit._drawn_angle(_with_drawing(s, at_fit), fitter) is None
    only_fit = Fitter(s.envelope.geom, (s.fit.angle_deg,), ground=s.envelope.ground)
    assert quadfit._drawn_angle(s, only_fit) is None
    assert quadfit._drawn_angle(_with_drawing(s, None), fitter) is None


def test_fire_retry_lists_placements_at_the_drawing_angle(corpus, policies, monkeypatch) -> None:
    """FOLLOWUPS 163: the drawing stands square to the street while the fit
    stands 30 degrees off it. Listed at the fit's angle, every placement
    stands the far end of its wall past Portland CE's 10 ft maximum, and the
    lot stayed RED on the hose. Listed at the angle the drawing stands at,
    the next placement within the maximum the hose reaches is kept -- and it
    is measured the whole way: the maximum measured again afterwards, as the
    screen does, changes nothing."""
    from flats.ingest import quadfit
    from flats.score.flags import Colour

    lot, s, fitter = _turned_case(corpus, policies)
    first = Polygon(s.drawing["building"])
    monkeypatch.setattr(
        fire, "route_ft", lambda b, *_a, **_k: 190.0 if b.equals(first) else 120.0
    )
    # The other-angle turn is not what moves it.
    monkeypatch.setattr(
        quadfit, "_turned_for_fire", lambda current, *_args, **_kwargs: (current, 190.0)
    )
    base = _coloured(s, Triage.green)

    got = fire_checked(base, lot, None, policy=policies[0], relief=policies[1], fitter=fitter)

    assert got.signed.colour is Colour.yellow
    assert got.drawing["building"] != s.drawing["building"]
    assert quadfit._drawn_angle(got, fitter) == 0.0
    assert got.facts.fire_route_ft == 120.0
    assert all(
        c.verdict is Verdict.passes for c in got.screening.checks if c.check != "fire_access_ft"
    )
    assert check(got.screening, "fire_access_ft").verdict is Verdict.passes
    again = quadfit.moved_checked(got, base.drawing, policy=policies[0], relief=policies[1])
    assert again.signed.colour is got.signed.colour
    assert again.screening.colour is got.screening.colour


@pytest.mark.parametrize("hold", ["drive", "door", "stretch"])
def test_a_placement_at_the_drawing_angle_keeps_what_kept_the_drawing_there(
    corpus, policies, monkeypatch, hold
) -> None:
    """FOLLOWUPS 163: a placement listed at the drawing's own angle is held
    to what the steps that turned the drawing hold theirs to: a drive in
    from the street left clear, and no court moved off its alley stretch or
    doors turned off the street where the drawing had neither. Refused, the
    lot stays as it was."""
    from flats.ingest import quadfit
    from flats.score.flags import Colour

    lot, s, fitter = _turned_case(corpus, policies)
    first = Polygon(s.drawing["building"])
    monkeypatch.setattr(
        fire, "route_ft", lambda b, *_a, **_k: 190.0 if b.equals(first) else 120.0
    )
    monkeypatch.setattr(
        quadfit, "_turned_for_fire", lambda current, *_args, **_kwargs: (current, 190.0)
    )
    real_drawing_for = quadfit.drawing_for
    turned_listed: list[bool] = []

    def drawing_for(screened, fitter, *, listing=None, where=None, **kwargs):
        got = real_drawing_for(screened, fitter, listing=listing, where=where, **kwargs)
        if listing is not None:
            turned_listed.append(math.isclose(screened.fit.angle_deg, 0.0, abs_tol=1e-6))
            # Only the drawing's angle lists anything here.
            if not turned_listed[-1]:
                listing.clear()
        if where is not None and got:
            got = {**got, "lane": got.get("lane") or [[0, 0], [1, 0], [1, 1], [0, 0]]}
        return got

    monkeypatch.setattr(quadfit, "drawing_for", drawing_for)
    if hold == "drive":
        monkeypatch.setattr(quadfit, "_lane_in_from_street", lambda _s: True)
        monkeypatch.setattr(quadfit, "_drive_clear", lambda *_a: False)
    elif hold == "door":
        monkeypatch.setattr(quadfit, "drawn_door_turned", lambda _s, drawing=None: drawing is not None)
    else:
        monkeypatch.setattr(quadfit, "court_off_stretch", lambda _s, drawing=None: drawing is not None)
    base = _coloured(s, Triage.green)

    got = fire_checked(base, lot, None, policy=policies[0], relief=policies[1], fitter=fitter)

    assert turned_listed == [True, False]
    assert got.drawing == base.drawing
    assert got.facts.fire_route_ft == 190.0
    assert got.signed.colour is Colour.red


def test_a_turned_drawing_failing_another_check_is_not_retried(
    corpus, policies, monkeypatch
) -> None:
    """Portland 1S2E07BC  -12600 (fire-reds-158 experiment A, withdrawn):
    the retry runs only where the hose is all that fails. A turned drawing
    that fails something else -- there, a minimum density; here, the fit --
    lists nothing at any angle and is not moved."""
    import dataclasses

    from flats.ingest import quadfit

    lot, s, fitter = _turned_case(corpus, policies)
    original_screen = quadfit.screen

    def fit_fails(*args, **kwargs):
        result = original_screen(*args, **kwargs)
        checks = tuple(
            dataclasses.replace(c, verdict=Verdict.fails) if c.check == "fit_ft" else c
            for c in result.checks
        )
        return dataclasses.replace(result, triage=Triage.red, checks=checks)

    listings = 0
    real_drawing_for = quadfit.drawing_for

    def drawing_for(screened, fitter, *, listing=None, **kwargs):
        nonlocal listings
        if listing is not None:
            listings += 1
        return real_drawing_for(screened, fitter, listing=listing, **kwargs)

    monkeypatch.setattr(quadfit, "screen", fit_fails)
    monkeypatch.setattr(quadfit, "drawing_for", drawing_for)
    monkeypatch.setattr(fire, "route_ft", lambda *_args, **_kwargs: 190.0)
    base = _coloured(s, Triage.green)

    got = fire_checked(base, lot, None, policy=policies[0], relief=policies[1], fitter=fitter)

    assert listings == 0
    assert got.drawing == base.drawing
    assert check(got.screening, "fit_ft").verdict is Verdict.fails
