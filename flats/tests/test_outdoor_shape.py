"""The open space a code asks for has to come in the shape it asks for.

FOLLOWUPS 7(b), 2026-09-29. Two codes state a shape beside the amount:

* Portland 33.110.240 and Table 110-4 -- 250 sq ft (200 in R2.5) in one
  contiguous piece that a 12 by 12 square (10 by 10) fits inside, off vehicle
  area and outside the front building setback.
* Milwaukie Table 19.505.3.D.1 -- 96 sq ft of private open space per
  ground-floor home, 5 ft its least dimension, directly accessible from it.

The amount check (7(a)) could clear a lot on thousands of square feet of
leftover that holds no 12 ft square once a turned pod, its lane and its court
stand on it. These tests pin the asymmetry the shape check keeps: a shape
found inside the fit's window is proven and passes; a shape not found there
may still exist outside it, so the lot is held out of GREEN on the unmeasured
fact -- never failed on it.
"""

from __future__ import annotations

from datetime import date

import pytest

from flats.designs.model import Orientation, load_catalog
from flats.fit.rectangle import Fit
from flats.rules.fields import FIELDS, OPTIONAL_FIELDS
from flats.rules.model import Provenance, Status
from flats.rules.resolver import Resolved, Verdict as RuleVerdict, ZoneResolution
from flats.score.screen import (
    CHECK_FIELD,
    FACT_UNOBSERVED,
    LotFacts,
    Triage,
    screen,
)
from flats.score.slack import SlackPolicy, Verdict

pytestmark = pytest.mark.unit

PROV = Provenance(
    cite="PCC 33.110.240",
    url="https://www.portland.gov/code/33/100s/110",
    retrieved=date(2026, 9, 29),
)
POLICY = SlackPolicy(tolerance={"fit_ft": 0.5})

POD56 = load_catalog().latest("pod56x36")
POD80 = load_catalog().latest("pod80x25")

CLEAR = {
    "quadplex_allowed": True,
    "min_lot_sqft": 3000,
    "setback_front_ft": 10,
    "min_frontage_ft": 25,
    "min_lot_width_ft": 25,
    "max_coverage_pct": 60,
    "max_far": 2.0,
    "max_height_ft": 35,
    "max_units": 4,
    "parking_min_per_unit": 1.0,
}
#: Portland R5's outdoor area, amount and shape.
PORTLAND = {"open_space_min_sqft": 250, "open_space_min_dimension_ft": 12}
#: Milwaukie's patio: 96 a home, multiplied out by the loader for four.
MILWAUKIE = {"open_space_min_sqft": 4 * 96, "private_open_space_min_dimension_ft": 5}

LOT = LotFacts(lot_sqft=8000, frontage_ft=80, lot_width_ft=80)


def rules(where: str = "or/multnomah/portland", **overrides) -> ZoneResolution:
    values = {**CLEAR, **overrides}
    return ZoneResolution(
        jurisdiction=where,
        zone="R5",
        verdict=RuleVerdict.trusted,
        values={
            name: Resolved(
                name=name,
                value=value,
                status=Status.verified,
                prov=PROV,
                layer=where,
                origin="zone",
            )
            for name, value in values.items()
            if value is not None
        },
    )


def fit(design, orientation: Orientation, *, spare: float = 0.0) -> Fit:
    """The pod with its court behind it, and ``spare`` feet more than that.

    No rear setback is stated, so the whole court is charged past the
    building and ``spare`` is exactly the fit check's slack.
    """
    court = design.parking.court_depth_ft
    width, depth = design.footprint.width_ft, design.footprint.depth_ft
    across_bldg, required = (width, depth) if orientation is Orientation.width_facing else (depth, width)
    row = 4 * design.parking.stall_width_ft
    best = required + court + spare
    return Fit(
        fits=True,
        width_ft=width,
        depth_ft=depth,
        best_depth_ft=best,
        slack_ft=best - required,
        orientation=orientation,
        across_ft=max(across_bldg + design.parking.lane_width_ft, row),
    )


def run(rule_set, design, orientation, *, spare: float = 0.0):
    return screen(rule_set, LOT, design, fit(design, orientation, spare=spare), policy=POLICY)


def check(result, name):
    return next(c for c in result.checks if c.check == name)


# --- the fields ------------------------------------------------------------


