"""
inspect_rlis_delta.py — Download the Metro RLIS quarterly delta ZIP and compare its
contents to our current cached taxlot data.

What this does:
1. Downloads the quarterly delta ZIP from ArcGIS Online (~1.3 GB) via optional proxy
2. Lists all shapefiles in the ZIP without extracting to disk
3. For key layers (Taxlots, Zoning, MAF), reads the .dbf column headers to check field schema
4. Compares taxlot fields against the fields we use in our enrichment pipeline
5. Optionally compares TLID counts against our cached GeoJSON if it exists

Usage:
    python inspect_rlis_delta.py
    python inspect_rlis_delta.py --proxy http://user:pass@proxy.host:port
    python inspect_rlis_delta.py --output /tmp/rlis_delta.zip  # save the ZIP for reuse
    python inspect_rlis_delta.py --zip /tmp/rlis_delta.zip     # skip download, use saved ZIP
"""
from __future__ import annotations

import argparse
import io
import json
import os
import struct
import sys
import zipfile
from pathlib import Path

import httpx

DELTA_ITEM_ID = "3949bc39e980444384312a8c4d7bdb08"
DELTA_DOWNLOAD_URL = f"https://drcmetro.maps.arcgis.com/sharing/rest/content/items/{DELTA_ITEM_ID}/data"

# Fields we rely on from tax_lots_metro_rlis in our enrichment pipeline
REQUIRED_TAXLOT_FIELDS = {
    "TLID", "ASSESSVAL", "LANDVAL", "BLDGVAL", "LANDUSE",
    "YEARBUILT", "BLDGSQFT", "SITEADDR", "JURIS_CITY", "STATECLASS",
}

# Fields we care about in the zoning layer
REQUIRED_ZONING_FIELDS = {"ZONE", "ZONING", "ZONECODE", "ZONE_CODE", "ZONE_ID", "JURIS"}

# Key shapefile names to look for inside the ZIP (lowercase matching)
LAYERS_OF_INTEREST = {
    "taxlots": "Taxlots (Public) — our primary parcel universe",
    "taxlots_change": "Taxlots Change - Geometry — geometry delta",
    "taxlot": "Taxlots (alternate name)",
    "zoning": "Zoning — Metro-wide zoning (coarse; we use city GIS for authoritative)",
    "maf": "Master Address File — address normalization",
    "master_address": "Master Address File (alternate name)",
    "city_limits": "City Limits — jurisdiction boundaries",
    "citylimits": "City Limits (alternate name)",
}


# ---------------------------------------------------------------------------
# DBF reader — read column headers from a .dbf file without loading all rows
# ---------------------------------------------------------------------------

def read_dbf_fields(dbf_bytes: bytes) -> list[str]:
    """
    Parse a dBASE III+ .dbf file header and return the list of field names.
    Stops reading at the header terminator (0x0D).
    """
    if len(dbf_bytes) < 32:
        return []

    # Bytes 8-11: number of records (unused here)
    # Bytes 8-9: header size in bytes (little-endian uint16 at offset 8)
    header_size = struct.unpack_from("<H", dbf_bytes, 8)[0]
    fields: list[str] = []

    # Field descriptors start at byte 32, each is 32 bytes, terminated by 0x0D
    offset = 32
    while offset < len(dbf_bytes) and offset < header_size:
        if dbf_bytes[offset] == 0x0D:
            break  # header terminator
        if offset + 11 > len(dbf_bytes):
            break
        field_name_raw = dbf_bytes[offset : offset + 11]
        field_name = field_name_raw.split(b"\x00", 1)[0].decode("ascii", errors="replace").strip()
        if field_name:
            fields.append(field_name)
        offset += 32

    return fields


