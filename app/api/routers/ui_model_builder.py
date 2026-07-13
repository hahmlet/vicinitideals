"""Model builder UI routes — builder page, form handler, panel, sensitivity, project ops."""

from __future__ import annotations

import asyncio
import io
import json
import time
import uuid as _uuid_mod
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlencode
from uuid import UUID

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from starlette.templating import _TemplateResponse
from sqlalchemy import and_, func, literal, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import app as _pkg
from app.api.deps import DBSession
from app.config import settings
from app.models.broker import Broker, Brokerage
from app.models.deal import Scenario, STANDARD_OPEX_CATEGORIES, USE_CATEGORY_LABELS, USE_CATEGORY_PRESETS, USE_COST_CATEGORIES, Deal, Scenario, DealOpportunity, DealStatus, IncomeStream, IncomeStreamType, OperatingExpenseLine, OperationalInputs, ProjectType, UnitMix, UseLine, UseLinePhase
from app.models.ingestion import DedupCandidate, DedupStatus, IngestJob, RecordType, SavedSearchCriteria
from app.models.org import Organization, User
from app.models.capital import CapitalModule, DrawSource, WaterfallTier
from app.models.cashflow import OperationalOutputs
from app.models.portfolio import Portfolio, PortfolioProject
from app.models.milestone import DEFAULT_DURATIONS, Milestone, MilestoneType, MilestoneType as MT
from app.models.opportunity import OPPORTUNITY_PROPERTY_TYPES, Opportunity, OpportunitySource, OpportunityStatus
from app.models.project import Project, ProjectStatus
from app.models.scraped_listing import ScrapedListing
from app.models.realie_usage import RealieUsage
from app.models.settings import UserSetting
from app.scrapers.realie import _current_month
from app.engines.dev_fee import BASIS_BUCKETS, BASIS_BUCKET_KEYS
from app.settings.resolver import resolve_dev_fee_config
from app.api.routers.ui_helpers import (
    _UMRow,
    _active_project_from_request,
    _auto_assign_opportunity_to_project,
    _bars_to_phase_rows,
    _base_ctx,
    _builder_gantt_from_milestones,
    _compute_gantt_axis,
    _extract_milestone_bars,
    _fd,
    _fi,
    _fmt_currency,
    _gantt_apply_pct,
    _get_address_issues_count,
    _get_counts,
    _get_user,
    _override_stabilized_cap,
    _seed_milestones,
    templates,
)
from app.api.routers.ui_model_outputs import (
    _dispatch_proforma_preflight,
    _load_draw_schedule_ctx,
    _milestone_label,
    _run_draw_schedule,
)
from app.api.routers.ui_wizards import _wizard_phases_present


router = APIRouter(include_in_schema=False)


def _ensure_unit_mix_ids(project) -> bool:
    """Backfill missing 'id' fields on unit_mix JSONB rows.

    Legacy rows uploaded before unit_mix had stable IDs end up missing the
    'id' key, which makes the delete handler unable to target them. Assign
    UUIDs in place and mark the JSONB column dirty so the update persists.
    """
    if project is None or not project.unit_mix:
        return False
    from uuid import uuid4 as _u4
    rows = list(project.unit_mix)
    changed = False
    for r in rows:
        if not r.get("id"):
            r["id"] = str(_u4())
            changed = True
    if changed:
        from sqlalchemy.orm.attributes import flag_modified
        project.unit_mix = rows
        flag_modified(project, "unit_mix")
    return changed

# ---------------------------------------------------------------------------
# Model Builder
# ---------------------------------------------------------------------------

def _sum_amount(rows: list) -> float | None:
    if not rows:
        return None
    total = sum(float(r.amount) for r in rows)
    return total if total else None


def _sum_annual(rows: list, field: str = "annual_amount") -> float | None:
    if not rows:
        return None
    total = sum(float(getattr(r, field, 0) or 0) for r in rows)
    return total if total else None


def _income_annual(streams: list) -> float | None:
    """Effective gross annual revenue at stabilization — applies stabilized_occupancy_pct."""
    if not streams:
        return None
    total = 0.0
    for s in streams:
        occupancy = float(s.stabilized_occupancy_pct or 100) / 100.0
        if s.amount_per_unit_monthly and s.unit_count:
            total += float(s.amount_per_unit_monthly) * int(s.unit_count) * occupancy * 12
        elif s.amount_fixed_monthly:
            total += float(s.amount_fixed_monthly) * occupancy * 12
    return total if total else None


def _capital_total(modules: list, junction_amts: dict[str, float] | None = None) -> float | None:
    """Sum module principals. If junction_amts is provided (project-scoped
    view), use the per-project junction amount instead of scenario-level
    source.amount so multi-project Sources totals reflect this project's
    share only."""
    total = 0.0
    for m in modules:
        if m.source and isinstance(m.source, dict):
            if m.source.get("is_bridge"):
                continue
            # float_earnings is Found Money — computed post-sizing, shown separately
            _vt = str(getattr(m, "vehicle_type", "") or "").replace("VehicleType.", "")
            if _vt == "float_earnings":
                continue
            if junction_amts is not None:
                amt = junction_amts.get(str(m.id), 0.0)
            else:
                amt = m.source.get("amount")
            if amt:
                total += float(amt)
    return total if total else None


# ---------------------------------------------------------------------------
# Builder form helpers
# ---------------------------------------------------------------------------

_ITEM_TYPE_TO_MODULE: dict[str, str] = {
    "use-lines": "sources_uses",
    "income-streams": "revenue",
    "expense-lines": "opex",
    "capital-modules": "sources_uses",
    "waterfall-tiers": "owners_profit",
    "milestones": "timeline",
    "unit-mix": "property",
}

# Capital-module Gantt: active_phase_* → ordered candidate (milestone_key,
# side) tuples. side="end" means the phase begins when that milestone
# completes; side="start" when it starts. The first candidate present on the
# deal's timeline wins, so a phase like "construction" resolves against
# whichever work-phase milestone the project actually uses. Keys must stay
# within app.schemas.vocab.ACTIVE_PHASE_KEYS (contract-tested).
_CM_PHASE_TO_MS: dict[str, list[tuple[str, str]]] = {
    "acquisition":          [("close", "end"), ("under_contract", "end"), ("offer_made", "end")],
    "pre_development":      [("pre_development", "start"), ("close", "end")],
    "pre_construction":     [("pre_development", "start"), ("close", "end")],
    "construction":         [
        ("construction", "start"),
        ("minor_renovation", "start"),
        ("major_renovation", "start"),
        ("renovation", "start"),
        ("conversion", "start"),
        ("close", "end"),  # fallback: construction begins right after close
    ],
    "lease_up":             [
        ("operation_lease_up", "start"),
        ("construction", "end"),
        ("minor_renovation", "end"),
        ("major_renovation", "end"),
        ("close", "end"),
    ],
    "operation_lease_up":   [("operation_lease_up", "start")],
    "stabilized":           [
        ("operation_stabilized", "start"),
        ("operation_lease_up", "end"),
    ],
    "operation_stabilized": [("operation_stabilized", "start")],
    "exit":                 [("divestment", "start"), ("operation_stabilized", "end")],
    "divestment":           [("divestment", "start"), ("operation_stabilized", "end")],
    # Legacy value written by the pre-cleanup wizard — treat as "runs
    # through divestment" so the bar renders to the far right.
    "perpetuity":           [("divestment", "start"), ("operation_stabilized", "end")],
}



from app.utils.form_helpers import _fp


async def _per_project_capital_modules_ui(
    session: AsyncSession, scenario_id: UUID, project_id: UUID
) -> list:
    """UI-side equivalent of the engine's ``_per_project_capital_modules``
    — loads CapitalModule rows attached to this project via the junction.
    Duplicated here to avoid cross-package import between UI and engine.
    """
    from app.models.capital import CapitalModuleProject
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


async def _lightweight_project_status_data(
    session: AsyncSession, scenario_id: UUID, project_id: UUID
) -> dict:
    """Minimal per-project data for ``_compute_calc_status``.

    Cheaper than re-running the full ``_load_builder_data`` per project.
    Fetches only the five keys ``_compute_calc_status`` reads: outputs,
    inputs, capital_modules, capital_total, uses_total.
    """
    outputs = (
        await session.execute(
            select(OperationalOutputs).where(
                OperationalOutputs.scenario_id == scenario_id,
                OperationalOutputs.project_id == project_id,
            )
        )
    ).scalar_one_or_none()
    inputs = (
        await session.execute(
            select(OperationalInputs).where(
                OperationalInputs.project_id == project_id
            )
        )
    ).scalar_one_or_none()
    capital_modules = await _per_project_capital_modules_ui(
        session, scenario_id, project_id
    )
    # capital_total must use this project's junction-scoped amount, not the
    # module's source.amount (which holds the scenario-wide last-sized value
    # for shared modules — e.g. P2's $4.3M would show on P1's pill,
    # producing a phantom $1.45M Sources/Uses surplus on P1).
    from app.models.capital import CapitalModuleProject as _CMP_lite
    _junction_by_module = {
        str(mid): float(amt or 0)
        for mid, amt in (
            await session.execute(
                select(_CMP_lite.capital_module_id, _CMP_lite.amount).where(
                    _CMP_lite.project_id == project_id
                )
            )
        ).all()
    }
    capital_total = 0.0
    for cm in capital_modules:
        _jam = _junction_by_module.get(str(cm.id))
        if _jam is not None:
            capital_total += _jam
            continue
        src = cm.source or {}
        amt = src.get("amount")
        if amt is None:
            continue
        try:
            capital_total += float(amt)
        except (TypeError, ValueError):
            continue
    use_lines = list(
        (
            await session.execute(
                select(UseLine).where(UseLine.project_id == project_id)
            )
        ).scalars()
    )
    uses_total = 0.0
    for ul in use_lines:
        if ul.is_deferred:
            continue
        if ul.amount is None:
            continue
        try:
            uses_total += float(ul.amount)
        except (TypeError, ValueError):
            continue
    # Gap Adjustment is a per-project phantom — needed by the Account Balance
    # factor in _compute_calc_status to flip Solvent → yellow when adjustments
    # are masking a real Sources Gap.
    has_gap_adjustment = await _has_any_gap_adjustment(session, project_id)
    return {
        "outputs": outputs,
        "inputs": inputs,
        "capital_modules": capital_modules,
        "capital_total": capital_total,
        "uses_total": uses_total,
        "has_gap_adjustment": has_gap_adjustment,
    }


# Severity ranking for rolling worst-status up from per-project to Underwriting.
_STATUS_RANK = {"ok": 0, "na": 0, "warn": 1, "fail": 2}


async def _compute_scenario_statuses(
    session: AsyncSession, scenario_id: UUID
) -> dict:
    """Per-project status dicts + Underwriting aggregate for tab-chip pills.

    Each per-project status matches the shape ``_compute_calc_status``
    returns (sources_uses / dscr / ltv + overall + failing_count). The
    Underwriting aggregate picks the worst severity across projects and
    sums their failing counts. No cross-project soft rules yet — combined
    DSCR / LTV portfolio checks are informational-only per the Phase 2f
    product decision; a future Phase 3b1 can add dedicated Underwriting-
    only rule rows if needed.
    """
    project_ids = [
        row[0]
        for row in (
            await session.execute(
                select(Project.id)
                .where(Project.scenario_id == scenario_id)
                .order_by(Project.created_at.asc())
            )
        )
    ]

    per_project: dict = {}
    worst_overall = "ok"
    worst_project_id = None
    total_failing = 0
    for pid in project_ids:
        data = await _lightweight_project_status_data(session, scenario_id, pid)
        status = _compute_calc_status(data)
        per_project[pid] = status
        total_failing += int(status.get("failing_count", 0) or 0)
        if _STATUS_RANK.get(status["overall"], 0) > _STATUS_RANK.get(
            worst_overall, 0
        ):
            worst_overall = status["overall"]
            worst_project_id = pid

    return {
        "per_project": per_project,
        "underwriting": {
            "overall": worst_overall,
            "failing_count": total_failing,
            "worst_project_id": worst_project_id,
        },
    }


async def _staleness_map(session: AsyncSession, scenario_id: UUID) -> dict:
    """Compute per-project + scenario-level staleness for tab chips.

    A project is stale iff any of its inputs (project-scoped or scenario-
    scoped) was updated after its ``OperationalOutputs.computed_at``. A
    never-computed project is stale by definition.

    Scenario-level input updates (edits to CapitalModule, WaterfallTier,
    CapitalModuleProject, ProjectAnchor) mark EVERY project on the scenario
    stale, since those tables are shared.

    Returns::

        {
            "per_project": {project_id: bool, ...},
            "underwriting": bool,   # True iff any project is stale
        }

    Migration 0052 added ``updated_at`` to the input tables; for fresh
    installs the initial value is server-default ``now()``, so existing
    deals won't light up as stale until a real edit happens.
    """
    from app.models.capital import CapitalModuleProject as _CMP
    from app.models.deal import Scenario, IncomeStream as _IS, OperatingExpenseLine as _OEL, OperationalInputs as _OI, UseLine as _UL
    from app.models.project import ProjectAnchor as _PA

    # ── Scenario-scoped max(updated_at) — applies to every project on this scenario.
    async def _scalar_max(stmt):
        return (await session.execute(stmt)).scalar_one_or_none()

    scenario_maxes = [
        await _scalar_max(
            select(func.max(CapitalModule.updated_at)).where(
                CapitalModule.scenario_id == scenario_id
            )
        ),
        await _scalar_max(
            select(func.max(WaterfallTier.updated_at)).where(
                WaterfallTier.scenario_id == scenario_id
            )
        ),
        await _scalar_max(
            select(func.max(_CMP.updated_at))
            .join(CapitalModule, CapitalModule.id == _CMP.capital_module_id)
            .where(CapitalModule.scenario_id == scenario_id)
        ),
        await _scalar_max(
            select(func.max(_PA.updated_at))
            .join(Project, Project.id == _PA.project_id)
            .where(Project.scenario_id == scenario_id)
        ),
    ]
    scenario_max = max((t for t in scenario_maxes if t is not None), default=None)

    # Per-project max(updated_at) across project-scoped input tables.
    project_ids = [
        row[0]
        for row in (
            await session.execute(
                select(Project.id).where(Project.scenario_id == scenario_id)
            )
        )
    ]

    per_project: dict = {}
    for pid in project_ids:
        proj_maxes = [
            await _scalar_max(
                select(func.max(_UL.updated_at)).where(_UL.project_id == pid)
            ),
            await _scalar_max(
                select(func.max(_IS.updated_at)).where(_IS.project_id == pid)
            ),
            await _scalar_max(
                select(func.max(_OEL.updated_at)).where(_OEL.project_id == pid)
            ),
            await _scalar_max(
                select(func.max(_OI.updated_at)).where(_OI.project_id == pid)
            ),
                await _scalar_max(
                select(func.max(Milestone.updated_at)).where(Milestone.project_id == pid)
            ),
        ]
        proj_max = max((t for t in proj_maxes if t is not None), default=None)

        computed_at = (
            await session.execute(
                select(OperationalOutputs.computed_at).where(
                    OperationalOutputs.scenario_id == scenario_id,
                    OperationalOutputs.project_id == pid,
                )
            )
        ).scalar_one_or_none()

        if computed_at is None:
            per_project[pid] = True
            continue

        max_input = max(
            (t for t in (proj_max, scenario_max) if t is not None), default=None
        )
        per_project[pid] = bool(max_input is not None and max_input > computed_at)

    return {
        "per_project": per_project,
        "underwriting": any(per_project.values()) if per_project else False,
    }


def _wizard_mode_from_request(request: Request) -> bool:
    """Read the single-flow deal-creation wizard flag off the parent page.

    HTMX form posts in the wizard chrome don't carry the `wizard=1` query
    param themselves, but the browser's current URL (sent in HX-Current-URL)
    does. Used by panel-render endpoints so the timeline approve button text
    and sidebar visibility stay consistent across in-wizard mutations.
    """
    _hx_url = request.headers.get("HX-Current-URL", "")
    if not _hx_url:
        return False
    from urllib.parse import urlparse, parse_qs
    return parse_qs(urlparse(_hx_url).query).get("wizard", [""])[0] == "1"


