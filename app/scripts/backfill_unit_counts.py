"""One-shot: backfill operational_inputs.unit_count_new from income_streams.

Sets unit_count_new = SUM(income_streams.unit_count) per project
where income stream units > 0 and unit_count_new is currently 0 or null.

Run once: uv run python app/scripts/backfill_unit_counts.py
"""
import asyncio
from sqlalchemy import select, func, update
from app.db import AsyncSessionLocal
from app.models.deal import IncomeStream, OperationalInputs
from app.models.project import Project


async def main() -> None:
    async with AsyncSessionLocal() as session:
        # Sum income stream unit_count per project
        stream_sums = await session.execute(
            select(
                IncomeStream.project_id,
                func.sum(IncomeStream.unit_count).label("total_units"),
            )
            .where(IncomeStream.unit_count.isnot(None), IncomeStream.unit_count > 0)
            .group_by(IncomeStream.project_id)
        )
        rows = stream_sums.all()

        updated = 0
        skipped = 0
        for project_id, total_units in rows:
            # Fetch operational_inputs for this project
            oi_row = await session.execute(
                select(OperationalInputs).where(
                    OperationalInputs.project_id == project_id
                )
            )
            oi = oi_row.scalar_one_or_none()
            if oi is None:
                print(f"  SKIP project {project_id}: no operational_inputs row")
                skipped += 1
                continue

            existing = int(oi.unit_count_new or 0)
            if existing > 0:
                print(
                    f"  SKIP project {project_id}: unit_count_new already {existing}"
                )
                skipped += 1
                continue

            # Look up project name for logging
            proj = await session.get(Project, project_id)
            name = proj.name if proj else str(project_id)

            oi.unit_count_new = total_units
            print(f"  SET '{name}': unit_count_new = {total_units}")
            updated += 1

        await session.commit()
        print(f"\nDone. Updated {updated}, skipped {skipped}.")


if __name__ == "__main__":
    asyncio.run(main())
