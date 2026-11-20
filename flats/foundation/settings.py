"""Foundation model settings: ``flats/config/foundation.yaml``, validated whole.

Every setting is ``{value, source}`` and every price ``{low, high, unit,
source}``. The loader refuses a file in which an expected entry is missing, an
unknown one appears, or any entry lacks its value or its source label -- the
settings are read as research authority, so they must never be half-read.

Settings are held as one frozen :class:`Settings`; a test or a later slice
changes one with :meth:`Settings.replace` (for instance halving the station
spacing for FD6 section 8 check 7), never by editing a module constant.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PATH = Path(__file__).resolve().parents[1] / "config" / "foundation.yaml"


@dataclass(frozen=True, slots=True)
class Price:
    """One section 6 price: low and high, carried separately, never averaged."""

    low: Decimal
    high: Decimal
    unit: str
    source: str


#: section -> the settings it holds, in file order. A setting's name is unique
#: across sections, so :class:`Settings` is flat.
SECTIONS: dict[str, tuple[str, ...]] = {
    "building": ("length_ft", "width_ft", "party_x_ft", "door_x_ft"),
    "raised": (
        "clear_in",
        "floor_depth_in",
        "footing_t_in",
        "footing_w_long_in",
        "footing_w_end_in",
        "footing_w_party_in",
        "stem_outside_in",
        "stem_party_in",
        "plain_wall_max_in",
        "engineered_stem_in",
        "vert_bar_spacing_ft",
        "vert_bars_extra_per_line",
        "vert_bar_extra_in",
        "level_bars_base",
        "level_bar_third_over_in",
        "level_bar_fourth_over_in",
        "footing_max_slope",
        "trench_w_in",
        "haul_share",
    ),
    "shared": ("embed_in", "use_frost_register", "bar_lb_per_ft", "lap", "concrete_waste", "rock_ton_per_yd3"),
    "slab": (
        "slab_top_in",
        "slab_t_in",
        "edge_w_in",
        "edge_d_in",
        "edge_extra_t_in",
        "fill_limit_in",
        "unbalanced_limit_in",
        "uprights_fill_over_in",
    ),
    "doors": (
        "landing_drop_in",
        "riser_in",
        "tread_in",
        "landing_depth_in",
        "guard_over_in",
        "handrail_risers",
    ),
    "sampling": (
        "station_ft",
        "high_point_along_ft",
        "high_point_across_ft",
        "fill_cell_ft",
        "lump_share",
        "grid_step_ft",
        "grid_margin_ft",
        "coarse_cell_over_m",
        "front_face_guess_over_deg",
        "tolerance_in",
    ),
    "record": ("fill_bands_in", "wall_bands_ft"),
    "classify": (
        "tall_wall_over_ft",
        "long_stair_over_ft",
        "guard_doors_min",
        "near_flat_relief_ft",
        "low_wall_max_ft",
        "shallow_fill_max_in",
    ),
    "ground_support": ("own_look_classes", "piles_classes", "footing_classes", "piles_per_pod"),
    "old_buildings": (
        "grow_ft",
        "corner_within_ft",
        "basement_floor_ft",
        "deep_stem_in",
        "bridge_run_ft",
        "bridge_corner_ft",
        "bridge_bars",
        "bridge_bar_lb_per_ft",
        "bridge_past_ft",
        "bridge_pad_extra_w_ft",
        "bridge_pad_len_ft",
        "year_band_1",
        "year_band_2",
        "share_before_1940",
        "share_1940_1959",
        "share_1960_on",
        "share_not_held",
    ),
    "flat_lot": (
        "fd3_length_ft",
        "homes",
        "party_strip_w_in",
        "party_strip_d_in",
        "strip_soil_in",
        "radon_layer_in",
        "radon_rock_ton_per_yd3",
        "wet_extra_base_in",
        "spoil_edge_extra_w_in",
        "slab_edge_bars",
        "slab_membrane_factor",
        "crawl_membrane_factor",
        "edge_board_sf_per_ft",
        "vents",
    ),
}

PRICES: tuple[str, ...] = (
    "concrete_yd3",
    "bar_lb",
    "form_sf",
    "rock_ton",
    "riser",
    "step_pad",
    "rail_ft",
    "pile",
    "pump",
    "haul_yd3",
    "slab_membrane_sf",
    "crawl_membrane_sf",
    "edge_board_sf",
    "vent",
    "radon_pipe",
    "fill_testing",
    "cassettes_12",
)

_LISTS = {"party_x_ft", "door_x_ft", "fill_bands_in", "wall_bands_ft", "own_look_classes", "piles_classes", "footing_classes"}
_INTS = {
    "vert_bars_extra_per_line",
    "level_bars_base",
    "handrail_risers",
    "piles_per_pod",
    "homes",
    "slab_edge_bars",
    "vents",
    "guard_doors_min",
    "bridge_bars",
    "year_band_1",
    "year_band_2",
}
_BOOLS = {"use_frost_register"}


@dataclass(frozen=True)
class Settings:
    """Every FD6 section 4 setting and section 6 price, by name."""

    # building
    length_ft: float
    width_ft: float
    party_x_ft: tuple[float, ...]
    door_x_ft: tuple[float, ...]
    # raised (B)
    clear_in: float
    floor_depth_in: float
    footing_t_in: float
    footing_w_long_in: float
    footing_w_end_in: float
    footing_w_party_in: float
    stem_outside_in: float
    stem_party_in: float
    plain_wall_max_in: float
    engineered_stem_in: float
    vert_bar_spacing_ft: float
    vert_bars_extra_per_line: int
    vert_bar_extra_in: float
    level_bars_base: int
    level_bar_third_over_in: float
    level_bar_fourth_over_in: float
    footing_max_slope: float
    trench_w_in: float
    haul_share: float
    # shared
    embed_in: float
    use_frost_register: bool
    bar_lb_per_ft: float
    lap: float
    concrete_waste: float
    rock_ton_per_yd3: float
    # slab (A)
    slab_top_in: float
    slab_t_in: float
    edge_w_in: float
    edge_d_in: float
    edge_extra_t_in: float
    fill_limit_in: float
    unbalanced_limit_in: float
    uprights_fill_over_in: float
    # doors
    landing_drop_in: float
    riser_in: float
    tread_in: float
    landing_depth_in: float
    guard_over_in: float
    handrail_risers: int
    # sampling
    station_ft: float
    high_point_along_ft: float
    high_point_across_ft: float
    fill_cell_ft: float
    lump_share: float
    grid_step_ft: float
    grid_margin_ft: float
    coarse_cell_over_m: float
    front_face_guess_over_deg: float
    tolerance_in: float
    # record
    fill_bands_in: tuple[float, ...]
    wall_bands_ft: tuple[float, ...]
    # classify
    tall_wall_over_ft: float
    long_stair_over_ft: float
    guard_doors_min: int
    near_flat_relief_ft: float
    low_wall_max_ft: float
    shallow_fill_max_in: float
    # ground support
    own_look_classes: tuple[str, ...]
    piles_classes: tuple[str, ...]
    footing_classes: tuple[str, ...]
    piles_per_pod: int
    # old buildings under the pod (FD6 5.8, FD7)
    grow_ft: float
    corner_within_ft: float
    basement_floor_ft: float
    deep_stem_in: float
    bridge_run_ft: float
    bridge_corner_ft: float
    bridge_bars: int
    bridge_bar_lb_per_ft: float
    bridge_past_ft: float
    bridge_pad_extra_w_ft: float
    bridge_pad_len_ft: float
    year_band_1: int
    year_band_2: int
    share_before_1940: float
    share_1940_1959: float
    share_1960_on: float
    share_not_held: float
    # flat-lot takeoff (FD3)
    fd3_length_ft: float
    homes: int
    party_strip_w_in: float
    party_strip_d_in: float
    strip_soil_in: float
    radon_layer_in: float
    radon_rock_ton_per_yd3: float
    wet_extra_base_in: float
    spoil_edge_extra_w_in: float
    slab_edge_bars: int
    slab_membrane_factor: float
    crawl_membrane_factor: float
    edge_board_sf_per_ft: float
    vents: int
    # prices and labels
    prices: dict[str, Price] = field(compare=False)
    sources: dict[str, str] = field(compare=False)

    def replace(self, **changes: Any) -> Settings:
        """A copy with some settings changed (a test, a sensitivity run)."""
        return dataclasses.replace(self, **changes)

    def price(self, key: str) -> Price:
        return self.prices[key]


def _number(where: str, raw: Any, *, integer: bool) -> float | int:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValueError(f"{where}: value must be a number, got {raw!r}")
    if integer:
        if float(raw) != int(raw):
            raise ValueError(f"{where}: value must be a whole number, got {raw!r}")
        return int(raw)
    return float(raw)


def _value(name: str, raw: Any) -> Any:
    if name in _BOOLS:
        if not isinstance(raw, bool):
            raise ValueError(f"{name}: value must be true or false, got {raw!r}")
        return raw
    if name in _LISTS:
        if not isinstance(raw, list) or not raw:
            raise ValueError(f"{name}: value must be a non-empty list")
        if name.endswith("_classes"):
            return tuple(str(v) for v in raw)
        return tuple(float(_number(name, v, integer=False)) for v in raw)
    return _number(name, raw, integer=name in _INTS)


def _price(key: str, raw: Any) -> Price:
    if not isinstance(raw, dict):
        raise ValueError(f"price {key}: must be a mapping of low, high, unit, source")
    extra = set(raw) - {"low", "high", "unit", "source"}
    if extra:
        raise ValueError(f"price {key}: unknown keys {sorted(extra)}")
    for part in ("low", "high", "unit", "source"):
        if raw.get(part) in (None, ""):
            raise ValueError(f"price {key}: needs {part}")
    low = Decimal(str(_number(f"price {key} low", raw["low"], integer=False)))
    high = Decimal(str(_number(f"price {key} high", raw["high"], integer=False)))
    if low > high:
        raise ValueError(f"price {key}: low {low} is above high {high}")
    return Price(low=low, high=high, unit=str(raw["unit"]), source=str(raw["source"]))


def parse(doc: dict[str, Any]) -> Settings:
    """Settings from an already-read YAML document (validated whole)."""
    if not isinstance(doc, dict):
        raise ValueError("foundation settings: the file must be a mapping")
    unknown = set(doc) - {*SECTIONS, "prices", "spec"}
    if unknown:
        raise ValueError(f"foundation settings: unknown sections {sorted(unknown)}")
    values: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for section, names in SECTIONS.items():
        block = doc.get(section)
        if not isinstance(block, dict):
            raise ValueError(f"section {section}: missing")
        extra = set(block) - set(names)
        if extra:
            raise ValueError(f"section {section}: unknown settings {sorted(extra)}")
        for name in names:
            entry = block.get(name)
            if not isinstance(entry, dict) or "value" not in entry:
                raise ValueError(f"{section}.{name}: missing, or has no value")
            if set(entry) - {"value", "source"}:
                raise ValueError(f"{section}.{name}: only value and source are allowed")
            if not str(entry.get("source") or "").strip():
                raise ValueError(f"{section}.{name}: has no source label")
            values[name] = _value(name, entry["value"])
            sources[f"{section}.{name}"] = str(entry["source"])
    raw_prices = doc.get("prices")
    if not isinstance(raw_prices, dict):
        raise ValueError("prices: missing")
    extra = set(raw_prices) - set(PRICES)
    if extra:
        raise ValueError(f"prices: unknown prices {sorted(extra)}")
    prices = {}
    for key in PRICES:
        if key not in raw_prices:
            raise ValueError(f"prices.{key}: missing")
        prices[key] = _price(key, raw_prices[key])
        sources[f"prices.{key}"] = prices[key].source
    return Settings(**values, prices=prices, sources=sources)


@lru_cache(maxsize=4)
def load(path: Path = PATH) -> Settings:
    """The settings file, validated whole (cached per path)."""
    return parse(yaml.safe_load(Path(path).read_text(encoding="utf-8")))
