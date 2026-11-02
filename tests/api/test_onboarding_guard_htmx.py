"""Onboarding guard behavior for signed-in HTMX requests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flats import FlatsRuleSignature
from app.models.org import MembershipStatus, User
from tests.conftest import seed_org, set_client_auth

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_HTMX = {"HX-Request": "true"}
_SIGN_FORM = {
    "layer_id": "or/clackamas/wilsonville",
    "zone": "R",
    "field": "setback_side_ft",
    "when": "",
    "verdict": "verified",
}


async def _pending_member(session: AsyncSession) -> User:
    _, user = await seed_org(session)
    user.membership_status = MembershipStatus.PENDING
    await session.commit()
    return user


async def test_pending_member_htmx_sign_is_refused_without_writing(
    client: AsyncClient, session: AsyncSession
) -> None:
    pending = await _pending_member(session)
    set_client_auth(client, pending.id)

    response = await client.post("/ui/flats/sign", data=_SIGN_FORM, headers=_HTMX)

    assert response.status_code == 403
    assert response.headers["HX-Redirect"] == "/pending-approval"
    signatures = (await session.execute(select(FlatsRuleSignature))).scalars().all()
    assert signatures == []


async def test_pending_member_htmx_flats_partial_is_refused(
    client: AsyncClient, session: AsyncSession
) -> None:
    pending = await _pending_member(session)
    set_client_auth(client, pending.id)

    response = await client.get(
        "/ui/flats/quote",
        params={"ref": "or/nowhere/no-such-city/99.txt#L1"},
        headers=_HTMX,
    )

    assert response.status_code == 403
    assert response.headers["HX-Redirect"] == "/pending-approval"


async def test_active_member_htmx_post_reaches_flats_handler(
    client: AsyncClient, session: AsyncSession
) -> None:
    _, active = await seed_org(session)
    await session.commit()
    set_client_auth(client, active.id)

    response = await client.post("/ui/flats/sign", data=_SIGN_FORM, headers=_HTMX)

    assert response.status_code == 200
    signatures = (await session.execute(select(FlatsRuleSignature))).scalars().all()
    assert len(signatures) == 1


async def test_user_without_org_can_use_onboarding_over_htmx(
    client: AsyncClient, session: AsyncSession
) -> None:
    _, user = await seed_org(session)
    user.org_id = None
    await session.commit()
    set_client_auth(client, user.id)

    response = await client.post(
        "/ui/onboarding/step",
        data={"_step": "1", "org_name": "New Org", "org_slug": "new-org"},
        headers=_HTMX,
    )

    assert response.status_code == 200
    assert "new-org" in response.text


async def test_pending_member_non_htmx_get_keeps_redirect(
    client: AsyncClient, session: AsyncSession
) -> None:
    pending = await _pending_member(session)
    set_client_auth(client, pending.id)

    response = await client.get("/flats", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/pending-approval"
