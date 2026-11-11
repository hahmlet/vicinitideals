"""Set access: crane pads, access, radii and the load-chart check (FOLLOWUPS 145)."""

from __future__ import annotations

import dataclasses
import math

import numpy as np
import pytest
from shapely.geometry import box

from flats.fit import set_access as sa
from flats.fit.set_access import Chart, Reach, Site

#: NOT A REAL CRANE. A made-up chart for these tests only: radius ft ->
#: capacity lb, falling with radius as every chart does.
FAKE_ROWS = ((10.0, 20000.0), (20.0, 12000.0), (30.0, 8000.0), (40.0, 5000.0))


def fake_chart(
    rows=FAKE_ROWS, hook: float | None = 300.0, key: str = "fake_not_a_crane"
) -> Chart:
    return Chart(
        key=key,
        hook_block_lb=hook,
        deductions_lb=0.0,
        max_pct=100.0,
        booms=(tuple(rows),),
    )


#: A 100 x 150 ft lot, street along its south line, the 80 x 25 pod 60 ft
#: back: a pad fits in front of it, on a straight drive from the street.
LOT = box(0, 0, 100, 150)
BUILDING = box(10, 60, 90, 85)
#: The same pod 20 ft back: no pad fits in front, so the crane sets up
#: behind it and needs bends to get there.
NEAR_FRONT = box(10, 20, 90, 45)
STREET = ((0.0, 0.0, 100.0, 0.0),)


@pytest.fixture(scope="module")
def rules() -> sa.Rules:
    return sa.load_rules()


@pytest.fixture(scope="module")
def solved(rules: sa.Rules) -> sa.Result:
    return sa.solve(Site(LOT, BUILDING, STREET), rules)


def test_printed_figures_parse() -> None:
    assert sa.parse_range("8'1\"") == pytest.approx((8 + 1 / 12, 8 + 1 / 12))
    assert sa.parse_range("4'-4'3.5\"") == pytest.approx((4.0, 4 + 3.5 / 12))
    assert sa.parse_range("4-6'") == (4.0, 6.0)
    assert sa.parse_weight("1,000-1,500") == (1000.0, 1500.0)
    assert sa.parse_weight("~4,100") == (4100.0, 4100.0)
    assert sa.parse_size("10 x 8 x 8.5") == ((10, 10), (8, 8), (8.5, 8.5))


def test_config_reads_steph_figures_high_end(rules: sa.Rules) -> None:
    assert (rules.pad_w_ft, rules.pad_l_ft) == (28.0, 40.0)
    assert rules.body_w_ft == pytest.approx(100 / 12)
    # Frame 1,500 + beam 1,100: the high figures.
    assert rules.rigging_lb == 2600.0
    assert rules.load("roof_cassettes", "single").weight_lb == 1194.0
    # Stair kits ride with the homes 3-4 cassette stack; the trusses are unweighed.
    h34 = rules.load("floor_cassettes_h34", "stack")
    assert h34.weight_lb == 4414 + 4 * 508
    assert h34.unweighed == ("loose trusses",)
    assert sum(s.count for s in rules.stacks if s.key != "site_container") == 6
    assert rules.charts == ()  # no chart is invented


def test_pod_frame_reads_the_drawn_footprint() -> None:
    f = sa.pod_frame(NEAR_FRONT)
    assert f.length_ft == pytest.approx(80)
    assert f.depth_ft == pytest.approx(
        25
    )  # the placed design, not the 30 ft piece list
    assert f.centre == pytest.approx((50, 32.5))
    turned = sa.pod_frame(box(0, 0, 25, 80))
    assert turned.length_ft == pytest.approx(80) and abs(
        turned.axis[1]
    ) == pytest.approx(1)


