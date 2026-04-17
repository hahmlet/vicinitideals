"""KNN-based market recommendation engine.

Queries the comp pool (scraped listings with financial data) and returns
weighted-average metrics for a subject property based on the K most
similar comps.

See docs/MARKET_MODEL.md for the full design rationale.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scraped_listing import ScrapedListing

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (see MARKET_MODEL.md §8)
# ---------------------------------------------------------------------------

DEFAULT_K = 7
MAX_DISTANCE = 2.0
MIN_COMPS = 3

WEIGHT_UNITS = 1.0
WEIGHT_VINTAGE = 0.8
WEIGHT_SQFT_PER_UNIT = 0.6
WEIGHT_LOCATION = 0.5

SQFT_PER_UNIT_NORM = 1500.0


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class SubjectProperty:
    """Minimal property description for KNN query."""

    units: int
    year_built: int
    sqft_per_unit: float | None = None
    jurisdiction: str | None = None


@dataclass
class CompResult:
    """A single comparable property with similarity score."""

    listing_id: str
    address: str
    units: int
    year_built: int
    sqft_per_unit: float | None
    jurisdiction: str | None
    noi_per_unit: float
    price_per_unit: float
    cap_rate: float | None
    occupancy_pct: float | None
    noi_per_sqft: float | None
    price_per_sqft: float | None
    distance: float
    similarity: float
    noi_source: str = "broker"  # "broker" | "hellodata"
    weight: float = 0.0  # set after normalization


@dataclass
class MarketRecommendation:
    """Weighted-median market metrics from KNN query (outlier-robust)."""

    noi_per_unit: float
    price_per_unit: float
    cap_rate: float | None
    occupancy_pct: float | None
    noi_per_sqft: float | None
    price_per_sqft: float | None

    # Weighted-mean variants (for reference / comparison)
    noi_per_unit_mean: float | None = None
    price_per_unit_mean: float | None = None

    comp_count: int = 0
    avg_distance: float = 0.0
    avg_similarity: float = 0.0
    low_confidence: bool = False
    comps: list[CompResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Distance computation
# ---------------------------------------------------------------------------


def _compute_distance(subject: SubjectProperty, comp: SubjectProperty) -> float:
    """Weighted Euclidean distance with NULL-tolerant dimensions."""
    terms: list[float] = []
    total_weight = 0.0

    # Unit count (log2 scale)
    if subject.units > 0 and comp.units > 0:
        d = math.log2(subject.units) - math.log2(comp.units)
        terms.append(WEIGHT_UNITS * d * d)
        total_weight += WEIGHT_UNITS

    # Vintage
    if subject.year_built and comp.year_built:
        a = (subject.year_built - 1900) / 130.0
        b = (comp.year_built - 1900) / 130.0
        d = a - b
        terms.append(WEIGHT_VINTAGE * d * d)
        total_weight += WEIGHT_VINTAGE

    # Sqft per unit
    if subject.sqft_per_unit is not None and comp.sqft_per_unit is not None:
        a = subject.sqft_per_unit / SQFT_PER_UNIT_NORM
        b = comp.sqft_per_unit / SQFT_PER_UNIT_NORM
        d = a - b
        terms.append(WEIGHT_SQFT_PER_UNIT * d * d)
        total_weight += WEIGHT_SQFT_PER_UNIT

    # Location (categorical: same = 0, different = 1)
    if subject.jurisdiction and comp.jurisdiction:
        d = 0.0 if subject.jurisdiction.lower() == comp.jurisdiction.lower() else 1.0
        terms.append(WEIGHT_LOCATION * d * d)
        total_weight += WEIGHT_LOCATION

    if total_weight == 0:
        return MAX_DISTANCE + 1  # no comparable dimensions

    return math.sqrt(sum(terms) / total_weight)


# ---------------------------------------------------------------------------
# Comp pool query
# ---------------------------------------------------------------------------


def _comp_eligibility_filter():
    """SQLAlchemy WHERE clause for eligible comps.

    A listing is eligible if it has structural data (units, year, price) AND
    at least one valid NOI source — either broker-reported (noi) or
    HelloData-synthesized (hellodata_noi_per_unit).
    """
    from sqlalchemy import and_, or_
    return (
        ScrapedListing.priority_bucket != "out_of_market",
        ScrapedListing.units.isnot(None),
        ScrapedListing.units > 0,
        ScrapedListing.asking_price.isnot(None),
        ScrapedListing.year_built.isnot(None),
        ScrapedListing.year_built < 2100,
        or_(
            and_(ScrapedListing.noi.isnot(None), ScrapedListing.noi > 0),
            and_(
                ScrapedListing.hellodata_noi_per_unit.isnot(None),
                ScrapedListing.hellodata_noi_per_unit > 0,
            ),
        ),
    )


async def _load_comp_pool(session: AsyncSession) -> list[dict[str, Any]]:
    """Load all eligible comps from the database.

    For each comp, we resolve NOI and occupancy from HelloData-synthesized
    values first (authoritative market data), falling back to broker-reported
    values.  This gives HelloData-enriched listings a more accurate
    contribution to the KNN pool.
    """
    stmt = (
        select(
            ScrapedListing.id,
            ScrapedListing.address_normalized,
            ScrapedListing.address_raw,
            ScrapedListing.units,
            ScrapedListing.year_built,
            ScrapedListing.gba_sqft,
            ScrapedListing.asking_price,
            ScrapedListing.noi,
            ScrapedListing.cap_rate,
            ScrapedListing.occupancy_pct,
            ScrapedListing.jurisdiction,
            ScrapedListing.city,
            # HelloData-synthesized metrics (preferred when present)
            ScrapedListing.hellodata_noi_per_unit,
            ScrapedListing.hellodata_opex_per_unit,
            ScrapedListing.hellodata_egi_per_unit,
            ScrapedListing.hellodata_market_rent_per_unit,
            ScrapedListing.hellodata_occupancy_pct,
        )
        .where(*_comp_eligibility_filter())
    )
    rows = (await session.execute(stmt)).mappings().all()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def get_market_recommendation(
    session: AsyncSession,
    subject: SubjectProperty,
    *,
    k: int = DEFAULT_K,
    max_distance: float = MAX_DISTANCE,
    exclude_listing_id: str | None = None,
) -> MarketRecommendation | None:
    """Query the comp pool and return weighted market metrics for a subject property.

    Returns None if no eligible comps are found within max_distance.
    """
    pool = await _load_comp_pool(session)
    if not pool:
        logger.warning("Market recommendation: comp pool is empty")
        return None

    # Score each comp
    scored: list[CompResult] = []
    for row in pool:
        listing_id = str(row["id"])
        if exclude_listing_id and listing_id == exclude_listing_id:
            continue

        units = row["units"]
        year_built = row["year_built"]
        sqft = float(row["gba_sqft"]) if row["gba_sqft"] else None
        sqft_per_unit = sqft / units if sqft and units > 0 else None
        jurisdiction = row["jurisdiction"] or row["city"]

        comp_subject = SubjectProperty(
            units=units,
            year_built=year_built,
            sqft_per_unit=sqft_per_unit,
            jurisdiction=jurisdiction,
        )

        dist = _compute_distance(subject, comp_subject)
        if dist > max_distance:
            continue

        price = float(row["asking_price"])

        # Resolve NOI — prefer broker-reported (pertains to this exact property),
        # fall back to HelloData-synthesized per-unit value if broker NOI missing.
        broker_noi = row.get("noi")
        hd_noi_per_unit = row.get("hellodata_noi_per_unit")
        if broker_noi is not None and broker_noi > 0:
            noi = float(broker_noi)
            noi_per_unit = noi / units
            noi_per_sqft = noi / sqft if sqft and sqft > 0 else None
            noi_source = "broker"
        elif hd_noi_per_unit is not None and hd_noi_per_unit > 0:
            noi_per_unit = float(hd_noi_per_unit)
            noi = noi_per_unit * units  # synthesize total for per-sqft calc
            noi_per_sqft = noi / sqft if sqft and sqft > 0 else None
            noi_source = "hellodata"
        else:
            continue  # shouldn't happen given eligibility filter, but be safe

        # Resolve occupancy — same preference order.
        broker_occ = row.get("occupancy_pct")
        hd_occ = row.get("hellodata_occupancy_pct")
        if broker_occ is not None:
            occupancy_pct = float(broker_occ)
        elif hd_occ is not None:
            occupancy_pct = float(hd_occ)
        else:
            occupancy_pct = None

        scored.append(CompResult(
            listing_id=listing_id,
            address=row["address_normalized"] or row["address_raw"] or "Unknown",
            units=units,
            year_built=year_built,
            sqft_per_unit=sqft_per_unit,
            jurisdiction=jurisdiction,
            noi_per_unit=noi_per_unit,
            price_per_unit=price / units,
            cap_rate=float(row["cap_rate"]) if row["cap_rate"] else None,
            occupancy_pct=occupancy_pct,
            noi_per_sqft=noi_per_sqft,
            price_per_sqft=price / sqft if sqft and sqft > 0 else None,
            distance=dist,
            similarity=1.0 / (1.0 + dist),
            noi_source=noi_source,
        ))

    if not scored:
        logger.info("Market recommendation: no comps within max_distance=%.2f", max_distance)
        return None

    # Sort by distance, take top K
    scored.sort(key=lambda c: c.distance)
    top_k = scored[:k]

    # Compute normalized weights
    total_sim = sum(c.similarity for c in top_k)
    for c in top_k:
        c.weight = c.similarity / total_sim if total_sim > 0 else 1.0 / len(top_k)

    # ── Blending: weighted median (primary) + weighted mean (reference) ──

    def _weighted_median(pairs: list[tuple[float, float]]) -> float | None:
        """Compute weighted median: sort by value, walk cumulative weight to 50%.

        Robust to outliers — a single extreme comp cannot move the median
        regardless of its similarity weight.
        """
        if not pairs:
            return None
        w_total = sum(w for w, _ in pairs)
        if w_total == 0:
            return None
        sorted_pairs = sorted(pairs, key=lambda p: p[1])
        cumulative = 0.0
        half = w_total / 2.0
        for i, (w, v) in enumerate(sorted_pairs):
            cumulative += w
            if cumulative >= half:
                # Interpolate with previous if we jumped past the midpoint
                if i > 0 and cumulative - w < half:
                    prev_v = sorted_pairs[i - 1][1]
                    frac = (half - (cumulative - w)) / w
                    return prev_v + frac * (v - prev_v)
                return v
        return sorted_pairs[-1][1]  # fallback: last value

    def _weighted_avg(pairs: list[tuple[float, float]]) -> float | None:
        if not pairs:
            return None
        w_total = sum(w for w, _ in pairs)
        if w_total == 0:
            return None
        return sum(w * v for w, v in pairs) / w_total

    # Core metrics — all comps have these
    noi_pairs = [(c.weight, c.noi_per_unit) for c in top_k]
    price_pairs = [(c.weight, c.price_per_unit) for c in top_k]

    noi_per_unit = _weighted_median(noi_pairs)
    price_per_unit = _weighted_median(price_pairs)

    # Optional metrics (only comps that have them)
    cap_pairs = [(c.weight, c.cap_rate) for c in top_k if c.cap_rate is not None]
    occ_pairs = [(c.weight, c.occupancy_pct) for c in top_k if c.occupancy_pct is not None]
    noi_sqft_pairs = [(c.weight, c.noi_per_sqft) for c in top_k if c.noi_per_sqft is not None]
    price_sqft_pairs = [(c.weight, c.price_per_sqft) for c in top_k if c.price_per_sqft is not None]

    avg_dist = sum(c.distance for c in top_k) / len(top_k)
    avg_sim = sum(c.similarity for c in top_k) / len(top_k)

    return MarketRecommendation(
        noi_per_unit=round(noi_per_unit, 2),
        price_per_unit=round(price_per_unit, 2),
        cap_rate=round(v, 4) if (v := _weighted_median(cap_pairs)) is not None else None,
        occupancy_pct=round(v, 4) if (v := _weighted_median(occ_pairs)) is not None else None,
        noi_per_sqft=round(v, 2) if (v := _weighted_median(noi_sqft_pairs)) is not None else None,
        price_per_sqft=round(v, 2) if (v := _weighted_median(price_sqft_pairs)) is not None else None,
        noi_per_unit_mean=round(v, 2) if (v := _weighted_avg(noi_pairs)) is not None else None,
        price_per_unit_mean=round(v, 2) if (v := _weighted_avg(price_pairs)) is not None else None,
        comp_count=len(top_k),
        avg_distance=round(avg_dist, 4),
        avg_similarity=round(avg_sim, 4),
        low_confidence=len(top_k) < MIN_COMPS,
        comps=top_k,
    )
