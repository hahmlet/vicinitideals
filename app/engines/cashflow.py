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
from app.models.capital import CapitalModule, CapitalModuleProject
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
# Max annual rent increase for LTL catchup — prevents unrealistic 20%+ jumps
LTL_CATCHUP_CAP_PCT = Decimal("10")


@dataclass(frozen=True)
class PhaseSpec:
    period_type: PeriodType
    months: int


async def compute_cash_flows(
    deal_model_id: UUID | str, session: AsyncSession
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

    projects = sorted(deal_model.projects, key=lambda p: p.created_at)
    if not projects:
        raise ValueError(f"Deal {deal_uuid} has no Project")

    # Per-project purge happens INSIDE _compute_project_cashflow, right after
    # prev_outputs is captured for DSCR convergence, so each iteration sees its
    # own prior NOI and wipes only its own rows (not a sibling's).
    last_summary: dict[str, Any] = {}
    for project in projects:
        last_summary = await _compute_project_cashflow(
            deal_model=deal_model,
            deal_uuid=deal_uuid,
            project=project,
            session=session,
        )
    return last_summary


async def _compute_project_cashflow(
    *,
    deal_model: Scenario,
    deal_uuid: UUID,
    project: Project,
    session: AsyncSession,
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

    # Now safe to wipe this project's prior rows — prev_outputs is captured.
    await _purge_project_outputs(session, deal_uuid, project.id)

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
        # Financing costs for the perm loan (flat from closing cost data)
        perm_financing_costs = ZERO
        perm_ft = str(getattr(cm, "funder_type", "") or "").replace("FunderType.", "")
        for cc in _DEFAULT_LOAN_COSTS.get(perm_ft, []):
            if "pct_of_principal" in cc:
                perm_financing_costs += _q(perm_amount * Decimal(str(cc["pct_of_principal"])) / HUNDRED)
            else:
                perm_financing_costs += Decimal(str(cc["flat"]))
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

    # Output purge happens once at the outer compute_cash_flows wrapper
    # before the per-project loop — not per-project here.
    cash_flow_rows: list[CashFlow] = []
    line_item_rows: list[CashFlowLineItem] = []
    net_cash_flow_series: list[Decimal] = []

    # Pre-seed cumulative with total sources so Cash Balance starts positive
    cumulative_cash_flow = total_sources
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
                income_mode=income_mode,
                first_stab_period=_first_stab_period,
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

            # ── Inject prepay penalties at exit ───────────��────────────────
            if phase.period_type == PeriodType.exit and month_index == 0:
                for _pp_cm in capital_modules:
                    _pp_src = _pp_cm.source or {}
                    _pp_pct = _to_decimal(_pp_src.get("prepay_penalty_pct"))
                    if _pp_pct <= ZERO or _pp_src.get("is_bridge"):
                        continue
                    _pp_amt = _to_decimal(_pp_src.get("amount"))
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

    total_project_cost = _calculate_total_project_cost(line_item_rows)
    # equity_required is set to 0 here; the waterfall engine overwrites it with
    # the actual sum of equity cash contributions after running its capital-call
    # allocation. Using peak-negative-NCF here conflates debt + equity.
    equity_required = ZERO
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

    # DSCR = Stabilized NOI / Annual Operation Debt Service
    annual_operation_debt_service = operation_debt_monthly * Decimal("12")
    dscr = (
        _q(noi_stabilized / annual_operation_debt_service)
        if annual_operation_debt_service > ZERO
        else ZERO
    )

    # Debt Yield = Stabilized NOI / Total Outstanding Debt Balance
    total_debt_balance = ZERO
    for cm in capital_modules:
        ft = str(cm.funder_type).replace("FunderType.", "")
        if ft not in _DEBT_FUNDER_TYPES:
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

    For multi-project scenarios, each project sees only the sources attached
    to it. A shared Source (junction rows for both P1 and P2) will appear
    in both projects' module lists — each iteration gets its own ORM
    instances because SQLAlchemy's identity map is session-scoped.

    Per-project ``amount`` / ``active_from`` / ``auto_size`` overlays from
    the junction are NOT applied here yet; migration 0048's backfill makes
    them identical to the CapitalModule's legacy fields for single-project.
    Phase 2c1 (deferred) will overlay them once the UI can write divergent
    per-project values.
    """
    result = await session.execute(
        select(CapitalModule)
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
    return list(result.scalars())


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


async def _purge_project_outputs(
    session: AsyncSession, deal_model_id: UUID, project_id: UUID
) -> None:
    """Purge a single project's output rows from the scenario.

    Also deletes legacy rows on this scenario where ``project_id IS NULL``
    — these exist only if migration 0050's backfill was skipped (never the
    case in practice, but the guard keeps the engine resilient).
    """
    for model in (CashFlowLineItem, CashFlow, OperationalOutputs):
        await session.execute(
            delete(model).where(
                model.scenario_id == deal_model_id,
                (model.project_id == project_id) | (model.project_id.is_(None)),
            )
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
        "value_add",
        "conversion",
        "new_construction",
    } and bool(inputs.hold_phase_enabled):
        hold_months = _positive_int(inputs.hold_months, fallback=0)
        if hold_months > 0:
            phases.append(PhaseSpec(PeriodType.hold, hold_months))

    if project_type == "acquisition":
        phases.append(
            PhaseSpec(
                PeriodType.minor_renovation,
                _positive_int(inputs.renovation_months, fallback=1),
            )
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


_CONSTRUCTION_PERIOD_TYPES = {
    PeriodType.acquisition, PeriodType.hold, PeriodType.pre_construction,
    PeriodType.construction, PeriodType.minor_renovation, PeriodType.major_renovation,
    PeriodType.conversion,
}

# Active-phase rank map used for Exit Vehicle detection (§2.10) and per-loan
# carry windowing.  A loan with active window [start_rank, end_rank) is active
# for phases whose rank falls in that half-open interval.
_APS_TO_RANK: dict[str, int] = {
    "acquisition": 0, "close": 0,
    "pre_construction": 2,
    "construction": 3,
    "lease_up": 4, "operation_lease_up": 4,
    "stabilized": 5, "operation_stabilized": 5,
    "exit": 6, "divestment": 6,
}


def _module_rank(module: object, side: str) -> int:
    """Rank of a module's active_phase_{start|end}.

    `start` missing → 0 (acquisition). `end` missing / "perpetuity" → 99.
    """
    raw = str(getattr(module, f"active_phase_{side}", "") or "")
    if side == "end":
        return _APS_TO_RANK.get(raw, 99)
    return _APS_TO_RANK.get(raw, 0)


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
      2. Else if end_rank >= 6 (exit/divestment): "sale".
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
    "operation":       {PeriodType.lease_up, PeriodType.stabilized},
    "exit":            {PeriodType.exit},
    "other":           {PeriodType.acquisition},
}

_DEBT_FUNDER_TYPES = {
    "senior_debt", "mezzanine_debt", "bridge", "soft_loan",
    "construction_loan", "bond", "permanent_debt",
    "acquisition_loan", "pre_development_loan", "owner_loan",
}

# Funder types for which Exit Vehicle applies — every funding line that has
# a real "ending" (matures, is refinanced, or is paid off at sale).  All
# other funder types (equity, grants, tax credits, owner_investment) are
# perpetuity-like from the engine's POV — single-draw, no vehicle UI.
_EXIT_VEHICLE_APPLIES = {
    "permanent_debt", "senior_debt", "mezzanine_debt", "bridge",
    "construction_loan", "acquisition_loan", "pre_development_loan",
    "soft_loan", "bond", "owner_loan",
}

# ── Loan closing cost defaults ────────────────────────────────────────────────
# Market-backed defaults (commloan.com, financelobby.com, aegisenvironmentalinc.com,
# lornellre.com, mrrate.com — April 2026):
#   Construction loan origination: 1.0% (banks 0.5–1%; private lenders 1–2%)
#   Perm origination: 0.5% (bank 0.25–1.0%; agency 0.5% typical)
#   Pre-dev / bridge origination: 1.5% (short-term bridge 1.5–3%)
#   Lender legal: $5,000 flat (small-medium CRE deals; CMBS goes higher)
#   ALTA survey: $3,500 ($2,500–$10,000 range; $3,500 representative)
#   Phase I ESA: $2,500 ($2,000–$5,000; $2,500 is median for standard commercial)
#   Appraisal: $3,500 ($3,000–$5,000+ for commercial)
#   Bond counsel legal: $15,000 (specialized; $10,000–$25,000 range)
#
# Phase assignment: closing costs fire at the loan's active_phase_start so they
# are excluded from phase-based bridge loan sizing (e.g. construction loan closing
# costs in "pre_construction" are not part of constr_costs).  The perm gap-fills
# to TPC which naturally covers them.
_DEFAULT_LOAN_COSTS: dict[str, list[dict]] = {
    "construction_loan": [
        {"label": "Origination Fee",       "pct_of_principal": Decimal("1.0")},
        {"label": "Lender Legal",          "flat": Decimal("5000")},
        {"label": "Title / Survey",        "flat": Decimal("3500")},
        {"label": "Environmental Phase I", "flat": Decimal("2500")},
    ],
    "permanent_debt": [
        {"label": "Origination Fee",       "pct_of_principal": Decimal("0.5")},
        {"label": "Lender Legal",          "flat": Decimal("5000")},
        {"label": "Appraisal",             "flat": Decimal("3500")},
        {"label": "Title",                 "flat": Decimal("2500")},
    ],
    "pre_development_loan": [
        {"label": "Origination Fee",       "pct_of_principal": Decimal("1.5")},
        {"label": "Lender Legal",          "flat": Decimal("3000")},
    ],
    "acquisition_loan": [
        {"label": "Origination Fee",       "pct_of_principal": Decimal("1.0")},
        {"label": "Lender Legal",          "flat": Decimal("5000")},
        {"label": "Title / Survey",        "flat": Decimal("3500")},
    ],
    "bridge": [
        {"label": "Origination Fee",       "pct_of_principal": Decimal("1.5")},
        {"label": "Lender Legal",          "flat": Decimal("3000")},
    ],
    "bond": [
        {"label": "Bond Issuance Fee",     "pct_of_principal": Decimal("1.0")},
        {"label": "Bond Counsel Legal",    "flat": Decimal("15000")},
    ],
}

# Maps CapitalModule.active_phase_start → UseLinePhase string for closing cost Use lines.
# Covers both short-form values ("lease_up") and milestone-key variants ("operation_lease_up")
# that the wizard stores verbatim from form data.  Unmapped values fall back to
# "pre_construction" (construction loan close is the most common default).
_APS_TO_USE_PHASE: dict[str, str] = {
    "acquisition":          "acquisition",
    "close":                "acquisition",      # milestone key for "loan closes at acq"
    "pre_construction":     "pre_construction",
    "construction":         "construction",
    "lease_up":             "operation",
    "operation_lease_up":   "operation",        # milestone key variant
    "stabilized":           "operation",
    "operation_stabilized": "operation",        # milestone key variant
    "exit":                 "exit",
    "divestment":           "exit",             # milestone key variant
}


def _carry_type_for_phase(carry: dict, is_construction: bool) -> str:
    """Extract carry_type from either flat {carry_type:...} or phased {phases:[...]} format.

    Normalises "accruing" → "capitalized_interest" in the cashflow engine only.
    The waterfall engine keeps accruing distinct (side-pocket vs principal accrual).
    """
    def _norm(ct: str) -> str:
        return "capitalized_interest" if ct == "accruing" else ct

    if "phases" in carry:
        target = "construction" if is_construction else "operation"
        for p in carry["phases"]:
            if p.get("name") == target:
                return _norm(p.get("carry_type", "none"))
        return "none"
    return _norm(carry.get("carry_type", "none"))


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
    def _loan_pre_op_months(module: object) -> int:
        """Compute the number of pre-op months within this loan's active window.

        Only counts construction-type phases (acquisition, hold, pre_construction,
        construction, renovation, conversion) that fall within the module's
        [active_phase_start, _resolve_active_end_rank) rank window.  This replaces
        the global ``constr_months_total`` so each loan uses its own N for the
        IR/CI carry formula.
        """
        start = str(getattr(module, "active_phase_start", "") or "")
        start_rank = _APS_TO_RANK.get(start, 0)
        # End-exclusive: derived from Exit Vehicle (supersedes active_phase_end).
        end_rank   = _resolve_active_end_rank(module, capital_modules)
        return sum(
            p.months for p in phases
            if p.period_type in _CONSTRUCTION_PERIOD_TYPES
            and start_rank <= _PERIOD_TYPE_RANK.get(p.period_type, 99) < end_rank
        )

    # Legacy global sum — kept for the legacy path (non-Phase-B deals) where
    # there's a single construction+perm pair and no per-loan active windows.
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
        # CI labels (100% factor — balance grows, use line is the accrued amount)
        "Capitalized Construction Interest",
        "Construction Interest Reserve",          # legacy label — aliased for backward compat
        "Capitalized Pre-Development Interest",
        "Capitalized Acquisition Interest",
        # IR labels (avg-draw factor — pre-funded pool, use line is the reserve bucket)
        "Interest Reserve",                       # construction IR
        "Pre-Development Interest Reserve",       # pre-dev IR
        "Acquisition Interest Reserve",           # acquisition IR
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
    # Pairs of (retired_module, retiring_module) resolved via exit_terms.vehicle.
    # Populated by the generic pairing pass below; consumed by the refi
    # writeback at the end of this sizing block.
    _retirement_pairs: list[tuple[object, object]] = []
    _bridge_io: dict = {}            # {funder_type: interest_amount} for new-path use lines
    _bridge_io_carry_type: dict = {} # {funder_type: "interest_reserve"|"capitalized_interest"}
    _cc_data:  dict = {}             # {id(module): {"flat": Decimal, "pct": Decimal, "module": m}}

    debt_types_list: list = getattr(inputs, "debt_types", None) or []

    if debt_types_list:
        # ── New multi-debt path ─────────────────────────────────────────────
        _BRIDGE_FUNDER_TYPES = {"pre_development_loan", "acquisition_loan", "construction_loan", "bridge"}
        _PRE_DEV_USE_PHASES  = {"pre_construction"}
        _ACQ_USE_PHASES      = {"acquisition", "other"}
        _CONSTR_USE_PHASES   = {"construction", "renovation", "conversion"}

        # Pre-compute the full set of closing cost Use line labels for auto-sized modules.
        # These are excluded from _phase_cost_sum so that closing costs do not inflate
        # the bridge loan sizing (construction closing costs fire at pre_construction but
        # should NOT grow constr_costs; they are financed by the perm gap-fill instead).
        _cc_labels: set[str] = set()
        for _pre_cm in capital_modules:
            _pre_ft = str(getattr(_pre_cm, "funder_type", "") or "").replace("FunderType.", "")
            if _pre_ft not in _DEFAULT_LOAN_COSTS or not (_pre_cm.source or {}).get("auto_size"):
                continue
            _pre_cm_lbl = getattr(_pre_cm, "label", "") or _pre_ft.replace("_", " ").title()
            for _pre_cost in _DEFAULT_LOAN_COSTS[_pre_ft]:
                _cc_labels.add(f"{_pre_cm_lbl} — {_pre_cost['label']}")

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
                _pdl_terms = (inputs.debt_terms or {}).get("pre_development_loan", {})
                _ltc = Decimal(str(_src.get("ltv_pct") or _pdl_terms.get("ltv_pct") or 100))
                _funded = _q(pre_dev_costs * _ltc / HUNDRED)
                _r = Decimal(str(_rate or 0))
                _pre_ct = _carry_type_for_phase(_carry, is_construction=True)
                _n = _loan_pre_op_months(_m)
                if _pre_ct == "interest_reserve":
                    _io_f = (_r / HUNDRED / Decimal("12") * (Decimal(_n + 1) / Decimal("2"))
                             ) if (_r > ZERO and _n > 0) else ZERO
                elif _pre_ct == "capitalized_interest":
                    _io_f = (_r / HUNDRED / Decimal("12") * Decimal(_n)
                             ) if (_r > ZERO and _n > 0) else ZERO
                else:
                    _io_f = ZERO
                _div = ONE - _io_f
                _principal = _q(_funded / _div) if (_div > ZERO and _funded > ZERO) else _funded
                if _principal > ZERO and _r > ZERO and _n > 0 and _io_f > ZERO:
                    _bridge_io["pre_development_loan"] = _q(_principal - _funded)
                    _bridge_io_carry_type["pre_development_loan"] = _pre_ct

            elif _ft == "acquisition_loan":
                _dt_terms = (inputs.debt_terms or {}).get("acquisition_loan", {})
                _ltv = Decimal(str(_src.get("ltv_pct") or _dt_terms.get("ltv_pct") or 70))
                _principal = _q(acq_costs * _ltv / HUNDRED)
                _r = Decimal(str(_rate or 0))
                _acq_ct = _carry_type_for_phase(_carry, is_construction=True)
                _n = _loan_pre_op_months(_m)
                if _principal > ZERO and _r > ZERO and _n > 0:
                    if _acq_ct == "interest_reserve":
                        _acq_interest = _q(_principal * _r / HUNDRED / Decimal("12") * (Decimal(_n + 1) / Decimal("2")))
                    elif _acq_ct == "capitalized_interest":
                        _acq_interest = _q(_principal * _r / HUNDRED / Decimal("12") * Decimal(_n))
                    else:
                        _acq_interest = ZERO
                    if _acq_interest > ZERO:
                        _bridge_io["acquisition_loan"] = _acq_interest
                        _bridge_io_carry_type["acquisition_loan"] = _acq_ct

            elif _ft == "construction_loan":
                _cl_terms = (inputs.debt_terms or {}).get("construction_loan", {})
                _ltc = Decimal(str(_src.get("ltv_pct") or _cl_terms.get("ltv_pct") or 75))
                _funded = _q(constr_costs * _ltc / HUNDRED)
                _r = Decimal(str(_cr or 0))
                _cl_ct = _carry_type_for_phase(_carry, is_construction=True)
                _n = _loan_pre_op_months(_m)
                if _cl_ct == "interest_reserve":
                    _io_f = (_r / HUNDRED / Decimal("12") * (Decimal(_n + 1) / Decimal("2"))
                             ) if (_r > ZERO and _n > 0) else ZERO
                elif _cl_ct == "capitalized_interest":
                    _io_f = (_r / HUNDRED / Decimal("12") * Decimal(_n)
                             ) if (_r > ZERO and _n > 0) else ZERO
                else:
                    _io_f = ZERO
                _div = ONE - _io_f
                _principal = _q(_funded / _div) if (_div > ZERO and _funded > ZERO) else _funded
                if _principal > ZERO and _r > ZERO and _n > 0 and _io_f > ZERO:
                    _bridge_io["construction_loan"] = _q(_principal - _funded)
                    _bridge_io_carry_type["construction_loan"] = _cl_ct

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

    # ── Closing costs (Phase B multi-debt path only) ──────────────────────────
    # For each auto-sized loan module with a funder_type in _DEFAULT_LOAN_COSTS:
    #   - Bridge loans (already sized above): compute flat + % costs from known principal.
    #   - Perm/gap-fill modules: flat costs added to total_uses; % costs folded into
    #     divisor algebraically so perm sizes up to cover its own origination fee in
    #     one pass (no multi-run convergence needed).
    # Use-line sentinel: amount == 0 (or no row) → compute; amount > 0 → user override.
    # User overrides are already in total_uses from the initial sum; we must not add them
    # again, and must not recompute them.
    _cc_data: dict = {}   # id(module) → {"flat": Decimal, "pct": Decimal, "module": m}
    if debt_types_list and auto_modules:
        for _ccm in capital_modules:
            _ccm_ft = str(getattr(_ccm, "funder_type", "") or "").replace("FunderType.", "")
            if _ccm_ft not in _DEFAULT_LOAN_COSTS or not (_ccm.source or {}).get("auto_size"):
                continue
            _ccm_lbl = getattr(_ccm, "label", "") or _ccm_ft.replace("_", " ").title()
            _cc_flat = ZERO
            _cc_pct  = ZERO
            for _cc in _DEFAULT_LOAN_COSTS[_ccm_ft]:
                _cc_full_lbl = f"{_ccm_lbl} — {_cc['label']}"
                _cc_exist = next((ul for ul in use_lines if getattr(ul, "label", "") == _cc_full_lbl), None)
                if _cc_exist and _to_decimal(getattr(_cc_exist, "amount", 0)) > ZERO:
                    continue  # user override — already in total_uses from initial sum
                if "pct_of_principal" in _cc:
                    _cc_pct += Decimal(str(_cc["pct_of_principal"])) / HUNDRED
                else:
                    _cc_flat += Decimal(str(_cc["flat"]))
            _cc_data[id(_ccm)] = {"flat": _cc_flat, "pct": _cc_pct, "module": _ccm}

        # Add closing costs to total_uses now.
        # Bridge modules (already removed from auto_modules): flat + pct from sized principal.
        # Perm/gap-fill modules still in auto_modules: flat only (pct folded into divisor below).
        _auto_mod_ids = {id(m) for m in auto_modules}
        for _cc_obj in _cc_data.values():
            _cc_ref = _cc_obj["module"]
            if id(_cc_ref) in _auto_mod_ids:
                # Gap-fill module: add flat costs now; % handled via divisor in gap-fill loop
                total_uses += _cc_obj["flat"]
            else:
                # Bridge module: principal known, add flat + pct × principal
                _cc_br_p = Decimal(str((_cc_ref.source or {}).get("amount") or 0))
                total_uses += _cc_obj["flat"]
                total_uses += _q(_cc_br_p * _cc_obj["pct"])

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
                    target_monthly_ds = _q(noi_annual / dscr_min / Decimal("12"))
                    principal = _pv_from_pmt(target_monthly_ds, rate_pct, amort_years)
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
            src["amount"] = str(_q(principal))
            await session.execute(
                sa_update(CapitalModule).where(CapitalModule.id == module.id).values(source=src)
            )
            module.source = src  # keep in-memory view consistent
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
                target_monthly_ds = _q(noi_annual / dscr_min / Decimal("12"))
                p_dscr = _pv_from_pmt(target_monthly_ds, rate_pct, amort_years)

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
            src["amount"] = str(_q(principal))
            await session.execute(
                sa_update(CapitalModule).where(CapitalModule.id == module.id).values(source=src)
            )
            module.source = src
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
        src["amount"] = str(_q(principal))
        await session.execute(
            sa_update(CapitalModule).where(CapitalModule.id == module.id).values(source=src)
        )
        module.source = src  # keep in-memory view consistent

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
            await session.execute(
                sa_update(CapitalModule)
                .where(CapitalModule.id == _retired.id)
                .values(source=retired_src)
            )
            _retired.source = retired_src

        retirer_src["construction_retirement"] = retired_amount
        await session.execute(
            sa_update(CapitalModule)
            .where(CapitalModule.id == _retirer.id)
            .values(source=retirer_src)
        )
        _retirer.source = retirer_src

        # Persist the resolved vehicle on the retired module's exit_terms so
        # the UI can look up "retires <label>" without re-running the resolver.
        retired_exit = dict(_retired.exit_terms or {})
        if retired_exit.get("vehicle") != str(_retirer.id):
            retired_exit["vehicle"] = str(_retirer.id)
            await session.execute(
                sa_update(CapitalModule)
                .where(CapitalModule.id == _retired.id)
                .values(exit_terms=retired_exit)
            )
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
            # Only auto-clear is_bridge when the funder_type is NOT a
            # bridge type — bridge-funder-type modules were sized as
            # bridges via _BRIDGE_FUNDER_TYPES and should stay flagged.
            _ft = str(getattr(_cm, "funder_type", "") or "").replace("FunderType.", "")
            if _ft not in {"pre_development_loan", "acquisition_loan",
                           "construction_loan", "bridge"}:
                src.pop("is_bridge", None)
                changed = True
        if changed:
            await session.execute(
                sa_update(CapitalModule)
                .where(CapitalModule.id == _cm.id)
                .values(source=src)
            )
            _cm.source = src

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
            if ct2 in ("interest_reserve", "capitalized_interest"):
                pass  # no periodic DS; reserve sized on zero DS for this module
            elif ct2 == "io_only":
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

    # Update or create construction interest use line (balance-only: not a cash outflow).
    # Label depends on carry type: IR → "Interest Reserve", CI → "Capitalized Construction Interest".
    # Collect ALL rows matching any known construction interest label, keep exactly one.
    _CONSTR_INT_LABELS = {
        "Capitalized Construction Interest",
        "Construction Interest Reserve",   # legacy
        "Interest Reserve",                # IR carry type
    }
    _constr_int_ct = _bridge_io_carry_type.get("construction_loan", "capitalized_interest")
    _constr_int_label = (
        "Interest Reserve"
        if _constr_int_ct == "interest_reserve"
        else "Capitalized Construction Interest"
    )
    _constr_int_notes = (
        "Auto-computed: interest reserve pre-funded from construction loan proceeds."
        if _constr_int_ct == "interest_reserve"
        else "Auto-computed: IO capitalized into construction loan principal."
    )
    _ci_rows = [ul for ul in use_lines if getattr(ul, "label", "") in _CONSTR_INT_LABELS]
    if _ci_rows:
        _ci_keep = _ci_rows[0]
        _ci_keep.label = _constr_int_label
        _ci_keep.amount = total_constr_io
        _ci_keep.notes = _constr_int_notes
        session.add(_ci_keep)
        for _ci_dup in _ci_rows[1:]:
            await session.delete(_ci_dup)
            use_lines.remove(_ci_dup)
    elif project_id and total_constr_io > ZERO:
        new_ul = UseLine(
            project_id=project_id,
            label=_constr_int_label,
            phase="construction",
            amount=total_constr_io,
            timing_type="first_day",
            notes=_constr_int_notes,
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
                    notes=_bnotes,
                )
                session.add(_new_io_ul)
                use_lines.append(_new_io_ul)

    # ── Write closing cost Use lines ──────────────────────────────────────────
    # All auto-sized modules now have final principals.  Write one Use line per
    # default closing cost, using amount==0 as the "compute" sentinel.
    # amount > 0 → user override → skip (already in DB, already correct in total_uses).
    if _cc_data and project_id:
        for _cc_obj in _cc_data.values():
            _ccm_ref  = _cc_obj["module"]
            _ccm_ft   = str(getattr(_ccm_ref, "funder_type", "") or "").replace("FunderType.", "")
            _ccm_lbl  = getattr(_ccm_ref, "label", "") or _ccm_ft.replace("_", " ").title()
            _ccm_p    = Decimal(str((_ccm_ref.source or {}).get("amount") or 0))
            _ccm_aps  = getattr(_ccm_ref, "active_phase_start", None) or ""
            _ccm_phase = _APS_TO_USE_PHASE.get(_ccm_aps, "pre_construction")

            for _cc in _DEFAULT_LOAN_COSTS[_ccm_ft]:
                _cc_full_lbl = f"{_ccm_lbl} — {_cc['label']}"
                _cc_exist = next(
                    (ul for ul in use_lines if getattr(ul, "label", "") == _cc_full_lbl), None
                )
                if _cc_exist and _to_decimal(getattr(_cc_exist, "amount", 0)) > ZERO:
                    continue  # user override — leave untouched

                if "pct_of_principal" in _cc:
                    _cc_amt = _q(_ccm_p * Decimal(str(_cc["pct_of_principal"])) / HUNDRED)
                else:
                    _cc_amt = Decimal(str(_cc["flat"]))

                if _cc_exist:
                    _cc_exist.amount = _cc_amt
                    _cc_exist.phase  = _ccm_phase
                    session.add(_cc_exist)
                elif _cc_amt > ZERO:
                    _new_cc_ul = UseLine(
                        project_id=project_id,
                        label=_cc_full_lbl,
                        phase=_ccm_phase,
                        amount=_cc_amt,
                        timing_type="first_day",
                        notes="Auto-computed — edit to override",
                    )
                    session.add(_new_cc_ul)
                    use_lines.append(_new_cc_ul)

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
    pmt = _monthly_pmt(principal, rate_pct, amort_years)
    factor = (ONE + monthly_rate) ** n_amort
    balance = _q(principal * factor - pmt * (factor - ONE) / monthly_rate)
    return _q(max(balance, ZERO))


def _sum_debt_service(modules: list, is_construction: bool) -> Decimal:
    """Compute total monthly debt service for construction or operation phase."""
    total = ZERO
    for m in modules:
        ft = str(m.funder_type).replace("FunderType.", "")
        if ft not in _DEBT_FUNDER_TYPES:
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
    income_mode: str = "revenue_opex",
    first_stab_period: int = 0,
    project_id: UUID | None = None,
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
                # Bad debt and concessions: separate % deductions from GPR
                bad_debt_pct = _percent(getattr(stream, "bad_debt_pct", None))
                concessions_pct = _percent(getattr(stream, "concessions_pct", None))
                bad_debt = _q(escalated_amount * bad_debt_pct)
                concessions = _q(escalated_amount * concessions_pct)
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
        # CI labels — no per-period cash outflow (accrues to balance or reserve pays it)
        "Capitalized Construction Interest",
        "Construction Interest Reserve",
        "Capitalized Pre-Development Interest",
        "Capitalized Acquisition Interest",
        # IR labels — pre-funded pool; no per-period cash outflow from project
        "Interest Reserve",
        "Pre-Development Interest Reserve",
        "Acquisition Interest Reserve",
        "Lease-Up Reserve",
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
        # Note: prepay penalties at exit are injected in the main compute_cash_flows
        # loop which has access to capital modules — not here.

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
        curve = str(getattr(inputs, "lease_up_curve", None) or "linear")
        if curve == "s_curve":
            # Logistic S-curve: slow start → fast middle → slow finish
            # occ(t) = initial + (stab - initial) × sigmoid(k × (t/N - 0.5))
            # where sigmoid(x) = 1 / (1 + e^(-x)), normalized so sigmoid(0)=0, sigmoid(N)=1
            import math
            k = float(getattr(inputs, "lease_up_curve_steepness", None) or 5)
            t_norm = float(month_index) / float(phase.months - 1)  # 0.0 → 1.0
            # Shift so midpoint is at 0.5, scale by steepness
            raw = 1.0 / (1.0 + math.exp(-k * (t_norm - 0.5)))
            # Normalize: map sigmoid(k*-0.5)..sigmoid(k*0.5) → 0..1
            low = 1.0 / (1.0 + math.exp(-k * (-0.5)))
            high = 1.0 / (1.0 + math.exp(-k * 0.5))
            normalized = (raw - low) / (high - low) if high > low else t_norm
            occ = initial_occupancy + (stabilized_occupancy - initial_occupancy) * Decimal(str(normalized))
            return _q(_clamp(occ, ZERO, stabilized_occupancy))
        # Default: linear ramp
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
