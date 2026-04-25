"""Re-extract broker license_number / license_state from already-stored Crexi
listing raw_json. No new API calls.

Crexi's per-asset /brokers endpoint returns license data under
``licenseDetails[*].number`` (e.g. ``"OR 880100065"``) and ``licenses[]``.
The original mapper looked for ``licenseNumber`` and missed both shapes;
this script walks every Crexi scraped_listing's ``raw_json->'brokers'``
and updates any broker that doesn't yet have a license set, respecting
``license_number_locked`` (skips manually-set rows).

Run:
    docker exec vicinitideals-api python scripts/backfill_crexi_broker_licenses.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import AsyncSessionLocal  # noqa: E402
from app.models.broker import Broker  # noqa: E402
from app.models.scraped_listing import ScrapedListing  # noqa: E402
from app.scrapers.crexi import _extract_crexi_license  # noqa: E402


async def main() -> int:
    examined = 0
    updated = 0
    skipped_locked = 0

    async with AsyncSessionLocal() as session:
        # Build a {crexi_broker_id: (license_number, license_state)} map by
        # walking every Crexi listing's raw_json->'brokers' once. Last write
        # wins, but Crexi is consistent so it doesn't matter.
        license_map: dict[int, tuple[str | None, str | None]] = {}
        listings = (
            await session.execute(
                select(ScrapedListing).where(ScrapedListing.source == "crexi")
            )
        ).scalars().all()
        for listing in listings:
            raw = listing.raw_json or {}
            brokers = raw.get("brokers") or []
            if not isinstance(brokers, list):
                continue
            for entry in brokers:
                if not isinstance(entry, dict):
                    continue
                bid = entry.get("id")
                if not isinstance(bid, int):
                    continue
                num, state = _extract_crexi_license(entry)
                if num:
                    license_map[bid] = (num, state)

        # Update brokers that don't have a license yet (or whose license
        # came from somewhere else and isn't locked).
        brokers = (
            await session.execute(
                select(Broker).where(Broker.crexi_broker_id.isnot(None))
            )
        ).scalars().all()
        for broker in brokers:
            examined += 1
            entry = license_map.get(broker.crexi_broker_id)
            if entry is None:
                continue
            num, state = entry
            if broker.license_number_locked:
                skipped_locked += 1
                continue
            if broker.license_number == num and broker.license_state == state:
                continue
            broker.license_number = num
            broker.license_state = state
            updated += 1

        await session.commit()

    print(f"Examined: {examined}  Updated: {updated}  SkippedLocked: {skipped_locked}")
    print(f"Crexi licenses available across all listings: {len(license_map)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
