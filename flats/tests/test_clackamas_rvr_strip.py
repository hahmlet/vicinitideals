"""Clackamas ZDO Table 1001-1: no Section 1009 strip for middle housing in
the R-5 to R-30 and VR districts (fg4-fixes, 2026-11-10; rel7 reader D's
risk note 4a, Eldorado 22E08AC02500).

1001.03 applies Section 1000 "as identified in Table 1001-1". The table's
row "Middle housing in the R-5, R-7, R-8.5, R-10, R-15, R-20, R-30, VR-4/5,
and VR-5/7 Districts" leaves the 1009 Landscaping column blank, where the
row for middle housing in all other zoning districts ticks it. So the
layer's five-foot 1009.03(B)(1) strip is held exempt in those nine
districts on both paths and kept everywhere else.

The table's cells are tick marks placed by column, so the stored text keeps
the PDF's layout and these tests read each tick by its column position.
"""

from __future__ import annotations

import pytest

from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.tests.test_frontage_caps import DOCS, quoted

pytestmark = pytest.mark.unit

CLACKAMAS = "or/clackamas/_unincorporated"
FIELD = "parking_lot_line_buffer_ft"
R_AND_VR = ("R5", "R7", "R8.5", "R10", "R15", "R20", "R30", "VR45", "VR57")
TABLE = DOCS / "or/clackamas/_unincorporated/zdo.1001.txt"
FORMS = ((), ("unit_lots",))


@pytest.fixture(scope="module")
def corpus() -> RuleSet:
    return RuleSet(load_rules(strict=True))


def _line(n: int) -> str:
    return TABLE.read_text(encoding="utf-8").splitlines()[n - 1]


def _ticks(n: int) -> set[str]:
    """The Section 1000 columns a table row ticks, read off the L94 header."""
    header = _line(94)
    cols = {h: header.index(h) for h in ("1005", "1006", "1007", "1009", "1015", "1017")}
    cols["1010"] = _line(95).index("1010")
    row = _line(n)
    hits = [i for i, c in enumerate(row) if c == "✓"]
    return {s for s, at in cols.items() if any(at - 2 <= i <= at + 4 for i in hits)}


def test_the_table_leaves_1009_blank_for_r_and_vr_middle_housing() -> None:
    assert _line(99).startswith("Middle housing in the R-5, R-7, R-8.5, R-10, R-15, R-20, R-30")
    assert "VR-4/5, and VR-5/7 Districts" in _line(99)
    assert _line(103).startswith("Quadplexes and")
    # Quadplexes and townhouses: 1006 and 1010 ticked, 1005 and 1009 blank.
    for row in (101, 104):
        assert _ticks(row) == {"1006", "1010"}, row
    # All other zoning districts: 1005 and 1009 both ticked.
    assert _line(109) == "Middle housing in all other zoning districts"
    assert {"1005", "1009", "1010"} <= _ticks(120)
    assert "Section 1000 applies to all development, as identified in Table 1001-1" in quoted(
        "or/clackamas/_unincorporated/zdo.1001.txt#L31-L32"
    )


@pytest.mark.parametrize("zone", R_AND_VR)
@pytest.mark.parametrize("form", FORMS)
def test_the_r_and_vr_districts_hold_no_strip(corpus: RuleSet, zone: str, form: tuple) -> None:
    got = corpus.resolve(CLACKAMAS, zone, conditions=form).values
    assert FIELD not in got


@pytest.mark.parametrize(("zone", "width"), [("R2.5", 5), ("HDR", 5), ("PMD", 5), ("C3", 5), ("VA", 10)])
@pytest.mark.parametrize("form", FORMS)
def test_every_other_district_keeps_it(corpus: RuleSet, zone: str, width: int, form: tuple) -> None:
    got = corpus.resolve(CLACKAMAS, zone, conditions=form).values
    assert got[FIELD].value == width
