"""Clackamas districts that need design review are YELLOW (Steph 2026-10-14).

ZDO 1102.01(A) requires design review for development in HDR, MR-1, MR-2, PMD
and VA (and every commercial district), and a quadplex is none of the listed
exceptions. From 2026-10-09 the by-right-only ruling (2026-10-08) made those
districts red. Steph's review rule of 2026-10-14 replaced it: a review held to
measurable standards is green, one that may add conditions or weighs judgement
beside them is yellow, one that is all judgement is red. Design review holds a
quadplex to Section 1005 (1102.03(A)), whose facade criteria mix measurable
standards with judgement words ("architectural relief, variety and visual
interest"), so the districts admit the pod with ``review_discretion:
judgement`` (REVIEW-CONDITIONS, yellow). PMU1-3 stay red: Table 510-3 and the
master plan (1102.03(B)) are a one-off decision.
"""

from __future__ import annotations

import pytest

from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

LAYER = "or/clackamas/_unincorporated"
REVIEWED = ["HDR", "MR1", "MR2", "PMD", "VA", "SCMU"]
#: SCMU's front building line turns on the street type of each frontage on
#: Map 1005-1 (1005.09), which no lot carries: admitted by the use, and grey
#: until that is read. Nothing is invented for it here. (HDR was grey for its
#: 1005.02(L) solar plane until the lot-line-bearing lane encoded it.)
UNENCODED = {"SCMU"}


@pytest.mark.parametrize("zone", REVIEWED)
def test_design_review_districts_admit_the_pod_with_a_judgement_flag(zone: str) -> None:
    got = RuleSet(load_rules()).resolve(LAYER, zone)
    assert got.values["quadplex_allowed"].value is True
    assert got.values["review_discretion"].value == "judgement"
    if zone not in UNENCODED:
        assert got.missing_required == (), zone


def test_the_districts_that_stay_by_right_are_untouched() -> None:
    # R-5 permits the quadplex and 1102.01(A) does not name it.
    use = RuleSet(load_rules()).resolve(LAYER, "R5").values["quadplex_allowed"]
    assert use.value is True



# --- the citation (FOLLOWUPS 52, Section 1102 stored 2026-10-09) --------------


def _held(zone: str):
    return load_rules()[LAYER].zones[zone].values["quadplex_allowed"]


@pytest.mark.parametrize("zone", REVIEWED)
def test_the_flag_cites_the_design_review_and_the_judgement_words(zone: str) -> None:
    # The use table says P and the value quotes it; the yellow is the
    # review's, so review_discretion quotes the 1005 words a reviewer weighs
    # and names 1102.01(A) and the Type II process in its cite.
    store = ProvenanceStore()
    held = load_rules()[LAYER].zones[zone].values
    assert "zdo.1102.txt" not in held["quadplex_allowed"].prov.quote
    review = held["review_discretion"]
    assert "1102.01(A)" in review.prov.cite and "Type II" in review.prov.cite
    words = " ".join(store.quote(review.prov.quote).split())
    assert "architectural relief, variety and visual interest" in words
    assert "Provide visual interest" in words
    gate = " ".join(store.quote(f"{LAYER}/zdo.1102.txt#L13,L131,L155").split())
    assert "HDR, MR-1, MR-2, MRR, PMD, RCHDR, SHD, VA, and VTH Districts" in gate
    assert "Type II application" in gate
    assert "conditions of design review approval" in gate


@pytest.mark.parametrize("zone", ["PMU1", "PMU2", "PMU3"])
def test_the_master_plan_districts_stay_red_and_cite_the_commercial_line(zone: str) -> None:
    held = _held(zone)
    assert held.value is False
    assert not held.variants
    text = ProvenanceStore().quote(held.prov.quote)
    assert "Commercial zoning districts" in text
    assert "Type II application" in text
    assert "a master plan shall be required" in text


def test_the_prefabricated_exception_is_a_single_family_word() -> None:
    # 1102.01(B) exempts "prefabricated structures"; ZDO 202 defines one as
    # designed for use as a single-family dwelling, so a factory-built
    # four-unit building is outside the exception.
    from flats.provenance.store import ProvenanceStore

    store = ProvenanceStore()
    exception = store.quote("or/clackamas/_unincorporated/zdo.1102.txt#L21")
    assert "design review is not required for detached single-family dwellings" in exception
    assert "prefabricated structures" in exception
    definition = store.quote("or/clackamas/_unincorporated/zdo.202.definitions.txt#L421")
    assert definition.startswith("PREFABRICATED STRUCTURE:")
    assert "designed for use as a single-family dwelling" in definition


def test_a_refusal_by_the_table_still_quotes_the_table() -> None:
    # R-2.5's X is the table's own refusal, not design review's.
    assert _held("R2.5").prov.quote == "or/clackamas/_unincorporated/zdo.315.txt#L41,L43-L54,L295-L306"
