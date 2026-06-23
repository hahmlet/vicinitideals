"""Deals-pipeline + opportunities sub-router (Phase 2a split from ui.py).

Routes: /deals/new, /deals, /deals/{id}, /ui/deals/*, /opportunities,
        /ui/opportunities/*, /opportunities/{id}
"""
from __future__ import annotations

import uuid as _uuid_mod
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import DBSession
from app.config import settings
from app.models.broker import Broker
from app.models.capital import CapitalModule
from app.models.deal import (
    Deal,
    Scenario,
    DealOpportunity,
    DealStatus,
    IncomeStream,
    OperatingExpenseLine,
    ProjectType,
    Scenario,
    UseLine,
    UseLinePhase,
)
from app.models.milestone import DEFAULT_DURATIONS, Milestone, MilestoneType
from app.models.opportunity import OPPORTUNITY_PROPERTY_TYPES, Opportunity, OpportunityStatus
from app.models.org import Organization, User
from app.models.project import Project
from app.models.scraped_listing import ScrapedListing
from app.settings.resolver import resolve_dev_fee_config
from app.api.routers.ui_helpers import (
    _apply_org_scope,
    _as_list,
    _auto_assign_opportunity_to_project,
    _base_ctx,
    _build_gantt_rows,
    _deal_address,
    _deal_building_description,
    _first_opportunity,
    _get_counts,
    _get_user,
    _primary_scenario,
    _seed_milestones,
    _STATUS_DISPLAY,
    _TYPE_DISPLAY,
    templates,
)

router = APIRouter(include_in_schema=False)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _levered_profit(noi: float | None, dscr: float | None) -> float | None:
    """Annual stabilized profit = NOI − annual operation debt service.

    The engine defines ``DSCR = stabilized NOI / annual operation debt
    service`` (cashflow.py), so debt carry = NOI / DSCR. DSCR is None when a
    scenario carries no operating debt (carry = 0 → profit = NOI); a
    non-positive DSCR leaves profit undefined.
    """
    if noi is None:
        return None
    if dscr is None:
        return noi
    if dscr > 0:
        return noi - noi / dscr
    return None


def _build_deal_row(deal: Deal) -> dict:
    scenario = _primary_scenario(deal)
    opp = _first_opportunity(deal)
    outputs = scenario.operational_outputs if scenario else None
    status_key = str(opp.status.value if opp and hasattr(opp.status, "value") else (opp.status if opp else "active"))
    status_display, status_badge = _STATUS_DISPLAY.get(status_key, ("Unknown", "badge-gray"))
    type_key = str(scenario.project_type.value if scenario and hasattr(scenario.project_type, "value") else (scenario.project_type if scenario else ""))
    return {
        "id": str(deal.id),
        "name": deal.name,
        "status": status_key,
        "status_display": status_display,
        "status_badge": status_badge,
        "type_display": _TYPE_DISPLAY.get(type_key, "—") if scenario else "—",
        "primary_model_name": scenario.name if scenario else None,
        "primary_model_id": str(scenario.id) if scenario else None,
        "address": _deal_address(deal),
        "building_description": _deal_building_description(deal),
        "noi": float(outputs.noi_stabilized) if outputs and outputs.noi_stabilized is not None else None,
        "profit": _levered_profit(
            float(outputs.noi_stabilized) if outputs and outputs.noi_stabilized is not None else None,
            float(outputs.dscr) if outputs and outputs.dscr is not None else None,
        ),
        "irr": float(outputs.project_irr_levered) if outputs and outputs.project_irr_levered is not None else None,
        "equity_multiple": None,  # TODO: load from SensitivityResult (needs join)
        "last_updated_fmt": deal.created_at.strftime("%b %-d, %Y") if deal.created_at else None,
    }


async def _gap_adj_by_scenario(
    session: DBSession, scenario_ids: list[UUID]
) -> dict[UUID, dict]:
    """Batch-compute the live Sources/Uses gap + adjustment flag per scenario.

    Gap = Σ committed source principal (CapitalModuleProject amounts) −
    Σ UseLine.amount (excluding exit-phase lines, *including* the negative
    Purchase-Price gap-adjustment phantom). Signed so a funding shortfall
    reads as a negative number; rounded to whole dollars so float noise
    doesn't register as a phantom gap. Mirrors the Underwriting "Sources
    Gap" KPI (sign-flipped) so the deals-list column reconciles with the
    per-deal panel.

    ``has_adj`` is True when any Gap Adjustment phantom row (Purchase Price,
    Revenue, OpEx, or NOI) carries a nonzero amount on the scenario's
    projects — drives cell coloring: yellow when adjusted, red when a gap
    remains with no adjustments, green when fully funded and unadjusted.

    One batched query per axis — avoids the per-project N+1 of
    ``_get_gap_adjustment_amounts``/``_has_any_gap_adjustment`` across a list.
    """
    from app.models.capital import CapitalModuleProject
    from app.schemas.gap_adjustment_names import (
        NOI_ADJUSTMENT_LABEL,
        OPEX_ADJUSTMENT_LABEL,
        PURCHASE_PRICE_ADJUSTMENT_LABEL,
        REVENUE_ADJUSTMENT_LABEL,
    )

    out: dict[UUID, dict] = {}
    if not scenario_ids:
        return out
    _zero = Decimal("0")

    # Σ Uses by scenario (exclude exit phase, mirror rollup_summary).
    uses_by_scn: dict[UUID, Decimal] = {}
    uses_rows = (
        await session.execute(
            select(Project.scenario_id, UseLine.amount, UseLine.phase)
            .join(Project, Project.id == UseLine.project_id)
            .where(Project.scenario_id.in_(scenario_ids))
        )
    ).all()
    for scn_id, amt, phase in uses_rows:
        if str(getattr(phase, "value", phase) or "") == UseLinePhase.exit.value:
            continue
        uses_by_scn[scn_id] = uses_by_scn.get(scn_id, _zero) + Decimal(str(amt or 0))

    # Σ committed source principal by scenario.
    src_by_scn: dict[UUID, Decimal] = {}
    src_rows = (
        await session.execute(
            select(
                CapitalModule.scenario_id,
                func.coalesce(func.sum(CapitalModuleProject.amount), 0),
            )
            .join(
                CapitalModuleProject,
                CapitalModuleProject.capital_module_id == CapitalModule.id,
            )
            .where(CapitalModule.scenario_id.in_(scenario_ids))
            .group_by(CapitalModule.scenario_id)
        )
    ).all()
    for scn_id, total in src_rows:
        src_by_scn[scn_id] = Decimal(str(total or 0))

    # Scenarios carrying any nonzero Gap Adjustment phantom row.
    adj_scn: set[UUID] = set()
    adj_scn.update(
        (
            await session.execute(
                select(Project.scenario_id)
                .join(UseLine, UseLine.project_id == Project.id)
                .where(
                    Project.scenario_id.in_(scenario_ids),
                    UseLine.label == PURCHASE_PRICE_ADJUSTMENT_LABEL,
                    UseLine.amount != 0,
                )
            )
        ).scalars()
    )
    adj_scn.update(
        (
            await session.execute(
                select(Project.scenario_id)
                .join(IncomeStream, IncomeStream.project_id == Project.id)
                .where(
                    Project.scenario_id.in_(scenario_ids),
                    IncomeStream.label == REVENUE_ADJUSTMENT_LABEL,
                    IncomeStream.amount_fixed_monthly.isnot(None),
                    IncomeStream.amount_fixed_monthly != 0,
                )
            )
        ).scalars()
    )
    adj_scn.update(
        (
            await session.execute(
                select(Project.scenario_id)
                .join(OperatingExpenseLine, OperatingExpenseLine.project_id == Project.id)
                .where(
                    Project.scenario_id.in_(scenario_ids),
                    OperatingExpenseLine.label.in_(
                        [OPEX_ADJUSTMENT_LABEL, NOI_ADJUSTMENT_LABEL]
                    ),
                    OperatingExpenseLine.annual_amount != 0,
                )
            )
        ).scalars()
    )

    for scn_id in scenario_ids:
        net = src_by_scn.get(scn_id, _zero) - uses_by_scn.get(scn_id, _zero)
        out[scn_id] = {"gap": float(round(net)), "has_adj": scn_id in adj_scn}
    return out


