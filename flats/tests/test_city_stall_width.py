"""Court stall widths follow a jurisdiction's stated minimum."""

from __future__ import annotations

import pytest

from flats.designs.model import Design, StallBands
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.score.paper import court_across

pytestmark = pytest.mark.unit

CANBY = "or/clackamas/canby"
ESTACADA = "or/clackamas/estacada"
GLADSTONE = "or/clackamas/gladstone"
LAKE_OSWEGO = "or/clackamas/lake-oswego"


def _design(*, units: int = 4, stalls_per_unit: float = 1) -> Design:
    return Design(
        id="stall-width-test",
        version=1,
        label="Stall width test",
        typology="townhome_rear_court",
        footprint={"width_ft": 56, "depth_ft": 36},
        units=units,
        stories=2,
        height_ft=26,
        parking={
            "stalls_per_unit": StallBands.one(stalls_per_unit),
            "config": "rear_court",
        },
        delivery={"method": "panelized"},
    )


@pytest.fixture(scope="module")
def ruleset() -> RuleSet:
    return RuleSet(load_rules())


def test_canby_four_stall_court_uses_its_stated_width(ruleset: RuleSet) -> None:
    zone = ruleset.resolve(CANBY, "R-2")
    across = court_across(_design(units=2), zone)

    assert across.stalls == 4
    assert across.turn_shape.stall_w_ft == 8.5
    assert across.width_ft == 4 * (8.5 + across.fix.stall_ft) + across.dead_end_ft
    assert across.turns is not None


def test_estacada_four_stall_court_uses_eight_foot_stalls(ruleset: RuleSet) -> None:
    zone = ruleset.resolve(ESTACADA, "R-3")
    across = court_across(_design(units=2, stalls_per_unit=2), zone)

    assert across.stalls == 4
    assert across.turn_shape.stall_w_ft == 8
    assert across.turns is not None


def test_a_stated_width_above_the_design_width_wins(ruleset: RuleSet) -> None:
    zone = ruleset.resolve(GLADSTONE, "R5")
    across = court_across(_design(), zone, turning=False)

    assert across.stall_ft == 9.5
    assert across.width_ft == across.stalls * 9.5


def test_an_unstated_width_uses_the_design_width(ruleset: RuleSet) -> None:
    zone = ruleset.resolve(LAKE_OSWEGO, "R-0")
    across = court_across(_design(), zone, turning=False)

    assert across.stall_ft == 9.0
    assert across.width_ft == across.stalls * 9.0
