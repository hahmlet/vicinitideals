"""Underwriting rollup — aggregates per-project engine output into a
Scenario-level view (combined timeline, combined cashflow, deduped Source
package, joined waterfall, combined IRR).

Not to be confused with the pre-existing ``app/engines/underwriting.py``,
which is the legacy deterministic multifamily calculator. This module is
new in Phase 2f and only does post-compute aggregation — no new math, no
new sizing, no new carry.

The cashflow engine has already run per-project (``compute_cash_flows``
in cashflow.py), populating CashFlow / CashFlowLineItem /
OperationalOutputs / DrawSource / WaterfallResult rows with ``project_id``
set. The rollup reads those rows and returns Scenario-level shapes the
UI can render.

Single-project Scenarios short-circuit to the sole project's rows — the
rollup is an identity view, identical to what the per-project output
already shows.

Designed for Phase 3 UI consumption:
  - ``rollup_cashflow(scenario_id, session)`` — summed CF by period
  - ``rollup_draws(scenario_id, session)`` — draw rows grouped by Source
  - ``rollup_sources(scenario_id, session)`` — one row per CapitalModule
    with total principal / covered projects
  - ``rollup_waterfall(scenario_id, session)`` — joined distribution rows
    with per-project scope
  - ``rollup_irr(scenario_id, session)`` — combined levered IRR on the
    summed NCF series
  - ``rollup_summary(scenario_id, session)`` — per-project outputs +
    aggregate totals in one payload

All Decimal arithmetic; shares ``_compute_xirr`` with the core engine so
IRR convention matches per-project numbers.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.cashflow import _compute_xirr as _engine_xirr
from app.models.capital import (
    CapitalModule,
    CapitalModuleProject,
    DrawSource,
    WaterfallResult,
    WaterfallTier,
)
from app.models.cashflow import CashFlow, OperationalOutputs

_ZERO = Decimal("0")


async def rollup_cashflow(
    scenario_id: UUID, session: AsyncSession
) -> list[dict[str, Any]]:
    """Sum cashflow rows across projects by (period, period_type).

    For single-project scenarios the SUM is over one row per period — i.e.
    the per-project values surface unchanged.
    """
    result = await session.execute(
        select(
            CashFlow.period,
            CashFlow.period_type,
            func.sum(CashFlow.gross_revenue).label("gross_revenue"),
            func.sum(CashFlow.vacancy_loss).label("vacancy_loss"),
            func.sum(CashFlow.effective_gross_income).label("effective_gross_income"),
            func.sum(CashFlow.operating_expenses).label("operating_expenses"),
            func.sum(CashFlow.capex_reserve).label("capex_reserve"),
            func.sum(CashFlow.noi).label("noi"),
            func.sum(CashFlow.debt_service).label("debt_service"),
            func.sum(CashFlow.net_cash_flow).label("net_cash_flow"),
        )
        .where(CashFlow.scenario_id == scenario_id)
        .group_by(CashFlow.period, CashFlow.period_type)
        .order_by(CashFlow.period)
    )
    return [dict(row._mapping) for row in result]


async def rollup_draws(
    scenario_id: UUID, session: AsyncSession
) -> list[dict[str, Any]]:
    """Return DrawSource rows for the Scenario with project scope intact.

    Shared-Source deduplication is NOT applied yet — Phase 2c1's joint
    draw schedule will emit one row per Source per period with per-project
    balance attribution. For now (1:1 junction), each DrawSource maps 1:1
    to one project.
    """
    result = await session.execute(
        select(DrawSource)
        .where(DrawSource.scenario_id == scenario_id)
        .order_by(DrawSource.sort_order, DrawSource.label)
    )
    rows: list[dict[str, Any]] = []
    for ds in result.scalars():
        rows.append(
            {
                "id": str(ds.id),
                "project_id": str(ds.project_id) if ds.project_id else None,
                "capital_module_id": str(ds.capital_module_id)
                if ds.capital_module_id
                else None,
                "label": ds.label,
                "source_type": ds.source_type,
                "funder_type": ds.funder_type,
                "active_from_milestone": ds.active_from_milestone,
                "active_to_milestone": ds.active_to_milestone,
                "draw_every_n_months": ds.draw_every_n_months,
                "annual_interest_rate": ds.annual_interest_rate,
                "total_commitment": ds.total_commitment,
            }
        )
    return rows


async def rollup_sources(
    scenario_id: UUID, session: AsyncSession
) -> list[dict[str, Any]]:
    """One row per CapitalModule with aggregate principal + covered projects.

    Shared Sources (module attached to >1 projects via junction) collapse to
    one row — the row's ``total_principal`` is the SUM of per-project
    junction amounts; ``covered_project_ids`` lists every project covered.

    For single-project deals today (1:1 backfill) this returns the same
    modules the scenario already had, with ``covered_project_ids`` of
    length one.
    """
    module_rows = list(
        (
            await session.execute(
                select(CapitalModule)
                .where(CapitalModule.scenario_id == scenario_id)
                .order_by(CapitalModule.stack_position)
            )
        ).scalars()
    )

    junction_rows: list[CapitalModuleProject] = []
    if module_rows:
        junction_rows = list(
            (
                await session.execute(
                    select(CapitalModuleProject).where(
                        CapitalModuleProject.capital_module_id.in_(
                            [m.id for m in module_rows]
                        )
                    )
                )
            ).scalars()
        )
    by_module: dict[UUID, list[CapitalModuleProject]] = defaultdict(list)
    for j in junction_rows:
        by_module[j.capital_module_id].append(j)

    out: list[dict[str, Any]] = []
    for m in module_rows:
        terms = by_module.get(m.id, [])
        total = sum((Decimal(str(t.amount or 0)) for t in terms), _ZERO)
        covered = [str(t.project_id) for t in terms]
        src = m.source or {}
        carry = m.carry or {}
        out.append(
            {
                "id": str(m.id),
                "label": m.label,
                "funder_type": str(m.funder_type).replace("FunderType.", ""),
                "stack_position": m.stack_position,
                "total_principal": total,
                "covered_project_ids": covered,
                "covered_project_count": len(covered),
                # True = multi-project / shared-Source. UI uses this to
                # render the "covers: P1, P2" chip and the drill-down that
                # shows per-project carry/IR contribution.
                "is_shared": len(covered) > 1,
                "interest_rate_pct": src.get("interest_rate_pct"),
                "amort_term_years": src.get("amort_term_years"),
                "carry_type": carry.get("carry_type"),
                "active_phase_start": m.active_phase_start,
                "active_phase_end": m.active_phase_end,
            }
        )
    return out


async def rollup_waterfall(
    scenario_id: UUID, session: AsyncSession
) -> list[dict[str, Any]]:
    """Joined waterfall table: every tier result, with its project_id and
    tier metadata. Order: (project_id, period, tier.priority)."""
    tier_rows = list(
        (
            await session.execute(
                select(WaterfallTier).where(WaterfallTier.scenario_id == scenario_id)
            )
        ).scalars()
    )
    tier_meta: dict[UUID, dict[str, Any]] = {
        t.id: {
            "priority": t.priority,
            "tier_type": str(t.tier_type).replace("WaterfallTierType.", ""),
            "description": t.description,
            "project_id": str(t.project_id) if t.project_id else None,
        }
        for t in tier_rows
    }

    wr_rows = list(
        (
            await session.execute(
                select(WaterfallResult)
                .where(WaterfallResult.scenario_id == scenario_id)
                .order_by(WaterfallResult.period)
            )
        ).scalars()
    )

    def _sort_key(r: WaterfallResult) -> tuple[str, int, int]:
        meta = tier_meta.get(r.tier_id, {})
        return (
            str(r.project_id) if r.project_id else "",
            r.period,
            int(meta.get("priority", 999)),
        )

    wr_rows.sort(key=_sort_key)
    out: list[dict[str, Any]] = []
    for r in wr_rows:
        meta = tier_meta.get(r.tier_id, {})
        out.append(
            {
                "project_id": str(r.project_id) if r.project_id else None,
                "period": r.period,
                "tier_id": str(r.tier_id),
                "tier_priority": meta.get("priority"),
                "tier_type": meta.get("tier_type"),
                "capital_module_id": str(r.capital_module_id)
                if r.capital_module_id
                else None,
                "cash_distributed": r.cash_distributed,
                "cumulative_distributed": r.cumulative_distributed,
                "party_irr_pct": r.party_irr_pct,
            }
        )
    return out


async def rollup_irr(scenario_id: UUID, session: AsyncSession) -> Decimal:
    """Combined levered IRR on the summed NCF series across all projects.

    Uses the engine's monthly-periodic XIRR helper so the IRR convention
    matches what per-project ``OperationalOutputs.project_irr_levered``
    reports. Returns Decimal percent (e.g. ``Decimal('12.3456')`` = 12.35%).
    Zero if the series has no sign change.
    """
    result = await session.execute(
        select(CashFlow.period, func.sum(CashFlow.net_cash_flow))
        .where(CashFlow.scenario_id == scenario_id)
        .group_by(CashFlow.period)
        .order_by(CashFlow.period)
    )
    series: list[Decimal] = [Decimal(str(row[1] or 0)) for row in result]
    return _engine_xirr(series)


async def rollup_em(scenario_id: UUID, session: AsyncSession) -> Decimal:
    """Combined equity multiple on the summed NCF series across all projects.

    EM = total equity returned / total equity invested.
    Uses the same NCF series as rollup_irr — positive periods are equity
    distributions, negative periods are equity calls.
    Returns Decimal ratio (e.g. ``Decimal('1.85')`` = 1.85×). Zero if no
    equity was invested.
    """
    result = await session.execute(
        select(CashFlow.period, func.sum(CashFlow.net_cash_flow))
        .where(CashFlow.scenario_id == scenario_id)
        .group_by(CashFlow.period)
        .order_by(CashFlow.period)
    )
    series: list[Decimal] = [Decimal(str(row[1] or 0)) for row in result]
    total_in = sum((abs(v) for v in series if v < _ZERO), _ZERO)
    total_out = sum((v for v in series if v > _ZERO), _ZERO)
    return (total_out / total_in).quantize(Decimal("0.000001")) if total_in > _ZERO else _ZERO


async def rollup_summary(
    scenario_id: UUID, session: AsyncSession
) -> dict[str, Any]:
    """Bundle per-project OperationalOutputs rows with aggregate totals.

    Shape::

        {
            "per_project": [{"project_id": ..., "dscr": ..., ...}, ...],
            "totals": {
                "total_project_cost": Decimal,
                "equity_required": Decimal,
                "combined_irr_pct": Decimal,
            }
        }

    For single-project scenarios ``per_project`` has one element and
    ``totals`` mirror it.
    """
    outputs = list(
        (
            await session.execute(
                select(OperationalOutputs).where(
                    OperationalOutputs.scenario_id == scenario_id
                )
            )
        ).scalars()
    )
    per_project = [
        {
            "project_id": str(o.project_id) if o.project_id else None,
            "total_project_cost": o.total_project_cost,
            "equity_required": o.equity_required,
            "noi_stabilized": o.noi_stabilized,
            "dscr": o.dscr,
            "project_irr_levered": o.project_irr_levered,
            "project_irr_unlevered": o.project_irr_unlevered,
            "cap_rate_on_cost_pct": o.cap_rate_on_cost_pct,
            "debt_yield_pct": o.debt_yield_pct,
            "total_timeline_months": o.total_timeline_months,
        }
        for o in outputs
    ]
    total_tpc = sum(
        (Decimal(str(o.total_project_cost or 0)) for o in outputs), _ZERO
    )
    total_eq = sum(
        (Decimal(str(o.equity_required or 0)) for o in outputs), _ZERO
    )
    # Total Uses across all projects, excluding exit-phase lines. Includes
    # Operating Reserve, Lease-Up Reserve, capitalized-interest stubs —
    # everything the user sees in their per-project S&U panel — so the
    # Sources Gap KPI on Underwriting reconciles cleanly with the per-
    # project gap math (Σ Uses − debt − committed equity).
    from app.models.deal import UseLine
    from app.models.project import Project
    _uses_rows = list(
        (
            await session.execute(
                select(UseLine.amount, UseLine.phase)
                .join(Project, Project.id == UseLine.project_id)
                .where(Project.scenario_id == scenario_id)
            )
        ).all()
    )
    total_uses = _ZERO
    for _amt, _ph in _uses_rows:
        _ph_val = str(getattr(_ph, "value", _ph) or "")
        if _ph_val == "exit":
            continue
        try:
            total_uses += Decimal(str(_amt or 0))
        except Exception:
            pass
    combined_irr = await rollup_irr(scenario_id, session)
    combined_em = await rollup_em(scenario_id, session)
    return {
        "per_project": per_project,
        "totals": {
            "total_project_cost": total_tpc,
            "total_uses": total_uses,
            "equity_required": total_eq,
            "combined_irr_pct": combined_irr,
            "combined_em_x": combined_em,
        },
    }
