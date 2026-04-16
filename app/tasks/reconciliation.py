"""Backfill task: reconcile all unlinked listings to parcels.

Runs the three-tier matching cascade (APN → address → spatial) against
every ScrapedListing where parcel_id IS NULL, writes reconciliation
columns, and emits a summary report to the Celery logger.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from typing import Any

from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models.scraped_listing import ScrapedListing
from app.reconciliation.matcher import (
    apply_reconciliation,
    reconcile_listing_to_parcel,
)
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _reconcile_all() -> dict[str, Any]:
    """Iterate all unlinked listings and attempt parcel matching."""
    strategy_counts: Counter[str] = Counter()
    spatial_distances: list[float] = []
    lot_mismatches: list[str] = []
    far_matches: list[str] = []  # spatial matches > 100m (~0.001 deg)
    errors: list[str] = []
    total = 0
    matched = 0

    async with AsyncSessionLocal() as session:
        listings = list(
            (
                await session.execute(
                    select(ScrapedListing).where(ScrapedListing.parcel_id.is_(None))
                )
            ).scalars()
        )
        total = len(listings)
        logger.info("Reconciliation backfill: %d unlinked listings to process", total)

        for listing in listings:
            try:
                parcel, strategy, confidence = await reconcile_listing_to_parcel(
                    session, listing
                )
                if parcel is not None and strategy is not None:
                    await apply_reconciliation(
                        session, listing, parcel, strategy, confidence
                    )
                    matched += 1
                    strategy_counts[strategy] += 1

                    if strategy == "spatial" and confidence is not None:
                        # Convert confidence back to approximate distance
                        dist = (1.0 - confidence) * 0.004
                        spatial_distances.append(dist)
                        if dist > 0.001:  # ~100m
                            addr = listing.address_normalized or listing.address_raw or str(listing.id)
                            far_matches.append(f"{addr} (dist={dist:.6f})")

                    if listing.lot_size_mismatch:
                        addr = listing.address_normalized or listing.address_raw or str(listing.id)
                        lot_mismatches.append(addr)
                else:
                    strategy_counts["unmatched"] += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{listing.id}: {exc}")
                logger.warning("Reconciliation failed for listing %s: %s", listing.id, exc)

        await session.commit()

    # Build report
    report: dict[str, Any] = {
        "total_unlinked": total,
        "matched": matched,
        "unmatched": total - matched,
        "by_strategy": dict(strategy_counts),
        "errors": len(errors),
    }
    if spatial_distances:
        report["spatial_avg_distance"] = round(
            sum(spatial_distances) / len(spatial_distances), 6
        )
        report["spatial_max_distance"] = round(max(spatial_distances), 6)
    if far_matches:
        report["far_matches_over_100m"] = far_matches
    if lot_mismatches:
        report["lot_size_mismatches"] = lot_mismatches
    if errors:
        report["error_details"] = errors[:20]  # cap to avoid huge logs

    # Log the report
    logger.info("=" * 60)
    logger.info("RECONCILIATION BACKFILL REPORT")
    logger.info("=" * 60)
    logger.info("Total unlinked: %d", total)
    logger.info("Matched: %d (%.0f%%)", matched, (matched / total * 100) if total else 0)
    logger.info("Unmatched: %d", total - matched)
    logger.info("By strategy: %s", dict(strategy_counts))
    if spatial_distances:
        logger.info(
            "Spatial distances — avg: %.6f, max: %.6f",
            report["spatial_avg_distance"],
            report["spatial_max_distance"],
        )
    if far_matches:
        logger.info("Far matches (>100m): %s", far_matches)
    if lot_mismatches:
        logger.info("Lot-size mismatches: %s", lot_mismatches)
    if errors:
        logger.info("Errors (%d): %s", len(errors), errors[:5])
    logger.info("=" * 60)

    return report


@celery_app.task(name="app.tasks.reconciliation.reconcile_all_listings_task", queue="default")
def reconcile_all_listings_task() -> dict[str, Any]:
    """Celery task: reconcile all unlinked listings to parcels."""
    return asyncio.get_event_loop().run_until_complete(_reconcile_all())
