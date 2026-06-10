"""
One-shot: reset debt_sizing_mode to gap_fill for Tower/Office Arbitrage
in scenario 4bc8fd71 (Combined Pool production).

These projects are zero-income buy-hold-sell deals. Gap fill is correct;
dual_constraint collapses to $0 bond because DSCR on $0 NOI = $0.

Usage:
    docker exec vicinitideals-api sh -c "cd /app && python scripts/fix_arbitrage_sizing_mode.py"
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import select
from app.db import AsyncSessionLocal
from app.models.deal import OperationalInputs
from app.models.project import Project

SCENARIO_ID = "4bc8fd71-788a-47c6-b6cd-c5325e84ddd6"
TARGET_NAMES = {"Tower Arbitrage", "Office Arbitrage"}


async def main() -> None:
    async with AsyncSessionLocal() as session:
        projects = list(
            (await session.execute(
                select(Project).where(Project.scenario_id == SCENARIO_ID)
            )).scalars()
        )
        targets = [p for p in projects if p.name in TARGET_NAMES]
        if not targets:
            print("ERROR: no matching projects found")
            sys.exit(1)

        for proj in targets:
            inputs = (await session.execute(
                select(OperationalInputs).where(OperationalInputs.project_id == proj.id)
            )).scalar_one_or_none()
            if inputs is None:
                print(f"  SKIP {proj.name}: no operational_inputs row")
                continue
            old = inputs.debt_sizing_mode
            inputs.debt_sizing_mode = "gap_fill"
            print(f"  {proj.name}: {old!r} → 'gap_fill'")

        await session.commit()
        print("\nDone. Recompute the scenario to apply.")


if __name__ == "__main__":
    asyncio.run(main())