async def _load_builder_data(session: AsyncSession, model_id: UUID, project_id: UUID | None = None) -> dict:
    """Load all line-item data for the model builder page/panel.

    model_id = Deal.id.  Line items (use_lines, income_streams, expense_lines,
    operational_inputs) belong to the active Project for this Deal.
    Capital modules and waterfall tiers belong to the Deal directly.

    project_id: if provided, load data for that specific Project; else default to first.
    """
    # Load the scenario (Scenario) to access income_mode and deal_id
    _scenario = await session.get(Scenario, model_id)

    # Resolve active Project for this Scenario
    default_project = None
    if project_id is not None:
        candidate = await session.get(Project, project_id)
        if candidate and candidate.scenario_id == model_id:
            default_project = candidate
    if default_project is None:
        default_project = (await session.execute(
            select(Project).where(Project.scenario_id == model_id).order_by(Project.created_at.asc()).limit(1)
        )).scalar_one_or_none()
    project_id = default_project.id if default_project else None
    timeline_approved = default_project.timeline_approved if default_project else False

    # Foolproofing: every project needs an operation_stabilized milestone so
    # reserve windows (IR, ODR, OR) have a deterministic Stabilization anchor.
    # Idempotent; flushes only when the milestone was missing.
    if default_project is not None:
        from app.services.stabilization_milestone import ensure_stabilization_milestone
        await ensure_stabilization_milestone(session, default_project)

    inputs = None
    use_lines: list = []
    income_streams: list = []
    expense_lines: list = []
    unit_mix_rows: list = []

    if project_id is not None:
        inputs = (await session.execute(
            select(OperationalInputs).where(OperationalInputs.project_id == project_id)
        )).scalar_one_or_none()

        use_lines = list((await session.execute(
            select(UseLine).where(UseLine.project_id == project_id).order_by(UseLine.phase, UseLine.label)
        )).scalars())

        income_streams = list((await session.execute(
            select(IncomeStream).where(IncomeStream.project_id == project_id).order_by(IncomeStream.label)
        )).scalars())

        expense_lines = list((await session.execute(
            select(OperatingExpenseLine).where(OperatingExpenseLine.project_id == project_id).order_by(OperatingExpenseLine.label)
        )).scalars())

        # unit_mix is JSONB on Project; wrap dicts for attribute-compatible access
        if default_project is not None and _ensure_unit_mix_ids(default_project):
            await session.flush()
        unit_mix_rows = [_UMRow(r) for r in (default_project.unit_mix or [])] if default_project else []

    # Scope outputs to the active project. Phase 2b's migration 0051
    # swapped UNIQUE(scenario_id) for UNIQUE(scenario_id, project_id), so
    # a scenario may now carry N rows (one per project). scalar_one_or_none
    # without project_id raised MultipleResultsFound on multi-project deals.
    _outputs_q = select(OperationalOutputs).where(
        OperationalOutputs.scenario_id == model_id
    )
    if project_id is not None:
        _outputs_q = _outputs_q.where(OperationalOutputs.project_id == project_id)
    outputs = (await session.execute(_outputs_q.limit(1))).scalar_one_or_none()

    # Carrying annual = avg monthly debt service in stabilized/operations phase × 12.
    # None = never computed; 0.0 = computed but no debt service.
    # Multi-project: filter CashFlow by active project_id so the bottom
    # "Est. Annual Debt Service" reflects this project's service only — not
    # a scenario-wide average that mixes projects together.
    from app.models.cashflow import CashFlow as _CashFlow, PeriodType as _PT

    def _cf_scope(q):
        q = q.where(_CashFlow.scenario_id == model_id)
        if project_id is not None:
            q = q.where(_CashFlow.project_id == project_id)
        return q

    _cf_count = (await session.execute(
        _cf_scope(select(func.count()).select_from(_CashFlow))
    )).scalar_one()
    if _cf_count:
        # Prefer stabilized phase; fall back to any operation phase; last resort = any period
        _ops_avg = (await session.execute(
            _cf_scope(select(func.avg(_CashFlow.debt_service)))
            .where(_CashFlow.period_type == _PT.stabilized)
        )).scalar_one_or_none()
        if _ops_avg is None:
            _ops_avg = (await session.execute(
                _cf_scope(select(func.avg(_CashFlow.debt_service)))
                .where(_CashFlow.period_type.in_([_PT.lease_up, _PT.stabilized]))
            )).scalar_one_or_none()
        if _ops_avg is None:
            _ops_avg = (await session.execute(
                _cf_scope(select(func.avg(_CashFlow.debt_service)))
            )).scalar_one_or_none()
        carrying_annual_computed: float | None = float(_ops_avg) * 12 if _ops_avg else 0.0

        # First stabilized period → profit metrics + run-rate (annualized)
        # revenue/opex.  Run-rate = first stabilized month × 12, the SAME basis
        # as noi_stabilized, so the nav cards' Stabilized column subtracts
        # cleanly: stabilized_revenue − stabilized_opex − carrying = NOI − DS.
        _stab_rows = list((await session.execute(
            _cf_scope(select(
                _CashFlow.net_cash_flow,
                _CashFlow.effective_gross_income,
                _CashFlow.operating_expenses,
            ))
            .where(_CashFlow.period_type == _PT.stabilized)
            .order_by(_CashFlow.period)
        )).all())
        if _stab_rows:
            _stab_ncf = [float(r[0]) for r in _stab_rows]
            stabilized_month1_ncf: float | None = _stab_ncf[0]
            stabilized_year1_ncf: float | None = float(sum(_stab_ncf[:12]))
            stabilized_revenue_annual: float | None = float(_stab_rows[0][1]) * 12
            stabilized_opex_annual: float | None = float(_stab_rows[0][2]) * 12
            # Profit run-rate after debt carry = NOI run-rate − annual debt service.
            profit_runrate_after_debt: float | None = (
                stabilized_revenue_annual
                - stabilized_opex_annual
                - (carrying_annual_computed or 0.0)
            )
        else:
            stabilized_month1_ncf = None
            stabilized_year1_ncf = None
            stabilized_revenue_annual = None
            stabilized_opex_annual = None
            profit_runrate_after_debt = None
    else:
        carrying_annual_computed = None  # not yet computed
        stabilized_month1_ncf = None
        stabilized_year1_ncf = None
        stabilized_revenue_annual = None
        stabilized_opex_annual = None
        profit_runrate_after_debt = None

    # On a single-project tab, show only that project's Sources (the modules
    # attached to it via the junction). Loading every scenario module here made
    # each project tab list all 8 projects' Sources — a ~$54M phantom sum even
    # though the balance pill (junction-scoped) read correct. The aggregate /
    # Combined Pool view (project_id is None) still shows the full stack.
    if project_id is not None:
        capital_modules = await _per_project_capital_modules_ui(
            session, model_id, project_id
        )
    else:
        capital_modules = list((await session.execute(
            select(CapitalModule).where(CapitalModule.scenario_id == model_id).order_by(CapitalModule.stack_position)
        )).scalars())

    # Per-module-per-phase annual debt service for the carrying costs table rows.
    # carrying_detail[module_id_str][phase_name] = annual_amount (float)

    def _annual_carry_amt(source: dict, carry_type: str) -> float:
        amount = source.get("amount")
        rate_pct = source.get("interest_rate_pct")
        if not amount or not rate_pct:
            return 0.0
        principal = float(amount)
        rate = float(rate_pct)
        if carry_type in ("io_only", "interest_reserve"):
            # True IO or pre-funded IR: annual interest cost = principal × rate
            # (IR: reserve pays it; io_only: borrower pays it — same carrying display)
            return principal * rate / 100.0
        elif carry_type == "capitalized_interest":
            # No periodic cash outflow — interest accrues to balance, paid at payoff
            return 0.0
        elif carry_type == "pi":
            r = rate / 100.0 / 12.0
            n = int(source.get("amort_term_years") or 30) * 12
            if r == 0:
                return principal / (n / 12)
            factor = (1 + r) ** n
            return (principal * r * factor / (factor - 1)) * 12
        return 0.0

    # Multi-project: per-row estimate should reflect THIS project's share of
    # the module principal (from the CapitalModuleProject junction), not the
    # scenario-level source.amount (which after auto-size holds the last
    # project's sized value). Fall back to source.amount only when no project
    # is selected (e.g. underwriting rollup view).
    _junction_amts: dict[str, float] = {}
    if project_id is not None:
        from app.models.capital import CapitalModuleProject as _CMP
        _jrows = list((await session.execute(
            select(_CMP.capital_module_id, _CMP.amount).where(_CMP.project_id == project_id)
        )).all())
        _junction_amts = {str(mid): float(amt or 0) for mid, amt in _jrows}

    carrying_detail: dict[str, dict[str, float]] = {}
    for _cm in capital_modules:
        if str(getattr(_cm, "vehicle_type", "") or "").replace("VehicleType.", "") != "debt":
            continue
        _src = dict(_cm.source or {})
        _carry = _cm.carry or {}
        _mid = str(_cm.id)
        if project_id is not None:
            # Override amount with this project's junction share
            _src["amount"] = _junction_amts.get(_mid, 0.0)
        if _carry.get("phases"):
            carrying_detail[_mid] = {
                p.get("name", ""): _annual_carry_amt(_src, p.get("carry_type", "none"))
                for p in _carry["phases"]
            }
        else:
            _ct = _carry.get("carry_type", "none")
            _amt = _annual_carry_amt(_src, _ct)
            carrying_detail[_mid] = {"construction": _amt, "operation": _amt}

    waterfall_tiers = list((await session.execute(
        select(WaterfallTier).where(WaterfallTier.scenario_id == model_id).order_by(WaterfallTier.priority, WaterfallTier.id)
    )).scalars())

    # Milestones for the default dev Project
    milestones: list = []
    if project_id is not None:
        milestones = list((await session.execute(
            select(Milestone)
            .where(Milestone.project_id == project_id)
        )).scalars())

    # Build milestone map for trigger-chain resolution
    _PHASE_ORDER = [
        "offer_made", "under_contract", "close", "pre_development",
        "construction", "operation_lease_up", "operation_stabilized", "divestment",
    ]
    ms_map = {m.id: m for m in milestones}

    # Auto-cap operation_stabilized at 30 years when no divestment milestone exists
    _STABILIZED_AUTO_DAYS = 10950
    _has_divestment = any(
        str(m.milestone_type).replace("MilestoneType.", "") == "divestment"
        for m in milestones
    )
    if not _has_divestment:
        for _m in milestones:
            if (
                str(_m.milestone_type).replace("MilestoneType.", "") == "operation_stabilized"
                and (_m.duration_days or 0) == 0
            ):
                _m.duration_days = _STABILIZED_AUTO_DAYS
                session.add(_m)

    def _phase_idx(m):
        raw = str(m.milestone_type).replace("MilestoneType.", "")
        return next((i for i, v in enumerate(_PHASE_ORDER) if v == raw), 99)

    def _ms_sort_key(m):
        start = m.computed_start(ms_map)
        return (start is None, start or 0, _phase_idx(m))

    milestones = sorted(milestones, key=_ms_sort_key)

    exit_lines = [u for u in use_lines if getattr(u.phase, "value", str(u.phase)) == "exit"]
    deferred_uses = [u for u in use_lines if getattr(u, "is_deferred", False)]
    deferred_total = sum(float(u.amount or 0) for u in deferred_uses)
    revenue_annual = _income_annual(income_streams)
    opex_annual = _sum_annual(expense_lines, "annual_amount")
    _capex_per_unit = float(inputs.capex_reserve_per_unit_annual or 0) if inputs else 0.0
    _total_units_for_reserve = sum((u.unit_count or 0) for u in unit_mix_rows)
    capex_reserve_annual = _capex_per_unit * _total_units_for_reserve
    opex_total_annual = (opex_annual or 0) + capex_reserve_annual
    # Multi-project Sources totals use per-project junction amounts so the
    # panel total doesn't show the scenario-wide (last-sized) principal.
    _cap_junction_amts: dict[str, float] = {}
    if project_id is not None:
        from app.models.capital import CapitalModuleProject as _CMP_sum
        _cap_junction_amts = {
            str(mid): float(amt or 0)
            for mid, amt in (await session.execute(
                select(_CMP_sum.capital_module_id, _CMP_sum.amount).where(
                    _CMP_sum.project_id == project_id
                )
            )).all()
        }
    capital_total = _capital_total(
        capital_modules, junction_amts=_cap_junction_amts if project_id is not None else None
    )
    uses_total_val = sum(float(u.amount or 0) for u in use_lines)
    # Load float_earnings_series for Found Money display in Sources panel.
    _fe_outputs = (
        await session.execute(
            select(OperationalOutputs).where(
                OperationalOutputs.scenario_id == model_id,
                OperationalOutputs.project_id == project_id,
            )
        )
    ).scalar_one_or_none() if project_id is not None else None
    _float_earnings_series: dict = (
        (_fe_outputs.float_earnings_series or {}) if _fe_outputs is not None else {}
    )

    # Equity ownership — computed from equity-type capital modules
    equity_modules = [
        m for m in capital_modules
        if str(getattr(m, "vehicle_type", "") or "").replace("VehicleType.", "") == "equity"
    ]
    _total_equity = sum(
        float((m.source or {}).get("amount", 0) or 0) for m in equity_modules
    )
    equity_ownership = [
        {
            "module": m,
            "amount": float((m.source or {}).get("amount", 0) or 0),
            "pct": (float((m.source or {}).get("amount", 0) or 0) / _total_equity * 100)
                   if _total_equity > 0 else 0.0,
        }
        for m in equity_modules
    ]
    # If no equity partners defined, synthesize a 100% org-owner row
    org_owner_fallback = not equity_ownership

    # Load org name for fallback display
    org_name = "Sponsor"
    try:
        from app.models.org import Organization as _Org
        _scenario_for_org = await session.get(Scenario, model_id)
        if _scenario_for_org:
            _deal_for_org = await session.get(Deal, _scenario_for_org.deal_id)
            if _deal_for_org and _deal_for_org.org_id:
                _org = await session.get(_Org, _deal_for_org.org_id)
                if _org:
                    org_name = _org.name
    except Exception:
        pass

    # ── Phase summaries ──────────────────────────────────────────────────────
    # Four logical phases built from milestone types.
    from app.models.milestone import MilestoneType as MT
    _PRE_DEV   = {MT.offer_made, MT.under_contract, MT.close, MT.pre_development}
    _CONSTRUCT = {MT.construction}
    _OPERATION = {MT.operation_lease_up, MT.operation_stabilized}
    _DIVEST    = {MT.divestment}

    def _phase_bucket(types: set) -> list:
        return [m for m in milestones if MT(m.milestone_type) in types]

    def _bucket_summary(bucket: list) -> dict:
        starts = [m.computed_start(ms_map) for m in bucket]
        starts = [s for s in starts if s]
        ends = [m.computed_end(ms_map) for m in bucket]
        ends = [e for e in ends if e]
        if not starts:
            return {"start": None, "end": None, "duration_days": None}
        start = min(starts)
        end = max(ends) if ends else None
        duration_days = (end - start).days if end and start else None
        return {"start": start, "end": end, "duration_days": duration_days}

    pre_dev_bucket  = _phase_bucket(_PRE_DEV)
    construct_bucket = _phase_bucket(_CONSTRUCT)
    operation_bucket = _phase_bucket(_OPERATION)
    divest_bucket    = _phase_bucket(_DIVEST)

    phase_summaries = {
        "pre_dev":      _bucket_summary(pre_dev_bucket),
        "construction": _bucket_summary(construct_bucket),
        "operation":    _bucket_summary(operation_bucket),
        "divestment":   _bucket_summary(divest_bucket),
        "has_divestment": bool(divest_bucket),
    }

    # Total timeline: earliest computed start → latest computed end
    _all_starts = [m.computed_start(ms_map) for m in milestones]
    _all_ends   = [m.computed_end(ms_map)   for m in milestones]
    _all_starts = [s for s in _all_starts if s]
    _all_ends   = [e for e in _all_ends   if e]
    if _all_starts and _all_ends:
        total_timeline_days = (max(_all_ends) - min(_all_starts)).days
    else:
        total_timeline_days = sum(m.duration_days for m in milestones)

    # ── Capital module source bars for Sources & Uses Gantt ─────────────────
    # Each source bar spans active_phase_start → active_phase_end. If no end
    # phase is set the bar extends to the right edge with a fade-out (perpetuity
    # convention for equity / permanent debt). Zero-amount modules are hidden
    # unless explicitly auto-sized (placeholder dashed bar).
    # Phase → milestone mapping lives in the module-level _CM_PHASE_TO_MS
    # (hoisted so the vocab contract test can import it).
    _cm_gantt_rows: list[dict] = []
    _bgd_cm = _builder_gantt_from_milestones(default_project, milestones)
    if _bgd_cm and capital_modules:
        _epoch_cm = _bgd_cm.get("epoch")
        _g_min_cm = _bgd_cm.get("g_min", 0)
        _g_max_cm = _bgd_cm.get("g_max", 1)
        _span_cm = max(_g_max_cm - _g_min_cm, 1)
        _ms_start_map: dict = {
            str(m.milestone_type).replace("MilestoneType.", ""): m.computed_start(ms_map)
            for m in milestones
            if m.computed_start(ms_map)
        }
        _ms_end_map: dict = {
            str(m.milestone_type).replace("MilestoneType.", ""): m.computed_end(ms_map)
            for m in milestones
            if m.computed_end(ms_map)
        }

        def _phase_to_date(phase: str | None) -> date | None:
            if not phase:
                return None
            candidates = _CM_PHASE_TO_MS.get(phase)
            if not candidates:
                return None
            for ms_key, side in candidates:
                source_map = _ms_end_map if side == "end" else _ms_start_map
                found = source_map.get(ms_key)
                if found:
                    return found
            return None

        # Derive end-phase string from Exit Vehicle when possible — matches
        # the engine's `_resolve_active_end_rank` logic.  Falls back to the
        # legacy `active_phase_end` field when vehicle is unset.
        def _gantt_end_phase(_cm: object) -> str | None:
            vt = str(getattr(_cm, "vehicle_type", "") or "").replace("VehicleType.", "")
            if vt != "debt":
                # Non-debt: runs through the end of the hold (display-wise)
                return "divestment"
            et = getattr(_cm, "exit_terms", None) or {}
            saved = (et.get("vehicle") or "").strip() if isinstance(et, dict) else ""
            if saved == "sale":
                return "divestment"
            if saved == "maturity":
                return "divestment"  # display convention: through end of deal
            if saved:
                for r in capital_modules:
                    if r is _cm:
                        continue
                    if str(getattr(r, "id", "")) == saved:
                        return str(r.active_phase_start or "")
            # Legacy fallback.
            legacy = str(getattr(_cm, "active_phase_end", "") or "")
            return legacy or None

        for _cm in capital_modules:
            _src = _cm.source or {}
            _src_amount = float(_src.get("amount") or 0)
            _auto_size = bool(_src.get("auto_size"))
            # Hide $0 sources that aren't marked for auto-sizing (zero means
            # the user hasn't committed this source, so it shouldn't take up
            # a Gantt row).
            if _src_amount <= 0 and not _auto_size:
                continue
            if not _cm.active_phase_start or not _epoch_cm:
                continue
            _from_date = _phase_to_date(_cm.active_phase_start)
            if not _from_date:
                continue
            _from_day = (_from_date - _epoch_cm).days
            _left = max(0.0, round(100.0 * (_from_day - _g_min_cm) / _span_cm, 2))
            _end_phase = _gantt_end_phase(_cm)
            _to_date = _phase_to_date(_end_phase) if _end_phase else None
            if _to_date:
                _to_day = (_to_date - _epoch_cm).days
                _right = min(100.0, round(100.0 * (_to_day - _g_min_cm) / _span_cm, 2))
                _width = max(_right - _left, 1.5)
                _fade = False
            else:
                _width = max(100.0 - _left, 1.5)
                _fade = True
            _vt = str(getattr(_cm, "vehicle_type", "") or "").replace("VehicleType.", "")
            _label = (_cm.label or _vt).replace(" (auto)", "").strip()
            _cm_gantt_rows.append({
                "label": _label,
                "source_type": _vt if _vt in ("equity", "debt", "grant", "forgivable_loan") else "debt",
                "vehicle_type": _vt,
                "left_pct": _left,
                "width_pct": _width,
                "fade_right": _fade,
                "unsized": _src_amount <= 0,
            })

    # AMI rent tier lookup — only computed when affordable_housing_project is enabled.
    ami_unit_data: dict = {}
    if inputs and getattr(inputs, "affordable_housing_project", False):
        from app.data.ami_portland_2025 import get_ami_tier as _get_ami_tier
        _stream_by_label = {s.label: s for s in income_streams}
        for _u in unit_mix_rows:
            _sl = (
                f"{_u.label} Rent (Renovated)"
                if getattr(_u, "unit_strategy", None) == "value_add_renovation"
                else f"{_u.label} Rent"
            )
            _s = _stream_by_label.get(_sl)
            _proposed: float | None = None
            if _s and _s.amount_per_unit_monthly:
                _proposed = float(_s.amount_per_unit_monthly)
            elif _u.market_rent_per_unit:
                _proposed = float(_u.market_rent_per_unit)
            if _proposed is not None:
                _beds = int(_u.beds or 1)
                ami_unit_data[str(_u.id)] = _get_ami_tier(_beds, _proposed)

    # Map milestone UUID → milestone_type key string (e.g. "operation_lease_up").
    # Template uses this to render Use line Active From labels without reading
    # the legacy milestone_key string column (dropped in migration 0086).
    _ms_id_to_key: dict[str, str] = {}
    for _ms in milestones:
        _mt = _ms.milestone_type
        _ms_id_to_key[str(_ms.id)] = _mt.value if hasattr(_mt, "value") else str(_mt)

    return {
        "inputs": inputs,
        "outputs": outputs,
        "use_lines": use_lines,
        "ms_id_to_key": _ms_id_to_key,
        "income_streams": income_streams,
        "expense_lines": expense_lines,
        "unit_mix_rows": unit_mix_rows,
        "capital_modules": capital_modules,
        # Per-project junction-scoped principal by module id (str). Template
        # uses this in the Sources table so Project N's tab shows Project N's
        # share, not the scenario-wide last-sized amount.
        "capital_junction_amts": _cap_junction_amts,
        "float_earnings_series": _float_earnings_series,
        "waterfall_tiers": waterfall_tiers,
        "milestones": milestones,
        "milestone_rows": [
            {
                "ms": m,
                "start": m.computed_start(ms_map),
                "end": m.computed_end(ms_map),
            }
            for m in milestones
        ],
        "use_line_count": len(use_lines),
        "income_stream_count": len(income_streams),
        "expense_line_count": len(expense_lines),
        "unit_mix_count": len(unit_mix_rows),
        "total_units": sum((u.unit_count or 0) for u in unit_mix_rows),
        "capital_module_count": len(capital_modules),
        "waterfall_tier_count": len(waterfall_tiers),
        "capital_total": capital_total,
        "uses_total": uses_total_val,
        "revenue_annual": revenue_annual,
        "opex_annual": opex_annual,
        "capex_reserve_annual": capex_reserve_annual,
        "opex_total_annual": opex_total_annual,
        "carrying_annual": carrying_annual_computed,
        "carrying_detail": carrying_detail,
        "stabilized_month1_ncf": stabilized_month1_ncf,
        "stabilized_year1_ncf": stabilized_year1_ncf,
        "stabilized_revenue_annual": stabilized_revenue_annual,
        "stabilized_opex_annual": stabilized_opex_annual,
        "profit_runrate_after_debt": profit_runrate_after_debt,
        "divestment_total": _sum_amount(exit_lines),
        "profit_total": float(outputs.noi_stabilized) if outputs and outputs.noi_stabilized else None,
        "equity_ownership": equity_ownership,
        "org_owner_fallback": org_owner_fallback,
        "org_name": org_name,
        "deferred_uses": deferred_uses,
        "deferred_total": deferred_total,
        "total_timeline_days": total_timeline_days,
        "total_timeline_months": round(total_timeline_days / 30.4) if total_timeline_days else 0,
        "phase_summaries": phase_summaries,
        "timeline_approved": timeline_approved,
        "deal_setup_complete": bool(getattr(inputs, "deal_setup_complete", False)) if inputs else False,
        "default_project_id": project_id,
        # Staleness map for top tab chips (Phase 3a): each project + the
        # Underwriting rollup get a dot when inputs have moved past the
        # last compute. Computed once per _load_builder_data call.
        "staleness": await _staleness_map(session, model_id),
        # Phase 3b: per-project calc-status + Underwriting aggregate for the
        # tab-chip pills. Each status dict follows the _compute_calc_status
        # shape; the Underwriting entry is the worst severity across projects.
        "scenario_statuses": await _compute_scenario_statuses(session, model_id),
        # Approval gate: every milestone needs a position AND a non-zero duration
        "timeline_approvable": len(milestones) > 0 and all(
            (m.target_date or m.trigger_milestone_id) and (m.duration_days or 0) > 0
            for m in milestones
        ),
        "timeline_missing_position": [
            m for m in milestones
            if not m.target_date and not m.trigger_milestone_id
        ],
        "timeline_missing_duration": [
            m for m in milestones
            if not (m.duration_days or 0) > 0
        ],
        # Gantt data for the timeline module panel (Gantt v2)
        "builder_gantt_data": _builder_gantt_from_milestones(default_project, milestones),
        "capital_module_gantt_rows": _cm_gantt_rows,
        # Wizard: show when unapproved and no milestone has a start date yet
        "wizard_needed": (not timeline_approved) and (not any(m.target_date for m in milestones)),
        "wizard_default_types": list(DEFAULT_DURATIONS.get(
            _scenario.project_type if _scenario else "", {}
        ).keys()),
        "wizard_deal_type": _scenario.project_type if _scenario else "",
        "wizard_deal_type_label": {
            "acquisition": "Acquisition",
            "value_add": "Value-Add",
            "conversion": "Conversion",
            "new_construction": "New Construction",
        }.get(_scenario.project_type if _scenario else "", "Project"),
        "income_mode": (_scenario.income_mode if _scenario else "revenue_opex") or "revenue_opex",
        "noi_annual": float(inputs.noi_stabilized_input) if inputs and inputs.noi_stabilized_input is not None else None,
        "ami_unit_data": ami_unit_data,
    }


