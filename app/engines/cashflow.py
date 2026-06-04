from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from uuid import UUID

_DIAG_ENABLED = os.environ.get("VD_DIAG_AUTOSIZE") == "1"

# Acquisition deals (turnkey rentals: acquisition → stabilized, no lease-up
# phase) get a short proof window starting at stabilization. The window is
# narrow because there is no ramp risk to model — it just sanity-checks that
# the Operating Reserve, perm debt service, and stabilized OpEx balance for
# the first months after close.
_ACQUISITION_PROOF_MONTHS = 3


def _diag(msg: str) -> None:
    """Diagnostic trace for auto-sizing — gated on VD_DIAG_AUTOSIZE=1 env var.

    Off by default; enable temporarily via env to debug sizing issues.
    """
    if _DIAG_ENABLED:
        print(f"[VD_DIAG] {msg}", flush=True)

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.cashflow import (
    CashFlow,
    CashFlowLineItem,
    LineItemCategory,
    OperationalOutputs,
    PeriodType,
)
from app.models.capital import CapitalModule, CapitalModuleProject
from app.models.capital_draw_event import CapitalDrawEvent, DrawAllocationReason
from app.models.deal import IncomeStream, OperatingExpenseLine, OperationalInputs, Scenario, UseLine
from app.models.milestone import Milestone, MilestoneType
from app.models.project import Project
from app.models.manifest import WorkflowRunManifest
from app.engines.draw_engine import compute_period_draw_inflow
from app.engines.interest import period_interest_months
from app.engines.period_engine import compound_accrual
from app.engines.bank_account import simulate as _bank_account_simulate
from app.engines.bank_account_extractor import (
    extract_full_window_proof,
    extract_operating_proof_window,
)
from app.engines.newton_solve import solve_principal_for_dscr
from types import SimpleNamespace as _SN
from app.engines.source_routing import route_use_to_sources as _route_use_to_sources

# Phase-plan + per-loan windowing + per-period structural helpers extracted
# to cashflow_compile.py (PR1 slices 1, 2, 3 of compile/evaluate split).
# Imports below are re-exported for backward compat — existing callers (tests,
# app/api/routers/ui.py:5288 importing _EXIT_VEHICLE_APPLIES, etc.) keep
# importing from app.engines.cashflow.
from app.engines.cashflow_compile import (
    PhaseSpec,
    lease_up_ramp_occupancy,
    _APS_TO_RANK,
    _CONSTRUCTION_PERIOD_TYPES,
    _EXIT_VEHICLE_APPLIES,
    _MILESTONE_TYPE_TO_PHASE_KEY,
    _PERIOD_TYPE_RANK,
    _apply_milestone_phase_overrides,
    _build_phase_plan,
    _calendar_month_count,
    _coerce_milestone_date,
    _eligible_retirers,
    _growth_factor,
    _is_expense_line_active,
    _is_stream_active,
    _loan_pre_op_months,
    _loan_start_abs_month,
    _manifest_unit_count,
    _milestone_dates_from_orm,
    _module_rank,
    _operating_unit_count,
    _phase_is_operational,
    _phase_milestone_key,
    _resolve_active_end_rank,
    _resolve_horizon_months,
    _resolve_vehicle,
    _stream_occupancy_pct,
)

try:
    import pyxirr
except ImportError:  # pragma: no cover - dependency is expected but keep runtime safe
    pyxirr = None


MONEY_PLACES = Decimal("0.000001")
ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")
PLACEHOLDER_DSCR = Decimal("1.250000")
# Max annual rent increase for LTL catchup — prevents unrealistic 20%+ jumps
LTL_CATCHUP_CAP_PCT = Decimal("10")

# Use line labels excluded from capital_outflow in NCF.
# These are pre-funded reserves that remain in the capital balance until consumed;
# they are NOT cash payments in the period they appear as use lines.
# Phase E: these ARE included as draw inflows at phase activation (reserve pre-fund).
_BALANCE_ONLY_LABELS: frozenset[str] = frozenset({
    "Operating Reserve",
    "Operating Deficit Reserve",
    "Cash Flow Support Reserve",
    "Capitalized Construction Interest",
    "Construction Interest Reserve",
    "Capitalized Pre-Development Interest",
    "Capitalized Acquisition Interest",
    "Interest Reserve",
    "Pre-Development Interest Reserve",
    "Acquisition Interest Reserve",
    "Construction DS Reserve",
})


def _run_bank_account_proof(
    *,
    cash_flow_rows: list,
    use_lines: list,
    phases: list,
    milestone_dates: dict | None,
    construction_monthly: list | None = None,
    dev_fee_paydowns_by_period: dict[int, Decimal] | None = None,
) -> dict | None:
    """Run the bank-account solvency proof.

    With ``construction_monthly`` supplied (draw_schedule.MonthlyCashFlow
    rows), the proof window covers Day 0 → Stabilization Start — every
    month between deal start and stabilization is simulated against the
    Operating Reserve floor. Without it, the window collapses to the
    legacy CO → Stabilization Start range (lease-up only).

    Returns a small summary dict with min balance, max shortfall, solvency
    flag, and `proof_start` ("day_0" or "co") — or None if the proof
    window can't be derived (no operating phases).
    """
    if not cash_flow_rows or not phases:
        return None

    # Walk phases to find the first lease-up period (= CO). If no lease-up
    # phase exists, fall back to the first stabilized period.
    co_period: int | None = None
    stab_period: int | None = None
    cursor = 0
    for ps in phases:
        if ps.period_type == PeriodType.lease_up and co_period is None:
            co_period = cursor
        if ps.period_type == PeriodType.stabilized and stab_period is None:
            stab_period = cursor
            if co_period is None:
                co_period = cursor
        cursor += ps.months
    if co_period is None:
        return None  # no operating window to prove

    # Acquisition pattern: no lease_up phase → co_period fell back to stab_period.
    # Extend the window N stabilized months so the extractor sees real rows;
    # otherwise [co, stab) is empty and the proof aborts.
    _acquisition_only = (stab_period is not None and co_period == stab_period)
    if _acquisition_only:
        proof_window_end = stab_period + _ACQUISITION_PROOF_MONTHS
    else:
        proof_window_end = stab_period

    # First period date — anchor from earliest milestone date the phase plan
    # uses. Phase 0 is acquisition; its start = "acquisition_start" or
    # "pre_construction_start" depending on whether pre-dev exists.
    anchor_date: date | None = None
    for key in ("pre_construction_start", "acquisition_start",
                "construction_start", "lease_up_start"):
        anchor_date = _first_milestone_date(milestone_dates or {}, (key,))
        if anchor_date is not None:
            break
    if anchor_date is None:
        return None  # can't anchor period 0 to a date

    first_period_dt = datetime(anchor_date.year, anchor_date.month, 1)

    if construction_monthly:
        bank_inputs = extract_full_window_proof(
            construction_monthly=construction_monthly,
            cash_flow_rows=cash_flow_rows,
            use_lines=use_lines,
            first_period_date=first_period_dt,
            co_period=co_period,
            stabilized_period=proof_window_end,
            dev_fee_paydowns_by_period=dev_fee_paydowns_by_period,
        )
        proof_start = "day_0"
    else:
        bank_inputs = extract_operating_proof_window(
            cash_flow_rows=cash_flow_rows,
            use_lines=use_lines,
            first_period_date=first_period_dt,
            co_period=co_period,
            stabilized_period=proof_window_end,
            dev_fee_paydowns_by_period=dev_fee_paydowns_by_period,
        )
        proof_start = "stabilized" if _acquisition_only else "co"
    if not bank_inputs.months:
        return None

    report = _bank_account_simulate(
        months=bank_inputs.months,
        opening_cash=bank_inputs.opening_cash,
        monthly_inflows=bank_inputs.monthly_inflows,
        monthly_outflows=bank_inputs.monthly_outflows,
        monthly_floor=bank_inputs.monthly_floor,
    )

    _diag(
        f"bank-account proof: opening={report.opening_cash} "
        f"min_balance={report.min_balance} "
        f"max_shortfall={report.max_shortfall} "
        f"is_solvent={report.is_solvent} "
        f"window=[period {co_period}, {stab_period}) "
        f"months={len(report.monthly)}"
    )

    # ── Stabilization-anchor validation (reserves-spec-align Slice 5d) ────
    # Per spec critique #4: the user anchors the Stabilization milestone
    # by hand. Reserve windows reference that anchor (IR up to it, OR
    # from it). If the user puts Stabilization BEFORE the operating
    # curves can actually carry DS (NOI < DS at the anchor), the IR
    # window ends prematurely and OR silently absorbs what should still
    # be IR coverage — the "no gap by construction" promise is defeated.
    # The validator computes the first operating-window period where
    # NOI >= DS (the curve-derived natural Stabilization point) and
    # compares it to the user-anchored stab_period.
    #   anchor earlier than curve  → "error"  (hard config issue)
    #   anchor later than curve    → "warning" (conservative; OR carries
    #                                more, deal still pencils)
    #   anchor matches curve       → None
    # The validator is purely informational on the proof row; it does
    # NOT block compute. The Underwriting render layer surfaces it as a
    # banner.
    stabilization_anchor = _validate_stabilization_anchor(
        cash_flow_rows=cash_flow_rows,
        co_period=co_period,
        stabilized_period=stab_period,
    )

    return {
        "opening_cash": str(report.opening_cash),
        "min_balance": str(report.min_balance),
        "min_balance_date": (
            report.min_balance_date.isoformat() if report.min_balance_date else None
        ),
        "max_shortfall": str(report.max_shortfall),
        "max_shortfall_date": (
            report.max_shortfall_date.isoformat() if report.max_shortfall_date else None
        ),
        "is_solvent": report.is_solvent,
        "co_period": co_period,
        "stabilized_period": stab_period,
        "months_simulated": len(report.monthly),
        "proof_start": proof_start,
        "stabilization_anchor": stabilization_anchor,
    }


def _validate_stabilization_anchor(
    *,
    cash_flow_rows: list,
    co_period: int,
    stabilized_period: int | None,
) -> dict | None:
    """Compare the user-anchored Stabilization to the curve-derived one.

    Walks the cash-flow rows from ``co_period`` forward and finds the
    first month where ``NOI >= debt_service`` — the natural point at
    which the operating curves can carry the lender's debt service on
    their own (no reserve draw needed). The reserves-spec-align spec
    (§4 / critique #4) treats that month as the curve-derived
    Stabilization point.

    Outcomes:
      * ``status="error"``   user's Stabilization < curve-derived month
        (IR window ends too early; OR is being asked to carry what
        should still be IR coverage; the "no gap by construction"
        promise breaks).
      * ``status="warning"`` user's Stabilization > curve-derived month
        (conservative — OR carries more than necessary; deal still
        pencils but more equity is parked in reserves than required).
      * ``None``             anchors match (or the validator can't
        derive a curve-derived month — e.g. NOI never catches DS in
        the modeled window).
    """
    if not cash_flow_rows or stabilized_period is None:
        return None

    rows_by_period = {
        getattr(r, "period", None): r for r in cash_flow_rows
        if getattr(r, "period", None) is not None
    }
    if not rows_by_period:
        return None

    # First operating-window month where NOI >= DS.
    curve_period: int | None = None
    for p in sorted(rows_by_period):
        if p < co_period:
            continue
        row = rows_by_period[p]
        noi = Decimal(str(getattr(row, "noi", 0) or 0))
        ds = Decimal(str(getattr(row, "debt_service", 0) or 0))
        if ds <= ZERO:
            # No DS this month (post-payoff or fully IR-funded with the
            # sweep already covering it) — not a meaningful comparison.
            continue
        if noi >= ds:
            curve_period = p
            break

    if curve_period is None:
        # NOI never catches DS in the modeled window — the deal itself
        # under-performs the debt; surface that as the proof's
        # is_solvent flag, not here.
        return None

    if curve_period == stabilized_period:
        return None

    if stabilized_period < curve_period:
        status = "error"
        message = (
            f"Stabilization anchored at period {stabilized_period} but "
            f"NOI does not cover DS until period {curve_period}. "
            f"Interest Reserve ends before lease-up can carry the debt; "
            f"Operating Reserve will absorb the gap. Move the "
            f"Stabilization milestone to period {curve_period} or later."
        )
    else:
        status = "warning"
        message = (
            f"Stabilization anchored at period {stabilized_period} but "
            f"NOI covered DS as early as period {curve_period}. "
            f"Operating Reserve will be sized for a longer pre-stab "
            f"runway than the operating curves require."
        )

    return {
        "status": status,
        "curve_derived_period": curve_period,
        "anchored_period": stabilized_period,
        "gap_months": stabilized_period - curve_period,
        "message": message,
    }


async def compute_cash_flows(
    deal_model_id: UUID | str,
    session: AsyncSession,
    *,
    construction_monthly: list | None = None,
) -> dict[str, Any]:
    """Compute and persist operational cash flows for every Project in a Scenario.

    Phase 2 refactor: loads the Scenario once, purges prior output rows once,
    then iterates ``sorted(scenario.projects, key=created_at)`` and delegates
    each project to ``_compute_project_cashflow``. For single-project scenarios
    (every production deal today) the loop runs exactly once and output is
    byte-identical to the pre-refactor engine.

    The function is idempotent for a given ``deal_model_id``: it deletes prior
    ``CashFlow`` / ``CashFlowLineItem`` / ``OperationalOutputs`` rows before
    re-running.

    Returns the last project's summary dict for backward-compat with single-
    project callers. The Underwriting rollup (``app/engines/underwriting.py``)
    aggregates across projects directly from the persisted per-project rows.
    """

    deal_uuid = UUID(str(deal_model_id))
    # Expire all cached ORM objects so _load_deal_model always reads fresh data.
    # The compute endpoint pre-loads Project in the same session; without
    # expire_all() the selectinload in _load_deal_model returns the cached
    # collection and misses any use_lines / expense_lines written earlier in
    # the same request cycle.
    session.expire_all()
    deal_model = await _load_deal_model(session, deal_uuid)
    if deal_model is None:
        raise ValueError(f"Deal {deal_uuid} was not found")

    # Anchor-topological compute order: anchored projects run after the
    # project they reference. With zero ProjectAnchor rows (current prod)
    # this returns the same order as sorted-by-created_at. Cycles raise
    # AnchorCycleError.
    from app.engines.anchor_resolver import (
        ordered_projects as _ordered_projects,
        resolve_project_start_dates as _resolve_start_dates,
    )
    projects = await _ordered_projects(deal_model, session)
    if not projects:
        raise ValueError(f"Deal {deal_uuid} has no Project")

    # Phase 2d1: resolve per-project start-date overrides from the
    # ProjectAnchor chain. Empty dict for zero-anchor scenarios.
    start_overrides = await _resolve_start_dates(deal_model, session)

    # Per-project purge happens INSIDE _compute_project_cashflow, right after
    # prev_outputs is captured for DSCR convergence, so each iteration sees its
    # own prior NOI and wipes only its own rows (not a sibling's).
    # Skip projects with no OperationalInputs (e.g. orphan rows created when
    # a user clicks "Add Building" but the wizard doesn't seed inputs on the
    # new project). Without this guard the whole compute aborts and outputs
    # never write for the valid sibling project.
    projects = [p for p in projects if p.operational_inputs is not None]
    if not projects:
        raise ValueError(f"Deal {deal_uuid} has no Project with OperationalInputs")

    last_summary: dict[str, Any] = {}
    for project in projects:
        last_summary = await _compute_project_cashflow(
            deal_model=deal_model,
            deal_uuid=deal_uuid,
            project=project,
            session=session,
            project_start_override=start_overrides.get(project.id),
            construction_monthly=construction_monthly,
        )

    # Phase D: reconcile module.source["amount"] = Σ(junction.amount) across all projects.
    # For single-project scenarios this is a no-op. For shared sources spanning multiple
    # projects, each project auto-sizes its own junction amount independently; the module-
    # level record should reflect the total rather than the last project's amount.
    if len(projects) > 1:
        await _reconcile_module_amounts_from_junctions(session, deal_uuid)

    return last_summary


