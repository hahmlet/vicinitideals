from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vicinitideals.models.capital import (
    CapitalModule,
    FunderType,
    WaterfallResult,
    WaterfallTier,
    WaterfallTierType,
)
from vicinitideals.models.cashflow import CashFlow, OperationalOutputs, PeriodType
from vicinitideals.models.deal import Scenario
from vicinitideals.models.manifest import WorkflowRunManifest
from vicinitideals.schemas.capital import CapitalCarrySchema, CapitalExitSchema, CapitalSourceSchema

try:
    import pyxirr
except ImportError:  # pragma: no cover - dependency is expected in runtime environments
    pyxirr = None


MONEY_PLACES = Decimal("0.000001")
ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")
DEFAULT_IRR_BASE_YEAR = 2020
PHASE_ORDER = {
    PeriodType.acquisition.value: 0,
    PeriodType.hold.value: 1,
    PeriodType.pre_construction.value: 2,
    PeriodType.minor_renovation.value: 3,
    PeriodType.major_renovation.value: 4,
    PeriodType.conversion.value: 5,
    PeriodType.construction.value: 6,
    PeriodType.lease_up.value: 7,
    PeriodType.stabilized.value: 8,
    PeriodType.exit.value: 9,
}
DEBT_FUNDER_TYPES = {
    FunderType.senior_debt.value,
    FunderType.mezzanine_debt.value,
    FunderType.bridge.value,
    FunderType.soft_loan.value,
    FunderType.construction_loan.value,
    FunderType.bond.value,
}
EQUITY_FUNDER_TYPES = {
    FunderType.preferred_equity.value,
    FunderType.common_equity.value,
    FunderType.tax_credit.value,
}
NON_RETURN_OF_CAPITAL_EXIT_TYPES = {"forgiven"}


@dataclass
class ModuleState:
    module: CapitalModule
    source: CapitalSourceSchema
    carry: CapitalCarrySchema
    exit_terms: CapitalExitSchema
    commitment: Decimal
    cumulative_contributed: Decimal = ZERO
    cumulative_distributed: Decimal = ZERO
    outstanding_principal: Decimal = ZERO
    accrued_interest_due: Decimal = ZERO
    accrued_pref_due: Decimal = ZERO


