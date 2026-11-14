"""Set access report: two cranes from Steph's guide, truck spots, street
set-ups (FOLLOWUPS 145, slice 2)."""

from __future__ import annotations

import dataclasses
import math
import re
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import LineString, Polygon, box

from flats.fit import set_access as sa
from flats.fit.set_access import Site

#: A 100 x 150 ft lot, street along its south line, the 80 x 25 pod 60 ft
#: back: room in front of it for a pad and a truck backed in.
LOT = box(0, 0, 100, 150)
BUILDING = box(10, 60, 90, 85)
STREET = ((0.0, 0.0, 100.0, 0.0),)
#: A 90 x 60 ft lot the pod nearly fills: no pad fits on it.
TIGHT = box(0, 0, 90, 60)
TIGHT_POD = box(5, 20, 85, 45)
TIGHT_STREET = ((0.0, 0.0, 90.0, 0.0),)


def street(width: float | None, curb: float | None = 12.0):
    """NOT A REAL STREET: a street reading with one near curb and one
    pavement width everywhere (None = not measured)."""

    def read(pts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        n = len(np.asarray(pts).reshape(-1, 2))
        return (
            np.full(n, np.nan if curb is None else float(curb)),
            np.full(n, np.nan if width is None else float(width)),
        )

    return read


@pytest.fixture(scope="module")
def rules() -> sa.Rules:
    return sa.load_rules()


@pytest.fixture(scope="module")
def deep(rules: sa.Rules) -> sa.Report:
    return sa.report(Site(LOT, BUILDING, STREET, street(36)), rules)


@pytest.fixture(scope="module")
def light(rules: sa.Rules) -> sa.Rules:
    """NOT A REAL FIGURE: the guide's rules with the site container made
    weightless, so the 28 t's other lifts decide."""
    return dataclasses.replace(rules, container_lb=0.0)


def test_printed_figures_parse() -> None:
    assert sa.parse_range("37 ft 5 in-38 ft 6 in") == pytest.approx((37 + 5 / 12, 38.5))
    assert sa.parse_range("100.3 in") == pytest.approx((100.3 / 12,) * 2)
    assert sa.parse_range("8'1\"") == pytest.approx((8 + 1 / 12,) * 2)
    assert sa.parse_size("25 x 8 ft 6 in") == ((25, 25), (8.5, 8.5))
    assert sa.parse_weight("556-723") == (556.0, 723.0)
    assert sa.parse_weight("~1,100") == (1100.0, 1100.0)


def test_config_holds_the_guide_figures(rules: sa.Rules) -> None:
    t28, t45 = rules.cranes
    assert (t28.short, t28.pad_w_ft, t28.pad_l_ft, t28.swing) == ("28 t", 26, 42, "rear_180")
    assert (t45.short, t45.pad_w_ft, t45.pad_l_ft, t45.swing) == ("45 t", 28, 42, "full_360")
    assert t28.method == "off_trailer" and t45.method == "whole_load"
    assert t28.chart.deductions_lb == 250  # folded jib, taken off
    assert t45.body_w_ft == pytest.approx(100.3 / 12)
    # Rigging, high ends: single picks 1,300; whole loads 1,500 + 1,100 + 500.
    assert rules.rig_single_lb == 1300 and rules.rig_whole_lb == 3100
    assert max(p.weight_lb for p in rules.pieces) == 863  # roof cassette, stair side
    assert rules.container_lb == 4600
    assert [w.stack_lb for w in rules.whole_loads] == [10339, 11120, 10273, 10186]
    assert rules.load_fp == (25, 8.5) and rules.truck_w_ft == 8.5
    # The 30 ft-depth piece list is gone.
    text = sa.RULES_PATH.read_text(encoding="utf-8")
    assert "30 ft depth" not in text and "12,074" not in text


def test_charts_read_the_next_longer_radius(rules: sa.Rules) -> None:
    t28, t45 = (c.chart for c in rules.cranes)
    got = t28.read(58.3)
    assert (got.row_ft, got.boom_ft, got.capacity_lb) == (60, 92, 3210)
    assert t28.read(60.0).capacity_lb == 3210
    assert (t28.read(60.01).row_ft, t28.read(60.01).capacity_lb) == (65, 2660)
    assert (t28.read(10).boom_ft, t28.read(10).capacity_lb) == (28, 34520)
    assert t28.read(9.9) is None  # inside every column's least radius
    beyond = t28.read(70.5)
    assert beyond.capacity_lb == 0 and beyond.row_ft is None and beyond.boom_ft is None
    assert t45.read(60).capacity_lb == 7660 and t45.read(60).boom_ft == 91
    assert t45.read(35).capacity_lb == 18900
    assert t45.read(60.5).capacity_lb == 0
    radii = np.linspace(5, 75, 141)
    for chart in (t28, t45):
        vec = chart.capacities(radii)
        scalar = [chart.capacity_at(r) for r in radii]
        assert [None if math.isnan(v) else v for v in vec] == scalar


def test_the_guide_chart_use_figures_come_out(rules: sa.Rules) -> None:
    """Guide section 4: the hardest single pick (front wall 798 lb + 800-1,300
    lb rigging) uses 51-66% of the 28 t (no jib, 60 ft line) and 21-28% of
    the 45 t; load 1's gross is ~12,900-13,400 lb."""
    t28, t45 = (c.chart for c in rules.cranes)
    cap77 = dict(t28.booms)[77.0]
    at60 = dict(cap77)[60.0]
    assert round(100 * (798 + 800) / at60) == 51 and round(100 * (798 + 1300) / at60) == 66
    at60_45 = dict(dict(t45.booms)[79.0])[60.0]
    assert 100 * (798 + 800) / at60_45 == pytest.approx(21, abs=0.5)
    assert 100 * (798 + 1300) / at60_45 == pytest.approx(28, abs=0.51)  # 27.5, the guide rounds up
    assert abs(10339 + rules.rig_whole_lb - 13400) <= 50


def test_set_points_hand_check(rules: sa.Rules) -> None:
    """Crane centred 25 ft behind the back wall: the end homes' front walls
    58.3 ft away, the end cassettes about 54 ft (guide section 4)."""
    frame = sa.pod_frame(box(-40, -12.5, 40, 12.5))
    assert (frame.length_ft, frame.depth_ft) == pytest.approx((80, 25))
    crane = np.array([0.0, -37.5])

    def far(key: str) -> float:
        piece = next(p for p in rules.pieces if p.key == key)
        return float(np.hypot(*(sa.set_points(frame, piece, rules.homes) - crane).T).max())

    assert far("ground_front_wall") == pytest.approx(math.hypot(30, 50))
    assert far("other_cassettes") == pytest.approx(math.hypot(40, 37.5))
    assert far("roof_cassette_stair") == pytest.approx(math.hypot(36, 37.5))
    # Stair kits and truss bundles: no farther than the walls (the guide).
    assert far("stair_kits") <= far("other_walls") + 1e-9


def test_28t_first_and_the_ladder_stops_at_a_pass(light: sa.Rules) -> None:
    rep = sa.report(Site(LOT, BUILDING, STREET, street(36)), light)
    assert (rep.crane, rep.setup) == ("28 t", "site")
    assert [(a.crane, a.setup, a.status) for a in rep.attempts] == [
        ("28 t", "site", "pass"),
        ("45 t", "site", sa.NOT_TRIED),
        ("28 t", "street", sa.NOT_TRIED),
        ("45 t", "street", sa.NOT_TRIED),
    ]
    plan = rep.plan
    assert plan.mode == "off_trailer" and plan.access == sa.STRAIGHT
    # Over the rear only: every set point and the whole truck spot lie
    # behind the pad's rear end.
    rear = np.array([math.cos(math.radians(plan.rear_deg)), math.sin(math.radians(plan.rear_deg))])
    pad_c = np.array(plan.pad.centroid.coords[0])
    origin = pad_c + rear * 21.0
    frame = sa.pod_frame(BUILDING)
    for piece in light.pieces:
        assert (((sa.set_points(frame, piece, light.homes) - origin) @ rear) >= -1e-6).all()
    assert (((np.asarray(plan.truck_spot.exterior.coords) - origin) @ rear) >= -1e-6).all()


def test_45t_only_where_the_28t_misses(deep: sa.Report) -> None:
    status = {(a.crane, a.setup): a.status for a in deep.attempts}
    assert status[("28 t", "site")] == "fail"
    assert any("Site container over the chart" in w for w in deep.attempts[0].why)
    assert status[("45 t", "site")] == "pass"
    assert status[("28 t", "street")] == sa.NOT_TRIED
    assert (deep.crane, deep.setup) == ("45 t", "site")


def test_45t_lands_each_whole_load_where_the_truck_stood(deep: sa.Report, rules: sa.Rules) -> None:
    plan = deep.plan
    assert (plan.mode, plan.truck) == ("whole_load", "lot")
    spot = plan.truck_spot
    # The load's plan, square to the street, on the lot, clear of the pod
    # and the pad.
    assert spot.area == pytest.approx(25 * 8.5)
    xs, ys = zip(*spot.exterior.coords)
    assert max(ys) - min(ys) == pytest.approx(25) and max(xs) - min(xs) == pytest.approx(8.5)
    assert LOT.covers(spot) and not spot.intersects(BUILDING) and not spot.intersects(plan.pad)
    centre_ft = math.dist(plan.axis, spot.centroid.coords[0])
    whole = [lf for lf in plan.lifts if lf.what == "whole_load"]
    assert len(whole) == 4
    assert all(lf.radius_ft == pytest.approx(centre_ft) for lf in whole)
    assert whole[1].gross_lb == 11120 + 3100
    # Pieces are picked off the landed load, never nearer than its centre.
    for lf in plan.lifts:
        if lf.what == "piece":
            assert lf.pick_ft >= centre_ft - 1e-6


def test_truck_spots_back_straight_in_from_the_street(rules: sa.Rules) -> None:
    spots = sa.lot_truck_spots(Site(LOT, BUILDING, STREET), rules)
    assert len(spots)
    polys = [Polygon(c) for c in spots.corners]
    assert all(LOT.covers(p) and p.intersection(BUILDING).area < 1e-6 for p in polys)
    # Behind the pod only through a side yard wide enough for the truck:
    # here the 10 ft yards pass 8.5 ft, so some spots are behind it.
    assert any(p.bounds[1] >= 85 for p in polys)
    walled = sa.lot_truck_spots(Site(LOT, box(0, 60, 100, 85), STREET), rules)
    assert len(walled) and all(Polygon(c).bounds[3] <= 60 + 1e-6 for c in walled.corners)


def test_street_set_up_needs_the_pad_to_fit_in_the_road(rules: sa.Rules) -> None:
    def status(width, curb=12.0):
        rep = sa.report(Site(TIGHT, TIGHT_POD, TIGHT_STREET, street(width, curb)), rules)
        return rep, {(a.crane, a.setup): a for a in rep.attempts}

    rep, by = status(27)
    assert by[("28 t", "site")].status == "fail" and by[("45 t", "site")].status == "fail"
    assert any("27 ft wide at most; the 45 t pad needs 28 ft" in w for w in by[("45 t", "street")].why)
    assert not any("wide at most" in w for w in by[("28 t", "street")].why)  # 26 ft fits
    rep, by = status(24)
    assert all(
        any("24 ft wide at most" in w for w in by[(c, "street")].why) for c in ("28 t", "45 t")
    )
    rep, by = status(None)
    assert by[("45 t", "street")].status == "unmeasured"
    rep = sa.report(Site(TIGHT, TIGHT_POD, TIGHT_STREET), rules)
    assert {a.status for a in rep.attempts if a.setup == "street"} == {"unmeasured"}
    assert rep.crane == "unmeasured"


def test_a_street_pad_stands_at_the_near_curb_and_says_power_lines(rules: sa.Rules) -> None:
    rep = sa.report(Site(TIGHT, TIGHT_POD, TIGHT_STREET, street(40, 12.0)), rules)
    plan = next(a.plan for a in rep.attempts if a.setup == "street" and a.plan is not None)
    assert plan.setup == "street"
    assert plan.pad.distance(TIGHT) == pytest.approx(12.0)
    assert sa.POWER_NOTE in plan.notes
    assert sa.POWER_NOTE in rep.row()["notes"]


def test_an_on_site_plan_off_a_lot_truck_has_no_power_line_note(deep: sa.Report) -> None:
    assert deep.plan.setup == "site" and deep.plan.truck == "lot"
    assert sa.POWER_NOTE not in deep.plan.notes
    assert "overhead power lines" in deep.not_checked


def test_report_row(deep: sa.Report) -> None:
    row = deep.row()
    assert row["crane"] == "45 t" and row["setup"] == "site" and row["mode"] == "whole_load"
    assert row["28t_site"] == "fail" and row["45t_site"] == "pass"
    assert row["chart_row_ft"] >= row["binding_radius_ft"]
    assert row["pct_of_chart"] == pytest.approx(100 * row["binding_gross_lb"] / row["chart_capacity_lb"], abs=0.1)


def test_no_pad_no_truck_spot_reasons(rules: sa.Rules) -> None:
    rep = sa.report(Site(TIGHT, TIGHT_POD, TIGHT_STREET, street(24)), rules)
    assert rep.crane == "neither"
    assert any("no 26 x 42 ft pad fits" in w for w in rep.why)


def test_site_from_drawing() -> None:
    ring = [list(p) for p in BUILDING.exterior.coords]
    site = sa.site_from_drawing(LOT, {"fits": True, "building": ring}, STREET, street(30))
    assert site is not None and site.building.equals(BUILDING) and site.street_reading is not None
    assert sa.site_from_drawing(LOT, {"fits": False, "building": ring}, STREET) is None


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
