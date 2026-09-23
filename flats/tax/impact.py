"""The three scenarios the tax-impact snapshot prices on one lot.

* **current** -- the lot as the roll holds it: its own AV and RMV.
* **new_house** -- the building (if any) demolished and one new single-family
  house built, no partition. Land MAV is what OAR 150-308-0120 leaves after a
  demolition, MAV x land RMV / total RMV, with the roll's AV standing in for
  MAV (they are equal whenever AV is below RMV, which is the ordinary
  Measure 50 case; a lot whose AV has reached RMV is flagged, since its MAV
  may be higher). The house adds its RMV x CPR (ORS 308.153).
* **pod** -- the lot partitioned into ``units`` fee-simple lots, one unit on
  each. Each new lot's land MAV is reset to its land RMV x CPR (ORS 308.156(5),
  OAR 150-308-0190(1)) and the unit adds its building RMV x CPR, so each lot's
  MAV is unit RMV x CPR. The old lot's MAV history does not carry over.

Every scenario reports year one and a ten-year cumulative with RMV and rates
held flat and AV growing 3% a year to its RMV cap -- illustrative, and
labelled so wherever it is shown.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Sequence

from flats.tax.oregon import (
    Bill,
    Levy,
    cumulative,
    demolished_mav,
    new_value_mav,
    partitioned_land_mav,
)

YEARS = 10
ZERO = Decimal("0.00")


@dataclass(frozen=True)
class Roll:
    """The assessor's values for one lot (RLIS LANDVAL/BLDGVAL/TOTALVAL/ASSESSVAL)."""

    land_value: Decimal
    building_value: Decimal
    total_value: Decimal
    assessed_value: Decimal


@dataclass(frozen=True)
class Outcome:
    """One scenario's figures on one lot (summed over the lots a pod makes)."""

    av: Decimal
    rmv: Decimal
    headline: Decimal  # permanent + urban renewal + bonds, after Measure 5
    local_option: Decimal
    city: Decimal  # the city's permanent + bond tax
    city_local_option: Decimal
    compression: Decimal
    ten_year: Decimal  # cumulative headline, illustrative
    ten_year_city: Decimal
    notes: list[str] = field(default_factory=list)

    @property
    def total(self) -> Decimal:
        return self.headline + self.local_option


def _outcome(bills: Sequence[Bill], city: str, count: int, notes: list[str]) -> Outcome:
    y1 = bills[0]
    n = Decimal(count)
    return Outcome(
        av=y1.av * n,
        rmv=y1.rmv * n,
        headline=y1.headline * n,
        local_option=y1.local_option * n,
        city=y1.district(city) * n,
        city_local_option=y1.district(city, local_option=True) * n,
        compression=y1.compression * n,
        ten_year=sum((b.headline for b in bills), ZERO) * n,
        ten_year_city=sum((b.district(city) for b in bills), ZERO) * n,
        notes=notes,
    )


def usable(roll: Roll) -> str | None:
    """Why the roll cannot be priced, or None."""
    if roll.total_value <= 0:
        return "no_rmv"
    if roll.assessed_value <= 0:
        return "no_av"
    if roll.land_value < 0 or roll.land_value > roll.total_value:
        return "land_value_outside_rmv"
    return None


def current(roll: Roll, levies: Sequence[Levy], city: str, years: int = YEARS) -> Outcome:
    notes = []
    if roll.assessed_value >= roll.total_value:
        notes.append("av_at_rmv_mav_unknown")
    mav = roll.assessed_value
    return _outcome(cumulative(mav, roll.total_value, levies, years), city, 1, notes)


def new_house(
    roll: Roll, levies: Sequence[Levy], city: str, cpr: Decimal, house_rmv: Decimal, years: int = YEARS
) -> Outcome:
    notes = []
    if roll.building_value > 0:
        land_mav = demolished_mav(roll.assessed_value, roll.land_value, roll.total_value)
        notes.append("land_mav_prorated_from_av")
        if roll.assessed_value >= roll.total_value:
            notes.append("av_at_rmv_mav_unknown")
    else:
        land_mav = roll.assessed_value  # vacant: the whole MAV is the land's
    mav = land_mav + new_value_mav(house_rmv, cpr)
    rmv = roll.land_value + house_rmv
    return _outcome(cumulative(mav, rmv, levies, years), city, 1, notes)


def pod(
    roll: Roll,
    levies: Sequence[Levy],
    city: str,
    cpr: Decimal,
    unit_rmv: Decimal,
    units: int = 4,
    years: int = YEARS,
) -> Outcome:
    # Back-tested 2026-09-23 on real Gresham partitions (PortlandMaps
    # assessor history, 2019-2025): where the new lots and their houses land
    # on the same roll, AV = unit RMV x that year's CPR to the $10 (6 of 6);
    # a house finished a year or two after the reset lands within ~3%. Two
    # ways a real pod departs from this: a lot that KEEPS an existing house
    # does not reset (it carries the parent's MAV), and the ratio is the one
    # of the year the pod reaches the roll, not this year's.
    notes = []
    land_share = roll.land_value / units
    if unit_rmv < land_share:
        notes.append("unit_value_below_land_share")
    building = max(unit_rmv - land_share, Decimal("0"))
    mav = partitioned_land_mav(land_share, cpr) + new_value_mav(building, cpr)
    rmv = max(unit_rmv, land_share)
    return _outcome(cumulative(mav, rmv, levies, years), city, units, notes)
