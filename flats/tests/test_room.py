"""How much bigger the pod could be, each way (FOLLOWUPS 37(ii)).

Steph, 2026-10-05: *"If we're getting room left, we need all dimensions. How
would this handle oddly shaped lots?"* The fit's room ran front to back
only. :func:`flats.score.room.room_for` adds the room across and the room
both ways at once, each searched on the lot's own shape for the plan the
screen took; on an odd lot "both" comes out under the smaller of the two.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
import shapely

from flats.designs.model import Orientation
from flats.fit.raster import GRID_FT, Grid, _integral
from flats.fit.rectangle import Fitter
from flats.score.paper import court_across, side_court
from flats.score.room import ROOM_CAP_FT, Room, room_for
from flats.score.screen import _beside_beyond, _beside_over, fit_for
from flats.tests.test_screen import (
    ACROSS_FT,
    ALLEY_FED,
    COURT_FT,
    DESIGN,
    SIDE_ALLEY_LOT,
    rules,
)
from flats.tests.test_side_court import OPEN, Rules, pod

pytestmark = pytest.mark.unit

#: The pod broadside with its lane, and the run it needs with its court
#: behind it (`rules()` states no rear yard, so the whole court is charged).
RUN_FT = 36.0 + COURT_FT


# --- the widest window ------------------------------------------------------


def _grid(cells: np.ndarray) -> Grid:
    return Grid(integral=_integral(cells), minx=0.0, miny=0.0, res=1.0, angle_deg=0.0, origin=(0.0, 0.0))


def test_the_widest_window_is_the_longest_run_of_deep_enough_columns() -> None:
    rng = np.random.default_rng(37)
    for _ in range(40):
        cells = rng.random((rng.integers(1, 12), rng.integers(1, 12))) < 0.75
        grid = _grid(cells)
        for d in range(0, grid.rows + 2):
            brute = max((w for w in range(1, grid.cols + 1) if grid.has_window(d, w)), default=0)
            assert grid.max_width_cells(d) == brute, (cells.astype(int), d)


def test_the_widest_window_holds_its_court_s_run_on_the_ground() -> None:
    # A 60 x 40 envelope with the rear yard behind its left half only. Forty
    # deep, the whole 60 stands; with 8 ft of court to land past the far
    # end, only the 30 ft with yard behind it does; 12 ft overruns the yard.
    env = shapely.box(0, 0, 60, 40)
    ground = env.union(shapely.box(0, 40, 30, 50))
    fitter = Fitter(env, (0.0,), ground=ground)
    assert fitter.widest(40.0) == 60.0
    assert fitter.widest(40.0, over_ft=8.0) == 30.0
    assert fitter.widest(40.0, over_ft=12.0) == 0.0
    # The yes/no agrees at every width, a cell either side.
    for over in (0.0, 8.0, 12.0):
        got = fitter.widest(40.0, over_ft=over)
        if got:
            assert fitter.holds(got, 40.0, over_ft=over)
        assert not fitter.holds(got + GRID_FT, 40.0, over_ft=over)


def test_the_widest_window_reads_every_angle_and_only_those_asked() -> None:
    # 50 x 100: thirty deep, 50 across at 0 deg, 100 turned a quarter.
    fitter = Fitter(shapely.box(0, 0, 50, 100), (0.0, 90.0))
    assert fitter.widest(30.0) == 100.0
    assert fitter.widest(30.0, angles=(0.0,)) == 50.0


# --- the room, each way -----------------------------------------------------


def test_on_a_rectangle_both_ways_is_the_smaller_of_the_two() -> None:
    fitter = Fitter(shapely.box(0, 0, ACROSS_FT + 5, RUN_FT + 7), (0.0,))
    fit = fit_for(fitter, DESIGN, rules())
    assert fit.orientation is Orientation.width_facing and not fit.beside and not fit.column
    got = room_for(fitter, DESIGN, rules(), fit)
    # Broadside, the pod's width runs across and its depth along.
    assert got == Room(width_ft=5.0, depth_ft=7.0, both_ft=5.0)


def test_an_odd_lot_has_room_each_way_and_none_both_ways() -> None:
    # An L: ten more feet across up front, ten more feet of run down the
    # narrower leg, and no corner where both are. Either change alone fits;
    # the two together do not -- the tight shape a single number hides.
    env = shapely.box(0, 0, ACROSS_FT + 10, RUN_FT).union(shapely.box(0, 0, ACROSS_FT, RUN_FT + 10))
    fitter = Fitter(env, (0.0,))
    fit = fit_for(fitter, DESIGN, rules())
    got = room_for(fitter, DESIGN, rules(), fit)
    assert got == Room(width_ft=10.0, depth_ft=10.0, both_ft=0.0)
    assert got.both_ft < min(got.width_ft, got.depth_ft)


def test_a_wedge_narrows_toward_the_rear() -> None:
    # A lot narrowing half a foot per foot of depth, the pod made to face
    # the street: at the run it needs the lot is 6 ft wider than the pod
    # and its lane, at that width the run has 12 ft to spare -- and each
    # foot longer costs half a foot across, so both ways it has only 4.
    facing = rules(orientation_constraint="axis_required")
    front, k, depth = ACROSS_FT + 6 + 0.5 * RUN_FT, 0.5, RUN_FT + 40
    env = shapely.Polygon([(0, 0), (front, 0), (front - k * depth, depth), (0, depth)])
    fitter = Fitter(env, (0.0,))
    fit = fit_for(fitter, DESIGN, facing)
    assert fit.orientation is Orientation.width_facing
    got = room_for(fitter, DESIGN, facing, fit)
    assert got is not None
    # A cell of the slanted edge is lost to the raster, never gained.
    assert got.width_ft == pytest.approx(6.0, abs=GRID_FT)
    assert got.depth_ft == pytest.approx(12.0, abs=GRID_FT)
    assert got.both_ft == pytest.approx(4.0, abs=GRID_FT)
    assert got.both_ft < min(got.width_ft, got.depth_ft)
    # Every number is one the lot was asked at and held, and a cell more
    # is not.
    assert fitter.holds(ACROSS_FT + got.width_ft, RUN_FT)
    assert fitter.holds(ACROSS_FT, RUN_FT + got.depth_ft)
    assert fitter.holds(ACROSS_FT + got.both_ft, RUN_FT + got.both_ft)
    assert not fitter.holds(ACROSS_FT + got.width_ft + GRID_FT, RUN_FT)
    assert not fitter.holds(ACROSS_FT + got.both_ft + GRID_FT, RUN_FT + got.both_ft + GRID_FT)


def test_a_court_wider_than_the_building_lets_the_building_widen_for_free() -> None:
    # Eight stalls at 9 ft are a 72 ft court: wider than the pod and its lane
    # (68), so the pod's first 4 ft wider cost nothing across.
    many = rules(parking_min_per_unit=2.0)
    court = court_across(DESIGN, many)
    assert court.width_ft > ACROSS_FT
    fitter = Fitter(shapely.box(0, 0, court.width_ft + 2, RUN_FT + 3), (0.0,))
    fit = fit_for(fitter, DESIGN, many)
    got = room_for(fitter, DESIGN, many, fit)
    assert got is not None
    assert got.width_ft == pytest.approx(court.width_ft + 2 - ACROSS_FT)


def test_end_on_the_pod_s_width_runs_along() -> None:
    # Too narrow broadside (68 across), wide enough end-on (36 + 12 = 48):
    # the run the lot has to spare is the pod's WIDTH, the room across its
    # depth.
    across = 36.0 + DESIGN.parking.lane_width_ft
    fitter = Fitter(shapely.box(0, 0, across + 3, 56.0 + COURT_FT + 6), (0.0,))
    fit = fit_for(fitter, DESIGN, rules())
    assert fit.orientation is Orientation.depth_facing
    got = room_for(fitter, DESIGN, rules(), fit)
    assert got == Room(width_ft=6.0, depth_ft=3.0, both_ft=3.0)


def test_the_column_along_a_side_alley_is_charged_its_own_way() -> None:
    # test_screen's 56 x 78 lot: the column fits with 1 ft to spare along,
    # and the building already fills the envelope's width.
    fitter = Fitter(shapely.box(0, 0, 56, 78), (0.0,), res=1.0)
    side = SIDE_ALLEY_LOT.alley
    fit = fit_for(fitter, DESIGN, rules(**ALLEY_FED), alley=side)
    assert fit.column
    got = room_for(fitter, DESIGN, rules(**ALLEY_FED), fit, alley=side)
    assert got == Room(width_ft=0.0, depth_ft=1.0, both_ft=0.0)


def test_the_court_beside_is_searched_along_the_street_only() -> None:
    # test_side_court's 85 x 66 envelope: the pod end-on (36 across) and the
    # 47 ft band beside it are 83 of the 85 across; the 56 ft run has 10 to
    # spare. Across is the pod's depth, along its width.
    r = Rules(OPEN)
    court = side_court(pod(), r)
    fitter = Fitter(shapely.box(0, 0, 85, 66), angles=(0.0, 90.0))
    fit = fitter.fit_beside(
        56, 36, band_ft=court.band_ft, beyond=lambda d: _beside_beyond(court, d, r),
        angles=(0.0,), over=lambda d: _beside_over(court, d, r),
    )
    assert fit.beside and fit.orientation is Orientation.depth_facing
    got = room_for(fitter, pod(), r, fit, street_deg=(0.0,))
    assert got == Room(width_ft=10.0, depth_ft=2.0, both_ft=2.0)
    # No street direction, no court beside to measure.
    assert room_for(fitter, pod(), r, fit, street_deg=()) is None


def test_a_fit_that_did_not_pass_has_no_room() -> None:
    fitter = Fitter(shapely.box(0, 0, ACROSS_FT + 5, RUN_FT - 1), (0.0,))
    fit = fit_for(fitter, DESIGN, rules())
    assert fit.slack_ft - COURT_FT < 0
    assert room_for(fitter, DESIGN, rules(), fit) is None
    # Nor does a fit searched some other way than this plan asks.
    big = Fitter(shapely.box(0, 0, 200, 200), (0.0,))
    wide = fit_for(big, DESIGN, rules())
    assert room_for(big, DESIGN, rules(), wide) is not None
    assert room_for(big, DESIGN, rules(), replace(wide, across_ft=1.0)) is None


def test_the_room_stops_at_the_cap() -> None:
    fitter = Fitter(shapely.box(0, 0, 400, 400), (0.0,))
    fit = fit_for(fitter, DESIGN, rules())
    assert room_for(fitter, DESIGN, rules(), fit) == Room(ROOM_CAP_FT, ROOM_CAP_FT, ROOM_CAP_FT)



# --- through the screen and onto the bridge's row ---------------------------


@pytest.fixture(scope="module")
def corpus():
    from flats.encode.load import load_trusted

    return load_trusted(strict=False).rules


def test_a_real_lot_carries_its_room_onto_the_row(corpus) -> None:
    # test_side_court's 13640 NE Fremont Ct: the pod end-on with its court
    # beside it, along the street.
    from flats.ingest.quadfit import lot_from_row, row_for, screen_lot
    from flats.score import relief, slack
    from flats.tests.test_side_court import real_row

    lot = lot_from_row(real_row(), corpus.layers)
    (s,) = screen_lot(
        lot, [pod()], rules=corpus, policy=slack.load_policy(), relief=relief.load_policy(), step_deg=1.0
    )
    assert s.fit.beside and s.signed.colour.value == "green"
    assert s.room is not None
    # Along is the fit check's own room; end-on, that is the pod's width.
    check = next(c for c in s.signed.checks if c.check == "fit_ft")
    assert s.room.width_ft == pytest.approx(min(check.slack, ROOM_CAP_FT), abs=GRID_FT)
    assert 0 <= s.room.both_ft <= min(s.room.width_ft, s.room.depth_ft)
    r = row_for(s)
    assert (r["room_width_ft"], r["room_depth_ft"], r["room_both_ft"]) == (
        round(s.room.width_ft, 3),
        round(s.room.depth_ft, 3),
        round(s.room.both_ft, 3),
    )


def test_a_red_lot_is_not_measured(corpus) -> None:
    # test_quadfit_bridge's 40 ft envelope holds no row of six: red, and a
    # bigger pod is no question there.
    from flats.ingest.quadfit import lot_from_row, row_for, screen_lot
    from flats.score import relief, slack
    from flats.tests.test_quadfit_bridge import row

    (s,) = screen_lot(
        lot_from_row(row()), [pod()], rules=corpus, policy=slack.load_policy(),
        relief=relief.load_policy(), step_deg=30.0,
    )
    assert s.signed.colour.value == "red" and s.room is None
    r = row_for(s)
    assert r["room_width_ft"] is r["room_depth_ft"] is r["room_both_ft"] is None
