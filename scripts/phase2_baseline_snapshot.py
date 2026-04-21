"""Capture canonical output state for a handful of single-project Scenarios.

Used as the byte-identical ground-truth for Phase 2 engine refactor: run this
BEFORE any engine change to get a baseline, then re-run AFTER the refactor and
diff the JSON files. Any delta means the refactor perturbed existing math.

Output: one JSON file per scenario at /tmp/phase2_baseline/<scenario_id>.json
containing cash_flows, operational_outputs, waterfall_results, and capital
module sized amounts — everything a Scenario writes to the DB during compute.

Usage (inside the vicinitideals-api container):
  python /app/scripts/phase2_baseline_snapshot.py SCENARIO_ID [SCENARIO_ID ...]

Decimals are serialized as strings via str(Decimal) so round-trip diffs do not
lose precision.
"""

from __future__ import annotations

import asyncio
import json
import sys
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models.capital import CapitalModule, WaterfallResult, WaterfallTier
from app.models.cashflow import CashFlow, CashFlowLineItem, OperationalOutputs


def _j(v):  # JSON-safe conversion
    if isinstance(v, Decimal):
        return str(v)
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if hasattr(v, "hex") and hasattr(v, "version"):
        return str(v)
    return v


def _row(obj, fields: list[str]) -> dict:
    return {f: _j(getattr(obj, f, None)) for f in fields}


_CF_FIELDS = [
    "period", "period_date", "period_type",
    "revenue", "opex", "noi", "debt_service", "capex",
    "net_cash_flow", "cash_balance",
    "outstanding_debt_balance",
]

_LI_FIELDS = [
    "period", "category", "label", "amount",
    "income_stream_id", "capital_module_id",
]

_OP_FIELDS = [
    "total_project_cost", "equity_required", "noi_stabilized",
    "dscr", "ltv", "project_irr_levered", "project_irr_unlevered",
    "moic", "cash_on_cash_pct", "yield_on_cost_pct",
    "total_timeline_months", "stabilized_period_start",
]

_WR_FIELDS = [
    "period", "tier_id", "capital_module_id",
    "cash_distributed", "cumulative_distributed", "party_irr_pct",
]


async def snapshot(scenario_id: UUID, out_dir: Path) -> None:
    async with AsyncSessionLocal() as session:
        cf_rows = list((await session.execute(
            select(CashFlow).where(CashFlow.scenario_id == scenario_id)
            .order_by(CashFlow.period)
        )).scalars())
        li_rows = list((await session.execute(
            select(CashFlowLineItem).where(CashFlowLineItem.scenario_id == scenario_id)
            .order_by(CashFlowLineItem.period, CashFlowLineItem.label)
        )).scalars())
        op = (await session.execute(
            select(OperationalOutputs).where(OperationalOutputs.scenario_id == scenario_id)
        )).scalar_one_or_none()
        tiers = list((await session.execute(
            select(WaterfallTier).where(WaterfallTier.scenario_id == scenario_id)
            .order_by(WaterfallTier.priority)
        )).scalars())
        tier_id_to_priority = {t.id: t.priority for t in tiers}
        wr_rows = list((await session.execute(
            select(WaterfallResult).where(WaterfallResult.scenario_id == scenario_id)
            .order_by(WaterfallResult.period)
        )).scalars())
        # Stable ordering for waterfall rows: (period, tier.priority, module_id)
        wr_rows.sort(key=lambda r: (r.period, tier_id_to_priority.get(r.tier_id, 999), str(r.capital_module_id)))
        modules = list((await session.execute(
            select(CapitalModule).where(CapitalModule.scenario_id == scenario_id)
            .order_by(CapitalModule.stack_position)
        )).scalars())

    snapshot = {
        "scenario_id": str(scenario_id),
        "cash_flows": [_row(cf, _CF_FIELDS) for cf in cf_rows],
        "cash_flow_line_items": [_row(li, _LI_FIELDS) for li in li_rows],
        "operational_outputs": _row(op, _OP_FIELDS) if op else None,
        "waterfall_results": [
            {**_row(wr, _WR_FIELDS),
             "tier_priority": tier_id_to_priority.get(wr.tier_id, 999)}
            for wr in wr_rows
        ],
        "capital_modules": [
            {"id": str(cm.id), "label": cm.label, "funder_type": cm.funder_type,
             "stack_position": cm.stack_position,
             "source_amount": _j((cm.source or {}).get("amount")),
             "source_auto_size": (cm.source or {}).get("auto_size"),
             "active_phase_start": cm.active_phase_start,
             "active_phase_end": cm.active_phase_end}
            for cm in modules
        ],
    }

    out_path = out_dir / f"{scenario_id}.json"
    out_path.write_text(json.dumps(snapshot, indent=2, default=_j, sort_keys=True))
    print(f"wrote {out_path}  cf={len(cf_rows)}  wr={len(wr_rows)}  modules={len(modules)}")


async def main(ids: list[str]) -> None:
    out_dir = Path("/tmp/phase2_baseline")
    out_dir.mkdir(parents=True, exist_ok=True)
    for sid in ids:
        await snapshot(UUID(sid), out_dir)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: phase2_baseline_snapshot.py SCENARIO_ID [...]")
        sys.exit(2)
    asyncio.run(main(sys.argv[1:]))
