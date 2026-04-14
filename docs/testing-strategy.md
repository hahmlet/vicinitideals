# Testing Strategy — re-modeling

## What We Have Today

- **18 test files**, ~100+ tests, ~7,400 lines of test code
- Async tests via `pytest-asyncio` (auto mode)
- In-memory SQLite for DB tests — fast, isolated, no external dependencies
- `httpx.AsyncClient` + `ASGITransport` for API integration tests
- Schema round-trip tests (Pydantic serialize → deserialize → compare)
- Contract tests (OpenAPI spec, response envelope format)
- Engine tests (cashflow, waterfall computation)
- Scraper tests (mocked HTTP for external services)

**What's missing:**
- No CI/CD pipeline (no automated test runs on push)
- No coverage tracking
- No root `conftest.py` — fixtures duplicated across files
- Manual table registration in test DB setup (fragile, breaks on new models)
- Engine tests (`test_cashflow.py`) hit the real production DB and `pytest.skip()` on failure
- No clear unit/integration separation

---

## The Two-Layer Model

Every test in this project should be clearly one of two things:

### Unit Tests

Test a single function or class **in isolation**. No database, no HTTP, no file I/O. Inputs go in, outputs come out. If it needs a database row, you build a Pydantic model or a plain dict — not an ORM object from a real session.

**What to unit test in this project:**
- Engine functions: `compute_cash_flows()`, `_build_phase_plan()`, `_compute_period()`
- Waterfall distribution logic
- Helper/utility functions (currency formatting, address normalization)
- Pydantic schema validation (round-trips, edge cases, defaults)
- Milestone sequencing and trigger chain logic

**Characteristics:**
- Fast: entire unit suite runs in <5 seconds
- No fixtures needed beyond simple data builders
- Deterministic: same inputs → same outputs every time
- An AI agent can run these, read the failure, and fix the code in one shot

### Integration Tests

Test that components work together — API endpoint → router → DB → response. These use the in-memory SQLite DB, the real FastAPI app, real dependency injection.

**What to integration test:**
- Every API endpoint (POST create → GET read → PATCH update → DELETE)
- HTMX UI routes (GET page renders, POST form submits redirect correctly)
- Compute pipeline (seed model → compute → verify outputs written to DB)
- Cascade behaviors (delete opportunity → deals cascade)

**Characteristics:**
- Slower: each test creates a fresh DB schema
- Require fixtures (session factory, client, seed data)
- Test the contract between components, not internal logic

---

## What to Change

### 1. Create a Root conftest.py

One file, all shared fixtures. Every test file imports from here instead of defining its own session factory.

```python
# tests/conftest.py

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from vicinitideals.api.deps import get_db
from vicinitideals.api.main import create_app
from vicinitideals.config import settings
from vicinitideals.models.base import Base
from vicinitideals.models.org import Organization, User


@pytest.fixture
async def db(tmp_path) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """In-memory SQLite session factory. Creates ALL tables automatically."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(
        bind=engine, class_=AsyncSession,
        expire_on_commit=False, autoflush=False,
    )

    # Create every table registered on Base — no manual list to maintain.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed the minimum required data (org + user)
    async with factory() as session:
        org = Organization(id=uuid4(), name="Test Org", slug="test-org")
        user = User(id=uuid4(), org_id=org.id, name="Test User", display_color="#333")
        session.add_all([org, user])
        await session.commit()

    yield factory
    await engine.dispose()


@pytest.fixture
async def session(db) -> AsyncGenerator[AsyncSession, None]:
    """Convenience: yields a single session from the factory."""
    async with db() as s:
        yield s


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {
        "X-API-Key": settings.vicinitideals_api_key,
        "X-User-ID": str(uuid4()),
    }


@pytest.fixture
async def client(db) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient wired to the real FastAPI app with test DB injected."""
    app = create_app()

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with db() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as c:
        yield c
```

**Key change:** `Base.metadata.create_all` instead of manually listing 25 tables. When you add a new model, tests pick it up automatically.

### 2. Add Pytest Markers

Register markers so you can run subsets:

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = [
    "unit: Pure logic tests, no DB or network",
    "integration: Tests that need the database or HTTP client",
    "slow: Tests that take >5s (compute, scenario sweeps)",
]
```

Then run selectively:
```bash
pytest -m unit           # <5 seconds, all logic tests
pytest -m integration    # DB-backed tests
pytest -m "not slow"     # skip compute-heavy tests during iteration
```

### 3. Add Coverage

```toml
# pyproject.toml
[project.optional-dependencies]
dev = [
    # ... existing ...
    "pytest-cov>=4.1",
]