async def compute_waterfall(
    deal_model_id: UUID | str, session: AsyncSession
) -> dict[str, Any]:
    """Compute and persist capital stack waterfall results for a deal.

    Requirements satisfied by this Stage 1B engine:
    - loads previously computed `CashFlow` rows from Stage 1A
    - deserializes `CapitalModule.source` / `.carry` / `.exit_terms`
    - allocates negative periods as capital calls by stack position
    - distributes positive periods across ordered `WaterfallTier` rows
    - persists one `WaterfallResult` per period × tier × capital module target
    - returns LP / GP IRR plus equity multiple and year-1 cash-on-cash

    Auto-fallback: if no equity CapitalModule exists, a synthetic common_equity
    module is created representing the org as 100% owner ($0 cash-in, residual
    interest only). If no WaterfallTier rows exist, debt_service tiers are
    auto-generated for each debt module plus a residual tier (100% GP/owner).
    """

    deal_uuid = UUID(str(deal_model_id))
    deal_model = await _load_deal_context(session, deal_uuid)
    if deal_model is None:
        raise ValueError(f"DealModel {deal_uuid} was not found")

    if not deal_model.capital_modules:
        raise ValueError(f"DealModel {deal_uuid} has no CapitalModule rows")

    # Auto-create equity module and/or tiers if missing
    await _ensure_equity_and_tiers(deal_uuid, deal_model, session)
    # Reload after potential inserts
    deal_model = await _load_deal_context(session, deal_uuid)

    capital_modules = sorted(
        deal_model.capital_modules,
        key=lambda module: (module.stack_position, module.label.lower(), str(module.id)),
    )

    waterfall_tiers = sorted(
        deal_model.waterfall_tiers,
        key=lambda tier: (tier.priority, str(tier.id)),
    )

    cash_flows = sorted(deal_model.cash_flows, key=lambda row: row.period)
    if not cash_flows:
        raise ValueError(
            "CashFlow rows are required before running the waterfall engine. "
            "Run the cashflow engine first."
        )

    await session.execute(
        delete(WaterfallResult).where(WaterfallResult.scenario_id == deal_uuid)
    )

    total_project_cost = _resolve_total_project_cost(deal_model.operational_outputs, cash_flows)
    module_states = _build_module_states(capital_modules, total_project_cost)
    state_by_id = {state.module.id: state for state in module_states}
    equity_states = [state for state in module_states if _is_equity_module(state.module)]
    gp_proxy_state = _resolve_gp_proxy_state(module_states, equity_states)

    lp_cashflows: dict[int, Decimal] = {}
    gp_cashflows: dict[int, Decimal] = {}
    running_totals: dict[tuple[UUID, UUID], Decimal] = {}
    result_rows: list[WaterfallResult] = []

    for cash_flow in cash_flows:
        phase_name = _enum_value(cash_flow.period_type)
        net_cash = _to_decimal(cash_flow.net_cash_flow)

        if net_cash < ZERO:
            capital_calls = _allocate_capital_calls(-net_cash, phase_name, module_states)
            for module_id, amount in capital_calls.items():
                if amount <= ZERO:
                    continue
                state = state_by_id[module_id]
                if _is_gp_equity_module(state.module):
                    _append_period_cashflow(gp_cashflows, cash_flow.period, -amount)
                elif _is_equity_module(state.module):
                    _append_period_cashflow(lp_cashflows, cash_flow.period, -amount)
            available_cash = ZERO
        else:
            available_cash = net_cash

        _accrue_current_period_obligations(cash_flow.period, phase_name, module_states)

        for tier in waterfall_tiers:
            target_states = _states_for_tier(
                tier=tier,
                all_states=module_states,
                equity_states=equity_states,
                gp_proxy_state=gp_proxy_state,
            )
            allocations = _apply_tier_distribution(
                tier=tier,
                phase_name=phase_name,
                period=cash_flow.period,
                available_cash=available_cash,
                target_states=target_states,
                gp_proxy_state=gp_proxy_state,
                lp_cashflows=lp_cashflows,
                gp_cashflows=gp_cashflows,
            )
            distributed = _q(sum(allocations.values(), ZERO))
            available_cash = _q(available_cash - distributed)

            for state in target_states:
                cash_distributed = _q(allocations.get(state.module.id, ZERO))
                running_key = (tier.id, state.module.id)
                running_totals[running_key] = _q(
                    running_totals.get(running_key, ZERO) + cash_distributed
                )
                result_rows.append(
                    WaterfallResult(
                        scenario_id=deal_uuid,
                        period=cash_flow.period,
                        tier_id=tier.id,
                        capital_module_id=state.module.id,
                        cash_distributed=cash_distributed,
                        cumulative_distributed=running_totals[running_key],
                        party_irr_pct=None,
                    )
                )

    lp_irr_pct = _compute_xirr_pct(lp_cashflows)
    gp_irr_pct = _compute_xirr_pct(gp_cashflows)
    equity_multiple = _compute_equity_multiple(lp_cashflows, gp_cashflows)
    cash_on_cash_year_1_pct = _compute_cash_on_cash_year_1_pct(lp_cashflows, gp_cashflows)

    exit_periods = {row.period for row in cash_flows if _enum_value(row.period_type) == PeriodType.exit.value}
    for row in result_rows:
        if row.period not in exit_periods:
            continue
        state = state_by_id[row.capital_module_id]
        if state.module.id == gp_proxy_state.module.id and gp_irr_pct is not None:
            row.party_irr_pct = gp_irr_pct
        elif _is_equity_module(state.module) and lp_irr_pct is not None:
            row.party_irr_pct = lp_irr_pct

    session.add_all(result_rows)
    await session.flush()

    # Write equity_required to OperationalOutputs: sum of all equity contributions
    # (negative LP+GP cash flows = cash in from equity investors)
    equity_required = _q(
        _negative_total(lp_cashflows) + _negative_total(gp_cashflows)
    )
    outputs_row = (
        await session.execute(
            select(OperationalOutputs).where(OperationalOutputs.scenario_id == deal_uuid)
        )
    ).scalar_one_or_none()
    if outputs_row is not None and equity_required > ZERO:
        outputs_row.equity_required = equity_required
        await session.flush()

    levered_metrics = await _apply_levered_metrics(deal_uuid, session)
    distribution_report = _build_investor_distribution_report(
        deal_uuid=deal_uuid,
        capital_modules=capital_modules,
        result_rows=result_rows,
    )

    summary = {
        "deal_model_id": str(deal_uuid),
        "capital_module_count": len(capital_modules),
        "waterfall_tier_count": len(waterfall_tiers),
        "cash_flow_count": len(cash_flows),
        "waterfall_result_count": len(result_rows),
        "lp_irr_pct": lp_irr_pct,
        "gp_irr_pct": gp_irr_pct,
        "equity_multiple": equity_multiple,
        "cash_on_cash_year_1_pct": cash_on_cash_year_1_pct,
        "dscr": levered_metrics["dscr"],
        "project_irr_levered": levered_metrics["project_irr_levered"],
        "distribution_report": distribution_report,
    }

    session.add(
        WorkflowRunManifest(
            scenario_id=deal_uuid,
            engine="waterfall",
            inputs_json=_json_ready(
                {
                    "model_id": str(deal_uuid),
                    "project_type": _enum_value(deal_model.project_type),
                    "capital_module_count": len(capital_modules),
                    "waterfall_tier_count": len(waterfall_tiers),
                    "cash_flow_count": len(cash_flows),
                }
            ),
            outputs_json=_json_ready(summary),
        )
    )
    await session.flush()

    return summary


