"""Backfill LoopNet MF-specific fields (units, stories, occupancy, price_per_unit)
from already-stored raw_json — no new API calls.

LoopNet uses different propertyFacts keys for Multifamily vs commercial listings:
  noUnits / noStories / averageOccupancy / pricePerUnit  (MF)
  buildingHeight / occupancyPercentage / percentLeased   (commercial)

The original mapper only read commercial keys, leaving MF rows with NULL
units/stories/occupancy/price_per_unit. This script re-maps every loopnet
row using the fixed mapper against its preserved raw_json.

Run:
    docker exec vicinitideals-api python scripts/backfill_loopnet_mf_fields.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import AsyncSessionLocal  # noqa: E402
from app.models.project import ScrapedListing  # noqa: E402
from app.scrapers.loopnet import map_to_scraped_listing  # noqa: E402


async def main() -> int:
    updated = 0
    examined = 0
    # Fields we may newly populate via re-mapping. (sub_type re-derived from
    # apartmentStyle so it can shift even when other fields don't.)
    BACKFILL_FIELDS = (
        "units", "stories", "occupancy_pct", "price_per_unit",
        "lot_sqft", "year_built", "year_renovated",
        "is_in_opportunity_zone", "sale_condition",
        "price_per_sqft", "gba_sqft",
        "sub_type",
    )
    fields_filled = dict.fromkeys(BACKFILL_FIELDS, 0)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ScrapedListing).where(ScrapedListing.source == "loopnet")
        )
        listings = list(result.scalars())

        for listing in listings:
            examined += 1
            raw = listing.raw_json or {}
            sale = raw.get("sale_details") or {}
            ext = raw.get("extended_details")
            if not sale:
                continue

            mapped = map_to_scraped_listing(
                sale, ext,
                listing_id=listing.source_id,
                lat=float(listing.lat) if listing.lat is not None else None,
                lng=float(listing.lng) if listing.lng is not None else None,
            )

            changed = False
            for col in BACKFILL_FIELDS:
                old = getattr(listing, col)
                new = mapped.get(col)
                if new is not None and old != new:
                    setattr(listing, col, new)
                    fields_filled[col] += 1
                    changed = True

            if changed:
                updated += 1

        await session.commit()

    print(f"Examined: {examined}  Updated: {updated}")
    for col, n in fields_filled.items():
        print(f"  {col}: {n} rows newly populated")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
