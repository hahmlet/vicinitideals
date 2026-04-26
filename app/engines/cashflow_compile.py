"""Pure-structure compile phase for the cashflow engine.

This module owns scenario "structure" — the parts of the engine that don't
depend on slider-controlled dollar inputs (Revenue, OpEx, Purchase Price).
Functions here are called once per scenario and produce data structures the
evaluate phase consumes to compute dollar flows.

PR1 scope (this module's initial slice):
    PhaseSpec dataclass, _MILESTONE_TYPE_TO_PHASE_KEY constant,
    _milestone_dates_from_orm, _build_phase_plan,
    _apply_milestone_phase_overrides, _phase_milestone_key,
    _coerce_milestone_date, _calendar_month_count.
    Plus the two small numeric parsers these functions rely on
    (_to_decimal, _positive_int) so the module is self-contained.

Subsequent PRs will move per-loan windowing (_loan_pre_op_months,
_PERIOD_TYPE_RANK), exit-vehicle pairing (_resolve_vehicle), per-period
revenue/opex factor pre-computation (currently inline in _compute_period),
and the bridge/closing-cost classification step.

Backward compat: ``app/engines/cashflow.py`` re-exports these names so any
caller that still does ``from app.engines.cashflow import PhaseSpec`` (e.g.
tests/engines/test_cashflow.py) continues to work.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from app.models.cashflow import PeriodType
from app.models.deal import OperationalInputs
from app.models.milestone import Milestone

ZERO = Decimal("0")
ONE = Decimal("1")

_MILESTONE_TYPE_TO_PHASE_KEY: dict[str, str] = {
    "construction": "construction_start",
    "operation_lease_up": "lease_up_start",
    "operation_stabilized": "stabilized_start",
    "divestment": "exit_date",
    "close": "acquisition_start",
    "pre_development": "pre_construction_start",
}


@dataclass(frozen=True)
class PhaseSpec:
    period_type: PeriodType
    months: int


def _to_decimal(value: Any, default: Decimal = ZERO) -> Decimal:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _positive_int(value: Any, fallback: int = 1) -> int:
    decimal_value = _to_decimal(value, Decimal(fallback))
    integer_value = int(decimal_value.to_integral_value(rounding=ROUND_HALF_UP))
    return max(fallback if fallback > 0 else 0, integer_value)


def _milestone_dates_from_orm(
    milestones: list[Milestone],
    milestone_map: dict[Any, Milestone],
) -> dict[str, Any]:
    """Derive milestone_dates dict from ORM Milestone records using trigger-chain resolution."""
    result: dict[str, Any] = {}
    for m in milestones:
        mtype = str(m.milestone_type).replace("MilestoneType.", "")
        phase_key = _MILESTONE_TYPE_TO_PHASE_KEY.get(mtype)
        if phase_key is None:
            continue
        start = m.computed_start(milestone_map)
        if start is not None:
            result[phase_key] = start.isoformat()
    return result


def _build_phase_plan(
    project_type: str,
    inputs: OperationalInputs,
    milestone_dates: dict[str, Any] | None = None,
    has_lease_up_milestone: bool = False,
    has_pre_development_milestone: bool = False,
    has_construction_milestone: bool = False,
) -> list[PhaseSpec]:
    phases: list[PhaseSpec] = [PhaseSpec(PeriodType.acquisition, 1)]

    if project_type in {
        "value_add",
        "conversion",
        "new_construction",
    } and bool(inputs.hold_phase_enabled):
        hold_months = _positive_int(inputs.hold_months, fallback=0)
        if hold_months > 0:
            phases.append(PhaseSpec(PeriodType.hold, hold_months))

    if project_type == "acquisition":
        # Post migration 0049 "acquisition" is a pure hold/stabilize strategy,
        # no renovation by default. Opt in by adding a construction milestone
        # or setting renovation_months > 0 — matches the lease_up pattern below.
        reno_months = _positive_int(inputs.renovation_months, fallback=0)
        if has_construction_milestone or reno_months > 0:
            phases.append(
                PhaseSpec(PeriodType.minor_renovation, max(reno_months, 1))
            )
    elif project_type == "value_add":
        # Optional pre-construction phase when user added a Pre Development milestone
        if has_pre_development_milestone or _positive_int(inputs.entitlement_months, fallback=0) > 0:
            phases.append(PhaseSpec(
                PeriodType.pre_construction,
                _positive_int(inputs.entitlement_months, fallback=1),
            ))
        phases.append(
            PhaseSpec(
                PeriodType.major_renovation,
                _positive_int(inputs.renovation_months, fallback=1),
            )
        )
    elif project_type == "conversion":
        phases.append(
            PhaseSpec(
                PeriodType.pre_construction,
                _positive_int(inputs.entitlement_months, fallback=1),
            )
        )
        phases.append(
            PhaseSpec(
                PeriodType.conversion,
                _positive_int(inputs.construction_months or inputs.renovation_months, fallback=1),
            )
        )
    elif project_type == "new_construction":
        phases.append(
            PhaseSpec(
                PeriodType.pre_construction,
                _positive_int(inputs.entitlement_months, fallback=1),
            )
        )
        phases.append(
            PhaseSpec(
                PeriodType.construction,
                _positive_int(inputs.construction_months, fallback=1),
            )
        )
    else:
        raise ValueError(f"Unsupported project_type: {project_type}")

    # Include lease_up phase only if explicitly configured:
    # - An operation_lease_up milestone exists, OR
    # - lease_up_months is explicitly set on OperationalInputs
    # If neither, assume immediate stabilization (no lease-up ramp needed).
    lease_up_months = _positive_int(inputs.lease_up_months, fallback=0)
    if has_lease_up_milestone or lease_up_months > 0:
        phases.append(PhaseSpec(PeriodType.lease_up, max(lease_up_months, 1)))

    stabilized_months = _positive_int(
        (_to_decimal(inputs.hold_period_years, ONE) * Decimal("12")),
        fallback=12,
    )
    phases.append(PhaseSpec(PeriodType.stabilized, stabilized_months))
    phases.append(PhaseSpec(PeriodType.exit, 1))
    effective_milestone_dates = milestone_dates if milestone_dates else inputs.milestone_dates
    return _apply_milestone_phase_overrides(phases, effective_milestone_dates)


def _apply_milestone_phase_overrides(
    phases: list[PhaseSpec], milestone_dates: Any
) -> list[PhaseSpec]:
    if not isinstance(milestone_dates, dict) or not milestone_dates:
        return phases

    parsed_dates = {
        key: parsed
        for key, value in milestone_dates.items()
        if isinstance(key, str)
        and (parsed := _coerce_milestone_date(value)) is not None
    }
    if not parsed_dates:
        return phases

    overridden: list[PhaseSpec] = []
    for index, phase in enumerate(phases):
        start_key = _phase_milestone_key(phase.period_type)
        if start_key is None:
            overridden.append(phase)
            continue

        start_date = parsed_dates.get(start_key)
        end_date: date | None = None
        for later_phase in phases[index + 1 :]:
            boundary_key = _phase_milestone_key(later_phase.period_type)
            if boundary_key is None:
                continue
            end_date = parsed_dates.get(boundary_key)
            if end_date is not None:
                break

        if start_date is None or end_date is None:
            overridden.append(phase)
            continue

        month_count = _calendar_month_count(start_date, end_date)
        overridden.append(
            PhaseSpec(phase.period_type, month_count if month_count > 0 else phase.months)
        )

    return overridden


def _phase_milestone_key(period_type: PeriodType) -> str | None:
    if period_type == PeriodType.pre_construction:
        return "pre_construction_start"
    if period_type in {
        PeriodType.minor_renovation,
        PeriodType.major_renovation,
        PeriodType.conversion,
        PeriodType.construction,
    }:
        return "construction_start"
    if period_type == PeriodType.lease_up:
        return "lease_up_start"
    if period_type == PeriodType.stabilized:
        return "stabilized_start"
    if period_type == PeriodType.exit:
        return "exit_date"
    return None


def _coerce_milestone_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        return None


def _calendar_month_count(start_date: date, end_date: date) -> int:
    if end_date <= start_date:
        return 0

    month_count = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
    if end_date.day > start_date.day:
        month_count += 1
    return max(1, month_count)
