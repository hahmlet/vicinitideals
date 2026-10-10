"""Price per home: what a lot costs for each townhome it could hold.

**A label, not a screen.** The number never moves a lot's green / yellow / red
(Steph, FOLLOWUPS 66, 2026-10-10): land price is passed on to the buyer and
flexes with the market, so the page shows it and lets a person filter on it.

    pods  = (lot area - roads) / pod_sqft, rounded down
    homes = pods x 4
    price = the best price source's total value   (county roll today)
    per home = price / homes

Roads take ``road_share_pct`` of the lot when it is big enough for
``road_from_pods`` or more pods; smaller lots take none. A lot that is green or
yellow today holds at least one pod. Pods are capped by the zone's encoded
density where one is stated (units per acre, or a minimum area per townhouse
lot), read through the same resolver the screen uses.

Anything above one pod is an ESTIMATE: new roads or a land division may need a
review, which is against the by-right rule.

**Price sources are an ordered list** (:data:`PRICE_SOURCES`); the first with a
positive amount wins, and every quote carries its source and as-of date. A paid
feed slots in ahead of the county roll by adding one entry that reads where the
feed writes its value -- nothing else changes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from flats.rules.fields import SQFT_PER_ACRE

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "price.yaml"

_MAX_ROAD_PCT = Decimal(90)


def as_decimal(value: Any) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        out = Decimal(str(value).strip().replace(",", "").lstrip("$"))
    except InvalidOperation:
        return None
    return out if out.is_finite() else None


@dataclass(frozen=True)
class PriceSettings:
    pod_sqft: Decimal
    road_share_pct: Decimal
    road_from_pods: int
    homes_per_pod: int
    default_per_home_max: Decimal

    def adjusted(self, *, pod_sqft: Any = None, road_share_pct: Any = None) -> "PriceSettings":
        """These settings with a person's overrides applied. A value that is
        blank, unreadable or out of range leaves the default in place."""
        out = self
        pod = as_decimal(pod_sqft)
        if pod is not None and Decimal(500) <= pod <= Decimal(1_000_000):
            out = replace(out, pod_sqft=pod)
        road = as_decimal(road_share_pct)
        if road is not None and Decimal(0) <= road <= _MAX_ROAD_PCT:
            out = replace(out, road_share_pct=road)
        return out


@lru_cache(maxsize=1)
def settings() -> PriceSettings:
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    return PriceSettings(
        pod_sqft=Decimal(str(raw["pod_sqft"])),
        road_share_pct=Decimal(str(raw["road_share_pct"])),
        road_from_pods=int(raw["road_from_pods"]),
        homes_per_pod=int(raw["homes_per_pod"]),
        default_per_home_max=Decimal(str(raw["default_per_home_max"])),
    )


# --- price sources ---------------------------------------------------------------


@dataclass(frozen=True)
class PriceSource:
    """Where a lot's price is read from: a path into the lot's facts."""

    name: str
    #: Path of the amount inside ``lot.facts`` -- e.g. ``("assessor", "total_value")``.
    amount_path: tuple[str, ...]
    #: Path of the as-of date inside ``lot.facts``; ``None`` when the source's
    #: date is the county copy's (the roll comes with the RLIS release).
    as_of_path: tuple[str, ...] | None = None
    basis: str = ""


#: Ordered: the first source with a positive amount wins. A paid feed goes in
#: FRONT of the county roll.
PRICE_SOURCES: tuple[PriceSource, ...] = (
    PriceSource(
        name="County real market value",
        amount_path=("assessor", "total_value"),
        as_of_path=None,
        basis="land + building, county assessor roll",
    ),
)


@dataclass(frozen=True)
class PriceQuote:
    amount: Decimal
    source: str
    as_of: str
    basis: str = ""


def _dig(facts: Mapping[str, Any], path: Sequence[str]) -> Any:
    node: Any = facts
    for key in path:
        if not isinstance(node, Mapping):
            return None
        node = node.get(key)
    return node


def quote_for(
    facts: Mapping[str, Any] | None,
    *,
    county_as_of: str = "",
    sources: Sequence[PriceSource] = PRICE_SOURCES,
) -> PriceQuote | None:
    """The first source that holds a positive price for this lot, with its
    source name and as-of date; ``None`` when none does."""
    for source in sources:
        amount = as_decimal(_dig(facts or {}, source.amount_path))
        if amount is None or amount <= 0:
            continue
        stated = _dig(facts or {}, source.as_of_path) if source.as_of_path else None
        return PriceQuote(amount, source.name, str(stated) if stated else county_as_of, source.basis)
    return None


# --- the zone's density ceiling --------------------------------------------------


@dataclass(frozen=True)
class ZoneCap:
    """What the zone's encoded rules say about how many homes a lot may hold.
    Either may be absent; both absent means no cap is stated."""

    du_per_acre: Decimal | None = None
    #: Smallest townhouse lot the zone allows (a unit-lots variant), sqft.
    unit_lot_sqft: Decimal | None = None

    def density_homes(self, area_sqft: Decimal) -> Decimal | None:
        if self.du_per_acre is None:
            return None
        return self.du_per_acre * area_sqft / Decimal(SQFT_PER_ACRE)

    def unit_lot_homes(self, area_sqft: Decimal) -> Decimal | None:
        if self.unit_lot_sqft is None:
            return None
        return area_sqft / self.unit_lot_sqft


def zone_caps(ruleset: Any, layers: Mapping[str, Any]) -> dict[tuple[str, str], ZoneCap]:
    """Every (layer, zone) that states a cap, read through the screen's own
    resolver under the ``unit_lots`` condition (four townhouse lots, the shape
    a pod is built as). A density marked exempt for a one-lot pod resolves to
    the unit-lots number here, which is the point."""
    out: dict[tuple[str, str], ZoneCap] = {}
    for layer_id, layer in layers.items():
        for zone in layer.zones:
            try:
                got = ruleset.resolve(layer_id, zone, ("unit_lots",), lot={"lot_sqft": 15_000.0})
            except Exception:  # noqa: BLE001 -- a zone the resolver cannot read states no cap
                continue
            density = got.values.get("max_density_du_per_acre")
            du = as_decimal(density.value) if density is not None else None
            minimum = got.values.get("min_lot_sqft")
            unit_lot = None
            if minimum is not None and not minimum.whole_project and "unit_lots" in (minimum.when or ()):
                unit_lot = as_decimal(minimum.value)
            du = du if du is not None and du > 0 else None
            unit_lot = unit_lot if unit_lot is not None and unit_lot > 0 else None
            if du is not None or unit_lot is not None:
                out[(layer_id, zone)] = ZoneCap(du, unit_lot)
    return out


# --- the calculation -------------------------------------------------------------


@dataclass(frozen=True)
class PodPrice:
    pods: int
    homes: int
    #: Price per home; ``None`` when there is no price or no pod fits.
    per_home: Decimal | None
    quote: PriceQuote | None
    #: Above one pod: new roads or a land division may need a review.
    estimate: bool
    roads_taken: bool
    #: ``"density"`` / ``"unit lot"`` when the zone's cap held the count down.
    capped_by: str | None


def pods_on(
    area_sqft: Any,
    cfg: PriceSettings,
    *,
    cap: ZoneCap | None = None,
    keep_one: bool = False,
) -> tuple[int, bool, str | None]:
    """(pods, roads taken, what capped it). ``keep_one``: the lot is green or
    yellow today, so it holds at least one pod."""
    area = as_decimal(area_sqft)
    if area is None or area <= 0:
        return (1 if keep_one else 0), False, None
    roads = area / cfg.pod_sqft >= cfg.road_from_pods
    usable = area * (Decimal(1) - cfg.road_share_pct / Decimal(100)) if roads else area
    pods = math.floor(usable / cfg.pod_sqft)
    capped_by = None
    if cap is not None:
        by_density = cap.density_homes(area)
        by_lot = cap.unit_lot_homes(area)
        limits = [h for h in (by_density, by_lot) if h is not None]
        if limits:
            pods_cap = math.floor(min(limits) / cfg.homes_per_pod)
            if pods_cap < pods:
                pods = pods_cap
                capped_by = "density" if by_density is not None and by_density <= min(limits) else "unit lot"
    if keep_one:
        pods = max(pods, 1)
    return pods, roads, capped_by


def price_per_home(
    area_sqft: Any,
    facts: Mapping[str, Any] | None,
    cfg: PriceSettings,
    *,
    cap: ZoneCap | None = None,
    keep_one: bool = False,
    county_as_of: str = "",
    sources: Sequence[PriceSource] = PRICE_SOURCES,
) -> PodPrice:
    pods, roads, capped_by = pods_on(area_sqft, cfg, cap=cap, keep_one=keep_one)
    homes = pods * cfg.homes_per_pod
    quote = quote_for(facts, county_as_of=county_as_of, sources=sources)
    per_home = quote.amount / homes if quote is not None and homes > 0 else None
    return PodPrice(pods, homes, per_home, quote, pods > 1, roads, capped_by)
