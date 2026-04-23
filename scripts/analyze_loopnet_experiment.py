"""Analyze 30-day LoopNet experiment snapshots → recommend refresh cadence.

Run after a full experiment month to produce a markdown report covering:
  - Update frequency per listing (count, histogram)
  - Field-level change rate (which fields actually move)
  - Age-bucket analysis (do fresh listings churn more in week 1?)
  - Budget consumption summary

Usage:
    uv run python scripts/analyze_loopnet_experiment.py \
        > reports/loopnet_experiment_$(date +%Y-%m).md

Writes to stdout (markdown). Redirect to a file for archiving.
"""

from __future__ import annotations

import asyncio
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from app.db import AsyncSessionLocal
from app.models.api_call_log import ApiCallLog
from app.models.listing_snapshot import ListingSnapshot
from app.models.project import ScrapedListing


async def _gather_snapshots(session) -> dict[Any, list[ListingSnapshot]]:
    stmt = (
        select(ListingSnapshot)
        .where(ListingSnapshot.endpoint == "sale_details")
        .order_by(ListingSnapshot.listing_id, ListingSnapshot.captured_at.asc())
    )
    result = await session.execute(stmt)
    by_listing: dict[Any, list[ListingSnapshot]] = defaultdict(list)
    for snap in result.scalars():
        by_listing[snap.listing_id].append(snap)
    return by_listing


def _price_from_snapshot(snap: ListingSnapshot) -> str | None:
    if not snap.raw_json:
        return None
    pf = (snap.raw_json.get("propertyFacts") or {})
    return pf.get("price")


def _changed_fields(a: ListingSnapshot, b: ListingSnapshot) -> list[str]:
    """Return list of propertyFacts field names whose values differ between snapshots."""
    aj = (a.raw_json or {}).get("propertyFacts") or {}
    bj = (b.raw_json or {}).get("propertyFacts") or {}
    changed = []
    for key in set(aj) | set(bj):
        if aj.get(key) != bj.get(key):
            changed.append(key)
    return changed


async def main() -> None:
    async with AsyncSessionLocal() as session:
        by_listing = await _gather_snapshots(session)
        total_snapshots = sum(len(v) for v in by_listing.values())
        total_listings = len(by_listing)

        # Per-listing change count (any propertyFacts field different between consecutive snapshots)
        change_counts: Counter[int] = Counter()
        field_change_counter: Counter[str] = Counter()
        for snaps in by_listing.values():
            n_changes = 0
            for i in range(1, len(snaps)):
                deltas = _changed_fields(snaps[i - 1], snaps[i])
                if deltas:
                    n_changes += 1
                    for f in deltas:
                        field_change_counter[f] += 1
            change_counts[n_changes] += 1

        # Budget consumption
        budget_stmt = (
            select(ApiCallLog.billing_month, func.count(ApiCallLog.id))
            .where(ApiCallLog.source == "loopnet")
            .group_by(ApiCallLog.billing_month)
            .order_by(ApiCallLog.billing_month)
        )
        budget_result = await session.execute(budget_stmt)
        budget_rows = list(budget_result)

        listing_count_stmt = select(func.count(ScrapedListing.id)).where(
            ScrapedListing.source == "loopnet"
        )
        total_listings_captured = (
            await session.execute(listing_count_stmt)
        ).scalar_one()

    # ------------------------------------------------------------------ render
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    out = sys.stdout.write

    out(f"# LoopNet Experiment Analysis\n\n")
    out(f"_Generated: {now}_\n\n")
    out(f"## Summary\n\n")
    out(f"- Listings captured in DB: **{total_listings_captured}**\n")
    out(f"- Listings with ≥1 snapshot: **{total_listings}**\n")
    out(f"- Total snapshots: **{total_snapshots}**\n\n")

    out(f"## Per-listing change count distribution\n\n")
    out(f"| Changes during experiment | Listings |\n|---:|---:|\n")
    for n in sorted(change_counts):
        out(f"| {n} | {change_counts[n]} |\n")

    if change_counts:
        unchanged = change_counts.get(0, 0)
        pct_unchanged = 100.0 * unchanged / max(total_listings, 1)
        out(f"\n**{unchanged} of {total_listings} listings ({pct_unchanged:.0f}%) never changed.**\n\n")

    out(f"## Field-level change frequency\n\n")
    out(f"| Field | # change events |\n|---|---:|\n")
    for field, count in field_change_counter.most_common(20):
        out(f"| `{field}` | {count} |\n")
    if not field_change_counter:
        out(f"_No field-level changes detected._\n")
    out("\n")

    out(f"## Budget consumption by month\n\n")
    out(f"| Billing month | API calls |\n|---|---:|\n")
    for month, count in budget_rows:
        out(f"| {month.isoformat()} | {count} |\n")
    out("\n")

    # ----------------------------------------------------- cadence recommendation
    out(f"## Recommended refresh cadence\n\n")
    if total_listings == 0:
        out(f"_Insufficient data._\n")
        return

    pct_unchanged_val = 100.0 * change_counts.get(0, 0) / total_listings
    if pct_unchanged_val >= 80:
        out(
            f"- {pct_unchanged_val:.0f}% of listings never changed during the experiment.\n"
            f"- **Recommend bi-monthly refresh** — weekly is overkill.\n"
            f"- Use `SaleDetails.lastUpdated` as cheap staleness signal where possible.\n"
        )
    elif pct_unchanged_val >= 50:
        out(
            f"- {pct_unchanged_val:.0f}% stable. **Recommend monthly refresh.**\n"
            f"- For MF listings attached to active opportunities, bump to weekly.\n"
        )
    else:
        out(
            f"- Only {pct_unchanged_val:.0f}% stable — brokers edit frequently.\n"
            f"- **Recommend weekly refresh** with daily polling for deal-attached listings.\n"
        )


if __name__ == "__main__":
    asyncio.run(main())