def test_both_shape_fields_are_optional_and_read_by_a_check() -> None:
    # A zone silent on the shape is silent, not unencoded: only two codes
    # state one. New fields are required by default, so this is a decision.
    for name in ("open_space_min_dimension_ft", "private_open_space_min_dimension_ft"):
        assert name in FIELDS
        assert name in OPTIONAL_FIELDS
        assert name in CHECK_FIELD.values()


# --- Portland: one square, anywhere legal ----------------------------------


def test_a_broadside_pod_leaves_its_square_beside_the_court() -> None:
    # 56 ft of building plus the 12 ft lane is a 68 ft window; the 36 ft row
    # leaves 32 ft beside the court, as deep as the court runs.
    result = run(rules(**PORTLAND), POD56, Orientation.width_facing)

    got = check(result, "open_space_shape")
    assert got.verdict is Verdict.passes
    assert got.observed == pytest.approx(32.0)
    assert result.triage is Triage.green


def test_a_turned_pod_whose_court_fills_the_window_is_not_certified() -> None:
    # The test that would have caught it. The 80 ft pod end-on is 25 ft
    # across; with its lane the window is 37 ft and the row of four takes 36
    # of it. The leftover clears 250 sq ft by thousands, and not one foot of
    # it is proven to hold a 12 ft square. Held out of GREEN -- not failed:
    # the square may stand outside the window, where nobody measured.
    result = run(rules(**PORTLAND), POD80, Orientation.depth_facing)

    assert check(result, "open_space_sqft").verdict is Verdict.passes
    assert "open_space_shape" in result.unchecked
    assert all(c.check != "open_space_shape" for c in result.checks)
    assert FACT_UNOBSERVED in result.reasons
    assert result.triage is Triage.unknown


def test_room_behind_the_court_proves_the_square_for_a_turned_pod() -> None:
    result = run(rules(**PORTLAND), POD80, Orientation.depth_facing, spare=12.0)

    got = check(result, "open_space_shape")
    assert got.verdict is Verdict.passes
    assert got.observed == pytest.approx(12.0)
    assert result.triage is Triage.green


def test_a_square_needs_its_area_too() -> None:
    # 12 ft behind a 37 ft window is 444 sq ft: enough for 250, not for 500.
    zone = rules(open_space_min_sqft=500, open_space_min_dimension_ft=12)

    result = run(zone, POD80, Orientation.depth_facing, spare=12.0)

    assert "open_space_shape" in result.unchecked
    assert result.triage is Triage.unknown


def test_an_unrecorded_orientation_proves_nothing() -> None:
    bare = fit(POD56, Orientation.width_facing)
    bare = Fit(**{**{f: getattr(bare, f) for f in bare.__dataclass_fields__}, "orientation": None})

    result = screen(rules(**PORTLAND), LOT, POD56, bare, policy=POLICY)

    assert "open_space_shape" in result.unchecked
    assert result.triage is Triage.unknown


# --- Milwaukie: a patio off each home --------------------------------------


MILWAUKIE_AT = "or/clackamas/milwaukie"


def test_a_14_ft_home_has_no_96_sq_ft_patio_in_a_5_ft_standoff() -> None:
    # Fourteen feet of rear wall and the 5 ft before the first stall is 70 sq
    # ft. The front yard might hold it; whether it may is a ruling nobody has
    # made, so the lot is held, not failed.
    result = run(rules(MILWAUKIE_AT, **MILWAUKIE), POD56, Orientation.width_facing)

    assert "private_open_space_shape" in result.unchecked
    assert FACT_UNOBSERVED in result.reasons
    assert result.triage is Triage.unknown


def test_the_court_sliding_back_two_feet_makes_the_patio() -> None:
    # 14 by 7 is 98 sq ft, least side 7.
    result = run(rules(MILWAUKIE_AT, **MILWAUKIE), POD56, Orientation.width_facing, spare=2.0)

    got = check(result, "private_open_space_shape")
    assert got.verdict is Verdict.passes
    assert got.observed == pytest.approx(7.0)
    assert result.triage is Triage.green


def test_a_20_ft_home_has_its_patio_in_the_standoff_alone() -> None:
    # 20 by 5 is 100 sq ft, and 5 ft is the least dimension the code allows.
    result = run(rules(MILWAUKIE_AT, **MILWAUKIE), POD80, Orientation.width_facing)

    got = check(result, "private_open_space_shape")
    assert got.observed == pytest.approx(5.0)
    assert result.triage is Triage.green


