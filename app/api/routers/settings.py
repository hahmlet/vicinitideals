"""Org & user defaults API.

Routes
------
GET  /api/settings/org                  list all org settings (org admin only)
PUT  /api/settings/org/{field_key}      upsert one org setting (org admin only)
GET  /api/settings/user                 list current user's settings
PUT  /api/settings/user/{field_key}     upsert one user setting
GET  /api/settings/resolve              resolve all defaults for current user/org
GET  /api/settings/resolve/{field_key}  resolve one field's default
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.api.deps import CurrentUserId, DBSession
from app.models.org import User
from app.models.settings import OrgSetting, UserSetting
from app.settings.defaults import ORG_SET_FIELDS, SYSTEM_BASELINE
from app.settings.resolver import resolve_all_defaults, resolve_default

log = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])

_SAVED_HTML = '<span style="color:var(--success,green)">Saved ✓</span>'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_user_or_401(user_id: uuid.UUID, session: DBSession) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def _require_org_admin(user: User) -> None:
    if not getattr(user, "is_org_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Org admin access required",
        )


# ---------------------------------------------------------------------------
# Org settings — org admin only
# ---------------------------------------------------------------------------


@router.get("/org")
async def list_org_settings(
    current_user_id: CurrentUserId,
    session: DBSession,
) -> list[dict[str, Any]]:
    """Return all org settings for the current user's org."""
    user = await _get_user_or_401(current_user_id, session)
    _require_org_admin(user)

    rows = (
        await session.execute(
            select(OrgSetting).where(OrgSetting.org_id == user.org_id)
        )
    ).scalars().all()

    return [
        {
            "field_key": r.field_key,
            "value": r.value,
            "user_overridable": r.user_overridable,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]


@router.put("/org/{field_key}", response_class=HTMLResponse)
async def upsert_org_setting(
    field_key: str,
    current_user_id: CurrentUserId,
    session: DBSession,
    value: Annotated[str, Form()],
) -> HTMLResponse:
    """Upsert one org setting (form-encoded). Returns HTMX-friendly saved indicator."""
    user = await _get_user_or_401(current_user_id, session)
    _require_org_admin(user)

    stmt = (
        pg_insert(OrgSetting)
        .values(
            id=uuid.uuid4(),
            org_id=user.org_id,
            field_key=field_key,
            value=value,
            updated_by=current_user_id,
        )
        .on_conflict_do_update(
            constraint="uq_org_settings_org_field",
            set_={"value": value, "updated_by": current_user_id},
        )
    )
    await session.execute(stmt)
    await session.commit()
    log.info("org_setting.upsert org=%s field=%s", user.org_id, field_key)
    return HTMLResponse(_SAVED_HTML)


# ---------------------------------------------------------------------------
# Org batch upsert — saves multiple fields in one request
# ---------------------------------------------------------------------------


@router.put("/org", response_class=JSONResponse)
async def batch_upsert_org_settings(
    request: Request,
    current_user_id: CurrentUserId,
    session: DBSession,
) -> dict[str, Any]:
    """Batch-upsert org settings.

    Accepts either the legacy flat body ``{field_key: value}`` or the new
    shape ``{values: {field_key: value}, permissions: {field_key: bool}}``.
    When ``permissions`` is present, ``user_overridable`` is updated for those
    fields.  ORG_SET_FIELDS entries in ``permissions`` are silently ignored
    (those fields are always locked at the code level).
    """
    user = await _get_user_or_401(current_user_id, session)
    _require_org_admin(user)
    raw: dict = await request.json()

    # Support both legacy flat shape and new {values, permissions} shape.
    if "values" in raw or "permissions" in raw:
        values: dict[str, str] = raw.get("values") or {}
        permissions: dict[str, bool] = raw.get("permissions") or {}
    else:
        values = raw
        permissions = {}

    # Collect all field_keys that need touching.
    all_keys = set(values) | set(permissions)

    for field_key in all_keys:
        insert_kwargs: dict[str, Any] = dict(
            id=uuid.uuid4(),
            org_id=user.org_id,
            field_key=str(field_key),
            updated_by=current_user_id,
        )
        update_set: dict[str, Any] = {"updated_by": current_user_id}

        if field_key in values:
            insert_kwargs["value"] = str(values[field_key])
            update_set["value"] = str(values[field_key])

        if field_key in permissions and field_key not in ORG_SET_FIELDS:
            insert_kwargs["user_overridable"] = bool(permissions[field_key])
            update_set["user_overridable"] = bool(permissions[field_key])

        # value is NOT NULL — skip if we have no value and no existing row.
        if "value" not in insert_kwargs:
            # permissions-only update: only update if row already exists.
            from sqlalchemy import update as sa_update
            await session.execute(
                sa_update(OrgSetting)
                .where(
                    OrgSetting.org_id == user.org_id,
                    OrgSetting.field_key == field_key,
                )
                .values(**{k: v for k, v in update_set.items() if k != "updated_by"})
            )
            continue

        stmt = (
            pg_insert(OrgSetting)
            .values(**insert_kwargs)
            .on_conflict_do_update(
                constraint="uq_org_settings_org_field",
                set_=update_set,
            )
        )
        await session.execute(stmt)

    await session.commit()
    log.info(
        "org_setting.batch_upsert org=%s values=%s perms=%s",
        user.org_id, list(values.keys()), list(permissions.keys()),
    )
    return {"ok": True, "saved": len(all_keys)}


# ---------------------------------------------------------------------------
# User batch upsert — saves multiple fields in one request
# ---------------------------------------------------------------------------


@router.put("/user", response_class=JSONResponse)
async def batch_upsert_user_settings(
    request: Request,
    current_user_id: CurrentUserId,
    session: DBSession,
) -> dict[str, Any]:
    """Batch-upsert user settings from a JSON {field_key: value} body.

    Fields in ORG_SET_FIELDS or where the org has set user_overridable=False
    are silently skipped — the client should not send them, but this enforces
    the permission server-side.
    """
    user = await _get_user_or_401(current_user_id, session)
    body: dict[str, str] = await request.json()

    # Load org overridable flags in one query.
    org_rows = (
        await session.execute(
            select(OrgSetting).where(OrgSetting.org_id == user.org_id)
        )
    ).scalars().all()
    overridable_map = {r.field_key: r.user_overridable for r in org_rows}

    saved = 0
    for field_key, value in body.items():
        if field_key in ORG_SET_FIELDS:
            continue
        if not overridable_map.get(field_key, True):
            continue
        stmt = (
            pg_insert(UserSetting)
            .values(
                id=uuid.uuid4(),
                user_id=current_user_id,
                org_id=user.org_id,
                field_key=str(field_key),
                value=str(value),
            )
            .on_conflict_do_update(
                constraint="uq_user_settings_user_field",
                set_={"value": str(value)},
            )
        )
        await session.execute(stmt)
        saved += 1

    await session.commit()
    log.info("user_setting.batch_upsert user=%s fields=%s", current_user_id, list(body.keys()))
    return {"ok": True, "saved": saved}


# ---------------------------------------------------------------------------
# User settings — any authenticated user
# ---------------------------------------------------------------------------


@router.get("/user")
async def list_user_settings(
    current_user_id: CurrentUserId,
    session: DBSession,
) -> list[dict[str, Any]]:
    """Return all settings for the current user."""
    rows = (
        await session.execute(
            select(UserSetting).where(UserSetting.user_id == current_user_id)
        )
    ).scalars().all()

    return [
        {
            "field_key": r.field_key,
            "value": r.value,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]


@router.put("/user/{field_key}", response_class=HTMLResponse)
async def upsert_user_setting(
    field_key: str,
    current_user_id: CurrentUserId,
    session: DBSession,
    value: Annotated[str, Form()],
) -> HTMLResponse:
    """Upsert one user setting (form-encoded). Returns HTMX-friendly saved indicator."""
    user = await _get_user_or_401(current_user_id, session)

    stmt = (
        pg_insert(UserSetting)
        .values(
            id=uuid.uuid4(),
            user_id=current_user_id,
            org_id=user.org_id,
            field_key=field_key,
            value=value,
        )
        .on_conflict_do_update(
            constraint="uq_user_settings_user_field",
            set_={"value": value},
        )
    )
    await session.execute(stmt)
    await session.commit()
    return HTMLResponse(_SAVED_HTML)


# ---------------------------------------------------------------------------
# Resolution — read-only endpoints reflecting full resolution chain
# ---------------------------------------------------------------------------


@router.get("/resolve")
async def resolve_all(
    current_user_id: CurrentUserId,
    session: DBSession,
) -> dict[str, str | None]:
    """Resolve all known defaults for the current user/org context."""
    user = await _get_user_or_401(current_user_id, session)
    return await resolve_all_defaults(current_user_id, user.org_id, session)


@router.get("/resolve/{field_key}")
async def resolve_one(
    field_key: str,
    current_user_id: CurrentUserId,
    session: DBSession,
) -> dict[str, str | None]:
    """Resolve a single field's default for the current user/org context."""
    if field_key not in SYSTEM_BASELINE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown field_key: {field_key}",
        )
    user = await _get_user_or_401(current_user_id, session)
    resolved_value = await resolve_default(field_key, current_user_id, user.org_id, session)
    return {"field_key": field_key, "value": resolved_value}
