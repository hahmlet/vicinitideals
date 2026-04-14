"""
rlis_delta.py — Quarterly RLIS taxlot cache refresh.

Downloads ONLY the required files from the Metro RLIS quarterly delta ZIP using HTTP
Range requests — no full 1.37 GB download needed. Extracts ~230 MB (taxlots_public
shapefile) directly from the remote ZIP, applies Multnomah + Clackamas county filter,
and replaces the local GIS cache.

Delta stats from Q1-2026:
  CHANGE  126,134  (98.4%) — attribute/geometry updates
  ADDED     1,647  (1.3%)
  DELETED     452  (0.4%)
Since 98% of records are CHANGEs that require full attribute data from taxlots_public,
a full quarterly replace is the correct strategy (not TLID-based diff).

ZIP member paths confirmed:
  TAXLOTS/taxlots_public.shp   320.9 MB uncompressed / 202.7 MB compressed
  TAXLOTS/taxlots_public.dbf    27 fields, 655,065 records
  TAXLOTS/taxlot_change.dbf     5 fields, ADDCHANGE ∈ {CHANGE, ADDED, DELETED}
  TAXLOTS/master_address.dbf   20 fields, 902,008 records

Run quarterly via cron (no proxy needed — drcmetro.maps.arcgis.com is public):
  0 2 1 1,4,7,10 * cd /app && uv run --extra tools python tools/gis_cache/rlis_delta.py >> /var/log/rlis_delta.log 2>&1

Usage:
    python rlis_delta.py              # standard run
    python rlis_delta.py --dry-run    # download + report, no write
    python rlis_delta.py --stats-only # fetch change log only (~15 MB), no replace
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import io
import json
import os
import struct
import sys
import zlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import shapefile  # pyshp — install: uv run --extra tools

def _resolve_root() -> Path:
    """Resolve GIS cache root: env var > relative to script > /app/data/gis_cache fallback."""
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
MANIFEST_PATH = ROOT / "manifest.json"
TAXLOT_CACHE = ROOT / "oregon" / "tax_lots_metro_rlis.geojson"

DELTA_ITEM_ID = "3949bc39e980444384312a8c4d7bdb08"
DELTA_URL = f"https://drcmetro.maps.arcgis.com/sharing/rest/content/items/{DELTA_ITEM_ID}/data"

# RLIS COUNTY field: M = Multnomah, C = Clackamas
RLIS_COUNTY_FILTER = {"M", "C"}

TAXLOT_KEEP_FIELDS = {
    "TLID", "ASSESSVAL", "LANDVAL", "BLDGVAL", "LANDUSE",
    "YEARBUILT", "BLDGSQFT", "SITEADDR", "JURIS_CITY", "STATECLASS",
    "COUNTY", "PROP_CODE", "SITECITY", "SITEZIP", "TOTALVAL",
    "YEARBUILT", "SALEDATE", "SALEPRICE",
}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _client() -> httpx.Client:
    return httpx.Client(follow_redirects=True, timeout=600.0,
                        headers={"User-Agent": "rlis-delta/1.0"})


def fetch_range(client: httpx.Client, url: str, start: int, end: int) -> bytes:
    resp = client.get(url, headers={"Range": f"bytes={start}-{end}"})
    resp.raise_for_status()
    return resp.content


def resolve_url(client: httpx.Client, url: str) -> tuple[str, int]:
    """Return (final_url, content_length) via HEAD request."""
    resp = client.head(url)
    resp.raise_for_status()
    return str(resp.url), int(resp.headers.get("content-length", 0))


# ---------------------------------------------------------------------------
# ZIP central directory parser (pure stdlib — no download of full file)
# ---------------------------------------------------------------------------

def parse_zip_central_directory(client: httpx.Client, url: str, total: int) -> dict[str, dict]:
    """
    Fetch and parse the ZIP central directory via Range requests.
    Returns dict of {member_name: {local_off, comp_size, uncomp_size, method}}.
    """
    # Fetch last 512 KB — enough to contain EOCD + central directory for this ZIP
    tail_size = 524288
    tail_start = total - tail_size
    tail = fetch_range(client, url, tail_start, total - 1)

    # Find EOCD signature
    idx = tail.rfind(b"PK\x05\x06")
    if idx == -1:
        raise RuntimeError("EOCD signature not found — ZIP corrupt or tail too small")

    _, _, _, _, cd_size, cd_offset, _ = struct.unpack_from("<HHHHIIH", tail[idx:], 4)
    print(f"  ZIP: central directory at offset {cd_offset:,}, size {cd_size:,} bytes")

    # Central directory may be within the tail or need a separate fetch
    if cd_offset >= tail_start:
        cd_bytes = tail[cd_offset - tail_start: cd_offset - tail_start + cd_size]
    else:
        print(f"  Central dir before tail — fetching {cd_size:,} bytes from offset {cd_offset:,}")
        cd_bytes = fetch_range(client, url, cd_offset, cd_offset + cd_size - 1)

    if len(cd_bytes) < cd_size:
        raise RuntimeError(f"Central directory incomplete: got {len(cd_bytes)}, expected {cd_size}")

    # Parse CD headers
    entries: dict[str, dict] = {}
    pos = 0
    CD_SIG = b"PK\x01\x02"
    while pos < len(cd_bytes) - 4:
        if cd_bytes[pos: pos + 4] != CD_SIG:
            break
        (_, _, _, method, _, _, _, comp_size, uncomp_size,
         fl, el, cl, _, _, _, local_off) = struct.unpack_from("<HHHHHH III HHH HHI I", cd_bytes, pos + 4)
        fname = cd_bytes[pos + 46: pos + 46 + fl].decode("utf-8", errors="replace")
        entries[fname] = dict(local_off=local_off, comp_size=comp_size,
                              uncomp_size=uncomp_size, method=method)
        pos += 46 + fl + el + cl

    print(f"  ZIP: {len(entries)} entries parsed")
    return entries


# ---------------------------------------------------------------------------
# Selective file extractor (range-fetch + decompress a single ZIP member)
# ---------------------------------------------------------------------------

def extract_member(client: httpx.Client, url: str, entry: dict) -> bytes:
    """
    Fetch + decompress a single ZIP member using HTTP Range requests.
    Only downloads that member's bytes, not the whole ZIP.
    """
    local_off = entry["local_off"]
    # Read local file header to find data start (30 + fname_len + extra_len)
    lh = fetch_range(client, url, local_off, local_off + 299)
    if lh[:4] != b"PK\x03\x04":
        raise RuntimeError(f"Bad local file header at offset {local_off}")
    fname_len = struct.unpack_from("<H", lh, 26)[0]
    extra_len = struct.unpack_from("<H", lh, 28)[0]
    data_start = local_off + 30 + fname_len + extra_len

    print(f"  Fetching {entry['comp_size']/1e6:.1f} MB compressed from offset {data_start:,}...")
    raw = fetch_range(client, url, data_start, data_start + entry["comp_size"] - 1)

    if entry["method"] == 8:  # deflate
        return zlib.decompress(raw, -15)
    elif entry["method"] == 0:  # stored
        return raw
    else:
        raise RuntimeError(f"Unsupported ZIP method: {entry['method']}")


# ---------------------------------------------------------------------------
# Shapefile → GeoJSON conversion (pyshp)
# ---------------------------------------------------------------------------

def _shape_to_geojson(shape: Any) -> dict | None:
    """Convert a pyshp shape to GeoJSON geometry dict."""
    if shape.shapeType == 0:
        return None
    if shape.shapeType in (1, 11, 21):
        return {"type": "Point", "coordinates": list(shape.points[0])}
    if shape.shapeType in (3, 13, 23):
        return {"type": "MultiLineString", "coordinates": [list(pt) for pt in shape.points]}
    if shape.shapeType in (5, 15, 25):
        parts = list(shape.parts) + [len(shape.points)]
        rings = [[list(pt) for pt in shape.points[parts[i]: parts[i + 1]]]
                 for i in range(len(parts) - 1)]
        if len(rings) == 1:
            return {"type": "Polygon", "coordinates": rings}
        return {"type": "MultiPolygon", "coordinates": [[r] for r in rings]}
    return None


def shp_dbf_to_geojson(
    shp_bytes: bytes,
    dbf_bytes: bytes,
    county_filter: set[str] | None = None,
    keep_fields: set[str] | None = None,
) -> list[dict]:
    """Convert in-memory shapefile bytes to GeoJSON feature list with optional filters."""
    sf = shapefile.Reader(shp=io.BytesIO(shp_bytes), dbf=io.BytesIO(dbf_bytes))
    field_names = [f[0] for f in sf.fields[1:]]  # skip DeletionFlag

    features = []
    county_field_idx = field_names.index("COUNTY") if "COUNTY" in field_names else None

    for shape_rec in sf.iterShapeRecords():
        rec = shape_rec.record

        # County filter
        if county_filter and county_field_idx is not None:
            county_val = str(rec[county_field_idx]).strip().upper()
            if county_val not in county_filter:
                continue

        props: dict[str, Any] = {}
        for i, fname in enumerate(field_names):
            if keep_fields is None or fname in keep_fields:
                val = rec[i]
                # Coerce to JSON-safe types
                if hasattr(val, "year"):  # date
                    props[fname] = val.isoformat()
                elif val is None:
                    props[fname] = None
                else:
                    props[fname] = val

        geom = _shape_to_geojson(shape_rec.shape)
        features.append({"type": "Feature", "properties": props, "geometry": geom})

    return features


# ---------------------------------------------------------------------------
# Change log reader (taxlot_change.dbf — no geometry needed)
# ---------------------------------------------------------------------------

def read_change_log(client: httpx.Client, url: str, entries: dict) -> dict:
    """
    Fetch taxlot_change.dbf (~15 MB compressed).
    Returns {counts: {CHANGE/ADDED/DELETED: N}, deleted_tlids: [...], added_tlids: [...]}.
    taxlot_change has no COUNTY field — we include all TLIDs; the DB purge
    is a no-op for non-M+C ones since they were never seeded.
    """
    entry = entries.get("TAXLOTS/taxlot_change.dbf")
    if not entry:
        print("  taxlot_change.dbf not found in ZIP — skipping change log")
        return {"counts": {}, "deleted_tlids": [], "added_tlids": []}

    print("\nReading change log (taxlot_change.dbf)...")
    dbf_bytes = extract_member(client, url, entry)

    record_count = struct.unpack_from("<I", dbf_bytes, 4)[0]
    header_size = struct.unpack_from("<H", dbf_bytes, 8)[0]
    record_size = struct.unpack_from("<H", dbf_bytes, 10)[0]

    fields: list[tuple[str, int]] = []
    pos = 32
    while pos < header_size:
        if dbf_bytes[pos] == 0x0D:
            break
        fname = dbf_bytes[pos: pos + 11].split(b"\x00", 1)[0].decode("ascii", "replace").strip()
        flen = dbf_bytes[pos + 16]
        if fname:
            fields.append((fname, flen))
        pos += 32

    tlid_idx = next((i for i, (f, _) in enumerate(fields) if f == "TLID"), None)
    addchange_idx = next((i for i, (f, _) in enumerate(fields) if f == "ADDCHANGE"), None)
    if addchange_idx is None:
        print("  ADDCHANGE field not found in taxlot_change.dbf")
        return {"counts": {}, "deleted_tlids": [], "added_tlids": []}

    counts: dict[str, int] = collections.Counter()
    deleted_tlids: list[str] = []
    added_tlids: list[str] = []

    for i in range(record_count):
        rec_start = header_size + i * record_size
        if rec_start + record_size > len(dbf_bytes):
            break
        if dbf_bytes[rec_start] == 0x2A:
            continue
        fpos = rec_start + 1
        tlid = ""
        addchange = ""
        for j, (fname, flen) in enumerate(fields):
            val = dbf_bytes[fpos: fpos + flen].decode("ascii", "replace").strip()
            if j == tlid_idx:
                tlid = val
            if j == addchange_idx:
                addchange = val
            fpos += flen
        counts[addchange] += 1
        if addchange == "DELETED":
            deleted_tlids.append(tlid)
        elif addchange == "ADDED":
            added_tlids.append(tlid)

    total = sum(counts.values())
    print(f"  {record_count:,} change records:")
    for val, cnt in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"    {val:12} {cnt:,}  ({cnt/total*100:.1f}%)")
    print(f"  Captured {len(deleted_tlids)} DELETED TLIDs, {len(added_tlids)} ADDED TLIDs")
    return {"counts": dict(counts), "deleted_tlids": deleted_tlids, "added_tlids": added_tlids}


# ---------------------------------------------------------------------------
# Manifest update
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def update_manifest(feature_count: int, size_bytes: int, change_stats: dict) -> None:
    if not MANIFEST_PATH.exists():
        print("  No manifest found — skipping manifest update")
        return
    try:
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"  Could not read manifest: {exc}")
        return

    now = datetime.now(UTC).isoformat()
    for entry in data.get("layers", []):
        if entry.get("slug") == "tax_lots_metro_rlis":
            entry["cached_at"] = now
            entry["feature_count"] = feature_count
            entry["size_bytes"] = size_bytes
            entry["size_mb"] = round(size_bytes / (1024 * 1024), 3)
            entry["sha256"] = _sha256(TAXLOT_CACHE)
            entry["rlis_delta_applied_at"] = now
            entry["rlis_delta_change_stats"] = change_stats
            break
    data["cached_at"] = now
    MANIFEST_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print("  Manifest updated")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(dry_run: bool = False, stats_only: bool = False) -> None:
    with _client() as client:
        print(f"Resolving {DELTA_URL} ...")
        final_url, total = resolve_url(client, DELTA_URL)
        print(f"Size: {total:,} bytes ({total/1e9:.2f} GB)")
        print(f"URL:  {final_url[:90]}")

        print("\nParsing ZIP central directory...")
        entries = parse_zip_central_directory(client, final_url, total)

        # Always read change log for stats
        change_stats = read_change_log(client, final_url, entries)

        if stats_only:
            print("\n[stats-only] Done — no cache update")
            return

        # Extract taxlots_public.shp + .dbf via range requests
        shp_entry = entries.get("TAXLOTS/taxlots_public.shp")
        dbf_entry = entries.get("TAXLOTS/taxlots_public.dbf")
        if not shp_entry or not dbf_entry:
            print("ERROR: taxlots_public.shp/.dbf not found in ZIP entries")
            sys.exit(1)

        print(f"\nExtracting taxlots_public.shp ({shp_entry['comp_size']/1e6:.1f} MB compressed)...")
        shp_bytes = extract_member(client, final_url, shp_entry)
        print(f"  Decompressed: {len(shp_bytes)/1e6:.1f} MB")

        print(f"Extracting taxlots_public.dbf ({dbf_entry['comp_size']/1e6:.1f} MB compressed)...")
        dbf_bytes = extract_member(client, final_url, dbf_entry)
        print(f"  Decompressed: {len(dbf_bytes)/1e6:.1f} MB")

        # Convert to GeoJSON with county filter
        print(f"\nConverting to GeoJSON (county filter: {RLIS_COUNTY_FILTER})...")
        features = shp_dbf_to_geojson(shp_bytes, dbf_bytes,
                                       county_filter=RLIS_COUNTY_FILTER,
                                       keep_fields=TAXLOT_KEEP_FIELDS)
        print(f"  {len(features):,} features after county filter (M + C)")

        if dry_run:
            print(f"\n[dry-run] Would write {len(features):,} features to {TAXLOT_CACHE}")
            print("[dry-run] No files written.")
            return

        # Write cache
        ROOT.mkdir(parents=True, exist_ok=True)
        (ROOT / "oregon").mkdir(exist_ok=True)
        geojson = {
            "type": "FeatureCollection",
            "name": "Taxlots — Portland Metro (Multnomah + Clackamas)",
            "features": features,
        }
        out_bytes = json.dumps(geojson, separators=(",", ":")).encode("utf-8")
        TAXLOT_CACHE.write_bytes(out_bytes)
        size = len(out_bytes)
        print(f"\nWrote {len(features):,} features → {TAXLOT_CACHE} ({size/1e6:.1f} MB)")

        update_manifest(len(features), size, change_stats)

        # Write sidecar for the Celery task to consume
        sidecar = {
            "applied_at": datetime.now(UTC).isoformat(),
            "feature_count": len(features),
            "change_stats": change_stats.get("counts", {}),
            "deleted_tlids": change_stats.get("deleted_tlids", []),
            "added_count": len(change_stats.get("added_tlids", [])),
            "zip_item_id": DELTA_ITEM_ID,
        }
        sidecar_path = ROOT / "oregon" / "rlis_delta_changes.json"
        sidecar_path.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
        print(f"Wrote sidecar → {sidecar_path}")

        # Dispatch Celery task for DB integration
        _dispatch_db_task()
        print("Done.")


def _dispatch_db_task() -> None:
    """Send rlis_quarterly_refresh_task to the Celery broker (Redis)."""
    broker = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/1")
    try:
        from celery import Celery as _Celery
        app = _Celery(broker=broker)
        app.send_task("vicinitideals.tasks.parcel_seed.rlis_quarterly_refresh_task")
        print(f"Dispatched rlis_quarterly_refresh_task to {broker}")
    except Exception as exc:
        print(f"  [warn] Could not dispatch Celery task: {exc}")
        print("  Run manually: celery call vicinitideals.tasks.parcel_seed.rlis_quarterly_refresh_task")


def main() -> None:
    parser = argparse.ArgumentParser(description="Quarterly RLIS taxlot cache refresh via range-extracted ZIP")
    parser.add_argument("--dry-run", action="store_true", help="Download + report, do not write to disk")
    parser.add_argument("--stats-only", action="store_true", help="Read change log only (~15 MB), skip taxlot replace")
    args = parser.parse_args()
    run(dry_run=args.dry_run, stats_only=args.stats_only)


if __name__ == "__main__":
    main()
