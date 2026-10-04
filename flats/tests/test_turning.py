"""The car that drives the court (:mod:`flats.fit.turning`).

The calibration is pinned here: the AASHTO P car backs out of a 9 x 18 ft
stall onto a 24 ft aisle and drives away, and cannot onto 22 ft. And the
findings behind the dead end (:mod:`flats.score.turns`): today's court cannot
be left by backing out once, and a few feet of aisle past the row's far end
is what lets a car back into a stall in the middle of it. Only questions the
search answers in seconds are asked here; the slow "no"s are the ledger's.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
import shapely

from flats.fit.turning import (
    BACK_IN,
    BACK_OUT,
    DRIVE_IN,
    DRIVE_OUT,
    TURN_FT,
    Court,
    Pose,
    arrives,
    axle_radius_ft,
    bodies,
    drive,
    facing,
    finds,
    leaves,
    parked_pose,
)

pytestmark = pytest.mark.unit


def _open_aisle_exit(aisle_ft: float, turn_ft: float = TURN_FT) -> bool:
    """A stall off a long straight aisle, its neighbours taken."""
    aisle = shapely.box(-60.0, 0.0, 60.0, aisle_ft)
    stall = shapely.box(-4.5, aisle_ft, 4.5, aisle_ft + 18.0)
    return finds(
        shapely.union_all([aisle, stall]),
        parked_pose(stall),
        lambda p: p.x > 40.0 and facing(p.heading, 0.0, 10.0),
        BACK_OUT,
        turn_ft=turn_ft,
        toward=(45.0, aisle_ft / 2),
    )


def test_the_car_backs_out_onto_the_standard_aisle_and_not_a_narrower_one() -> None:
    assert _open_aisle_exit(24.0)
    assert not _open_aisle_exit(22.0)


def test_the_published_car_is_the_least_nimble_the_standard_module_serves() -> None:
    """AASHTO's P car turns its outer front wheel on 24 ft; half a foot wider
    and it cannot back out of a 9 x 18 stall onto the 24 ft aisle at all.
    So the design car of the highway book is exactly the car the stall
    tables were drawn for, and nothing more nimble is assumed."""
    assert TURN_FT == 24.0
    assert not _open_aisle_exit(24.0, turn_ft=24.5)


def test_the_parked_car_fits_its_stall() -> None:
    stall = Court().stall(0)
    p = parked_pose(stall)
    car = bodies(np.array([p.x]), np.array([p.y]), np.array([p.heading]))
    assert stall.contains(car[0])


def test_the_axle_radius_follows_the_outer_wheel() -> None:
    r = axle_radius_ft(22.0)
    assert math.hypot(r + 6.583 / 2, 11.0) == pytest.approx(22.0)


def test_today_s_court_cannot_be_left_by_backing_out_once() -> None:
    assert not leaves(Court(), 3, BACK_OUT)


def test_today_s_court_is_entered_nose_first_at_the_lane_and_left_nose_first_at_the_dead_end() -> None:
    court = Court()
    assert arrives(court, 0, DRIVE_IN)
    assert leaves(court, 3, DRIVE_OUT, nose_out=True)


def test_a_dead_end_lets_a_car_back_into_the_middle_of_the_row() -> None:
    court = Court(extra_ft=8.0)
    assert arrives(court, 1, BACK_IN, nose_out=True)
    assert leaves(court, 1, DRIVE_OUT, nose_out=True)


def test_nothing_is_found_off_the_ground() -> None:
    ground = shapely.box(0.0, 0.0, 10.0, 10.0)
    assert not drive(ground, Pose(5.0, 5.0, 0.0), lambda p: True, BACK_OUT)
