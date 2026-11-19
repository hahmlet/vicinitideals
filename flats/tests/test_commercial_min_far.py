"""Minimum floor area ratio as printed in Beaverton's Table 20.20.15 and
Hillsboro's Table 12.24.460-1 (FOLLOWUPS 203).

A pod on a lot too big for its floor area to reach the minimum is never
GREEN: YELLOW with FAR-MIN where more pods could reach it (rulings.yaml
2026-11-04), RED only where they cannot fit.
"""

from __future__ import annotations

import pytest

from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.score.flags import Colour
from flats.score.screen import CLOSER_LOOK_MIN_FAR, LotFacts
from flats.tests.test_screen import DESIGN, NO_RELIEF, run, rules

pytestmark = pytest.mark.unit

BEAVERTON = "or/washington/beaverton"
HILLSBORO = "or/washington/hillsboro"
FLOOR_SQFT = DESIGN.ground_sqft * DESIGN.stories


@pytest.fixture(scope="module")
def corpus() -> RuleSet:
    return RuleSet(load_rules(strict=True))


@pytest.mark.parametrize(
    ("zone", "far"),
    [("RC-E", 0.30), ("TC-MU", 0.50), ("TC-HDR", 0.30), ("SC-MU", 0.40), ("SC-HDR", 0.40), ("SC-S", 0.60)],
)
def test_beaverton_table_20_20_15_minimum_far(corpus: RuleSet, zone: str, far: float) -> None:
    got = corpus.resolve(BEAVERTON, zone, ())
    assert got.get("min_far") == pytest.approx(far)


def test_hillsboro_scr_v_minimum_far_by_station_distance(corpus: RuleSet) -> None:
    field = corpus.layers[HILLSBORO].zones["SCR-V"].values["min_far"]
    assert field.value == pytest.approx(0.5)
    (far,) = [v for v in field.variants if getattr(v, "band", None) is not None]
    assert far.value == pytest.approx(0.4)


@pytest.mark.parametrize("far", [0.4, 0.5])
def test_a_big_lot_below_the_minimum_is_yellow_not_green(far: float) -> None:
    # A lot one pod cannot fill to the minimum, with room for more pods.
    lot_sqft = 2 * FLOOR_SQFT / far
    lot = LotFacts(lot_sqft=lot_sqft, frontage_ft=150, lot_width_ft=150, buildable_area_sqft=lot_sqft / 2)
    got = run(rules(min_far=far), lot=lot, relief=NO_RELIEF)
    assert got.colour is Colour.yellow
    assert got.binds == ()
    assert CLOSER_LOOK_MIN_FAR in got.reasons
    assert "FAR-MIN" in {f.code for f in got.flags}
