"""Price per home as SQL, for the Lots page filter, count and sort.

The arithmetic is :mod:`flats.score.price`'s, written a second time as one SQL
expression over ``flats.lot_prices`` -- plain numbers stored per lot (price,
area, the zone's two density limits) -- so a filter can run over the whole
county copy (about 1.2 million lots) without reading the wide lot row or its
JSON. The pod size and road share stay adjustable because they are applied
here, to the stored numbers. ``tests/api/test_ui_flats_price.py`` holds this
and the Python version to the same answer on edge lots; change them together.

A lot with no ``lot_prices`` row reads as "no price" and unknown area.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import Numeric, and_, case, cast, func, literal, or_
from sqlalchemy.sql.elements import ColumnElement

from app.models.flats import FlatsLotPrice
from flats.rules.fields import SQFT_PER_ACRE
from flats.score.price import PriceSettings

_NUM = Numeric(20, 6)


def pods_column(cfg: PriceSettings, colour_rank: ColumnElement[Any]) -> ColumnElement[Any]:
    """Pods the lot holds. ``colour_rank`` is the lot's best colour as 0..3
    (green, yellow, unknown, red); green and yellow keep at least one pod."""
    price = FlatsLotPrice
    area = cast(price.area_sqft, _NUM)
    pod = literal(cfg.pod_sqft, _NUM)
    road = literal(cfg.road_share_pct / Decimal(100), _NUM)
    usable = case((area / pod >= cfg.road_from_pods, area * (1 - road)), else_=area)
    raw = func.floor(usable / pod)
    # LEAST ignores NULL, so a zone with only one limit is held by that one.
    homes_cap = func.least(
        cast(price.cap_du_per_acre, _NUM) * area / literal(Decimal(SQFT_PER_ACRE), _NUM),
        area / cast(price.cap_unit_lot_sqft, _NUM),
    )
    capped = case(
        (homes_cap.is_(None), raw),
        else_=func.least(raw, func.floor(homes_cap / cfg.homes_per_pod)),
    )
    pods = case((colour_rank <= 1, func.greatest(capped, 1)), else_=capped)
    return case(
        (and_(price.area_sqft.is_not(None), price.area_sqft > 0), pods),
        else_=case((colour_rank <= 1, 1), else_=0),
    )


def per_home_column(cfg: PriceSettings, pods: ColumnElement[Any]) -> ColumnElement[Any]:
    """Price per home; NULL when there is no price or no pod fits."""
    return case((pods > 0, FlatsLotPrice.amount / (pods * cfg.homes_per_pod)), else_=None)


def within(per_home: ColumnElement[Any], pods: ColumnElement[Any], ceiling: Decimal) -> ColumnElement[Any]:
    """The filter: at or under ``ceiling`` per home. A lot with no price is
    kept (never hidden by the default); a lot no pod fits on is not."""
    return or_(per_home <= ceiling, and_(FlatsLotPrice.amount.is_(None), pods > 0))
