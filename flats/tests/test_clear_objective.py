"""Steph's ruling of 2026-10-15 (FOLLOWUPS 85): ORS 197A.400.

A city or county may apply only clear and objective standards to housing
inside an urban growth boundary. Where the only thing turning a lot red is a
judgement-based path -- a conditional use on judgement criteria, a one-off
judgement review -- the lot is GREEN with a flag below the yellow line:
"state law voids the judgement test; the city may refuse at first and an
appeal may be needed". The "may add conditions" review tier (YELLOW since
2026-10-14) goes the same way: any condition added must itself be clear and
objective.

Unchanged: a use the code does not list; land outside a UGB; the statute's
own exceptions (Portland's central city and Gateway, historic areas); a
measured standard the pod misses (RED); a zone with no clear standards to
judge by (grey).
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from flats.rules.loader import load_rules
from flats.rules.resolver import Resolved, RuleSet
from flats.score.flags import Colour, load_registry
from flats.score.screen import (
    CLEAR_OBJECTIVE,
    CLOSER_LOOK_REVIEW_CONDITIONS,
    USE_PROHIBITED,
    LotFacts,
    clear_objective_reaches,
)
from flats.tests.test_round2_rulings import PROV, WHERE, run
from flats.tests.test_round2_rulings import facts as _facts
from flats.tests.test_round2_rulings import rules as _rules

pytestmark = pytest.mark.unit


def facts(**over) -> LotFacts:
    return _facts(**{"inside_ugb": True, **over})


def rules(*, relief=(), **overrides):
    """A trusted rule set the statute reaches (``clear_objective_housing``)
    unless told otherwise; ``relief`` rides on ``quadplex_allowed``."""
    got = _rules(**{"clear_objective_housing": True, **overrides})
    if relief:
        q = got.values["quadplex_allowed"]
        got.values["quadplex_allowed"] = replace(q, relief=tuple(relief))
    return got


CU = ((("conditional_use",), True, "Test Code 2.2, the fourplex a conditional use"),)
JUDGEMENT = ((("judgement_review",), True, "Test Code 3.3, design review on 'compatible'"),)


def flags(result, code):
    return [f for f in result.flags if f.code == code]


# --- the ruling -------------------------------------------------------------


@pytest.mark.parametrize("path", [CU, JUDGEMENT], ids=["conditional_use", "judgement_review"])
def test_a_judgement_only_path_is_green_with_the_flag(path) -> None:
    got = run(facts(), rules(quadplex_allowed=False, relief=path))
    assert got.colour is Colour.green
    assert USE_PROHIBITED not in got.reasons
    assert not got.binds
    (flag,) = flags(got, "CLEAR-OBJECTIVE")
    assert path[0][0][0] in flag.key
    assert flag.source == path[0][2]


def test_the_flag_sits_below_the_yellow_line_and_says_why() -> None:
    entry = load_registry()["CLEAR-OBJECTIVE"]
    assert entry.severity < 3
    assert entry.description.startswith(
        "State law voids the judgement test; the city may refuse at first and an appeal may be needed"
    )
    assert CLEAR_OBJECTIVE in entry.raised_from


def test_the_yellow_review_tier_is_green_with_the_flag_now() -> None:
    """Scope change, Steph 2026-10-15: a review that may add conditions (and a
    mixed list that weighs judgement words) is GREEN with the flag inside a
    UGB -- a lot with a measurable review can never rank below a
    judgement-only lot that is now green."""
    for how in ("conditions", "judgement"):
        got = run(facts(), rules(review_discretion=how))
        assert got.colour is Colour.green, how
        assert CLOSER_LOOK_REVIEW_CONDITIONS not in got.reasons
        assert not flags(got, "REVIEW-CONDITIONS")
        (flag,) = flags(got, "CLEAR-OBJECTIVE")
        assert how in flag.key


def test_washington_countys_type_ii_gate_is_green_with_the_flag_now() -> None:
    gates = {"type_i_max_buildable_sqft": 10000, "type_i_density_escape_du_per_acre": 15}
    got = run(facts(lot_sqft=20000), rules(**gates))
    assert got.colour is Colour.green
    (flag,) = flags(got, "CLEAR-OBJECTIVE")
    assert "buildable_area" in flag.key


# --- what stays as it is ------------------------------------------------------


def test_a_use_the_code_does_not_list_stays_red() -> None:
    """No path at all: nothing for the statute to clear."""
    got = run(facts(), rules(quadplex_allowed=False))
    assert got.colour is Colour.red
    assert USE_PROHIBITED in got.reasons
    assert not flags(got, "CLEAR-OBJECTIVE")


def test_a_path_the_statute_does_not_clear_stays_red() -> None:
    """A planned development or a variance is its own procedure, not a
    judgement test laid over a listed use."""
    pd = ((("planned_development",), True, "Test Code 4.4"),)
    got = run(facts(), rules(quadplex_allowed=False, relief=pd))
    assert got.colour is Colour.red
    assert not flags(got, "CLEAR-OBJECTIVE")


@pytest.mark.parametrize("inside", [False, None], ids=["outside", "unknown"])
def test_outside_a_ugb_nothing_changes(inside) -> None:
    lot = facts(inside_ugb=inside)
    assert run(lot, rules(quadplex_allowed=False, relief=CU)).colour is Colour.red
    review = run(lot, rules(review_discretion="conditions"))
    assert review.colour is Colour.yellow
    assert flags(review, "REVIEW-CONDITIONS") and not flags(review, "CLEAR-OBJECTIVE")


def test_the_statutes_exceptions_keep_the_old_rule() -> None:
    """Where a layer holds an exception (Portland: central city and Gateway,
    ORS 197A.400(2)(a)) ``clear_objective_housing`` is false."""
    rs = rules(quadplex_allowed=False, relief=CU, clear_objective_housing=False)
    assert run(facts(), rs).colour is Colour.red
    review = run(facts(), rules(review_discretion="judgement", clear_objective_housing=False))
    assert review.colour is Colour.yellow


def test_a_measured_fail_stays_red() -> None:
    got = run(facts(lot_sqft=2000), rules(quadplex_allowed=False, relief=CU))
    assert got.colour is Colour.red
    assert flags(got, "CLEAR-OBJECTIVE")
    assert any(b.check == "min_lot_area_sqft" for b in got.binds)
    assert not any(b.check == "use" for b in got.binds)


def test_the_reach_needs_both_the_rule_and_the_boundary() -> None:
    assert clear_objective_reaches(rules(), facts())
    assert not clear_objective_reaches(rules(), facts(inside_ugb=None))
    assert not clear_objective_reaches(rules(clear_objective_housing=None), facts())


# --- the corpus -------------------------------------------------------------


@pytest.fixture(scope="module")
def corpus() -> RuleSet:
    return RuleSet(load_rules())


def test_the_state_layer_holds_the_statute_and_portland_the_exception(corpus) -> None:
    assert corpus.resolve("or/clackamas/canby", "R-1.5").get("clear_objective_housing") is True
    assert corpus.resolve("or/multnomah/portland", "R5").get("clear_objective_housing") is False


@pytest.mark.parametrize(
    ("layer", "zone", "relief"),
    [
        ("or/clackamas/canby", "R-1.5", "judgement_review"),
        ("or/clackamas/canby", "R-2", "judgement_review"),
        ("or/clackamas/canby", "C-R", "judgement_review"),
        ("or/clackamas/gladstone", "C1", "conditional_use"),
        ("or/clackamas/gladstone", "C3", "conditional_use"),
        ("or/clackamas/gladstone", "LI", "conditional_use"),
        ("or/clackamas/milwaukie", "NMU", "conditional_use"),
        ("or/clackamas/milwaukie", "SMU", "conditional_use"),
        ("or/clackamas/estacada", "R-2", "conditional_use"),
        ("or/clackamas/estacada", "R-3", "conditional_use"),
        ("or/clackamas/estacada", "C-1", "conditional_use"),
        ("or/multnomah/fairview", "VMU", "conditional_use"),
        ("or/multnomah/fairview", "VA", "conditional_use"),
        ("or/washington/cornelius", "CMU", "conditional_use"),
    ],
)
def test_each_opened_zone_names_its_path_and_cites_it(corpus, layer, zone, relief) -> None:
    allowed: Resolved = corpus.resolve(layer, zone).values["quadplex_allowed"]
    assert allowed.value is False
    paths = [(when, cite) for when, value, cite in allowed.relief if value is True and relief in when]
    assert paths, (layer, zone)
    assert all("ORS 197A.400" in cite for _when, cite in paths)


@pytest.mark.parametrize(
    ("layer", "zone"),
    [
        ("or/clackamas/happy-valley", "MUC"),
        ("or/clackamas/wilsonville", "PDC"),
        ("or/clackamas/milwaukie", "MUTSA"),
        ("or/clackamas/oregon-city", "MUE"),
        ("or/washington/cornelius", "CC"),
        ("or/multnomah/_unincorporated", "EFU"),
    ],
)
def test_unlisted_uses_and_farm_zones_keep_no_path(corpus, layer, zone) -> None:
    allowed = corpus.resolve(layer, zone).values["quadplex_allowed"]
    assert allowed.value is False
    assert not any(value is True for _when, value, _cite in allowed.relief)


def test_provenance_is_the_test_codes() -> None:
    # Guards the helper import: the reused rule set is the round-2 one.
    assert rules().jurisdiction == WHERE and rules().values["min_lot_sqft"].prov == PROV