async def _build_deal_rows(session: DBSession, loaded_deals: list[Deal]) -> list[dict]:
    """Build deal-row dicts and attach the live ``gap_adj`` + ``gap_has_adj``.

    Gap data is loaded in one batched pass keyed by primary-scenario id so the
    deals list stays a fixed number of queries regardless of row count.
    """
    rows = [_build_deal_row(d) for d in loaded_deals]
    scn_of_row: list[UUID | None] = []
    scn_ids: list[UUID] = []
    for d in loaded_deals:
        scn = _primary_scenario(d)
        sid = scn.id if scn else None
        scn_of_row.append(sid)
        if sid is not None:
            scn_ids.append(sid)
    gap_map = await _gap_adj_by_scenario(session, scn_ids)
    for row, sid in zip(rows, scn_of_row):
        info = gap_map.get(sid) if sid is not None else None
        row["gap_adj"] = info["gap"] if info else None
        row["gap_has_adj"] = bool(info["has_adj"]) if info else False
    return rows


# Maps UI filter value → DB enum. Statuses not in this map (under_contract, closed)
# don't exist in the DB yet — selecting them returns 0 results intentionally.
_STATUS_DB_MAP = {
    "evaluation": OpportunityStatus.hypothetical,
    "execution": OpportunityStatus.active,
}
_VALID_STATUS_FILTERS = {"evaluation", "execution", "under_contract", "closed"}


async def _load_deals(
    session: DBSession,
    status_filter=None,
    type_filter=None,
    model_filter=None,
    q: str = "",
    include_archived: bool = False,
    hide_test: bool = False,
    user: User | None = None,
) -> list[Deal]:
    """Load Deals with their Scenarios and linked Opportunities for the deals page."""
    stmt = (
        select(Deal)
        .options(
            selectinload(Deal.scenarios)
                .selectinload(Scenario.projects)
                .selectinload(Project.opportunity),
            selectinload(Deal.scenarios).selectinload(Scenario.operational_outputs),
        )
        .order_by(Deal.created_at.desc())
    )

    stmt = _apply_org_scope(stmt, user, Deal)

    if not include_archived:
        stmt = stmt.where(Deal.status != DealStatus.archived)

    if hide_test:
        # NULL-safe: a row with no name is NOT a test fixture. Without coalesce,
        # ~NULL.ilike(...) evaluates to NULL and the row is silently excluded —
        # which hid every Crexi opportunity (all have NULL name).
        _hn = func.coalesce(Deal.name, "")
        stmt = stmt.where(
            ~_hn.ilike("%e2e%") &
            ~_hn.op("~*")(r"phase\s+\w+\s+test\s+\w+")
        )

    if q:
        stmt = stmt.where(Deal.name.ilike(f"%{q}%"))

    result = await session.execute(stmt)
    deals = list(result.scalars().unique())

    statuses = _as_list(status_filter)
    if statuses:
        known = [s for s in statuses if s in _STATUS_DB_MAP]
        targets = {_STATUS_DB_MAP[s] for s in known}
        if targets:
            # Deals with no linked opportunity cannot be filtered by status — keep them.
            # Deals with a linked opportunity are kept only if their opp_status matches.
            deals = [
                d for d in deals
                if _first_opportunity(d) is None or _first_opportunity(d).opp_status in targets
            ]
        # If none of the selected status values map to DB values, no filtering is applied.

    model_filters = _as_list(model_filter)
    has_primary = "has" in model_filters
    no_primary = "none" in model_filters
    if has_primary and not no_primary:
        deals = [d for d in deals if _primary_scenario(d) is not None]
    elif no_primary and not has_primary:
        deals = [d for d in deals if _primary_scenario(d) is None]

    types = _as_list(type_filter)
    if types:
        deals = [
            d for d in deals
            if _primary_scenario(d) is None or str(getattr(_primary_scenario(d).project_type, "value", _primary_scenario(d).project_type)) in types
        ]

    return deals