async def _ensure_equity_and_tiers(
    deal_uuid: UUID,
    deal_model: Scenario,
    session: AsyncSession,
) -> None:
    """Auto-create a synthetic equity module and/or waterfall tiers when missing.

    If no equity CapitalModule exists: creates a common_equity module for the org
    at $0 commitment (residual interest only — org is 100% owner by default).

    If no WaterfallTier rows exist: auto-generates one debt_service tier per
    debt module (ordered by stack_position) plus a residual tier (100% GP/owner).

    Both synthetic objects are marked with notes so they're identifiable.
    """
    capital_modules = sorted(
        deal_model.capital_modules,
        key=lambda m: (m.stack_position, str(m.id)),
    )
    equity_modules = [m for m in capital_modules if _is_equity_module(m)]
    debt_modules = [m for m in capital_modules if _is_debt_module(m)]

    # Auto-create equity module if none exists
    synthetic_equity: CapitalModule | None = None
    if not equity_modules:
        max_position = max((m.stack_position for m in capital_modules), default=0)
        synthetic_equity = CapitalModule(
            scenario_id=deal_uuid,
            label="Owner Equity",
            funder_type=FunderType.common_equity,
            stack_position=max_position + 1,
            source={"amount": "0", "notes": "Auto-created: org is 100% owner (no cash-in equity source configured)"},
            carry={"carry_type": "none"},
            exit_terms={"exit_type": "profit_share", "trigger": "ongoing", "profit_share_pct": 100},
            active_phase_start="acquisition",
            active_phase_end="exit",
        )
        session.add(synthetic_equity)
        await session.flush()
        capital_modules.append(synthetic_equity)
        equity_modules = [synthetic_equity]

    # Auto-create tiers if none exist
    if not deal_model.waterfall_tiers:
        priority = 1
        # One debt_service tier per debt module, linked by capital_module_id
        for debt_module in debt_modules:
            session.add(WaterfallTier(
                scenario_id=deal_uuid,
                capital_module_id=debt_module.id,
                priority=priority,
                tier_type=WaterfallTierType.debt_service,
                lp_split_pct=Decimal("0"),
                gp_split_pct=Decimal("0"),
                description=f"Auto: debt service for {debt_module.label}",
            ))
            priority += 1
        # Residual: 100% to GP/owner
        session.add(WaterfallTier(
            scenario_id=deal_uuid,
            capital_module_id=None,
            priority=priority,
            tier_type=WaterfallTierType.residual,
            lp_split_pct=Decimal("0"),
            gp_split_pct=Decimal("100"),
            description="Auto: residual cash flow to owner (100% GP)",
        ))
        await session.flush()


async def get_waterfall_distribution_report(
    deal_model_id: UUID | str, session: AsyncSession
) -> dict[str, Any]:
    deal_uuid = UUID(str(deal_model_id))
    deal_model = await _load_deal_context(session, deal_uuid)
    if deal_model is None:
        raise ValueError(f"DealModel {deal_uuid} was not found")

    capital_modules = sorted(
        deal_model.capital_modules,
        key=lambda module: (module.stack_position, module.label.lower(), str(module.id)),
    )
    result_rows = list(
        (
            await session.execute(
                select(WaterfallResult)
                .where(WaterfallResult.scenario_id == deal_uuid)
                .order_by(WaterfallResult.period.asc(), WaterfallResult.id.asc())
            )
        ).scalars()
    )
    return _build_investor_distribution_report(
        deal_uuid=deal_uuid,
        capital_modules=capital_modules,
        result_rows=result_rows,
    )


def _build_investor_distribution_report(
    *,
    deal_uuid: UUID,
    capital_modules: list[CapitalModule],
    result_rows: list[WaterfallResult],
) -> dict[str, Any]:
    rows_by_module: dict[UUID, list[WaterfallResult]] = {}
    total_cash_distributed = ZERO
    for row in sorted(result_rows, key=lambda item: (item.period, str(item.id))):
        rows_by_module.setdefault(row.capital_module_id, []).append(row)
        total_cash_distributed = _q(total_cash_distributed + _to_decimal(row.cash_distributed))

    investors: list[dict[str, Any]] = []
    for module in capital_modules:
        module_rows = rows_by_module.get(module.id, [])
        timeline: list[dict[str, Any]] = []
        total_distributed = ZERO
        year_one_distributions = ZERO
        running_cumulative = ZERO
        current_period: int | None = None
        current_period_distribution = ZERO
        latest_party_irr_pct: Decimal | None = None

        for row in module_rows:
            period = int(row.period)
            cash_distributed = _to_decimal(row.cash_distributed)
            total_distributed = _q(total_distributed + cash_distributed)
            if period in range(0, 12):
                year_one_distributions = _q(year_one_distributions + max(cash_distributed, ZERO))
            if row.party_irr_pct is not None:
                latest_party_irr_pct = _to_decimal(row.party_irr_pct)

            if current_period is None:
                current_period = period
            if period != current_period:
                running_cumulative = _q(running_cumulative + current_period_distribution)
                timeline.append(
                    {
                        "period": current_period,
                        "cash_distributed": current_period_distribution,
                        "cumulative_distributed": running_cumulative,
                    }
                )
                current_period = period
                current_period_distribution = ZERO
            current_period_distribution = _q(current_period_distribution + cash_distributed)

        if current_period is not None:
            running_cumulative = _q(running_cumulative + current_period_distribution)
            timeline.append(
                {
                    "period": current_period,
                    "cash_distributed": current_period_distribution,
                    "cumulative_distributed": running_cumulative,
                }
            )

        committed_capital = _resolve_committed_capital(module)
        equity_multiple = (
            _q(total_distributed / committed_capital)
            if committed_capital is not None and committed_capital > ZERO
            else None
        )
        cash_on_cash_year_1_pct = (
            _q((year_one_distributions / committed_capital) * HUNDRED)
            if committed_capital is not None and committed_capital > ZERO
            else None
        )
        share_of_total_distributions_pct = (
            _q((total_distributed / total_cash_distributed) * HUNDRED)
            if total_cash_distributed > ZERO
            else None
        )

        investors.append(
            {
                "capital_module_id": module.id,
                "investor_name": module.label,
                "funder_type": _enum_value(module.funder_type),
                "stack_position": module.stack_position,
                "committed_capital": committed_capital,
                "total_cash_distributed": total_distributed,
                "ending_cumulative_distributed": running_cumulative,
                "latest_party_irr_pct": latest_party_irr_pct,
                "equity_multiple": equity_multiple,
                "cash_on_cash_year_1_pct": cash_on_cash_year_1_pct,
                "share_of_total_distributions_pct": share_of_total_distributions_pct,
                "timeline": timeline,
            }
        )

    return {
        "scenario_id": str(deal_uuid),
        "investor_count": len(investors),
        "total_cash_distributed": total_cash_distributed,
        "investors": investors,
    }


