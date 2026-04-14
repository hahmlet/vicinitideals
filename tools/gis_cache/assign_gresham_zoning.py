"""
assign_gresham_zoning.py — Bulk-assign zoning_code/zoning_description to Gresham parcels.

Reads city_zoning.geojson (Gresham Planning/MapServer/4) and the parcels table.
For each Gresham parcel with geometry but no zoning_code, uses the first exterior
ring vertex as a representative point and does point-in-polygon against zoning
polygons, then bulk-updates the DB.

Uses synchronous psycopg2 and raw SQL for performance (22k parcels).

Usage:
    cd /app
    python tools/gis_cache/assign_gresham_zoning.py
    python tools/gis_cache/assign_gresham_zoning.py --overwrite  # also replace existing
    python tools/gis_cache/assign_gresham_zoning.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


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
ZONING_CACHE = ROOT / "gresham" / "city_zoning.geojson"


# ---------------------------------------------------------------------------
# Point-in-polygon (ray casting, no external deps)
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
        rings = coords
        if not rings or not _point_in_ring(px, py, rings[0]):
            return False
        return not any(_point_in_ring(px, py, h) for h in rings[1:])
    elif gtype == "MultiPolygon":
        for poly_rings in coords:
            if not poly_rings:
                continue
            if _point_in_ring(px, py, poly_rings[0]):
                if not any(_point_in_ring(px, py, h) for h in poly_rings[1:]):
                    return True
    return False


def _rep_point(geom: dict) -> tuple[float, float] | None:
    """Fast representative point: midpoint of first exterior ring bbox."""
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
        # Use bbox center (fast, doesn't iterate all vertices for centroid)
        return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    except (IndexError, TypeError, ZeroDivisionError):
        return None


# ---------------------------------------------------------------------------
# Load zoning polygons with spatial index (bbox grid)
# ---------------------------------------------------------------------------

def load_zoning_polygons(path: Path) -> list[dict]:
    with open(path) as f:
        data = json.load(f)
    polys = []
    for feat in data.get("features", []):
        props = feat.get("properties", {})
        geom = feat.get("geometry")
        if not geom:
            continue
        zone = (props.get("ZONE") or "").strip()
        desc = (props.get("DESCRIPT") or "").strip()
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
            "description": desc,
            "geometry": geom,
            "minx": min(xs), "miny": min(ys), "maxx": max(xs), "maxy": max(ys),
        })
    return polys


def lookup_zone(px: float, py: float, polys: list[dict]) -> tuple[str, str] | None:
    for p in polys:
        if not (p["minx"] <= px <= p["maxx"] and p["miny"] <= py <= p["maxy"]):
            continue
        if _pip(px, py, p["geometry"]):
            return p["zone"], p["description"]
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--batch", type=int, default=1000, help="DB batch size")
    args = parser.parse_args()

    if not ZONING_CACHE.exists():
        print(f"ERROR: {ZONING_CACHE} not found. Run cache_layers.py --only city_zoning first.", file=sys.stderr)
        sys.exit(1)

    print(f"Loading zoning polygons from {ZONING_CACHE} …")
    polys = load_zoning_polygons(ZONING_CACHE)
    print(f"  {len(polys)} zoning polygons")

    import asyncio
    import asyncpg
    from vicinitideals.config import settings

    # asyncpg DSN: strip the +asyncpg dialect prefix
    dsn = str(settings.database_url).replace("postgresql+asyncpg://", "postgresql://")

    async def run() -> None:
        conn = await asyncpg.connect(dsn)
        overwrite_clause = "" if args.overwrite else "AND zoning_code IS NULL"
        rows = await conn.fetch(f"""
            SELECT id::text, geometry::text
            FROM parcels
            WHERE jurisdiction = 'gresham'
              AND geometry IS NOT NULL
              {overwrite_clause}
        """)
        print(f"  {len(rows)} parcels to process")

        matched = skipped = errors = 0
        updates: list[tuple[str, str, str]] = []  # (zoning_code, zoning_description, id)

        for row in rows:
            parcel_id, geom_raw = row["id"], row["geometry"]
            try:
                geom = json.loads(geom_raw) if isinstance(geom_raw, str) else geom_raw
                pt = _rep_point(geom)
                if pt is None:
                    skipped += 1
                    continue
                hit = lookup_zone(pt[0], pt[1], polys)
                if hit is None:
                    skipped += 1
                    continue
                updates.append((hit[0], hit[1], parcel_id))
                matched += 1
            except Exception as e:
                print(f"  WARN {parcel_id}: {e}")
                errors += 1

        print(f"  matched={matched}  skipped={skipped}  errors={errors}")

        if args.dry_run:
            print("Dry run — no DB writes.")
            for z, d, pid in updates[:10]:
                print(f"  {pid} → {z} ({d})")
            await conn.close()
            return

        if not updates:
            print("Nothing to update.")
            await conn.close()
            return

        BATCH = args.batch
        for i in range(0, len(updates), BATCH):
            batch = updates[i:i + BATCH]
            await conn.executemany(
                "UPDATE parcels SET zoning_code=$1, zoning_description=$2 WHERE id=$3::uuid",
                batch,
            )
            print(f"  committed {min(i + BATCH, len(updates))}/{len(updates)}")

        await conn.close()
        print(f"Done — {len(updates)} parcels updated.")

    asyncio.run(run())


if __name__ == "__main__":
    main()
