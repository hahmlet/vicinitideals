"""5x5 sensitivity matrix for the full cashflow engine.

Distinct from `sensitivity.py` (which uses the legacy DealInputs dataclass
from underwriting.py). This module operates on the live OperationalInputs
ORM model and the full compute_cash_flows pipeline, producing a matrix
suitable for display in the Sensitivity UI tab and the investor Excel
export.

Two modes:
- ``mode="first"`` (default, back-compat): mutate only the first project's
  OperationalInputs. Suitable for single-project scenarios and the existing
  UI Sensitivity tab. Cell value = last project's summary metric.
- ``mode="combined"``: mutate every project's OperationalInputs in lockstep.
  For ``metric="project_irr_levered"`` the cell value is the combined
  Levered IRR computed via ``rollup_irr`` over the summed monthly NCF
  series across all projects. Required for the investor export, which
  must report deal-level (not single-project) returns.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.cashflow import compute_cash_flows
from app.engines.underwriting_rollup import rollup_irr
from app.models.deal import OperationalInputs
from app.models.project import Project

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
        "default_step": Decimal("0.25"),
        "min": Decimal("0"),
        "max": Decimal("10"),
    },
    "noi_escalation_rate_pct": {
        "label": "NOI / Rent Growth (%)",
        "field": "noi_escalation_rate_pct",
        "format": "pct",
        "default_step": Decimal("0.25"),
        "min": Decimal("0"),
        "max": Decimal("10"),
    },
}

METRIC_SPECS: dict[str, dict[str, Any]] = {
    "project_irr_levered":   {"label": "Levered IRR (%)",      "format": "pct"},
    "project_irr_unlevered": {"label": "Unlevered IRR (%)",    "format": "pct"},
    "dscr":                  {"label": "DSCR",                 "format": "multiple"},
    "noi_stabilized":        {"label": "Stabilized NOI ($)",   "format": "currency"},
    "noi_exit_year":         {"label": "Exit Year NOI ($)",    "format": "currency"},
    "cap_rate_on_cost_pct":  {"label": "Cap Rate on Cost (%)", "format": "pct"},
    "debt_yield_pct":        {"label": "Debt Yield (%)",       "format": "pct"},
}

GRID_SIZE = 5


def _generate_axis_values(
    base: Decimal, spec: dict[str, Any], step_override: Decimal | None = None
) -> list[Decimal]:
    """5 distinct values spaced by `step` (override or `default_step`),
    sliding off-center if the centered window would cross `min` or `max`.

    Plain clamping produces duplicates when the base sits at (or near) a
    boundary — e.g. base=0, step=0.5 gave [0, 0, 0, 0.5, 1]. Here we slide
    the whole window so all 5 cells stay inside [min, max] and distinct.
    """
    step = step_override if step_override is not None else spec["default_step"]
    lo = spec["min"]
    hi = spec["max"]
    half = Decimal((GRID_SIZE - 1) // 2)
    span = Decimal(GRID_SIZE - 1) * step

    start = base - half * step
    if start < lo:
        start = lo
    end = start + span
    if end > hi:
        end = hi
        start = max(lo, end - span)
        if end - start < span:
            # Range too tight for the configured step: spread evenly.
            step = (end - start) / Decimal(GRID_SIZE - 1) if end > start else Decimal("0")
    return [start + Decimal(i) * step for i in range(GRID_SIZE)]


async def compute_sensitivity_matrix(
    deal_model_id: UUID | str,
    session: AsyncSession,
    *,
    axis_x: str = "noi_escalation_rate_pct",
    axis_y: str = "exit_cap_rate_pct",
    metric: str = "project_irr_levered",
    mode: Literal["first", "combined"] = "first",
    step_overrides: dict[str, Decimal] | None = None,
) -> dict[str, Any]:
    """Run 25 compute_cash_flows cycles; return a matrix dict.

    Args:
      mode:
        - "first" (default): mutate only the first project's
          OperationalInputs and read metric from the last summary.
        - "combined": mutate all projects' OperationalInputs in lockstep.
          For ``metric="project_irr_levered"`` returns the deal-level
          combined IRR (rollup over summed NCF). For other metrics the
          last-project summary value is used (caller's responsibility).
      step_overrides: optional dict mapping axis field name → Decimal step
        size to override the registry's ``default_step`` for that axis.

    Shape:
    {
        "axis_x": {"field", "label", "format", "values": [5 floats]},
        "axis_y": {...},
        "metric": {"field", "label", "format"},
        "mode": "first" | "combined",
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
    if mode not in ("first", "combined"):
        raise ValueError(f"Unknown mode: {mode}")

    deal_uuid = UUID(str(deal_model_id))
    spec_x = AXIS_SPECS[axis_x]
    spec_y = AXIS_SPECS[axis_y]
    overrides = step_overrides or {}

    projects_q = (await session.execute(
        select(Project).where(Project.scenario_id == deal_uuid)
        .order_by(Project.created_at)
    )).scalars().all()
    if not projects_q:
        raise ValueError(f"No project found for deal {deal_uuid}")

    if mode == "first":
        target_projects = [projects_q[0]]
    else:
        target_projects = list(projects_q)

    inputs_rows: list[OperationalInputs] = []
    for project in target_projects:
        row = (await session.execute(
            select(OperationalInputs).where(OperationalInputs.project_id == project.id)
        )).scalar_one_or_none()
        if row is None:
            if mode == "first":
                raise ValueError(f"No OperationalInputs for project {project.id}")
            # Combined mode: skip orphan projects without inputs
            continue
        inputs_rows.append(row)
    if not inputs_rows:
        raise ValueError(f"No OperationalInputs found for deal {deal_uuid}")

    # Use the first inputs row as the basis for the axis windows. In combined
    # mode we still slide a single shared window across all projects so the
    # grid axes stay legible — the alternative (per-project axes) cannot be
    # rendered as a single 5x5 table.
    anchor = inputs_rows[0]
    base_x = Decimal(str(getattr(anchor, spec_x["field"]) or 0))
    base_y = Decimal(str(getattr(anchor, spec_y["field"]) or 0))

    x_values = _generate_axis_values(base_x, spec_x, overrides.get(spec_x["field"]))
    y_values = _generate_axis_values(base_y, spec_y, overrides.get(spec_y["field"]))

    def _closest_idx(values: list[Decimal], target: Decimal) -> int:
        return min(range(len(values)), key=lambda i: abs(values[i] - target))

    base_x_idx = _closest_idx(x_values, base_x)
    base_y_idx = _closest_idx(y_values, base_y)

    # Snapshot per-project base values so we can restore exactly after the run
    base_snapshot: list[tuple[OperationalInputs, Decimal, Decimal]] = [
        (
            row,
            Decimal(str(getattr(row, spec_x["field"]) or 0)),
            Decimal(str(getattr(row, spec_y["field"]) or 0)),
        )
        for row in inputs_rows
    ]

    grid: list[list[float | None]] = [[None] * GRID_SIZE for _ in range(GRID_SIZE)]

    for yi, yv in enumerate(y_values):
        for row in inputs_rows:
            setattr(row, spec_y["field"], yv)
        for xi, xv in enumerate(x_values):
            for row in inputs_rows:
                setattr(row, spec_x["field"], xv)
                session.add(row)
            await session.flush()
            try:
                summary = await compute_cash_flows(
                    deal_model_id=deal_uuid, session=session
                )
                if mode == "combined" and metric == "project_irr_levered":
                    irr_decimal = await rollup_irr(deal_uuid, session)
                    grid[yi][xi] = float(irr_decimal) if irr_decimal is not None else None
                else:
                    metric_val = summary.get(metric)
                    grid[yi][xi] = float(metric_val) if metric_val is not None else None
            except Exception:  # noqa: BLE001
                grid[yi][xi] = None

    # Restore base values per-project and refresh persisted rows
    for row, bx, by in base_snapshot:
        setattr(row, spec_x["field"], bx)
        setattr(row, spec_y["field"], by)
        session.add(row)
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
        "mode": mode,
        "base_x_index": base_x_idx,
        "base_y_index": base_y_idx,
        "values": grid,
    }