def _resolve_committed_capital(module: CapitalModule) -> Decimal | None:
    if not isinstance(module.source, dict):
        return None
    amount = module.source.get("amount")
    if amount in (None, ""):
        return None
    return _q(_to_decimal(amount))


async def _apply_levered_metrics(
    deal_model_id: UUID, session: AsyncSession
) -> dict[str, Decimal | None]:
    cash_flows = list(
        (
            await session.execute(
                select(CashFlow)
                .where(CashFlow.scenario_id == deal_model_id)
                .order_by(CashFlow.period.asc())
            )
        ).scalars()
    )
    if not cash_flows:
        return {"dscr": None, "project_irr_levered": None}

    debt_service_rows = (
        await session.execute(
            select(WaterfallResult.period, WaterfallResult.cash_distributed)
            .join(WaterfallTier, WaterfallTier.id == WaterfallResult.tier_id)
            .where(
                WaterfallResult.scenario_id == deal_model_id,
                WaterfallTier.tier_type == WaterfallTierType.debt_service.value,
            )
        )
    ).all()
    debt_service_by_period: dict[int, Decimal] = {}
    for period, cash_distributed in debt_service_rows:
        debt_service_by_period[period] = _q(
            debt_service_by_period.get(period, ZERO) + _to_decimal(cash_distributed)
        )

    outputs = (
        await session.execute(
            select(OperationalOutputs).where(OperationalOutputs.scenario_id == deal_model_id)
        )
    ).scalar_one_or_none()
    if outputs is None:
        outputs = OperationalOutputs(scenario_id=deal_model_id)
        session.add(outputs)

    unlevered_cashflows = {
        cash_flow.period: _to_decimal(cash_flow.net_cash_flow) for cash_flow in cash_flows
    }
    if outputs.project_irr_unlevered is None:
        outputs.project_irr_unlevered = _compute_xirr_pct(unlevered_cashflows) or ZERO

    # Seed running_cumulative with total_sources so the Capital Balance column
    # stays consistent with the cashflow engine's pre-seed. compute_cash_flows
    # initialises cumulative_cash_flow = total_sources; without this offset the
    # waterfall would restart from ZERO and overwrite the balance with bare NCF sums.
    total_sources = ZERO
    for cm_src in (
        await session.execute(
            select(CapitalModule).where(CapitalModule.scenario_id == deal_model_id)
        )
    ).scalars():
        _amt = (cm_src.source or {}).get("amount")
        if _amt:
            total_sources += _q(_to_decimal(_amt))

    running_cumulative = total_sources
    levered_cashflows: dict[int, Decimal] = {}
    for cash_flow in cash_flows:
        prior_debt_service = _to_decimal(cash_flow.debt_service)
        non_operating_adjustments = _q(
            _to_decimal(cash_flow.net_cash_flow) - _to_decimal(cash_flow.noi) + prior_debt_service
        )
        waterfall_ds = _q(debt_service_by_period.get(cash_flow.period, ZERO))
        # When the waterfall has no debt-service distribution for this period
        # (e.g. DSCR < 1, deal can't cover its own debt service from NOI),
        # preserve the cashflow-engine obligation so carrying costs are visible.
        debt_service = waterfall_ds if waterfall_ds > ZERO else prior_debt_service

        cash_flow.debt_service = debt_service
        cash_flow.net_cash_flow = _q(
            _to_decimal(cash_flow.noi) - debt_service + non_operating_adjustments
        )
        running_cumulative = _q(running_cumulative + _to_decimal(cash_flow.net_cash_flow))
        cash_flow.cumulative_cash_flow = running_cumulative
        levered_cashflows[cash_flow.period] = _to_decimal(cash_flow.net_cash_flow)

    if outputs.noi_stabilized is None:
        stabilized_noi_annual = _annualized_median(
            [
                _to_decimal(row.noi)
                for row in cash_flows
                if _enum_value(row.period_type) == PeriodType.stabilized.value
                and _to_decimal(row.noi) > ZERO
            ]
        )
        if stabilized_noi_annual is not None:
            outputs.noi_stabilized = stabilized_noi_annual

    computed_dscr = _compute_dscr(cash_flows, outputs)
    if computed_dscr is not None:
        outputs.dscr = computed_dscr
    elif outputs.dscr is None:
        outputs.dscr = ZERO

    levered_irr = _compute_xirr_pct(levered_cashflows)
    if levered_irr is not None:
        outputs.project_irr_levered = levered_irr
    elif outputs.project_irr_levered is None:
        outputs.project_irr_levered = (
            _to_decimal(outputs.project_irr_unlevered)
            if outputs.project_irr_unlevered is not None
            else ZERO
        )

    outputs.computed_at = datetime.now(timezone.utc)
    await session.flush()

    return {
        "dscr": _to_decimal(outputs.dscr) if outputs.dscr is not None else None,
        "project_irr_levered": (
            _to_decimal(outputs.project_irr_levered)
            if outputs.project_irr_levered is not None
            else None
        ),
    }


