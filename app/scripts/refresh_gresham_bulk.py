"""Bulk-refresh every Gresham parcel from the city's ArcGIS Taxlots endpoint.

Pages the full Taxlots layer in chunks, normalizes each feature via
`_feature_to_parcel`, and upserts through the standard `_upsert_parcel` flow
(which also reclassifies priority bucket). Non-null values from ArcGIS replace
whatever is currently stored; NULLs from ArcGIS do NOT clobber existing data.

Usage
-----
    uv run python -m app.scripts.refresh_gresham_bulk                # full run
    uv run python -m app.scripts.refresh_gresham_bulk --limit 200    # smoke test
    uv run python -m app.scripts.refresh_gresham_bulk --page-size 500

On the production VM (inside the API container):
    docker compose exec vicinitideals-api \
        python -m app.scripts.refresh_gresham_bulk
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import time

from app.db import AsyncSessionLocal
from app.scrapers.arcgis import iter_all_gresham_taxlots
from app.scrapers.parcel_enrichment import _upsert_parcel

logger = logging.getLogger("refresh_gresham_bulk")

COMMIT_EVERY = 200


async def refresh(*, page_size: int, limit: int | None) -> dict[str, int]:
    seen = 0
    upserted = 0
    skipped = 0
    errors = 0

    started = time.monotonic()
    async with AsyncSessionLocal() as session:
        pending = 0
        async for record in iter_all_gresham_taxlots(page_size=page_size):
            seen += 1
            if not record.get("apn"):
                skipped += 1
                continue
            record.setdefault("county", "Multnomah")
            record.setdefault("jurisdiction", "gresham")
            try:
                await _upsert_parcel(session, record)
                upserted += 1
                pending += 1
            except Exception as exc:  # noqa: BLE001
                errors += 1
                logger.warning("Upsert failed for APN %r: %s", record.get("apn"), exc)

            if pending >= COMMIT_EVERY:
                await session.commit()
                pending = 0
                logger.info(
                    "progress: seen=%d upserted=%d skipped=%d errors=%d elapsed=%.1fs",
                    seen, upserted, skipped, errors, time.monotonic() - started,
                )

            if limit is not None and seen >= limit:
                break

        if pending:
            await session.commit()

    elapsed = time.monotonic() - started
    logger.info(
        "done: seen=%d upserted=%d skipped=%d errors=%d elapsed=%.1fs",
        seen, upserted, skipped, errors, elapsed,
    )
    return {"seen": seen, "upserted": upserted, "skipped": skipped, "errors": errors}


def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk-refresh Gresham parcels from ArcGIS.")
    parser.add_argument("--page-size", type=int, default=1000, help="Features per ArcGIS page.")
    parser.add_argument("--limit", type=int, default=None, help="Stop after N features (for smoke tests).")
    parser.add_argument("--log-level", default="INFO", help="Logging level (default: INFO).")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    asyncio.run(refresh(page_size=args.page_size, limit=args.limit))


if __name__ == "__main__":
    main()
