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

import dataclasses
import json

import pytest
import shapely

from flats.encode.load import load_trusted
from flats.geom import split_zone as sz
from flats.ingest.quadfit import _screen_lot_once, lot_from_row, screen_lot
from flats.score import flags as flag_plan, relief, slack
from flats.tests.test_quadfit_bridge import X0, Y0, pod4, row

pytestmark = pytest.mark.unit

W, D = 100.0, 200.0
OFF_PLAN_DISTRICTS = dict.fromkeys(
    (
        "pdx_johnson_creek_impervious",
        "pdx_johnson_creek_unmeasured",
        "pdx_special_building_setback",
        "pdx_glendoveer_lr75",
        "pdx_plan_district_unmeasured",
        "pdx_nw_residential_limited",
        "pdx_gateway_min_far",
        "pdx_east_corridor_min_far_half",
        "pdx_east_corridor_min_far_one",
    ),
    False,
)
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
    # Portland's plan district tracings answer from the lot's shape and the
    # layers, which this row is read without; the lot is off all three.
    lot = dataclasses.replace(lot, observed={**lot.observed, **OFF_PLAN_DISTRICTS})
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
    # Gresham LDR-7: the sidewalk easement moves the yards by a footnote that
    # states no number until a depth is taken, so with none it has no worst
    # reading anybody can compute.
    s = screened(corpus, policies, bound=True, jurisdiction="gresham", zone="LDR-7")
    assert "sidewalk_easement" in s.rules.unencoded
    assert severities(s)["FACT-SIDEWALK-EASEMENT"] == 5


#: A Gresham LDR-7 lot a street ends near (FOLLOWUPS 58): the bridge cannot say
#: it is not at the end. Its own polygon is held, so the envelope is the one
#: FLATS cuts, and Marine Drive is answered (the row carries no layers).
NEAR_END = dict(
    jurisdiction="gresham",
    zone="LDR-7",
    street_end_ft=40.0,
    lot_wkb=shapely.to_wkb(shapely.box(X0, Y0, X0 + W, Y0 + D)),
)


def near_end(corpus, policies, *, easement_ft: float, **observed):
    lot = lot_from_row(row(**{**BIG, **NEAR_END, "sidewalk_easement_ft": easement_ft}))
    lot = dataclasses.replace(
        lot,
        observed={
            **lot.observed,
            **OFF_PLAN_DISTRICTS,
            "north_of_marine_drive": False,
            **observed,
        },
    )
    (s,) = screen_lot(lot, [pod4()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    return s


def test_the_end_of_a_minor_access_street_is_a_number_now(corpus, policies) -> None:
    # Table 4.0131 note 5's 25 ft maximum is encoded on the fact, so the fact
    # is no longer a footnote with no number; read "at the end", the drawn
    # building is measured from the street (10 ft yard + 7 ft easement).
    s = near_end(corpus, policies, easement_ft=7.0, at_street_end=True)
    assert "at_street_end" not in s.rules.unencoded
    assert s.rules.get("setback_front_max_ft") == 25
    assert s.facts.front_max_streets == ((True, 17.0, 17.0, 7.0),)
    assert s.signed.colour is flag_plan.Colour.green


def test_a_lot_whose_building_stands_within_25_ft_of_every_street_clears_the_end(
    corpus, policies
) -> None:
    # Not observed either way: tried both ways, it clears on both, so the
    # flag stays named at 0 and the lot is GREEN.
    s = near_end(corpus, policies, easement_ft=7.0)
    assert severities(s)["FACT-AT-STREET-END"] == 0
    assert s.signed.colour is flag_plan.Colour.green


def test_a_building_past_the_25_ft_on_the_strict_reading_keeps_the_end_flag(
    corpus, policies
) -> None:
    # A 20 ft easement depth puts the building 30 ft from the lot line: past
    # 25 measured from the line, within it from the easement. Which one the
    # code measures from is a question, so "at the end" is not cleared and
    # the lot stays YELLOW -- never GREEN, and never RED on a fact nobody
    # observed.
    s = near_end(corpus, policies, easement_ft=20.0)
    assert severities(s)["FACT-AT-STREET-END"] == 5
    assert s.signed.colour is flag_plan.Colour.yellow


def test_a_red_plan_is_left_alone(corpus, policies) -> None:
    # The test lot at 50 x 100 misses its yards in Gresham: a bind already,
    # and nothing a flag says can make it redder.
    lot = lot_from_row(row(jurisdiction="gresham", zone="LDR-7"))
    (s,) = _screen_lot_once(
        lot, [pod4()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0
    )
    assert s.signed.binds
    assert all(f.severity is None for f in s.signed.flags)


def test_a_split_zone_question_does_not_hold_back_the_relief_of_another_fact(
    corpus, policies
) -> None:
    # A lot whose plan stands across a zone line is yellow for that, and for
    # that alone: the neighbour facts it clears at their worst reading still
    # drop to 0. The re-screens the bound runs raise ZONE-SPLIT too (their
    # plans stand somewhere else); that question is not "a new miss", and
    # must not keep the other flags at their full severity.
    east = sz.Piece("CM2", 40 * D, shapely.box(X0 + 60, Y0, X0 + W, Y0 + D), 40.0)
    split = {sz.ROW_KEY: sz.encode(sz.Split((east,), own_sqft=60 * D))}
    s = screened(corpus, policies, bound=True, jurisdiction="portland", zone="CM2", **split)
    got = severities(s)
    assert "ZONE-SPLIT" in got
    assert all(got[c] == 0 for c in NEIGHBOURS)
    assert s.signed.colour is flag_plan.Colour.yellow