[tool.coverage.run]
source = ["vicinitideals"]
omit = ["vicinitideals/tasks/*", "vicinitideals/scrapers/*"]

[tool.coverage.report]
fail_under = 60
show_missing = true
skip_empty = true
```

Run: `pytest --cov --cov-report=term-missing`

Start at 60% floor. Raise it as coverage improves. Don't aim for 100% — scraper and Celery task code is better tested via integration than unit coverage.

### 4. Fix Engine Tests

`test_cashflow.py` currently hits the production DB via `AsyncSessionLocal` and skips if the DB isn't available. This is fragile and untestable by an AI agent. Refactor to use the shared `db` fixture:

```python
# tests/engines/test_cashflow.py

import pytest
from vicinitideals.engines.cashflow import compute_cash_flows

@pytest.mark.integration
async def test_compute_generates_rows(db, session):
    model_id = await _seed_minimal_deal(session)
    await session.commit()

    summary = await compute_cash_flows(deal_model_id=model_id, session=session)

    assert summary["cash_flow_count"] > 0
    assert summary["line_item_count"] >= summary["cash_flow_count"]
```

No `pytest.skip()`, no production DB dependency. Runs in CI, runs locally, an AI agent can diagnose failures.

### 5. Organize Test Directory

```
tests/
├── conftest.py              ← shared fixtures (db, client, auth_headers, seed helpers)
├── unit/
│   ├── test_cashflow_logic.py    ← pure functions from engines/cashflow.py
│   ├── test_waterfall_logic.py   ← distribution math
│   ├── test_milestone_chain.py   ← trigger sequencing
│   ├── test_schema_roundtrip.py  ← Pydantic validation
│   └── test_formatters.py        ← currency, pct, date formatters
├── integration/
│   ├── test_api_deals.py         ← CRUD endpoints for deals/opportunities
│   ├── test_api_models.py        ← model builder endpoints
│   ├── test_api_capital.py       ← capital stack + waterfall endpoints
│   ├── test_api_compute.py       ← compute pipeline end-to-end
│   ├── test_ui_routes.py         ← HTMX page renders + form submissions
│   └── test_cascades.py          ← FK cascade and data integrity
├── contract/
│   ├── test_router_envelopes.py  ← response format contracts
│   └── test_compute_contracts.py ← output schema contracts
└── scrapers/                     ← existing scraper tests (keep as-is)
```

The current 3,041-line `test_routers.py` should be split by domain. Each file tests one router. An AI agent working on the capital stack module only needs to run `pytest tests/integration/test_api_capital.py`.

---

## Seed Helper Pattern

Replace 100-line seed functions with composable builders:

```python
# tests/conftest.py (continued)

from vicinitideals.models.deal import Deal, OperationalInputs, IncomeStream, UseLine, OperatingExpenseLine
from vicinitideals.models.project import Opportunity, Project
from vicinitideals.models.capital import CapitalModule


async def seed_opportunity(session, **overrides) -> Opportunity:
    """Create an Opportunity with sensible defaults. Override any field."""
    from vicinitideals.models.org import Organization
    org = (await session.execute(select(Organization).limit(1))).scalar_one()
    defaults = dict(
        org_id=org.id,
        name="Test Opportunity",
        status="active",
    )
    defaults.update(overrides)
    opp = Opportunity(**defaults)
    session.add(opp)
    await session.flush()
    return opp


async def seed_deal(session, *, opportunity=None, **overrides) -> Deal:
    """Create Deal + Opportunity + default Project + OperationalInputs."""
    if opportunity is None:
        opportunity = await seed_opportunity(session)

    defaults = dict(
        opportunity_id=opportunity.id,
        name="Base Case",
        project_type="acquisition_major_reno",
        version=1,
        is_active=True,
    )
    defaults.update(overrides)
    deal = Deal(**defaults)
    session.add(deal)
    await session.flush()

    project = Project(
        deal_id=deal.id,
        opportunity_id=opportunity.id,
        name="Default Project",
        deal_type=deal.project_type,
    )
    session.add(project)
    await session.flush()

    inputs = OperationalInputs(
        project_id=project.id,
        unit_count_new=12,
        hold_period_years=5,
        exit_cap_rate_pct=Decimal("5.5"),
        expense_growth_rate_pct_annual=Decimal("3.0"),
    )
    session.add(inputs)
    await session.flush()

    return deal


