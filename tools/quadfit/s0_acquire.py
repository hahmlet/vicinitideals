"""s0 — download raw inputs for the quadfit pipeline.

Two source families, both idempotent (skip files already on disk; --force):

1. Metro RLIS quarterly ZIP (drcmetro ArcGIS item) — selective HTTP-Range
   member extraction reusing tools/gis_cache/rlis_delta.py helpers:
   taxlots (Multnomah only), street centerlines, Metro regional zoning
   (covers PDF-only Fairview + unincorporated county), UGB.
   All native EPSG:2913. Geometry converted via pyshp __geo_interface__
   (correct hole handling — rlis_delta's own converter splits holes into
   separate polygons, which would inflate lot areas).

2. Authoritative per-city zoning via ArcGIS REST (objectId-paginated,
   outSR=2913): Portland, Gresham, Troutdale, Wood Village.

Outputs: data/quadfit/raw/*.geojson (coordinates in EPSG:2913 feet).
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path
from typing import Any

TOOL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL_DIR))
sys.path.insert(0, str(TOOL_DIR.parents[0] / "gis_cache"))

import httpx
import shapefile  # pyshp

import rlis_delta as rd
from common import DATA_DIR

RAW_DIR = DATA_DIR / "raw"

# member key → (shp member, dbf member, keep_fields or None=all, multnomah_only)
RLIS_MEMBERS: dict[str, tuple[str, str, set[str] | None, bool]] = {
    "taxlots": (
        "TAXLOTS/taxlots_public.shp",
        "TAXLOTS/taxlots_public.dbf",
        rd.TAXLOT_KEEP_FIELDS,
        True,
    ),
    "streets": (
        "STREETS/streets.shp",
        "STREETS/streets.dbf",
        {"LOCALID", "STREETNAME", "PREFIX", "FTYPE", "TYPE", "F_ZLEV", "T_ZLEV"},
        False,
    ),
    "zoning_metro": ("LAND/zoning.shp", "LAND/zoning.dbf", None, False),
    "ugb": ("BOUNDARY/ugb.shp", "BOUNDARY/ugb.dbf", None, False),
}

# slug → (layer query url, outFields)
ARCGIS_LAYERS: dict[str, tuple[str, list[str]]] = {
    "zoning_portland": (
        "https://www.portlandmaps.com/arcgis/rest/services/Public/Zoning/MapServer/0",
        ["ZONE", "ZONE_DESC", "OVRLY", "MAPLABEL", "UNINC"],
    ),
    "zoning_gresham": (
        "https://gis.greshamoregon.gov/ext/rest/services/GME/Planning/MapServer/4",
        ["ZONE", "DISTRICT", "DESCRIPT"],
    ),
    "zoning_troutdale": (
        "https://maps.troutdaleoregon.gov/server/rest/services/Public_Web/City_GIS/MapServer/74",
        ["zonecode", "description"],
    ),
    "zoning_wood_village": (
        "https://services7.arcgis.com/5Loh3xXKWLd2M7xA/arcgis/rest/services/Zoning/FeatureServer/9",
        ["Labeling", "Name"],
    ),
    # Lake Oswego's north edge crosses into Multnomah County (~1,450 lots).
    "zoning_lake_oswego": (
        "https://maps.ci.oswego.or.us/server/rest/services/Layers_Geocortex/MapServer/68",
        ["LAYER", "INFO", "LINK"],
    ),
}

OUT_SR = 2913  # request server-side projection to the working CRS


def raw_path(key: str) -> Path:
    return RAW_DIR / f"{key}.geojson"


def _write_geojson(path: Path, features: list[dict[str, Any]], name: str) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    doc = {"type": "FeatureCollection", "name": name, "features": features}
    path.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    print(f"  wrote {len(features):,} features -> {path} ({path.stat().st_size/1e6:.1f} MB)")


# ---------------------------------------------------------------------------
# RLIS ZIP extraction
# ---------------------------------------------------------------------------


def shp_to_features(
    shp_bytes: bytes,
    dbf_bytes: bytes,
    keep_fields: set[str] | None,
    multnomah_only: bool,
) -> list[dict[str, Any]]:
    sf = shapefile.Reader(shp=io.BytesIO(shp_bytes), dbf=io.BytesIO(dbf_bytes))
    field_names = [f[0] for f in sf.fields[1:]]
    print(f"  dbf fields: {field_names}")
    county_idx = field_names.index("COUNTY") if "COUNTY" in field_names else None

    features: list[dict[str, Any]] = []
    for sr in sf.iterShapeRecords():
        rec = sr.record
        if multnomah_only and county_idx is not None:
            if str(rec[county_idx]).strip().upper() != "M":
                continue
        props: dict[str, Any] = {}
        for i, fname in enumerate(field_names):
            if keep_fields is not None and fname not in keep_fields:
                continue
            val = rec[i]
            props[fname] = val.isoformat() if hasattr(val, "year") else val
        try:
            geom = sr.shape.__geo_interface__ if sr.shape.shapeType != 0 else None
        except Exception:  # degenerate shapes in county data
            geom = None
        features.append({"type": "Feature", "properties": props, "geometry": geom})
    return features


def extract_rlis(force: bool, keys: set[str] | None = None) -> None:
    targets = {
        key: spec
        for key, spec in RLIS_MEMBERS.items()
        if (keys is None or key in keys) and (force or not raw_path(key).exists())
    }
    if not targets:
        print("RLIS: all member caches present — skipping")
        return
    with rd._client() as client:
        print(f"RLIS: resolving {rd.DELTA_URL}")
        url, total = rd.resolve_url(client, rd.DELTA_URL)
        print(f"RLIS: ZIP is {total/1e9:.2f} GB")
        entries = rd.parse_zip_central_directory(client, url, total)
        for key, (shp_m, dbf_m, keep, m_only) in targets.items():
            print(f"RLIS: extracting {key} ({shp_m})")
            shp_entry, dbf_entry = entries.get(shp_m), entries.get(dbf_m)
            if not shp_entry or not dbf_entry:
                raise RuntimeError(f"{shp_m} / {dbf_m} not found in RLIS ZIP")
            shp_bytes = rd.extract_member(client, url, shp_entry)
            dbf_bytes = rd.extract_member(client, url, dbf_entry)
            feats = shp_to_features(shp_bytes, dbf_bytes, keep, m_only)
            _write_geojson(raw_path(key), feats, key)


# ---------------------------------------------------------------------------
# ArcGIS layer fetch (objectId pagination, esri JSON -> GeoJSON)
# ---------------------------------------------------------------------------


def _shoelace(ring: list[list[float]]) -> float:
    area = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        area += x1 * y2 - x2 * y1
    return area / 2.0


def _point_in_ring(pt: list[float], ring: list[list[float]]) -> bool:
    x, y = pt
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def esri_polygon_to_geojson(esri_geom: dict[str, Any] | None) -> dict[str, Any] | None:
    """Esri rings (shells CW, holes CCW) -> GeoJSON MultiPolygon."""
    if not esri_geom or "rings" not in esri_geom:
        return None
    shells: list[list[list[float]]] = []
    holes: list[list[list[float]]] = []
    for ring in esri_geom["rings"]:
        if len(ring) < 4:
            continue
        (shells if _shoelace(ring) < 0 else holes).append(ring)
    if not shells:  # nonconforming server orientation — treat all as shells
        shells, holes = holes, []
    polys: list[list[list[list[float]]]] = [[s] for s in shells]
    for hole in holes:
        for poly in polys:
            if _point_in_ring(hole[0], poly[0]):
                poly.append(hole)
                break
        else:
            polys.append([hole])  # orphan hole — keep as shell rather than drop
    return {"type": "MultiPolygon", "coordinates": polys}


def fetch_arcgis_layer(slug: str, url: str, out_fields: list[str], force: bool) -> None:
    path = raw_path(slug)
    if path.exists() and not force:
        print(f"{slug}: cache present — skipping")
        return
    print(f"{slug}: {url}")
    with httpx.Client(timeout=120, follow_redirects=True,
                      headers={"User-Agent": "quadfit/1.0"}) as client:
        r = client.get(f"{url}/query", params={
            "where": "1=1", "returnIdsOnly": "true", "f": "json"})
        r.raise_for_status()
        ids_doc = r.json()
        oid_field = ids_doc.get("objectIdFieldName", "OBJECTID")
        oids = sorted(ids_doc.get("objectIds") or [])
        print(f"  {len(oids):,} object ids ({oid_field})")
        features: list[dict[str, Any]] = []
        chunk = 400
        for i in range(0, len(oids), chunk):
            batch = oids[i : i + chunk]
            r = client.get(f"{url}/query", params={
                "objectIds": ",".join(map(str, batch)),
                "outFields": ",".join(out_fields),
                "returnGeometry": "true",
                "outSR": OUT_SR,
                "f": "json",
            })
            r.raise_for_status()
            doc = r.json()
            if "error" in doc:
                raise RuntimeError(f"{slug}: {doc['error']}")
            for feat in doc.get("features", []):
                features.append({
                    "type": "Feature",
                    "properties": feat.get("attributes", {}),
                    "geometry": esri_polygon_to_geojson(feat.get("geometry")),
                })
            if (i // chunk) % 10 == 0:
                print(f"  {len(features):,}/{len(oids):,}")
    _write_geojson(path, features, slug)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only", nargs="*", help="subset of dataset keys")
    args = ap.parse_args()

    keys = set(args.only or [*RLIS_MEMBERS, *ARCGIS_LAYERS])
    if keys & set(RLIS_MEMBERS):
        extract_rlis(args.force, keys)
    for slug, (url, fields) in ARCGIS_LAYERS.items():
        if slug in keys:
            fetch_arcgis_layer(slug, url, fields, args.force)
    print("s0 done.")


if __name__ == "__main__":
    main()