@router.get("/deals/new", response_class=HTMLResponse)
async def deals_new_page(
    request: Request,
    session: DBSession,
    opp_id: str = Query(default=""),
    from_opp: str = Query(default=""),
    from_listing: str = Query(default=""),
    clone_of: str = Query(default=""),
    proforma_task_id: str = Query(default=""),
) -> HTMLResponse:
    """Single landing page for creating a new deal.

    Query params carry context from upstream entry points so every "Create
    Deal" button across the app funnels through this one URL:

    - ``?from_opp=<opportunity_id>`` (alias: ``?opp_id=``) — pre-fill name +
      asking-price from a linked Opportunity. Submit creates a new Scenario
      linked to that Opportunity.
    - ``?from_listing=<scraped_listing_id>`` — pre-fill from a ScrapedListing.
      The listing is promoted into an Opportunity at submit time.
    - ``?clone_of=<scenario_id>`` — pre-fill from an existing Scenario.
      Submit clones the source's Projects, UseLines, IncomeStreams,
      ExpenseLines, CapitalModules, WaterfallTiers, etc. while re-applying
      current org Type 1 defaults.
    """
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    ctx = _base_ctx(user, dedup_count, "deals", conflicts_count=conflicts_count)

    # Normalize ``opp_id`` (legacy) → ``from_opp``. Both supported during the
    # transition period; from_opp wins if both are set.
    effective_opp_id = (from_opp or opp_id).strip()

    pre_name: str = ""
    pre_acquisition_cost: float | None = None
    pre_deal_type: str = "acquisition"
    banner_text: str = ""
    context_kind: str = "blank"  # one of: blank | from_opp | from_listing | clone_of

    if clone_of:
        try:
            _src = await session.get(Scenario, UUID(clone_of))
        except ValueError:
            _src = None
        if _src is not None:
            context_kind = "clone_of"
            pre_name = f"{_src.name} (Copy)"
            pre_deal_type = getattr(_src.project_type, "value", _src.project_type) or "acquisition"
            banner_text = f"Cloning from: {_src.name}"
    elif from_listing:
        try:
            _listing = await session.get(
                ScrapedListing, UUID(from_listing),
                options=[selectinload(ScrapedListing.broker)],
            )
        except ValueError:
            _listing = None
        if _listing is not None:
            context_kind = "from_listing"
            pre_name = _listing.address_normalized or _listing.address_raw or "Unnamed Listing Deal"
            if _listing.asking_price is not None and float(_listing.asking_price) > 0:
                pre_acquisition_cost = float(_listing.asking_price)
            banner_text = f"From listing: {pre_name}"
    elif effective_opp_id:
        try:
            _opp = await session.get(Opportunity, UUID(effective_opp_id))
        except ValueError:
            _opp = None
        if _opp is not None:
            context_kind = "from_opp"
            pre_name = _opp.name or ""
            if _opp.asking_price is not None and _opp.asking_price > 0:
                pre_acquisition_cost = float(_opp.asking_price)
            banner_text = f"Linked to opportunity: {pre_name}"

    # Load scenario templates for the template picker
    from app.models.scenario_template import ScenarioTemplate as _ST
    _templates_for_picker = []
    if user is not None and user.org_id is not None:
        _templates_for_picker = list((await session.execute(
            select(_ST)
            .where(_ST.org_id == user.org_id)
            .order_by(_ST.created_at.desc())
        )).scalars())

    ctx.update({
        "context_kind": context_kind,
        "banner_text": banner_text,
        "from_opp": effective_opp_id if context_kind == "from_opp" else "",
        "from_listing": from_listing if context_kind == "from_listing" else "",
        "clone_of": clone_of if context_kind == "clone_of" else "",
        "pre_name": pre_name,
        "pre_acquisition_cost": pre_acquisition_cost,
        "pre_deal_type": pre_deal_type,
        # Legacy template variable kept for safety; new template prefers pre_acquisition_cost.
        "opp_id": effective_opp_id,
        "opp_name": pre_name,
        "opp_asking_price": pre_acquisition_cost,
        "proforma_task_id": proforma_task_id.strip(),
        "scenario_templates": _templates_for_picker,
    })
    return templates.TemplateResponse(request, "deals_new.html", ctx)


@router.get("/deals", response_class=HTMLResponse)
async def deals_page(
    request: Request,
    session: DBSession,
    q: str = Query(default=""),
    status: list[str] = Query(default=[]),
    type: list[str] = Query(default=[]),
    model: list[str] = Query(default=[]),
    include_archived: str = Query(default=""),
    hide_test: str = Query(default=""),
) -> HTMLResponse:
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)

    archived = include_archived == "1"
    # Default hide_test ON for admin users when not explicitly set
    is_admin = user is not None and bool(getattr(user, "is_admin", False))
    effective_hide_test = (hide_test == "1") if hide_test != "" else is_admin
    loaded_deals = await _load_deals(
        session, status, type, model, q, archived, effective_hide_test, user=user
    )
    deals = await _build_deal_rows(session, loaded_deals)

    total_stmt = _apply_org_scope(
        select(func.count()).select_from(Deal).where(Deal.status != DealStatus.archived),
        user, Deal,
    )
    total_count = int((await session.execute(total_stmt)).scalar_one())

    archived_stmt = _apply_org_scope(
        select(func.count()).select_from(Deal).where(Deal.status == DealStatus.archived),
        user, Deal,
    )
    archived_count = int((await session.execute(archived_stmt)).scalar_one())

    irr_values = [d["irr"] for d in deals if d["irr"] is not None]
    avg_irr = sum(irr_values) / len(irr_values) if irr_values else None
    equity_values = [d["noi"] for d in deals if d.get("noi") is not None]  # use NOI as pipeline proxy
    # pipeline_value = total equity required across deals with outputs
    equity_req_values: list[float] = []
    for loaded_deal in loaded_deals:
        scenario = _primary_scenario(loaded_deal)
        if scenario and scenario.operational_outputs and scenario.operational_outputs.equity_required is not None:
            equity_req_values.append(float(scenario.operational_outputs.equity_required))
    pipeline_value = sum(equity_req_values) if equity_req_values else None

    return templates.TemplateResponse(
        request,
        "deals.html",
        {
            "deals": deals,
            "total_count": total_count,
            "archived_count": archived_count,
            "include_archived": archived,
            "hide_test": effective_hide_test,
            "q": q,
            "status": status,
            "deal_type": type,
            "model_filter": model,
            "stats": {
                "pipeline_count": total_count,
                "avg_irr": avg_irr,
                "pipeline_value": pipeline_value,
                "no_model_count": sum(1 for d in deals if not d["primary_model_name"]),
            },
            **_base_ctx(user, dedup_count, "deals", conflicts_count=conflicts_count),
        },
    )


@router.get("/ui/deals/rows", response_class=HTMLResponse)
async def deals_rows(
    request: Request,
    session: DBSession,
    q: str = Query(default=""),
    status: list[str] = Query(default=[]),
    type: list[str] = Query(default=[]),
    model: list[str] = Query(default=[]),
    include_archived: str = Query(default=""),
    hide_test: str = Query(default=""),
) -> HTMLResponse:
    user = await _get_user(session, request)
    archived = include_archived == "1"
    loaded_deals = await _load_deals(
        session, status, type, model, q, archived, hide_test == "1", user=user
    )
    deals = await _build_deal_rows(session, loaded_deals)
    return templates.TemplateResponse(request, "partials/deals_rows.html", {"deals": deals})


