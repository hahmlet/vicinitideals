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

