"""REST/MCP milestone CRUD — Slice 5 (REST parity).

Covers:
- Milestone CRUD round-trip (create with duration → list → update → delete)
- Trigger-chain creation (B triggered by A) + rewiring (reordering)
- Chain-resolved computed_start/computed_end in the read shape
- 404 scoping on wrong model_id
- Trigger validation (cross-model reference, self-trigger, cycles)
- MCP-shaped flow: deal built purely via the JSON API gets a timeline whose
  dates resolve through the trigger chain (NOT the scalar fallback)
- Wizard regression: the timeline wizard (now backed by the same
  app/services/milestones.py service) still creates a wired chain
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.milestone import Milestone

pytestmark = [pytest.mark.asyncio, pytest.mark.unit]

ANCHOR_DATE = date(2026, 1, 1)


async def _seed_model(session: AsyncSession):
    from tests.conftest import (
        seed_deal_model_with_financials,
        seed_opportunity,
        seed_org,
    )

    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, _, _ = await seed_deal_model_with_financials(session, opp, user)
    return org, user, opp, deal_model


async def _post_anchor(client: AsyncClient, model_id, duration_days: int = 45):
    resp = await client.post(
        f"/api/models/{model_id}/milestones",
        json={
            "milestone_type": "close",
            "duration_days": duration_days,
            "target_date": ANCHOR_DATE.isoformat(),
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# CRUD round-trip
# ---------------------------------------------------------------------------

async def test_milestone_crud_roundtrip(
    client: AsyncClient, session: AsyncSession
) -> None:
    _, _, _, deal_model = await _seed_model(session)

    created = await _post_anchor(client, deal_model.id, duration_days=45)
    assert created["milestone_type"] == "close"
    assert created["duration_days"] == 45
    assert created["computed_start_date"] == ANCHOR_DATE.isoformat()
    assert created["computed_end_date"] == (ANCHOR_DATE + timedelta(days=45)).isoformat()

    listed = (await client.get(f"/api/models/{deal_model.id}/milestones")).json()
    assert len(listed) == 1
    assert listed[0]["id"] == created["id"]

    updated = await client.patch(
        f"/api/models/{deal_model.id}/milestones/{created['id']}",
        json={"duration_days": 60, "label": "Closing"},
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["duration_days"] == 60
    assert body["label"] == "Closing"
    assert body["computed_end_date"] == (ANCHOR_DATE + timedelta(days=60)).isoformat()

    deleted = await client.delete(
        f"/api/models/{deal_model.id}/milestones/{created['id']}"
    )
    assert deleted.status_code == 204

    listed = (await client.get(f"/api/models/{deal_model.id}/milestones")).json()
    assert listed == []


# ---------------------------------------------------------------------------
# Trigger chains
# ---------------------------------------------------------------------------

async def test_trigger_chain_creation_resolves_dates(
    client: AsyncClient, session: AsyncSession
) -> None:
    """B triggered by A: computed dates resolve through the chain."""
    _, _, _, deal_model = await _seed_model(session)

    anchor = await _post_anchor(client, deal_model.id, duration_days=45)

    b = await client.post(
        f"/api/models/{deal_model.id}/milestones",
        json={
            "milestone_type": "construction",
            "duration_days": 180,
            "trigger_milestone_id": anchor["id"],
        },
    )
    assert b.status_code == 201, b.text
    b_body = b.json()
    assert b_body["trigger_milestone_id"] == anchor["id"]
    # B starts at A's end (anchor date + 45d), ends 180d later.
    b_start = ANCHOR_DATE + timedelta(days=45)
    assert b_body["computed_start_date"] == b_start.isoformat()
    assert b_body["computed_end_date"] == (b_start + timedelta(days=180)).isoformat()

    c = await client.post(
        f"/api/models/{deal_model.id}/milestones",
        json={
            "milestone_type": "operation_stabilized",
            "duration_days": 1825,
            "trigger_milestone_id": b_body["id"],
            "trigger_offset_days": 30,
        },
    )
    assert c.status_code == 201, c.text
    c_start = b_start + timedelta(days=180 + 30)
    assert c.json()["computed_start_date"] == c_start.isoformat()

    # Sequence orders were appended in creation order.
    listed = (await client.get(f"/api/models/{deal_model.id}/milestones")).json()
    assert [m["milestone_type"] for m in listed] == [
        "close", "construction", "operation_stabilized",
    ]
    assert [m["sequence_order"] for m in listed] == sorted(
        m["sequence_order"] for m in listed
    )


async def test_trigger_chain_rewire_reorders_dates(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Re-pointing C's trigger from B to A moves its computed start."""
    _, _, _, deal_model = await _seed_model(session)

    anchor = await _post_anchor(client, deal_model.id, duration_days=45)
    b = (await client.post(
        f"/api/models/{deal_model.id}/milestones",
        json={
            "milestone_type": "construction",
            "duration_days": 180,
            "trigger_milestone_id": anchor["id"],
        },
    )).json()
    c = (await client.post(
        f"/api/models/{deal_model.id}/milestones",
        json={
            "milestone_type": "operation_lease_up",
            "duration_days": 120,
            "trigger_milestone_id": b["id"],
        },
    )).json()
    assert c["computed_start_date"] == (
        ANCHOR_DATE + timedelta(days=45 + 180)
    ).isoformat()

    # Rewire: C now triggers directly off the anchor.
    rewired = await client.patch(
        f"/api/models/{deal_model.id}/milestones/{c['id']}",
        json={"trigger_milestone_id": anchor["id"]},
    )
    assert rewired.status_code == 200, rewired.text
    assert rewired.json()["computed_start_date"] == (
        ANCHOR_DATE + timedelta(days=45)
    ).isoformat()


