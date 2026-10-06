"""A utility easement nobody maps, read as a yard on every street line
(FOLLOWUPS 43, Steph 2026-10-01).

Beaverton BDC 20.05 / 20.22 note 7: "In no case shall a building encroach
into a Public Utility Easement (PUE)". No layer says where the easements
run, so the footnote held every lot it reaches on ``utility_easement`` and
Beaverton had no green lot. Steph's ruling: the building fits with a 10 ft
yard on every street line -> the question is answered; fits only at 5 ft ->
yellow; not even at 5 ft -> red. Oregon City's "public utility easements may
supersede the minimum setback" takes the same rule (Steph 2026-10-05).

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
from flats.ingest import quadfit
from flats.ingest.quadfit import (
    _chose,
    _fit_missed,
    _screen_lot_once,
    easement_checked,
    lot_from_row,
    screen_lot,
)
from flats.score import relief, slack
from flats.score.screen import STEEP_GROUND
from flats.score.slack import Verdict
from flats.tests.test_quadfit_bridge import X0, Y0

pytestmark = pytest.mark.unit

BEAVERTON = "or/washington/beaverton"
ASSUMED = "UTILITY-EASEMENT-ASSUMED"
OPEN = "FACT-UTILITY-EASEMENT"


# --- the ruling and the floor -------------------------------------------------


def test_beaverton_and_oregon_city_are_ruled_at_ten_and_five() -> None:
    for layer in (BEAVERTON, "or/clackamas/oregon-city"):
        got = easement.rules()[layer]
        assert (got.green_ft, got.yellow_ft) == (10.0, 5.0), layer
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
    # quadfit's envelope: no floor reaches it, nothing is answered.
    assert pick(as_is_missed=False, green_missed=False, green_measured=False) == "as_is"
    assert pick(as_is_missed=False, green_missed=False, green_measured=True) == "green"
    assert pick(as_is_missed=False, green_missed=True, green_measured=True, yellow_missed=False) == "yellow"
    # Short at the narrow yard too: held to that miss.
    assert pick(as_is_missed=False, green_missed=True, green_measured=True, yellow_missed=True) == "yellow"
    # Short at the code's own yards and at both of the ruling's: the
    # easement is not why the lot fails.
    assert pick(as_is_missed=True, green_missed=True, green_measured=True, yellow_missed=True) == "as_is"
    # But an as-is miss does not stop the ruling's yards being asked: on a
    # corner lot the open question can choose the front the plan misses on.
    assert pick(as_is_missed=True, green_missed=False, green_measured=True) == "green"
    assert pick(as_is_missed=True, green_missed=True, green_measured=True, yellow_missed=False) == "yellow"


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


def missed(s, check: str = "fit_ft"):
    """``s`` with its fit missed, under ``check``'s name."""
    checks = tuple(
        dataclasses.replace(c, check=check, verdict=Verdict.fails) if c.check == "fit_ft" else c
        for c in s.screening.checks
    )
    return dataclasses.replace(s, screening=dataclasses.replace(s.screening, checks=checks))


def on_steep_ground(s):
    """``s`` with its fit missed on ground too steep to build on, named as
    :func:`flats.ingest.quadfit.slope_checked` names it."""
    return missed(s, STEEP_GROUND)


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


def test_a_miss_on_steep_ground_is_a_miss(corpus, policies) -> None:
    s = as_is(corpus, policies, lot_from_row(lot_row(), corpus.layers))
    assert not _fit_missed(s)
    assert _fit_missed(on_steep_ground(s))


def corner_row(w: float = 100.0, d: float = 200.0) -> dict[str, object]:
    """:func:`lot_row` with a second street along its east edge."""
    edges = [
        [X0, Y0, X0 + w, Y0, "F"],
        [X0 + w, Y0, X0 + w, Y0 + d, "F"],
        [X0 + w, Y0 + d, X0, Y0 + d, "R"],
        [X0, Y0 + d, X0, Y0, "S"],
    ]
    return lot_row(w, d, tier="B", edges_json=json.dumps(edges), front_bearings_json="[0.0, 90.0]")


@pytest.mark.parametrize("check", ["fit_ft", STEEP_GROUND])
def test_a_corner_lot_missed_at_the_code_own_yards_is_still_asked_at_the_wide_one(
    corpus, policies, check
) -> None:
    # 2026-10-05 bound, 1S123AB02236: a corner lot whose open question ranked
    # the front the building misses on (on steep ground) above the one it
    # fits on. Answered, the building fits: the as-is miss was the question's.
    lot = lot_from_row(corner_row(), corpus.layers)
    before = as_is(corpus, policies, lot)
    assert _chose(lot, before)
    (got,) = easement_checked(
        lot, [missed(before, check)],
        rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0,
    )
    assert got.lot.observed.get("utility_easement") is False
    assert not _fit_missed(got)
    assert flags(got)[ASSUMED].bounds == (10.0, 10.0)


