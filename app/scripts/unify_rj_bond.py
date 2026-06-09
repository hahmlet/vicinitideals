"""One-shot: unify the 8 per-project "Raymond James Bond" modules into ONE
shared module on the Unified Underwriting host scenario.

The consolidation script created a standalone CapitalModule per project (one
junction each), so the pooled view listed 8 "Raymond James Bond" rows. The
engine already supports a single Source split across projects via the
capital_module_projects junction (Phase D reconciles module.source["amount"]
to Σ junction amounts; each project sizes its own slice). This collapses the
8 modules into one survivor carrying all 8 project slices.

Also corrects the one slice mistakenly entered at 5.5% — the unified bond is a
single 6.0% facility carried to maturity (terms are module-level, so a single
survivor at 6.0% applies to every slice).

Idempotent: re-running after unification is a no-op (only one bond module
remains, so nothing to merge).

Run on VM 114:
    docker exec vicinitideals-api python -m app.scripts.unify_rj_bond
Then recompute the scenario twice (float<->bond gap-fill needs two passes).
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.models.capital import CapitalModule, CapitalModuleProject
from app.models.deal import UseLine

try:  # WaterfallTier lives in app.models.capital in this codebase
    from app.models.capital import WaterfallTier
except ImportError:  # pragma: no cover - defensive
    WaterfallTier = None  # type: ignore[assignment]

SCENARIO_ID = UUID("4bc8fd71-788a-47c6-b6cd-c5325e84ddd6")
LABEL = "Raymond James Bond"
UNIFIED_RATE = "6.0"


async def unify(
    session: AsyncSession,
    scenario_id: UUID,
    *,
    label: str = LABEL,
    unified_rate: str = UNIFIED_RATE,
) -> dict:
    """Collapse all ``label`` modules on ``scenario_id`` into one survivor.

    Repoints use-line routing, waterfall tiers, project junctions and
    float-earnings parent pointers onto the survivor, then deletes the empty
    siblings. Returns a summary dict. Caller commits.
    """
    mods = list(
        (
            await session.execute(
                select(CapitalModule)
                .where(
                    CapitalModule.scenario_id == scenario_id,
                    CapitalModule.label == label,
                )
                .order_by(CapitalModule.stack_position, CapitalModule.id)
            )
        ).scalars()
    )
    if len(mods) <= 1:
        return {"merged": 0, "survivor": str(mods[0].id) if mods else None}

    def _rate(m: CapitalModule) -> str:
        return str((m.source or {}).get("interest_rate_pct") or "")

    # Survivor: prefer a clean 6.0% module already in the senior stack slot.
    survivor = next(
        (m for m in mods if _rate(m) == unified_rate and m.stack_position == 1),
        mods[0],
    )
    others = [m for m in mods if m.id != survivor.id]
    other_ids = [m.id for m in others]
    all_ids = [m.id for m in mods]

    # Distinctness guard — merged junctions must not collide on
    # (capital_module_id, project_id).
    jproj = list(
        (
            await session.execute(
                select(CapitalModuleProject.project_id).where(
                    CapitalModuleProject.capital_module_id.in_(all_ids)
                )
            )
        ).scalars()
    )
    assert len(jproj) == len(set(jproj)), "bond modules share a project — abort"

    # 1. Repoint explicit use-line source routing (FK is SET NULL — repoint to
    #    keep the routing instead of silently nulling it).
    ul_res = await session.execute(
        update(UseLine)
        .where(UseLine.source_capital_module_id.in_(other_ids))
        .values(source_capital_module_id=survivor.id)
    )

    # 2. Repoint waterfall tiers (NO ACTION FK — must move before delete).
    wt_count = 0
    if WaterfallTier is not None:
        wt_res = await session.execute(
            update(WaterfallTier)
            .where(WaterfallTier.capital_module_id.in_(other_ids))
            .values(capital_module_id=survivor.id)
        )
        wt_count = wt_res.rowcount

    # 3. Repoint per-project junctions onto the survivor (CASCADE FK — repoint
    #    BEFORE deleting modules so the slices survive).
    cmp_res = await session.execute(
        update(CapitalModuleProject)
        .where(CapitalModuleProject.capital_module_id.in_(other_ids))
        .values(capital_module_id=survivor.id)
    )

    # 4. Repoint float-earnings parent_module_id pointers that referenced a
    #    soon-to-be-deleted bond slice.
    floats = list(
        (
            await session.execute(
                select(CapitalModule).where(
                    CapitalModule.scenario_id == scenario_id,
                    CapitalModule.vehicle_type == "float_earnings",
                )
            )
        ).scalars()
    )
    repointed_floats = 0
    for fm in floats:
        src = dict(fm.source or {})
        parent = src.get("parent_module_id")
        if parent and UUID(str(parent)) in set(other_ids):
            src["parent_module_id"] = str(survivor.id)
            fm.source = src
            repointed_floats += 1

    # 5. Normalize survivor terms: single 6.0% facility, carried to maturity,
    #    senior stack slot, amount = Σ of all project slices.
    total = Decimal("0")
    for amt in (
        await session.execute(
            select(CapitalModuleProject.amount).where(
                CapitalModuleProject.capital_module_id == survivor.id
            )
        )
    ).scalars():
        total += Decimal(str(amt or 0))

    src = dict(survivor.source or {})
    src["interest_rate_pct"] = unified_rate
    src["amount"] = str(total)
    survivor.source = src
    et = dict(survivor.exit_terms or {})
    et["vehicle"] = "maturity"
    survivor.exit_terms = et
    survivor.stack_position = 1

    # 6. Delete the now-empty sibling modules.
    for m in others:
        await session.delete(m)
    await session.flush()

    return {
        "merged": len(others),
        "survivor": str(survivor.id),
        "slices": len(jproj),
        "use_lines_repointed": ul_res.rowcount,
        "waterfall_tiers_repointed": wt_count,
        "junctions_repointed": cmp_res.rowcount,
        "float_parents_repointed": repointed_floats,
        "total": str(total),
        "rate": unified_rate,
    }


async def main() -> None:
    async with AsyncSessionLocal() as session:
        summary = await unify(session, SCENARIO_ID)
        if not summary.get("merged"):
            print(f"Nothing to do — survivor {summary.get('survivor')}.")
            return
        await session.commit()
        print(summary)


if __name__ == "__main__":
    asyncio.run(main())
