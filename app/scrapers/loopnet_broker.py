"""LoopNet broker ingestion — parse slugs from listing data, fetch + upsert.

Two paths for getting broker info:
  1. Free (no API call): every SaleDetails.broker[*] entry already includes
     name, worksFor.name (firm), image, and most importantly url with the
     embedded slug. We persist this immediately at listing-ingest time.
  2. Optional (1 API call/broker, cached forever): /loopnet/broker/
     extendedDetails returns bio, jobTitle, specialties, propertyTypes,
     markets, languages — useful for broker-level context but not required
     for listing → broker linkage.

For each new listing during the weekly sweep:
  - Parse all broker slugs from sale_details.broker[*].url
  - Look up Broker by loopnet_broker_id (the slug)
  - If not found, create a Broker row from the inline SD data
  - Optionally enrich with /broker/extendedDetails (config flag)
  - Set listing.broker_id to the FIRST broker (the listing's primary)
"""

from __future__ import annotations

import re
import uuid
from typing import Any

# /commercial-real-estate-brokers/profile/{name-slug}/{broker-slug}/{listing-id}#...
# Examples:
#   /profile/jeffrey-weitz/mzwstflb/38985870#RealEstateAgent
#   /profile/thomas-tsai/zxz0drxb/...
_BROKER_SLUG_RE = re.compile(
    r"/profile/[^/]+/([a-z0-9]{4,20})/?(?:\d+)?(?:#|$|\?)",
    re.IGNORECASE,
)

BROKER_DETAILS_PATH = "/loopnet/broker/extendedDetails"


def parse_broker_slug(url: str | None) -> str | None:
    """Extract the alphanumeric broker slug from a LoopNet broker profile URL.

    Returns None if the URL doesn't match the expected pattern. Slug is
    lowercased for consistency.
    """
    if not url:
        return None
    m = _BROKER_SLUG_RE.search(str(url))
    return m.group(1).lower() if m else None


def extract_brokers_from_sale_details(
    sale_details: dict[str, Any],
) -> list[dict[str, Any]]:
    """Pull the SD.broker[*] list and shape each entry into a normalized dict.

    Returns list of {slug, name, firm, image, url} (None for missing fields).
    Order is preserved — index 0 is the listing's primary broker.
    """
    raw = sale_details.get("broker") or []
    if not isinstance(raw, list):
        return []

    out: list[dict[str, Any]] = []
    for b in raw:
        if not isinstance(b, dict):
            continue
        url = b.get("url")
        slug = parse_broker_slug(url)
        works_for = b.get("worksFor") or {}
        firm_name = works_for.get("name") if isinstance(works_for, dict) else None
        firm_logo = works_for.get("logo") if isinstance(works_for, dict) else None
        firm_url = works_for.get("url") if isinstance(works_for, dict) else None
        out.append({
            "loopnet_broker_id": slug,
            "name": b.get("name"),
            "firm_name": firm_name,
            "firm_logo": firm_logo,
            "firm_url": firm_url,
            "image": b.get("image"),
            "url": url,
        })
    return out


def split_full_name(full_name: str | None) -> tuple[str | None, str | None]:
    """Best-effort first/last name split. 'Jordan Carter' → ('Jordan', 'Carter').

    Multi-word last names (like 'Van Der Berg') are kept together.
    Suffixes (Jr, II, III) become part of last name.
    """
    if not full_name:
        return None, None
    parts = str(full_name).strip().split()
    if not parts:
        return None, None
    if len(parts) == 1:
        return parts[0], None
    return parts[0], " ".join(parts[1:])


async def fetch_broker_extended_details(
    guard,  # BudgetGuard, but avoid circular import
    broker_slug: str,
) -> dict[str, Any] | None:
    """POST /loopnet/broker/extendedDetails. Returns first data[] entry or None."""
    body = await guard.call(
        BROKER_DETAILS_PATH,
        {"brokerId": str(broker_slug)},
        listing_source_id=str(broker_slug),
    )
    data = body.get("data") or []
    return data[0] if data else None


# ---------------------------------------------------------------------------
# Upsert helpers (DB-side, no API calls)
# ---------------------------------------------------------------------------

async def upsert_brokerage_from_loopnet(
    session,
    *,
    name: str | None,
) -> uuid.UUID | None:
    """Find-or-create Brokerage by normalized name. Returns its id or None."""
    if not name:
        return None
    from sqlalchemy import select

    from app.models.broker import Brokerage
    from app.services.broker_normalize import normalize_name

    normalized = normalize_name(name)
    if not normalized:
        return None
    existing = (
        await session.execute(
            select(Brokerage).where(Brokerage.name == normalized)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing.id
    new_b = Brokerage(id=uuid.uuid4(), name=normalized)
    session.add(new_b)
    await session.flush()
    return new_b.id


async def upsert_broker_from_loopnet(
    session,
    broker_dict: dict[str, Any],
) -> uuid.UUID | None:
    """Find-or-create Broker by loopnet_broker_id (slug).

    `broker_dict` is one entry from extract_brokers_from_sale_details(); may
    optionally include 'extended' key with full /broker/extendedDetails data.
    Returns the Broker.id or None if no slug.
    """
    slug = broker_dict.get("loopnet_broker_id")
    if not slug:
        return None

    from sqlalchemy import select

    from app.models.broker import Broker
    from app.services.broker_normalize import normalize_name

    existing = (
        await session.execute(
            select(Broker).where(Broker.loopnet_broker_id == slug)
        )
    ).scalar_one_or_none()

    full_name = normalize_name(broker_dict.get("name"))
    first, last = split_full_name(full_name)

    # Brokerage linkage — find/create
    brokerage_id = await upsert_brokerage_from_loopnet(
        session, name=broker_dict.get("firm_name"),
    )

    extended = broker_dict.get("extended") or {}
    phone = broker_dict.get("phone") or extended.get("phone")
    # Phone column is String(50); strip extension annotations to be safe.
    if phone:
        phone = str(phone).strip()[:50]
    email = broker_dict.get("email") or extended.get("email")
    if email:
        email = str(email).strip()[:255]

    if existing is not None:
        # Refresh fields from latest LoopNet data (don't clobber non-null
        # locked or richer values from other sources)
        if first and not existing.first_name:
            existing.first_name = first
        if last and not existing.last_name:
            existing.last_name = last
        if broker_dict.get("image") and not existing.thumbnail_url:
            existing.thumbnail_url = broker_dict["image"]
        if brokerage_id and not existing.brokerage_id:
            existing.brokerage_id = brokerage_id
        if phone and not existing.phone:
            existing.phone = phone
        if email and not existing.email:
            existing.email = email
        return existing.id

    # Create new broker
    new_b = Broker(
        id=uuid.uuid4(),
        loopnet_broker_id=slug,
        first_name=first,
        last_name=last,
        thumbnail_url=broker_dict.get("image"),
        brokerage_id=brokerage_id,
        phone=phone,
        email=email,
    )
    session.add(new_b)
    await session.flush()
    return new_b.id
