"""The fit drawn back on the lot (FOLLOWUPS 5): where the building, lane and court stand."""

from __future__ import annotations

import json

import pytest
import shapely

from flats.fit.draw import draw
from flats.fit.rectangle import Fitter

#: A 60 ft x 120 ft envelope with the street along its south edge (y = 0).
ENVELOPE = shapely.box(0, 0, 60, 120)
SOUTH = ((0.0, -10.0, 60.0, -10.0),)
NORTH = ((0.0, 130.0, 60.0, 130.0),)


def _drawn(envelope=ENVELOPE, street=SOUTH, *, width=36.0, depth=40.0, lane=12.0,
           court=30.0, beyond=10.0, court_width=0.0):
    fitter = Fitter(envelope, angles=(0.0,))
    fit = fitter.fit(width, depth, allow_flip=False, placement=False, lane_ft=lane,
                     court_width_ft=court_width)
    return fit, draw(fitter, fit, width_ft=width, depth_ft=depth, lane_ft=lane,
                     court_depth_ft=court, court_beyond_ft=beyond, street=street)


def test_building_stands_at_the_street_end_with_lane_and_court_behind() -> None:
    fit, got = _drawn()
    assert got is not None and got.fits
    b = got.building.bounds
    # Building at the south (street) edge, 36 wide and 40 deep.
    assert b[1] == pytest.approx(0.0, abs=0.51)
    assert b[2] - b[0] == pytest.approx(36.0)
    assert b[3] - b[1] == pytest.approx(40.0)
    # Lane beside it, from the street to the building's back.
    lane = got.lane.bounds
    assert lane[0] == pytest.approx(b[2])
    assert lane[2] - lane[0] == pytest.approx(12.0)
    assert (lane[1], lane[3]) == pytest.approx((b[1], b[3]))
    # Court behind, across the whole searched width.
    court = got.court.bounds
    assert court[1] == pytest.approx(b[3])
    assert court[3] - court[1] == pytest.approx(30.0)
    assert court[2] - court[0] == pytest.approx(fit.across_ft)
    # The room is the building plus what the court needs past the envelope.
    room = got.room.bounds
    assert room[3] - room[1] == pytest.approx(50.0)
    assert got.room.buffer(1e-6).contains(got.building)


def test_street_to_the_north_flips_the_plan() -> None:
    _, got = _drawn(street=NORTH)
    assert got is not None
    assert got.building.bounds[3] == pytest.approx(120.0, abs=0.51)
    assert got.court.bounds[3] == pytest.approx(got.building.bounds[1])


def test_a_lot_too_shallow_shows_the_room_it_has() -> None:
    shallow = shapely.box(0, 0, 60, 45)
    _, got = _drawn(shallow)
    assert got is not None and not got.fits
    room = got.room.bounds
    assert room[3] - room[1] == pytest.approx(45.0, abs=0.51)
    # The court runs past the room: the shortfall is visible.
    assert got.court.bounds[3] > room[3]


def test_a_tight_fit_is_drawn_where_it_stands() -> None:
    """FOLLOWUPS 45 / 49(d): a plan the screen passed inside the fit's
    tolerance (Steph 2026-09-25) is drawn fitting, half a foot short, so a
    hose route and a pad grade can be measured to its building; a hair
    further short is still the shortfall."""
    tight = shapely.box(0, 0, 60, 49.5)
    _, plain = _drawn(tight)
    assert plain is not None and not plain.fits and not plain.tight
    fitter = Fitter(tight, angles=(0.0,))
    fit = fitter.fit(36.0, 40.0, allow_flip=False, placement=False, lane_ft=12.0)
    got = draw(fitter, fit, width_ft=36.0, depth_ft=40.0, lane_ft=12.0, court_depth_ft=30.0,
               court_beyond_ft=10.0, street=SOUTH, short_ft=0.5)
    assert got is not None and got.fits and got.tight
    assert got.room.bounds[3] - got.room.bounds[1] == pytest.approx(49.5)
    b = got.building.bounds
    assert (b[2] - b[0], b[3] - b[1]) == pytest.approx((36.0, 40.0))
    assert got.to_json()["tight"] is True
    short = shapely.box(0, 0, 60, 49.0)
    fitter = Fitter(short, angles=(0.0,))
    fit = fitter.fit(36.0, 40.0, allow_flip=False, placement=False, lane_ft=12.0)
    got = draw(fitter, fit, width_ft=36.0, depth_ft=40.0, lane_ft=12.0, court_depth_ft=30.0,
               court_beyond_ft=10.0, street=SOUTH, short_ft=0.5)
    assert got is not None and not got.fits and not got.tight
    assert "tight" not in got.to_json()


