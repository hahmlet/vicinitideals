"""A utility easement nobody maps, read as a yard on every street line
(FOLLOWUPS 43, Steph 2026-10-01).

Beaverton BDC 20.05 / 20.22 note 7: "In no case shall a building encroach
into a Public Utility Easement (PUE)". No layer says where the easements
run, so the footnote held every lot it reaches on ``utility_easement`` and
Beaverton had no green lot. Steph's ruling: the building fits with a 10 ft
yard on every street line -> the question is answered; fits only at 5 ft ->
yellow; not even at 5 ft -> red.

What must hold: the floor touches street lines only; a lot clear of it
answers the question and says what it assumed; a lot that fits only at the
narrow yard stays open; one that fits at neither is held to the miss; a lot
that already misses at the code's own yards, and a city with no ruling,
keep the answer they had.
"""

from __future__ import annotations

import dataclasses
import json

import pytest
import shapely
from shapely.geometry import box

from flats.designs.model import load_catalog
from flats.encode.load import load_trusted
from flats.fit import easement
from flats.fit.easement import EasementRule, floored, pick
from flats.geom.envelope import Setbacks
from flats.ingest.quadfit import _fit_missed, _screen_lot_once, easement_checked, lot_from_row, screen_lot
from flats.score import relief, slack
from flats.tests.test_quadfit_bridge import X0, Y0

pytestmark = pytest.mark.unit

BEAVERTON = "or/washington/beaverton"
ASSUMED = "UTILITY-EASEMENT-ASSUMED"
OPEN = "FACT-UTILITY-EASEMENT"


# --- the ruling and the floor -------------------------------------------------


def test_beaverton_is_ruled_at_ten_and_five() -> None:
    got = easement.rules()[BEAVERTON]
    assert (got.green_ft, got.yellow_ft) == (10.0, 5.0)
    assert easement.rule_for("or/multnomah/portland") is None
    assert easement.rule_for(None) is None


def test_a_rule_needs_the_narrow_yard_inside_the_wide_one() -> None:
    with pytest.raises(ValueError):
        EasementRule(green_ft=5.0, yellow_ft=10.0)
    with pytest.raises(ValueError):
        EasementRule(green_ft=10.0, yellow_ft=0.0)


def test_the_floor_reaches_street_lines_only() -> None:
    code = Setbacks(
        front_ft=5.0, side_ft=5.0, rear_ft=8.0, street_side_ft=7.0, alley_side_ft=0.0,
        street_off_corridor_ft=0.0, alley_rear_ft=0.0, street_clear_ft=12.0,
    )
    got = floored(code, 10.0)
    assert (got.front_ft, got.street_side_ft, got.street_off_corridor_ft, got.street_clear_ft) == (
        10.0, 10.0, 10.0, 12.0,
    )
    # "Just the side on a street": side, rear and alley lines keep the code's.
    assert (got.side_ft, got.rear_ft, got.alley_side_ft, got.alley_rear_ft) == (5.0, 8.0, 0.0, 0.0)


def test_a_street_side_the_code_does_not_tell_apart_follows_the_floored_front() -> None:
    got = floored(Setbacks(front_ft=5.0, side_ft=5.0, rear_ft=5.0), 10.0)
    assert got.street_side_ft is None and got.front_ft == 10.0


def test_no_floor_is_no_change() -> None:
    code = Setbacks(front_ft=5.0, side_ft=5.0, rear_ft=5.0)
    assert floored(code, None) is code
    assert floored(code, 0.0) is code


def test_which_screening_answers() -> None:
    # Already short at the code's own yards: the easement changes nothing.
    assert pick(as_is_missed=True, green_missed=False, green_measured=True) == "as_is"
    # quadfit's envelope: no floor reaches it, nothing is answered.
    assert pick(as_is_missed=False, green_missed=False, green_measured=False) == "as_is"
    assert pick(as_is_missed=False, green_missed=False, green_measured=True) == "green"
    assert pick(as_is_missed=False, green_missed=True, green_measured=True) == "yellow"


# --- through the bridge -------------------------------------------------------


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


def pod():
    return load_catalog().latest("pod56x36")


