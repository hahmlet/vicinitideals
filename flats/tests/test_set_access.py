"""Set access, slices 3-4 (FOLLOWUPS 145; Steph 2026-11-14): the IC-80 from
one long face, then both (its trailer on the lot or in the street, pieces
picked there and carried), then the hired 45 t on site and in the street.

Every figure checked here is the crane spec's (Factory-Sim
``docs/research/S3e-crane-20x25.md``) as stored in
``flats/config/set_access.yaml``. Lots are drawn boxes, not real lots."""

from __future__ import annotations

import dataclasses
import math
import re
from pathlib import Path

import types

import numpy as np
import pytest
import yaml
from shapely.geometry import LineString, box

from flats.fit import set_access as sa
from flats.fit.set_access import Site

#: NOT A REAL LOT: the front face 14 ft off the street lot line, 31 ft
#: behind, 12 ft beside each end.
FRONT_LOT = box(0, 0, 104, 70)
FRONT_POD = box(12, 14, 92, 39)
SOUTH = ((0.0, 0.0, 104.0, 0.0),)

#: NOT A REAL LOT: a corner lot whose front yard holds a kept tree; the back
#: face works and the trailer backs in from the side street.
BACK_LOT = box(0, 0, 104, 130)
BACK_STREETS = ((0.0, 0.0, 104.0, 0.0), (0.0, 0.0, 0.0, 130.0))
TREE = box(40, 4, 60, 12)

#: NOT A REAL LOT: a corner lot too tight for the IC-80 (8 ft yards, 10 ft
#: beside the west end) with a back yard for the 45 t's pad.
YARD_LOT = box(0, 0, 140, 150)
YARD_POD = box(10, 8, 90, 33)
YARD_STREETS = ((0.0, 0.0, 140.0, 0.0), (140.0, 0.0, 140.0, 150.0))

#: NOT A REAL LOT: the pod fills the lot; only a street set-up can serve.
FULL_LOT = box(0, 0, 120, 40)
FULL_POD = box(20, 7.5, 100, 32.5)
FULL_STREET = ((0.0, 0.0, 120.0, 0.0),)


