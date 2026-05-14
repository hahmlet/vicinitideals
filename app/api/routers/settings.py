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
from app.models.settings import OrgDealTypeDefault, OrgSetting, UserDealTypeDefault, UserSetting
from app.settings.defaults import ORG_SET_FIELDS, SYSTEM_BASELINE
from app.settings.resolver import resolve_all_defaults, resolve_default, resolve_timeline_defaults

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


# ---------------------------------------------------------------------------
# Timeline defaults — per-deal-type milestone configuration
# ---------------------------------------------------------------------------


@router.get("/timeline-defaults")
async def get_timeline_defaults(
    current_user_id: CurrentUserId,
    session: DBSession,
) -> dict[str, Any]:
    """Resolve full timeline defaults template for current user/org."""
    user = await _get_user_or_401(current_user_id, session)
    return await resolve_timeline_defaults(current_user_id, user.org_id, session)


@router.put("/timeline-defaults/org", response_class=JSONResponse)
async def batch_upsert_org_timeline_defaults(
    request: Request,
    current_user_id: CurrentUserId,
    session: DBSession,
) -> dict[str, Any]:
    """Batch upsert org timeline defaults.

    Body shape:
    {
      "acquisition": {"offer_made": {"included": true, "duration_days": 14, ...}},
      "permissions": {"acquisition": {"construction": {"user_overridable": false}}}
    }
    """
    user = await _get_user_or_401(current_user_id, session)
    _require_org_admin(user)
    raw: dict = await request.json()

    permissions: dict = raw.pop("permissions", {}) or {}
    saved = 0

    for deal_type, milestones in raw.items():
        if not isinstance(milestones, dict):
            continue
        for milestone_type, cfg in milestones.items():
            if not isinstance(cfg, dict):
                continue

            perm_cfg = (permissions.get(deal_type) or {}).get(milestone_type) or {}
            user_overridable = bool(perm_cfg["user_overridable"]) if "user_overridable" in perm_cfg else None

            insert_kwargs: dict[str, Any] = {
                "id": uuid.uuid4(),
                "org_id": user.org_id,
                "deal_type": str(deal_type),
                "milestone_type": str(milestone_type),
                "updated_by": current_user_id,
            }
            update_set: dict[str, Any] = {"updated_by": current_user_id}

            for col in ("included", "duration_days", "starts_after_type", "offset_days"):
                if col in cfg:
                    insert_kwargs[col] = cfg[col]
                    update_set[col] = cfg[col]
            if user_overridable is not None:
                insert_kwargs["user_overridable"] = user_overridable
                update_set["user_overridable"] = user_overridable

            stmt = (
                pg_insert(OrgDealTypeDefault)
                .values(**insert_kwargs)
                .on_conflict_do_update(
                    constraint="uq_org_deal_type_defaults",
                    set_=update_set,
                )
            )
            await session.execute(stmt)
            saved += 1

    await session.commit()
    log.info("org_timeline_defaults.upsert org=%s saved=%s", user.org_id, saved)
    return {"ok": True, "saved": saved}


@router.put("/timeline-defaults/user", response_class=JSONResponse)
async def batch_upsert_user_timeline_defaults(
    request: Request,
    current_user_id: CurrentUserId,
    session: DBSession,
) -> dict[str, Any]:
    """Batch upsert user timeline defaults.

    Body shape: same as org, without 'permissions' key.
    Rows where org has user_overridable=False are silently skipped.
    """
    user = await _get_user_or_401(current_user_id, session)
    raw: dict = await request.json()

    # Load org overridable flags
    org_rows = (
        await session.execute(
            select(OrgDealTypeDefault).where(OrgDealTypeDefault.org_id == user.org_id)
        )
    ).scalars().all()
    org_lock_map: dict[tuple, bool] = {
        (r.deal_type, r.milestone_type): r.user_overridable for r in org_rows
    }

    saved = 0
    for deal_type, milestones in raw.items():
        if not isinstance(milestones, dict):
            continue
        for milestone_type, cfg in milestones.items():
            if not isinstance(cfg, dict):
                continue
            # Respect org lock
            if not org_lock_map.get((deal_type, milestone_type), True):
                continue

            insert_kwargs: dict[str, Any] = {
                "id": uuid.uuid4(),
                "user_id": current_user_id,
                "org_id": user.org_id,
                "deal_type": str(deal_type),
                "milestone_type": str(milestone_type),
            }
            update_set: dict[str, Any] = {}

            for col in ("included", "duration_days", "starts_after_type", "offset_days"):
                if col in cfg:
                    insert_kwargs[col] = cfg[col]
                    update_set[col] = cfg[col]

            if not update_set:
                continue

            stmt = (
                pg_insert(UserDealTypeDefault)
                .values(**insert_kwargs)
                .on_conflict_do_update(
                    constraint="uq_user_deal_type_defaults",
                    set_=update_set,
                )
            )
            await session.execute(stmt)
            saved += 1

    await session.commit()
    log.info("user_timeline_defaults.upsert user=%s saved=%s", current_user_id, saved)
    return {"ok": True, "saved": saved}


