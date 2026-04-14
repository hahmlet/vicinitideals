"""Capital stack and waterfall endpoints."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy import select

from vicinitideals.api.deps import DBSession
from vicinitideals.engines.waterfall import compute_waterfall, get_waterfall_distribution_report
from vicinitideals.models.capital import CapitalModule, WaterfallResult, WaterfallTier
from vicinitideals.models.deal import Scenario
from vicinitideals.observability import (
    build_observability_payload,
    begin_observation,
    elapsed_ms,
    log_observation,
    utc_now,
)
from vicinitideals.schemas.capital import (
    CapitalModuleBase,
    CapitalModuleRead,
    CapitalModuleUpdate,
    WaterfallDistributionReportRead,
    WaterfallResultRead,
    WaterfallTierBase,
    WaterfallTierRead,
    WaterfallTierUpdate,
)

router = APIRouter(tags=["capital"])
logger = logging.getLogger(__name__)


class CapitalModuleCreateRequest(CapitalModuleBase):
    pass


class CapitalModuleUpdateRequest(CapitalModuleUpdate):
    pass


class WaterfallTierCreateRequest(WaterfallTierBase):
    pass


class WaterfallTierUpdateRequest(WaterfallTierUpdate):
    pass


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


async def _get_deal_model_or_404(session: DBSession, model_id: UUID) -> Scenario:
    model = await session.get(Scenario, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Deal model not found")
    return model


async def _get_capital_module_or_404(
    session: DBSession,
    model_id: UUID,
    capital_module_id: UUID,
) -> CapitalModule:
    await _get_deal_model_or_404(session, model_id)
    capital_module = await session.get(CapitalModule, capital_module_id)
    if capital_module is None or capital_module.scenario_id != model_id:
        raise HTTPException(status_code=404, detail="Capital module not found")
    return capital_module


async def _get_waterfall_tier_or_404(
    session: DBSession,
    model_id: UUID,
    tier_id: UUID,
) -> WaterfallTier:
    await _get_deal_model_or_404(session, model_id)
    tier = await session.get(WaterfallTier, tier_id)
    if tier is None or tier.scenario_id != model_id:
        raise HTTPException(status_code=404, detail="Waterfall tier not found")
    return tier


async def _validate_capital_module_reference(
    session: DBSession,
    model_id: UUID,
    capital_module_id: UUID | None,
) -> None:
    if capital_module_id is None:
        return
    capital_module = await session.get(CapitalModule, capital_module_id)
    if capital_module is None or capital_module.scenario_id != model_id:
        raise HTTPException(status_code=404, detail="Capital module not found")


@router.get("/models/{model_id}/capital-modules", response_model=list[CapitalModuleRead])
async def list_capital_modules(model_id: UUID, session: DBSession) -> list[CapitalModule]:
    await _get_deal_model_or_404(session, model_id)
    result = await session.execute(
        select(CapitalModule)
        .where(CapitalModule.scenario_id == model_id)
        .order_by(CapitalModule.stack_position.asc(), CapitalModule.label.asc())
    )
    return list(result.scalars())


@router.post(
    "/models/{model_id}/capital-modules",
    response_model=CapitalModuleRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_capital_module(
    model_id: UUID,
    payload: CapitalModuleCreateRequest,
    session: DBSession,
) -> CapitalModule:
    await _get_deal_model_or_404(session, model_id)
    module = CapitalModule(scenario_id=model_id, **_json_safe(payload.model_dump()))
    session.add(module)
    await session.flush()
    await session.refresh(module)
    return module


@router.put("/models/{model_id}/capital-modules/{capital_module_id}", response_model=CapitalModuleRead)
@router.patch("/models/{model_id}/capital-modules/{capital_module_id}", response_model=CapitalModuleRead)
async def update_capital_module(
    model_id: UUID,
    capital_module_id: UUID,
    payload: CapitalModuleUpdateRequest,
    session: DBSession,
) -> CapitalModule:
    capital_module = await _get_capital_module_or_404(session, model_id, capital_module_id)

    for field, value in _json_safe(payload.model_dump(exclude_unset=True)).items():
        setattr(capital_module, field, value)

    await session.flush()
    await session.refresh(capital_module)
    return capital_module


@router.delete(
    "/models/{model_id}/capital-modules/{capital_module_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_capital_module(
    model_id: UUID,
    capital_module_id: UUID,
    session: DBSession,
) -> Response:
    capital_module = await _get_capital_module_or_404(session, model_id, capital_module_id)

    waterfall_results = await session.execute(
        select(WaterfallResult).where(WaterfallResult.capital_module_id == capital_module_id)
    )
    for result in waterfall_results.scalars():
        await session.delete(result)

    waterfall_tiers = await session.execute(
        select(WaterfallTier).where(WaterfallTier.capital_module_id == capital_module_id)
    )
    for tier in waterfall_tiers.scalars():
        tier.capital_module_id = None

    await session.delete(capital_module)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/models/{model_id}/waterfall-tiers", response_model=list[WaterfallTierRead])
async def list_waterfall_tiers(model_id: UUID, session: DBSession) -> list[WaterfallTier]:
    await _get_deal_model_or_404(session, model_id)
    result = await session.execute(
        select(WaterfallTier)
        .where(WaterfallTier.scenario_id == model_id)
        .order_by(WaterfallTier.priority.asc(), WaterfallTier.id.asc())
    )
    return list(result.scalars())


@router.post(
    "/models/{model_id}/waterfall-tiers",
    response_model=WaterfallTierRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_waterfall_tier(
    model_id: UUID,
    payload: WaterfallTierCreateRequest,
    session: DBSession,
) -> WaterfallTier:
    await _get_deal_model_or_404(session, model_id)
    await _validate_capital_module_reference(session, model_id, payload.capital_module_id)
    tier = WaterfallTier(scenario_id=model_id, **payload.model_dump())
    session.add(tier)
    await session.flush()
    await session.refresh(tier)
    return tier


@router.put("/models/{model_id}/waterfall-tiers/{tier_id}", response_model=WaterfallTierRead)
@router.patch("/models/{model_id}/waterfall-tiers/{tier_id}", response_model=WaterfallTierRead)
async def update_waterfall_tier(
    model_id: UUID,
    tier_id: UUID,
    payload: WaterfallTierUpdateRequest,
    session: DBSession,
) -> WaterfallTier:
    tier = await _get_waterfall_tier_or_404(session, model_id, tier_id)
    payload_data = payload.model_dump(exclude_unset=True)

    if "capital_module_id" in payload_data:
        await _validate_capital_module_reference(session, model_id, payload_data["capital_module_id"])

    for field, value in payload_data.items():
        setattr(tier, field, value)

    await session.flush()
    await session.refresh(tier)
    return tier


@router.delete(
    "/models/{model_id}/waterfall-tiers/{tier_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_waterfall_tier(
    model_id: UUID,
    tier_id: UUID,
    session: DBSession,
) -> Response:
    tier = await _get_waterfall_tier_or_404(session, model_id, tier_id)

    waterfall_results = await session.execute(
        select(WaterfallResult).where(WaterfallResult.tier_id == tier_id)
    )
    for result in waterfall_results.scalars():
        await session.delete(result)

    await session.delete(tier)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/models/{model_id}/waterfall", response_model=list[WaterfallResultRead])
async def get_waterfall_results(model_id: UUID, session: DBSession) -> list[WaterfallResult]:
    await _get_deal_model_or_404(session, model_id)
    result = await session.execute(
        select(WaterfallResult)
        .where(WaterfallResult.scenario_id == model_id)
        .order_by(WaterfallResult.period.asc(), WaterfallResult.id.asc())
    )
    return list(result.scalars())


@router.get("/models/{model_id}/waterfall/report", response_model=WaterfallDistributionReportRead)
async def get_model_waterfall_report(model_id: UUID, session: DBSession) -> dict[str, Any]:
    await _get_deal_model_or_404(session, model_id)
    try:
        return await get_waterfall_distribution_report(deal_model_id=model_id, session=session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/models/{model_id}/waterfall/compute")
async def compute_model_waterfall(model_id: UUID, request: Request, session: DBSession) -> dict[str, Any]:
    await _get_deal_model_or_404(session, model_id)
    trace_id, started_at, started_at_monotonic = begin_observation(
        getattr(request.state, "trace_id", None)
    )
    user_id = getattr(request.state, "user_id", None)
    log_observation(
        logger,
        "underwriting_compute_started",
        trace_id=trace_id,
        run_type="waterfall",
        deal_model_id=model_id,
        user_id=user_id,
    )
    try:
        result = await compute_waterfall(deal_model_id=model_id, session=session)
    except ValueError as exc:
        log_observation(
            logger,
            "underwriting_compute_failed",
            trace_id=trace_id,
            run_type="waterfall",
            deal_model_id=model_id,
            duration_ms=elapsed_ms(started_at_monotonic),
            user_id=user_id,
            error=str(exc),
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    completed_at = utc_now()
    duration_ms = elapsed_ms(started_at_monotonic)
    response = dict(result)
    response["observability"] = build_observability_payload(
        trace_id=trace_id,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=duration_ms,
        run_type="waterfall",
        deal_model_id=str(model_id),
        user_id=user_id,
    )
    log_observation(
        logger,
        "underwriting_compute_completed",
        trace_id=trace_id,
        run_type="waterfall",
        deal_model_id=model_id,
        duration_ms=duration_ms,
        user_id=user_id,
    )
    return response
