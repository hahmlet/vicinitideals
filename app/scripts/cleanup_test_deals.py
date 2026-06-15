"""One-shot CLI to purge accumulated E2E / regression **test deals** from a DB.

Thin wrapper over :func:`app.services.test_cleanup.purge_test_deals` — see that
module for the match predicate, the FK-ordered delete graph, and the safety
guards. The same logic runs automatically every day as the
``app.tasks.maintenance.purge_test_deals_task`` Celery janitor, so deals no
longer accumulate; this CLI is for ad-hoc / backfill runs.

Dry-run by default (rolls back, changes nothing). Pass ``--execute`` to commit.
``--max-age-hours N`` restricts deletion to rows older than N hours; the default
is no age limit (purge every match).

Run inside the api container::

    docker exec vicinitideals-api python -m app.scripts.cleanup_test_deals            # dry-run
    docker exec vicinitideals-api python -m app.scripts.cleanup_test_deals --execute  # delete
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import text

from app.db import AsyncSessionLocal
from app.services.test_cleanup import _MATCH, purge_test_deals


async def _run(execute: bool, max_age_hours: int | None) -> None:
    async with AsyncSessionLocal() as session:
        opp_sample = (await session.execute(text(
            f"SELECT name FROM opportunities WHERE ({_MATCH}) ORDER BY name LIMIT 8"
        ))).scalars().all()
        deal_sample = (await session.execute(text(
            f"SELECT name FROM deals d WHERE ({_MATCH}) "
            f"AND NOT EXISTS (SELECT 1 FROM scenarios s WHERE s.deal_id = d.id) "
            f"ORDER BY name LIMIT 8"
        ))).scalars().all()
        print("sample matched opportunities:", ", ".join(repr(s) for s in opp_sample) or "(none)")
        print("sample orphan test deals:    ", ", ".join(repr(s) for s in deal_sample) or "(none)")

        result = await purge_test_deals(session, execute=execute, max_age_hours=max_age_hours)

    print(f"matched roots: {result['matched']}")
    verb = "deleted" if execute else "would delete"
    for label, n in result["rows_affected"].items():
        print(f"  {verb} {n:>7} {label}")
    print(f"  {'=' * 40}")
    print(f"  total rows {verb}: {result['total_rows']}")
    if execute:
        print("COMMITTED. Test deals purged.")
    else:
        print("DRY-RUN — rolled back, nothing changed. Re-run with --execute to delete.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Purge accumulated E2E/regression test deals.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete (default is a dry-run that rolls back).",
    )
    parser.add_argument(
        "--max-age-hours",
        type=int,
        default=None,
        help="Only purge rows older than N hours (default: no age limit).",
    )
    args = parser.parse_args()
    asyncio.run(_run(args.execute, args.max_age_hours))


if __name__ == "__main__":
    main()
