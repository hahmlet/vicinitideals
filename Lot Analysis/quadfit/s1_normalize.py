"""s1 — normalize raw downloads into canonical Parquet stages.

- Taxlots: validity repair, drop empty/degenerate geometry, explode
  multipolygons keeping the largest part, condo-stack dedupe (many TLIDs
  sharing one footprint collapse to a representative row with stack_count).
- Streets: geometry + name only.
- Zoning layers (every layer referenced by rules.yaml): validity repair +
  zone_raw column extracted from the configured zone_field.
- UGB: polygons as-is.

Everything already in EPSG:2913 (s0 requests outSR=2913 / RLIS native).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

TOOL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL_DIR))

from common import load_rules, write_stage
from s0_acquire import raw_path

TAXLOT_PROP_COLUMNS = [
    "TLID", "SITEADDR", "SITECITY", "SITEZIP", "JURIS_CITY", "COUNTY",
    "STATECLASS", "PROP_CODE", "LANDUSE", "YEARBUILT", "BLDGSQFT",
    "LANDVAL", "BLDGVAL", "TOTALVAL", "ASSESSVAL", "SALEDATE", "SALEPRICE",
]


def _load_features(key: str) -> list[dict[str, Any]]:
    path = raw_path(key)
    if not path.exists():
        raise SystemExit(f"missing raw input {path} — run s0_acquire.py first")
    doc = json.loads(path.read_bytes())
    return doc["features"]


def _clean_polygon(geom: Any) -> tuple[Any | None, float, int]:
    """(largest polygon part, full valid area, part count) — None if degenerate."""
    import shapely
    from shapely import get_parts

    if geom is None or geom.is_empty:
        return None, 0.0, 0
    g = shapely.make_valid(geom)
    if g.is_empty:
        return None, 0.0, 0
    parts = [p for p in get_parts(g) if p.geom_type == "Polygon" and p.area > 0]
    if not parts:
        return None, 0.0, 0
    full_area = sum(p.area for p in parts)
    largest = max(parts, key=lambda p: p.area)
    return largest, full_area, len(parts)


def normalize_taxlots() -> None:
    import pandas as pd
    from shapely.geometry import shape

    feats = _load_features("taxlots")
    print(f"taxlots: {len(feats):,} raw features")

    rows: list[dict[str, Any]] = []
    dropped_geom = 0
    for f in feats:
        geom_json = f.get("geometry")
        geom = shape(geom_json) if geom_json else None
        largest, full_area, n_parts = _clean_polygon(geom)
        if largest is None:
            dropped_geom += 1
            continue
        props = f.get("properties", {})
        row = {c: props.get(c) for c in TAXLOT_PROP_COLUMNS}
        row["area_sqft"] = full_area
        row["part_count"] = n_parts
        row["geom"] = largest
        rows.append(row)
    print(f"taxlots: dropped {dropped_geom:,} with no usable polygon geometry")

    df = pd.DataFrame(rows)

    # Condo-stack dedupe: units platted as identical/near-identical footprints.
    # Key on rounded representative point + rounded area.
    keys = [
        (round(g.centroid.x, 1), round(g.centroid.y, 1), round(a))
        for g, a in zip(df["geom"], df["area_sqft"])
    ]
    df["_stack_key"] = keys
    sizes = df.groupby("_stack_key")["TLID"].transform("size")
    df["stack_count"] = sizes
    df["stacked"] = sizes > 1
    before = len(df)
    df = df.drop_duplicates(subset="_stack_key", keep="first").drop(columns="_stack_key")
    print(f"taxlots: condo-stack dedupe {before:,} -> {len(df):,} "
          f"({(df['stacked']).sum():,} representatives of stacks)")

    write_stage(df, "s1_lots")


def normalize_streets() -> None:
    import pandas as pd
    from shapely.geometry import shape

    feats = _load_features("streets")
    rows = []
    for f in feats:
        gj = f.get("geometry")
        if not gj:
            continue
        rows.append({
            "name": f.get("properties", {}).get("STREETNAME"),
            "geom": shape(gj),
        })
    print(f"streets: {len(rows):,} centerline features")
    write_stage(pd.DataFrame(rows), "s1_streets")


def normalize_zoning() -> None:
    import pandas as pd
    from shapely.geometry import shape

    rules = load_rules()
    layer_fields: dict[str, str] = {}
    for j in rules.jurisdictions.values():
        if j.zoning_layer and j.zone_field:
            existing = layer_fields.get(j.zoning_layer)
            if existing and existing != j.zone_field:
                raise SystemExit(
                    f"zoning layer {j.zoning_layer} referenced with two zone_fields")
            layer_fields[j.zoning_layer] = j.zone_field

    for slug, field in layer_fields.items():
        feats = _load_features(slug)
        rows = []
        missing_field = 0
        for f in feats:
            gj = f.get("geometry")
            if not gj:
                continue
            largest, full_area, _ = _clean_polygon(shape(gj))
            if largest is None:
                continue
            props = f.get("properties", {})
            if field not in props:
                missing_field += 1
            # Zone assignment must consider every part of a multi-part zone
            # polygon, so keep the full valid geometry, not just the largest.
            import shapely

            g = shapely.make_valid(shape(gj))
            rows.append({"zone_raw": props.get(field), "geom": g})
        if missing_field:
            print(f"{slug}: WARNING zone_field '{field}' missing on {missing_field} features")
        print(f"{slug}: {len(rows):,} zone polygons (field {field})")
        write_stage(pd.DataFrame(rows), f"s1_zoning_{slug}")


def normalize_ugb() -> None:
    import pandas as pd
    import shapely
    from shapely.geometry import shape

    feats = _load_features("ugb")
    geoms = [shapely.make_valid(shape(f["geometry"])) for f in feats if f.get("geometry")]
    print(f"ugb: {len(geoms)} polygons")
    write_stage(pd.DataFrame({"geom": geoms}), "s1_ugb")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", nargs="*", choices=["taxlots", "streets", "zoning", "ugb"])
    args = ap.parse_args()
    wanted = set(args.only or ["taxlots", "streets", "zoning", "ugb"])
    if "taxlots" in wanted:
        normalize_taxlots()
    if "streets" in wanted:
        normalize_streets()
    if "zoning" in wanted:
        normalize_zoning()
    if "ugb" in wanted:
        normalize_ugb()
    print("s1 done.")


if __name__ == "__main__":
    main()
