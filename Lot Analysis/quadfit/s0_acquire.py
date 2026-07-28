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
import time
from pathlib import Path
from typing import Any

TOOL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL_DIR))
sys.path.insert(0, str(TOOL_DIR.parents[1] / "tools" / "gis_cache"))

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

# --- Phase 2: overlay / utility layers (see SOURCES_PHASE2.md for the audit).
# slug -> spec dict: url, fields, optional where, gtype ("polygon"|"polyline").
# Slugs match OverlaySpec.key as overlay_<key> / utility layers as util_<key>.
_PDX = "https://www.portlandmaps.com/arcgis/rest/services/Public"
_GRE = "https://gis.greshamoregon.gov/ext/rest/services/GME"
_TRO = "https://maps.troutdaleoregon.gov/server/rest/services/Public_Web"
_FAI = "https://services5.arcgis.com/3DoY8p7EnUTzaIE7/arcgis/rest/services"
_WV = "https://services7.arcgis.com/5Loh3xXKWLd2M7xA/arcgis/rest/services"
_METRO = "https://services2.arcgis.com/McQ0OlIABe29rJJy/arcgis/rest/services"

PHASE2_LAYERS: dict[str, dict[str, Any]] = {
    # Portland environmental zone GEOMETRY (not the OVRLY letters on zoning)
    "overlay_pdx_ezone_p": {
        "url": f"{_PDX}/BPS_Zoning_Code_Layers/MapServer/117",
        "fields": ["OVRLY", "ZONE", "PLDIST"]},
    "overlay_pdx_ezone_c": {
        "url": f"{_PDX}/BPS_Zoning_Code_Layers/MapServer/118",
        "fields": ["OVRLY", "ZONE", "PLDIST"]},
    "overlay_pdx_ezone_v": {
        "url": f"{_PDX}/BPS_Zoning_Code_Layers/MapServer/116",
        "fields": ["OVRLY", "ZONE", "PLDIST"]},
    # Gresham natural resource / hazard overlays
    "overlay_gresham_wetlands": {
        "url": f"{_GRE}/Environmental/MapServer/15",
        "fields": ["COWARDIN", "HGM", "WETLAND_TYPE"]},
    "overlay_gresham_streams": {
        "url": f"{_GRE}/Environmental/MapServer/0",
        "fields": ["NAME"], "gtype": "polyline"},
    "overlay_gresham_hcra": {
        "url": f"{_GRE}/Environmental/MapServer/12",
        "fields": ["OBJECTID"]},
    "overlay_gresham_hillside": {
        "url": f"{_GRE}/Environmental/MapServer/8",
        "fields": ["OBJECTID"]},
    # Troutdale Title 3 vegetated corridor (city-hosted RLIS derivative)
    "overlay_troutdale_veco": {
        "url": f"{_TRO}/City_GIS/MapServer/77",
        "fields": ["flood96", "fema", "wetbuf", "riparian", "title3"]},
    # Fairview natural resource layer (polygons ARE the buffered corridors)
    "overlay_fairview_nrl": {
        "url": f"{_FAI}/Natural_Resource_Layer/FeatureServer/0",
        "fields": ["TYPE"]},
    # Regional fallbacks (Wood Village, unincorporated, Troutdale wetlands)
    "overlay_metro_title3": {
        "url": f"{_METRO}/Title_3_Land/FeatureServer/0",
        "fields": ["FLOOD96", "FEMA", "WETBUF", "RIPARIAN", "TITLE3"]},
    "overlay_metro_title13": {
        "url": f"{_METRO}/Title_13_Habitat_Conservation_Areas/FeatureServer/0",
        "fields": ["HCA_VALUE"]},
    "overlay_metro_wetlands": {
        "url": f"{_METRO}/Wetlands/FeatureServer/0",
        "fields": ["SOURCE"]},
    # Flood: FEMA NFHL, single county-wide source of record
    "overlay_fema_flood": {
        "url": "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28",
        "fields": ["FLD_ZONE", "ZONE_SUBTY", "SFHA_TF", "STATIC_BFE"],
        # NFHL rejects the unquoted/spaceless form intermittently — keep quoted
        "where": "\"DFIRM_ID\" = '41051C'"},
    # Sewer mains (split-candidate proximity; water skipped — see caveats)
    "util_sewer_portland": {
        "url": f"{_PDX}/Utilities_Sewer/MapServer/3",
        "fields": ["OWNRSHIP", "SERVSTAT", "PIPESIZE"], "gtype": "polyline"},
    "util_sewer_gresham": {
        "url": f"{_GRE}/Wastewater/MapServer/5",
        "fields": ["gnownedby"], "gtype": "polyline"},
    "util_sewer_troutdale": {
        "url": f"{_TRO}/City_GIS/MapServer/11",
        "fields": ["owner", "date_built"], "gtype": "polyline"},
    "util_sewer_fairview": {
        "url": f"{_FAI}/Sewer_Main_Public/FeatureServer/7",
        "fields": ["DIA", "YEAR_CONST"], "gtype": "polyline"},
    "util_sewer_wood_village": {
        "url": f"{_WV}/Sanitary_Sewer_Main/FeatureServer/19",
        "fields": ["DIAMETER", "MATERIAL"], "gtype": "polyline"},
}

