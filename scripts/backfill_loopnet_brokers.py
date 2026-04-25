"""Backfill Brokers + listing.broker_id from stored LoopNet raw_json.

No new API calls — everything we need (slug, name, firm, image) is already
inside SaleDetails.broker[*] which we preserved in raw_json.

Run:
    docker exec vicinitideals-api python scripts/backfill_loopnet_brokers.py
"""

from __future__ import annotations

import asyncio
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import AsyncSessionLocal  # noqa: E402
from app.models.project import ScrapedListing  # noqa: E402
from app.scrapers.loopnet_broker import (  # noqa: E402
    extract_brokers_from_sale_details,
    upsert_broker_from_loopnet,
)


async def main() -> int:
    examined = 0
    listings_with_broker_set = 0
    listings_with_no_slug = 0
    brokers_created_or_touched: set = set()
    multi_broker_listings = 0
    per_listing_broker_counts: Counter[int] = Counter()

    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            select(ScrapedListing).where(ScrapedListing.source == "loopnet")
        )).scalars().all()

        for r in rows:
            examined += 1
            sale = (r.raw_json or {}).get("sale_details") or {}
            brokers = extract_brokers_from_sale_details(sale)

            slugs_in_listing = [b for b in brokers if b.get("loopnet_broker_id")]
            per_listing_broker_counts[len(slugs_in_listing)] += 1
            if len(slugs_in_listing) > 1:
                multi_broker_listings += 1

            if not slugs_in_listing:
                listings_with_no_slug += 1
                continue

            primary_id = None
            for i, b in enumerate(slugs_in_listing):
                bid = await upsert_broker_from_loopnet(session, b)
                if bid is not None:
                    brokers_created_or_touched.add(b["loopnet_broker_id"])
                    if i == 0:
                        primary_id = bid

            if primary_id is not None and r.broker_id != primary_id:
                r.broker_id = primary_id
                listings_with_broker_set += 1

            # Commit each listing's broker work so a later failure doesn't
            # roll back what we already did.
            await session.commit()

    print(f"Examined: {examined} LoopNet listings")
    print(f"Listings with primary broker_id newly set: {listings_with_broker_set}")
    print(f"Listings with NO parseable broker slug:    {listings_with_no_slug}")
    print(f"Multi-broker listings (>=2):               {multi_broker_listings}")
    print(f"Unique broker slugs created/touched:       {len(brokers_created_or_touched)}")
    print()
    print("Broker count distribution per listing:")
    for n in sorted(per_listing_broker_counts):
        print(f"  {n} broker(s): {per_listing_broker_counts[n]} listings")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
