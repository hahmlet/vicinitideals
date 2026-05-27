"""Root pytest conftest — shared fixtures and seed helpers for all test suites.

All fixtures here are available to every test in the tests/ tree without
explicit import.  Use these instead of writing per-file DB setup.

Database backend
----------------
Tests run against a dedicated Postgres test container (re-modeling-postgres-test
on VM 114, port 5433). Each pytest run creates a fresh database with a unique
suffix, applies the full schema via Base.metadata.create_all, and drops the
database on teardown. This gives true parity with the production Postgres
schema — JSONB, ARRAY, server defaults, and Postgres-specific operators all
behave identically to prod.

Connection URL is read from TEST_DATABASE_URL (env var); defaults to the
canonical LAN-accessible test container.

Fixture scopes
--------------
_test_engine : session-scoped — creates the per-run database, yields one
               AsyncEngine pointed at it, drops the database on teardown.
session      : function-scoped — a fresh async session per test, rolled back
               on teardown so tests are isolated without re-creating tables.
client       : function-scoped — an httpx.AsyncClient backed by the ASGI app
               with the test DB injected; use for UI / API integration tests.

Seed helpers
------------
seed_org()                  → Organization + User tuple
seed_opportunity()          → Opportunity (requires org)
seed_deal_model()           → Deal + DealModel linked to an Opportunity
seed_deal_model_with_financials()  → DealModel + OperationalInputs + IncomeStream + OpEx line
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from collections.abc import AsyncGenerator
from decimal import Decimal
from typing import AsyncIterator
from urllib.parse import urlsplit, urlunsplit

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.api.deps import get_db
from app.api.main import create_app
from app.models import Base  # imports all ORM models, enabling create_all
from app.models.deal import (
    Deal,
    DealModel,
    IncomeStream,
    IncomeStreamType,
    OperatingExpenseLine,
    OperationalInputs,
    ProjectType,
)
from app.models.org import Organization, User
from app.models.project import (
    Opportunity,
    OpportunityCategory,
    OpportunitySource,
    OpportunityStatus,
)

# ---------------------------------------------------------------------------
# Test database URL — connects to dedicated test Postgres container on VM 114.
# Override with TEST_DATABASE_URL for CI or alternate hosts.
# ---------------------------------------------------------------------------
_DEFAULT_TEST_DB_URL = (
    "postgresql+asyncpg://test:test@192.168.1.28:5433/re_modeling_test"
)
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", _DEFAULT_TEST_DB_URL)


# ---------------------------------------------------------------------------
# Windows asyncio event loop policy — decided once per pytest invocation.
#
# asyncpg fails on Windows ProactorEventLoop (connection teardown errors).
# Playwright needs ProactorEventLoop (subprocess transport for the Node driver).
# These can't coexist in one process — policy is global, not per-loop.
#
# Resolution: inspect collected items after collection. If any E2E tests are
# in the run → Proactor (Playwright wins, asyncpg unit tests in the same
# invocation may flake, run them separately). Otherwise → Selector (default
# safe choice for asyncpg-only runs). Hook fires before pytest-asyncio
# creates the session loop, so the policy is in effect when it matters.
# ---------------------------------------------------------------------------

def pytest_collection_finish(session: "pytest.Session") -> None:
    if sys.platform != "win32":
        return
    has_e2e = any("e2e" in str(item.path).replace("\\", "/").split("/tests/")[-1]
                  for item in session.items)
    if has_e2e:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    else:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _swap_database(url: str, new_db: str) -> str:
    """Return ``url`` with its path component replaced by ``/new_db``."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{new_db}", parts.query, parts.fragment))


# ---------------------------------------------------------------------------
# Engine lifecycle — split across two fixtures to dodge asyncpg's loop affinity
#
# asyncpg connections are pinned to the asyncio event loop that opened them.
# pytest-asyncio creates a new event loop per test, so session-scoped async
# connections explode on second use. To stay sane:
#   1. DB CREATE / DROP runs through the sync psycopg2 driver (no loop).
#   2. The AsyncEngine is function-scoped — fresh per test, disposed after.
# Schema is created once, in the session-scoped DB fixture, also via sync.
# ---------------------------------------------------------------------------