async def _compute_project_cashflow(
    *,
    deal_model: Scenario,
    deal_uuid: UUID,
    project: Project,
    session: AsyncSession,
    project_start_override: Any = None,
    construction_monthly: list | None = None,
) -> dict[str, Any]:
    """Compute and persist cash flows for a single Project within a Scenario.

    Writes fresh ``CashFlow`` / ``CashFlowLineItem`` / ``OperationalOutputs``
    rows scoped to ``project.id``. Caller (``compute_cash_flows``) is
    responsible for purging prior scenario-wide output rows once, before the
    per-project loop.
    """

    if project.operational_inputs is None:
        raise ValueError(
            f"Project {project.id} (scenario {deal_uuid}) is missing OperationalInputs"
        )

    inputs = project.operational_inputs
    streams = sorted(project.income_streams, key=lambda stream: stream.label.lower())
    expense_lines = sorted(project.expense_lines, key=lambda line: line.label.lower())
    use_lines = list(project.use_lines)

    capital_modules = await _per_project_capital_modules(
        session, deal_uuid, project.id
    )

    # Build milestone_dates from ORM Milestone records, overlaying any stored in inputs
    orm_milestones = list((await session.execute(
        select(Milestone).where(Milestone.project_id == project.id)
    )).scalars())
    milestone_map = {m.id: m for m in orm_milestones}
    milestone_dates = _milestone_dates_from_orm(orm_milestones, milestone_map)
    # Stored inputs.milestone_dates overrides ORM-derived dates (manual overrides)
    if isinstance(inputs.milestone_dates, dict):
        milestone_dates.update(inputs.milestone_dates)
    # Phase 2d1: apply anchor-resolved start date if the scenario has one
    # for this project. Shift every phase-key date by (override - earliest
    # current date) so the internal chain timing is preserved but the whole
    # project starts at the resolved date. No-op when override is None.
    if project_start_override is not None and milestone_dates:
        from datetime import date as _date_cls
        def _parse(v):
            if isinstance(v, _date_cls):
                return v
            if isinstance(v, str):
                try:
                    return _date_cls.fromisoformat(v)
                except ValueError:
                    return None
            return None
        parsed: dict[str, _date_cls] = {}
        for k, v in milestone_dates.items():
            d = _parse(v)
            if d is not None:
                parsed[k] = d
        if parsed:
            earliest = min(parsed.values())
            delta = project_start_override - earliest
            if delta.days != 0:
                for k, d in parsed.items():
                    milestone_dates[k] = (d + delta).isoformat()
    has_lease_up_milestone = any(
        str(m.milestone_type) in ("operation_lease_up", MilestoneType.operation_lease_up)
        for m in orm_milestones
    )
    has_pre_development_milestone = any(
        str(m.milestone_type) in ("pre_development", MilestoneType.pre_development)
        for m in orm_milestones
    )
    has_construction_milestone = any(
        str(m.milestone_type) in ("construction", MilestoneType.construction)
        for m in orm_milestones
    )

    # Build phase plan first so auto-sizing knows construction duration for IO budgeting
    phases = _build_phase_plan(
        _project_type_name(deal_model.project_type),
        inputs,
        milestone_dates=milestone_dates,
        has_lease_up_milestone=has_lease_up_milestone,
        has_pre_development_milestone=has_pre_development_milestone,
        has_construction_milestone=has_construction_milestone,
        capital_modules=capital_modules,
        orm_milestones=orm_milestones,
    )

    # Look up previously computed NOI so auto-sizing uses the accurate value.
    # The estimate from _estimate_stabilized_noi_monthly misses escalation
    # carry-in and capex reserve, causing the DSCR cap to fire at the wrong
    # level. Scope by project_id now that a scenario can carry N output rows
    # (one per project) — each project's DSCR convergence reads only its own
    # prior NOI.
    #
    # Note: the outer compute_cash_flows wrapper purges ALL scenario outputs
    # once before the per-project loop, so within a single compute invocation
    # prev_outputs is None on every iteration. The prev row only survives
    # across separate compute calls, which is when convergence matters.
    prev_outputs = (await session.execute(
        select(OperationalOutputs).where(
            OperationalOutputs.scenario_id == deal_uuid,
            OperationalOutputs.project_id == project.id,
        )
    )).scalar_one_or_none()
    prev_noi_stabilized = _to_decimal(prev_outputs.noi_stabilized) if prev_outputs else None

    # Capture prior iteration's waterfall-driven deferred Dev Fee paydowns so
    # the bank-account proof sees them as outflows from the operating account.
    # Pre-reserves-spec-align, the proof's max_shortfall fed into a Cash Flow
    # Support Reserve UseLine; that helper was removed in Slice 5b — ODR
    # (Slice 4) is the engine's first-class home for the operating shortfall,
    # and the proof is now validation-only.
    prev_dev_fee_paydowns: dict[int, Decimal] = {}
    if prev_outputs is not None:
        _series = prev_outputs.dev_fee_balance_series or {}
        for _row in _series.get("periods", []) or []:
            try:
                _amt = Decimal(str(_row.get("paydown_from_waterfall", "0")))
            except (InvalidOperation, ValueError, TypeError):
                continue
            if _amt > ZERO:
                prev_dev_fee_paydowns[int(_row["period"])] = _amt

    # Flush any pending (unflushed) ORM objects from a prior compute pass
    # before the bulk DELETE runs.  With autoflush=False, session.add_all()
    # rows from a previous pass remain PENDING and are NOT evicted by
    # synchronize_session="evaluate" — they would survive the DELETE and be
    # committed alongside the new pass, producing mixed-pass data in the DB.
    # Flushing here ensures all prior-pass rows are written then immediately
    # deleted, so only the current pass commits.
    await session.flush()

    # Now safe to wipe this project's prior rows — prev_outputs is captured.
    await _purge_project_outputs(session, deal_uuid, project.id)

    income_mode: str = (deal_model.income_mode or "revenue_opex")

    # Recompute auto Developer Fee Use Line BEFORE debt sizing so total Uses
    # reflect the current % × basis. Mutates use_lines in place and flushes.
    # Pass capital_modules + org + milestone_dates so the multi-source binding
    # context (per-Source allowances, funded/deferred split, release schedule,
    # structural diff) is populated for the explainer modal. Legacy behavior
    # is preserved when no Vehicle has fee_terms set.
    from app.engines.dev_fee import recompute_auto_dev_fee
    await recompute_auto_dev_fee(
        use_lines,
        inputs,
        session,
        modules=capital_modules,
        milestone_dates=milestone_dates,
        org_id=getattr(deal_model, "org_id", None),
    )

    # Resolve grant caps (source.maximum) into actual source.amount based on
    # per-Use eligibility. Must run BEFORE _auto_size_debt_modules so the
    # gap-fill solver reads the capped grant contribution.
    from app.engines.grant_caps import resolve_grant_caps
    await resolve_grant_caps(capital_modules, use_lines, session)

    # Pre-size any auto_size=True debt modules before computing debt service
    await _auto_size_debt_modules(
        capital_modules, inputs, streams, expense_lines, use_lines, phases, session,
        prev_noi_stabilized=prev_noi_stabilized,
        income_mode=income_mode,
    )

    # After debt sizing, auto-size any DDF module with auto_size=True.
    # DDF is always last-resort: fills residual gap after all other sources.
    _auto_size_ddf_module(capital_modules, use_lines)

    # Flush auto-sized module.source changes (held as ORM-dirty in memory) so
    # downstream raw-SQL reads see the auto-sized amounts. The earlier bulk
    # sa_update path was replaced by ORM dirty tracking to avoid MissingGreenlet
    # from expired JSONB attrs on in-session CapitalModule rows.
    await session.flush()

    # Phase 2c1: sync the auto-sized amount back onto the per-project junction
    # row so the Coverage modal reflects the current computed amount and so
    # subsequent per-project compute iterations on a shared Source read an
    # up-to-date junction. No-op for single-project scenarios where
    # junction.amount == source.amount pre- and post-compute.
    await _sync_junction_amounts_after_compute(
        session, deal_uuid, project.id, capital_modules
    )

    # Build milestone month map once for carry schedule resolution.
    _milestone_month_map = _build_milestone_month_map(phases)

    # Identify modules with a carry schedule so they can be excluded from the
    # two-phase DS constants and handled per-period instead.
    _schedule_module_ids: set = set()
    for _scm in capital_modules:
        if _is_debt_cm(_scm) and (_scm.carry or {}).get("schedule"):
            _schedule_module_ids.add(_scm.id)

    construction_debt_monthly = _sum_debt_service(
        capital_modules, is_construction=True, exclude_ids=_schedule_module_ids
    )
    operation_debt_monthly = _sum_debt_service(
        capital_modules, is_construction=False, exclude_ids=_schedule_module_ids
    )

    # Pre-compute per-absolute-month DS for schedule-based modules.
    _total_months = sum(p.months for p in phases)
    _schedule_period_ds: dict[int, Decimal] = {}
    for _scm in capital_modules:
        if _scm.id not in _schedule_module_ids:
            continue
        _scm_carry = _scm.carry or {}
        _scm_schedule = _scm_carry.get("schedule", [])
        _scm_principal = Decimal(str((_scm.source or {}).get("amount") or 0))
        _scm_base_rate = (_scm.source or {}).get("interest_rate_pct")
        _scm_start_abs = _loan_start_abs_month(_scm, phases)
        _scm_resolved = _resolve_carry_schedule(_scm_schedule, _milestone_month_map, _scm_start_abs)
        for _abs_m in range(_total_months):
            _loan_m = _abs_m - _scm_start_abs
            if _loan_m < 0:
                continue
            _active_phase = _carry_for_loan_month(_scm_resolved, _loan_m)
            _ds = _period_ds_from_schedule_phase(_active_phase, _scm_principal, _scm_base_rate)
            if _ds:
                _schedule_period_ds[_abs_m] = _schedule_period_ds.get(_abs_m, ZERO) + _ds

    # ── Refi net proceeds computation ────────────────────────────────────────
    # When a perm module takes out a bridge (construction_retirement tagged),
    # compute net refi proceeds: perm_amount − bridge_balloon − prepay − financing_costs.
    # Positive surplus = cash to equity; negative = equity call needed.
    # Injected as a capital event line item at the first period of the perm's active phase.
    _refi_event: dict[str, Any] | None = None
    for cm in capital_modules:
        src = cm.source or {}
        if not src.get("construction_retirement"):
            continue
        perm_amount = _to_decimal(src.get("amount"))
        retirement_amount = _to_decimal(src.get("construction_retirement"))
        # Find the bridge module to compute balloon balance
        bridge = next(
            (m for m in capital_modules if (m.source or {}).get("is_bridge")),
            None,
        )
        bridge_balloon = retirement_amount  # default: full payoff
        prepay_penalty = ZERO
        if bridge is not None:
            b_src = bridge.source or {}
            b_carry = bridge.carry or {}
            b_rate = b_src.get("interest_rate_pct") or b_carry.get("io_rate_pct")
            b_amort = int(b_src.get("amort_term_years") or 30)
            # Count months the bridge was active (pre-op phases)
            b_months = sum(
                p.months for p in phases
                if p.period_type in _CONSTRUCTION_PERIOD_TYPES
            )
            b_io_months = int((b_carry.get("io_period_months") or 0))
            bridge_balloon = _balloon_balance(
                retirement_amount, b_rate, b_amort, b_months, io_months=b_io_months,
            )
            # Prepay penalty on bridge
            ppct = _to_decimal(b_src.get("prepay_penalty_pct"))
            if ppct > ZERO:
                prepay_penalty = _q(bridge_balloon * ppct / HUNDRED)
        # Total Finance Costs for the perm loan (single global %)
        perm_financing_costs = _q(perm_amount * DEFAULT_FINANCE_COST_PCT / HUNDRED)
        net_refi = _q(perm_amount - bridge_balloon - prepay_penalty - perm_financing_costs)
        _refi_event = {
            "perm_amount": perm_amount,
            "bridge_balloon": bridge_balloon,
            "prepay_penalty": prepay_penalty,
            "financing_costs": perm_financing_costs,
            "net_proceeds": net_refi,
            "perm_active_phase_start": str(getattr(cm, "active_phase_start", "") or ""),
        }
        break  # only one perm takeout per deal

    # ── Float-earnings on Day-1 draws ────────────────────────────────────
    # Treasury yield income on parent sources that draw 100% at start
    # (typically tax-exempt construction bonds). Computed AFTER auto-sizing
    # so reserves (IR / OR / LUR / CFSR) stay sized as if this float income
    # doesn't exist — see docs/feature-plans/interest-earned-on-day-1-draws.md
    # for the conservative reserve invariant.
    from app.engines.float_earnings import compute_scenario_float_earnings
    from app.engines.debt_paydown import resolve_milestone_period

    _float_constr_months = sum(
        p.months for p in phases if p.period_type in _CONSTRUCTION_PERIOD_TYPES
    )
    _float_results = compute_scenario_float_earnings(
        capital_modules=capital_modules,
        milestones=orm_milestones,
        construction_months=_float_constr_months,
    )
    _float_warnings: list[str] = [w for r in _float_results for w in r.warnings]

    # Pre-resolve found-money firing periods once so the per-month loop only
    # does dict lookups. All float earnings route to the GP/LP waterfall as
    # a lump sum at the waterfall_milestone_id period.
    _found_money_period_to_source_idx: dict[int, list[int]] = {}
    for _fr_idx, _fr in enumerate(_float_results):
        if _fr.total_earnings <= ZERO or _fr.waterfall_milestone_id is None:
            continue
        _fm_period = resolve_milestone_period(
            milestone_id=_fr.waterfall_milestone_id,
            milestone_map=milestone_map,
            milestone_month_map=_milestone_month_map,
        )
        if _fm_period is None:
            continue
        _found_money_period_to_source_idx.setdefault(_fm_period, []).append(_fr_idx)


    # Output purge happens once at the outer compute_cash_flows wrapper
    # before the per-project loop — not per-project here.
    cash_flow_rows: list[CashFlow] = []
    line_item_rows: list[CashFlowLineItem] = []
    net_cash_flow_series: list[Decimal] = []
    draw_event_rows: list[CapitalDrawEvent] = []

    # Phase E: start at zero. Capital draws flow in period-by-period as uses fire.
    # Per-period draw inflows replace the old total_sources lump pre-seed.
    cumulative_cash_flow = ZERO
    stabilized_noi_monthly: Decimal | None = None
    period = 0
    _operating_reserve_seeded = False
    _refi_injected = False

    # Resolve operating reserve amount once — used to reset capital balance at
    # start of first operational phase so the invariant holds:
    #   Capital Balance[first stab month] = reserve + min(0, NCF)
    _op_reserve_amount = next(
        (_to_decimal(ul.amount) for ul in use_lines
         if getattr(ul, "label", "") == "Operating Reserve"),
        ZERO,
    )

    # Compute the period index of the first stabilized month.  NOI-mode
    # escalation anchors here so "Stabilized NOI" input means "NOI at year 1
    # of stabilization" (the underwriting convention) — not "NOI at deal
    # close".  Without this anchor, escalation from deal month 0 lifts the
    # display NOI above the sizing NOI, preventing DSCR convergence to the
    # minimum in dscr_capped / dual_constraint modes.
    _first_stab_period = 0
    _accum = 0
    for _p in phases:
        if _p.period_type == PeriodType.stabilized:
            _first_stab_period = _accum
            break
        _accum += _p.months

    # Phase B: pre-compute milestone FK overrides for UseLines that have
    # active_from_milestone_id set. Built once before the phase loop so
    # milestone resolution doesn't repeat per-period.
    _ul_phase_overrides = _build_use_line_phase_overrides(
        use_lines, milestone_map, phases
    )

    # Pre-compute monthly interest for IR-carry loans that extend through lease-up.
    # Passed to _compute_period so income covers interest in those months rather
    # than sending it to equity while the IR pool draws separately.
    _ir_lease_up_monthly = _sum_ir_lease_up_interest(capital_modules, phases)

    # Reserve labels already drawn — prevents re-firing when a use_line's phase
    # maps to multiple period_types (e.g. "operation" → lease_up + stabilized).
    _drawn_reserve_labels: set[str] = set()

    for phase in phases:
        for month_index in range(phase.months):
            period_result = _compute_period(
                deal_model_id=deal_uuid,
                project_id=project.id,
                period=period,
                phase=phase,
                month_index=month_index,
                inputs=inputs,
                streams=streams,
                expense_lines=expense_lines,
                use_lines=use_lines,
                stabilized_noi_monthly=stabilized_noi_monthly,
                construction_debt_monthly=construction_debt_monthly,
                operation_debt_monthly=operation_debt_monthly,
                schedule_debt_monthly=_schedule_period_ds.get(period, ZERO),
                income_mode=income_mode,
                first_stab_period=_first_stab_period,
                use_line_phase_overrides=_ul_phase_overrides,
                ir_lease_up_interest=_ir_lease_up_monthly,
            )

            if phase.period_type == PeriodType.stabilized and stabilized_noi_monthly is None:
                stabilized_noi_monthly = period_result["noi"]

            # ── Inject refi net proceeds at the first month of perm's active phase ─
            if _refi_event and not _refi_injected and month_index == 0:
                _refi_phase_key = _refi_event["perm_active_phase_start"]
                # "construction" as an active-phase key matches any of the
                # construction-type period types (real construction, renovation,
                # or conversion) — which one fires depends on the deal type.
                _construction_periods = {
                    PeriodType.construction, PeriodType.minor_renovation,
                    PeriodType.major_renovation, PeriodType.conversion,
                }
                if phase.period_type.value == _refi_phase_key or (
                    _refi_phase_key in ("operation_stabilized", "stabilized")
                    and phase.period_type == PeriodType.stabilized
                ) or (
                    _refi_phase_key in ("operation_lease_up", "lease_up")
                    and phase.period_type == PeriodType.lease_up
                ) or (
                    _refi_phase_key == "construction"
                    and phase.period_type in _construction_periods
                ):
                    _net = _refi_event["net_proceeds"]
                    _refi_items = [
                        _expense_line_item(
                            deal_uuid, period,
                            LineItemCategory.capital_event,
                            "Refi — Bridge Payoff",
                            _refi_event["bridge_balloon"],
                            {"phase": phase.period_type.value, "direction": "outflow",
                             "detail": "balloon_balance"},
                        ),
                    ]
                    if _refi_event["prepay_penalty"] > ZERO:
                        _refi_items.append(_expense_line_item(
                            deal_uuid, period,
                            LineItemCategory.capital_event,
                            "Refi — Prepay Penalty",
                            _refi_event["prepay_penalty"],
                            {"phase": phase.period_type.value, "direction": "outflow"},
                        ))
                    if _refi_event["financing_costs"] > ZERO:
                        _refi_items.append(_expense_line_item(
                            deal_uuid, period,
                            LineItemCategory.capital_event,
                            "Refi — Financing Costs",
                            _refi_event["financing_costs"],
                            {"phase": phase.period_type.value, "direction": "outflow"},
                        ))
                    if _net > ZERO:
                        _refi_items.append(_expense_line_item(
                            deal_uuid, period,
                            LineItemCategory.capital_event,
                            "Refi — Net Proceeds to Equity",
                            _net,
                            {"phase": phase.period_type.value, "direction": "inflow",
                             "detail": "net_refi_proceeds"},
                        ))
                    elif _net < ZERO:
                        _refi_items.append(_expense_line_item(
                            deal_uuid, period,
                            LineItemCategory.capital_event,
                            "Refi — Equity Call (Shortfall)",
                            abs(_net),
                            {"phase": phase.period_type.value, "direction": "outflow",
                             "detail": "refi_shortfall"},
                        ))
                    period_result["line_items"].extend(_refi_items)
                    # Adjust net cash flow for the refi event
                    period_result["net_cash_flow"] = _q(
                        period_result["net_cash_flow"] + _net
                    )
                    _refi_injected = True


            # ── Inject found-money events into the waterfall ─────────────
            # Float earnings hit the GP/LP waterfall as a lump sum at the
            # waterfall_milestone_id period. The waterfall adds them to
            # distributable cash and distributes through normal tier order.
            if period in _found_money_period_to_source_idx:
                for _fr_idx in _found_money_period_to_source_idx[period]:
                    _fr_fm = _float_results[_fr_idx]
                    _fm_amt = _fr_fm.total_earnings
                    if _fm_amt <= ZERO:
                        continue
                    period_result["line_items"].append(_expense_line_item(
                        deal_uuid, period,
                        LineItemCategory.capital_event,
                        f"Found Money → Waterfall ({_fr_fm.float_source_id!s:.8}…)",
                        _fm_amt,
                        {"phase": phase.period_type.value,
                         "direction": "informational",
                         "detail": "found_money",
                         "float_source_id": str(_fr_fm.float_source_id),
                         "parent_module_id":
                             str(_fr_fm.parent_module_id)
                             if _fr_fm.parent_module_id else None},
                    ))

            # ── Inject prepay penalties at exit ───────────��────────────────
            if phase.period_type == PeriodType.exit and month_index == 0:
                for _pp_cm in capital_modules:
                    _pp_src = _pp_cm.source or {}
                    _pp_pct = _to_decimal(_pp_src.get("prepay_penalty_pct"))
                    if _pp_pct <= ZERO or _pp_src.get("is_bridge"):
                        continue
                    _pp_amt = _to_decimal(_pp_src.get("amount"))
                    # Voluntary float-earnings paydowns reduce the effective
                    # principal driving the balloon and prepay calc. The cash
                    if _pp_amt <= ZERO:
                        continue
                    _pp_carry = _pp_cm.carry or {}
                    _pp_rate = _pp_src.get("interest_rate_pct") or _pp_carry.get("io_rate_pct")
                    _pp_amort = int(_pp_src.get("amort_term_years") or 30)
                    _pp_io = int((_pp_carry.get("io_period_months") or 0))
                    # months active = total hold period
                    _pp_months = sum(p.months for p in phases if p.period_type != PeriodType.exit)
                    _pp_bal = _balloon_balance(_pp_amt, _pp_rate, _pp_amort, _pp_months, io_months=_pp_io)
                    _pp_cost = _q(_pp_bal * _pp_pct / HUNDRED)
                    if _pp_cost > ZERO:
                        period_result["line_items"].append(_expense_line_item(
                            deal_uuid, period,
                            LineItemCategory.capital_event,
                            f"Prepay Penalty — {getattr(_pp_cm, 'label', 'Debt')}",
                            _pp_cost,
                            {"phase": "exit", "direction": "outflow",
                             "prepay_penalty_pct": float(_pp_pct),
                             "balloon_balance": float(_pp_bal)},
                        ))
                        period_result["net_cash_flow"] = _q(
                            period_result["net_cash_flow"] - _pp_cost
                        )

            # Phase E: per-period draw inflow — capital arrives as uses fire.
            # BALANCE_ONLY reserves injected as lump at phase start (month_index==0).
            # Non-BALANCE_ONLY uses draw matching inflow same period (net zero to balance).
            _draw = compute_period_draw_inflow(
                phase=phase,
                month_index=month_index,
                use_lines=use_lines,
                use_line_phase_overrides=_ul_phase_overrides,
                balance_only_labels=_BALANCE_ONLY_LABELS,
                use_line_phase_map=_USE_LINE_PHASE_MAP,
                already_drawn_reserves=_drawn_reserve_labels,
            )
            if month_index == 0:
                for _rul in use_lines:
                    _rlbl = getattr(_rul, "label", "")
                    if _rlbl not in _BALANCE_ONLY_LABELS or _rlbl in _drawn_reserve_labels:
                        continue
                    _rpt = (
                        (_ul_phase_overrides or {}).get(_rul.id)
                        or _USE_LINE_PHASE_MAP.get(
                            str(getattr(_rul, "phase", "") or "").replace("UseLinePhase.", ""),
                            set(),
                        )
                    )
                    if phase.period_type in _rpt:
                        _drawn_reserve_labels.add(_rlbl)
            if _draw > ZERO:
                _reason = (
                    DrawAllocationReason.acquisition
                    if phase.period_type == PeriodType.acquisition
                    else DrawAllocationReason.reserve_prefund
                    if month_index == 0
                    else DrawAllocationReason.period_funding
                )
                # Primary funding module: highest-priority eligible module for this
                # period (permissive — all modules eligible until eligibility configured).
                _routed = _route_use_to_sources(
                    _SN(eligible_module_ids=[], cost_category=""),
                    capital_modules,
                )
                _primary_mod_id = _routed[0].id if _routed else None
                draw_event_rows.append(CapitalDrawEvent(
                    scenario_id=deal_uuid,
                    project_id=project.id,
                    period=period,
                    period_type=phase.period_type.value,
                    amount=_q(_draw),
                    allocation_reason=_reason,
                    module_id=_primary_mod_id,
                ))

            # Cumulative cash balance:
            #   Phase E: add draw inflow first (reserves pre-fund at phase start,
            #     non-BALANCE_ONLY uses cancel with capital_outflow in NCF).
            #   First stabilized period: reset to the operating reserve.  The debt is
            #     sized so that cash flows through lease-up land exactly at the reserve
            #     amount when stabilization begins.
            #   Post-seed (stabilized): positive NCF is distributable profit — do NOT
            #     add to balance.  Negative NCF drains the reserve — DO subtract.
            _is_stabilized = phase.period_type == PeriodType.stabilized
            _ncf = period_result["net_cash_flow"]
            cumulative_cash_flow += _draw
            if _is_stabilized and not _operating_reserve_seeded:
                cumulative_cash_flow = _op_reserve_amount
                _operating_reserve_seeded = True
            elif _operating_reserve_seeded:
                # Post-seed: only drain on negative NCF
                if _ncf < 0:
                    cumulative_cash_flow += _ncf
            else:
                # Pre-stabilized (acquisition, construction, lease-up): accumulate all NCF
                cumulative_cash_flow += _ncf
            cash_flow_rows.append(
                CashFlow(
                    scenario_id=deal_uuid,
                    project_id=project.id,
                    period=period,
                    period_type=phase.period_type,
                    gross_revenue=_q(period_result["gross_revenue"]),
                    vacancy_loss=_q(period_result["vacancy_loss"]),
                    effective_gross_income=_q(period_result["effective_gross_income"]),
                    operating_expenses=_q(period_result["operating_expenses"]),
                    capex_reserve=_q(period_result["capex_reserve"]),
                    noi=_q(period_result["noi"]),
                    debt_service=_q(period_result["debt_service"]),
                    net_cash_flow=_q(period_result["net_cash_flow"]),
                    cumulative_cash_flow=_q(cumulative_cash_flow),
                )
            )
            line_item_rows.extend(period_result["line_items"])
            net_cash_flow_series.append(_q(period_result["net_cash_flow"]))
            period += 1

    # Phase E: bulk-insert draw events for this project (prior rows purged above
    # at the compute_cash_flows level alongside CashFlow / CashFlowLineItem).
    if draw_event_rows:
        session.add_all(draw_event_rows)

    total_project_cost = _calculate_total_project_cost(line_item_rows)
    # equity_required = the funding gap this project's equity must fill =
    # max(0, Σ UseLine.amount (excluding exit phase) − Σ debt module
    # principal via junction overlay). Uses Σ Uses, NOT TPC: the S&U panel
    # the user sees includes Operating Reserve, Lease-Up Reserve, and
    # capitalized-interest stub lines that are excluded from TPC for
    # auto-sizing purposes but are real cash-out items the equity stack
    # has to cover. Mirroring the panel's visible total keeps Equity
    # Required ↔ Sources Gap reconcilable from a single mental model.
    #
    # Single-project deals: the waterfall engine subsequently overwrites
    # equity_required with the richer LP+GP capital-call sum. Multi-
    # project deals: the waterfall's scenario-wide sum gets dumped onto
    # the default project only — nonsense — so the waterfall skips the
    # overwrite for multi-project and these per-project values stand.
    _project_debt_principal = ZERO
    for _cm_eq in capital_modules:
        if not _is_debt_cm(_cm_eq):
            continue
        _src_eq = _cm_eq.source or {}
        if _src_eq.get("is_bridge"):
            continue
        _amt_eq = _src_eq.get("amount")
        if _amt_eq:
            try:
                _project_debt_principal += Decimal(str(_amt_eq))
            except Exception:
                pass
    _project_total_uses = ZERO
    for _ul_eq in use_lines:
        _ph = str(getattr(_ul_eq.phase, "value", _ul_eq.phase) or "")
        if _ph == "exit":
            continue
        try:
            _project_total_uses += Decimal(str(_ul_eq.amount or 0))
        except Exception:
            pass
    equity_required = (
        _project_total_uses - _project_debt_principal
        if _project_total_uses > _project_debt_principal
        else ZERO
    )
    total_timeline_months = len(cash_flow_rows)

    if stabilized_noi_monthly is None and cash_flow_rows:
        stabilized_noi_monthly = _to_decimal(cash_flow_rows[-1].noi)
    noi_stabilized = _q((stabilized_noi_monthly or ZERO) * Decimal("12"))

    # Exit Year NOI = trailing-12-month NOI from the final operational periods.
    # This is distinct from Stabilized NOI (year-1 of stabilization) and does
    # respond to rent-growth + hold-period sensitivity axes.
    _op_rows = [
        r for r in cash_flow_rows
        if r.period_type in (PeriodType.lease_up, PeriodType.stabilized)
    ]
    if len(_op_rows) >= 12:
        noi_exit_year = _q(sum((_to_decimal(r.noi) for r in _op_rows[-12:]), ZERO))
    elif _op_rows:
        noi_exit_year = _q(_to_decimal(_op_rows[-1].noi) * Decimal("12"))
    else:
        noi_exit_year = noi_stabilized

    cap_rate_on_cost_pct = (
        _q((noi_stabilized / total_project_cost) * HUNDRED)
        if total_project_cost > ZERO
        else ZERO
    )

    # DSCR = Stabilized NOI / Annual Operation Debt Service.
    # _schedule_module_ids are excluded from operation_debt_monthly because
    # their per-period DS comes from _schedule_period_ds (not the two-phase
    # constant). For the DSCR aggregate denominator, add back the operation-
    # phase DS of each scheduled module — otherwise DSCR = NOI/0 and the
    # dual-constraint sizing loop has no cap signal.
    _dscr_op_debt_monthly = operation_debt_monthly + _scheduled_operation_ds(
        capital_modules, _schedule_module_ids
    )
    annual_operation_debt_service = _dscr_op_debt_monthly * Decimal("12")
    dscr = (
        _q(noi_stabilized / annual_operation_debt_service)
        if annual_operation_debt_service > ZERO
        else ZERO
    )

    # Debt Yield = Stabilized NOI / Total Outstanding Debt Balance
    total_debt_balance = ZERO
    for cm in capital_modules:
        if not _is_debt_cm(cm):
            continue
        src = cm.source or {}
        if src.get("is_bridge"):
            continue  # bridge is taken out by perm — don't double-count
        amt = src.get("amount")
        if amt:
            total_debt_balance += Decimal(str(amt))
    debt_yield_pct = (
        _q((noi_stabilized / total_debt_balance) * HUNDRED)
        if total_debt_balance > ZERO
        else ZERO
    )

    project_irr_unlevered = _compute_xirr(net_cash_flow_series)
    project_irr_levered = project_irr_unlevered

    outputs = OperationalOutputs(
        scenario_id=deal_uuid,
        project_id=project.id,
        total_project_cost=_q(total_project_cost),
        equity_required=_q(equity_required),
        total_timeline_months=total_timeline_months,
        noi_stabilized=noi_stabilized,
        cap_rate_on_cost_pct=cap_rate_on_cost_pct,
        dscr=dscr,
        debt_yield_pct=debt_yield_pct,
        project_irr_levered=project_irr_levered,
        project_irr_unlevered=project_irr_unlevered,
        computed_at=datetime.now(timezone.utc),
    )

    summary = {
        "deal_model_id": str(deal_uuid),
        "cash_flow_count": total_timeline_months,
        "line_item_count": len(line_item_rows),
        "total_project_cost": _q(total_project_cost),
        "equity_required": _q(equity_required),
        "total_timeline_months": total_timeline_months,
        "noi_stabilized": noi_stabilized,
        "noi_exit_year": noi_exit_year,
        "cap_rate_on_cost_pct": cap_rate_on_cost_pct,
        "project_irr_unlevered": project_irr_unlevered,
        "project_irr_levered": project_irr_levered,
        "dscr": dscr,
        "debt_yield_pct": debt_yield_pct,
    }

    # ── Bank-account proof (validation only) ──────────────────────────────
    # Per the reserves-spec-align design (§3 / spec critique #4), the
    # bank-account proof is a sanity check on the new IR / ODR / OR reserve
    # set — not the sizing path for a "Cash Flow Support Reserve" UseLine.
    # The CFSR auto-upsert was removed in Slice 5b; Operating Deficit
    # Reserve (Slice 4) is the engine's first-class home for the operating
    # shortfall. Slice 5d will extend the proof with a Stabilization-anchor
    # validator so an early-anchored Stabilization milestone surfaces as a
    # deal-level error instead of being silently absorbed by OR.
    bank_account_proof = _run_bank_account_proof(
        cash_flow_rows=cash_flow_rows,
        use_lines=use_lines,
        phases=phases,
        milestone_dates=milestone_dates,
        construction_monthly=construction_monthly,
        dev_fee_paydowns_by_period=prev_dev_fee_paydowns,
    )
    if bank_account_proof is not None:
        summary["bank_account_proof"] = bank_account_proof
    # Persist the proof on OperationalOutputs so the Underwriting view can
    # read it at render time without re-running the simulation. Always
    # write — None when no proof window exists — so the column clears
    # stale data on deals that no longer model an operating phase.
    outputs.bank_account_proof = bank_account_proof

    # Persist float-earnings results so the UI can render the period-level
    # balance schedule + warnings without re-running compute. Always write —
    # None when no float_earnings sources exist — so stale data clears.
    if _float_results or _float_warnings:
        # Pre-resolve found money periods so the waterfall can inject earnings
        # into net_cash at the right period without re-loading milestones.
        _found_money_by_period: dict[int, Decimal] = {}
        for _fr in _float_results:
            if _fr.total_earnings <= ZERO or _fr.waterfall_milestone_id is None:
                continue
            _p = resolve_milestone_period(
                milestone_id=_fr.waterfall_milestone_id,
                milestone_map=milestone_map,
                milestone_month_map=_milestone_month_map,
            )
            if _p is None:
                continue
            _found_money_by_period[_p] = _found_money_by_period.get(_p, ZERO) + _fr.total_earnings

        outputs.float_earnings_series = {
            "sources": [
                {
                    "float_source_id": str(r.float_source_id),
                    "parent_module_id": str(r.parent_module_id) if r.parent_module_id else None,
                    "total_earnings": float(r.total_earnings),
                    "waterfall_milestone_id": str(r.waterfall_milestone_id) if r.waterfall_milestone_id else None,
                    "schedule": [
                        {
                            "period": row.period,
                            "opening_balance": float(row.opening_balance),
                            "monthly_earnings": float(row.monthly_earnings),
                            "closing_balance": float(row.closing_balance),
                        }
                        for row in r.schedule
                    ],
                    "warnings": list(r.warnings),
                }
                for r in _float_results
            ],
            # Period number (str-keyed for JSONB) → total found money amount
            # injected into net_cash at that period in the waterfall.
            "found_money_periods": {
                str(p): float(a) for p, a in _found_money_by_period.items()
            },
            "warnings": list(_float_warnings),
        }
        if _float_warnings:
            summary.setdefault("warnings", []).extend(_float_warnings)
        summary["float_earnings_total"] = float(
            sum((r.total_earnings for r in _float_results), ZERO)
        )
    else:
        outputs.float_earnings_series = None

    # Write computed total_earnings back to each float_earnings module's
    # source["amount"] so the S&U panel can show the Found Money amount
    # without re-running the engine. Zero clears stale values when blocked.
    for _fr in _float_results:
        _fm = next((m for m in capital_modules if m.id == _fr.float_source_id), None)
        if _fm is not None:
            _new_src = dict(_fm.source or {})
            _new_src["amount"] = float(_fr.total_earnings)
            _fm.source = _new_src

    # Tag every line-item with its owning project before persist. The
    # CashFlowLineItem / _expense_line_item constructors inside _compute_period
    # default project_id=None; this sweep gives the Underwriting rollup a
    # per-project filter without threading the id through every call site.
    for _li in line_item_rows:
        if _li.project_id is None:
            _li.project_id = project.id

    session.add_all(cash_flow_rows)
    session.add_all(line_item_rows)
    session.add(outputs)
    await session.flush()

    session.add(
        WorkflowRunManifest(
            scenario_id=deal_uuid,
            engine="cashflow",
            inputs_json=_json_ready(
                {
                    "model_id": str(deal_uuid),
                    "project_type": _project_type_name(deal_model.project_type),
                    "unit_count": _manifest_unit_count(inputs),
                    "income_stream_count": len(streams),
                }
            ),
            outputs_json=_json_ready(summary),
        )
    )
    await session.flush()

    return summary


