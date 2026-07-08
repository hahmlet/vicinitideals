"""Contract-suite fixtures.

Historically re-exported `client` / `auth_headers` / `test_session_factory`
from tests/api/test_routers.py's inline SQLite harness. That harness was
migrated to the shared Postgres conftest (tests/conftest.py), which already
provides `client` and `auth_headers` to every suite — only
`test_session_factory` needs a local definition here, built on the shared
per-run test engine so contract tests can seed data in their own committed
session before driving the API.
"""

from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest_asyncio.fixture(loop_scope="session")
async def test_session_factory(_test_engine, _rebind_app_db, session):
    """Session factory bound to the per-run Postgres test DB.

    Depends on `session` so the shared truncate-on-teardown cleanup runs
    after each contract test, wiping rows committed through this factory.
    """
    yield async_sessionmaker(
        bind=_test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def _ui_session_auth(client, session):
    """Give the contract client a real signed session cookie.

    Since session auth landed (cfdd992, hardened in 6cf361e), non-/api paths
    like /openapi.json and /projects sit behind the login-redirect middleware:
    API-key headers alone get a 303 to /login before the API-key middleware
    can produce its contract envelope. Seed an active user and set the
    session cookie + CSRF header so requests reach the contract surfaces.
    """
    from tests.conftest import seed_org, set_client_auth

    _org, user = await seed_org(session)
    await session.commit()
    set_client_auth(client, user.id)
