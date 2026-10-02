"""What a city takes off a lot before it divides by the acre.

Ten Oregon codes state a density or a floor area ratio per *net* acre, and no
two of them subtract the same list (FOLLOWUPS 30). Until 2026-10-02 the
screen held only the lot's own area, which is a bound on net area and nothing
more: it settled a floor that clears and a ceiling that is exceeded, and held
every other lot as a question nobody could answer -- ~36,500 of them.

Steph's ruling (option A, 2026-10-02): an ordinary existing lot dedicates
nothing and sets nothing aside, so its net area is the lot less what each
city's own list subtracts *and something here measures* -- floodplain and the
mapped resource overlays. What the list names and nothing measures (slopes
over a threshold, landslide areas, trees, stormwater facilities) is assumed
absent, and the rule file says so by name.

Two lists per value, because a list can be read with certainty or not:

* ``less`` -- the city's sentence subtracts this ground, and the layer that
  measures it is the city's own map (or one the city adopts).
* ``may_less`` -- subtracted on one reading and not on another, or measured
  only by a regional stand-in for the map the code names (Metro's Title 3
  and Title 13 layers in Washington County).

Nothing says how the measured areas overlap one another, so net area is a
range, not a number: the most it can be is the lot less the single largest
certain deduction (the overlaps all coincide), and the least is the lot less
every deduction on both lists added up (nothing overlaps). A standard that
gives the same verdict at both ends is settled; one that does not is still a
question, held exactly as before. The range is honest about the one thing the
per-overlay areas cannot say.
"""

from __future__ import annotations

from typing import Mapping

from pydantic import BaseModel, ConfigDict

#: The pod's own driveway -- the lane in from the street and the aisle, not
#: the stalls (:func:`flats.score.paper.paved` with ``stalls=False``).
#: Beaverton and Cornelius subtract "areas used for private streets and
#: common driveways", and neither code defines a common driveway, so the
#: pod's drive is one (Steph, 2026-10-02).
DRIVE_AISLE = "drive_aisle"

#: FEMA's 100-year floodplain, floodway and fringe together. quadfit splits
#: the layer in two (``fema_floodway`` carved, ``fema_sfha`` -- the fringe,
#: floodway excluded -- flagged), and the two are disjoint by construction
#: (s0_acquire ``derive_fema_split``), so their sum is the floodplain exactly.
FLOODPLAIN = "floodplain"
FLOODWAY = "fema_floodway"

#: Every deduction a rule file may name that something here measures, and the
#: s5o columns (``ovl_<key>_sqft``) whose sum is its area on the lot. An
#: overlay is measured only on the lots of the jurisdictions quadfit's
#: overlays.yaml lists for it, and is zero -- not missing -- everywhere else,
#: so a layer naming an overlay its city is not covered by would read "none
#: here" off a map that was never laid over it. ``test_net_area`` holds every
#: layer to that.
MEASURED: dict[str, tuple[str, ...]] = {
    FLOODPLAIN: ("ovl_fema_sfha_sqft", "ovl_fema_floodway_sqft"),
    FLOODWAY: ("ovl_fema_floodway_sqft",),
    **{
        key: (f"ovl_{key}_sqft",)
        for key in (
            "gresham_hcra",
            "gresham_wetlands",
            "gresham_hillside",
            "troutdale_veco",
            "metro_wetlands",
            "washington_cws_corridor",
            "washington_habitat",
            "west_linn_wra_stream",
            "west_linn_wra_ephemeral",
            "west_linn_wra_piped",
            "west_linn_rci",
            "west_linn_wetlands",
            "west_linn_flood",
            "happy_valley_nroz",
            "happy_valley_slope",
            "oregon_city_nrod",
            "milwaukie_hca",
            "milwaukie_wqr",
            "milwaukie_wetlands",
        )
    },
}

#: Every name ``less`` and ``may_less`` accept.
DEDUCTIONS: frozenset[str] = frozenset({*MEASURED, DRIVE_AISLE})

#: Floor below which a net area is treated as no land at all: a rate on it is
#: unbounded, so a ceiling fails and a floor clears.
_NO_LAND_SQFT = 1.0


class NetArea(BaseModel):
    """One city's subtraction list, as far as this project can measure it."""

    model_config = ConfigDict(frozen=True)

    less: tuple[str, ...] = ()
    may_less: tuple[str, ...] = ()
    #: What the list names that nothing measures, in the code's own words,
    #: assumed absent on an ordinary existing lot (Steph, option A).
    assumed_none: tuple[str, ...] = ()


def measured_deductions(row: Mapping[str, object]) -> dict[str, float]:
    """Per measured deduction, its square feet on this lot, from an s5o row.

    A deduction whose column the row does not carry is left out, so a rule
    naming it cannot settle anything on this lot -- a missing measurement is
    never read as "none here".
    """
    out: dict[str, float] = {}
    for key, columns in MEASURED.items():
        total = 0.0
        for column in columns:
            raw = row.get(column)
            if raw is None:
                break
            try:
                value = float(raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                break
            if value != value:  # NaN
                break
            total += max(value, 0.0)
        else:
            out[key] = total
    return out


def net_span(
    net: NetArea,
    gross_sqft: float,
    measured: Mapping[str, float] | None,
    drive_aisle_sqft: float | None = None,
) -> tuple[float, float] | None:
    """The least and the most this lot's net area can be, in square feet.

    None where a deduction the list names was not measured on this lot: the
    caller falls back to the gross-area bound.
    """
    if measured is None:
        return None
    have = dict(measured)
    if drive_aisle_sqft is not None:
        have[DRIVE_AISLE] = drive_aisle_sqft
    if any(key not in have for key in (*net.less, *net.may_less)):
        return None
    # A layer's polygons can overlap one another, and s5o sums each
    # intersection, so one overlay can report more than the lot.
    sure = [min(have[key], gross_sqft) for key in net.less]
    maybe = [min(have[key], gross_sqft) for key in net.may_less]
    most = gross_sqft - max(sure, default=0.0)
    least = gross_sqft - min(gross_sqft, sum(sure) + sum(maybe))
    return max(least, _NO_LAND_SQFT), max(most, _NO_LAND_SQFT)


__all__ = [
    "DEDUCTIONS",
    "DRIVE_AISLE",
    "FLOODPLAIN",
    "FLOODWAY",
    "MEASURED",
    "NetArea",
    "measured_deductions",
    "net_span",
]
