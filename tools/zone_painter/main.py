"""Fairview Zone Painter — standalone tool on its own port.

Loads Fairview parcels from the main re-modeling DB, shows them on a Leaflet
map, and lets you ctrl+click / shift+drag select parcels and assign a value
to any whitelisted field in one pass.

Run:
    cd re-modeling
    python -m uvicorn tools.zone_painter.main:app --port 8765 --reload

Then open http://localhost:8765
"""

from __future__ import annotations

import json
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# DB connection — reads DATABASE_URL from re-modeling/.env
# ---------------------------------------------------------------------------
_ENV_FILE = Path(__file__).parent.parent.parent / ".env"
load_dotenv(_ENV_FILE)

_raw_url = os.environ.get(
    "DATABASE_URL",
    "postgresql://vicinitideals:changeme@localhost:5432/vicinitideals",
)
DATABASE_URL = _raw_url.replace("postgresql+asyncpg://", "postgresql://")

_pool: asyncpg.Pool | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=5)
    yield
    await _pool.close()


app = FastAPI(lifespan=lifespan, title="Fairview Zone Painter")

# ---------------------------------------------------------------------------
# Allowed fields — whitelist for /assign and /parcels.geojson
# Maps field_name -> SQL column name (same here, but explicit for safety)
# ---------------------------------------------------------------------------
ALLOWED_FIELDS: dict[str, str] = {
    "zoning_code": "zoning_code",
    "enterprise_zone_name": "enterprise_zone_name",
    "cultural_sensitivity": "cultural_sensitivity",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _geom_to_dict(raw) -> dict | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return None


def _validate_field(field: str) -> str:
    """Return the SQL column name or raise 400."""
    col = ALLOWED_FIELDS.get(field)
    if not col:
        raise HTTPException(status_code=400, detail=f"Unknown field '{field}'. Allowed: {list(ALLOWED_FIELDS)}")
    return col


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index():
    return (Path(__file__).parent / "painter.html").read_text(encoding="utf-8")


@app.get("/parcels.geojson")
async def get_parcels(field: str = Query(default="zoning_code")):
    """Return all Fairview parcels with polygon geometry.

    `field` controls which painted-value column is returned in properties
    so the frontend knows what's already assigned in the current mode.
    """
    col = _validate_field(field)
    # Use f-string only for the whitelisted column name — safe against injection
    rows = await _pool.fetch(
        f"""
        SELECT
            id::text,
            apn,
            {col}       AS painted_value,
            address_normalized,
            geometry
        FROM parcels
        WHERE geometry IS NOT NULL
          AND LOWER(jurisdiction) = 'fairview'
        ORDER BY apn
        """
    )
    features = []
    for row in rows:
        geom = _geom_to_dict(row["geometry"])
        if not geom:
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
    return JSONResponse({"type": "FeatureCollection", "features": features})


class AssignRequest(BaseModel):
    parcel_ids: list[str]
    field_name: str
    value: str


@app.post("/assign")
async def assign(req: AssignRequest):
    """Bulk-assign a value to a whitelisted field for a list of parcel UUIDs."""
    if not req.parcel_ids:
        raise HTTPException(status_code=400, detail="No parcel IDs provided")
    col = _validate_field(req.field_name)
    value = req.value.strip()
    if not value:
        raise HTTPException(status_code=400, detail="Value is required")

    ids = [uuid.UUID(pid) for pid in req.parcel_ids]
    result = await _pool.execute(
        f"UPDATE parcels SET {col} = $1 WHERE id = ANY($2::uuid[])",
        value,
        ids,
    )
    count = int(result.split()[-1])
    return {"updated": count, "field_name": req.field_name, "value": value}


@app.get("/stats")
async def stats(field: str = Query(default="zoning_code")):
    """Progress summary for the active mode field."""
    col = _validate_field(field)
    row = await _pool.fetchrow(
        f"""
        SELECT
            COUNT(*)                                        AS total,
            COUNT(*) FILTER (WHERE {col} IS NOT NULL)      AS painted
        FROM parcels
        WHERE geometry IS NOT NULL
          AND LOWER(jurisdiction) = 'fairview'
        """
    )
    return {"total": row["total"], "painted": row["painted"], "field": field}