def lot_row(w: float = 100.0, d: float = 200.0, **over: object) -> dict[str, object]:
    """A Beaverton RMA lot, ``w`` by ``d``, its street along the south edge."""
    edges = [
        [X0, Y0, X0 + w, Y0, "F"],
        [X0 + w, Y0, X0 + w, Y0 + d, "S"],
        [X0 + w, Y0 + d, X0, Y0 + d, "R"],
        [X0, Y0 + d, X0, Y0, "S"],
    ]
    base: dict[str, object] = {
        "TLID": "1S116AA00100",
        "jurisdiction": "beaverton",
        "zone": "RMA",
        "tier": "A",
        "area_sqft": w * d,
        "frontage_ft": w,
        "lot_width_ft": w,
        "lot_depth_ft": d,
        "edges_json": json.dumps(edges),
        "front_bearings_json": "[0.0]",
        "fronts_cul_de_sac": False,
        "split_zone": False,
        "ovl_fema_sfha": False,
        "ovl_fema_floodway": False,
        "sewer_main_dist_ft": 12.0,
        "in_sewer_district": None,
        "wkb": shapely.to_wkb(box(X0 + 5, Y0 + 10, X0 + w - 5, Y0 + d - 15)),
        "lot_wkb": shapely.to_wkb(box(X0, Y0, X0 + w, Y0 + d)),
    }
    base.update(over)
    return base


def as_is(corpus, policies, lot):
    (s,) = _screen_lot_once(
        lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0
    )
    return s


def screened(corpus, policies, lot):
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    return s


def flags(s) -> dict[str, object]:
    return {f.code: f for f in s.signed.flags}


def ruled(monkeypatch, green: float, yellow: float) -> None:
    monkeypatch.setattr(
        easement, "rules", lambda path=None: {BEAVERTON: EasementRule(green_ft=green, yellow_ft=yellow)}
    )


def test_the_footnote_holds_the_lot_on_the_question(corpus, policies) -> None:
    # Before the ruling is applied: the lot fits, and waits on the easement.
    s = as_is(corpus, policies, lot_from_row(lot_row(), corpus.layers))
    assert not _fit_missed(s)
    assert OPEN in flags(s) and ASSUMED not in flags(s)


def test_a_lot_clear_of_ten_feet_has_its_question_answered(corpus, policies) -> None:
    s = screened(corpus, policies, lot_from_row(lot_row(), corpus.layers))
    assert s.lot.observed.get("utility_easement") is False
    assert s.envelope is not None and s.envelope.source == "flats"
    assert s.envelope.setbacks.front_ft >= 10.0
    got = flags(s)
    assert OPEN not in got
    # Named, with the yard it assumed, and below the yellow line.
    assert got[ASSUMED].bounds == (10.0, 10.0)
    assert s.facts is not None and s.facts.easement_street_ft == 10.0


def test_a_lot_that_fits_only_at_the_narrow_yard_stays_open(corpus, policies, monkeypatch) -> None:
    # A wide yard no plan on a 200-ft lot clears; the narrow one is the
    # code's own 10 ft front, which it does.
    ruled(monkeypatch, green=150.0, yellow=10.0)
    s = screened(corpus, policies, lot_from_row(lot_row(), corpus.layers))
    assert "utility_easement" not in s.lot.observed
    assert not _fit_missed(s)
    got = flags(s)
    assert OPEN in got
    assert got[ASSUMED].bounds == (10.0, 10.0)


def test_a_lot_that_fits_at_neither_yard_is_held_to_the_miss(corpus, policies, monkeypatch) -> None:
    ruled(monkeypatch, green=170.0, yellow=150.0)
    s = screened(corpus, policies, lot_from_row(lot_row(), corpus.layers))
    assert _fit_missed(s)
    assert s.envelope.setbacks.front_ft == 150.0
    assert flags(s)[ASSUMED].bounds == (150.0, 150.0)


def test_a_lot_short_at_the_code_own_yards_keeps_its_answer(corpus, policies) -> None:
    lot = lot_from_row(lot_row(w=40.0, d=70.0), corpus.layers)
    before = as_is(corpus, policies, lot)
    assert _fit_missed(before)
    got = easement_checked(
        lot, [before], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0
    )
    assert got[0] is before


def test_a_city_with_no_ruling_is_untouched(corpus, policies) -> None:
    lot = lot_from_row(lot_row(jurisdiction="portland", zone="R5"), corpus.layers)
    before = as_is(corpus, policies, lot)
    got = easement_checked(
        lot, [before], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0
    )
    assert got[0] is before


def test_a_lot_already_answered_is_not_asked_again(corpus, policies) -> None:
    lot = lot_from_row(lot_row(), corpus.layers)
    lot = dataclasses.replace(lot, observed={**lot.observed, "utility_easement": False})
    before = as_is(corpus, policies, lot)
    got = easement_checked(
        lot, [before], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0
    )
    assert got[0] is before
