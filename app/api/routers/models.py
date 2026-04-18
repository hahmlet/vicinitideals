"""Deal, operational inputs, income streams, use lines, expense lines, and cashflow endpoints."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy import select

from app.api.deps import CurrentUserId, DBSession
from app.engines.cashflow import compute_cash_flows
from app.engines.waterfall import compute_waterfall
from app.exporters import (
    DealImportResult,
    DealImportValidationResult,
    export_deal_model_json,
    export_deal_model_workbook,
    import_deal_model_json,
    make_export_filename,
    validate_deal_import_payload,
)
from app.models.cashflow import CashFlow, CashFlowLineItem, OperationalOutputs
from app.models.deal import Deal, IncomeStream, OperatingExpenseLine, OperationalInputs, Scenario, UseLine
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
    ScenarioBase as DealModelBase,
    ScenarioRead as DealModelRead,
    IncomeStreamBase,
    IncomeStreamRead,
    IncomeStreamUpdate,
    OperatingExpenseLineBase,
    OperatingExpenseLineRead,
    OperatingExpenseLineUpdate,
    OperationalInputsBase,
    OperationalInputsRead,
    OperationalOutputsRead,
    UseLineCreate,
    UseLineRead,
    UseLineUpdate,
    WorkflowRunManifestRead,
)

router = APIRouter(tags=["models"])
logger = logging.getLogger(__name__)


class DealModelCreateRequest(DealModelBase):
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
    project = await _get_default_project_for_deal(session, model_id)
    if use_line is None or use_line.project_id != project.id:
        raise HTTPException(status_code=404, detail="Use line not found")
    return use_line


# ---------------------------------------------------------------------------
# Opportunities (was "Projects") — collection of Deals
# ---------------------------------------------------------------------------

@router.get("/opportunities/{opportunity_id}/models", response_model=list[DealModelRead])
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
    response_model=DealModelRead,
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
    # Create the default Project for this Scenario
    project = Project(
        scenario_id=scenario.id,
        opportunity_id=opportunity_id,
        name="Default Project",
        deal_type=scenario.project_type,
    )
    session.add(project)
    await session.flush()
    await session.refresh(scenario)
    return scenario


# Legacy route — kept for backward compat (UI still uses /projects/{id}/models)
@router.get("/projects/{project_id}/models", response_model=list[DealModelRead])
async def list_project_models(project_id: UUID, session: DBSession) -> list[Scenario]:
    """Backward-compat: project_id here is an Opportunity ID."""
    return await list_opportunity_models(opportunity_id=project_id, session=session)


@router.post(
    "/projects/{project_id}/models",
    response_model=DealModelRead,
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


class DealModelPatchRequest(DealModelBase):
    name: str | None = None


@router.patch("/models/{model_id}", response_model=DealModelRead)
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


@router.put("/models/{model_id}/income-streams/{stream_id}", response_model=IncomeStreamRead)
@router.patch("/models/{model_id}/income-streams/{stream_id}", response_model=IncomeStreamRead)
async def update_income_stream(
    model_id: UUID,
    stream_id: UUID,
    payload: IncomeStreamUpdateRequest,
    session: DBSession,
) -> IncomeStream:
    stream = await _get_income_stream_or_404(session, model_id, stream_id)

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
    expense_line = OperatingExpenseLine(project_id=project.id, **payload.model_dump())
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

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(expense_line, field, value)

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
    use_line = UseLine(project_id=project.id, **payload.model_dump())
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
    result = await session.execute(
        select(OperationalOutputs).where(OperationalOutputs.scenario_id == model_id)
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
    # so the cashflow + waterfall engines see correct committed amounts.
    try:
        from app.api.routers.ui import _run_draw_schedule  # lazy to avoid circular import
        await _run_draw_schedule(session, model_id, writeback=True)
    except Exception:
        pass  # Don't block compute if draw schedule can't run (missing milestones etc.)

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

    result: dict[str, Any] | None = None
    prev_dscr: Decimal | None = None
    iterations_used = 0
    try:
        for _iter in range(MAX_ITERATIONS):
            result = await compute_cash_flows(deal_model_id=model_id, session=session)
            iterations_used = _iter + 1
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
    waterfall_result: dict[str, Any] | None = None
    try:
        waterfall_result = await compute_waterfall(deal_model_id=model_id, session=session)
    except ValueError:
        # Cashflow succeeded — don't fail the whole request if waterfall can't run
        # (e.g. no capital modules configured yet)
        pass

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
async def export_model_xlsx(model_id: UUID, session: DBSession) -> Response:
    model = await _get_deal_or_404(session, model_id)
    workbook_bytes = await export_deal_model_workbook(deal_model_id=model_id, session=session)
    filename = make_export_filename(model)
    return Response(
        content=workbook_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
