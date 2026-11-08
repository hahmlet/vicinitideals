"""FOLLOWUPS 105 round 3 (coordinator 2026-11-08): one unread target held.

Tigard RES-A through RES-C: "off-street parking areas provided at the side
or rear of buildings and not in garages must be screened from adjacent
properties to the S-3 standard, as provided in Table 18.420.2"
(18.280.040.D.4, 18.280/18.280.040.txt#L111). The pod's open rear court is
that parking, and Chapter 18.420 is not held, so whether S-3 takes court
ground is unread. The zones' permission is ``qualified_by`` the unobserved
``tigard_s3_screen_reaches_court``: out of GREEN (YELLOW), never RED.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from flats.rules.conditions import condition
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet, Verdict as RuleVerdict
from flats.score import relief, slack
from flats.score.configure import Configuration
from flats.score.flags import Colour, colour_rules, load_registry
from flats.score.screen import FACT_UNOBSERVED, screen
from flats.tests.test_round2_rulings import DESIGN, facts, fit as _fit

TIGARD = "or/washington/tigard"
S3 = "tigard_s3_screen_reaches_court"
S3_FLAG = "FACT-TIGARD-S3-SCREEN-REACHES-COURT"
HELD = ("RES-A", "RES-B", "RES-C")


@pytest.fixture(scope="module")
def corpus() -> RuleSet:
    return RuleSet(load_rules(strict=True))


def fit():
    # Room to spare every way, so that Tigard's own court (8.5 x 16 stalls on
    # a 20 ft aisle) is searched at its width and the lot clears on the rest.
    base = _fit()
    return replace(base, best_depth_ft=base.depth_ft + 120.0, slack_ft=120.0, across_ft=200.0)


#: A lot that clears every Tigard standard the screen measures.
ROOMY = {"street_lines_ft": (80.0,), "lot_sqft": 20000}


def _run(resolved, lot_facts, config):
    return screen(
        resolved,
        lot_facts,
        DESIGN,
        fit(),
        policy=slack.SlackPolicy(tolerance={"fit_ft": 0.5}),
        relief=relief.load_policy(),
        config=config,
    )


def _signed(corpus: RuleSet, zone: str):
    # Signed as the release signs it: an unsigned draft returns before the
    # facts are read, so the question would never be asked.
    return replace(corpus.resolve(TIGARD, zone, ()), verdict=RuleVerdict.trusted)


@pytest.mark.parametrize("zone", HELD)
def test_the_s3_screen_qualifies_the_lower_density_zones(corpus: RuleSet, zone: str) -> None:
    resolved = corpus.resolve(TIGARD, zone, ())
    assert S3 in resolved.levers
    assert S3 in resolved.unencoded
    # The qualifier holds the lot; it does not take the permission away.
    assert resolved.get("quadplex_allowed") is True


def test_the_other_tigard_zones_do_not_turn_on_it(corpus: RuleSet) -> None:
    for zone in corpus.layers[TIGARD].zones:
        if zone not in HELD:
            assert S3 not in corpus.resolve(TIGARD, zone, ()).levers, zone


def test_nothing_observes_the_fact_and_nothing_assumes_it() -> None:
    fact = condition(S3)
    assert fact.kind == "site_fact"
    assert fact.assume is None


@pytest.mark.parametrize("zone", HELD)
def test_an_unread_s3_screen_turns_a_green_yellow(corpus: RuleSet, zone: str) -> None:
    settled = _run(_signed(corpus, zone), facts(**ROOMY), Configuration())
    assert settled.colour is Colour.green
    got = _run(_signed(corpus, zone), facts(**ROOMY), Configuration(unknown=(S3,)))
    assert got.colour is Colour.yellow
    assert got.reasons == (FACT_UNOBSERVED,)
    assert [f for f in got.flags if f.code == S3_FLAG]


@pytest.mark.parametrize("zone", HELD)
def test_the_hold_never_makes_a_lot_red(corpus: RuleSet, zone: str) -> None:
    # The same lot with the fact settled False, against the fact unread: the
    # hold can only take a GREEN to YELLOW. Whatever else holds or fails the
    # lot is unchanged, and no colour gets worse than YELLOW on it.
    lot = facts(street_lines_ft=(80.0,), lot_sqft=900)
    settled = _run(_signed(corpus, zone), lot, Configuration())
    held = _run(_signed(corpus, zone), lot, Configuration(unknown=(S3,)))
    assert not [f for f in settled.flags if f.code == S3_FLAG]
    if settled.colour is Colour.red:
        assert held.colour is Colour.red
    else:
        assert held.colour is not Colour.red
    assert set(settled.reasons) <= set(held.reasons)


def test_the_s3_flag_is_registered_at_the_yellow_line() -> None:
    entry = load_registry()[S3_FLAG]
    assert entry.severity >= colour_rules().yellow_at_severity