# ---------------------------------------------------------------------------
# Source Vehicles — saved capital source presets
# ---------------------------------------------------------------------------

from sqlalchemy.exc import IntegrityError as _IntegrityError  # noqa: E402

from app.models.capital import CapitalModule as _CapitalModule  # noqa: E402
from app.models.source_vehicle import SourceVehicle as _OSV, SourceVehicle as _USV  # noqa: E402


def _sv_body_to_jsonb(body: dict) -> tuple[dict, dict, dict]:
    """Convert flat API body to (source_config, carry_config, exit_config) JSONB dicts."""
    source: dict = {}
    if body.get("interest_rate_pct") is not None:
        source["interest_rate_pct"] = float(body["interest_rate_pct"])
    if body.get("ltv_pct") is not None:
        source["ltv_pct"] = float(body["ltv_pct"])
    if body.get("amort_term_years") is not None:
        source["amort_term_years"] = int(body["amort_term_years"])
    if body.get("hold_term_years") is not None:
        source["hold_term_years"] = int(body["hold_term_years"])
    if body.get("dscr_min") is not None:
        source["dscr_min"] = float(body["dscr_min"])
    if body.get("draw_every_n_months") is not None:
        source["draw_every_n_months"] = int(body["draw_every_n_months"])
    if body.get("draw_active_from_milestone"):
        source["draw_active_from_milestone"] = body["draw_active_from_milestone"]
    if body.get("draw_active_from_offset_days") is not None:
        source["draw_active_from_offset_days"] = int(body["draw_active_from_offset_days"])

    carry: dict = {}
    constr_ct = body.get("construction_carry_type")
    oper_ct = body.get("operation_carry_type")
    if constr_ct or oper_ct:
        phases = []
        if constr_ct:
            phases.append({"name": "construction", "carry_type": constr_ct})
        if oper_ct:
            phases.append({"name": "operation", "carry_type": oper_ct})
        carry["phases"] = phases

    exit_cfg: dict = {}
    if body.get("exit_type"):
        exit_cfg["exit_type"] = body["exit_type"]

    return source or None, carry or None, exit_cfg or None


@router.get("/source-vehicles")
async def list_source_vehicles(
    current_user_id: CurrentUserId,
    session: DBSession,
) -> JSONResponse:
    """Return org + user vehicles for the current user (used by wizard dropdown)."""
    user = await _get_user_or_401(current_user_id, session)
    from app.models.source_vehicle import SourceVehicle as _SV_list
    all_vs = (
        await session.execute(
            select(_SV_list).where(
                ((_SV_list.scope == "org") & (_SV_list.owner_id == user.org_id)) |
                ((_SV_list.scope == "user") & (_SV_list.owner_id == user.id))
            ).order_by(_SV_list.scope.desc(), _SV_list.label)
        )
    ).scalars().all()

    result = [
        {
            "id": str(v.id),
            "name": v.label,
            "vehicle_type": v.vehicle_type,
            "equity_role": v.equity_role,
            "funder_type": v.funder_type,  # compat shim
            "owner": v.scope,
            "source_config": v.source_config,
            "carry_config": v.carry_config,
            "exit_config": v.exit_config,
        }
        for v in all_vs
    ]
    return JSONResponse(result)


@router.post("/source-vehicles/org")
async def create_org_source_vehicle(
    request: Request,
    current_user_id: CurrentUserId,
    session: DBSession,
) -> JSONResponse:
    user = await _get_user_or_401(current_user_id, session)
    _require_org_admin(user)
    body = await request.json()
    name = (body.get("name") or "").strip()
    vehicle_type = (body.get("vehicle_type") or body.get("funder_type") or "").strip()
    if not name or not vehicle_type:
        raise HTTPException(status_code=400, detail="name and vehicle_type are required")
    source_cfg, carry_cfg, exit_cfg = _sv_body_to_jsonb(body)
    from app.models.source_vehicle import SourceVehicle as _SV_create
    vehicle = _SV_create(
        scope="org",
        owner_id=user.org_id,
        label=name,
        vehicle_type=vehicle_type,
        equity_role=body.get("equity_role"),
        source_config=source_cfg,
        carry_config=carry_cfg,
        exit_config=exit_cfg,
        active_phase_start=body.get("active_phase_start"),
        active_phase_end=body.get("active_phase_end"),
        created_by=user.id,
        updated_by=user.id,
    )
    session.add(vehicle)
    try:
        await session.commit()
        await session.refresh(vehicle)
    except _IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="A vehicle with that name already exists in this org.")
    return JSONResponse({"id": str(vehicle.id), "name": vehicle.label, "vehicle_type": vehicle.vehicle_type})


