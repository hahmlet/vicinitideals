"""PRICE layer: what an old basement under the pod would cost (FD6 section 5.8; FD7).

A **conditional** cost -- "if this building had a basement" -- kept OUT of every
method's main total, plus a third figure weighted by how likely a basement is for
the lot's year built. Per old building (one FD7 case each), from the measured
stretches (:mod:`flats.foundation.oldbuild`):

* **B** (FD7_infill_cases.py ``remedies()``): bridge the gap with the wall when
  the longest stretch is within reach (``bridge_corner_ft`` when any stretch
  reaches a pod corner, else ``bridge_run_ft``) -- heavier bars through the gap
  and past it, and a widened footing beside it; otherwise take the wall down to
  the old basement floor over every stretch.
* **A** (``remedies()`` "SLAB"): everything under the floor over the old outline
  rebuilt in tested rock to the old floor, hauled in, and a soils visit.
* **B+P** is not priced: the piles would carry the wall past the backfill (a
  simplification, stated on every result).

The depth of old backfill under the new footing is ``basement_floor_ft`` less
the lot's own footing depth (:func:`flats.foundation.model.embed_of`), so the
frost register moves it.

Every figure is materials and unavoidable hired services, low and high apart,
as section 6.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from flats.foundation import cost as costing
from flats.foundation.measure import Measured, OldBuilding
from flats.foundation.settings import Settings

FT3_PER_YD3 = 27.0

BRIDGE, DEEPEN, NO_WALL = "bridge", "deepen", "no wall over it"
NOT_HELD = "not held"

SIMPLIFICATIONS = (
    "Two scenarios (FD8 2c): no basement (the method totals) and has basement (the totals plus this cost), beside the likelihood of a basement for the lot's year built; the likelihood-weighted figure is kept for the record and never shown as a cost.",
    "Each old building is one FD7 case: one reach for the whole building (the corner overhang when any stretch reaches a pod corner), its longest stretch against it.",
    "B+P is not priced: the screw piles would carry the wall past the backfill.",
    "Outlines under basement_min_sf (400 sq ft) are left out: a shed or a detached garage has no basement (FD8 2c).",
)


@dataclass(frozen=True, slots=True)
class Exposure:
    """One FD7 case: the inputs ``remedies()`` takes."""

    wall_ft: float
    floor_sf: float
    corner: bool
    longest_ft: float

    @classmethod
    def of(cls, b: OldBuilding) -> Exposure:
        return cls(b.wall_ft, b.floor_sf, b.corner, b.longest_ft)


@dataclass(frozen=True)
class BuildingCost:
    bldg_id: str | None
    exposure: Exposure
    #: "bridge", "deepen", or "no wall over it".
    b_remedy: str
    b: costing.Cost
    a: costing.Cost


@dataclass(frozen=True)
class Infill:
    """Every old building under one pod, priced conditionally."""

    buildings: tuple[BuildingCost, ...]
    year_built: int | None
    year_band: str
    basement_share: float
    embed_in: float
    backfill_ft: float
    held: bool

    @property
    def any(self) -> bool:
        return bool(self.buildings)

    @property
    def wall_crossed(self) -> bool:
        return any(bc.exposure.wall_ft > 0 for bc in self.buildings)

    @property
    def longest_ft(self) -> float:
        return max((bc.exposure.longest_ft for bc in self.buildings), default=0.0)

    @property
    def wall_ft(self) -> float:
        return sum(bc.exposure.wall_ft for bc in self.buildings)

    @property
    def floor_sf(self) -> float:
        return sum(bc.exposure.floor_sf for bc in self.buildings)

    def total(self, method: str, prices: str) -> Decimal:
        """Conditional total for ``method`` ("B" or "A") at "low" or "high" prices."""
        return sum((getattr(getattr(bc, method.lower()), prices) for bc in self.buildings), Decimal(0))

    def weighted(self, method: str, prices: str) -> Decimal:
        return self.total(method, prices) * Decimal(str(self.basement_share))


def year_band(year: int | None, s: Settings) -> str:
    """FD5's year bands (fd5.year_band): before 1940, 1940-1959, 1960 on, not held."""
    if year is None or year <= 0:
        return NOT_HELD
    if year < s.year_band_1:
        return f"before {s.year_band_1}"
    if year < s.year_band_2:
        return f"{s.year_band_1}-{s.year_band_2 - 1}"
    return f"{s.year_band_2} on"