async def _load_deal_model(session: AsyncSession, deal_model_id: UUID) -> Scenario | None:
    result = await session.execute(
        select(Scenario)
        .options(
            selectinload(Scenario.projects).options(
                selectinload(Project.operational_inputs),
                selectinload(Project.income_streams),
                selectinload(Project.expense_lines),
                selectinload(Project.use_lines),
            ),
        )
        .where(Scenario.id == deal_model_id)
    )
    return result.scalar_one_or_none()


def _phase_string_from_milestone_id(
    milestone_id: "UUID | None",
    milestone_map: "dict | None",
) -> str | None:
    """Resolve a milestones.id FK to its canonical phase-string value.

    Returns the milestone's ``milestone_type`` (e.g. "close", "operation_stabilized")
    which is accepted by both ``_APS_TO_USE_PHASE`` and ``_APS_TO_RANK``. Returns
    ``None`` when the FK is unset or the milestone isn't in the map.
    """
    if not milestone_id or not milestone_map:
        return None
    m = milestone_map.get(milestone_id)
    if m is None:
        return None
    mt = str(getattr(m, "milestone_type", "") or "").replace("MilestoneType.", "")
    return mt or None


def _apply_milestone_fk_overlay_inplace(
    module: CapitalModule,
    junction: CapitalModuleProject,
    milestone_map: "dict",
) -> None:
    """Overlay milestone-FK-derived phase strings onto module.active_phase_start
    / active_phase_end (in-memory only — not persisted).

    Resolution order, highest priority first:
      1. Junction's per-project milestone FK (multi-project scenarios)
      2. Module's scenario-level milestone FK
      3. Whatever the module already has on ``active_phase_start`` /
         ``active_phase_end`` (legacy string field — unchanged)

    The in-memory mutation makes downstream helpers that read the string
    field (``_loan_pre_op_months``, ``_APS_TO_USE_PHASE`` lookups, refi-event
    activation, etc.) automatically benefit from rename-safe, trigger-chain
    aware milestone references without threading milestone_map through every
    call site.
    """
    from_id = (
        getattr(junction, "active_from_milestone_id", None)
        or getattr(module, "active_from_milestone_id", None)
    )
    from_phase = _phase_string_from_milestone_id(from_id, milestone_map)
    if from_phase:
        module.active_phase_start = from_phase

    to_id = (
        getattr(junction, "active_to_milestone_id", None)
        or getattr(module, "active_to_milestone_id", None)
    )
    to_phase = _phase_string_from_milestone_id(to_id, milestone_map)
    if to_phase:
        module.active_phase_end = to_phase


def _apply_junction_overlay_inplace(
    session: AsyncSession,
    module: CapitalModule,
    junction: CapitalModuleProject,
) -> None:
    """Phase 2c1: overlay junction.amount + junction.auto_size onto module.source.

    Called from ``_per_project_capital_modules`` at load time. Only writes
    when the values actually differ — single-project scenarios where
    junction.amount matches source.amount become no-ops. The write is
    an in-place mutation of ``module.source`` (a JSON dict) which
    SQLAlchemy tracks as dirty and flushes on the next session.flush().
    """
    junction_amount = junction.amount
    if junction_amount is None:
        return
    current_src = dict(module.source or {})
    try:
        j_amount_dec = Decimal(str(junction_amount))
    except Exception:
        return
    current_amount = current_src.get("amount")
    try:
        c_amount_dec = (
            Decimal(str(current_amount)) if current_amount is not None else None
        )
    except Exception:
        c_amount_dec = None
    current_auto = bool(current_src.get("auto_size"))
    j_auto = bool(junction.auto_size)
    if c_amount_dec == j_amount_dec and current_auto == j_auto:
        return  # no-op — junction matches source already
    new_src = dict(current_src)
    new_src["amount"] = float(j_amount_dec) if j_amount_dec else 0.0
    new_src["auto_size"] = j_auto
    module.source = new_src  # SQLAlchemy sees this as a change; flush writes it


async def _sync_junction_amounts_after_compute(
    session: AsyncSession,
    scenario_id: UUID,
    project_id: UUID,
    modules: list[CapitalModule],
) -> None:
    """Phase 2c1: write post-auto-size amounts back to the junction.

    After ``_auto_size_debt_modules`` finishes, ``module.source["amount"]``
    holds the final sized principal for the active project. Mirror that
    onto the project's junction row so the Coverage modal shows the
    computed amount next time the user opens it, and so subsequent
    per-project compute iterations on the same scenario read a junction
    that agrees with the latest engine output.
    """
    for module in modules:
        src_amount = (module.source or {}).get("amount")
        if src_amount is None:
            continue
        try:
            amt = _whole_dollar(Decimal(str(src_amount)))
        except Exception:
            continue
        # ORM dirty tracking only. Bulk sa_update(CapitalModuleProject)
        # expires junction-row attrs in the identity map and triggers a lazy
        # refresh on later access — MissingGreenlet in async context.
        junction = (await session.execute(
            select(CapitalModuleProject).where(
                CapitalModuleProject.capital_module_id == module.id,
                CapitalModuleProject.project_id == project_id,
            )
        )).scalar_one_or_none()
        if junction is not None:
            junction.amount = amt


async def _reconcile_module_amounts_from_junctions(
    session: AsyncSession,
    scenario_id: UUID,
) -> None:
    """Set module.source["amount"] = Σ(junction.amount) across all projects.

    Fixes the last-project-wins bug: when multiple projects share a Source,
    each project's auto-size writes its own computed amount to
    ``CapitalModule.source["amount"]``. After all per-project computations
    complete, the module-level total should equal the sum of all per-project
    junction amounts. For single-project scenarios, Σ(junction) == existing
    amount and this is a no-op.
    """
    rows = (await session.execute(
        select(CapitalModule, func.sum(CapitalModuleProject.amount).label("junction_total"))
        .join(CapitalModuleProject, CapitalModuleProject.capital_module_id == CapitalModule.id)
        .where(CapitalModule.scenario_id == scenario_id)
        .group_by(CapitalModule.id)
    )).all()

    for module, junction_total in rows:
        if junction_total is None:
            continue
        try:
            total_dec = _q(Decimal(str(junction_total)))
        except Exception:
            continue
        src = dict(module.source or {})
        current = src.get("amount")
        try:
            current_dec = Decimal(str(current)) if current is not None else None
        except Exception:
            current_dec = None
        if current_dec is not None and _q(current_dec) == total_dec:
            continue
        src["amount"] = str(total_dec)
        module.source = src


async def _per_project_capital_modules(
    session: AsyncSession,
    scenario_id: UUID,
    project_id: UUID,
) -> list[CapitalModule]:
    """Load CapitalModules scoped to a single Project via the junction table.

    Only modules with a ``capital_module_projects`` row for ``project_id``
    are returned. For single-project scenarios (every production deal today)
    the backfill from migration 0048 created one junction row per module
    pointing at the default project — so this query returns the same module
    list as the old scenario-wide ``WHERE scenario_id=X`` lookup. Math is
    byte-identical.

    For multi-project scenarios, each project sees only the Sources attached
    to it. A **shared Source** (junction rows for both P1 and P2) appears
    in both projects' module lists — SQLAlchemy's session-scoped identity
    map hands each iteration its own ORM instance reference.

    **Per-project amount overlay (Phase 2c1, 2026-04-22):** when the junction
    row carries a non-null ``amount``, overlay it onto ``module.source["amount"]``
    and ``module.source["auto_size"]`` in memory. This makes divergent per-
    project amounts set via the Coverage modal actually take effect in the
    engine. The overlay is persisted via a direct SQL UPDATE before the
    engine runs so downstream ``session.refresh(cm, ["source"])`` calls
    reload the overlaid value rather than wiping it. Post-compute, the
    auto-sized amount is synced back to the junction by
    ``_sync_junction_amounts_after_compute`` so the Coverage modal shows
    the correct amount on the next render.

    Single-project scenarios: junction.amount == module.source.amount from
    Phase 1 backfill, so the overlay is a no-op and math is byte-identical.

    See ``is_shared_source`` and ``junction_amount_for`` for helpers that
    read the junction directly.
    """
    rows = (
        await session.execute(
            select(CapitalModule, CapitalModuleProject)
            .join(
                CapitalModuleProject,
                CapitalModuleProject.capital_module_id == CapitalModule.id,
            )
            .where(
                CapitalModule.scenario_id == scenario_id,
                CapitalModuleProject.project_id == project_id,
            )
            .order_by(CapitalModule.stack_position)
        )
    ).all()
    # Phase 2c2 (2026-05-21): build a milestone_map from every FK referenced
    # by the loaded modules and junctions, then overlay milestone-derived phase
    # strings onto module.active_phase_start / active_phase_end before the
    # junction-amount overlay. This makes downstream engine reads of the
    # legacy string field (loan pre-op months, _APS_TO_USE_PHASE lookups,
    # refi-event activation) rename-safe and trigger-chain aware without
    # threading a milestone_map through every call site.
    milestone_ids: set[UUID] = set()
    for module, junction in rows:
        for attr_obj, attr_name in (
            (module, "active_from_milestone_id"),
            (module, "active_to_milestone_id"),
            (junction, "active_from_milestone_id"),
            (junction, "active_to_milestone_id"),
        ):
            mid = getattr(attr_obj, attr_name, None)
            if mid:
                milestone_ids.add(mid)
    milestone_map: dict[UUID, Milestone] = {}
    if milestone_ids:
        ms_rows = (await session.execute(
            select(Milestone).where(Milestone.id.in_(milestone_ids))
        )).scalars().all()
        milestone_map = {m.id: m for m in ms_rows}

    modules: list[CapitalModule] = []
    for module, junction in rows:
        if milestone_map:
            _apply_milestone_fk_overlay_inplace(module, junction, milestone_map)
        _apply_junction_overlay_inplace(session, module, junction)
        modules.append(module)
    if modules:
        # Persist the overlays as a single batched operation so later
        # session.refresh(cm, ["source"]) calls re-read the overlaid amount
        # from the DB rather than wiping it.
        await session.flush()
        return modules

    # Self-heal: modules created after migration 0048 (deal creation path,
    # setup-complete handler, etc.) don't all insert junction rows. If this
    # scenario has modules but no junction rows pointing at this project,
    # and the scenario has exactly one project, auto-create the junction
    # (matching what the 0048 backfill would have produced) and return the
    # now-attached modules. No-op for genuinely multi-project scenarios
    # where divergent attachment is intentional.
    all_modules = list((await session.execute(
        select(CapitalModule)
        .where(CapitalModule.scenario_id == scenario_id)
        .order_by(CapitalModule.stack_position)
    )).scalars())
    if not all_modules:
        return []
    n_projects = int((await session.execute(
        select(func.count()).select_from(Project).where(Project.scenario_id == scenario_id)
    )).scalar_one())
    if n_projects != 1:
        return modules  # empty — don't guess attachment in multi-project scenarios
    already_attached = set((await session.execute(
        select(CapitalModuleProject.capital_module_id)
        .where(CapitalModuleProject.project_id == project_id)
    )).scalars())
    for cm in all_modules:
        if cm.id in already_attached:
            continue
        session.add(CapitalModuleProject(
            capital_module_id=cm.id,
            project_id=project_id,
            amount=Decimal(str((cm.source or {}).get("amount") or 0)),
            active_from=cm.active_phase_start,
            active_to=cm.active_phase_end,
            active_from_milestone_id=getattr(cm, "active_from_milestone_id", None),
            active_to_milestone_id=getattr(cm, "active_to_milestone_id", None),
            auto_size=bool((cm.source or {}).get("auto_size")),
        ))
    await session.flush()
    _diag(f"self-healed junction: scenario={scenario_id} project={project_id} attached={len(all_modules)}")

    # Overlay module-level milestone FK onto the freshly attached modules so
    # downstream engine reads of active_phase_start respect FK over legacy
    # string here too. (Self-healed junctions have no per-project override yet,
    # so only module-FKs matter on this branch.)
    self_heal_milestone_ids: set[UUID] = {
        mid for cm in all_modules
        for mid in (
            getattr(cm, "active_from_milestone_id", None),
            getattr(cm, "active_to_milestone_id", None),
        )
        if mid
    }
    if self_heal_milestone_ids:
        ms_rows = (await session.execute(
            select(Milestone).where(Milestone.id.in_(self_heal_milestone_ids))
        )).scalars().all()
        self_heal_map = {m.id: m for m in ms_rows}
        for cm in all_modules:
            from_phase = _phase_string_from_milestone_id(
                getattr(cm, "active_from_milestone_id", None), self_heal_map
            )
            if from_phase:
                cm.active_phase_start = from_phase
            to_phase = _phase_string_from_milestone_id(
                getattr(cm, "active_to_milestone_id", None), self_heal_map
            )
            if to_phase:
                cm.active_phase_end = to_phase
    return all_modules


async def is_shared_source(
    session: AsyncSession, capital_module_id: UUID
) -> bool:
    """Return True if the CapitalModule is attached to >1 Project via junction.

    Used by the Underwriting rollup to branch on shared-Source display and
    by future Phase 2f joint-draw logic. For every production deal today
    (1:1 backfill), always returns False.
    """
    count = (
        await session.execute(
            select(func.count())
            .select_from(CapitalModuleProject)
            .where(CapitalModuleProject.capital_module_id == capital_module_id)
        )
    ).scalar_one()
    return int(count) > 1


async def junction_amount_for(
    session: AsyncSession,
    capital_module_id: UUID,
    project_id: UUID,
) -> Decimal | None:
    """Return the per-project amount from the junction row, or None if the
    module isn't attached to that project. Decimal, not float, because this
    feeds financial math.
    """
    row = (
        await session.execute(
            select(CapitalModuleProject.amount).where(
                CapitalModuleProject.capital_module_id == capital_module_id,
                CapitalModuleProject.project_id == project_id,
            )
        )
    ).scalar_one_or_none()
    return Decimal(str(row)) if row is not None else None


async def is_shared_source(
    session: AsyncSession, capital_module_id: UUID
) -> bool:
    """Return True if the CapitalModule is attached to >1 Project via junction.

    Used by the Underwriting rollup to branch on shared-Source display and
    by future Phase 2f joint-draw logic. For every production deal today
    (1:1 backfill), always returns False.
    """
    count = (
        await session.execute(
            select(func.count())
            .select_from(CapitalModuleProject)
            .where(CapitalModuleProject.capital_module_id == capital_module_id)
        )
    ).scalar_one()
    return int(count) > 1


async def junction_amount_for(
    session: AsyncSession,
    capital_module_id: UUID,
    project_id: UUID,
) -> Decimal | None:
    """Return the per-project amount from the junction row, or None if the
    module isn't attached to that project. Decimal, not float, because this
    feeds financial math.
    """
    row = (
        await session.execute(
            select(CapitalModuleProject.amount).where(
                CapitalModuleProject.capital_module_id == capital_module_id,
                CapitalModuleProject.project_id == project_id,
            )
        )
    ).scalar_one_or_none()
    return Decimal(str(row)) if row is not None else None


async def _purge_existing_outputs(session: AsyncSession, deal_model_id: UUID) -> None:
    """Scenario-wide purge — deletes every output row for the scenario.

    Kept for anything that still wants to wipe the whole scenario at once;
    the per-project engine path now prefers :func:`_purge_project_outputs`
    so an iteration doesn't wipe its siblings' results mid-loop.
    """
    await session.execute(
        delete(CashFlowLineItem).where(CashFlowLineItem.scenario_id == deal_model_id)
    )
    await session.execute(delete(CashFlow).where(CashFlow.scenario_id == deal_model_id))
    await session.execute(
        delete(OperationalOutputs).where(OperationalOutputs.scenario_id == deal_model_id)
    )
    await session.execute(
        delete(CapitalDrawEvent).where(CapitalDrawEvent.scenario_id == deal_model_id)
    )


async def _purge_project_outputs(
    session: AsyncSession, deal_model_id: UUID, project_id: UUID
) -> None:
    """Purge a single project's output rows from the scenario.

    Also deletes legacy rows on this scenario where ``project_id IS NULL``
    — these exist only if migration 0050's backfill was skipped (never the
    case in practice, but the guard keeps the engine resilient).
    """
    for model in (CashFlowLineItem, CashFlow, OperationalOutputs, CapitalDrawEvent):
        await session.execute(
            delete(model).where(
                model.scenario_id == deal_model_id,
                (model.project_id == project_id) | (model.project_id.is_(None)),
            )
        )


# NOTE: _MILESTONE_TYPE_TO_PHASE_KEY and _milestone_dates_from_orm extracted
# to cashflow_compile.py (re-imported at top of this file).


# NOTE: _build_phase_plan, _apply_milestone_phase_overrides, _phase_milestone_key,
# _coerce_milestone_date, _calendar_month_count extracted to cashflow_compile.py
# (re-imported at top of this file).


# NOTE: _CONSTRUCTION_PERIOD_TYPES + _APS_TO_RANK + _resolve_horizon_months
# extracted to cashflow_compile.py (re-imported at top of this file).
# main's _resolve_horizon_months + signature change to _build_phase_plan
# (capital_modules, orm_milestones params) ported into cashflow_compile.py.


# NOTE: _module_rank, _eligible_retirers, _resolve_vehicle,
# _resolve_active_end_rank extracted to cashflow_compile.py.


# (_resolve_vehicle and _resolve_active_end_rank extracted to cashflow_compile.py)


# Maps UseLinePhase string values to the PeriodType(s) where the outflow fires.
# "construction" covers all building-work phases so it fires regardless of project type
# (acquisition uses minor_renovation; value_add uses major_renovation;
#  new_construction uses construction). "pre_construction" falls back to acquisition.
_USE_LINE_PHASE_MAP: dict[str, set[PeriodType]] = {
    "acquisition":     {PeriodType.acquisition},
    "pre_construction":{PeriodType.pre_construction},
    "construction":    {PeriodType.construction, PeriodType.major_renovation, PeriodType.minor_renovation, PeriodType.conversion},
    "renovation":      {PeriodType.minor_renovation, PeriodType.major_renovation},
    "conversion":      {PeriodType.conversion},
    "operation":            {PeriodType.lease_up, PeriodType.stabilized},
    "operation_lease_up":   {PeriodType.lease_up},
    "operation_stabilized": {PeriodType.stabilized},
    "exit":            {PeriodType.exit},
    "other":           {PeriodType.acquisition},
}

# Phase B: milestone_type → period_types mapping for FK-anchored UseLines.
# When a UseLine has active_from_milestone_id set, we resolve period_types from
# the milestone type rather than the legacy phase string.
_MILESTONE_TYPE_TO_PERIOD_TYPES: dict[str, set[PeriodType]] = {
    "close":                {PeriodType.acquisition},
    "under_contract":       {PeriodType.acquisition},
    "offer_made":           {PeriodType.acquisition},
    "pre_development":      {PeriodType.pre_construction},
    "construction":         {PeriodType.construction, PeriodType.major_renovation, PeriodType.minor_renovation, PeriodType.conversion},
    "operation_lease_up":   {PeriodType.lease_up},
    "operation_stabilized": {PeriodType.stabilized},
    "divestment":           {PeriodType.exit},
}


def _period_types_in_range(
    from_types: set[PeriodType],
    to_types: set[PeriodType],
    phases: list,
) -> set[PeriodType]:
    """Return all PeriodTypes that appear between from_types and to_types in the phase plan (inclusive)."""
    result: set[PeriodType] = set()
    in_range = False
    for p in phases:
        if p.period_type in from_types:
            in_range = True
        if in_range:
            result.add(p.period_type)
            if p.period_type in to_types:
                break
    return result or from_types


def _build_use_line_phase_overrides(
    use_lines: list,
    milestone_map: dict,
    phases: list,
) -> dict:
    """Pre-compute {use_line.id: set[PeriodType]} for UseLines with milestone FKs.

    UseLines without active_from_milestone_id are not included; the engine
    falls back to _USE_LINE_PHASE_MAP for those.
    """
    overrides: dict = {}
    for ul in use_lines:
        from_id = getattr(ul, "active_from_milestone_id", None)
        if not from_id:
            continue
        m_from = milestone_map.get(from_id)
        if m_from is None:
            continue
        mt_from = str(getattr(m_from, "milestone_type", "") or "").replace("MilestoneType.", "")
        from_types = _MILESTONE_TYPE_TO_PERIOD_TYPES.get(mt_from, set())
        if not from_types:
            continue
        to_id = getattr(ul, "spread_to_milestone_id", None)
        if to_id:
            m_to = milestone_map.get(to_id)
            if m_to is not None:
                mt_to = str(getattr(m_to, "milestone_type", "") or "").replace("MilestoneType.", "")
                to_types = _MILESTONE_TYPE_TO_PERIOD_TYPES.get(mt_to, set())
                if to_types:
                    overrides[ul.id] = _period_types_in_range(from_types, to_types, phases)
                    continue
        overrides[ul.id] = from_types
    return overrides

def _is_debt_cm(m: object) -> bool:
    """Return True if the capital module is a debt instrument (vehicle_type == "debt")."""
    vt = str(getattr(m, "vehicle_type", None) or "").replace("VehicleType.", "")
    return vt == "debt"

