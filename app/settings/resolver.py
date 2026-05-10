"""Default resolution engine.

Resolves the effective value for a field_key given a user/org context.

Resolution order
----------------
Org-Set fields (in ORG_SET_FIELDS):
    org setting → system baseline   (user override is bypassed entirely)

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
    """Resolve one field's effective default for a given user/org context.

    Returns the resolved string value, or None when the field has no default
    at any level (Type 4). Callers are responsible for type-casting the result.
    """
    if field_key in ORG_SET_FIELDS:
        result = await session.execute(
            select(OrgSetting).where(
                OrgSetting.org_id == org_id,
                OrgSetting.field_key == field_key,
            )
        )
        org_row = result.scalar_one_or_none()
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
    result = await session.execute(
        select(OrgSetting).where(
            OrgSetting.org_id == org_id,
            OrgSetting.field_key == field_key,
        )
    )
    org_row = result.scalar_one_or_none()
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

    Org-Set fields use org value (or system baseline). All others follow the
    full User → Org → System chain. Returned dict always covers all SYSTEM_BASELINE
    keys; values are non-None (system baseline covers all known keys).
    """
    org_rows = (
        await session.execute(select(OrgSetting).where(OrgSetting.org_id == org_id))
    ).scalars().all()
    user_rows = (
        await session.execute(select(UserSetting).where(UserSetting.user_id == user_id))
    ).scalars().all()

    org_map = {r.field_key: r.value for r in org_rows}
    user_map = {r.field_key: r.value for r in user_rows}

    resolved: dict[str, str | None] = {}
    for key in SYSTEM_BASELINE:
        if key in ORG_SET_FIELDS:
            resolved[key] = org_map.get(key, SYSTEM_BASELINE[key])
        elif key in user_map:
            resolved[key] = user_map[key]
        elif key in org_map:
            resolved[key] = org_map[key]
        else:
            resolved[key] = SYSTEM_BASELINE[key]
    return resolved