def test_a_lot_with_one_reading_that_missed_keeps_its_answer(corpus, policies) -> None:
    # One front, one cut: the floor can only shrink the envelope that missed.
    lot = lot_from_row(lot_row(), corpus.layers)
    before = missed(as_is(corpus, policies, lot))
    assert not _chose(lot, before)
    got = easement_checked(
        lot, [before], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0
    )
    assert got[0] is before


def test_a_wide_yard_missed_on_steep_ground_falls_to_the_narrow_one(
    corpus, policies, monkeypatch
) -> None:
    # The slope names a miss steep_ground, not fit_ft: read as a fit, the
    # wide yard "answered" a lot that missed there and the narrow yard was
    # never asked (2026-10-05 bound).
    real = quadfit._screen_lot_once

    def steep_at_ten(here, *args, **kwargs):
        got = real(here, *args, **kwargs)
        if here.facts.easement_street_ft == 10.0:
            return [on_steep_ground(s) for s in got]
        return got

    monkeypatch.setattr(quadfit, "_screen_lot_once", steep_at_ten)
    (got,) = easement_checked(
        lot_from_row(lot_row(), corpus.layers),
        [as_is(corpus, policies, lot_from_row(lot_row(), corpus.layers))],
        rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0,
    )
    assert "utility_easement" not in got.lot.observed
    assert not _fit_missed(got)
    assert flags(got)[ASSUMED].bounds == (5.0, 5.0)


def at_ten(monkeypatch, how) -> None:
    """Every screening at the 10 ft yard passed through ``how``."""
    real = quadfit._screen_lot_once

    def screen(here, *args, **kwargs):
        got = real(here, *args, **kwargs)
        if here.facts.easement_street_ft == 10.0:
            return [how(s) for s in got]
        return got

    monkeypatch.setattr(quadfit, "_screen_lot_once", screen)


def test_a_wide_yard_that_puts_the_hose_out_of_reach_falls_to_the_narrow_one(
    corpus, policies, monkeypatch
) -> None:
    # 2026-10-06 bound: 3 big Oregon City lots fit at 10 ft, but the deeper
    # building put the hose route past 150 ft -- red, and the 5 ft yard,
    # where it may reach, was never asked.
    at_ten(monkeypatch, lambda s: missed(s, "fire_access_ft"))
    lot = lot_from_row(lot_row(), corpus.layers)
    (got,) = easement_checked(
        lot, [as_is(corpus, policies, lot)],
        rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0,
    )
    assert "utility_easement" not in got.lot.observed
    assert not quadfit._lost(got, as_is(corpus, policies, lot))
    assert flags(got)[ASSUMED].bounds == (5.0, 5.0)


def test_a_check_failing_at_the_code_own_yards_is_not_the_yard_s(
    corpus, policies, monkeypatch
) -> None:
    # Failing as it stands and at 10 ft alike: the yard did not cause it,
    # and the question is answered at the wide yard.
    at_ten(monkeypatch, lambda s: missed(s, "fire_access_ft"))
    lot = lot_from_row(lot_row(), corpus.layers)
    before = missed(as_is(corpus, policies, lot), "fire_access_ft")
    assert not _fit_missed(before)
    (got,) = easement_checked(
        lot, [before], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0,
    )
    assert got.lot.observed.get("utility_easement") is False
    assert flags(got)[ASSUMED].bounds == (10.0, 10.0)


def test_what_the_yard_lost() -> None:
    from types import SimpleNamespace

    def plan(*failing: str):
        checks = tuple(
            SimpleNamespace(check=c, verdict=Verdict.fails if c in failing else Verdict.passes)
            for c in ("fit_ft", "fire_access_ft", "min_density_du_per_acre")
        )
        return SimpleNamespace(screening=SimpleNamespace(checks=checks))

    assert not quadfit._lost(plan(), plan())
    assert quadfit._lost(plan("fit_ft"), plan())
    # A fit missed both ways is still a miss at the yard.
    assert quadfit._lost(plan("fit_ft"), plan("fit_ft"))
    assert quadfit._lost(plan("fire_access_ft"), plan())
    assert not quadfit._lost(plan("min_density_du_per_acre"), plan("min_density_du_per_acre"))
    assert quadfit._lost(on_steep(), plan())


def on_steep():
    from types import SimpleNamespace

    return SimpleNamespace(
        screening=SimpleNamespace(checks=(SimpleNamespace(check=STEEP_GROUND, verdict=Verdict.fails),))
    )