def _auto_size_ddf_module(
    capital_modules: list,
    use_lines: list,
) -> None:
    """Size any deferred_developer_fee module with auto_size=True.

    Runs after _auto_size_debt_modules so debt principals are final.
    DDF = max(0, uses_total - other_sources_total), capped at the total
    developer fee (sum of is_auto_dev_fee + is_auto_acquisition_fee lines).
    """
    _ZERO = Decimal("0")
    ddf_modules = [
        m for m in capital_modules
        if str(getattr(m, "vehicle_type", None) or "").replace("VehicleType.", "") == "deferred_developer_fee"
        and bool((m.source or {}).get("auto_size"))
    ]
    if not ddf_modules:
        return

    uses_total = sum(
        (_to_decimal(getattr(ul, "amount", _ZERO)) for ul in use_lines),
        _ZERO,
    )
    other_sources_total = sum(
        (
            _to_decimal((m.source or {}).get("amount", _ZERO))
            for m in capital_modules
            if str(getattr(m, "vehicle_type", None) or "").replace("VehicleType.", "")
            not in ("deferred_developer_fee", "float_earnings")
        ),
        _ZERO,
    )
    gap = max(_ZERO, uses_total - other_sources_total)

    dev_fee_total = sum(
        (
            _to_decimal(getattr(ul, "amount", _ZERO))
            for ul in use_lines
            if getattr(ul, "is_auto_dev_fee", False)
            or getattr(ul, "is_auto_acquisition_fee", False)
        ),
        _ZERO,
    )
    ddf_amount = min(gap, dev_fee_total) if dev_fee_total > _ZERO else gap

    for m in ddf_modules:
        src = dict(m.source or {})
        src["amount"] = float(ddf_amount)
        m.source = src


# ── Loan sub-type detection ───────────────────────────────────────────────────
# Maps label keywords → legacy loan subtype keys used by bridge sizing and
# cost-category assignment (acquisition_loan → "acquisition" cost cat).  Labels
# are set by Deal Setup wizard to standardised patterns (e.g. "Construction
# Loan (auto)", "Pre-Development Loan (auto)").
# This replaces funder_type comparisons inside the Phase B engine paths.
_LOAN_SUBTYPE_PATTERNS: list[tuple[str, str]] = [
    ("pre-development", "pre_development_loan"),
    ("pre_development",  "pre_development_loan"),
    ("acquisition loan", "acquisition_loan"),
    ("construction-to-perm", "bond"),
    ("construction to perm", "bond"),
    ("bond",            "bond"),
    ("construction",    "construction_loan"),
    ("bridge",          "bridge"),
    ("permanent",       "permanent_debt"),
    ("perm debt",       "permanent_debt"),
]


def _loan_subtype_from_module(m: object) -> str:
    """Derive a legacy loan-subtype key from a module's label.

    Used for bridge sizing and finance-cost category assignment.
    Returns an empty string when no known pattern matches.
    """
    label_lc = (getattr(m, "label", "") or "").lower()
    for kw, subtype in _LOAN_SUBTYPE_PATTERNS:
        if kw in label_lc:
            return subtype
    return ""

# Funder types for which Exit Vehicle applies — every funding line that has
# a real "ending" (matures, is refinanced, or is paid off at sale).  All
# other funder types (equity, grants, tax credits, owner_investment) are
# perpetuity-like from the engine's POV — single-draw, no vehicle UI.
# NOTE: _EXIT_VEHICLE_APPLIES extracted to cashflow_compile.py.

# ── Total Finance Costs default ────────────────────────────────────────────────
# Single global % applied to every CapitalModule's principal/commitment.
# Covers origination + lender legal + appraisal + title + environmental + similar.
# Engine writes one "{module.label} — Total Finance Costs" UseLine per module
# with is_auto_finance_cost=True.  User edit to any field flips the flag to
# False so engine stops recomputing; user delete then recompute regenerates.
# TODO: per-source-type rates (grants vs equity vs debt) via org setting.
DEFAULT_FINANCE_COST_PCT: Decimal = Decimal("2.0")

# Maps CapitalModule.active_phase_start → UseLinePhase string for closing cost Use lines.
# Covers both short-form values ("lease_up") and milestone-key variants ("operation_lease_up")
# that the wizard stores verbatim from form data.  Unmapped values fall back to
# "pre_construction" (construction loan close is the most common default).
_APS_TO_USE_PHASE: dict[str, str] = {
    "acquisition":          "acquisition",
    "close":                "acquisition",      # milestone key for "loan closes at acq"
    "offer_made":           "acquisition",      # milestone key variant
    "under_contract":       "acquisition",      # milestone key variant
    "pre_construction":     "pre_construction",
    "pre_development":      "pre_construction", # milestone key variant
    "construction":         "construction",
    "lease_up":             "operation",
    "operation_lease_up":   "operation",        # milestone key variant
    "stabilized":           "operation",
    "operation_stabilized": "operation",        # milestone key variant
    "exit":                 "exit",
    "divestment":           "exit",             # milestone key variant
}


def _carry_type_for_phase(carry: dict, is_construction: bool) -> str:
    """Extract carry_type from either flat, phased, or schedule format.

    For schedule format: construction → first phase; operation → first IO/PI phase.
    Normalises "accruing" → "capitalized_interest" in the cashflow engine only.
    """
    def _norm(ct: str) -> str:
        return "capitalized_interest" if ct == "accruing" else ct

    if carry.get("schedule"):
        schedule = carry["schedule"]
        if is_construction:
            return _norm(schedule[0].get("carry_type", "none")) if schedule else "none"
        # operations: find first IO or PI phase (IR/CI are pre-funded pre-op)
        for p in schedule:
            ct = _norm(p.get("carry_type", "none"))
            if ct in ("io_only", "pi"):
                return ct
        return "none"
    if carry.get("phases"):
        target = "construction" if is_construction else "operation"
        for p in carry["phases"]:
            if p.get("name") == target:
                return _norm(p.get("carry_type", "none"))
        return "none"
    return _norm(carry.get("carry_type", "none"))


def _get_phase_carry(carry: dict, phase_name: str) -> dict | None:
    """Return the carry config dict for a named phase, or None if not phased / not found."""
    if not carry.get("phases"):
        return None
    for p in carry["phases"]:
        if p.get("name") == phase_name:
            return p
    return None


def _constr_phase_rate_pct(carry: dict, src: dict) -> float | Decimal | None:
    """Construction-phase interest rate, sourced with the same precedence as
    `_op_phase_rate_and_amort` uses for the operation phase.

    Precedence:
      1. carry.schedule first IR/CI phase rate_pct (what cashflow charges pre-op)
      2. legacy carry.phases[name='construction'] io_rate_pct / rate_pct
      3. source.interest_rate_pct (legacy headline rate)
    """
    for p in (carry or {}).get("schedule") or []:
        ct = p.get("carry_type")
        if ct in ("interest_reserve", "capitalized_interest", "accruing") and p.get("rate_pct") is not None:
            return p["rate_pct"]
    constr_phase = _get_phase_carry(carry, "construction") or {}
    return (
        constr_phase.get("io_rate_pct")
        or constr_phase.get("rate_pct")
        or (src or {}).get("interest_rate_pct")
    )


def _op_phase_rate_and_amort(
    carry: dict, src: dict
) -> tuple[float | None, int]:
    """Return (rate_pct, amort_years) for the operation-phase debt the
    auto-sizer should use.

    Must match the values _period_ds_from_schedule_phase will charge during
    operation, otherwise sized DSCR will diverge from realised DSCR.

    Precedence:
      1. carry.schedule first IO/PI phase (what cashflow pays during op)
      2. legacy carry.phases[name='operation']
      3. source.interest_rate_pct / src.amort_term_years
      4. flat carry.io_rate_pct / default 30y
    """
    sched_op_phase = next(
        (
            p for p in ((carry or {}).get("schedule") or [])
            if p.get("carry_type") in ("io_only", "pi") and p.get("rate_pct") is not None
        ),
        None,
    )
    op_carry_legacy = _get_phase_carry(carry, "operation")
    rate_pct = (
        (sched_op_phase or {}).get("rate_pct")
        or (op_carry_legacy or {}).get("io_rate_pct")
        or (op_carry_legacy or {}).get("rate_pct")
        or src.get("interest_rate_pct")
        or (carry or {}).get("io_rate_pct")
    )
    amort_years = int(
        (sched_op_phase or {}).get("amort_term_years")
        or (op_carry_legacy or {}).get("amort_term_years")
        or src.get("amort_term_years")
        or 30
    )
    return rate_pct, amort_years


# ---------------------------------------------------------------------------
# Flexible carry schedule helpers (N-phase, supersedes two-phase system)
# ---------------------------------------------------------------------------

#: Maps user-facing milestone keys to PeriodType so we can locate the phase's
#: starting month in a compiled PhaseSpec list.
_MILESTONE_KEY_TO_PERIOD: dict[str, "PeriodType"] = {
    "close":                  PeriodType.acquisition,
    "pre_development":        PeriodType.pre_construction,
    "construction":           PeriodType.construction,
    "operation_lease_up":     PeriodType.lease_up,
    "operation_stabilized":   PeriodType.stabilized,
}


def _build_milestone_month_map(phases: list) -> dict[str, int]:
    """Map milestone key → absolute cashflow month when that phase begins."""
    result: dict[str, int] = {}
    cursor = 0
    for phase in phases:
        for key, pt in _MILESTONE_KEY_TO_PERIOD.items():
            if phase.period_type == pt and key not in result:
                result[key] = cursor
        cursor += phase.months
    result["_total"] = cursor
    return result


def _resolve_carry_schedule(
    schedule: list[dict],
    milestone_month_map: dict[str, int],
    loan_start_abs: int,
) -> list[dict]:
    """Expand a carry schedule into resolved phases with absolute loan-month boundaries.

    Each returned dict has:
      start_loan_month  — inclusive loan-relative month when phase becomes active
      end_loan_month    — exclusive loan-relative month when phase ends (None = remainder)
      carry_type        — normalised carry type string
      rate_pct          — float or None (None = inherit from source)
      amort_term_years  — int or None
    """
    resolved: list[dict] = []
    cursor = 0
    total_abs = milestone_month_map.get("_total", 0)
    for phase in schedule:
        dur = phase.get("duration") or {}
        dur_type = dur.get("type", "remainder")

        if dur_type == "months":
            phase_end = cursor + int(dur.get("months") or 0)
        elif dur_type == "milestone":
            mk = dur.get("milestone_key", "")
            abs_mk = milestone_month_map.get(mk, total_abs)
            phase_end: int | None = max(0, abs_mk - loan_start_abs)
        else:
            phase_end = None  # remainder — extends to loan maturity

        ct = (phase.get("carry_type") or "none").replace("accruing", "capitalized_interest")
        resolved.append({
            "start_loan_month": cursor,
            "end_loan_month": phase_end,
            "carry_type": ct,
            "rate_pct": phase.get("rate_pct"),
            "amort_term_years": phase.get("amort_term_years"),
            "label": phase.get("label", ""),
        })
        if phase_end is None:
            break  # remainder is always last
        cursor = phase_end
    return resolved


def _carry_for_loan_month(resolved: list[dict], loan_month: int) -> dict:
    """Return the active carry phase dict for a loan-relative month index."""
    for phase in resolved:
        end = phase["end_loan_month"]
        if end is None or loan_month < end:
            return phase
    return resolved[-1] if resolved else {"carry_type": "none", "rate_pct": None}


def _schedule_preop_months(
    schedule: list[dict],
    milestone_month_map: dict[str, int],
    loan_start_abs: int,
) -> int:
    """Total months of IR + CI carry phases in a schedule.

    Driven by what the user entered for each carry phase (months, milestone,
    or remainder) — not the deal's construction timeline. Used to size both
    constr_io_factor and the matching pre-funded Interest Reserve /
    Capitalized Construction Interest Use line so they reference the same
    duration and Sources = Uses.
    """
    if not schedule:
        return 0
    total_abs = milestone_month_map.get("_total", 0)
    resolved = _resolve_carry_schedule(schedule, milestone_month_map, loan_start_abs)
    total = 0
    for phase in resolved:
        ct = phase.get("carry_type")
        if ct not in ("interest_reserve", "capitalized_interest"):
            continue
        start = int(phase.get("start_loan_month") or 0)
        end = phase.get("end_loan_month")
        if end is None:
            end = max(0, total_abs - loan_start_abs)
        total += max(0, int(end) - start)
    return total


def _draw_schedule_for(carry_type: str, draw_type: str | None) -> str:
    """Map draw_type field → period_interest_months draw_schedule argument.

    Spec convention (reserves-spec-align, §2): "Interest accrues on the full
    funded balance from Close." Both IR and CI carry now default to ``"lump"``
    (full-balance accrual) so the IR pool covers the conservative lender case
    where 100% of the loan is funded day one. The legacy ``"linear"`` default
    for IR (average-draw N+1/2 factor) understated the reserve relative to
    spec; callers that genuinely need linear draws must set
    ``draw_type="draw_down"`` explicitly on the source.
    """
    if draw_type == "fully_drawn":
        return "lump"
    if draw_type == "draw_down":
        return "linear"
    return "lump"


def _compute_preop_carry_cost(
    schedule: list[dict],
    funded: Decimal,
    preop_months: int,
    base_rate: Decimal,
    milestone_month_map: dict[str, int],
    loan_start_abs: int,
    draw_type: str | None = None,
) -> Decimal:
    """Total IR + CI reserve cost for schedule phases that fall in the pre-op window.

    Phases with carry_type io_only / pi within the pre-op window are NOT
    pre-funded — they result in periodic monthly DS (handled in the main loop).
    """
    total = ZERO
    total_abs = milestone_month_map.get("_total", 0)
    cursor = 0
    for phase in schedule:
        dur = phase.get("duration") or {}
        dur_type = dur.get("type", "remainder")
        if dur_type == "months":
            phase_end = cursor + int(dur.get("months") or 0)
        elif dur_type == "milestone":
            mk = dur.get("milestone_key", "")
            abs_mk = milestone_month_map.get(mk, total_abs)
            phase_end = max(0, abs_mk - loan_start_abs)
        else:
            phase_end = preop_months  # remainder — cap at pre-op boundary
        phase_dur = max(0, min(phase_end, preop_months) - cursor)
        if phase_dur > 0:
            p_rate = Decimal(str(phase.get("rate_pct") or 0)) or base_rate
            p_ct = (phase.get("carry_type") or "none").replace("accruing", "capitalized_interest")
            if p_ct == "interest_reserve" and p_rate > ZERO:
                total += period_interest_months(funded, phase_dur, float(p_rate), draw_schedule=_draw_schedule_for("interest_reserve", draw_type))
            elif p_ct == "capitalized_interest" and p_rate > ZERO:
                total += compound_accrual(funded, p_rate / Decimal("1200"), phase_dur)
        if phase_end >= preop_months or dur_type == "remainder":
            break
        cursor = phase_end
    return total


def _scheduled_operation_ds(
    capital_modules: list, schedule_module_ids: set
) -> Decimal:
    """Sum monthly DS during the operation phase for scheduled-carry modules.

    Each scheduled module contributes the DS of its last PI/IO carry phase
    (typically the long-term P&I phase after IR/CI pre-funded phases). Used
    to keep the DSCR aggregate non-zero when debt is sized via carry.schedule.
    """
    total = ZERO
    for module in capital_modules:
        if module.id not in schedule_module_ids:
            continue
        carry = module.carry or {}
        principal = Decimal(str((module.source or {}).get("amount") or 0))
        if principal <= ZERO:
            continue
        base_rate = (module.source or {}).get("interest_rate_pct")
        operation_phase: dict | None = None
        for phase in (carry.get("schedule") or []):
            ct = (phase.get("carry_type") or "").replace(
                "accruing", "capitalized_interest"
            )
            if ct in ("pi", "io_only"):
                operation_phase = {**phase, "carry_type": ct}
        if operation_phase is not None:
            total += _period_ds_from_schedule_phase(
                operation_phase, principal, base_rate
            )
    return total


def _period_ds_from_schedule_phase(
    phase: dict,
    principal: Decimal,
    base_rate: float | None,
) -> Decimal:
    """Monthly DS contribution for a single carry schedule phase."""
    ct = phase.get("carry_type", "none")
    if ct in ("interest_reserve", "capitalized_interest", "none"):
        return ZERO  # pre-funded or no DS
    rate = phase.get("rate_pct") or base_rate
    if not rate:
        return ZERO
    if ct == "io_only":
        return _monthly_io(principal, rate)
    if ct == "pi":
        ay = int(phase.get("amort_term_years") or 30)
        return _monthly_pmt(principal, rate, ay)
    return ZERO


def _pv_from_pmt(monthly_pmt: Decimal, rate_pct: float | None, amort_years: int) -> Decimal:
    """Compute PV (loan principal) given a target monthly P&I payment."""
    if not rate_pct or monthly_pmt <= ZERO:
        return ZERO
    monthly_rate = Decimal(str(rate_pct)) / HUNDRED / Decimal("12")
    n = amort_years * 12
    if monthly_rate == ZERO:
        return _q(monthly_pmt * Decimal(n))
    pv_factor = (ONE - (ONE + monthly_rate) ** -n) / monthly_rate
    return _q(monthly_pmt * pv_factor)


def _estimate_stabilized_noi_monthly(
    streams: list,
    expense_lines: list,
    inputs: "OperationalInputs",
) -> Decimal:
    """Estimate stabilized monthly NOI from line items — used for debt sizing pre-pass."""
    stabilized = PeriodType.stabilized

    gross_revenue = ZERO
    for stream in streams:
        if not _is_stream_active(stream, stabilized):
            continue
        base = _stream_base_amount(stream)
        occupancy = _percent(stream.stabilized_occupancy_pct, default=Decimal("95"))
        bad_debt_pct = _percent(getattr(stream, "bad_debt_pct", None))
        concessions_pct = _percent(getattr(stream, "concessions_pct", None))
        gross_revenue += _q(base * occupancy * (ONE - bad_debt_pct - concessions_pct))

    operating_expenses = ZERO
    for line in expense_lines:
        if not _is_expense_line_active(line, stabilized):
            continue
        annual = _to_decimal(line.annual_amount)
        operating_expenses += _q(annual / Decimal("12"))

    return _q(gross_revenue - operating_expenses)


def _odr_pool(
    streams: list,
    expense_lines: list,
    inputs: "OperationalInputs",
    lease_up_months: int,
) -> Decimal:
    """Operating Deficit Reserve — Σ max(OpEx_k − LUR_k, 0) across lease-up.

    Spec §3.2: ODR funds the gap between operating cost and effective rent
    while the property absorbs from initial → stabilized occupancy. Sizes
    off the deal's curves (income ramp + opex ramp) so the pool reflects
    exactly the months the property cannot self-fund OpEx.

    Returns ``ZERO`` when ``lease_up_months <= 0`` — ODR is not auto-created
    on pure acquisition / stabilized deals (gating is enforced at the
    write-back site).

    The ramp model mirrors the period loop's contract: occupancy steps
    linearly from ``initial_occupancy_pct`` to ``stabilized_occupancy_pct``;
    per-stream effective revenue scales by ``(occ × (1 − bad_debt −
    concessions))``; expense lines flagged ``scale_with_lease_up`` follow
    the same ramp (floored at ``lease_up_floor_pct``); other lines stay
    at their stabilized monthly run-rate. Balance-independent — does not
    enter the principal divisor solve.
    """
    if lease_up_months <= 0:
        return ZERO

    # NULL initial_occupancy_pct → 0% (new construction, no pre-leasing).
    # Matches the wizard slider default and label text ("0% = new
    # construction (no pre-leasing). Higher = existing tenants staying
    # through lease-up."). The old 50% default produced a silent
    # mismatch where the UI showed 0 but the engine ran as if 50.
    initial_occ = _percent(inputs.initial_occupancy_pct, default=ZERO)
    stabilized_occ = Decimal("0.95")

    stream_inputs: list[tuple[Decimal, Decimal, Decimal]] = []
    for stream in streams:
        if not _is_stream_active(stream, PeriodType.lease_up):
            continue
        base = _stream_base_amount(stream)
        occ_target = _percent(stream.stabilized_occupancy_pct, default=Decimal("95"))
        bad_debt = _percent(getattr(stream, "bad_debt_pct", None))
        concessions = _percent(getattr(stream, "concessions_pct", None))
        net_factor = ONE - bad_debt - concessions
        stream_inputs.append((base, occ_target, net_factor))

    expense_inputs: list[tuple[Decimal, bool, Decimal]] = []
    for line in expense_lines:
        if not _is_expense_line_active(line, PeriodType.lease_up):
            continue
        monthly = _q(_to_decimal(line.annual_amount) / Decimal("12"))
        scale_with_ramp = bool(getattr(line, "scale_with_lease_up", False))
        floor_pct = _percent(getattr(line, "lease_up_floor_pct", None), default=ZERO)
        expense_inputs.append((monthly, scale_with_ramp, floor_pct))

    # Use the same curve as the period-loop and revenue side. Reading
    # `lease_up_curve` and `lease_up_curve_steepness` directly off
    # inputs keeps the three call sites byte-identical.
    _lu_curve = str(getattr(inputs, "lease_up_curve", None) or "linear")
    _lu_steep = getattr(inputs, "lease_up_curve_steepness", None)

    pool = ZERO
    for k in range(lease_up_months):
        ramp_occ = lease_up_ramp_occupancy(
            initial_occ=initial_occ,
            stabilized_occ=stabilized_occ,
            month_index=k,
            months=lease_up_months,
            curve=_lu_curve,
            steepness=_lu_steep,
        )

        income_k = ZERO
        for base, occ_target, net_factor in stream_inputs:
            stream_occ = (
                (ramp_occ / stabilized_occ) * occ_target
                if stabilized_occ > ZERO
                else ZERO
            )
            income_k += _q(base * stream_occ * net_factor)

        opex_k = ZERO
        for monthly, scale_with_ramp, floor_pct in expense_inputs:
            scale = ONE
            if scale_with_ramp:
                scale = max(ramp_occ, floor_pct)
            opex_k += _q(monthly * scale)

        deficit = opex_k - income_k
        if deficit > ZERO:
            pool += deficit

    return _q(pool)


def _ir_lease_up_pool(
    funded: Decimal,
    rate_pct: float | Decimal,
    n_months: int,
    lease_up_phase: "PhaseSpec",
    streams: list,
    expense_lines: list,
    inputs: "OperationalInputs",
) -> Decimal:
    """IR pool required for lease-up months. Spec convention: **LUR-blind**.

    Per the reserves-spec-align design (§3.1), the Interest Reserve must
    cover 100% of calculated interest over its active window — the lender
    wants full interest funded at Close regardless of how lease-up rent
    actually materializes. Revenue is therefore NOT netted against sized
    interest; the ramping LUR becomes a principal-paydown sweep at runtime
    (Slice 5) rather than a sizing offset.

    Returns ``funded × monthly_rate × n_months`` (full-balance accrual to
    match the ``"lump"`` draw-schedule used in ``_draw_schedule_for``).
    Parameters ``lease_up_phase``, ``streams``, ``expense_lines``, ``inputs``
    are kept in the signature so callers (and future net-of-revenue modes)
    do not need to be touched — but they are unused in the spec-aligned
    path.
    """
    del lease_up_phase, streams, expense_lines, inputs  # LUR-blind by design.
    if n_months <= 0 or rate_pct <= ZERO:
        return ZERO
    rate = Decimal(str(rate_pct))
    monthly_interest = _q(funded * rate / HUNDRED / Decimal("12"))
    return _q(monthly_interest * Decimal(n_months))


def _sum_ir_lease_up_interest(modules: list, phases: list) -> Decimal:
    """Monthly interest for IR-carry loans that extend through lease-up.

    After auto-sizing, call this to get the total monthly interest amount
    that income should cover during lease-up (passed to _compute_period).
    Only counts loans whose active window extends past the lease-up phase
    (end_rank > 4, i.e. through stabilized or further).
    """
    lease_up_phase = next((p for p in phases if p.period_type == PeriodType.lease_up), None)
    if not lease_up_phase:
        return ZERO
    total = ZERO
    for m in modules:
        if not _is_debt_cm(m):
            continue
        carry = m.carry or {}
        ct = _carry_type_for_phase(carry, is_construction=True)
        if ct != "interest_reserve":
            continue
        end_rank = _resolve_active_end_rank(m, modules)
        if end_rank <= 4:
            continue
        src = m.source or {}
        amount = _to_decimal(src.get("amount") or 0)
        if amount <= ZERO:
            continue
        # Use the schedule's IR-phase rate, not the headline source rate.
        # The cashflow engine charges the schedule rate during the carry
        # phase — pulling source.interest_rate_pct here over-estimates IR
        # whenever the schedule rate differs from the headline rate
        # (e.g. tax-exempt bonds with reduced carry-phase rate).
        rate = Decimal(str(
            _constr_phase_rate_pct(carry, src)
            or src.get("interest_rate_pct")
            or 0
        ))
        if rate > ZERO:
            total += _q(amount * rate / HUNDRED / Decimal("12"))
    return total


