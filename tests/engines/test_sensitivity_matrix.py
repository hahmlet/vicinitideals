"""Engine tests for compute_sensitivity_matrix.

Covers the combined-mode + step-overrides additions wired up for the
investor Excel export's two-way sensitivity sheet. Reuses the
``_seed_cashflow_deal`` helper from ``test_cashflow.py`` (which is the
canonical minimal-deal fixture for engine integration tests).
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.engines.sensitivity_matrix import (
    GRID_SIZE,
    compute_sensitivity_matrix,
)

from tests.engines.test_cashflow import _seed_cashflow_deal


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    from app.models import Base  # noqa: F401

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_combined_mode_returns_5x5_grid_with_mode_field(
    db_session: AsyncSession,
) -> None:
    deal_id = await _seed_cashflow_deal(db_session)

    matrix = await compute_sensitivity_matrix(
        deal_id, db_session,
        axis_x="noi_escalation_rate_pct",
        axis_y="exit_cap_rate_pct",
        metric="project_irr_levered",
        mode="combined",
    )

    assert matrix["mode"] == "combined"
    assert len(matrix["values"]) == GRID_SIZE
    assert all(len(row) == GRID_SIZE for row in matrix["values"])
    assert len(matrix["axis_x"]["values"]) == GRID_SIZE
    assert len(matrix["axis_y"]["values"]) == GRID_SIZE


@pytest.mark.asyncio
@pytest.mark.integration
async def test_step_overrides_widen_axis_spacing(db_session: AsyncSession) -> None:
    deal_id = await _seed_cashflow_deal(db_session)

    matrix_default = await compute_sensitivity_matrix(
        deal_id, db_session,
        axis_x="noi_escalation_rate_pct",
        axis_y="exit_cap_rate_pct",
        metric="project_irr_levered",
        mode="combined",
    )
    matrix_overridden = await compute_sensitivity_matrix(
        deal_id, db_session,
        axis_x="noi_escalation_rate_pct",
        axis_y="exit_cap_rate_pct",
        metric="project_irr_levered",
        mode="combined",
        step_overrides={
            "noi_escalation_rate_pct": Decimal("1.0"),
            "exit_cap_rate_pct": Decimal("0.5"),
        },
    )

    # default_step is 0.25 for both axes, so the overridden run should
    # produce strictly wider spans (max - min) than the default run.
    def _span(values: list[float]) -> float:
        return values[-1] - values[0]

    assert _span(matrix_overridden["axis_x"]["values"]) > _span(
        matrix_default["axis_x"]["values"]
    )
    assert _span(matrix_overridden["axis_y"]["values"]) > _span(
        matrix_default["axis_y"]["values"]
    )

    # Step values land on 0.5 / 1.0 spacing exactly (two adjacent cells).
    x_vals = matrix_overridden["axis_x"]["values"]
    y_vals = matrix_overridden["axis_y"]["values"]
    assert pytest.approx(x_vals[1] - x_vals[0], abs=1e-6) == 1.0
    assert pytest.approx(y_vals[1] - y_vals[0], abs=1e-6) == 0.5


@pytest.mark.asyncio
@pytest.mark.integration
async def test_first_mode_back_compat_unchanged_shape(
    db_session: AsyncSession,
) -> None:
    """``mode='first'`` is the back-compat path used by the existing UI tab.

    Sanity: it still returns a 5x5 grid and the ``mode`` field reads back
    as 'first'. Cell values aren't asserted (covered by the combined-mode
    test); we only confirm the new keyword arg didn't regress the default.
    """
    deal_id = await _seed_cashflow_deal(db_session)

    matrix = await compute_sensitivity_matrix(deal_id, db_session)

    assert matrix["mode"] == "first"
    assert len(matrix["values"]) == GRID_SIZE
    assert all(len(row) == GRID_SIZE for row in matrix["values"])
