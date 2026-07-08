"""Integration tests for the auto Developer Fee Use Line lifecycle:

- Deal-create POST seeds an `is_auto_dev_fee=True` row per project_type
- Form PUT honors the auto flag: only `dev_fee_pct` is editable, label /
  cost_category / phase are preserved
- API DELETE  (`/api/models/.../use-lines/...`) returns 403 on the auto row
- Form DELETE (`/ui/forms/.../use-lines/...`) returns 403 on the auto row
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import COOKIE_NAME, create_session_token
from app.models.deal import UseLine, UseLinePhase
from app.models.project import Project


pytestmark = pytest.mark.asyncio


async def _auth(client: AsyncClient, user_id) -> None:
    """Attach a signed session cookie to the test client."""
    from tests.conftest import set_client_auth
    set_client_auth(client, user_id)


# ---------------------------------------------------------------------------
# Auto-seed on deal create — one row per project_type
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "deal_type, expected_basis, expected_phase",
    [
        ("acquisition", "purchase_price", "acquisition"),
        ("value_add", "tpc_excl_self", "construction"),
        ("conversion", "tpc_excl_self", "construction"),
        ("new_construction", "tpc_excl_self", "construction"),
    ],
)
async def test_create_deal_seeds_auto_dev_fee_row(
    client: AsyncClient,
    session: AsyncSession,
    deal_type: str,
    expected_basis: str,
    expected_phase: str,
) -> None:
    from tests.conftest import seed_org

    org, user = await seed_org(session)
    await session.commit()
    await _auth(client, user.id)

    resp = await client.post(
        "/ui/deals/create",
        data={
            "name": f"Auto Dev Fee {deal_type}",
            "deal_type": deal_type,
            "acquisition_cost": "1000000",
            "org_id": str(org.id),
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text  # RedirectResponse to /models/{id}/builder

    # Find the project just created
    project = (
        await session.execute(
            select(Project).order_by(Project.created_at.desc()).limit(1)
        )
    ).scalar_one()

    auto_rows = (
        await session.execute(
            select(UseLine).where(
                UseLine.project_id == project.id,
                UseLine.is_auto_dev_fee.is_(True),
            )
        )
    ).scalars().all()

    assert len(auto_rows) == 1, "Exactly one auto Dev Fee row should be seeded"
    row = auto_rows[0]
    assert row.label == "Developer Fee"
    assert row.cost_category == "soft"
    assert row.dev_fee_basis == expected_basis
    assert str(row.phase.value if hasattr(row.phase, "value") else row.phase) == expected_phase
    # Engine recomputes; seed amount starts at 0.
    assert Decimal(str(row.amount)) == Decimal("0")
    # Snapshotted % matches SYSTEM_BASELINE
    expected_pct = Decimal("5.0") if deal_type == "acquisition" else Decimal("12.0")
    assert Decimal(str(row.dev_fee_pct)) == expected_pct


# ---------------------------------------------------------------------------
# Form PUT — only % is editable on the auto row
# ---------------------------------------------------------------------------


async def _seed_deal_with_auto_dev_fee(
    session: AsyncSession,
) -> tuple[UUID, UUID, UUID, UUID]:
    """Returns (model_id, project_id, auto_dev_fee_use_line_id, user_id)."""
    from tests.conftest import seed_org, seed_opportunity, seed_deal_model_with_financials

    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, _, _ = await seed_deal_model_with_financials(session, opp, user)
    project = (
        await session.execute(
            select(Project).where(Project.scenario_id == deal_model.id)
        )
    ).scalar_one()

    auto_row = UseLine(
        id=uuid4(),
        project_id=project.id,
        label="Developer Fee",
        phase=UseLinePhase.construction,
        cost_category="soft",
        amount=Decimal("0"),
        timing_type="spread",
        is_deferred=False,
        is_auto_dev_fee=True,
        dev_fee_pct=Decimal("12.0"),
        dev_fee_basis="tpc_excl_self",
    )
    session.add(auto_row)
    await session.flush()
    await session.commit()
    return deal_model.id, project.id, auto_row.id, user.id


async def test_form_put_only_updates_pct_on_auto_row(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    model_id, project_id, ul_id, user_id = await _seed_deal_with_auto_dev_fee(session)
    await _auth(client, user_id)

    # Caller tries to change everything — handler must ignore label/category/etc.
    resp = await client.put(
        f"/ui/forms/{model_id}/use-lines/{ul_id}",
        data={
            "label": "HIJACKED LABEL",
            "amount": "999999",
            "cost_category": "hard",
            "timing_type": "first_day",
            "milestone_key": "close",
            "is_deferred": "true",
            "notes": "user note",
            "dev_fee_pct": "7.5",
            "dev_fee_basis": "purchase_price",
        },
    )
    assert resp.status_code == 200, resp.text

    # Re-read from DB
    session.expire_all()
    row = await session.get(UseLine, ul_id)
    assert row is not None
    assert row.label == "Developer Fee"          # preserved
    assert row.cost_category == "soft"            # preserved
    assert row.is_deferred is False               # preserved
    assert Decimal(str(row.amount)) == Decimal("0")  # engine owns $, not user
    assert Decimal(str(row.dev_fee_pct)) == Decimal("7.5")  # updated
    assert row.dev_fee_basis == "purchase_price"  # basis toggled
    assert row.notes == "user note"               # notes updatable


# ---------------------------------------------------------------------------
# DELETE guards — both endpoints
# ---------------------------------------------------------------------------


async def test_api_delete_returns_403_for_auto_dev_fee(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    model_id, _project_id, ul_id, user_id = await _seed_deal_with_auto_dev_fee(session)
    await _auth(client, user_id)
    resp = await client.delete(f"/api/models/{model_id}/use-lines/{ul_id}")
    assert resp.status_code == 403, resp.text
    assert "auto Developer Fee" in resp.text or "Developer Fee" in resp.text


async def test_form_delete_returns_403_for_auto_dev_fee(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    model_id, _project_id, ul_id, user_id = await _seed_deal_with_auto_dev_fee(session)
    await _auth(client, user_id)
    resp = await client.delete(f"/ui/forms/{model_id}/use-lines/{ul_id}")
    assert resp.status_code == 403, resp.text
    assert "Developer Fee" in resp.text


async def test_api_delete_still_works_for_regular_use_line(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    """Sanity: the guard targets only is_auto_dev_fee rows."""
    from tests.conftest import seed_org, seed_opportunity, seed_deal_model_with_financials

    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, _, _ = await seed_deal_model_with_financials(session, opp, user)
    project = (
        await session.execute(
            select(Project).where(Project.scenario_id == deal_model.id)
        )
    ).scalar_one()
    regular = UseLine(
        id=uuid4(),
        project_id=project.id,
        label="Architect Fees",
        phase=UseLinePhase.pre_construction,
        cost_category="soft",
        amount=Decimal("50000"),
        timing_type="first_day",
    )
    session.add(regular)
    await session.commit()

    resp = await client.delete(f"/api/models/{deal_model.id}/use-lines/{regular.id}")
    assert resp.status_code == 204, resp.text
