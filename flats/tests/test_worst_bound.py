"""A flag the lot clears at its worst reading drops to severity 0 (FOLLOWUPS 37 item 3).

Steph's flag plan, 2026-10-02: a flag a lot clears even at its worst reading
stays a flag, at severity 0, and does not hold the lot out of GREEN. The
bridge (:func:`flats.ingest.quadfit._bounded`) screens a design the fact
flags alone hold at yellow once more under every yes and no for those facts,
the whole way, and lowers them only where no answer turns it red.

Three things it must never do: lower a fact whose bad answer refuses the
building, lower a fact on a footnote that states no number (there is no
worst reading to compute), or let a lot it turns GREEN skip the fire route a
GREEN is held to.
"""

from __future__ import annotations

import json

import pytest
import shapely

from flats.encode.load import load_trusted
from flats.ingest.quadfit import _screen_lot_once, lot_from_row
from flats.score import flags as flag_plan, relief, slack
from flats.tests.test_quadfit_bridge import X0, Y0, pod4, row

pytestmark = pytest.mark.unit

W, D = 100.0, 200.0
#: A 100 x 200 lot, street along the south edge: room for the pod and its
#: court in every zone here, so what holds it out of GREEN is the flags.
BIG = dict(
    area_sqft=W * D,
    frontage_ft=W,
    lot_width_ft=W,
    lot_depth_ft=D,
    edges_json=json.dumps(
        [
            [X0, Y0, X0 + W, Y0, "F"],
            [X0 + W, Y0, X0 + W, Y0 + D, "S"],
            [X0 + W, Y0 + D, X0, Y0 + D, "R"],
            [X0, Y0 + D, X0, Y0, "S"],
        ]
    ),
    wkb=shapely.to_wkb(shapely.box(X0 + 5, Y0 + 10, X0 + W - 5, Y0 + D - 10)),
)


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


def screened(corpus, policies, *, bound: bool, **over):
    lot = lot_from_row(row(**{**BIG, **over}))
    (s,) = _screen_lot_once(
        lot, [pod4()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0,
        bound=bound,
    )
    return s


def severities(s) -> dict[str, int]:
    return {f.code: flag_plan.severity_of(f) for f in s.signed.flags}


NEIGHBOURS = (
    "FACT-ABUTS-NONRESIDENTIAL-ZONE",
    "FACT-CIVIC-CORRIDOR-SETBACK",
    "FACT-CIVIC-CORRIDOR-SETBACK-ALL-STREETS",
)


def test_facts_no_answer_can_turn_red_drop_to_zero_and_stay_named(corpus, policies) -> None:
    # Portland CM2: the neighbour's zone and the civic corridor each move a
    # setback, and on a lot this size no combination of them misses one.
    before = screened(corpus, policies, bound=False, jurisdiction="portland", zone="CM2")
    assert all(severities(before)[c] == 5 for c in NEIGHBOURS)
    after = screened(corpus, policies, bound=True, jurisdiction="portland", zone="CM2")
    got = severities(after)
    # Still named -- a flag, not deleted -- at 0, on the verdict and the
    # signed colour alike.
    assert all(got[c] == 0 for c in NEIGHBOURS)
    assert all(
        f.severity == 0 for f in after.screening.flags if f.code in NEIGHBOURS
    )
    assert not after.signed.binds


def test_a_lot_the_bound_makes_green_is_held_to_the_fire_route(corpus, policies) -> None:
    # Held at yellow, the plan skipped the route where none was found; once
    # its facts are bounded it is GREEN but for the route, and a GREEN is
    # measured. With no truck road here the route is unmeasured and says so.
    before = screened(corpus, policies, bound=False, jurisdiction="portland", zone="CM2")
    assert not before.facts.fire_route_tried
    assert "MEASURE-FIRE-ROUTE" not in severities(before)
    after = screened(corpus, policies, bound=True, jurisdiction="portland", zone="CM2")
    assert after.facts.fire_route_tried
    assert severities(after)["MEASURE-FIRE-ROUTE"] == 8
    assert after.signed.colour is flag_plan.Colour.yellow


def test_a_fact_whose_bad_answer_refuses_the_building_keeps_its_severity(
    corpus, policies
) -> None:
    # Happy Valley R20: a middle-housing child lot may not take a quadplex,
    # so the assumption that this lot is not one is worth exactly the lot.
    s = screened(corpus, policies, bound=True, jurisdiction="happy_valley", zone="R20")
    assert severities(s)["FACT-MIDDLE-HOUSING-CHILD-LOT"] == 5
    assert s.signed.colour is flag_plan.Colour.yellow


def test_a_fact_on_a_footnote_with_no_number_is_never_bounded(corpus, policies) -> None:
    # Gresham LDR-7: the sidewalk easement and the local street move the
    # yards by a footnote that states no number, so neither has a worst
    # reading anybody can compute.
    s = screened(corpus, policies, bound=True, jurisdiction="gresham", zone="LDR-7")
    assert {"sidewalk_easement", "local_street"} <= s.rules.unencoded
    got = severities(s)
    assert got["FACT-SIDEWALK-EASEMENT"] == 5 and got["FACT-LOCAL-STREET"] == 5


def test_a_red_plan_is_left_alone(corpus, policies) -> None:
    # The test lot at 50 x 100 misses its yards in Gresham: a bind already,
    # and nothing a flag says can make it redder.
    lot = lot_from_row(row(jurisdiction="gresham", zone="LDR-7"))
    (s,) = _screen_lot_once(
        lot, [pod4()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0
    )
    assert s.signed.binds
    assert all(f.severity is None for f in s.signed.flags)
