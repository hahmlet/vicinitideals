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


# ─── Per-loan windowing + Exit Vehicle pairing (PR1 slice 2) ────────────────
# Each loan's IR/CI interest accrues only during the phases within its
# [active_phase_start, active_phase_end) window. The rank constants below
# convert phase identifiers into ordinals so we can window-filter the phase
# list per loan. Rank semantics: a loan with [start_rank, end_rank) includes
# phases whose rank is >= start_rank AND < end_rank. End-exclusive because
# the loan is taken out at the START of the end phase.

_CONSTRUCTION_PERIOD_TYPES = {
    PeriodType.acquisition, PeriodType.hold, PeriodType.pre_construction,
    PeriodType.construction, PeriodType.minor_renovation, PeriodType.major_renovation,
    PeriodType.conversion,
}

# Active-phase rank map used for Exit Vehicle detection (§2.10) and per-loan
# carry windowing. A loan with active window [start_rank, end_rank) is active
# during phases whose rank ∈ [start_rank, end_rank).
_APS_TO_RANK: dict[str, int] = {
    "acquisition": 0, "close": 0,
    "pre_construction": 2,
    "construction": 3,
    "lease_up": 4, "operation_lease_up": 4,
    "stabilized": 5, "operation_stabilized": 5,
    "exit": 6, "divestment": 6,
}

# Period-type rank map used by _loan_pre_op_months. Same semantics as
# _APS_TO_RANK but keyed by PeriodType enum (not phase string).
_PERIOD_TYPE_RANK: dict[PeriodType, int] = {
    PeriodType.acquisition:       0,
    PeriodType.hold:              1,
    PeriodType.pre_construction:  2,
    PeriodType.minor_renovation:  3,
    PeriodType.major_renovation:  3,
    PeriodType.construction:      3,
    PeriodType.conversion:        3,
    PeriodType.lease_up:          4,
    PeriodType.stabilized:        5,
    PeriodType.exit:              6,
}

# Funder types that participate in Exit Vehicle pairing (debt that gets
# refinanced or paid off at maturity/sale). Equity, grants, etc. are excluded
# (they ride to perpetuity and the waterfall handles them at exit).
_EXIT_VEHICLE_APPLIES = {
    "permanent_debt", "senior_debt", "mezzanine_debt", "bridge",
    "construction_loan", "acquisition_loan", "pre_development_loan",
    "soft_loan", "bond", "owner_loan",
}


def _module_rank(module: object, side: str) -> int:
    """Rank of a module's active_phase_{start|end}.

    `start` missing → 0 (acquisition). `end` missing / "perpetuity" → 99.
    """
    raw = str(getattr(module, f"active_phase_{side}", "") or "")
    if side == "end":
        return _APS_TO_RANK.get(raw, 99)
    return _APS_TO_RANK.get(raw, 0)


def _resolve_active_end_rank(module: object, all_modules: list) -> int:
    """Derive a module's active-end rank from its Exit Vehicle.

    Supersedes reading ``active_phase_end`` directly — the user-editable field
    is deprecated (duplicates the Exit Vehicle intent).  Rules:

      * non-exit-vehicle funder types (equity, grants, etc.) → 99 (perpetuity;
        waterfall handles at exit)
      * ``exit_terms.vehicle == "maturity"`` / unset → 99 (balloon uses amort)
      * ``exit_terms.vehicle == "sale"`` → 6 (exit/divestment rank)
      * ``exit_terms.vehicle == <uuid>`` → retirer's start_rank (handoff point)

    Falls back to the legacy ``active_phase_end`` if vehicle is unset AND a
    legacy value is stored — this keeps old rows working until the DB cleanup.
    """
    ft = str(getattr(module, "funder_type", "") or "").replace("FunderType.", "")
    if ft not in _EXIT_VEHICLE_APPLIES:
        return 99

    exit_terms = getattr(module, "exit_terms", None) or {}
    saved = (exit_terms.get("vehicle") or "").strip() if isinstance(exit_terms, dict) else ""

    if saved == "sale":
        return 6
    if saved == "maturity":
        return 99
    if saved:
        # UUID of a retirer — look it up and use its start rank.
        for r in all_modules:
            if r is module:
                continue
            if str(getattr(r, "id", "")) == saved:
                return _module_rank(r, "start")
        # Dangling reference — fall through to legacy / default.

    # Legacy fallback: honour stored active_phase_end if present.
    legacy = str(getattr(module, "active_phase_end", "") or "")
    if legacy:
        return _APS_TO_RANK.get(legacy, 99)
    return 99


