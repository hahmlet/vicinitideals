"""Price per home as SQL, for the Lots page filter, count and sort.

The arithmetic is :mod:`flats.score.price`'s, written a second time as one SQL
expression so a filter can run over the whole county copy (about 1.2 million
lots) without loading rows. ``tests/api/test_ui_flats_price.py`` holds the two
to the same answer on edge lots; change them together.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any, Sequence

from sqlalchemy import Numeric, and_, case, cast, func, literal, or_, tuple_
from sqlalchemy.sql.elements import ColumnElement

from app.models.flats import FlatsLot
from flats.rules.fields import SQFT_PER_ACRE
from flats.score.price import PRICE_SOURCES, PriceSettings, PriceSource, ZoneCap

_NUM = Numeric(20, 6)


def layer_column() -> ColumnElement[Any]:
    """The layer a lot is screened under: a pocket's, where it has one
    (``facts.snapshot_zone.of``), else its jurisdiction. Matches
    ``ui_flats._pocket_of``."""
    zone = FlatsLot.facts["snapshot_zone"]
    return func.coalesce(
        case((func.jsonb_typeof(zone) == "object", zone["of"].astext), else_=None),
        FlatsLot.jurisdiction,
    )


def _source_amount(source: PriceSource) -> ColumnElement[Any]:
    node: Any = FlatsLot.facts
    for key in source.amount_path:
        node = node[key]
    return cast(node.astext, _NUM)


def price_column(sources: Sequence[PriceSource] = PRICE_SOURCES) -> ColumnElement[Any]:
    """The lot's price: the first source whose amount is positive, else NULL."""
    amounts = [_source_amount(s) for s in sources]
    return case(*[(a > 0, a) for a in amounts], else_=None)


def _by_value(
    caps: dict[tuple[str, str], ZoneCap], attr: str, scale: Any
) -> ColumnElement[Any]:
    """A CASE over (layer, zone) giving each zone's cap constant, grouped by
    value so the expression stays a few dozen branches wide."""
    groups: dict[Decimal, list[tuple[str, str]]] = defaultdict(list)
    for key, cap in caps.items():
        value = getattr(cap, attr)
        if value is not None:
            groups[value].append(key)
    if not groups:
        return literal(None, _NUM)
    layer = layer_column()
    return case(
        *[(tuple_(layer, FlatsLot.zone).in_(pairs), literal(value, _NUM)) for value, pairs in groups.items()],
        else_=None,
    )


def pods_column(
    cfg: PriceSettings, caps: dict[tuple[str, str], ZoneCap], colour_rank: ColumnElement[Any]
) -> ColumnElement[Any]:
    """Pods the lot holds. ``colour_rank`` is the lot's best colour as 0..3
    (green, yellow, unknown, red); green and yellow keep at least one pod."""
    area = cast(FlatsLot.area_sqft, _NUM)
    pod = literal(cfg.pod_sqft, _NUM)
    road = literal(cfg.road_share_pct / Decimal(100), _NUM)
    usable = case((area / pod >= cfg.road_from_pods, area * (1 - road)), else_=area)
    raw = func.floor(usable / pod)
    du = _by_value(caps, "du_per_acre", None)
    unit_lot = _by_value(caps, "unit_lot_sqft", None)
    # LEAST ignores NULL, so a zone with only one limit is held by that one.
    homes_cap = func.least(du * area / literal(Decimal(SQFT_PER_ACRE), _NUM), area / unit_lot)
    capped = case(
        (homes_cap.is_(None), raw),
        else_=func.least(raw, func.floor(homes_cap / cfg.homes_per_pod)),
    )
    pods = case((colour_rank <= 1, func.greatest(capped, 1)), else_=capped)
    return case((and_(FlatsLot.area_sqft.is_not(None), FlatsLot.area_sqft > 0), pods), else_=case((colour_rank <= 1, 1), else_=0))


def per_home_column(
    cfg: PriceSettings, pods: ColumnElement[Any], sources: Sequence[PriceSource] = PRICE_SOURCES
) -> ColumnElement[Any]:
    """Price per home; NULL when there is no price or no pod fits."""
    return case((pods > 0, price_column(sources) / (pods * cfg.homes_per_pod)), else_=None)


def within(
    per_home: ColumnElement[Any], pods: ColumnElement[Any], ceiling: Decimal, sources: Sequence[PriceSource] = PRICE_SOURCES
) -> ColumnElement[Any]:
    """The filter: at or under ``ceiling`` per home. A lot with no price is
    kept (never hidden by the default); a lot no pod fits on is not."""
    return or_(per_home <= ceiling, and_(price_column(sources).is_(None), pods > 0))
