"""
assign_zoning_bulk.py — Bulk spatial-join zoning data to parcels for all configured cities.

For each jurisdiction with a cached zoning polygon layer, computes a representative
point from each parcel's RLIS geometry and does point-in-polygon matching against
the cached zoning polygons. Updates zoning_code + zoning_description in bulk.

Usage:
    python tools/gis_cache/assign_zoning_bulk.py
    python tools/gis_cache/assign_zoning_bulk.py --overwrite   # also replace existing codes
    python tools/gis_cache/assign_zoning_bulk.py --dry-run
    python tools/gis_cache/assign_zoning_bulk.py --only gresham lake_oswego
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Jurisdiction → zoning layer config
# zone_field: property key for the zoning code
# desc_field: property key for the human-readable description (None = skip)
# ---------------------------------------------------------------------------

class ZoningConfig(NamedTuple):
    city_dir: str           # subdirectory in gis_cache
    geojson_file: str       # filename
    zone_field: str         # property key → zoning_code
    desc_field: str | None  # property key → zoning_description
    db_jurisdiction: str | None = None  # override if DB value differs from dict key

ZONING_CONFIGS: dict[str, ZoningConfig] = {
    "gresham":      ZoningConfig("gresham",      "city_zoning.geojson",             "ZONE",              "DESCRIPT"),
    "troutdale":    ZoningConfig("troutdale",     "zoning_troutdale.geojson",        "zonecode",          "description"),
    "oregon_city":  ZoningConfig("oregon_city",   "zoning_oregon_city.geojson",      "ZONE",              None,            "oregon city"),
    "lake_oswego":  ZoningConfig("lake_oswego",   "zoning_lake_oswego.geojson",      "LAYER",             None,            "lake oswego"),
    "west_linn":    ZoningConfig("west_linn",     "zoning_west_linn.geojson",        "ZONE",              "ZONINGDISTRICT","west linn"),
    "happy_valley": ZoningConfig("happy_valley",  "zoning_happy_valley.geojson",     "ZONE",              None,            "happy valley"),
    "milwaukie":    ZoningConfig("milwaukie",     "zoning_milwaukie.geojson",        "ZONE",              "DESCRIPTIO"),
    "wood_village": ZoningConfig("wood_village",  "zoning_wood_village.geojson",     "Labeling",          "Name",          "wood village"),
    "wilsonville":  ZoningConfig("wilsonville",   "zoning_wilsonville.geojson",      "ZONE_CODE",         None),
    "tualatin":     ZoningConfig("tualatin",      "zoning_tualatin.geojson",         "PLANDIST.CZONE",    "PLANDIST.ZONE_NAME"),
    "gladstone":    ZoningConfig("gladstone",     "zoning_gladstone.geojson",        "ZONE",              "ZONE_CLASS"),
}


def _resolve_root() -> Path:
    if env := os.environ.get("GIS_CACHE_ROOT"):
        return Path(env)
    try:
        candidate = Path(__file__).resolve().parents[2] / "data" / "gis_cache"
        if candidate.parent.exists():
            return candidate
    except IndexError:
        pass
    return Path("/app/data/gis_cache")


ROOT = _resolve_root()


# ---------------------------------------------------------------------------
# Point-in-polygon (ray casting)
# ---------------------------------------------------------------------------

def _point_in_ring(px: float, py: float, ring: list) -> bool:
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _pip(px: float, py: float, geom: dict) -> bool:
    gtype = geom.get("type", "")
    coords = geom.get("coordinates", [])
    if gtype == "Polygon":
        if not coords or not _point_in_ring(px, py, coords[0]):
            return False
        return not any(_point_in_ring(px, py, h) for h in coords[1:])
    elif gtype == "MultiPolygon":
        for poly_rings in coords:
            if not poly_rings:
                continue
            if _point_in_ring(px, py, poly_rings[0]):
                if not any(_point_in_ring(px, py, h) for h in poly_rings[1:]):
                    return True
    return False


def _rep_point(geom: dict) -> tuple[float, float] | None:
    """Bbox midpoint of the first exterior ring — fast and avoids iterating all vertices."""
    gtype = geom.get("type", "")
    coords = geom.get("coordinates", [])
    try:
        if gtype == "Polygon" and coords:
            ring = coords[0]
        elif gtype == "MultiPolygon" and coords and coords[0]:
            ring = coords[0][0]
        elif gtype == "Point":
            return float(coords[0]), float(coords[1])
        else:
            return None
        xs = [c[0] for c in ring]
        ys = [c[1] for c in ring]
        return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    except (IndexError, TypeError, ZeroDivisionError):
        return None


def load_zoning_polygons(cfg: ZoningConfig) -> list[dict]:
    path = ROOT / cfg.city_dir / cfg.geojson_file
    with open(path) as f:
        data = json.load(f)
    polys = []
    for feat in data.get("features", []):
        props = feat.get("properties") or {}
        geom = feat.get("geometry")
        if not geom:
            continue
        zone = str(props.get(cfg.zone_field) or "").strip()
        desc = str(props.get(cfg.desc_field) or "").strip() if cfg.desc_field else None
        if not zone:
            continue
        coords_flat: list = []
        if geom["type"] == "Polygon":
            coords_flat = geom["coordinates"][0] if geom["coordinates"] else []
        elif geom["type"] == "MultiPolygon":
            for poly in geom["coordinates"]:
                if poly:
                    coords_flat.extend(poly[0])
        if not coords_flat:
            continue
        xs = [c[0] for c in coords_flat]
        ys = [c[1] for c in coords_flat]
        polys.append({
            "zone": zone,
            "desc": desc,
            "geometry": geom,
            "minx": min(xs), "miny": min(ys), "maxx": max(xs), "maxy": max(ys),
        })
    return polys


def lookup_zone(px: float, py: float, polys: list[dict]) -> tuple[str, str | None] | None:
    for p in polys:
        if not (p["minx"] <= px <= p["maxx"] and p["miny"] <= py <= p["maxy"]):
            continue
        if _pip(px, py, p["geometry"]):
            return p["zone"], p["desc"]
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run_jurisdiction(
    conn,
    jurisdiction: str,
    cfg: ZoningConfig,
    overwrite: bool,
    dry_run: bool,
) -> dict[str, int]:
    path = ROOT / cfg.city_dir / cfg.geojson_file
    if not path.exists():
        print(f"  [{jurisdiction}] SKIP — cache file not found: {path}")
        return {"matched": 0, "skipped": 0, "errors": 0}

    polys = load_zoning_polygons(cfg)
    if not polys:
        print(f"  [{jurisdiction}] SKIP — 0 zoning polygons in cache")
        return {"matched": 0, "skipped": 0, "errors": 0}

    db_jur = cfg.db_jurisdiction or jurisdiction
    overwrite_clause = "" if overwrite else "AND zoning_code IS NULL"
    rows = await conn.fetch(f"""
        SELECT id::text, geometry::text
        FROM parcels
        WHERE LOWER(jurisdiction) = LOWER($1)
          AND geometry IS NOT NULL
          {overwrite_clause}
    """, db_jur)

    matched = skipped = errors = 0
    updates: list[tuple[str, str | None, str]] = []

    for row in rows:
        try:
            geom = json.loads(row["geometry"]) if isinstance(row["geometry"], str) else row["geometry"]
            pt = _rep_point(geom)
            if pt is None:
                skipped += 1
                continue
            hit = lookup_zone(pt[0], pt[1], polys)
            if hit is None:
                skipped += 1
                continue
            updates.append((hit[0], hit[1], row["id"]))
            matched += 1
        except Exception as e:
            errors += 1

    print(f"  [{jurisdiction}] {len(rows)} parcels — matched={matched} skipped={skipped} errors={errors} ({len(polys)} zoning polys)")

    if dry_run or not updates:
        return {"matched": matched, "skipped": skipped, "errors": errors}

    BATCH = 1000
    for i in range(0, len(updates), BATCH):
        batch = updates[i:i + BATCH]
        await conn.executemany(
            "UPDATE parcels SET zoning_code=$1, zoning_description=$2 WHERE id=$3::uuid",
            batch,
        )

    return {"matched": matched, "skipped": skipped, "errors": errors}


async def main_async(jurisdictions: list[str], overwrite: bool, dry_run: bool) -> None:
    import asyncpg
    from vicinitideals.config import settings

    dsn = str(settings.database_url).replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)

    totals = {"matched": 0, "skipped": 0, "errors": 0}
    for jur in jurisdictions:
        cfg = ZONING_CONFIGS[jur]
        r = await run_jurisdiction(conn, jur, cfg, overwrite, dry_run)
        for k in totals:
            totals[k] += r[k]

    if not dry_run:
        await conn.execute("COMMIT")  # ensure flushed

    await conn.close()
    print(f"\nTotal: matched={totals['matched']} skipped={totals['skipped']} errors={totals['errors']}")
    if dry_run:
        print("(dry run — no changes written)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing zoning_code values")
    parser.add_argument("--only", nargs="+", metavar="JUR", help="Limit to specific jurisdictions")
    args = parser.parse_args()

    jurisdictions = args.only if args.only else list(ZONING_CONFIGS.keys())
    invalid = [j for j in jurisdictions if j not in ZONING_CONFIGS]
    if invalid:
        print(f"Unknown jurisdictions: {invalid}", file=sys.stderr)
        print(f"Available: {list(ZONING_CONFIGS.keys())}", file=sys.stderr)
        sys.exit(1)

    print(f"Assigning zoning for: {jurisdictions}")
    if args.dry_run:
        print("(dry run)")
    asyncio.run(main_async(jurisdictions, args.overwrite, args.dry_run))


if __name__ == "__main__":
    main()
