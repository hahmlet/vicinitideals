"""
Clone scenario for CFSR investigation.

Creates "Combined Pool (CFSR Test)" as an inactive copy of scenario 4bc8fd71.
Copies ALL use_line fields (including timing_type, active_from_milestone_id,
spread_to_milestone_id, eligible_module_ids) with proper ID remapping so the
test scenario computes identically to production.

Usage:
    docker exec vicinitideals-api sh -c "cd /app && python scripts/clone_scenario_for_test.py"
"""
from __future__ import annotations

import asyncio
import sys
import uuid as _uuid

sys.path.insert(0, "/app")

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.models.capital import CapitalModule, WaterfallTier
from app.models.capital import CapitalModuleProject as CMP
from app.models.deal import (
    IncomeStream,
    OperatingExpenseLine,
    OperationalInputs,
    Scenario,
    UseLine,
)
from app.models.milestone import Milestone
from app.models.project import Project

SOURCE_SCENARIO_ID = "4bc8fd71-788a-47c6-b6cd-c5325e84ddd6"
CLONE_NAME = "Combined Pool (CFSR Test)"


async def clone_project_data(
    src_proj: Project,
    dst_proj: Project,
    session: AsyncSession,
    ms_id_map: dict,
    module_id_map: dict,
) -> None:
    """Copy milestones + all line items from src → dst with ID remapping."""

    # --- milestones (two-pass: create then wire triggers) ---
    src_milestones = list(
        (await session.execute(
            select(Milestone).where(Milestone.project_id == src_proj.id)
        )).scalars()
    )
    for ms in src_milestones:
        new_ms = Milestone(
            project_id=dst_proj.id,
            milestone_type=ms.milestone_type,
            label=ms.label,
            target_date=ms.target_date,
            duration_days=ms.duration_days,
            sequence_order=ms.sequence_order,
        )
        session.add(new_ms)
        await session.flush()
        ms_id_map[ms.id] = new_ms.id

    for ms in src_milestones:
        if ms.trigger_milestone_id and ms.trigger_milestone_id in ms_id_map:
            new_ms_obj = await session.get(Milestone, ms_id_map[ms.id])
            if new_ms_obj:
                new_ms_obj.trigger_milestone_id = ms_id_map[ms.trigger_milestone_id]
                new_ms_obj.trigger_offset_days = ms.trigger_offset_days

    # --- use lines (full field copy with ID remapping) ---
    src_use_lines = list(
        (await session.execute(
            select(UseLine).where(UseLine.project_id == src_proj.id)
        )).scalars()
    )
    for u in src_use_lines:
        new_active_from = ms_id_map.get(u.active_from_milestone_id) if u.active_from_milestone_id else None
        new_spread_to = ms_id_map.get(u.spread_to_milestone_id) if u.spread_to_milestone_id else None
        new_source_cm = module_id_map.get(u.source_capital_module_id) if u.source_capital_module_id else None
        new_eligible = [module_id_map.get(mid, mid) for mid in (u.eligible_module_ids or [])]

        session.add(UseLine(
            project_id=dst_proj.id,
            label=u.label,
            phase=u.phase,
            amount=u.amount,
            timing_type=u.timing_type,
            is_deferred=u.is_deferred,
            notes=u.notes,
            cost_category=u.cost_category,
            dev_fee_basis_bucket=u.dev_fee_basis_bucket,
            active_from_milestone_id=new_active_from,
            spread_to_milestone_id=new_spread_to,
            source_capital_module_id=new_source_cm,
            eligible_module_ids=new_eligible,
            is_auto_dev_fee=u.is_auto_dev_fee,
            dev_fee_pct=u.dev_fee_pct,
            dev_fee_basis=u.dev_fee_basis,
            is_auto_finance_cost=u.is_auto_finance_cost,
            dev_fee_release_schedule=u.dev_fee_release_schedule,
            dev_fee_binding_context=u.dev_fee_binding_context,
            is_auto_acquisition_fee=u.is_auto_acquisition_fee,
            dev_fee_acquisition_treatment=u.dev_fee_acquisition_treatment,
            dev_fee_acquisition_pct=u.dev_fee_acquisition_pct,
            acquisition_fee_pct=u.acquisition_fee_pct,
        ))

    # --- income streams ---
    for s in (await session.execute(
        select(IncomeStream).where(IncomeStream.project_id == src_proj.id)
    )).scalars():
        session.add(IncomeStream(
            project_id=dst_proj.id,
            stream_type=s.stream_type,
            label=s.label,
            unit_count=s.unit_count,
            amount_per_unit_monthly=s.amount_per_unit_monthly,
            amount_fixed_monthly=s.amount_fixed_monthly,
            stabilized_occupancy_pct=s.stabilized_occupancy_pct,
            escalation_rate_pct_annual=s.escalation_rate_pct_annual,
            active_in_phases=s.active_in_phases,
            notes=s.notes,
        ))

    # --- expense lines ---
    for e in (await session.execute(
        select(OperatingExpenseLine).where(OperatingExpenseLine.project_id == src_proj.id)
    )).scalars():
        session.add(OperatingExpenseLine(
            project_id=dst_proj.id,
            label=e.label,
            annual_amount=e.annual_amount,
            escalation_rate_pct_annual=e.escalation_rate_pct_annual,
            active_in_phases=e.active_in_phases,
            notes=e.notes,
        ))

    # --- unit mix ---
    if src_proj.unit_mix:
        dst_proj.unit_mix = list(src_proj.unit_mix)

    # --- operational inputs (all columns verbatim) ---
    src_inputs = (await session.execute(
        select(OperationalInputs).where(OperationalInputs.project_id == src_proj.id)
    )).scalar_one_or_none()
    if src_inputs:
        new_inputs = OperationalInputs(project_id=dst_proj.id)
        skip = {"id", "project_id"}
        for col in OperationalInputs.__table__.columns:
            if col.name not in skip:
                setattr(new_inputs, col.name, getattr(src_inputs, col.name, None))
        session.add(new_inputs)