async def _load_deal_context(session: AsyncSession, deal_model_id: UUID) -> Scenario | None:
    result = await session.execute(
        select(Scenario)
        .options(
            selectinload(Scenario.capital_modules),
            selectinload(Scenario.waterfall_tiers),
            selectinload(Scenario.cash_flows),
            selectinload(Scenario.operational_outputs),
        )
        .where(Scenario.id == deal_model_id)
    )
    return result.scalar_one_or_none()


def _resolve_total_project_cost(
    outputs: OperationalOutputs | None, cash_flows: list[CashFlow]
) -> Decimal:
    if outputs is not None and outputs.total_project_cost is not None:
        return _to_decimal(outputs.total_project_cost)

    negative_periods = [
        -_to_decimal(row.net_cash_flow)
        for row in cash_flows
        if _to_decimal(row.net_cash_flow) < ZERO
    ]
    return _q(sum(negative_periods, ZERO))


def _build_module_states(
    capital_modules: list[CapitalModule], total_project_cost: Decimal
) -> list[ModuleState]:
    states: list[ModuleState] = []
    for module in capital_modules:
        source = CapitalSourceSchema.model_validate(module.source or {})
        carry = CapitalCarrySchema.model_validate(module.carry or {"carry_type": "none"})
        exit_terms = CapitalExitSchema.model_validate(
            module.exit_terms or {"exit_type": "full_payoff", "trigger": "sale"}
        )
        commitment = _resolve_commitment(source, total_project_cost)
        states.append(
            ModuleState(
                module=module,
                source=source,
                carry=carry,
                exit_terms=exit_terms,
                commitment=commitment,
            )
        )
    return states


def _resolve_commitment(source: CapitalSourceSchema, total_project_cost: Decimal) -> Decimal:
    if source.amount is not None:
        return _q(source.amount)
    if source.pct_of_total_cost is not None:
        return _q(total_project_cost * _percent(source.pct_of_total_cost))
    if source.draws:
        return _q(sum((_to_decimal(draw.amount) for draw in source.draws), ZERO))
    return ZERO


def _allocate_capital_calls(
    required_amount: Decimal, phase_name: str, module_states: list[ModuleState]
) -> dict[UUID, Decimal]:
    remaining = _q(required_amount)
    allocations: dict[UUID, Decimal] = {state.module.id: ZERO for state in module_states}

    ordered_states = sorted(
        module_states,
        key=lambda state: (
            1 if not _module_active_for_phase(state.module, phase_name) else 0,
            state.module.stack_position,
            state.module.label.lower(),
        ),
    )

    for state in ordered_states:
        if remaining <= ZERO:
            break
        if not _module_active_for_phase(state.module, phase_name):
            continue

        remaining_commitment = _q(max(state.commitment - state.cumulative_contributed, ZERO))
        if remaining_commitment <= ZERO and _is_equity_module(state.module):
            remaining_commitment = remaining

        contribution = _q(min(remaining, remaining_commitment))
        if contribution <= ZERO:
            continue

        state.cumulative_contributed = _q(state.cumulative_contributed + contribution)
        state.outstanding_principal = _q(state.outstanding_principal + contribution)
        allocations[state.module.id] = _q(allocations[state.module.id] + contribution)
        remaining = _q(remaining - contribution)

    if remaining > ZERO and module_states:
        fallback = next(
            (state for state in reversed(module_states) if _is_equity_module(state.module)),
            module_states[-1],
        )
        fallback.cumulative_contributed = _q(fallback.cumulative_contributed + remaining)
        fallback.outstanding_principal = _q(fallback.outstanding_principal + remaining)
        allocations[fallback.module.id] = _q(allocations[fallback.module.id] + remaining)

    return allocations


def _accrue_current_period_obligations(
    period: int, phase_name: str, module_states: list[ModuleState]
) -> None:
    for state in module_states:
        if state.outstanding_principal <= ZERO:
            continue
        if not _module_active_for_phase(state.module, phase_name):
            continue

        annual_rate = _annual_rate_decimal(state.source)
        if annual_rate <= ZERO:
            continue

        period_rate = _q(annual_rate / Decimal("12"))
        accrual = _q(state.outstanding_principal * period_rate)
        if accrual <= ZERO:
            continue

        if _is_debt_module(state.module):
            if state.carry.carry_type == "capitalized_interest" or state.carry.capitalized:
                state.outstanding_principal = _q(state.outstanding_principal + accrual)
            elif state.carry.carry_type == "accruing" and state.carry.payment_frequency == "at_exit":
                state.accrued_interest_due = _q(state.accrued_interest_due + accrual)
            else:
                state.accrued_interest_due = _q(state.accrued_interest_due + accrual)
        elif _is_equity_module(state.module):
            state.accrued_pref_due = _q(state.accrued_pref_due + accrual)


def _states_for_tier(
    *,
    tier: WaterfallTier,
    all_states: list[ModuleState],
    equity_states: list[ModuleState],
    gp_proxy_state: ModuleState,
) -> list[ModuleState]:
    if tier.capital_module_id is not None:
        matched = [state for state in all_states if state.module.id == tier.capital_module_id]
        return matched or [gp_proxy_state]

    tier_type = _enum_value(tier.tier_type)
    if tier_type in {
        WaterfallTierType.pref_return.value,
        WaterfallTierType.return_of_equity.value,
        WaterfallTierType.catch_up.value,
        WaterfallTierType.irr_hurdle_split.value,
        WaterfallTierType.residual.value,
    }:
        return equity_states or [gp_proxy_state]

    return all_states or [gp_proxy_state]


