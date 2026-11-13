"""FOLLOWUPS 105 round 2 (coordinator 2026-11-08): two references followed to a rule.

* Beaverton Downtown, Figure 70.20.10.6.2: a facade on a Type A frontage
  takes the Non-residential Active Ground Floor Design, a ground floor at
  least 16 ft floor to floor (70.20.10.6 S1.a, D.2), against the pod's 12.
  Traced 2026-11-13 (FOLLOWUPS 105 item 1, flats.geom.active_frontage and
  flats/tests/test_active_frontage.py): a Type B frontage owes the
  Residential design's 12 ft (S2.c) under ``beaverton_active_frontage``,
  Type A 16 ft with ``beaverton_type_a_frontage`` too; a lot either fact
  leaves unanswered is held out of GREEN.
* Washington County 430-84: alley access only from an "improved alley"
  (409-3.3 A, not held). Where the court is reached from the alley the lot
  carries ALLEY-IMPROVEMENT-UNCONFIRMED, below the yellow line: no colour
  moves.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from flats.designs.model import load_catalog
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet, Verdict as RuleVerdict
from flats.score import relief, slack
from flats.score.configure import Configuration
from flats.score.flags import Colour, colour_rules, load_registry
from flats.score.screen import FACT_UNOBSERVED, screen
from flats.tests.test_round2_rulings import DESIGN, check, facts, fit, rules

BEAVERTON = "or/washington/beaverton"
WASHCO = "or/washington/_unincorporated"
TYPE_A = "beaverton_type_a_frontage"
ON_MAP = "beaverton_active_frontage"
DOWNTOWN = ("RC-BC", "RC-OT", "RC-MU", "RC-DT")
ALLEY_FLAG = "ALLEY-IMPROVEMENT-UNCONFIRMED"
TYPE_A_FLAG = "FACT-BEAVERTON-TYPE-A-FRONTAGE"


@pytest.fixture(scope="module")
def corpus() -> RuleSet:
    return RuleSet(load_rules(strict=True))


def _run(rule_set, lot_facts, config=None, design=DESIGN):
    return screen(
        rule_set,
        lot_facts,
        design,
        fit(),
        policy=slack.SlackPolicy(tolerance={"fit_ft": 0.5}),
        relief=relief.load_policy(),
        config=config,
    )


# --- Beaverton Downtown -------------------------------------------------------


@pytest.mark.parametrize("zone", DOWNTOWN)
def test_the_ground_floor_binds_only_on_a_mapped_frontage(corpus: RuleSet, zone: str) -> None:
    assert corpus.resolve(BEAVERTON, zone, ()).get("min_ground_story_ft") is None
    # Type B: the Residential design's 12 ft is the least it may take (S2.c).
    assert corpus.resolve(BEAVERTON, zone, (ON_MAP,)).get("min_ground_story_ft") == 12
    assert corpus.resolve(BEAVERTON, zone, (ON_MAP, TYPE_A)).get("min_ground_story_ft") == 16
    # Levers, so an unanswered fact holds the lot out of GREEN.
    levers = corpus.layers[BEAVERTON].zones[zone].values["min_ground_story_ft"].levers
    assert {ON_MAP, TYPE_A} <= levers


def test_other_beaverton_zones_do_not_turn_on_it(corpus: RuleSet) -> None:
    for zone in ("RC-E", "RMA", "CM-RM"):
        assert TYPE_A not in corpus.resolve(BEAVERTON, zone, ()).levers
        assert ON_MAP not in corpus.resolve(BEAVERTON, zone, ()).levers


@pytest.mark.parametrize("zone", DOWNTOWN)
def test_an_unobserved_type_a_frontage_is_never_green(corpus: RuleSet, zone: str) -> None:
    # Signed as the release signs it: an unsigned draft returns before the
    # facts are read, so the question would never be asked.
    resolved = replace(corpus.resolve(BEAVERTON, zone, ()), verdict=RuleVerdict.trusted)
    got = _run(resolved, facts(street_lines_ft=(80.0,)), Configuration(unknown=(ON_MAP, TYPE_A)))
    assert got.colour is not Colour.green
    assert FACT_UNOBSERVED in got.reasons
    assert [f for f in got.flags if f.code == TYPE_A_FLAG]


def test_the_pod_misses_sixteen_feet_on_a_type_a_frontage() -> None:
    pod = load_catalog().latest("pod80x30")
    assert pod.ground_story_ft is not None and pod.ground_story_ft < 16
    got = _run(rules(min_ground_story_ft=16), facts(street_lines_ft=(80.0,)), design=pod)
    assert check(got, "min_ground_story_ft").verdict is slack.Verdict.fails
    assert got.colour is Colour.red


def test_the_type_a_flag_is_registered_at_the_yellow_line() -> None:
    entry = load_registry()[TYPE_A_FLAG]
    assert entry.severity >= colour_rules().yellow_at_severity


# --- Washington County improved alley ------------------------------------------

ALLEY_LOT = {"street_lines_ft": (80.0,), "alley_at_rear": True, "alley_rear_whole": True, "alley_width_ft": 20.0}


def test_the_county_reads_the_improved_alley_sentence(corpus: RuleSet) -> None:
    zone = next(iter(corpus.layers[WASHCO].zones))
    assert corpus.resolve(WASHCO, zone, ()).get("alley_improved_required") is True


def test_an_alley_fed_court_carries_the_flag_and_keeps_its_colour() -> None:
    entry = load_registry()[ALLEY_FLAG]
    assert entry.severity < colour_rules().yellow_at_severity
    sent = {"parking_alley_access_required": True}
    flagged = _run(rules(**sent, alley_improved_required=True), facts(**ALLEY_LOT))
    plain = _run(rules(**sent), facts(**ALLEY_LOT))
    assert [f.by for f in flagged.flags if f.code == ALLEY_FLAG] == ["ALLEY_IMPROVEMENT_UNCONFIRMED"]
    assert flagged.colour is plain.colour
    assert flagged.reasons == plain.reasons


def test_no_flag_where_the_court_is_fed_from_the_street() -> None:
    # The county only permits alley access; with nothing sending the court
    # there, the alley is not used and nothing is flagged.
    got = _run(rules(alley_improved_required=True), facts(**ALLEY_LOT))
    assert not [f for f in got.flags if f.code == ALLEY_FLAG]
    no_alley = _run(
        rules(parking_alley_access_required=True, alley_improved_required=True),
        facts(street_lines_ft=(80.0,)),
    )
    assert not [f for f in no_alley.flags if f.code == ALLEY_FLAG]