async def seed_deal_with_financials(session) -> Deal:
    """Full deal with income streams, use lines, opex, and a capital source."""
    deal = await seed_deal(session)
    project = deal.projects[0] if deal.projects else (
        await session.execute(
            select(Project).where(Project.deal_id == deal.id)
        )
    ).scalar_one()

    session.add(IncomeStream(
        project_id=project.id,
        stream_type="residential_rent",
        label="Market Rent",
        unit_count=12,
        amount_per_unit_monthly=Decimal("1650"),
        stabilized_occupancy_pct=Decimal("95"),
        escalation_rate_pct_annual=Decimal("3.0"),
    ))
    session.add(UseLine(
        project_id=project.id,
        label="Purchase Price",
        phase="acquisition",
        amount=Decimal("1200000"),
    ))
    session.add(OperatingExpenseLine(
        project_id=project.id,
        label="Insurance",
        annual_amount=Decimal("9600"),
        escalation_rate_pct_annual=Decimal("3.0"),
    ))
    session.add(CapitalModule(
        deal_id=deal.id,
        label="Conventional Loan",
        funder_type="senior_debt",
        stack_position=1,
        source={"amount": "900000", "interest_rate_pct": 6.5},
        carry={"carry_type": "pi", "payment_frequency": "monthly"},
        exit_terms={"exit_type": "full_payoff", "trigger": "sale"},
    ))
    await session.flush()
    return deal
```

Usage in tests:
```python
async def test_compute_produces_noi(db):
    async with db() as session:
        deal = await seed_deal_with_financials(session)
        await session.commit()

    async with db() as session:
        summary = await compute_cash_flows(deal.id, session)
        assert summary["cash_flow_count"] > 0
```

Composable, readable, and an AI agent can quickly understand what data exists.

---

## Concrete Example 1: Unit Test for Waterfall Distribution

This tests pure math — no DB needed.

```python
# tests/unit/test_waterfall_logic.py

from decimal import Decimal
import pytest
from vicinitideals.engines.waterfall import allocate_tier


@pytest.mark.unit
class TestAllocateTier:
    """Verify waterfall allocation math for a single tier."""

    def test_debt_service_takes_full_amount_when_sufficient(self):
        allocated, remaining = allocate_tier(
            available=Decimal("10000"),
            tier_type="debt_service",
            owed=Decimal("3000"),
        )
        assert allocated == Decimal("3000")
        assert remaining == Decimal("7000")

    def test_debt_service_takes_partial_when_insufficient(self):
        allocated, remaining = allocate_tier(
            available=Decimal("1000"),
            tier_type="debt_service",
            owed=Decimal("3000"),
        )
        assert allocated == Decimal("1000")
        assert remaining == Decimal("0")

    def test_pref_return_caps_at_hurdle(self):
        allocated, remaining = allocate_tier(
            available=Decimal("50000"),
            tier_type="pref_return",
            owed=Decimal("8000"),  # 8% pref on 100k equity
        )
        assert allocated == Decimal("8000")
        assert remaining == Decimal("42000")

    def test_residual_split_70_30(self):
        allocated_lp, allocated_gp, remaining = allocate_residual(
            available=Decimal("100000"),
            lp_pct=Decimal("70"),
            gp_pct=Decimal("30"),
        )
        assert allocated_lp == Decimal("70000")
        assert allocated_gp == Decimal("30000")
        assert remaining == Decimal("0")

    def test_zero_available_returns_zero(self):
        allocated, remaining = allocate_tier(
            available=Decimal("0"),
            tier_type="debt_service",
            owed=Decimal("5000"),
        )
        assert allocated == Decimal("0")
        assert remaining == Decimal("0")
```

**Why this pattern works for AI agents:** Each test has a descriptive name, one assertion focus, obvious inputs and expected outputs. When `test_pref_return_caps_at_hurdle` fails, the agent knows exactly what broke and where to look.

---

## Concrete Example 2: Integration Test for Deal Detail Page

This tests the new `/deals/{id}` route end-to-end.

```python
# tests/integration/test_ui_deals.py

import pytest
from httpx import AsyncClient

from tests.conftest import seed_deal, seed_opportunity