def test_no_room_at_the_width_draws_nothing() -> None:
    narrow = shapely.box(0, 0, 20, 120)
    fit, got = _drawn(narrow)
    assert fit.angle_deg is None
    assert got is None


def test_no_lane_draws_none() -> None:
    _, got = _drawn(lane=0.0)
    assert got is not None and got.lane is None


def test_rotated_lot_draws_inside_the_envelope() -> None:
    from shapely import affinity

    turned = affinity.rotate(ENVELOPE, 30, origin=(0, 0))
    line = affinity.rotate(shapely.LineString([(0, -10), (60, -10)]), 30, origin=(0, 0))
    street = [(*line.coords[0], *line.coords[1])]
    fitter = Fitter(turned, angles=(0.0, 30.0))
    fit = fitter.fit(36.0, 40.0, allow_flip=False, placement=False, lane_ft=12.0)
    got = draw(fitter, fit, width_ft=36.0, depth_ft=40.0, lane_ft=12.0, court_depth_ft=30.0,
               court_beyond_ft=10.0, street=street)
    assert fit.angle_deg == 30.0
    assert got is not None and got.fits
    assert turned.buffer(0.01).contains(got.building)
    assert turned.buffer(0.01).contains(got.lane)
    # Street end: the building touches the rotated south line.
    south = affinity.rotate(shapely.LineString([(0, 0), (60, 0)]), 30, origin=(0, 0))
    assert got.building.distance(south) < 0.6


def test_json_is_rounded_rings_and_carries_the_envelope() -> None:
    _, got = _drawn()
    out = got.to_json(ENVELOPE)
    assert set(out) == {"fits", "room", "building", "lane", "court", "envelope"}
    assert out["building"][0] == out["building"][-1]
    assert all(round(v, 1) == v for xy in out["building"] for v in xy)
    assert len(out["envelope"]) == 1
    assert len(json.dumps(out)) < 1000


def test_the_street_along_the_long_side_puts_the_building_against_it() -> None:
    # A 120 x 60 lot fronting its long north side, searched at the angle
    # that runs the plan east-west: building and court both reach the
    # street, and the drawing puts the building, not the court, at it --
    # the way round that the street end alone could not tell.
    wide = shapely.box(0, 0, 120, 60)
    fitter = Fitter(wide, angles=(90.0,))
    fit = fitter.fit(36.0, 40.0, allow_flip=False, placement=False, lane_ft=12.0)
    got = draw(fitter, fit, width_ft=36.0, depth_ft=40.0, lane_ft=12.0, court_depth_ft=30.0,
               court_beyond_ft=10.0, street=((0.0, 70.0, 120.0, 70.0),))
    assert got is not None and got.fits
    north = shapely.LineString([(0, 60), (120, 60)])
    assert got.building.distance(north) < 0.6
    assert got.building.distance(north) <= got.court.distance(north)


def test_the_court_is_drawn_on_the_ground_the_fit_passed_it_on() -> None:
    # FOLLOWUPS 33. The room is 50 ft deep (40 of building, 10 the court
    # charges the envelope); the court's other 20 ft stand in the rear yard.
    # Where that yard lies behind the room the plan fits and draws there;
    # where the only strips beyond the envelope are side yards, the court
    # has nowhere to run and the plan does not fit -- however deep a room
    # the envelope alone holds.
    envelope = shapely.box(0, 0, 60, 50)
    for ground, fits in ((shapely.box(0, 0, 60, 70), True), (shapely.box(-20, 0, 80, 50), False)):
        fitter = Fitter(envelope, angles=(0.0,), ground=ground)
        fit = fitter.fit(36.0, 40.0, allow_flip=False, placement=False, lane_ft=12.0, over_ft=20.0)
        got = draw(fitter, fit, width_ft=36.0, depth_ft=40.0, lane_ft=12.0,
                   court_depth_ft=30.0, court_beyond_ft=10.0, street=SOUTH)
        assert got is not None and got.fits is fits
        assert (fit.slack_ft - 10.0 >= 0) is fits
        if fits:
            assert ground.buffer(1e-6).contains(got.court)