def _sync_url(url: str) -> str:
    """Strip the ``+asyncpg`` driver suffix so SQLAlchemy uses psycopg2 sync."""
    return url.replace("+asyncpg", "")


@pytest.fixture(scope="session")
def _test_db_url() -> str:
    """Provision a unique Postgres database for this pytest run.

    Synchronous because the lifecycle (CREATE DATABASE → create_all → DROP
    DATABASE) needs to live outside any asyncio event loop — see the comment
    on the fixture block above.
    """
    run_db = f"re_modeling_test_{uuid.uuid4().hex[:12]}"
    admin_url = _sync_url(TEST_DATABASE_URL)
    run_url = _swap_database(TEST_DATABASE_URL, run_db)

    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{run_db}"'))
    admin_engine.dispose()

    # Schema bootstrap also runs synchronously — no loop, no asyncpg.
    sync_engine = create_engine(_sync_url(run_url))
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()

    try:
        yield run_url
    finally:
        admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with admin_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{run_db}" WITH (FORCE)'))
        admin_engine.dispose()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def _test_engine(_test_db_url: str):
    """Session-scoped AsyncEngine bound to the per-run test database.

    Lives for the entire pytest session because asyncpg connections are
    pinned to the event loop that opened them — and with
    ``asyncio_default_test_loop_scope = "session"`` all tests share one loop,
    so one engine + a connection pool is safe.
    """
    engine = create_async_engine(_test_db_url, poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Session — function-scoped, rolled back after each test
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(loop_scope="session")
async def session(_test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Yield a fresh async session, then truncate all tables for the next test.

    Why truncate-on-teardown instead of transaction rollback: tests in this
    suite frequently call ``session.commit()`` (engine compute helpers commit
    cashflow rows so subsequent queries see them). A SAVEPOINT-based rollback
    fixture fights asyncpg's connection-bound state machine. Truncating the
    schema between tests is a few ms on the test DB and gives full isolation
    regardless of what the test code does with transactions.
    """
    factory = async_sessionmaker(
        bind=_test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with factory() as sess:
        try:
            yield sess
        finally:
            await sess.close()

    # Cleanup: wipe all rows so the next test starts from a clean slate.
    table_names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    if table_names:
        async with _test_engine.begin() as conn:
            await conn.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))


@pytest_asyncio.fixture(loop_scope="session")
async def db_session(session: AsyncSession) -> AsyncGenerator[AsyncSession, None]:
    """Alias for legacy tests that ask for ``db_session`` instead of ``session``."""
    yield session


# ---------------------------------------------------------------------------
# HTTP client — wires FastAPI app to the test DB via dependency override
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(loop_scope="session")
async def client(session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient backed by the ASGI app with the test DB session injected."""
    app = create_app()

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-User-ID": str(uuid.uuid4())},
    ) as c:
        yield c

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def api_key() -> str:
    from app.config import settings
    return settings.vicinitideals_api_key


@pytest.fixture
def auth_headers(api_key: str) -> dict[str, str]:
    return {
        "X-API-Key": api_key,
        "X-User-ID": str(uuid.uuid4()),
    }


def set_client_auth(client: AsyncClient, user_id: "uuid.UUID | str") -> None:
    """Set session cookie AND CSRF token header on *client* for an authenticated user.

    Call this instead of ``client.cookies.set(COOKIE_NAME, ...)`` so that
    the CSRF middleware (which validates X-CSRF-Token on all mutations) is
    satisfied in integration tests.
    """
    from app.api.auth import COOKIE_NAME, create_session_token
    from app.api.csrf import make_csrf_token

    uid = str(user_id)
    client.cookies.set(COOKIE_NAME, create_session_token(uid))
    client.headers["X-CSRF-Token"] = make_csrf_token(uid)


# ---------------------------------------------------------------------------
# Seed helpers — call these in individual tests to populate the DB
# ---------------------------------------------------------------------------

async def seed_org(session: AsyncSession) -> tuple[Organization, User]:
    """Create an Organization and a User; flush but don't commit.

    Returns (org, user).
    """
    org = Organization(
        id=uuid.uuid4(),
        name="Test Org",
        slug=f"test-org-{uuid.uuid4().hex[:8]}",
    )
    user = User(
        id=uuid.uuid4(),
        org_id=org.id,
        name="Test User",
        display_color="#3366FF",
    )
    session.add_all([org, user])
    await session.flush()
    return org, user


async def seed_opportunity(
    session: AsyncSession,
    org: Organization,
    user: User,
    *,
    name: str | None = None,
) -> Opportunity:
    """Create a minimal Opportunity (proposed, active, user-generated)."""
    opp = Opportunity(
        id=uuid.uuid4(),
        org_id=org.id,
        name=name or f"Test Opportunity {uuid.uuid4().hex[:6]}",
        status=OpportunityStatus.active,
        project_category=OpportunityCategory.proposed,
        source=OpportunitySource.user_generated,
        source_url=f"hypothetical://{uuid.uuid4().hex}",
        created_by_user_id=user.id,
    )
    session.add(opp)
    await session.flush()
    return opp


async def seed_deal_model(
    session: AsyncSession,
    opportunity: Opportunity,
    user: User,
    *,
    name: str = "Base Case",
    project_type: ProjectType = ProjectType.value_add,
) -> DealModel:
    """Create a top-level Deal + DealModel linked to an Opportunity.

    Returns the DealModel (financial model record).
    """
    top_deal = Deal(
        id=uuid.uuid4(),
        org_id=opportunity.org_id,
        name=name,
        created_by_user_id=user.id,
    )
    session.add(top_deal)
    await session.flush()
    deal_model = DealModel(
        id=uuid.uuid4(),
        deal_id=top_deal.id,
        created_by_user_id=user.id,
        name=name,
        version=1,
        is_active=True,
        project_type=project_type,
    )
    session.add(deal_model)
    await session.flush()
    return deal_model


async def seed_deal_model_with_financials(
    session: AsyncSession,
    opportunity: Opportunity,
    user: User,
) -> tuple[DealModel, OperationalInputs, IncomeStream, OperatingExpenseLine]:
    """Create a DealModel with OperationalInputs, one IncomeStream, and one OpEx line.

    Returns (deal_model, inputs, income_stream, opex_line).
    """
    from app.models.project import Project

    deal_model = await seed_deal_model(session, opportunity, user)

    # Post-acquisition dev effort that owns the OperationalInputs
    project = Project(
        id=uuid.uuid4(),
        scenario_id=deal_model.id,
        opportunity_id=opportunity.id,
        name="Main Project",
    )
    session.add(project)
    await session.flush()

    inputs = OperationalInputs(
        id=uuid.uuid4(),
        project_id=project.id,
        unit_count_new=8,
        exit_cap_rate_pct=Decimal("5.5"),
        expense_growth_rate_pct_annual=Decimal("3.0"),
        opex_per_unit_annual=Decimal("3600"),
        mgmt_fee_pct=Decimal("8.0"),
        property_tax_annual=Decimal("18000"),
        insurance_annual=Decimal("9600"),
        capex_reserve_per_unit_annual=Decimal("600"),
    )
    income = IncomeStream(
        id=uuid.uuid4(),
        project_id=project.id,
        stream_type=IncomeStreamType.residential_rent,
        label="1BR Units",
        unit_count=8,
        amount_per_unit_monthly=Decimal("1450"),
        stabilized_occupancy_pct=Decimal("95"),
        escalation_rate_pct_annual=Decimal("3.0"),
    )
    opex = OperatingExpenseLine(
        id=uuid.uuid4(),
        project_id=project.id,
        label="Property Management",
        annual_amount=Decimal("8640"),
        escalation_rate_pct_annual=Decimal("3.0"),
    )
    session.add_all([inputs, income, opex])
    await session.flush()
    return deal_model, inputs, income, opex
