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
            "type": ["1400", "1600", "1800", "1110", "1700", "1500"],
            "alley": [False, True, False, False, False, True],
            "wkb": [line(y) for y in range(6)],
        }
    ).to_parquet(tmp_path / "s1_streets.parquet")
    _, geoms = fire.load_truck_roads(tmp_path / "s1_streets.parquet")
    # A local street and a named private road; not an alley, an unnamed
    # drive, a freeway, or a street the stage file marked an alley.
    assert sorted(g.coords[0][1] for g in geoms) == [0.0, 4.0]


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

X0, Y0 = 7_650_000.0, 680_000.0


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


def _coloured(s, triage: Triage):
    import dataclasses

    return dataclasses.replace(
        s,
        screening=dataclasses.replace(s.screening, triage=triage),
        signed=dataclasses.replace(s.signed, triage=triage),
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


def test_a_plan_short_of_green_with_a_route_is_still_measured(corpus, policies) -> None:
    lot = lot_from_row(bridge_row(), corpus.layers)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    got = fire_checked(_coloured(s, Triage.yellow), lot, None, policy=policies[0], relief=policies[1])
    assert got.facts.fire_route_tried and got.facts.fire_route_ft is not None


def test_a_plan_red_both_ways_is_not_measured(corpus, policies) -> None:
    lot = lot_from_row(bridge_row(), corpus.layers)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    import dataclasses

    red = dataclasses.replace(
        s,
        screening=dataclasses.replace(s.screening, triage=Triage.red),
        signed=dataclasses.replace(s.signed, triage=Triage.red),
        facts=dataclasses.replace(s.facts, fire_route_ft=None, fire_route_tried=False),
    )
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