async def _auto_size_debt_modules(
    capital_modules: list,
    inputs: "OperationalInputs",
    streams: list,
    expense_lines: list,
    use_lines: list,
    phases: list,
    session: "AsyncSession",
    prev_noi_stabilized: Decimal | None = None,
    income_mode: str = "revenue_opex",
) -> None:
    """Pre-size CapitalModules that have source.auto_size=True.

    Writes source["amount"] in-memory and flushes to DB so that
    _sum_debt_service sees real numbers on the next call.

    Principal is sized to cover the base amount (DSCR-capped or gap-fill),
    PLUS the operating reserve, PLUS construction IO — solved algebraically so
    the cash balance at operations start equals the full reserve target.
    """
    _diag(f"=== _auto_size_debt_modules CALLED n_cap_mod={len(capital_modules)} n_ul={len(use_lines)}")
    for _dbg_cm in capital_modules:
        _diag(f"  [pre-filter] cm={_dbg_cm.id} vt={getattr(_dbg_cm,'vehicle_type',None)} source={_dbg_cm.source}")
    # Non-debt auto-sized sources (equity, grants) must NOT enter this loop.
    # Grants are pre-resolved by resolve_grant_caps; equity gets a separate pass below.
    auto_modules = [m for m in capital_modules if (m.source or {}).get("auto_size") and _is_debt_cm(m)]
    if not auto_modules:
        _diag("EARLY RETURN: no auto_modules")
        return

    # Milestone map for schedule resolution (months / milestone / remainder).
    # Needed by schedule-aware helpers when modules carry their own carry.schedule.
    _milestone_month_map = _build_milestone_month_map(phases)

    _diag(f"=== _auto_size_debt_modules CONTINUE n_auto={len(auto_modules)}")
    for _dm in capital_modules:
        _diag(f"  [in] cm={_dm.id} vt={getattr(_dm,'vehicle_type',None)} auto_size={(_dm.source or {}).get('auto_size')} amt_src={(_dm.source or {}).get('amount')}")
    for _dul in use_lines:
        _diag(f"  [in] ul label={getattr(_dul,'label','')!r} phase={getattr(_dul,'phase',None)} amt={getattr(_dul,'amount',None)} pid={getattr(_dul,'project_id',None)}")

    debt_sizing_mode = inputs.debt_sizing_mode or "gap_fill"
    reserve_months = int(inputs.operation_reserve_months or 6)
    # Operating Reserve basis: spec §3.3 parametrize sizing on {ds | opex |
    # opex_plus_ds}. Default "ds" matches the current behavior. Slice 5 adds
    # the DB column + UI; for now the attribute is read defensively so an
    # un-migrated scenario falls back to the default cleanly.
    operating_reserve_basis = (
        getattr(inputs, "operation_reserve_basis", None) or "ds"
    )

    # ── Per-loan active-window phase months ─────────────────────────────────
    # Each loan's IR/CI interest accrues only during the phases within its
    # [active_phase_start, active_phase_end) window — not every construction-
    # type phase in the deal.  This rank mapping converts active_phase_start /
    # active_phase_end strings into ordinal ranks so we can window-filter the
    # phase list per loan.
    #
    # Rank semantics: a loan with [start_rank, end_rank) includes all phases
    # whose rank is >= start_rank AND < end_rank.  End-exclusive because the
    # loan is taken out at the START of the end phase (e.g. active_to="lease_up"
    # means the perm takes over at lease_up start; the construction loan is not
    # active during lease_up itself).
    # _PERIOD_TYPE_RANK and _loan_pre_op_months extracted to cashflow_compile.py.

    # Legacy global sum — kept for the legacy path (non-Phase-B deals) where
    # there's a single construction+perm pair and no per-loan active windows.
    constr_months_total = sum(
        p.months for p in phases if p.period_type in _CONSTRUCTION_PERIOD_TYPES
    )
    # Narrower count for Construction DS Reserve — excludes acquisition/hold since
    # those phases don't incur building-related debt service; pure acquisition deals
    # always have a 1-month acquisition phase which would otherwise trigger the reserve.
    _actual_build_months = sum(
        p.months for p in phases
        if p.period_type in _CONSTRUCTION_PERIOD_TYPES
        and p.period_type not in {PeriodType.acquisition, PeriodType.hold}
    )

    # Count lease-up months — the perm debt must also cover these shortfalls so that
    # the cash balance at the first Stabilized period equals the Operating Reserve.
    # Income during lease-up is modelled as a linear ramp: 0 → full NOI, so the
    # average is 50 % of stabilized NOI.  This is used to reduce the gross shortfall.
    lease_up_months = sum(
        p.months for p in phases if p.period_type == PeriodType.lease_up
    )

    # Sum all non-exit use_lines as total project cost proxy.
    # Balance-only labels (reserves + capitalized interest) are excluded from
    # the input total via the module-level _BALANCE_ONLY_LABELS — they're
    # handled directly in sizing and would double-count otherwise.
    total_uses = ZERO
    for ul in use_lines:
        phase_str = str(getattr(ul.phase, "value", ul.phase))
        if phase_str == "exit":
            continue
        if getattr(ul, "label", "") in _BALANCE_ONLY_LABELS:
            continue
        total_uses += _to_decimal(ul.amount)

    # If no use lines are defined yet, skip auto-sizing entirely so we don't zero
    # out a previously computed principal when the user hasn't filled in the Sources
    # & Uses tab yet.
    if total_uses <= ZERO:
        return

    # Sum fixed (non-auto) sources
    def _fixed_sources(exclude_module: object) -> Decimal:
        total = ZERO
        for cm in capital_modules:
            if cm is exclude_module:
                continue
            src = cm.source or {}
            if src.get("auto_size"):
                continue
            amt = src.get("amount")
            if amt:
                total += Decimal(str(amt))
        return total

    if income_mode == "noi":
        # NOI mode: use the user-entered stabilized NOI + any gap adjustment phantom.
        _noi_input = _to_decimal(inputs.noi_stabilized_input) if inputs.noi_stabilized_input else ZERO
        _noi_adj = ZERO
        for _el_noi in expense_lines:
            if getattr(_el_noi, "label", "") == "Gap Adjustment — NOI":
                _noi_adj = _to_decimal(getattr(_el_noi, "annual_amount", 0) or 0)
                break
        noi_annual = _noi_input + _noi_adj
    elif prev_noi_stabilized is not None and prev_noi_stabilized > ZERO:
        # Use the previously computed NOI — more accurate than the estimator because
        # it includes escalation carry-in and capex reserve deductions.
        noi_annual = prev_noi_stabilized
    else:
        noi_monthly = _estimate_stabilized_noi_monthly(streams, expense_lines, inputs)
        noi_annual = noi_monthly * Decimal("12")

    # Pre-compute opex_monthly — independent of principal, needed for reserve sizing
    opex_monthly_pre = ZERO
    for line in expense_lines:
        active = {str(phase) for phase in (line.active_in_phases or [])}
        if "stabilized" in active or "operation_stabilized" in active:
            opex_monthly_pre += _q(_to_decimal(line.annual_amount) / Decimal("12"))

    # Operating Deficit Reserve — spec §3.2. Curve-driven, balance-independent,
    # gated on the presence of a lease-up phase. Computed up front so it can
    # enter ``total_uses`` for the principal solve; written back as a UseLine
    # after sizing completes. ``"Operating Deficit Reserve"`` lives in
    # ``_BALANCE_ONLY_LABELS`` so the prior amount on the row does not
    # double-count when the deal recomputes.
    _odr_amount = _odr_pool(streams, expense_lines, inputs, lease_up_months)
    if _odr_amount > ZERO:
        total_uses += _odr_amount

    # Phase B: new multi-debt path when debt_types is explicitly set on inputs.
    # Bridge loans (pre_development_loan, acquisition_loan, construction_loan, bridge)
    # are sized to their phase costs and marked is_bridge=True so they're excluded from
    # the Sources display total.  Permanent debt still gap-fills to TPC.
    # Legacy 3-path is preserved when debt_types is None (backward compat).
    # Pairs of (retired_module, retiring_module) resolved via exit_terms.vehicle.
    # Populated by the generic pairing pass below; consumed by the refi
    # writeback at the end of this sizing block.
    _retirement_pairs: list[tuple[object, object]] = []
    _bridge_io: dict = {}            # {funder_type: interest_amount} for new-path use lines
    _bridge_io_carry_type: dict = {} # {funder_type: "interest_reserve"|"capitalized_interest"}
    _bridge_io_module: dict = {}     # {funder_type: capital_module.id} for reserve → source attribution
    _cc_data:  dict = {}             # {id(module): {"flat": Decimal, "pct": Decimal, "module": m}}

    debt_types_list: list = getattr(inputs, "debt_types", None) or []
    _diag(f"debt_types_list={debt_types_list} debt_sizing_mode={debt_sizing_mode}")

    if debt_types_list:
        # ── New multi-debt path ─────────────────────────────────────────────
        _PRE_DEV_USE_PHASES  = {"pre_construction"}
        _ACQ_USE_PHASES      = {"acquisition", "other"}
        _CONSTR_USE_PHASES   = {"construction", "renovation", "conversion"}

        # Pre-compute the full set of Total Finance Costs Use line labels for ALL
        # CapitalModules.  Excluded from _phase_cost_sum so finance costs do not
        # inflate bridge loan sizing (they're folded into the perm gap-fill divisor
        # for auto-sized modules; added directly for fixed-amount modules).
        _cc_labels: set[str] = set()
        for _pre_cm in capital_modules:
            _pre_cm_lbl = (
                getattr(_pre_cm, "label", "")
                or _loan_subtype_from_module(_pre_cm).replace("_", " ").title()
            )
            _cc_labels.add(f"{_pre_cm_lbl} — Total Finance Costs")

        def _phase_cost_sum(phase_set: set) -> Decimal:
            return sum(
                (_to_decimal(ul.amount)
                 for ul in use_lines
                 if str(getattr(ul.phase, "value", ul.phase) or "") in phase_set
                 and getattr(ul, "label", "") not in _BALANCE_ONLY_LABELS
                 and getattr(ul, "label", "") not in _cc_labels),
                ZERO,
            )

        pre_dev_costs  = _phase_cost_sum(_PRE_DEV_USE_PHASES)
        acq_costs      = _phase_cost_sum(_ACQ_USE_PHASES)
        constr_costs   = _phase_cost_sum(_CONSTR_USE_PHASES)

        _pre_dev_months = sum(p.months for p in phases if p.period_type == PeriodType.pre_construction)
        _acq_months     = sum(p.months for p in phases if p.period_type == PeriodType.acquisition)

        for _m in list(auto_modules):
            _ft = _loan_subtype_from_module(_m)
            if _ft not in {"pre_development_loan", "acquisition_loan", "construction_loan", "bridge"}:
                continue
            _src    = dict(_m.source or {})
            _carry  = _m.carry or {}
            _rate   = _src.get("interest_rate_pct") or _carry.get("io_rate_pct")
            _cr     = _constr_phase_rate_pct(_carry, _src) or _rate

            if _ft == "pre_development_loan":
                _ltc = Decimal(str(_src.get("ltv_pct") or 100))
                _funded = _q(pre_dev_costs * _ltc / HUNDRED)
                _r = Decimal(str(_rate or 0))
                _pre_ct = _carry_type_for_phase(_carry, is_construction=True)
                _draw_type = _src.get("draw_type")
                _n = _loan_pre_op_months(_m, capital_modules, phases)
                _pre_schedule = _carry.get("schedule")
                if _pre_schedule and _n > 0 and _funded > ZERO:
                    _interest_carry = _compute_preop_carry_cost(
                        _pre_schedule, _funded, _n, _r, _milestone_month_map,
                        _loan_start_abs_month(_m, phases), draw_type=_draw_type,
                    )
                    _io_f = (_interest_carry / _funded) if _funded > ZERO else ZERO
                elif _pre_ct == "interest_reserve" and _r > ZERO and _n > 0:
                    _interest_carry = period_interest_months(_funded, _n, _r, draw_schedule=_draw_schedule_for(_pre_ct, _draw_type))
                    # Add lease-up IR shortfall if this loan extends past construction.
                    _lu_phase = next((p for p in phases if p.period_type == PeriodType.lease_up), None)
                    if _resolve_active_end_rank(_m, capital_modules) > 4 and _lu_phase:
                        _interest_carry += _ir_lease_up_pool(
                            _funded, _r, _lu_phase.months, _lu_phase, streams, expense_lines, inputs
                        )
                    _io_f = (_interest_carry / _funded) if _funded > ZERO else ZERO
                elif _pre_ct == "capitalized_interest" and _r > ZERO and _n > 0:
                    # Compound CI: _io_f = factor-1 makes _div = 2-factor → principal = funded/(2-factor)
                    _io_f = (ONE + _r / Decimal("1200")) ** _n - ONE
                else:
                    _io_f = ZERO
                _div = ONE - _io_f
                _principal = _q(_funded / _div) if (_div > ZERO and _funded > ZERO) else _funded
                if _principal > ZERO and _r > ZERO and _n > 0 and _io_f > ZERO:
                    _bridge_io["pre_development_loan"] = _q(_principal - _funded)
                    _bridge_io_carry_type["pre_development_loan"] = _pre_ct
                    _bridge_io_module["pre_development_loan"] = _m.id

            elif _ft == "acquisition_loan":
                _ltv = Decimal(str(_src.get("ltv_pct") or 70))
                _principal = _q(acq_costs * _ltv / HUNDRED)
                _r = Decimal(str(_rate or 0))
                _acq_ct = _carry_type_for_phase(_carry, is_construction=True)
                _draw_type = _src.get("draw_type")
                _n = _loan_pre_op_months(_m, capital_modules, phases)
                _acq_schedule = _carry.get("schedule")
                if _acq_schedule and _n > 0 and _principal > ZERO:
                    _acq_interest = _compute_preop_carry_cost(
                        _acq_schedule, _principal, _n, _r, _milestone_month_map,
                        _loan_start_abs_month(_m, phases), draw_type=_draw_type,
                    )
                elif _principal > ZERO and _r > ZERO and _n > 0:
                    if _acq_ct == "interest_reserve":
                        _acq_interest = period_interest_months(_principal, _n, _r, draw_schedule=_draw_schedule_for(_acq_ct, _draw_type))
                        _lu_phase = next((p for p in phases if p.period_type == PeriodType.lease_up), None)
                        if _resolve_active_end_rank(_m, capital_modules) > 4 and _lu_phase:
                            _acq_interest += _ir_lease_up_pool(
                                _principal, _r, _lu_phase.months, _lu_phase, streams, expense_lines, inputs
                            )
                    elif _acq_ct == "capitalized_interest":
                        _acq_interest = compound_accrual(_principal, _r / Decimal("1200"), _n)
                    else:
                        _acq_interest = ZERO
                else:
                    _acq_interest = ZERO
                if _acq_interest > ZERO:
                    _bridge_io["acquisition_loan"] = _acq_interest
                    _bridge_io_carry_type["acquisition_loan"] = _acq_ct
                    _bridge_io_module["acquisition_loan"] = _m.id

            elif _ft == "construction_loan":
                _ltc = Decimal(str(_src.get("ltv_pct") or 75))
                _funded = _q(constr_costs * _ltc / HUNDRED)
                _r = Decimal(str(_cr or 0))
                _cl_ct = _carry_type_for_phase(_carry, is_construction=True)
                _draw_type = _src.get("draw_type")
                _n = _loan_pre_op_months(_m, capital_modules, phases)
                _cl_schedule = _carry.get("schedule")
                if _cl_schedule and _n > 0 and _funded > ZERO:
                    _interest_carry = _compute_preop_carry_cost(
                        _cl_schedule, _funded, _n, _r, _milestone_month_map,
                        _loan_start_abs_month(_m, phases), draw_type=_draw_type,
                    )
                    _io_f = (_interest_carry / _funded) if _funded > ZERO else ZERO
                elif _cl_ct == "interest_reserve" and _r > ZERO and _n > 0:
                    _interest_carry = period_interest_months(_funded, _n, _r, draw_schedule=_draw_schedule_for(_cl_ct, _draw_type))
                    _lu_phase = next((p for p in phases if p.period_type == PeriodType.lease_up), None)
                    if _resolve_active_end_rank(_m, capital_modules) > 4 and _lu_phase:
                        _interest_carry += _ir_lease_up_pool(
                            _funded, _r, _lu_phase.months, _lu_phase, streams, expense_lines, inputs
                        )
                    _io_f = (_interest_carry / _funded) if _funded > ZERO else ZERO
                elif _cl_ct == "capitalized_interest" and _r > ZERO and _n > 0:
                    # Compound CI: _io_f = factor-1 makes _div = 2-factor → principal = funded/(2-factor)
                    _io_f = (ONE + _r / Decimal("1200")) ** _n - ONE
                else:
                    _io_f = ZERO
                _div = ONE - _io_f
                _principal = _q(_funded / _div) if (_div > ZERO and _funded > ZERO) else _funded
                if _principal > ZERO and _r > ZERO and _n > 0 and _io_f > ZERO:
                    _bridge_io["construction_loan"] = _q(_principal - _funded)
                    _bridge_io_carry_type["construction_loan"] = _cl_ct
                    _bridge_io_module["construction_loan"] = _m.id

            elif _ft == "bridge":
                _existing_amt = _src.get("amount")
                _principal = Decimal(str(_existing_amt)) if _existing_amt else ZERO
            else:
                continue

            if _principal < ZERO:
                _principal = ZERO
            _src["amount"] = str(_whole_dollar(_principal))
            _src["is_bridge"] = True
            _diag(f"bridge sized cm={_m.id} subtype={_ft} -> amount={_src['amount']}")
            _m.source = _src
            auto_modules = [x for x in auto_modules if x is not _m]  # remove from gap-fill loop

    # ── Generic Exit Vehicle pairing (supersedes legacy construction_and_perm) ─
    # For every capital module, resolve its Exit Vehicle via _resolve_vehicle
    # (reads exit_terms.vehicle with default-selection fallback).  When the
    # vehicle is another source, record the (retired, retirer) pair so:
    #   - the retired module is excluded from the gap-fill pool
    #   - the retirer's source gets construction_retirement = retired balloon
    # This generalises the old `debt_structure == "construction_and_perm"`
    # specialisation to any debt-with-finite-Active-To configuration.
    for _candidate in list(capital_modules):
        # Only full_payoff loans route through the auto-pair logic. Equity
        # modules (profit_share, equity_conversion) and grants (forgiven)
        # shouldn't be retired by another source even when overlap exists.
        _cand_exit = _candidate.exit_terms or {}
        _cand_exit_type = str(_cand_exit.get("exit_type") or "full_payoff")
        if _cand_exit_type != "full_payoff":
            continue
        _vehicle, _retirer = _resolve_vehicle(_candidate, capital_modules)
        if _vehicle != "source" or _retirer is None:
            continue
        # Equity modules cannot retire debt — skip spurious pairs where a user
        # accidentally set exit_terms.vehicle to an equity source.
        _retirer_vt = str(getattr(_retirer, "vehicle_type", "") or "").replace("VehicleType.", "")
        if _retirer_vt == "equity":
            continue
        # Already handled by the multi-debt path above (is_bridge already set)?
        _c_src = _candidate.source or {}
        if _c_src.get("is_bridge"):
            # Still record the pair so the writeback can tag the retirer,
            # but don't try to re-exclude from auto_modules (already done).
            _retirement_pairs.append((_candidate, _retirer))
            continue
        _retirement_pairs.append((_candidate, _retirer))
        # Remove retired from gap-fill pool so only the retirer sizes to TPC.
        auto_modules = [m for m in auto_modules if m is not _candidate]

    # When bridge loans carry their own IR/CI (new multi-debt path), the gap-fill module
    # (e.g. permanent debt) must cover those interest costs in the permanent capital stack.
    # Both interest_reserve and capitalized_interest add to total_uses:
    #   - interest_reserve: IR pool was a real funded cost; perm replaces the full loan commitment
    #   - capitalized_interest: balance grew; perm must retire the grown balance
    # True IO (io_only) is NOT captured in _bridge_io — periodic payments appear in DS only.
    # Guard: only adjust when there is a downstream gap-fill module to absorb it.
    if debt_types_list and _bridge_io and auto_modules:
        for _bio_ft, _bio_amt in _bridge_io.items():
            if _bio_amt > ZERO:
                total_uses += _bio_amt

    # ── Total Finance Costs (one row per DEBT CapitalModule) ────────────────────
    # Apply DEFAULT_FINANCE_COST_PCT × principal to debt modules only.
    # Equity / grants do not get finance cost rows yet — extending to non-debt
    # sources requires Sources-side handling so they cover their own cost.
    # Engine-managed rows carry is_auto_finance_cost=True.  A row where the
    # flag is False is a user override → leave alone (already in total_uses).
    # Auto-sized modules: pct folded into gap-fill divisor.
    # Fixed-amount debt modules (pre-sized bridge): pct × known amount added
    # directly to total_uses.
    _cc_data: dict = {}   # id(module) → {"flat": Decimal, "pct": Decimal, "module": m}
    _diag(f"CC-INIT entering block debt_types_list={bool(debt_types_list)} auto_modules={[m.id for m in auto_modules]}")
    if debt_types_list and auto_modules:
        _fc_rate = DEFAULT_FINANCE_COST_PCT / HUNDRED
        _auto_mod_ids = {id(m) for m in auto_modules}
        for _ccm in capital_modules:
            if not _is_debt_cm(_ccm):
                continue
            # Skip user-entered fixed debt with no auto_size and no pre-sizing.
            _is_auto = id(_ccm) in _auto_mod_ids
            _pre_sized = Decimal(str((_ccm.source or {}).get("amount") or 0)) > ZERO
            if not _is_auto and not _pre_sized:
                continue
            _ccm_lbl = (
                getattr(_ccm, "label", "")
                or _loan_subtype_from_module(_ccm).replace("_", " ").title()
            )
            _cc_full_lbl = f"{_ccm_lbl} — Total Finance Costs"
            # Match the existing FC row by module link + (auto-flag OR label
            # suffix).  Matching by exact label alone breaks when the user
            # edits the label on the override — engine then creates a duplicate.
            _ccm_id = getattr(_ccm, "id", None)
            _cc_exist = next(
                (
                    ul for ul in use_lines
                    if getattr(ul, "source_capital_module_id", None) == _ccm_id
                    and (
                        getattr(ul, "is_auto_finance_cost", False)
                        or (getattr(ul, "label", "") or "").endswith(" — Total Finance Costs")
                    )
                ),
                None,
            )
            if _cc_exist is not None and not getattr(_cc_exist, "is_auto_finance_cost", False):
                continue
            # On 2nd+ compute, the engine-managed FC row from the prior pass
            # is already in total_uses via the initial use_lines sum.  For
            # auto-sized modules subtract it back out so divisor fold-in can
            # re-derive FC from the freshly-solved principal (no double-count).
            # Fixed modules re-add the correct amount below from known principal.
            if _cc_exist is not None and getattr(_cc_exist, "is_auto_finance_cost", False):
                total_uses -= _q(Decimal(str(getattr(_cc_exist, "amount", 0) or 0)))
            _cc_data[id(_ccm)] = {"flat": ZERO, "pct": _fc_rate, "module": _ccm}

        for _cc_obj in _cc_data.values():
            _cc_ref = _cc_obj["module"]
            if id(_cc_ref) in _auto_mod_ids:
                pass  # divisor fold-in below
            else:
                _cc_br_p = Decimal(str((_cc_ref.source or {}).get("amount") or 0))
                total_uses += _q(_cc_br_p * _cc_obj["pct"])

    # Lease-Up Reserve = perm debt service during lease-up minus ~1/3 stabilized NOI (phantom CF avg).
    # Computed inside the loop when the gap-fill DS path is active; written as a use
    # line after the loop so S&U always balances.
    _lease_up_carry: Decimal = ZERO
    # Phase 2e1: track which module's DS drove the reserve computation so the
    # resulting Lease-Up Reserve + Operating Reserve UseLines can carry a
    # source_capital_module_id back to that module (the "primary perm").
    _reserve_source_module: CapitalModule | None = None
    _constr_ds_reserve: Decimal = ZERO
    _constr_ds_source_module: CapitalModule | None = None

    for module in auto_modules:
        src = dict(module.source or {})
        carry = module.carry or {}
        # Sizer rate MUST match what cashflow pays — see _op_phase_rate_and_amort.
        rate_pct, amort_years = _op_phase_rate_and_amort(carry, src)
        # Per-loan DSCR floor: source.dscr_min → debt_terms staging → PLACEHOLDER_DSCR (1.25).
        _dt_perm = dict((inputs.debt_terms or {}).get("permanent_debt") or {})
        dscr_min = _to_decimal(src.get("dscr_min") or _dt_perm.get("dscr_min") or PLACEHOLDER_DSCR)
        op_carry = _get_phase_carry(carry, "operation")

        # Construction IO rate: schedule first (IR/CI phase), then legacy phased
        # carry, then source headline rate. Falls back to op-phase rate if no
        # construction rate found anywhere.
        constr_rate_pct = _constr_phase_rate_pct(carry, src) or rate_pct
        # IO factor: fraction of principal consumed by construction IO over all constr phases
        # Solved algebraically: P = base / (1 - constr_io_factor) so that
        # cash at ops start = P - base = reserve (net of construction IO charges)
        # In new multi-debt deals the construction loan handles its own IO, so perm's
        # constr_io_factor is forced to zero to avoid double-counting.
        constr_io_factor = ZERO
        _constr_ct = _carry_type_for_phase(carry, is_construction=True)
        # Apply factor when there is no dedicated construction_loan handling its own DS.
        # Covers both legacy (no debt_types_list) and multi-debt deals using perm-only structure.
        _has_constr_loan = "construction_loan" in (debt_types_list or [])
        # Phase-aware preop months: when the module has carry.schedule, size the
        # factor off the schedule's IR/CI phase durations (months / milestone /
        # remainder) rather than the deal's construction phase total. The IR Use
        # line written downstream will use the same number, so Sources = Uses.
        _module_schedule = (carry or {}).get("schedule") or []
        _preop_months = (
            _schedule_preop_months(
                _module_schedule,
                _milestone_month_map,
                _loan_start_abs_month(module, phases),
            )
            if _module_schedule
            else _actual_build_months
        )
        if constr_rate_pct and _preop_months > 0 and not _has_constr_loan:
            _c_monthly_rate = Decimal(str(constr_rate_pct)) / HUNDRED / Decimal("12")
            if _constr_ct == "pi" and amort_years > 0 and _c_monthly_rate > ZERO:
                _cn = amort_years * 12
                _cf = (ONE + _c_monthly_rate) ** _cn
                _pmt_f_c = _c_monthly_rate * _cf / (_cf - ONE)
                constr_io_factor = _pmt_f_c * Decimal(str(_preop_months))
            else:
                # Perm loans default to fully_drawn (full balance at close).
                # draw_type="draw_down" overrides to (N+1)/2 average-balance factor.
                _perm_draw_type = src.get("draw_type")
                _n_factor = (
                    (Decimal(_preop_months + 1) / 2)
                    if _perm_draw_type == "draw_down"
                    else Decimal(str(_preop_months))
                )
                constr_io_factor = _c_monthly_rate * _n_factor

        fixed = _fixed_sources(module)
        divisor = ONE - constr_io_factor

        # Fold perm closing-cost % into divisor so the gap-fill principal covers its own
        # origination fee algebraically (Sources = Uses on the first compute run).
        # Only applies when this module has auto-computed % closing costs (not user-overrides).
        _m_cc = _cc_data.get(id(module))
        if _m_cc and _m_cc["pct"] > ZERO:
            divisor -= _m_cc["pct"]

        # Closed-form solve targeting Operating Reserve at first Stabilized period.
        #
        # The debt must cover: TPC + construction IO + lease-up debt service
        #                      - lease-up income + reserve at stabilization
        #
        # Let P = principal, f_c = constr_io_factor, f_m = pmt_factor, L = lease_up_months,
        #     R = reserve_months, I_lu = avg lease-up income (≈ 1/3 of stabilized NOI/mo).
        #
        #   P = TPC + P·f_c + P·f_m·L − I_lu·L + P·f_m·R
        #   P·(1 − f_c − f_m·(L + R)) = TPC − I_lu·L
        #   P = (TPC − I_lu·L) / (1 − f_c − f_m·(L + R))
        #
        # When L = 0 this collapses to the original formula.
        #
        # LEASE-UP INCOME FACTOR = 1/3  (derived from phantom cash flow analysis)
        # ─────────────────────────────────────────────────────────────────────────
        # Assumptions: 60/40 revenue/opex split at stabilization; revenue ramps
        # linearly 0 → 100% over L months; opex ramps linearly 50 → 100% (fixed
        # costs persist at low occupancy).
        #
        #   Avg revenue  = 50% of stabilized revenue  (linear 0 → 100%)
        #   Avg opex     = 75% of stabilized opex     (linear 50% → 100%)
        #
        # For a $500k NOI example (revenue $833k, opex $333k, L = 9 months):
        #   Month | Rev%  | OpEx%  |  Revenue  |   OpEx   |    NOI
        #     1   |   0%  |  50%   |        $0 |  $13,889 | −$13,889
        #     2   |  13%  |  56%   |    $8,681 |  $15,625 |  −$6,944
        #     3   |  25%  |  63%   |   $17,361 |  $17,361 |       $0
        #     4   |  38%  |  69%   |   $26,042 |  $19,097 |   $6,944
        #     5   |  50%  |  75%   |   $34,722 |  $20,833 |  $13,889
        #     6   |  63%  |  81%   |   $43,403 |  $22,569 |  $20,833
        #     7   |  75%  |  88%   |   $52,083 |  $24,306 |  $27,778
        #     8   |  88%  |  94%   |   $60,764 |  $26,042 |  $34,722
        #     9   | 100%  | 100%   |   $69,444 |  $27,778 |  $41,667
        #                                          Total NOI: $125,000
        #
        #   Avg monthly NOI = $125,000 / 9 = $13,889 = 33.3% of stabilized $41,667
        #
        # Algebraically: (0.5·R − 0.75·E) / (R − E)
        #              = (0.5·833k − 0.75·333k) / 500k = 167k / 500k = 1/3
        #
        # Using 50% (naive linear revenue average) overstates income by ~$62k over
        # 9 months because it ignores sticky fixed costs at low occupancy.
        _LEASE_UP_INCOME_FACTOR = Decimal("1") / Decimal("3")
        noi_monthly_est = noi_annual / Decimal("12") if noi_annual > ZERO else ZERO
        # The 1/3 NOI offset assumes income ramps during lease-up. If every
        # income stream is gated to `stabilized` (or later), no revenue
        # actually collects during lease-up — but OpEx still drains cash.
        # Replace the positive NOI credit with a NEGATIVE offset equal to
        # the projected OpEx burden so LUR covers (DS + OpEx) × L months.
        # Apply the expense growth factor at lease-up midpoint so the sizer
        # tracks the per-period opex the cashflow simulation actually charges
        # (3 %/yr default growth × elapsed months produces a few-percent bump
        # by the time the deal reaches lease-up).
        _streams_ramp_lease_up = any(
            _is_stream_active(s, PeriodType.lease_up) for s in streams
        )
        if not _streams_ramp_lease_up:
            _lu_start_period = sum(
                p.months for p in phases
                if p.period_type != PeriodType.lease_up
                and _PERIOD_TYPE_RANK.get(p.period_type, 99)
                    < _PERIOD_TYPE_RANK.get(PeriodType.lease_up, 99)
            )
            _lu_midpoint = _lu_start_period + Decimal(lease_up_months) / Decimal("2")
            _opex_growth = _growth_factor(
                inputs.expense_growth_rate_pct_annual, int(_lu_midpoint)
            )
            lease_up_income_offset = -_q(opex_monthly_pre * _opex_growth * Decimal(lease_up_months))
        else:
            lease_up_income_offset = _q(noi_monthly_est * _LEASE_UP_INCOME_FACTOR * Decimal(lease_up_months))
        effective_uses = total_uses - fixed - lease_up_income_offset

        if rate_pct:
            monthly_rate = Decimal(str(rate_pct)) / HUNDRED / Decimal("12")
            n = amort_years * 12
            if monthly_rate > ZERO:
                factor = (ONE + monthly_rate) ** n
                pmt_factor = monthly_rate * factor / (factor - ONE)
            else:
                pmt_factor = ONE / Decimal(n) if n > 0 else ZERO

            # OR basis routing (spec §3.3 / critique #1):
            #   - "ds"          → OR = DS × R; balance-dependent → folded into divisor.
            #   - "opex"        → OR = OpEx × R; balance-independent → added to effective_uses.
            #   - "opex_plus_ds"→ both: DS portion in divisor, OpEx portion in effective_uses.
            # When OR_basis includes DS the divisor still closes the {IR, OR}
            # simultaneous system in one pass — IR contributes `f_c`, OR-on-DS
            # contributes `pmt_factor·R`, both per principal.
            _or_uses_ds = operating_reserve_basis in ("ds", "opex_plus_ds")
            _or_uses_opex = operating_reserve_basis in ("opex", "opex_plus_ds")
            _r_in_divisor = Decimal(reserve_months) if _or_uses_ds else ZERO
            _or_opex_fixed = (
                _q(opex_monthly_pre * Decimal(reserve_months))
                if _or_uses_opex
                else ZERO
            )

            # Try closed-form simultaneous solve. `pmt_factor · lease_up_months`
            # still represents PI-loan DS during lease-up (Slice 5 cleans this
            # up when _lease_up_carry is deleted under the IO-only assumption).
            ds_divisor = divisor - pmt_factor * (_r_in_divisor + Decimal(lease_up_months))
            if ds_divisor > ZERO:
                principal = _q((effective_uses + _or_opex_fixed) / ds_divisor)
                # Capture lease-up carry = net debt service shortfall during lease-up.
                # This becomes a Use line so Sources = Uses after compute.
                if lease_up_months > 0:
                    # IR-carry loans extending through lease-up (end_rank > 4) are still
                    # interest-only during lease-up; their lease-up costs are captured by
                    # _ir_lease_up_pool in total_constr_io.  Adding PI DS here would
                    # double-count the same period.  Only compute LUR for loans that pay
                    # cash DS (PI/IO carry) starting at CO.
                    _constr_ct_lu = _carry_type_for_phase(carry, is_construction=True)
                    _end_rank_lu = _resolve_active_end_rank(module, capital_modules)
                    _ir_covers_lease_up = (
                        _constr_ct_lu == "interest_reserve" and _end_rank_lu > 4
                    )
                    if not _ir_covers_lease_up:
                        _lu = _q(principal * pmt_factor * Decimal(lease_up_months) - lease_up_income_offset)
                        _lease_up_carry = _lu if _lu > ZERO else ZERO
                        if _lu > ZERO:
                            _reserve_source_module = module
                # If no lease-up carry was captured, still tag the reserve
                # source to the first auto-sized perm-like module so the
                # Operating Reserve has a Source attribution.
                if _reserve_source_module is None:
                    _reserve_source_module = module
                ds_check = _q(principal * pmt_factor)
                if ds_check < opex_monthly_pre:
                    # OpEx is actually larger — fall back to opex-based reserve
                    reserve = _q(opex_monthly_pre * Decimal(reserve_months))
                    principal = _q((total_uses - fixed + reserve) / divisor) if divisor > ZERO else total_uses - fixed + reserve
            else:
                # Degenerate: divisor ≤ 0; use opex reserve without lease-up adjustment
                reserve = _q(opex_monthly_pre * Decimal(reserve_months))
                principal = _q((total_uses - fixed + reserve) / divisor) if divisor > ZERO else total_uses - fixed + reserve
        else:
            # No-interest debt (soft loan, grant): no DS, use opex-based reserve
            reserve = _q(opex_monthly_pre * Decimal(reserve_months))
            principal = _q((total_uses - fixed + reserve) / divisor) if divisor > ZERO else total_uses - fixed + reserve

        if debt_sizing_mode == "dscr_capped":
            # ── DSCR-capped sizing with closing-cost parity ─────────────────
            # Invariant: whether the cap binds or not, P always satisfies two
            # parallel constraints (both or either):
            #   (a) DSCR:            P × f_m × 12 ≤ NOI / DSCR_min
            #   (b) Gap-fill solve:  P × (1 − f_c − f_m·(R+L) − perm_pct) = effective_uses
            #
            # When both are feasible, pick the smaller: the hard lender cap binds.
            # When (b) ≤ (a), pick (b): DSCR is slack, sizing fits.
            #
            # Closing-cost parity: both P_gapfill and P_capped are full loan
            # amounts the lender actually funds (including the financed
            # origination fee).  The DSCR check uses DS on the full P, matching
            # the lender's view.  No hidden re-inflation.
            #
            # When the cap binds, the orig fee written to the Use line is
            # P_capped × perm_pct — honest cost based on what the lender funded.
            # The resulting Sources gap = (TPC + flat_costs + P_capped·perm_pct
            # + reserve) − P_capped − fixed is a real funding gap the user
            # must resolve via equity/scope.
            if rate_pct and principal > ZERO and noi_annual > ZERO and dscr_min > ZERO:
                gf_ds_monthly = _monthly_pmt(principal, rate_pct, amort_years)
                gf_dscr = (
                    noi_annual / (gf_ds_monthly * Decimal("12"))
                    if gf_ds_monthly > ZERO
                    else Decimal("999")
                )
                if gf_dscr < dscr_min:
                    # Hard cap binds: compute P at exactly DSCR_min
                    principal = solve_principal_for_dscr(
                        noi_annual=noi_annual,
                        target_dscr=dscr_min,
                        rate_pct=Decimal(str(rate_pct)),
                        amort_years=amort_years,
                    )
                    # Note: no closing-cost re-inflation here. The lender's cap
                    # is on DS(P), not on P·(1−perm_pct).  Any closing cost
                    # shortfall surfaces as a real Sources gap downstream.

            _ltv_raw = src.get("ltv_pct")
            if _ltv_raw is not None:
                _ltv = _percent(Decimal(str(_ltv_raw)))
                _cap_rate = _percent(
                    Decimal(str(src.get("refi_cap_rate_pct") or inputs.exit_cap_rate_pct or 0))
                )
                if noi_annual > ZERO and _cap_rate > ZERO and _ltv > ZERO:
                    _p_ltv = _q((noi_annual / _cap_rate) * _ltv)
                    if principal > _p_ltv:
                        principal = _p_ltv
                        src["binding_constraint"] = "ltv"

            if principal < ZERO:
                principal = ZERO
            src["amount"] = str(_whole_dollar(principal))
            if constr_io_factor > ZERO and _constr_ct in ("io_only", "pi"):
                _constr_ds_reserve += _q(principal * constr_io_factor)
                if _constr_ds_source_module is None:
                    _constr_ds_source_module = module
            module.source = src  # ORM dirty tracking — flushed at end of compute
            continue

        if debt_sizing_mode == "dual_constraint":
            # ── MIN(LTV, DSCR) dual-constraint sizing ─────────────────────
            # Industry-standard: lender computes both LTV-based and DSCR-based
            # maximums and funds the smaller.  Property value for LTV uses the
            # engine's projected stabilized NOI / going-in cap rate (or an
            # optional refi_cap_rate_pct override on the source).
            #
            #   P_ltv  = (NOI_annual / cap_rate) × LTV%
            #   P_dscr = PV(rate/12, amort_months, -NOI_annual / 12 / DSCR_min)
            #   P      = MIN(P_ltv, P_dscr, P_gapfill)
            #
            # P_gapfill (already computed above) acts as a third ceiling: no
            # point funding more than the project actually needs.
            p_gapfill = principal  # from gap-fill solve above
            ltv_pct_used = Decimal(str(src.get("ltv_pct") or 65))
            ltv = _percent(ltv_pct_used)
            # Persist the effective LTV% so the Calculation Status modal and
            # downstream UI can report which cap was actually applied.
            src["ltv_pct"] = float(ltv_pct_used)
            cap_for_ltv = _percent(
                Decimal(str(src.get("refi_cap_rate_pct") or inputs.exit_cap_rate_pct or 0))
            )
            p_ltv = Decimal("999999999999")
            if noi_annual > ZERO and cap_for_ltv > ZERO and ltv > ZERO:
                property_value = _q(noi_annual / cap_for_ltv)
                p_ltv = _q(property_value * ltv)

            p_dscr = Decimal("999999999999")
            if rate_pct and noi_annual > ZERO and dscr_min > ZERO:
                p_dscr = solve_principal_for_dscr(
                    noi_annual=noi_annual,
                    target_dscr=dscr_min,
                    rate_pct=Decimal(str(rate_pct)),
                    amort_years=amort_years,
                )

            principal = min(p_gapfill, p_ltv, p_dscr)
            if principal < ZERO:
                principal = ZERO
            # Tag which constraint bound for transparency
            if principal == p_ltv:
                src["binding_constraint"] = "ltv"
            elif principal == p_dscr:
                src["binding_constraint"] = "dscr"
            else:
                src["binding_constraint"] = "gap_fill"
            src["amount"] = str(_whole_dollar(principal))
            if constr_io_factor > ZERO and _constr_ct in ("io_only", "pi"):
                _constr_ds_reserve += _q(principal * constr_io_factor)
                if _constr_ds_source_module is None:
                    _constr_ds_source_module = module
            module.source = src  # ORM dirty tracking — flushed at end of compute
            continue

        # gap_fill — principal already computed by _solve_principal_with_reserve above.
        # Apply LTV cap against stabilized value if source.ltv_pct is set.
        _ltv_raw = src.get("ltv_pct")
        if _ltv_raw is not None:
            _ltv = _percent(Decimal(str(_ltv_raw)))
            _cap_rate = _percent(
                Decimal(str(src.get("refi_cap_rate_pct") or inputs.exit_cap_rate_pct or 0))
            )
            if noi_annual > ZERO and _cap_rate > ZERO and _ltv > ZERO:
                _p_ltv = _q((noi_annual / _cap_rate) * _ltv)
                if principal > _p_ltv:
                    principal = _p_ltv
                    src["binding_constraint"] = "ltv"
        if principal < ZERO:
            principal = ZERO
        src["amount"] = str(_whole_dollar(principal))
        if constr_io_factor > ZERO and _constr_ct in ("io_only", "pi"):
            _constr_ds_reserve += _q(principal * constr_io_factor)
            if _constr_ds_source_module is None:
                _constr_ds_source_module = module
        module.source = src  # ORM dirty tracking — flushed at end of compute

    # Generic Exit Vehicle writeback: for every (retired, retirer) pair, tag
    # the retired loan is_bridge and write construction_retirement onto the
    # retirer so the §2.10 refi-event emission picks it up.
    #
    # In the legacy construction_and_perm flow the bridge's amount was mirrored
    # to the perm's amount (since conceptually they were one loan). Here the
    # bridge has been sized independently (via LTV * acq_costs etc.), so we
    # preserve its own amount — the retirer's gap-fill sizing already targets
    # TPC so it has enough to retire the bridge at handoff.
    for _retired, _retirer in _retirement_pairs:
        retirer_src = dict(_retirer.source or {})
        retired_src = dict(_retired.source or {})
        retired_amount = retired_src.get("amount", "0")

        if not retired_src.get("is_bridge"):
            retired_src["is_bridge"] = True
            _retired.source = retired_src

        retirer_src["construction_retirement"] = retired_amount
        _retirer.source = retirer_src

        # Persist the resolved vehicle on the retired module's exit_terms so
        # the UI can look up "retires <label>" without re-running the resolver.
        retired_exit = dict(_retired.exit_terms or {})
        if retired_exit.get("vehicle") != str(_retirer.id):
            retired_exit["vehicle"] = str(_retirer.id)
            _retired.exit_terms = retired_exit

    # Cleanup: strip stale construction_retirement / is_bridge from modules
    # that are no longer part of any pair this run (e.g. the user deleted a
    # bridge that was previously retired by this perm).
    _retirers_now = {id(r) for _, r in _retirement_pairs}
    _retireds_now = {id(b) for b, _ in _retirement_pairs}
    for _cm in capital_modules:
        src = dict(_cm.source or {})
        changed = False
        if id(_cm) not in _retirers_now and src.get("construction_retirement"):
            src.pop("construction_retirement", None)
            changed = True
        if id(_cm) not in _retireds_now and src.get("is_bridge"):
            # Only auto-clear is_bridge when the module label does NOT indicate a
            # bridge-typed loan — those were sized as bridges via the label-based
            # detection path and should stay flagged.
            _ft = _loan_subtype_from_module(_cm)
            if _ft not in {"pre_development_loan", "acquisition_loan",
                           "construction_loan", "bridge"}:
                src.pop("is_bridge", None)
                changed = True
        if changed:
            _cm.source = src

    # Compute actual reserve (max of OpEx vs actual debt service, × reserve months)
    # opex_monthly_pre already computed above; re-use it here.
    opex_monthly = opex_monthly_pre
    # Re-sum debt service now that amounts are set. Rate + amort MUST come
    # from the same source as _period_ds_from_schedule_phase (operating-phase
    # schedule entry) so actual_reserve matches what cashflow actually pays —
    # otherwise opex-fallback uses the wrong DS comparison and the Operating
    # Reserve UseLine diverges from what the sizer assumed, producing a
    # residual Sources gap.
    ds_monthly = ZERO
    for m in auto_modules:
        src2 = m.source or {}
        carry2 = m.carry or {}
        amt2 = src2.get("amount")
        if amt2:
            p2 = Decimal(str(amt2))
            ct2 = _carry_type_for_phase(carry2, is_construction=False)
            rate2, ay2 = _op_phase_rate_and_amort(carry2, src2)
            if ct2 in ("interest_reserve", "capitalized_interest"):
                pass  # no periodic DS; reserve sized on zero DS for this module
            elif ct2 == "io_only":
                ds_monthly += _monthly_io(p2, rate2)
            elif ct2 == "pi":
                ds_monthly += _monthly_pmt(p2, rate2, ay2)
    # In NOI mode there is no separate OpEx figure — size reserve on DS only,
    # regardless of operating_reserve_basis.
    if income_mode == "noi":
        actual_reserve = _q(ds_monthly * Decimal(reserve_months))
        _or_basis_label = "Debt Service"
        _or_basis_monthly = ds_monthly
    else:
        if operating_reserve_basis == "ds":
            _or_basis_monthly = ds_monthly
            _or_basis_label = "Debt Service"
        elif operating_reserve_basis == "opex":
            _or_basis_monthly = opex_monthly
            _or_basis_label = "OpEx"
        else:  # opex_plus_ds
            _or_basis_monthly = opex_monthly + ds_monthly
            _or_basis_label = "OpEx + Debt Service"
        actual_reserve = _q(_or_basis_monthly * Decimal(reserve_months))

    # Compute actual construction IO across auto-sized modules.
    # Multi-debt path: dedicated construction_loan IO is in _bridge_io.
    # Perm-only path (or any deal whose construction-period carry sits on the
    # gap-fill module itself): the perm's principal was inflated by
    # constr_io_factor — we need a matching Use line for that pre-funded
    # interest reserve / capitalised interest, otherwise Sources > Uses by
    # exactly P · monthly_rate · build_months.
    total_constr_io = ZERO
    _constr_int_perm_module: CapitalModule | None = None
    _constr_int_perm_ct: str | None = None
    _has_constr_loan_module = bool(
        debt_types_list and "construction_loan" in debt_types_list
    )
    if _has_constr_loan_module:
        total_constr_io = _bridge_io.get("construction_loan", ZERO)
    else:
        for m in auto_modules:
            src3 = m.source or {}
            carry3 = m.carry or {}
            amt3 = src3.get("amount")
            if not amt3:
                continue
            p3 = Decimal(str(amt3))
            cr3 = _constr_phase_rate_pct(carry3, src3)
            if not cr3:
                continue
            # IO/PI carry pays debt service in cash during construction — that
            # cash carry is funded by the Construction DS Reserve line, not by
            # a Capitalized Construction Interest / IR pool.  Writing both
            # double-counts P × constr_io_factor in Uses (Sources < Uses by
            # exactly one carry amount).  Skip IR writeback for IO/PI here.
            _carry3_ct = _carry_type_for_phase(carry3, is_construction=True)
            if _carry3_ct in ("io_only", "pi"):
                continue
            # Use the module's own schedule duration when present (months /
            # milestone / remainder, as the user entered), else fall back to
            # the deal's construction-phase total.
            _m_schedule = (carry3 or {}).get("schedule") or []
            _m_preop_months = (
                _schedule_preop_months(
                    _m_schedule,
                    _milestone_month_map,
                    _loan_start_abs_month(m, phases),
                )
                if _m_schedule
                else constr_months_total
            )
            if _m_preop_months <= 0:
                continue
            # Split construction vs lease-up months so income ramp can offset
            # the lease-up portion (construction months use gross interest).
            _n_constr3 = _loan_pre_op_months(m, capital_modules, phases)
            _n_lu3 = max(0, _m_preop_months - _n_constr3)
            # Perm path: principal solve at line ~2710 defaults to fully_drawn
            # when draw_type is unset. Match that default here so Sources = Uses.
            _perm_draw_type3 = src3.get("draw_type") or "fully_drawn"
            _ds_carry = _q(
                period_interest_months(
                    p3,
                    _n_constr3,
                    float(cr3),
                    draw_schedule=_draw_schedule_for(_carry3_ct, _perm_draw_type3),
                )
            )
            _lu_phase3 = next((p for p in phases if p.period_type == PeriodType.lease_up), None)
            if _n_lu3 > 0 and _lu_phase3 and _carry3_ct == "interest_reserve":
                _ds_carry += _ir_lease_up_pool(
                    p3, cr3, _n_lu3, _lu_phase3, streams, expense_lines, inputs
                )
            if _ds_carry <= ZERO:
                continue
            total_constr_io += _ds_carry
            if _constr_int_perm_module is None:
                _constr_int_perm_module = m
                _constr_int_perm_ct = _carry_type_for_phase(
                    carry3, is_construction=True
                )

    # Get project_id from the first use_line (all belong to the same project)
    project_id = getattr(use_lines[0], "project_id", None) if use_lines else None
    _diag(f"WRITE-BACK project_id={project_id} _cc_data_n={len(_cc_data)} cc_module_ids={[_cc_data[k]['module'].id for k in _cc_data]}")
    for _dk, _dv in _cc_data.items():
        _dm2 = _dv['module']
        _diag(f"  cc module id={_dm2.id} vt={getattr(_dm2,'vehicle_type',None)} source.amount={(_dm2.source or {}).get('amount')} flat={_dv['flat']} pct={_dv['pct']}")

    # Update or create Operating Reserve use line
    _reserve_basis = _or_basis_label
    _reserve_amount_basis = _or_basis_monthly
    _reserve_notes = (
        f"Auto-computed ({_reserve_basis} basis): "
        f"${_reserve_amount_basis:,.0f}/mo × {reserve_months} months"
    )
    op_reserve_found = False
    _op_reserve_source_id = _reserve_source_module.id if _reserve_source_module else None
    for ul in use_lines:
        if getattr(ul, "label", "") == "Operating Reserve":
            ul.amount = actual_reserve
            ul.notes = _reserve_notes
            ul.source_capital_module_id = _op_reserve_source_id
            ul.cost_category = "soft"
            session.add(ul)
            op_reserve_found = True
            break
    if not op_reserve_found and project_id and actual_reserve > ZERO:
        new_op = UseLine(
            project_id=project_id,
            source_capital_module_id=_op_reserve_source_id,
            label="Operating Reserve",
            phase="operation",
            amount=actual_reserve,
            timing_type="first_day",
            cost_category="soft",
            dev_fee_basis_bucket="operating_reserve",
            notes=_reserve_notes,
        )
        session.add(new_op)
        use_lines.append(new_op)

    # Operating Deficit Reserve writeback. Spec §3.2: gated on the presence of
    # a lease-up phase. ``_odr_amount`` was computed up front and folded into
    # ``total_uses`` for the principal solve; here we surface it as a UseLine
    # so it appears in the Sources & Uses and the cash-flow line items can key
    # off ``label == "Operating Deficit Reserve"`` in Slice 5's waterfall.
    _odr_notes = (
        f"Auto-computed: Σ max(OpEx − LUR, 0) over {lease_up_months} lease-up months"
        if lease_up_months > 0
        else "Auto-cleared: no lease-up phase in timeline"
    )
    odr_found = False
    for ul in use_lines:
        if getattr(ul, "label", "") == "Operating Deficit Reserve":
            ul.amount = _odr_amount
            ul.notes = _odr_notes
            ul.cost_category = "soft"
            session.add(ul)
            odr_found = True
            break
    if not odr_found and project_id and _odr_amount > ZERO:
        new_odr = UseLine(
            project_id=project_id,
            label="Operating Deficit Reserve",
            phase="lease_up",
            amount=_odr_amount,
            timing_type="first_day",
            cost_category="soft",
            dev_fee_basis_bucket="operating_deficit_reserve",
            notes=_odr_notes,
        )
        session.add(new_odr)
        use_lines.append(new_odr)

    # Merge Lease-Up Reserve into Interest Reserve: perm DS shortfall during lease-up
    # is pre-stabilization carry, same as construction IR.  Add to total_constr_io so
    # the single IR use line covers the full pre-stabilization reserve pool.
    total_constr_io += _lease_up_carry

    # Update or create construction interest use line (balance-only: not a cash outflow).
    # Label depends on carry type: IR → "Interest Reserve", CI → "Capitalized Construction Interest".
    # Collect ALL rows matching any known construction interest label, keep exactly one.
    _CONSTR_INT_LABELS = {
        "Capitalized Construction Interest",
        "Construction Interest Reserve",   # legacy
        "Interest Reserve",                # IR carry type
    }
    _constr_int_ct = (
        _bridge_io_carry_type.get("construction_loan")
        or _constr_int_perm_ct
        or "capitalized_interest"
    )
    _constr_int_label = (
        "Interest Reserve"
        if _constr_int_ct == "interest_reserve"
        else "Capitalized Construction Interest"
    )
    _constr_int_notes = (
        "Auto-computed: interest reserve pre-funded from loan proceeds (includes lease-up DS shortfall)."
        if _constr_int_ct == "interest_reserve"
        else "Auto-computed: IO capitalized into loan principal."
    )
    _constr_int_bucket = (
        "interest_reserve" if _constr_int_ct == "interest_reserve"
        else "capitalized_interest"
    )
    # Phase 2e1: tag the Construction IO reserve with the construction loan
    # module id when present; otherwise the perm module that carries the
    # construction-period interest (perm-only structures with IR/CI carry).
    _ci_source_id = _bridge_io_module.get("construction_loan") or (
        _constr_int_perm_module.id if _constr_int_perm_module else None
    )
    _ci_rows = [ul for ul in use_lines if getattr(ul, "label", "") in _CONSTR_INT_LABELS]
    if _ci_rows:
        _ci_keep = _ci_rows[0]
        _ci_keep.label = _constr_int_label
        _ci_keep.amount = total_constr_io
        _ci_keep.notes = _constr_int_notes
        _ci_keep.source_capital_module_id = _ci_source_id
        _ci_keep.cost_category = "soft"
        _ci_keep.dev_fee_basis_bucket = _constr_int_bucket
        session.add(_ci_keep)
        for _ci_dup in _ci_rows[1:]:
            await session.delete(_ci_dup)
            use_lines.remove(_ci_dup)
    elif project_id and total_constr_io > ZERO:
        new_ul = UseLine(
            project_id=project_id,
            source_capital_module_id=_ci_source_id,
            label=_constr_int_label,
            phase="construction",
            amount=total_constr_io,
            timing_type="first_day",
            cost_category="soft",
            dev_fee_basis_bucket=_constr_int_bucket,
            notes=_constr_int_notes,
        )
        session.add(new_ul)
        use_lines.append(new_ul)

    # Lease-Up Reserve is merged into Interest Reserve (total_constr_io += _lease_up_carry above).
    # Delete any stale LUR rows left from before this change.
    for ul in list(use_lines):
        if getattr(ul, "label", "") == "Lease-Up Reserve":
            await session.delete(ul)
            use_lines.remove(ul)

    # Construction DS Reserve: pre-fund debt service payments during construction/renovation.
    # Applies only to cash-paying carry types (io_only, pi); CI/IR have their own use line mechanisms.
    _cds_source_id = _constr_ds_source_module.id if _constr_ds_source_module else None
    cds_reserve_found = False
    for ul in use_lines:
        if getattr(ul, "label", "") == "Construction DS Reserve":
            if _constr_ds_reserve > ZERO:
                ul.amount = _constr_ds_reserve
                ul.notes = f"Auto-computed: debt service during {constr_months_total}-month construction funded from bond proceeds"
                ul.source_capital_module_id = _cds_source_id
                ul.cost_category = "soft"
                session.add(ul)
            else:
                await session.delete(ul)
                use_lines.remove(ul)
            cds_reserve_found = True
            break
    if not cds_reserve_found and project_id and _constr_ds_reserve > ZERO:
        new_cds = UseLine(
            project_id=project_id,
            source_capital_module_id=_cds_source_id,
            label="Construction DS Reserve",
            phase="construction",
            amount=_constr_ds_reserve,
            timing_type="first_day",
            cost_category="soft",
            dev_fee_basis_bucket="construction_ds_reserve",
            notes=f"Auto-computed: debt service during {constr_months_total}-month construction funded from bond proceeds",
        )
        session.add(new_cds)
        use_lines.append(new_cds)

    # Phase B: write interest use lines for pre_development_loan and acquisition_loan.
    # Label is carry-type-aware: IR → "…Interest Reserve", CI → "Capitalized … Interest".
    # construction_loan interest uses the existing block above.
    if debt_types_list and project_id:
        _BRIDGE_INT_LABEL_MAP = {
            # (funder_type, carry_type) → label
            ("pre_development_loan", "interest_reserve"):      "Pre-Development Interest Reserve",
            ("pre_development_loan", "capitalized_interest"):  "Capitalized Pre-Development Interest",
            ("acquisition_loan",     "interest_reserve"):      "Acquisition Interest Reserve",
            ("acquisition_loan",     "capitalized_interest"):  "Capitalized Acquisition Interest",
        }
        _BRIDGE_ALL_LABELS = {
            "Pre-Development Interest Reserve",
            "Capitalized Pre-Development Interest",
            "Acquisition Interest Reserve",
            "Capitalized Acquisition Interest",
        }
        for _bft in ("pre_development_loan", "acquisition_loan"):
            _bio_amt = _bridge_io.get(_bft, ZERO)
            _bft_ct  = _bridge_io_carry_type.get(_bft, "capitalized_interest")
            _blabel  = _BRIDGE_INT_LABEL_MAP.get((_bft, _bft_ct),
                           f"Capitalized {_bft.replace('_', ' ').title()} Interest")
            _bnotes  = (
                f"Auto-computed: interest reserve pre-funded from {_bft.replace('_', ' ')} proceeds."
                if _bft_ct == "interest_reserve"
                else f"Auto-computed: IO capitalized into {_bft.replace('_', ' ')} principal."
            )
            _bbucket = (
                "interest_reserve" if _bft_ct == "interest_reserve"
                else "capitalized_interest"
            )
            # Find any existing row with any known label for this loan type
            _bft_prefix = "Pre-Development" if "pre_dev" in _bft else "Acquisition"
            _existing_bio = next(
                (ul for ul in use_lines
                 if getattr(ul, "label", "") in _BRIDGE_ALL_LABELS
                 and _bft_prefix in getattr(ul, "label", "")),
                None,
            )
            if _existing_bio:
                if _bio_amt > ZERO:
                    _existing_bio.label  = _blabel
                    _existing_bio.amount = _bio_amt
                    _existing_bio.notes  = _bnotes
                    _existing_bio.source_capital_module_id = _bridge_io_module.get(_bft)
                    _existing_bio.cost_category = "soft"
                    _existing_bio.dev_fee_basis_bucket = _bbucket
                    session.add(_existing_bio)
                else:
                    await session.delete(_existing_bio)
                    use_lines.remove(_existing_bio)
            elif _bio_amt > ZERO:
                _new_io_ul = UseLine(
                    project_id=project_id,
                    source_capital_module_id=_bridge_io_module.get(_bft),
                    label=_blabel,
                    phase="construction",
                    amount=_bio_amt,
                    timing_type="first_day",
                    cost_category="soft",
                    dev_fee_basis_bucket=_bbucket,
                    notes=_bnotes,
                )
                session.add(_new_io_ul)
                use_lines.append(_new_io_ul)

    # ── Write Total Finance Costs Use lines (one per CapitalModule) ─────────────
    # All auto-sized modules now have final principals.  Write/update one row per
    # module labeled "{module.label} — Total Finance Costs", carrying
    # is_auto_finance_cost=True so a later user edit (which flips the flag to
    # False via the form handler) is respected on the next compute.
    _diag(f"CC-WRITEBACK guard: _cc_data={bool(_cc_data)} project_id={project_id} -> enter={bool(_cc_data and project_id)}")
    if _cc_data and project_id:
        _fc_rate = DEFAULT_FINANCE_COST_PCT / HUNDRED
        for _cc_obj in _cc_data.values():
            _ccm_ref  = _cc_obj["module"]
            _ccm_ft   = _loan_subtype_from_module(_ccm_ref)
            _ccm_lbl  = getattr(_ccm_ref, "label", "") or _ccm_ft.replace("_", " ").title()
            _ccm_p    = Decimal(str((_ccm_ref.source or {}).get("amount") or 0))
            _ccm_aps  = getattr(_ccm_ref, "active_phase_start", None) or ""
            # Finance costs (origination, lender legal, appraisal, title) are paid
            # at LOAN CLOSING, not at loan activation. Refi-specific finance costs
            # are handled separately by the refi event (cashflow.py refi block).
            # Coerce later-stage activation values back to acquisition so the
            # auto-FC UseLine fires at deal close, where the lender is actually
            # paid. Default fallback is "acquisition" (the common case).
            _ccm_phase = _APS_TO_USE_PHASE.get(_ccm_aps, "acquisition")
            if _ccm_phase in {"operation", "exit"}:
                _ccm_phase = "acquisition"

            _cc_full_lbl = f"{_ccm_lbl} — Total Finance Costs"
            # Match the existing FC row by module link + (auto-flag OR label
            # suffix).  Matching by exact label alone breaks when the user
            # edits the label on the override — engine then creates a duplicate.
            _ccm_id = getattr(_ccm_ref, "id", None)
            _cc_exist = next(
                (
                    ul for ul in use_lines
                    if getattr(ul, "source_capital_module_id", None) == _ccm_id
                    and (
                        getattr(ul, "is_auto_finance_cost", False)
                        or (getattr(ul, "label", "") or "").endswith(" — Total Finance Costs")
                    )
                ),
                None,
            )
            # User override — flag turned off → leave untouched.
            if _cc_exist is not None and not getattr(_cc_exist, "is_auto_finance_cost", False):
                continue

            _cc_amt = _q(_ccm_p * _fc_rate)
            _diag(f"  CC write label={_cc_full_lbl!r} _ccm_p={_ccm_p} pct={_fc_rate} -> amt={_cc_amt} exist_id={getattr(_cc_exist,'id',None) if _cc_exist else None}")

            _cc_cat = "acquisition" if _ccm_ft == "acquisition_loan" else "soft"
            # NOTE: auto-FC UseLine deliberately does NOT inherit the parent
            # module's active_from_milestone_id. Finance costs (origination,
            # title, appraisal, lender legal) are paid at LOAN CLOSING — which
            # in this codebase is the "close" milestone, regardless of when the
            # loan first becomes active. The UseLine phase is already coerced
            # to "acquisition" upstream (see _ccm_phase derivation).
            if _cc_exist is not None:
                _cc_exist.amount = _cc_amt
                _cc_exist.phase  = _ccm_phase
                _cc_exist.source_capital_module_id = getattr(_ccm_ref, "id", None)
                _cc_exist.cost_category = _cc_cat
                _cc_exist.is_auto_finance_cost = True
                _cc_exist.dev_fee_basis_bucket = "total_finance_costs"
                session.add(_cc_exist)
            elif _cc_amt > ZERO:
                _new_cc_ul = UseLine(
                    project_id=project_id,
                    source_capital_module_id=getattr(_ccm_ref, "id", None),
                    label=_cc_full_lbl,
                    phase=_ccm_phase,
                    amount=_cc_amt,
                    timing_type="first_day",
                    cost_category=_cc_cat,
                    is_auto_finance_cost=True,
                    dev_fee_basis_bucket="total_finance_costs",
                    notes="Auto-computed — edit any field to disable; delete to reset.",
                )
                session.add(_new_cc_ul)
                use_lines.append(_new_cc_ul)

    # ── Equity auto-size pass ─────────────────────────────────────────────────
    # After all debt is sized, set equity auto-sized modules to fill any remaining
    # gap. In stack_position order: first equity gets the remainder, rest get $0.
    # Grants are excluded — resolve_grant_caps already set their amounts.
    _equity_auto = [
        m for m in capital_modules
        if (m.source or {}).get("auto_size")
        and str(getattr(m, "vehicle_type", None) or "").replace("VehicleType.", "") == "equity"
    ]
    if _equity_auto:
        # Equity gap-fill needs the FULL use-line total (including Operating
        # Reserve and other balance-only labels excluded from the debt sizer's
        # `total_uses`). Those rows appear in the Sources=Uses display; equity
        # must cover whatever debt did not. The debt sizer excludes them because
        # they're algebraically folded into the debt principal — so `_eq_covered`
        # already includes the reserve inside the debt amount, and using the
        # reserve-inclusive total here produces the correct zero remainder when
        # debt covers everything, and the correct positive remainder otherwise.
        _eq_total_uses = sum(
            (_to_decimal(ul.amount) for ul in use_lines
             if str(getattr(ul.phase, "value", ul.phase)) != "exit"),
            ZERO,
        )
        _eq_covered = sum(
            _to_decimal((_cm.source or {}).get("amount") or 0)
            for _cm in capital_modules
            if _cm not in _equity_auto and (_cm.source or {}).get("amount")
        )
        _eq_remaining = max(ZERO, _eq_total_uses - _eq_covered)
        _eq_sorted = sorted(_equity_auto, key=lambda m: (m.stack_position or 999, m.id or 0))
        for _i, _eq_m in enumerate(_eq_sorted):
            _eq_src = dict(_eq_m.source or {})
            _eq_src["amount"] = str(_whole_dollar(_eq_remaining if _i == 0 else ZERO))
            _eq_m.source = _eq_src
        _diag(f"equity auto-size pass: remaining={_eq_remaining} modules={[m.id for m in _eq_sorted]}")

    await session.flush()


