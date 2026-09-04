"""Deal, operational inputs, income streams, use lines, expense lines, and cashflow endpoints."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUserId, DBSession
from app.engines.cashflow import compute_cash_flows
from app.schemas.gap_adjustment import SliderRequest, SliderResponse
from app.schemas.gap_adjustment_names import (
    NOI_ADJUSTMENT_LABEL,
    OPEX_ADJUSTMENT_LABEL,
    PURCHASE_PRICE_ADJUSTMENT_LABEL,
    REVENUE_ADJUSTMENT_LABEL,
    is_reserved_label as _is_reserved_label,
)
from app.engines.waterfall import compute_waterfall
from app.exporters import (
    DealImportResult,
    DealImportValidationResult,
    export_deal_model_json,
    import_deal_model_json,
    validate_deal_import_payload,
)
from app.exporters.investor_export import export_investor_workbook, make_investor_filename
from app.models.cashflow import CashFlow, CashFlowLineItem, OperationalOutputs
from app.models.deal import Deal, IncomeStream, OperatingExpenseLine, OperationalInputs, Scenario, UseLine, resolve_opex_annual_amount
from app.models.manifest import WorkflowRunManifest
from app.models.project import Opportunity, Project
from app.observability import (
    build_observability_payload,
    begin_observation,
    elapsed_ms,
    log_observation,
    utc_now,
)
from app.schemas.deal import (
    CashFlowRead,
    ScenarioBase as ScenarioBase,
    ScenarioRead as ScenarioRead,
    IncomeStreamBase,
    IncomeStreamRead,
    IncomeStreamUpdate,
    OperatingExpenseLineBase,
    OperatingExpenseLineRead,
    OperatingExpenseLineUpdate,
    OperationalInputsBase,
    OperationalInputsRead,
    OperationalOutputsRead,
    USE_LINE_ENGINE_OWNED_FIELDS,
    UseLineCreate,
    UseLineRead,
    UseLineUpdate,
    WorkflowRunManifestRead,
)

router = APIRouter(tags=["models"])
logger = logging.getLogger(__name__)


class DealModelCreateRequest(ScenarioBase):
    created_by_user_id: UUID | None = None


class OperationalInputsUpsertRequest(OperationalInputsBase):
    pass


class IncomeStreamCreateRequest(IncomeStreamBase):
    pass


class IncomeStreamUpdateRequest(IncomeStreamUpdate):
    pass


class OperatingExpenseLineCreateRequest(OperatingExpenseLineBase):
    pass


class OperatingExpenseLineUpdateRequest(OperatingExpenseLineUpdate):
    pass


class UseLineCreateRequest(UseLineCreate):
    pass


class UseLineUpdateRequest(UseLineUpdate):
    pass


async def _get_deal_or_404(session: DBSession, model_id: UUID) -> Scenario:
    model = await session.get(Scenario, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return model


# Transitional helper: each Scenario has exactly one default Project (seeded by migration 0010).
# Once the UI supports multi-project scenarios, callers will pass project_id explicitly.
async def _get_default_project_for_deal(session: DBSession, deal_id: UUID) -> Project:
    result = await session.execute(
        select(Project).where(Project.scenario_id == deal_id).order_by(Project.created_at.asc()).limit(1)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="No project found for this deal")
    return project


# Backward-compat alias used by other parts of the code
_get_deal_model_or_404 = _get_deal_or_404


async def _get_income_stream_or_404(
    session: DBSession,
    model_id: UUID,
    stream_id: UUID,
) -> IncomeStream:
    await _get_deal_or_404(session, model_id)
    stream = await session.get(IncomeStream, stream_id)
    project = await _get_default_project_for_deal(session, model_id)
    if stream is None or stream.project_id != project.id:
        raise HTTPException(status_code=404, detail="Income stream not found")
    return stream


async def _get_expense_line_or_404(
    session: DBSession,
    model_id: UUID,
    expense_line_id: UUID,
) -> OperatingExpenseLine:
    await _get_deal_or_404(session, model_id)
    expense_line = await session.get(OperatingExpenseLine, expense_line_id)
    project = await _get_default_project_for_deal(session, model_id)
    if expense_line is None or expense_line.project_id != project.id:
        raise HTTPException(status_code=404, detail="Expense line not found")
    return expense_line


async def _get_use_line_or_404(
    session: DBSession,
    model_id: UUID,
    use_line_id: UUID,
) -> UseLine:
    await _get_deal_or_404(session, model_id)
    use_line = await session.get(UseLine, use_line_id)
    if use_line is None:
        raise HTTPException(status_code=404, detail="Use line not found")
    from app.models.project import Project as _ULProject
    _ul_proj = await session.get(_ULProject, use_line.project_id)
    if _ul_proj is None or _ul_proj.scenario_id != model_id:
        raise HTTPException(status_code=404, detail="Use line not found")
    return use_line


# ---------------------------------------------------------------------------
# Opportunities (was "Projects") — collection of Deals
# ---------------------------------------------------------------------------

@router.get("/opportunities/{opportunity_id}/models", response_model=list[ScenarioRead])
async def list_opportunity_models(opportunity_id: UUID, session: DBSession) -> list[Scenario]:
    opp = await session.get(Opportunity, opportunity_id)
    if opp is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    # Scenarios link to Opportunity via Project.  Get all scenarios that have a project
    # referencing this opportunity.
    result = await session.execute(
        select(Scenario)
        .join(Project, Project.scenario_id == Scenario.id)
        .where(Project.opportunity_id == opportunity_id)
        .order_by(Scenario.created_at.desc())
    )
    return list(result.scalars().unique())


@router.post(
    "/opportunities/{opportunity_id}/models",
    response_model=ScenarioRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_opportunity_model(
    opportunity_id: UUID,
    payload: DealModelCreateRequest,
    session: DBSession,
) -> Scenario:
    opp = await session.get(Opportunity, opportunity_id)
    if opp is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    # Create a Deal to hold this Scenario if one doesn't exist
    deal = Deal(
        org_id=opp.org_id,
        created_by_user_id=payload.created_by_user_id,
        name=opp.name,
    )
    session.add(deal)
    await session.flush()

    scenario = Scenario(deal_id=deal.id, **payload.model_dump())
    session.add(scenario)
    await session.flush()
    # Create the default Project for this Scenario. (Project carries no
    # deal-type column — the type lives on Scenario.project_type. Passing
    # deal_type here raised TypeError and 500'd this route; caught by the
    # Slice 5 MCP-shaped flow test.)
    project = Project(
        scenario_id=scenario.id,
        opportunity_id=opportunity_id,
        name="Default Project",
    )
    session.add(project)
    await session.flush()
    # Seed org-default document tasks onto the new project (no-op if none).
    from app.services.document_task_seeding import seed_default_tasks
    await seed_default_tasks(session, opp.org_id, project.id)
    await session.refresh(scenario)
    return scenario


# Legacy route — kept for backward compat (UI still uses /projects/{id}/models)
@router.get("/projects/{project_id}/models", response_model=list[ScenarioRead])
async def list_project_models(project_id: UUID, session: DBSession) -> list[Scenario]:
    """Backward-compat: project_id here is an Opportunity ID."""
    return await list_opportunity_models(opportunity_id=project_id, session=session)


@router.post(
    "/projects/{project_id}/models",
    response_model=ScenarioRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_model(
    project_id: UUID,
    payload: DealModelCreateRequest,
    session: DBSession,
) -> Scenario:
    """Backward-compat: project_id here is an Opportunity ID."""
    return await create_opportunity_model(
        opportunity_id=project_id, payload=payload, session=session
    )


class DealModelPatchRequest(ScenarioBase):
    name: str | None = None


@router.patch("/models/{model_id}", response_model=ScenarioRead)
async def patch_deal_model(
    model_id: UUID,
    payload: DealModelPatchRequest,
    session: DBSession,
) -> Scenario:
    model = await _get_deal_or_404(session, model_id)
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(model, k, v)
    await session.flush()
    await session.refresh(model)
    return model


# ---------------------------------------------------------------------------
# Project-opportunity mapping (used by E2E seed helpers)
# ---------------------------------------------------------------------------

@router.get("/models/{model_id}/project-opportunities")
async def list_model_project_opportunities(model_id: UUID, session: DBSession) -> list[dict]:
    """Return [{project_id, opportunity_id}] for all dev projects in this model."""
    await _get_deal_or_404(session, model_id)
    rows = (await session.execute(
        select(Project.id, Project.opportunity_id)
        .where(Project.scenario_id == model_id)
        .order_by(Project.created_at.asc())
    )).all()
    return [{"project_id": str(r[0]), "opportunity_id": str(r[1]) if r[1] else None} for r in rows]


# ---------------------------------------------------------------------------
# Operational inputs (Project-level)
# ---------------------------------------------------------------------------

@router.get("/models/{model_id}/inputs", response_model=OperationalInputsRead | None)
async def get_operational_inputs(model_id: UUID, session: DBSession) -> OperationalInputs | None:
    await _get_deal_or_404(session, model_id)
    project = await _get_default_project_for_deal(session, model_id)
    result = await session.execute(
        select(OperationalInputs).where(OperationalInputs.project_id == project.id)
    )
    return result.scalar_one_or_none()


@router.put("/models/{model_id}/inputs", response_model=OperationalInputsRead)
async def upsert_operational_inputs(
    model_id: UUID,
    payload: OperationalInputsUpsertRequest,
    session: DBSession,
) -> OperationalInputs:
    await _get_deal_or_404(session, model_id)
    project = await _get_default_project_for_deal(session, model_id)
    inputs = (
        await session.execute(
            select(OperationalInputs).where(OperationalInputs.project_id == project.id)
        )
    ).scalar_one_or_none()

    payload_data = payload.model_dump(exclude_unset=True)
    # Engine-owned: noi_auto_seeded is set by the KNN comp auto-seed path and
    # cleared by the NOI form handler. It lives on OperationalInputsBase only
    # for deal-json-v3 round-trip fidelity — never writable via the public API.
    payload_data.pop("noi_auto_seeded", None)
    if inputs is None:
        inputs = OperationalInputs(project_id=project.id, **payload_data)
        session.add(inputs)
    else:
        for field, value in payload_data.items():
            setattr(inputs, field, value)

    await session.flush()
    await session.refresh(inputs)
    return inputs


# ---------------------------------------------------------------------------
# Income streams (Project-level)
# ---------------------------------------------------------------------------

@router.get("/models/{model_id}/income-streams", response_model=list[IncomeStreamRead])
async def list_income_streams(model_id: UUID, session: DBSession) -> list[IncomeStream]:
    await _get_deal_or_404(session, model_id)
    project = await _get_default_project_for_deal(session, model_id)
    result = await session.execute(
        select(IncomeStream)
        .where(IncomeStream.project_id == project.id)
        .order_by(IncomeStream.label.asc())
    )
    return list(result.scalars())


@router.post(
    "/models/{model_id}/income-streams",
    response_model=IncomeStreamRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_income_stream(
    model_id: UUID,
    payload: IncomeStreamCreateRequest,
    session: DBSession,
) -> IncomeStream:
    await _get_deal_or_404(session, model_id)
    project = await _get_default_project_for_deal(session, model_id)
    stream = IncomeStream(project_id=project.id, **payload.model_dump())
    session.add(stream)
    await session.flush()
    await session.refresh(stream)
    return stream


def _assert_not_phantom_row(label: str | None, row_kind: str) -> None:
    """Reject mutations to Gap Adjustment phantom rows via the public API.

    The slider feature owns these rows (identified by reserved label) and
    manages their lifecycle through the dedicated /sliders endpoint. Direct
    edits or deletions through the public CRUD endpoints would break the
    slider's contract that "row exists ↔ slider is non-zero."

    To remove an adjustment, drag the slider back to zero.
    """
    if _is_reserved_label(label):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"{row_kind} {label!r} is a Gap Adjustment phantom row owned "
                "by the slider feature; edit or remove it via the slider, "
                "not the line-item endpoints"
            ),
        )


@router.put("/models/{model_id}/income-streams/{stream_id}", response_model=IncomeStreamRead)
@router.patch("/models/{model_id}/income-streams/{stream_id}", response_model=IncomeStreamRead)
async def update_income_stream(
    model_id: UUID,
    stream_id: UUID,
    payload: IncomeStreamUpdateRequest,
    session: DBSession,
) -> IncomeStream:
    stream = await _get_income_stream_or_404(session, model_id, stream_id)
    _assert_not_phantom_row(stream.label, "IncomeStream")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(stream, field, value)

    await session.flush()
    await session.refresh(stream)
    return stream


@router.delete("/models/{model_id}/income-streams/{stream_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_income_stream(
    model_id: UUID,
    stream_id: UUID,
    session: DBSession,
) -> Response:
    stream = await _get_income_stream_or_404(session, model_id, stream_id)
    _assert_not_phantom_row(stream.label, "IncomeStream")

    line_items = await session.execute(
        select(CashFlowLineItem).where(CashFlowLineItem.income_stream_id == stream_id)
    )
    for line_item in line_items.scalars():
        line_item.income_stream_id = None

    await session.delete(stream)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Expense lines (Project-level)
# ---------------------------------------------------------------------------

@router.get("/models/{model_id}/expense-lines", response_model=list[OperatingExpenseLineRead])
async def list_expense_lines(model_id: UUID, session: DBSession) -> list[OperatingExpenseLine]:
    await _get_deal_or_404(session, model_id)
    project = await _get_default_project_for_deal(session, model_id)
    result = await session.execute(
        select(OperatingExpenseLine)
        .where(OperatingExpenseLine.project_id == project.id)
        .order_by(OperatingExpenseLine.label.asc())
    )
    return list(result.scalars())


@router.post(
    "/models/{model_id}/expense-lines",
    response_model=OperatingExpenseLineRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_expense_line(
    model_id: UUID,
    payload: OperatingExpenseLineCreateRequest,
    session: DBSession,
) -> OperatingExpenseLine:
    await _get_deal_or_404(session, model_id)
    project = await _get_default_project_for_deal(session, model_id)
    data = payload.model_dump()
    if data.get("per_type") is None:
        data["per_type"] = "flat"
    if not data.get("active_in_phases"):
        data["active_in_phases"] = ["lease_up", "stabilized"]
    data["annual_amount"] = resolve_opex_annual_amount(
        project,
        data.get("per_type"),
        data.get("per_value"),
        data.get("annual_amount"),
    )
    expense_line = OperatingExpenseLine(project_id=project.id, **data)
    session.add(expense_line)
    await session.flush()
    await session.refresh(expense_line)
    return expense_line


@router.put("/models/{model_id}/expense-lines/{expense_line_id}", response_model=OperatingExpenseLineRead)
@router.patch("/models/{model_id}/expense-lines/{expense_line_id}", response_model=OperatingExpenseLineRead)
async def update_expense_line(
    model_id: UUID,
    expense_line_id: UUID,
    payload: OperatingExpenseLineUpdateRequest,
    session: DBSession,
) -> OperatingExpenseLine:
    expense_line = await _get_expense_line_or_404(session, model_id, expense_line_id)
    _assert_not_phantom_row(expense_line.label, "OperatingExpenseLine")
    project = await _get_default_project_for_deal(session, model_id)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(expense_line, field, value)

    if expense_line.per_type is None:
        expense_line.per_type = "flat"
    expense_line.annual_amount = resolve_opex_annual_amount(
        project,
        expense_line.per_type,
        expense_line.per_value,
        expense_line.annual_amount,
    )

    await session.flush()
    await session.refresh(expense_line)
    return expense_line


@router.delete(
    "/models/{model_id}/expense-lines/{expense_line_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_expense_line(
    model_id: UUID,
    expense_line_id: UUID,
    session: DBSession,
) -> Response:
    expense_line = await _get_expense_line_or_404(session, model_id, expense_line_id)
    _assert_not_phantom_row(expense_line.label, "OperatingExpenseLine")
    await session.delete(expense_line)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Use lines (Project-level)
# ---------------------------------------------------------------------------

@router.get("/models/{model_id}/use-lines", response_model=list[UseLineRead])
async def list_use_lines(model_id: UUID, session: DBSession) -> list[UseLine]:
    await _get_deal_or_404(session, model_id)
    project = await _get_default_project_for_deal(session, model_id)
    result = await session.execute(
        select(UseLine)
        .where(UseLine.project_id == project.id)
        .order_by(UseLine.phase.asc(), UseLine.label.asc())
    )
    return list(result.scalars())


@router.post(
    "/models/{model_id}/use-lines",
    response_model=UseLineRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_use_line(
    model_id: UUID,
    payload: UseLineCreateRequest,
    session: DBSession,
) -> UseLine:
    await _get_deal_or_404(session, model_id)
    project = await _get_default_project_for_deal(session, model_id)
    # Engine-owned fields (is_auto_*, dev_fee_binding_context) exist on
    # UseLineBase only for round-trip fidelity — strip from the public API.
    use_line = UseLine(
        project_id=project.id,
        **payload.model_dump(exclude=USE_LINE_ENGINE_OWNED_FIELDS),
    )
    session.add(use_line)
    await session.flush()
    await session.refresh(use_line)
    return use_line


@router.put("/models/{model_id}/use-lines/{use_line_id}", response_model=UseLineRead)
@router.patch("/models/{model_id}/use-lines/{use_line_id}", response_model=UseLineRead)
async def update_use_line(
    model_id: UUID,
    use_line_id: UUID,
    payload: UseLineUpdateRequest,
    session: DBSession,
) -> UseLine:
    use_line = await _get_use_line_or_404(session, model_id, use_line_id)
    _assert_not_phantom_row(use_line.label, "UseLine")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(use_line, field, value)
    await session.flush()
    await session.refresh(use_line)
    return use_line


@router.delete("/models/{model_id}/use-lines/{use_line_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_use_line(
    model_id: UUID,
    use_line_id: UUID,
    session: DBSession,
) -> Response:
    use_line = await _get_use_line_or_404(session, model_id, use_line_id)
    _assert_not_phantom_row(use_line.label, "UseLine")
    if use_line.is_auto_dev_fee:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The auto Developer Fee Use Line cannot be deleted. Set its % to 0 to disable.",
        )
    await session.delete(use_line)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Outputs + compute
# ---------------------------------------------------------------------------

@router.get("/models/{model_id}/outputs", response_model=OperationalOutputsRead | None)
async def get_operational_outputs(
    model_id: UUID,
    session: DBSession,
) -> OperationalOutputs | None:
    await _get_deal_or_404(session, model_id)
    # Scenario may now carry N operational_outputs rows (one per project)
    # after migration 0051. Return the default (oldest) project's row so
    # legacy single-row callers see the expected shape.
    result = await session.execute(
        select(OperationalOutputs)
        .join(Project, Project.id == OperationalOutputs.project_id)
        .where(OperationalOutputs.scenario_id == model_id)
        .order_by(Project.created_at.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


@router.post("/models/{model_id}/compute")
async def compute_model_cashflows(model_id: UUID, request: Request, session: DBSession) -> Any:
    await _get_deal_or_404(session, model_id)

    # Auto-create OperationalInputs if missing (pre-existing deals may not have one)
    default_project = (await session.execute(
        select(Project).where(Project.scenario_id == model_id).order_by(Project.created_at.asc()).limit(1)
    )).scalar_one_or_none()
    if default_project:
        existing_inputs = (await session.execute(
            select(OperationalInputs).where(OperationalInputs.project_id == default_project.id)
        )).scalar_one_or_none()
        if existing_inputs is None:
            session.add(OperationalInputs(project_id=default_project.id))
            await session.flush()

    trace_id, started_at, started_at_monotonic = begin_observation(
        getattr(request.state, "trace_id", None)
    )
    user_id = getattr(request.state, "user_id", None)
    log_observation(
        logger,
        "underwriting_compute_started",
        trace_id=trace_id,
        run_type="cashflow",
        deal_model_id=model_id,
        user_id=user_id,
    )
    # Auto-size draw sources before cashflow: writes CapitalModule.source["amount"]
    # so the cashflow + waterfall engines see correct committed amounts. Also
    # capture the returned schedule's monthly_cash_flows; they feed the Day 0
    # → Stabilization Start bank-account proof. We re-run inside the
    # iteration loop too so the proof sees the latest reserve sizing.
    from app.api.routers.ui_model_outputs import _run_draw_schedule  # lazy to avoid circular import
    try:
        _initial_schedule = await _run_draw_schedule(session, model_id, writeback=True)
    except Exception:
        _initial_schedule = None  # Don't block compute if draw schedule can't run

    # ── Fix-point iteration for sizing convergence ──────────────────────────
    # When debt_sizing_mode is 'dscr_capped' or 'dual_constraint', the first
    # sizing pass uses an estimated stabilized NOI. The final computed NOI may
    # differ slightly (escalation carry-in, capex reserve, lease-up scaling),
    # causing the displayed DSCR to drift above the minimum by 0.01–0.05×.
    # Each subsequent call to compute_cash_flows reads the previous
    # OperationalOutputs.noi_stabilized and uses it for sizing — so simply
    # re-running the compute converges DSCR to the exact minimum.
    #
    # We cap at 5 iterations to prevent infinite loops if any math goes
    # unstable. Practically, convergence happens in 2 passes for any
    # well-formed deal.
    MAX_ITERATIONS = 5
    DSCR_CONVERGENCE_TOLERANCE = Decimal("0.005")  # 0.005× = half a basis point
    _sizing_mode = (
        (existing_inputs.debt_sizing_mode if existing_inputs else None)
        if default_project else None
    )
    _iterative_modes = {"dscr_capped", "dual_constraint"}
    _should_iterate = _sizing_mode in _iterative_modes

    # Idempotency: zero any Cash Flow Support Reserve persisted by a prior
    # compute so this run converges to a fresh fixed point. Without this the
    # auto-grown reserve stacks across clicks and, for capitalized-interest
    # deals, diverges (runaway bond → numeric overflow → 500). The engine
    # re-grows it from zero each compute via its needs_recompute loop below.
    try:
        await session.execute(
            update(UseLine)
            .where(UseLine.label == "Cash Flow Support Reserve")
            .where(
                UseLine.project_id.in_(
                    select(Project.id).where(Project.scenario_id == model_id)
                )
            )
            .values(amount=Decimal("0"))
        )
        await session.flush()
    except Exception:
        pass  # never block compute on a reserve reset

    result: dict[str, Any] | None = None
    waterfall_result: dict[str, Any] | None = None
    prev_dscr: Decimal | None = None
    prev_dev_fee_paydown_total: Decimal | None = None
    _prev_shortfall: Decimal | None = None
    iterations_used = 0
    _schedule = _initial_schedule
    try:
        for _iter in range(MAX_ITERATIONS):
            # Re-run draw schedule each iteration: reserves (Cash Flow
            # Support, OR) can shift between passes, so the construction
            # window must use the freshest sizing.
            if _iter > 0:
                try:
                    _schedule = await _run_draw_schedule(
                        session, model_id, writeback=True
                    )
                except Exception:
                    _schedule = None
            _construction_monthly = (
                list(getattr(_schedule, "monthly_cash_flows", []) or [])
                if _schedule is not None
                else None
            )
            result = await compute_cash_flows(
                deal_model_id=model_id,
                session=session,
                construction_monthly=_construction_monthly,
            )
            iterations_used = _iter + 1
            # Bank-account reserve convergence: when the engine has just
            # created / updated / removed an auto-managed Cash Flow Support
            # Reserve, the new reserve has not yet been folded into reserve
            # sizing — re-run so Sources = Uses on the next pass. This
            # supersedes the DSCR convergence break for the iteration that
            # triggered the reserve change.
            _needs_recompute = (
                isinstance(result, dict) and result.get("needs_recompute") is True
            )

            # Waterfall must run inside the loop so the NEXT iteration's
            # bank-account proof reads this iter's deferred Dev Fee paydown
            # schedule (via OperationalOutputs.dev_fee_balance_series). If
            # the paydown total changes materially, force another pass so
            # the proof reflects the fresh schedule. (Pre-reserves-spec-align,
            # the proof's max_shortfall also sized a Cash Flow Support Reserve
            # UseLine — that helper was removed in Slice 5b; the proof is now
            # validation-only and ODR funds the operating shortfall.)
            try:
                waterfall_result = await compute_waterfall(deal_model_id=model_id, session=session)
            except ValueError:
                waterfall_result = None
            _cur_dev_fee_paydown_total = Decimal("0")
            if isinstance(waterfall_result, dict):
                _raw = waterfall_result.get("deferred_dev_fee_paydown_total")
                if _raw is not None:
                    try:
                        _cur_dev_fee_paydown_total = Decimal(str(_raw))
                    except Exception:
                        _cur_dev_fee_paydown_total = Decimal("0")
            _paydown_changed = (
                prev_dev_fee_paydown_total is not None
                and abs(_cur_dev_fee_paydown_total - prev_dev_fee_paydown_total) > Decimal("1.0")
            )
            prev_dev_fee_paydown_total = _cur_dev_fee_paydown_total
            if _paydown_changed:
                _needs_recompute = True

            # Divergence guard for the Cash Flow Support Reserve loop. A solvable
            # shortfall shrinks each pass as the reserve (and bond) fill it. If it
            # stops shrinking, the deal is structurally insolvent — the bond can't
            # outrun its own debt service — so stop and leave the residual gap as
            # a user-visible signal rather than iterate toward a numeric blow-up.
            _cur_shortfall: Decimal | None = None
            if isinstance(result, dict):
                _bap = result.get("bank_account_proof")
                if isinstance(_bap, dict) and _bap.get("max_shortfall") is not None:
                    try:
                        _cur_shortfall = Decimal(str(_bap["max_shortfall"]))
                    except Exception:
                        _cur_shortfall = None
            _diverging = (
                _prev_shortfall is not None
                and _cur_shortfall is not None
                and _cur_shortfall >= _prev_shortfall
            )
            _prev_shortfall = _cur_shortfall
            if _diverging:
                break

            if _needs_recompute and _iter < MAX_ITERATIONS - 1:
                continue
            if not _should_iterate:
                break
            _cur_dscr = result.get("dscr") if isinstance(result, dict) else None
            if _cur_dscr is None:
                break
            try:
                _cur_dscr_dec = Decimal(str(_cur_dscr))
            except Exception:
                break
            # Converged when the DSCR stabilizes between iterations
            if prev_dscr is not None and abs(_cur_dscr_dec - prev_dscr) < DSCR_CONVERGENCE_TOLERANCE:
                break
            prev_dscr = _cur_dscr_dec
    except (ValueError, KeyError, TypeError, ZeroDivisionError) as exc:
        log_observation(
            logger,
            "underwriting_compute_failed",
            trace_id=trace_id,
            run_type="cashflow",
            deal_model_id=model_id,
            duration_ms=elapsed_ms(started_at_monotonic),
            user_id=user_id,
            error=str(exc),
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Surface the iteration count for observability
    if isinstance(result, dict):
        result["sizing_iterations"] = iterations_used

    # Automatically chain waterfall compute after cashflow so that:
    # - owner distributions flow out of the cash balance each period
    # - project_irr_levered and equity_required are correctly computed
    # - auto-creates equity module + tiers if not yet configured
    # NOTE: waterfall now runs INSIDE the convergence loop above so the
    # bank-account proof can read the latest deferred Dev Fee paydown schedule
    # on the next iteration. `waterfall_result` holds the last-iteration value.

    completed_at = utc_now()
    duration_ms = elapsed_ms(started_at_monotonic)
    response = dict(result)
    if waterfall_result:
        response["waterfall"] = {
            "lp_irr_pct": waterfall_result.get("lp_irr_pct"),
            "gp_irr_pct": waterfall_result.get("gp_irr_pct"),
            "equity_multiple": waterfall_result.get("equity_multiple"),
            "project_irr_levered": waterfall_result.get("project_irr_levered"),
        }
    response["observability"] = build_observability_payload(
        trace_id=trace_id,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=duration_ms,
        run_type="cashflow",
        deal_model_id=str(model_id),
        user_id=user_id,
    )
    log_observation(
        logger,
        "underwriting_compute_completed",
        trace_id=trace_id,
        run_type="cashflow",
        deal_model_id=model_id,
        duration_ms=duration_ms,
        user_id=user_id,
    )

    # ── Snapshot: capture audit record after every successful compute ────────
    try:
        from app.exporters.snapshot import capture_snapshot
        snap = await capture_snapshot(session, model_id, triggered_by="compute")
        response["snapshot_version"] = snap.version
    except Exception:
        logger.warning(
            "snapshot capture failed",
            extra={"deal_model_id": str(model_id), "trace_id": trace_id},
            exc_info=True,
        )  # Never block the compute response on snapshot failure

    # HX-Trigger makes the topbar Calculation Status pill refresh on the
    # client — more reliable than relying on the hx-on::after-request JS
    # handler, which can silently no-op on edge cases.
    import json as _json
    from fastapi.responses import JSONResponse
    return JSONResponse(
        content=_json.loads(_json.dumps(response, default=str)),
        headers={"HX-Trigger": "calcStatusChanged"},
    )


@router.get("/models/{model_id}/cashflow", response_model=list[CashFlowRead])
async def get_model_cashflow(model_id: UUID, session: DBSession) -> list[CashFlow]:
    await _get_deal_or_404(session, model_id)
    result = await session.execute(
        select(CashFlow)
        .where(CashFlow.scenario_id == model_id)
        .order_by(CashFlow.period.asc())
    )
    return list(result.scalars())


@router.get("/models/{model_id}/runs", response_model=list[WorkflowRunManifestRead])
async def list_model_runs(model_id: UUID, session: DBSession) -> list[WorkflowRunManifest]:
    await _get_deal_or_404(session, model_id)
    result = await session.execute(
        select(WorkflowRunManifest)
        .where(WorkflowRunManifest.scenario_id == model_id)
        .order_by(WorkflowRunManifest.created_at.desc())
        .limit(50)
    )
    return list(result.scalars())


@router.post("/models/{model_id}/runs/{run_id}/replay")
async def replay_model_run(model_id: UUID, run_id: str, session: DBSession) -> dict[str, Any]:
    await _get_deal_or_404(session, model_id)
    manifest = (
        await session.execute(
            select(WorkflowRunManifest).where(
                WorkflowRunManifest.scenario_id == model_id,
                WorkflowRunManifest.run_id == run_id,
            )
        )
    ).scalar_one_or_none()
    if manifest is None:
        raise HTTPException(status_code=404, detail="Workflow run not found")

    try:
        if manifest.engine == "cashflow":
            return await compute_cash_flows(deal_model_id=model_id, session=session)
        if manifest.engine == "waterfall":
            return await compute_waterfall(deal_model_id=model_id, session=session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    raise HTTPException(status_code=400, detail=f"Unsupported workflow engine '{manifest.engine}'")


@router.get("/models/{model_id}/export/json")
async def export_model_json(model_id: UUID, session: DBSession) -> dict[str, Any]:
    await _get_deal_or_404(session, model_id)
    return await export_deal_model_json(session=session, model_id=model_id)


@router.post("/models/import/validate", response_model=DealImportValidationResult)
async def validate_model_import(payload: dict[str, Any]) -> DealImportValidationResult:
    return validate_deal_import_payload(payload)


@router.post(
    "/projects/{project_id}/models/import",
    response_model=DealImportResult,
    status_code=status.HTTP_201_CREATED,
)
async def import_project_model(
    project_id: UUID,
    payload: dict[str, Any],
    session: DBSession,
    current_user_id: CurrentUserId,
) -> DealImportResult:
    """Backward-compat: project_id here is an Opportunity ID."""
    opp = await session.get(Opportunity, project_id)
    if opp is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    try:
        return await import_deal_model_json(
            session=session,
            project_id=project_id,
            payload=payload,
            created_by_user_id=current_user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/models/{model_id}/export/xlsx")
async def export_model_xlsx(
    model_id: UUID,
    session: DBSession,
    profile: str = "internal",
) -> Response:
    """Excel export of the model. ``profile`` picks the sheet set:
    internal (default, full underwriting), lp, lender, or proforma —
    unknown values fall back to internal inside the exporter."""
    model = await _get_deal_or_404(session, model_id)
    workbook_bytes = await export_investor_workbook(model_id, session, profile=profile)
    deal = await session.get(Deal, model.deal_id) if model.deal_id else None
    filename = make_investor_filename(model, deal, profile=profile)
    return Response(
        content=workbook_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Gap Adjustment slider endpoint
# ---------------------------------------------------------------------------


async def _upsert_revenue_phantom(
    session: DBSession,
    project_id: UUID,
    monthly_amount: Decimal,
) -> IncomeStream:
    # Race-safe upsert: SELECT-then-INSERT under partial unique index
    # (migration 0094). Two concurrent slider POSTs both miss the SELECT,
    # one INSERT wins, the other catches IntegrityError and falls back to
    # an UPDATE on the row that did win. Last write wins, no duplicates.
    existing = (await session.execute(
        select(IncomeStream).where(
            IncomeStream.project_id == project_id,
            IncomeStream.label == REVENUE_ADJUSTMENT_LABEL,
        )
    )).scalars().first()
    if existing is not None:
        existing.amount_fixed_monthly = monthly_amount
        existing.stabilized_occupancy_pct = Decimal("100")
        return existing
    row = IncomeStream(
        project_id=project_id,
        stream_type="other",
        label=REVENUE_ADJUSTMENT_LABEL,
        amount_fixed_monthly=monthly_amount,
        stabilized_occupancy_pct=Decimal("100"),  # slider value = exact NOI delta
        # Active in operating phases only — adjustment to stabilized NOI.
        active_in_phases=["lease_up", "stabilized", "exit"],
    )
    try:
        async with session.begin_nested():
            session.add(row)
            await session.flush()
        return row
    except IntegrityError:
        existing = (await session.execute(
            select(IncomeStream).where(
                IncomeStream.project_id == project_id,
                IncomeStream.label == REVENUE_ADJUSTMENT_LABEL,
            )
        )).scalars().first()
        if existing is None:
            raise
        existing.amount_fixed_monthly = monthly_amount
        existing.stabilized_occupancy_pct = Decimal("100")
        return existing


async def _upsert_opex_phantom(
    session: DBSession,
    project_id: UUID,
    annual_amount: Decimal,
) -> OperatingExpenseLine:
    existing = (await session.execute(
        select(OperatingExpenseLine).where(
            OperatingExpenseLine.project_id == project_id,
            OperatingExpenseLine.label == OPEX_ADJUSTMENT_LABEL,
        )
    )).scalars().first()
    if existing is not None:
        existing.annual_amount = annual_amount
        return existing
    row = OperatingExpenseLine(
        project_id=project_id,
        label=OPEX_ADJUSTMENT_LABEL,
        annual_amount=annual_amount,
        per_type="flat",
        active_in_phases=["lease_up", "stabilized", "exit"],
    )
    try:
        async with session.begin_nested():
            session.add(row)
            await session.flush()
        return row
    except IntegrityError:
        existing = (await session.execute(
            select(OperatingExpenseLine).where(
                OperatingExpenseLine.project_id == project_id,
                OperatingExpenseLine.label == OPEX_ADJUSTMENT_LABEL,
            )
        )).scalars().first()
        if existing is None:
            raise
        existing.annual_amount = annual_amount
        return existing


async def _upsert_noi_phantom(
    session: DBSession,
    project_id: UUID,
    annual_amount: Decimal,
) -> OperatingExpenseLine:
    """Upsert the NOI gap-adjustment phantom for income_mode='noi' deals.

    Stored as an OperatingExpenseLine with NOI_ADJUSTMENT_LABEL so the cashflow
    engine can pick it up in the NOI path and add it to noi_stabilized_input.
    Positive = assume higher NOI; negative = assume lower NOI.
    """
    existing = (await session.execute(
        select(OperatingExpenseLine).where(
            OperatingExpenseLine.project_id == project_id,
            OperatingExpenseLine.label == NOI_ADJUSTMENT_LABEL,
        )
    )).scalars().first()
    if existing is not None:
        existing.annual_amount = annual_amount
        return existing
    row = OperatingExpenseLine(
        project_id=project_id,
        label=NOI_ADJUSTMENT_LABEL,
        annual_amount=annual_amount,
        per_type="flat",
    )
    try:
        session.add(row)
        await session.flush()
        return row
    except Exception:
        await session.rollback()
        existing = (await session.execute(
            select(OperatingExpenseLine).where(
                OperatingExpenseLine.project_id == project_id,
                OperatingExpenseLine.label == NOI_ADJUSTMENT_LABEL,
            )
        )).scalars().first()
        if existing is None:
            raise
        existing.annual_amount = annual_amount
        return existing


async def _upsert_pp_phantom(
    session: DBSession,
    project_id: UUID,
    amount: Decimal,
) -> UseLine:
    existing = (await session.execute(
        select(UseLine).where(
            UseLine.project_id == project_id,
            UseLine.label == PURCHASE_PRICE_ADJUSTMENT_LABEL,
        )
    )).scalars().first()
    if existing is not None:
        existing.amount = amount
        return existing
    # UseLinePhase enum is imported via app.models.deal but referenced as
    # the string value to match how the existing line items are seeded
    # (see test_engine_snapshots.py). Negative amounts are explicitly
    # supported by the engine — the auto-sizer subtracts them from
    # total_uses in cashflow.py:1603.
    from app.models.deal import UseLinePhase
    row = UseLine(
        project_id=project_id,
        label=PURCHASE_PRICE_ADJUSTMENT_LABEL,
        phase=UseLinePhase.acquisition,
        amount=amount,
        timing_type="first_day",
        dev_fee_basis_bucket="acquisition",
        cost_category="acquisition",
    )
    try:
        async with session.begin_nested():
            session.add(row)
            await session.flush()
        return row
    except IntegrityError:
        existing = (await session.execute(
            select(UseLine).where(
                UseLine.project_id == project_id,
                UseLine.label == PURCHASE_PRICE_ADJUSTMENT_LABEL,
            )
        )).scalars().first()
        if existing is None:
            raise
        existing.amount = amount
        existing.cost_category = "acquisition"
        return existing


def _compute_lock_key(model_id: UUID) -> int:
    """A stable 64-bit lock id for one scenario.

    Postgres advisory locks take a bigint, so the UUID is folded down to its
    first eight bytes. Collisions between two different scenarios would cost
    one of them a short wait and nothing else -- the lock guards a recompute,
    not correctness of the result -- so the cheap derivation is the right one.
    """
    return int.from_bytes(model_id.bytes[:8], "big", signed=True)


@router.post("/models/{model_id}/sliders", response_model=SliderResponse)
async def update_gap_adjustment_sliders(
    model_id: UUID,
    payload: SliderRequest,
    session: DBSession,
) -> SliderResponse:
    """Apply Gap Adjustment slider deltas and recompute.

    Each non-None field upserts the corresponding phantom row to that
    absolute amount. ``None`` leaves the row untouched. ``0`` sets it to
    zero (the row stays in place — drag-to-zero doesn't delete; the user
    keeps the adjustment lineage so they can drag it again later).

    Runs ``compute_cash_flows`` synchronously after upserting and returns
    the post-compute metrics. The UI should debounce slider drag events
    to avoid hammering this endpoint mid-drag.
    """
    # One recompute of a scenario at a time.
    #
    # A fast drag on the slider fires two POSTs, and each gets its own session
    # in production. ``compute_cash_flows`` clears this scenario's cash flows,
    # line items, draw events and outputs and writes them again, so two of them
    # running together are not merely racing on the outputs table's unique
    # constraint -- which is the error that shows -- they are interleaving four
    # delete-then-insert passes over the same rows. Migration 0094 and the
    # IntegrityError fallbacks below fixed exactly this for the three phantom
    # rows and did not reach the compute.
    #
    # Transaction-scoped, so it releases on the commit at the end of this
    # request or on any rollback out of it. The second drag waits a second or
    # two and then recomputes from the first one's result, which is what the
    # user meant by dragging twice.
    #
    # Found 2026-09-04, by the concurrency test in
    # tests/api/test_gap_adjustment_sliders.py the moment it was given a
    # session per request and could collide for the first time.
    await session.execute(select(func.pg_advisory_xact_lock(_compute_lock_key(model_id))))

    scenario = await _get_deal_or_404(session, model_id)
    income_mode = str(getattr(scenario, "income_mode", None) or "revenue_opex")
    # Multi-project: caller supplies project_id (UI passes active project's id).
    # Single-project / unspecified: fall back to the scenario's default (first)
    # project. Validates that the project belongs to this scenario to prevent
    # cross-scenario phantom row leakage.
    if payload.project_id is not None:
        proj = await session.get(Project, payload.project_id)
        if proj is None or proj.scenario_id != model_id:
            raise HTTPException(
                status_code=404,
                detail="Project not found on this scenario",
            )
        project = proj
    else:
        project = await _get_default_project_for_deal(session, model_id)

    if income_mode == "noi":
        # NOI mode: revenue and opex sliders don't apply; use a single NOI delta.
        if payload.noi_delta_annual is not None:
            await _upsert_noi_phantom(session, project.id, payload.noi_delta_annual)
    else:
        # revenue_opex mode: UI sends annual revenue; store as monthly (÷12).
        if payload.revenue_delta_annual is not None:
            await _upsert_revenue_phantom(session, project.id, payload.revenue_delta_annual / Decimal("12"))
        if payload.opex_delta_annual is not None:
            await _upsert_opex_phantom(session, project.id, payload.opex_delta_annual)
    if payload.pp_delta is not None:
        await _upsert_pp_phantom(session, project.id, payload.pp_delta)

    await session.flush()

    # Two-pass compute for DSCR-capped deals: a single pass sizes debt from
    # the previously stored NOI estimate; the second pass re-sizes with the
    # actual computed NOI, converging DSCR to the minimum. Matches the
    # fix-point logic in the /compute endpoint so Reset+Recalc doesn't leave
    # DSCR below the minimum.
    _inputs = (await session.execute(
        select(OperationalInputs).where(OperationalInputs.project_id == project.id)
    )).scalar_one_or_none()
    _sizing_mode = _inputs.debt_sizing_mode if _inputs else None
    _passes = 2 if _sizing_mode in {"dscr_capped", "dual_constraint"} else 1
    for _ in range(_passes):
        await compute_cash_flows(deal_model_id=model_id, session=session)

    await session.commit()

    # Read back the post-compute metrics + the resolved deltas for echo.
    outputs = (await session.execute(
        select(OperationalOutputs).where(
            OperationalOutputs.scenario_id == model_id,
            OperationalOutputs.project_id == project.id,
        )
    )).scalar_one_or_none()

    revenue = (await session.execute(
        select(IncomeStream).where(
            IncomeStream.project_id == project.id,
            IncomeStream.label == REVENUE_ADJUSTMENT_LABEL,
        )
    )).scalars().first()
    opex = (await session.execute(
        select(OperatingExpenseLine).where(
            OperatingExpenseLine.project_id == project.id,
            OperatingExpenseLine.label == OPEX_ADJUSTMENT_LABEL,
        )
    )).scalars().first()
    noi_row = (await session.execute(
        select(OperatingExpenseLine).where(
            OperatingExpenseLine.project_id == project.id,
            OperatingExpenseLine.label == NOI_ADJUSTMENT_LABEL,
        )
    )).scalars().first()
    pp = (await session.execute(
        select(UseLine).where(
            UseLine.project_id == project.id,
            UseLine.label == PURCHASE_PRICE_ADJUSTMENT_LABEL,
        )
    )).scalars().first()

    # Revenue stored monthly → return as annual (×12) to match UI's annual scale.
    rev_monthly = Decimal(str(revenue.amount_fixed_monthly)) if revenue and revenue.amount_fixed_monthly is not None else Decimal("0")
    rev_amt = rev_monthly * Decimal("12")
    opex_amt = Decimal(str(opex.annual_amount)) if opex and opex.annual_amount is not None else Decimal("0")
    noi_amt = Decimal(str(noi_row.annual_amount)) if noi_row and noi_row.annual_amount is not None else Decimal("0")
    pp_amt = Decimal(str(pp.amount)) if pp and pp.amount is not None else Decimal("0")

    return SliderResponse(
        revenue_delta_annual=rev_amt,
        opex_delta_annual=opex_amt,
        noi_delta_annual=noi_amt,
        pp_delta=pp_amt,
        has_any_adjustment=any(v != 0 for v in (rev_amt, opex_amt, noi_amt, pp_amt)),
        dscr=Decimal(str(outputs.dscr)) if outputs and outputs.dscr is not None else None,
        total_project_cost=(
            Decimal(str(outputs.total_project_cost))
            if outputs and outputs.total_project_cost is not None else None
        ),
        equity_required=(
            Decimal(str(outputs.equity_required))
            if outputs and outputs.equity_required is not None else None
        ),
    )
