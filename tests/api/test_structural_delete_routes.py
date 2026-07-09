"""Integration tests for the deletion-regression class of builder routes
(app/api/routers/ui_model_builder.py).

Covers:
  - POST /ui/deals/{id}/variant                       — deep-copy a Scenario
  - POST /ui/deals/{id}/new-project                   — add Project to Scenario
  - POST /ui/deals/{id}/project/{pid}/delete          — delete one Project
  - POST /ui/deals/{id}/delete-variant                — delete whole Scenario

Assertions verify rows are actually created/gone in the DB, not just 200s.
`{id}` in these URLs is the Scenario id (builder-route convention).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import Deal, Scenario, UseLine
from app.models.milestone import Milestone
from app.models.project import Project

from tests.conftest import (
    seed_deal_model_with_financials,
    seed_opportunity,
    seed_org,
    set_client_auth,
)

pytestmark = pytest.mark.asyncio


async def _seed(session: AsyncSession):
    """Org + user + opp + scenario-with-financials. Returns plain ids."""
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, _, _ = await seed_deal_model_with_financials(session, opp, user)
    project = (
        await session.execute(
            select(Project).where(Project.scenario_id == deal_model.id)
        )
    ).scalar_one()
    await session.commit()
    return org, user, opp, deal_model, project


# ---------------------------------------------------------------------------
# POST /ui/deals/{id}/variant — create (so we can also delete)
# ---------------------------------------------------------------------------


async def test_create_variant_deep_copies_scenario(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, user, _opp, deal_model, project = await _seed(session)
    scenario_id, deal_id, project_id = deal_model.id, deal_model.deal_id, project.id
    set_client_auth(client, user.id)

    resp = await client.post(
        f"/ui/deals/{scenario_id}/variant",
        data={"name": "Variant B"},
        follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text
    assert "/builder" in resp.headers["location"]

    session.expire_all()
    variants = (
        await session.execute(
            select(Scenario).where(
                Scenario.deal_id == deal_id, Scenario.name == "Variant B"
            )
        )
    ).scalars().all()
    assert len(variants) == 1
    new_scenario = variants[0]
    assert new_scenario.id != scenario_id
    assert new_scenario.is_active is False
    assert new_scenario.version == 2

    # Projects deep-copied (new rows, same opportunity lineage)
    new_projects = (
        await session.execute(
            select(Project).where(Project.scenario_id == new_scenario.id)
        )
    ).scalars().all()
    assert len(new_projects) == 1
    assert new_projects[0].id != project_id


async def test_create_variant_is_faithful_copy(
    client: AsyncClient, session: AsyncSession
) -> None:
    """A variant must compute identically to its source until edited.

    Regression for the 2026-07-08 'Remove Rochelle - Add Edgemont' incident:
    the old clone (a) hand-picked UseLine kwargs, dropping
    is_auto_finance_cost + source_capital_module_id (engine then regenerated
    a second FC row → finance costs double-counted), and (b) re-applied
    current org Type 1 defaults over the copied OperationalInputs, resetting
    per-project debt_sizing_mode (gap_fill → dual_constraint zeroed two
    net-negative projects' bond slices via the DSCR cap).
    """
    from app.models.capital import CapitalModule, CapitalModuleProject
    from app.models.deal import OperationalInputs
    from app.models.milestone import Milestone, MilestoneType

    _org, user, _opp, deal_model, project = await _seed(session)
    scenario_id, deal_id, project_id = deal_model.id, deal_model.deal_id, project.id

    ms = Milestone(
        project_id=project_id,
        milestone_type=MilestoneType.close,
        label="Close",
        duration_days=30,
        sequence_order=1,
    )
    session.add(ms)
    await session.flush()

    bond = CapitalModule(
        scenario_id=scenario_id,
        label="Test Bond",
        vehicle_type="debt",
        stack_position=0,
        source={"amount": 1_000_000, "auto_size": True, "rate_pct": 5.5},
        fee_terms={"origination_pct": 1.0},
        active_from_milestone_id=ms.id,
    )
    session.add(bond)
    await session.flush()
    floatm = CapitalModule(
        scenario_id=scenario_id,
        label="Float",
        vehicle_type="float_earnings",
        stack_position=1,
        source={
            "parent_module_id": str(bond.id),
            "waterfall_milestone_id": str(ms.id),
        },
    )
    session.add(floatm)
    session.add(CapitalModuleProject(
        capital_module_id=bond.id,
        project_id=project_id,
        amount=Decimal("1000000"),
        auto_size=True,
        active_from_milestone_id=ms.id,
    ))
    fc_line = UseLine(
        project_id=project_id,
        label="Test Bond — Total Finance Costs",
        amount=Decimal("20000"),
        is_auto_finance_cost=True,
        source_capital_module_id=bond.id,
        active_from_milestone_id=ms.id,
    )
    whitelisted_line = UseLine(
        project_id=project_id,
        label="Bond-only Cost",
        amount=Decimal("5000"),
        eligible_module_ids=[bond.id],
    )
    session.add_all([fc_line, whitelisted_line])
    # Per-project choices that differ from org Type 1 defaults — the old
    # clone reset these to org policy.
    inputs = (await session.execute(
        select(OperationalInputs).where(OperationalInputs.project_id == project_id)
    )).scalar_one()
    inputs.debt_sizing_mode = "dual_constraint"
    inputs.operation_reserve_months = 9
    bond_id = bond.id
    await session.commit()

    set_client_auth(client, user.id)
    resp = await client.post(
        f"/ui/deals/{scenario_id}/variant",
        data={"name": "Faithful"},
        follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text

    session.expire_all()
    new_scn = (await session.execute(
        select(Scenario).where(Scenario.deal_id == deal_id, Scenario.name == "Faithful")
    )).scalar_one()
    new_proj = (await session.execute(
        select(Project).where(Project.scenario_id == new_scn.id)
    )).scalar_one()
    new_ms = (await session.execute(
        select(Milestone).where(Milestone.project_id == new_proj.id)
    )).scalar_one()
    new_bond = (await session.execute(
        select(CapitalModule).where(
            CapitalModule.scenario_id == new_scn.id, CapitalModule.label == "Test Bond"
        )
    )).scalar_one()
    new_float = (await session.execute(
        select(CapitalModule).where(
            CapitalModule.scenario_id == new_scn.id, CapitalModule.label == "Float"
        )
    )).scalar_one()

    # Module fidelity: fee_terms + milestone window survive, remapped.
    assert new_bond.id != bond_id
    assert new_bond.fee_terms == {"origination_pct": 1.0}
    assert new_bond.active_from_milestone_id == new_ms.id

    # Float JSONB cross-refs remapped onto the clone's rows.
    assert new_float.source["parent_module_id"] == str(new_bond.id)
    assert new_float.source["waterfall_milestone_id"] == str(new_ms.id)

    # Junction remapped (module, project, milestone window).
    new_junction = (await session.execute(
        select(CapitalModuleProject).where(
            CapitalModuleProject.capital_module_id == new_bond.id
        )
    )).scalar_one()
    assert new_junction.project_id == new_proj.id
    assert new_junction.auto_size is True
    assert new_junction.active_from_milestone_id == new_ms.id

    # Auto finance-cost line: flag survives, source module remapped — the
    # engine must UPDATE this row on compute, not create a duplicate.
    new_fc = (await session.execute(
        select(UseLine).where(
            UseLine.project_id == new_proj.id,
            UseLine.label == "Test Bond — Total Finance Costs",
        )
    )).scalar_one()
    assert new_fc.is_auto_finance_cost is True
    assert new_fc.source_capital_module_id == new_bond.id
    assert new_fc.active_from_milestone_id == new_ms.id

    # Eligibility whitelist remapped onto the cloned module.
    new_wl = (await session.execute(
        select(UseLine).where(
            UseLine.project_id == new_proj.id, UseLine.label == "Bond-only Cost"
        )
    )).scalar_one()
    assert list(new_wl.eligible_module_ids) == [new_bond.id]

    # OperationalInputs verbatim — org Type 1 defaults must NOT clobber
    # per-project choices.
    new_inputs = (await session.execute(
        select(OperationalInputs).where(OperationalInputs.project_id == new_proj.id)
    )).scalar_one()
    assert new_inputs.debt_sizing_mode == "dual_constraint"
    assert new_inputs.operation_reserve_months == 9


# ---------------------------------------------------------------------------
# POST /ui/deals/{id}/new-project
# ---------------------------------------------------------------------------


async def test_new_project_creates_project_and_acquisition_use_line(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, user, opp, deal_model, _project = await _seed(session)
    scenario_id, opp_id = deal_model.id, opp.id
    set_client_auth(client, user.id)

    resp = await client.post(
        f"/ui/deals/{scenario_id}/new-project",
        data={
            "name": "Phase 2",
            "deal_type": "value_add",
            "opportunity_id": str(opp_id),
            "acquisition_cost": "750000",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text

    session.expire_all()
    new_proj = (
        await session.execute(
            select(Project).where(
                Project.scenario_id == scenario_id, Project.name == "Phase 2"
            )
        )
    ).scalar_one()
    # ?project= param on the redirect — the builder invariant that JSONB
    # updates silently no-op without it.
    assert f"project={new_proj.id}" in resp.headers["location"]

    acq_line = (
        await session.execute(
            select(UseLine).where(
                UseLine.project_id == new_proj.id,
                UseLine.cost_category == "acquisition",
            )
        )
    ).scalar_one()
    assert Decimal(str(acq_line.amount)) == Decimal("750000")

    # Milestones seeded for the new project
    milestones = (
        await session.execute(
            select(Milestone).where(Milestone.project_id == new_proj.id)
        )
    ).scalars().all()
    assert len(milestones) > 0


async def test_new_project_requires_opportunity_and_positive_cost(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, user, opp, deal_model, _project = await _seed(session)
    scenario_id, opp_id = deal_model.id, opp.id
    set_client_auth(client, user.id)

    missing_opp = await client.post(
        f"/ui/deals/{scenario_id}/new-project",
        data={"name": "Bad", "deal_type": "value_add", "acquisition_cost": "100"},
        follow_redirects=False,
    )
    assert missing_opp.status_code == 400

    zero_cost = await client.post(
        f"/ui/deals/{scenario_id}/new-project",
        data={
            "name": "Bad 2",
            "deal_type": "value_add",
            "opportunity_id": str(opp_id),
            "acquisition_cost": "0",
        },
        follow_redirects=False,
    )
    assert zero_cost.status_code == 400

    session.expire_all()
    count = len(
        (
            await session.execute(
                select(Project).where(Project.scenario_id == scenario_id)
            )
        ).scalars().all()
    )
    assert count == 1  # nothing created


# ---------------------------------------------------------------------------
# POST /ui/deals/{id}/project/{pid}/delete
# ---------------------------------------------------------------------------


async def test_delete_project_removes_rows(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, user, opp, deal_model, _project = await _seed(session)
    scenario_id, opp_id = deal_model.id, opp.id
    set_client_auth(client, user.id)

    # Create a second project through the real route so children exist
    created = await client.post(
        f"/ui/deals/{scenario_id}/new-project",
        data={
            "name": "Doomed",
            "deal_type": "value_add",
            "opportunity_id": str(opp_id),
            "acquisition_cost": "500000",
        },
        follow_redirects=False,
    )
    assert created.status_code == 303, created.text

    session.expire_all()
    doomed = (
        await session.execute(
            select(Project).where(
                Project.scenario_id == scenario_id, Project.name == "Doomed"
            )
        )
    ).scalar_one()
    doomed_id = doomed.id

    resp = await client.post(
        f"/ui/deals/{scenario_id}/project/{doomed_id}/delete",
        follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text

    session.expire_all()
    assert await session.get(Project, doomed_id) is None
    # Children gone too — no orphaned use lines or milestones
    orphan_lines = (
        await session.execute(
            select(UseLine).where(UseLine.project_id == doomed_id)
        )
    ).scalars().all()
    assert orphan_lines == []
    orphan_ms = (
        await session.execute(
            select(Milestone).where(Milestone.project_id == doomed_id)
        )
    ).scalars().all()
    assert orphan_ms == []


async def test_delete_last_project_is_refused(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, user, _opp, deal_model, project = await _seed(session)
    scenario_id, project_id = deal_model.id, project.id
    set_client_auth(client, user.id)

    resp = await client.post(
        f"/ui/deals/{scenario_id}/project/{project_id}/delete",
        follow_redirects=False,
    )
    # Silently refused via redirect back to the builder — project survives
    assert resp.status_code == 303
    session.expire_all()
    assert await session.get(Project, project_id) is not None


# ---------------------------------------------------------------------------
# POST /ui/deals/{id}/delete-variant
# ---------------------------------------------------------------------------


async def test_delete_variant_removes_scenario_keeps_deal(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, user, _opp, deal_model, _project = await _seed(session)
    scenario_id, deal_id = deal_model.id, deal_model.deal_id
    set_client_auth(client, user.id)

    # Create the variant we will delete
    created = await client.post(
        f"/ui/deals/{scenario_id}/variant",
        data={"name": "Kill Me"},
        follow_redirects=False,
    )
    assert created.status_code == 303, created.text

    session.expire_all()
    victim = (
        await session.execute(
            select(Scenario).where(
                Scenario.deal_id == deal_id, Scenario.name == "Kill Me"
            )
        )
    ).scalar_one()
    victim_id = victim.id
    victim_project_ids = [
        p.id
        for p in (
            await session.execute(
                select(Project).where(Project.scenario_id == victim_id)
            )
        ).scalars()
    ]

    resp = await client.post(
        f"/ui/deals/{victim_id}/delete-variant", follow_redirects=False
    )
    assert resp.status_code == 303, resp.text
    # Redirect lands on the surviving sibling variant's builder
    assert f"/models/{scenario_id}/builder" in resp.headers["location"]

    session.expire_all()
    assert await session.get(Scenario, victim_id) is None
    for pid in victim_project_ids:
        assert await session.get(Project, pid) is None
    # Deal survives — it still has the original scenario
    assert await session.get(Deal, deal_id) is not None
    assert await session.get(Scenario, scenario_id) is not None


async def test_delete_last_variant_also_deletes_deal(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Regression guard for the test-deal janitor bug class: deleting the last
    Scenario must also delete the owning top-level Deal row, not orphan it."""
    _org, user, _opp, deal_model, project = await _seed(session)
    scenario_id, deal_id, project_id = deal_model.id, deal_model.deal_id, project.id
    set_client_auth(client, user.id)

    resp = await client.post(
        f"/ui/deals/{scenario_id}/delete-variant", follow_redirects=False
    )
    assert resp.status_code == 303, resp.text
    assert resp.headers["location"] == "/deals"

    session.expire_all()
    assert await session.get(Scenario, scenario_id) is None
    assert await session.get(Project, project_id) is None
    assert await session.get(Deal, deal_id) is None


async def test_delete_variant_wrong_org_403(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, _user, _opp, deal_model, _project = await _seed(session)
    scenario_id = deal_model.id

    _other_org, other_user = await seed_org(session)
    await session.commit()
    set_client_auth(client, other_user.id)

    resp = await client.post(
        f"/ui/deals/{scenario_id}/delete-variant", follow_redirects=False
    )
    assert resp.status_code == 403
    session.expire_all()
    assert await session.get(Scenario, scenario_id) is not None