def basement_share(year: int | None, s: Settings) -> float:
    if year is None or year <= 0:
        return s.share_not_held
    if year < s.year_band_1:
        return s.share_before_1940
    if year < s.year_band_2:
        return s.share_1940_1959
    return s.share_1960_on


def _yd3(ft3: float) -> float:
    return ft3 / FT3_PER_YD3


def b_cost(e: Exposure, s: Settings, embed_in: float) -> tuple[str, costing.Cost]:
    """FD7 remedies 1 and 2 for B: bridge when the longest stretch is in reach, else deepen."""
    p = s.prices
    if e.wall_ft <= 0:
        return NO_WALL, costing.Cost(())
    reach = s.bridge_corner_ft if e.corner else s.bridge_run_ft
    if e.longest_ft <= reach + s.tolerance_in / 12:
        bars = s.bridge_bars * (e.wall_ft + s.bridge_past_ft) * s.bridge_bar_lb_per_ft * s.lap
        pad = _yd3(s.bridge_pad_extra_w_ft * s.footing_t_in / 12 * s.bridge_pad_len_ft * (1 if e.corner else 2)) * s.concrete_waste
        return BRIDGE, costing.Cost(
            (
                costing.priced("bridging bars", bars, p["bar_lb"]),
                costing.priced("widened footing beside the gap", pad, p["concrete_yd3"]),
            )
        )
    d = s.basement_floor_ft - embed_in / 12
    conc = _yd3(s.deep_stem_in / 12 * d * e.wall_ft) * s.concrete_waste
    forms = 2 * d * e.wall_ft
    bars = (s.level_bars_base * e.wall_ft * s.lap + e.wall_ft / s.vert_bar_spacing_ft * d) * s.bar_lb_per_ft
    return DEEPEN, costing.Cost(
        (
            costing.priced("concrete, wall to the old floor", conc, p["concrete_yd3"]),
            costing.priced("forms, wall to the old floor", forms, p["form_sf"]),
            costing.priced("bars, wall to the old floor", bars, p["bar_lb"]),
        )
    )


def a_cost(e: Exposure, s: Settings) -> costing.Cost:
    """FD7 remedy 6 for A: tested rock under the whole patch, to the old floor."""
    p = s.prices
    if e.floor_sf <= 0:
        return costing.Cost(())
    vol = _yd3(e.floor_sf * s.basement_floor_ft)
    return costing.Cost(
        (
            costing.priced("tested rock under the patch", vol * s.rock_ton_per_yd3, p["rock_ton"]),
            costing.priced("haul, rock under the patch", vol, p["haul_yd3"]),
            costing.priced("soils visit", 1, p["fill_testing"]),
        )
    )


def assess(m: Measured, s: Settings, embed_in: float) -> Infill:
    """Every old building under the pod, priced conditionally, and the weighted figure."""
    out = []
    for b in m.old_buildings:
        if b.area_sf < s.basement_min_sf:
            continue  # FD8 2c: a shed or a detached garage has no basement
        e = Exposure.of(b)
        remedy, bc = b_cost(e, s, embed_in)
        out.append(BuildingCost(b.bldg_id, e, remedy, bc, a_cost(e, s)))
    return Infill(
        buildings=tuple(out),
        year_built=m.year_built,
        year_band=year_band(m.year_built, s),
        basement_share=basement_share(m.year_built, s),
        embed_in=embed_in,
        backfill_ft=s.basement_floor_ft - embed_in / 12,
        held=m.old_buildings_held,
    )