async def test_trigger_validation_rejects_bad_references(
    client: AsyncClient, session: AsyncSession
) -> None:
    _, _, _, deal_model = await _seed_model(session)
    anchor = await _post_anchor(client, deal_model.id)

    # Trigger pointing at a milestone that doesn't exist on this project.
    import uuid as _uuid
    bad = await client.post(
        f"/api/models/{deal_model.id}/milestones",
        json={
            "milestone_type": "construction",
            "duration_days": 180,
            "trigger_milestone_id": str(_uuid.uuid4()),
        },
    )
    assert bad.status_code == 400

    # Self-trigger via update.
    self_trig = await client.patch(
        f"/api/models/{deal_model.id}/milestones/{anchor['id']}",
        json={"trigger_milestone_id": anchor["id"]},
    )
    assert self_trig.status_code == 400

    # Cycle: A ← B, then try A ← ... ← B → A.
    b = (await client.post(
        f"/api/models/{deal_model.id}/milestones",
        json={
            "milestone_type": "construction",
            "duration_days": 180,
            "trigger_milestone_id": anchor["id"],
        },
    )).json()
    cycle = await client.patch(
        f"/api/models/{deal_model.id}/milestones/{anchor['id']}",
        json={"trigger_milestone_id": b["id"]},
    )
    assert cycle.status_code == 400


# ---------------------------------------------------------------------------
# 404 scoping
# ---------------------------------------------------------------------------