async def _builder_panel_oob_response(
    request: Request,
    model,
    active_module: str,
    panel_data: dict,
    project_id: UUID | None,
    session: AsyncSession,
    extra_ctx: dict | None = None,
) -> HTMLResponse:
    """Return builder panel HTML with OOB calc-status pill and module-nav swaps appended."""
    ctx = {
        "request": request,
        "model": model,
        "active_module": active_module,
        "wizard_mode": _wizard_mode_from_request(request),
        **panel_data,
        **(extra_ctx or {}),
    }
    panel_html = templates.env.get_template("partials/model_builder_panel.html").render(ctx)

    _cs = _compute_calc_status(panel_data)
    _has_adj = await _has_any_gap_adjustment(session, project_id) if project_id else False
    _pill_html = _render_calc_status_pill_html(_cs, model.id, has_any_adjustment=_has_adj)
    oob_pill = f'<div id="calc-status-pill-container" hx-swap-oob="innerHTML">{_pill_html}</div>'

    nav_ctx = {
        "active_module": active_module,
        "locked": not panel_data.get("timeline_approved", False),
        "deal_setup_complete": panel_data.get("deal_setup_complete", False),
        "nav_base_path": f"/models/{model.id}/builder",
        **{k: panel_data.get(k) for k in (
            "capital_module_count", "capital_total",
            "use_line_count", "uses_total", "income_stream_count", "revenue_annual",
            "expense_line_count", "opex_annual", "capex_reserve_annual", "opex_total_annual",
            "carrying_annual", "stabilized_revenue_annual", "stabilized_opex_annual",
            "profit_runrate_after_debt", "equity_ownership", "org_owner_fallback",
            "deferred_uses", "deferred_total", "profit_total", "divestment_total",
            "phase_summaries", "outputs", "income_mode", "noi_annual",
            "unit_mix_count", "total_units", "default_project_id",
        )},
    }
    nav_html = templates.env.get_template("partials/model_builder_nav_cards.html").render(nav_ctx)
    oob_nav = f'<div id="module-nav-cards" hx-swap-oob="innerHTML">{nav_html}</div>'

    return HTMLResponse(panel_html + oob_pill + oob_nav)


@router.post("/ui/forms/{model_id}/{item_type}", response_class=HTMLResponse)
@router.put("/ui/forms/{model_id}/{item_type}/{item_id}", response_class=HTMLResponse)
async def handle_form_create_or_update(
    request: Request,
    model_id: UUID,
    item_type: str,
    session: DBSession,
    item_id: str = "",
) -> HTMLResponse:
    """Accept form-encoded data, persist the mutation, return refreshed panel HTML."""
    model = await session.get(Scenario, model_id)
    if model is None:
        return HTMLResponse("<p class='text-muted'>Model not found.</p>", status_code=404)

    if settings.org_isolation_enabled:
        _wuser = await _get_user(session, request)
        _wuser_org = getattr(_wuser, "org_id", None) if _wuser is not None else None
        _wdeal = await session.get(Deal, model.deal_id) if model.deal_id else None
        if _wuser_org is None or _wdeal is None or _wdeal.org_id != _wuser_org:
            return HTMLResponse("<p class='text-muted'>Model not found.</p>", status_code=404)

    # Resolve active Project for line items that belong to Project level.
    # Multi-project deals: prefer the project from the form's active URL
    # (HX-Current-URL header carries it), fall back to the oldest project.
    default_project = (await session.execute(
        select(Project).where(Project.scenario_id == model_id).order_by(Project.created_at.asc()).limit(1)
    )).scalar_one_or_none()
    project_id = await _active_project_from_request(request, session, model_id)
    if project_id is None:
        project_id = default_project.id if default_project else None

    form = await request.form()
    module = _ITEM_TYPE_TO_MODULE.get(item_type, "uses")

    if item_type == "use-lines":
        from app.services.model_builder_forms.use_line import save_use_line
        await save_use_line(session, model_id, project_id, item_id, form)
    elif item_type == "income-streams":
        from app.services.model_builder_forms.income_stream import save_income_stream
        await save_income_stream(session, project_id, item_id, form)
    elif item_type == "expense-lines":
        from app.services.model_builder_forms.expense_line import save_expense_line
        await save_expense_line(session, project_id, item_id, form)
    elif item_type == "capital-modules":
        from app.services.model_builder_forms.capital_module import save_capital_module
        await save_capital_module(session, model_id, project_id, default_project, item_id, form)
    elif item_type == "waterfall-tiers":
        from app.services.model_builder_forms.waterfall_tier import save_waterfall_tier
        await save_waterfall_tier(session, model_id, item_id, form)
    elif item_type == "milestones":
        from app.services.model_builder_forms.milestone import save_milestone
        await save_milestone(session, model_id, project_id, item_id, form)
    elif item_type == "unit-mix":
        from app.services.model_builder_forms.unit_mix import save_unit_mix
        await save_unit_mix(session, project_id, item_id, form)

    if item_type in ("capital-modules", "milestones"):
        from app.services.capital_module_milestones import sync_milestone_fks_for_scenario
        await sync_milestone_fks_for_scenario(session, model_id)

    await session.flush()
    panel_data = await _load_builder_data(session, model_id, project_id=project_id)
    return await _builder_panel_oob_response(request, model, module, panel_data, project_id, session)


@router.delete("/ui/forms/{model_id}/{item_type}/{item_id}", response_class=HTMLResponse)
async def handle_form_delete(
    request: Request,
    model_id: UUID,
    item_type: str,
    item_id: str,
    session: DBSession,
) -> HTMLResponse:
    """Delete a line item and return the refreshed panel HTML."""
    model = await session.get(Scenario, model_id)
    if model is None:
        return HTMLResponse("<p class='text-muted'>Model not found.</p>", status_code=404)

    module = _ITEM_TYPE_TO_MODULE.get(item_type, "uses")
    try:
        uid = UUID(item_id)
    except (ValueError, AttributeError):
        # Legacy unit-mix rows may have rendered without an id; surface a panel
        # refresh rather than 500 so the user can retry after backfill runs.
        if item_type == "unit-mix":
            _active_proj_id = await _active_project_from_request(request, session, model_id)
            panel_data = await _load_builder_data(session, model_id, project_id=_active_proj_id)
            return await _builder_panel_oob_response(request, model, module, panel_data, _active_proj_id, session)
        return HTMLResponse("<p class='text-muted'>Invalid item id.</p>", status_code=400)

    row = None
    if item_type == "use-lines":
        row = await session.get(UseLine, uid)
    elif item_type == "income-streams":
        row = await session.get(IncomeStream, uid)
    elif item_type == "expense-lines":
        row = await session.get(OperatingExpenseLine, uid)
    elif item_type == "capital-modules":
        row = await session.get(CapitalModule, uid)
    elif item_type == "waterfall-tiers":
        row = await session.get(WaterfallTier, uid)
    elif item_type == "milestones":
        row = await session.get(Milestone, uid)
    elif item_type == "unit-mix":
        # JSONB — find the project and filter out the row by id
        _del_proj_id = await _active_project_from_request(request, session, model_id)
        if _del_proj_id:
            _del_proj = await session.get(Project, _del_proj_id)
            if _del_proj is not None:
                _del_proj.unit_mix = [d for d in (_del_proj.unit_mix or []) if d.get("id") != str(uid)]
                session.add(_del_proj)
        await session.flush()
        _active_proj_id2 = await _active_project_from_request(request, session, model_id)
        panel_data = await _load_builder_data(session, model_id, project_id=_active_proj_id2)
        return await _builder_panel_oob_response(request, model, module, panel_data, _active_proj_id2, session)

    if row is not None:
        if item_type == "use-lines" and getattr(row, "is_auto_dev_fee", False):
            return HTMLResponse(
                "<p class='text-muted'>The auto Developer Fee Use Line cannot be "
                "deleted. Set its % to 0 to disable.</p>",
                status_code=403,
            )
        await session.delete(row)
        await session.flush()

    _active_proj_id = await _active_project_from_request(request, session, model_id)
    panel_data = await _load_builder_data(session, model_id, project_id=_active_proj_id)
    return await _builder_panel_oob_response(request, model, module, panel_data, _active_proj_id, session)