def _monthly_pmt(principal: Decimal, rate_pct: float | None, amort_years: int = 30) -> Decimal:
    """P&I monthly payment via standard amortization formula."""
    if not rate_pct:
        return ZERO
    monthly_rate = Decimal(str(rate_pct)) / HUNDRED / Decimal("12")
    if monthly_rate == ZERO:
        return _q(principal / Decimal(amort_years * 12))
    n = amort_years * 12
    factor = (ONE + monthly_rate) ** n
    return _q(principal * monthly_rate * factor / (factor - ONE))


def _monthly_io(principal: Decimal, rate_pct: float | None) -> Decimal:
    """Interest-only monthly payment."""
    if not rate_pct:
        return ZERO
    return _q(principal * Decimal(str(rate_pct)) / HUNDRED / Decimal("12"))


def _balloon_balance(
    principal: Decimal,
    rate_pct: float | None,
    amort_years: int,
    months_elapsed: int,
    io_months: int = 0,
) -> Decimal:
    """Remaining loan balance after *months_elapsed* of payments.

    Handles IO-then-amortizing: the first *io_months* are interest-only
    (balance stays at principal), then amortization begins.  Uses the
    standard FV-of-annuity formula:

        balance = principal × (1+r)^n_amort − pmt × [(1+r)^n_amort − 1] / r

    where n_amort = months_elapsed − io_months (clamped ≥ 0).
    Returns the original principal if no rate or no amortization.
    """
    if principal <= ZERO:
        return ZERO
    if not rate_pct or amort_years <= 0:
        return principal  # no amortization → full balance outstanding
    monthly_rate = Decimal(str(rate_pct)) / HUNDRED / Decimal("12")
    if monthly_rate == ZERO:
        # Zero-rate amortization: straight-line paydown
        total_months = amort_years * 12
        amort_months_paid = max(0, months_elapsed - io_months)
        remaining = principal - _q(principal * Decimal(amort_months_paid) / Decimal(total_months))
        return _q(max(remaining, ZERO))
    n_amort = max(0, months_elapsed - io_months)
    if n_amort == 0:
        return principal  # still in IO period
    if n_amort >= amort_years * 12:
        return ZERO  # fully amortized — sweep residual to exact $0
    pmt = _monthly_pmt(principal, rate_pct, amort_years)
    factor = (ONE + monthly_rate) ** n_amort
    balance = _q(principal * factor - pmt * (factor - ONE) / monthly_rate)
    return _q(max(balance, ZERO))


