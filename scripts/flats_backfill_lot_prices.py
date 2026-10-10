"""Fill ``flats.lot_prices`` for county copies loaded before the table existed.

The Lots page's price-per-home filter and sort read this table (FOLLOWUPS 66).
The bridge loader fills it for every new bundle; this one-shot fills a copy that
is already live, and refreshes it after a rules change moves a zone's density
limit. It writes only ``flats.lot_prices`` -- no lot, result or run is touched --
and each snapshot is one transaction, so a failure leaves the table as it was.

    uv run python scripts/flats_backfill_lot_prices.py --snapshot 3 --snapshot 4 --dry-run
    uv run python scripts/flats_backfill_lot_prices.py --snapshot 3 --snapshot 4

Run it after the deploy that created the table (migration 0143); until then the
Lots page shows every lot as "no price". Safe to run again.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from flats.ingest import lot_prices  # noqa: E402


def _dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def backfill(db_url: str, snapshot_ids: list[int], *, dry_run: bool = False) -> dict[str, Any]:
    """Write the price row of every lot in each snapshot; returns counts."""
    import asyncpg

    caps = lot_prices.current_caps()
    report: dict[str, Any] = {"dry_run": dry_run, "zone_caps": len(caps), "snapshots": {}}
    conn = await asyncpg.connect(_dsn(db_url))
    try:
        for snapshot_id in snapshot_ids:
            try:
                async with conn.transaction():
                    written = await lot_prices.refresh(conn, snapshot_id, caps)
                    lots = await conn.fetchval("SELECT count(*) FROM flats.lots WHERE snapshot_id = $1", snapshot_id)
                    stored = await conn.fetchrow(
                        "SELECT count(*)::int AS rows, count(amount)::int AS priced, count(cap_du_per_acre)::int AS capped "
                        "FROM flats.lot_prices WHERE snapshot_id = $1",
                        snapshot_id,
                    )
                    if stored["rows"] != lots:
                        raise SystemExit(f"VERIFY FAILED: snapshot {snapshot_id} has {lots} lots, {stored['rows']} price rows")
                    report["snapshots"][snapshot_id] = {"lots": lots, "written": written, **dict(stored)}
                    if dry_run:
                        raise _DryRun
            except _DryRun:
                report["snapshots"][snapshot_id]["rolled_back"] = True
    finally:
        await conn.close()
    return report


class _DryRun(Exception):
    pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--snapshot", type=int, action="append", required=True, help="flats.snapshots id (repeatable)")
    parser.add_argument("--db-url", default=None, help="default: app settings' database_url")
    parser.add_argument("--dry-run", action="store_true", help="do the work in a transaction and roll it back")
    args = parser.parse_args(argv)
    db_url = args.db_url
    if db_url is None:
        from app.config import settings

        db_url = settings.database_url
    print(json.dumps(asyncio.run(backfill(db_url, args.snapshot, dry_run=args.dry_run)), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
