"""Engine snapshot helpers — safety net for the cashflow.py compile/evaluate refactor.

Captures the full persisted engine state (CashFlow, CashFlowLineItem,
OperationalOutputs, post-auto-size CapitalModule.source.amount) for a scenario,
serializes it deterministically to JSON, and compares against a checked-in
snapshot file. A byte-level mismatch fails the test with a unified diff.

Run normally to verify equivalence:

    uv run pytest tests/engines/test_engine_snapshots.py -q

Regenerate snapshots when the engine is intentionally changed:

    SNAPSHOT_UPDATE=1 uv run pytest tests/engines/test_engine_snapshots.py -q

Complementary tooling (for the prod-data half of refactor verification):
    scripts/phase2_baseline_snapshot.py  — snapshots real prod scenarios
    scripts/phase2_verify_byte_identical.py  — re-runs and diffs them
    tests/phase2_baseline/  — checked-in baselines from real prod data

This module covers seeded, deterministic, in-memory cases (CI-friendly,
no DB dependency). The phase2 scripts cover real production scenarios.
Use both before merging an engine refactor.
"""

from __future__ import annotations

import difflib
import json
import os
import re
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

from app.models.capital import CapitalModule
from app.models.cashflow import CashFlow, CashFlowLineItem, OperationalOutputs
from app.models.project import Project

SNAPSHOT_DIR = Path(__file__).parent / "snapshots"
SNAPSHOT_UPDATE_ENV = "SNAPSHOT_UPDATE"


