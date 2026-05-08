"""Retroactive polygon filter — archive scraper-sourced opportunities outside all DB polygons.

Targets only: non-archived, org_id IS NULL (unlinked), promotion_source in loopnet/crexi/scraper.
Portland land exclusion applies: land listings only match non-portland polygons.

Usage:
    uv run python app/scripts/retroactive_polygon_filter.py          # live run
    uv run python app/scripts/retroactive_polygon_filter.py --dry-run
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models.opportunity import Opportunity
from app.scrapers.geo_utils import load_all_polygons_from_db, point_in_polygon

DRY_RUN = "--dry-run" in sys.argv


def _passes_filter(opp: Opportunity, polygons: list[dict[str, Any]]) -> bool:
    if not opp.lat or not opp.lng:
        return True  # no coords — can't filter, keep
    lat = float(opp.lat)
    lng = float(opp.lng)
    is_land = "land" in (opp.property_type or "").lower()
    for poly in polygons:
        if not point_in_polygon(poly["points"], lng, lat):
            continue
        if is_land and poly["name"] == "portland":
            continue
        return True
    return False


async def main() -> None:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        polygons = await load_all_polygons_from_db(session)
        if not polygons:
            print("No polygons in DB — aborting (would archive everything).")
            await engine.dispose()
            return
        print(f"Loaded {len(polygons)} polygons from DB.")

        opps = (
            await session.execute(
                select(Opportunity).where(
                    Opportunity.archived == False,  # noqa: E712
                    Opportunity.org_id.is_(None),
                    Opportunity.promotion_source.in_(["loopnet", "crexi", "scraper"]),
                )
            )
        ).scalars().all()
        print(f"Checking {len(opps)} scraper-sourced unlinked opportunities...")

        to_archive: list[uuid.UUID] = []
        for opp in opps:
            if not _passes_filter(opp, polygons):
                to_archive.append(opp.id)

        print(f"Found {len(to_archive)} to archive.")

        if DRY_RUN:
            print("DRY RUN — no changes made.")
        elif to_archive:
            await session.execute(
                update(Opportunity)
                .where(Opportunity.id.in_(to_archive))
                .values(archived=True)
            )
            await session.commit()
            print(f"Archived {len(to_archive)} opportunities.")
        else:
            print("Nothing to archive.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