@router.post("/ui/deals/create", response_class=HTMLResponse)
async def create_deal(
    request: Request,
    session: DBSession,
    new: str = Query(default=""),
) -> HTMLResponse:
    """Unified deal-creation entry point. All non-clone deal creations land here.

    Form hidden fields carry context from /deals/new:
      - ``opportunity_id`` — link to an existing Opportunity (from-opp path)
      - ``listing_id``    — promote a ScrapedListing into an Opportunity
                            (from-listing path); falls back to acquisition_cost
                            taken from the listing if the form omits it.

    Existing-Opportunity path: links to that Opportunity.
    From-listing path: promotes the listing to org-scoped Opportunity.
    Blank: creates a new manual Opportunity from the form name.

    Clone path uses POST /ui/deals/{deal_id}/variant — separate handler
    because of its deep-copy semantics.
    """
    form = await request.form()
    name = str(form.get("name", "")).strip()
    deal_type_raw = str(form.get("deal_type", "acquisition")).strip()
    org_id_raw = str(form.get("org_id", "")).strip()
    opp_id_raw = str(form.get("opportunity_id", "")).strip()
    listing_id_raw = str(form.get("listing_id", "")).strip()
    acq_cost_raw = str(form.get("acquisition_cost", "")).strip()
    proforma_task_id_raw = str(form.get("proforma_task_id", "")).strip()
    template_id_raw = str(form.get("template_id", "")).strip()

    user = await _get_user(session, request)

    # ── Listing-promotion path: resolve the ScrapedListing first so it can
    # feed defaults into name + acq_cost when the form omits them.
    listing: ScrapedListing | None = None
    if listing_id_raw:
        try:
            listing = await session.get(
                ScrapedListing, UUID(listing_id_raw),
                options=[selectinload(ScrapedListing.broker)],
            )
        except ValueError:
            listing = None
        if listing is None:
            return HTMLResponse("<p class='text-muted'>Listing not found.</p>", status_code=404)
        # Enforce listing has a real asking price — without it the seeded
        # Acquisition UseLine lands at $0 and downstream debt sizing produces
        # gaps that can't be reconciled later.
        if not listing.asking_price or float(listing.asking_price) <= 0:
            return HTMLResponse(
                "<p class='text-muted'>This listing has no asking price. "
                "Set a price on the listing first, or create the deal manually "
                "from <a href='/deals/new'>Deals → New</a>.</p>",
                status_code=400,
            )
        # Listing-derived defaults when form fields are blank.
        if not name:
            name = listing.address_normalized or listing.address_raw or "Unnamed Listing Deal"
        if not acq_cost_raw:
            acq_cost_raw = str(listing.asking_price)

    if not name:
        return HTMLResponse("<p class='text-muted'>Deal name is required.</p>", status_code=400)

    # Required: acquisition_cost > 0. Same invariant as the Add-Project flow —
    # the seeded UseLine must have a real value or downstream debt sizing
    # silently produces gaps that can't be reconciled by a later edit.
    try:
        acq_cost = Decimal(acq_cost_raw) if acq_cost_raw else Decimal("0")
    except (InvalidOperation, ValueError):
        return HTMLResponse(
            "<p class='text-muted'>Invalid acquisition cost.</p>", status_code=400,
        )
    if acq_cost <= 0:
        return HTMLResponse(
            "<p class='text-muted'>Acquisition cost must be greater than zero.</p>",
            status_code=400,
        )

    # Resolve org_id: form value → user's org → first org
    org_id = None
    if org_id_raw:
        try:
            org_id = UUID(org_id_raw)
        except ValueError:
            pass
    if org_id is None and user is not None:
        org_id = user.org_id
    if org_id is None:
        return HTMLResponse(
            "<p class='text-muted'>No organization on your account. Complete account setup first.</p>",
            status_code=403,
        )

    try:
        deal_type = ProjectType(deal_type_raw)
    except ValueError:
        deal_type = ProjectType.acquisition

    # Resolve / create Opportunity. Three paths:
    #   1. opportunity_id form field → link existing
    #   2. listing_id form field → promote the ScrapedListing
    #   3. blank → create a fresh manual Opportunity from the form name
    opportunity: Opportunity | None = None
    if opp_id_raw:
        try:
            opportunity = await session.get(Opportunity, UUID(opp_id_raw))
        except ValueError:
            pass

    if opportunity is None and listing is not None:
        # ScrapedListing IS the Opportunity (single-table inheritance) —
        # check for an existing Deal linked via Scenario→Project before
        # creating a duplicate.
        existing_listing_deal = (await session.execute(
            select(Deal)
            .join(Scenario, Scenario.deal_id == Deal.id)
            .join(Project, Project.scenario_id == Scenario.id)
            .where(Project.opportunity_id == listing.id)
            .limit(1)
        )).scalar_one_or_none()
        if existing_listing_deal is not None:
            return RedirectResponse(url=f"/deals/{existing_listing_deal.id}", status_code=303)
        opportunity = listing
        if not opportunity.org_id:
            opportunity.org_id = org_id
            opportunity.opp_status = OpportunityStatus.active.value
            if not opportunity.name:
                opportunity.name = name
            await session.flush()

    _opportunity_is_new = False
    if opportunity is None:
        _opportunity_is_new = True
        opportunity = Opportunity(
            org_id=org_id,
            name=name,
            opp_status=OpportunityStatus.active.value,
            source="manual",
            source_id=_uuid_mod.uuid4().hex,
            source_url="",
            created_by_user_id=user.id if user else None,
        )
        session.add(opportunity)
        await session.flush()
    else:
        await session.flush()

    # Deal → Scenario (financial plan) → Project → Opportunity
    top_deal = Deal(
        org_id=org_id,
        name=name,
        created_by_user_id=user.id if user else None,
    )
    session.add(top_deal)
    await session.flush()

    from app.services.scenario_factory import create_scenario as _create_scenario
    scenario, dev_project, _ = await _create_scenario(
        session=session,
        deal_id=top_deal.id,
        deal_type=deal_type,
        user_id=user.id if user else None,
        org_id=org_id,
        opportunity_id=opportunity.id,
    )

    await _auto_assign_opportunity_to_project(opportunity, dev_project, session)
    for milestone in _seed_milestones(dev_project, deal_type):
        session.add(milestone)

    # Seed the Acquisition UseLine with the user-confirmed cost. Pre-fill
    # in the form pulls from the linked listing's asking_price; user can
    # override with their underwriting price before submit.
    session.add(UseLine(
        project_id=dev_project.id,
        label=f"{opportunity.name or 'Property'} - Acquisition",
        phase=UseLinePhase.acquisition,
        cost_category="acquisition",
        dev_fee_basis_bucket="acquisition",
        amount=acq_cost,
        timing_type="first_day",
    ))

    from app.services.vehicle_preload import preload_equity_modules
    await preload_equity_modules(session, scenario.id, org_id, project_id=dev_project.id)

    # Auto Developer Fee — engine recomputes $ each pass; user overrides %
    # in the Use drawer. Set pct=0 to effectively disable for this deal.
    if user is not None:
        dev_fee_cfg = await resolve_dev_fee_config(
            user.id, org_id, deal_type, session
        )
        if str(dev_fee_cfg["enabled"]).lower() == "true":
            try:
                _pct = Decimal(dev_fee_cfg["pct"])
            except (InvalidOperation, TypeError):
                _pct = Decimal("0")
            _phase_str = dev_fee_cfg["phase"]
            try:
                _phase_enum = UseLinePhase(_phase_str)
            except ValueError:
                _phase_enum = UseLinePhase.construction
            session.add(UseLine(
                project_id=dev_project.id,
                label="Developer Fee",
                phase=_phase_enum,
                cost_category="soft",
                amount=Decimal("0"),
                timing_type=dev_fee_cfg["timing"],
                is_auto_dev_fee=True,
                dev_fee_pct=_pct,
                dev_fee_basis=dev_fee_cfg["basis"],
            ))

    await session.commit()

    # Apply scenario template if one was selected
    if template_id_raw:
        try:
            _tmpl_id = UUID(template_id_raw)
            from app.models.scenario_template import ScenarioTemplate as _STCreate
            _tmpl = await session.get(_STCreate, _tmpl_id)
            if _tmpl and _tmpl.org_id == org_id:
                from app.exporters.template_apply import apply_template_to_project
                async with session.begin_nested():
                    await apply_template_to_project(session, _tmpl.template_json, dev_project.id)
                await session.commit()
        except Exception:
            pass  # template application failure should not block deal creation

    # Single-flow wizard: land directly inside the wizard chrome at the timeline
    # step. The user never sees the full builder UI until they finish the
    # setup wizard. Builder route reads wizard=1 to hide sidebar/topbar and
    # the approve-timeline handler reads _wizard to route into setup.
    redirect_url = f"/models/{scenario.id}/builder?module=timeline&wizard=1"
    if new == "1":
        redirect_url += "&new=1"
    if proforma_task_id_raw:
        # Stash in Redis so the deal-setup wizard can auto-load the preflight
        # even after multiple redirects. Key is consumed when the wizard loads.
        import redis as _redis  # type: ignore
        _r2 = _redis.from_url(settings.redis_url, decode_responses=True)
        _r2.set(
            f"proforma:scenario:{scenario.id}:email_task_id",
            proforma_task_id_raw,
            ex=7 * 86_400,
        )
    return RedirectResponse(url=redirect_url, status_code=303)


