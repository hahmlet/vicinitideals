"""Integration test: per-project phase plan cells in investor export.

Exports a workbook for a minimal scenario and verifies the per-project
sheet exposes the phase-window named cells produced by
:func:`app.engines.phase_plan.build_project_phase_windows`. Future Excel
formulas (e.g. construction-to-perm origination gating) will reference
these cells in-sheet, so they must exist with sensible integer values.
"""
from __future__ import annotations

from io import BytesIO

import pytest
from openpyxl import load_workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.exporters.investor_export import export_investor_workbook
from tests.conftest import (
    seed_deal_model_with_financials,
    seed_opportunity,
    seed_org,
)


pytestmark = pytest.mark.asyncio


async def _seed_multi_project_scenario(session: AsyncSession):
    """Per-project sheets are skipped when len(projects)==1, so seed a
    second project so ``_build_project_sheet`` actually fires."""
    from decimal import Decimal as _D
    from uuid import uuid4

    from app.models.deal import OperationalInputs as _OI
    from app.models.project import Project as _Project

    org, user = await seed_org(session)
    opportunity = await seed_opportunity(session, org, user, name="Phase-Plan-Smoke")
    deal_model, _, _, _ = await seed_deal_model_with_financials(
        session, opportunity, user
    )
    extra = _Project(
        id=uuid4(),
        scenario_id=deal_model.id,
        opportunity_id=None,
        name="Second",
    )
    session.add(extra)
    await session.flush()
    session.add(
        _OI(
            id=uuid4(), project_id=extra.id,
            unit_count_new=4,
            exit_cap_rate_pct=_D("5.5"),
        )
    )
    await session.flush()
    return deal_model


async def test_phase_plan_named_cells_present_and_resolve(session: AsyncSession) -> None:
    scenario = await _seed_multi_project_scenario(session)
    blob = await export_investor_workbook(scenario.id, session)
    wb = load_workbook(BytesIO(blob), data_only=False)

    defined = {name for name in wb.defined_names}

    # At minimum: acquisition + stabilized + exit always exist on any project.
    required = {
        "p1_phase_acquisition_start_month",
        "p1_phase_acquisition_end_month",
        "p1_phase_acquisition_duration_months",
        "p1_phase_stabilized_start_month",
        "p1_phase_stabilized_end_month",
        "p1_phase_stabilized_duration_months",
        "p1_phase_exit_start_month",
        "p1_phase_exit_end_month",
        "p1_total_horizon_months",
    }
    missing = required - defined
    assert not missing, f"phase plan cells missing from workbook: {sorted(missing)}"


async def test_phase_plan_cell_values_are_positive_integers_in_order(
    session: AsyncSession,
) -> None:
    """Each phase window must satisfy 1 ≤ start ≤ end and durations chain."""
    scenario = await _seed_multi_project_scenario(session)
    blob = await export_investor_workbook(scenario.id, session)
    wb = load_workbook(BytesIO(blob), data_only=False)

    def _resolve(name: str) -> int | None:
        dn = wb.defined_names.get(name)
        if dn is None:
            return None
        for sheet_name, cell_ref in dn.destinations:
            sheet = wb[sheet_name]
            value = sheet[cell_ref].value
            return int(value) if value is not None else None
        return None

    acq_start = _resolve("p1_phase_acquisition_start_month")
    acq_end = _resolve("p1_phase_acquisition_end_month")
    stab_start = _resolve("p1_phase_stabilized_start_month")
    stab_end = _resolve("p1_phase_stabilized_end_month")
    horizon = _resolve("p1_total_horizon_months")

    assert acq_start == 1  # acquisition is always month 1
    assert acq_end is not None and acq_end >= acq_start
    assert stab_start is not None and stab_start > acq_end
    assert stab_end is not None and stab_end >= stab_start
    assert horizon is not None and horizon == stab_end + (
        # exit phase is always 1 month, so horizon = stabilized_end + 1
        # unless an exit milestone shrinks the plan — accept either +1 or +0
        # for milestone-overridden scenarios.
        1 if _resolve("p1_phase_exit_start_month") == stab_end + 1 else 0
    )
