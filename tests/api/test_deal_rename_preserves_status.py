"""Regression tests for /ui/deals/{deal_id}/update.

The rename form historically posted a hidden `status` field sourced from
`Opportunity.status` (the scraped-listing status), not `opp_status` (the
pipeline stage). That silently corrupted the pipeline stage on every
rename, hiding deals from filtered lists. These tests pin down the
contract:

- Renaming with no `status` field must leave `opp_status` untouched.
- An explicit valid `status` (pipeline enum) still updates `opp_status`.
- An invalid `status` (anything not in the pipeline enum) is ignored.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import COOKIE_NAME, create_session_token
from app.api.csrf import make_csrf_token
from app.models.deal import Deal, ProjectType
from app.models.opportunity import Opportunity
from app.models.project import Project

from tests.conftest import seed_deal_model, seed_opportunity, seed_org


async def _scaffold(session: AsyncSession, opp_status: str = "active"):
    """Build org/user/opp/deal/project chain with a known opp_status."""
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    opp.opp_status = opp_status
    # Mimic the production data shape that triggered the original bug:
    # opp.status (scraped-listing status) is NULL.
    opp.status = None
    await session.flush()

    deal_model = await seed_deal_model(
        session, opp, user, name="Original Name", project_type=ProjectType.acquisition
    )
    project = Project(
        id=uuid.uuid4(),
        scenario_id=deal_model.id,
        opportunity_id=opp.id,
        name="Main Project",
    )
    session.add(project)
    await session.flush()

    # The route loads Deal (top-level), not DealModel — fetch its id.
    top_deal_id = deal_model.deal_id
    await session.commit()
    return user, opp, top_deal_id


async def _post_update(
    client: AsyncClient, user_id: uuid.UUID, deal_id: uuid.UUID, data: dict
):
    cookies = {COOKIE_NAME: create_session_token(user_id)}
    headers = {"X-CSRF-Token": make_csrf_token(str(user_id))}
    return await client.post(
        f"/ui/deals/{deal_id}/update",
        cookies=cookies,
        headers=headers,
        data=data,
        follow_redirects=False,
    )


@pytest.mark.asyncio
async def test_rename_only_preserves_opp_status(
    client: AsyncClient, session: AsyncSession
) -> None:
    user, opp, deal_id = await _scaffold(session, opp_status="active")
    opp_id = opp.id

    resp = await _post_update(client, user.id, deal_id, {"name": "New Name"})

    assert resp.status_code in (200, 303)
    # Re-fetch from DB, not the cached instance.
    refreshed_opp = (
        await session.execute(select(Opportunity).where(Opportunity.id == opp_id))
    ).scalar_one()
    refreshed_deal = (
        await session.execute(select(Deal).where(Deal.id == deal_id))
    ).scalar_one()

    assert refreshed_deal.name == "New Name"
    # The original bug wrote the literal string "None" here — this assertion
    # would have caught that immediately.
    assert refreshed_opp.opp_status == "active"


@pytest.mark.asyncio
async def test_rename_with_invalid_status_field_ignored(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Explicit but invalid `status` (e.g. literal string 'None') is ignored."""
    user, opp, deal_id = await _scaffold(session, opp_status="hypothetical")
    opp_id = opp.id

    resp = await _post_update(
        client, user.id, deal_id, {"name": "Renamed", "status": "None"}
    )

    assert resp.status_code in (200, 303)
    refreshed_opp = (
        await session.execute(select(Opportunity).where(Opportunity.id == opp_id))
    ).scalar_one()
    assert refreshed_opp.opp_status == "hypothetical"


@pytest.mark.asyncio
async def test_rename_with_valid_status_field_updates(
    client: AsyncClient, session: AsyncSession
) -> None:
    """A valid pipeline status value still flows through (defense-in-depth)."""
    user, opp, deal_id = await _scaffold(session, opp_status="hypothetical")
    opp_id = opp.id

    resp = await _post_update(
        client, user.id, deal_id, {"name": "Renamed", "status": "active"}
    )

    assert resp.status_code in (200, 303)
    refreshed_opp = (
        await session.execute(select(Opportunity).where(Opportunity.id == opp_id))
    ).scalar_one()
    assert refreshed_opp.opp_status == "active"
