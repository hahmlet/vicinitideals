"""Cross-org isolation tests — confirm list and detail endpoints do not
leak deals, opportunities, or portfolios across organizations when
settings.org_isolation_enabled is True (the production default).
"""
from __future__ import annotations

import sys
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import COOKIE_NAME, create_session_token
from app.models.opportunity import Opportunity, OpportunityCategory, OpportunitySource, OpportunityStatus
from app.models.org import Organization, User
from app.models.portfolio import Portfolio
from app.models.project import Project

from tests.conftest import seed_deal_model, seed_opportunity, seed_org

# Some tests render templates that use Linux-only strftime tokens (``%-d``)
# and trigger Jinja relationship lazy-loads outside the greenlet context on
# Windows. Skip those rendering-heavy assertions when running locally on
# Windows; they still execute under CI Linux and in deployed production.
_SKIP_WIN = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Template lazy-load / %-d strftime is Linux-only; runs in CI.",
)

pytestmark = pytest.mark.asyncio


async def _seed_org_with_active_deal(
    session: AsyncSession, label: str
) -> tuple[Organization, User, Opportunity, "object"]:
    org, user = await seed_org(session)
    org.name = f"Org {label}"
    user.name = f"User {label}"
    opp = await seed_opportunity(session, org, user, name=f"Opp {label}")
    deal_model = await seed_deal_model(session, opp, user, name=f"Deal {label}")
    project = Project(
        id=uuid.uuid4(),
        scenario_id=deal_model.id,
        opportunity_id=opp.id,
        name=f"Project {label}",
    )
    session.add(project)
    await session.flush()
    await session.commit()
    return org, user, opp, deal_model


def _cookies_for(user: User) -> dict[str, str]:
    return {COOKIE_NAME: create_session_token(user.id)}


async def test_helper_scopes_query_when_flag_on(session: AsyncSession) -> None:
    """Direct unit-style check on _apply_org_scope: returns only rows
    matching user.org_id when isolation is enabled, and an empty result
    when the user has no org."""
    from sqlalchemy import select
    from app.api.routers.ui import _apply_org_scope
    from app.config import settings as _settings
    from app.models.deal import Deal

    assert _settings.org_isolation_enabled is True, "test assumes prod default"

    org_a, user_a, _opp_a, _deal_a = await _seed_org_with_active_deal(session, "Helper-A")
    org_b, _user_b, _opp_b, _deal_b = await _seed_org_with_active_deal(session, "Helper-B")

    stmt = _apply_org_scope(select(Deal), user_a, Deal)
    rows = (await session.execute(stmt)).scalars().all()
    org_ids = {r.org_id for r in rows}
    assert org_ids == {org_a.id}

    anon_stmt = _apply_org_scope(select(Deal), None, Deal)
    anon_rows = (await session.execute(anon_stmt)).scalars().all()
    assert anon_rows == []


@_SKIP_WIN
async def test_deals_list_only_shows_own_org(client: AsyncClient, session: AsyncSession) -> None:
    org_a, user_a, _opp_a, _deal_a = await _seed_org_with_active_deal(session, "A")
    org_b, user_b, _opp_b, _deal_b = await _seed_org_with_active_deal(session, "B")

    resp = await client.get("/deals", cookies=_cookies_for(user_a))
    assert resp.status_code == 200
    body = resp.text
    assert "Deal A" in body
    assert "Deal B" not in body

    resp = await client.get("/deals", cookies=_cookies_for(user_b))
    assert resp.status_code == 200
    body = resp.text
    assert "Deal B" in body
    assert "Deal A" not in body


async def test_active_opportunities_tab_only_shows_own_org(
    client: AsyncClient, session: AsyncSession
) -> None:
    org_a, user_a, _opp_a, _deal_a = await _seed_org_with_active_deal(session, "A")
    org_b, user_b, _opp_b, _deal_b = await _seed_org_with_active_deal(session, "B")

    resp = await client.get("/ui/opportunities/rows/deals", cookies=_cookies_for(user_a))
    assert resp.status_code == 200
    body = resp.text
    assert "Opp A" in body
    assert "Opp B" not in body


