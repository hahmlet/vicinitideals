"""Integration tests for money-math readback routes (app/api/routers/capital.py).

Covers:
  - GET /api/models/{model_id}/waterfall — raw WaterfallResult readback after
    a real compute (POST /api/models/{id}/compute chains the waterfall engine)
  - GET/PUT/DELETE /api/models/{model_id}/use-line-source-fee-basis

All capital.py routes resolve CurrentUserId and enforce that the user's org
owns the deal — tests set the X-User-ID header to a seeded real user.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capital import CapitalModule, WaterfallResult
from app.models.deal import UseLine
from app.models.project import Project

from tests.conftest import (
    seed_deal_model_with_financials,
    seed_opportunity,
    seed_org,
)

pytestmark = pytest.mark.asyncio


async def _seed_computable_deal(session: AsyncSession):
    """A small value-add deal with one auto-sizing perm loan — the same shape
    the reserve-idempotency regression test uses, proven to compute green.

    Returns (model_id, project_id, user_id) as plain values (captured before
    any route call can expire the ORM instances).
    """
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, inputs, _income, _opex = await seed_deal_model_with_financials(
        session, opp, user
    )
    project = (
        await session.execute(
            select(Project).where(Project.scenario_id == deal_model.id)
        )
    ).scalar_one()

    inputs.purchase_price = Decimal("1000000")
    inputs.closing_costs_pct = Decimal("2.0")
    inputs.renovation_cost_total = Decimal("500000")
    inputs.renovation_months = 6
    inputs.lease_up_months = 3
    session.add(inputs)

    session.add_all(
        [
            UseLine(
                project_id=project.id,
                label="Acquisition",
                phase="acquisition",
                amount=Decimal("1000000"),
                cost_category="acquisition",
                timing_type="first_day",
            ),
            UseLine(
                project_id=project.id,
                label="Hard Costs",
                phase="construction",
                amount=Decimal("500000"),
                cost_category="hard",
                timing_type="first_day",
            ),
            CapitalModule(
                scenario_id=deal_model.id,
                label="Permanent Loan",
                vehicle_type="debt",
                stack_position=1,
                source={
                    "amount": 0,
                    "interest_rate_pct": 6.5,
                    "auto_size": True,
                    "amort_term_years": 30,
                },
                carry={"carry_type": "pi", "payment_frequency": "monthly"},
                exit_terms={"exit_type": "full_payoff", "trigger": "sale"},
                active_phase_start="acquisition",
                active_phase_end="exit",
            ),
        ]
    )
    await session.commit()
    return deal_model.id, project.id, user.id


# ---------------------------------------------------------------------------
# GET /api/models/{model_id}/waterfall — readback after compute
# ---------------------------------------------------------------------------


async def test_waterfall_readback_after_compute(
    client: AsyncClient, session: AsyncSession
) -> None:
    model_id, _project_id, user_id = await _seed_computable_deal(session)
    client.headers["X-User-ID"] = str(user_id)

    compute = await client.post(f"/api/models/{model_id}/compute")
    assert compute.status_code == 200, compute.text

    resp = await client.get(f"/api/models/{model_id}/waterfall")
    assert resp.status_code == 200, resp.text
    rows = resp.json()

    # Compute chains the waterfall engine, which persists WaterfallResult rows.
    session.expire_all()
    db_rows = (
        await session.execute(
            select(WaterfallResult).where(WaterfallResult.scenario_id == model_id)
        )
    ).scalars().all()
    assert len(rows) == len(db_rows)
    assert len(rows) > 0, "compute should persist waterfall results"

    # Periods come back sorted ascending and rows carry distribution substance
    periods = [r["period"] for r in rows]
    assert periods == sorted(periods)
    assert all("cash_distributed" in r and "tier_id" in r for r in rows)
    # Readback must mirror the persisted engine output exactly, row for row.
    db_by_id = {str(r.id): r for r in db_rows}
    for api_row in rows:
        db_row = db_by_id[api_row["id"]]
        assert Decimal(str(api_row["cash_distributed"])) == Decimal(
            str(db_row.cash_distributed)
        )
        assert api_row["period"] == db_row.period


async def test_waterfall_readback_wrong_org_user_404(
    client: AsyncClient, session: AsyncSession
) -> None:
    model_id, _project_id, _user_id = await _seed_computable_deal(session)
    _other_org, other_user = await seed_org(session)
    await session.commit()

    client.headers["X-User-ID"] = str(other_user.id)
    resp = await client.get(f"/api/models/{model_id}/waterfall")
    assert resp.status_code == 404


async def test_waterfall_readback_unknown_model_404(
    client: AsyncClient, session: AsyncSession
) -> None:
    _, user = await seed_org(session)
    await session.commit()
    client.headers["X-User-ID"] = str(user.id)
    resp = await client.get(f"/api/models/{uuid.uuid4()}/waterfall")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Use-line x source fee-basis matrix — GET / PUT / DELETE
# ---------------------------------------------------------------------------


async def _seed_fee_basis_context(session: AsyncSession):
    """Returns (model_id, use_line_id, capital_module_id, user_id)."""
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, _, _ = await seed_deal_model_with_financials(session, opp, user)
    project = (
        await session.execute(
            select(Project).where(Project.scenario_id == deal_model.id)
        )
    ).scalar_one()

    use_line = UseLine(
        project_id=project.id,
        label="Architect Fees",
        phase="pre_construction",
        amount=Decimal("50000"),
        timing_type="first_day",
    )
    module = CapitalModule(
        scenario_id=deal_model.id,
        label="Construction Loan",
        vehicle_type="debt",
        stack_position=1,
        source={"amount": 1000000, "interest_rate_pct": 7.0},
        carry={"carry_type": "io_only"},
        exit_terms={},
    )
    session.add_all([use_line, module])
    await session.flush()
    await session.commit()
    return deal_model.id, use_line.id, module.id, user.id


async def test_fee_basis_put_get_delete_roundtrip(
    client: AsyncClient, session: AsyncSession
) -> None:
    model_id, use_line_id, module_id, user_id = await _seed_fee_basis_context(session)
    client.headers["X-User-ID"] = str(user_id)

    # Empty before any decision is stored
    empty = await client.get(f"/api/models/{model_id}/use-line-source-fee-basis")
    assert empty.status_code == 200, empty.text
    assert empty.json() == []

    # PUT upsert (insert)
    put1 = await client.put(
        f"/api/models/{model_id}/use-line-source-fee-basis",
        json={
            "use_line_id": str(use_line_id),
            "capital_module_id": str(module_id),
            "included_in_basis": False,
        },
    )
    assert put1.status_code == 200, put1.text
    assert put1.json()["included_in_basis"] is False

    listed = await client.get(f"/api/models/{model_id}/use-line-source-fee-basis")
    rows = listed.json()
    assert len(rows) == 1
    assert rows[0]["use_line_id"] == str(use_line_id)
    assert rows[0]["capital_module_id"] == str(module_id)

    # PUT upsert (update, not duplicate)
    put2 = await client.put(
        f"/api/models/{model_id}/use-line-source-fee-basis",
        json={
            "use_line_id": str(use_line_id),
            "capital_module_id": str(module_id),
            "included_in_basis": True,
        },
    )
    assert put2.status_code == 200, put2.text

    listed2 = await client.get(f"/api/models/{model_id}/use-line-source-fee-basis")
    rows2 = listed2.json()
    assert len(rows2) == 1
    assert rows2[0]["included_in_basis"] is True

    # DELETE removes the row; a second DELETE is idempotent
    del1 = await client.delete(
        f"/api/models/{model_id}/use-line-source-fee-basis/{use_line_id}/{module_id}"
    )
    assert del1.status_code == 204
    assert (
        await client.get(f"/api/models/{model_id}/use-line-source-fee-basis")
    ).json() == []

    del2 = await client.delete(
        f"/api/models/{model_id}/use-line-source-fee-basis/{use_line_id}/{module_id}"
    )
    assert del2.status_code == 204


async def test_fee_basis_put_rejects_foreign_use_line(
    client: AsyncClient, session: AsyncSession
) -> None:
    """A use line from another scenario must 404 — the fee-basis matrix cannot
    leak across deals."""
    model_id, _use_line_id, module_id, user_id = await _seed_fee_basis_context(session)
    _other_model_id, other_use_line_id, _other_module_id, _other_user_id = (
        await _seed_fee_basis_context(session)
    )
    client.headers["X-User-ID"] = str(user_id)

    resp = await client.put(
        f"/api/models/{model_id}/use-line-source-fee-basis",
        json={
            "use_line_id": str(other_use_line_id),
            "capital_module_id": str(module_id),
            "included_in_basis": True,
        },
    )
    assert resp.status_code == 404
