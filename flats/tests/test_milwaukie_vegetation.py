"""Milwaukie's minimum vegetation in R-MD and R-HD (FOLLOWUPS 222).

Table 19.301.4 row C.5 prints 15 / 25 / 25 / 30 percent across R-MD's four
lot-size columns, and Table 19.302.4 prints 15 for R-HD. Neither zone carried
the row until the 2026-11-27 completeness check, so a pod that left too
little of the lot unbuilt and unpaved was screened against nothing.

The 40 percent front-yard vegetation of 19.301.5.C / 19.302.5.D has no field;
it rides on `parking_front_yard_max_pct` (50), and the last test here fails if
that carrier is narrowed or loosened without a field taking its place.
"""

from __future__ import annotations

import pytest

from flats.rules.loader import load_rules
from flats.rules.model import Layer

pytestmark = pytest.mark.unit

MILWAUKIE = "or/clackamas/milwaukie"


@pytest.fixture(scope="module")
def milwaukie() -> Layer:
    return load_rules()[MILWAUKIE]


@pytest.mark.parametrize(
    ("lot_sqft", "pct"),
    [
        (1500, 15),
        (2999, 15),
        (3000, 25),
        (4999, 25),
        (5000, 25),
        (6999, 25),
        (7000, 30),
        (12000, 30),
    ],
)
def test_r_md_vegetation_follows_the_lot_size_column(
    milwaukie: Layer, lot_sqft: int, pct: int
) -> None:
    held = milwaukie.zones["R-MD"].values["min_landscaped_pct"]
    assert held.under(lot={"lot_sqft": lot_sqft}).value == pct


def test_r_md_vegetation_with_no_lot_area_is_not_the_last_column(
    milwaukie: Layer,
) -> None:
    held = milwaukie.zones["R-MD"].values["min_landscaped_pct"].under()
    assert held.ambiguous


def test_r_hd_vegetation_is_fifteen(milwaukie: Layer) -> None:
    assert milwaukie.zones["R-HD"].values["min_landscaped_pct"].value == 15


def test_front_yard_vegetation_is_carried_by_the_vehicle_share(
    milwaukie: Layer,
) -> None:
    """40 percent vegetated is at most 60 percent vehicle area; the 50
    percent cap is the stricter of the two on the same front yard, in both
    zones and on both the one-lot and unit-lot paths."""
    carrier = milwaukie.defaults["parking_front_yard_max_pct"]
    assert carrier.value <= 100 - 40
    assert not carrier.unless
    assert not carrier.variants
    for zone in ("R-MD", "R-HD"):
        assert "parking_front_yard_max_pct" not in milwaukie.zones[zone].values
