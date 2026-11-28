"""Gresham's floor area ratio in LDR-5, LDR-7 and TR (FOLLOWUPS 222).

Table 4.0130 row J prints 1.0 / 0.7 / 1.0 for single detached, duplex,
triplex and quadplex in the LDR-5, LDR-7 and TR columns, NA for every other
use (the townhouse among them) and NA in the other four columns. Until
2026-11-27 only OFR cited the row (as its NA), and the LDR-7 note said the
ratio "does not bind this pod" because of the 7,000 sq ft minimum lot. But
note 2 lets every existing taxlot under the minimum be built on
(lot_of_record_relief), so the ratio is what binds on a small lot: the pod's
4,032 sq ft of floor over a 5,000 sq ft LDR-7 lot is 0.81.
"""

from __future__ import annotations

import pytest

from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.score.screen import LotFacts, Triage, screen
from flats.tests.test_screen import DESIGN, POLICY, fit, rules

pytestmark = pytest.mark.unit

GRESHAM = "or/multnomah/gresham"
ROW_J = {"LDR-5": 1.0, "LDR-7": 0.7, "TR": 1.0}


@pytest.fixture(scope="module")
def rule_set() -> RuleSet:
    return RuleSet(load_rules())


@pytest.mark.parametrize(("zone", "ratio"), sorted(ROW_J.items()))
def test_row_j_resolves_in_its_three_columns(rule_set: RuleSet, zone: str, ratio: float) -> None:
    got = rule_set.resolve(GRESHAM, zone).values["max_far"]
    assert got.value == ratio
    assert "4.0130.txt#L9,L106-L109" in got.prov.quote


@pytest.mark.parametrize("zone", sorted(ROW_J))
def test_the_townhouse_split_is_all_other_uses_na(rule_set: RuleSet, zone: str) -> None:
    got = rule_set.resolve(GRESHAM, zone, ("unit_lots",))
    assert "max_far" not in got.values
    assert "max_far" in got.exempted


def test_ldr7_ratio_binds_on_a_small_lot_of_record(rule_set: RuleSet) -> None:
    ratio = rule_set.resolve(GRESHAM, "LDR-7").values["max_far"].value
    small = LotFacts(lot_sqft=5_000, frontage_ft=60, lot_width_ft=60)
    roomy = LotFacts(lot_sqft=7_000, frontage_ft=70, lot_width_ft=70)

    def run(lot: LotFacts):
        return screen(rules(max_far=ratio), lot, DESIGN, fit(), policy=POLICY)

    over = run(small)
    assert over.triage is not Triage.green
    assert any(c.check == "far" for c in over.checks)
    assert run(roomy).triage is Triage.green
