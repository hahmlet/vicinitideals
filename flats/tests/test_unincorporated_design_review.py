"""Clackamas districts that need design review are RED, not green (Steph 2026-10-09).

ZDO 1102.01(A) requires design review for development in HDR, MR-1, MR-2, PMD
and VA, and a quadplex is none of the listed exceptions. The by-right-only
ruling (2026-10-08) makes those districts red, although Table 315-1 prints a
bare P for the use. 163 MR-1/MR-2 lots were green on the live map before this.
"""

from __future__ import annotations

import pytest

from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

LAYER = "or/clackamas/_unincorporated"


@pytest.mark.parametrize("zone", ["HDR", "MR1", "MR2", "PMD", "VA"])
def test_design_review_districts_refuse_the_pod_outright(zone: str) -> None:
    use = RuleSet(load_rules()).resolve(LAYER, zone).values["quadplex_allowed"]
    assert use.value is False
    assert use.levers == frozenset()


def test_the_districts_that_stay_by_right_are_untouched() -> None:
    # R-5 permits the quadplex and 1102.01(A) does not name it.
    use = RuleSet(load_rules()).resolve(LAYER, "R5").values["quadplex_allowed"]
    assert use.value is True



# --- the citation (FOLLOWUPS 52, Section 1102 stored 2026-10-09) --------------


def _held(zone: str):
    return load_rules()[LAYER].zones[zone].values["quadplex_allowed"]


@pytest.mark.parametrize("zone", ["HDR", "MR1", "MR2", "PMD", "VA"])
def test_the_refusal_cites_the_design_review_sentence_not_the_use_table(zone: str) -> None:
    # The use table says P; the red is the ruling's, so the value quotes
    # 1102.01(A), which names the district, and 1102.03, the Type II process.
    from flats.provenance.store import ProvenanceStore

    quote = _held(zone).prov.quote
    assert quote.startswith("or/clackamas/_unincorporated/zdo.1102.txt#")
    text = ProvenanceStore().quote(quote)
    assert "Design review is required for" in text
    assert "HDR, MR-1, MR-2, MRR, PMD, RCHDR, SHD, VA, and VTH Districts" in text
    assert "Type II application" in text


@pytest.mark.parametrize("zone", ["SCMU", "PMU1", "PMU2", "PMU3"])
def test_the_commercial_refusals_cite_the_commercial_line(zone: str) -> None:
    from flats.provenance.store import ProvenanceStore

    text = ProvenanceStore().quote(_held(zone).prov.quote)
    assert "Commercial zoning districts" in text
    assert "Type II application" in text


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