async def test_milestone_404_on_wrong_model(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, user, _, deal_model = await _seed_model(session)
    anchor = await _post_anchor(client, deal_model.id)

    import uuid as _uuid
    missing_model = _uuid.uuid4()
    assert (await client.get(f"/api/models/{missing_model}/milestones")).status_code == 404
    assert (
        await client.post(
            f"/api/models/{missing_model}/milestones",
            json={"milestone_type": "close", "duration_days": 1},
        )
    ).status_code == 404

    # A milestone reached through a DIFFERENT (real) model must 404 too.
    from tests.conftest import seed_deal_model_with_financials, seed_opportunity

    other_opp = await seed_opportunity(session, org, user)
    other_model, _, _, _ = await seed_deal_model_with_financials(
        session, other_opp, user
    )
    cross = await client.patch(
        f"/api/models/{other_model.id}/milestones/{anchor['id']}",
        json={"duration_days": 99},
    )
    assert cross.status_code == 404
    cross_del = await client.delete(
        f"/api/models/{other_model.id}/milestones/{anchor['id']}"
    )
    assert cross_del.status_code == 404


# ---------------------------------------------------------------------------
# MCP-shaped flow — deal built purely via the JSON API
# ---------------------------------------------------------------------------

async def test_mcp_shaped_flow_builds_timeline_with_resolving_chain(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Create the model via the API, add a full trigger-chained timeline via
    the API, and prove computed_start resolves through the chain (the engine
    would otherwise fall back to the OperationalInputs scalar months)."""
    from tests.conftest import seed_opportunity, seed_org

    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)

    # 1. Create the model (Deal + Scenario + default Project) via the API.
    model_resp = await client.post(
        f"/api/opportunities/{opp.id}/models",
        json={"name": "API-built Deal", "project_type": "new_construction"},
    )
    assert model_resp.status_code == 201, model_resp.text
    model_id = model_resp.json()["id"]

    # 2. Build the timeline purely via the API: anchor + chained phases.
    chain_spec = [
        ("close", 45, None),
        ("pre_development", 90, "close"),
        ("construction", 365, "pre_development"),
        ("operation_lease_up", 120, "construction"),
        ("operation_stabilized", 1825, "operation_lease_up"),
    ]
    ids: dict[str, str] = {}
    for mt, dur, trigger in chain_spec:
        payload: dict = {"milestone_type": mt, "duration_days": dur}
        if trigger is None:
            payload["target_date"] = ANCHOR_DATE.isoformat()
        else:
            payload["trigger_milestone_id"] = ids[trigger]
        resp = await client.post(f"/api/models/{model_id}/milestones", json=payload)
        assert resp.status_code == 201, resp.text
        ids[mt] = resp.json()["id"]

    # 3. Every milestone resolves a start date through the chain via the API…
    listed = (await client.get(f"/api/models/{model_id}/milestones")).json()
    assert len(listed) == 5
    starts = {m["milestone_type"]: m["computed_start_date"] for m in listed}
    assert None not in starts.values(), f"unresolved chain: {starts}"
    expected_construction_start = ANCHOR_DATE + timedelta(days=45 + 90)
    assert starts["construction"] == expected_construction_start.isoformat()
    assert starts["operation_stabilized"] == (
        ANCHOR_DATE + timedelta(days=45 + 90 + 365 + 120)
    ).isoformat()

    # 4. …and through the ORM's own computed_start (what the cashflow engine
    # calls), proving the engine sees trigger-chain windows, not the scalar
    # fallback path.
    rows = list((await session.execute(
        select(Milestone)
    )).scalars())
    rows = [r for r in rows if str(r.id) in set(ids.values())]
    milestone_map = {r.id: r for r in rows}
    by_type = {str(r.milestone_type).replace("MilestoneType.", ""): r for r in rows}
    orm_start = by_type["construction"].computed_start(milestone_map)
    assert orm_start == expected_construction_start
    assert by_type["construction"].trigger_milestone_id is not None
    assert by_type["close"].is_anchor


# ---------------------------------------------------------------------------
# Wizard regression — the wizard now runs on the same service
# ---------------------------------------------------------------------------

async def test_timeline_wizard_still_creates_wired_chain(
    client: AsyncClient, session: AsyncSession
) -> None:
    """POST the timeline wizard form and verify the two-pass creation still
    produces the same chain shape (anchor pinned, others trigger-wired,
    default/override/auto-cap durations applied)."""
    from tests.conftest import set_client_auth

    _, user, _, deal_model = await _seed_model(session)
    # /ui routes need a session cookie — HTMX requests no longer bypass the
    # auth middleware (2026-07-08 fix). set_client_auth also supplies the
    # CSRF header the csrf_protection middleware demands on HTMX POSTs.
    set_client_auth(client, user.id)
    from app.models.project import Project

    project = (await session.execute(
        select(Project).where(Project.scenario_id == deal_model.id)
    )).scalar_one()
    project_id = project.id  # capture before expire_all (async lazy-load)

    resp = await client.post(
        f"/ui/projects/{project_id}/timeline-wizard",
        data={
            "anchor_type": "close",
            "anchor_date": "2026-01-01",
            "anchor_duration_days": "45",
            "milestone_types": ["close", "construction", "operation_stabilized"],
            "duration_construction": "180",
        },
        headers={"hx-request": "true"},
    )
    assert resp.status_code == 303, resp.text

    session.expire_all()
    rows = list((await session.execute(
        select(Milestone)
        .where(Milestone.project_id == project_id)
        .order_by(Milestone.sequence_order)
    )).scalars())
    assert [str(r.milestone_type).replace("MilestoneType.", "") for r in rows] == [
        "close", "construction", "operation_stabilized",
    ]
    close_ms, constr_ms, stab_ms = rows

    # Anchor: calendar-pinned, no trigger.
    assert close_ms.target_date == ANCHOR_DATE
    assert close_ms.duration_days == 45
    assert close_ms.trigger_milestone_id is None

    # Chain wired in submitted order with offset 0.
    assert constr_ms.trigger_milestone_id == close_ms.id
    assert constr_ms.trigger_offset_days == 0
    assert constr_ms.duration_days == 180  # per-milestone override honored
    assert stab_ms.trigger_milestone_id == constr_ms.id
    # No divestment selected → stabilized auto-capped at 30 years.
    assert stab_ms.duration_days == 10950

    # Chain resolves dates end-to-end (the whole point of the wizard fix).
    milestone_map = {r.id: r for r in rows}
    assert stab_ms.computed_start(milestone_map) == ANCHOR_DATE + timedelta(
        days=45 + 180
    )
