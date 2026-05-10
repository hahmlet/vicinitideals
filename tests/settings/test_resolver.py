"""Unit tests for the org & user defaults resolution engine.

Uses the shared in-memory SQLite session fixture. Seeds OrgSetting and
UserSetting rows directly without going through the API layer.
"""

from __future__ import annotations

import pytest

from app.models.settings import OrgSetting, UserSetting
from app.settings.defaults import ORG_SET_FIELDS, SYSTEM_BASELINE
from app.settings.resolver import resolve_all_defaults, resolve_default
from tests.conftest import seed_org


# ---------------------------------------------------------------------------
# resolve_default — single field
# ---------------------------------------------------------------------------


async def test_user_setting_wins_over_org_setting(session):
    """User-Default (Type 3) overrides Org-Default (Type 2)."""
    org, user = await seed_org(session)
    field = "hold_term_years"

    session.add(OrgSetting(org_id=org.id, field_key=field, value="10"))
    session.add(UserSetting(user_id=user.id, org_id=org.id, field_key=field, value="15"))
    await session.flush()

    result = await resolve_default(field, user.id, org.id, session)
    assert result == "15"


async def test_org_setting_wins_over_system_baseline(session):
    """Org-Default (Type 2) overrides system baseline when no user setting exists."""
    org, user = await seed_org(session)
    field = "hold_term_years"

    session.add(OrgSetting(org_id=org.id, field_key=field, value="12"))
    await session.flush()

    result = await resolve_default(field, user.id, org.id, session)
    assert result == "12"


async def test_system_baseline_returned_when_no_settings(session):
    """System baseline is the fallback when no org or user setting exists."""
    org, user = await seed_org(session)
    field = "hold_term_years"

    result = await resolve_default(field, user.id, org.id, session)
    assert result == SYSTEM_BASELINE[field]


async def test_org_set_field_ignores_user_setting(session):
    """Org-Set (Type 1) bypasses user setting entirely — org value always wins."""
    org, user = await seed_org(session)
    field = "operation_reserve_months"
    assert field in ORG_SET_FIELDS

    session.add(OrgSetting(org_id=org.id, field_key=field, value="9"))
    session.add(UserSetting(user_id=user.id, org_id=org.id, field_key=field, value="3"))
    await session.flush()

    result = await resolve_default(field, user.id, org.id, session)
    assert result == "9"


async def test_org_set_field_falls_back_to_system_baseline(session):
    """Org-Set field returns system baseline when org has no setting configured."""
    org, user = await seed_org(session)
    field = "debt_sizing_mode"
    assert field in ORG_SET_FIELDS

    result = await resolve_default(field, user.id, org.id, session)
    assert result == SYSTEM_BASELINE[field]


# ---------------------------------------------------------------------------
# resolve_all_defaults — batch resolution
# ---------------------------------------------------------------------------


async def test_resolve_all_covers_every_baseline_key(session):
    """resolve_all_defaults returns one entry per key in SYSTEM_BASELINE."""
    org, user = await seed_org(session)
    resolved = await resolve_all_defaults(user.id, org.id, session)
    assert set(resolved.keys()) == set(SYSTEM_BASELINE.keys())


async def test_resolve_all_applies_full_resolution_chain(session):
    """resolve_all_defaults respects all three layers simultaneously."""
    org, user = await seed_org(session)

    # Org-Default field: user wins
    session.add(OrgSetting(org_id=org.id, field_key="hold_term_years", value="10"))
    session.add(UserSetting(user_id=user.id, org_id=org.id, field_key="hold_term_years", value="20"))

    # Org-Set field: org wins despite user setting
    session.add(OrgSetting(org_id=org.id, field_key="operation_reserve_months", value="9"))
    session.add(UserSetting(user_id=user.id, org_id=org.id, field_key="operation_reserve_months", value="3"))

    await session.flush()

    resolved = await resolve_all_defaults(user.id, org.id, session)

    assert resolved["hold_term_years"] == "20"
    assert resolved["operation_reserve_months"] == "9"
    assert resolved["dscr_min"] == SYSTEM_BASELINE["dscr_min"]
