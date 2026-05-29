"""Integration tests for POST /ui/deals/email/{id}/create-deals.

Covers:
- Two distinct deal names → two Deal + Scenario rows created
- Same deal name for two files → grouped into one Deal
- email.status updated to opportunity_created
- Redis email_config key stored per file with correct sheet/page values
- Redirect points to first deal's builder wizard
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.deps import get_db
from app.api.main import app
from app.models.deal import Deal
from app.models.email_ingest import InboundEmail
from app.models.opportunity import Opportunity


# ---------------------------------------------------------------------------
# In-memory Redis stand-in
# ---------------------------------------------------------------------------

class _FakeRedis:
    def __init__(self, store: dict, *, decode_responses: bool = False):
        self._store = store
        self._decode = decode_responses

    def get(self, key: str):
        val = self._store.get(key)
        if val is None:
            return None
        if self._decode:
            return val.decode() if isinstance(val, bytes) else val
        return val if isinstance(val, bytes) else str(val).encode()

    def set(self, key: str, value, ex=None):
        if isinstance(value, str):
            value = value.encode()
        elif not isinstance(value, bytes):
            value = str(value).encode()
        self._store[key] = value

    def getdel(self, key: str):
        val = self.get(key)
        self._store.pop(key, None)
        return val


@pytest.fixture
def redis_store() -> dict:
    return {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _seed_org_and_user(session):
    from app.models.org import Organization, User
    suffix = uuid.uuid4().hex[:8]
    org = Organization(id=uuid.uuid4(), name=f"Email Test Org {suffix}", slug=f"email-test-{suffix}")
    session.add(org)
    await session.flush()
    user = User(
        id=uuid.uuid4(),
        org_id=org.id,
        name="Test User",
        email=f"test-{suffix}@example.com",
        hashed_password="$2b$12$dummy_hash_not_used_in_tests",
    )
    session.add(user)
    await session.flush()
    return org, user


async def _seed_inbound_email(session, org_id: uuid.UUID, task_ids: list[str]) -> InboundEmail:
    attachments_meta = [
        {"proforma_task_id": tid, "filename": f"file_{i}.xlsx", "size_bytes": 1024}
        for i, tid in enumerate(task_ids)
    ]
    row = InboundEmail(
        id=uuid.uuid4(),
        org_id=org_id,
        sender_email="broker@example.com",
        status="pending_review",
        proforma_task_ids=task_ids,
        attachments_meta=attachments_meta,
    )
    session.add(row)
    await session.flush()
    return row


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_two_names_create_two_deals(session, redis_store):
    """Two distinct deal names → 2 Deal rows, email.status = opportunity_created."""
    org, user = await _seed_org_and_user(session)
    task_ids = ["task-a1", "task-b1"]
    email_row = await _seed_inbound_email(session, org.id, task_ids)
    await session.commit()

    store = redis_store

    def _fake_from_url(url, **kwargs):
        return _FakeRedis(store, decode_responses=kwargs.get("decode_responses", False))

    async def _db_override() -> AsyncGenerator:
        yield session

    app.dependency_overrides[get_db] = _db_override
    try:
        with patch("redis.from_url", _fake_from_url):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/ui/deals/email/{email_row.id}/create-deals",
                    headers={"X-User-ID": str(user.id), "hx-request": "true"},
                    data={
                        "task_id_0": "task-a1",
                        "file_kind_0": "xlsx",
                        "deal_name_0": "Brittany Place",
                        "rev_sheet_0": "Revenue",
                        "rev_range_0": "",
                        "opex_sheet_0": "OpEx",
                        "opex_range_0": "",
                        "task_id_1": "task-b1",
                        "file_kind_1": "xlsx",
                        "deal_name_1": "Oak Street Apts",
                        "rev_sheet_1": "P&L",
                        "rev_range_1": "A1:D50",
                        "opex_sheet_1": "P&L",
                        "opex_range_1": "A52:D90",
                    },
                    follow_redirects=False,
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 303
    location = resp.headers["location"]
    assert "/builder?module=timeline&wizard=1" in location

    # Reload email row
    await session.refresh(email_row)
    assert email_row.status == "opportunity_created"
    assert email_row.opportunity_id is not None

    # 2 Deals
    result = await session.execute(select(Deal).where(Deal.org_id == org.id))
    deals = result.scalars().all()
    assert len(deals) == 2
    assert {d.name for d in deals} == {"Brittany Place", "Oak Street Apts"}

    # 2 Opportunities
    opp_result = await session.execute(select(Opportunity).where(Opportunity.org_id == org.id))
    opps = opp_result.scalars().all()
    assert len(opps) == 2

    # Redis config keys set for each file
    for tid in task_ids:
        key = f"proforma:{tid}:email_config"
        assert key in store, f"Missing Redis config key for {tid}"

    # Brittany Place config
    bp_cfg = json.loads(store["proforma:task-a1:email_config"].decode())
    assert bp_cfg["rev_sheet"] == "Revenue"
    assert bp_cfg["opex_sheet"] == "OpEx"
    assert bp_cfg["import_revenue"] is True
    assert bp_cfg["import_opex"] is True

    # Oak Street with range
    oak_cfg = json.loads(store["proforma:task-b1:email_config"].decode())
    assert oak_cfg["rev_range"] == "A1:D50"
    assert oak_cfg["opex_range"] == "A52:D90"

    # Wizard task_id key stored for first scenario
    scenario_id_str = location.split("/models/")[1].split("/")[0]
    wizard_key = f"proforma:scenario:{scenario_id_str}:email_task_id"
    assert wizard_key in store


@pytest.mark.asyncio
async def test_same_name_groups_into_one_deal(session, redis_store):
    """Three rows where two share the same deal name → 2 Deals total, not 3."""
    org, user = await _seed_org_and_user(session)
    task_ids = ["task-x1", "task-x2", "task-x3"]
    email_row = await _seed_inbound_email(session, org.id, task_ids)
    await session.commit()

    store = redis_store

    def _fake_from_url(url, **kwargs):
        return _FakeRedis(store, decode_responses=kwargs.get("decode_responses", False))

    async def _db_override() -> AsyncGenerator:
        yield session

    app.dependency_overrides[get_db] = _db_override
    try:
        with patch("redis.from_url", _fake_from_url):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/ui/deals/email/{email_row.id}/create-deals",
                    headers={"X-User-ID": str(user.id), "hx-request": "true"},
                    data={
                        # Row 0: Deal A, revenue sheet
                        "task_id_0": "task-x1",
                        "file_kind_0": "xlsx",
                        "deal_name_0": "Hazelwood Commons",
                        "rev_sheet_0": "Revenue",
                        "rev_range_0": "",
                        "opex_sheet_0": "",
                        "opex_range_0": "",
                        # Row 1: Deal B
                        "task_id_1": "task-x2",
                        "file_kind_1": "xlsx",
                        "deal_name_1": "Pine Ridge",
                        "rev_sheet_1": "P&L",
                        "rev_range_1": "",
                        "opex_sheet_1": "",
                        "opex_range_1": "",
                        # Row 2: Same as row 0 name → groups with Hazelwood
                        "task_id_2": "task-x3",
                        "file_kind_2": "xlsx",
                        "deal_name_2": "Hazelwood Commons",
                        "rev_sheet_2": "",
                        "rev_range_2": "",
                        "opex_sheet_2": "OpEx",
                        "opex_range_2": "",
                    },
                    follow_redirects=False,
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 303

    result = await session.execute(select(Deal).where(Deal.org_id == org.id))
    deals = result.scalars().all()
    assert len(deals) == 2
    assert {d.name for d in deals} == {"Hazelwood Commons", "Pine Ridge"}

    # Both Hazelwood files get config keys
    assert f"proforma:task-x1:email_config" in store
    assert f"proforma:task-x3:email_config" in store

    # Wizard key points to first file (task-x1) for Hazelwood (first deal)
    location = resp.headers["location"]
    scenario_id_str = location.split("/models/")[1].split("/")[0]
    assert store.get(f"proforma:scenario:{scenario_id_str}:email_task_id", b"").decode() == "task-x1"


@pytest.mark.asyncio
async def test_wrong_org_returns_404(session, redis_store):
    """User from different org cannot create deals from another org's email."""
    org1, user1 = await _seed_org_and_user(session)
    org2, user2 = await _seed_org_and_user(session)
    task_ids = ["task-z1"]
    email_row = await _seed_inbound_email(session, org1.id, task_ids)
    await session.commit()

    store = redis_store

    def _fake_from_url(url, **kwargs):
        return _FakeRedis(store, decode_responses=kwargs.get("decode_responses", False))

    async def _db_override() -> AsyncGenerator:
        yield session

    app.dependency_overrides[get_db] = _db_override
    try:
        with patch("redis.from_url", _fake_from_url):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/ui/deals/email/{email_row.id}/create-deals",
                    headers={"X-User-ID": str(user2.id), "hx-request": "true"},  # wrong org
                    data={
                        "task_id_0": "task-z1",
                        "file_kind_0": "xlsx",
                        "deal_name_0": "Test Deal",
                    },
                    follow_redirects=False,
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 404