def test_hand_checked_set_radii(rules: sa.Rules) -> None:
    """From an axis of rotation at (50, 100), behind the pod."""
    f = sa.pod_frame(NEAR_FRONT)
    cor = (50.0, 100.0)

    def far(key: str) -> float:
        return max(
            math.dist(cor, p)
            for p in sa.set_points(f, rules.load(key, "single"), rules.homes)
        )

    # Long walls: centres at x = 20..80 on y = 20 and 45; far one (20, 20).
    assert far("ground_long_walls") == pytest.approx(math.hypot(30, 80))
    # Short walls: x = 10..90 on the centreline y = 32.5; far one (10, 32.5).
    assert far("ground_short_walls") == pytest.approx(math.hypot(40, 67.5))
    # Cassettes: centreline, inset 2 ft (half the 4 ft narrowest) -> (12, 32.5).
    assert far("roof_cassettes") == pytest.approx(math.hypot(38, 67.5))
    # Stair kits: anywhere in the footprint -> corner (10, 20).
    assert far("stair_kits") == pytest.approx(math.hypot(40, 80))


def test_truck_radius_at_the_nearest_frontage() -> None:
    site = Site(LOT, NEAR_FRONT, STREET)
    cor = np.array([50.0, 100.0])
    assert sa._truck_ft(site, cor, 0.0) == pytest.approx(100.0)
    # Pushed out into the street, away from the lot.
    assert sa._truck_ft(site, cor, 15.0) == pytest.approx(115.0)


def test_governing_radius_is_the_longer_of_pick_and_set() -> None:
    assert Reach("single", "x", 30.0, 50.0).governing_ft == 50.0
    assert Reach("single", "x", 60.0, 50.0).governing_ft == 60.0
    assert Reach("single", "x", None, 50.0).governing_ft is None


def test_chart_reads_the_next_longer_radius_never_interpolates() -> None:
    c = fake_chart()
    assert c.capacity_at(20.0) == 12000.0
    assert c.capacity_at(20.1) == 8000.0  # not 11,960
    assert c.capacity_at(39.0) == 5000.0
    assert c.capacity_at(40.5) == 0.0  # past the chart
    assert c.capacity_at(9.0) is None  # inside the least radius: unmeasured
    assert c.reach_for(9000.0) == 20.0
    assert c.reach_for(30000.0) is None
    # Two boom columns: the better one at each radius.
    two = Chart(
        "two", 300.0, 0.0, 100.0, (FAKE_ROWS, ((10.0, 15000.0), (25.0, 10000.0)))
    )
    assert two.capacity_at(21.0) == 10000.0


def test_chart_refuses_capacity_rising_with_radius() -> None:
    with pytest.raises(ValueError):
        sa._chart(
            "bad",
            {
                "hook_block_lb": 1,
                "booms": [{"boom_ft": 40, "rows": [[10, 1000], [20, 2000]]}],
            },
            100.0,
        )


def test_unmeasured_with_no_chart(solved: sa.Result) -> None:
    assert solved.checks["pad_room"] == sa.PASS
    assert solved.checks["access"] == sa.PASS  # a straight drive in from the street
    assert solved.checks["lifts"] == sa.UNMEASURED
    assert solved.status == sa.UNMEASURED
    assert "no load chart loaded" in solved.why
    env = solved.best.envelope()
    assert "stack:ground_walls" in env and "single:roof_cassettes" in env
    assert all(r is not None for r in env.values())
    # The best pad is in front of the pod, never on it, and its stacks come
    # off the truck at the lot line: (50, 38) is 38 ft from the street.
    assert not solved.best.polygon.intersects(BUILDING.buffer(-0.01))
    assert solved.best.access == sa.STRAIGHT
    assert env["stack:ground_walls"] == pytest.approx(
        math.dist(solved.best.centre, (solved.best.centre[0], 0))
    )
    # Stair kits reach the far back corner of the pod.
    far_corner = max(math.dist(solved.best.centre, c) for c in BUILDING.exterior.coords)
    assert env["single:stair_kits"] == pytest.approx(far_corner)


def test_pad_behind_the_pod_needs_bends_so_access_is_unmeasured(
    rules: sa.Rules,
) -> None:
    got = sa.solve(Site(LOT, NEAR_FRONT, STREET), rules)
    assert got.checks["pad_room"] == sa.PASS
    assert got.best.access == sa.BENDS
    assert got.checks["access"] == sa.UNMEASURED
    assert got.status == sa.UNMEASURED


