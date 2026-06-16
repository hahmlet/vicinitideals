"""Portfolios + saved-filters sub-router (Phase 2a split from ui.py).

Routes: /portfolios, /portfolios/{id}, /ui/portfolios/*, /ui/deals/search,
        /api/saved-filters
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DBSession
from app.config import settings
from app.models.deal import Deal, Scenario, DealStatus
from app.models.portfolio import Portfolio, PortfolioProject
from app.models.project import Project
from app.api.routers.ui_helpers import (
    _apply_org_scope,
    _base_ctx,
    _build_portfolio_gantt,
    _first_opportunity,
    _get_counts,
    _get_user,
    _primary_scenario,
    templates,
)

router = APIRouter(include_in_schema=False)

# ---------------------------------------------------------------------------
# Portfolios
# ---------------------------------------------------------------------------


@router.get("/portfolios", response_class=HTMLResponse)
async def portfolios_page(
    request: Request,
    session: DBSession,
) -> HTMLResponse:
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)

    portfolios_stmt = (
        select(Portfolio)
        .options(
            selectinload(Portfolio.portfolio_projects)
                .selectinload(PortfolioProject.opportunity),
            selectinload(Portfolio.portfolio_projects)
                .selectinload(PortfolioProject.scenario)
                .selectinload(Scenario.operational_outputs),
        )
        .order_by(Portfolio.created_at.desc())
    )
    portfolios_stmt = _apply_org_scope(portfolios_stmt, user, Portfolio)
    portfolios_result = await session.execute(portfolios_stmt)
    portfolios = list(portfolios_result.scalars().unique())

    # Build summary row per portfolio
    portfolio_rows = []
    for p in portfolios:
        deal_count = len(p.portfolio_projects)
        irr_values = [
            float(pp.scenario.operational_outputs.project_irr_levered)
            for pp in p.portfolio_projects
            if pp.scenario and pp.scenario.operational_outputs
            and pp.scenario.operational_outputs.project_irr_levered is not None
        ]
        avg_irr = sum(irr_values) / len(irr_values) if irr_values else None
        portfolio_rows.append({
            "id": str(p.id),
            "name": p.name,
            "deal_count": deal_count,
            "avg_irr": avg_irr,
            "created_at_fmt": p.created_at.strftime("%b %-d, %Y") if p.created_at else None,
        })

    return templates.TemplateResponse(
        request, "portfolios.html",
        {
            "portfolios": portfolio_rows,
            **_base_ctx(user, dedup_count, "portfolios", conflicts_count=conflicts_count),
        },
    )


@router.get("/ui/deals/search", response_class=HTMLResponse)
async def deals_search(
    request: Request,
    session: DBSession,
    q: str = Query(default=""),
) -> HTMLResponse:
    """HTMX deal search — returns an <ul> of results for portfolio add-deal picker."""
    if not q or len(q) < 2:
        return HTMLResponse("")
    user = await _get_user(session, request)
    stmt = (
        select(Deal)
        .where(Deal.name.ilike(f"%{q}%"), Deal.status != DealStatus.archived)
        .order_by(Deal.name)
        .limit(8)
    )
    stmt = _apply_org_scope(stmt, user, Deal)
    results = list((await session.execute(stmt)).scalars())
    if not results:
        return HTMLResponse('<li style="padding:8px 12px;color:var(--text-muted);font-size:13px">No deals found</li>')
    items = "".join(
        f'<li style="padding:8px 12px;cursor:pointer;font-size:13px;border-bottom:1px solid var(--border)" '
        f'onclick="document.getElementById(\'deal-id-input\').value=\'{deal.id}\'; '
        f'document.getElementById(\'deal-search-display\').value=\'{deal.name.replace(chr(39), chr(39)+chr(39))}\'; '
        f'document.getElementById(\'deal-search-results\').innerHTML=\'\'">'
        f'{deal.name}</li>'
        for deal in results
    )
    return HTMLResponse(items)


@router.post("/ui/portfolios/create", response_class=HTMLResponse)
async def create_portfolio(
    request: Request,
    session: DBSession,
) -> HTMLResponse:
    form = await request.form()
    name = str(form.get("name", "")).strip()
    if not name:
        return HTMLResponse("<p class='text-muted'>Portfolio name is required.</p>", status_code=400)

    user = await _get_user(session, request)
    org_id = user.org_id if user else None
    if org_id is None:
        return HTMLResponse(
            "<p class='text-muted'>No organization on your account. Complete account setup first.</p>",
            status_code=403,
        )

    p = Portfolio(org_id=org_id, name=name)
    session.add(p)
    await session.commit()
    return RedirectResponse(url=f"/portfolios/{p.id}", status_code=303)


@router.get("/portfolios/{portfolio_id}", response_class=HTMLResponse)
async def portfolio_detail(
    request: Request,
    portfolio_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)

    portfolio = await session.get(
        Portfolio,
        portfolio_id,
        options=[
            selectinload(Portfolio.portfolio_projects)
                .selectinload(PortfolioProject.opportunity),
            selectinload(Portfolio.portfolio_projects)
                .selectinload(PortfolioProject.scenario)
                .selectinload(Scenario.operational_outputs),
        ],
    )
    if portfolio is None:
        return HTMLResponse("<p class='text-muted'>Portfolio not found.</p>", status_code=404)
    if settings.org_isolation_enabled:
        user_org_id = getattr(user, "org_id", None) if user is not None else None
        if user_org_id is None or portfolio.org_id != user_org_id:
            return HTMLResponse("<p class='text-muted'>Portfolio not found.</p>", status_code=404)

    # Build deal summary rows
    deal_rows = []
    for pp in portfolio.portfolio_projects:
        out = pp.scenario.operational_outputs if pp.scenario else None
        deal_rows.append({
            "opportunity_id": str(pp.project_id),
            "opportunity_name": pp.opportunity.name if pp.opportunity else "—",
            "scenario_id": str(pp.scenario_id) if pp.scenario_id else None,
            "scenario_name": pp.scenario.name if pp.scenario else None,
            "noi": float(out.noi_stabilized) if out and out.noi_stabilized is not None else None,
            "irr": float(out.project_irr_levered) if out and out.project_irr_levered is not None else None,
            "equity_required": float(out.equity_required) if out and out.equity_required is not None else None,
        })

    # Build Gantt — find Deals whose scenarios/projects reference these opportunity IDs
    opp_ids = [pp.project_id for pp in portfolio.portfolio_projects if pp.project_id]
    gantt_rows: list[dict] = []
    if opp_ids:
        deals_stmt = (
            select(Deal)
            .join(Scenario, Scenario.deal_id == Deal.id)
            .join(Project, Project.scenario_id == Scenario.id)
            .where(Project.opportunity_id.in_(opp_ids))
            .options(
                selectinload(Deal.scenarios).selectinload(Scenario.projects).selectinload(Project.milestones),
                selectinload(Deal.scenarios).selectinload(Scenario.projects).selectinload(Project.opportunity),
            )
            .distinct()
        )
        deals_for_gantt = list((await session.execute(deals_stmt)).scalars().unique())

        # Match each pp opportunity → Deal, build entries list
        entries = []
        for deal in deals_for_gantt:
            opp = _first_opportunity(deal)
            if opp is None or opp.id not in opp_ids:
                continue
            scenario = _primary_scenario(deal)
            entries.append((deal.name, scenario.name if scenario else "", deal))

        gantt_data = _build_portfolio_gantt(entries)

    # Aggregate stats
    irr_values = [r["irr"] for r in deal_rows if r["irr"] is not None]
    equity_values = [r["equity_required"] for r in deal_rows if r["equity_required"] is not None]
    noi_values = [r["noi"] for r in deal_rows if r["noi"] is not None]

    return templates.TemplateResponse(
        request, "portfolio_detail.html",
        {
            "portfolio": portfolio,
            "portfolio_id": str(portfolio.id),
            "portfolio_name": portfolio.name,
            "deal_rows": deal_rows,
            "gantt_data": gantt_data,
            "stats": {
                "deal_count": len(deal_rows),
                "avg_irr": sum(irr_values) / len(irr_values) if irr_values else None,
                "total_equity": sum(equity_values) if equity_values else None,
                "total_noi": sum(noi_values) if noi_values else None,
            },
            **_base_ctx(user, dedup_count, "portfolios", conflicts_count=conflicts_count),
        },
    )


@router.post("/ui/portfolios/{portfolio_id}/add-deal", response_class=HTMLResponse)
async def portfolio_add_deal(
    request: Request,
    portfolio_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Add a deal (by Deal.id) to a portfolio."""
    form = await request.form()
    deal_id_raw = str(form.get("deal_id", "")).strip()
    try:
        deal_id = UUID(deal_id_raw)
    except ValueError:
        return HTMLResponse("<p class='text-muted'>Invalid deal ID.</p>", status_code=400)

    # Resolve opportunity + active scenario from the Deal
    deal = await session.get(
        Deal, deal_id,
        options=[
            selectinload(Deal.scenarios).selectinload(Scenario.projects),
        ],
    )
    if deal is None:
        return HTMLResponse("<p class='text-muted'>Deal not found.</p>", status_code=404)

    active_scenario = _primary_scenario(deal)
    _first_proj = active_scenario.projects[0] if active_scenario and active_scenario.projects else None
    if _first_proj is None or _first_proj.opportunity_id is None:
        return HTMLResponse("<p class='text-muted'>Deal has no linked opportunity.</p>", status_code=400)

    # Upsert — skip if opportunity already in portfolio
    existing = (await session.execute(
        select(PortfolioProject).where(
            PortfolioProject.portfolio_id == portfolio_id,
            PortfolioProject.project_id == _first_proj.opportunity_id,
        )
    )).scalar_one_or_none()

    if existing is None:
        pp = PortfolioProject(
            portfolio_id=portfolio_id,
            project_id=_first_proj.opportunity_id,
            scenario_id=active_scenario.id if active_scenario else None,
        )
        session.add(pp)
    await session.commit()

    return RedirectResponse(url=f"/portfolios/{portfolio_id}", status_code=303)