@router.get("/deals/{deal_id}", response_class=HTMLResponse)
async def deal_detail(
    request: Request,
    deal_id: UUID,
    session: DBSession,
    tab: str = Query(default="overview"),
    error: str = Query(default=""),
) -> HTMLResponse:
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)

    deal = await session.get(
        Deal,
        deal_id,
        options=[
            selectinload(Deal.scenarios).selectinload(Scenario.operational_outputs),
            selectinload(Deal.scenarios).selectinload(Scenario.projects).selectinload(Project.milestones),
            selectinload(Deal.scenarios).selectinload(Scenario.projects).selectinload(Project.opportunity),
        ],
    )
    if deal is None:
        return HTMLResponse("<p class='text-muted'>Deal not found.</p>", status_code=404)
    if settings.org_isolation_enabled:
        user_org_id = getattr(user, "org_id", None) if user is not None else None
        if user_org_id is None or deal.org_id != user_org_id:
            return HTMLResponse("<p class='text-muted'>Deal not found.</p>", status_code=404)

    opportunity = _first_opportunity(deal)

    # Financial models (Scenarios) for this Deal
    models = []
    for scenario in deal.scenarios:
        out = scenario.operational_outputs
        type_key = str(scenario.project_type.value if hasattr(scenario.project_type, "value") else scenario.project_type)
        first_proj = scenario.projects[0] if scenario.projects else None
        models.append({
            "id": str(scenario.id),
            "name": scenario.name,
            "version": scenario.version,
            "is_active": scenario.is_active,
            "type_display": _TYPE_DISPLAY.get(type_key, type_key),
            "project_name": first_proj.name if first_proj else "—",
            "project_id": str(first_proj.id) if first_proj else None,
            "noi": float(out.noi_stabilized) if out and out.noi_stabilized is not None else None,
            "irr": float(out.project_irr_levered) if out and out.project_irr_levered is not None else None,
            "equity_required": float(out.equity_required) if out and out.equity_required is not None else None,
            "created_at_fmt": scenario.created_at.strftime("%b %-d, %Y") if scenario.created_at else None,
        })
    models.sort(key=lambda m: (0 if m["is_active"] else 1, -m["version"]))

    # Build Gantt data from milestones across all scenarios/projects
    gantt_data = _build_gantt_rows(deal)

    # Status comes from the linked Opportunity (pipeline stage)
    status_key = str(opportunity.status.value if opportunity and hasattr(opportunity.status, "value") else (opportunity.status if opportunity else "active"))
    status_display, status_badge = _STATUS_DISPLAY.get(status_key, ("Unknown", "badge-gray"))

    return templates.TemplateResponse(
        request,
        "deal_detail.html",
        {
            "deal": deal,
            "deal_id": str(deal.id),
            "deal_name": deal.name,
            "opp": opportunity,
            "opp_id": str(opportunity.id) if opportunity else "",
            "opp_name": opportunity.name if opportunity else "",
            "status_key": status_key,
            "status_display": status_display,
            "status_badge": status_badge,
            "models": models,
            "gantt_data": gantt_data,
            "active_tab": tab,
            "primary_model_id": models[0]["id"] if models else None,
            "flash_error": error,
            **_base_ctx(user, dedup_count, "deals", conflicts_count=conflicts_count),
        },
    )


