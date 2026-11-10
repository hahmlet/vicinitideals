"""A lot whose street direction nobody measured (FOLLOWUPS 164).

Where the code makes a fit right or wrong by the way the building stands to
the street -- its long side parallel (``orientation_constraint:
axis_required``, or townhouse lots), its front doors facing one
(``entrance_faces_street`` ``required`` / ``required_named``), or a turned
fit waiting on an entrance standard nobody settled -- a lot with no street
bearing was searched at every angle, and nothing could check the angle the
fit took. Found by tigard-entrances (d35ef11a, "Left out"): the turned pod
went through unflagged.

Such a fit is held out of GREEN on MEASURE-STREET-DIRECTION
(``FACT_UNOBSERVED``), never failed on this ground alone. In a door zone the
bridge no longer binds the doors to no street at all (which no fit meets,
a RED on ground nobody measured, then a side-door YELLOW under the wrong
flag): it searches the lot free, as the side-door search would, and the
screen holds it.
"""

from __future__ import annotations

import pytest

from flats.designs.model import Orientation
from flats.score import relief, slack
from flats.score.flags import Colour, registry
from flats.score.paper import doors_to_the_side, turns_on_the_street
from flats.score.screen import (
    FACT_UNOBSERVED,
    STREET_DIRECTION,
    _MEASURED_FLAG,
    GeometryTier,
    screen,
)
from flats.tests.test_entrance_orientation import OLD, POD, _fit
from flats.tests.test_round2_rulings import facts, rules

pytestmark = pytest.mark.unit

FLAG = "MEASURE-STREET-DIRECTION"
POLICY = slack.SlackPolicy(tolerance={"fit_ft": 0.5})


def _run(fit, street: tuple[float, ...], design=POD, **values):
    return screen(
        rules(**values),
        facts(lot_sqft=12000, street_bearings=street),
        design,
        fit,
        policy=POLICY,
        relief=relief.load_policy(),
    )


def _codes(result) -> set[str]:
    return {f.code for f in result.flags}


AXIS = {"orientation_constraint": "axis_required", "entrance_faces_street": "not_required"}


# --- the flag and the rule ------------------------------------------------------------


def test_the_flag_is_registered_above_the_yellow_line() -> None:
    assert _MEASURED_FLAG[STREET_DIRECTION] == FLAG
    kind = registry()[FLAG]
    assert kind.severity >= 3
    assert FACT_UNOBSERVED in kind.raised_from


def test_which_zones_turn_on_the_street() -> None:
    assert turns_on_the_street(rules(**AXIS), POD)
    assert turns_on_the_street(rules(**AXIS), OLD)
    assert turns_on_the_street(rules(entrance_faces_street="required"), POD)
    assert turns_on_the_street(rules(entrance_faces_street="required_named"), POD)
    assert turns_on_the_street(rules(entrance_faces_street="unclear"), POD)
    # The side-door search frees the doors, not the standard.
    with doors_to_the_side():
        assert turns_on_the_street(rules(entrance_faces_street="required"), POD)
    for value in ("alternative", "not_required"):
        assert not turns_on_the_street(rules(entrance_faces_street=value), POD)
    # A design with no door face, in a zone with no axis rule.
    assert not turns_on_the_street(rules(entrance_faces_street="required"), OLD)


# --- the screen ----------------------------------------------------------------------


@pytest.mark.parametrize("orientation", [Orientation.width_facing, Orientation.depth_facing])
def test_parallel_required_with_no_bearing_is_held_yellow_and_flagged(orientation) -> None:
    fit = _fit(37.0, orientation)
    measured = _run(fit, (37.0,), **AXIS)
    assert measured.colour is Colour.green
    got = _run(fit, (), **AXIS)
    assert got.colour is Colour.yellow
    assert FLAG in _codes(got)
    assert FACT_UNOBSERVED in got.reasons
    # Held, never failed on this ground.
    assert not any(c.check == STREET_DIRECTION for c in got.checks)


