"""Shared DrawSource service — one code path for UI and REST/MCP CRUD.

Extracted from the draw-schedule handlers in
app/api/routers/ui_model_outputs.py so the builder UI and the REST router
(app/api/routers/milestones.py) create/update/delete DrawSource rows
identically. DrawSource rows are what the draw-schedule engine iterates;
the reconciler in ``_load_draw_schedule_ctx`` keeps them in sync with
CapitalModules, so rows created here follow the same shape it expects.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capital import DrawSource


async def next_draw_source_sort_order(
    session: AsyncSession, scenario_id: UUID
) -> int:
    """Next sort_order for a new DrawSource on this scenario (max + 1)."""
    max_order = (await session.execute(
        select(DrawSource.sort_order)
        .where(DrawSource.scenario_id == scenario_id)
        .order_by(DrawSource.sort_order.desc())
        .limit(1)
    )).scalar_one_or_none()
    return (max_order or 0) + 1


async def list_scenario_draw_sources(
    session: AsyncSession, scenario_id: UUID
) -> list[DrawSource]:
    """All DrawSources for a scenario in draw-schedule (sort_order) order."""
    rows = (await session.execute(
        select(DrawSource)
        .where(DrawSource.scenario_id == scenario_id)
        .order_by(DrawSource.sort_order, DrawSource.id)
    )).scalars()
    return list(rows)


async def get_draw_source_for_model(
    session: AsyncSession, scenario_id: UUID, source_id: UUID
) -> DrawSource | None:
    """Fetch a DrawSource scoped to the scenario; None when absent/foreign."""
    ds = await session.get(DrawSource, source_id)
    if ds is None or ds.scenario_id != scenario_id:
        return None
    return ds


async def create_draw_source(
    session: AsyncSession,
    scenario_id: UUID,
    *,
    label: str,
    active_from_milestone: str,
    active_to_milestone: str,
    source_type: str = "equity",
    draw_every_n_months: int = 1,
    annual_interest_rate: Decimal = Decimal("0"),
    active_from_offset_days: int = 0,
    active_to_offset_days: int = 0,
    total_commitment: Decimal | None = None,
    project_id: UUID | None = None,
    capital_module_id: UUID | None = None,
    sort_order: int | None = None,
) -> DrawSource:
    """Create a DrawSource row. ``sort_order=None`` appends after the max."""
    if sort_order is None:
        sort_order = await next_draw_source_sort_order(session, scenario_id)

    ds = DrawSource(
        id=uuid.uuid4(),
        scenario_id=scenario_id,
        project_id=project_id,
        sort_order=sort_order,
        label=label.strip(),
        source_type=source_type,
        draw_every_n_months=max(1, draw_every_n_months),
        annual_interest_rate=annual_interest_rate,
        active_from_milestone=active_from_milestone,
        active_to_milestone=active_to_milestone,
        active_from_offset_days=active_from_offset_days,
        active_to_offset_days=active_to_offset_days,
        total_commitment=total_commitment,
        capital_module_id=capital_module_id,
    )
    session.add(ds)
    await session.flush()
    return ds


async def update_draw_source(
    session: AsyncSession,
    draw_source: DrawSource,
    fields: dict,
) -> DrawSource:
    """Apply a partial update to a DrawSource and flush."""
    for key, value in fields.items():
        if key == "draw_every_n_months" and value is not None:
            value = max(1, int(value))
        setattr(draw_source, key, value)
    await session.flush()
    return draw_source


async def delete_draw_source(
    session: AsyncSession, draw_source: DrawSource
) -> None:
    """Delete a DrawSource row and flush."""
    await session.delete(draw_source)
    await session.flush()
