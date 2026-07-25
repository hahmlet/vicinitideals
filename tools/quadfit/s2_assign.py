"""s2 — jurisdiction tagging + majority-area zone assignment.

- jurisdiction: RLIS JURIS_CITY literal routed through rules.yaml
  juris_city_codes (run with --report to see the raw histogram when
  calibrating those code lists).
- zone: STRtree spatial join against the jurisdiction's zoning layer;
  majority intersection area wins. zone_frac < 0.9 flags split_zone.
- inside_ugb: representative point within any UGB polygon.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL_DIR))

from common import load_rules, read_stage, write_stage

SPLIT_ZONE_THRESHOLD = 0.9


def assign_majority_zone(lot_geoms: list, zone_geoms: list, zone_codes: list):
    """Vectorized majority-area zone join.

    Returns (zone_raw list, zone_frac list) aligned with lot_geoms.
    """
    import numpy as np
    import shapely
    from shapely.strtree import STRtree

    lots = np.array(lot_geoms, dtype=object)
    zones = np.array(zone_geoms, dtype=object)
    tree = STRtree(zones)
    li, zi = tree.query(lots, predicate="intersects")
    inter = shapely.intersection(lots[li], zones[zi])
    inter_area = shapely.area(inter)

    best: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for lot_idx, zone_idx, a in zip(li, zi, inter_area):
        if a > 0:
            best[int(lot_idx)][zone_codes[int(zone_idx)]] += float(a)

    zone_out: list[str | None] = [None] * len(lot_geoms)
    frac_out: list[float | None] = [None] * len(lot_geoms)
    lot_areas = shapely.area(lots)
    for lot_idx, zmap in best.items():
        code, area = max(zmap.items(), key=lambda kv: kv[1])
        zone_out[lot_idx] = code
        frac_out[lot_idx] = min(1.0, area / lot_areas[lot_idx]) if lot_areas[lot_idx] else None
    return zone_out, frac_out


def flag_z_overlay(lot_geoms: list, z_geoms: list, shrink_ft: float = 0.5):
    """Boolean array: lot has ANY portion inside a Constrained Sites (z) polygon.

    Lots are shrunk slightly first so a shared boundary with a neighboring z
    polygon doesn't count as being inside it.
    """
    import numpy as np
    import shapely
    from shapely.strtree import STRtree

    flag = np.zeros(len(lot_geoms), dtype=bool)
    if not z_geoms:
        return flag
    tree = STRtree(np.array(z_geoms, dtype=object))
    shrunk = shapely.buffer(np.array(lot_geoms, dtype=object), -shrink_ft)
    li, _ = tree.query(shrunk, predicate="intersects")
    flag[li] = True
    return flag


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", action="store_true",
                    help="print JURIS_CITY histogram and exit")
    args = ap.parse_args()

    rules = load_rules()
    lots = read_stage("s1_lots")

    if args.report:
        hist = Counter((str(v).strip().upper() or "<blank>")
                       for v in lots["JURIS_CITY"].fillna("<null>"))
        for code, n in hist.most_common():
            mapped = rules.jurisdiction_for_juris_city(code)
            print(f"  {code!r:30} {n:>8,}  -> {mapped}")
        return

    lots["jurisdiction"] = [
        rules.jurisdiction_for_juris_city(v) for v in lots["JURIS_CITY"]
    ]

    # Zone join, one zoning layer at a time; a layer may serve several
    # jurisdictions (Metro regional zoning covers Fairview + unincorporated).
    lots["zone_raw"] = None
    lots["zone_frac"] = None
    by_layer: dict[str, list[str]] = defaultdict(list)
    for key, j in rules.jurisdictions.items():
        if j.eligible and j.zoning_layer:
            by_layer[j.zoning_layer].append(key)

    for layer, juris_keys in by_layer.items():
        zdf = read_stage(f"s1_zoning_{layer}")
        mask = lots["jurisdiction"].isin(juris_keys)
        idx = lots.index[mask]
        if not len(idx):
            print(f"{layer}: no lots routed — skipping")
            continue
        print(f"{layer}: assigning {len(idx):,} lots against "
              f"{len(zdf):,} zone polygons ({', '.join(juris_keys)})")
        zone_raw, zone_frac = assign_majority_zone(
            list(lots.loc[idx, "geom"]),
            list(zdf["geom"]),
            [str(z) if z is not None else "" for z in zdf["zone_raw"]],
        )
        lots.loc[idx, "zone_raw"] = zone_raw
        lots.loc[idx, "zone_frac"] = zone_frac

    lots["split_zone"] = lots["zone_frac"].map(
        lambda v: bool(v is not None and v < SPLIT_ZONE_THRESHOLD)
    )

    # UGB membership via representative point (cheap, robust for lots).
    import numpy as np
    from shapely.strtree import STRtree
    import shapely

    ugb = read_stage("s1_ugb")
    tree = STRtree(np.array(list(ugb["geom"]), dtype=object))
    reps = shapely.point_on_surface(np.array(list(lots["geom"]), dtype=object))
    li, _ = tree.query(reps, predicate="within")
    inside = np.zeros(len(lots), dtype=bool)
    inside[li] = True
    lots["inside_ugb"] = inside

    # Portland Constrained Sites overlay (PCC 33.418, map symbol "z"): the
    # triplex/fourplex allowance (33.110.265.E) does not apply to lots where
    # ANY portion is inside the overlay, in every R20-R2.5 zone. Flag here for
    # the s3 funnel; the Portland layer also covers the Portland-administered
    # unincorporated pockets (UNINC areas). OVRLY is comma-separated letters.
    from common import DATA_DIR, features_to_geoms, load_geojson_features

    z_flag = np.zeros(len(lots), dtype=bool)
    raw_pdx = DATA_DIR / "raw" / "zoning_portland.geojson"
    if raw_pdx.exists():
        z_feats = [
            f for f in load_geojson_features(raw_pdx)
            if "z" in ((f.get("properties") or {}).get("OVRLY") or "")
        ]
        z_geoms = [
            shapely.make_valid(g) for g in features_to_geoms(z_feats) if g is not None
        ]
        z_flag = flag_z_overlay(list(lots["geom"]), z_geoms)
        print(f"z overlay: {int(z_flag.sum()):,} lots touch Constrained Sites "
              f"({len(z_geoms):,} z polygons, PCC 33.418)")
    lots["has_z_overlay"] = z_flag

    assigned = lots["zone_raw"].notna().sum()
    print(f"s2: {assigned:,}/{len(lots):,} lots have a zone; "
          f"{lots['split_zone'].sum():,} split-zone; "
          f"{inside.sum():,} inside UGB")
    write_stage(lots, "s2_lots")
    print("s2 done.")


if __name__ == "__main__":
    main()