def _apply_tier_distribution(
    *,
    tier: WaterfallTier,
    phase_name: str,
    period: int,
    available_cash: Decimal,
    target_states: list[ModuleState],
    gp_proxy_state: ModuleState,
    lp_cashflows: dict[int, Decimal],
    gp_cashflows: dict[int, Decimal],
) -> dict[UUID, Decimal]:
    allocations: dict[UUID, Decimal] = {state.module.id: ZERO for state in target_states}
    if available_cash <= ZERO:
        return allocations

    tier_type = _enum_value(tier.tier_type)

    if tier_type == WaterfallTierType.debt_service.value:
        remaining = available_cash
        for state in target_states:
            if not _is_debt_module(state.module):
                continue
            if not _module_active_for_phase(state.module, phase_name):
                continue

            due = ZERO
            payment_due = _payment_due_this_period(period, state.carry.payment_frequency)
            if payment_due or phase_name == PeriodType.exit.value:
                due += state.accrued_interest_due

            if phase_name == PeriodType.exit.value and state.exit_terms.exit_type in {
                "full_payoff",
                "tranche_payoff",
            }:
                due += state.outstanding_principal

            amount = _q(min(remaining, due))
            if amount <= ZERO:
                continue

            interest_paid = _q(min(amount, state.accrued_interest_due))
            principal_paid = _q(amount - interest_paid)
            state.accrued_interest_due = _q(state.accrued_interest_due - interest_paid)
            state.outstanding_principal = _q(max(state.outstanding_principal - principal_paid, ZERO))
            state.cumulative_distributed = _q(state.cumulative_distributed + amount)
            allocations[state.module.id] = _q(allocations[state.module.id] + amount)
            remaining = _q(remaining - amount)
        return allocations

    if tier_type == WaterfallTierType.pref_return.value:
        remaining = available_cash
        for state in target_states:
            if not _is_equity_module(state.module):
                continue
            if not _module_active_for_phase(state.module, phase_name):
                continue

            amount = _q(min(remaining, state.accrued_pref_due))
            if amount <= ZERO:
                continue

            state.accrued_pref_due = _q(state.accrued_pref_due - amount)
            state.cumulative_distributed = _q(state.cumulative_distributed + amount)
            allocations[state.module.id] = _q(allocations[state.module.id] + amount)
            if _is_gp_equity_module(state.module):
                _append_period_cashflow(gp_cashflows, period, amount)
            else:
                _append_period_cashflow(lp_cashflows, period, amount)
            remaining = _q(remaining - amount)
        return allocations

    if tier_type == WaterfallTierType.return_of_equity.value:
        remaining = available_cash
        for state in target_states:
            if not _module_active_for_phase(state.module, phase_name):
                continue
            if _is_debt_module(state.module) and phase_name != PeriodType.exit.value:
                continue
            if state.exit_terms.exit_type in NON_RETURN_OF_CAPITAL_EXIT_TYPES:
                continue

            amount = _q(min(remaining, state.outstanding_principal))
            if amount <= ZERO:
                continue

            state.outstanding_principal = _q(max(state.outstanding_principal - amount, ZERO))
            state.cumulative_distributed = _q(state.cumulative_distributed + amount)
            allocations[state.module.id] = _q(allocations[state.module.id] + amount)
            if _is_gp_equity_module(state.module):
                _append_period_cashflow(gp_cashflows, period, amount)
            elif _is_equity_module(state.module):
                _append_period_cashflow(lp_cashflows, period, amount)
            remaining = _q(remaining - amount)
        return allocations

    lp_split, gp_split = _normalized_splits(tier)

    if tier_type == WaterfallTierType.catch_up.value:
        total_lp_distributions = _positive_total(lp_cashflows)
        total_gp_distributions = _positive_total(gp_cashflows)
        target_gp_share = gp_split if (lp_split + gp_split) > ZERO else ONE
        gp_target_total = _q(
            (target_gp_share / max(ONE - target_gp_share, MONEY_PLACES)) * total_lp_distributions
        )
        gp_shortfall = _q(max(gp_target_total - total_gp_distributions, ZERO))
        gp_amount = _q(min(available_cash, gp_shortfall if gp_shortfall > ZERO else available_cash * gp_split))
        lp_amount = _q(max(available_cash - gp_amount, ZERO))
        _allocate_split_amounts(
            allocations=allocations,
            lp_amount=lp_amount,
            gp_amount=gp_amount,
            target_states=target_states,
            gp_proxy_state=gp_proxy_state,
            period=period,
            lp_cashflows=lp_cashflows,
            gp_cashflows=gp_cashflows,
        )
        return allocations

    if tier_type == WaterfallTierType.irr_hurdle_split.value:
        hurdle = _percent(tier.irr_hurdle_pct)
        lp_irr_fraction = _compute_xirr_fraction(lp_cashflows)
        if lp_irr_fraction is None or lp_irr_fraction < hurdle:
            _allocate_split_amounts(
                allocations=allocations,
                lp_amount=available_cash,
                gp_amount=ZERO,
                target_states=target_states,
                gp_proxy_state=gp_proxy_state,
                period=period,
                lp_cashflows=lp_cashflows,
                gp_cashflows=gp_cashflows,
            )
            return allocations

        _allocate_split_amounts(
            allocations=allocations,
            lp_amount=_q(available_cash * lp_split),
            gp_amount=_q(available_cash * gp_split),
            target_states=target_states,
            gp_proxy_state=gp_proxy_state,
            period=period,
            lp_cashflows=lp_cashflows,
            gp_cashflows=gp_cashflows,
        )
        return allocations

    if tier_type == WaterfallTierType.residual.value:
        _allocate_split_amounts(
            allocations=allocations,
            lp_amount=_q(available_cash * lp_split),
            gp_amount=_q(available_cash * gp_split),
            target_states=target_states,
            gp_proxy_state=gp_proxy_state,
            period=period,
            lp_cashflows=lp_cashflows,
            gp_cashflows=gp_cashflows,
        )
        return allocations

    return allocations


