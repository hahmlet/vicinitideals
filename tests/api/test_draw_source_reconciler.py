"""DrawSource reconciler tests.

The reconciler lives at the top of ``_load_draw_schedule_ctx`` in
``app/api/routers/ui.py``. Every load:

1. Deletes orphan DrawSources (rows with ``capital_module_id=NULL`` or
   pointing to a CapitalModule that no longer exists).
2. Creates missing DrawSources for CapitalModules that have none.

Both bugs were happening in production data: the auto-seeder only ran when
zero DrawSources existed, so sources added after the initial compute were
silently invisible to the draw schedule engine; wizard re-runs left
``capital_module_id=NULL`` rows behind as phantoms in the Sources Summary
KPI tile.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.ui import _load_draw_schedule_ctx
from app.models.capital import CapitalModule, DrawSource


@pytest.mark.asyncio
async def test_reconciler_deletes_orphan_draw_sources(
    session: AsyncSession,
) -> None:
    """DrawSource rows with capital_module_id=NULL must be removed on load."""
    from tests.conftest import seed_org, seed_opportunity, seed_deal_model_with_financials

    _, user = await seed_org(session)
    opp = await seed_opportunity(session, await _org_for(session, user), user)
    deal_model, _, _, _ = await seed_deal_model_with_financials(session, opp, user)

    # Plant an orphan: NULL capital_module_id, label looks like the
    # legacy "Permanent Debt (auto)" phantom seen in production.
    orphan = DrawSource(
        scenario_id=deal_model.id,
        label="Permanent Debt (auto)",
        source_type="debt",
        capital_module_id=None,
        active_from_milestone="operation_lease_up",
        active_to_milestone="operation_lease_up",
        sort_order=99,
    )
    session.add(orphan)
    await session.commit()
    orphan_id = orphan.id

    # Trigger the reconciler.
    await _load_draw_schedule_ctx(session, deal_model.id)
    await session.commit()

    # Orphan is gone.
    remaining = (
        await session.execute(
            select(DrawSource).where(DrawSource.id == orphan_id)
        )
    ).scalar_one_or_none()
    assert remaining is None


@pytest.mark.asyncio
async def test_reconciler_creates_missing_draw_source_for_grant(
    session: AsyncSession,
) -> None:
    """CapitalModule added after the initial seed must get a DrawSource."""
    from tests.conftest import seed_org, seed_opportunity, seed_deal_model_with_financials

    _, user = await seed_org(session)
    opp = await seed_opportunity(session, await _org_for(session, user), user)
    deal_model, _, _, _ = await seed_deal_model_with_financials(session, opp, user)

    # Simulate the user adding a grant *after* whatever initial seed ran:
    # CapitalModule exists, no matching DrawSource.
    grant = CapitalModule(
        scenario_id=deal_model.id,
        label="OR-MEP / Energy Trust",
        vehicle_type="grant",
        stack_position=1,
        source={"amount": "250000", "auto_size": True, "interest_rate_pct": 0.0},
        carry={},
        exit_terms={},
        active_phase_start="acquisition",
        active_phase_end="construction",
    )
    session.add(grant)
    await session.commit()

    # Pre-condition: no DrawSource for the grant yet.
    pre = (
        await session.execute(
            select(DrawSource).where(
                DrawSource.scenario_id == deal_model.id,
                DrawSource.capital_module_id == grant.id,
            )
        )
    ).scalar_one_or_none()
    assert pre is None

    # Trigger reconciler.
    await _load_draw_schedule_ctx(session, deal_model.id)
    await session.commit()

    # Post-condition: a DrawSource now exists for the grant.
    post = (
        await session.execute(
            select(DrawSource).where(
                DrawSource.scenario_id == deal_model.id,
                DrawSource.capital_module_id == grant.id,
            )
        )
    ).scalar_one_or_none()
    assert post is not None
    assert post.label == "OR-MEP / Energy Trust"
    assert post.source_type == "equity"  # grants map to source_type="equity"
    assert post.total_commitment == Decimal("250000")


@pytest.mark.asyncio
async def test_reconciler_skips_zero_amount_equity_stubs(
    session: AsyncSession,
) -> None:
    """Unfunded equity placeholders (no amount) should NOT get a DrawSource."""
    from tests.conftest import seed_org, seed_opportunity, seed_deal_model_with_financials

    _, user = await seed_org(session)
    opp = await seed_opportunity(session, await _org_for(session, user), user)
    deal_model, _, _, _ = await seed_deal_model_with_financials(session, opp, user)

    stub = CapitalModule(
        scenario_id=deal_model.id,
        label="Owner Equity",
        vehicle_type="equity",
        stack_position=2,
        source={"auto_size": True},  # No amount key
        carry={},
        exit_terms={},
        active_phase_start="acquisition",
        active_phase_end="exit",
    )
    session.add(stub)
    await session.commit()

    await _load_draw_schedule_ctx(session, deal_model.id)
    await session.commit()

    rows = (
        await session.execute(
            select(DrawSource).where(
                DrawSource.scenario_id == deal_model.id,
                DrawSource.capital_module_id == stub.id,
            )
        )
    ).scalars().all()
    assert rows == [], "Zero-amount equity stubs must not generate a DrawSource"


@pytest.mark.asyncio
async def test_reconciler_idempotent_on_healthy_data(
    session: AsyncSession,
) -> None:
    """Two loads in a row produce identical DrawSource sets."""
    from tests.conftest import seed_org, seed_opportunity, seed_deal_model_with_financials

    _, user = await seed_org(session)
    opp = await seed_opportunity(session, await _org_for(session, user), user)
    deal_model, _, _, _ = await seed_deal_model_with_financials(session, opp, user)

    cm = CapitalModule(
        scenario_id=deal_model.id,
        label="RJ Bond",
        vehicle_type="debt",
        stack_position=1,
        source={"amount": "10000000", "auto_size": True, "interest_rate_pct": 6.0},
        carry={"carry_type": "pi", "io_rate_pct": 6.0},
        exit_terms={},
        active_phase_start="acquisition",
        active_phase_end="exit",
    )
    session.add(cm)
    await session.commit()

    # First load → reconciler creates DrawSource.
    await _load_draw_schedule_ctx(session, deal_model.id)
    await session.commit()
    first = (
        await session.execute(
            select(DrawSource.id).where(DrawSource.scenario_id == deal_model.id)
        )
    ).scalars().all()

    # Second load → reconciler must NOT recreate.
    await _load_draw_schedule_ctx(session, deal_model.id)
    await session.commit()
    second = (
        await session.execute(
            select(DrawSource.id).where(DrawSource.scenario_id == deal_model.id)
        )
    ).scalars().all()

    assert set(first) == set(second)
    assert len(first) == len(second)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _org_for(session: AsyncSession, user) -> object:
    """seed_opportunity needs an Organization arg; fetch via user.org_id."""
    from app.models.org import Organization
    org = await session.get(Organization, user.org_id)
    assert org is not None
    return org