def _strip_uuids(value: Any) -> Any:
    """Recursively replace UUID-shaped strings with the literal "<uuid>".

    Engine output embeds raw UUIDs (use_line_id, capital_module_id, etc.) into
    JSON columns like ``CashFlowLineItem.adjustments``. Auto-generated UUIDs
    differ across runs, so leaving them in the snapshot makes it nondeterministic.
    Identity references aren't load-bearing for engine math equivalence, so we
    flatten them to a sentinel.
    """
    if isinstance(value, dict):
        return {k: _strip_uuids(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_strip_uuids(item) for item in value]
    if isinstance(value, str) and _UUID_RE.match(value):
        return "<uuid>"
    return value


def _decimal_str(value: Any) -> str | None:
    """Render a Decimal/None deterministically.

    Strips trailing-zero-only fractional drift so 1.000000 and 1.0 collapse to
    "1.000000" (the engine's canonical six-place quantization). Anything that
    comes through as None stays None.
    """
    if value is None:
        return None
    d = Decimal(str(value))
    return f"{d:.6f}"


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _decimal_str(value)
    if isinstance(value, UUID):
        return str(value)
    if hasattr(value, "value"):
        return value.value
    return str(value)


def _project_index_map(projects: list[Project]) -> dict[UUID, int]:
    """Map project_id → stable ordinal so snapshots don't churn on UUID drift.

    Projects ordered by created_at — matches the engine's compute order — so
    project 0 is the deal's first project, project 1 the second, etc.
    """
    sorted_projects = sorted(projects, key=lambda p: (p.created_at or 0, p.name or ""))
    return {p.id: idx for idx, p in enumerate(sorted_projects)}


async def serialize_engine_state(
    session: AsyncSession, scenario_id: UUID
) -> str:
    """Gather all engine output rows for a scenario, return canonical JSON.

    Output structure:
        {
          "cash_flows": [ {"project_idx", "period", "period_type", ...money fields...}, ... ],
          "cash_flow_line_items": [ ... ],
          "operational_outputs": [ {"project_idx", ...metric fields...}, ... ],
          "capital_modules": [ {"funder_type", "stack_position", "source_amount"}, ... ]
        }

    Volatile fields are stripped: row UUIDs (replaced with stable ordinals
    derived from join keys), computed_at timestamps (replaced with the literal
    "<computed>" sentinel when present, None otherwise).
    """
    project_rows = (
        (await session.execute(select(Project).where(Project.scenario_id == scenario_id))).scalars().all()
    )
    project_idx = _project_index_map(list(project_rows))

    def _pidx(pid: UUID | None) -> int | None:
        return project_idx.get(pid) if pid else None

    cash_flows = (
        (
            await session.execute(
                select(CashFlow)
                .where(CashFlow.scenario_id == scenario_id)
                .order_by(CashFlow.project_id, CashFlow.period)
            )
        )
        .scalars()
        .all()
    )
    cash_flow_line_items = (
        (
            await session.execute(
                select(CashFlowLineItem)
                .where(CashFlowLineItem.scenario_id == scenario_id)
                .order_by(
                    CashFlowLineItem.project_id,
                    CashFlowLineItem.period,
                    CashFlowLineItem.category,
                    CashFlowLineItem.label,
                )
            )
        )
        .scalars()
        .all()
    )
    operational_outputs = (
        (
            await session.execute(
                select(OperationalOutputs)
                .where(OperationalOutputs.scenario_id == scenario_id)
                .order_by(OperationalOutputs.project_id)
            )
        )
        .scalars()
        .all()
    )
    capital_modules = (
        (
            await session.execute(
                select(CapitalModule)
                .where(CapitalModule.scenario_id == scenario_id)
                .order_by(CapitalModule.stack_position, CapitalModule.label)
            )
        )
        .scalars()
        .all()
    )

    payload: dict[str, list[dict[str, Any]]] = {
        "cash_flows": [
            {
                "project_idx": _pidx(cf.project_id),
                "period": cf.period,
                "period_type": getattr(cf.period_type, "value", cf.period_type),
                "gross_revenue": _decimal_str(cf.gross_revenue),
                "vacancy_loss": _decimal_str(cf.vacancy_loss),
                "effective_gross_income": _decimal_str(cf.effective_gross_income),
                "operating_expenses": _decimal_str(cf.operating_expenses),
                "capex_reserve": _decimal_str(cf.capex_reserve),
                "noi": _decimal_str(cf.noi),
                "debt_service": _decimal_str(cf.debt_service),
                "net_cash_flow": _decimal_str(cf.net_cash_flow),
                "cumulative_cash_flow": _decimal_str(cf.cumulative_cash_flow),
            }
            for cf in cash_flows
        ],
        "cash_flow_line_items": [
            {
                "project_idx": _pidx(li.project_id),
                "period": li.period,
                "category": getattr(li.category, "value", li.category),
                "label": li.label,
                "base_amount": _decimal_str(li.base_amount),
                "adjustments": _strip_uuids(li.adjustments),
                "net_amount": _decimal_str(li.net_amount),
            }
            for li in cash_flow_line_items
        ],
        "operational_outputs": [
            {
                "project_idx": _pidx(o.project_id),
                "total_project_cost": _decimal_str(o.total_project_cost),
                "equity_required": _decimal_str(o.equity_required),
                "total_timeline_months": o.total_timeline_months,
                "noi_stabilized": _decimal_str(o.noi_stabilized),
                "cap_rate_on_cost_pct": _decimal_str(o.cap_rate_on_cost_pct),
                "dscr": _decimal_str(o.dscr),
                "project_irr_levered": _decimal_str(o.project_irr_levered),
                "project_irr_unlevered": _decimal_str(o.project_irr_unlevered),
                "debt_yield_pct": _decimal_str(o.debt_yield_pct),
                "computed_at": "<computed>" if o.computed_at else None,
            }
            for o in operational_outputs
        ],
        "capital_modules": [
            {
                "stack_position": cm.stack_position,
                "funder_type": getattr(cm.funder_type, "value", cm.funder_type),
                "label": cm.label,
                "source_amount": _decimal_str((cm.source or {}).get("amount")),
                "source_construction_retirement": _decimal_str(
                    (cm.source or {}).get("construction_retirement")
                ),
            }
            for cm in capital_modules
        ],
    }

    return json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n"


def assert_matches_snapshot(actual: str, snapshot_name: str) -> None:
    """Compare a serialized engine state to a checked-in snapshot.

    On mismatch, prints a unified diff and fails the test. When the
    SNAPSHOT_UPDATE env var is set to a truthy value, overwrites the snapshot
    file instead — use this when intentionally changing engine output.
    """
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_path = SNAPSHOT_DIR / f"{snapshot_name}.json"

    if os.environ.get(SNAPSHOT_UPDATE_ENV):
        snapshot_path.write_text(actual, encoding="utf-8")
        return

    if not snapshot_path.exists():
        snapshot_path.write_text(actual, encoding="utf-8")
        raise AssertionError(
            f"Snapshot {snapshot_path.name} did not exist; wrote it now. "
            "Re-run the test to confirm stability."
        )

    expected = snapshot_path.read_text(encoding="utf-8")
    if actual == expected:
        return

    diff = "".join(
        difflib.unified_diff(
            expected.splitlines(keepends=True),
            actual.splitlines(keepends=True),
            fromfile=f"snapshot/{snapshot_name}.json",
            tofile=f"actual/{snapshot_name}.json",
            n=3,
        )
    )
    raise AssertionError(
        f"Engine output drifted from snapshot {snapshot_name!r}.\n"
        f"Run `SNAPSHOT_UPDATE=1 pytest tests/engines/test_engine_snapshots.py` "
        f"to accept the new output if intended.\n\n{diff}"
    )