def _eligible_retirers(module: object, all_modules: list) -> list:
    """Return modules whose active window covers `module`'s end point.

    A retirer R qualifies when:
      - R is not the same module
      - R.start_rank <= module.end_rank  (already active at the handoff)
      - R.end_rank   >  module.end_rank  (still active after module ends)

    Module end-rank is derived via `_resolve_active_end_rank` (Exit Vehicle
    supersedes the deprecated `active_phase_end` field).
    """
    e_rank = _resolve_active_end_rank(module, all_modules)
    if e_rank >= 99:
        return []  # perpetuity — nothing to retire
    out: list = []
    for r in all_modules:
        if r is module:
            continue
        r_end = _resolve_active_end_rank(r, all_modules)
        if _module_rank(r, "start") <= e_rank < r_end:
            out.append(r)
    return out


def _resolve_vehicle(module: object, all_modules: list) -> tuple[str, object | None]:
    """Resolve the Exit Vehicle for `module`.

    Reads `exit_terms.vehicle`. Returns:
      ("maturity", None) — balloon at amort end, no refi event
      ("sale",     None) — balloon at divestment, no refi event
      ("source",   R)    — retirer R absorbs the balance (§2.10 refi)

    Falls back to default-selection when vehicle is unset or points to a
    module that no longer qualifies.  Default selection:
      1. If ≥1 eligible source exists: prefer those with start_rank == end_rank
         (enter exactly at handoff); tie-break by lowest stack_position, then
         alphabetical label.
      2. Else if end_rank >= 6 (exit\\divestment): "sale".
      3. Else: "maturity".
    """
    exit_terms = getattr(module, "exit_terms", None) or {}
    saved = (exit_terms.get("vehicle") or "").strip() if isinstance(exit_terms, dict) else ""
    eligible = _eligible_retirers(module, all_modules)

    if saved == "maturity":
        return ("maturity", None)
    if saved == "sale":
        return ("sale", None)
    if saved and saved not in {"maturity", "sale"}:
        # Honour the user's explicit pick regardless of overlap — timing
        # semantics around "end" vs "start" make strict overlap checks too
        # brittle (new loan often starts the day the old one closes, which
        # may read as adjacent-not-overlapping depending on rank mapping).
        # Engine trusts the user; compute math handles the handoff via
        # construction_retirement regardless of exact date alignment.
        for r in all_modules:
            if r is module:
                continue
            if str(getattr(r, "id", "")) == saved:
                return ("source", r)
        # Stored vehicle points at a deleted/missing module → fall through.

    if eligible:
        e_rank = _resolve_active_end_rank(module, all_modules)
        exact = [r for r in eligible if _module_rank(r, "start") == e_rank]
        pool = exact or eligible

        def _sort_key(r: object) -> tuple:
            return (
                int(getattr(r, "stack_position", 0) or 0),
                str(getattr(r, "label", "") or ""),
            )

        return ("source", sorted(pool, key=_sort_key)[0])
    if _resolve_active_end_rank(module, all_modules) >= 6:
        return ("sale", None)
    return ("maturity", None)


def _loan_pre_op_months(module: object, capital_modules: list, phases: list) -> int:
    """Compute the number of pre-op months within this loan's active window.

    Only counts construction-type phases (acquisition, hold, pre_construction,
    construction, renovation, conversion) that fall within the module's
    [active_phase_start, _resolve_active_end_rank) rank window. Replaces the
    global ``constr_months_total`` so each loan uses its own N for the IR/CI
    carry formula.

    Promoted from an inner function inside ``_auto_size_debt_modules`` to a
    free function in PR1 slice 2 of the compile/evaluate split. ``capital_modules``
    and ``phases`` are now explicit parameters (formerly closure references).
    """
    start = str(getattr(module, "active_phase_start", "") or "")
    start_rank = _APS_TO_RANK.get(start, 0)
    # End-exclusive: derived from Exit Vehicle (supersedes active_phase_end).
    end_rank = _resolve_active_end_rank(module, capital_modules)
    return sum(
        p.months for p in phases
        if p.period_type in _CONSTRUCTION_PERIOD_TYPES
        and start_rank <= _PERIOD_TYPE_RANK.get(p.period_type, 99) < end_rank
    )
