"""Timeline wizard, deal setup wizard, and wizard step handlers.

Extracted from ui.py as part of the Phase 2a sub-router split. Handles
all guided-creation flows: timeline milestone wizard, deal setup wizard
(income mode, proforma import, source vehicles), and approve-timeline.

Imports from ui_helpers and ui_model_outputs; never from ui.py at module level.
"""
from __future__ import annotations

import io
import json
import uuid as _uuid_mod
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import DBSession
from app.config import settings
from app.models.capital import CapitalModule, DrawSource, WaterfallTier
from app.models.deal import (
    Deal,
    Scenario,
    IncomeStream,
    IncomeStreamType,
    OperatingExpenseLine,
    OperationalInputs,
    ProjectType,
    UseLine,
)
from app.models.milestone import DEFAULT_DURATIONS, Milestone, MilestoneType
from app.models.opportunity import Opportunity
from app.models.org import User
from app.models.project import Project
from app.models.scraped_listing import ScrapedListing
from app.api.routers.ui_helpers import (
    _fd,
    _get_user,
    templates,
)
from app.api.routers.ui_model_outputs import (
    _dispatch_proforma_preflight,
    _milestone_label,
)

router = APIRouter(include_in_schema=False)

@router.post("/ui/projects/{project_id}/timeline-wizard", response_class=HTMLResponse)
async def timeline_wizard_submit(
    request: Request,
    project_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Process wizard form: clear seeded milestones, create anchor + selected milestones."""
    from sqlalchemy import delete as sa_delete
    from datetime import date as _date

    proj = await session.get(Project, project_id)
    if proj is None:
        return HTMLResponse("<p class='text-muted'>Project not found.</p>", status_code=404)

    form = await request.form()
    anchor_type_raw = str(form.get("anchor_type", ""))
    anchor_date_raw = str(form.get("anchor_date", ""))
    anchor_duration_raw = str(form.get("anchor_duration_days", "0"))
    selected_types = form.getlist("milestone_types")  # includes anchor
    new_name = str(form.get("new_name", "")).strip()
    new_deal_type_raw = str(form.get("new_deal_type", "")).strip()

    # If name/type provided (new deal wizard step 0), update deal records
    if new_name or new_deal_type_raw:
        scenario = await session.get(Scenario, proj.scenario_id)
        if scenario:
            if new_deal_type_raw:
                try:
                    new_dt = ProjectType(new_deal_type_raw)
                    scenario.project_type = new_dt
                except ValueError:
                    pass
            if new_name:
                if scenario.deal_id:
                    deal_obj = await session.get(Deal, scenario.deal_id)
                    if deal_obj:
                        deal_obj.name = new_name
                if proj.opportunity_id:
                    opp_obj = await session.get(Opportunity, proj.opportunity_id)
                    if opp_obj:
                        opp_obj.name = new_name

    try:
        anchor_mt = MilestoneType(anchor_type_raw)
    except ValueError:
        return HTMLResponse("<p class='text-muted'>Invalid anchor type.</p>", status_code=400)

    try:
        anchor_date = _date.fromisoformat(anchor_date_raw.strip()[:10])
    except (ValueError, AttributeError):
        return HTMLResponse("<p class='text-muted'>Invalid start date.</p>", status_code=400)

    try:
        anchor_duration = max(0, int(anchor_duration_raw))
    except (ValueError, TypeError):
        anchor_duration = 0

    _STABILIZED_AUTO_DAYS = 10950  # 30 years — applied when no divestment milestone
    # Default durations for acquisition-phase milestones when the user has not
    # supplied an override — sourced from DEFAULT_DURATIONS so values stay in sync.
    # Trigger chain (Pass 2 below) wires these in submitted order.
    _ACQUISITION_DEFAULT_DAYS: dict[str, int] = DEFAULT_DURATIONS["acquisition"]

    # Clear existing milestones and detach any ProjectAnchor — user is setting
    # a manual start date; they can re-anchor later via Timeline Anchors panel.
    await session.execute(sa_delete(Milestone).where(Milestone.project_id == project_id))
    from app.models.project import ProjectAnchor as _PA_wiz
    await session.execute(sa_delete(_PA_wiz).where(_PA_wiz.project_id == project_id))
    await session.flush()

    has_divestment = "divestment" in selected_types
    valid_types = {mt.value for mt in MilestoneType}

    # Filter + de-dupe while preserving submitted order (the canonical CRE
    # timeline order the user picked in the UI).  Unknown types are skipped.
    ordered_types: list[str] = []
    seen: set[str] = set()
    for mt_str in selected_types:
        if mt_str in valid_types and mt_str not in seen:
            ordered_types.append(mt_str)
            seen.add(mt_str)

    # Two-pass creation so we can build a trigger chain.
    # Pass 1: instantiate every milestone with its duration + target_date
    # on the anchor.  Pass 2: assign trigger_milestone_id so each non-anchor
    # milestone starts at the end of the previous one in submitted order.
    # Without the trigger chain, computed_start() returns None for non-
    # anchor milestones, _milestone_dates_from_orm skips them, and the
    # cashflow engine falls back to the legacy OperationalInputs scalar
    # fields (which are NULL on wizard-created deals) → every phase
    # defaults to 1 month and the carry-type math collapses.
    created: list[Milestone] = []
    for seq, mt_str in enumerate(ordered_types):
        mt = MilestoneType(mt_str)
        is_anchor = mt == anchor_mt

        # Per-milestone duration override via ``duration_{type}=N`` form field.
        override_raw = form.get(f"duration_{mt_str}")
        if override_raw is not None and str(override_raw).strip() != "":
            try:
                dur = max(0, int(override_raw))
            except (ValueError, TypeError):
                dur = 0
        elif mt == MilestoneType.operation_stabilized and not has_divestment:
            # Auto-cap stabilized at 30 years when no divestment
            dur = _STABILIZED_AUTO_DAYS
        elif mt == MilestoneType.divestment:
            # Divestment is a single-day event (sale closing date)
            dur = 1
        elif is_anchor:
            dur = anchor_duration
        elif mt_str in _ACQUISITION_DEFAULT_DAYS:
            dur = _ACQUISITION_DEFAULT_DAYS[mt_str]
        else:
            dur = 0

        row = Milestone(
            project_id=project_id,
            milestone_type=mt,
            target_date=anchor_date if is_anchor else None,
            duration_days=dur,
            sequence_order=seq,
        )
        session.add(row)
        created.append(row)

    # Flush so every Milestone gets a primary key before we wire trigger refs.
    await session.flush()

    # Pass 2: build the trigger chain in submitted order.  Each non-anchor
    # milestone triggers off the previous one with offset=0 so its start date
    # equals the prior milestone's end date (prev.start + prev.duration_days).
    prev: Milestone | None = None
    for row in created:
        if row.milestone_type == anchor_mt:
            prev = row
            continue
        if prev is not None:
            row.trigger_milestone_id = prev.id
            row.trigger_offset_days = 0
        prev = row

    await session.commit()
    _tw_url = f"/models/{proj.scenario_id}/builder?project={project_id}&module=timeline"
    if str(form.get("_wizard", "")).strip() == "1":
        _tw_url += "&wizard=1"
    return RedirectResponse(url=_tw_url, status_code=303)


@router.post("/ui/projects/{project_id}/approve-timeline", response_class=HTMLResponse)
async def approve_timeline(
    request: Request,
    project_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Toggle timeline approval on the dev Project.

    Normal POST → approve (redirect to sources).
    POST with _unapprove=1 → re-open (redirect back to timeline).
    POST with _wizard=1 → single-flow deal-creation wizard mode; redirect into
    the setup wizard with wizard chrome still active.
    """
    proj = await session.get(Project, project_id)
    if proj is None:
        return HTMLResponse("<p class='text-muted'>Project not found.</p>", status_code=404)
    form = await request.form()
    unapprove = str(form.get("_unapprove", "")).strip() == "1"
    wizard_mode = str(form.get("_wizard", "")).strip() == "1"
    proj.timeline_approved = not unapprove
    await session.commit()
    if unapprove:
        _unapp_url = f"/models/{proj.scenario_id}/builder?project={project_id}&module=timeline"
        if wizard_mode:
            _unapp_url += "&wizard=1"
        return RedirectResponse(url=_unapp_url, status_code=303)
    if wizard_mode:
        return RedirectResponse(
            url=f"/models/{proj.scenario_id}/builder?project={project_id}&module=deal_setup&wizard=1",
            status_code=303,
        )
    return RedirectResponse(url=f"/models/{proj.scenario_id}/builder?project={project_id}&module=sources", status_code=303)


async def _wizard_active_from_options(
    session: "AsyncSession",
    default_project: "Project | None",
) -> list[tuple[str, str]]:
    """Build the Active From dropdown options for wizard step 3 from the
    default project's seeded milestones. Each option is (key, label) where
    `key` is the milestone_type the wizard submits (resolved to a CapitalModule
    milestone FK during finalize). Labels fall back to a humanized form of the
    milestone_type when no override label is set.
    """
    if default_project is None:
        return []
    rows = list((await session.execute(
        select(Milestone)
        .where(Milestone.project_id == default_project.id)
        .order_by(Milestone.sequence_order, Milestone.id)
    )).scalars())
    if not rows:
        return []
    out: list[tuple[str, str]] = []
    for m in rows:
        mt = str(getattr(m, "milestone_type", "") or "").replace("MilestoneType.", "")
        label = m.label or _milestone_label(mt)
        out.append((mt, label))
    return out


async def _wizard_phases_present(
    session: "AsyncSession",
    default_project: "Project | None",
) -> set[str]:
    """Return the set of MilestoneType keys present on the default project.

    Used by Step 2 of the setup wizard to filter the debt-card list:
      - construction_loan / construction_to_perm require a Construction milestone
      - pre_development_loan requires a Pre-Development milestone

    Cards whose required phase is absent are hidden (not disabled) so the picker
    stays uncluttered. Re-derived on every wizard GET/POST — milestones are the
    source of truth, no persisted allow-list.
    """
    if default_project is None:
        return set()
    rows = list((await session.execute(
        select(Milestone.milestone_type).where(Milestone.project_id == default_project.id)
    )).scalars())
    out: set[str] = set()
    for mt in rows:
        out.add(str(mt or "").replace("MilestoneType.", ""))
    return out


async def _seed_wizard_perm_defaults(inputs: "OperationalInputs", session: "DBSession", request: "Request") -> None:
    """Seed permanent-debt staging from user/org resolved defaults when not already set."""
    _wiz_user = await _get_user(session, request)
    if _wiz_user is None:
        return
    from app.settings.resolver import resolve_all_defaults as _resolve_all
    _wiz_defs = await _resolve_all(_wiz_user.id, _wiz_user.org_id, session)
    _wiz_dt = dict(inputs.debt_terms or {})
    _wiz_pd = dict(_wiz_dt.get("permanent_debt", {}))
    _wiz_dirty = False
    for _def_key, _staging_key, _cast in (
        ("hold_term_years", "hold_term_years", int),
        ("amort_term_years", "amort_years", int),
        ("ltv_pct", "ltv_pct", float),
        ("dscr_min", "dscr_min", float),
    ):
        if _staging_key not in _wiz_pd:
            _raw = _wiz_defs.get(_def_key)
            if _raw:
                try:
                    _wiz_pd[_staging_key] = _cast(_raw)
                    _wiz_dirty = True
                except (ValueError, TypeError):
                    pass
    if _wiz_dirty:
        _wiz_dt["permanent_debt"] = _wiz_pd
        inputs.debt_terms = _wiz_dt
        session.add(inputs)
        await session.flush()
    # Org-Set debt_sizing_mode reflects org policy when no value yet on inputs.
    if not inputs.debt_sizing_mode:
        _dsm_default = _wiz_defs.get("debt_sizing_mode")
        if _dsm_default:
            inputs.debt_sizing_mode = _dsm_default
            session.add(inputs)
            await session.flush()


async def _wizard_debt_vehicles(session: "AsyncSession", user) -> list[dict]:
    """Debt+forgivable_loan Source Vehicles visible to this user (for Step 2 picker)."""
    from app.models.source_vehicle import SourceVehicle as _SV_wiz
    rows = (await session.execute(
        select(_SV_wiz).where(
            _SV_wiz.vehicle_type.in_(["debt", "forgivable_loan"]),
            (
                ((_SV_wiz.scope == "org") & (_SV_wiz.owner_id == user.org_id)) |
                ((_SV_wiz.scope == "user") & (_SV_wiz.owner_id == user.id))
            ),
        ).order_by(_SV_wiz.label)
    )).scalars().all()
    return [{"id": str(v.id), "name": v.label, "vehicle_type": v.vehicle_type} for v in rows]


@router.get("/ui/models/{model_id}/setup", response_class=HTMLResponse)
async def deal_setup_wizard_get(
    request: Request,
    model_id: UUID,
    session: DBSession,
    step: int = Query(default=-1),
) -> HTMLResponse:
    """Render a single wizard step fragment (used by Back buttons and direct links)."""
    model = await session.get(Scenario, model_id)
    if model is None:
        return HTMLResponse("Not found", status_code=404)
    default_project = (await session.execute(
        select(Project).where(Project.scenario_id == model_id).order_by(Project.created_at).limit(1)
    )).scalar_one_or_none()
    inputs = (await session.execute(
        select(OperationalInputs).where(OperationalInputs.project_id == default_project.id)
    )).scalar_one_or_none() if default_project else None

    # If step not explicitly requested, start at step 1.
    if step == -1:
        step = 1

    # Sync wizard staging (inputs.debt_terms) from live CapitalModule.source so
    # re-opening the wizard reflects edits made via Settings drawer or Edit
    # Source drawer between setups. Read-only mirror — engine still uses
    # CapitalModule.source as source of truth.
    if inputs is not None:
        _perm = (await session.execute(
            select(CapitalModule).where(
                CapitalModule.scenario_id == model_id,
                CapitalModule.vehicle_type == "debt",
            ).limit(1)
        )).scalar_one_or_none()
        if _perm is not None and isinstance(_perm.source, dict):
            _dt = dict(inputs.debt_terms or {})
            _pd_entry = dict(_dt.get("permanent_debt", {}))
            if "hold_term_years" in _perm.source:
                _pd_entry["hold_term_years"] = _perm.source["hold_term_years"]
            if "dscr_min" in _perm.source:
                _pd_entry["dscr_min"] = _perm.source["dscr_min"]
            _dt["permanent_debt"] = _pd_entry
            inputs.debt_terms = _dt
            session.add(inputs)
            await session.flush()

    # Seed perm-debt staging from user/org resolved defaults when not already set.
    if inputs is not None:
        await _seed_wizard_perm_defaults(inputs, session, request)
    _wiz_user = await _get_user(session, request)
    _svd = await _wizard_debt_vehicles(session, _wiz_user) if _wiz_user else []
    _wiz_active_from_opts = await _wizard_active_from_options(session, default_project)

    # Review (Step 6) Back button: jump to Step 2 when every selected debt has
    # a vehicle (Steps 3-5 were skipped). Otherwise return to Step 5.
    _review_back_step = 5
    if step == 6 and inputs is not None:
        _selected = inputs.debt_types or []
        _dt_now = inputs.debt_terms or {}
        if _selected and all((_dt_now.get(_ft) or {}).get("vehicle_id") for _ft in _selected):
            _review_back_step = 2

    _wiz_phases_present = await _wizard_phases_present(session, default_project)

    # Recover proforma_task_id stashed by create_deal when the deal originated
    # from an email attachment. The key is consumed (deleted) on first use so
    # the auto-load banner only fires once.
    import redis as _redis_sync  # type: ignore
    _rw = _redis_sync.from_url(settings.redis_url, decode_responses=True)
    _email_task_id = _rw.getdel(f"proforma:scenario:{model_id}:email_task_id") or ""

    return templates.TemplateResponse(request, "partials/deal_setup_wizard.html", {
        "request": request, "model": model, "inputs": inputs, "step": step,
        "source_vehicles_debt": _svd,
        "wizard_active_from_opts": _wiz_active_from_opts,
        "review_back_step": _review_back_step,
        "phases_present": _wiz_phases_present,
        "proforma_task_id": _email_task_id,
    })


async def _prefill_noi_from_listing(
    model: "Scenario",
    default_project: "Project",
    inputs: "OperationalInputs",
    session: "AsyncSession",
) -> None:
    """If the project's linked opportunity has NOI data, pre-fill
    OperationalInputs.noi_stabilized_input. Does nothing if already set."""
    if inputs.noi_stabilized_input is not None:
        return  # already set — don't overwrite a previous entry
    # Opportunity IS the listing — read NOI directly from Project.opportunity_id
    if default_project.opportunity_id is None:
        return
    listing = await session.get(ScrapedListing, default_project.opportunity_id)
    if listing is None:
        return
    noi_value = listing.proforma_noi if listing.proforma_noi is not None else listing.noi
    if noi_value is not None:
        inputs.noi_stabilized_input = noi_value
        inputs.noi_auto_seeded = True
        session.add(inputs)


@router.post("/ui/models/{model_id}/setup/step", response_class=HTMLResponse)
async def deal_setup_wizard_step(
    request: Request,
    model_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Save a wizard step's data and return the next step fragment."""
    form = await request.form()
    step = int(form.get("step", 1))
    # Field-level validation errors collected during the step handler.
    # Keyed by vehicle_type (or "_form" for cross-cutting errors).  When
    # non-empty, the same step is re-rendered instead of advancing.
    wizard_errors: dict[str, str] = {}

    model = await session.get(Scenario, model_id)
    if model is None:
        return HTMLResponse("Not found", status_code=404)
    default_project = (await session.execute(
        select(Project).where(Project.scenario_id == model_id).order_by(Project.created_at).limit(1)
    )).scalar_one_or_none()
    if default_project is None:
        return HTMLResponse("No project found", status_code=400)

    inputs = (await session.execute(
        select(OperationalInputs).where(OperationalInputs.project_id == default_project.id)
    )).scalar_one_or_none()
    if inputs is None:
        # Legacy fallback: post-refactor every Scenario is created with an
        # OperationalInputs row via app.services.scenario_factory, so this
        # branch only fires for pre-factory deals. Create an empty row and
        # apply current org/user defaults — same logic the factory uses on
        # fresh deals — so the engine never sees a NULL Type 1 field.
        from app.services.scenario_factory import apply_defaults_to_existing
        inputs = OperationalInputs(project_id=default_project.id)
        session.add(inputs)
        await session.flush()
        _wizard_user = await _get_user(session, request)
        if _wizard_user is not None:
            await apply_defaults_to_existing(
                session=session,
                scenario=model,
                inputs=inputs,
                user_id=_wizard_user.id,
                org_id=_wizard_user.org_id,
            )
        # Discount Rate / Hurdle lives on Scenario and tracks the org/user
        # IRR Hurdle Tier 1 (required return for NPV + waterfall). The factory
        # doesn't write it because it isn't in DEFAULT_REGISTRY (no scalar
        # equivalent), so the legacy fallback handles it explicitly.
        if _wizard_user is not None and model.discount_rate_pct is None:
            from decimal import Decimal as _D
            from app.settings.resolver import resolve_default as _resolve_one
            _irr1 = await _resolve_one(
                "irr_hurdle_pct_tier1", _wizard_user.id, _wizard_user.org_id, session,
            )
            if _irr1 is not None:
                try:
                    model.discount_rate_pct = _D(_irr1)
                    session.add(model)
                except Exception:
                    pass

    # Save current step's data
    if step == 1:
        # Step 1 (new): income mode + permanent-debt sizing mode + optional
        # pro forma upload. Three knobs on one screen; sizing-mode was moved
        # off Step 5 in the May 2026 wizard refactor.
        income_mode = str(form.get("income_mode") or "revenue_opex")
        if income_mode not in ("revenue_opex", "noi"):
            income_mode = "revenue_opex"
        model.income_mode = income_mode

        # Permanent-debt sizing mode (gap_fill / dscr_capped / dual_constraint)
        sizing_mode = str(form.get("debt_sizing_mode") or "").strip()
        if sizing_mode in ("gap_fill", "dscr_capped", "dual_constraint"):
            inputs.debt_sizing_mode = sizing_mode

        # Lease-up absorption (only submitted when lease_up phase present)
        _init_occ = _fd(form.get("initial_occupancy_pct"))
        if _init_occ is not None:
            inputs.initial_occupancy_pct = _init_occ
        _curve = str(form.get("lease_up_curve") or "").strip()
        if _curve in ("linear", "s_curve"):
            inputs.lease_up_curve = _curve
        _steepness = _fd(form.get("lease_up_curve_steepness"))
        if _steepness is not None:
            inputs.lease_up_curve_steepness = _steepness

        session.add(model)
        session.add(inputs)

        # Pre-fill NOI from linked opportunity's scraped listing
        if income_mode == "noi":
            await _prefill_noi_from_listing(model, default_project, inputs, session)
    elif step == 2:
        # Debt type checkboxes → debt_types list
        _valid_types = {
            "pre_development_loan", "acquisition_loan", "construction_loan",
            "bridge", "permanent_debt", "construction_to_perm",
        }
        selected = [t for t in form.getlist("debt_types") if t in _valid_types]
        if selected:
            inputs.debt_types = selected

        # Per-debt-type Source Vehicle selection → pre-populate debt_terms so
        # Step 4 shows vehicle's rate/carry without the user having to re-enter.
        from app.models.source_vehicle import SourceVehicle as _SV_s2
        _dt2 = dict(inputs.debt_terms or {})
        for _ft2 in (selected or []):
            _vid_raw = str(form.get(f"vehicle_id_{_ft2}", "") or "").strip()
            _entry2 = dict(_dt2.get(_ft2, {}))
            if not _vid_raw:
                _entry2.pop("vehicle_id", None)
                _dt2[_ft2] = _entry2
                continue
            try:
                _vid = UUID(_vid_raw)
            except (ValueError, AttributeError):
                continue
            _sv2 = (await session.execute(
                select(_SV_s2).where(_SV_s2.id == _vid)
            )).scalar_one_or_none()
            if _sv2 is None:
                continue
            _entry2["vehicle_id"] = str(_vid)
            if _sv2.interest_rate_pct is not None:
                _entry2["rate_pct"] = float(_sv2.interest_rate_pct)
            if _sv2.carry_type:
                _entry2["loan_type"] = _sv2.carry_type
            if _sv2.amort_term_years:
                _entry2["amort_years"] = int(_sv2.amort_term_years)
            _dt2[_ft2] = _entry2
        inputs.debt_terms = _dt2 if _dt2 else inputs.debt_terms
    elif step == 3:
        # Per-debt milestone & Exit Vehicle config.  The old "Active To"
        # column is gone — end of loan is derived from Exit Vehicle in the
        # finalize step (and in the engine at compute time).
        _valid_debt_types = set(inputs.debt_types or [])
        dmc: dict = {}
        for ft in _valid_debt_types:
            active_from  = form.get(f"{ft}_active_from") or ""
            # New field name; accept the old "retired_by" for form re-submits
            # that round-tripped through the old POST shape.
            exit_vehicle = (
                form.get(f"{ft}_exit_vehicle")
                or form.get(f"{ft}_retired_by")
                or ""
            )
            # Normalise: legacy 'perpetuity' → 'maturity'.
            if exit_vehicle == "perpetuity":
                exit_vehicle = "maturity"
            # Validate vehicle: must be 'maturity' | 'sale' | another picked debt.
            if exit_vehicle and exit_vehicle not in {"maturity", "sale"} and exit_vehicle not in _valid_debt_types:
                wizard_errors[ft] = (
                    f"Exit Vehicle {exit_vehicle!r} is not one of the selected debt types."
                )
                continue
            if exit_vehicle == ft:
                wizard_errors[ft] = "A loan cannot retire itself. Pick a different Exit Vehicle."
                continue
            if active_from or exit_vehicle:
                dmc[ft] = {
                    "active_from":  active_from,
                    "exit_vehicle": exit_vehicle or "maturity",
                }
        if wizard_errors:
            # Re-render step 3 with errors; do not advance
            pass
        elif dmc:
            inputs.debt_milestone_config = dmc
    elif step == 4:
        # Per-debt terms: loan type, rate, amort years
        # Validate with explicit try/except and range checks so bad input
        # surfaces as a field error, not a 500.
        _VALID_LOAN_TYPES = {
            "io_only", "interest_reserve", "capitalized_interest",
            "pi", "io_then_pi",
        }
        dt_terms = dict(inputs.debt_terms or {})
        for ft in (inputs.debt_types or []):
            loan_type   = form.get(f"{ft}_loan_type")
            rate_raw    = form.get(f"{ft}_rate_pct")
            amort_raw   = form.get(f"{ft}_amort_years")
            hold_raw    = form.get(f"{ft}_hold_term_years")
            entry = dict(dt_terms.get(ft, {}))

            if loan_type:
                if loan_type not in _VALID_LOAN_TYPES:
                    wizard_errors[ft] = f"Unknown loan type: {loan_type!r}"
                    continue
                entry["loan_type"] = loan_type

            if rate_raw:
                try:
                    rate_val = float(rate_raw)
                except (TypeError, ValueError):
                    wizard_errors[ft] = f"Interest rate must be a number (got {rate_raw!r})"
                    continue
                if rate_val < 0 or rate_val > 30:
                    wizard_errors[ft] = (
                        f"Interest rate {rate_val}% is outside 0–30%. Enter a realistic rate."
                    )
                    continue
                entry["rate_pct"] = rate_val

            if amort_raw:
                try:
                    amort_val = int(amort_raw)
                except (TypeError, ValueError):
                    wizard_errors[ft] = f"Amortization must be a whole number of years (got {amort_raw!r})"
                    continue
                if amort_val < 1 or amort_val > 40:
                    wizard_errors[ft] = f"Amortization {amort_val} years is outside 1–40 years."
                    continue
                entry["amort_years"] = amort_val

            if hold_raw:
                try:
                    hold_val = int(hold_raw)
                except (TypeError, ValueError):
                    wizard_errors[ft] = f"Hold term must be a whole number of years (got {hold_raw!r})"
                    continue
                if hold_val < 1 or hold_val > 40:
                    wizard_errors[ft] = f"Hold term {hold_val} years is outside 1–40 years."
                    continue
                entry["hold_term_years"] = hold_val

            if entry:
                dt_terms[ft] = entry
        if not wizard_errors:
            inputs.debt_terms = dt_terms
    elif step == 5:
        # Per-debt sizing — LTV / fixed amount / minimum DSCR. The permanent-
        # debt sizing-mode picker moved to Step 1 in the May 2026 refactor;
        # this step is no longer responsible for it. Reserves & Floors (old
        # Step 6) is gone entirely — those fields come from org defaults.
        dt_terms = dict(inputs.debt_terms or {})
        for ft in (inputs.debt_types or []):
            sizing_approach = form.get(f"{ft}_sizing_approach")
            ltv_pct         = form.get(f"{ft}_ltv_pct")
            fixed_amount    = form.get(f"{ft}_fixed_amount")
            if sizing_approach or ltv_pct or fixed_amount:
                entry = dict(dt_terms.get(ft, {}))
                if sizing_approach: entry["sizing_approach"] = sizing_approach
                if ltv_pct:         entry["ltv_pct"]        = float(ltv_pct)
                if fixed_amount:    entry["fixed_amount"]   = float(fixed_amount)
                dt_terms[ft] = entry
        dscr_val = form.get("dscr_minimum")
        if dscr_val:
            try:
                _perm = dict(dt_terms.get("permanent_debt", {}))
                _perm["dscr_min"] = float(dscr_val)
                dt_terms["permanent_debt"] = _perm
            except (TypeError, ValueError):
                pass
        inputs.debt_terms = dt_terms

    _post_user = await _get_user(session, request)
    _post_svd = await _wizard_debt_vehicles(session, _post_user) if _post_user else []

    # If validation failed, don't persist and re-render the same step with errors
    if wizard_errors:
        _post_active_from_opts = await _wizard_active_from_options(session, default_project)
        _post_phases_present = await _wizard_phases_present(session, default_project)
        return templates.TemplateResponse(request, "partials/deal_setup_wizard.html", {
            "request": request, "model": model, "inputs": inputs, "step": step,
            "wizard_errors": wizard_errors, "source_vehicles_debt": _post_svd,
            "wizard_active_from_opts": _post_active_from_opts,
            "phases_present": _post_phases_present,
        })

    session.add(inputs)
    await session.commit()
    await session.refresh(inputs)
    await session.refresh(model)

    # ── Step 1 → optional pro forma upload ────────────────────────────────
    # New (May 2026): the upload zone lives directly on Step 1 instead of a
    # separate page. When a file is attached we dispatch into the preflight
    # logic that used to live behind /proforma-preflight. With no file the
    # user clicked "Skip Import →" (or NOI mode) and we advance to Step 2.
    if step == 1:
        from starlette.datastructures import UploadFile as _StarletteUploadFile
        _pf_all = [
            f for f in form.getlist("file")
            if isinstance(f, _StarletteUploadFile) and (f.filename or "")
        ]
        if len(_pf_all) > 1:
            # Multi-file: stage all, extract sheet names / page counts, show
            # combined config table (shared partial) for user to configure all
            # files at once. Submit goes to /upload-proforma-multi.
            import redis as _redis_mf
            import openpyxl as _openpyxl_mf
            import os as _os_mf
            r_mf = _redis_mf.from_url(settings.redis_url, decode_responses=False)
            files_ctx: list[dict] = []
            for pf in _pf_all:
                _content = await pf.read()
                _fname = pf.filename or ""
                _ext = _os_mf.path.splitext(_fname)[1].lower().lstrip(".")
                _fkind = "xlsx" if _ext in {"xlsx", "xlsm", "xlsb"} else "doc"
                _tid = str(_uuid_mod.uuid4())
                r_mf.set(f"proforma:{_tid}:file", _content, ex=86400)
                r_mf.set(f"proforma:{_tid}:filename", _fname.encode(), ex=86400)
                _sheet_names: list[str] = []
                _page_count: int | None = None
                if _fkind == "xlsx":
                    try:
                        _wb = _openpyxl_mf.load_workbook(
                            io.BytesIO(_content), data_only=True, read_only=True)
                        _sheet_names = list(_wb.sheetnames)
                        _wb.close()
                    except Exception:
                        pass
                elif _ext == "pdf":
                    try:
                        import pdfplumber as _pdp_mf  # type: ignore
                        with _pdp_mf.open(io.BytesIO(_content)) as _pdf:
                            _page_count = len(_pdf.pages)
                    except Exception:
                        pass
                files_ctx.append({
                    "task_id": _tid,
                    "filename": _fname,
                    "file_kind": _fkind,
                    "sheet_names": _sheet_names,
                    "single_sheet": len(_sheet_names) == 1,
                    "page_count": _page_count,
                    "size_bytes": len(_content),
                })
            return templates.TemplateResponse(
                request,
                "partials/proforma_multi_preflight.html",
                {"model_id": model_id, "files": files_ctx},
            )
        elif _pf_all:
            return await _dispatch_proforma_preflight(
                request=request, model_id=model_id, upload=_pf_all[0],
            )

    # ── Step 2 → vehicle-skip routing ─────────────────────────────────────
    # If every selected debt type was assigned a Source Vehicle, Steps 3-5
    # (milestones, terms, sizing) are redundant — the vehicle carries that
    # data already. Jump straight to Review. If ANY debt is on "Use defaults"
    # we drop into 3/4/5 for all of them (per-debt skipping is future work).
    next_step = step + 1
    review_back_step = step  # default: Review's back goes to the prior step
    if step == 2:
        _selected = inputs.debt_types or []
        _dt_now = inputs.debt_terms or {}
        _all_have_vehicle = bool(_selected) and all(
            (_dt_now.get(_ft) or {}).get("vehicle_id") for _ft in _selected
        )
        if _all_have_vehicle:
            next_step = 6
            review_back_step = 2

    # Seed perm-debt defaults so Step 4 shows user/org preference, not template fallback.
    await _seed_wizard_perm_defaults(inputs, session, request)
    _next_active_from_opts = await _wizard_active_from_options(session, default_project)
    _next_phases_present = await _wizard_phases_present(session, default_project)
    return templates.TemplateResponse(request, "partials/deal_setup_wizard.html", {
        "request": request, "model": model, "inputs": inputs, "step": next_step,
        "source_vehicles_debt": _post_svd,
        "wizard_active_from_opts": _next_active_from_opts,
        "review_back_step": review_back_step,
        "phases_present": _next_phases_present,
    })


@router.post("/ui/models/{model_id}/setup/complete")
async def deal_setup_wizard_complete(
    request: Request,
    model_id: UUID,
    session: DBSession,
) -> Response:
    """Finalize setup: mark complete and auto-create the primary debt CapitalModule(s)."""
    from app.models.capital import CapitalModule, CapitalModuleProject

    model = await session.get(Scenario, model_id)
    if model is None:
        return HTMLResponse("Not found", status_code=404)
    default_project = (await session.execute(
        select(Project).where(Project.scenario_id == model_id).order_by(Project.created_at).limit(1)
    )).scalar_one_or_none()
    if default_project is None:
        return HTMLResponse("No project", status_code=400)

    inputs = (await session.execute(
        select(OperationalInputs).where(OperationalInputs.project_id == default_project.id)
    )).scalar_one_or_none()
    if inputs is None:
        return HTMLResponse("No inputs", status_code=400)

    form = await request.form()
    dt = inputs.debt_terms or {}
    debt_types = inputs.debt_types  # None for pre-migration deals
    debt_structure = inputs.debt_structure or "perm_only"

    # Remove any existing auto-created debt modules (clean re-run).
    # Cascade dependent rows manually first — WaterfallResult and
    # WaterfallTier both reference capital_module_id with NOT NULL +
    # default-NO-ACTION FKs, so SQLAlchemy's default "set FK to NULL on
    # parent delete" behavior throws a NotNullViolation. Delete the
    # dependents explicitly to keep the wizard re-runnable on scenarios
    # that have been computed before.
    from sqlalchemy import delete as _sa_delete
    from app.models.capital import WaterfallResult as _WR
    existing_auto = list((await session.execute(
        select(CapitalModule).where(
            CapitalModule.scenario_id == model_id,
            CapitalModule.label.like("%(auto)%"),
        )
    )).scalars())
    # Snapshot share state so wizard re-runs don't silently strip junctions
    # added by Add Project. Map vehicle_type → set of non-default project IDs
    # that had a junction on the OLD auto module. After recreation we restore
    # those junctions on the matching new module so shared auto-debt persists.
    _prior_auto_shares: dict[str, set[UUID]] = {}
    if existing_auto:
        _prior_junctions = list((await session.execute(
            select(CapitalModuleProject).where(
                CapitalModuleProject.capital_module_id.in_([cm.id for cm in existing_auto])
            )
        )).scalars())
        _ft_by_mod = {cm.id: str(getattr(cm, "vehicle_type", "") or "").replace("VehicleType.", "") for cm in existing_auto}
        for _j in _prior_junctions:
            if _j.project_id == default_project.id:
                continue
            _ft = _ft_by_mod.get(_j.capital_module_id)
            if _ft:
                _prior_auto_shares.setdefault(_ft, set()).add(_j.project_id)
    if existing_auto:
        _auto_ids = [cm.id for cm in existing_auto]
        await session.execute(
            _sa_delete(_WR).where(_WR.capital_module_id.in_(_auto_ids))
        )
        await session.execute(
            _sa_delete(WaterfallTier).where(WaterfallTier.capital_module_id.in_(_auto_ids))
        )
        await session.flush()
    for cm in existing_auto:
        await session.delete(cm)

    # Closing-cost pre-load data collected during Phase B module creation.
    # Populated in the loop below; used after both branches to write $0 Use line stubs.
    _cc_preload_modules: list[dict] = []

    # If a Source Vehicle was chosen at deal creation, use it for the auto module
    # instead of the wizard's per-debt-type config.
    _sv_module_created = False
    if model.source_vehicle_id is not None:
        from app.models.source_vehicle import SourceVehicle as _SV2
        _sv = (await session.execute(
            select(_SV2).where(_SV2.id == model.source_vehicle_id)
        )).scalar_one_or_none()
        if _sv is not None:
            _sv_module_created = True
            _sv_label = f"{_sv.label} (auto)"
            _sv_ft_str = _sv.vehicle_type or "debt"  # for _cc_preload_modules key
            _sv_source = dict(_sv.source_config or {})
            _sv_source.setdefault("auto_size", True)
            session.add(CapitalModule(
                scenario_id=model_id,
                label=_sv_label,
                vehicle_type=_sv.vehicle_type,
                equity_role=_sv.equity_role,
                stack_position=1,
                source=_sv_source,
                carry=_sv.carry_config or {},
                exit_terms=_sv.exit_config or {"exit_type": "full_payoff", "trigger": "end of hold period"},
                active_phase_start=_sv.active_phase_start or "acquisition",
                active_phase_end=_sv.active_phase_end or "stabilized",
                source_vehicle_id=model.source_vehicle_id,
            ))
            _cc_preload_modules.append({
                "loan_subtype": _sv_ft_str,
                "label": _sv_label,
                "active_phase_start": _sv.active_phase_start or "acquisition",
            })

    if debt_types and not _sv_module_created:
        # ── New multi-debt path ───────────────────────────────────────────────
        # Build one CapitalModule per selected debt type using debt_milestone_config
        # and debt_terms (per-debt dicts).  Falls back to sensible defaults if the
        # wizard steps were skipped (e.g. re-running on a backfilled deal).
        dmc = inputs.debt_milestone_config or {}

        # Valid debt sub-type keys (used to validate/skip unknown entries).
        _FT_MAP: set[str] = {
            "pre_development_loan", "acquisition_loan", "construction_loan",
            "bridge", "permanent_debt", "construction_to_perm",
        }
        _LABEL: dict[str, str] = {
            "pre_development_loan": "Pre-Development Loan",
            "acquisition_loan":     "Acquisition Loan",
            "construction_loan":    "Construction Loan",
            "bridge":               "Bridge Loan",
            "permanent_debt":       "Permanent Debt",
            "construction_to_perm": "Construction-to-Perm",
        }
        # Defaults must match deal_setup_wizard.html Step 4 (_dt_default_*).
        # Any mismatch means wizard re-runs show ghost field changes.
        _DEFAULT_RATE: dict[str, float] = {
            "pre_development_loan": 8.0,
            "acquisition_loan":     6.5,
            "construction_loan":    6.0,
            "bridge":               7.5,
            "permanent_debt":       5.0,
            "construction_to_perm": 5.0,
        }
        _DEFAULT_LOAN_TYPE: dict[str, str] = {
            "pre_development_loan": "interest_reserve",
            "acquisition_loan":     "interest_reserve",
            "construction_loan":    "interest_reserve",
            "bridge":               "interest_reserve",
            "permanent_debt":       "pi",
            "construction_to_perm": "io_then_pi",
        }
        _DEFAULT_FROM: dict[str, str] = {
            "pre_development_loan": "pre_construction",
            "acquisition_loan":     "acquisition",
            "construction_loan":    "acquisition",
            "bridge":               "lease_up",
            "permanent_debt":       "lease_up",
            "construction_to_perm": "acquisition",
        }
        # Exit Vehicle default per debt type — first available retirer in the
        # preference chain wins, else fall back to the trailing sentinel.
        # Mirrors the Jinja `_vehicle_pref_chain` in deal_setup_wizard.html
        # (§3 Milestones & Retirement).
        _VEHICLE_PREF_CHAIN: dict[str, list[str]] = {
            "pre_development_loan": ["acquisition_loan","construction_loan","construction_to_perm","bridge","maturity"],
            "acquisition_loan":     ["construction_loan","construction_to_perm","permanent_debt","bridge","maturity"],
            "construction_loan":    ["permanent_debt","construction_to_perm","sale","maturity"],
            "bridge":               ["permanent_debt","sale","maturity"],
            "permanent_debt":       ["maturity"],
            "construction_to_perm": ["sale","maturity"],
        }

        def _default_vehicle(ft_str: str, picked: set[str]) -> str:
            for cand in _VEHICLE_PREF_CHAIN.get(ft_str, ["maturity"]):
                if cand in {"maturity", "sale"}:
                    return cand
                if cand in picked and cand != ft_str:
                    return cand
            return "maturity"

        # Phase-rank lookup used to derive active_phase_end from the resolved
        # vehicle.  Mirrors cashflow._APS_TO_RANK; duplicated here to avoid a
        # circular import between the router and the engine.
        _APS_TO_PHASE: dict[int, str] = {
            0: "acquisition", 2: "pre_construction", 3: "construction",
            4: "lease_up", 5: "stabilized", 6: "exit",
        }
        _PHASE_TO_RANK: dict[str, int] = {
            "acquisition": 0, "close": 0,
            "pre_construction": 2,
            "construction": 3,
            "lease_up": 4, "operation_lease_up": 4,
            "stabilized": 5, "operation_stabilized": 5,
            "exit": 6, "divestment": 6,
        }

        # ── Pass 1: pre-generate UUIDs so Exit Vehicle can reference siblings
        # by id.  Collect per-debt config so Pass 2 can resolve vehicle and
        # derive active_phase_end without rescanning the form.
        _picked = {ft_str for ft_str in debt_types if ft_str in _FT_MAP}
        _module_plan: list[dict] = []
        _uuid_by_debt_type: dict[str, "_uuid_mod.UUID"] = {}
        for pos, ft_str in enumerate(debt_types, start=1):
            if ft_str not in _FT_MAP:
                continue
            cfg   = dmc.get(ft_str, {})
            terms = dt.get(ft_str, {})
            rate        = float(terms.get("rate_pct") or _DEFAULT_RATE.get(ft_str, 6.0))
            loan_type   = terms.get("loan_type") or _DEFAULT_LOAN_TYPE.get(ft_str, "io_only")
            amort_years = int(terms.get("amort_years") or 30)
            ltv_pct     = float(terms.get("ltv_pct")) if terms.get("ltv_pct") is not None else None
            active_from = cfg.get("active_from") or _DEFAULT_FROM.get(ft_str, "acquisition")
            # Stabilized-acquisition deals: the perm loan IS the acquisition
            # financing — no construction/lease-up to refinance out of. Default
            # active_from = "acquisition" so closing costs flow at close instead
            # of dumping into month 1 of stabilized (where they'd otherwise
            # show as a phantom -$25K NCF spike). Value-add / new-construction
            # keep the standard "lease_up" default — perm refinances out the
            # construction loan at stabilization, costs hit then.
            _scn_proj_type = str(getattr(model, "project_type", "") or "").replace("ProjectType.", "")
            if (
                ft_str == "permanent_debt"
                and _scn_proj_type == "acquisition"
                and not cfg.get("active_from")
            ):
                active_from = "acquisition"

            # Resolve Exit Vehicle — legacy 'retired_by' + 'active_to' are
            # honoured as fallbacks so in-flight wizard re-submits still work
            # while old rows propagate through the finalize path.
            vehicle_raw = (cfg.get("exit_vehicle") or cfg.get("retired_by") or "").strip()
            if vehicle_raw == "perpetuity" or not vehicle_raw:
                vehicle_raw = _default_vehicle(ft_str, _picked)
            _module_plan.append({
                "pos": pos,
                "ft_str": ft_str,
                "rate": rate,
                "loan_type": loan_type,
                "amort_years": amort_years,
                "active_from": active_from,
                "vehicle_raw": vehicle_raw,
            })
            _uuid_by_debt_type[ft_str] = _uuid_mod.uuid4()

        # ── Pass 2: create CapitalModule rows with fully-resolved exit_terms
        # and derived active_phase_end.
        for plan in _module_plan:
            ft_str      = plan["ft_str"]
            rate        = plan["rate"]
            loan_type   = plan["loan_type"]
            amort_years = plan["amort_years"]
            active_from = plan["active_from"]
            vehicle_raw = plan["vehicle_raw"]
            pos         = plan["pos"]
            cm_id       = _uuid_by_debt_type[ft_str]

            if loan_type == "interest_reserve":
                carry: dict = {"carry_type": "interest_reserve", "io_rate_pct": rate}
            elif loan_type == "capitalized_interest":
                carry = {"carry_type": "capitalized_interest", "io_rate_pct": rate}
            elif loan_type == "io_only":
                carry = {"carry_type": "io_only", "io_rate_pct": rate}
            elif loan_type == "pi":
                carry = {"carry_type": "pi", "amort_term_years": amort_years, "io_rate_pct": rate}
            else:  # io_then_pi
                carry = {
                    "phases": [
                        {"name": "construction", "carry_type": "interest_reserve", "io_rate_pct": rate},
                        {"name": "operation", "carry_type": "pi", "amort_term_years": amort_years, "io_rate_pct": rate},
                    ]
                }

            # Resolve vehicle to the persisted form:
            #   "maturity" / "sale" → literal
            #   <picked debt-type>   → retirer module's UUID
            if vehicle_raw in {"maturity", "sale"}:
                vehicle_value = vehicle_raw
                derived_end = "exit" if vehicle_raw == "sale" else "exit"  # maturity = perpetuity, through exit
                exit_trigger = "end of hold period" if vehicle_raw == "maturity" else "Sale"
            elif vehicle_raw in _uuid_by_debt_type:
                retirer_uuid = _uuid_by_debt_type[vehicle_raw]
                vehicle_value = str(retirer_uuid)
                # Derived end = retirer's active_from (handoff point)
                retirer_plan = next(p for p in _module_plan if p["ft_str"] == vehicle_raw)
                derived_end = retirer_plan["active_from"]
                exit_trigger = _LABEL.get(vehicle_raw, vehicle_raw.replace("_", " "))
            else:
                # Shouldn't happen after validation, but stay defensive.
                vehicle_value = "maturity"
                derived_end = "exit"
                exit_trigger = "end of hold period"

            exit_terms_dict: dict = {
                "exit_type": "full_payoff",
                "trigger":   exit_trigger,
                "vehicle":   vehicle_value,
            }

            _cm_label_for_cc = f"{_LABEL.get(ft_str, ft_str)} (auto)"
            _source_dict: dict = {"auto_size": True, "interest_rate_pct": rate}
            if ltv_pct is not None:
                _source_dict["ltv_pct"] = ltv_pct
            # Perm-debt requires hold_term_years (validator-enforced) and
            # optionally dscr_min. Read from wizard staging (debt_terms[ft]),
            # default hold_term_years to amort_years if user didn't pick one.
            if ft_str == "permanent_debt":
                _terms_for_pd = dt.get(ft_str, {}) if isinstance(dt, dict) else {}
                _hold_raw = _terms_for_pd.get("hold_term_years") if isinstance(_terms_for_pd, dict) else None
                _source_dict["hold_term_years"] = (
                    int(_hold_raw) if _hold_raw else amort_years
                )
                _dscr_raw = _terms_for_pd.get("dscr_min") if isinstance(_terms_for_pd, dict) else None
                if _dscr_raw is not None:
                    try:
                        _source_dict["dscr_min"] = float(_dscr_raw)
                    except (TypeError, ValueError):
                        pass
            _cm_vid_raw = dt.get(ft_str, {}).get("vehicle_id") if isinstance(dt, dict) else None
            _cm_vid = UUID(_cm_vid_raw) if _cm_vid_raw else None

            # If a Source Vehicle was picked for this debt type, inherit
            # rate/term/sizing/carry/exit from the vehicle's JSONB presets.
            # Vehicle wins on overlap; wizard form values fill in gaps.
            _cm_vehicle_type = "debt"
            if _cm_vid is not None:
                from app.models.source_vehicle import SourceVehicle as _SVDebt
                _sv_pick = (await session.execute(
                    select(_SVDebt).where(_SVDebt.id == _cm_vid)
                )).scalar_one_or_none()
                if _sv_pick is not None:
                    _cm_label_for_cc = f"{_sv_pick.label} (auto)"
                    _cm_vehicle_type = _sv_pick.vehicle_type or "debt"
                    _sv_source = dict(_sv_pick.source_config or {})
                    _sv_source.setdefault("auto_size", True)
                    for _k, _v in _source_dict.items():
                        if _k not in _sv_source:
                            _sv_source[_k] = _v
                    _source_dict = _sv_source
                    if _sv_pick.carry_config:
                        carry = dict(_sv_pick.carry_config)
                    if _sv_pick.exit_config:
                        exit_terms_dict = dict(_sv_pick.exit_config)
                    if _sv_pick.active_phase_start:
                        active_from = _sv_pick.active_phase_start
                    if _sv_pick.active_phase_end:
                        derived_end = _sv_pick.active_phase_end

            session.add(CapitalModule(
                id=cm_id,
                scenario_id=model_id,
                label=_cm_label_for_cc,
                vehicle_type=_cm_vehicle_type,
                stack_position=pos,
                source=_source_dict,
                carry=carry,
                exit_terms=exit_terms_dict,
                active_phase_start=active_from,
                active_phase_end=derived_end,
                source_vehicle_id=_cm_vid,
            ))
            _cc_preload_modules.append({
                "loan_subtype": ft_str,
                "label": _cm_label_for_cc,
                "active_phase_start": active_from,
            })

    elif not _sv_module_created:
        # ── Legacy 3-path (backward compat for pre-migration deals) ──────────
        if debt_structure == "construction_to_perm":
            construction_rate = dt.get("construction_rate_pct") or dt.get("perm_rate_pct") or 4.5
            perm_rate = dt.get("perm_rate_pct") or construction_rate
            amort_years = int(dt.get("perm_amort_years") or 30)
            session.add(CapitalModule(
                scenario_id=model_id,
                label="Bond / Construction-to-Perm (auto)",
                vehicle_type="debt",
                stack_position=1,
                source={"auto_size": True, "interest_rate_pct": perm_rate},
                carry={
                    "phases": [
                        {"name": "construction", "carry_type": "io_only", "io_rate_pct": construction_rate},
                        {"name": "operation", "carry_type": "pi", "amort_term_years": amort_years, "io_rate_pct": perm_rate},
                    ]
                },
                exit_terms={"exit_type": "full_payoff", "trigger": "end of hold period"},
                active_phase_start="pre_construction",
                active_phase_end="stabilized",
            ))

        elif debt_structure == "construction_and_perm":
            construction_rate = dt.get("construction_rate_pct") or 6.0
            perm_rate = dt.get("perm_rate_pct") or 5.0
            amort_years = int(dt.get("perm_amort_years") or 30)
            session.add(CapitalModule(
                scenario_id=model_id,
                label="Construction Loan (auto)",
                vehicle_type="debt",
                stack_position=1,
                source={"auto_size": True, "interest_rate_pct": construction_rate},
                carry={"carry_type": "io_only", "io_rate_pct": construction_rate},
                exit_terms={"exit_type": "full_payoff", "trigger": "permanent_financing_close"},
                active_phase_start="pre_construction",
                active_phase_end="lease_up",
            ))
            session.add(CapitalModule(
                scenario_id=model_id,
                label="Permanent Debt (auto)",
                vehicle_type="debt",
                stack_position=2,
                source={"auto_size": True, "interest_rate_pct": perm_rate},
                carry={"carry_type": "pi", "amort_term_years": amort_years, "io_rate_pct": perm_rate},
                exit_terms={"exit_type": "full_payoff", "trigger": "end of hold period"},
                active_phase_start="lease_up",
                active_phase_end="stabilized",
            ))

        else:  # perm_only
            perm_rate = dt.get("perm_rate_pct") or 5.0
            amort_years = int(dt.get("perm_amort_years") or 30)
            session.add(CapitalModule(
                scenario_id=model_id,
                label="Permanent Debt (auto)",
                vehicle_type="debt",
                stack_position=1,
                source={"auto_size": True, "interest_rate_pct": perm_rate},
                carry={"carry_type": "pi", "amort_term_years": amort_years, "io_rate_pct": perm_rate},
                exit_terms={"exit_type": "full_payoff", "trigger": "end of hold period"},
                active_phase_start="acquisition",
                active_phase_end="stabilized",
            ))

    # Sync debt_structure from debt_types for engine backward compat.
    # Phase B will generalise the engine to use debt_types directly; until then
    # the sizing function gates on debt_structure to detect construction+perm bridges.
    if debt_types:
        if "construction_to_perm" in debt_types:
            inputs.debt_structure = "construction_to_perm"
        elif "construction_loan" in debt_types and "permanent_debt" in debt_types:
            inputs.debt_structure = "construction_and_perm"
        elif debt_types == ["permanent_debt"]:
            inputs.debt_structure = "perm_only"
        # Other combinations (pre_development, acquisition, bridge) left as-is until Phase B

    # All projects in the scenario — used below to seed Uses, Reserves,
    # OpEx, and CapitalModuleProject junction rows on every project so
    # multi-project deals don't leave Project 2+ empty after Deal Setup.
    all_scenario_projects = list((await session.execute(
        select(Project).where(Project.scenario_id == model_id).order_by(Project.created_at.asc())
    )).scalars())



    inputs.deal_setup_complete = True
    session.add(inputs)

    # Deal Setup is scenario-level (income mode, debt stack). Propagate
    # the completion flag to every other Project's OperationalInputs so
    # their tabs don't keep gating users back to the wizard. Create rows
    # for projects that lack OperationalInputs (e.g. freshly added
    # Projects 2+ that haven't hit the wizard individually).
    other_projects = list((await session.execute(
        select(Project).where(
            Project.scenario_id == model_id,
            Project.id != default_project.id,
        )
    )).scalars())
    for other_proj in other_projects:
        other_inputs = (await session.execute(
            select(OperationalInputs).where(OperationalInputs.project_id == other_proj.id)
        )).scalar_one_or_none()
        if other_inputs is None:
            other_inputs = OperationalInputs(project_id=other_proj.id)
            session.add(other_inputs)
        other_inputs.deal_setup_complete = True
        # Propagate scenario-level debt config so the engine's closing-cost
        # auto-sizing runs for every project. Without these, the per-project
        # compute skips the CC write-back block (it checks debt_types_list)
        # and leaves Appraisal / Origination / Legal / Title at $0.
        other_inputs.debt_types = inputs.debt_types
        other_inputs.debt_structure = inputs.debt_structure
        other_inputs.debt_milestone_config = inputs.debt_milestone_config
        # Sizing-policy fields default from the scenario when not yet set.
        # Only propagate when the other project has no explicit value — this
        # preserves per-project overrides (e.g. gap_fill on an arbitrage
        # deal when the rest of the pool uses dual_constraint).
        if other_inputs.debt_sizing_mode is None:
            other_inputs.debt_sizing_mode = inputs.debt_sizing_mode
        if other_inputs.construction_floor_pct is None:
            other_inputs.construction_floor_pct = inputs.construction_floor_pct
        if other_inputs.operation_reserve_months is None:
            other_inputs.operation_reserve_months = inputs.operation_reserve_months

    # Create $0 Operating Reserve placeholder in Uses for every project
    # (populated at compute time). Multi-project deals each need their own.
    for _proj in all_scenario_projects:
        _existing_reserve = (await session.execute(
            select(UseLine).where(
                UseLine.project_id == _proj.id,
                UseLine.label == "Operating Reserve",
            )
        )).scalar_one_or_none()
        if _existing_reserve is None:
            session.add(UseLine(
                project_id=_proj.id,
                label="Operating Reserve",
                phase="operation",
                amount=Decimal("0"),
                timing_type="first_day",
                cost_category="soft",
                dev_fee_basis_bucket="operating_reserve",
                notes="Sized at compute time: max(OpEx, Debt Service) × reserve months",
            ))

    # Attach every newly-created CapitalModule to the DEFAULT project only.
    # Other projects start without coverage on these auto modules; when the
    # user runs Add Project (drawer), the share-or-clone checkboxes decide
    # whether each Source is shared (junction extended) or cloned (new module
    # owned solely by the new project). Default is per-project, not shared.
    #
    # Explicit flush before the SELECT — autoflush has historically dropped
    # the just-added rows in this handler (likely an interaction with the
    # earlier cascade-delete batch in this same transaction). Without the
    # flush, the SELECT comes back empty and no junctions get attached, so
    # subsequent computes return empty module lists for default_project and
    # the deal silently has no debt coverage.
    await session.flush()
    _auto_modules = list((await session.execute(
        select(CapitalModule).where(
            CapitalModule.scenario_id == model_id,
            CapitalModule.label.like("%(auto)%"),
        )
    )).scalars())
    for _mod in _auto_modules:
        _existing_j = (await session.execute(
            select(CapitalModuleProject).where(
                CapitalModuleProject.capital_module_id == _mod.id,
                CapitalModuleProject.project_id == default_project.id,
            )
        )).scalar_one_or_none()
        if _existing_j is None:
            session.add(CapitalModuleProject(
                capital_module_id=_mod.id,
                project_id=default_project.id,
                amount=Decimal(str((_mod.source or {}).get("amount") or 0)),
                active_from=_mod.active_phase_start,
                active_to=_mod.active_phase_end,
                auto_size=bool((_mod.source or {}).get("auto_size")),
            ))
        # Restore prior shared-with-other-projects junctions for this funder
        # type so wizard re-runs preserve coverage added via Add Project.
        _mod_vt = str(getattr(_mod, "vehicle_type", "") or "").replace("VehicleType.", "")
        for _pid in _prior_auto_shares.get(_mod_vt, set()):
            session.add(CapitalModuleProject(
                capital_module_id=_mod.id,
                project_id=_pid,
                amount=Decimal("0"),
                active_from=_mod.active_phase_start,
                active_to=_mod.active_phase_end,
                auto_size=bool((_mod.source or {}).get("auto_size")),
            ))

    # ── Pre-load $0 closing cost Use line stubs for Phase B modules ──────────

    # ── UnitMix: seed from opportunity if none exist ─────────────────────────
    # unit_mix is JSONB on Project; shape: [{label, unit_count, beds, baths, sqft, rent_monthly, notes}]
    existing_unit_mix: list = default_project.unit_mix or []

    # Physical attributes from the linked opportunity
    _opp_for_units: Opportunity | None = None
    if default_project.opportunity_id:
        _opp_for_units = await session.get(Opportunity, default_project.opportunity_id)

    building_unit_count: int = int(inputs.unit_count_new or 0)
    if _opp_for_units and _opp_for_units.units and not building_unit_count:
        building_unit_count = int(_opp_for_units.units)

    if not existing_unit_mix and building_unit_count:
        # Keep OperationalInputs in sync
        if not inputs.unit_count_new:
            inputs.unit_count_new = building_unit_count
            session.add(inputs)
        default_project.unit_mix = [{
            "label": "All Units",
            "unit_count": building_unit_count,
            "notes": "Seeded from opportunity — break into unit types as needed",
        }]
        session.add(default_project)
        existing_unit_mix = default_project.unit_mix

    # ── Market recommendation: KNN query for revenue/expense prefill ────────
    from app.engines.market import SubjectProperty, get_market_recommendation

    _market_rec = None
    _market_occupancy = Decimal("95")
    if _opp_for_units:
        _subj_units = building_unit_count or int(_opp_for_units.units or 0)
        _subj_year = _opp_for_units.year_built
        _subj_sqft = float(_opp_for_units.gba_sqft) if _opp_for_units.gba_sqft else None
        _subj_sqft_per_unit = _subj_sqft / _subj_units if _subj_sqft and _subj_units > 0 else None
        _subj_juris = _opp_for_units.jurisdiction or _opp_for_units.city
        _exclude_listing_id = str(_opp_for_units.id)
        if _subj_units > 0 and _subj_year:
            try:
                _market_rec = await get_market_recommendation(
                    session,
                    SubjectProperty(
                        units=_subj_units,
                        year_built=_subj_year,
                        sqft_per_unit=_subj_sqft_per_unit,
                        jurisdiction=_subj_juris,
                    ),
                    exclude_listing_id=_exclude_listing_id,
                )
                if _market_rec and not _market_rec.low_confidence:
                    if _market_rec.occupancy_pct is not None:
                        _market_occupancy = Decimal(str(round(_market_rec.occupancy_pct * 100, 1)))
            except Exception:
                pass  # market recommendation failed; fall back to defaults

    # If NOI mode and no NOI prefilled from listing, use market recommendation.
    # Mark as auto-seeded so the builder can show a confirm-or-override banner
    # — a silent KNN-based number shouldn't be accepted as the user's input.
    if model.income_mode == "noi" and inputs.noi_stabilized_input is None and _market_rec and not _market_rec.low_confidence:
        _market_noi = Decimal(str(round(_market_rec.noi_per_unit * building_unit_count, 2)))
        inputs.noi_stabilized_input = _market_noi
        inputs.noi_auto_seeded = True
        session.add(inputs)

    # ── Revenue: seed one IncomeStream per UnitMix row ──────────────────────
    # Skip entirely in NOI mode — Revenue module is not used
    # Only seed if no income streams exist yet
    existing_income = (await session.execute(
        select(IncomeStream).where(IncomeStream.project_id == default_project.id).limit(1)
    )).scalar_one_or_none()

    if existing_income is None and model.income_mode != "noi":
        # Reload unit_mix in case it was just seeded above
        await session.flush()
        await session.refresh(default_project)
        unit_mix_rows: list[dict] = default_project.unit_mix or []

        total_units = sum(int(row.get("unit_count", 0)) for row in unit_mix_rows)
        for row in unit_mix_rows:
            _uc = int(row.get("unit_count", 0))
            _rent = Decimal(str(
                row.get("in_place_rent_per_unit") or row.get("market_rent_per_unit")
                or row.get("rent_monthly") or 0
            ))
            session.add(IncomeStream(
                project_id=default_project.id,
                stream_type=IncomeStreamType.residential_rent,
                label=row.get("label", "Unit Mix"),
                unit_count=_uc,
                amount_per_unit_monthly=_rent,
                stabilized_occupancy_pct=_market_occupancy,
                escalation_rate_pct_annual=Decimal("3"),
                active_in_phases=["lease_up", "stabilized"],
            ))

        if total_units > 0:
            session.add(IncomeStream(
                project_id=default_project.id,
                stream_type=IncomeStreamType.deposit_forfeit,
                label="Turnover on Deposit",
                unit_count=total_units,
                amount_per_unit_monthly=Decimal("0"),
                stabilized_occupancy_pct=Decimal("100"),
                escalation_rate_pct_annual=Decimal("3"),
                active_in_phases=["stabilized"],
                notes="$/unit/mo to configure — typically 4.5% annual turnover × avg rent × recovery rate / 12",
            ))

    # ── OpEx: seed canonical standard lines for every project ───────────────
    # Skip individual labels that already exist (idempotent re-run).
    # Seeded in all income modes — user may switch from NOI to revenue/opex.
    # (label, per_type, scale_with_lease_up, lease_up_floor_pct, active_phases)
    _OPEX_SEEDS = [
        ("Real Estate Taxes",          "flat", False, None, ["lease_up", "stabilized"]),
        ("Insurance",                  "flat", False, None, ["lease_up", "stabilized"]),
        ("Property Management",        "flat", True,  None, ["lease_up", "stabilized"]),
        ("Utilities — Water/Sewer",    "flat", True,  None, ["lease_up", "stabilized"]),
        ("Utilities — Electric",       "flat", True,  None, ["lease_up", "stabilized"]),
        ("Utilities — Gas",            "flat", True,  None, ["lease_up", "stabilized"]),
        ("Utilities — Trash",          "flat", True,  None, ["lease_up", "stabilized"]),
        ("Repairs & Maintenance",      "flat", True,  None, ["stabilized"]),
        ("Marketing & Leasing",        "flat", True,  None, ["lease_up", "stabilized"]),
        ("Administrative",             "flat", False, None, ["lease_up", "stabilized"]),
        ("Payroll",                    "flat", False, None, ["lease_up", "stabilized"]),
        ("Landscaping & Snow Removal", "flat", False, None, ["lease_up", "stabilized"]),
        ("Pest Control",               "flat", False, None, ["lease_up", "stabilized"]),
        ("Cleaning & Janitorial",      "flat", False, None, ["lease_up", "stabilized"]),
        ("Security",                   "flat", False, None, ["lease_up", "stabilized"]),
        ("Resident Services",          "flat", True,  None, ["stabilized"]),
        ("Jurisdiction Fees",          "flat", False, None, ["lease_up", "stabilized"]),
        ("Legal",                      "flat", False, None, ["lease_up", "stabilized"]),
        ("Bank/Software Fees",         "flat", False, None, ["lease_up", "stabilized"]),
        ("Unit Turnover",              "flat", False, None, ["stabilized"]),
    ]

    for _opex_proj in all_scenario_projects:
        _existing_opex_labels = set((await session.execute(
            select(OperatingExpenseLine.label).where(
                OperatingExpenseLine.project_id == _opex_proj.id
            )
        )).scalars())
        for label, per_type, scale, floor_pct, phases in _OPEX_SEEDS:
            if label in _existing_opex_labels:
                continue
            session.add(OperatingExpenseLine(
                project_id=_opex_proj.id,
                label=label,
                annual_amount=Decimal("0"),
                per_type=per_type,
                scale_with_lease_up=scale,
                lease_up_floor_pct=Decimal(str(floor_pct)) if floor_pct is not None else None,
                escalation_rate_pct_annual=Decimal("3"),
                active_in_phases=phases,
            ))

    # Save Deal Health thresholds from wizard step 7 form.
    _ht: dict[str, float] = {}
    for _key, _default in (
        ("ht_occ_green", None), ("ht_oer_green", None),
        ("ht_dscr_green", None), ("ht_margin_green", None),
    ):
        _raw = form.get(_key)
        if _raw is not None:
            try:
                _ht[_key.removeprefix("ht_")] = float(_raw)
            except (ValueError, TypeError):
                pass
    if _ht:
        model.health_thresholds = {**(model.health_thresholds or {}), **_ht}

    # Resolve CapitalModule.active_from_milestone_id / active_to_milestone_id
    # FKs from the active_phase_start / active_phase_end strings. Milestones
    # are seeded earlier in this handler (per project), so the FK lookup is
    # safe here. Engine prefers FK over string when both exist, so future
    # milestone renames / date drags carry through to debt activation timing
    # without touching the legacy string field.
    from app.services.capital_module_milestones import (
        sync_milestone_fks_for_scenario,
    )
    await sync_milestone_fks_for_scenario(session, model_id)

    await session.commit()

    # Redirect to builder — NOI mode lands on the NOI module first, else
    # Property (the natural starting point for filling in unit mix /
    # building data before moving on to S&U).
    # Preserve the active Project from HX-Current-URL so multi-project deals
    # don't snap the user back to Project 1 after finishing Deal Setup.
    _first_module = "noi" if model.income_mode == "noi" else "property"
    _active_proj_q = ""
    _hx_url = request.headers.get("HX-Current-URL", "")
    if _hx_url:
        from urllib.parse import urlparse, parse_qs
        _qs = parse_qs(urlparse(_hx_url).query)
        _p = _qs.get("project", [""])[0]
        if _p:
            _active_proj_q = f"&project={_p}"
    from starlette.responses import Response as StarletteResponse
    response = StarletteResponse(status_code=204)
    response.headers["HX-Redirect"] = f"/models/{model_id}/builder?module={_first_module}{_active_proj_q}"
    return response


