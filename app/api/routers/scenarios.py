"""Sensitivity sweep endpoints (was: Scenario sweep).

URL paths remain /scenarios/... for backward compat with existing clients.
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUserId, DBSession
from app.models.deal import Scenario as FinancialScenario  # financial plan
from app.models.project import Opportunity, Project
from app.models.scenario import (
    Sensitivity,
    SensitivityResult,
    SensitivityStatus,
)
from app.observability import format_timestamp, log_observation, new_trace_id, utc_now
from app.schemas.scenario import (
    ScenarioAttributionRead,
    ScenarioComparisonPointRead,
    ScenarioComparisonRead,
    ScenarioMetricDeltaRead,
    ScenarioRead,
    ScenarioResultRead,
    ScenarioVariableDescriptorRead,
    SensitivityResultRead,
)
from app.tasks.scenario import SCENARIO_VARIABLES, _dispatch_scenario_sweep, sweep_variable

router = APIRouter(tags=["scenarios"])
logger = logging.getLogger(__name__)

COMPARE_METRIC_FIELDS = (
    "project_irr_pct",
    "lp_irr_pct",
    "gp_irr_pct",
    "equity_multiple",
    "cash_on_cash_year1_pct",
)
ZERO = Decimal("0")
DECIMAL_PLACES = Decimal("0.000001")


class ScenarioCreateRequest(BaseModel):
    scenario_id: UUID          # financial plan (Scenario from deal.py) to sweep against
    variable: str
    range_min: Decimal
    range_max: Decimal
    range_steps: int = 10


@router.get("/scenarios/variables")
async def list_scenario_variables() -> dict[str, dict[str, str]]:
    return SCENARIO_VARIABLES


@router.post(
    "/projects/{project_id}/scenarios",
    response_model=dict[str, str],
    status_code=status.HTTP_201_CREATED,
)
async def create_project_scenario(
    project_id: UUID,
    payload: ScenarioCreateRequest,
    request: Request,
    session: DBSession,
    current_user_id: CurrentUserId,
) -> dict[str, str]:
    opportunity = await session.get(Opportunity, project_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    financial_scenario = await session.get(FinancialScenario, payload.scenario_id)
    if financial_scenario is None:
        raise HTTPException(status_code=404, detail="Financial scenario not found")

    if payload.variable not in SCENARIO_VARIABLES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid scenario variable '{payload.variable}'. "
                f"Valid keys: {sorted(SCENARIO_VARIABLES)}"
            ),
        )

    if payload.range_steps < 1:
        raise HTTPException(status_code=400, detail="range_steps must be at least 1")

    if payload.range_min > payload.range_max:
        raise HTTPException(
            status_code=400,
            detail="range_min must be less than or equal to range_max",
        )

    sensitivity = Sensitivity(
        opportunity_id=project_id,
        scenario_id=payload.scenario_id,
        created_by_user_id=current_user_id,
        variable=payload.variable,
        range_min=payload.range_min,
        range_max=payload.range_max,
        range_steps=payload.range_steps,
        status=SensitivityStatus.pending,
    )
    session.add(sensitivity)
    await session.commit()
    await session.refresh(sensitivity)

    trace_id = new_trace_id(getattr(request.state, "trace_id", None))
    queued_at = utc_now()
    task_id = f"sensitivity-{sensitivity.id}"
    try:
        async_result = cast(Any, sweep_variable).apply_async(
            args=[str(sensitivity.id)],
            kwargs={"trace_id": trace_id},
            queue="analysis",
        )
        task_id = async_result.id or task_id
    except Exception:
        asyncio.create_task(
            _dispatch_scenario_sweep(
                str(sensitivity.id),
                task_id=task_id,
                trace_id=trace_id,
            )
        )

    sensitivity.status = SensitivityStatus.running
    sensitivity.celery_task_id = task_id
    await session.commit()

    log_observation(
        logger,
        "sensitivity_run_queued",
        trace_id=trace_id,
        sensitivity_id=sensitivity.id,
        scenario_id=sensitivity.scenario_id,
        task_id=task_id,
        variable=sensitivity.variable,
        triggered_by=current_user_id,
    )
    return {
        "status": "queued",
        "task_id": task_id,
        "scenario_id": str(sensitivity.id),
        "trace_id": trace_id,
        "queued_at": format_timestamp(queued_at),
    }


@router.get("/scenarios/{scenario_id}/results", response_model=list[SensitivityResultRead])
async def get_scenario_results(
    scenario_id: UUID,
    session: DBSession,
    run_number: int | None = Query(default=None, alias="run", ge=1),
) -> list[SensitivityResult]:
    sensitivity = await session.get(Sensitivity, scenario_id)
    if sensitivity is None:
        raise HTTPException(status_code=404, detail="Scenario not found")

    requested_run = run_number or max(int(getattr(sensitivity, "run_count", 1) or 1), 1)
    result = await session.execute(
        select(SensitivityResult)
        .where(
            SensitivityResult.sensitivity_id == scenario_id,
            SensitivityResult.run_number == requested_run,
        )
        .order_by(SensitivityResult.variable_value.asc())
    )
    return list(result.scalars())


def _to_decimal(value: object | None) -> Decimal | None:
    if value in (None, ""):
        return None
    if isinstance(value, Decimal):
        return value.quantize(DECIMAL_PLACES)
    return Decimal(str(value)).quantize(DECIMAL_PLACES)


def _resolve_baseline_value(sensitivity: Sensitivity) -> Decimal | None:
    if not sensitivity.variable.startswith("operational."):
        return None

    fin_scenario = sensitivity.scenario
    _default_proj = (
        next((p for p in sorted(fin_scenario.projects, key=lambda p: p.created_at)), None)
        if fin_scenario and fin_scenario.projects
        else None
    )
    inputs = _default_proj.operational_inputs if _default_proj else None
    if inputs is None:
        return None

    attribute_name = sensitivity.variable.split(".", 1)[1]
    if not hasattr(inputs, attribute_name):
        return None

    return _to_decimal(getattr(inputs, attribute_name))


def _resolve_baseline_result(
    results: list[SensitivityResult],
    baseline_value: Decimal | None,
) -> SensitivityResult | None:
    if not results:
        return None
    if baseline_value is None:
        return results[len(results) // 2]

    return min(
        results,
        key=lambda result: abs((_to_decimal(result.variable_value) or ZERO) - baseline_value),
    )


def _build_metric_delta(
    value: Decimal | None,
    baseline_value: Decimal | None,
) -> ScenarioMetricDeltaRead:
    if value is None:
        return ScenarioMetricDeltaRead(value=None, delta=None, delta_pct=None)

    delta = None if baseline_value is None else (value - baseline_value).quantize(DECIMAL_PLACES)
    delta_pct = None
    if baseline_value not in (None, ZERO) and delta is not None:
        delta_pct = ((delta / baseline_value) * Decimal("100")).quantize(DECIMAL_PLACES)

    return ScenarioMetricDeltaRead(value=value, delta=delta, delta_pct=delta_pct)


def _build_comparison_point(
    result: SensitivityResult,
    *,
    sensitivity: Sensitivity,
    baseline_result: SensitivityResult | None,
    baseline_value: Decimal | None,
) -> ScenarioComparisonPointRead:
    compared_value = _to_decimal(result.variable_value) or ZERO
    value_delta = None if baseline_value is None else (compared_value - baseline_value).quantize(DECIMAL_PLACES)

    if value_delta is None or value_delta == ZERO:
        direction = "no_change"
    elif value_delta > ZERO:
        direction = "increase"
    else:
        direction = "decrease"

    variable_meta = SCENARIO_VARIABLES.get(
        sensitivity.variable,
        {"label": sensitivity.variable, "unit": "value"},
    )

    metric_values: dict[str, ScenarioMetricDeltaRead] = {}
    for metric_name in COMPARE_METRIC_FIELDS:
        current_value = _to_decimal(getattr(result, metric_name))
        baseline_metric_value = (
            _to_decimal(getattr(baseline_result, metric_name)) if baseline_result is not None else None
        )
        metric_values[metric_name] = _build_metric_delta(current_value, baseline_metric_value)

    return ScenarioComparisonPointRead(
        variable_value=compared_value,
        attribution=ScenarioAttributionRead(
            driver=sensitivity.variable,
            label=variable_meta["label"],
            unit=variable_meta["unit"],
            baseline_value=baseline_value,
            compared_value=compared_value,
            delta=value_delta,
            direction=direction,
        ),
        project_irr_pct=metric_values["project_irr_pct"],
        lp_irr_pct=metric_values["lp_irr_pct"],
        gp_irr_pct=metric_values["gp_irr_pct"],
        equity_multiple=metric_values["equity_multiple"],
        cash_on_cash_year1_pct=metric_values["cash_on_cash_year1_pct"],
    )


@router.get("/scenarios/{scenario_id}/compare", response_model=ScenarioComparisonRead)
async def get_scenario_compare(
    scenario_id: UUID,
    session: DBSession,
) -> ScenarioComparisonRead:
    result = await session.execute(
        select(Sensitivity)
        .options(
            selectinload(Sensitivity.results),
            selectinload(Sensitivity.scenario).selectinload(FinancialScenario.projects).selectinload(Project.operational_inputs),
        )
        .where(Sensitivity.id == scenario_id)
    )
    sensitivity = result.scalar_one_or_none()
    if sensitivity is None:
        raise HTTPException(status_code=404, detail="Scenario not found")

    latest_run = max(int(getattr(sensitivity, "run_count", 1) or 1), 1)
    active_results = [
        item for item in list(sensitivity.results) if getattr(item, "run_number", 1) == latest_run
    ]
    ordered_results = sorted(
        active_results or list(sensitivity.results),
        key=lambda item: _to_decimal(item.variable_value) or ZERO,
    )
    baseline_value = _resolve_baseline_value(sensitivity)
    baseline_result = _resolve_baseline_result(ordered_results, baseline_value)
    variable_meta = SCENARIO_VARIABLES.get(
        sensitivity.variable,
        {"label": sensitivity.variable, "unit": "value"},
    )

    return ScenarioComparisonRead(
        sensitivity_id=sensitivity.id,
        opportunity_id=sensitivity.opportunity_id,
        scenario_id=sensitivity.scenario_id,
        status=sensitivity.status,
        variable=ScenarioVariableDescriptorRead(
            key=sensitivity.variable,
            label=variable_meta["label"],
            unit=variable_meta["unit"],
        ),
        baseline=SensitivityResultRead.model_validate(baseline_result) if baseline_result is not None else None,
        comparisons=[
            _build_comparison_point(
                item,
                sensitivity=sensitivity,
                baseline_result=baseline_result,
                baseline_value=baseline_value,
            )
            for item in ordered_results
        ],
    )


@router.get("/scenarios/{scenario_id}/status")
async def get_scenario_status(scenario_id: UUID, session: DBSession) -> dict[str, Any]:
    sensitivity = await session.get(Sensitivity, scenario_id)
    if sensitivity is None:
        raise HTTPException(status_code=404, detail="Scenario not found")

    return {
        "id": str(sensitivity.id),
        "opportunity_id": str(sensitivity.opportunity_id),
        "scenario_id": str(sensitivity.scenario_id),
        "status": getattr(sensitivity.status, "value", sensitivity.status),
        "task_id": sensitivity.celery_task_id,
        "run_count": max(int(getattr(sensitivity, "run_count", 1) or 1), 1),
        "model_version_snapshot": sensitivity.model_version_snapshot,
    }
