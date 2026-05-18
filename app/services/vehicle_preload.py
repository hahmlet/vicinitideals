"""
vehicle_preload.py — Auto-seed GP Equity + LP Equity capital modules on scenario creation.

Finds or creates org-level default SourceVehicle records for GP and LP equity,
then creates CapitalModule rows for the new scenario so the model builder
always starts with at least two equity sources.

Called from the POST /ui/deals/create-model endpoint before commit.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capital import CapitalModule
from app.models.source_vehicle import SourceVehicle


async def preload_equity_modules(
    session: AsyncSession,
    scenario_id: uuid.UUID,
    org_id: uuid.UUID,
    project_id: uuid.UUID | None = None,
) -> list[CapitalModule]:
    """Ensure scenario has GP Equity + LP Equity capital modules with project junctions.

    Finds existing org-level default vehicles by (scope, owner_id, equity_role).
    Creates vehicles if absent. Creates CapitalModule rows for the scenario.
    Creates CapitalModuleProject junction rows so the engine and UI see $0 committed
    amounts immediately — user edits via Coverage modal to set real amounts.
    Idempotent: returns immediately if equity modules already exist.

    Returns the newly created CapitalModule rows (empty list if already existed).
    """
    from app.models.capital import CapitalModuleProject

    # Skip if equity modules already exist on this scenario
    existing = (
        await session.execute(
            select(CapitalModule).where(
                CapitalModule.scenario_id == scenario_id,
                CapitalModule.vehicle_type == "equity",
            )
        )
    ).scalars().all()
    if existing:
        return []

    gp_vehicle = await _get_or_create_vehicle(
        session, org_id, label="GP Equity", equity_role="gp", stack_pos=0
    )
    lp_vehicle = await _get_or_create_vehicle(
        session, org_id, label="LP Equity", equity_role="lp", stack_pos=10
    )
    await session.flush()

    gp_module = CapitalModule(
        scenario_id=scenario_id,
        source_vehicle_id=gp_vehicle.id,
        label="GP Equity",
        vehicle_type="equity",
        equity_role="gp",
        stack_position=90,
        source={"auto_size": True, "is_residual": True},
        carry=None,
        exit_terms=None,
    )
    lp_module = CapitalModule(
        scenario_id=scenario_id,
        source_vehicle_id=lp_vehicle.id,
        label="LP Equity",
        vehicle_type="equity",
        equity_role="lp",
        stack_position=80,
        source={"auto_size": False, "amount": "0"},
        carry=None,
        exit_terms=None,
    )
    session.add(gp_module)
    session.add(lp_module)
    await session.flush()

    # Wire both modules to the project via junction rows so the engine loads them
    # and the S&U panel shows $0 (not stale JSONB amounts from prior states).
    if project_id is not None:
        for mod in (lp_module, gp_module):
            session.add(CapitalModuleProject(
                capital_module_id=mod.id,
                project_id=project_id,
                amount=Decimal("0"),
                active_from="acquisition",
                active_to="exit",
                auto_size=False,
            ))

    return [gp_module, lp_module]


async def _get_or_create_vehicle(
    session: AsyncSession,
    org_id: uuid.UUID,
    label: str,
    equity_role: str,
    stack_pos: int,
) -> SourceVehicle:
    vehicle = (
        await session.execute(
            select(SourceVehicle).where(
                SourceVehicle.scope == "org",
                SourceVehicle.owner_id == org_id,
                SourceVehicle.equity_role == equity_role,
                SourceVehicle.vehicle_type == "equity",
            ).limit(1)
        )
    ).scalar_one_or_none()

    if vehicle is None:
        vehicle = SourceVehicle(
            scope="org",
            owner_id=org_id,
            label=label,
            vehicle_type="equity",
            equity_role=equity_role,
            default_waterfall_position=stack_pos,
            draw_cadence="residual_gap_filler" if equity_role == "gp" else "monthly",
        )
        session.add(vehicle)

    return vehicle
