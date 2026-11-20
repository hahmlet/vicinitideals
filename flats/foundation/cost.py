"""Cost, low and high, line by line (FD6 section 6).

Materials, plus hired services only where they cannot be avoided [Steph]. No
labour of our own crew, no waiting, no financing. Low and high are carried
separately all the way through and never averaged.

Quantities arrive as floats from :mod:`flats.foundation.model`; each line is
priced in :class:`~decimal.Decimal` (the repo's money convention): the float
quantity is taken exactly (``Decimal(float)``) and multiplied by the price as
written in ``flats/config/foundation.yaml``. Lines are kept unrounded; a total
is the exact sum of its lines, rounded only for display (:func:`dollars`).

The lines that do not follow the ground come from the FD3 flat-lot takeoff
(:func:`flat_lot`), rebuilt here from the ``flat_lot`` settings so that the
section 6 table (concrete 48.1 cu yd, $7,698-10,585 ...) is derived, not typed.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from functools import lru_cache

from flats.foundation.settings import Price, Settings

FT3_PER_YD3 = 27.0


def _yd3(ft3: float) -> float:
    return ft3 / FT3_PER_YD3


def _sqft(width_in: float, depth_in: float) -> float:
    return width_in * depth_in / 144.0


@dataclass(frozen=True, slots=True)
class CostLine:
    name: str
    quantity: float
    unit: str
    low: Decimal
    high: Decimal


@dataclass(frozen=True)
class Cost:
    lines: tuple[CostLine, ...]

    @property
    def low(self) -> Decimal:
        return sum((ln.low for ln in self.lines), Decimal(0))

    @property
    def high(self) -> Decimal:
        return sum((ln.high for ln in self.lines), Decimal(0))

    def line(self, name: str) -> CostLine:
        for ln in self.lines:
            if ln.name == name:
                return ln
        raise KeyError(name)


def dollars(value: Decimal) -> int:
    """Whole dollars, for display (half to even, as Python's own rounding)."""
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def priced(name: str, quantity: float, price: Price) -> CostLine:
    q = Decimal(quantity)
    return CostLine(name, float(quantity), price.unit, q * price.low, q * price.high)


# ---------------------------------------------------------------- the flat-lot takeoff (FD3)


@dataclass(frozen=True, slots=True)
class FlatLot:
    """FD3's flat-lot quantities for one pod: the lines that do not follow the ground."""

    slab_concrete_net_yd3: float
    slab_concrete_yd3: float
    slab_level_bar_ft_net: float
    slab_bars_lb: float
    rock_dry_ton: float
    rock_wet_ton: float
    haul_dry_yd3: float
    haul_wet_yd3: float
    slab_membrane_sf: float
    edge_board_sf: float
    crawl_membrane_sf: float


@lru_cache(maxsize=16)
def flat_lot(s: Settings) -> FlatLot:
    """FD3_flat_lot_takeoff.py ``slab()`` and ``stem_wall()``, on the length
    ``fixed_length_ft`` (the framing; FD3 drew 80 ft 3-3/4 in, see the settings
    file) and the building width."""
    length, width = s.fixed_length_ft, s.width_ft
    perim = 2 * (length + width)
    area = length * width
    parties = len(s.party_x_ft)
    edge_ft3 = _sqft(s.edge_w_in, s.edge_d_in) * perim
    inner_l = length - 2 * s.edge_w_in / 12
    inner_w = width - 2 * s.edge_w_in / 12
    slab_ft3 = inner_l * inner_w * s.slab_t_in / 12
    party_ft3 = _sqft(s.party_strip_w_in, s.party_strip_d_in - s.slab_t_in) * parties * inner_w
    concrete_net = _yd3(edge_ft3 + slab_ft3 + party_ft3)
    base_in_dry = s.strip_soil_in + s.slab_top_in - s.slab_t_in - s.radon_layer_in
    base_dry = _yd3(inner_l * inner_w * base_in_dry / 12)
    base_wet = _yd3(inner_l * inner_w * (base_in_dry + s.wet_extra_base_in) / 12)
    radon_ton = _yd3(inner_l * inner_w * s.radon_layer_in / 12) * s.radon_rock_ton_per_yd3
    spoil = _yd3(
        area * s.strip_soil_in / 12
        + _sqft(s.edge_w_in + s.spoil_edge_extra_w_in, s.embed_in - s.strip_soil_in) * perim
    )
    bar_ft_net = s.slab_edge_bars * perim + s.slab_edge_bars * parties * inner_w
    dry_ton = base_dry * s.rock_ton_per_yd3
    wet_ton = base_wet * s.rock_ton_per_yd3
    return FlatLot(
        slab_concrete_net_yd3=concrete_net,
        slab_concrete_yd3=concrete_net * s.concrete_waste,
        slab_level_bar_ft_net=bar_ft_net,
        slab_bars_lb=bar_ft_net * s.lap * s.bar_lb_per_ft,
        rock_dry_ton=dry_ton + radon_ton,
        rock_wet_ton=wet_ton + radon_ton,
        haul_dry_yd3=spoil,
        haul_wet_yd3=spoil + (wet_ton - dry_ton) / s.rock_ton_per_yd3,
        slab_membrane_sf=area * s.slab_membrane_factor,
        edge_board_sf=perim * s.edge_board_sf_per_ft,
        crawl_membrane_sf=area * s.crawl_membrane_factor,
    )


# ---------------------------------------------------------------- steps and rails


def unit_door_cost(s: Settings, k: int, sides: int) -> tuple[Decimal, Decimal]:
    """FD8 2a: one door with a k-riser precast unit, low and high:
    (unit + installation + sides x railing) x (1 + markup). Delivery is not in it."""
    p = s.prices
    unit, rail, install = p[f"precast_unit_{k}"], p[f"precast_rail_{k}"], p["precast_install"]
    factor = Decimal(1) + Decimal(str(s.precast_markup))
    low = (unit.low + install.low + sides * rail.low) * factor
    high = (unit.high + install.high + sides * rail.high) * factor
    return low, high


def _steps(s: Settings, door_res, *, slab: bool) -> list[CostLine]:
    p = s.prices
    if s.steps_rule == "precast":
        # FD8 2a: a step pad where no unit is needed (k = 0), else one precast
        # unit with its railing. A door over the cap takes no price: the method
        # is not used on the lot (MethodResult.usable).
        pads = sum(1 for d in door_res if d.units == 0)
        low = high = Decimal(0)
        n = 0
        for d in door_res:
            if d.units and not d.over_cap:
                lo, hi = unit_door_cost(s, d.units, d.rail_sides)
                low, high, n = low + lo, high + hi, n + 1
        out = [priced("step pads", pads, p["step_pad"])]
        out.append(CostLine("precast steps and railings", float(n), "per door (FD8 2a; delivery not included)", low, high))
        return out
    rail = sum(d.rail_ft for d in door_res)
    out = []
    if slab:
        out.append(priced("step pads", len(door_res), p["step_pad"]))
        risers = sum(d.risers - 1 for d in door_res)  # every riser after the first
    else:
        risers = sum(d.risers for d in door_res)
    out.append(priced("steps", risers, p["riser"]))
    out.append(priced("rails", rail, p["rail_ft"]))
    return out


# ---------------------------------------------------------------- B and B+P


def raised_cost(
    s: Settings,
    *,
    concrete_yd3: float,
    bars_lb: float,
    form_sf: float,
    haul_yd3: float,
    door_res,
    piles: int = 0,
) -> Cost:
    p = s.prices
    flat = flat_lot(s)
    lines = [
        priced("concrete", concrete_yd3, p["concrete_yd3"]),
        priced("pump", 1, p["pump"]),
        priced("bars", bars_lb, p["bar_lb"]),
        priced("forms", form_sf, p["form_sf"]),
        priced("haul", haul_yd3, p["haul_yd3"]),
        priced("ground sheet", flat.crawl_membrane_sf, p["crawl_membrane_sf"]),
        priced("crawlspace vents", s.vents, p["vent"]),
        priced("12 floor cassettes", 1, p["cassettes_12"]),
    ]
    if piles:
        lines.append(priced("screw piles", piles, p["pile"]))
    lines += _steps(s, door_res, slab=False)
    return Cost(tuple(lines))


# ---------------------------------------------------------------- A


def slab_cost(
    s: Settings,
    *,
    wet: bool,
    fill_ton: float,
    conc_extra_yd3: float,
    extra_bars_lb: float,
    form_sf: float,
    door_res,
) -> Cost:
    p = s.prices
    flat = flat_lot(s)
    lines = [
        priced("concrete, flat lot", flat.slab_concrete_yd3, p["concrete_yd3"]),
        priced("pump", 1, p["pump"]),
        priced("bars, flat lot", flat.slab_bars_lb, p["bar_lb"]),
        priced("rock under the slab", flat.rock_wet_ton if wet else flat.rock_dry_ton, p["rock_ton"]),
        priced("haul", flat.haul_wet_yd3 if wet else flat.haul_dry_yd3, p["haul_yd3"]),
        priced("ground sheet", flat.slab_membrane_sf, p["slab_membrane_sf"]),
        priced("edge insulation", flat.edge_board_sf, p["edge_board_sf"]),
        priced("radon pipes", s.homes, p["radon_pipe"]),
        priced("fill testing", 1, p["fill_testing"]),
        priced("rock fill", fill_ton, p["rock_ton"]),
        priced("concrete, deeper edge", conc_extra_yd3, p["concrete_yd3"]),
        priced("bars, deeper edge", extra_bars_lb, p["bar_lb"]),
        priced("forms", form_sf, p["form_sf"]),
    ]
    lines += _steps(s, door_res, slab=True)
    return Cost(tuple(lines))
