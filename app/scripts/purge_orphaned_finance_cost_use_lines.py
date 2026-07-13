"""One-shot cleanup: delete orphaned auto-generated Total Finance Costs UseLines.

Prior consolidation/rebuild one-shots (e.g. unify_rj_bond.py,
rebuild_edgemont_variant.py) deleted or replaced CapitalModule rows without
cleaning up dependent UseLine.source_capital_module_id references. The
cashflow engine's writeback pass matches existing "{module.label} — Total
Finance Costs" rows by source_capital_module_id, so an orphaned row (NULL FK,
or FK pointing at a module no longer linked to that project) is never found
and a fresh row gets written for the surviving module — leaving the orphan
behind as a duplicate Uses line every compute.

The engine now self-heals this on every compute (see cashflow.py
"CC-WRITEBACK guard" block), but existing orphans already in the DB won't be
touched until each affected project is recomputed. This script deletes them
directly so the Sources & Uses panel is correct immediately, without waiting
on (or forcing) a recompute of every affected deal.

Dry-run by default; pass --apply to delete.

    python -m app.scripts.purge_orphaned_finance_cost_use_lines
    python -m app.scripts.purge_orphaned_finance_cost_use_lines --apply
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import delete, select

from app.db import AsyncSessionLocal
from app.models.capital import CapitalModuleProject
from app.models.deal import UseLine


async def _main(apply: bool) -> None:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(UseLine).where(UseLine.is_auto_finance_cost == True)  # noqa: E712
            )
        ).scalars().all()
        print(f"Scanned {len(rows)} auto-finance-cost use_lines.")

        junctions = (await session.execute(select(CapitalModuleProject))).scalars().all()
        live_by_project: dict = {}
        for j in junctions:
            live_by_project.setdefault(j.project_id, set()).add(j.capital_module_id)

        orphans = [
            r for r in rows
            if r.source_capital_module_id is None
            or r.source_capital_module_id not in live_by_project.get(r.project_id, set())
        ]
        print(f"{len(orphans)} are orphaned (NULL FK or FK not linked to their project).")
        by_project: dict[str, int] = {}
        for r in orphans:
            key = str(r.project_id)
            by_project[key] = by_project.get(key, 0) + 1
        for pid, n in sorted(by_project.items(), key=lambda kv: -kv[1]):
            print(f"  {n:>3} × project {pid}")

        if not orphans:
            print("Nothing to delete.")
            return

        total_amount = sum((r.amount or 0) for r in orphans)
        print(f"Total orphaned amount: {total_amount}")

        if apply:
            ids = [r.id for r in orphans]
            await session.execute(delete(UseLine).where(UseLine.id.in_(ids)))
            await session.commit()
            print(f"DELETED {len(ids)} rows.")
        else:
            print("DRY RUN (no commit).  Re-run with --apply to delete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Actually delete rows.")
    args = parser.parse_args()
    asyncio.run(_main(apply=args.apply))
