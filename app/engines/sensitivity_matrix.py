"""5x5 sensitivity matrix for the full cashflow engine.

Distinct from `sensitivity.py` (which uses the legacy DealInputs dataclass
from underwriting.py). This module operates on the live OperationalInputs
ORM model and the full compute_cash_flows pipeline, producing a matrix
suitable for display in the Sensitivity UI tab.

Approach:
- User picks two axes and a target metric.
- For each cell in the 5x5 grid, mutate OperationalInputs in-memory, call
  compute_cash_flows, extract the metric from the returned summary.
- After all 25 cells, restore the base-case values and run compute_cash_flows
  once more so the persisted CashFlow / OperationalOutputs rows are correct.
- Return a JSON-serializable dict for OperationalOutputs.sensitivity_matrix.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.cashflow import compute_cash_flows
from app.models.deal import OperationalInputs, Project

# ---------------------------------------------------------------------------
# Axis + metric registry
# ---------------------------------------------------------------------------

AXIS_SPECS: dict[str, dict[str, Any]] = {
    "exit_cap_rate_pct": {
        "label": "Exit Cap Rate (%)",
        "field": "exit_cap_rate_pct",
        "format": "pct",
        "default_step": Decimal("0.25"),
        "min": Decimal("3"),
        "max": Decimal("12"),
    },
    "expense_growth_rate_pct_annual": {
        "label": "Expense Growth (%)",
        "field": "expense_growth_rate_pct_annual",
        "format": "pct",
        "default_step": Decimal("0.5"),
        "min": Decimal("0"),
        "max": Decimal("10"),
    },
    "hold_period_years": {
        "label": "Hold Period (yrs)",
        "field": "hold_period_years",
        "format": "int",
        "default_step": Decimal("1"),
        "min": Decimal("3"),
        "max": Decimal("15"),
    },
    "noi_escalation_rate_pct": {
        "label": "NOI / Rent Growth (%)",
        "field": "noi_escalation_rate_pct",
        "format": "pct",
        "default_step": Decimal("0.5"),
        "min": Decimal("0"),
        "max": Decimal("10"),
    },
}

METRIC_SPECS: dict[str, dict[str, Any]] = {
    "project_irr_levered":   {"label": "Levered IRR (%)",      "format": "pct"},
    "project_irr_unlevered": {"label": "Unlevered IRR (%)",    "format": "pct"},
    "dscr":                  {"label": "DSCR",                 "format": "multiple"},
    "noi_stabilized":        {"label": "Stabilized NOI ($)",   "format": "currency"},
    "cap_rate_on_cost_pct":  {"label": "Cap Rate on Cost (%)", "format": "pct"},
    "debt_yield_pct":        {"label": "Debt Yield (%)",       "format": "pct"},
}

GRID_SIZE = 5


def _generate_axis_values(base: Decimal, spec: dict[str, Any]) -> list[Decimal]:
    """5 values centered on `base`, spaced by `default_step`, clamped to bounds."""
    step = spec["default_step"]
    lo = spec["min"]
    hi = spec["max"]
    half = (GRID_SIZE - 1) // 2
    values = [base + (Decimal(i - half) * step) for i in range(GRID_SIZE)]
    return [max(lo, min(hi, v)) for v in values]


async def compute_sensitivity_matrix(
    deal_model_id: UUID | str,
    session: AsyncSession,
    *,
    axis_x: str = "noi_escalation_rate_pct",
    axis_y: str = "exit_cap_rate_pct",
    metric: str = "project_irr_levered",
) -> dict[str, Any]:
    """Run 25 compute_cash_flows cycles; return a matrix dict.

    Shape:
    {
        "axis_x": {"field", "label", "format", "values": [5 floats]},
        "axis_y": {...},
        "metric": {"field", "label", "format"},
        "base_x_index": int, "base_y_index": int,
        "values": [[5 floats-or-None] × 5 rows],  # values[y][x]
    }
    """
    if axis_x not in AXIS_SPECS:
        raise ValueError(f"Unknown axis_x: {axis_x}")
    if axis_y not in AXIS_SPECS:
        raise ValueError(f"Unknown axis_y: {axis_y}")
    if axis_x == axis_y:
        raise ValueError("axis_x and axis_y must differ")
    if metric not in METRIC_SPECS:
        raise ValueError(f"Unknown metric: {metric}")

    deal_uuid = UUID(str(deal_model_id))
    spec_x = AXIS_SPECS[axis_x]
    spec_y = AXIS_SPECS[axis_y]

    project = (await session.execute(
        select(Project).where(Project.scenario_id == deal_uuid)
        .order_by(Project.created_at).limit(1)
    )).scalar_one_or_none()
    if project is None:
        raise ValueError(f"No project found for deal {deal_uuid}")
    inputs = (await session.execute(
        select(OperationalInputs).where(OperationalInputs.project_id == project.id)
    )).scalar_one_or_none()
    if inputs is None:
        raise ValueError(f"No OperationalInputs for project {project.id}")

    base_x = Decimal(str(getattr(inputs, spec_x["field"]) or 0))
    base_y = Decimal(str(getattr(inputs, spec_y["field"]) or 0))

    x_values = _generate_axis_values(base_x, spec_x)
    y_values = _generate_axis_values(base_y, spec_y)

    def _closest_idx(values: list[Decimal], target: Decimal) -> int:
        return min(range(len(values)), key=lambda i: abs(values[i] - target))

    base_x_idx = _closest_idx(x_values, base_x)
    base_y_idx = _closest_idx(y_values, base_y)

    grid: list[list[float | None]] = [[None] * GRID_SIZE for _ in range(GRID_SIZE)]

    for yi, yv in enumerate(y_values):
        setattr(inputs, spec_y["field"], yv)
        for xi, xv in enumerate(x_values):
            setattr(inputs, spec_x["field"], xv)
            session.add(inputs)
            await session.flush()
            try:
                summary = await compute_cash_flows(deal_model_id=deal_uuid, session=session)
                metric_val = summary.get(metric)
                grid[yi][xi] = float(metric_val) if metric_val is not None else None
            except Exception:  # noqa: BLE001
                grid[yi][xi] = None

    # Restore base values and refresh base-case persisted rows
    setattr(inputs, spec_x["field"], base_x)
    setattr(inputs, spec_y["field"], base_y)
    session.add(inputs)
    await session.flush()
    try:
        await compute_cash_flows(deal_model_id=deal_uuid, session=session)
    except Exception:  # noqa: BLE001
        pass  # Base case may have been invalid to begin with

    return {
        "axis_x": {
            "field": axis_x,
            "label": spec_x["label"],
            "format": spec_x["format"],
            "values": [float(v) for v in x_values],
        },
        "axis_y": {
            "field": axis_y,
            "label": spec_y["label"],
            "format": spec_y["format"],
            "values": [float(v) for v in y_values],
        },
        "metric": {
            "field": metric,
            "label": METRIC_SPECS[metric]["label"],
            "format": METRIC_SPECS[metric]["format"],
        },
        "base_x_index": base_x_idx,
        "base_y_index": base_y_idx,
        "values": grid,
    }