def _allocate_split_amounts(
    *,
    allocations: dict[UUID, Decimal],
    lp_amount: Decimal,
    gp_amount: Decimal,
    target_states: list[ModuleState],
    gp_proxy_state: ModuleState,
    period: int,
    lp_cashflows: dict[int, Decimal],
    gp_cashflows: dict[int, Decimal],
) -> None:
    lp_targets = [state for state in target_states if _is_lp_equity_module(state.module)] or [
        state for state in target_states if _is_equity_module(state.module)
    ] or target_states
    if lp_amount > ZERO:
        for state, amount in _pro_rata_allocate(lp_amount, lp_targets):
            state.cumulative_distributed = _q(state.cumulative_distributed + amount)
            allocations[state.module.id] = _q(allocations.get(state.module.id, ZERO) + amount)
        _append_period_cashflow(lp_cashflows, period, lp_amount)

    gp_targets = [state for state in target_states if _is_gp_equity_module(state.module)]
    if gp_amount > ZERO:
        if gp_targets:
            for state, amount in _pro_rata_allocate(gp_amount, gp_targets):
                state.cumulative_distributed = _q(state.cumulative_distributed + amount)
                allocations[state.module.id] = _q(allocations.get(state.module.id, ZERO) + amount)
        else:
            gp_proxy_state.cumulative_distributed = _q(gp_proxy_state.cumulative_distributed + gp_amount)
            allocations[gp_proxy_state.module.id] = _q(
                allocations.get(gp_proxy_state.module.id, ZERO) + gp_amount
            )
        _append_period_cashflow(gp_cashflows, period, gp_amount)



def _pro_rata_allocate(
    total_amount: Decimal, target_states: list[ModuleState]
) -> list[tuple[ModuleState, Decimal]]:
    if not target_states:
        return []

    weights = [
        state.outstanding_principal
        if state.outstanding_principal > ZERO
        else state.cumulative_contributed
        for state in target_states
    ]
    total_weight = sum(weights, ZERO)
    if total_weight <= ZERO:
        total_weight = Decimal(len(target_states))
        weights = [ONE for _ in target_states]

    remaining = _q(total_amount)
    allocations: list[tuple[ModuleState, Decimal]] = []
    for index, state in enumerate(target_states):
        if index == len(target_states) - 1:
            amount = remaining
        else:
            amount = _q(total_amount * (weights[index] / total_weight))
            remaining = _q(remaining - amount)
        allocations.append((state, amount))
    return allocations


def _resolve_gp_proxy_state(
    all_states: list[ModuleState], equity_states: list[ModuleState]
) -> ModuleState:
    common_equity = [
        state for state in equity_states if _enum_value(state.module.funder_type) == FunderType.common_equity.value
    ]
    if common_equity:
        return sorted(common_equity, key=lambda state: state.module.stack_position)[-1]
    if equity_states:
        return sorted(equity_states, key=lambda state: state.module.stack_position)[-1]
    return sorted(all_states, key=lambda state: state.module.stack_position)[-1]


def _module_active_for_phase(module: CapitalModule, phase_name: str) -> bool:
    start = module.active_phase_start
    end = module.active_phase_end
    current_index = PHASE_ORDER.get(phase_name, 0)
    start_index = PHASE_ORDER.get(start, 0) if start else 0
    end_index = PHASE_ORDER.get(end, max(PHASE_ORDER.values())) if end else max(PHASE_ORDER.values())
    return start_index <= current_index <= end_index


def _annual_rate_decimal(source: CapitalSourceSchema) -> Decimal:
    if source.interest_rate_pct is not None:
        return _percent(source.interest_rate_pct)
    if source.draws:
        total = sum((_to_decimal(draw.amount) for draw in source.draws), ZERO)
        if total > ZERO:
            weighted = sum(
                (_to_decimal(draw.amount) * _percent(draw.io_rate_pct)) for draw in source.draws
            )
            return _q(weighted / total)
    return ZERO


def _payment_due_this_period(period: int, payment_frequency: str) -> bool:
    if payment_frequency == "annual":
        return (period + 1) % 12 == 0
    if payment_frequency == "quarterly":
        return (period + 1) % 3 == 0
    if payment_frequency == "at_exit":
        return False
    return True