async def main() -> None:
    async with AsyncSessionLocal() as session:
        src = await session.get(Scenario, SOURCE_SCENARIO_ID)
        if src is None:
            print(f"ERROR: source scenario {SOURCE_SCENARIO_ID} not found")
            sys.exit(1)

        # --- create clone scenario ---
        new_scenario = Scenario(
            deal_id=src.deal_id,
            name=CLONE_NAME,
            version=src.version + 1,
            is_active=False,
            project_type=src.project_type,
            min_reserve_construction=src.min_reserve_construction,
            min_reserve_operational=src.min_reserve_operational,
            income_mode=src.income_mode,
            risk_free_rate_pct=src.risk_free_rate_pct,
            health_thresholds=src.health_thresholds,
            discount_rate_pct=src.discount_rate_pct,
        )
        session.add(new_scenario)
        await session.flush()
        print(f"New scenario ID: {new_scenario.id}")

        # --- copy capital modules first (need module_id_map for use_line remapping) ---
        src_modules = list(
            (await session.execute(
                select(CapitalModule).where(CapitalModule.scenario_id == SOURCE_SCENARIO_ID)
            )).scalars()
        )
        module_id_map: dict = {}
        for cm in src_modules:
            new_cm = CapitalModule(
                scenario_id=new_scenario.id,
                label=cm.label,
                vehicle_type=cm.vehicle_type,
                equity_role=cm.equity_role,
                stack_position=cm.stack_position,
                source=cm.source,
                carry=cm.carry,
                exit_terms=cm.exit_terms,
                active_phase_start=cm.active_phase_start,
                active_phase_end=cm.active_phase_end,
            )
            session.add(new_cm)
            await session.flush()
            module_id_map[cm.id] = new_cm.id
            print(f"  Cloned capital module: {cm.label}")

        # --- copy projects ---
        src_projects = list(
            (await session.execute(
                select(Project).where(Project.scenario_id == SOURCE_SCENARIO_ID)
                .order_by(Project.created_at.asc())
            )).scalars()
        )
        project_id_map: dict = {}
        ms_id_map: dict = {}

        for src_proj in src_projects:
            new_proj = Project(
                scenario_id=new_scenario.id,
                opportunity_id=src_proj.opportunity_id,
                name=src_proj.name,
                timeline_approved=src_proj.timeline_approved,
            )
            session.add(new_proj)
            await session.flush()
            project_id_map[src_proj.id] = new_proj.id
            print(f"  Cloning project: {src_proj.name}")

            await clone_project_data(
                src_proj, new_proj, session, ms_id_map, module_id_map
            )

        # --- capital_module_projects junction rows ---
        src_junctions = list(
            (await session.execute(
                select(CMP).where(CMP.capital_module_id.in_(list(module_id_map.keys())))
            )).scalars()
        )
        for j in src_junctions:
            new_pid = project_id_map.get(j.project_id)
            new_mid = module_id_map.get(j.capital_module_id)
            if new_pid is None or new_mid is None:
                continue
            session.add(CMP(
                capital_module_id=new_mid,
                project_id=new_pid,
                amount=j.amount,
                active_from=j.active_from,
                active_to=j.active_to,
                active_from_offset_days=j.active_from_offset_days,
                active_to_offset_days=j.active_to_offset_days,
                auto_size=j.auto_size,
            ))

        # --- waterfall tiers ---
        for t in (await session.execute(
            select(WaterfallTier).where(WaterfallTier.scenario_id == SOURCE_SCENARIO_ID)
        )).scalars():
            session.add(WaterfallTier(
                scenario_id=new_scenario.id,
                project_id=project_id_map.get(t.project_id) if t.project_id else None,
                capital_module_id=module_id_map.get(t.capital_module_id) if t.capital_module_id else None,
                priority=t.priority,
                tier_type=t.tier_type,
                irr_hurdle_pct=t.irr_hurdle_pct,
                lp_split_pct=t.lp_split_pct,
                gp_split_pct=t.gp_split_pct,
                description=t.description,
                max_pct_of_distributable=t.max_pct_of_distributable,
                interest_rate_pct=t.interest_rate_pct,
            ))

        await session.commit()
        print(f"\nClone complete: {new_scenario.id}")
        print(f"  Name: {CLONE_NAME}")
        print(f"  Projects: {len(src_projects)}")
        print(f"  Capital modules: {len(src_modules)}")


if __name__ == "__main__":
    asyncio.run(main())