def read_first_n_bytes_from_zip_member(zf: zipfile.ZipFile, name: str, n: int = 8192) -> bytes:
    """Read the first n bytes of a ZIP member without extracting the whole file."""
    with zf.open(name) as f:
        return f.read(n)


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def download_with_progress(url: str, proxy: str | None, output_path: Path | None) -> bytes | Path:
    """
    Stream-download url. If output_path is given, write to disk and return the path.
    Otherwise accumulate in memory and return bytes.
    """
    proxies = {"http://": proxy, "https://": proxy} if proxy else None

    print(f"  Connecting to {url} ...")
    with httpx.Client(proxies=proxies, follow_redirects=True, timeout=600.0) as client:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            chunks: list[bytes] = []
            dest = open(output_path, "wb") if output_path else None
            try:
                for chunk in resp.iter_bytes(chunk_size=1024 * 512):  # 512 KB chunks
                    if dest:
                        dest.write(chunk)
                    else:
                        chunks.append(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded / total * 100
                        mb = downloaded / 1_048_576
                        print(f"\r  {mb:,.0f} MB / {total/1_048_576:,.0f} MB  ({pct:.1f}%)", end="", flush=True)
                print()  # newline after progress
            finally:
                if dest:
                    dest.close()

    if output_path:
        print(f"  Saved to {output_path}")
        return output_path
    return b"".join(chunks)


# ---------------------------------------------------------------------------
# Comparison against current cached GeoJSON
# ---------------------------------------------------------------------------

def compare_to_cached_taxlots(zf: zipfile.ZipFile, taxlot_member: str) -> None:
    """Read a sample of TLIDs from the delta and compare to our cached GeoJSON."""
    cache_path = Path(__file__).resolve().parents[2] / "data" / "gis_cache" / "oregon" / "tax_lots_metro_rlis.geojson"
    if not cache_path.exists():
        print("  [skip] No cached taxlot GeoJSON found at", cache_path)
        return

    print(f"\n  Comparing delta against cached GeoJSON: {cache_path}")
    try:
        with open(cache_path, encoding="utf-8") as f:
            cached = json.load(f)
        cached_count = len(cached.get("features", []))
        cached_tlids = {
            str(feat["properties"].get("TLID", ""))
            for feat in cached.get("features", [])
            if feat.get("properties", {}).get("TLID")
        }
        print(f"  Cached: {cached_count:,} features, {len(cached_tlids):,} unique TLIDs")
    except Exception as exc:
        print(f"  [error] Could not read cached GeoJSON: {exc}")
        return

    # Read first 100 KB of the delta taxlot shapefile's .dbf to sample TLIDs
    # The actual count comparison requires reading the full file — report header only
    with zf.open(taxlot_member) as f:
        dbf_bytes = f.read(512)  # just enough for record count
    if len(dbf_bytes) >= 8:
        record_count = struct.unpack_from("<I", dbf_bytes, 4)[0]
        print(f"  Delta:  {record_count:,} records in shapefile header")
        if cached_count > 0:
            delta_pct = (record_count - cached_count) / cached_count * 100
            print(f"  Delta vs cache: {record_count - cached_count:+,} records ({delta_pct:+.1f}%)")


# ---------------------------------------------------------------------------
# Main inspection logic
# ---------------------------------------------------------------------------

def inspect_zip(zip_source: bytes | Path, proxy: str | None = None) -> None:
    if isinstance(zip_source, Path):
        zf = zipfile.ZipFile(zip_source, "r")
    else:
        zf = zipfile.ZipFile(io.BytesIO(zip_source), "r")

    with zf:
        all_names = zf.namelist()
        print(f"\n{'='*70}")
        print(f"ZIP CONTENTS — {len(all_names)} files")
        print(f"{'='*70}")

        # Group by layer (strip extension, collect .shp/.dbf/.prj/.shx)
        shp_layers: dict[str, list[str]] = {}
        for name in all_names:
            lower = name.lower()
            if lower.endswith((".shp", ".dbf", ".prj", ".shx", ".cpg")):
                base = name.rsplit(".", 1)[0]
                shp_layers.setdefault(base, []).append(name)

        print(f"\n  {len(shp_layers)} shapefile layers found:\n")
        for base in sorted(shp_layers.keys()):
            exts = ", ".join(n.rsplit(".", 1)[-1].upper() for n in sorted(shp_layers[base]))
            print(f"    {base}  [{exts}]")

        # Find layers of interest
        print(f"\n{'='*70}")
        print("KEY LAYERS — field schema")
        print(f"{'='*70}")

        found_taxlot_dbf: str | None = None
        found_taxlot_change_dbf: str | None = None

        for base, members in shp_layers.items():
            lower_base = base.lower()
            is_interesting = any(kw in lower_base for kw in LAYERS_OF_INTEREST)
            if not is_interesting:
                continue

            dbf_member = next((m for m in members if m.lower().endswith(".dbf")), None)
            shp_member = next((m for m in members if m.lower().endswith(".shp")), None)
            if not dbf_member:
                print(f"\n  [{base}] — no .dbf found")
                continue

            print(f"\n  [{base}]")

            # Read DBF fields
            try:
                dbf_bytes = read_first_n_bytes_from_zip_member(zf, dbf_member, n=4096)
                fields = read_dbf_fields(dbf_bytes)
                print(f"    Fields ({len(fields)}): {', '.join(fields)}")

                # Check required fields
                field_set = {f.upper() for f in fields}
                if "taxlot" in lower_base and "change" not in lower_base:
                    missing = REQUIRED_TAXLOT_FIELDS - field_set
                    present = REQUIRED_TAXLOT_FIELDS & field_set
                    print(f"    Required fields present ({len(present)}/{len(REQUIRED_TAXLOT_FIELDS)}): {', '.join(sorted(present))}")
                    if missing:
                        print(f"    MISSING required fields: {', '.join(sorted(missing))}")
                    else:
                        print(f"    All required taxlot fields PRESENT")
                    found_taxlot_dbf = dbf_member

                elif "change" in lower_base and "taxlot" in lower_base:
                    found_taxlot_change_dbf = dbf_member
                    print(f"    ^ This is the geometry delta layer")

                elif "zoning" in lower_base:
                    zoning_found = REQUIRED_ZONING_FIELDS & field_set
                    print(f"    Zoning-related fields: {', '.join(zoning_found) or '(none matched)'}")

            except Exception as exc:
                print(f"    [error reading DBF] {exc}")

            # SHP record count from header (bytes 24-27 = file length in 16-bit words)
            if shp_member:
                try:
                    shp_bytes = read_first_n_bytes_from_zip_member(zf, shp_member, n=100)
                    if len(shp_bytes) >= 28:
                        file_words = struct.unpack_from(">I", shp_bytes, 24)[0]
                        file_bytes = file_words * 2
                        print(f"    .shp file size: {file_bytes / 1_048_576:.1f} MB")
                except Exception:
                    pass

        # Compare to our cache
        if found_taxlot_dbf:
            taxlot_shp = found_taxlot_dbf.rsplit(".", 1)[0] + ".dbf"
            compare_to_cached_taxlots(zf, found_taxlot_dbf)

        # Summary on the change geometry layer
        print(f"\n{'='*70}")
        print("DELTA STRATEGY ASSESSMENT")
        print(f"{'='*70}")
        if found_taxlot_change_dbf:
            print("""
  Taxlots Change - Geometry layer is present.
  Strategy options:
    A) Full replace:  download Taxlots (Public) shapefile each quarter (~full size)
    B) Geometry diff: download Taxlots Change layer (likely much smaller) and apply
       TLID-based upserts to our cached GeoJSON

  Recommendation: read field schema of the change layer to understand
  what 'change type' field exists (ADD/DELETE/MODIFY etc.), then implement
  option B for quarterly updates instead of full re-download.
""")
        else:
            print("""
  No Taxlots Change layer found — ZIP may only contain full snapshots.
  Use full quarterly re-download strategy.
""")


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect Metro RLIS quarterly delta ZIP")
    parser.add_argument("--proxy", help="Datacenter proxy URL (e.g. http://user:pass@host:port)")
    parser.add_argument("--output", help="Save downloaded ZIP to this path for reuse")
    parser.add_argument("--zip", help="Skip download; use this local ZIP file instead")
    args = parser.parse_args()

    proxy = args.proxy or os.environ.get("PROXYON_DATACENTER_PROXIES", "").split(",")[0].strip() or None

    if args.zip:
        zip_path = Path(args.zip)
        if not zip_path.exists():
            print(f"ERROR: {zip_path} does not exist")
            sys.exit(1)
        print(f"Using local ZIP: {zip_path}")
        inspect_zip(zip_path, proxy=proxy)
        return

    output_path = Path(args.output) if args.output else None

    print(f"Downloading RLIS quarterly delta from ArcGIS Online...")
    print(f"  Item ID: {DELTA_ITEM_ID}")
    if proxy:
        print(f"  Proxy: {proxy}")
    else:
        print(f"  No proxy (set PROXYON_DATACENTER_PROXIES or --proxy to route through datacenter)")

    zip_data = download_with_progress(DELTA_DOWNLOAD_URL, proxy, output_path)
    inspect_zip(output_path if output_path else zip_data, proxy=proxy)


if __name__ == "__main__":
    main()
