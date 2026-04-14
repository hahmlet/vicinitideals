from __future__ import annotations

from collections.abc import AsyncGenerator
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from vicinitideals.models import Base  # imports all ORM models, enabling create_all
from vicinitideals.models.deal import OperatingExpenseLine
from vicinitideals.models.org import Organization, User
from vicinitideals.models.project import Project
from vicinitideals.scripts.import_tower_ap_deal import import_tower_ap_deal, load_formulas_payload


@pytest.fixture
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.xfail(
    reason="Tower/A&P parity validation not yet reconciled with post-refactor engine outputs",
    strict=True,
)
@pytest.mark.asyncio
async def test_tower_ap_formulas_parity_validates_excel_targets(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    formulas_path = Path(__file__).resolve().parents[2] / "formulas.json"
    assert formulas_path.exists(), "Expected REAL-73 formulas fixture at re-modeling/formulas.json"

    payload = load_formulas_payload(formulas_path)

    async with session_factory() as session:
        summary = await import_tower_ap_deal(payload, session=session, validation_tolerance_pct="0.1")

        projects = {project["name"]: project for project in summary["projects"]}
        assert set(projects) == {"Tower", "A&P"}

        for name, project in projects.items():
            assert project["validation"]["passed"] is True
            assert project["validation"]["checked_metrics"] >= 4
            assert project["cashflow"]["noi_stabilized"] > 0
            assert project["waterfall"]["dscr"] >= 1.15
            assert project["waterfall"]["equity_multiple"] > 1.0
            assert project["waterfall"]["project_irr_levered"] is not None

            deal_model_id = UUID(project["deal_model_id"])
            expense_count = (
                await session.execute(
                    select(func.count())
                    .select_from(OperatingExpenseLine)
                    .join(Project, Project.id == OperatingExpenseLine.project_id)
                    .where(Project.scenario_id == deal_model_id)
                )
            ).scalar_one()
            assert expense_count == 22, f"{name} should import the 22 itemized expense lines"

            expense_lines = list(
                (
                    await session.execute(
                        select(OperatingExpenseLine)
                        .join(Project, Project.id == OperatingExpenseLine.project_id)
                        .where(Project.scenario_id == deal_model_id)
                    )
                ).scalars()
            )
            assert all(
                Decimal(str(line.escalation_rate_pct_annual)) == Decimal("3")
                for line in expense_lines
            )
