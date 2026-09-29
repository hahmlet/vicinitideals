"""Regression: POST /settings/organization/invite echoed the raw email into HTML.

The success fragment interpolated the submitted address without escaping, so
markup in the field was swapped into the page by HTMX. The resend route
already escaped it; the invite route now does too.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import seed_org, set_client_auth

pytestmark = pytest.mark.asyncio


async def test_invite_confirmation_escapes_email(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, admin = await seed_org(session)
    admin.is_org_admin = True
    await session.commit()
    set_client_auth(client, admin.id)

    payload = "<img src=x onerror=alert(1)>@example.com"
    with patch("app.emails.send_invite_email", new=AsyncMock()), \
         patch("app.api.rate_limit.check_rate_limit", new=AsyncMock(return_value=True)):
        resp = await client.post(
            "/settings/organization/invite",
            data={"invite_email": payload},
            headers={"hx-request": "true"},
        )

    assert resp.status_code == 200
    assert "<img" not in resp.text
    assert "&lt;img" in resp.text
