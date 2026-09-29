"""Integration tests for previously-untested routes in app/api/routers/ui_model_builder.py.

Covers:
  - GET  /ui/models/{id}/projects/{project_id}/adopt-source   (candidate list)
  - POST /ui/models/{id}/projects/{project_id}/adopt-source   (CapitalModuleProject write)
  - GET  /ui/models/{id}/balance-bar                          (deprecated alias of the
                                                                calc-status pill; asserts
                                                                the Sources-vs-Uses numbers)

Cross-org access to adopt-source lives in tests/api/test_bug_adopt_source_cross_org.py;
cross-org read of balance-bar in tests/api/test_bug_balance_bar_cross_org.py.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capital import CapitalModule, CapitalModuleProject
from app.models.deal import UseLine, UseLinePhase
from app.models.org import Organization, User
from app.models.project import Project

from tests.conftest import (
    seed_deal_model,
    seed_deal_model_with_financials,
    seed_opportunity,
    seed_org,
    set_client_auth,
)

pytestmark = pytest.mark.asyncio

_HX = {"hx-request": "true"}


async def _seed_two_projects(session: AsyncSession):
    """Scenario with P1 + P2. Two Sources, both attached to P1 only.

    Returns plain ids: (user_id, model_id, p1_id, p2_id, debt_id, equity_id)."""
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    scen = await seed_deal_model(session, opp, user)
    p1 = Project(id=uuid.uuid4(), scenario_id=scen.id, opportunity_id=opp.id, name="Phase 1")
    session.add(p1)
    await session.flush()
    p2 = Project(id=uuid.uuid4(), scenario_id=scen.id, opportunity_id=opp.id, name="Phase 2")
    session.add(p2)
    debt = CapitalModule(
        scenario_id=scen.id, label="Perm Loan", vehicle_type="debt", stack_position=1,
        source={"amount": "600000", "auto_size": True},
        active_phase_start="stabilized", active_phase_end="exit",
    )
    equity = CapitalModule(
        scenario_id=scen.id, label="LP Equity", vehicle_type="equity", stack_position=2,
        source={"amount": "400000"},
    )
    session.add_all([debt, equity])
    await session.flush()
    session.add_all([
        CapitalModuleProject(capital_module_id=debt.id, project_id=p1.id,
                             amount=Decimal("600000"), auto_size=True),
        CapitalModuleProject(capital_module_id=equity.id, project_id=p1.id,
                             amount=Decimal("400000"), auto_size=False),
    ])
    await session.commit()
    return user.id, scen.id, p1.id, p2.id, debt.id, equity.id


async def _junctions(session: AsyncSession, project_id) -> list[CapitalModuleProject]:
    session.expire_all()
    return list((await session.execute(
        select(CapitalModuleProject).where(CapitalModuleProject.project_id == project_id)
    )).scalars())


# ---------------------------------------------------------------------------
# GET adopt-source
# ---------------------------------------------------------------------------


async def test_adopt_source_modal_lists_only_unattached_sources(
    client: AsyncClient, session: AsyncSession
) -> None:
    user_id, model_id, p1_id, p2_id, debt_id, equity_id = await _seed_two_projects(session)
    set_client_auth(client, user_id)

    resp = await client.get(
        f"/ui/models/{model_id}/projects/{p2_id}/adopt-source", headers=_HX
    )
    assert resp.status_code == 200, resp.text[:500]
    assert "Adopt a Source for Phase 2" in resp.text
    assert f'value="{debt_id}"' in resp.text and "Perm Loan" in resp.text
    assert f'value="{equity_id}"' in resp.text and "LP Equity" in resp.text

    # P1 already carries both -> nothing to adopt.
    resp = await client.get(
        f"/ui/models/{model_id}/projects/{p1_id}/adopt-source", headers=_HX
    )
    assert resp.status_code == 200
    assert "No other Sources on this Deal are available to adopt" in resp.text
    assert f'value="{debt_id}"' not in resp.text


async def test_adopt_source_modal_project_not_on_model_404(
    client: AsyncClient, session: AsyncSession
) -> None:
    user_id, model_id, _p1, _p2, _d, _e = await _seed_two_projects(session)
    set_client_auth(client, user_id)
    resp = await client.get(
        f"/ui/models/{model_id}/projects/{uuid.uuid4()}/adopt-source", headers=_HX
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST adopt-source
# ---------------------------------------------------------------------------


async def test_adopt_source_write_creates_zero_amount_junction(
    client: AsyncClient, session: AsyncSession
) -> None:
    user_id, model_id, p1_id, p2_id, debt_id, _equity_id = await _seed_two_projects(session)
    set_client_auth(client, user_id)

    resp = await client.post(
        f"/ui/models/{model_id}/projects/{p2_id}/adopt-source",
        data={"source_id": str(debt_id)}, headers=_HX,
    )
    assert resp.status_code == 200, resp.text[:500]
    assert resp.headers["HX-Redirect"] == (
        f"/models/{model_id}/builder?module=sources_uses&project={p2_id}"
    )

    rows = await _junctions(session, p2_id)
    assert len(rows) == 1
    row = rows[0]
    assert row.capital_module_id == debt_id
    # Coverage starts at $0 — the Source's terms are shared, the amount is not.
    assert row.amount == Decimal("0")
    assert row.auto_size is True  # mirrors module.source["auto_size"]
    assert (row.active_from, row.active_to) == ("stabilized", "exit")

    # P1's junctions and amounts are untouched.
    p1_rows = {r.capital_module_id: r.amount for r in await _junctions(session, p1_id)}
    assert p1_rows[debt_id] == Decimal("600000")

    # Idempotent: adopting again does not duplicate the junction.
    resp = await client.post(
        f"/ui/models/{model_id}/projects/{p2_id}/adopt-source",
        data={"source_id": str(debt_id)}, headers=_HX,
    )
    assert resp.status_code == 200
    assert len(await _junctions(session, p2_id)) == 1


async def test_adopt_source_write_rejects_bad_input(
    client: AsyncClient, session: AsyncSession
) -> None:
    user_id, model_id, _p1, p2_id, _debt_id, _e = await _seed_two_projects(session)
    # A Source on a different scenario (same org).
    org_user = await session.get(User, user_id)
    org = await session.get(Organization, org_user.org_id)
    opp = await seed_opportunity(session, org, org_user)
    other_scen = await seed_deal_model(session, opp, org_user, name="Other")
    foreign = CapitalModule(scenario_id=other_scen.id, label="Foreign", vehicle_type="equity",
                            stack_position=1, source={"amount": "5"})
    session.add(foreign)
    await session.commit()
    foreign_id = foreign.id
    set_client_auth(client, user_id)
    url = f"/ui/models/{model_id}/projects/{p2_id}/adopt-source"

    assert (await client.post(url, data={"source_id": ""}, headers=_HX)).status_code == 400
    assert (await client.post(url, data={"source_id": "nope"}, headers=_HX)).status_code == 400
    resp = await client.post(url, data={"source_id": str(foreign_id)}, headers=_HX)
    assert resp.status_code == 404
    resp = await client.post(url, data={"source_id": str(uuid.uuid4())}, headers=_HX)
    assert resp.status_code == 404
    # Project not on this model.
    resp = await client.post(
        f"/ui/models/{model_id}/projects/{uuid.uuid4()}/adopt-source",
        data={"source_id": str(foreign_id)}, headers=_HX,
    )
    assert resp.status_code == 404
    assert await _junctions(session, p2_id) == []


# ---------------------------------------------------------------------------
# GET /ui/models/{id}/balance-bar
# ---------------------------------------------------------------------------


async def _seed_balance(session: AsyncSession, *, uses: str, equity: str | None):
    """Financial-seeded scenario + one $uses acquisition Use and an optional
    equity Source junctioned for $equity. No debt, no compute -> DSCR/LTV are
    n/a, so Sources vs Uses is the only live factor."""
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    scen, _inputs, _inc, _opx = await seed_deal_model_with_financials(session, opp, user)
    project = (await session.execute(
        select(Project).where(Project.scenario_id == scen.id)
    )).scalar_one()
    session.add(UseLine(project_id=project.id, label="Purchase Price",
                        phase=UseLinePhase.acquisition, amount=Decimal(uses),
                        timing_type="first_day"))
    if equity is not None:
        mod = CapitalModule(scenario_id=scen.id, label="LP Equity", vehicle_type="equity",
                            stack_position=1, source={"amount": equity})
        session.add(mod)
        await session.flush()
        session.add(CapitalModuleProject(capital_module_id=mod.id, project_id=project.id,
                                         amount=Decimal(equity), auto_size=False))
    await session.commit()
    return user.id, scen.id


async def test_balance_bar_reports_sources_gap_amount(
    client: AsyncClient, session: AsyncSession
) -> None:
    user_id, model_id = await _seed_balance(session, uses="1000000", equity="750000")
    set_client_auth(client, user_id)
    resp = await client.get(f"/ui/models/{model_id}/balance-bar", headers=_HX)
    assert resp.status_code == 200, resp.text[:500]
    assert "calc-status-pill warn" in resp.text
    assert "-$250,000 Sources Gap" in resp.text
    assert f'hx-get="/ui/models/{model_id}/calc-status/modal"' in resp.text


async def test_balance_bar_reports_sources_surplus_amount(
    client: AsyncClient, session: AsyncSession
) -> None:
    user_id, model_id = await _seed_balance(session, uses="1000000", equity="1125000")
    set_client_auth(client, user_id)
    resp = await client.get(f"/ui/models/{model_id}/balance-bar", headers=_HX)
    assert resp.status_code == 200
    assert "+$125,000 Sources Surplus" in resp.text


async def test_balance_bar_balanced_is_valid(
    client: AsyncClient, session: AsyncSession
) -> None:
    user_id, model_id = await _seed_balance(session, uses="1000000", equity="1000000")
    set_client_auth(client, user_id)
    resp = await client.get(f"/ui/models/{model_id}/balance-bar", headers=_HX)
    assert resp.status_code == 200
    assert "calc-status-pill ok" in resp.text
    assert "Calculation Valid" in resp.text
    assert "Sources Gap" not in resp.text and "Surplus" not in resp.text


async def test_balance_bar_matches_calc_status_pill(
    client: AsyncClient, session: AsyncSession
) -> None:
    user_id, model_id = await _seed_balance(session, uses="1000000", equity="750000")
    set_client_auth(client, user_id)
    bar = await client.get(f"/ui/models/{model_id}/balance-bar", headers=_HX)
    pill = await client.get(f"/ui/models/{model_id}/calc-status", headers=_HX)
    assert bar.text == pill.text
