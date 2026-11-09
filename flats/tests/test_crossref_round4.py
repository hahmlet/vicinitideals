"""FOLLOWUPS 105 round 4 (2026-11-09): references followed to their targets.

* Washington County, the four districts the pod uses off the Middle Housing
  path (R-9 NB, R-24 NB, NMU, CCMU). Their parking reaches Section 413 (390-7,
  392-9.7 A), and 413-4.10 sends every parking lot to 407-6, whose 407-6.4 is
  the 5-foot strip the Middle Housing districts already carry.
* The same four are under Section 411 (411-1.3 exempts Middle Housing only).
  The 411-5 matrix names no North Bethany district, so R-9 NB and R-24 NB fall
  to its Other row, "to be determined by review authority": their side and
  rear yards are qualified by ``washington_county_411_buffer``, unobserved.
* Section 409 is held: an improved alley of 1-8 units is paved at least 16 ft,
  and the alley flag now names the width.
* West Linn Chapters 42 (clear vision) and 28 (river protection) are held and
  read; neither is encoded (no vision-triangle mechanism; no Title 13 map over
  West Linn).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flats.rules.conditions import condition
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.score.flags import fact_code, load_registry

WASHCO = "or/washington/_unincorporated"
OFF_PATH = ("R-9 NB", "R-24 NB", "NMU", "CCMU")
NORTH_BETHANY = ("R-9 NB", "R-24 NB")
BUFFER = "washington_county_411_buffer"
DOCS = Path(__file__).resolve().parents[1] / "provenance" / "docs"


@pytest.fixture(scope="module")
def corpus() -> RuleSet:
    return RuleSet(load_rules(strict=True))


@pytest.mark.parametrize("zone", OFF_PATH)
def test_the_off_path_districts_carry_the_five_foot_strip(corpus: RuleSet, zone: str) -> None:
    assert corpus.resolve(WASHCO, zone, ()).get("parking_lot_line_buffer_ft") == 5


@pytest.mark.parametrize("zone", NORTH_BETHANY)
@pytest.mark.parametrize("field", ("setback_side_ft", "setback_rear_ft"))
def test_the_north_bethany_yards_wait_on_the_411_buffer(corpus: RuleSet, zone: str, field: str) -> None:
    value = corpus.layers[WASHCO].zones[zone].values[field]
    assert value.qualified_by == BUFFER
    assert BUFFER in corpus.resolve(WASHCO, zone, ()).levers


def test_the_411_buffer_is_unobserved_and_flagged_at_the_yellow_line() -> None:
    fact = condition(BUFFER)
    assert fact.kind == "site_fact" and fact.assume is None
    entry = load_registry()[fact_code(BUFFER)]
    assert entry.severity >= 5


def test_the_middle_housing_districts_do_not_wait_on_it(corpus: RuleSet) -> None:
    for zone in ("R-5", "R-9", "R-24", "TO:R9-12"):
        assert BUFFER not in corpus.resolve(WASHCO, zone, ()).levers


def test_the_alley_flag_names_the_sixteen_feet() -> None:
    entry = load_registry()["ALLEY-IMPROVEMENT-UNCONFIRMED"]
    assert "16 ft" in entry.description
    text = (DOCS / WASHCO / "cdc.409.private-streets.txt").read_text(encoding="utf-8").splitlines()
    assert text[110].startswith("(10) 1-8 units 16 ft.")


@pytest.mark.parametrize(
    "path",
    (
        "or/washington/_unincorporated/cdc.409.private-streets.txt",
        "or/clackamas/west-linn/42.clear-vision.txt",
        "or/clackamas/west-linn/28.river-protection.txt",
    ),
)
def test_the_fetched_chapters_are_stored_with_their_hash(path: str) -> None:
    meta = json.loads((DOCS / (path + ".meta.json")).read_text(encoding="utf-8"))
    assert meta["retrieved"] == "2026-11-09"
    assert len(meta["sha256"]) == 64