def test_lifts_pass_and_fail_against_a_test_chart(
    rules: sa.Rules, solved: sa.Result
) -> None:
    pad = solved.best
    flat = dataclasses.replace(
        rules,
        truck_offset_ft=12.0,
        loads=tuple(dataclasses.replace(ld, unweighed=()) for ld in rules.loads),
    )
    # NOT A REAL CRANE: a big flat chart every lift clears.
    big = fake_chart(rows=((10.0, 50000.0), (300.0, 50000.0)))
    # The pad's own truck pick was measured at the lot line (offset unset).
    ok = sa.check_lifts(pad, flat, big)
    assert ok.status == sa.UNMEASURED  # radius a lower bound
    assert all(
        lf.why == "truck position past the lot line unset"
        for lf in ok.lifts
        if lf.status == sa.UNMEASURED
    )
    measured = dataclasses.replace(
        pad,
        reach=tuple(dataclasses.replace(r, pick_lower_bound=False) for r in pad.reach),
    )
    ok = sa.check_lifts(measured, flat, big)
    assert ok.status == sa.PASS
    walls = next(
        lf for lf in ok.lifts if lf.kind == "stack" and lf.load == "ground_walls"
    )
    assert walls.gross_lb == 12074 + 2600 + 300
    assert ok.binding is walls  # the heaviest lift on a flat chart
    assert walls.slack_lb == pytest.approx(50000 - walls.gross_lb)
    # NOT A REAL CRANE: too small for the wall stack anywhere.
    small = fake_chart(rows=((10.0, 9000.0), (300.0, 9000.0)))
    bad = sa.check_lifts(pad, flat, small)
    assert bad.status == sa.FAIL  # a lower-bound radius that already fails is a fail
    assert (
        bad.binding.load in {"ground_walls", "upper_walls"} and bad.binding.slack_lb < 0
    )
    # Unweighed trusses keep the homes 3-4 stack unmeasured, never pass.
    trusses = sa.check_lifts(measured, rules, big)
    h34 = next(
        lf
        for lf in trusses.lifts
        if lf.kind == "stack" and lf.load == "floor_cassettes_h34"
    )
    assert h34.status == sa.UNMEASURED and h34.gross_lower_bound


def test_no_room_for_the_pad_fails_with_a_reason(rules: sa.Rules) -> None:
    got = sa.solve(Site(box(0, 0, 90, 50), box(5, 15, 85, 40), STREET), rules)
    assert got.status == sa.FAIL
    assert got.checks["pad_room"] == sa.FAIL
    assert any("pad fits" in w for w in got.why)


def test_exit_blocked_by_the_building(rules: sa.Rules) -> None:
    # The pod spans the lot with 3 ft each side: the back yard holds a pad,
    # but no 8.33 ft path reaches the street past the building.
    got = sa.solve(Site(box(0, 0, 86, 150), box(3, 20, 83, 45), STREET), rules)
    assert got.checks["pad_room"] == sa.PASS
    assert got.checks["access"] == sa.FAIL
    assert got.status == sa.FAIL
    # Widen the side gap to 10 ft and the crane drives out down the side.
    wide = sa.solve(Site(box(0, 0, 100, 150), box(3, 20, 83, 45), STREET), rules)
    assert wide.checks["access"] in {sa.PASS, sa.UNMEASURED}


def test_slope_limit_unset_is_unmeasured_and_set_limit_fails(rules: sa.Rules) -> None:
    site = Site(LOT, BUILDING, STREET)
    got = sa.solve(site, rules, grade_of=lambda poly: 3.0)
    assert got.checks["slope"] == sa.UNMEASURED  # no threshold yet
    steep = sa.solve(
        site,
        dataclasses.replace(rules, max_pad_slope_pct=2.0),
        grade_of=lambda poly: 3.0,
    )
    assert steep.checks["slope"] == sa.FAIL and steep.status == sa.FAIL
    level = sa.solve(
        site,
        dataclasses.replace(rules, max_pad_slope_pct=5.0),
        grade_of=lambda poly: 3.0,
    )
    assert level.checks["slope"] == sa.PASS


def test_site_from_drawing() -> None:
    ring = [list(c) for c in BUILDING.exterior.coords]
    assert sa.site_from_drawing(
        LOT, {"fits": True, "building": ring}, STREET
    ).building.equals(BUILDING)
    assert sa.site_from_drawing(LOT, {"fits": False, "building": ring}, STREET) is None
