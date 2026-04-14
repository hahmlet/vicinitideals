"""Tests for the Deal → DealOpportunity → Scenario → Project FK chain."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from vicinitideals.models.deal import Deal, DealOpportunity, ProjectType, Scenario
from vicinitideals.models.project import Project
from tests.conftest import seed_deal_model, seed_deal_model_with_financials, seed_opportunity, seed_org


@pytest.mark.asyncio
async def test_deal_hierarchy_basic_creation_and_navigation(session):
    org, user = await seed_org(session)
    opportunity = await seed_opportunity(session, org, user)
    scenario = await seed_deal_model(session, opportunity, user)

    reloaded = (
        await session.execute(
            select(Scenario)
            .where(Scenario.id == scenario.id)
            .options(selectinload(Scenario.deal), selectinload(Scenario.projects))
        )
    ).scalar_one()

    assert reloaded.deal is not None
    assert reloaded.deal.name == reloaded.name

    deal = (
        await session.execute(
            select(Deal)
            .where(Deal.id == reloaded.deal.id)
            .options(selectinload(Deal.scenarios))
        )
    ).scalar_one()

    assert deal.scenarios[0].id == scenario.id


@pytest.mark.asyncio
async def test_deal_opportunity_unique_constraint(session):
    org, user = await seed_org(session)
    opportunity = await seed_opportunity(session, org, user)

    top_deal = Deal(
        id=uuid.uuid4(),
        org_id=org.id,
        name="Constraint Test Deal",
        created_by_user_id=user.id,
    )
    session.add(top_deal)
    await session.flush()

    session.add(DealOpportunity(deal_id=top_deal.id, opportunity_id=opportunity.id))
    await session.flush()

    with pytest.raises(Exception):
        session.add(DealOpportunity(deal_id=top_deal.id, opportunity_id=opportunity.id))
        await session.flush()


@pytest.mark.asyncio
async def test_deal_cascade_delete_removes_scenario_and_link(session):
    org, user = await seed_org(session)
    opportunity = await seed_opportunity(session, org, user)
    scenario = await seed_deal_model(session, opportunity, user)

    deal_id = scenario.deal_id
    scenario_id = scenario.id

    top_deal = (await session.execute(select(Deal).where(Deal.id == deal_id))).scalar_one()

    await session.delete(top_deal)
    await session.flush()

    assert (
        await session.execute(select(Scenario).where(Scenario.id == scenario_id))
    ).scalar_one_or_none() is None

    assert (
        await session.execute(
            select(DealOpportunity).where(DealOpportunity.deal_id == deal_id)
        )
    ).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_deal_supports_multiple_scenarios(session):
    org, user = await seed_org(session)
    opportunity = await seed_opportunity(session, org, user)

    top_deal = Deal(
        id=uuid.uuid4(),
        org_id=org.id,
        name="Multi-Scenario Deal",
        created_by_user_id=user.id,
    )
    session.add(top_deal)
    await session.flush()

    session.add(DealOpportunity(deal_id=top_deal.id, opportunity_id=opportunity.id))

    for name in ("Base Case", "Conservative"):
        session.add(
            Scenario(
                id=uuid.uuid4(),
                deal_id=top_deal.id,
                created_by_user_id=user.id,
                name=name,
                version=1,
                is_active=True,
                project_type=ProjectType.acquisition_minor_reno,
            )
        )
    await session.flush()

    deal = (
        await session.execute(
            select(Deal).where(Deal.id == top_deal.id).options(selectinload(Deal.scenarios))
        )
    ).scalar_one()

    assert len(deal.scenarios) == 2
    assert {s.name for s in deal.scenarios} == {"Base Case", "Conservative"}


@pytest.mark.asyncio
async def test_seed_deal_model_with_financials_creates_full_chain(session):
    org, user = await seed_org(session)
    opportunity = await seed_opportunity(session, org, user)
    deal_model, inputs, income, opex = await seed_deal_model_with_financials(session, opportunity, user)

    assert deal_model.id is not None
    assert inputs.project_id is not None
    assert income.unit_count == 8
    assert opex.label == "Property Management"

    project = (
        await session.execute(select(Project).where(Project.id == inputs.project_id))
    ).scalar_one()
    assert project.scenario_id == deal_model.id
