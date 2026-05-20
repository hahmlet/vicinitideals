"""Unit tests for resolve_dev_fee_config — org/user override chain.

Tests follow the same pattern as the milestone defaults resolver tests:
SYSTEM_BASELINE → OrgSetting → UserSetting (gated by org user_overridable flag).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.settings import OrgSetting, UserSetting
from app.settings.resolver import resolve_dev_fee_config
from tests.conftest import seed_org


@pytest.mark.unit
async def test_baseline_returns_system_defaults(session):
    org, user = await seed_org(session)
    cfg = await resolve_dev_fee_config(user.id, org.id, "acquisition", session)
    assert cfg["pct"] == "5.0"
    assert cfg["basis"] == "purchase_price"

    cfg2 = await resolve_dev_fee_config(user.id, org.id, "new_construction", session)
    assert cfg2["pct"] == "12.0"
    assert cfg2["basis"] == "tpc_excl_self"


@pytest.mark.unit
async def test_org_setting_overrides_baseline(session):
    org, user = await seed_org(session)
    session.add(OrgSetting(
        id=uuid.uuid4(),
        org_id=org.id,
        field_key="dev_fee_pct_value_add",
        value="8.5",
        user_overridable=True,
    ))
    await session.flush()

    cfg = await resolve_dev_fee_config(user.id, org.id, "value_add", session)
    assert cfg["pct"] == "8.5"


@pytest.mark.unit
async def test_user_setting_overrides_org_when_overridable(session):
    org, user = await seed_org(session)
    session.add_all([
        OrgSetting(
            id=uuid.uuid4(),
            org_id=org.id,
            field_key="dev_fee_pct_value_add",
            value="8.5",
            user_overridable=True,
        ),
        UserSetting(
            id=uuid.uuid4(),
            user_id=user.id,
            org_id=org.id,
            field_key="dev_fee_pct_value_add",
            value="3.0",
        ),
    ])
    await session.flush()

    cfg = await resolve_dev_fee_config(user.id, org.id, "value_add", session)
    assert cfg["pct"] == "3.0"


@pytest.mark.unit
async def test_user_setting_ignored_when_org_locks(session):
    """Org user_overridable=False forces the org value."""
    org, user = await seed_org(session)
    session.add_all([
        OrgSetting(
            id=uuid.uuid4(),
            org_id=org.id,
            field_key="dev_fee_pct_value_add",
            value="8.5",
            user_overridable=False,
        ),
        UserSetting(
            id=uuid.uuid4(),
            user_id=user.id,
            org_id=org.id,
            field_key="dev_fee_pct_value_add",
            value="3.0",
        ),
    ])
    await session.flush()

    cfg = await resolve_dev_fee_config(user.id, org.id, "value_add", session)
    assert cfg["pct"] == "8.5"


@pytest.mark.unit
async def test_unknown_deal_type_falls_back_to_acquisition(session):
    org, user = await seed_org(session)
    cfg = await resolve_dev_fee_config(user.id, org.id, "totally_invalid", session)
    # Acquisition baseline values
    assert cfg["pct"] == "5.0"
    assert cfg["basis"] == "purchase_price"


@pytest.mark.unit
async def test_returns_all_four_slots(session):
    org, user = await seed_org(session)
    cfg = await resolve_dev_fee_config(user.id, org.id, "new_construction", session)
    assert set(cfg.keys()) == {"enabled", "pct", "basis", "timing", "phase"}