async def test_other_org_deal_detail_404(
    client: AsyncClient, session: AsyncSession
) -> None:
    org_a, user_a, _opp_a, _deal_a = await _seed_org_with_active_deal(session, "A")
    org_b, _user_b, _opp_b, deal_b = await _seed_org_with_active_deal(session, "B")

    from app.models.deal import Deal
    from sqlalchemy import select

    parent_deal_id = (
        await session.execute(select(Deal.id).where(Deal.org_id == org_b.id))
    ).scalar_one()

    resp = await client.get(f"/deals/{parent_deal_id}", cookies=_cookies_for(user_a))
    assert resp.status_code == 404


async def test_other_org_opportunity_detail_404(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org_a, user_a, _opp_a, _deal_a = await _seed_org_with_active_deal(session, "A")
    _org_b, _user_b, opp_b, _deal_b = await _seed_org_with_active_deal(session, "B")

    resp = await client.get(f"/opportunities/{opp_b.id}", cookies=_cookies_for(user_a))
    assert resp.status_code == 404


@_SKIP_WIN
async def test_unpromoted_opportunity_remains_visible(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Opportunities with org_id=None are the shared scraping pool — must
    stay visible across orgs even with isolation enabled."""
    _org_a, user_a, _opp_a, _deal_a = await _seed_org_with_active_deal(session, "A")

    unpromoted = Opportunity(
        id=uuid.uuid4(),
        org_id=None,
        name="Unpromoted Listing",
        status=OpportunityStatus.active,
        project_category=OpportunityCategory.proposed,
        source=OpportunitySource.loopnet,
        source_url=f"hypothetical://{uuid.uuid4().hex}",
    )
    session.add(unpromoted)
    await session.commit()

    resp = await client.get(
        f"/opportunities/{unpromoted.id}", cookies=_cookies_for(user_a)
    )
    assert resp.status_code == 200


@_SKIP_WIN
async def test_portfolios_list_only_shows_own_org(
    client: AsyncClient, session: AsyncSession
) -> None:
    org_a, user_a, _opp_a, _deal_a = await _seed_org_with_active_deal(session, "A")
    org_b, _user_b, _opp_b, _deal_b = await _seed_org_with_active_deal(session, "B")

    portfolio_a = Portfolio(id=uuid.uuid4(), org_id=org_a.id, name="Portfolio A")
    portfolio_b = Portfolio(id=uuid.uuid4(), org_id=org_b.id, name="Portfolio B")
    session.add_all([portfolio_a, portfolio_b])
    await session.commit()

    resp = await client.get("/portfolios", cookies=_cookies_for(user_a))
    assert resp.status_code == 200
    body = resp.text
    assert "Portfolio A" in body
    assert "Portfolio B" not in body


async def test_other_org_dev_fee_explainer_404(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Dev Fee explainer modal must not leak UseLine data across orgs.

    Org gate returns 404 before any DB query for UseLines or templates,
    so this test is safe on Windows.
    """
    _org_a, user_a, _opp_a, _deal_a = await _seed_org_with_active_deal(session, "A")
    _org_b, _user_b, _opp_b, deal_b = await _seed_org_with_active_deal(session, "B")

    resp = await client.get(
        f"/ui/models/{deal_b.id}/dev-fee/explainer",
        cookies=_cookies_for(user_a),
    )
    assert resp.status_code == 404


async def test_unauth_dev_fee_explainer_404(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Unauthenticated request to Dev Fee explainer must 404."""
    _org_a, _user_a, _opp_a, deal_a = await _seed_org_with_active_deal(session, "A")

    resp = await client.get(f"/ui/models/{deal_a.id}/dev-fee/explainer")
    assert resp.status_code == 404