@router.post("/ui/deals/{deal_id}/archive", response_class=HTMLResponse)
async def archive_deal(
    request: Request,
    deal_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    user = await _get_user(session, request)
    deal = await session.get(Deal, deal_id)
    if deal is not None and (user is None or deal.org_id == user.org_id):
        deal.status = DealStatus.archived
        await session.flush()
    loaded_deals = await _load_deals(session, user=user)
    deals = await _build_deal_rows(session, loaded_deals)
    return templates.TemplateResponse(request, "partials/deals_rows.html", {"deals": deals})


@router.post("/ui/deals/{deal_id}/update", response_class=HTMLResponse)
async def update_deal(
    request: Request,
    deal_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    user = await _get_user(session, request)
    form = await request.form()
    name = str(form.get("name", "")).strip()

    deal = await session.get(
        Deal,
        deal_id,
        options=[
            selectinload(Deal.scenarios).selectinload(Scenario.projects).selectinload(Project.opportunity),
        ],
    )
    if deal is None or (user is not None and deal.org_id != user.org_id):
        return HTMLResponse("<p class='text-muted'>Not found.</p>", status_code=404)

    if name:
        deal.name = name
    # Pipeline stage (opp_status) is intentionally NOT updated here. Renaming
    # must only rename — earlier versions of this handler accepted a `status`
    # field, but the rename form sourced it from Opportunity.status (the
    # scraped-listing status), not opp_status, and silently corrupted the
    # pipeline stage on every rename.
    if "status" in form:
        status_raw = str(form.get("status", "")).strip()
        opp = _first_opportunity(deal)
        if opp is not None and status_raw in {"hypothetical", "active", "archived"}:
            opp.opp_status = status_raw
    await session.commit()
    return RedirectResponse(url=f"/deals/{deal_id}", status_code=303)


# ── Opportunities ─────────────────────────────────────────────────────────────

@router.get("/opportunities", response_class=HTMLResponse)
async def opportunities_page(
    request: Request,
    session: DBSession,
) -> HTMLResponse:
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    jur_rows = await session.execute(
        select(func.lower(Opportunity.jurisdiction), func.lower(Opportunity.county))
        .where(Opportunity.jurisdiction.isnot(None))
        .where(Opportunity.jurisdiction != "")
        .distinct()
        .order_by(func.lower(Opportunity.jurisdiction), func.lower(Opportunity.county))
    )
    seen_jur: set[str] = set()
    jurisdiction_options: list[dict[str, str]] = []
    for jur, county in jur_rows:
        if not jur or not jur.strip():
            continue
        if jur == "unincorporated":
            county_part = (county or "").strip()
            value = f"unincorporated_{county_part}" if county_part else "unincorporated"
            label = f"Unin. {county_part.title()}" if county_part else "Unincorporated"
        else:
            value, label = jur, jur.title()
        if value not in seen_jur:
            seen_jur.add(value)
            jurisdiction_options.append({"value": value, "label": label})
    jurisdiction_options.sort(key=lambda x: x["label"])
    is_admin = user is not None and bool(getattr(user, "is_admin", False))
    return templates.TemplateResponse(request, "opportunities.html", {
        "request": request,
        "jurisdiction_options": jurisdiction_options,
        "hide_test_default": is_admin,
        "property_types": OPPORTUNITY_PROPERTY_TYPES,
        **_base_ctx(user, dedup_count, "opportunities", conflicts_count=conflicts_count),
    })


# ── Opportunities sub-table HTMX endpoints ────────────────────────────────────

def _filter_opps(opps: list, q: str) -> list:
    if not q:
        return opps
    q_lower = q.lower()
    return [
        o for o in opps
        if q_lower in (o.name or "").lower()
        or q_lower in (o.listing_name or "").lower()
        or q_lower in (o.address_normalized or "").lower()
        or q_lower in (o.street or "").lower()
        or q_lower in (o.apn or "").lower()
    ]


def _apply_opp_filters(
    stmt: object,
    favorited: int,
    jurisdiction: list[str],
    min_units: int | None,
    max_units: int | None,
    property_type: list[str],
    hide_test: bool = False,
) -> object:
    if hide_test:
        # NULL-safe: a row with no name is NOT a test fixture. Without coalesce,
        # ~NULL.ilike(...) evaluates to NULL and the row is silently excluded —
        # which hid every Crexi opportunity (all have NULL name).
        _hn = func.coalesce(Opportunity.name, "")
        stmt = stmt.where(
            ~_hn.ilike("%e2e%") &
            ~_hn.op("~*")(r"phase\s+\w+\s+test\s+\w+")
        )
    if favorited:
        stmt = stmt.where(Opportunity.is_favorited.is_(True))
    if jurisdiction:
        plain, compound = [], []
        for j in jurisdiction:
            if j.startswith("unincorporated_"):
                compound.append(j[len("unincorporated_"):])
            else:
                plain.append(j.lower())
        clauses = []
        if plain:
            clauses.append(func.lower(Opportunity.jurisdiction).in_(plain))
        for county_part in compound:
            clauses.append(
                and_(
                    func.lower(Opportunity.jurisdiction) == "unincorporated",
                    func.lower(Opportunity.county) == county_part,
                )
            )
        if clauses:
            stmt = stmt.where(or_(*clauses))
    if min_units is not None:
        stmt = stmt.where(Opportunity.units >= min_units)
    if max_units is not None:
        stmt = stmt.where(Opportunity.units <= max_units)
    if property_type:
        stmt = stmt.where(func.lower(Opportunity.property_type).in_([p.lower() for p in property_type]))
    return stmt


@router.get("/ui/opportunities/rows/deals", response_class=HTMLResponse)
async def opportunities_rows_deals(
    request: Request,
    session: DBSession,
    q: str = Query(default=""),
    favorited: int = Query(default=0),
    jurisdiction: list[str] = Query(default=[]),
    min_units: int | None = Query(default=None),
    max_units: int | None = Query(default=None),
    property_type: list[str] = Query(default=[]),
    hide_test: str = Query(default=""),
) -> HTMLResponse:
    user = await _get_user(session, request)
    active_oppo_ids = select(Project.opportunity_id).where(
        Project.opportunity_id.isnot(None)
    )
    stmt = (
        select(Opportunity)
        .where(
            Opportunity.id.in_(active_oppo_ids),
            Opportunity.archived.is_(False),
        )
        .order_by(Opportunity.last_seen_at.desc())
    )
    stmt = _apply_org_scope(stmt, user, Opportunity)
    stmt = _apply_opp_filters(stmt, favorited, jurisdiction, min_units, max_units, property_type, hide_test == "1")
    opps = _filter_opps(list((await session.execute(stmt)).scalars().unique()), q)
    return templates.TemplateResponse(request, "partials/opportunities_rows.html", {
        "request": request, "opps": opps, "table": "deals",
    })


@router.get("/ui/opportunities/rows/offmarket", response_class=HTMLResponse)
async def opportunities_rows_offmarket(
    request: Request,
    session: DBSession,
    q: str = Query(default=""),
    favorited: int = Query(default=0),
    jurisdiction: list[str] = Query(default=[]),
    min_units: int | None = Query(default=None),
    max_units: int | None = Query(default=None),
    property_type: list[str] = Query(default=[]),
    hide_test: str = Query(default=""),
) -> HTMLResponse:
    active_oppo_ids = select(Project.opportunity_id).where(
        Project.opportunity_id.isnot(None)
    )
    stmt = (
        select(Opportunity)
        .where(
            Opportunity.promotion_source == "manual",
            Opportunity.id.notin_(active_oppo_ids),
            Opportunity.archived.is_(False),
        )
        .order_by(Opportunity.last_seen_at.desc())
    )
    stmt = _apply_opp_filters(stmt, favorited, jurisdiction, min_units, max_units, property_type, hide_test == "1")
    opps = _filter_opps(list((await session.execute(stmt)).scalars().unique()), q)
    return templates.TemplateResponse(request, "partials/opportunities_rows.html", {
        "request": request, "opps": opps, "table": "offmarket",
    })


@router.get("/ui/opportunities/rows/onmarket", response_class=HTMLResponse)
async def opportunities_rows_onmarket(
    request: Request,
    session: DBSession,
    q: str = Query(default=""),
    favorited: int = Query(default=0),
    jurisdiction: list[str] = Query(default=[]),
    min_units: int | None = Query(default=None),
    max_units: int | None = Query(default=None),
    property_type: list[str] = Query(default=[]),
    hide_test: str = Query(default=""),
) -> HTMLResponse:
    active_oppo_ids = select(Project.opportunity_id).where(
        Project.opportunity_id.isnot(None)
    )
    stmt = (
        select(Opportunity)
        .where(
            Opportunity.source.in_(["loopnet", "loopnet_lease", "crexi", "scraper"]),
            Opportunity.id.notin_(active_oppo_ids),
            Opportunity.archived.is_(False),
        )
        .order_by(Opportunity.last_seen_at.desc())
    )
    stmt = _apply_opp_filters(stmt, favorited, jurisdiction, min_units, max_units, property_type, hide_test == "1")
    opps = _filter_opps(list((await session.execute(stmt)).scalars().unique()), q)
    return templates.TemplateResponse(request, "partials/opportunities_rows.html", {
        "request": request, "opps": opps, "table": "onmarket",
    })


@router.patch("/ui/opportunities/{opp_id}/favorite", response_class=HTMLResponse)
async def toggle_opportunity_favorite(
    request: Request,
    session: DBSession,
    opp_id: UUID,
) -> HTMLResponse:
    opp = await session.get(Opportunity, opp_id)
    if opp is None:
        return HTMLResponse("Not found", status_code=404)
    opp.is_favorited = not opp.is_favorited
    await session.commit()
    await session.refresh(opp)
    # Return updated star button only
    starred = "★" if opp.is_favorited else "☆"
    title = "Unfavorite" if opp.is_favorited else "Favorite"
    return HTMLResponse(
        f'<button class="star-btn {"starred" if opp.is_favorited else ""}"'
        f' hx-patch="/ui/opportunities/{opp_id}/favorite"'
        f' hx-target="closest .star-cell"'
        f' hx-swap="innerHTML"'
        f' title="{title}">{starred}</button>'
    )




# ── Opportunity creation wizard ────────────────────────────────────────────────

def _safe_uuid_str(raw: str) -> str:
    """Return raw if it parses as a UUID, else empty string."""
    if not raw:
        return ""
    try:
        UUID(raw)
        return raw
    except ValueError:
        return ""


def _parse_optional_uuid(raw: str) -> UUID | None:
    """Parse a UUID, or return None for blank/invalid input (e.g. a '— None —' pick)."""
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None


def _safe_return_path(raw: str) -> str:
    """Only allow same-origin paths starting with `/` and free of CRLF / scheme.

    Caller-provided redirect target — we filter to prevent open-redirect to an
    attacker-controlled URL.
    """
    if not raw or not raw.startswith("/") or raw.startswith("//"):
        return ""
    if any(ch in raw for ch in ("\r", "\n")):
        return ""
    return raw


async def _broker_options(session: DBSession) -> list[dict]:
    """Brokers as ``{id, label}`` dicts for a manual-opportunity broker picker.

    Eager-loads brokerage so the label can include the firm without a lazy
    load in the template. Ordered by name. ~450 rows — fine for a native
    ``<select>`` (browsers handle thousands and type-to-search works).
    """
    rows = (await session.execute(
        select(Broker)
        .options(selectinload(Broker.brokerage))
        .order_by(Broker.last_name, Broker.first_name)
    )).scalars().unique().all()
    options: list[dict] = []
    for b in rows:
        full = f"{b.last_name or ''}, {b.first_name or ''}".strip(", ").strip() or "Unknown"
        firm = b.brokerage.name if b.brokerage else None
        options.append({"id": str(b.id), "label": f"{full} · {firm}" if firm else full})
    return options


@router.get("/ui/opportunities/wizard", response_class=HTMLResponse)
async def opportunity_wizard_get(
    request: Request,
    session: DBSession,
    step: int = Query(default=1),
    opp_id: str = Query(default=""),
    link_to_deal: str = Query(default=""),
    return_to: str = Query(default=""),
) -> HTMLResponse:
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    opp = None
    if opp_id:
        try:
            opp = await session.get(Opportunity, UUID(opp_id))
        except (ValueError, Exception):
            pass
    ctx = {
        "request": request, "step": step, "opp": opp,
        "opp_id": opp_id,
        "brokers": await _broker_options(session),
        "opp_broker_id": str(opp.broker_id) if opp and opp.broker_id else "",
        "deal_type": request.query_params.get("deal_type", ""),
        "opp_asking_price": "", "opp_notes": "",
        "deal_type_label": "",
        # Carry-through for the "create-from-deal" flow: when the wizard is
        # opened from the Add-Project drawer's empty state, both params are
        # set, threaded through every step's form, and consumed by /complete
        # to link the new opp to the deal and bounce back to the builder.
        "link_to_deal": _safe_uuid_str(link_to_deal),
        "return_to": _safe_return_path(return_to),
        **_base_ctx(user, dedup_count, "opportunities", conflicts_count=conflicts_count),
    }
    return templates.TemplateResponse(request, "opportunity_wizard.html", ctx)


@router.get("/ui/opportunities/wizard/search", response_class=HTMLResponse)
async def opportunity_wizard_search(
    request: Request,
    session: DBSession,
    q: str = Query(default=""),
    opp_id: str = Query(default=""),
) -> HTMLResponse:
    """Step 2 HTMX search - finds a matching scraped Opportunity."""
    if not q or len(q.strip()) < 3:
        return HTMLResponse("")

    q_lower = q.strip().lower()

    # Priority 1: search scraped Opportunities by address or APN
    stmt = (
        select(Opportunity)
        .where(
            Opportunity.source.in_(["loopnet", "loopnet_lease", "crexi", "scraper"]),
            Opportunity.archived.is_(False),
        )
        .order_by(Opportunity.last_seen_at.desc())
        .limit(200)
    )
    candidates = list((await session.execute(stmt)).scalars().unique())
    matched_opp: Opportunity | None = None
    for c in candidates:
        if (
            q_lower in (c.address_normalized or "").lower()
            or q_lower in (c.street or "").lower()
            or q_lower in (c.apn or "").lower()
            or q_lower in (c.name or "").lower()
            or q_lower in (c.listing_name or "").lower()
        ):
            matched_opp = c
            break

    if matched_opp:
        return templates.TemplateResponse(request, "partials/wizard_match_card.html", {
            "request": request,
            "match_type": "listing",
            "match": matched_opp,
            "opp_id": opp_id,
        })

    return HTMLResponse(
        '<div style="color:var(--text-muted);font-size:13px;padding:12px 0">'
        "No match found for that address or APN.</div>"
    )


@router.post("/ui/opportunities/wizard/step", response_class=HTMLResponse)
async def opportunity_wizard_step(
    request: Request,
    session: DBSession,
) -> HTMLResponse:
    form = await request.form()
    step = int(form.get("step", 1))
    opp_id_str = str(form.get("opp_id", "") or "")
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)

    # Carry-through params from the create-from-deal flow.
    _link_to_deal = _safe_uuid_str(str(form.get("link_to_deal", "") or ""))
    _return_to = _safe_return_path(str(form.get("return_to", "") or ""))

    _deal_type_labels = {
        "acquisition": "Acquisition",
        "value_add": "Value-Add",
        "conversion": "Conversion",
        "new_construction": "New Construction",
    }

    if step == 1:
        name = str(form.get("name", "")).strip()
        deal_type = str(form.get("deal_type", "value_add"))
        notes = str(form.get("notes", "") or "").strip()
        broker_id = _parse_optional_uuid(str(form.get("broker_id", "") or "").strip())

        if opp_id_str:
            try:
                opp = await session.get(Opportunity, UUID(opp_id_str))
            except ValueError:
                opp = None
        else:
            opp = None

        if opp is None:
            if user is None or user.org_id is None:
                return HTMLResponse("No organization found", status_code=400)
            opp = Opportunity(
                org_id=user.org_id,
                name=name,
                notes=notes,
                broker_id=broker_id,
                source="manual",
                source_url="",
                promotion_source="manual",
                created_by_user_id=user.id if user else None,
            )
            session.add(opp)
        else:
            opp.name = name
            opp.notes = notes
            opp.broker_id = broker_id

        await session.commit()
        await session.refresh(opp)
        opp_id_str = str(opp.id)

        return templates.TemplateResponse(request, "opportunity_wizard.html", {
            "request": request, "step": 2, "opp": opp,
            "opp_id": opp_id_str,
            "deal_type": deal_type,
            "deal_type_label": _deal_type_labels.get(deal_type, deal_type),
            "link_to_deal": _link_to_deal,
            "return_to": _return_to,
            **_base_ctx(user, dedup_count, "opportunities", conflicts_count=conflicts_count),
        })

    elif step == 2:
        # Step 2: property linking was removed (parcel decommission); the step
        # is now a pass-through that advances to the review screen.
        opp = await session.get(Opportunity, UUID(opp_id_str)) if opp_id_str else None
        if opp is None:
            return HTMLResponse("Opportunity not found", status_code=400)

        deal_type = str(form.get("deal_type", "value_add"))
        return templates.TemplateResponse(request, "opportunity_wizard.html", {
            "request": request, "step": 3, "opp": opp,
            "opp_id": opp_id_str,
            "deal_type": deal_type,
            "deal_type_label": _deal_type_labels.get(deal_type, deal_type),
            "link_to_deal": _link_to_deal,
            "return_to": _return_to,
            **_base_ctx(user, dedup_count, "opportunities", conflicts_count=conflicts_count),
        })

    return HTMLResponse("Invalid step", status_code=400)


@router.post("/ui/opportunities/wizard/complete")
async def opportunity_wizard_complete(
    request: Request,
    session: DBSession,
) -> Response:
    """Finalize opportunity creation — redirect to deal or opportunity detail.

    ``link_to_deal`` is no longer used to create a junction row (DealOpportunity
    was dropped in migration 0067). The opportunity is already linked via
    Scenario→Project→Opportunity. ``return_to`` controls the post-finalize
    landing URL — same-origin paths only; falls back to the opportunity detail.
    """
    form = await request.form()
    opp_id_str = str(form.get("opp_id", "") or "")
    if not opp_id_str:
        return HTMLResponse("Missing opp_id", status_code=400)

    return_to = _safe_return_path(str(form.get("return_to", "") or ""))
    target = return_to or f"/opportunities/{opp_id_str}"
    return RedirectResponse(url=target, status_code=303)


@router.get("/opportunities/{opp_id}", response_class=HTMLResponse)
async def opportunity_detail(
    request: Request,
    opp_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    opp = (await session.execute(
        select(Opportunity)
        .where(Opportunity.id == opp_id)
        .options(
            selectinload(Opportunity.dev_projects).selectinload(Project.scenario),
        )
    )).scalar_one_or_none()
    if opp is None:
        return HTMLResponse("Not found", status_code=404)
    if settings.org_isolation_enabled and opp.org_id is not None:
        user_org_id = getattr(user, "org_id", None) if user is not None else None
        if user_org_id is None or opp.org_id != user_org_id:
            return HTMLResponse("Not found", status_code=404)
    return templates.TemplateResponse(request, "opportunity_detail.html", {
        "request": request, "opp": opp,
        "brokers": await _broker_options(session),
        "opp_broker_id": str(opp.broker_id) if opp.broker_id else "",
        **_base_ctx(user, dedup_count, "opportunities", conflicts_count=conflicts_count),
    })


@router.post("/ui/opportunities/{opp_id}/archive")
async def archive_opportunity(
    opp_id: UUID,
    session: DBSession,
) -> RedirectResponse:
    """Archive a manually-created opportunity (sets archived=True, keeps all data)."""
    opp = await session.get(Opportunity, opp_id)
    if opp is None:
        return RedirectResponse("/opportunities", status_code=303)
    opp.archived = True
    opp.opp_status = OpportunityStatus.archived.value
    await session.commit()
    return RedirectResponse("/opportunities", status_code=303)


@router.post("/ui/opportunities/{opp_id}/set-broker", response_class=HTMLResponse)
async def set_opportunity_broker(
    request: Request,
    opp_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Set/clear the broker on an opportunity. Returns the broker editor partial (HTMX swap)."""
    user = await _get_user(session, request)
    opp = await session.get(Opportunity, opp_id)
    if opp is None:
        return HTMLResponse("Not found", status_code=404)
    if settings.org_isolation_enabled and opp.org_id is not None:
        user_org_id = getattr(user, "org_id", None) if user is not None else None
        if user_org_id is None or opp.org_id != user_org_id:
            return HTMLResponse("Not found", status_code=404)
    form = await request.form()
    opp.broker_id = _parse_optional_uuid(str(form.get("broker_id", "") or "").strip())
    await session.commit()
    return templates.TemplateResponse(request, "partials/opportunity_broker.html", {
        "request": request, "opp": opp,
        "brokers": await _broker_options(session),
        "opp_broker_id": str(opp.broker_id) if opp.broker_id else "",
        "broker_saved": True,
    })


