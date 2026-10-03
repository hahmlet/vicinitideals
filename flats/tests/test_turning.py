"""The car that drives the court (:mod:`flats.fit.turning`).

The calibration is pinned here: the car backs out of a 9 x 18 ft stall onto
a 24 ft aisle and drives away, and cannot onto 22 ft. And the finding that
keeps the module unwired: today's court cannot be left by backing out once,
and can by a three-point turn.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
import shapely

from flats.fit.turning import (
    BACK_OUT,
    THREE_POINT,
    Court,
    Pose,
    axle_radius_ft,
    bodies,
    drive,
    facing,
    leaves,
    parked_pose,
)

pytestmark = pytest.mark.unit


def _open_aisle_exit(aisle_ft: float) -> bool:
    """A stall off a long straight aisle, its neighbours taken."""
    aisle = shapely.box(-60.0, 0.0, 60.0, aisle_ft)
    stall = shapely.box(-4.5, aisle_ft, 4.5, aisle_ft + 18.0)
    return drive(
        shapely.union_all([aisle, stall]),
        parked_pose(stall),
        lambda p: p.x > 40.0 and facing(p.heading, 0.0, 10.0),
        BACK_OUT,
        toward=(45.0, aisle_ft / 2),
    )


def test_the_car_backs_out_onto_the_standard_aisle_and_not_a_narrower_one() -> None:
    assert _open_aisle_exit(24.0)
    assert not _open_aisle_exit(22.0)


def test_the_highway_car_could_not_use_the_standard_module() -> None:
    """Why the turn is calibrated rather than AASHTO P's 24 ft: that car
    cannot back out of a 9 x 18 stall onto a 24 ft aisle at all."""
    aisle = shapely.box(-60.0, 0.0, 60.0, 24.0)
    stall = shapely.box(-4.5, 24.0, 4.5, 42.0)
    assert not drive(
        shapely.union_all([aisle, stall]),
        parked_pose(stall),
        lambda p: p.x > 40.0 and facing(p.heading, 0.0, 10.0),
        BACK_OUT,
        turn_ft=24.0,
        toward=(45.0, 12.0),
    )


def test_the_parked_car_fits_its_stall() -> None:
    stall = Court().stall(0)
    p = parked_pose(stall)
    car = bodies(np.array([p.x]), np.array([p.y]), np.array([p.heading]))
    assert stall.contains(car[0])


def test_the_axle_radius_follows_the_outer_wheel() -> None:
    r = axle_radius_ft(22.0)
    assert math.hypot(r + 6.583 / 2, 11.0) == pytest.approx(22.0)


def test_today_s_court_cannot_be_left_by_backing_out_once() -> None:
    court = Court()
    assert not leaves(court, 0, BACK_OUT)
    assert not leaves(court, 3, BACK_OUT)


def test_today_s_court_can_be_left_by_a_three_point_turn() -> None:
    assert leaves(Court(), 3, THREE_POINT)


def test_nothing_is_found_off_the_ground() -> None:
    ground = shapely.box(0.0, 0.0, 10.0, 10.0)
    assert not drive(ground, Pose(5.0, 5.0, 0.0), lambda p: True, BACK_OUT)