@router.post("/ui/portfolios/{portfolio_id}/remove-deal", response_class=HTMLResponse)
async def portfolio_remove_deal(
    request: Request,
    portfolio_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    from sqlalchemy import delete as sa_delete
    form = await request.form()
    opp_id_raw = str(form.get("opportunity_id", "")).strip()
    try:
        opp_id = UUID(opp_id_raw)
    except ValueError:
        return HTMLResponse("<p class='text-muted'>Invalid opportunity ID.</p>", status_code=400)

    await session.execute(
        sa_delete(PortfolioProject).where(
            PortfolioProject.portfolio_id == portfolio_id,
            PortfolioProject.project_id == opp_id,
        )
    )
    await session.commit()
    return RedirectResponse(url=f"/portfolios/{portfolio_id}", status_code=303)


# ── Saved Filters ────────────────────────────────────────────────────────────
# Per-user, per-page named filter snapshots used by the Listings/
# Opportunities/Deals filter bars. Stored as the URL query string the page
# already speaks, so loading a saved filter == redirect to /<page>?<query>
# and the URL itself is shareable.

_SAVED_FILTER_PAGES = {"listings", "opportunities", "deals"}


def _saved_filter_landing(page: str) -> str:
    """Map a filter-form page key back to the URL the saved filter loads against."""
    return {
        "listings": "/listings",
        "opportunities": "/opportunities",
        "deals": "/deals",
    }.get(page, "/")


@router.get("/api/saved-filters")
async def list_saved_filters(
    request: Request,
    session: DBSession,
    page: str = Query(...),
) -> dict:
    """List the current user's saved filters for one page."""
    from app.models.saved_filter import SavedFilter
    user = await _get_user(session, request)
    if user is None or page not in _SAVED_FILTER_PAGES:
        return {"items": []}
    rows = list((await session.execute(
        select(SavedFilter)
        .where(SavedFilter.user_id == user.id, SavedFilter.page == page)
        .order_by(SavedFilter.name)
    )).scalars())
    base = _saved_filter_landing(page)
    return {
        "items": [
            {
                "id": str(r.id),
                "name": r.name,
                "url": f"{base}?{r.query_string}" if r.query_string else base,
                "query_string": r.query_string,
            }
            for r in rows
        ]
    }


@router.post("/api/saved-filters")
async def create_saved_filter(
    request: Request,
    session: DBSession,
) -> dict:
    """Create or rename-overwrite a saved filter for the current user."""
    from app.models.saved_filter import SavedFilter
    user = await _get_user(session, request)
    if user is None:
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    form = await request.form()
    page = str(form.get("page", "")).strip()
    name = str(form.get("name", "")).strip()[:120]
    query_string = str(form.get("query_string", "")).strip()
    if page not in _SAVED_FILTER_PAGES or not name:
        return JSONResponse({"detail": "Missing page or name"}, status_code=400)

    existing = (await session.execute(
        select(SavedFilter).where(
            SavedFilter.user_id == user.id,
            SavedFilter.page == page,
            SavedFilter.name == name,
        )
    )).scalar_one_or_none()
    if existing:
        existing.query_string = query_string
        existing.updated_at = datetime.now(UTC)
        row = existing
    else:
        row = SavedFilter(
            user_id=user.id,
            page=page,
            name=name,
            query_string=query_string,
        )
        session.add(row)
    await session.commit()
    base = _saved_filter_landing(page)
    return {
        "id": str(row.id),
        "name": row.name,
        "url": f"{base}?{row.query_string}" if row.query_string else base,
    }


@router.delete("/api/saved-filters/{filter_id}")
async def delete_saved_filter(
    request: Request,
    filter_id: UUID,
    session: DBSession,
) -> dict:
    from app.models.saved_filter import SavedFilter
    user = await _get_user(session, request)
    if user is None:
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    row = await session.get(SavedFilter, filter_id)
    if row is None or row.user_id != user.id:
        return JSONResponse({"detail": "Not found"}, status_code=404)
    await session.delete(row)
    await session.commit()
    return {"ok": True}
