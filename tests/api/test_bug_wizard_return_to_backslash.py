"""Bug: open redirect through the opportunity wizard's ``return_to``.

POST /ui/opportunities/wizard/complete redirects to ``return_to`` after
``_safe_return_path`` checks it is a same-origin path. The check refused
``//evil`` but not ``/\\evil``: browsers treat a backslash as a slash, so
``Location: /\\evil.example`` sends the user off-site. Any backslash now
falls back to the opportunity page.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.ui_deals_pipeline import _safe_return_path
from tests.conftest import seed_org, set_client_auth


@pytest.mark.parametrize("raw", ["/\\evil.example", "/\\/evil.example", "/ok\\..\\x"])
def test_safe_return_path_refuses_backslash(raw: str) -> None:
    assert _safe_return_path(raw) == ""


@pytest.mark.asyncio
async def test_wizard_complete_backslash_return_to_stays_on_site(
    client: AsyncClient, session: AsyncSession
):
    _org, user = await seed_org(session)
    await session.commit()
    set_client_auth(client, user.id)
    opp_id = str(uuid.uuid4())

    resp = await client.post(
        "/ui/opportunities/wizard/complete",
        data={"opp_id": opp_id, "return_to": "/\\evil.example/phish"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/opportunities/{opp_id}"
