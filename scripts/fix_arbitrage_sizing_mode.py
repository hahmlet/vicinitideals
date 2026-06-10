"""
One-shot: reset debt_sizing_mode to gap_fill for Tower/Office Arbitrage
in scenario 4bc8fd71 (Combined Pool production).

These projects are zero-income buy-hold-sell deals. gap_fill is correct;
dual_constraint collapses bond to $0 because DSCR on $0 NOI = $0.

Usage:
    docker exec vicinitideals-api sh -c "cd /app && python scripts/fix_arbitrage_sizing_mode.py"
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text
from app.db import AsyncSessionLocal

# operational_inputs.id for Tower/Office Arbitrage in scenario 4bc8fd71
TARGET_OI_IDS = (
    "86efe545-fd3d-4d55-bdb4-bb49c9f33deb",   # Office Arbitrage
    "7d5cfd9a-d793-44f1-be36-bf29c26ac6d6",   # Tower Arbitrage
)


async def main() -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                "UPDATE operational_inputs "
                "SET debt_sizing_mode = 'gap_fill' "
                "WHERE id = ANY(:ids) "
                "RETURNING id, debt_sizing_mode"
            ),
            {"ids": list(TARGET_OI_IDS)},
        )
        rows = result.fetchall()
        for row in rows:
            print(f"  Updated {row[0]} → {row[1]!r}")
        if not rows:
            print("ERROR: no rows updated — check IDs")
            sys.exit(1)
        await session.commit()
        print(f"\nDone ({len(rows)} rows). Recompute the scenario to apply.")


if __name__ == "__main__":
    asyncio.run(main())