def test_parallel_required_with_a_bearing_is_unchanged() -> None:
    fit = _fit(0.0, Orientation.width_facing)
    got = _run(fit, (0.0,), **AXIS)
    assert got.colour is Colour.green
    assert FLAG not in _codes(got)


def test_door_required_with_no_bearing_is_held_yellow_and_flagged() -> None:
    fit = _fit(37.0, Orientation.width_facing)
    assert _run(fit, (37.0,), entrance_faces_street="required").colour is Colour.green
    got = _run(fit, (), entrance_faces_street="required")
    assert got.colour is Colour.yellow
    assert FLAG in _codes(got)


def test_a_landlocked_lot_is_held_whatever_angle_the_fit_names() -> None:
    fit = _fit(None, Orientation.width_facing)
    lot = facts(lot_sqft=12000, geometry=GeometryTier.landlocked)
    got = screen(rules(**AXIS), lot, POD, fit, policy=POLICY, relief=relief.load_policy())
    assert got.colour is not Colour.green
    assert FLAG in _codes(got)


def test_a_zone_with_no_orientation_rule_is_unchanged() -> None:
    fit = _fit(37.0, Orientation.depth_facing)
    for design in (POD, OLD):
        got = _run(fit, (), design=design, entrance_faces_street="not_required")
        assert FLAG not in _codes(got)
        assert got.colour is _run(fit, (0.0,), design=design, entrance_faces_street="not_required").colour
    got = _run(fit, (), entrance_faces_street="alternative")
    assert got.colour is Colour.green
    assert FLAG not in _codes(got)


def test_a_fit_that_misses_is_not_flagged() -> None:
    got = _run(_fit(37.0, Orientation.width_facing, fits=False), (), **AXIS)
    assert FLAG not in _codes(got)


# --- the bridge: a door zone, no street line found --------------------------------------


@pytest.fixture(scope="module")
def corpus():
    from flats.encode.load import load_trusted

    return load_trusted(strict=False).rules


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


def _landlocked(corpus, policies, wide: float, deep: float):
    import json

    import shapely
    from shapely.geometry import box

    from flats.ingest.quadfit import lot_from_row, screen_lot
    from flats.tests.test_fire import X0, Y0, bridge_row

    edges = [
        [X0, Y0, X0 + wide, Y0, "S"],
        [X0 + wide, Y0, X0 + wide, Y0 + deep, "S"],
        [X0 + wide, Y0 + deep, X0, Y0 + deep, "S"],
        [X0, Y0 + deep, X0, Y0, "S"],
    ]
    row = bridge_row(
        TLID="1S2E20AA  -99164",
        zone="R5",
        tier="D",
        front_bearings_json="[]",
        area_sqft=wide * deep,
        lot_depth_ft=deep,
        frontage_ft=0.0,
        lot_width_ft=wide,
        edges_json=json.dumps(edges),
        wkb=shapely.to_wkb(box(X0 + 5, Y0 + 5, X0 + wide - 5, Y0 + deep - 5)),
        lot_wkb=shapely.to_wkb(box(X0, Y0, X0 + wide, Y0 + deep)),
    )
    lot = lot_from_row(row, corpus.layers)
    assert not lot.front_bearings
    (s,) = screen_lot(lot, [POD], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    return s


@pytest.mark.parametrize(("wide", "deep"), [(95.0, 200.0), (140.0, 140.0)])
def test_a_door_zone_lot_with_no_street_is_searched_free_and_held(corpus, policies, wide, deep) -> None:
    s = _landlocked(corpus, policies, wide, deep)
    from flats.score.paper import door_rule

    assert door_rule(s.rules, POD) is not None  # Portland R5 binds the doors
    assert s.fit.fits
    assert s.signed.colour is Colour.yellow
    assert s.screening.colour is not Colour.green
    codes = {f.code for f in s.signed.flags}
    assert FLAG in codes
    # Not the side-door hold: nobody showed the street-facing fit missed.
    assert "ENTRANCE-SIDE-DOOR" not in codes
