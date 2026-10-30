"""Fill ``flats.lot_works_as`` for runs loaded before the table existed (FOLLOWUPS 121).

The Lots page's "Works as" filter reads this table; the bridge loader fills it
for every new run. Writes only ``flats.lot_works_as``. Dry run by default:

    python scripts/flats_backfill_works_as.py            # prints what it would write
    python scripts/flats_backfill_works_as.py --write
    python scripts/flats_backfill_works_as.py --write --run 87

Only runs with no rows are filled unless ``--run`` names them. Safe to run again.
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

from flats.ingest import lot_works_as  # noqa: E402


def _dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def backfill(db_url: str, run_ids: list[int] | None = None, *, write: bool = False) -> dict[str, Any]:
    """Fill each run that lacks rows (or each one named); returns counts per run."""
    import asyncpg

    report: dict[str, Any] = {"write": write, "runs": {}}
    conn = await asyncpg.connect(_dsn(db_url))
    try:
        if run_ids:
            targets = run_ids
        else:
            targets = [
                r["id"]
                for r in await conn.fetch(
                    "SELECT id FROM flats.runs r WHERE NOT EXISTS "
                    "(SELECT 1 FROM flats.lot_works_as w WHERE w.run_id = r.id) ORDER BY id"
                )
            ]
        for run_id in targets:
            would = await conn.fetchval(
                "SELECT count(*) FROM flats.lot_results WHERE run_id = $1 AND checks ? 'forms'", run_id
            )
            entry: dict[str, Any] = {"would_write": would}
            if write:
                async with conn.transaction():
                    entry["written"] = await lot_works_as.refresh(conn, run_id)
            report["runs"][run_id] = entry
    finally:
        await conn.close()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", type=int, action="append", help="flats.runs id (repeatable); default: runs lacking rows")
    parser.add_argument("--write", action="store_true", help="write the rows (default is a dry run)")
    parser.add_argument("--db-url", default=None, help="default: the app settings database_url")
    args = parser.parse_args(argv)
    db_url = args.db_url
    if db_url is None:
        from app.config import settings

        db_url = settings.database_url
    print(json.dumps(asyncio.run(backfill(db_url, args.run, write=args.write)), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