@router.put("/source-vehicles/org/{vehicle_id}")
async def update_org_source_vehicle(
    vehicle_id: uuid.UUID,
    request: Request,
    current_user_id: CurrentUserId,
    session: DBSession,
) -> JSONResponse:
    user = await _get_user_or_401(current_user_id, session)
    _require_org_admin(user)
    from app.models.source_vehicle import SourceVehicle as _SV_upd
    vehicle = await session.get(_SV_upd, vehicle_id)
    if vehicle is None or vehicle.scope != "org" or vehicle.owner_id != user.org_id:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    body = await request.json()
    name = (body.get("name") or "").strip()
    vehicle_type = (body.get("vehicle_type") or body.get("funder_type") or "").strip()
    if not name or not vehicle_type:
        raise HTTPException(status_code=400, detail="name and vehicle_type are required")
    vehicle.label = name
    vehicle.vehicle_type = vehicle_type
    if "equity_role" in body:
        vehicle.equity_role = body["equity_role"]
    vehicle.updated_by = user.id
    vehicle.source_config, vehicle.carry_config, vehicle.exit_config = _sv_body_to_jsonb(body)
    try:
        await session.commit()
    except _IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="A vehicle with that name already exists in this org.")
    return JSONResponse({"ok": True})


@router.delete("/source-vehicles/org/{vehicle_id}")
async def delete_org_source_vehicle(
    vehicle_id: uuid.UUID,
    current_user_id: CurrentUserId,
    session: DBSession,
) -> JSONResponse:
    user = await _get_user_or_401(current_user_id, session)
    _require_org_admin(user)
    from app.models.source_vehicle import SourceVehicle as _SV_del
    vehicle = await session.get(_SV_del, vehicle_id)
    if vehicle is None or vehicle.scope != "org" or vehicle.owner_id != user.org_id:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    await session.delete(vehicle)
    await session.commit()
    return JSONResponse({"ok": True})


@router.post("/source-vehicles/user")
async def create_user_source_vehicle(
    request: Request,
    current_user_id: CurrentUserId,
    session: DBSession,
) -> JSONResponse:
    user = await _get_user_or_401(current_user_id, session)
    body = await request.json()
    name = (body.get("name") or "").strip()
    vehicle_type = (body.get("vehicle_type") or body.get("funder_type") or "").strip()
    if not name or not vehicle_type:
        raise HTTPException(status_code=400, detail="name and vehicle_type are required")
    source_cfg, carry_cfg, exit_cfg = _sv_body_to_jsonb(body)
    from app.models.source_vehicle import SourceVehicle as _SV_ucreate
    vehicle = _SV_ucreate(
        scope="user",
        owner_id=user.id,
        label=name,
        vehicle_type=vehicle_type,
        equity_role=body.get("equity_role"),
        source_config=source_cfg,
        carry_config=carry_cfg,
        exit_config=exit_cfg,
        active_phase_start=body.get("active_phase_start"),
        active_phase_end=body.get("active_phase_end"),
    )
    session.add(vehicle)
    try:
        await session.commit()
        await session.refresh(vehicle)
    except _IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="You already have a vehicle with that name.")
    return JSONResponse({"id": str(vehicle.id), "name": vehicle.label, "vehicle_type": vehicle.vehicle_type})


@router.put("/source-vehicles/user/{vehicle_id}")
async def update_user_source_vehicle(
    vehicle_id: uuid.UUID,
    request: Request,
    current_user_id: CurrentUserId,
    session: DBSession,
) -> JSONResponse:
    user = await _get_user_or_401(current_user_id, session)
    from app.models.source_vehicle import SourceVehicle as _SV_uupd
    vehicle = await session.get(_SV_uupd, vehicle_id)
    if vehicle is None or vehicle.scope != "user" or vehicle.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    body = await request.json()
    name = (body.get("name") or "").strip()
    vehicle_type = (body.get("vehicle_type") or body.get("funder_type") or "").strip()
    if not name or not vehicle_type:
        raise HTTPException(status_code=400, detail="name and vehicle_type are required")
    vehicle.label = name
    vehicle.vehicle_type = vehicle_type
    if "equity_role" in body:
        vehicle.equity_role = body["equity_role"]
    vehicle.source_config, vehicle.carry_config, vehicle.exit_config = _sv_body_to_jsonb(body)
    try:
        await session.commit()
    except _IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="You already have a vehicle with that name.")
    return JSONResponse({"ok": True})


@router.delete("/source-vehicles/user/{vehicle_id}")
async def delete_user_source_vehicle(
    vehicle_id: uuid.UUID,
    current_user_id: CurrentUserId,
    session: DBSession,
) -> JSONResponse:
    user = await _get_user_or_401(current_user_id, session)
    from app.models.source_vehicle import SourceVehicle as _SV_udel
    vehicle = await session.get(_SV_udel, vehicle_id)
    if vehicle is None or vehicle.scope != "user" or vehicle.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    await session.delete(vehicle)
    await session.commit()
    return JSONResponse({"ok": True})
