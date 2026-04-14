"""Root pytest conftest — shared fixtures and seed helpers for all test suites.

All fixtures here are available to every test in the tests/ tree without
explicit import.  Use these instead of writing per-file DB setup.

Fixture scopes
--------------
engine   : session-scoped — one in-memory SQLite engine for the entire run.
           Tables are created once; individual tests get isolated sessions.
session  : function-scoped — a fresh async session per test, rolled back on
           teardown so tests are isolated without re-creating tables.
client   : function-scoped — an httpx.AsyncClient backed by the ASGI app with
           the test DB injected; use for UI / API integration tests.

Seed helpers
------------
seed_org()                  → Organization + User tuple
seed_opportunity()          → Opportunity (requires org)
seed_deal_model()                  → Deal + DealOpportunity + DealModel linked to an Opportunity
seed_deal_model_with_financials()  → DealModel + OperationalInputs + IncomeStream + OpEx line
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from decimal import Decimal
from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.api.main import create_app
from app.models import Base  # imports all ORM models, enabling create_all
from app.models.deal import (
    Deal,
    DealModel,
    DealOpportunity,
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
# Engine — session-scoped (one per test run, tables created once)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop_policy():
    """Use default asyncio policy — required by pytest-asyncio in session scope."""
    import asyncio
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(scope="session")
async def _test_engine():
    """In-memory SQLite engine shared across the whole test session.

    Uses StaticPool so all connections share the same in-memory database.
    Base.metadata.create_all picks up every ORM model imported in models/__init__.py —
    no manual table list needed.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


# ---------------------------------------------------------------------------
# Session — function-scoped, rolled back after each test
# ---------------------------------------------------------------------------

@pytest.fixture
async def session(_test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Yield a fresh async session; rolls back after each test for isolation."""
    factory = async_sessionmaker(
        bind=_test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with factory() as sess:
        yield sess
        await sess.rollback()


# ---------------------------------------------------------------------------
# HTTP client — wires FastAPI app to the test DB via dependency override
# ---------------------------------------------------------------------------

@pytest.fixture
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
    project_type: ProjectType = ProjectType.acquisition_major_reno,
) -> DealModel:
    """Create a top-level Deal + DealOpportunity + DealModel linked to an Opportunity.

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
    session.add(DealOpportunity(deal_id=top_deal.id, opportunity_id=opportunity.id))
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
        deal_type=deal_model.project_type.value,
    )
    session.add(project)
    await session.flush()

    inputs = OperationalInputs(
        id=uuid.uuid4(),
        project_id=project.id,
        unit_count_new=8,
        hold_period_years=5,
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