def _sum_debt_service(
    modules: list,
    is_construction: bool,
    exclude_ids: set | None = None,
) -> Decimal:
    """Compute total monthly debt service for construction or operation phase."""
    total = ZERO
    for m in modules:
        if exclude_ids and getattr(m, "id", None) in exclude_ids:
            continue
        if not _is_debt_cm(m):
            continue
        carry = m.carry or {}
        ct = _carry_type_for_phase(carry, is_construction)
        source = m.source or {}
        amount = source.get("amount")
        if not amount:
            continue
        principal = Decimal(str(amount))
        # Rate may be in source["interest_rate_pct"] or flat carry["io_rate_pct"]
        rate_pct = source.get("interest_rate_pct") or carry.get("io_rate_pct")
        if ct in ("interest_reserve", "capitalized_interest"):
            continue  # no periodic DS — IR pre-funded; CI accrues to balance
        elif ct == "io_only":
            # True IO — periodic cash payments, balance stays flat
            carry_phase = _get_phase_carry(carry, "construction" if is_construction else "operation")
            phase_rate = carry_phase.get("io_rate_pct") if carry_phase else None
            total += _monthly_io(principal, phase_rate or rate_pct)
        elif ct == "pi":
            carry_phase = _get_phase_carry(carry, "operation")
            amort_years = int(
                (carry_phase or {}).get("amort_term_years")
                or source.get("amort_term_years")
                or 30
            )
            phase_rate = (carry_phase or {}).get("io_rate_pct") if carry_phase else None
            total += _monthly_pmt(principal, phase_rate or rate_pct, amort_years)
        # ct == "none" → zero contribution (falls through)
    return total


