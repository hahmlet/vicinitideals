"""Run the monthly county-source check by hand and write its row.

The same check Celery beat runs on the 3rd of each month
(``app.tasks.flats_probe``): every source in ``flats/config/pipeline.yaml``
asked whether it is still what the copy in use was taken from -- one
metadata request and one count request per ArcGIS layer, one item request
per RLIS archive. Nothing is downloaded and nothing in the copy changes;
the result is one ``flats.probes`` row, and the Lots pages read the newest.

A check that cannot complete (no copy in use, the network gone) is written
as a ``failed`` row rather than raised, so the page can say "the check did
not complete" instead of "not checked yet".

Usage (inside the api container):

    python scripts/flats_probe.py            # write the row
    python scripts/flats_probe.py --dry-run  # run it, print it, roll back
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.config import settings  # noqa: E402
from app.services.flats_refresh import run_probe  # noqa: E402


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db-url", default=settings.database_url)
    parser.add_argument("--dry-run", action="store_true", help="run the check, print it, write nothing")
    args = parser.parse_args(argv)

    engine = create_async_engine(args.db_url, echo=False, future=True)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with Session() as session:
            row = await run_probe(session, log=print)
            for f in row.findings:
                if f["finding"] != "ok":
                    print(f"  {f['finding']:<16} {f['key']}: {f['detail']}")
            print(f"probe: {row.status}, {len(row.findings)} findings, {row.seconds}s")
            if args.dry_run:
                await session.rollback()
                print("dry run, rolled back")
            else:
                await session.commit()
                print(f"flats.probes row {row.id} written")
            return 0 if row.status != "failed" else 1
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
