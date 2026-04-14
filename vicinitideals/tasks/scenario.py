"""Celery tasks for scenario sweeps on the analysis queue."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

from celery import chord, group
from celery.utils.log import get_task_logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vicinitideals.db import AsyncSessionLocal
from vicinitideals.engines.cashflow import compute_cash_flows
from vicinitideals.models.cashflow import CashFlow, OperationalOutputs, PeriodType
from vicinitideals.models.deal import DealModel, OperationalInputs
from vicinitideals.models.project import Project
from vicinitideals.models.scenario import Scenario, ScenarioResult, ScenarioStatus
from vicinitideals.observability import begin_observation, elapsed_ms, log_observation
from vicinitideals.tasks.celery_app import celery_app

try:
    from vicinitideals.engines.waterfall import compute_waterfall
except ImportError:  # pragma: no cover - Stage 1B may not be present in every checkout

    async def compute_waterfall(
        deal_model_id: UUID | str,
        session: AsyncSession,
    ) -> dict[str, Any]:
        del deal_model_id, session
        raise ValueError("Waterfall engine is not available")

logger = get_task_logger(__name__)

RUN_SCENARIO_TASK = "vicinitideals.tasks.scenario.run_scenario"
FINALIZE_SCENARIO_TASK = "vicinitideals.tasks.scenario.finalize_scenario"
MONEY_PLACES = Decimal("0.000001")
ZERO = Decimal("0")
HUNDRED = Decimal("100")
INTEGER_VARIABLE_KEYS = {"operational.lease_up_months"}

SCENARIO_VARIABLES = {
    "operational.exit_cap_rate_pct": {"label": "Exit Cap Rate", "unit": "pct"},
    "operational.lease_up_months": {"label": "Lease-Up Months", "unit": "months"},
    "operational.expense_growth_rate_pct_annual": {
        "label": "Expense Growth Rate",
        "unit": "pct",
    },
    "operational.hold_period_years": {"label": "Hold Period", "unit": "years"},
    "operational.hard_cost_per_unit": {
        "label": "Hard Cost per Unit",
        "unit": "dollars",
    },
}


@celery_app.task(bind=True, name="vicinitideals.tasks.scenario.run_scenario")
def run_scenario(
    self,
    scenario_id: str,
    variable_value: str | Decimal | None = None,
    trace_id: str | None = None,
) -> str:
    """Run a full scenario sweep, or a single sweep point when `variable_value` is provided."""
    task_id = getattr(self.request, "id", None)
    return asyncio.run(
        _run_scenario_async(
            scenario_id=scenario_id,
            task_id=task_id,
            variable_value=variable_value,
            trace_id=trace_id,
        )
    )


@celery_app.task(bind=True, name="vicinitideals.tasks.scenario.sweep_variable")
def sweep_variable(self, scenario_id: str, trace_id: str | None = None) -> None:
    """Dispatch one analysis-queue subtask per scenario value via Celery chord."""
    task_id = getattr(self.request, "id", None)
    asyncio.run(
        _dispatch_scenario_sweep(
            str(scenario_id),
            task_id=task_id,
            trace_id=trace_id,
        )
    )
    return None


@celery_app.task(name="vicinitideals.tasks.scenario.finalize_scenario")
def _finalize_scenario_task(results: list[str], scenario_id: str) -> str:
    """Mark a chord-dispatched scenario as complete after all points finish."""
    del results
    return asyncio.run(_finalize_scenario_async(str(scenario_id)))


async def _run_scenario_async(
    *,
    scenario_id: str | UUID,
    task_id: str | None = None,
    variable_value: str | Decimal | None = None,
    trace_id: str | None = None,
) -> str:
    trace_id, _, started_at_monotonic = begin_observation(trace_id or task_id or str(scenario_id))
    scenario_uuid = UUID(str(scenario_id))

    if variable_value is not None:
        decimal_value = _to_decimal(variable_value)
        if decimal_value is None:
            raise ValueError(f"Scenario value '{variable_value}' is not numeric")
        log_observation(
            logger,
            "scenario_point_started",
            trace_id=trace_id,
            scenario_id=scenario_uuid,
            task_id=task_id,
            variable_value=decimal_value,
        )
        metrics = await _evaluate_scenario_value(scenario_uuid, decimal_value)
        await _persist_scenario_result(scenario_uuid, decimal_value, metrics)
        log_observation(
            logger,
            "scenario_point_completed",
            trace_id=trace_id,
            scenario_id=scenario_uuid,
            task_id=task_id,
            variable_value=decimal_value,
            duration_ms=elapsed_ms(started_at_monotonic),
        )
        return str(scenario_uuid)

    scenario = await _prepare_scenario_run(scenario_uuid, task_id=task_id)
    if scenario is None:
        raise ValueError(f"Scenario {scenario_uuid} was not found")

    if scenario.variable not in SCENARIO_VARIABLES:
        await _mark_scenario_failed(
            scenario_uuid,
            f"Unsupported scenario variable '{scenario.variable}'",
            task_id=task_id,
        )
        return str(scenario_uuid)

    if int(scenario.range_steps) <= 0:
        await _mark_scenario_failed(
            scenario_uuid,
            "range_steps must be greater than zero",
            task_id=task_id,
        )
        return str(scenario_uuid)

    values = _generate_sweep_values(scenario)
    log_observation(
        logger,
        "scenario_run_started",
        trace_id=trace_id,
        scenario_id=scenario_uuid,
        task_id=task_id,
        deal_model_id=scenario.scenario_id,
        variable=scenario.variable,
        points=len(values),
    )

    try:
        for value in values:
            metrics = await _evaluate_scenario_value(scenario_uuid, value)
            await _persist_scenario_result(scenario_uuid, value, metrics)
    except Exception as exc:
        log_observation(
            logger,
            "scenario_run_failed",
            trace_id=trace_id,
            scenario_id=scenario_uuid,
            task_id=task_id,
            variable=scenario.variable,
            duration_ms=elapsed_ms(started_at_monotonic),
            error=str(exc),
        )
        await _mark_scenario_failed(scenario_uuid, str(exc), task_id=task_id)
        raise

    await _set_scenario_status(
        scenario_uuid,
        ScenarioStatus.complete,
        task_id=task_id,
    )
    log_observation(
        logger,
        "scenario_run_completed",
        trace_id=trace_id,
        scenario_id=scenario_uuid,
        task_id=task_id,
        variable=scenario.variable,
        points=len(values),
        duration_ms=elapsed_ms(started_at_monotonic),
    )
    return str(scenario_uuid)


async def _dispatch_scenario_sweep(
    scenario_id: str | UUID,
    task_id: str | None = None,
    trace_id: str | None = None,
) -> None:
    scenario_uuid = UUID(str(scenario_id))
    scenario = await _prepare_scenario_run(scenario_uuid, task_id=task_id)
    if scenario is None:
        raise ValueError(f"Scenario {scenario_uuid} was not found")

    if scenario.variable not in SCENARIO_VARIABLES:
        await _mark_scenario_failed(
            scenario_uuid,
            f"Unsupported scenario variable '{scenario.variable}'",
            task_id=task_id,
        )
        return

    values = _generate_sweep_values(scenario)
    trace_id = trace_id or task_id or str(scenario_uuid)
    header = group(
        celery_app.signature(
            RUN_SCENARIO_TASK,
            args=[str(scenario_uuid), str(value)],
            kwargs={"trace_id": trace_id},
        ).set(queue="analysis")
        for value in values
    )
    callback = celery_app.signature(
        FINALIZE_SCENARIO_TASK,
        args=[str(scenario_uuid)],
    ).set(queue="analysis")
    async_result = chord(header)(callback)

    await _set_scenario_task_id(scenario_uuid, async_result.id or task_id)
    log_observation(
        logger,
        "scenario_sweep_dispatched",
        trace_id=trace_id,
        scenario_id=scenario_uuid,
        task_id=async_result.id or task_id,
        points=len(values),
    )


async def _prepare_scenario_run(
    scenario_id: UUID,
    task_id: str | None = None,
) -> Scenario | None:
    async with AsyncSessionLocal() as session:
        scenario = await _load_scenario(session, scenario_id)
        if scenario is None:
            return None

        result_check = await session.execute(
            select(ScenarioResult.id)
            .where(ScenarioResult.sensitivity_id == scenario_id)
            .limit(1)
        )
        has_existing_results = result_check.first() is not None
        current_run_count = max(int(getattr(scenario, "run_count", 1) or 1), 1)

        scenario.status = ScenarioStatus.running
        if task_id:
            scenario.celery_task_id = task_id
        scenario.run_count = current_run_count + 1 if has_existing_results else current_run_count
        scenario.model_version_snapshot = _build_model_version_snapshot(scenario)
        await session.commit()
        await session.refresh(scenario)
        return scenario


def _build_model_version_snapshot(scenario: Scenario) -> dict[str, Any]:
    deal_model = scenario.scenario
    _default_proj = next((p for p in sorted(deal_model.projects, key=lambda p: p.created_at)), None) if deal_model and deal_model.projects else None
    inputs = _default_proj.operational_inputs if _default_proj else None
    project_type = None
    if deal_model is not None:
        project_type = getattr(deal_model.project_type, "value", deal_model.project_type)

    return {
        "deal_model_id": str(scenario.scenario_id),
        "deal_model_version": deal_model.version if deal_model is not None else None,
        "project_type": project_type,
        "unit_count_new": inputs.unit_count_new if inputs is not None else None,
        "purchase_price": None if inputs is None or inputs.purchase_price is None else str(inputs.purchase_price),
        "exit_cap_rate_pct": None
        if inputs is None or inputs.exit_cap_rate_pct is None
        else str(inputs.exit_cap_rate_pct),
        "hold_period_years": None
        if inputs is None or inputs.hold_period_years is None
        else str(inputs.hold_period_years),
        "captured_at": datetime.now(UTC).isoformat(),
    }


async def _evaluate_scenario_value(
    scenario_id: UUID,
    value: Decimal,
) -> dict[str, Decimal | None]:
    async with AsyncSessionLocal() as session:
        scenario = await _load_scenario(session, scenario_id)
        if scenario is None:
            raise ValueError(f"Scenario {scenario_id} was not found")
        if scenario.scenario is None:
            raise ValueError(f"Scenario {scenario_id} is missing a Deal")
        _default_proj = (
            next((p for p in sorted(scenario.scenario.projects, key=lambda p: p.created_at)), None)
            if scenario.scenario.projects
            else None
        )
        if _default_proj is None or _default_proj.operational_inputs is None:
            raise ValueError(
                f"Scenario {scenario_id} is missing a Deal with OperationalInputs"
            )

        inputs = _default_proj.operational_inputs
        _apply_scenario_override(inputs, scenario.variable, value)
        await session.flush()

        cashflow_summary = await compute_cash_flows(
            deal_model_id=scenario.scenario_id,
            session=session,
        )

        waterfall_summary: dict[str, Any] = {}
        try:
            waterfall_summary = await compute_waterfall(
                deal_model_id=scenario.scenario_id,
                session=session,
            )
        except Exception as exc:  # pragma: no cover - optional when no capital stack exists
            logger.info(
                "Skipping waterfall metrics for scenario %s at %s: %s",
                scenario_id,
                value,
                exc,
            )

        outputs = await _load_operational_outputs(session, scenario.scenario_id)
        first_stabilized_year_noi = await _load_first_stabilized_year_noi(
            session,
            scenario.scenario_id,
        )
        metrics = _extract_metrics(
            outputs=outputs,
            cashflow_summary=cashflow_summary,
            waterfall_summary=waterfall_summary,
            first_stabilized_year_noi=first_stabilized_year_noi,
        )
        await session.rollback()
        return metrics


async def _persist_scenario_result(
    scenario_id: UUID,
    value: Decimal,
    metrics: dict[str, Decimal | None],
) -> None:
    async with AsyncSessionLocal() as session:
        scenario = await session.get(Scenario, scenario_id)
        if scenario is None:
            raise ValueError(f"Scenario {scenario_id} was not found")

        session.add(
            ScenarioResult(
                sensitivity_id=scenario_id,
                run_number=max(int(getattr(scenario, "run_count", 1) or 1), 1),
                variable_value=_q(value),
                project_irr_pct=metrics.get("project_irr_pct"),
                lp_irr_pct=metrics.get("lp_irr_pct"),
                gp_irr_pct=metrics.get("gp_irr_pct"),
                equity_multiple=metrics.get("equity_multiple"),
                cash_on_cash_year1_pct=metrics.get("cash_on_cash_year1_pct"),
            )
        )
        await session.commit()


async def _finalize_scenario_async(scenario_id: str | UUID) -> str:
    scenario_uuid = UUID(str(scenario_id))
    await _set_scenario_status(scenario_uuid, ScenarioStatus.complete)
    return str(scenario_uuid)


async def _set_scenario_status(
    scenario_id: UUID,
    status: ScenarioStatus,
    task_id: str | None = None,
) -> None:
    async with AsyncSessionLocal() as session:
        scenario = await session.get(Scenario, scenario_id)
        if scenario is None:
            return
        scenario.status = status
        if task_id:
            scenario.celery_task_id = task_id
        await session.commit()


async def _set_scenario_task_id(scenario_id: UUID, task_id: str | None) -> None:
    if not task_id:
        return
    async with AsyncSessionLocal() as session:
        scenario = await session.get(Scenario, scenario_id)
        if scenario is None:
            return
        scenario.celery_task_id = task_id
        await session.commit()


async def _mark_scenario_failed(
    scenario_id: UUID,
    reason: str,
    task_id: str | None = None,
) -> None:
    log_observation(
        logger,
        "scenario_marked_failed",
        trace_id=task_id or str(scenario_id),
        scenario_id=scenario_id,
        task_id=task_id,
        error=reason,
    )
    logger.warning("Scenario %s failed: %s", scenario_id, reason)
    await _set_scenario_status(scenario_id, ScenarioStatus.failed, task_id=task_id)


async def _load_scenario(session: AsyncSession, scenario_id: UUID) -> Scenario | None:
    result = await session.execute(
        select(Scenario)
        .options(
            selectinload(Scenario.scenario).selectinload(DealModel.projects).selectinload(Project.operational_inputs)
        )
        .where(Scenario.id == scenario_id)
    )
    return result.scalar_one_or_none()


async def _load_operational_outputs(
    session: AsyncSession,
    deal_model_id: UUID,
) -> OperationalOutputs | None:
    result = await session.execute(
        select(OperationalOutputs).where(OperationalOutputs.scenario_id == deal_model_id)
    )
    return result.scalar_one_or_none()


async def _load_first_stabilized_year_noi(
    session: AsyncSession,
    deal_model_id: UUID,
) -> Decimal | None:
    result = await session.execute(
        select(CashFlow.noi)
        .where(
            CashFlow.scenario_id == deal_model_id,
            CashFlow.period_type == PeriodType.stabilized.value,
        )
        .order_by(CashFlow.period.asc())
        .limit(12)
    )
    rows = [_to_decimal(value) for value in result.scalars().all()]
    values = [value for value in rows if value is not None]
    if not values:
        return None
    return _q(sum(values, ZERO))


def _generate_sweep_values(scenario: Scenario) -> list[Decimal]:
    start = _to_decimal(scenario.range_min, ZERO) or ZERO
    end = _to_decimal(scenario.range_max, ZERO) or ZERO
    steps = max(int(scenario.range_steps), 1)

    if steps == 1:
        return [_q(start)]

    step_size = (end - start) / Decimal(steps - 1)
    return [_q(start + (step_size * Decimal(idx))) for idx in range(steps)]


def _apply_scenario_override(
    inputs: OperationalInputs,
    variable: str,
    value: Decimal,
) -> None:
    if variable not in SCENARIO_VARIABLES:
        raise ValueError(f"Unsupported scenario variable '{variable}'")

    prefix = "operational."
    if not variable.startswith(prefix):
        raise ValueError(f"Unsupported scenario scope for '{variable}'")

    attribute_name = variable[len(prefix) :]
    if not hasattr(inputs, attribute_name):
        raise ValueError(f"OperationalInputs has no attribute '{attribute_name}'")

    if variable in INTEGER_VARIABLE_KEYS:
        coerced: Any = int(value.to_integral_value(rounding=ROUND_HALF_UP))
    else:
        coerced = _q(value)

    setattr(inputs, attribute_name, coerced)


def _extract_metrics(
    *,
    outputs: OperationalOutputs | None,
    cashflow_summary: dict[str, Any] | None,
    waterfall_summary: dict[str, Any] | None,
    first_stabilized_year_noi: Decimal | None,
) -> dict[str, Decimal | None]:
    summary = cashflow_summary or {}
    waterfall = waterfall_summary or {}

    total_project_cost = _coalesce_decimal(
        outputs.total_project_cost if outputs is not None else None,
        summary.get("total_project_cost"),
    )
    equity_required = _coalesce_decimal(
        outputs.equity_required if outputs is not None else None,
        summary.get("equity_required"),
    )
    project_irr_pct = _coalesce_decimal(
        outputs.project_irr_levered if outputs is not None else None,
        summary.get("project_irr_levered"),
    )
    annual_noi = first_stabilized_year_noi or _coalesce_decimal(
        outputs.noi_stabilized if outputs is not None else None,
        summary.get("noi_stabilized"),
    )

    equity_multiple: Decimal | None = None
    cash_on_cash_year1_pct: Decimal | None = None
    if equity_required not in (None, ZERO):
        if total_project_cost is not None:
            equity_multiple = _q(total_project_cost / equity_required)
        if annual_noi is not None:
            cash_on_cash_year1_pct = _q((annual_noi / equity_required) * HUNDRED)

    return {
        "project_irr_pct": _q(project_irr_pct) if project_irr_pct is not None else None,
        "lp_irr_pct": _nullable_quantized(waterfall.get("lp_irr_pct")),
        "gp_irr_pct": _nullable_quantized(waterfall.get("gp_irr_pct")),
        "equity_multiple": equity_multiple,
        "cash_on_cash_year1_pct": cash_on_cash_year1_pct,
    }


def _nullable_quantized(value: Any) -> Decimal | None:
    decimal_value = _to_decimal(value)
    if decimal_value is None:
        return None
    return _q(decimal_value)


def _coalesce_decimal(*values: Any) -> Decimal | None:
    for value in values:
        decimal_value = _to_decimal(value)
        if decimal_value is not None:
            return decimal_value
    return None


def _to_decimal(value: Any, default: Decimal | None = None) -> Decimal | None:
    if value in (None, ""):
        return default
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return Decimal(int(value))
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))

    text = str(value).strip().replace(",", "").replace("$", "").replace("%", "")
    if not text:
        return default
    return Decimal(text)


def _q(value: Decimal) -> Decimal:
    return value.quantize(MONEY_PLACES)


__all__ = ["SCENARIO_VARIABLES", "run_scenario", "sweep_variable"]