def _compute_dscr(
    cash_flows: list[CashFlow], outputs: OperationalOutputs | None
) -> Decimal | None:
    stabilized_rows = [
        row for row in cash_flows if _enum_value(row.period_type) == PeriodType.stabilized.value
    ]
    if not stabilized_rows:
        return None

    stabilized_annual_debt_service = _annualized_median(
        [
            _to_decimal(row.debt_service)
            for row in stabilized_rows
            if _to_decimal(row.debt_service) > ZERO
        ]
    )
    if stabilized_annual_debt_service is None or stabilized_annual_debt_service <= ZERO:
        return None

    stabilized_noi_annual = (
        _to_decimal(outputs.noi_stabilized)
        if outputs is not None and outputs.noi_stabilized is not None
        else _annualized_median(
            [
                _to_decimal(row.noi)
                for row in stabilized_rows
                if _to_decimal(row.noi) > ZERO
            ]
        )
    )
    if stabilized_noi_annual is None or stabilized_noi_annual <= ZERO:
        return None

    return _q(stabilized_noi_annual / stabilized_annual_debt_service)


def _annualized_median(values: list[Decimal]) -> Decimal | None:
    median_value = _median_decimal(values)
    if median_value is None:
        return None
    return _q(median_value * Decimal("12"))


def _median_decimal(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None

    ordered = sorted(_q(value) for value in values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return _q((ordered[middle - 1] + ordered[middle]) / Decimal("2"))


def _normalized_splits(tier: WaterfallTier) -> tuple[Decimal, Decimal]:
    lp_split = _percent(tier.lp_split_pct)
    gp_split = _percent(tier.gp_split_pct)
    total = lp_split + gp_split
    if total <= ZERO:
        if tier.capital_module_id is not None:
            return ONE, ZERO
        return Decimal("0.80"), Decimal("0.20")
    return _q(lp_split / total), _q(gp_split / total)


def _compute_xirr_pct(period_cashflows: dict[int, Decimal]) -> Decimal | None:
    irr_fraction = _compute_xirr_fraction(period_cashflows)
    if irr_fraction is None:
        return None
    return _q(irr_fraction * HUNDRED)


def _compute_xirr_fraction(period_cashflows: dict[int, Decimal]) -> Decimal | None:
    if pyxirr is None or not period_cashflows:
        return None

    ordered_periods = sorted(period_cashflows.items())
    values = [float(_q(amount)) for _, amount in ordered_periods if _q(amount) != ZERO]
    if not values or not any(value < 0 for value in values) or not any(value > 0 for value in values):
        return None

    dates = [_period_to_date(period) for period, amount in ordered_periods if _q(amount) != ZERO]
    try:
        irr_value = pyxirr.xirr(dates, values)
    except Exception:  # pragma: no cover - pyxirr can reject degenerate series
        return None
    if irr_value is None:
        return None
    return Decimal(str(irr_value))


def _period_to_date(period: int) -> date:
    year = DEFAULT_IRR_BASE_YEAR + (period // 12)
    month = (period % 12) + 1
    return date(year, month, 1)


def _compute_equity_multiple(
    lp_cashflows: dict[int, Decimal], gp_cashflows: dict[int, Decimal]
) -> Decimal:
    total_positive = _positive_total(lp_cashflows) + _positive_total(gp_cashflows)
    total_contributed = _negative_total(lp_cashflows) + _negative_total(gp_cashflows)
    if total_contributed <= ZERO:
        return ZERO
    return _q(total_positive / total_contributed)


def _compute_cash_on_cash_year_1_pct(
    lp_cashflows: dict[int, Decimal], gp_cashflows: dict[int, Decimal]
) -> Decimal:
    year_one_periods = range(0, 12)
    year_one_distributions = sum(
        (max(lp_cashflows.get(period, ZERO), ZERO) + max(gp_cashflows.get(period, ZERO), ZERO))
        for period in year_one_periods
    )
    total_equity_contributed = _negative_total(lp_cashflows) + _negative_total(gp_cashflows)
    if total_equity_contributed <= ZERO:
        return ZERO
    return _q((year_one_distributions / total_equity_contributed) * HUNDRED)


def _append_period_cashflow(period_cashflows: dict[int, Decimal], period: int, amount: Decimal) -> None:
    period_cashflows[period] = _q(period_cashflows.get(period, ZERO) + amount)


def _positive_total(period_cashflows: dict[int, Decimal]) -> Decimal:
    return _q(sum((max(amount, ZERO) for amount in period_cashflows.values()), ZERO))


def _negative_total(period_cashflows: dict[int, Decimal]) -> Decimal:
    return _q(sum((-amount for amount in period_cashflows.values() if amount < ZERO), ZERO))


def _is_debt_module(module: CapitalModule) -> bool:
    return _enum_value(module.funder_type) in DEBT_FUNDER_TYPES


def _is_equity_module(module: CapitalModule) -> bool:
    return _enum_value(module.funder_type) in EQUITY_FUNDER_TYPES


def _is_gp_equity_module(module: CapitalModule) -> bool:
    return _enum_value(module.funder_type) == FunderType.common_equity.value


def _is_lp_equity_module(module: CapitalModule) -> bool:
    return _is_equity_module(module) and not _is_gp_equity_module(module)


def _enum_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _to_decimal(value: Any, default: Decimal = ZERO) -> Decimal:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


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


def _percent(value: Any, default: Decimal = ZERO) -> Decimal:
    amount = _to_decimal(value, default)
    return _q(amount / HUNDRED)


def _q(value: Decimal) -> Decimal:
    return _to_decimal(value).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


__all__ = ["compute_waterfall"]
