"""One-shot: merge duplicate Broker rows across sources.

Idempotent — safe to re-run. Use after Oregon enrichment + LoopNet ingest.

Run:
    docker exec vicinitideals-api python scripts/merge_duplicate_brokers.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import AsyncSessionLocal  # noqa: E402
from app.services.broker_dedup import merge_duplicate_brokers  # noqa: E402


async def main() -> int:
    async with AsyncSessionLocal() as session:
        report = await merge_duplicate_brokers(session)
        await session.commit()

    print(f"License groups examined: {report.license_groups}")
    print(f"  merged:                {report.license_groups_merged}")
    print(f"  skipped (name mismatch): {report.license_groups_skipped_name_mismatch}")
    print(f"Name-only groups:        {report.name_groups}")
    print(f"  merged:                {report.name_groups_merged}")
    print(f"Listings reassigned:     {report.listings_reassigned}")
    print(f"Disciplinary actions reassigned: {report.disciplinary_actions_reassigned}")
    print(f"Brokers deleted:         {report.brokers_deleted}")
    print(f"Skipped (locked loser):  {report.skipped_locked}")
    if report.skipped_groups:
        print()
        print("Skipped groups (manual review):")
        for g in report.skipped_groups:
            print(f"  {json.dumps(g)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
