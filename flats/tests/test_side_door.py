"""The pod that fits only with its doors to a side yard (FOLLOWUPS 177).

Steph 2026-11-10 (rulings.yaml ``2026-11-10-side-door-fit-yellow``): the
2026-11-08 ruling stands for the design -- no street-facing door on the end
home -- so where a code makes the front doors face the street the pod is
searched with its 80 ft door face toward one. Where that search misses the
fit and the pod fits turned sideways, the lot is YELLOW, flagged
ENTRANCE-SIDE-DOOR ("fits only with doors facing the side; needs a
street-facing end door (design change)"): never GREEN, not RED on this
ground alone. A lot that fits facing the street, or misses both ways, is
unchanged (:func:`flats.ingest.quadfit.side_door_checked`).
"""

from __future__ import annotations

import dataclasses

import pytest

from flats.designs.model import Orientation
from flats.score import relief, slack
from flats.score.flags import Colour, registry
from flats.score.paper import door_limit, door_rule, door_turned, doors_to_the_side
from flats.score.screen import CLOSER_LOOK_ENTRANCE_SIDE, screen
from flats.tests.test_entrance_orientation import POD, _bridge, _fit
from flats.tests.test_round2_rulings import facts, rules

pytestmark = pytest.mark.unit

FLAG = "ENTRANCE-SIDE-DOOR"


@pytest.fixture(scope="module")
def corpus():
    from flats.encode.load import load_trusted

    return load_trusted(strict=False).rules


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


@pytest.fixture(autouse=True)
def _wide_lane_only(monkeypatch) -> None:
    """These Portland lots are measured on the 12 ft lane alone: the 9 ft
    retry (rulings.yaml 2026-11-10-portland-driveway-9ft) fits some of them
    facing the street, which test_portland_narrow_drive.py covers."""
    from flats.ingest import quadfit

    monkeypatch.setattr(quadfit, "narrow_lane_checked", lambda lot, designs, got, **kw: got)


def _street_only(monkeypatch) -> None:
    from flats.ingest import quadfit

    monkeypatch.setattr(quadfit, "side_door_checked", lambda lot, designs, got, **kw: got)


def _codes(s) -> set[str]:
    return {f.code for f in s.signed.flags}


# --- the switch -------------------------------------------------------------------


def test_the_side_search_frees_the_doors_only_inside_its_block() -> None:
    got = rules(entrance_faces_street="required")
    assert door_limit(got, POD) == 0.0
    with doors_to_the_side():
        assert door_limit(got, POD) is None
        # The standard still binds; only the search is freed.
        assert door_rule(got, POD) == 0.0
    assert door_limit(got, POD) == 0.0


def test_the_flag_is_registered_at_the_yellow_line() -> None:
    kind = registry()[FLAG]
    assert kind.severity >= 3
    assert CLOSER_LOOK_ENTRANCE_SIDE in kind.raised_from


# --- the screen: a side-door fit is never GREEN --------------------------------------


def test_a_side_door_fit_is_held_yellow_with_the_street_facing_miss() -> None:
    fit = _fit(90.0, Orientation.depth_facing)
    values = {"entrance_faces_street": "required"}
    policy = slack.SlackPolicy(tolerance={"fit_ft": 0.5})
    plain = screen(
        rules(**values), facts(lot_sqft=12000, street_bearings=(0.0,)), POD, fit,
        policy=policy, relief=relief.load_policy(),
    )
    marked = screen(
        rules(**values),
        dataclasses.replace(
            facts(lot_sqft=12000, street_bearings=(0.0,)), entrance_side_fit=(75.0, 118.0)
        ),
        POD,
        fit,
        policy=policy,
        relief=relief.load_policy(),
    )
    assert plain.colour is Colour.green
    assert marked.colour is Colour.yellow
    assert CLOSER_LOOK_ENTRANCE_SIDE in marked.reasons
    (flag,) = [f for f in marked.flags if f.code == FLAG]
    assert flag.bounds == (75.0, 118.0)


# --- the bridge: the three cases ------------------------------------------------------


@pytest.mark.parametrize(
    ("wide", "deep"),
    [
        (95.0, 200.0),
        # The shape of 1S2E04CB  -09000 (Portland R5, 89.9 x 98.6): end-on
        # with a few feet spare, 74.5 ft against 118 facing the street.
        (90.0, 99.0),
    ],
)
def test_a_lot_that_fits_only_sideways_is_yellow_and_flagged(
    corpus, policies, monkeypatch, wide, deep
) -> None:
    s = _bridge(corpus, policies, wide, deep)
    assert s.signed.colour is Colour.yellow
    assert s.screening.colour is not Colour.green
    assert FLAG in _codes(s)
    assert s.fit.fits and door_turned(POD, s.fit, s.lot.front_bearings)
    (flag,) = [f for f in s.signed.flags if f.code == FLAG]
    low, high = flag.bounds
    assert low < high  # the street-facing fit missed
    _street_only(monkeypatch)
    street = _bridge(corpus, policies, wide, deep)
    assert street.signed.colour is Colour.red
    assert FLAG not in _codes(street)


def test_a_lot_that_fits_facing_the_street_is_unchanged(corpus, policies, monkeypatch) -> None:
    s = _bridge(corpus, policies, 140.0, 140.0)
    assert FLAG not in _codes(s)
    assert s.fit.fits and not door_turned(POD, s.fit, s.lot.front_bearings)
    _street_only(monkeypatch)
    street = _bridge(corpus, policies, 140.0, 140.0)
    assert s.signed.colour is street.signed.colour
    assert s.screening.fit_slack_ft == street.screening.fit_slack_ft
    assert _codes(s) == _codes(street)


def test_a_lot_that_fits_neither_way_stays_red_unchanged(corpus, policies, monkeypatch) -> None:
    s = _bridge(corpus, policies, 50.0, 100.0)
    assert s.signed.colour is Colour.red
    assert FLAG not in _codes(s)
    _street_only(monkeypatch)
    street = _bridge(corpus, policies, 50.0, 100.0)
    assert s.screening.fit_slack_ft == street.screening.fit_slack_ft
    assert s.screening.head == street.screening.head
    assert _codes(s) == _codes(street)


# --- a lot with no street line at all ------------------------------------------------


def _no_street(corpus, policies, wide: float, deep: float):
    """A Portland R5 lot on which s4 found no street line (tier D, no street
    bearing, every edge a side)."""
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
        TLID="1S2E20AA  -99177",
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
    assert lot.facts.landlocked and not lot.front_bearings
    (s,) = screen_lot(lot, [POD], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    return s


@pytest.mark.parametrize(("wide", "deep"), [(95.0, 200.0), (140.0, 140.0)])
def test_a_lot_with_no_street_line_gets_no_side_door_search(
    corpus, policies, monkeypatch, wide, deep
) -> None:
    # Coordinator 2026-11-10: a lot with no street line keeps today's answer;
    # the side-door search must not turn it RED -> YELLOW.
    s = _no_street(corpus, policies, wide, deep)
    assert door_rule(s.rules, POD) is not None
    assert s.signed.colour is Colour.red
    assert FLAG not in _codes(s)
    _street_only(monkeypatch)
    street = _no_street(corpus, policies, wide, deep)
    assert s.signed.colour is street.signed.colour
    assert s.screening.head == street.screening.head
    assert _codes(s) == _codes(street)