def test_turned_end_on_the_homes_open_on_a_flank_the_window_does_not_hold() -> None:
    result = run(rules(MILWAUKIE_AT, **MILWAUKIE), POD80, Orientation.depth_facing, spare=20.0)

    assert "private_open_space_shape" in result.unchecked
    assert result.triage is Triage.unknown


# --- silence ---------------------------------------------------------------


def test_a_zone_stating_no_shape_runs_no_shape_check() -> None:
    # The same turned pod that is held above, where only the amount is asked.
    result = run(rules(open_space_min_sqft=250), POD80, Orientation.depth_facing)

    names = {c.check for c in result.checks} | set(result.unchecked)
    assert not {"open_space_shape", "private_open_space_shape"} & names
    assert result.triage is Triage.green


# --- (b1) the square measured on the lot's own ground ----------------------

import dataclasses  # noqa: E402

import shapely  # noqa: E402

from flats.fit.outdoor import largest_square, open_ground  # noqa: E402


def measured(square_ft: float) -> LotFacts:
    return dataclasses.replace(LOT, outdoor_square_ft=square_ft)


def test_a_square_the_window_misses_but_the_lot_holds_passes() -> None:
    # The turned pod that is held above, where the bridge measured a 14 ft
    # square on the lot's side yard: the window was the only thing short.
    result = screen(
        rules(**PORTLAND), measured(14.0), POD80, fit(POD80, Orientation.depth_facing), policy=POLICY
    )

    got = check(result, "open_space_shape")
    assert (got.observed, got.verdict) == (14.0, Verdict.passes)
    assert result.triage is Triage.green


def test_a_square_the_lot_cannot_hold_is_a_real_miss_not_a_question() -> None:
    result = screen(
        rules(**PORTLAND), measured(9.0), POD80, fit(POD80, Orientation.depth_facing), policy=POLICY
    )

    got = check(result, "open_space_shape")
    assert got.verdict is Verdict.fails
    assert "open_space_shape" not in result.unchecked
    assert FACT_UNOBSERVED not in result.reasons
    assert result.triage not in (Triage.green, Triage.unknown)


def test_the_front_setback_the_building_and_the_pavement_are_not_outdoor_area() -> None:
    # A 50 by 100 lot, street along the bottom, 10 ft front yard. A 36 ft
    # building standing 5 ft off the west line leaves 9 ft on the east side;
    # the ground behind the paved court is 5 ft deep. No 12 ft square.
    lot = shapely.box(0, 0, 50, 100)
    building = shapely.box(5, 10, 41, 66)
    court = shapely.box(5, 71, 41, 95)
    ground = open_ground(lot, front_lines=[(0, 0, 50, 0)], front_ft=10, taken=[building, court])

    assert largest_square(ground, [0.0], min_area_sqft=250) == pytest.approx(9.0)
    # Without the front yard struck, the 10 ft strip along the street would
    # hold a 10 ft square -- ground 33.110.240.C.3 forbids.
    loose = open_ground(lot, front_lines=[], front_ft=10, taken=[building, court])
    assert largest_square(loose, [0.0], min_area_sqft=250) == pytest.approx(10.0)


def test_a_wider_lot_holds_the_square_in_its_side_yard() -> None:
    lot = shapely.box(0, 0, 60, 100)
    building = shapely.box(5, 10, 41, 66)
    ground = open_ground(lot, front_lines=[(0, 0, 60, 0)], front_ft=10, taken=[building])

    assert largest_square(ground, [0.0], min_area_sqft=250) >= 19.0


def test_the_square_must_stand_in_a_piece_that_holds_the_whole_area() -> None:
    # Two separate 13 by 13 plots: each holds the square, neither the 250.
    ground = shapely.union_all([shapely.box(0, 0, 13, 13), shapely.box(20, 0, 33, 13)])

    assert largest_square(ground, [0.0], min_area_sqft=250) == 0.0
    assert largest_square(ground, [0.0], min_area_sqft=144) == pytest.approx(13.0)


def test_an_overlay_carve_is_not_counted_as_outdoor_area() -> None:
    lot = shapely.box(0, 0, 30, 30)
    carve = shapely.box(0, 15, 30, 30)
    ground = open_ground(lot, front_lines=[], front_ft=0, carve=carve)

    assert largest_square(ground, [0.0]) == pytest.approx(15.0)