@pytest.mark.integration
class TestDealDetailPage:

    async def test_deal_detail_renders_overview(self, client: AsyncClient, db):
        async with db() as session:
            deal = await seed_deal(session)
            opp_id = deal.opportunity_id
            await session.commit()

        resp = await client.get(f"/deals/{opp_id}")
        assert resp.status_code == 200
        html = resp.text
        # Page renders with deal name
        assert "Test Opportunity" in html
        # Overview tab is active by default
        assert 'class="detail-tab active"' in html

    async def test_deal_detail_models_tab(self, client: AsyncClient, db):
        async with db() as session:
            deal = await seed_deal(session)
            opp_id = deal.opportunity_id
            await session.commit()

        resp = await client.get(f"/deals/{opp_id}?tab=models")
        assert resp.status_code == 200
        assert "Base Case" in resp.text
        assert "Open" in resp.text  # "Open →" button

    async def test_deal_detail_404_for_bad_id(self, client: AsyncClient):
        resp = await client.get("/deals/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    async def test_update_deal_changes_name(self, client: AsyncClient, db):
        async with db() as session:
            deal = await seed_deal(session)
            opp_id = deal.opportunity_id
            await session.commit()

        resp = await client.post(
            f"/ui/deals/{opp_id}/update",
            data={"name": "Renamed Deal", "status": "hypothetical"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert f"/deals/{opp_id}" in resp.headers["location"]

        # Verify the name actually changed
        detail = await client.get(f"/deals/{opp_id}")
        assert "Renamed Deal" in detail.text

    async def test_link_parcel_to_deal(self, client: AsyncClient, db):
        from vicinitideals.models.parcel import Parcel
        async with db() as session:
            deal = await seed_deal(session)
            opp_id = deal.opportunity_id
            parcel = Parcel(apn="R123456789", address_normalized="123 Main St, Portland, OR")
            session.add(parcel)
            await session.commit()

        resp = await client.post(
            f"/ui/deals/{opp_id}/link-parcel",
            data={"apn": "R123456789", "relationship": "unchanged"},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        # Parcel tab should now show the linked parcel
        detail = await client.get(f"/deals/{opp_id}?tab=parcels")
        assert "R123456789" in detail.text
        assert "123 Main St" in detail.text

    async def test_link_parcel_not_found(self, client: AsyncClient, db):
        async with db() as session:
            deal = await seed_deal(session)
            opp_id = deal.opportunity_id
            await session.commit()

        resp = await client.post(
            f"/ui/deals/{opp_id}/link-parcel",
            data={"apn": "DOESNOTEXIST", "relationship": "unchanged"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "error=parcel_not_found" in resp.headers["location"]
```

**Why this pattern works for AI agents:** Tests follow a Arrange → Act → Assert structure. Names describe the expected behavior. When `test_link_parcel_to_deal` fails, the agent can see:
1. What data was seeded
2. What HTTP call was made
3. What the expected response was
4. Where to look (the `link_parcel_to_deal` route in `ui.py`)

---

## CI/CD: GitHub Actions

```yaml
# .github/workflows/test-re-modeling.yml
name: re-modeling tests

on:
  push:
    paths: ['re-modeling/**']
  pull_request:
    paths: ['re-modeling/**']

jobs:
  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: re-modeling
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: pip
      - run: pip install -e '.[dev]'
      - run: pytest -m "not slow" --cov --cov-report=term-missing --tb=short -q
```

This runs on every push that touches `re-modeling/`. Skip slow tests in CI to keep the feedback loop under 2 minutes.

---

## What an AI Agent Needs to Fix Things

When an agent runs `pytest` and gets failures, it needs:

1. **Clear test names** — `test_compute_produces_noi` tells it where to look
2. **Short assertion chains** — one concept per test, not 15 asserts in a row
3. **Traceable seed data** — `seed_deal_with_financials()` is readable; 100-line manual inserts are not
4. **Markers for scoping** — run `pytest -m unit` first (fast), then `-m integration` if unit passes
5. **No skip-on-failure** — `pytest.skip("DB not available")` hides real bugs; use in-memory DB always

When a test fails, the agent's workflow should be:
```
1. Read test name → understand what was being tested
2. Read test body → understand what was expected
3. Read error message → understand what actually happened
4. Read the source function → find the bug
5. Fix → re-run that single test → confirm green
```

Design every test with this workflow in mind.

---

## Priority Order

1. **Create root `tests/conftest.py`** with `db`, `session`, `client`, `auth_headers` fixtures + seed helpers
2. **Switch `Base.metadata.create_all`** instead of manual table lists (prevents "table not found" on new models)
3. **Fix `test_cashflow.py`** to use in-memory DB instead of production DB
4. **Add `pytest-cov`** to dev deps + initial `.coveragerc`
5. **Register pytest markers** in `pyproject.toml`
6. **Split `test_routers.py`** (3,041 lines) into per-domain files
7. **Add GitHub Actions workflow** for automated test runs
8. **Write unit tests** for engine functions that currently only have integration coverage
