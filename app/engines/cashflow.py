from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes as sa_attributes, selectinload

from app.models.cashflow import (
    CashFlow,
    CashFlowLineItem,
    LineItemCategory,
    OperationalOutputs,
    PeriodType,
)
from app.models.capital import CapitalModule
from app.models.deal import IncomeStream, OperatingExpenseLine, OperationalInputs, Scenario, UseLine
from app.models.milestone import Milestone, MilestoneType
from app.models.project import Project
from app.models.manifest import WorkflowRunManifest

try:
    import pyxirr
except ImportError:  # pragma: no cover - dependency is expected but keep runtime safe
    pyxirr = None


MONEY_PLACES = Decimal("0.000001")
ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")
PLACEHOLDER_DSCR = Decimal("1.250000")


@dataclass(frozen=True)
class PhaseSpec:
    period_type: PeriodType
    months: int


async def compute_cash_flows(
    deal_model_id: UUID | str, session: AsyncSession
) -> dict[str, Any]:
    """Compute and persist operational cash flows for a deal model.

    The function is idempotent for a given `deal_model_id`: it deletes prior
    generated `CashFlow`, `CashFlowLineItem`, and `OperationalOutputs` rows,
    then re-computes the full monthly operating lifecycle using `Decimal`
    arithmetic and placeholder leverage metrics for Stage 1A.
    """

    deal_uuid = UUID(str(deal_model_id))
    # Expire all cached ORM objects so _load_deal_model always reads fresh data.
    # The compute endpoint pre-loads Project in the same session; without expire_all()
    # the selectinload in _load_deal_model returns the cached collection and misses
    # any use_lines / expense_lines written earlier in the same request cycle.
    session.expire_all()
    deal_model = await _load_deal_model(session, deal_uuid)
    if deal_model is None:
        raise ValueError(f"Deal {deal_uuid} was not found")

    default_project = next(
        (p for p in sorted(deal_model.projects, key=lambda p: p.created_at)), None
    )
    if default_project is None:
        raise ValueError(f"Deal {deal_uuid} has no Project")
    if default_project.operational_inputs is None:
        raise ValueError(f"Deal {deal_uuid} is missing OperationalInputs")

    inputs = default_project.operational_inputs
    streams = sorted(default_project.income_streams, key=lambda stream: stream.label.lower())
    expense_lines = sorted(default_project.expense_lines, key=lambda line: line.label.lower())
    use_lines = list(default_project.use_lines)

    capital_modules = list((await session.execute(
        select(CapitalModule).where(CapitalModule.scenario_id == deal_uuid)
    )).scalars())

    # Build milestone_dates from ORM Milestone records, overlaying any stored in inputs
    orm_milestones = list((await session.execute(
        select(Milestone).where(Milestone.project_id == default_project.id)
    )).scalars())
    milestone_map = {m.id: m for m in orm_milestones}
    milestone_dates = _milestone_dates_from_orm(orm_milestones, milestone_map)
    # Stored inputs.milestone_dates overrides ORM-derived dates (manual overrides)
    if isinstance(inputs.milestone_dates, dict):
        milestone_dates.update(inputs.milestone_dates)
    has_lease_up_milestone = any(
        str(m.milestone_type) in ("operation_lease_up", MilestoneType.operation_lease_up)
        for m in orm_milestones
    )
    has_pre_development_milestone = any(
        str(m.milestone_type) in ("pre_development", MilestoneType.pre_development)
        for m in orm_milestones
    )

    # Build phase plan first so auto-sizing knows construction duration for IO budgeting
    phases = _build_phase_plan(
        _project_type_name(deal_model.project_type),
        inputs,
        milestone_dates=milestone_dates,
        has_lease_up_milestone=has_lease_up_milestone,
        has_pre_development_milestone=has_pre_development_milestone,
    )

    # Look up previously computed NOI so auto-sizing uses the accurate value.
    # The estimate from _estimate_stabilized_noi_monthly misses escalation carry-in
    # and capex reserve, causing the DSCR cap to fire at the wrong level.
    # We fetch this BEFORE _purge_existing_outputs so the row still exists.
    prev_outputs = (await session.execute(
        select(OperationalOutputs).where(OperationalOutputs.scenario_id == deal_uuid)
    )).scalar_one_or_none()
    prev_noi_stabilized = _to_decimal(prev_outputs.noi_stabilized) if prev_outputs else None

    income_mode: str = (deal_model.income_mode or "revenue_opex")

    # Pre-size any auto_size=True debt modules before computing debt service
    await _auto_size_debt_modules(
        capital_modules, inputs, streams, expense_lines, use_lines, phases, session,
        prev_noi_stabilized=prev_noi_stabilized,
        income_mode=income_mode,
    )

    # Reload module.source from DB after auto-sizing: SQLAlchemy's bulk UPDATE
    # (sa_update) may expire JSON columns on in-session ORM objects, making stale
    # reads possible before the next flush. A targeted refresh guarantees we see
    # the auto-sized amounts when summing total_sources below.
    for cm in capital_modules:
        await session.refresh(cm, attribute_names=["source"])

    construction_debt_monthly = _sum_debt_service(capital_modules, is_construction=True)
    operation_debt_monthly = _sum_debt_service(capital_modules, is_construction=False)

    # Sum all capital sources with a fixed amount — injected as period-0 inflow so
    # Cash Balance starts positive and draws down through construction.
    # pct_of_total_cost sources are skipped here (total_cost unknown pre-loop).
    total_sources = ZERO
    for cm in capital_modules:
        src = cm.source or {}
        amt = src.get("amount")
        if amt:
            total_sources += Decimal(str(amt))

    await _purge_existing_outputs(session, deal_uuid)
    cash_flow_rows: list[CashFlow] = []
    line_item_rows: list[CashFlowLineItem] = []
    net_cash_flow_series: list[Decimal] = []

    # Pre-seed cumulative with total sources so Cash Balance starts positive
    cumulative_cash_flow = total_sources
    stabilized_noi_monthly: Decimal | None = None
    period = 0
    _operating_reserve_seeded = False

    # Resolve operating reserve amount once — used to reset capital balance at
    # start of first operational phase so the invariant holds:
    #   Capital Balance[first stab month] = reserve + min(0, NCF)
    _op_reserve_amount = next(
        (_to_decimal(ul.amount) for ul in use_lines
         if getattr(ul, "label", "") == "Operating Reserve"),
        ZERO,
    )

    for phase in phases:
        for month_index in range(phase.months):
            period_result = _compute_period(
                deal_model_id=deal_uuid,
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
                income_mode=income_mode,
            )

            if phase.period_type == PeriodType.stabilized and stabilized_noi_monthly is None:
                stabilized_noi_monthly = period_result["noi"]

            # Cumulative cash balance:
            #   Pre-stabilized (construction, lease-up) + exit: accumulate NCF fully.
            #   First stabilized period: reset to the operating reserve.  The debt is
            #     sized so that cash flows through lease-up land exactly at the reserve
            #     amount when stabilization begins.
            #   Post-seed (stabilized): positive NCF is distributable profit — do NOT
            #     add to balance.  Negative NCF drains the reserve — DO subtract.
            _is_stabilized = phase.period_type == PeriodType.stabilized
            _ncf = period_result["net_cash_flow"]
            if _is_stabilized and not _operating_reserve_seeded:
                cumulative_cash_flow = _op_reserve_amount
                _operating_reserve_seeded = True
            elif _operating_reserve_seeded:
                # Post-seed: only drain on negative NCF
                if _ncf < 0:
                    cumulative_cash_flow += _ncf
            else:
                # Pre-seed (acquisition, construction, lease-up): accumulate all NCF
                cumulative_cash_flow += _ncf
            cash_flow_rows.append(
                CashFlow(
                    scenario_id=deal_uuid,
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

    total_project_cost = _calculate_total_project_cost(line_item_rows)
    # equity_required is set to 0 here; the waterfall engine overwrites it with
    # the actual sum of equity cash contributions after running its capital-call
    # allocation. Using peak-negative-NCF here conflates debt + equity.
    equity_required = ZERO
    total_timeline_months = len(cash_flow_rows)

    if stabilized_noi_monthly is None and cash_flow_rows:
        stabilized_noi_monthly = _to_decimal(cash_flow_rows[-1].noi)
    noi_stabilized = _q((stabilized_noi_monthly or ZERO) * Decimal("12"))

    cap_rate_on_cost_pct = (
        _q((noi_stabilized / total_project_cost) * HUNDRED)
        if total_project_cost > ZERO
        else ZERO
    )

    # DSCR = Stabilized NOI / Annual Operation Debt Service
    annual_operation_debt_service = operation_debt_monthly * Decimal("12")
    dscr = (
        _q(noi_stabilized / annual_operation_debt_service)
        if annual_operation_debt_service > ZERO
        else ZERO
    )

    project_irr_unlevered = _compute_xirr(net_cash_flow_series)
    project_irr_levered = project_irr_unlevered

    outputs = OperationalOutputs(
        scenario_id=deal_uuid,
        total_project_cost=_q(total_project_cost),
        equity_required=_q(equity_required),
        total_timeline_months=total_timeline_months,
        noi_stabilized=noi_stabilized,
        cap_rate_on_cost_pct=cap_rate_on_cost_pct,
        dscr=dscr,
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
        "cap_rate_on_cost_pct": cap_rate_on_cost_pct,
        "project_irr_unlevered": project_irr_unlevered,
        "project_irr_levered": project_irr_levered,
        "dscr": dscr,
    }

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
                    "hold_period_years": inputs.hold_period_years,
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


async def _purge_existing_outputs(session: AsyncSession, deal_model_id: UUID) -> None:
    await session.execute(
        delete(CashFlowLineItem).where(CashFlowLineItem.scenario_id == deal_model_id)
    )
    await session.execute(delete(CashFlow).where(CashFlow.scenario_id == deal_model_id))
    await session.execute(
        delete(OperationalOutputs).where(OperationalOutputs.scenario_id == deal_model_id)
    )


_MILESTONE_TYPE_TO_PHASE_KEY: dict[str, str] = {
    "construction": "construction_start",
    "operation_lease_up": "lease_up_start",
    "operation_stabilized": "stabilized_start",
    "divestment": "exit_date",
    "close": "acquisition_start",
    "pre_development": "pre_construction_start",
}


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
) -> list[PhaseSpec]:
    phases: list[PhaseSpec] = [PhaseSpec(PeriodType.acquisition, 1)]

    if project_type in {
        "acquisition_major_reno",
        "acquisition_conversion",
        "new_construction",
    } and bool(inputs.hold_phase_enabled):
        hold_months = _positive_int(inputs.hold_months, fallback=0)
        if hold_months > 0:
            phases.append(PhaseSpec(PeriodType.hold, hold_months))

    if project_type == "acquisition_minor_reno":
        phases.append(
            PhaseSpec(
                PeriodType.minor_renovation,
                _positive_int(inputs.renovation_months, fallback=1),
            )
        )
    elif project_type == "acquisition_major_reno":
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
    elif project_type == "acquisition_conversion":
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


_CONSTRUCTION_PERIOD_TYPES = {
    PeriodType.acquisition, PeriodType.hold, PeriodType.pre_construction,
    PeriodType.construction, PeriodType.minor_renovation, PeriodType.major_renovation,
    PeriodType.conversion,
}

# Maps UseLinePhase string values to the PeriodType(s) where the outflow fires.
# "construction" covers all building-work phases so it fires regardless of project type
# (acquisition_minor_reno uses minor_renovation; acquisition_major_reno uses major_renovation;
#  new_construction uses construction). "pre_construction" falls back to acquisition.
_USE_LINE_PHASE_MAP: dict[str, set[PeriodType]] = {
    "acquisition":     {PeriodType.acquisition},
    "pre_construction":{PeriodType.pre_construction},
    "construction":    {PeriodType.construction, PeriodType.major_renovation, PeriodType.minor_renovation, PeriodType.conversion},
    "renovation":      {PeriodType.minor_renovation, PeriodType.major_renovation},
    "conversion":      {PeriodType.conversion},
    "operation":       {PeriodType.lease_up, PeriodType.stabilized},
    "exit":            {PeriodType.exit},
    "other":           {PeriodType.acquisition},
}

_DEBT_FUNDER_TYPES = {
    "senior_debt", "mezzanine_debt", "bridge", "soft_loan",
    "construction_loan", "bond", "permanent_debt",
}


def _carry_type_for_phase(carry: dict, is_construction: bool) -> str:
    """Extract carry_type from either flat {carry_type:...} or phased {phases:[...]} format."""
    if "phases" in carry:
        target = "construction" if is_construction else "operation"
        for p in carry["phases"]:
            if p.get("name") == target:
                return p.get("carry_type", "none")
        return "none"
    return carry.get("carry_type", "none")


def _get_phase_carry(carry: dict, phase_name: str) -> dict | None:
    """Return the carry config dict for a named phase, or None if not phased / not found."""
    if "phases" not in carry:
        return None
    for p in carry["phases"]:
        if p.get("name") == phase_name:
            return p
    return None


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
        gross_revenue += _q(base * occupancy)

    operating_expenses = ZERO
    for line in expense_lines:
        if not _is_expense_line_active(line, stabilized):
            continue
        annual = _to_decimal(line.annual_amount)
        operating_expenses += _q(annual / Decimal("12"))

    return _q(gross_revenue - operating_expenses)


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
    auto_modules = [m for m in capital_modules if (m.source or {}).get("auto_size")]
    if not auto_modules:
        return

    debt_sizing_mode = inputs.debt_sizing_mode or "gap_fill"
    dscr_min = _to_decimal(inputs.dscr_minimum or PLACEHOLDER_DSCR)
    reserve_months = int(inputs.operation_reserve_months or 6)

    # Count months in construction-type phases so we can budget construction IO
    constr_months_total = sum(
        p.months for p in phases if p.period_type in _CONSTRUCTION_PERIOD_TYPES
    )

    # Count lease-up months — the perm debt must also cover these shortfalls so that
    # the cash balance at the first Stabilized period equals the Operating Reserve.
    # Income during lease-up is modelled as a linear ramp: 0 → full NOI, so the
    # average is 50 % of stabilized NOI.  This is used to reduce the gross shortfall.
    lease_up_months = sum(
        p.months for p in phases if p.period_type == PeriodType.lease_up
    )

    # System-managed balance-only labels — excluded from total_uses (handled in sizing directly)
    # Lease-Up Reserve is also excluded: it's derived from P after solving, not an input to it.
    # "Construction Interest Reserve" is the legacy label (renamed → Capitalized Construction Interest).
    # Keep it here so pre-rename DB rows don't get counted in the gap-fill total.
    _BALANCE_ONLY_LABELS = {
        "Operating Reserve",
        "Capitalized Construction Interest",
        "Construction Interest Reserve",          # legacy label — aliased for backward compat
        "Capitalized Pre-Development Interest",   # Phase B: per-bridge IO use lines
        "Capitalized Acquisition Interest",       # Phase B: per-bridge IO use lines
        "Lease-Up Reserve",
    }

    # Sum all non-exit use_lines as total project cost proxy
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
        # NOI mode: use the user-entered stabilized NOI directly
        _noi_input = _to_decimal(inputs.noi_stabilized_input) if inputs.noi_stabilized_input else ZERO
        noi_annual = _noi_input
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
        if "stabilized" in active:
            opex_monthly_pre += _q(_to_decimal(line.annual_amount) / Decimal("12"))

    # Phase B: new multi-debt path when debt_types is explicitly set on inputs.
    # Bridge loans (pre_development_loan, acquisition_loan, construction_loan, bridge)
    # are sized to their phase costs and marked is_bridge=True so they're excluded from
    # the Sources display total.  Permanent debt still gap-fills to TPC.
    # Legacy 3-path is preserved when debt_types is None (backward compat).
    _bridge_module: object = None
    _perm_mod: object = None
    _bridge_io: dict = {}   # {funder_type: capitalized_io_amount} for new-path use lines

    debt_types_list: list = getattr(inputs, "debt_types", None) or []

    if debt_types_list:
        # ── New multi-debt path ─────────────────────────────────────────────
        _BRIDGE_FUNDER_TYPES = {"pre_development_loan", "acquisition_loan", "construction_loan", "bridge"}
        _PRE_DEV_USE_PHASES  = {"pre_construction"}
        _ACQ_USE_PHASES      = {"acquisition", "other"}
        _CONSTR_USE_PHASES   = {"construction", "renovation", "conversion"}

        def _phase_cost_sum(phase_set: set) -> Decimal:
            return sum(
                (_to_decimal(ul.amount)
                 for ul in use_lines
                 if str(getattr(ul.phase, "value", ul.phase) or "") in phase_set
                 and getattr(ul, "label", "") not in _BALANCE_ONLY_LABELS),
                ZERO,
            )

        pre_dev_costs  = _phase_cost_sum(_PRE_DEV_USE_PHASES)
        acq_costs      = _phase_cost_sum(_ACQ_USE_PHASES)
        constr_costs   = _phase_cost_sum(_CONSTR_USE_PHASES)

        _pre_dev_months = sum(p.months for p in phases if p.period_type == PeriodType.pre_construction)
        _acq_months     = sum(p.months for p in phases if p.period_type == PeriodType.acquisition)

        for _m in list(auto_modules):
            _ft = str(getattr(_m, "funder_type", "") or "")
            if _ft not in _BRIDGE_FUNDER_TYPES:
                continue
            _src    = dict(_m.source or {})
            _carry  = _m.carry or {}
            _rate   = _src.get("interest_rate_pct") or _carry.get("io_rate_pct")
            _cc     = _get_phase_carry(_carry, "construction")
            _cr     = (_cc or {}).get("io_rate_pct") if _cc else None
            if not _cr:
                _cr = _rate

            if _ft == "pre_development_loan":
                _r = Decimal(str(_rate or 0))
                _io_f = (_r / HUNDRED / Decimal("12") * Decimal(_pre_dev_months)) if (_r > ZERO and _pre_dev_months > 0) else ZERO
                _div = ONE - _io_f
                _principal = _q(pre_dev_costs / _div) if (_div > ZERO and pre_dev_costs > ZERO) else pre_dev_costs
                if _principal > ZERO and _r > ZERO and _pre_dev_months > 0:
                    _bridge_io["pre_development_loan"] = _q(_principal * _r / HUNDRED / Decimal("12") * Decimal(_pre_dev_months))

            elif _ft == "acquisition_loan":
                _dt_terms = (inputs.debt_terms or {}).get("acquisition_loan", {})
                _ltv = Decimal(str(_dt_terms.get("ltv_pct") or _src.get("ltv_pct") or 70))
                _principal = _q(acq_costs * _ltv / HUNDRED)
                _r = Decimal(str(_rate or 0))
                if _principal > ZERO and _r > ZERO and _acq_months > 0:
                    _bridge_io["acquisition_loan"] = _q(_principal * _r / HUNDRED / Decimal("12") * Decimal(_acq_months))

            elif _ft == "construction_loan":
                _r = Decimal(str(_cr or 0))
                _io_f = (_r / HUNDRED / Decimal("12") * Decimal(constr_months_total)) if (_r > ZERO and constr_months_total > 0) else ZERO
                _div = ONE - _io_f
                _principal = _q(constr_costs / _div) if (_div > ZERO and constr_costs > ZERO) else constr_costs
                if _principal > ZERO and _r > ZERO and constr_months_total > 0:
                    _bridge_io["construction_loan"] = _q(_principal * _r / HUNDRED / Decimal("12") * Decimal(constr_months_total))

            elif _ft == "bridge":
                _existing_amt = _src.get("amount")
                _principal = Decimal(str(_existing_amt)) if _existing_amt else ZERO
            else:
                continue

            if _principal < ZERO:
                _principal = ZERO
            _src["amount"] = str(_q(_principal))
            _src["is_bridge"] = True
            await session.execute(
                sa_update(CapitalModule).where(CapitalModule.id == _m.id).values(source=_src)
            )
            _m.source = _src
            auto_modules = [x for x in auto_modules if x is not _m]  # remove from gap-fill loop

    else:
        # ── Legacy 3-path: construction_and_perm bridge detection ───────────
        # For Construction + Permanent (Separate), the construction loan is a bridge
        # that gets taken out by the permanent loan.  Only the perm leg should
        # gap-fill total uses; the construction loan principal mirrors the perm amount.
        debt_structure = getattr(inputs, "debt_structure", None) or "perm_only"
        if debt_structure == "construction_and_perm":
            _perm_mod = next(
                (m for m in auto_modules if str(getattr(m, "funder_type", "")) == "permanent_debt"),
                None,
            )
            _constr_mod = next(
                (m for m in auto_modules if str(getattr(m, "funder_type", "")) == "construction_loan"),
                None,
            )
            if _perm_mod and _constr_mod:
                _bridge_module = _constr_mod
                # Exclude the bridge from the gap-fill loop so only perm sizes to TPC.
                auto_modules = [m for m in auto_modules if m is not _constr_mod]

    # When bridge loans carry their own IO (new multi-debt path), the gap-fill module
    # (e.g. permanent debt) must pay off those bridge loans at retirement, including
    # accrued IO.  Add captured bridge IO to total_uses so perm sizes to cover it.
    # This is safe: bridge IO amounts are already finalized above before the gap-fill loop.
    if debt_types_list and _bridge_io:
        for _bio_ft, _bio_amt in _bridge_io.items():
            if _bio_amt > ZERO:
                total_uses += _bio_amt

    # Lease-Up Reserve = perm debt service during lease-up minus ~1/3 stabilized NOI (phantom CF avg).
    # Computed inside the loop when the gap-fill DS path is active; written as a use
    # line after the loop so S&U always balances.
    _lease_up_carry: Decimal = ZERO

    for module in auto_modules:
        src = dict(module.source or {})
        carry = module.carry or {}
        # Rate may be in source["interest_rate_pct"] or flat carry["io_rate_pct"]
        rate_pct = src.get("interest_rate_pct") or carry.get("io_rate_pct")

        # Get amort_term_years from carry (phased) or source
        op_carry = _get_phase_carry(carry, "operation")
        amort_years = int(
            (op_carry or {}).get("amort_term_years")
            or src.get("amort_term_years")
            or 30
        )

        # Construction IO rate: use construction-phase carry rate if specified, else fall back to source rate
        constr_carry = _get_phase_carry(carry, "construction")
        constr_rate_pct = (constr_carry or {}).get("io_rate_pct") if constr_carry else None
        if not constr_rate_pct:
            constr_rate_pct = rate_pct
        # IO factor: fraction of principal consumed by construction IO over all constr phases
        # Solved algebraically: P = base / (1 - constr_io_factor) so that
        # cash at ops start = P - base = reserve (net of construction IO charges)
        # In new multi-debt deals the construction loan handles its own IO, so perm's
        # constr_io_factor is forced to zero to avoid double-counting.
        constr_io_factor = ZERO
        if not debt_types_list and constr_rate_pct and constr_months_total > 0:
            constr_io_factor = (
                Decimal(str(constr_rate_pct)) / HUNDRED / Decimal("12")
                * Decimal(str(constr_months_total))
            )

        fixed = _fixed_sources(module)
        divisor = ONE - constr_io_factor

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

            # Try closed-form DS-based reserve (reserve sized at stabilization)
            ds_divisor = divisor - pmt_factor * Decimal(reserve_months + lease_up_months)
            if ds_divisor > ZERO:
                principal = _q(effective_uses / ds_divisor)
                # Capture lease-up carry = net debt service shortfall during lease-up.
                # This becomes a Use line so Sources = Uses after compute.
                if lease_up_months > 0:
                    _lu = _q(principal * pmt_factor * Decimal(lease_up_months) - lease_up_income_offset)
                    _lease_up_carry = _lu if _lu > ZERO else ZERO
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
            # Check whether gap-fill principal keeps DSCR ≥ min.
            # If yes: use gap-fill (Sources = Uses, DSCR satisfied).
            # If no: cap at DSCR max (real funding gap, show deficit).
            if rate_pct and principal > ZERO and noi_annual > ZERO and dscr_min > ZERO:
                gf_ds_monthly = _monthly_pmt(principal, rate_pct, amort_years)
                gf_dscr = noi_annual / (gf_ds_monthly * Decimal("12")) if gf_ds_monthly > ZERO else Decimal("999")
                if gf_dscr < dscr_min:
                    target_monthly_ds = _q(noi_annual / dscr_min / Decimal("12"))
                    principal = _pv_from_pmt(target_monthly_ds, rate_pct, amort_years)

            if principal < ZERO:
                principal = ZERO
            src["amount"] = str(_q(principal))
            await session.execute(
                sa_update(CapitalModule).where(CapitalModule.id == module.id).values(source=src)
            )
            module.source = src  # keep in-memory view consistent
            continue

        # gap_fill — principal already computed by _solve_principal_with_reserve above
        if principal < ZERO:
            principal = ZERO
        src["amount"] = str(_q(principal))
        await session.execute(
            sa_update(CapitalModule).where(CapitalModule.id == module.id).values(source=src)
        )
        module.source = src  # keep in-memory view consistent

    # For construction_and_perm: mirror perm amount to the bridge construction loan.
    # The bridge is marked is_bridge=True so the Sources & Uses display excludes it
    # from the debt total (avoiding double-counting vs the perm leg).
    # Also store construction_retirement on the perm source so the UI can break down
    # how perm proceeds are allocated (retirement vs net new debt).
    if _bridge_module is not None and _perm_mod is not None:
        perm_src = dict(_perm_mod.source or {})
        perm_amount = perm_src.get("amount", "0")
        bridge_src = dict(_bridge_module.source or {})
        bridge_src["amount"] = perm_amount
        bridge_src["is_bridge"] = True
        await session.execute(
            sa_update(CapitalModule)
            .where(CapitalModule.id == _bridge_module.id)
            .values(source=bridge_src)
        )
        _bridge_module.source = bridge_src
        # Tag perm module with the retirement amount so UI renders the split breakdown.
        perm_src["construction_retirement"] = perm_amount
        await session.execute(
            sa_update(CapitalModule)
            .where(CapitalModule.id == _perm_mod.id)
            .values(source=perm_src)
        )
        _perm_mod.source = perm_src

    # Compute actual reserve (max of OpEx vs actual debt service, × reserve months)
    # opex_monthly_pre already computed above; re-use it here.
    opex_monthly = opex_monthly_pre
    # Re-sum debt service now that amounts are set
    ds_monthly = ZERO
    for m in auto_modules:
        src2 = m.source or {}
        carry2 = m.carry or {}
        amt2 = src2.get("amount")
        if amt2:
            p2 = Decimal(str(amt2))
            op_carry2 = _get_phase_carry(carry2, "operation")
            ct2 = _carry_type_for_phase(carry2, is_construction=False)
            rate2 = src2.get("interest_rate_pct")
            if ct2 == "io_only":
                phase_rate2 = (op_carry2 or {}).get("io_rate_pct") if op_carry2 else None
                ds_monthly += _monthly_io(p2, phase_rate2 or rate2)
            elif ct2 == "pi":
                ay2 = int((op_carry2 or {}).get("amort_term_years") or src2.get("amort_term_years") or 30)
                phase_rate2 = (op_carry2 or {}).get("io_rate_pct") if op_carry2 else None
                ds_monthly += _monthly_pmt(p2, phase_rate2 or rate2, ay2)
    # In NOI mode there is no separate OpEx figure — size reserve on DS only
    actual_reserve = _q(
        ds_monthly * Decimal(reserve_months)
        if income_mode == "noi"
        else max(opex_monthly, ds_monthly) * Decimal(reserve_months)
    )

    # Compute actual construction IO across auto-sized modules.
    # New multi-debt path: construction loan IO is in _bridge_io["construction_loan"];
    # perm does not pay IO during construction, so auto_modules loop would produce ZERO.
    # Legacy path: iterate auto_modules (may include a phased perm with constr IO carry).
    total_constr_io = ZERO
    if debt_types_list:
        total_constr_io = _bridge_io.get("construction_loan", ZERO)
    elif constr_months_total > 0:
        for m in auto_modules:
            src3 = m.source or {}
            carry3 = m.carry or {}
            amt3 = src3.get("amount")
            if amt3:
                p3 = Decimal(str(amt3))
                constr_carry3 = _get_phase_carry(carry3, "construction")
                cr3 = (constr_carry3 or {}).get("io_rate_pct") if constr_carry3 else None
                if not cr3:
                    cr3 = src3.get("interest_rate_pct")
                if cr3:
                    total_constr_io += _q(
                        p3 * Decimal(str(cr3)) / HUNDRED / Decimal("12")
                        * Decimal(str(constr_months_total))
                    )

    # Get project_id from the first use_line (all belong to the same project)
    project_id = getattr(use_lines[0], "project_id", None) if use_lines else None

    # Update or create Operating Reserve use line
    if income_mode == "noi":
        _reserve_basis = "Debt Service"
        _reserve_amount_basis = ds_monthly
    else:
        _reserve_basis = "Debt Service" if ds_monthly >= opex_monthly else "OpEx"
        _reserve_amount_basis = max(opex_monthly, ds_monthly)
    _reserve_notes = (
        f"Auto-computed ({_reserve_basis} basis): "
        f"${_reserve_amount_basis:,.0f}/mo × {reserve_months} months"
    )
    op_reserve_found = False
    for ul in use_lines:
        if getattr(ul, "label", "") == "Operating Reserve":
            ul.amount = actual_reserve
            ul.notes = _reserve_notes
            session.add(ul)
            op_reserve_found = True
            break
    if not op_reserve_found and project_id and actual_reserve > ZERO:
        new_op = UseLine(
            project_id=project_id,
            label="Operating Reserve",
            phase="operation",
            amount=actual_reserve,
            timing_type="first_day",
            notes=_reserve_notes,
        )
        session.add(new_op)
        use_lines.append(new_op)

    # Update or create Capitalized Construction Interest use line (balance-only: not a cash outflow).
    # Collect ALL rows matching either the current or the legacy label, then keep exactly one.
    _CI_LABELS = {"Capitalized Construction Interest", "Construction Interest Reserve"}
    _ci_rows = [ul for ul in use_lines if getattr(ul, "label", "") in _CI_LABELS]
    if _ci_rows:
        # Keep the first, delete every duplicate
        _ci_keep = _ci_rows[0]
        _ci_keep.label = "Capitalized Construction Interest"
        _ci_keep.amount = total_constr_io
        session.add(_ci_keep)
        for _ci_dup in _ci_rows[1:]:
            await session.delete(_ci_dup)
            use_lines.remove(_ci_dup)
    elif project_id and total_constr_io > ZERO:
        new_ul = UseLine(
            project_id=project_id,
            label="Capitalized Construction Interest",
            phase="construction",
            amount=total_constr_io,
            timing_type="first_day",
            notes="Auto-computed: IO on debt principal during construction phases.",
        )
        session.add(new_ul)
        use_lines.append(new_ul)

    # Update or create Lease-Up Reserve use line (balance-only: perm DS shortfall during lease-up)
    lu_reserve_found = False
    for ul in use_lines:
        if getattr(ul, "label", "") == "Lease-Up Reserve":
            if _lease_up_carry > ZERO:
                ul.amount = _lease_up_carry
                ul.notes = f"Auto-computed: perm debt service during {lease_up_months}-month lease-up net of ~1/3 stabilized NOI (phantom CF avg, 60/40 split, opex 50→100%)"
                session.add(ul)
            else:
                await session.delete(ul)
                use_lines.remove(ul)
            lu_reserve_found = True
            break
    if not lu_reserve_found and project_id and _lease_up_carry > ZERO:
        new_lu = UseLine(
            project_id=project_id,
            label="Lease-Up Reserve",
            phase="operation_lease_up",
            amount=_lease_up_carry,
            timing_type="first_day",
            notes=f"Auto-computed: perm debt service during {lease_up_months}-month lease-up net of ~1/3 stabilized NOI (phantom CF avg, 60/40 split, opex 50→100%)",
        )
        session.add(new_lu)
        use_lines.append(new_lu)

    # Phase B: write Capitalized Pre-Development Interest and Capitalized Acquisition Interest
    # use lines for new multi-debt deals (construction_loan IO uses the existing CI block above).
    if debt_types_list and project_id:
        for _bft, _blabel in [
            ("pre_development_loan", "Capitalized Pre-Development Interest"),
            ("acquisition_loan",     "Capitalized Acquisition Interest"),
        ]:
            _bio_amt = _bridge_io.get(_bft, ZERO)
            _existing_bio = next((ul for ul in use_lines if getattr(ul, "label", "") == _blabel), None)
            if _existing_bio:
                if _bio_amt > ZERO:
                    _existing_bio.amount = _bio_amt
                    session.add(_existing_bio)
                else:
                    await session.delete(_existing_bio)
                    use_lines.remove(_existing_bio)
            elif _bio_amt > ZERO:
                _new_io_ul = UseLine(
                    project_id=project_id,
                    label=_blabel,
                    phase="construction",
                    amount=_bio_amt,
                    timing_type="first_day",
                    notes=f"Auto-computed: IO on {_bft} during active phase.",
                )
                session.add(_new_io_ul)
                use_lines.append(_new_io_ul)

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


def _sum_debt_service(modules: list, is_construction: bool) -> Decimal:
    """Compute total monthly debt service for construction or operation phase."""
    total = ZERO
    for m in modules:
        ft = str(m.funder_type).replace("FunderType.", "")
        if ft not in _DEBT_FUNDER_TYPES:
            continue
        carry = m.carry or {}
        ct = _carry_type_for_phase(carry, is_construction)
        if ct not in ("io_only", "pi"):
            continue
        source = m.source or {}
        amount = source.get("amount")
        if not amount:
            continue
        principal = Decimal(str(amount))
        # Rate may be in source["interest_rate_pct"] or flat carry["io_rate_pct"]
        rate_pct = source.get("interest_rate_pct") or carry.get("io_rate_pct")
        if ct == "io_only":
            # Use phase-specific IO rate if available
            carry_phase = _get_phase_carry(carry, "construction" if is_construction else "operation")
            phase_rate = carry_phase.get("io_rate_pct") if carry_phase else None
            total += _monthly_io(principal, phase_rate or rate_pct)
        elif ct == "pi":
            # amort_term_years may be in the carry phase (phased carry) or source (flat carry)
            carry_phase = _get_phase_carry(carry, "operation")
            amort_years = int(
                (carry_phase or {}).get("amort_term_years")
                or source.get("amort_term_years")
                or 30
            )
            phase_rate = (carry_phase or {}).get("io_rate_pct") if carry_phase else None
            total += _monthly_pmt(principal, phase_rate or rate_pct, amort_years)
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
    income_mode: str = "revenue_opex",
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
    )
    capital_inflow = ZERO
    capital_outflow = ZERO
    line_items: list[CashFlowLineItem] = []

    _is_operational_phase = phase.period_type in {PeriodType.lease_up, PeriodType.stabilized}

    if income_mode == "noi" and _is_operational_phase:
        # NOI mode: skip stream/expense loops. Compute monthly NOI from the stabilized input
        # with compound annual escalation: noi_monthly = (noi_annual/12) × (1+rate)^(period/12)
        _noi_annual = _to_decimal(inputs.noi_stabilized_input) if inputs.noi_stabilized_input else ZERO
        _esc_rate = _to_decimal(inputs.noi_escalation_rate_pct) if inputs.noi_escalation_rate_pct else Decimal("3")
        _esc_factor = _growth_factor(_esc_rate, period)
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
                escalated_amount = _q(base_amount * escalation_factor)
                occupancy_pct = _stream_occupancy_pct(stream, phase, month_index, inputs)
                net_income = _q(escalated_amount * occupancy_pct)
                vacancy = _q(escalated_amount - net_income)
            else:
                escalated_amount = ZERO
                occupancy_pct = ZERO
                net_income = ZERO
                vacancy = ZERO

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
                    initial_occ = _percent(inputs.initial_occupancy_pct, default=Decimal("50"))
                    stabilized_occ = Decimal("0.95")  # default stabilized occupancy
                    if phase.months <= 1:
                        ramp_occ = stabilized_occ
                    else:
                        step = (stabilized_occ - initial_occ) / Decimal(phase.months - 1)
                        ramp_occ = _clamp(initial_occ + step * Decimal(month_index), ZERO, stabilized_occ)
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
    _BALANCE_ONLY = {
        "Operating Reserve",
        "Capitalized Construction Interest",
        "Construction Interest Reserve",
        "Capitalized Pre-Development Interest",
        "Capitalized Acquisition Interest",
    }
    if use_lines:
        for ul in use_lines:
            if getattr(ul, "label", "") in _BALANCE_ONLY:
                continue
            ul_phase_str = str(ul.phase).replace("UseLinePhase.", "")
            period_types = _USE_LINE_PHASE_MAP.get(ul_phase_str, set())
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
    net_cash_flow = _q(noi - debt_service - capital_outflow + capital_inflow)

    return {
        "gross_revenue": _q(gross_revenue),
        "vacancy_loss": _q(vacancy_loss),
        "effective_gross_income": _q(effective_gross_income),
        "operating_expenses": _q(operating_expenses),
        "capex_reserve": _q(capex_reserve),
        "noi": noi,
        "debt_service": debt_service,
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
            sale_proceeds = _q(
                (stabilized_noi_monthly * Decimal("12")) / _percent(inputs.exit_cap_rate_pct)
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

    return items


def _is_stream_active(stream: IncomeStream, period_type: PeriodType) -> bool:
    active_in_phases = {str(phase) for phase in (stream.active_in_phases or [])}
    phase_name = period_type.value
    if phase_name in active_in_phases:
        return True
    return phase_name == PeriodType.exit.value and PeriodType.stabilized.value in active_in_phases


def _is_expense_line_active(expense_line: OperatingExpenseLine, period_type: PeriodType) -> bool:
    active_in_phases = {str(phase) for phase in (expense_line.active_in_phases or [])}
    phase_name = period_type.value
    if phase_name in active_in_phases:
        return True
    return phase_name == PeriodType.exit.value and PeriodType.stabilized.value in active_in_phases


def _stream_base_amount(stream: IncomeStream) -> Decimal:
    if stream.amount_fixed_monthly is not None:
        return _to_decimal(stream.amount_fixed_monthly)
    # When unit_count is explicitly NULL (not set), treat as 1 unit so per-unit amounts
    # aren't silently zeroed out.  Explicit 0 is respected (disables the stream).
    units = _to_decimal(stream.unit_count) if stream.unit_count is not None else ONE
    return _q(_to_decimal(stream.amount_per_unit_monthly) * units)


def _stream_occupancy_pct(
    stream: IncomeStream,
    phase: PhaseSpec,
    month_index: int,
    inputs: OperationalInputs,
) -> Decimal:
    stabilized_occupancy = _percent(stream.stabilized_occupancy_pct, default=Decimal("95"))

    if phase.period_type == PeriodType.hold:
        return _q(stabilized_occupancy * (ONE - _percent(inputs.hold_vacancy_rate_pct)))

    if phase.period_type in {
        PeriodType.minor_renovation,
        PeriodType.major_renovation,
        PeriodType.conversion,
    }:
        return _q(stabilized_occupancy * (ONE - _percent(inputs.income_reduction_pct_during_reno)))

    if phase.period_type == PeriodType.lease_up:
        initial_occupancy = _percent(inputs.initial_occupancy_pct, default=Decimal("50"))
        if phase.months <= 1:
            return stabilized_occupancy
        step = (stabilized_occupancy - initial_occupancy) / Decimal(phase.months - 1)
        return _q(_clamp(initial_occupancy + (step * Decimal(month_index)), ZERO, stabilized_occupancy))

    if phase.period_type in {PeriodType.stabilized, PeriodType.exit}:
        return stabilized_occupancy

    return ZERO


def _operating_unit_count(inputs: OperationalInputs, period_type: PeriodType) -> Decimal:
    if period_type in {PeriodType.hold, PeriodType.minor_renovation, PeriodType.major_renovation}:
        return _to_decimal(inputs.unit_count_existing or inputs.unit_count_new)
    if period_type == PeriodType.conversion:
        return _to_decimal(inputs.unit_count_after_conversion or inputs.unit_count_new)
    if period_type in {PeriodType.lease_up, PeriodType.stabilized, PeriodType.exit}:
        return _to_decimal(inputs.unit_count_after_conversion or inputs.unit_count_new)
    return ZERO


def _phase_is_operational(period_type: PeriodType) -> bool:
    return period_type in {
        PeriodType.hold,
        PeriodType.minor_renovation,
        PeriodType.major_renovation,
        PeriodType.conversion,
        PeriodType.lease_up,
        PeriodType.stabilized,
        PeriodType.exit,
    }


def _monthly_expense(annual_amount: Any, growth_factor: Decimal) -> Decimal:
    return _q((_to_decimal(annual_amount) / Decimal("12")) * growth_factor)


def _allocate_evenly(amount: Any, months: int) -> Decimal:
    month_count = max(1, months)
    return _q(_to_decimal(amount) / Decimal(month_count))


def _growth_factor(rate_pct_annual: Any, period: int) -> Decimal:
    rate = _percent(rate_pct_annual)
    if rate <= ZERO or period <= 0:
        return ONE
    return _q((ONE + rate) ** (Decimal(period) / Decimal("12")))


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
    except Exception:
        return ZERO
    return _q(Decimal(str(result)) * HUNDRED)


def _expense_line_item(
    deal_model_id: UUID,
    period: int,
    category: LineItemCategory,
    label: str,
    amount: Decimal,
    adjustments: dict[str, Any],
) -> CashFlowLineItem:
    return CashFlowLineItem(
        scenario_id=deal_model_id,
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


def _manifest_unit_count(inputs: OperationalInputs) -> int:
    return int(
        _to_decimal(
            inputs.unit_count_after_conversion or inputs.unit_count_existing or inputs.unit_count_new or 0
        )
    )


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
