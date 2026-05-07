"""One-time backfill: link Opportunities to Parcels where parcel_id is NULL.

Run after deploying migration 0073 + parcel_matching service:
    uv run python app/scripts/backfill_parcel_links.py

Processes all unlinked Opportunities ordered by last_seen_at DESC (most
recently active first) in batches of 500. Prints progress and final summary.
Does NOT modify Opportunities that already have parcel_id set.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import func, select

from app.db import AsyncSessionLocal
from app.models.opportunity import Opportunity
from app.services.parcel_matching import link_parcel_if_unlinked

BATCH_SIZE = 500


async def run() -> None:
    async with AsyncSessionLocal() as session:
        total_unlinked: int = (
            await session.execute(
                select(func.count(Opportunity.id)).where(Opportunity.parcel_id.is_(None))
            )
        ).scalar_one()

    print(f"Unlinked opportunities to process: {total_unlinked}")
    if total_unlinked == 0:
        print("Nothing to do.")
        return

    matched = 0
    unmatched = 0
    offset = 0

    while True:
        async with AsyncSessionLocal() as session:
            batch = list(
                (
                    await session.execute(
                        select(Opportunity)
                        .where(Opportunity.parcel_id.is_(None))
                        .order_by(Opportunity.last_seen_at.desc())
                        .limit(BATCH_SIZE)
                        .offset(offset)
                    )
                )
                .scalars()
                .all()
            )
            if not batch:
                break

            for opp in batch:
                linked = await link_parcel_if_unlinked(session, opp)
                if linked:
                    matched += 1
                else:
                    unmatched += 1

            await session.commit()
            processed = offset + len(batch)
            print(
                f"  Progress: {processed}/{total_unlinked} "
                f"(matched so far: {matched}, unmatched: {unmatched})"
            )
            if len(batch) < BATCH_SIZE:
                break
            offset += BATCH_SIZE

    print(f"\nDone. Matched {matched} / {total_unlinked} ({unmatched} unmatched).")


if __name__ == "__main__":
    asyncio.run(run())
