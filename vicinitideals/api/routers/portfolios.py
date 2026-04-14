"""Portfolio list, creation, summary, and gantt endpoints."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload

from vicinitideals.api.deps import DBSession
from vicinitideals.models.cashflow import CashFlow, PeriodType
from vicinitideals.models.deal import DealModel, OperationalInputs
from vicinitideals.models.project import Project
from vicinitideals.models.org import Organization
from vicinitideals.models.portfolio import GanttEntry, GanttPhase, Portfolio, PortfolioProject
from vicinitideals.schemas.portfolio import GanttEntryRead, PortfolioCreate, PortfolioRead

router = APIRouter(tags=["portfolios"])

ZERO = Decimal("0")
PHASE_SEQUENCE: tuple[PeriodType, ...] = (
    PeriodType.acquisition,
    PeriodType.hold,
    PeriodType.pre_construction,
    PeriodType.minor_renovation,
    PeriodType.major_renovation,
    PeriodType.conversion,
    PeriodType.construction,
    PeriodType.lease_up,
    PeriodType.stabilized,
    PeriodType.exit,
)
PHASE_START_KEYS: dict[PeriodType, tuple[str, ...]] = {
    PeriodType.acquisition: ("acquisition_start", "start_date", "close_date"),
    PeriodType.hold: ("hold_start",),
    PeriodType.pre_construction: ("pre_construction_start",),
    PeriodType.minor_renovation: ("construction_start",),
    PeriodType.major_renovation: ("construction_start",),
    PeriodType.conversion: ("construction_start",),
    PeriodType.construction: ("construction_start",),
    PeriodType.lease_up: ("lease_up_start",),
    PeriodType.stabilized: ("stabilized_start",),
    PeriodType.exit: ("exit_date",),
}
PHASE_ORDER = {phase.value: index for index, phase in enumerate(PHASE_SEQUENCE)}


@router.get("/portfolios", response_model=list[PortfolioRead])
async def list_portfolios(
    session: DBSession,
    response: Response,
    org_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[PortfolioRead]:
    total_stmt = select(func.count()).select_from(Portfolio)
    if org_id is not None:
        total_stmt = total_stmt.where(Portfolio.org_id == org_id)

    total_count = int((await session.execute(total_stmt)).scalar_one())
    response.headers["X-Total-Count"] = str(total_count)

    project_counts = (
        select(
            PortfolioProject.portfolio_id.label("portfolio_id"),
            func.count(PortfolioProject.project_id).label("project_count"),
        )
        .group_by(PortfolioProject.portfolio_id)
        .subquery()
    )

    stmt = (
        select(
            Portfolio,
            func.coalesce(project_counts.c.project_count, 0).label("project_count"),
        )
        .outerjoin(project_counts, project_counts.c.portfolio_id == Portfolio.id)
        .order_by(Portfolio.created_at.desc(), Portfolio.name.asc())
        .limit(limit)
        .offset(offset)
    )
    if org_id is not None:
        stmt = stmt.where(Portfolio.org_id == org_id)

    result = await session.execute(stmt)
    rows = result.all()
    return [
        PortfolioRead.model_validate(
            {
                "id": portfolio.id,
                "org_id": portfolio.org_id,
                "name": portfolio.name,
                "created_at": portfolio.created_at,
                "project_count": int(project_count or 0),
            }
        )
        for portfolio, project_count in rows
    ]


@router.post("/portfolios", response_model=PortfolioRead, status_code=status.HTTP_201_CREATED)
async def create_portfolio(payload: PortfolioCreate, session: DBSession) -> Portfolio:
    organization = await session.get(Organization, payload.org_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    portfolio = Portfolio(**payload.model_dump())
    session.add(portfolio)
    await session.flush()
    await session.refresh(portfolio)
    return portfolio


@router.get("/portfolios/{portfolio_id}/summary")
async def get_portfolio_summary(portfolio_id: UUID, session: DBSession) -> dict[str, Any]:
    portfolio = await session.get(Portfolio, portfolio_id)
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    portfolio_projects = await _load_portfolio_projects(session, portfolio_id)
    gantt_entries = list(
        (
            await session.execute(select(GanttEntry).where(GanttEntry.portfolio_id == portfolio_id))
        ).scalars()
    )

    total_capital = ZERO
    total_project_cost = ZERO
    total_equity_required = ZERO
    total_noi_stabilized = ZERO
    project_rollups: list[dict[str, Any]] = []

    for portfolio_project in portfolio_projects:
        total_capital += _decimal_or_zero(portfolio_project.capital_contribution)

        deal_model = await _resolve_portfolio_deal_model(session, portfolio_project)
        outputs = deal_model.operational_outputs if deal_model is not None else None

        total_project_cost += _decimal_or_zero(
            outputs.total_project_cost if outputs is not None else None
        )
        total_equity_required += _decimal_or_zero(
            outputs.equity_required if outputs is not None else None
        )
        total_noi_stabilized += _decimal_or_zero(
            outputs.noi_stabilized if outputs is not None else None
        )
        project_rollups.append(
            {
                "project_id": portfolio_project.project_id,
                "project_name": portfolio_project.opportunity.name,
                "deal_model_id": deal_model.id if deal_model is not None else None,
                "start_date": portfolio_project.start_date,
                "capital_contribution": portfolio_project.capital_contribution,
                "noi_stabilized": outputs.noi_stabilized if outputs is not None else None,
                "project_irr_levered": (
                    outputs.project_irr_levered if outputs is not None else None
                ),
                "total_project_cost": outputs.total_project_cost if outputs is not None else None,
                "equity_required": outputs.equity_required if outputs is not None else None,
            }
        )

    return {
        "id": str(portfolio.id),
        "name": portfolio.name,
        "org_id": str(portfolio.org_id),
        "project_count": len(portfolio_projects),
        "gantt_entry_count": len(gantt_entries),
        "total_capital_contribution": total_capital,
        "total_project_cost": total_project_cost,
        "total_equity_required": total_equity_required,
        "total_noi_stabilized": total_noi_stabilized,
        "projects": project_rollups,
    }


@router.post("/portfolios/{portfolio_id}/gantt/compute", response_model=list[GanttEntryRead])
async def compute_portfolio_gantt(portfolio_id: UUID, session: DBSession) -> list[GanttEntry]:
    portfolio = await session.get(Portfolio, portfolio_id)
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    portfolio_projects = await _load_portfolio_projects(session, portfolio_id)
    await session.execute(delete(GanttEntry).where(GanttEntry.portfolio_id == portfolio_id))

    entries: list[GanttEntry] = []
    for portfolio_project in portfolio_projects:
        deal_model = await _resolve_portfolio_deal_model(session, portfolio_project)
        if deal_model is None:
            continue

        cash_flows = list(
            (
                await session.execute(
                    select(CashFlow)
                    .where(CashFlow.scenario_id == deal_model.id)
                    .order_by(CashFlow.period.asc())
                )
            ).scalars()
        )
        if not cash_flows:
            continue

        for phase, start_period, end_period in _group_cash_flows_by_phase(cash_flows):
            start_date, end_date = _resolve_phase_dates(
                portfolio_project=portfolio_project,
                inputs=next(
                    (p.operational_inputs for p in sorted(deal_model.projects, key=lambda p: p.created_at) if p.operational_inputs),
                    None
                ),
                phase=phase,
                start_period=start_period,
                end_period=end_period,
            )
            entry = GanttEntry(
                portfolio_id=portfolio_id,
                project_id=portfolio_project.project_id,
                phase=GanttPhase(phase.value),
                start_date=start_date,
                end_date=end_date,
            )
            session.add(entry)
            entries.append(entry)

    await session.flush()
    return sorted(
        entries,
        key=lambda entry: (
            entry.start_date,
            entry.project_id,
            PHASE_ORDER.get(entry.phase, len(PHASE_ORDER)),
        ),
    )


@router.get("/portfolios/{portfolio_id}/gantt", response_model=list[GanttEntryRead])
async def get_portfolio_gantt(portfolio_id: UUID, session: DBSession) -> list[GanttEntry]:
    portfolio = await session.get(Portfolio, portfolio_id)
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    result = await session.execute(
        select(GanttEntry)
        .where(GanttEntry.portfolio_id == portfolio_id)
        .order_by(GanttEntry.start_date.asc(), GanttEntry.end_date.asc())
    )
    return list(result.scalars())


async def _load_portfolio_projects(
    session: DBSession,
    portfolio_id: UUID,
) -> list[PortfolioProject]:
    result = await session.execute(
        select(PortfolioProject)
        .options(
            selectinload(PortfolioProject.opportunity),
            selectinload(PortfolioProject.scenario).selectinload(DealModel.projects).selectinload(Project.operational_inputs),
            selectinload(PortfolioProject.scenario).selectinload(DealModel.operational_outputs),
        )
        .where(PortfolioProject.portfolio_id == portfolio_id)
        .order_by(PortfolioProject.project_id.asc())
    )
    return list(result.scalars())


async def _resolve_portfolio_deal_model(
    session: DBSession,
    portfolio_project: PortfolioProject,
) -> DealModel | None:
    linked_model = portfolio_project.scenario
    if linked_model is not None and linked_model.is_active:
        return linked_model

    result = await session.execute(
        select(DealModel)
        .options(
            selectinload(DealModel.projects).selectinload(Project.operational_inputs),
            selectinload(DealModel.operational_outputs),
        )
        .join(Project, Project.scenario_id == DealModel.id)
        .where(Project.opportunity_id == portfolio_project.project_id)
        .order_by(DealModel.is_active.desc(), DealModel.version.desc(), DealModel.created_at.desc())
    )
    models = list(result.scalars())
    if not models:
        return linked_model

    active_model = next((model for model in models if model.is_active), None)
    if active_model is not None:
        return active_model
    return linked_model or models[0]


def _group_cash_flows_by_phase(cash_flows: list[CashFlow]) -> list[tuple[PeriodType, int, int]]:
    grouped: list[tuple[PeriodType, int, int]] = []
    current_phase: PeriodType | None = None
    start_period = 0
    end_period = 0

    for row in cash_flows:
        phase = _coerce_period_type(row.period_type)
        if phase is None:
            continue
        if current_phase is None:
            current_phase = phase
            start_period = row.period
            end_period = row.period
            continue
        if phase == current_phase:
            end_period = row.period
            continue

        grouped.append((current_phase, start_period, end_period))
        current_phase = phase
        start_period = row.period
        end_period = row.period

    if current_phase is not None:
        grouped.append((current_phase, start_period, end_period))
    return grouped


def _resolve_phase_dates(
    *,
    portfolio_project: PortfolioProject,
    inputs: OperationalInputs | None,
    phase: PeriodType,
    start_period: int,
    end_period: int,
) -> tuple[date, date]:
    milestone_dates = inputs.milestone_dates if inputs is not None else None
    anchor_date = _resolve_anchor_date(portfolio_project.start_date, milestone_dates)

    projected_start = _add_months(anchor_date, start_period)
    projected_end = _month_end(_add_months(anchor_date, end_period))

    milestone_start = _first_milestone_date(milestone_dates, PHASE_START_KEYS.get(phase, ()))
    if phase == PeriodType.acquisition and milestone_start is None:
        milestone_start = anchor_date
    milestone_end = _phase_end_from_milestones(phase, milestone_dates)

    start_date = milestone_start or projected_start
    end_date = milestone_end or projected_end
    if end_date < start_date:
        end_date = start_date
    return start_date, end_date


def _resolve_anchor_date(
    start_date: date | None,
    milestone_dates: dict[str, Any] | None,
) -> date:
    if start_date is not None:
        return start_date
    milestone_start = _first_milestone_date(
        milestone_dates,
        PHASE_START_KEYS[PeriodType.acquisition],
    )
    if milestone_start is not None:
        return milestone_start
    return date.today()


def _phase_end_from_milestones(
    phase: PeriodType,
    milestone_dates: dict[str, Any] | None,
) -> date | None:
    if not milestone_dates:
        return None
    if phase == PeriodType.exit:
        return _first_milestone_date(milestone_dates, PHASE_START_KEYS[PeriodType.exit])

    try:
        current_index = PHASE_SEQUENCE.index(phase)
    except ValueError:
        return None

    for later_phase in PHASE_SEQUENCE[current_index + 1 :]:
        boundary = _first_milestone_date(milestone_dates, PHASE_START_KEYS.get(later_phase, ()))
        if boundary is not None:
            return boundary - timedelta(days=1)
    return None


def _first_milestone_date(
    milestone_dates: dict[str, Any] | None,
    keys: tuple[str, ...],
) -> date | None:
    if not milestone_dates:
        return None
    for key in keys:
        parsed = _parse_date(milestone_dates.get(key))
        if parsed is not None:
            return parsed
    return None


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        return None

    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _add_months(base_date: date, months: int) -> date:
    month_index = base_date.month - 1 + months
    year = base_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(base_date.day, monthrange(year, month)[1])
    return date(year, month, day)


def _month_end(value: date) -> date:
    return date(value.year, value.month, monthrange(value.year, value.month)[1])


def _coerce_period_type(value: Any) -> PeriodType | None:
    if isinstance(value, PeriodType):
        return value
    try:
        return PeriodType(str(value))
    except ValueError:
        return None


def _decimal_or_zero(value: Any) -> Decimal:
    if value is None:
        return ZERO
    return Decimal(str(value))