# USGS 3DEP 1 m DEM tiles for per-lot slope (urban Multnomah bbox, WGS84).
DEM_DIR_NAME = "dem"
DEM_BBOX_4326 = (-122.87, 45.40, -122.24, 45.65)
TNM_API = "https://tnmaccess.nationalmap.gov/api/v1/products"


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


def esri_polyline_to_geojson(esri_geom: dict[str, Any] | None) -> dict[str, Any] | None:
    if not esri_geom or "paths" not in esri_geom:
        return None
    paths = [p for p in esri_geom["paths"] if len(p) >= 2]
    if not paths:
        return None
    return {"type": "MultiLineString", "coordinates": paths}


def fetch_arcgis_layer(slug: str, url: str, out_fields: list[str], force: bool,
                       where: str = "1=1", gtype: str = "polygon") -> None:
    path = raw_path(slug)
    if path.exists() and not force:
        print(f"{slug}: cache present — skipping")
        return
    print(f"{slug}: {url}")
    convert = esri_polygon_to_geojson if gtype == "polygon" else esri_polyline_to_geojson
    with httpx.Client(timeout=120, follow_redirects=True,
                      headers={"User-Agent": "quadfit/1.0"}) as client:
        # A wrong field name errors EVERY query — indistinguishable from a
        # flaky host downstream, so validate the spec against the layer first.
        meta = client.get(url, params={"f": "json"}).json()
        have = {f["name"].lower() for f in meta.get("fields", [])}
        if have:
            bad = [f for f in out_fields if f.lower() not in have]
            if bad:
                raise RuntimeError(f"{slug}: fields {bad} not on layer "
                                   f"(has: {sorted(have)})")
        # Flaky hosts (FEMA especially) 400 the identical query intermittently.
        ids_doc: dict[str, Any] = {}
        for attempt in range(5):
            if attempt:
                time.sleep(10 * attempt)
            r = client.get(f"{url}/query", params={
                "where": where, "returnIdsOnly": "true", "f": "json"})
            r.raise_for_status()
            ids_doc = r.json()
            if "error" not in ids_doc:
                break
            print(f"  id query error (attempt {attempt + 1}/5): "
                  f"{ids_doc['error'].get('message')}")
        if "error" in ids_doc:
            raise RuntimeError(f"{slug}: id query failed: {ids_doc['error']}")
        oid_field = ids_doc.get("objectIdFieldName", "OBJECTID")
        oids = sorted(ids_doc.get("objectIds") or [])
        if not oids:
            raise RuntimeError(f"{slug}: id query returned 0 ids — refusing to "
                               "write an empty layer (check the where clause)")
        print(f"  {len(oids):,} object ids ({oid_field})")
        features: list[dict[str, Any]] = []

        def fetch_batch(batch: list[int], offset_ft: float = 0.0,
                        retried: bool = False) -> None:
            # POST: objectId lists overflow GET URL limits on AGOL hosts
            params = {
                "objectIds": ",".join(map(str, batch)),
                "outFields": ",".join(out_fields),
                "returnGeometry": "true",
                "outSR": OUT_SR,
                "f": "json",
            }
            if offset_ft:
                params["maxAllowableOffset"] = offset_ft
            r = client.post(f"{url}/query", data=params)
            r.raise_for_status()
            doc = r.json()
            if "error" in doc:
                # Transient server hiccups look identical to bad-geometry
                # errors; without this backoff one blip cascades into a
                # per-feature bisect storm that skips the whole layer.
                if not retried:
                    time.sleep(5)
                    fetch_batch(batch, offset_ft, retried=True)
                    return
                if len(batch) > 1:  # bisect to isolate the failing features
                    mid = len(batch) // 2
                    fetch_batch(batch[:mid], offset_ft, retried=True)
                    fetch_batch(batch[mid:], offset_ft, retried=True)
                    return
                if not offset_ft:  # giant geometry: retry with 1 ft simplify
                    fetch_batch(batch, offset_ft=1.0, retried=True)
                    return
                print(f"  WARNING: oid {batch[0]} unfetchable — skipped")
                return
            for feat in doc.get("features", []):
                features.append({
                    "type": "Feature",
                    "properties": feat.get("attributes", {}),
                    "geometry": convert(feat.get("geometry")),
                })

        chunk = 400
        for i in range(0, len(oids), chunk):
            fetch_batch(oids[i : i + chunk])
            if (i // chunk) % 10 == 0:
                print(f"  {len(features):,}/{len(oids):,}")
    _write_geojson(path, features, slug)


def derive_fema_split(force: bool) -> None:
    """Split raw NFHL zones into floodway (carve) vs SFHA fringe (flag)."""
    src = raw_path("overlay_fema_flood")
    fw_path, fr_path = raw_path("overlay_fema_floodway"), raw_path("overlay_fema_sfha")
    if not src.exists() or (fw_path.exists() and fr_path.exists() and not force):
        return
    doc = json.loads(src.read_text(encoding="utf-8"))
    fw, fr = [], []
    for f in doc["features"]:
        p = f.get("properties") or {}
        if "FLOODWAY" in str(p.get("ZONE_SUBTY") or "").upper():
            fw.append(f)
        elif str(p.get("SFHA_TF") or "").upper() == "T":
            fr.append(f)
    _write_geojson(fw_path, fw, "overlay_fema_floodway")
    _write_geojson(fr_path, fr, "overlay_fema_sfha")


def fetch_dem_tiles(force: bool) -> None:
    """USGS 3DEP 1 m GeoTIFF tiles covering the urban-county bbox.

    Prefers the newest lidar project per tile footprint. Idempotent by
    filename; ~15-20 tiles, ~5-7 GB total, one-time.
    """
    dem_dir = RAW_DIR / DEM_DIR_NAME
    dem_dir.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=None, follow_redirects=True,
                      headers={"User-Agent": "quadfit/1.0"}) as client:
        items: list[dict[str, Any]] = []
        offset = 0
        while True:
            r = client.get(TNM_API, params={
                "datasets": "Digital Elevation Model (DEM) 1 meter",
                "bbox": ",".join(map(str, DEM_BBOX_4326)),
                "outputFormat": "JSON", "max": 100, "offset": offset,
            })
            r.raise_for_status()
            doc = r.json()
            items.extend(doc.get("items", []))
            offset += 100
            if offset >= int(doc.get("total", 0)):
                break
        # One product per tile cell: newest publication wins.
        by_cell: dict[str, dict[str, Any]] = {}
        for it in items:
            url = it.get("downloadURL") or ""
            if not url.endswith(".tif"):
                continue
            # cell id like "x50y503" is stable across project vintages
            cell = next((p for p in url.split("_") if p.startswith("x")), url)
            prev = by_cell.get(cell)
            if prev is None or (it.get("publicationDate") or "") > (
                    prev.get("publicationDate") or ""):
                by_cell[cell] = it
        print(f"dem: {len(by_cell)} tiles cover bbox {DEM_BBOX_4326}")
        for cell, it in sorted(by_cell.items()):
            url = it["downloadURL"]
            dest = dem_dir / url.rsplit("/", 1)[-1]
            if dest.exists() and not force:
                print(f"  {dest.name}: present — skipping")
                continue
            print(f"  {dest.name}: downloading...")
            with client.stream("GET", url) as resp:
                resp.raise_for_status()
                tmp = dest.with_suffix(".part")
                with tmp.open("wb") as fh:
                    for chunk in resp.iter_bytes(1 << 20):
                        fh.write(chunk)
                tmp.replace(dest)
            print(f"  {dest.name}: {dest.stat().st_size/1e6:.0f} MB")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only", nargs="*", help="subset of dataset keys (or 'dem')")
    args = ap.parse_args()

    keys = set(args.only or [*RLIS_MEMBERS, *ARCGIS_LAYERS, *PHASE2_LAYERS, "dem"])
    if keys & set(RLIS_MEMBERS):
        extract_rlis(args.force, keys)
    for slug, (url, fields) in ARCGIS_LAYERS.items():
        if slug in keys:
            fetch_arcgis_layer(slug, url, fields, args.force)
    failed: list[str] = []
    for slug, spec in PHASE2_LAYERS.items():
        if slug in keys:
            try:
                fetch_arcgis_layer(slug, spec["url"], spec["fields"], args.force,
                                   where=spec.get("where", "1=1"),
                                   gtype=spec.get("gtype", "polygon"))
            except Exception as exc:  # one dead host must not sink the rest
                print(f"  FAILED {slug}: {exc}")
                failed.append(slug)
    derive_fema_split(args.force)
    if "dem" in keys:
        fetch_dem_tiles(args.force)
    if failed:
        raise SystemExit(f"s0 finished with failures: {failed}")
    print("s0 done.")


if __name__ == "__main__":
    main()
