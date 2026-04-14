"""Internal tools routes — Zone Painter and future tooling."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from vicinitideals.api.deps import DBSession
from vicinitideals.api.routers.ui import (
    _base_ctx,
    _get_address_issues_count,
    _get_dedup_count,
    _get_user,
    templates,
)

router = APIRouter(tags=["tools"])

# ---------------------------------------------------------------------------
# Whitelisted parcel fields the painter can write
# ---------------------------------------------------------------------------
PAINTER_FIELDS: dict[str, str] = {
    "zoning_code": "zoning_code",
    "enterprise_zone_name": "enterprise_zone_name",
    "cultural_sensitivity": "cultural_sensitivity",
}

PAINTER_MODES = [
    {"id": "zoning_code",          "label": "Zoning"},
    {"id": "enterprise_zone_name", "label": "Enterprise Zone"},
    {"id": "cultural_sensitivity", "label": "Cultural Sensitivity"},
]

# Max parcels returned per viewport request (protects browser from OOM)
MAX_PAINTER_FEATURES = 3000


def _validate_painter_field(field: str) -> str:
    col = PAINTER_FIELDS.get(field)
    if not col:
        raise HTTPException(status_code=400, detail=f"Unknown field '{field}'")
    return col


def _jurisdiction_clause(jurisdiction: str) -> tuple[str, dict]:
    """Return (SQL WHERE snippet, params dict) for a jurisdiction value.

    Special values:
      unincorporated_multnomah  — jurisdiction='unincorporated', county='multnomah'
      unincorporated_clackamas  — jurisdiction='unincorporated', county='clackamas'
    All others match jurisdiction column directly (case-insensitive).
    """
    if jurisdiction == "unincorporated_multnomah":
        return "LOWER(jurisdiction) = 'unincorporated' AND LOWER(county) = 'multnomah'", {}
    if jurisdiction == "unincorporated_clackamas":
        return "LOWER(jurisdiction) = 'unincorporated' AND LOWER(county) = 'clackamas'", {}
    return "LOWER(jurisdiction) = LOWER(:jurisdiction)", {"jurisdiction": jurisdiction}


def _bbox_clause(bbox: str | None) -> tuple[str, dict]:
    """Parse 'west,south,east,north' bbox string into a SQL clause + params.

    Uses the first vertex of the outer ring as a cheap proxy for the parcel
    centroid — no PostGIS required. Works for both Polygon and MultiPolygon.
    Returns empty string + {} if bbox is absent or malformed.
    """
    if not bbox:
        return "", {}
    parts = bbox.split(",")
    if len(parts) != 4:
        return "", {}
    try:
        west, south, east, north = (float(p) for p in parts)
    except ValueError:
        return "", {}

    clause = """
        AND CASE geometry->>'type'
              WHEN 'Polygon'      THEN (geometry->'coordinates'->0->0->>0)::float
              WHEN 'MultiPolygon' THEN (geometry->'coordinates'->0->0->0->>0)::float
              ELSE NULL
            END BETWEEN :bbox_west AND :bbox_east
        AND CASE geometry->>'type'
              WHEN 'Polygon'      THEN (geometry->'coordinates'->0->0->>1)::float
              WHEN 'MultiPolygon' THEN (geometry->'coordinates'->0->0->0->>1)::float
              ELSE NULL
            END BETWEEN :bbox_south AND :bbox_north
    """
    params = {"bbox_west": west, "bbox_south": south, "bbox_east": east, "bbox_north": north}
    return clause, params


# ---------------------------------------------------------------------------
# Zone Painter page
# ---------------------------------------------------------------------------

@router.get("/tools/zone-painter", response_class=HTMLResponse)
async def zone_painter_page(request: Request, session: DBSession) -> HTMLResponse:
    user_id = str(getattr(request.state, "user_id", None) or "")
    user = await _get_user(session, user_id)
    dedup_count = await _get_dedup_count(session)
    address_issues_count = await _get_address_issues_count(session)
    return templates.TemplateResponse(
        request,
        "zone_painter.html",
        {
            "modes": PAINTER_MODES,
            **_base_ctx(user, dedup_count, "tools", address_issues_count),
        },
    )


# ---------------------------------------------------------------------------
# Zone Painter data endpoints
# ---------------------------------------------------------------------------

@router.get("/tools/zone-painter/parcels.geojson")
async def painter_parcels(
    session: DBSession,
    field: str = Query(default="zoning_code"),
    jurisdiction: str = Query(default="fairview"),
    bbox: str | None = Query(default=None),
) -> JSONResponse:
    col = _validate_painter_field(field)
    j_clause, j_params = _jurisdiction_clause(jurisdiction)
    b_clause, b_params = _bbox_clause(bbox)

    rows = await session.execute(
        text(f"""
            SELECT
                id::text,
                apn,
                {col}              AS painted_value,
                address_normalized,
                geometry
            FROM parcels
            WHERE geometry IS NOT NULL
              AND {j_clause}
              {b_clause}
            ORDER BY apn
            LIMIT {MAX_PAINTER_FEATURES}
        """),
        {**j_params, **b_params},
    )
    features = []
    for row in rows.mappings():
        geom = row["geometry"]
        if geom is None:
            continue
        if isinstance(geom, str):
            try:
                geom = json.loads(geom)
            except Exception:
                continue
        features.append({
            "type": "Feature",
            "id": row["id"],
            "geometry": geom,
            "properties": {
                "id": row["id"],
                "apn": row["apn"],
                "painted_value": row["painted_value"],
                "address": row["address_normalized"] or "",
            },
        })
    return JSONResponse({
        "type": "FeatureCollection",
        "features": features,
        "truncated": len(features) == MAX_PAINTER_FEATURES,
    })


class PainterAssignRequest(BaseModel):
    parcel_ids: list[str]
    field_name: str
    value: str
    jurisdiction: str = "fairview"


@router.post("/tools/zone-painter/assign")
async def painter_assign(req: PainterAssignRequest, session: DBSession) -> dict[str, Any]:
    if not req.parcel_ids:
        raise HTTPException(status_code=400, detail="No parcel IDs provided")
    col = _validate_painter_field(req.field_name)
    value = req.value.strip()
    if not value:
        raise HTTPException(status_code=400, detail="Value is required")

    ids = [uuid.UUID(pid) for pid in req.parcel_ids]
    result = await session.execute(
        text(f"UPDATE parcels SET {col} = :value WHERE id = ANY(:ids)"),
        {"value": value, "ids": ids},
    )
    await session.commit()
    return {"updated": result.rowcount, "field_name": req.field_name, "value": value}


@router.get("/tools/zone-painter/stats")
async def painter_stats(
    session: DBSession,
    field: str = Query(default="zoning_code"),
    jurisdiction: str = Query(default="fairview"),
) -> dict[str, Any]:
    col = _validate_painter_field(field)
    j_clause, j_params = _jurisdiction_clause(jurisdiction)
    row = await session.execute(
        text(f"""
            SELECT
                COUNT(*)                                   AS total,
                COUNT(*) FILTER (WHERE {col} IS NOT NULL)  AS painted
            FROM parcels
            WHERE geometry IS NOT NULL
              AND {j_clause}
        """),
        j_params,
    )
    r = row.mappings().one()
    return {"total": r["total"], "painted": r["painted"], "field": field}
