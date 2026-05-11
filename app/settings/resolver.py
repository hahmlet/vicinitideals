"""Default resolution engine.

Resolves the effective value for a field_key given a user/org context.

Resolution order
----------------
Org-Set fields (in ORG_SET_FIELDS):
    org setting → system baseline   (user override bypassed unconditionally)

Fields where org has set user_overridable=False:
    org setting → system baseline   (user override bypassed by admin choice)

All other fields:
    1. User setting  (Type 3 — User-Default)
    2. Org setting   (Type 2 — Org-Default)
    3. System baseline (Type 5 — hardcoded constant)
    4. None          (Type 4 — No Default; only for keys not in SYSTEM_BASELINE)
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import OrgSetting, UserSetting
from app.settings.defaults import ORG_SET_FIELDS, SYSTEM_BASELINE


async def resolve_default(
    field_key: str,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    session: AsyncSession,
) -> str | None:
    """Resolve one field's effective default for a given user/org context."""
    result = await session.execute(
        select(OrgSetting).where(
            OrgSetting.org_id == org_id,
            OrgSetting.field_key == field_key,
        )
    )
    org_row = result.scalar_one_or_none()

    # Org-Set fields and admin-locked fields skip user setting entirely.
    locked = field_key in ORG_SET_FIELDS or (
        org_row is not None and not org_row.user_overridable
    )
    if locked:
        return org_row.value if org_row else SYSTEM_BASELINE.get(field_key)

    # Type 3: User-Default
    result = await session.execute(
        select(UserSetting).where(
            UserSetting.user_id == user_id,
            UserSetting.field_key == field_key,
        )
    )
    user_row = result.scalar_one_or_none()
    if user_row:
        return user_row.value

    # Type 2: Org-Default
    if org_row:
        return org_row.value

    # Type 5: System baseline (or None for Type 4)
    return SYSTEM_BASELINE.get(field_key)


async def resolve_all_defaults(
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    session: AsyncSession,
) -> dict[str, str | None]:
    """Resolve every field_key in SYSTEM_BASELINE in two DB round-trips.

    Org-Set fields and admin-locked fields use org value (or system baseline).
    All others follow the full User → Org → System chain.
    """
    org_rows = (
        await session.execute(select(OrgSetting).where(OrgSetting.org_id == org_id))
    ).scalars().all()
    user_rows = (
        await session.execute(select(UserSetting).where(UserSetting.user_id == user_id))
    ).scalars().all()

    # org_map: field_key → (value, user_overridable)
    org_map: dict[str, tuple[str, bool]] = {
        r.field_key: (r.value, r.user_overridable) for r in org_rows
    }
    user_map: dict[str, str] = {r.field_key: r.value for r in user_rows}

    resolved: dict[str, str | None] = {}
    for key in SYSTEM_BASELINE:
        org_entry = org_map.get(key)
        org_value = org_entry[0] if org_entry else None
        user_overridable = org_entry[1] if org_entry else True

        locked = key in ORG_SET_FIELDS or not user_overridable

        if locked:
            resolved[key] = org_value if org_value is not None else SYSTEM_BASELINE[key]
        elif key in user_map:
            resolved[key] = user_map[key]
        elif org_value is not None:
            resolved[key] = org_value
        else:
            resolved[key] = SYSTEM_BASELINE[key]

    return resolved


def build_overridable_map(
    org_rows: list[OrgSetting],
) -> dict[str, bool]:
    """Return {field_key: user_overridable} for all SYSTEM_BASELINE keys.

    ORG_SET_FIELDS are always False regardless of DB value.
    Fields with no OrgSetting row default to True (backward compatible).
    """
    db_map = {r.field_key: r.user_overridable for r in org_rows}
    return {
        key: False if key in ORG_SET_FIELDS else db_map.get(key, True)
        for key in SYSTEM_BASELINE
    }
