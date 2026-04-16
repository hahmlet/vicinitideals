"""Three-tier parcel-listing matching cascade.

Matching order:
  1. APN normalized exact match
  2. Address + zip code DB lookup
  3. Spatial proximity (lat/lng within ~200m)

Each match records the strategy used and a confidence score so results
can be audited and improved over time.
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.parcel import Parcel
from app.models.scraped_listing import ScrapedListing

logger = logging.getLogger(__name__)

# ~200m bounding box in degrees (generous for geocoding offsets)
_SPATIAL_WINDOW = Decimal("0.002")

# Lot-size mismatch threshold — flag if listing claims 20%+ more than parcel
_LOT_MISMATCH_RATIO = Decimal("1.20")


def normalize_apn(apn: str) -> str:
    """Strip formatting characters for matching.

    Removes dashes, spaces, dots, commas and uppercases.  Original stored
    value is always preserved — this is used at query time only.
    """
    return re.sub(r"[\s\-\.\,]+", "", apn).upper()


async def reconcile_listing_to_parcel(
    session: AsyncSession,
    listing: ScrapedListing,
) -> tuple[Parcel | None, str | None, float | None]:
    """Run the three-tier matching cascade for a single listing.

    Returns:
        (matched_parcel, strategy, confidence)
        strategy is one of "apn", "address", "spatial", or None if unmatched.
        confidence is 1.0 for APN/address, distance-based for spatial.
    """
    # ── Tier 1: APN normalized match ─────────────────────────────────────
    if listing.apn:
        # Handle multi-APN listings — try the first one
        raw_apn = re.split(r"[,;]", listing.apn)[0].strip()
        if raw_apn:
            norm = normalize_apn(raw_apn)
            parcel = (
                await session.execute(
                    select(Parcel).where(Parcel.apn_normalized == norm)
                )
            ).scalar_one_or_none()
            if parcel:
                logger.info("APN match: listing %s → parcel %s (%s)", listing.id, parcel.id, parcel.apn)
                return parcel, "apn", 1.0

    # ── Tier 2: Address + zip match ──────────────────────────────────────
    street = listing.street or ""
    zip_code = listing.zip_code or ""
    if street.strip() and zip_code.strip():
        # Use street-only (not full address with city) to avoid the broker-city problem
        pattern = f"%{street.strip()}%"
        parcel = (
            await session.execute(
                select(Parcel)
                .where(
                    Parcel.address_normalized.ilike(pattern),
                    Parcel.zip_code == zip_code.strip(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if parcel:
            logger.info("Address match: listing %s → parcel %s", listing.id, parcel.id)
            return parcel, "address", 1.0

    # ── Tier 3: Spatial proximity ────────────────────────────────────────
    lat = listing.lat
    lng = listing.lng
    if lat is not None and lng is not None:
        lat_d = Decimal(str(lat))
        lng_d = Decimal(str(lng))
        dist_expr = func.abs(Parcel.latitude - lat_d) + func.abs(Parcel.longitude - lng_d)
        parcel = (
            await session.execute(
                select(Parcel)
                .where(
                    Parcel.latitude.between(lat_d - _SPATIAL_WINDOW, lat_d + _SPATIAL_WINDOW),
                    Parcel.longitude.between(lng_d - _SPATIAL_WINDOW, lng_d + _SPATIAL_WINDOW),
                )
                .order_by(dist_expr)
                .limit(1)
            )
        ).scalar_one_or_none()
        if parcel:
            # Compute confidence from distance (0.004 max → 0.0 confidence, 0.0 dist → 1.0)
            p_lat = Decimal(str(parcel.latitude)) if parcel.latitude is not None else lat_d
            p_lng = Decimal(str(parcel.longitude)) if parcel.longitude is not None else lng_d
            dist = abs(lat_d - p_lat) + abs(lng_d - p_lng)
            max_dist = _SPATIAL_WINDOW * 2
            confidence = float(max(Decimal("0"), Decimal("1") - dist / max_dist))
            logger.info(
                "Spatial match: listing %s → parcel %s (dist=%.6f, conf=%.3f)",
                listing.id, parcel.id, dist, confidence,
            )
            return parcel, "spatial", round(confidence, 3)

    return None, None, None


def detect_lot_size_mismatch(
    listing: ScrapedListing,
    parcel: Parcel,
) -> bool:
    """Return True if listing lot size exceeds parcel lot size by >20%.

    This suggests the listing may cover multiple parcels (assemblage).
    """
    listing_lot = listing.lot_sqft
    parcel_lot = parcel.lot_sqft

    # Fall back to gis_acres → sqft conversion if lot_sqft not available
    if parcel_lot is None and parcel.gis_acres is not None:
        parcel_lot = Decimal(str(parcel.gis_acres)) * Decimal("43560")

    if listing_lot is None or parcel_lot is None:
        return False
    if parcel_lot <= 0:
        return False

    listing_d = Decimal(str(listing_lot))
    parcel_d = Decimal(str(parcel_lot))

    return listing_d > parcel_d * _LOT_MISMATCH_RATIO


async def apply_reconciliation(
    session: AsyncSession,
    listing: ScrapedListing,
    parcel: Parcel,
    strategy: str,
    confidence: float,
) -> None:
    """Write reconciliation results onto a listing after a successful match.

    Sets parcel_id, jurisdiction, match_strategy, match_confidence,
    and lot_size_mismatch flag.
    """
    listing.parcel_id = parcel.id
    listing.jurisdiction = parcel.jurisdiction
    listing.match_strategy = strategy
    listing.match_confidence = Decimal(str(confidence))
    listing.lot_size_mismatch = detect_lot_size_mismatch(listing, parcel)