@router.post("/ui/models/{model_id}/unit-mix/apply-to-revenue", response_class=HTMLResponse)
async def apply_unit_mix_to_revenue(
    request: Request,
    model_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Add IncomeStream rows for UnitMix rows that don't already have one.
    **Additive only** — never deletes or overwrites existing streams.

    Strategy → generated label mapping:
      - base_escalation:       "{unit_label} Rent"
      - ltl_catchup:           "{unit_label} Rent"
      - value_add_renovation:  "{unit_label} Rent (Renovated)"

    If a stream already exists at the generated label this handler skips
    it (preserving rent / occupancy / escalation edits). Stub streams like
    "All Units" stay put — the user deletes them manually once the
    per-unit-type streams look right.
    """
    model = await session.get(Scenario, model_id)
    if model is None:
        return HTMLResponse("<p class='text-muted'>Model not found.</p>", status_code=404)

    # Resolve active project from HX-Current-URL (multi-project tabs) and
    # fall back to the default project. All inserts and the panel re-render
    # must use this project_id, not default_project.
    active_proj_id = await _active_project_from_request(request, session, model_id)
    if active_proj_id is None:
        default_project = (await session.execute(
            select(Project).where(Project.scenario_id == model_id).order_by(Project.created_at.asc()).limit(1)
        )).scalar_one_or_none()
        if default_project is None:
            return HTMLResponse("<p class='text-muted'>No project.</p>", status_code=400)
        active_proj_id = default_project.id

    _active_proj = await session.get(Project, active_proj_id)
    if _active_proj is not None and _ensure_unit_mix_ids(_active_proj):
        await session.flush()
    unit_mix_rows = [_UMRow(r) for r in (_active_proj.unit_mix or [])] if _active_proj else []
    if not unit_mix_rows:
        panel_data = await _load_builder_data(session, model_id, project_id=active_proj_id)
        return await _builder_panel_oob_response(request, model, "property", panel_data, active_proj_id, session)

    # Build the candidate stream list from each UnitMix row's strategy.
    # Additive sync filters this list against existing labels below.
    to_generate: list[dict] = []
    for u in unit_mix_rows:
        strategy = (u.unit_strategy or "base_escalation")
        label = f"{u.label} Rent"
        count = int(u.unit_count or 0)
        if count <= 0:
            continue

        ip_rent = _to_decimal_or_none(u.in_place_rent_per_unit)
        mkt_rent = _to_decimal_or_none(u.market_rent_per_unit)
        post_reno = _to_decimal_or_none(u.post_reno_rent_per_unit)

        if strategy == "value_add_renovation":
            # Post-reno rent is the target; fall back to market if unset
            base_rent = post_reno or mkt_rent or ip_rent
            stream = dict(
                label=f"{u.label} Rent (Renovated)",
                stream_type=IncomeStreamType.residential_rent,
                unit_count=count,
                amount_per_unit_monthly=base_rent,
                stabilized_occupancy_pct=Decimal("95"),
                escalation_rate_pct_annual=Decimal("3"),
                renovation_absorption_rate=Decimal("1"),
                active_in_phases=["lease_up", "stabilized"],
            )
        elif strategy == "ltl_catchup":
            stream = dict(
                label=label,
                stream_type=IncomeStreamType.residential_rent,
                unit_count=count,
                amount_per_unit_monthly=(ip_rent or mkt_rent or Decimal("0")),
                stabilized_occupancy_pct=Decimal("95"),
                catchup_target_rent=mkt_rent,
                escalation_rate_pct_annual=Decimal("3"),
                active_in_phases=["lease_up", "stabilized"],
            )
        else:  # base_escalation
            stream = dict(
                label=label,
                stream_type=IncomeStreamType.residential_rent,
                unit_count=count,
                amount_per_unit_monthly=(ip_rent or mkt_rent or Decimal("0")),
                stabilized_occupancy_pct=Decimal("95"),
                escalation_rate_pct_annual=Decimal("3"),
                active_in_phases=["lease_up", "stabilized"],
            )
        to_generate.append(stream)

    # Additive-only: skip any generated label whose stream already exists.
    # Preserves manual rent / occupancy / escalation edits the user made.
    generated_labels = {s["label"] for s in to_generate}
    existing_labels: set[str] = set()
    if generated_labels:
        existing_labels = set((await session.execute(
            select(IncomeStream.label).where(
                IncomeStream.project_id == active_proj_id,
                IncomeStream.label.in_(generated_labels),
            )
        )).scalars())

    for data in to_generate:
        if data["label"] in existing_labels:
            continue
        session.add(IncomeStream(project_id=active_proj_id, **data))
    await session.flush()

    # Return the refreshed Revenue panel — the sync banner triggers from
    # there, so stay oriented on Revenue rather than bouncing to Property.
    panel_data = await _load_builder_data(session, model_id, project_id=active_proj_id)
    return await _builder_panel_oob_response(request, model, "revenue", panel_data, active_proj_id, session)


def _to_decimal_or_none(v) -> Decimal | None:
    """Coerce a numeric value to Decimal, or None if zero/missing."""
    if v is None:
        return None
    try:
        d = Decimal(str(v))
        return d if d != 0 else None
    except Exception:
        return None


@router.post("/ui/models/{model_id}/sensitivity/run", response_class=HTMLResponse)
async def run_sensitivity_analysis(
    request: Request,
    model_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Run a 5x5 sensitivity compute and persist the result as JSON on
    OperationalOutputs.sensitivity_matrix. Returns the refreshed Sensitivity
    panel so the user sees results inline."""
    from app.engines.sensitivity_matrix import compute_sensitivity_matrix

    model = await session.get(Scenario, model_id)
    if model is None:
        return HTMLResponse("<p class='text-muted'>Model not found.</p>", status_code=404)

    form = await request.form()
    axis_x = form.get("axis_x") or "noi_escalation_rate_pct"
    axis_y = form.get("axis_y") or "exit_cap_rate_pct"
    metric = form.get("metric") or "project_irr_levered"

    try:
        matrix = await compute_sensitivity_matrix(
            deal_model_id=model_id,
            session=session,
            axis_x=axis_x,
            axis_y=axis_y,
            metric=metric,
        )
    except ValueError as e:
        # Bad axis/metric combo — surface the error in the panel
        panel_data = await _load_builder_data(session, model_id)
        return await _builder_panel_oob_response(
            request, model, "sensitivity", panel_data, None, session,
            extra_ctx={"sensitivity_error": str(e)},
        )

    # Persist on OperationalOutputs.sensitivity_matrix (JSON column).
    # compute_sensitivity_matrix runs a final compute_cash_flows so a fresh
    # OperationalOutputs row now exists. Scope to default project because
    # sensitivity_matrix is a scenario-wide artifact today (Phase 3d/e will
    # revisit per-project sensitivity).
    outputs = (await session.execute(
        select(OperationalOutputs)
        .where(OperationalOutputs.scenario_id == model_id)
        .join(Project, Project.id == OperationalOutputs.project_id)
        .order_by(Project.created_at.asc())
        .limit(1)
    )).scalar_one_or_none()
    if outputs is not None:
        outputs.sensitivity_matrix = matrix
        session.add(outputs)
        await session.flush()

    panel_data = await _load_builder_data(session, model_id)
    return await _builder_panel_oob_response(request, model, "sensitivity", panel_data, None, session)


_CLONE_ROW_SKIP = {"id", "created_at", "updated_at"}


def _clone_row(obj, **overrides):
    """New ORM instance copying every column verbatim except the PK and
    timestamps — introspection-based so new columns are never silently
    dropped (the old hand-picked kwarg lists rotted as columns were added:
    clones lost is_auto_finance_cost, source_capital_module_id, fee_terms,
    module milestone windows, …). JSON/list values are deep-copied so later
    remaps never mutate the source row. ``overrides`` replace specific
    columns (FKs)."""
    import copy as _copy
    data = {}
    for col in obj.__table__.columns:
        key = col.key
        if key in _CLONE_ROW_SKIP:
            continue
        val = getattr(obj, key)
        if isinstance(val, (dict, list)):
            val = _copy.deepcopy(val)
        data[key] = val
    data.update(overrides)
    return type(obj)(**data)


def _remap_id(value, id_map: dict):
    """Map an id through id_map; pass through None and unknown ids unchanged."""
    if value is None:
        return None
    return id_map.get(value, value)


async def _copy_project_milestones(
    src_proj: Project, dst_proj: Project, session: AsyncSession
) -> dict:
    """Clone src project's milestones onto dst (two-pass trigger-chain remap).
    Returns the old→new milestone id map."""
    src_milestones = list((await session.execute(
        select(Milestone).where(Milestone.project_id == src_proj.id)
    )).scalars())
    ms_id_map: dict = {}
    new_by_old: dict = {}
    for ms in src_milestones:
        new_ms = _clone_row(
            ms, project_id=dst_proj.id, opportunity_id=None,
            trigger_milestone_id=None,
        )
        session.add(new_ms)
        await session.flush()
        ms_id_map[ms.id] = new_ms.id
        new_by_old[ms.id] = new_ms
    for ms in src_milestones:  # pass 2 — wire trigger ids
        if ms.trigger_milestone_id is not None:
            new_by_old[ms.id].trigger_milestone_id = ms_id_map.get(ms.trigger_milestone_id)
    return ms_id_map


async def _copy_project_lines(
    src_proj: Project,
    dst_proj: Project,
    session: AsyncSession,
    ms_id_map: dict,
    module_id_map: dict | None = None,
) -> dict:
    """Copy use lines, income streams, expense lines, unit_mix, and
    OperationalInputs from src_proj to dst_proj.

    Milestone FKs remap through ``ms_id_map``. Capital-module FKs
    (source_capital_module_id, eligible_module_ids) remap through
    ``module_id_map`` when the caller cloned the scenario's modules too
    (cross-scenario variant); same-scenario copies pass no map and module
    ids stay valid as-is.

    OperationalInputs copy is VERBATIM — a clone must compute identically
    to its source. (An earlier version re-applied current org Type 1
    defaults here, which silently clobbered per-project choices like
    debt_sizing_mode and changed the clone's numbers.)

    Returns the old→new use-line id map (for fee-basis row copies)."""
    module_id_map = module_id_map or {}
    _ms_str_map = {str(k): str(v) for k, v in ms_id_map.items()}

    ul_id_map: dict = {}
    for u in (await session.execute(
        select(UseLine).where(UseLine.project_id == src_proj.id)
    )).scalars():
        new_u = _clone_row(
            u,
            project_id=dst_proj.id,
            active_from_milestone_id=_remap_id(u.active_from_milestone_id, ms_id_map),
            spread_to_milestone_id=_remap_id(u.spread_to_milestone_id, ms_id_map),
            source_capital_module_id=_remap_id(u.source_capital_module_id, module_id_map),
            eligible_module_ids=[_remap_id(m, module_id_map) for m in (u.eligible_module_ids or [])],
            dev_fee_binding_context={},  # engine output — regenerated on compute
        )
        # dev_fee_release_schedule stores milestone ids inside JSONB —
        # remap them too or the schedule points at the source project's
        # milestones. Unknown ids are left as-is (engine ignores them).
        sched = new_u.dev_fee_release_schedule or {}
        if sched:
            weights = [
                {**w, "milestone_id": _ms_str_map.get(str(w.get("milestone_id")), w.get("milestone_id"))}
                for w in sched.get("weights", [])
            ]
            fh = sched.get("final_holdback")
            if isinstance(fh, dict) and fh.get("milestone_id"):
                fh = {**fh, "milestone_id": _ms_str_map.get(str(fh["milestone_id"]), fh["milestone_id"])}
            new_u.dev_fee_release_schedule = {**sched, "weights": weights} | (
                {"final_holdback": fh} if fh else {}
            )
        session.add(new_u)
        await session.flush()
        ul_id_map[u.id] = new_u.id

    for s in (await session.execute(
        select(IncomeStream).where(IncomeStream.project_id == src_proj.id)
    )).scalars():
        session.add(_clone_row(s, project_id=dst_proj.id))

    for e in (await session.execute(
        select(OperatingExpenseLine).where(OperatingExpenseLine.project_id == src_proj.id)
    )).scalars():
        session.add(_clone_row(e, project_id=dst_proj.id))

    # Copy unit_mix JSONB
    if src_proj.unit_mix:
        dst_proj.unit_mix = list(src_proj.unit_mix)
        session.add(dst_proj)

    # Copy OperationalInputs if any (verbatim — see docstring)
    src_inputs = (await session.execute(
        select(OperationalInputs).where(OperationalInputs.project_id == src_proj.id)
    )).scalar_one_or_none()
    if src_inputs:
        session.add(_clone_row(src_inputs, project_id=dst_proj.id))
    return ul_id_map


async def _copy_project_data(
    src_proj: Project,
    dst_proj: Project,
    session: AsyncSession,
) -> None:
    """Copy milestones (with trigger remapping), use lines, income streams,
    expense lines, and operational inputs between two projects in the SAME
    scenario (clone-from). Capital-module FKs stay as-is — both projects see
    the same scenario-level modules. Caller is responsible for deleting
    dst_proj's existing data first."""
    ms_id_map = await _copy_project_milestones(src_proj, dst_proj, session)
    await _copy_project_lines(src_proj, dst_proj, session, ms_id_map)


@router.post("/ui/deals/{deal_id}/variant", response_class=HTMLResponse)
async def create_deal_copy(
    request: Request,
    deal_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Deep-copy a Scenario into a new Scenario with the same Projects, milestones, and line items.

    A variant is a FAITHFUL copy: it must compute identically to its source
    until the user edits it. Every FK / embedded id that points at another
    copied row (milestone trigger chains, module windows, junction windows,
    use-line source module + eligibility whitelist, float-earnings parent +
    routing milestones, fee-basis rows) is remapped onto the clone's rows."""
    import copy as _copy
    source = await session.get(Scenario, deal_id)
    if source is None:
        return HTMLResponse("<p class='text-muted'>Deal not found.</p>", status_code=404)

    user = await _get_user(session, request)
    form = await request.form()
    variant_name = str(form.get("name", "")).strip() or f"{source.name} (Copy)"
    selected_project_ids = set(form.getlist("project_ids"))

    # New Scenario under same top-level Deal. Factory in Scenario-only mode;
    # Project + OperationalInputs creation happens in the clone loop below.
    from app.services.scenario_factory import create_scenario as _create_scenario
    # Resolve org_id from the source Deal so defaults resolve against the
    # right organization even when source's creator is no longer the caller.
    _src_deal = await session.get(Deal, source.deal_id)
    _org_id = _src_deal.org_id if _src_deal else (user.org_id if user else None)
    new_deal, _, _ = await _create_scenario(
        session=session,
        deal_id=source.deal_id,
        deal_type=source.project_type,
        user_id=user.id if user else None,
        org_id=_org_id,
        name=variant_name,
        version=source.version + 1,
        is_active=False,
        project_name=None,  # Scenario-only mode — clone loop creates Projects.
        source_scenario=source,
    )

    # Faithful copy of scenario-level Type 1 columns. The factory re-resolved
    # them from current org policy, but a variant must start as an exact copy
    # of its source — a refreshed value (e.g. risk_free_rate_pct) silently
    # changes every project's numbers on first compute.
    from app.settings.defaults import DEFAULT_REGISTRY as _DEFAULTS
    for _spec in _DEFAULTS.values():
        if _spec.type == 1 and _spec.target == "scenario":
            _src_val = getattr(source, _spec.column, None)
            if _src_val is not None:
                setattr(new_deal, _spec.column, _src_val)

    # ── Pass 1: Projects + milestones. Milestones for ALL projects are cloned
    # before any scenario-level rows, because modules/junctions can reference
    # milestones in any project. ──
    source_projects = list((await session.execute(
        select(Project).where(Project.scenario_id == deal_id).order_by(Project.created_at.asc())
    )).scalars())
    if selected_project_ids:
        source_projects = [p for p in source_projects if str(p.id) in selected_project_ids]

    project_id_map: dict = {}
    new_proj_by_old: dict = {}
    ms_id_map: dict = {}  # global (milestone ids are unique across projects)
    for src_proj in source_projects:
        new_proj = _clone_row(src_proj, scenario_id=new_deal.id)
        session.add(new_proj)
        await session.flush()
        project_id_map[src_proj.id] = new_proj.id
        new_proj_by_old[src_proj.id] = new_proj
        ms_id_map.update(await _copy_project_milestones(src_proj, new_proj, session))

    # ── Pass 2: Scenario-level Capital modules (column-driven; milestone
    # windows remapped). ──
    from app.models.capital import CapitalModuleProject as _CMP
    from app.models.capital import UseLineSourceFeeBasis as _ULFB
    from app.models.project import ProjectAnchor as _PA

    src_modules = list((await session.execute(
        select(CapitalModule).where(CapitalModule.scenario_id == deal_id)
    )).scalars())
    module_id_map: dict = {}
    new_mod_by_old: dict = {}
    for cm in src_modules:
        new_cm = _clone_row(
            cm,
            scenario_id=new_deal.id,
            active_from_milestone_id=_remap_id(cm.active_from_milestone_id, ms_id_map),
            active_to_milestone_id=_remap_id(cm.active_to_milestone_id, ms_id_map),
        )
        session.add(new_cm)
        await session.flush()
        module_id_map[cm.id] = new_cm.id
        new_mod_by_old[cm.id] = new_cm
    # Float-earnings modules embed cross-references in their source JSON:
    # parent_module_id (the bond whose balance earns) and waterfall/paydown
    # milestone ids. Left unmapped they point at the SOURCE scenario and the
    # clone's float silently zeroes.
    for cm in src_modules:
        new_cm = new_mod_by_old[cm.id]
        src_json = new_cm.source or {}
        if str(new_cm.vehicle_type or "") != "float_earnings" or not src_json:
            continue
        new_src = _copy.deepcopy(src_json)
        if src_json.get("parent_module_id"):
            try:
                _old_pm = UUID(str(src_json["parent_module_id"]))
                new_src["parent_module_id"] = str(_remap_id(_old_pm, module_id_map))
            except ValueError:
                pass
        for _ms_key in ("waterfall_milestone_id", "paydown_milestone_id"):
            _old_ms_raw = src_json.get(_ms_key)
            if _old_ms_raw:
                try:
                    new_src[_ms_key] = str(_remap_id(UUID(str(_old_ms_raw)), ms_id_map))
                except ValueError:
                    pass
        new_cm.source = new_src

    # ── Pass 3: capital_module_projects junction rows. Without these the
    # copied Sources are orphaned (no project links) and the engine silently
    # skips sizing on every module. ──
    src_junctions = list((await session.execute(
        select(_CMP).where(_CMP.capital_module_id.in_(list(module_id_map.keys())))
    )).scalars())
    for j in src_junctions:
        new_pid = project_id_map.get(j.project_id)
        if new_pid is None:
            continue  # project was excluded from copy; skip its junction
        session.add(_clone_row(
            j,
            capital_module_id=module_id_map[j.capital_module_id],
            project_id=new_pid,
            active_from_milestone_id=_remap_id(j.active_from_milestone_id, ms_id_map),
            active_to_milestone_id=_remap_id(j.active_to_milestone_id, ms_id_map),
        ))

    # ── Pass 4: per-project financial rows (module FKs remapped onto the
    # cloned modules). ──
    ul_id_map: dict = {}
    for src_proj in source_projects:
        ul_id_map.update(await _copy_project_lines(
            src_proj, new_proj_by_old[src_proj.id], session,
            ms_id_map, module_id_map,
        ))

    # ── Pass 5: use-line ↔ source fee-basis rows ──
    if ul_id_map:
        for fb in (await session.execute(
            select(_ULFB).where(_ULFB.use_line_id.in_(list(ul_id_map.keys())))
        )).scalars():
            new_mid = module_id_map.get(fb.capital_module_id)
            if new_mid is None:
                continue
            session.add(_clone_row(
                fb, use_line_id=ul_id_map[fb.use_line_id], capital_module_id=new_mid,
            ))

    # ── Pass 6: draw sources (scenario-scoped; milestone refs are string
    # keys, not FKs — only project/module ids need remapping). ──
    for ds in (await session.execute(
        select(DrawSource).where(DrawSource.scenario_id == deal_id)
    )).scalars():
        if ds.project_id is not None and ds.project_id not in project_id_map:
            continue  # its project was excluded from the copy
        session.add(_clone_row(
            ds,
            scenario_id=new_deal.id,
            project_id=_remap_id(ds.project_id, project_id_map),
            capital_module_id=_remap_id(ds.capital_module_id, module_id_map),
        ))

    # ── Pass 7: ProjectAnchor rows (cross-project timeline coupling). ──
    src_anchors = list((await session.execute(
        select(_PA).where(_PA.project_id.in_(list(project_id_map.keys())))
    )).scalars())
    for a in src_anchors:
        new_anchor_pid = project_id_map.get(a.project_id)
        new_parent_pid = project_id_map.get(a.anchor_project_id)
        if new_anchor_pid is None or new_parent_pid is None:
            continue  # drop dangling anchors when parent project wasn't copied
        session.add(_clone_row(
            a,
            project_id=new_anchor_pid,
            anchor_project_id=new_parent_pid,
            # None when the anchor milestone's project wasn't copied.
            anchor_milestone_id=ms_id_map.get(a.anchor_milestone_id),
        ))

    # ── Pass 8: Scenario-level Waterfall tiers ──
    for t in (await session.execute(
        select(WaterfallTier).where(WaterfallTier.scenario_id == deal_id)
    )).scalars():
        if t.project_id is not None and t.project_id not in project_id_map:
            continue  # tier belongs to an excluded project
        session.add(_clone_row(
            t,
            scenario_id=new_deal.id,
            project_id=_remap_id(t.project_id, project_id_map),
            capital_module_id=_remap_id(t.capital_module_id, module_id_map),
        ))

    await session.commit()
    # Phase 3e: land on the Underwriting tab of the new variant so the user
    # sees the rolled-up view (with every project's staleness dot lit) and
    # knows to click Compute before any per-project edits.
    return RedirectResponse(
        url=f"/models/{new_deal.id}/builder?view=underwriting",
        status_code=303,
    )


@router.post("/ui/deals/{deal_id}/new-project", response_class=HTMLResponse)
async def create_deal_project(
    request: Request,
    deal_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Add a new Project to an existing Scenario (max 8). Redirects to builder with timeline wizard."""
    deal = await session.get(Scenario, deal_id)
    if deal is None:
        return HTMLResponse("<p class='text-muted'>Deal not found.</p>", status_code=404)

    project_count = int((await session.execute(
        select(func.count()).select_from(Project).where(Project.scenario_id == deal_id)
    )).scalar_one())
    if project_count >= 8:
        return HTMLResponse("<p class='text-muted'>Maximum 8 projects per deal.</p>", status_code=400)

    form = await request.form()
    project_name = str(form.get("name", "")).strip() or f"Project {project_count + 1}"

    try:
        pt = ProjectType(str(form.get("deal_type", "")))
    except ValueError:
        try:
            pt = ProjectType(str(deal.project_type))
        except ValueError:
            pt = ProjectType.acquisition

    # Required: opportunity_id. Tying every project to an opportunity is the
    # invariant that lets us seed a non-zero Acquisition UseLine — without it
    # the model has $0 of Uses and downstream debt sizing produces gaps that
    # can't be reconciled by a later edit.
    _opp_id_raw = str(form.get("opportunity_id", "")).strip()
    if not _opp_id_raw:
        return HTMLResponse(
            "<p class='text-muted'>Pick an opportunity to convert into this project.</p>",
            status_code=400,
        )
    try:
        _opp_id = UUID(_opp_id_raw)
    except ValueError:
        return HTMLResponse(
            "<p class='text-muted'>Invalid opportunity id.</p>", status_code=400,
        )

    opp = await session.get(Opportunity, _opp_id)
    if opp is None:
        return HTMLResponse(
            "<p class='text-muted'>Opportunity not found.</p>", status_code=404,
        )

    # Required: acquisition_cost > 0. Pre-filled from the opportunity's
    # listing price client-side, but always editable so the user can
    # override with their underwriting price. Without this we end up with
    # a $0 Acquisition UseLine and the same recompute-gap bug that motivated
    # this whole flow.
    _acq_raw = str(form.get("acquisition_cost", "")).strip()
    try:
        _acq_amount = Decimal(_acq_raw) if _acq_raw else Decimal("0")
    except (InvalidOperation, ValueError):
        return HTMLResponse(
            "<p class='text-muted'>Invalid acquisition cost.</p>", status_code=400,
        )
    if _acq_amount <= 0:
        return HTMLResponse(
            "<p class='text-muted'>Acquisition cost must be greater than zero.</p>",
            status_code=400,
        )

    new_proj = Project(
        scenario_id=deal_id,
        opportunity_id=_opp_id,
        name=project_name,
    )
    session.add(new_proj)
    await session.flush()

    # Seed org-default document tasks onto this new project (no-op if none).
    from app.services.document_task_seeding import seed_default_tasks
    await seed_default_tasks(session, opp.org_id, new_proj.id)

    await _auto_assign_opportunity_to_project(opp, new_proj, session)

    for milestone in _seed_milestones(new_proj, pt):
        session.add(milestone)
    await session.flush()

    # Seed the Acquisition UseLine using the user-confirmed cost. Mirrors the
    # pattern used at deal creation (project 1) so multi-project deals are
    # symmetric — every project lands with a populated Acquisition row.
    session.add(UseLine(
        project_id=new_proj.id,
        label=f"{opp.name or 'Property'} - Acquisition",
        phase=UseLinePhase.acquisition,
        cost_category="acquisition",
        dev_fee_basis_bucket="acquisition",
        amount=_acq_amount,
        timing_type="first_day",
    ))

    # ── Seed OperationalInputs with scenario-level sizing config ──────────
    # If the deal already has Deal Setup completed, the default project's
    # OperationalInputs holds the scenario-level debt + sizing config the
    # user filled in. Copy those onto the new project's inputs so the
    # engine respects the same DSCR cap, sizing mode, reserve months, etc.
    # Without this the new project silently falls back to gap-fill, leaving
    # debt over-leveraged and the Sources/Uses panel showing zero gap when
    # there should be one.
    _default_inputs = (await session.execute(
        select(OperationalInputs)
        .join(Project, Project.id == OperationalInputs.project_id)
        .where(
            Project.scenario_id == deal_id,
            Project.id != new_proj.id,
        )
        .order_by(Project.created_at.asc())
        .limit(1)
    )).scalar_one_or_none()
    if _default_inputs is not None:
        session.add(OperationalInputs(
            project_id=new_proj.id,
            debt_types=_default_inputs.debt_types,
            debt_structure=_default_inputs.debt_structure,
            debt_milestone_config=_default_inputs.debt_milestone_config,
            debt_sizing_mode=_default_inputs.debt_sizing_mode,
            construction_floor_pct=_default_inputs.construction_floor_pct,
            operation_reserve_months=_default_inputs.operation_reserve_months,
            deal_setup_complete=_default_inputs.deal_setup_complete,
        ))
        await session.flush()

    # ── Source share / clone decisions ────────────────────────────────────
    # Default: each project gets its OWN copy of every existing CapitalModule
    # (cloned with its own junction). User opts in to sharing a Source by
    # checking the box in the drawer — checked Sources add the new project
    # to the existing module's junction (one principal underwriting both).
    from app.models.capital import CapitalModule as _CM_create, CapitalModuleProject as _CMP_create
    _shared_ids: set[str] = {
        s.strip() for s in form.getlist("share_source_ids") if s and s.strip()
    }
    _existing_modules = list((await session.execute(
        select(_CM_create).where(_CM_create.scenario_id == deal_id)
    )).scalars())
    _max_pos = max((m.stack_position or 0) for m in _existing_modules) if _existing_modules else 0
    for _m in _existing_modules:
        if str(_m.id) in _shared_ids:
            # Share: add new project to existing junction (idempotent).
            _existing_j = (await session.execute(
                select(_CMP_create).where(
                    _CMP_create.capital_module_id == _m.id,
                    _CMP_create.project_id == new_proj.id,
                )
            )).scalar_one_or_none()
            if _existing_j is None:
                session.add(_CMP_create(
                    capital_module_id=_m.id,
                    project_id=new_proj.id,
                    amount=Decimal("0"),
                    active_from=_m.active_phase_start,
                    active_to=_m.active_phase_end,
                    auto_size=bool((_m.source or {}).get("auto_size")),
                ))
        else:
            # Clone: new CapitalModule + junction tied to new project only.
            # Reset auto-sized principal so the engine sizes for the new
            # project's own Uses; user-set amounts are preserved as a
            # starting point the user can edit afterwards.
            _src_copy = dict(_m.source or {})
            if _src_copy.get("auto_size"):
                _src_copy["amount"] = 0
            _max_pos += 1
            _new_mod = _CM_create(
                scenario_id=deal_id,
                label=_m.label,
                vehicle_type=_m.vehicle_type,
                equity_role=_m.equity_role,
                stack_position=_max_pos,
                source=_src_copy,
                carry=dict(_m.carry or {}),
                exit_terms=dict(_m.exit_terms or {}),
                active_phase_start=_m.active_phase_start,
                active_phase_end=_m.active_phase_end,
            )
            session.add(_new_mod)
            await session.flush()
            session.add(_CMP_create(
                capital_module_id=_new_mod.id,
                project_id=new_proj.id,
                amount=Decimal("0"),
                active_from=_new_mod.active_phase_start,
                active_to=_new_mod.active_phase_end,
                auto_size=bool((_new_mod.source or {}).get("auto_size")),
            ))
    await session.flush()

    # Optional Timeline Anchor — set when the user picks a parent milestone
    # in the Add Project drawer. anchor_project_id is derived from the
    # milestone's project_id so the form only needs one dropdown.
    _anchor_ms_raw = str(form.get("anchor_milestone_id", "")).strip()
    if _anchor_ms_raw:
        from app.models.milestone import Milestone as _AnchorMS
        from app.models.project import ProjectAnchor as _PA_create
        try:
            _anchor_ms_id = UUID(_anchor_ms_raw)
        except ValueError:
            _anchor_ms_id = None
        if _anchor_ms_id is not None:
            _pivot = await session.get(_AnchorMS, _anchor_ms_id)
            if _pivot is not None and _pivot.project_id != new_proj.id:
                # Confirm parent project belongs to this scenario
                _parent_proj = await session.get(Project, _pivot.project_id)
                if _parent_proj and _parent_proj.scenario_id == deal_id:
                    try:
                        _off_m = int(form.get("offset_months") or 0)
                    except (TypeError, ValueError):
                        _off_m = 0
                    try:
                        _off_d = int(form.get("offset_days") or 0)
                    except (TypeError, ValueError):
                        _off_d = 0
                    session.add(_PA_create(
                        project_id=new_proj.id,
                        anchor_project_id=_parent_proj.id,
                        anchor_milestone_id=_anchor_ms_id,
                        offset_months=_off_m,
                        offset_days=_off_d,
                    ))
                    await session.flush()

    # HTMX-driven submit (drawer form uses hx-post) — return HX-Redirect so
    # the browser does a full navigation to the new project. Plain
    # RedirectResponse retained as fallback for direct (non-HTMX) calls.
    if request.headers.get("HX-Request") == "true":
        from starlette.responses import Response as _StarletteResp
        _resp = _StarletteResp(status_code=204)
        _resp.headers["HX-Redirect"] = (
            f"/models/{deal_id}/builder?project={new_proj.id}"
        )
        return _resp
    return RedirectResponse(
        url=f"/models/{deal_id}/builder?project={new_proj.id}", status_code=303
    )


@router.post("/ui/projects/{project_id}/rename", response_class=HTMLResponse)
async def rename_project(
    request: Request,
    project_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Rename a Project. Returns the rendered breadcrumb span for HTMX swap."""
    project = await session.get(Project, project_id)
    if project is None:
        return HTMLResponse("<span>Project not found</span>", status_code=404)

    form = await request.form()
    new_name = str(form.get("name", "")).strip()
    if not new_name:
        new_name = project.name  # ignore empty submits, keep existing
    project.name = new_name[:255]
    await session.commit()

    safe = (
        new_name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )
    return HTMLResponse(
        f'<span class="proj-tab-name" '
        f'data-project-id="{project_id}" '
        f'onclick="event.preventDefault(); event.stopPropagation(); _startProjectRename(event)" '
        f'style="cursor:pointer" '
        f'title="Click to rename">{safe}</span>'
    )


@router.post("/ui/deals/{deal_id}/project/{project_id}/clone-from", response_class=HTMLResponse)
async def clone_project_from(
    deal_id: UUID,
    project_id: UUID,
    request: Request,
    session: DBSession,
) -> HTMLResponse:
    """Replace target project's financial data with a copy from another project in the same scenario."""
    from sqlalchemy import delete as sa_delete

    form = await request.form()
    source_project_id_raw = str(form.get("source_project_id", "")).strip()
    if not source_project_id_raw:
        return HTMLResponse("<p class='text-muted'>No source project selected.</p>", status_code=400)
    try:
        source_project_id = UUID(source_project_id_raw)
    except ValueError:
        return HTMLResponse("<p class='text-muted'>Invalid source project ID.</p>", status_code=400)

    target_proj = await session.get(Project, project_id)
    source_proj = await session.get(Project, source_project_id)

    if target_proj is None or source_proj is None:
        return HTMLResponse("<p class='text-muted'>Project not found.</p>", status_code=404)
    if target_proj.scenario_id != deal_id or source_proj.scenario_id != deal_id:
        return HTMLResponse("<p class='text-muted'>Projects must belong to the same scenario.</p>", status_code=400)
    if target_proj.id == source_proj.id:
        return HTMLResponse("<p class='text-muted'>Cannot clone a project onto itself.</p>", status_code=400)

    # Clear existing data on target
    await session.execute(sa_delete(Milestone).where(Milestone.project_id == project_id))
    await session.execute(sa_delete(UseLine).where(UseLine.project_id == project_id))
    await session.execute(sa_delete(IncomeStream).where(IncomeStream.project_id == project_id))
    await session.execute(sa_delete(OperatingExpenseLine).where(OperatingExpenseLine.project_id == project_id))
    if target_proj:
        target_proj.unit_mix = []
        session.add(target_proj)
    await session.execute(sa_delete(OperationalInputs).where(OperationalInputs.project_id == project_id))
    await session.flush()

    # Copy from source
    await _copy_project_data(source_proj, target_proj, session)
    await session.flush()

    return RedirectResponse(url=f"/models/{deal_id}/builder?project={project_id}", status_code=303)


@router.post("/ui/deals/{deal_id}/project/{project_id}/delete")
async def delete_deal_project(
    deal_id: UUID,
    project_id: UUID,
    session: DBSession,
) -> RedirectResponse:
    """Delete a Project and all its child rows from a Scenario.

    `deal_id` here is the Scenario id (URL kept consistent with the rest
    of the model-builder routes). The deal must keep at least one project,
    so deletion is rejected when only one remains.
    """
    from sqlalchemy import delete as sa_delete
    from app.models.portfolio import GanttEntry
    from app.models.org import ProjectVisibility
    from app.models.project import PermitStub
    from app.models.cashflow import CashFlowLineItem

    proj = await session.get(Project, project_id)
    if proj is None or proj.scenario_id != deal_id:
        return RedirectResponse(url=f"/models/{deal_id}/builder", status_code=303)

    project_count = int((await session.execute(
        select(func.count()).select_from(Project).where(Project.scenario_id == deal_id)
    )).scalar_one())
    if project_count <= 1:
        return RedirectResponse(
            url=f"/models/{deal_id}/builder?project={project_id}", status_code=303
        )

    # Non-CASCADE child tables: delete explicitly. Most other children
    # (capital_modules, draw_sources, waterfall_tiers, cash_flows,
    # operational_outputs) cascade from projects.id ondelete=CASCADE.
    # cash_flow_line_items.income_stream_id has NO CASCADE, so it must be
    # cleared before use_lines/income_streams are deleted.
    await session.execute(sa_delete(CashFlowLineItem).where(CashFlowLineItem.project_id == project_id))
    await session.execute(sa_delete(UseLine).where(UseLine.project_id == project_id))
    await session.execute(sa_delete(IncomeStream).where(IncomeStream.project_id == project_id))
    await session.execute(sa_delete(OperatingExpenseLine).where(OperatingExpenseLine.project_id == project_id))
    await session.execute(sa_delete(OperationalInputs).where(OperationalInputs.project_id == project_id))
    # Defensive deletes for tables whose FK isn't ondelete=CASCADE everywhere.
    await session.execute(sa_delete(PortfolioProject).where(PortfolioProject.project_id == project_id))
    await session.execute(sa_delete(GanttEntry).where(GanttEntry.project_id == project_id))
    await session.execute(sa_delete(ProjectVisibility).where(ProjectVisibility.project_id == project_id))
    await session.execute(sa_delete(PermitStub).where(PermitStub.project_id == project_id))
    # Milestones: must delete via raw SQL BEFORE session.delete(proj) so the
    # ORM doesn't try to null out project_id on cached milestone rows (which
    # would violate ck_milestones_single_parent — both parent FKs null).
    # Trigger-chain refs from sibling projects' milestones are auto-nulled by
    # the DB (trigger_milestone_id FK is ondelete=SET NULL).
    await session.execute(sa_delete(Milestone).where(Milestone.project_id == project_id))
    await session.flush()
    # Expire any cached state on `proj` so the ORM doesn't replay a stale
    # milestones collection during the delete cascade.
    await session.refresh(proj)

    await session.delete(proj)
    await session.commit()

    return RedirectResponse(url=f"/models/{deal_id}/builder", status_code=303)


@router.post("/ui/deals/{deal_id}/delete-variant")
async def delete_scenario_variant(
    request: Request,
    deal_id: UUID,
    session: DBSession,
) -> RedirectResponse:
    """Delete an entire Scenario variant and all its child rows.

    `deal_id` is the Scenario id (consistent with other builder routes).
    The owning Deal must keep at least one Scenario, so deletion is silently
    rejected when only one remains.
    """
    from sqlalchemy import delete as sa_delete
    from app.models.portfolio import GanttEntry
    from app.models.org import ProjectVisibility
    from app.models.project import PermitStub
    from app.models.scenario import Sensitivity, SensitivityResult
    from app.models.manifest import WorkflowRunManifest
    from app.models.cashflow import CashFlow, CashFlowLineItem, OperationalOutputs as _OpOut
    from app.models.capital import WaterfallResult, WaterfallTier as _WTier

    user = await _get_user(session, request)
    if user is None:
        raise HTTPException(status_code=403)

    scenario = await session.get(Scenario, deal_id)
    if scenario is None:
        raise HTTPException(status_code=404)

    owning_deal = await session.get(Deal, scenario.deal_id)
    if owning_deal is None or owning_deal.org_id != user.org_id:
        raise HTTPException(status_code=403)

    # "Variants" in the UI are scenarios sharing the same Opportunity via Projects
    # (same logic as deal_variants in the builder GET route).
    opp = (await session.execute(
        select(Opportunity).join(Project, Project.opportunity_id == Opportunity.id)
        .where(Project.scenario_id == deal_id).limit(1)
    )).scalar_one_or_none()

    if opp:
        sibling_ids_result = await session.execute(
            select(Scenario.id)
            .join(Project, Project.scenario_id == Scenario.id)
            .where(Project.opportunity_id == opp.id)
            .where(Scenario.id != deal_id)
            .order_by(Scenario.created_at)
            .limit(1)
        )
        survivor_id = sibling_ids_result.scalar_one_or_none()
    else:
        survivor_id = None

    if survivor_id:
        survivor_proj = (await session.execute(
            select(Project).where(Project.scenario_id == survivor_id).limit(1)
        )).scalar_one_or_none()
        redirect_url = (
            f"/models/{survivor_id}/builder?project={survivor_proj.id}"
            if survivor_proj else f"/models/{survivor_id}/builder?view=underwriting"
        )
    else:
        redirect_url = "/deals"

    # Delete parent Deal too if this was its only Scenario
    deal_scenario_count = (await session.execute(
        select(func.count()).select_from(Scenario).where(Scenario.deal_id == owning_deal.id)
    )).scalar_one()
    is_last = deal_scenario_count <= 1

    project_ids = (await session.execute(
        select(Project.id).where(Project.scenario_id == deal_id)
    )).scalars().all()

    # Many legacy FKs on scenarios.id have NO ACTION (no cascade) — must delete
    # those children explicitly before deleting the scenario row.

    if project_ids:
        # income_stream_id FK on cash_flow_line_items has no CASCADE
        await session.execute(sa_delete(CashFlowLineItem).where(CashFlowLineItem.project_id.in_(project_ids)))
        await session.execute(sa_delete(UseLine).where(UseLine.project_id.in_(project_ids)))
        await session.execute(sa_delete(IncomeStream).where(IncomeStream.project_id.in_(project_ids)))
        await session.execute(sa_delete(OperatingExpenseLine).where(OperatingExpenseLine.project_id.in_(project_ids)))
        await session.execute(sa_delete(OperationalInputs).where(OperationalInputs.project_id.in_(project_ids)))
        await session.execute(sa_delete(PortfolioProject).where(PortfolioProject.project_id.in_(project_ids)))
        await session.execute(sa_delete(GanttEntry).where(GanttEntry.project_id.in_(project_ids)))
        await session.execute(sa_delete(ProjectVisibility).where(ProjectVisibility.project_id.in_(project_ids)))
        await session.execute(sa_delete(PermitStub).where(PermitStub.project_id.in_(project_ids)))
        await session.execute(sa_delete(Milestone).where(Milestone.project_id.in_(project_ids)))

    # Scenario-level NO ACTION FKs — delete in dependency order:
    # waterfall_results/tiers reference capital_modules.id (no CASCADE), so
    # delete them before capital_modules.
    await session.execute(sa_delete(WaterfallResult).where(WaterfallResult.scenario_id == deal_id))
    await session.execute(sa_delete(_WTier).where(_WTier.scenario_id == deal_id))
    await session.execute(sa_delete(CapitalModule).where(CapitalModule.scenario_id == deal_id))
    await session.execute(sa_delete(CashFlowLineItem).where(CashFlowLineItem.scenario_id == deal_id))
    await session.execute(sa_delete(CashFlow).where(CashFlow.scenario_id == deal_id))
    await session.execute(sa_delete(_OpOut).where(_OpOut.scenario_id == deal_id))
    await session.execute(sa_delete(PortfolioProject).where(PortfolioProject.scenario_id == deal_id))
    sensitivity_ids = (await session.execute(
        select(Sensitivity.id).where(Sensitivity.scenario_id == deal_id)
    )).scalars().all()
    if sensitivity_ids:
        await session.execute(sa_delete(SensitivityResult).where(SensitivityResult.sensitivity_id.in_(sensitivity_ids)))
    await session.execute(sa_delete(Sensitivity).where(Sensitivity.scenario_id == deal_id))
    await session.execute(sa_delete(WorkflowRunManifest).where(WorkflowRunManifest.scenario_id == deal_id))

    await session.execute(sa_delete(Scenario).where(Scenario.id == deal_id))
    if is_last:
        await session.execute(sa_delete(Deal).where(Deal.id == owning_deal.id))
    await session.commit()

    return RedirectResponse(url=redirect_url, status_code=303)


@router.get("/ui/deals/{deal_id}/add-project/search", response_class=HTMLResponse)
async def add_project_search(
    deal_id: UUID,
    request: Request,
    session: DBSession,
    q: str = Query(default=""),
) -> HTMLResponse:
    """HTMX search for the Add-Project drawer. Mirrors the wizard step 2
    opportunity search UX: returns one best-match opportunity card.

    Eligibility: any opp the user can see (their org OR scraped/null-org),
    excluding archived rows. Flags rows already bound to a project on this
    scenario so the user gets a clear 'already used' message instead of a
    silent re-add attempt.
    """
    if not q or len(q.strip()) < 3:
        return HTMLResponse("")

    user = await _get_user(session, request)
    if user is None:
        return HTMLResponse("")

    q_clean = q.strip()
    q_lower = q_clean.lower()

    bound_rows = (await session.execute(
        select(Project.opportunity_id).where(Project.scenario_id == deal_id)
    )).all()
    bound_ids = {r[0] for r in bound_rows if r[0] is not None}

    stmt = (
        select(Opportunity)
        .where(
            ((Opportunity.org_id == user.org_id) | (Opportunity.org_id.is_(None))),
            Opportunity.archived.is_(False),
            (
                Opportunity.address_normalized.ilike(f"%{q_clean}%")
                | Opportunity.street.ilike(f"%{q_clean}%")
                | Opportunity.name.ilike(f"%{q_clean}%")
                | Opportunity.listing_name.ilike(f"%{q_clean}%")
                | Opportunity.apn.ilike(f"%{q_clean}%")
            ),
        )
        .order_by(
            Opportunity.org_id.desc().nullslast(),
            Opportunity.last_seen_at.desc().nullslast(),
        )
        .limit(25)
    )
    candidates = list((await session.execute(stmt)).scalars().unique())

    matched: Opportunity | None = None
    for c in candidates:
        haystack = " ".join([
            (c.address_normalized or ""),
            (c.street or ""),
            (c.name or ""),
            (c.listing_name or ""),
            (c.apn or ""),
        ]).lower()
        if q_lower in haystack:
            matched = c
            break
    if matched is None and candidates:
        matched = candidates[0]

    return templates.TemplateResponse(request, "partials/add_project_search_match.html", {
        "request": request,
        "match": matched,
        "already_bound": (matched is not None and matched.id in bound_ids),
    })


@router.post("/ui/models/{model_id}/stack-order", response_class=HTMLResponse)
async def save_stack_order(
    request: Request,
    model_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Batch-update stack_position for all capital modules from a confirm-order form submission."""
    form = await request.form()
    modules = list((await session.execute(
        select(CapitalModule).where(CapitalModule.scenario_id == model_id)
    )).scalars())
    for m in modules:
        key = f"pos_{m.id}"
        if val := _fi(form.get(key), None):
            m.stack_position = val
    await session.flush()
    _active_proj_id = await _active_project_from_request(request, session, model_id)
    panel_data = await _load_builder_data(session, model_id, project_id=_active_proj_id)
    model = await session.get(Scenario, model_id)
    return await _builder_panel_oob_response(request, model, "sources", panel_data, _active_proj_id, session)


@router.post("/ui/models/{model_id}/capital-modules/reorder", response_class=HTMLResponse)
async def reorder_capital_modules(
    request: Request,
    model_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Drag-reorder capital modules — receives ordered list of IDs, assigns stack_position 1..N."""
    form = await request.form()
    ordered_ids = form.getlist("order")
    for i, id_str in enumerate(ordered_ids, start=1):
        try:
            mod = await session.get(CapitalModule, UUID(id_str))
            if mod and mod.scenario_id == model_id:
                mod.stack_position = i
        except (ValueError, Exception):
            pass
    await session.flush()
    _active_proj_id = await _active_project_from_request(request, session, model_id)
    panel_data = await _load_builder_data(session, model_id, project_id=_active_proj_id)
    model = await session.get(Scenario, model_id)
    ctx = {"model": model, "active_module": "sources", **panel_data}
    return templates.TemplateResponse(request, "partials/model_builder_panel.html", ctx)


@router.post("/ui/models/{model_id}/settings", response_class=HTMLResponse)
async def save_model_settings(
    request: Request,
    model_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Save model name, project type, and scalar operational inputs from the Settings drawer."""
    form = await request.form()
    name = str(form.get("name", "")).strip()
    deal_type_raw = str(form.get("deal_type", "")).strip()
    expense_growth = form.get("expense_growth_rate_pct_annual")
    exit_cap = form.get("exit_cap_rate_pct")
    going_in_cap = form.get("going_in_cap_rate_pct")
    capex_reserve = form.get("capex_reserve_per_unit_annual")
    risk_free_rate = form.get("risk_free_rate_pct")
    discount_rate = form.get("discount_rate_pct")
    hold_period = form.get("hold_period_years")
    debt_structure = str(form.get("debt_structure") or "").strip() or None
    debt_sizing_mode = str(form.get("debt_sizing_mode") or "").strip() or None
    dscr_minimum = form.get("dscr_minimum")
    operation_reserve_months = form.get("operation_reserve_months")
    perm_rate_pct = form.get("perm_rate_pct")
    construction_rate_pct = form.get("construction_rate_pct")
    perm_amort_years = form.get("perm_amort_years")

    deal = await session.get(Scenario, model_id)
    if deal is None:
        return HTMLResponse("<p class='text-muted'>Not found.</p>", status_code=404)

    if name:
        deal.name = name
    if deal_type_raw:
        try:
            deal.project_type = ProjectType(deal_type_raw)
        except ValueError:
            pass
    if risk_free_rate is not None:
        try:
            deal.risk_free_rate_pct = float(risk_free_rate)
        except (ValueError, TypeError):
            pass
    if discount_rate is not None:
        try:
            deal.discount_rate_pct = float(discount_rate)
        except (ValueError, TypeError):
            pass

    await session.flush()

    # Update OperationalInputs for the default project
    default_project = (await session.execute(
        select(Project).where(Project.scenario_id == model_id).order_by(Project.created_at.asc()).limit(1)
    )).scalar_one_or_none()
    if default_project:
        inputs = (await session.execute(
            select(OperationalInputs).where(OperationalInputs.project_id == default_project.id)
        )).scalar_one_or_none()
        if inputs is None:
            inputs = OperationalInputs(project_id=default_project.id)
            session.add(inputs)

        if expense_growth is not None:
            try:
                inputs.expense_growth_rate_pct_annual = float(expense_growth)
            except (ValueError, TypeError):
                pass
        if exit_cap is not None:
            try:
                inputs.exit_cap_rate_pct = float(exit_cap)
            except (ValueError, TypeError):
                pass
        if going_in_cap is not None:
            try:
                inputs.going_in_cap_rate_pct = float(going_in_cap)
            except (ValueError, TypeError):
                pass
        if capex_reserve is not None:
            try:
                inputs.capex_reserve_per_unit_annual = float(capex_reserve)
            except (ValueError, TypeError):
                pass
        if hold_period is not None:
            try:
                hold_years = float(hold_period)
                # Hold period now sourced from operation_stabilized milestone
                # duration AND per-perm-debt CapitalModule.source.hold_term_years.
                from app.models.milestone import Milestone as _Milestone
                stabilized_ms = (await session.execute(
                    select(_Milestone).where(
                        _Milestone.project_id == default_project.id,
                        _Milestone.milestone_type == "operation_stabilized",
                    )
                )).scalar_one_or_none()
                if stabilized_ms is not None:
                    stabilized_ms.duration_days = round(hold_years * 365)
                # Mirror to all perm-debt modules so engine resolver picks it up.
                hold_int = max(1, int(round(hold_years)))
                _perm_mods = list((await session.execute(
                    select(CapitalModule).where(CapitalModule.scenario_id == model_id)
                )).scalars())
                for _cm in _perm_mods:
                    if str(getattr(_cm, "vehicle_type", "") or "").replace("VehicleType.", "") != "debt":
                        continue
                    _src = dict(_cm.source or {})
                    _src["hold_term_years"] = hold_int
                    _cm.source = _src
                    session.add(_cm)
                # Mirror to wizard staging (inputs.debt_terms) so re-opening
                # the Deal Setup wizard reflects the latest value instead of
                # the stale staging dict from initial setup.
                _dt = dict(inputs.debt_terms or {})
                _pd_entry = dict(_dt.get("permanent_debt", {}))
                _pd_entry["hold_term_years"] = hold_int
                _dt["permanent_debt"] = _pd_entry
                inputs.debt_terms = _dt
            except (ValueError, TypeError):
                pass

        if debt_structure:
            inputs.debt_structure = debt_structure
        if debt_sizing_mode:
            inputs.debt_sizing_mode = debt_sizing_mode
        if dscr_minimum:
            try:
                _dscr_val = float(dscr_minimum)
                # Per-perm-debt dscr_min replaces deal-level dscr_minimum.
                _dscr_mods = list((await session.execute(
                    select(CapitalModule).where(CapitalModule.scenario_id == model_id)
                )).scalars())
                for _cm in _dscr_mods:
                    if str(getattr(_cm, "vehicle_type", "") or "").replace("VehicleType.", "") != "debt":
                        continue
                    _src = dict(_cm.source or {})
                    _src["dscr_min"] = _dscr_val
                    _cm.source = _src
                    session.add(_cm)
                # Mirror to wizard staging.
                _dt = dict(inputs.debt_terms or {})
                _pd_entry = dict(_dt.get("permanent_debt", {}))
                _pd_entry["dscr_min"] = _dscr_val
                _dt["permanent_debt"] = _pd_entry
                inputs.debt_terms = _dt
            except (ValueError, TypeError):
                pass
        if operation_reserve_months:
            try:
                inputs.operation_reserve_months = int(operation_reserve_months)
            except Exception:
                pass
        _ahp_val = (form.get("affordable_housing_project") == "1")
        inputs.affordable_housing_project = _ahp_val
        # Scenario-level toggle — propagate to every project's OperationalInputs
        # so the flag stays consistent regardless of which project tab is
        # active when the Settings drawer is reopened.
        _sibling_oi = list((await session.execute(
            select(OperationalInputs)
            .join(Project, Project.id == OperationalInputs.project_id)
            .where(Project.scenario_id == model_id)
            .where(OperationalInputs.project_id != default_project.id)
        )).scalars())
        for _oi in _sibling_oi:
            _oi.affordable_housing_project = _ahp_val
        # Sync auto-sized CapitalModules with rate / amort form fields
        # (deal-level OperationalInputs.debt_terms is no longer authoritative).
        if any([perm_rate_pct, construction_rate_pct, perm_amort_years, debt_structure]):
            auto_mods = list((await session.execute(
                select(CapitalModule).where(CapitalModule.scenario_id == model_id)
            )).scalars())
            for cm in auto_mods:
                src = cm.source or {}
                if not src.get("auto_size"):
                    continue
                src = dict(src)
                carry = dict(cm.carry or {})
                from app.engines.cashflow import _loan_subtype_from_module as _ls_fn
                ft = _ls_fn(cm)
                if ft in ("bond",) and perm_rate_pct:
                    src["interest_rate_pct"] = float(perm_rate_pct)
                    if "phases" in carry:
                        for ph in carry["phases"]:
                            if ph.get("name") == "operation":
                                if perm_rate_pct:
                                    ph["io_rate_pct"] = float(perm_rate_pct)
                                if perm_amort_years:
                                    ph["amort_term_years"] = int(perm_amort_years)
                            elif ph.get("name") == "construction" and construction_rate_pct:
                                ph["io_rate_pct"] = float(construction_rate_pct)
                elif ft in ("permanent_debt",) and perm_rate_pct:
                    src["interest_rate_pct"] = float(perm_rate_pct)
                    if perm_amort_years:
                        carry["amort_term_years"] = int(perm_amort_years)
                elif ft in ("construction_loan",) and construction_rate_pct:
                    src["interest_rate_pct"] = float(construction_rate_pct)
                cm.source = src
                cm.carry = carry
                session.add(cm)

    _ht: dict[str, float] = {}
    for _key in ("ht_occ_green", "ht_oer_green", "ht_dscr_green", "ht_margin_green"):
        _raw = form.get(_key)
        if _raw is not None:
            try:
                _ht[_key.removeprefix("ht_")] = float(_raw)
            except (ValueError, TypeError):
                pass
    if _ht:
        deal.health_thresholds = {**(deal.health_thresholds or {}), **_ht}

    await session.commit()

    return RedirectResponse(url=f"/models/{model_id}/builder", status_code=303)


@router.get("/models/{model_id}/builder", response_class=HTMLResponse)
async def model_builder(
    request: Request,
    model_id: UUID,
    session: DBSession,
    module: str = Query(default=""),
    project: str = Query(default=""),  # optional Project.id to view a specific project
    view: str = Query(default=""),  # "underwriting" for the scenario-level rollup; default = per-project
    new: str = Query(default=""),  # set to "1" when redirected from new deal creation
    wizard: str = Query(default=""),  # "1" = single-flow deal-creation wizard mode (hide chrome)
    proforma_task_id: str = Query(default=""),  # pre-staged file from email ingest
) -> HTMLResponse:
    model = await session.get(Scenario, model_id)
    if model is None:
        return HTMLResponse("<p class='text-muted'>Model not found.</p>", status_code=404)

    owning_deal = await session.get(Deal, model.deal_id) if model.deal_id else None

    user = await _get_user(session, request)
    if settings.org_isolation_enabled:
        user_org_id = getattr(user, "org_id", None) if user is not None else None
        if user_org_id is None or owning_deal is None or owning_deal.org_id != user_org_id:
            return HTMLResponse("<p class='text-muted'>Model not found.</p>", status_code=404)

    # `project` context var = the Opportunity (purchase target), for display in topbar
    # Find Opportunity via the first Project linked to this Scenario
    _first_proj = (await session.execute(
        select(Project).where(Project.scenario_id == model_id).limit(1)
    )).scalar_one_or_none()
    opportunity = (
        await session.get(Opportunity, _first_proj.opportunity_id)
        if _first_proj and _first_proj.opportunity_id else None
    )
    dedup_count, conflicts_count = await _get_counts(session)
    address_issues_count = await _get_address_issues_count(session)

    # All Projects in this Scenario (tab row)
    deal_projects = list((await session.execute(
        select(Project).where(Project.scenario_id == model_id).order_by(Project.created_at.asc())
    )).scalars())

    # Resolve which project to view
    active_project_id: UUID | None = None
    if project:
        try:
            candidate_id = UUID(project)
            if any(p.id == candidate_id for p in deal_projects):
                active_project_id = candidate_id
        except ValueError:
            pass
    if active_project_id is None and deal_projects:
        active_project_id = deal_projects[0].id

    # Phase 3a: ``view=underwriting`` routes to the scenario-level rollup.
    # active_project_id stays populated (for tab-chip rendering); the
    # template branches on active_view to show rollup panels instead of
    # the per-project sidebar / module editor.
    active_view = "underwriting" if view == "underwriting" else "project"

    data = await _load_builder_data(session, model_id, project_id=active_project_id)

    # Load rollup data only when the Underwriting tab is active — cheap DB
    # aggregations; safe to run scenario-wide.
    underwriting_rollup_data: dict = {}
    if active_view == "underwriting":
        from app.engines.underwriting_rollup import (
            rollup_cashflow,
            rollup_draws,
            rollup_irr,
            rollup_sources,
            rollup_summary,
        )
        underwriting_rollup_data = {
            "cashflow": await rollup_cashflow(model_id, session),
            "sources": await rollup_sources(model_id, session),
            "draws": await rollup_draws(model_id, session),
            "combined_irr_pct": await rollup_irr(model_id, session),
            "summary": await rollup_summary(model_id, session),
        }
        # Phase 2d1: Timeline Anchors panel data.
        # Load current ProjectAnchor rows + every project's milestones so the
        # form can render a per-parent <optgroup> milestone dropdown.
        from app.models.milestone import Milestone as _MS
        from app.models.project import ProjectAnchor as _PA
        _anchors = list(
            (
                await session.execute(
                    select(_PA)
                    .join(Project, Project.id == _PA.project_id)
                    .where(Project.scenario_id == model_id)
                )
            ).scalars()
        )
        _ms_rows = list(
            (
                await session.execute(
                    select(_MS)
                    .join(Project, Project.id == _MS.project_id)
                    .where(Project.scenario_id == model_id)
                    .order_by(_MS.sequence_order.asc())
                )
            ).scalars()
        )
        _ms_by_project: dict = {}
        for _m in _ms_rows:
            _ms_by_project.setdefault(_m.project_id, []).append(_m)
        underwriting_rollup_data["anchors"] = {
            "by_project": {a.project_id: a for a in _anchors},
            "milestones_by_project": _ms_by_project,
        }

    # Sibling scenarios for the variant tab row: other Scenarios sharing the same Opportunity (via Projects)
    deal_variants: list = []
    if opportunity:
        _dv_result = await session.execute(
            select(Scenario)
            .join(Project, Project.scenario_id == Scenario.id)
            .where(Project.opportunity_id == opportunity.id)
            .order_by(Scenario.created_at)
        )
        deal_variants = list(_dv_result.scalars().unique())
    if not deal_variants:
        deal_variants = [model]

    # Resolve Deal.id for the breadcrumb — model.deal_id IS the parent Deal
    parent_deal_id: UUID | None = model.deal_id

    # Determine active module — deal_setup gates modules after timeline approval
    _inputs = data.get("inputs")
    _deal_setup_complete = bool(getattr(_inputs, "deal_setup_complete", False)) if _inputs else False
    _timeline_approved = data.get("timeline_approved", False)
    if not _timeline_approved:
        active_module = module or "timeline"
    elif not _deal_setup_complete and module not in ("timeline", "deal_setup", ""):
        # Redirect so the URL reflects where the user actually lands. Preserve
        # the active project so multi-project deals don't snap back to P1.
        _proj_q = f"&project={active_project_id}" if active_project_id else ""
        return RedirectResponse(url=f"/models/{model_id}/builder?module=deal_setup{_proj_q}", status_code=302)
    else:
        active_module = module or ("sources_uses" if _deal_setup_complete else "deal_setup")

    # Canonicalize URL so it always carries ?project= for per-project views.
    # Without this, HX-Current-URL on form posts/deletes lacks the project
    # param and `_active_project_from_request` returns None, silently no-op'ing
    # JSONB writes (e.g. unit-mix delete). Skip for scenario-level rollup view.
    if active_view != "underwriting" and not project and active_project_id is not None:
        _view_q = f"&view={view}" if view else ""
        _new_q = f"&new={new}" if new else ""
        # Preserve wizard=1 across the canonicalization redirect; otherwise the
        # single-flow deal-creation chrome drops on the very first hop after
        # /ui/deals/create.
        _wiz_q = f"&wizard={wizard}" if wizard else ""
        return RedirectResponse(
            url=f"/models/{model_id}/builder?module={active_module}&project={active_project_id}{_view_q}{_new_q}{_wiz_q}",
            status_code=302,
        )

    # Cash flow periods — only loaded when the cashflow module is active.
    # Multi-project: filter by active project_id so the per-project tab
    # doesn't interleave both projects' rows (which previously showed
    # Project 2's $5M acquisition on Project 1's cashflow page).
    cash_flow_rows: list = []
    if active_module == "cashflow":
        from app.models.cashflow import CashFlow
        _cf_q = select(CashFlow).where(CashFlow.scenario_id == model_id)
        if active_project_id is not None:
            _cf_q = _cf_q.where(CashFlow.project_id == active_project_id)
        cash_flow_rows = list((await session.execute(
            _cf_q.order_by(CashFlow.period)
        )).scalars())


    _ddf_recovery_by_period: dict[int, float] = {}
    _ddf_balance_by_period: dict[int, float] = {}
    if active_module == "cashflow":
        _oo_ddf_q = select(OperationalOutputs.dev_fee_balance_series).where(
            OperationalOutputs.scenario_id == model_id
        )
        if active_project_id is not None:
            _oo_ddf_q = _oo_ddf_q.where(OperationalOutputs.project_id == active_project_id)
        _ddf_series = (await session.execute(_oo_ddf_q)).scalar_one_or_none() or {}
        for _ddf_p in (_ddf_series.get("periods") or []):
            _ddf_prd = int(_ddf_p.get("period", 0))
            _ddf_recov = float(_ddf_p.get("paydown_from_waterfall") or 0) + float(_ddf_p.get("paydown_from_float_topup") or 0)
            if _ddf_recov > 0:
                _ddf_recovery_by_period[_ddf_prd] = _ddf_recov
            _ddf_balance_by_period[_ddf_prd] = float(_ddf_p.get("closing_balance") or 0)

    # Active project object (for Clone From drawer label)
    active_project = next((p for p in deal_projects if p.id == active_project_id), None)

    # Resolved anchor start date for the active project. When the project is
    # anchored to another project's milestone, the timeline wizard's Start
    # Date input is replaced by a read-only display of this computed date.
    active_project_anchor_date = None
    active_project_anchor_parent = None
    if active_project_id is not None:
        from app.models.project import ProjectAnchor as _PA_active
        _active_anchor = (await session.execute(
            select(_PA_active).where(_PA_active.project_id == active_project_id)
        )).scalar_one_or_none()
        if _active_anchor is not None:
            from app.engines.anchor_resolver import resolve_project_start_dates
            from app.models.deal import Scenario as _Scn
            _scn = await session.get(_Scn, model_id)
            await session.refresh(_scn, ["projects"])
            _resolved = await resolve_project_start_dates(_scn, session)
            active_project_anchor_date = _resolved.get(active_project_id)
            active_project_anchor_parent = next(
                (p for p in deal_projects if p.id == _active_anchor.anchor_project_id),
                None,
            )

    # Milestones for every project on the scenario — feeds the Add Project
    # drawer's "Anchor Start Date To" optgroup dropdown so the user can wire
    # the new project to a parent milestone at creation time.
    anchor_milestones_by_project: dict = {}
    if deal_projects:
        from app.models.milestone import Milestone as _MS_anchor
        _anchor_ms_rows = list(
            (
                await session.execute(
                    select(_MS_anchor)
                    .join(Project, Project.id == _MS_anchor.project_id)
                    .where(Project.scenario_id == model_id)
                    .order_by(_MS_anchor.sequence_order.asc())
                )
            ).scalars()
        )
        for _ms in _anchor_ms_rows:
            anchor_milestones_by_project.setdefault(_ms.project_id, []).append(_ms)

    # Add-Project drawer is search-driven (see GET /ui/deals/{deal_id}/add-project/search),
    # so no eager opportunity list is needed here.

    # When deal_setup is the active module, resolve wizard step and missing building data
    # so the included partials/deal_setup_wizard.html has everything it needs.
    # Deal Setup is a scenario-level wizard (income mode, debt stack), so the
    # template always reads the default project's OperationalInputs — not the
    # active project's. Otherwise Project 2's tab would render the wizard with
    # inputs=None and Step 7 (Review) crashes on `inputs.debt_sizing_mode`.
    wizard_step: int = 1
    deal_setup_inputs = data.get("inputs")
    _wizard_phases_present_bld: set[str] = set()
    # Map debt_type → list of project names sharing the existing auto module
    # (excluding the currently-active project). Step 7 of the wizard renders
    # a "shared with X" chip when this list is non-empty.
    wizard_share_info: dict[str, list[str]] = {}
    if active_module == "deal_setup" and not proforma_task_id:
        # Recover pre-staged proforma task ID from Redis when deal originated
        # from an email attachment. Key is consumed on first read so the
        # auto-load banner fires once only.
        import redis as _redis_bld  # type: ignore
        _rw_bld = _redis_bld.from_url(settings.redis_url, decode_responses=True)
        proforma_task_id = _rw_bld.getdel(f"proforma:scenario:{model_id}:email_task_id") or ""
    if active_module == "deal_setup":
        _default_proj = (await session.execute(
            select(Project).where(Project.scenario_id == model_id).order_by(Project.created_at.asc()).limit(1)
        )).scalar_one_or_none()
        if _default_proj is not None:
            deal_setup_inputs = (await session.execute(
                select(OperationalInputs).where(OperationalInputs.project_id == _default_proj.id)
            )).scalar_one_or_none()
            wizard_step = 1
            _wizard_phases_present_bld = await _wizard_phases_present(session, _default_proj)
            # Find existing auto modules + their junction-shared projects so
            # the Step 7 review can flag "shared with {project}" entries.
            from app.models.capital import CapitalModuleProject as _CMP_ws
            _auto_mods = list((await session.execute(
                select(CapitalModule).where(
                    CapitalModule.scenario_id == model_id,
                    CapitalModule.label.like("%(auto)%"),
                )
            )).scalars())
            _proj_name_by_id = {p.id: p.name for p in deal_projects}
            for _mod in _auto_mods:
                _junctions = list((await session.execute(
                    select(_CMP_ws.project_id).where(_CMP_ws.capital_module_id == _mod.id)
                )).scalars())
                _other_names = [
                    _proj_name_by_id[pid] for pid in _junctions
                    if pid != active_project_id and pid in _proj_name_by_id
                ]
                if _other_names:
                    _vt_str = str(getattr(_mod, "vehicle_type", "") or "").replace("VehicleType.", "")
                    wizard_share_info[_vt_str] = _other_names

    # Draw schedule data — loaded for draw_schedule and cashflow modules
    draw_schedule_data: dict = {}
    if active_module in ("draw_schedule", "cashflow"):
        draw_schedule_data = await _load_draw_schedule_ctx(session, model_id)
        if active_module == "cashflow":
            _sched = await _run_draw_schedule(session, model_id, writeback=False)
            if _sched:
                draw_schedule_data["schedule"] = _sched

    # Pre-render the calc-status pill so it's visible on initial page load
    # without depending on an HTMX hx-trigger="load" round-trip (which was
    # silently failing for some states, leaving the topbar empty).
    # On the Underwriting view, the pill should reflect the scenario's
    # worst-status aggregate (so it doesn't just mirror Project 1's pill);
    # on per-project tabs, it remains the active project's status.
    if active_view == "underwriting":
        _scen_st = data.get("scenario_statuses") or {}
        _uw_st = (_scen_st.get("underwriting") or {})
        _calc_status = {
            "overall": _uw_st.get("overall", "na"),
            "failing_count": int(_uw_st.get("failing_count") or 0),
            # The detail modal uses sources_uses/dscr/ltv keys; for the
            # Underwriting pill we rely on the per-project chips for drilldown
            # and just surface the aggregate severity here.
            "sources_uses": {"status": "na", "label": "See per-project chips", "detail": "", "meta": {}},
            "dscr": {"status": "na", "label": "See per-project chips", "detail": "", "meta": {}},
            "ltv": {"status": "na", "label": "See per-project chips", "detail": "", "meta": {}},
            "account_balance": {"status": "na", "label": "See per-project chips", "detail": "", "meta": {}},
        }
    else:
        # Compute _has_adj first so the Account Balance factor in
        # _compute_calc_status can read it via data["has_gap_adjustment"].
        _has_adj_pre = False
        if active_project_id is not None:
            _has_adj_pre = await _has_any_gap_adjustment(session, active_project_id)
        data["has_gap_adjustment"] = _has_adj_pre
        _calc_status = _compute_calc_status(data)
    _has_adj = False
    if active_view != "underwriting" and active_project_id is not None:
        _has_adj = await _has_any_gap_adjustment(session, active_project_id)
    calc_status_pill_html = _render_calc_status_pill_html(
        _calc_status, model_id, has_any_adjustment=_has_adj
    )

    # Override wizard_default_types from org/user resolved timeline template.
    org_discount_rate_default: str | None = None
    if user is not None:
        from app.settings.resolver import resolve_timeline_defaults as _resolve_tl_bld
        from app.settings.resolver import resolve_default as _resolve_one_bld
        _tl_template = await _resolve_tl_bld(user.id, user.org_id, session)
        _bld_deal_type = data.get("wizard_deal_type", "")
        _tl_for_dt = _tl_template.get(_bld_deal_type, {})
        data["wizard_default_types"] = [mt for mt, cfg in _tl_for_dt.items() if cfg.get("included")]
        data["wizard_timeline_template"] = _tl_template
        # Discount Rate / Hurdle placeholder — mirror IRR Hurdle Tier 1 org/user
        # default so the empty-field hint matches what the engine will use.
        try:
            org_discount_rate_default = await _resolve_one_bld(
                "irr_hurdle_pct_tier1", user.id, user.org_id, session
            )
        except Exception:
            org_discount_rate_default = None

    ctx = {
        "model": model,
        "project": active_project or opportunity,
        "breadcrumb_deal_name": owning_deal.name if owning_deal else model.name,
        "parent_deal_id": str(parent_deal_id) if parent_deal_id else None,
        "deal_variants": deal_variants,
        "deal_projects": deal_projects,
        "anchor_milestones_by_project": anchor_milestones_by_project,
        "active_project_id": str(active_project_id) if active_project_id else None,
        "active_project": active_project,
        "active_project_anchor_date": active_project_anchor_date,
        "active_project_anchor_parent": active_project_anchor_parent,
        "active_view": active_view,
        "underwriting_rollup": underwriting_rollup_data,
        "active_module": active_module,
        "deal_setup_complete": _deal_setup_complete,
        "new_deal": new == "1",
        "wizard_mode": wizard == "1",
        "proforma_task_id": proforma_task_id.strip(),
        "cash_flow_rows": cash_flow_rows,
        "ddf_recovery_by_period": _ddf_recovery_by_period,
        "ddf_balance_by_period": _ddf_balance_by_period,
        "step": wizard_step,
        "phases_present": _wizard_phases_present_bld,
        "wizard_share_info": wizard_share_info,
        "calc_status_pill_html": calc_status_pill_html,
        **data,
        # Override inputs when the wizard is active so it always reads the
        # default project's OperationalInputs (Deal Setup is scenario-level).
        # Spread AFTER `**data` so this wins.
        **({"inputs": deal_setup_inputs} if active_module == "deal_setup" else {}),
        **draw_schedule_data,
        **_base_ctx(user, dedup_count, "deals", address_issues_count, conflicts_count=conflicts_count),
        "org_set_fields": frozenset({"debt_sizing_mode", "operation_reserve_months", "capex_reserve_per_unit_annual", "risk_free_rate_pct"}),
        "org_discount_rate_default": org_discount_rate_default,
    }
    return templates.TemplateResponse(request, "model_builder.html", ctx)


@router.get("/ui/panel/{model_id}", response_class=HTMLResponse)
async def builder_panel(
    request: Request,
    model_id: UUID,
    session: DBSession,
    module: str = Query(default="sources"),
) -> HTMLResponse:
    """HTMX endpoint — returns the panel partial after a mutation."""
    from app.models.cashflow import CashFlow

    model = await session.get(Scenario, model_id)
    if model is None:
        return HTMLResponse("<p class='text-muted'>Model not found.</p>", status_code=404)

    _active_proj_id = await _active_project_from_request(request, session, model_id)
    data = await _load_builder_data(session, model_id, project_id=_active_proj_id)
    ctx: dict = {
        "model": model,
        "active_module": module,
        "active_project_id": str(_active_proj_id) if _active_proj_id else None,
        **data,
    }

    # Cash flow periods — only loaded when the cashflow module is active.
    # Filter by active project so per-project tab doesn't interleave rows.
    if module == "cashflow":
        _cf_q2 = select(CashFlow).where(CashFlow.scenario_id == model_id)
        if _active_proj_id is not None:
            _cf_q2 = _cf_q2.where(CashFlow.project_id == _active_proj_id)
        cf_rows = list((await session.execute(
            _cf_q2.order_by(CashFlow.period)
        )).scalars())
        ctx["cash_flow_rows"] = cf_rows
        _oo_ddf_q2 = select(OperationalOutputs.dev_fee_balance_series).where(
            OperationalOutputs.scenario_id == model_id
        )
        if _active_proj_id is not None:
            _oo_ddf_q2 = _oo_ddf_q2.where(OperationalOutputs.project_id == _active_proj_id)
        _ddf_s2 = (await session.execute(_oo_ddf_q2)).scalar_one_or_none() or {}
        _ddf_rec2: dict[int, float] = {}
        _ddf_bal2: dict[int, float] = {}
        for _p2 in (_ddf_s2.get('periods') or []):
            _pr2 = int(_p2.get('period', 0))
            _r2 = float(_p2.get('paydown_from_waterfall') or 0) + float(_p2.get('paydown_from_float_topup') or 0)
            if _r2 > 0:
                _ddf_rec2[_pr2] = _r2
            _ddf_bal2[_pr2] = float(_p2.get('closing_balance') or 0)
        ctx['ddf_recovery_by_period'] = _ddf_rec2
        ctx['ddf_balance_by_period'] = _ddf_bal2

    # Draw schedule data — loaded for draw_schedule and cashflow modules
    if module in ("draw_schedule", "cashflow"):
        ds_ctx = await _load_draw_schedule_ctx(session, model_id)
        ctx.update(ds_ctx)
        if module == "cashflow":
            _sched = await _run_draw_schedule(session, model_id, writeback=False)
            if _sched:
                ctx["schedule"] = _sched

    return templates.TemplateResponse(request, "partials/model_builder_panel.html", ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2d1: Timeline Anchors — upsert / remove ProjectAnchor rows.
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/ui/models/{model_id}/anchors", response_class=HTMLResponse
)
async def upsert_project_anchor(
    request: Request,
    model_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Upsert a ProjectAnchor row from the Timeline Anchors form.

    Form fields:
      project_id          — the anchored (child) project
      anchor_milestone_id — the pivot milestone on the parent project
      offset_months       — int
      offset_days         — int

    ``anchor_project_id`` is derived server-side from the picked milestone's
    ``project_id`` so the UI only needs one milestone dropdown. Returns
    HX-Redirect to the Underwriting tab so pill, staleness dots, and
    timeline re-render.
    """
    from app.models.milestone import Milestone as _MS
    from app.models.project import ProjectAnchor as _PA
    from app.engines.anchor_resolver import AnchorCycleError, _check_no_cycles
    form = await request.form()
    try:
        child_id = UUID(str(form.get("project_id", "")))
        ms_id = UUID(str(form.get("anchor_milestone_id", "")))
    except (ValueError, TypeError):
        return HTMLResponse(
            "<p class='text-muted'>Invalid project_id or anchor_milestone_id.</p>",
            status_code=400,
        )
    offset_months = int(form.get("offset_months") or 0)
    offset_days = int(form.get("offset_days") or 0)

    # Resolve parent project from the picked milestone.
    pivot = await session.get(_MS, ms_id)
    if pivot is None:
        return HTMLResponse(
            "<p class='text-muted'>Anchor milestone not found.</p>", status_code=404
        )
    parent_id = pivot.project_id
    if parent_id == child_id:
        return HTMLResponse(
            "<p class='text-muted'>A project cannot anchor to its own milestone.</p>",
            status_code=400,
        )

    # Gather every project on the scenario for the cycle check. Include the
    # proposed edge ``child ← parent`` plus all existing anchor edges.
    project_ids = [
        row[0]
        for row in (
            await session.execute(
                select(Project.id).where(Project.scenario_id == model_id)
            )
        )
    ]
    if child_id not in project_ids or parent_id not in project_ids:
        return HTMLResponse(
            "<p class='text-muted'>Projects must belong to this scenario.</p>",
            status_code=400,
        )
    existing_anchors = list(
        (
            await session.execute(
                select(_PA).where(_PA.project_id.in_(project_ids))
            )
        ).scalars()
    )
    parent_of: dict = {a.project_id: a.anchor_project_id for a in existing_anchors}
    parent_of[child_id] = parent_id  # proposed edge
    try:
        _check_no_cycles(parent_of, project_ids)
    except AnchorCycleError as exc:
        return HTMLResponse(
            f"<p class='text-muted'>Cycle rejected: {exc}</p>", status_code=400
        )

    existing = (
        await session.execute(
            select(_PA).where(_PA.project_id == child_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.anchor_project_id = parent_id
        existing.anchor_milestone_id = ms_id
        existing.offset_months = offset_months
        existing.offset_days = offset_days
        session.add(existing)
    else:
        session.add(
            _PA(
                project_id=child_id,
                anchor_project_id=parent_id,
                anchor_milestone_id=ms_id,
                offset_months=offset_months,
                offset_days=offset_days,
            )
        )
    await session.commit()

    response = HTMLResponse("")
    response.headers["HX-Redirect"] = (
        f"/models/{model_id}/builder?view=underwriting"
    )
    return response


@router.delete(
    "/ui/models/{model_id}/anchors/{project_id}", response_class=HTMLResponse
)
async def delete_project_anchor(
    model_id: UUID,
    project_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Remove a ProjectAnchor row — project reverts to its own start date."""
    from app.models.project import ProjectAnchor as _PA
    existing = (
        await session.execute(
            select(_PA).where(_PA.project_id == project_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        await session.delete(existing)
        await session.commit()
    response = HTMLResponse("")
    response.headers["HX-Redirect"] = (
        f"/models/{model_id}/builder?view=underwriting"
    )
    return response


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3c: Source coverage modal — edit which Projects a CapitalModule is
# attached to (capital_module_projects junction rows).
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/ui/models/{model_id}/sources/{source_id}/coverage",
    response_class=HTMLResponse,
)
async def source_coverage_modal(
    request: Request,
    model_id: UUID,
    source_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Render the Source Coverage modal.

    Lists every Project on the Scenario with an Included checkbox + per-
    project amount / active_from / active_to / auto_size fields. Existing
    ``capital_module_projects`` rows pre-fill their projects' inputs; not-
    yet-attached projects render with empty values + include-checkbox off.
    """
    from app.models.capital import CapitalModuleProject
    module = await session.get(CapitalModule, source_id)
    if module is None or module.scenario_id != model_id:
        return HTMLResponse(
            "<p class='text-muted'>Source not found.</p>", status_code=404
        )
    projects = list(
        (
            await session.execute(
                select(Project)
                .where(Project.scenario_id == model_id)
                .order_by(Project.created_at.asc())
            )
        ).scalars()
    )
    junction_rows = list(
        (
            await session.execute(
                select(CapitalModuleProject).where(
                    CapitalModuleProject.capital_module_id == source_id
                )
            )
        ).scalars()
    )
    by_project = {j.project_id: j for j in junction_rows}
    rows = []
    for p in projects:
        j = by_project.get(p.id)
        rows.append(
            {
                "project": p,
                "included": j is not None,
                "amount": j.amount if j else (module.source or {}).get("amount"),
                "active_from": j.active_from
                if j
                else module.active_phase_start,
                "active_to": j.active_to if j else module.active_phase_end,
                "auto_size": j.auto_size if j else False,
            }
        )
    return templates.TemplateResponse(
        request,
        "partials/underwriting/coverage_modal.html",
        {
            "model_id": str(model_id),
            "module": module,
            "rows": rows,
        },
    )


@router.post(
    "/ui/models/{model_id}/sources/{source_id}/coverage",
    response_class=HTMLResponse,
)
async def source_coverage_write(
    request: Request,
    model_id: UUID,
    source_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Write junction changes submitted by the coverage modal.

    Form fields per project (keyed by project_id):

        included[<pid>]         — "1" to attach (checkbox); absent = detach
        amount[<pid>]           — Decimal-ish string
        active_from[<pid>]      — milestone key
        active_to[<pid>]        — milestone key
        auto_size[<pid>]        — "1" / absent

    Invariant: a CapitalModule must retain at least one junction row. If the
    submitted form would leave zero, the last row stays untouched with a
    soft warning (TODO: surface warning to user — for now the handler
    silently keeps the row).
    """
    from app.models.capital import CapitalModuleProject
    module = await session.get(CapitalModule, source_id)
    if module is None or module.scenario_id != model_id:
        return HTMLResponse(
            "<p class='text-muted'>Source not found.</p>", status_code=404
        )
    form = await request.form()

    projects = list(
        (
            await session.execute(
                select(Project)
                .where(Project.scenario_id == model_id)
                .order_by(Project.created_at.asc())
            )
        ).scalars()
    )
    junction_rows = list(
        (
            await session.execute(
                select(CapitalModuleProject).where(
                    CapitalModuleProject.capital_module_id == source_id
                )
            )
        ).scalars()
    )
    by_project = {j.project_id: j for j in junction_rows}

    included_after: list[UUID] = []
    for p in projects:
        key = str(p.id)
        included = form.get(f"included[{key}]") == "1"
        if not included:
            continue
        included_after.append(p.id)

    # Orphan guard — never leave a module with zero junction rows. If the
    # submission would, keep the first existing row.
    if not included_after and junction_rows:
        fallback = junction_rows[0]
        included_after = [fallback.project_id]

    for p in projects:
        key = str(p.id)
        included = p.id in included_after
        amt_raw = (form.get(f"amount[{key}]") or "").strip()
        af = (form.get(f"active_from[{key}]") or "").strip() or None
        at = (form.get(f"active_to[{key}]") or "").strip() or None
        auto = form.get(f"auto_size[{key}]") == "1"
        amt = _fd(amt_raw)
        existing = by_project.get(p.id)
        if included:
            if existing is not None:
                if amt is not None:
                    existing.amount = amt
                existing.active_from = af
                existing.active_to = at
                existing.auto_size = auto
                session.add(existing)
            else:
                session.add(
                    CapitalModuleProject(
                        capital_module_id=source_id,
                        project_id=p.id,
                        amount=amt if amt is not None else Decimal("0"),
                        active_from=af,
                        active_to=at,
                        auto_size=auto,
                    )
                )
        elif existing is not None:
            await session.delete(existing)

    await session.commit()
    # Signal the client to reload the Underwriting page so every panel
    # (pill, staleness dots, source package, rollup CF) picks up the junction
    # change. HX-Redirect is the cleanest way from an HTMX form submission.
    response = HTMLResponse("")
    response.headers["HX-Redirect"] = (
        f"/models/{model_id}/builder?view=underwriting"
    )
    return response


# ─────────────────────────────────────────────────────────────────────────────
# Adopt Source — project-perspective recovery path. Surfaces scenario
# CapitalModules not yet junctioned to a given project, then writes the
# junction when one is chosen. Recovery for Add Project's share box being
# missed or wiped by a wizard re-run.
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/ui/models/{model_id}/projects/{project_id}/adopt-source",
    response_class=HTMLResponse,
)
async def adopt_source_modal(
    request: Request,
    model_id: UUID,
    project_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Render the Adopt Source picker for a project."""
    from app.models.capital import CapitalModuleProject
    project = await session.get(Project, project_id)
    if project is None or project.scenario_id != model_id:
        return HTMLResponse(
            "<p class='text-muted'>Project not found.</p>", status_code=404
        )
    all_modules = list((await session.execute(
        select(CapitalModule)
        .where(CapitalModule.scenario_id == model_id)
        .order_by(CapitalModule.stack_position.asc())
    )).scalars())
    attached_ids = set((await session.execute(
        select(CapitalModuleProject.capital_module_id).where(
            CapitalModuleProject.project_id == project_id
        )
    )).scalars())
    candidates = [m for m in all_modules if m.id not in attached_ids]
    return templates.TemplateResponse(
        request,
        "partials/adopt_source_modal.html",
        {
            "model_id": str(model_id),
            "project_id": str(project_id),
            "project_name": project.name,
            "candidates": candidates,
        },
    )


@router.post(
    "/ui/models/{model_id}/projects/{project_id}/adopt-source",
    response_class=HTMLResponse,
)
async def adopt_source_write(
    request: Request,
    model_id: UUID,
    project_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Attach the chosen scenario CapitalModule to this project."""
    from app.models.capital import CapitalModuleProject
    project = await session.get(Project, project_id)
    if project is None or project.scenario_id != model_id:
        return HTMLResponse(
            "<p class='text-muted'>Project not found.</p>", status_code=404
        )
    form = await request.form()
    src_raw = str(form.get("source_id", "")).strip()
    if not src_raw:
        return HTMLResponse(
            "<p class='text-muted'>Pick a Source.</p>", status_code=400
        )
    try:
        source_id = UUID(src_raw)
    except ValueError:
        return HTMLResponse(
            "<p class='text-muted'>Invalid Source.</p>", status_code=400
        )
    module = await session.get(CapitalModule, source_id)
    if module is None or module.scenario_id != model_id:
        return HTMLResponse(
            "<p class='text-muted'>Source not on this Deal.</p>", status_code=404
        )
    existing = (await session.execute(
        select(CapitalModuleProject).where(
            CapitalModuleProject.capital_module_id == source_id,
            CapitalModuleProject.project_id == project_id,
        )
    )).scalar_one_or_none()
    if existing is None:
        session.add(CapitalModuleProject(
            capital_module_id=source_id,
            project_id=project_id,
            amount=Decimal("0"),
            active_from=module.active_phase_start,
            active_to=module.active_phase_end,
            auto_size=bool((module.source or {}).get("auto_size")),
        ))
        await session.commit()
    response = HTMLResponse("")
    response.headers["HX-Redirect"] = (
        f"/models/{model_id}/builder?module=sources_uses&project={project_id}"
    )
    return response


# ─────────────────────────────────────────────────────────────────────────────
# Developer Fee explainer modal (migration 0103). Surfaces the
# dev_fee_binding_context written by the engine: per-Source allowance table,
# binding constraint, funded/deferred split, release schedule, pending
# custom-Use decisions, structural-diff signal.
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/ui/models/{model_id}/dev-fee/explainer",
    response_class=HTMLResponse,
)
async def dev_fee_explainer_modal(
    request: Request,
    model_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Render the Developer Fee calculation explainer modal."""
    user = await _get_user(session, request)
    scenario = await session.get(Scenario, model_id)
    if scenario is None:
        return HTMLResponse("<p class='text-muted'>Not found.</p>", status_code=404)
    if settings.org_isolation_enabled:
        user_org_id = getattr(user, "org_id", None) if user is not None else None
        _deal = await session.get(Deal, scenario.deal_id)
        if user_org_id is None or _deal is None or _deal.org_id != user_org_id:
            return HTMLResponse("<p class='text-muted'>Not found.</p>", status_code=404)
    # Locate the auto Dev Fee Use Line for this scenario. UseLines belong
    # to Projects which belong to a Scenario — join through Project.
    rows = list(
        (
            await session.execute(
                select(UseLine)
                .join(Project, UseLine.project_id == Project.id)
                .where(
                    Project.scenario_id == model_id,
                    UseLine.is_auto_dev_fee.is_(True),
                )
            )
        ).scalars()
    )
    if not rows:
        return HTMLResponse(
            "<p class='text-muted'>No Developer Fee row on this scenario.</p>",
            status_code=404,
        )
    auto_line = rows[0]
    ctx = dict(getattr(auto_line, "dev_fee_binding_context", {}) or {})

    # Module label lookup for nicer display.
    modules = list(
        (
            await session.execute(
                select(CapitalModule).where(
                    CapitalModule.scenario_id == model_id
                )
            )
        ).scalars()
    )
    modules_by_id = {str(m.id): m for m in modules}

    # Enrich pending decisions with labels.
    pending_raw = ctx.get("pending_custom_use_decisions") or []
    use_lines_index = {
        str(u.id): u
        for u in (
            await session.execute(
                select(UseLine)
                .join(Project, UseLine.project_id == Project.id)
                .where(Project.scenario_id == model_id)
            )
        ).scalars()
    }
    pending = []
    for pair in pending_raw:
        ul = use_lines_index.get(str(pair.get("use_line_id")))
        mod = modules_by_id.get(str(pair.get("capital_module_id")))
        pending.append(
            {
                "use_line_id": pair.get("use_line_id"),
                "capital_module_id": pair.get("capital_module_id"),
                "use_line_label": getattr(ul, "label", None) if ul else None,
                "vehicle_label": getattr(mod, "label", None) if mod else None,
            }
        )

    # Phase B: deferred Dev Fee balance schedule + float-earnings topup
    # summary, both written by the engine onto OperationalOutputs.
    outputs_row = (
        await session.execute(
            select(OperationalOutputs)
            .join(Project, Project.id == OperationalOutputs.project_id)
            .where(OperationalOutputs.scenario_id == model_id)
            .order_by(Project.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    deferred_balance_series = (
        outputs_row.dev_fee_balance_series if outputs_row else None
    )
    float_series = (
        (outputs_row.float_earnings_series or {}) if outputs_row else {}
    )
    dev_fee_topup_sources = []
    for src in (float_series.get("sources") or []):
        topup = float(src.get("dev_fee_topup_amount") or 0)
        if topup <= 0:
            continue
        parent_id = str(src.get("parent_module_id")) if src.get("parent_module_id") else None
        parent_mod = modules_by_id.get(parent_id) if parent_id else None
        dev_fee_topup_sources.append(
            {
                "parent_label": getattr(parent_mod, "label", None) or "(unknown)",
                "topup_amount": topup,
                "waterfall_milestone_id": src.get("waterfall_milestone_id") or src.get("paydown_milestone_id"),
            }
        )

    return templates.TemplateResponse(
        request,
        "partials/dev_fee_explainer_modal.html",
        {
            "model_id": str(model_id),
            "auto_line": auto_line,
            "ctx": ctx,
            "modules_by_id": modules_by_id,
            "pending": pending,
            "acquisition_treatment": getattr(
                auto_line, "dev_fee_acquisition_treatment", None
            ),
            "structural_diff_detected": bool(
                ctx.get("structural_diff_detected", False)
            ),
            "deferred_balance_series": deferred_balance_series,
            "dev_fee_topup_sources": dev_fee_topup_sources,
        },
    )


def _compute_calc_status(data: dict) -> dict:
    """Produce the 3-factor calculation status: Sources=Uses, DSCR, LTV.

    Each factor returns a dict with:
      status: "ok" | "warn" | "fail" | "na"
      label: short human summary
      detail: longer explanation for the modal
      meta: structured data (numbers) for display

    Overall status rolls up to "ok" (green) only if ALL factors are ok/na.
    """
    capital_total = float(data.get("capital_total") or 0.0)
    uses_total = float(data.get("uses_total") or 0.0)
    outputs = data.get("outputs")
    inputs = data.get("inputs")
    capital_modules = data.get("capital_modules") or []

    # ── Factor 1: Sources vs Uses ──
    gap = capital_total - uses_total
    if not capital_total and not uses_total:
        su_status = {
            "status": "na",
            "label": "No sources/uses yet",
            "detail": "Add Sources and Uses to see balance check.",
            "meta": {"capital_total": 0, "uses_total": 0, "gap": 0},
        }
    elif abs(gap) < 1.0:
        su_status = {
            "status": "ok",
            "label": "Sources = Uses",
            "detail": f"Balanced at {_fmt_currency(uses_total)}.",
            "meta": {"capital_total": capital_total, "uses_total": uses_total, "gap": 0},
        }
    elif gap > 0:
        su_status = {
            "status": "warn",
            "label": f"Surplus {_fmt_currency(gap)}",
            "detail": f"Sources ({_fmt_currency(capital_total)}) exceed Uses ({_fmt_currency(uses_total)}) by {_fmt_currency(gap)}. The extra capital isn't needed — consider reducing a debt amount or equity.",
            "meta": {"capital_total": capital_total, "uses_total": uses_total, "gap": gap},
        }
    else:
        su_status = {
            "status": "fail",
            "label": f"Gap {_fmt_currency(-gap)}",
            "detail": f"Uses ({_fmt_currency(uses_total)}) exceed Sources ({_fmt_currency(capital_total)}) by {_fmt_currency(-gap)}. Either increase debt sizing (raise LTV or DSCR), reduce Uses, or add equity.",
            "meta": {"capital_total": capital_total, "uses_total": uses_total, "gap": gap},
        }

    # ── Factor 2: DSCR ──
    dscr_val = None
    dscr_min = None
    if outputs is not None and getattr(outputs, "dscr", None):
        try:
            dscr_val = float(outputs.dscr)
        except (TypeError, ValueError):
            dscr_val = None
    # DSCR floor: same precedence as the cashflow engine —
    #   source.dscr_min → operational_inputs.debt_terms.permanent_debt.dscr_min → 1.20
    _dt_perm_dscr: float | None = None
    if inputs is not None:
        _dt = getattr(inputs, "debt_terms", None) or {}
        if isinstance(_dt, dict):
            _dt_perm = _dt.get("permanent_debt") or {}
            if isinstance(_dt_perm, dict):
                try:
                    _v_dt = _dt_perm.get("dscr_min")
                    if _v_dt is not None:
                        _dt_perm_dscr = float(_v_dt)
                except (TypeError, ValueError):
                    pass
    for _cm in capital_modules:
        if str(getattr(_cm, "vehicle_type", "") or "").replace("VehicleType.", "") != "debt":
            continue
        _src = getattr(_cm, "source", None) or {}
        try:
            _v = _src.get("dscr_min") if isinstance(_src, dict) else None
            if _v is not None:
                dscr_min = float(_v)
            elif _dt_perm_dscr is not None:
                dscr_min = _dt_perm_dscr
            else:
                dscr_min = 1.20
        except (TypeError, ValueError):
            dscr_min = _dt_perm_dscr if _dt_perm_dscr is not None else 1.20
        break

    if dscr_val is None or dscr_min is None:
        dscr_status = {
            "status": "na",
            "label": "DSCR not computed",
            "detail": "Run Compute to calculate DSCR. Requires debt modules and an operational NOI.",
            "meta": {"dscr": None, "dscr_min": dscr_min},
        }
    elif dscr_val >= dscr_min:
        headroom = dscr_val - dscr_min
        dscr_status = {
            "status": "ok",
            "label": f"DSCR {dscr_val:.2f}× (min {dscr_min:.2f}×)",
            "detail": f"DSCR is {headroom:.2f}× above the minimum. The deal comfortably covers its debt service.",
            "meta": {"dscr": dscr_val, "dscr_min": dscr_min, "headroom": headroom},
        }
    else:
        shortfall = dscr_min - dscr_val
        dscr_status = {
            "status": "fail",
            "label": f"DSCR {dscr_val:.2f}× < min {dscr_min:.2f}×",
            "detail": f"DSCR is {shortfall:.2f}× below the minimum. The deal isn't producing enough NOI to cover debt service at lender requirements. Reduce debt, increase NOI, or lower the DSCR minimum if your lender allows.",
            "meta": {"dscr": dscr_val, "dscr_min": dscr_min, "shortfall": shortfall},
        }

    # ── Factor 3: LTV ──
    # Compute actual LTV = total non-bridge debt / property value (NOI / exit cap).
    # Always shown to the user as informational. Green/red treatment ONLY when
    # sizing mode is dual_constraint (because otherwise LTV isn't a constraint
    # the engine actively targets — it's just a derived number).
    sizing_mode = (getattr(inputs, "debt_sizing_mode", None) or "") if inputs else ""
    is_dual_constraint = (sizing_mode == "dual_constraint")

    # Actual LTV calculation. Multi-project: prefer the per-project junction
    # amount over the scenario-level source.amount. source.amount holds the
    # last-sized value (P2 in last-write-wins), so on P1's tab the LTV would
    # otherwise compute against P2's much larger principal — easily pushing
    # the displayed LTV above 100% for the smaller project.
    _DEC_ZERO = Decimal("0")
    _junction_amts = data.get("capital_junction_amts") or {}
    total_non_bridge_debt = _DEC_ZERO
    for m in capital_modules:
        src = m.source or {}
        if src.get("is_bridge"):
            continue
        if str(getattr(m, "vehicle_type", "") or "").replace("VehicleType.", "") == "debt":
            _jam = _junction_amts.get(str(m.id))
            amt = _jam if _jam is not None else src.get("amount")
            if amt:
                try:
                    total_non_bridge_debt += Decimal(str(amt))
                except Exception:
                    pass

    noi_dec = Decimal(str(outputs.noi_stabilized)) if (outputs and getattr(outputs, "noi_stabilized", None)) else _DEC_ZERO
    exit_cap = Decimal(str(inputs.exit_cap_rate_pct)) if (inputs and getattr(inputs, "exit_cap_rate_pct", None)) else _DEC_ZERO
    property_value = (noi_dec / (exit_cap / Decimal("100"))) if (noi_dec > 0 and exit_cap > 0) else _DEC_ZERO
    actual_ltv_pct = float(total_non_bridge_debt / property_value * Decimal("100")) if property_value > 0 and total_non_bridge_debt > 0 else None

    # Collect per-module binding info (for dual_constraint diagnostics)
    ltv_binding_modules: list[dict] = []
    any_has_ltv = False
    for m in capital_modules:
        src = m.source or {}
        if src.get("is_bridge"):
            continue
        binding = src.get("binding_constraint")
        ltv_pct_cfg = src.get("ltv_pct")
        if ltv_pct_cfg:
            any_has_ltv = True
        if binding == "ltv":
            ltv_binding_modules.append({
                "label": m.label,
                "ltv_pct": float(ltv_pct_cfg) if ltv_pct_cfg else None,
                "amount": float(src.get("amount") or 0),
            })

    # Headline LTV cap for the "max debt at X% LTV" display. Prefer the LTV
    # setting on the first non-bridge debt module with ltv_pct; fall back to
    # the engine's 65% default when dual_constraint is on; else None.
    _headline_ltv_pct: float | None = None
    for m in capital_modules:
        src = m.source or {}
        if src.get("is_bridge"):
            continue
        _cfg = src.get("ltv_pct")
        if _cfg:
            try:
                _headline_ltv_pct = float(_cfg)
                break
            except (TypeError, ValueError):
                pass
    if _headline_ltv_pct is None and is_dual_constraint:
        _headline_ltv_pct = 65.0

    max_debt_at_ltv: float | None = None
    if _headline_ltv_pct and property_value > 0:
        max_debt_at_ltv = float(property_value * Decimal(str(_headline_ltv_pct)) / Decimal("100"))

    ltv_meta = {
        "actual_ltv_pct": actual_ltv_pct,
        "total_debt": float(total_non_bridge_debt) if total_non_bridge_debt else 0,
        "property_value": float(property_value) if property_value else 0,
        "binding_modules": ltv_binding_modules,
        "headline_ltv_pct": _headline_ltv_pct,
        "max_debt_at_ltv": max_debt_at_ltv,
    }

    if actual_ltv_pct is None:
        # Diagnose exactly which input is missing so the user knows what to fix.
        _missing: list[str] = []
        if noi_dec <= 0:
            _missing.append("stabilized NOI (run Compute)")
        if exit_cap <= 0:
            _missing.append("exit cap rate (set in Settings or the Divestment module)")
        if total_non_bridge_debt <= 0:
            _missing.append("non-bridge debt (add a permanent loan source)")
        if _missing:
            _detail = "Missing: " + "; ".join(_missing) + "."
        else:
            _detail = "Derived property value came out to zero — check inputs."
        ltv_status = {
            "status": "na",
            "label": "LTV not computable",
            "detail": _detail,
            "meta": ltv_meta,
        }
    elif not is_dual_constraint:
        # gap_fill / dscr_capped: LTV is a derived outcome, not an active
        # constraint. Treat it as healthy (ok) when it lands inside the
        # configured LTV cap, warn when it exceeds the cap. Detail still
        # notes the user can switch to Dual-Constraint to make it actively bind.
        _cap = _headline_ltv_pct
        _within_cap = (_cap is None) or (actual_ltv_pct <= float(_cap) + 0.05)
        _detail = (
            f"Debt ${float(total_non_bridge_debt):,.0f} / property value "
            f"${float(property_value):,.0f} = {actual_ltv_pct:.1f}%. Sizing "
            f"mode is '{sizing_mode or 'gap_fill'}', so LTV is a derived "
            f"outcome — not an active constraint. Switch to Dual-Constraint "
            f"in Deal Setup to size debt by MIN(LTV, DSCR, gap-fill)."
        )
        if _within_cap:
            ltv_status = {
                "status": "ok",
                "label": f"LTV {actual_ltv_pct:.1f}%",
                "detail": _detail,
                "meta": ltv_meta,
            }
        else:
            ltv_status = {
                "status": "warn",
                "label": f"LTV {actual_ltv_pct:.1f}% — exceeds {_cap}% cap",
                "detail": _detail,
                "meta": ltv_meta,
            }
    elif ltv_binding_modules and gap < -1.0:
        first = ltv_binding_modules[0]
        pct = first.get("ltv_pct")
        ltv_status = {
            "status": "fail",
            "label": f"LTV {pct}% — binding with gap" if pct else "LTV binding with gap",
            "detail": (
                f"{first['label']} is sized at its LTV cap "
                f"({pct}% of $NOI/exit_cap property value)"
                if pct else
                f"{first['label']} is sized at its LTV cap"
            ) + (
                ". DSCR may have headroom, but dual-constraint sizing uses "
                "MIN(LTV, DSCR, gap-fill) — the lowest cap wins. To close "
                "the Sources gap, raise the LTV on this source (or switch "
                "to a different sizing mode)."
            ),
            "meta": ltv_meta,
        }
    elif ltv_binding_modules:
        first = ltv_binding_modules[0]
        pct = first.get("ltv_pct")
        ltv_status = {
            "status": "ok",
            "label": f"LTV {actual_ltv_pct:.1f}% (cap {pct}%)" if pct else f"LTV {actual_ltv_pct:.1f}%",
            "detail": f"{first['label']} is sized exactly at the LTV cap. Sources = Uses, so this is fine.",
            "meta": ltv_meta,
        }
    else:
        ltv_status = {
            "status": "ok",
            "label": f"LTV {actual_ltv_pct:.1f}% (slack)",
            "detail": "LTV is not the binding constraint — DSCR or gap-fill is sizing your debt. Plenty of LTV headroom.",
            "meta": ltv_meta,
        }

    # ── Overall rollup ──
    # ── Factor 4: Account Balance (bank-account solvency proof) ──
    # Binary status read from outputs.bank_account_proof.is_solvent. Color
    # modulated by Sources Gap and Gap Adjustment so a solvent proof on a
    # deal that doesn't really balance reads as "Solvent — with caveats."
    ba_proof = (
        outputs.bank_account_proof
        if outputs is not None and getattr(outputs, "bank_account_proof", None)
        else None
    )
    has_gap_adj = bool(data.get("has_gap_adjustment"))
    has_sources_gap = (su_status["status"] == "fail")
    if not ba_proof:
        ba_status = {
            "status": "na",
            "label": "Account Balance not computed",
            "detail": "Run Compute and add a project timeline to verify the deal stays solvent through stabilization.",
            "meta": {"is_solvent": None, "max_shortfall": None, "months_simulated": None, "proof_start": None},
        }
    else:
        _is_solvent = bool(ba_proof.get("is_solvent"))
        _max_shortfall = ba_proof.get("max_shortfall", "0")
        try:
            _max_shortfall_f = float(_max_shortfall)
        except (TypeError, ValueError):
            _max_shortfall_f = 0.0
        _months = int(ba_proof.get("months_simulated") or 0)
        _proof_start = ba_proof.get("proof_start") or ""
        ba_meta = {
            "is_solvent": _is_solvent,
            "max_shortfall": _max_shortfall_f,
            "months_simulated": _months,
            "proof_start": _proof_start,
        }
        if not _is_solvent:
            ba_status = {
                "status": "fail",
                "label": f"Insolvent — max shortfall {_fmt_currency(_max_shortfall_f)}",
                "detail": (
                    f"Simulated bank account drops below the Operating Reserve floor during "
                    f"the {_months}-month proof window. This indicates an engine sizing bug "
                    f"— reserves or draws are off."
                ),
                "meta": ba_meta,
            }
        elif has_gap_adj or has_sources_gap:
            _reasons: list[str] = []
            if has_sources_gap:
                _reasons.append("a Sources Gap is open")
            if has_gap_adj:
                _reasons.append("a Gap Adjustment is active")
            ba_status = {
                "status": "warn",
                "label": "Solvent — with caveats",
                "detail": (
                    f"The bank-account proof passes over the {_months}-month window, "
                    f"but {' and '.join(_reasons)}. The proof assumes Sources cover Uses; "
                    f"solvency is structurally sound but operationally hypothetical until "
                    f"the gap is closed or the adjustments are removed."
                ),
                "meta": ba_meta,
            }
        else:
            ba_status = {
                "status": "ok",
                "label": "Solvent",
                "detail": (
                    f"Simulated bank account stays at or above the Operating Reserve floor "
                    f"for every month of the {_months}-month proof window."
                ),
                "meta": ba_meta,
            }

    factors = [su_status, dscr_status, ltv_status, ba_status]
    failing_count = sum(1 for f in factors if f["status"] in ("fail", "warn"))
    if failing_count == 0:
        overall = "ok"
    else:
        overall = "warn"

    return {
        "overall": overall,
        "failing_count": failing_count,
        "sources_uses": su_status,
        "dscr": dscr_status,
        "ltv": ltv_status,
        "account_balance": ba_status,
    }


async def _get_gap_adjustment_amounts(
    session: AsyncSession, project_id: UUID
) -> dict[str, float]:
    """Return current Gap Adjustment phantom amounts as a dict.

    Keys: ``revenue_annual`` (IncomeStream.amount_fixed_monthly × 12),
    ``opex_annual`` (OperatingExpenseLine.annual_amount for OpEx phantom),
    ``noi_annual`` (OperatingExpenseLine.annual_amount for NOI phantom),
    ``pp`` (UseLine.amount).  Missing rows resolve to 0.0. Used by the
    calc-status modal to drive per-section yellow override + adjustment
    notes (Sources=Uses ← PP; DSCR/LTV ← Revenue + OpEx).
    """
    from app.schemas.gap_adjustment_names import (
        NOI_ADJUSTMENT_LABEL,
        OPEX_ADJUSTMENT_LABEL,
        PURCHASE_PRICE_ADJUSTMENT_LABEL,
        REVENUE_ADJUSTMENT_LABEL,
    )

    out = {"revenue_annual": 0.0, "opex_annual": 0.0, "noi_annual": 0.0, "pp": 0.0}
    rev = (await session.execute(
        select(IncomeStream).where(
            IncomeStream.project_id == project_id,
            IncomeStream.label == REVENUE_ADJUSTMENT_LABEL,
        )
    )).scalars().first()
    if rev and rev.amount_fixed_monthly is not None:
        try:
            out["revenue_annual"] = float(rev.amount_fixed_monthly) * 12
        except (TypeError, ValueError):
            pass
    noi = (await session.execute(
        select(OperatingExpenseLine).where(
            OperatingExpenseLine.project_id == project_id,
            OperatingExpenseLine.label == NOI_ADJUSTMENT_LABEL,
        )
    )).scalars().first()
    if noi and noi.annual_amount is not None:
        try:
            out["noi_annual"] = float(noi.annual_amount)
        except (TypeError, ValueError):
            pass
    opex = (await session.execute(
        select(OperatingExpenseLine).where(
            OperatingExpenseLine.project_id == project_id,
            OperatingExpenseLine.label == OPEX_ADJUSTMENT_LABEL,
        )
    )).scalars().first()
    if opex and opex.annual_amount is not None:
        try:
            out["opex_annual"] = float(opex.annual_amount)
        except (TypeError, ValueError):
            pass
    pp = (await session.execute(
        select(UseLine).where(
            UseLine.project_id == project_id,
            UseLine.label == PURCHASE_PRICE_ADJUSTMENT_LABEL,
        )
    )).scalars().first()
    if pp and pp.amount is not None:
        try:
            out["pp"] = float(pp.amount)
        except (TypeError, ValueError):
            pass
    return out


async def _has_any_gap_adjustment(session: AsyncSession, project_id: UUID) -> bool:
    """True iff at least one Gap Adjustment phantom row has a nonzero amount.

    Gap Adjustment phantom rows materialize the slider deltas; the
    calc-status pill stays yellow as long as any of them are non-zero,
    even if Sources=Uses / DSCR / LTV all individually pass — the user
    needs visible feedback that the model balances "with adjustments"
    rather than "for real."
    """
    from app.schemas.gap_adjustment_names import (
        NOI_ADJUSTMENT_LABEL,
        OPEX_ADJUSTMENT_LABEL,
        PURCHASE_PRICE_ADJUSTMENT_LABEL,
        REVENUE_ADJUSTMENT_LABEL,
    )

    rev = (await session.execute(
        select(IncomeStream).where(
            IncomeStream.project_id == project_id,
            IncomeStream.label == REVENUE_ADJUSTMENT_LABEL,
        )
    )).scalars().first()
    if rev and rev.amount_fixed_monthly and float(rev.amount_fixed_monthly) != 0:
        return True
    noi = (await session.execute(
        select(OperatingExpenseLine).where(
            OperatingExpenseLine.project_id == project_id,
            OperatingExpenseLine.label == NOI_ADJUSTMENT_LABEL,
        )
    )).scalars().first()
    if noi and noi.annual_amount and float(noi.annual_amount) != 0:
        return True
    opex = (await session.execute(
        select(OperatingExpenseLine).where(
            OperatingExpenseLine.project_id == project_id,
            OperatingExpenseLine.label == OPEX_ADJUSTMENT_LABEL,
        )
    )).scalars().first()
    if opex and opex.annual_amount and float(opex.annual_amount) != 0:
        return True
    pp = (await session.execute(
        select(UseLine).where(
            UseLine.project_id == project_id,
            UseLine.label == PURCHASE_PRICE_ADJUSTMENT_LABEL,
        )
    )).scalars().first()
    if pp and pp.amount and float(pp.amount) != 0:
        return True
    return False


def _render_calc_status_pill_html(
    status: dict,
    model_id: UUID,
    has_any_adjustment: bool = False,
) -> str:
    """Render the calc-status pill button HTML from a computed status dict.

    ``has_any_adjustment`` overrides "ok" → "warn" (yellow) so a model
    that pencils only via Gap Adjustment phantom rows is visibly distinct
    from a model that pencils unaided. Real failures still surface as
    "warn" with their existing label — the override only applies to the
    otherwise-green case.
    """
    if status["overall"] == "ok" and has_any_adjustment:
        label = "⚠ Balanced w/ adjustments"
        cls = "warn"
    elif status["overall"] == "ok":
        label = "✓ Calculation Valid"
        cls = "ok"
    else:
        n = status["failing_count"]
        _specific: list[str] = []
        su = status.get("sources_uses", {})
        if su.get("status") in ("fail", "warn"):
            _gap = (su.get("meta") or {}).get("gap") or 0
            if _gap < 0:
                _specific.append(f"-${abs(float(_gap)):,.0f} Sources Gap")
            elif _gap > 0:
                _specific.append(f"+${float(_gap):,.0f} Sources Surplus")
        _dscr_f = status.get("dscr", {})
        if _dscr_f.get("status") in ("fail", "warn"):
            _dscr_val = (_dscr_f.get("meta") or {}).get("dscr")
            if _dscr_val is not None:
                _specific.append(f"{float(_dscr_val):.2f}× DSCR — Too Low")
            else:
                _specific.append("DSCR — Issue")
        _ltv_f = status.get("ltv", {})
        if _ltv_f.get("status") in ("fail", "warn"):
            _actual = (_ltv_f.get("meta") or {}).get("actual_ltv_pct")
            if _actual is not None:
                _specific.append(f"{float(_actual):.1f}% LTV — Too High")
            else:
                _specific.append("LTV — Too High")
        if n == 1 and _specific:
            label = f"⚠ {_specific[0]}"
        else:
            label = f"⚠ {n} issue{'s' if n != 1 else ''}"
        cls = "warn"
    return (
        f'<button type="button" class="calc-status-pill {cls}" '
        f'hx-get="/ui/models/{model_id}/calc-status/modal" '
        f'hx-target="#calc-status-modal-body" '
        f'hx-swap="innerHTML" '
        f'onclick="document.getElementById(\'calc-status-modal\').style.display=\'flex\'">'
        f'{label}</button>'
    )


def _is_underwriting_view_request(request: Request) -> bool:
    """True when the user is currently on the Underwriting (rollup) view.

    HTMX sends HX-Current-URL on every refresh; the pill + modal routes
    use it to decide whether to render scenario-aggregate state (when the
    parent page is on ?view=underwriting) or per-project state.
    """
    _hx_url = request.headers.get("HX-Current-URL", "")
    if not _hx_url:
        return False
    from urllib.parse import urlparse, parse_qs
    return parse_qs(urlparse(_hx_url).query).get("view", [""])[0] == "underwriting"


async def _aggregate_status_for_underwriting(
    session: AsyncSession, model_id: UUID
) -> dict:
    """Build a calc_status-shaped dict from _compute_scenario_statuses so
    the pill on Underwriting reflects the worst-project severity instead
    of mirroring the default project's pill."""
    _scen_st = await _compute_scenario_statuses(session, model_id)
    _uw_st = (_scen_st.get("underwriting") or {})
    return {
        "overall": _uw_st.get("overall", "na"),
        "failing_count": int(_uw_st.get("failing_count") or 0),
        "sources_uses": {"status": "na", "label": "See per-project chips", "detail": "", "meta": {}},
        "dscr": {"status": "na", "label": "See per-project chips", "detail": "", "meta": {}},
        "ltv": {"status": "na", "label": "See per-project chips", "detail": "", "meta": {}},
        "account_balance": {"status": "na", "label": "See per-project chips", "detail": "", "meta": {}},
    }


@router.get("/ui/models/{model_id}/calc-status", response_class=HTMLResponse)
async def model_calc_status_pill(
    request: Request,
    model_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Returns the center-top calculation status pill HTML.

    On the per-project view: 3-factor (Sources=Uses, DSCR, LTV) for the
    active project. On the Underwriting view: scenario aggregate via
    _compute_scenario_statuses so the pill stays consistent with the tab
    chips and doesn't snap to Project 1's pill after modal interactions.
    """
    has_adj = False
    if _is_underwriting_view_request(request):
        status = await _aggregate_status_for_underwriting(session, model_id)
    else:
        _active_proj_id = await _active_project_from_request(request, session, model_id)
        data = await _load_builder_data(session, model_id, project_id=_active_proj_id)
        status = _compute_calc_status(data)
        if _active_proj_id is not None:
            has_adj = await _has_any_gap_adjustment(session, _active_proj_id)
    return HTMLResponse(
        _render_calc_status_pill_html(status, model_id, has_any_adjustment=has_adj)
    )


@router.get("/ui/models/{model_id}/calc-status/modal", response_class=HTMLResponse)
async def model_calc_status_modal(
    request: Request,
    model_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Returns the modal body HTML with the 3-factor diagnostic.

    Emits an HX-Trigger response header so the topbar pill re-fetches its
    state whenever the modal opens — keeps pill and modal in lockstep.
    On Underwriting view the modal shows the aggregate (no specific
    factor drill-downs); per-project drilldowns are reachable via the
    project tab chips.
    """
    if _is_underwriting_view_request(request):
        status = await _aggregate_status_for_underwriting(session, model_id)
        # Underwriting modal shows per-project breakdown, not the 3-factor
        # diagnostic. Load full scenario_statuses + project list for the
        # template's severity-sorted card list.
        _scen_st_full = await _compute_scenario_statuses(session, model_id)
        _deal_projects = list(
            (
                await session.execute(
                    select(Project)
                    .where(Project.scenario_id == model_id)
                    .order_by(Project.created_at.asc())
                )
            ).scalars()
        )
        response = templates.TemplateResponse(
            request,
            "partials/calc_status_modal_underwriting.html",
            {
                "status": status,
                "model_id": str(model_id),
                "scenario_statuses": _scen_st_full,
                "deal_projects": _deal_projects,
            },
        )
    else:
        _active_proj_id = await _active_project_from_request(request, session, model_id)
        data = await _load_builder_data(session, model_id, project_id=_active_proj_id)
        status = _compute_calc_status(data)
        gap_adjustments = (
            await _get_gap_adjustment_amounts(session, _active_proj_id)
            if _active_proj_id is not None
            else {"revenue_annual": 0.0, "opex_annual": 0.0, "noi_annual": 0.0, "pp": 0.0}
        )
        response = templates.TemplateResponse(
            request,
            "partials/calc_status_modal.html",
            {
                "status": status,
                "model_id": str(model_id),
                "gap_adjustments": gap_adjustments,
            },
        )
    response.headers["HX-Trigger"] = "calcStatusChanged"
    return response


@router.get("/ui/models/{model_id}/balance-bar", response_class=HTMLResponse)
async def model_balance_bar(
    request: Request,
    model_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """DEPRECATED — kept for back-compat. Redirects to calc-status pill.
    Sidebar balance bar replaced by center-top status pill.
    """
    return await model_calc_status_pill(request, model_id, session)


@router.get("/ui/models/{model_id}/module-nav")
async def model_module_nav(
    request: Request,
    model_id: UUID,
    session: DBSession,
    module: str = "",
) -> _TemplateResponse:
    """Returns the module nav cards partial for sidebar live-refresh after mutations."""
    _active_proj_id = await _active_project_from_request(request, session, model_id)
    data = await _load_builder_data(session, model_id, project_id=_active_proj_id)
    ctx: dict[str, Any] = {
        "request": request,
        "active_module": module,
        "locked": not data.get("timeline_approved", False),
        "deal_setup_complete": data.get("deal_setup_complete", False),
        "nav_base_path": f"/models/{model_id}/builder",
        **{k: data.get(k) for k in (
            "capital_module_count", "capital_total",
            "use_line_count", "uses_total",
            "income_stream_count", "revenue_annual",
            "expense_line_count", "opex_annual",
            "capex_reserve_annual", "opex_total_annual",
            "carrying_annual",
            "stabilized_revenue_annual", "stabilized_opex_annual",
            "profit_runrate_after_debt",
            "equity_ownership", "org_owner_fallback",
            "deferred_uses", "deferred_total", "profit_total",
            "divestment_total", "phase_summaries", "outputs",
            "income_mode", "noi_annual",
            "unit_mix_count", "total_units",
            # Keep active project on every nav link — without this, _proj_qs
            # falls back to empty and OpEx/Sources/etc. links drop the project.
            "default_project_id",
        )},
    }
    return templates.TemplateResponse(request, "partials/model_builder_nav_cards.html", ctx)