def _compute_period(
    *,
    deal_model_id: UUID,
    period: int,
    phase: PhaseSpec,
    month_index: int,
    inputs: OperationalInputs,
    streams: list[IncomeStream],
    expense_lines: list[OperatingExpenseLine],
    use_lines: list[UseLine] | None = None,
    stabilized_noi_monthly: Decimal | None,
    construction_debt_monthly: Decimal = ZERO,
    operation_debt_monthly: Decimal = ZERO,
    schedule_debt_monthly: Decimal = ZERO,
    income_mode: str = "revenue_opex",
    first_stab_period: int = 0,
    project_id: UUID | None = None,
    use_line_phase_overrides: dict | None = None,
    ir_lease_up_interest: Decimal = ZERO,
) -> dict[str, Any]:
    gross_revenue = ZERO
    vacancy_loss = ZERO
    effective_gross_income = ZERO
    operating_expenses = ZERO
    capex_reserve = ZERO
    debt_service = (
        construction_debt_monthly
        if phase.period_type in _CONSTRUCTION_PERIOD_TYPES
        else operation_debt_monthly
    ) + schedule_debt_monthly
    capital_inflow = ZERO
    capital_outflow = ZERO
    line_items: list[CashFlowLineItem] = []

    _is_operational_phase = phase.period_type in {PeriodType.lease_up, PeriodType.stabilized}

    if income_mode == "noi" and _is_operational_phase:
        # NOI mode: the `noi_stabilized_input` is "NOI at first stabilized
        # month" (the underwriting convention). Escalation anchors at
        # first_stab_period so:
        #   - First stab month (period == first_stab_period): esc_factor = 1.0
        #   - Year 2 of stab (period = first_stab + 12): esc_factor = (1+r)
        #   - Lease-up phase: escalation is clamped at 1.0 so it doesn't
        #     exceed the stabilized value (simplification — lease-up NOI
        #     isn't modeled separately in NOI mode)
        # This prevents DSCR drift in dscr_capped / dual_constraint sizing
        # because the NOI used for sizing (raw input) == NOI shown at first
        # stabilized month.
        _noi_annual = _to_decimal(inputs.noi_stabilized_input) if inputs.noi_stabilized_input else ZERO
        for _el_noi in (expense_lines or []):
            if getattr(_el_noi, "label", "") == "Gap Adjustment — NOI":
                _noi_annual += _to_decimal(getattr(_el_noi, "annual_amount", 0) or 0)
                break
        _esc_rate = _to_decimal(inputs.noi_escalation_rate_pct) if inputs.noi_escalation_rate_pct else Decimal("3")
        _esc_period = max(0, period - first_stab_period)
        _esc_factor = _growth_factor(_esc_rate, _esc_period)
        _noi_monthly = _q(_noi_annual / Decimal("12") * _esc_factor)
        gross_revenue = _noi_monthly
        vacancy_loss = ZERO
        effective_gross_income = _noi_monthly
        operating_expenses = ZERO
        # Zero-initialize variables only assigned in the else branch so unconditional
        # code below (legacy scalar loop, capex reserve) doesn't raise UnboundLocalError.
        units_operating = ZERO
        expense_growth = ONE
        property_tax = insurance = operating_expense = management_fee = carrying_cost = ZERO
        line_items.append(
            CashFlowLineItem(
                scenario_id=deal_model_id,
                period=period,
                category=LineItemCategory.income,
                label="NOI (Stabilized)",
                base_amount=_q(_noi_annual / Decimal("12")),
                adjustments=_json_ready({
                    "phase": phase.period_type.value,
                    "escalation_factor": _esc_factor,
                    "income_mode": "noi",
                }),
                net_amount=_noi_monthly,
            )
        )
    else:
        for stream in streams:
            base_amount = _stream_base_amount(stream)
            escalation_factor = _growth_factor(stream.escalation_rate_pct_annual, period)

            active = _is_stream_active(stream, phase.period_type)
            if active:
                # LTL catchup: accelerated escalation up to cap, then normal
                _catchup_target = _to_decimal(getattr(stream, "catchup_target_rent", None))
                if _catchup_target > ZERO and base_amount > ZERO:
                    # Simulate year-by-year catchup from base to target
                    _cap = LTL_CATCHUP_CAP_PCT / HUNDRED
                    _normal_rate = _percent(stream.escalation_rate_pct_annual)
                    _current = base_amount
                    _years = period // 12
                    _month_in_year = period % 12
                    for _yr in range(_years):
                        if _current < _catchup_target:
                            _increase = min(
                                _catchup_target - _current,
                                _current * _cap,
                            )
                            _current = _q(_current + _increase)
                        else:
                            _current = _q(_current * (ONE + _normal_rate))
                    # Partial year: interpolate
                    if _month_in_year > 0:
                        if _current < _catchup_target:
                            _yr_increase = min(
                                _catchup_target - _current,
                                _current * _cap,
                            )
                            _current = _q(_current + _yr_increase * Decimal(_month_in_year) / Decimal("12"))
                        else:
                            _current = _q(_current * (ONE + _normal_rate) ** (Decimal(_month_in_year) / Decimal("12")))
                    escalated_amount = _current
                else:
                    escalated_amount = _q(base_amount * escalation_factor)
                # Renovation absorption: two modes
                # 1. Discrete capture schedule (PropRise-style): [{year: 1, capture_pct: 0}, ...]
                # 2. Continuous linear ramp: renovation_absorption_rate scales 0→100%
                _capture_sched = getattr(stream, "renovation_capture_schedule", None)
                _reno_abs = _to_decimal(getattr(stream, "renovation_absorption_rate", None))
                if _capture_sched and phase.period_type in {
                    PeriodType.minor_renovation, PeriodType.major_renovation,
                    PeriodType.construction, PeriodType.conversion,
                    PeriodType.lease_up, PeriodType.stabilized,
                }:
                    # Discrete: look up capture_pct for the current year (1-indexed)
                    _current_year = (period // 12) + 1
                    _cap_pct = Decimal("100")  # default to full capture
                    for entry in _capture_sched:
                        if int(entry.get("year", 0)) == _current_year:
                            _cap_pct = Decimal(str(entry.get("capture_pct", 100)))
                            break
                    escalated_amount = _q(escalated_amount * _cap_pct / HUNDRED)
                elif _reno_abs > ZERO and phase.period_type in {
                    PeriodType.minor_renovation, PeriodType.major_renovation,
                    PeriodType.construction, PeriodType.conversion,
                    PeriodType.lease_up,
                }:
                    _reno_months = int(inputs.renovation_months or inputs.construction_months or 0)
                    _lu_months = int(inputs.lease_up_months or 0)
                    _total_abs = _reno_months + _lu_months
                    if _total_abs > 0:
                        _abs_frac = _q(Decimal(min(period + 1, _total_abs)) / Decimal(_total_abs))
                        _abs_frac = _clamp(_abs_frac, ZERO, ONE)
                        escalated_amount = _q(escalated_amount * _abs_frac)
                occupancy_pct = _stream_occupancy_pct(stream, phase, month_index, inputs)
                after_vacancy = _q(escalated_amount * occupancy_pct)
                vacancy = _q(escalated_amount - after_vacancy)
                # Bad debt and concessions: % of GPR, but capped so EGI stays >= 0.
                # When combined deductions exceed collected rent (e.g. full vacancy),
                # scale both down proportionally so net_income floors at zero and the
                # accounting identity (net + vacancy + bad_debt + concessions == GPR) holds.
                bad_debt_pct = _percent(getattr(stream, "bad_debt_pct", None))
                concessions_pct = _percent(getattr(stream, "concessions_pct", None))
                bad_debt = _q(escalated_amount * bad_debt_pct)
                concessions = _q(escalated_amount * concessions_pct)
                _total_deductions = bad_debt + concessions
                if _total_deductions > after_vacancy and _total_deductions > ZERO:
                    _scale = after_vacancy / _total_deductions
                    bad_debt = _q(bad_debt * _scale)
                    concessions = after_vacancy - bad_debt
                net_income = _q(after_vacancy - bad_debt - concessions)
            else:
                escalated_amount = ZERO
                occupancy_pct = ZERO
                net_income = ZERO
                vacancy = ZERO
                bad_debt = ZERO
                concessions = ZERO
                bad_debt_pct = ZERO
                concessions_pct = ZERO

            gross_revenue += escalated_amount
            vacancy_loss += vacancy
            effective_gross_income += net_income

            line_items.append(
                CashFlowLineItem(
                    scenario_id=deal_model_id,
                    period=period,
                    income_stream_id=stream.id,
                    category=LineItemCategory.income,
                    label=stream.label,
                    base_amount=_q(base_amount),
                    adjustments=_json_ready(
                        {
                            "phase": phase.period_type.value,
                            "active": active,
                            "units": stream.unit_count or 0,
                            "occupancy_pct": occupancy_pct * HUNDRED,
                            "escalation_factor": escalation_factor,
                            "vacancy_loss": vacancy,
                            "bad_debt": bad_debt,
                            "concessions": concessions,
                            "bad_debt_pct": bad_debt_pct * HUNDRED,
                            "concessions_pct": concessions_pct * HUNDRED,
                        }
                    ),
                    net_amount=net_income,
                )
            )

        expense_growth = _growth_factor(inputs.expense_growth_rate_pct_annual, period)
        units_operating = _operating_unit_count(inputs, phase.period_type)

        property_tax = _monthly_expense(inputs.property_tax_annual, expense_growth)
        insurance = _monthly_expense(inputs.insurance_annual, expense_growth)
        operating_expense = (
            _q((_to_decimal(inputs.opex_per_unit_annual) * units_operating / Decimal("12")) * expense_growth)
            if _phase_is_operational(phase.period_type)
            else ZERO
        )
        itemized_operating_expense = ZERO
        for expense_line in expense_lines:
            line_growth = _growth_factor(expense_line.escalation_rate_pct_annual, period)
            line_active = _is_expense_line_active(expense_line, phase.period_type)
            if line_active:
                line_base = _monthly_expense(expense_line.annual_amount, line_growth)
                # During lease-up, scale occupancy-sensitive lines by the same ramp used for revenue
                lease_up_scale = ONE
                if phase.period_type == PeriodType.lease_up and expense_line.scale_with_lease_up:
                    floor_pct = _percent(expense_line.lease_up_floor_pct, default=ZERO)
                    # NULL → 0% to match the wizard slider default; see
                    # comment on _odr_pool's initial_occ for the rationale.
                    initial_occ = _percent(inputs.initial_occupancy_pct, default=ZERO)
                    stabilized_occ = Decimal("0.95")  # default stabilized occupancy
                    # Use the shared lease-up ramp helper so OpEx tracks
                    # whichever curve (linear / s_curve) the wizard slider
                    # picked. Same helper is used by _stream_occupancy_pct
                    # on the revenue side and by _odr_pool when sizing the
                    # Operating Deficit Reserve.
                    ramp_occ = lease_up_ramp_occupancy(
                        initial_occ=initial_occ,
                        stabilized_occ=stabilized_occ,
                        month_index=month_index,
                        months=phase.months,
                        curve=str(getattr(inputs, "lease_up_curve", None) or "linear"),
                        steepness=getattr(inputs, "lease_up_curve_steepness", None),
                    )
                    lease_up_scale = _clamp(ramp_occ, floor_pct, ONE)
                line_amount = _q(line_base * lease_up_scale)
            else:
                line_base = ZERO
                line_amount = ZERO
                lease_up_scale = ZERO
            itemized_operating_expense += line_amount
            line_items.append(
                _expense_line_item(
                    deal_model_id,
                    period,
                    LineItemCategory.expense,
                    expense_line.label,
                    line_amount,
                    {
                        "phase": phase.period_type.value,
                        "active": line_active,
                        "annual_amount": expense_line.annual_amount,
                        "escalation_factor": line_growth,
                        "lease_up_scale": float(lease_up_scale) if phase.period_type == PeriodType.lease_up else None,
                        "expense_line_id": str(expense_line.id),
                    },
                )
            )
        management_fee = _q(effective_gross_income * _percent(inputs.mgmt_fee_pct))
        carrying_cost = (
            _q(_to_decimal(inputs.purchase_price) * _percent(inputs.carrying_cost_pct_annual) / Decimal("12"))
            if phase.period_type
            in {
                PeriodType.hold,
                PeriodType.pre_construction,
                PeriodType.minor_renovation,
                PeriodType.major_renovation,
                PeriodType.conversion,
                PeriodType.construction,
                PeriodType.lease_up,
            }
            else ZERO
        )

        operating_expenses += (
            property_tax
            + insurance
            + operating_expense
            + itemized_operating_expense
            + management_fee
            + carrying_cost
        )

        # Legacy scalar fields (property_tax_annual, insurance_annual, opex_per_unit_annual,
        # mgmt_fee_pct, carrying_cost_pct_annual on OperationalInputs) are superseded by
        # OperatingExpenseLine rows. Only write line items when non-zero to avoid duplicates
        # and noise on deals that have migrated to line-item OpEx.
        for _lbl, _amt, _meta in [
            ("Property Tax",       property_tax,     {"phase": phase.period_type.value, "annual_amount": inputs.property_tax_annual or ZERO}),
            ("Insurance",          insurance,         {"phase": phase.period_type.value, "annual_amount": inputs.insurance_annual or ZERO}),
            ("Operating Expenses", operating_expense, {"phase": phase.period_type.value, "units": units_operating}),
            ("Management Fee",     management_fee,    {"phase": phase.period_type.value, "mgmt_fee_pct": inputs.mgmt_fee_pct or ZERO}),
            ("Carrying Cost",      carrying_cost,     {"phase": phase.period_type.value, "carrying_cost_pct_annual": inputs.carrying_cost_pct_annual or ZERO}),
        ]:
            if _amt > ZERO:
                line_items.append(_expense_line_item(deal_model_id, period, LineItemCategory.expense, _lbl, _amt, _meta))

    if phase.period_type in {PeriodType.lease_up, PeriodType.stabilized, PeriodType.exit}:
        capex_reserve = _q(
            (_to_decimal(inputs.capex_reserve_per_unit_annual) * units_operating / Decimal("12"))
            * expense_growth
        )
        line_items.append(
            _expense_line_item(
                deal_model_id,
                period,
                LineItemCategory.capex_reserve,
                "Capex Reserve",
                capex_reserve,
                {"phase": phase.period_type.value, "units": units_operating},
            )
        )

    capital_events = _phase_capital_events(
        phase=phase,
        inputs=inputs,
        month_index=month_index,
        deal_model_id=deal_model_id,
        period=period,
        stabilized_noi_monthly=stabilized_noi_monthly,
        has_use_lines=bool(use_lines),
        income_mode=income_mode,
        first_stab_period=first_stab_period,
    )
    for item in capital_events:
        line_items.append(item)
        direction = (item.adjustments or {}).get("direction")
        if direction == "inflow":
            capital_inflow += _to_decimal(item.net_amount)
        else:
            capital_outflow += _to_decimal(item.net_amount)

    # UseLine outflows: first_day fires at month_index==0; spread fires every month.
    # Balance-only lines (Operating Reserve, Capitalized Construction Interest) are excluded —
    # their costs are already captured via cash balance residual and debt_service respectively.
    if use_lines:
        for ul in use_lines:
            if getattr(ul, "label", "") in _BALANCE_ONLY_LABELS:
                continue
            # Phase B: prefer milestone FK override; fall back to phase string
            period_types = (
                (use_line_phase_overrides or {}).get(ul.id)
                or _USE_LINE_PHASE_MAP.get(
                    str(getattr(ul, "phase", "") or "").replace("UseLinePhase.", ""),
                    set(),
                )
            )
            if phase.period_type not in period_types:
                continue
            total_amount = _to_decimal(ul.amount)
            if total_amount == ZERO:
                continue
            ul_timing = str(getattr(ul, "timing_type", "first_day")).replace("UseLineTiming.", "")
            if ul_timing == "spread":
                # Divide evenly across all months of this phase
                monthly_amount = _q(total_amount / Decimal(str(max(phase.months, 1))))
                # Rounding remainder: add to last month
                if month_index == phase.months - 1:
                    monthly_amount = total_amount - _q(monthly_amount * Decimal(str(phase.months - 1)))
                amount = monthly_amount
            else:
                # first_day: lump sum on month 0 only
                if month_index != 0:
                    continue
                amount = total_amount
            line_items.append(
                _expense_line_item(
                    deal_model_id, period,
                    LineItemCategory.capital_event,
                    ul.label,
                    amount,
                    {"phase": phase.period_type.value, "direction": "outflow",
                     "timing": ul_timing, "use_line_id": str(ul.id)},
                )
            )
            capital_outflow += amount

    line_items.append(
        _expense_line_item(
            deal_model_id,
            period,
            LineItemCategory.debt_service,
            "Debt Service (Stage 1A placeholder)",
            debt_service,
            {"phase": phase.period_type.value, "placeholder": True},
        )
    )

    noi = _q(effective_gross_income - operating_expenses - capex_reserve)

    # Spec §3 / §7 — LUR sweep to principal during the IR window.
    # Pre-spec, this block netted NOI against sized interest by inflating
    # ``debt_service``. That made the IR pool look smaller than the lender
    # actually funded and let lease-up rent shrink the sized reserve. Under
    # the spec, IR pays 100% of interest during its window (sized LUR-blind
    # in ``_ir_lease_up_pool``); excess NOI sweeps to principal — reducing
    # the lender's payoff balance, not the interest-bearing balance, not the
    # sized DS amount. The sweep shows up here as a real cash outflow so the
    # period's distributable cash equals the post-sweep residual.
    lur_sweep = ZERO
    if phase.period_type == PeriodType.lease_up and ir_lease_up_interest > ZERO:
        lur_sweep = max(ZERO, noi)
        if lur_sweep > ZERO:
            line_items.append(
                CashFlowLineItem(
                    scenario_id=deal_model_id,
                    period=period,
                    category=LineItemCategory.debt_service,
                    label="LUR Sweep to Principal",
                    base_amount=lur_sweep,
                    adjustments=_json_ready({
                        "phase": phase.period_type.value,
                        "applies_to": "payoff_balance_only",
                    }),
                    net_amount=lur_sweep,
                )
            )

    net_cash_flow = _q(noi - debt_service - capital_outflow + capital_inflow - lur_sweep)

    return {
        "gross_revenue": _q(gross_revenue),
        "vacancy_loss": _q(vacancy_loss),
        "effective_gross_income": _q(effective_gross_income),
        "operating_expenses": _q(operating_expenses),
        "capex_reserve": _q(capex_reserve),
        "noi": noi,
        "debt_service": debt_service,
        "lur_sweep": lur_sweep,
        "net_cash_flow": net_cash_flow,
        "line_items": line_items,
    }


def _phase_months_from_milestones(
    milestone_dates: dict[str, Any] | None,
    *,
    start_keys: tuple[str, ...],
    end_keys: tuple[str, ...],
    fallback: int,
) -> int:
    if not milestone_dates:
        return fallback

    start_date = _first_milestone_date(milestone_dates, start_keys)
    end_date = _first_milestone_date(milestone_dates, end_keys)
    if start_date is None or end_date is None or end_date <= start_date:
        return fallback

    months = ((end_date.year - start_date.year) * 12) + (end_date.month - start_date.month)
    return max(1, months or 1)


def _first_milestone_date(milestone_dates: dict[str, Any], keys: tuple[str, ...]) -> date | None:
    for key in keys:
        parsed = _parse_milestone_date(milestone_dates.get(key))
        if parsed is not None:
            return parsed
    return None


def _parse_milestone_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _phase_capital_events(
    *,
    phase: PhaseSpec,
    inputs: OperationalInputs,
    month_index: int,
    deal_model_id: UUID,
    period: int,
    stabilized_noi_monthly: Decimal | None,
    has_use_lines: bool = False,
    income_mode: str = "revenue_opex",
    first_stab_period: int = 0,
) -> list[CashFlowLineItem]:
    """Generate capital event line items for a phase.

    Legacy scalar cost items (purchase_price, renovation_cost_total, etc.) are
    suppressed when use_lines exist — the UseLine table is the authoritative source
    for capital costs.  Exit sale proceeds are always computed regardless.
    """
    items: list[CashFlowLineItem] = []

    if has_use_lines:
        # Skip all legacy scalar COST items; fall through to exit proceeds only.
        pass
    elif phase.period_type == PeriodType.acquisition and month_index == 0:
        purchase_price = _to_decimal(inputs.purchase_price)
        closing_costs = _q(purchase_price * _percent(inputs.closing_costs_pct))
        items.extend(
            [
                _expense_line_item(
                    deal_model_id,
                    period,
                    LineItemCategory.capital_event,
                    "Purchase Price",
                    purchase_price,
                    {"phase": phase.period_type.value, "direction": "outflow"},
                ),
                _expense_line_item(
                    deal_model_id,
                    period,
                    LineItemCategory.capital_event,
                    "Closing Costs",
                    closing_costs,
                    {
                        "phase": phase.period_type.value,
                        "direction": "outflow",
                        "closing_costs_pct": inputs.closing_costs_pct or ZERO,
                    },
                ),
            ]
        )

    elif phase.period_type == PeriodType.pre_construction:
        entitlement_cost = _allocate_evenly(inputs.entitlement_cost, phase.months)
        items.append(
            _expense_line_item(
                deal_model_id,
                period,
                LineItemCategory.capital_event,
                "Entitlement / Pre-Construction Cost",
                entitlement_cost,
                {"phase": phase.period_type.value, "direction": "outflow"},
            )
        )

    elif phase.period_type in {PeriodType.minor_renovation, PeriodType.major_renovation}:
        renovation_cost = _allocate_evenly(inputs.renovation_cost_total, phase.months)
        items.append(
            _expense_line_item(
                deal_model_id,
                period,
                LineItemCategory.capital_event,
                "Renovation Cost",
                renovation_cost,
                {"phase": phase.period_type.value, "direction": "outflow"},
            )
        )

    elif phase.period_type == PeriodType.conversion:
        units = _to_decimal(inputs.unit_count_after_conversion or inputs.unit_count_new)
        conversion_cost = _q(_to_decimal(inputs.conversion_cost_per_unit) * units)
        permit_cost = _to_decimal(inputs.change_of_use_permit_cost)
        total_conversion = _q(conversion_cost + permit_cost)
        items.append(
            _expense_line_item(
                deal_model_id,
                period,
                LineItemCategory.capital_event,
                "Conversion Cost",
                _allocate_evenly(total_conversion, phase.months),
                {"phase": phase.period_type.value, "direction": "outflow"},
            )
        )

    elif phase.period_type == PeriodType.construction:
        unit_count = _to_decimal(inputs.unit_count_new)
        hard_cost_total = _q(_to_decimal(inputs.hard_cost_per_unit) * unit_count)
        soft_cost_total = _q(hard_cost_total * _percent(inputs.soft_cost_pct_of_hard))
        contingency_total = _q((hard_cost_total + soft_cost_total) * _percent(inputs.contingency_pct))
        items.extend(
            [
                _expense_line_item(
                    deal_model_id,
                    period,
                    LineItemCategory.capital_event,
                    "Hard Costs",
                    _allocate_evenly(hard_cost_total, phase.months),
                    {"phase": phase.period_type.value, "direction": "outflow"},
                ),
                _expense_line_item(
                    deal_model_id,
                    period,
                    LineItemCategory.capital_event,
                    "Soft Costs",
                    _allocate_evenly(soft_cost_total, phase.months),
                    {"phase": phase.period_type.value, "direction": "outflow"},
                ),
                _expense_line_item(
                    deal_model_id,
                    period,
                    LineItemCategory.capital_event,
                    "Construction Contingency",
                    _allocate_evenly(contingency_total, phase.months),
                    {"phase": phase.period_type.value, "direction": "outflow"},
                ),
            ]
        )

    if phase.period_type == PeriodType.exit:
        sale_proceeds = ZERO
        if stabilized_noi_monthly is not None and _percent(inputs.exit_cap_rate_pct) > ZERO:
            _esc_rate = _to_decimal(inputs.noi_escalation_rate_pct) if inputs.noi_escalation_rate_pct else Decimal("3")
            _esc_period = max(0, period - first_stab_period)
            _exit_noi = _q(stabilized_noi_monthly * _growth_factor(_esc_rate, _esc_period))
            sale_proceeds = _q(
                (_exit_noi * Decimal("12")) / _percent(inputs.exit_cap_rate_pct)
            )
        selling_costs = _q(sale_proceeds * _percent(inputs.selling_costs_pct))
        items.extend(
            [
                _expense_line_item(
                    deal_model_id,
                    period,
                    LineItemCategory.capital_event,
                    "Sale Proceeds",
                    sale_proceeds,
                    {"phase": phase.period_type.value, "direction": "inflow"},
                ),
                _expense_line_item(
                    deal_model_id,
                    period,
                    LineItemCategory.capital_event,
                    "Selling Costs",
                    selling_costs,
                    {
                        "phase": phase.period_type.value,
                        "direction": "outflow",
                        "selling_costs_pct": inputs.selling_costs_pct or ZERO,
                    },
                ),
            ]
        )
        # Note: prepay penalties at exit are injected in the main compute_cash_flows
        # loop which has access to capital modules — not here.

    return items


def _stream_base_amount(stream: IncomeStream) -> Decimal:
    if stream.amount_fixed_monthly is not None:
        return _to_decimal(stream.amount_fixed_monthly)
    # When unit_count is explicitly NULL (not set), treat as 1 unit so per-unit amounts
    # aren't silently zeroed out.  Explicit 0 is respected (disables the stream).
    units = _to_decimal(stream.unit_count) if stream.unit_count is not None else ONE
    return _q(_to_decimal(stream.amount_per_unit_monthly) * units)


def _monthly_expense(annual_amount: Any, growth_factor: Decimal) -> Decimal:
    return _q((_to_decimal(annual_amount) / Decimal("12")) * growth_factor)


def _allocate_evenly(amount: Any, months: int) -> Decimal:
    month_count = max(1, months)
    return _q(_to_decimal(amount) / Decimal(month_count))


def _calculate_total_project_cost(line_items: list[CashFlowLineItem]) -> Decimal:
    total = ZERO
    for item in line_items:
        if item.category != LineItemCategory.capital_event:
            continue
        direction = (item.adjustments or {}).get("direction")
        if direction != "inflow":
            total += _to_decimal(item.net_amount)
    return _q(total)


def _calculate_equity_required(net_cash_flow_series: list[Decimal]) -> Decimal:
    running = ZERO
    minimum = ZERO
    for amount in net_cash_flow_series:
        running += _to_decimal(amount)
        if running < minimum:
            minimum = running
    return _q(abs(minimum))


def _compute_xirr(cash_flows: list[Decimal]) -> Decimal:
    if pyxirr is None or not cash_flows:
        return ZERO

    has_positive = any(amount > ZERO for amount in cash_flows)
    has_negative = any(amount < ZERO for amount in cash_flows)
    if not (has_positive and has_negative):
        return ZERO

    dates = [_add_months(date(2026, 1, 1), idx) for idx in range(len(cash_flows))]
    try:
        result = pyxirr.xirr(dates, [float(amount) for amount in cash_flows])
        if result is None or not (result == result):  # None or NaN
            return ZERO
        return _q(Decimal(str(result)) * HUNDRED)
    except Exception:
        return ZERO


def _expense_line_item(
    deal_model_id: UUID,
    period: int,
    category: LineItemCategory,
    label: str,
    amount: Decimal,
    adjustments: dict[str, Any],
    *,
    project_id: UUID | None = None,
) -> CashFlowLineItem:
    return CashFlowLineItem(
        scenario_id=deal_model_id,
        project_id=project_id,
        period=period,
        income_stream_id=None,
        category=category,
        label=label,
        base_amount=_q(amount),
        adjustments=_json_ready(adjustments),
        net_amount=_q(amount),
    )


def _project_type_name(value: Any) -> str:
    return str(getattr(value, "value", value))


def _positive_int(value: Any, fallback: int = 1) -> int:
    decimal_value = _to_decimal(value, Decimal(fallback))
    integer_value = int(decimal_value.to_integral_value(rounding=ROUND_HALF_UP))
    return max(fallback if fallback > 0 else 0, integer_value)


def _percent(value: Any, default: Decimal = ZERO) -> Decimal:
    return _q(_to_decimal(value, default) / HUNDRED)


def _to_decimal(value: Any, default: Decimal = ZERO) -> Decimal:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _q(value: Any) -> Decimal:
    return _to_decimal(value).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def _whole_dollar(value: Any) -> Decimal:
    return _to_decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _clamp(value: Decimal, lower: Decimal, upper: Decimal) -> Decimal:
    return max(lower, min(upper, value))


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_ready(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, Decimal):
        return format(_q(value), "f")
    if isinstance(value, UUID):
        return str(value)
    return value


def _add_months(base_date: date, months: int) -> date:
    month_number = base_date.month - 1 + months
    year = base_date.year + (month_number // 12)
    month = (month_number % 12) + 1
    day = min(base_date.day, 28)
    return date(year, month, day)


__all__ = ["compute_cash_flows"]