@pytest.mark.parametrize("side", [False, True])
@pytest.mark.parametrize("angle", [0.0, 179.94, 180.0])
def test_a_corner_building_stands_in_the_corner_at_either_scan_order(angle, side) -> None:
    # rel4 move-read finding 3 (1N1E29DD  -05600, Portland CM2): a 100 x
    # 131.6 ft corner lot fronting north and east. Every window flush with
    # the north street ties at nought, so the scan order picked one -- and
    # the fit angle turning half a turn (0.0 -> 179.94) left the building
    # 8 ft off the east street, past the zone's maximum front setback.
    # Equally near a street, the window nearest both streets wins -- the
    # east line a second front, or (``side``, Portland's shortest-line
    # front, 33.910) a side street the building is not set back from.
    lot = shapely.box(0, 0, 100, 131.6)
    north = (0.0, 141.6, 100.0, 141.6)
    east = (110.0, 0.0, 110.0, 131.6)
    fitter = Fitter(lot, angles=(angle,))
    fit = fitter.fit(80.0, 30.0, allow_flip=False, placement=False, lane_ft=12.0)
    streets = dict(street=(north,), side_streets=(east,)) if side else dict(street=(north, east))
    got = draw(fitter, fit, width_ft=80.0, depth_ft=30.0, lane_ft=12.0, court_depth_ft=43.0,
               court_beyond_ft=0.0, **streets)
    assert got is not None and got.fits
    b = got.building.bounds
    assert b[3] == pytest.approx(131.6, abs=0.6)
    assert b[2] == pytest.approx(100.0, abs=0.6)


def test_a_through_lot_keeps_its_one_street_direction() -> None:
    # Two parallel fronts are one street direction: nothing to spread over,
    # the building still stands at the nearer of them.
    lot = shapely.box(0, 0, 60, 120)
    fitter = Fitter(lot, angles=(0.0,))
    fit = fitter.fit(36.0, 40.0, allow_flip=False, placement=False, lane_ft=12.0)
    got = draw(fitter, fit, width_ft=36.0, depth_ft=40.0, lane_ft=12.0, court_depth_ft=30.0,
               court_beyond_ft=10.0, street=SOUTH + NORTH)
    assert got is not None and got.fits
    b = got.building.bounds
    assert b[1] == pytest.approx(0.0, abs=0.6) or b[3] == pytest.approx(120.0, abs=0.6)


@pytest.mark.parametrize("alley_x", [-5.0, 65.0])
def test_a_side_alley_column_stands_along_the_alley(alley_x) -> None:
    """FOLLOWUPS 5: a column of stalls along a side alley is drawn as a
    strip on the alley's side of the room, as wide as one stall plus the
    back-out shortfall -- not as a row across the room behind the building."""
    fitter = Fitter(ENVELOPE, angles=(0.0,))
    fit = fitter.fit(36.0, 40.0, allow_flip=False, placement=False, lane_ft=12.0)
    alley = ((alley_x, 0.0, alley_x, 120.0),)
    got = draw(fitter, fit, width_ft=36.0, depth_ft=40.0, lane_ft=12.0, court_depth_ft=40.0,
               court_beyond_ft=10.0, street=SOUTH, column_across_ft=18.0, alley_lines=alley)
    assert got is not None and got.fits
    room, court = got.room.bounds, got.court.bounds
    assert court[2] - court[0] == pytest.approx(18.0)
    assert court[1] == pytest.approx(got.building.bounds[3])
    if alley_x < 0:
        assert court[0] == pytest.approx(room[0])
    else:
        assert court[2] == pytest.approx(room[2])
    # Without the alley's side the court keeps the room's whole width.
    plain = draw(fitter, fit, width_ft=36.0, depth_ft=40.0, lane_ft=12.0, court_depth_ft=40.0,
                 court_beyond_ft=10.0, street=SOUTH, column_across_ft=18.0)
    assert plain.court.bounds[2] - plain.court.bounds[0] == pytest.approx(fit.across_ft)