def street(width: float | None = 36.0, curb: float | None = 2.0):
    """NOT A REAL STREET: one near curb and one pavement width everywhere
    (None = not measured)."""

    def read(pts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        n = len(np.asarray(pts).reshape(-1, 2))
        return (
            np.full(n, np.nan if curb is None else float(curb)),
            np.full(n, np.nan if width is None else float(width)),
        )

    return read


def centre(gap: float | None = 10.5):
    """NOT A REAL STREET: the centreline ``gap`` ft out from every street lot
    line (None = not held). 10.5 ft puts the IC-80's street trailer (8.5 ft
    wide, its far side at the centreline) 2 ft off the lot line."""

    def read(pts: np.ndarray) -> np.ndarray:
        return np.full(len(np.asarray(pts).reshape(-1, 2)), np.nan if gap is None else float(gap))

    return read


def level(_poly) -> float:
    """NOT A REAL GRADE: every polygon falls 0.5%."""
    return 0.5


@pytest.fixture(scope="module")
def rules() -> sa.Rules:
    return sa.load_rules()


@pytest.fixture(scope="module")
def front(rules: sa.Rules) -> sa.Report:
    return sa.report(Site(FRONT_LOT, FRONT_POD, SOUTH, street(), street_centre=centre()), rules, grade_of=level)


@pytest.fixture(scope="module")
def back(rules: sa.Rules) -> sa.Report:
    return sa.report(Site(BACK_LOT, FRONT_POD, BACK_STREETS, None, obstacles=TREE), rules, grade_of=level)


@pytest.fixture(scope="module")
def yard(rules: sa.Rules) -> sa.Report:
    return sa.report(Site(YARD_LOT, YARD_POD, YARD_STREETS, street(), street_centre=centre()), rules, grade_of=level)


def _lift(plan, key: str) -> sa.Lift:
    return next(lf for lf in plan.lifts if lf.key == key)


def _attempt(rep: sa.Report, step: str) -> sa.Attempt:
    return next(a for a in rep.attempts if a.step == step)


# --------------------------------------------------------------------------
# Step 1 of the build: the figures, as printed
# --------------------------------------------------------------------------


def test_printed_figures_parse() -> None:
    assert sa.parse_range("37 ft 5 in-38 ft 6 in") == pytest.approx((37 + 5 / 12, 38.5))
    assert sa.parse_range("100.3 in") == pytest.approx((100.3 / 12,) * 2)
    assert sa.parse_range("8'1\"") == pytest.approx((8 + 1 / 12,) * 2)
    assert sa.parse_range("6-7") == (6.0, 7.0)
    assert sa.parse_size("25 x 8 ft 6 in") == ((25, 25), (8.5, 8.5))
    assert sa.parse_weight("556-723") == (556.0, 723.0)
    assert sa.parse_weight("~1,100") == (1100.0, 1100.0)


def test_config_holds_the_spec_figures(rules: sa.Rules) -> None:
    raw = yaml.safe_load(sa.RULES_PATH.read_text(encoding="utf-8"))
    assert set(raw) >= {"ic80", "nbt45"} and not any("28" in k for k in raw)  # the 28 t is gone
    ic = rules.ic80
    assert ic.out_w_ft == pytest.approx(9 + 7 / 12)  # 9 ft 7 in spread
    assert ic.off_face_ft == 7 and ic.min_radius_ft == 14 and ic.along_ft == 10
    assert ic.strip_w_ft == 10 and ic.swing_ft == 12 and ic.level_pct == 3  # spec 3.9: ~3% at the pads
    assert ic.rigging_lb == 400 and ic.hook_lb == 90
    assert (ic.route_w_ft, ic.route_turn_w_ft) == pytest.approx((6.5, 9.5))
    assert rules.max_pct == 75 and rules.deck_l_ft == 53
    t = rules.t45
    # Spec 4.1/4.3 (updated): the 250 lb overhaul ball, 11,250 lb on a single
    # line, the 329 lb one-sheave block above it; ~300 lb container slings.
    assert (t.pad_w_ft, t.pad_l_ft) == (28, 42) and t.ball_lb == 250
    assert (t.single_line_lb, t.block_lb, t.container_sling_lb) == (11250, 329, 300)
    assert t.chart.deductions_lb == 450 and t.rigging_lb == 1300
    assert t.whole_rigging_lb == 2600 and t.max_piece_radius_ft == 80 and t.level_pct == 1
    assert len(rules.pieces) == 16
    # Slice 3c: the sample's two wall-gear cases, spec 3.6's 400 and 800 lb columns.
    assert ic.wall_gear_lb == {"light": 400, "heavy": 800} and ic.wall_rigging_lb is None
    # Slice 4b (S3e 3.7/3.10 at 9985b64): walls flat off (FOLLOWUPS 215 a);
    # 3% of the chart lost per 1% downhill; the 360 deg column past ~3%
    # across; 6 ft 6 in upright, ~27 ft crosswise; 20 ft from a line.
    assert (ic.carry_walls_flat, ic.carry_slope_per_pct, ic.carry_cross_pct) == (False, 0.03, 3)
    assert (ic.carry_w_ft, ic.carry_cross_w_ft, ic.carry_power_ft) == (6.5, 27, 20)
    assert ic.carry_chart_360.capacity_at(12) == 3200 and ic.carry_chart.capacity_at(14) == 3400
    assert rules.ic80_places == ("lot", "street") and rules.places == ("lot", "curb")
    # Spec 3.4's per-piece hook table (high ends) and its Load column.
    hooks = {p.key: p.hook_ft for p in rules.pieces}
    assert hooks["ground_front_wall"] == 16 and hooks["upper_back_wall"] == 25
    assert hooks["floor_cassette_wet4f"] == 22 and hooks["roof_cassette_full4"] == 31
    assert (hooks["floor_closing_trusses"], hooks["roof_closing_trusses"]) == (23, 32)
    assert (hooks["stair_truss_pieces"], hooks["stair_kit"]) == (21, 21)
    loads = {p.key: p.loads for p in rules.pieces}
    assert loads["ground_back_wall"] == (1,) and loads["end_wall"] == (1, 3)
    assert loads["floor_closing_trusses"] == (2,) and loads["roof_closing_trusses"] == (4,)
    assert loads["upper_front_wall"] == (3,) and loads["roof_cassette_wet3"] == (4,)
    assert {w.key: w.within_ft for w in rules.whole_loads} == {
        "ground_walls": 35, "upper_walls": 35, "floor_cassettes": 50, "roof_cassettes": 50,
    }


def test_ic80_chart_reads_the_next_longer_radius(rules: sa.Rules) -> None:
    ic = rules.ic80
    assert ic.set_chart.read(31).row_ft == 32 and ic.set_chart.capacity_at(31) == 1750
    assert ic.set_chart.read(21.9).row_ft == 22 and ic.set_chart.capacity_at(21.9) == 3050
    assert ic.set_chart.capacity_at(14) == 5200
    assert ic.carry_chart.read(18.1).row_ft == 20 and ic.carry_chart.capacity_at(18.1) == 1800
    assert max(ic.carry_chart.radii()) == 30  # the extension taken off: no rows past 30 ft
    assert ic.hook_at(32) == 28 and ic.hook_at(31) == 28 and ic.hook_at(40) is None


def test_spec_3_5_chart_use(rules: sa.Rules) -> None:
    """Spec 3.5's table: 400 lb rigging + 90 lb hook, % of chart and the
    farthest radius within 75% (the hook height also holding)."""
    ic = rules.ic80

    def pct(key: str, r: float) -> float:
        p = rules.piece(key)
        return 100 * (p.weight_lb + 490) / ic.set_chart.capacity_at(r)

    assert round(pct("ground_front_wall", 32)) == 74
    assert round(pct("roof_cassette_full4", 22)) == 49
    assert round(pct("ground_back_wall", 32)) == 60
    farthest = {
        "ground_front_wall": 32, "upper_front_wall": 32, "ground_back_wall": 36, "upper_back_wall": 34,
        "end_wall": 34, "party_wall": 34, "roof_cassette_full4": 28,
    }
    for key, want in farthest.items():
        p = rules.piece(key)
        assert ic.reach(p.weight_lb + 490, p.hook_ft) == want, key
    # The stair kit's ~21 ft hook (spec 3.4's table) leaves its 36 ft load
    # reach whole; the roof closing trusses' ~32 ft holds them to 28 ft
    # ("from no more than ~28 ft out", spec 3.4).
    kit = rules.piece("stair_kit")
    assert ic.set_chart.reach_for(kit.weight_lb + 490) == 36
    assert kit.hook_ft == 21 and ic.reach(kit.weight_lb + 490, kit.hook_ft) == 36
    roof_t = rules.piece("roof_closing_trusses")
    assert ic.reach(roof_t.weight_lb + 490, roof_t.hook_ft) == 28
    # Off the trailer the hook height does not limit the pick (spec 3.4).
    full3 = rules.piece("roof_cassette_full3")
    assert ic.reach(full3.weight_lb + 490, full3.hook_ft) == 28
    assert ic.pick_reach(full3.weight_lb + 490) == ic.set_chart.reach_for(full3.weight_lb + 490) > 28


@pytest.mark.parametrize(
    ("key", "want"),
    [("ground_front_wall", (32, 26, 22)), ("upper_front_wall", (32, 28, 22)),
     ("ground_back_wall", (36, 30, 24)), ("upper_back_wall", (34, 28, 24)),
     ("end_wall", (34, 28, 24)), ("party_wall", (34, 28, 24))],
)
def test_spec_3_6_rigging_reach(rules: sa.Rules, key: str, want: tuple[int, int, int]) -> None:
    ic = rules.ic80
    p = rules.piece(key)
    got = tuple(ic.set_chart.reach_for(p.weight_lb + rig + ic.hook_lb) for rig in (400, 800, 1300))
    assert got == want


def test_spec_3_7_carry(rules: sa.Rules) -> None:
    """Walls carried upright on rubber, the extension off: 72% (ground
    front wall), 70-71% (end and party walls). Cassettes go flat and
    crosswise (S3e 3.7 at 9985b64): 25-28% on the 12 ft row, FULL4 44% on
    the 14 ft row; lengthwise (96%) is not tried."""
    ic = rules.ic80
    lift = sa._ic80_carry_lift(ic, rules, rules.piece("ground_front_wall"), None)  # type: ignore[arg-type]
    assert lift.carried and lift.row_ft == 20 and round(lift.pct_of_chart) == 72
    assert lift.status == sa.PASS  # the path is the trailer check's
    end = sa._ic80_carry_lift(ic, rules, rules.piece("end_wall"), None)  # type: ignore[arg-type]
    assert end.row_ft == 22 and round(end.pct_of_chart) == 71
    full4 = rules.piece("roof_cassette_full4")
    assert round(100 * (full4.weight_lb + 490) / ic.carry_chart.capacity_at(20.6)) == 96  # lengthwise: no
    cas = sa._ic80_carry_lift(ic, rules, full4, None)  # type: ignore[arg-type]
    assert cas.radius_ft == 12.1 and cas.row_ft == 14 and round(cas.pct_of_chart) == 44 and cas.status == sa.PASS
    wet = sa._ic80_carry_lift(ic, rules, rules.piece("floor_cassette_wet4f"), None)  # type: ignore[arg-type]
    assert wet.radius_ft == 11.1 and wet.row_ft == 12 and round(wet.pct_of_chart) == 28
    # Across a slope past ~3%: the 360 deg column, 35-58%.
    assert round(sa._ic80_carry_lift(ic, rules, full4, None, across=True).pct_of_chart) == 58  # type: ignore[arg-type]
    # Walls flat and crosswise (only behind the switch): 12.1 ft, 31-38%.
    flat = sa._ic80_carry_lift(ic, rules, rules.piece("ground_front_wall"), None, flat=True)  # type: ignore[arg-type]
    assert flat.row_ft == 14 and round(flat.pct_of_chart) == 38


def test_spec_3_8_container(rules: sa.Rules) -> None:
    ic = rules.ic80
    gross = rules.container_lb + ic.container_sling_lb + ic.hook_lb
    assert gross == 4840
    stowed = dataclasses.replace(ic.set_chart, deductions_lb=ic.stowed_deduct_lb)
    assert stowed.reach_for(gross) == 10
    assert 100 * gross / stowed.capacity_at(10) < 65  # "still under 65%"


def test_spec_4_4_and_4_5(rules: sa.Rules) -> None:
    t = rules.t45
    wall = rules.piece("ground_front_wall")
    assert t.chart.reach_for(wall.weight_lb + t.rigging_lb + t.ball_lb) == 80
    stacks = {w.key: t.chart.reach_for(t.whole_gross(w.stack_lb)) for w in rules.whole_loads}
    # Spec 4.5 prints ~35 / ~35 / ~50 / ~50, the 450 lb folded-jib allowance
    # taken off the chart (spec 4.3).
    assert stacks == {"ground_walls": 35, "upper_walls": 35, "floor_cassettes": 50, "roof_cassettes": 50}
    # The hook: the one-sheave block on the wall stacks (over 11,250 lb on
    # the ball), the ball on the rest.
    walls, roof = rules.whole_loads[0], rules.whole_loads[-1]
    assert t.whole_gross(walls.stack_lb) == walls.stack_lb + 2600 + 329
    assert t.whole_gross(roof.stack_lb) == roof.stack_lb + 2600 + 250
    # The container: ~4,600 + ~300 slings + 250 ball + 450 jib = 5,600 ("~5,600").
    assert rules.container_lb + t.container_sling_lb + t.ball_lb + t.chart.deductions_lb == 5600


# --------------------------------------------------------------------------
# Step 2 of the build: the IC-80 site check
# --------------------------------------------------------------------------


def test_ic80_one_face_from_the_front(front: sa.Report) -> None:
    assert front.result == "IC-80 one face (front)" and front.face == "front"
    plan = front.plan
    assert isinstance(plan, sa.IC80Plan) and plan.status == sa.PASS and plan.truck == "street"
    assert {c.name for c in plan.checks} >= {"working strip", "outriggers", "level", "swing room", "trailer", "route"}
    # Spec 3.5's three reaches: far walls ~31 read at 32, middle pieces ~21.9
    # read at 22, near walls 14.
    assert _lift(plan, "upper_back_wall").set_ft == pytest.approx(32.0, abs=0.01)
    assert _lift(plan, "roof_cassette_full4").set_ft == pytest.approx(math.hypot(10, 19.5), abs=0.01)
    assert _lift(plan, "roof_cassette_full4").row_ft == 22
    assert _lift(plan, "ground_front_wall").set_ft == pytest.approx(14.0, abs=0.01)
    assert round(_lift(plan, "roof_cassette_full4").pct_of_chart) == 49
    # Spec 3.6: the far back wall leaves 1,750 x 75% - 615 - 90 = 607.5 lb.
    assert plan.rigging_limit_lb == pytest.approx(607.5)
    # Spec 3.5 "Front is the default"; the back is still reported.
    assert _attempt(front, "ic80_back").status == sa.FAIL
    assert [a.status for a in front.attempts[2:]] == [sa.NOT_TRIED] * 3


def test_ic80_from_the_back_sets_the_far_front_wall_at_74_percent(back: sa.Report) -> None:
    assert back.result == "IC-80 one face (back)"
    plan = back.plan
    wall = _lift(plan, "ground_front_wall")
    assert wall.row_ft == 32 and round(wall.pct_of_chart) == 74
    assert plan.rigging_limit_lb == pytest.approx(1750 * 0.75 - 798 - 90)
    assert plan.truck == "lot"
    front = _attempt(back, "ic80_front")
    assert front.status == sa.FAIL and any(w.startswith("working strip") for w in front.why)
    assert any(w.startswith("IC-80 one face (front): working strip") for w in back.why)


def test_heavier_rigging_needs_both_faces(rules: sa.Rules) -> None:
    """Spec 3.6: with 800 lb rigging the far walls cannot be set from one
    face; from both, each far wall is set from its own face, ~14 ft out."""
    heavy = dataclasses.replace(rules, ic80=dataclasses.replace(rules.ic80, rigging_lb=800.0))  # NOT A REAL FIGURE
    rep = sa.report(Site(FRONT_LOT, FRONT_POD, SOUTH, street(), street_centre=centre()), heavy, grade_of=level)
    for step in ("ic80_front", "ic80_back"):
        got = _attempt(rep, step)
        assert got.status == sa.FAIL
        assert any(lf.status == sa.FAIL and "planning line" in lf.why for lf in got.plan.sets)
    both = _attempt(rep, "ic80_both").plan
    assert both.faces == ("front", "back")
    assert all(lf.status == sa.PASS for lf in both.sets)
    assert _lift(dataclasses.replace(both, lifts=both.sets), "ground_back_wall").set_ft == pytest.approx(14.0, abs=0.01)
    # Each load parks on its own (Steph 2026-11-14), but loads 1 and 3 each
    # hold a front and a back wall, and one load is one spot: the back wall
    # of each would be carried round, and with 800 lb rigging that carry is
    # over the line (spec 3.7 is figured at 400 lb), so no spot serves them.
    assert set(both.trailer_spots) == {2, 4}
    trailer = next(c for c in both.checks if c.name == "trailer")
    assert trailer.detail.startswith("load 1: ") and "load 4: at the street, every piece within reach" in trailer.detail
    assert "the first short: Ground back wall (carried: over the 75% planning line" in trailer.detail
    assert not any(lf.carried for lf in both.lifts)
    assert not rep.result.startswith("IC-80")


def test_stack_order_follows_the_crane_face(front: sa.Report, back: sa.Report) -> None:
    """DECISIONS S-wallstack: the far face's walls on top; from the back the
    stack is flipped."""
    assert front.row()["stack"] == "back walls on top, end and party walls in the middle, front walls at the bottom"
    assert back.row()["stack"] == "front walls on top, end and party walls in the middle, back walls at the bottom"


CORNER = Site(BACK_LOT, FRONT_POD, BACK_STREETS, street(), street_centre=centre())  # NOT A REAL LOT: BACK_LOT without the tree


def test_heavy_gear_both_faces_with_one_move(rules: sa.Rules) -> None:
    """Slice 3c (option A): with 800 lb wall gear the far walls need both
    faces. Each wall load is stacked back walls on top; the trailer parks
    at the back for the back, end and party walls, then moves once to the
    front for the front walls. Still four deliveries."""
    light = sa.report(CORNER, sa.with_wall_gear(rules, "light"), grade_of=level)
    assert light.result == "IC-80 one face (front)"
    heavy = sa.report(CORNER, sa.with_wall_gear(rules, "heavy"), grade_of=level)
    assert heavy.result == sa.IC80_BOTH
    row = heavy.row()
    assert row["truck"] == "1 lot at the back, then street at the front, 2 lot, 3 lot at the back, then street at the front, 4 lot"
    assert row["stack"].startswith("back walls on top") and row["stack"].endswith(
        "the trailer moves once, back to front (loads 1 and 3)"
    )
    trailer = next(c for c in heavy.plan.checks if c.name == "trailer")
    assert "load 1: parked at the back for the back walls, end and party walls" in trailer.detail
    # Only the walls take the gear.
    roof = _lift(heavy.plan, "roof_cassette_full4")
    assert roof.gross_lb == rules.piece("roof_cassette_full4").weight_lb + 400 + 90
    wall = _lift(heavy.plan, "ground_back_wall")
    assert wall.gross_lb == rules.piece("ground_back_wall").weight_lb + 800 + 90


def test_heavy_gear_needs_a_park_on_both_faces(rules: sa.Rules) -> None:
    """No trailer spot reaches the back face: the move cannot help."""
    heavy = sa.report(Site(FRONT_LOT, FRONT_POD, SOUTH, street(), street_centre=centre()), sa.with_wall_gear(rules, "heavy"),
                      grade_of=level)
    assert not heavy.result.startswith("IC-80")
    both = _attempt(heavy, "ic80_both")
    assert both.status == sa.FAIL and "moved once" not in next(c for c in both.plan.checks if c.name == "trailer").detail


def test_pads_level_within_three_percent(rules: sa.Rules) -> None:
    """Slice 4 (spec 3.9): level applies at each set-up spot's pads, ~3%;
    the strip between need not be level."""
    site = Site(FRONT_LOT, FRONT_POD, SOUTH, street(), street_centre=centre())
    assert sa.report(site, rules, grade_of=lambda _p: 2.5).result == "IC-80 one face (front)"
    steep = sa.report(site, rules, grade_of=lambda _p: 4.0)
    assert not steep.result.startswith("IC-80")
    assert "level" in _attempt(steep, "ic80_front").plan.binding_check
    blind = sa.report(site, rules, grade_of=lambda _p: None)
    assert _attempt(blind, "ic80_front").status == sa.UNMEASURED
    none = sa.report(site, rules)
    assert _attempt(none, "ic80_front").status == sa.UNMEASURED
    assert any("no elevation model read" in w for w in none.why)


def test_swing_room_twelve_feet_beyond_each_end(rules: sa.Rules) -> None:
    # 8 ft beside the west end: the outriggers (5.85 ft past the end) fit, the swing does not.
    rep = sa.report(Site(box(4, 0, 104, 70), FRONT_POD, ((4.0, 0.0, 104.0, 0.0),), street(), street_centre=centre()), rules,
                    grade_of=level)
    got = _attempt(rep, "ic80_front")
    assert got.status == sa.FAIL and got.plan.binding_check == "swing room"


def test_route_six_and_a_half_feet_wide(rules: sa.Rules) -> None:
    """A wall along the street leaves one gap: 5 ft stops the IC-80; 8 ft
    lets it drive straight in to open ground where it can turn."""

    def wall(gap: float):
        return box(0, 0.2, 50, 1.5).union(box(50 + gap, 0.2, 104, 1.5))

    shut = sa.report(Site(FRONT_LOT, FRONT_POD, SOUTH, street(), obstacles=wall(5)), rules, grade_of=level)
    route = next(c for c in _attempt(shut, "ic80_front").plan.checks if c.name == "route")
    assert route.status == sa.FAIL
    open_ = sa.report(Site(FRONT_LOT, FRONT_POD, SOUTH, street(), obstacles=wall(8)), rules, grade_of=level)
    route = next(c for c in _attempt(open_, "ic80_front").plan.checks if c.name == "route")
    assert route.status == sa.PASS and "straight in" in route.detail


def test_back_face_carries_from_the_street(front: sa.Report) -> None:
    """From the back face the street trailer is ~50 ft off: every piece is
    picked in the street and carried. The walls go upright through a 12 ft
    side yard; a crosswise cassette needs ~27 ft and finds none."""
    got = _attempt(front, "ic80_back")
    trailer = next(c for c in got.plan.checks if c.name == "trailer")
    assert trailer.status == sa.FAIL
    assert "load 1: at the street, end wall, ground back wall, ground front wall, party wall picked there and carried" \
        in trailer.detail
    assert "carried walls upright, path 6.5 ft wide" in trailer.detail
    assert "carried cassettes flat, crosswise, path 27 ft wide" in trailer.detail
    assert "paving" not in trailer.detail


def test_trailer_unmeasured_where_the_centreline_is_not(rules: sa.Rules) -> None:
    rep = sa.report(Site(FRONT_LOT, FRONT_POD, SOUTH, None), rules, grade_of=level)
    got = _attempt(rep, "ic80_front")
    trailer = next(c for c in got.plan.checks if c.name == "trailer")
    # Slice 4b: every piece may now be carried, so the street trailer at a
    # place not read is tried, and is never better than unmeasured.
    assert trailer.status == sa.UNMEASURED and "where the trailer stands is not measured" in trailer.detail
    assert not rep.result.startswith("IC-80")


def test_the_curb_is_ignored_for_the_ic80(rules: sa.Rules) -> None:
    """Steph 2026-11-14: "ignore the curb". The IC-80's street trailer is
    placed from the centreline; no curb read changes it."""
    for curb in (None, 2.0, 30.0):
        rep = sa.report(Site(FRONT_LOT, FRONT_POD, SOUTH, street(curb=curb), street_centre=centre()), rules,
                        grade_of=level)
        assert rep.result == "IC-80 one face (front)" and rep.row()["ic80_way"] == "street"


def test_street_trailer_spots_from_the_centreline(rules: sa.Rules) -> None:
    site = Site(FRONT_LOT, FRONT_POD, SOUTH, None, street_centre=centre())
    spots, measured = sa.street_truck_spots(site, rules)
    assert measured and len(spots) and set(spots.place) == {"street"}
    # Its far side at the centreline, 10.5 ft out: the deck 2 ft off the lot line.
    assert np.allclose(spots.centres[:, 1], -(10.5 - rules.truck_w_ft / 2))
    none, measured = sa.street_truck_spots(Site(FRONT_LOT, FRONT_POD, SOUTH, None), rules)
    assert not measured and not len(none)
    far, measured = sa.street_truck_spots(Site(FRONT_LOT, FRONT_POD, SOUTH, None, street_centre=centre(None)), rules)
    assert not measured and not len(far)


#: NOT A REAL LOT: 30 ft side yards both ends and a 46 ft back yard, so a
#: crosswise cassette (~27 ft path) gets round the pod to where it hangs
#: off the back face (crane 7 ft out, the panel ~12 ft beyond).
WIDE_LOT = box(0, 0, 140, 85)
WIDE_POD = box(30, 14, 110, 39)
WIDE_SOUTH = ((0.0, 0.0, 140.0, 0.0),)


def test_crosswise_cassettes_carried_round_a_wide_side_yard(rules: sa.Rules) -> None:
    """Slice 4b: from the back face every piece is carried from the street,
    the cassettes flat and crosswise down a 30 ft side yard."""
    rep = sa.report(Site(WIDE_LOT, WIDE_POD, WIDE_SOUTH, street(), street_centre=centre()), rules, grade_of=level)
    back = _attempt(rep, "ic80_back").plan
    trailer = next(c for c in back.checks if c.name == "trailer")
    assert trailer.status == sa.PASS and "cassettes flat, crosswise, path 27 ft wide" in trailer.detail, trailer.detail
    assert back.status == sa.PASS and "carry" in back.way


def test_carry_slope_costs_the_chart(rules: sa.Rules) -> None:
    """Spec 3.7 [est]: usable chart = chart x (1 - 0.03 x downhill %). An
    upright wall (72%) takes ~1%; a crosswise cassette (44% at most) takes
    5%; past ~3% the 360 deg column is read."""
    lot = types.SimpleNamespace(rules=rules)
    wall, cas = [rules.piece("ground_front_wall")], [rules.piece("roof_cassette_full4")]
    assert sa._carry_slope(lot, wall, False, 1.0, "")[0] == sa.PASS  # type: ignore[arg-type]  # 71.6 / 0.97 = 73.8%
    st, why = sa._carry_slope(lot, wall, False, 2.0, "")  # type: ignore[arg-type]
    assert st == sa.FAIL and "planning line" in why
    assert sa._carry_slope(lot, cas, False, 3.0, "")[0] == sa.PASS  # type: ignore[arg-type]  # 43.7 / 0.91 = 48%
    st, why = sa._carry_slope(lot, cas, False, 5.0, "")  # type: ignore[arg-type]  # 360 deg: 58.3 / 0.85 = 69%
    assert st == sa.PASS and "360 deg" in why
    st, why = sa._carry_slope(lot, cas, False, 8.0, "")  # type: ignore[arg-type]  # 58.3 / 0.76 = 77%
    assert st == sa.FAIL
    assert sa._carry_slope(lot, cas, False, None, "not read")[0] == sa.UNMEASURED  # type: ignore[arg-type]
    assert sa._carry_slope(lot, cas, False, 0.0, "")[0] == sa.PASS  # type: ignore[arg-type]


def test_walls_flat_switch(rules: sa.Rules) -> None:
    """Walls carried flat and crosswise wait on FOLLOWUPS 215(a): off by
    default; on, a wall over the line upright (heavy gear) can go flat."""
    assert sa.with_carry(rules).ic80 == rules.ic80
    heavy = sa.with_wall_gear(rules, "heavy")
    ic = heavy.ic80
    gf = heavy.piece("ground_front_wall")
    assert sa._ic80_carry_lift(ic, heavy, gf, None).status == sa.FAIL  # type: ignore[arg-type]
    assert sa._ic80_carry_lift(ic, heavy, gf, None, flat=True).status == sa.PASS  # type: ignore[arg-type]
    site = Site(WIDE_LOT, WIDE_POD, WIDE_SOUTH, street(), street_centre=centre())
    off = _attempt(sa.report(site, heavy, grade_of=level), "ic80_back").plan
    on = _attempt(sa.report(site, sa.with_carry(heavy, walls_flat=True), grade_of=level), "ic80_back").plan
    t_off = next(c for c in off.checks if c.name == "trailer")
    t_on = next(c for c in on.checks if c.name == "trailer")
    assert "walls flat, crosswise" not in t_off.detail and "walls flat, crosswise" in t_on.detail
    assert sa._ORDER[t_on.status] <= sa._ORDER[t_off.status]


def test_power_line_notes(rules: sa.Rules, front: sa.Report) -> None:
    """Spec 3.10 at 9985b64: never checked; a carry names 1926.1411(a), a
    street trailer names the four ways a street plan still works."""
    rep = sa.report(Site(WIDE_LOT, WIDE_POD, WIDE_SOUTH, street(), street_centre=centre()), rules, grade_of=level)
    back = _attempt(rep, "ic80_back").plan
    assert any("1926.1411(a)" in n and "de-energises and grounds" in n for n in back.notes)
    assert any(n.startswith("street trailer: with a power line on the lot's side") for n in front.plan.notes)
    assert not any("1926.1411(a)" in n for n in front.plan.notes)  # nothing carried from the front


def test_canopy_blocks_and_its_cost_is_shown(rules: sa.Rules) -> None:
    """Slice 4: a canopy map's crowns (no height read) in the swing room
    block the IC-80; the answer without trees is reported beside it."""
    crown = sa.Trees(box(2, 20, 8, 30))  # NOT A REAL TREE: in the west swing room
    rep = sa.report(Site(FRONT_LOT, FRONT_POD, SOUTH, street(), street_centre=centre(), trees=crown), rules,
                    grade_of=level)
    plan = _attempt(rep, "ic80_front").plan
    trees = next(c for c in plan.checks if c.name == "trees")
    assert trees.status == sa.FAIL and "swing room" in trees.detail
    assert plan.status == sa.FAIL and plan.bare_status == sa.PASS
    assert not rep.result.startswith("IC-80 one face (front)")
    assert rep.result_no_trees == "IC-80 one face (front)"
    row = rep.row()
    assert row["result_no_trees"] == "IC-80 one face (front)" and "trees" in row["ic80_front_checks"]
    # Off the map: unmeasured, never a pass.
    off = sa.report(Site(FRONT_LOT, FRONT_POD, SOUTH, street(), street_centre=centre(),
                         trees=sa.Trees(box(0, 0, 0, 0), covered=False)), rules, grade_of=level)
    assert next(c for c in _attempt(off, "ic80_front").plan.checks if c.name == "trees").status == sa.UNMEASURED
    assert off.result == sa.UNMEASURED_ANSWER or not off.result.startswith("IC-80")


def test_canopy_on_the_carry_path(rules: sa.Rules) -> None:
    """Crowns across the front yard leave the swing room and the back
    working ground clear but stand on every carry path from the street."""
    crown = sa.Trees(box(0, 0.5, 104, 10))  # NOT A REAL TREE
    site = Site(FRONT_LOT, FRONT_POD, SOUTH, street(), street_centre=centre(), trees=crown)
    rep = sa.report(site, rules, grade_of=level)
    trees = next(c for c in _attempt(rep, "ic80_back").plan.checks if c.name == "trees")
    assert trees.status == sa.FAIL and "carry path of load 1 and 3" in trees.detail


def test_unknown_front_names_the_faces_and_takes_the_worse(rules: sa.Rules) -> None:
    rep = sa.report(Site(FRONT_LOT, FRONT_POD, (), None), rules, grade_of=level)
    assert rep.result == sa.UNMEASURED_ANSWER
    one = _attempt(rep, "ic80_front").plan
    assert one.faces == ("long face 1",)
    # Front walls taken on both faces: the far wall is the heavier front wall.
    assert _lift(one, "ground_front_wall").set_ft == pytest.approx(32.0, abs=0.01)
    assert any(w.startswith("IC-80 one face (long face 1)") for w in rep.why)


def test_container_side_check_is_reported_not_ruled(front: sa.Report) -> None:
    """Spec 3.8: within ~10 ft of the IC-80. A trailer 2 ft off the lot line
    leaves no room for the crane between it and the lot, even in the street;
    it is reported beside the answer, not in it."""
    assert front.plan.container.status == sa.FAIL
    assert front.result.startswith("IC-80")
    assert front.row()["container"] == sa.FAIL


def test_container_may_be_lifted_from_the_street(rules: sa.Rules) -> None:
    """Steph 2026-11-14: the IC-80 may step into the street for the
    container lift only. With 10 ft between the lot line and the curb, the
    crane stands there; without the street stance it cannot."""
    site = Site(box(0, 0, 104, 80), box(12, 24, 92, 49), SOUTH, street(curb=10), street_centre=centre(18.5))  # NOT A REAL LOT
    got = _attempt(sa.report(site, rules, grade_of=level), "ic80_front").plan.container
    assert got.status == sa.PASS and "in the street for this lift; power lines not checked" in got.detail
    off = dataclasses.replace(rules, ic80=dataclasses.replace(rules.ic80, container_street=False))
    assert _attempt(sa.report(site, off, grade_of=level), "ic80_front").plan.container.status == sa.FAIL


# --------------------------------------------------------------------------
# Step 3 of the build: the 45 t
# --------------------------------------------------------------------------


def test_45t_on_site_where_the_ic80_cannot(yard: sa.Report, rules: sa.Rules) -> None:
    assert yard.result == sa.T45_SITE
    for step in ("ic80_front", "ic80_back", "ic80_both"):
        assert _attempt(yard, step).status == sa.FAIL
    plan = yard.plan
    assert isinstance(plan, sa.Plan) and plan.access == sa.STRAIGHT and plan.level == sa.PASS
    assert plan.mode == "whole_load" and plan.truck == "lot"
    assert all(lf.radius_ft <= 80 + 1e-6 for lf in plan.lifts if lf.what == "piece")
    for w in rules.whole_loads:
        lf = _lift(plan, w.key)
        assert lf.radius_ft <= w.within_ft + 1e-6 and lf.status == sa.PASS
    # The stack lands where the trailer stood, clear of the pad.
    assert not plan.truck_spot.intersects(plan.pad.buffer(-0.01))
    assert _attempt(yard, "45t_street").status == sa.NOT_TRIED


def test_45t_pad_level_within_one_percent(rules: sa.Rules) -> None:
    rep = sa.report(Site(YARD_LOT, YARD_POD, YARD_STREETS, street()), rules, grade_of=lambda _p: 2.0)
    got = _attempt(rep, "45t_site")
    assert got.status == sa.FAIL and got.plan.level == sa.FAIL
    blind = sa.report(Site(YARD_LOT, YARD_POD, YARD_STREETS, street()), rules)
    assert _attempt(blind, "45t_site").status == sa.UNMEASURED


def test_street_set_up_needs_the_width(rules: sa.Rules) -> None:
    narrow = sa.report(Site(FULL_LOT, FULL_POD, FULL_STREET, street(width=24)), rules, grade_of=level)
    assert narrow.result == sa.NOT_VIABLE
    assert any("24 ft wide at most; the 45 t pad needs 28 ft" in w for w in narrow.why)
    assert _attempt(narrow, "45t_site").status == sa.FAIL
    blind = sa.report(Site(FULL_LOT, FULL_POD, FULL_STREET, street(width=None)), rules, grade_of=level)
    assert _attempt(blind, "45t_street").status == sa.UNMEASURED
    assert blind.result == sa.UNMEASURED_ANSWER


def test_street_pad_stands_at_the_near_curb(rules: sa.Rules) -> None:
    lot = _lot(Site(FULL_LOT, FULL_POD, FULL_STREET, street(width=36, curb=12)), rules)
    pads, status, _ = sa._street_pads(lot, rules.t45, [sa.set_points(lot.frame, p, rules.homes) for p in rules.pieces])
    assert status == sa.PASS and pads
    centre, _, access = pads[0]
    assert access == sa.STRAIGHT and centre[1] == pytest.approx(-(12 + 14))


def _lot(site: Site, rules: sa.Rules) -> sa._Lot:
    frame = sa.pod_frame(site.building)
    curb, measured = sa.curb_truck_spots(site, rules)
    return sa._Lot(site, rules, frame, sa._front(site, frame), site.lot.difference(site.building),
                   sa.lot_truck_spots(site, rules), curb, measured, None)


def test_truck_spots_hold_the_53_ft_deck(rules: sa.Rules) -> None:
    site = Site(YARD_LOT, YARD_POD, YARD_STREETS, street())
    lot = sa.lot_truck_spots(site, rules)
    assert len(lot)
    sides = np.hypot(*(lot.corners[:, 1] - lot.corners[:, 0]).T)
    assert np.allclose(sides, 53.0)
    curb, measured = sa.curb_truck_spots(site, rules)
    assert measured and len(curb)
    # At the near curb (2 ft out) on the south street: the deck's near side 2 ft off.
    south = curb.centres[np.isclose(curb.axis[:, 1], 0.0)]
    assert np.allclose(south[:, 1], -(2 + rules.truck_w_ft / 2))


# --------------------------------------------------------------------------
# Step 4 of the build: the per-lot output
# --------------------------------------------------------------------------


def test_report_row(front: sa.Report, yard: sa.Report) -> None:
    row = front.row()
    assert row["result"] == "IC-80 one face (front)" and row["face"] == "front" and row["crane"] == "IC-80"
    assert row["hardest_lift"] == "Upper back wall" and row["chart_row_ft"] == 32
    assert row["binding_check"] == "lifts: Upper back wall"
    assert row["truck"] == "1 street, 2 street, 3 street, 4 street"  # each trailer load's spot
    assert row["ic80_way"] == "street" and row["ic80_front_way"] == "street" and row["ic80_front_checks"] == ""
    assert row["rigging_limit_lb"] == 608 and row["ic80_front"] == sa.PASS and row["45t_site"] == sa.NOT_TRIED
    assert set(sa.STEPS) <= set(row)
    y = yard.row()
    assert y["result"] == "45 t on site" and y["crane"] == "45 t" and y["mode"] == "whole_load"
    assert "IC-80 one face (front)" in y["why"]


def test_power_lines_not_checked_on_every_set_up(front: sa.Report, back: sa.Report, yard: sa.Report, rules: sa.Rules) -> None:
    narrow = sa.report(Site(FULL_LOT, FULL_POD, FULL_STREET, street(width=24), street_centre=centre()), rules,
                       grade_of=level)
    for rep in (front, back, yard, narrow):
        assert sa.POWER_NOTE in rep.notes
        assert sa.POWER_NOTE in rep.row()["notes"]
        assert any("overhead power lines" in n for n in rep.not_checked)
        for a in rep.attempts:
            if a.plan is not None:
                assert sa.POWER_NOTE in a.plan.notes


def test_no_answer_leaves_every_reason(rules: sa.Rules) -> None:
    rep = sa.report(Site(FULL_LOT, FULL_POD, FULL_STREET, street(width=24)), rules, grade_of=level)
    steps = {w.split(":")[0] for w in rep.why}
    assert {"IC-80 one face (front)", "IC-80 one face (back)", "IC-80 both faces", "45 t on site",
            "45 t in the street"} <= steps


# --------------------------------------------------------------------------
# Plumbing
# --------------------------------------------------------------------------


def test_site_from_drawing() -> None:
    ring = [list(p) for p in FRONT_POD.exterior.coords]
    site = sa.site_from_drawing(FRONT_LOT, {"fits": True, "building": ring}, SOUTH, street(30))
    assert site is not None and site.building.equals(FRONT_POD) and site.street_reading is not None
    assert sa.site_from_drawing(FRONT_LOT, {"fits": False, "building": ring}, SOUTH) is None


def test_street_reader_reads_curb_and_width() -> None:
    from flats.geom.curbs import StreetEdges

    centre = LineString([(-50, -20), (150, -20)])
    edges = StreetEdges.build(widths=[(LineString([(-50, -21), (150, -21)]), 36.0)])
    read = sa.street_reader(edges, np.array([centre], dtype=object), max_gap_ft=50.0)
    curb, width = read(np.array([[50.0, 0.0], [50.0, 200.0]]))
    assert width[0] == 36 and curb[0] == pytest.approx(20 - (18 - 3))
    assert math.isnan(width[1]) and math.isnan(curb[1])  # too far from any street


def test_report_only_nothing_reads_it_into_the_colour() -> None:
    """Steph 2026-11-14: no colour, reasons or flags. Nothing in flats/
    outside this module imports set_access."""
    root = Path(sa.__file__).resolve().parents[1]
    users = [
        p
        for p in root.rglob("*.py")
        if p.name not in ("set_access.py", "test_set_access.py")
        and re.search(
            r"(import\s+flats\.fit\.set_access|from\s+flats\.fit\.set_access\s+import"
            r"|from\s+flats\.fit\s+import\s+[^\n]*\bset_access\b)",
            p.read_text(encoding="utf-8", errors="ignore"),
        )
    ]
    assert users == []
