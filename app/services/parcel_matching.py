"""Parcel-to-Opportunity matching service.

Tries three strategies in priority order:
  1. APN exact — any element of opp.apn_normalized matches parcel.apn_normalized
  2. Lat/lng proximity — within 30 m (haversine fallback; no PostGIS required)
  3. Address text — street_number + normalized street_full_name match

All strategies are read-only lookups. Mutation is isolated to
link_parcel_if_unlinked() which sets opp.parcel_id and is idempotent.
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import TYPE_CHECKING

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.parcel import Parcel

if TYPE_CHECKING:
    from app.models.opportunity import Opportunity

# Proximity threshold in metres — within this radius a parcel is a geo match.
_GEO_THRESHOLD_M = 75.0
# Rough degree bounding box for SQL pre-filter (~0.001° ≈ 110 m at lat 45°).
_GEO_BOX_DEG = 0.001


# ── Helpers ───────────────────────────────────────────────────────────────────

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return distance in metres between two lat/lng points."""
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _normalize_street_name(raw: str | None) -> str:
    """Lowercase, strip accents, collapse whitespace, remove punctuation."""
    if not raw:
        return ""
    s = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode()
    s = s.lower()
    s = re.sub(r"'", "", s)  # remove apostrophes before other punct
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _opp_street_number(opp: "Opportunity") -> int | None:
    """Extract leading integer from opp.street (e.g. '123 Oak Ave' → 123)."""
    raw = opp.street or opp.address_normalized or ""
    m = re.match(r"^\s*(\d+)", raw)
    return int(m.group(1)) if m else None


# ── Core matching strategies ──────────────────────────────────────────────────

async def _match_by_apn(session: AsyncSession, opp: "Opportunity") -> Parcel | None:
    """Strategy 1: any element of opp.apn_normalized matches parcel.apn_normalized."""
    if not opp.apn_normalized:
        return None
    # apn_normalized on Parcel is a single String; on Opportunity it's ARRAY.
    stmt = (
        select(Parcel)
        .where(Parcel.apn_normalized.in_(opp.apn_normalized))
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _match_by_latlng(session: AsyncSession, opp: "Opportunity") -> Parcel | None:
    """Strategy 2: lat/lng proximity within _GEO_THRESHOLD_M metres."""
    if opp.lat is None or opp.lng is None:
        return None
    lat, lng = float(opp.lat), float(opp.lng)
    # Coarse bounding-box filter in SQL, then exact haversine in Python.
    stmt = (
        select(Parcel)
        .where(
            and_(
                Parcel.latitude.isnot(None),
                Parcel.longitude.isnot(None),
                func.abs(Parcel.latitude - lat) < _GEO_BOX_DEG,
                func.abs(Parcel.longitude - lng) < _GEO_BOX_DEG,
            )
        )
    )
    candidates = list((await session.execute(stmt)).scalars().all())
    best: Parcel | None = None
    best_dist = _GEO_THRESHOLD_M
    for p in candidates:
        dist = _haversine_m(lat, lng, float(p.latitude), float(p.longitude))
        if dist <= best_dist:
            best_dist = dist
            best = p
    return best


async def _match_by_address(session: AsyncSession, opp: "Opportunity") -> Parcel | None:
    """Strategy 3: match against parcel.address_normalized using street number prefix filter."""
    street_num = _opp_street_number(opp)
    if street_num is None:
        return None
    raw_street = (opp.street or opp.address_normalized or "").split(" ", 1)
    if len(raw_street) < 2:
        return None
    opp_street_norm = _normalize_street_name(raw_street[1])
    if not opp_street_norm:
        return None

    # SQL pre-filter: address_normalized starts with the street number
    stmt = select(Parcel).where(
        Parcel.address_normalized.ilike(f"{street_num} %")
    )
    candidates = list((await session.execute(stmt)).scalars().all())
    for p in candidates:
        if not p.address_normalized:
            continue
        # Parse street name portion from parcel address (skip leading number token)
        parts = p.address_normalized.split(" ", 1)
        if len(parts) < 2:
            continue
        if _normalize_street_name(parts[1]) == opp_street_norm:
            return p
    return None


# ── Public API ────────────────────────────────────────────────────────────────

async def find_matching_parcel(session: AsyncSession, opp: "Opportunity") -> Parcel | None:
    """Return best Parcel match for an Opportunity, or None.

    Tries strategies in priority order: APN → lat/lng → address text.
    Returns on first hit.
    """
    parcel = await _match_by_apn(session, opp)
    if parcel:
        return parcel
    parcel = await _match_by_latlng(session, opp)
    if parcel:
        return parcel
    return await _match_by_address(session, opp)


async def link_parcel_if_unlinked(session: AsyncSession, opp: "Opportunity") -> bool:
    """Set opp.parcel_id if unlinked and a match is found.

    Idempotent — skips oppos that already have a parcel_id.
    Returns True if a parcel was linked, False otherwise.
    Does NOT commit; caller owns the transaction.
    """
    if opp.parcel_id is not None:
        return False
    parcel = await find_matching_parcel(session, opp)
    if parcel:
        opp.parcel_id = parcel.id
        return True
    return False
