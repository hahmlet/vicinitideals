"""Wilsonville's Village zone: the quadplex route is for lots with a home (FOLLOWUPS 110).

Every number FLATS holds for a quadplex in V comes through 4.125(.23), and
(.23) opens "For lots previously developed with at least one residential
unit". A vacant Villebois lot is built through the SAP/PDP/FDP process of
(.18)(B) instead, which states no quadplex standard. Run 81 had two vacant V
lots green on (.23)'s numbers.

What must hold: the assessor roll answers ``no_existing_dwelling`` on
Wilsonville's lots only, True on vacant land with no building value and
False only where a home's value stands on residential land; V's permission
is qualified on it, so a lot with a home keeps its answer, a vacant lot and
a lot the roll does not settle are never green, and a lot red for another
reason stays red.
"""

from __future__ import annotations

import pytest

from flats.designs.model import load_catalog
from flats.encode.load import load_trusted
from flats.geom.roll import NO_DWELLING_FACT, no_existing_dwelling
from flats.ingest.quadfit import (
    DWELLING_ANSWERS,
    OBSERVABLE,
    S4_COLUMNS,
    lot_from_row,
    observed_facts,
    screen_lot,
)
from flats.rules.conditions import CONDITIONS
from flats.rules.loader import load_rules
from flats.score import flags as flag_plan
from flats.score import relief, slack
from flats.score.flags import fact_code
from flats.tests.test_utility_easement import lot_row as _beaverton_row

pytestmark = pytest.mark.unit

WILSONVILLE = "or/clackamas/wilsonville"
FLAG = fact_code(NO_DWELLING_FACT)
HOME = {"LANDUSE": "SFR", "PROP_CODE": "101", "BLDGVAL": 521780.0}
APARTMENTS = {"LANDUSE": "MFR", "PROP_CODE": "701", "BLDGVAL": 4186560.0}
VACANT = {"LANDUSE": "VAC", "PROP_CODE": "100", "BLDGVAL": 0.0}


# --- the roll reading ---------------------------------------------------------


def test_the_roll_answers_vacant_built_and_unsettled() -> None:
    assert no_existing_dwelling(VACANT) is True
    # A vacant class alone is enough with no building value.
    assert no_existing_dwelling({"LANDUSE": None, "PROP_CODE": "700", "BLDGVAL": 0}) is True
    assert no_existing_dwelling(HOME) is False
    assert no_existing_dwelling(APARTMENTS) is False
    # A house the roll has not valued yet, a building on land still called
    # vacant, a building of value on tract land, no value on file: unsettled.
    assert no_existing_dwelling({"LANDUSE": "SFR", "PROP_CODE": "101", "BLDGVAL": 0}) is None
    assert no_existing_dwelling({"LANDUSE": "VAC", "PROP_CODE": "100", "BLDGVAL": 9000}) is None
    assert no_existing_dwelling({"LANDUSE": "RUR", "PROP_CODE": "400", "BLDGVAL": 9000}) is None
    assert no_existing_dwelling({"LANDUSE": "SFR", "PROP_CODE": "101", "BLDGVAL": None}) is None
    assert no_existing_dwelling({"LANDUSE": "SFR", "PROP_CODE": "101", "BLDGVAL": float("nan")}) is None


def test_the_fact_is_registered_unassumed_and_read_on_wilsonville_only() -> None:
    assert CONDITIONS[NO_DWELLING_FACT].kind == "site_fact"
    assert CONDITIONS[NO_DWELLING_FACT].assume is None
    assert NO_DWELLING_FACT in OBSERVABLE
    assert DWELLING_ANSWERS == frozenset({"wilsonville"})
    assert {"LANDUSE", "PROP_CODE", "BLDGVAL"} <= set(S4_COLUMNS)
    assert observed_facts(_v_row(**VACANT))[NO_DWELLING_FACT] is True
    assert observed_facts(_v_row(**HOME))[NO_DWELLING_FACT] is False
    assert NO_DWELLING_FACT not in observed_facts(_v_row())
    assert NO_DWELLING_FACT not in observed_facts(_beaverton_row(**VACANT))


# --- the rule -----------------------------------------------------------------


def test_vs_permission_is_qualified_on_a_home_with_the_codes_own_words() -> None:
    held = load_rules()[WILSONVILLE].zones["V"].values["quadplex_allowed"]
    assert held.value is True
    assert held.qualified_by == NO_DWELLING_FACT
    assert "4.125(.23)" in held.qualified_cite and "4.125(.18)(B)" in held.qualified_cite
    from flats.provenance.store import ProvenanceStore

    text = ProvenanceStore().quote(held.qualified_quote)
    assert "previously developed with at least one" in text
    assert "may require modifications to the PDP" in text
    assert "Is consistent with the approved Specific Area Plan" in text


def test_the_flag_is_yellow() -> None:
    reg = flag_plan.registry()
    t = reg.types[FLAG]
    assert "4.125(.23)" in t.description
    assert t.severity >= flag_plan.colour_rules().yellow_at_severity


# --- through the bridge -------------------------------------------------------


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


def _v_row(w: float = 120.0, d: float = 200.0, **over: object) -> dict[str, object]:
    return _beaverton_row(w, d, TLID="31W15AC00000", jurisdiction="wilsonville", zone="V", **over)


def _screened(corpus, policies, row):
    (s,) = screen_lot(
        lot_from_row(row, corpus.layers),
        [load_catalog().latest("pod56x36")],
        rules=corpus,
        policy=policies[0],
        relief=policies[1],
        step_deg=30.0,
    )
    return s


def test_a_lot_with_a_home_keeps_its_answer(corpus, policies) -> None:
    s = _screened(corpus, policies, _v_row(**HOME))
    assert s.lot.observed.get(NO_DWELLING_FACT) is False
    assert FLAG not in {f.code for f in s.signed.flags}
    assert s.signed.colour is flag_plan.Colour.green


def test_a_vacant_lot_is_held_open_by_name_never_green(corpus, policies) -> None:
    home = _screened(corpus, policies, _v_row(**HOME))
    vacant = _screened(corpus, policies, _v_row(**VACANT))
    assert vacant.lot.observed.get(NO_DWELLING_FACT) is True
    assert FLAG in {f.code for f in vacant.signed.flags}
    assert vacant.signed.colour is flag_plan.Colour.yellow
    # Nothing but the home moved: the checks are the same checks.
    assert [(c.check, c.verdict) for c in vacant.screening.checks] == [
        (c.check, c.verdict) for c in home.screening.checks
    ]


def test_a_lot_the_roll_does_not_settle_is_never_green(corpus, policies) -> None:
    s = _screened(corpus, policies, _v_row(LANDUSE="SFR", PROP_CODE="101", BLDGVAL=0.0))
    assert NO_DWELLING_FACT not in s.lot.observed
    assert FLAG in {f.code for f in s.signed.flags}
    assert s.signed.colour is not flag_plan.Colour.green


def test_red_for_another_reason_stays_red(corpus, policies) -> None:
    # 6,000 sq ft is under (.23)'s 7,000: red whether or not anyone lives there.
    s = _screened(corpus, policies, _v_row(w=40.0, d=150.0, **VACANT))
    assert s.signed.colour is flag_plan.Colour.red
