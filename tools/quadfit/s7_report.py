"""s7 — aggregate results: per-lot table, summary.md, spot-check GeoJSON.

Headline statistics use tiers A+B only (clean geometry); tier C (irregular,
conservative envelope) is reported separately; tier D is excluded. frontier_json
holds max-depth-per-width in CELLS at s6_meta grid resolution.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL_DIR))

from common import DATA_DIR, load_footprints, load_rules, read_stage

HEADLINE_TIERS = ("A", "B")


def _pct(n: int, d: int) -> str:
    return f"{100.0 * n / d:.1f}%" if d else "n/a"


def sweep_fit_matrix(df, widths_ft, frontier_cells, res, sweep):
    """Boolean matrix lots x sweep-widths for a constant-area sweep."""
    import numpy as np

    cols = []
    for w in sweep.widths():
        try:
            w_idx = widths_ft.index(round(w, 4))
        except ValueError:
            cols.append(np.zeros(len(df), dtype=bool))
            continue
        d_needed_cells = math.ceil((sweep.area_sqft / w) / res)
        cols.append(frontier_cells[:, w_idx] >= d_needed_cells)
    return np.column_stack(cols)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spot-check", type=int, default=36)
    args = ap.parse_args()

    import numpy as np
    import pandas as pd

    rules = load_rules()
    fps = load_footprints()
    meta = json.loads((DATA_DIR / "s6_meta.json").read_text(encoding="utf-8"))
    res = meta["grid_resolution_ft"]
    widths_ft = [round(w, 4) for w in meta["frontier_widths_ft"]]
    fp_names = [f["name"] for f in meta["footprints"]]

    lots = read_stage("s6_lots")
    frontier_cells = np.array([json.loads(s) for s in lots["frontier_json"]], dtype=np.int32)
    funnel = json.loads((DATA_DIR / "funnel.json").read_text(encoding="utf-8"))

    head = lots[lots["tier"].isin(HEADLINE_TIERS)]
    head_frontier = frontier_cells[lots["tier"].isin(HEADLINE_TIERS).to_numpy()]

    L: list[str] = []
    L.append("# Quadfit — Multnomah County quadplex buildability\n")
    L.append(f"Grid resolution {res} ft · headline universe = tiers A+B "
             f"({len(head):,} of {len(lots):,} eligible lots). Results are an "
             "**upper bound** — see Blind spots.\n")

    # Rules confidence disclosure
    unverified = [
        (k, z.zone) for k, j in rules.jurisdictions.items()
        for z in j.zones if z.confidence != "verified"
    ]
    if unverified:
        L.append(f"\n> ⚠ {len(unverified)} zone rules still `needs_verification`: "
                 + ", ".join(f"{k}:{z}" for k, z in unverified) + "\n")

    L.append("\n## Exclusion funnel\n")
    L.append("| step | dropped | remaining |")
    L.append("|---|---:|---:|")
    L.append(f"| {funnel[0]['step']} | | {funnel[0]['count']:,} |")
    for row in funnel[1:]:
        L.append(f"| {row['step']} | {row['dropped']:,} | {row['remaining']:,} |")

    L.append("\n## Eligible universe\n")
    L.append("| jurisdiction | lots | tier A | B | C | D |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for j, grp in lots.groupby("jurisdiction"):
        t = grp["tier"].value_counts()
        L.append(f"| {j} | {len(grp):,} | {t.get('A',0):,} | {t.get('B',0):,} "
                 f"| {t.get('C',0):,} | {t.get('D',0):,} |")

    L.append("\n## Footprint fit rates (headline: tiers A+B)\n")
    L.append("| footprint | fits | fit % | +coverage ok | flip-only | tier C fits |")
    L.append("|---|---:|---:|---:|---:|---:|")
    tier_c = lots[lots["tier"] == "C"]
    for name in fp_names:
        fits = int(head[f"fits_{name}"].sum())
        cov = int(head[f"fits_cov_{name}"].sum())
        flip_only = int((head[f"fits_{name}_df"] & ~head[f"fits_{name}_wf"]).sum())
        c_fits = int(tier_c[f"fits_{name}"].sum())
        L.append(f"| {name} | {fits:,} | {_pct(fits, len(head))} | {cov:,} "
                 f"| {flip_only:,} | {c_fits:,}/{len(tier_c):,} |")

    L.append("\n### By jurisdiction\n")
    L.append("| jurisdiction | " + " | ".join(fp_names) + " | any |")
    L.append("|---|" + "---:|" * (len(fp_names) + 1))
    any_fit = np.zeros(len(head), dtype=bool)
    for name in fp_names:
        any_fit |= head[f"fits_{name}"].to_numpy()
    head = head.assign(_any=any_fit)
    for j, grp in head.groupby("jurisdiction"):
        cells = [
            _pct(int(grp[f"fits_{name}"].sum()), len(grp)) for name in fp_names
        ]
        cells.append(_pct(int(grp["_any"].sum()), len(grp)))
        L.append(f"| {j} ({len(grp):,}) | " + " | ".join(cells) + " |")

    L.append("\n### By zone (10 largest)\n")
    L.append("| jurisdiction / zone | lots | " + " | ".join(fp_names) + " |")
    L.append("|---|---:|" + "---:|" * len(fp_names))
    zone_sizes = head.groupby(["jurisdiction", "zone"]).size().sort_values(ascending=False)
    for (j, z), n in zone_sizes.head(10).items():
        grp = head[(head["jurisdiction"] == j) & (head["zone"] == z)]
        cells = [_pct(int(grp[f"fits_{name}"].sum()), len(grp)) for name in fp_names]
        L.append(f"| {j} / {z} | {n:,} | " + " | ".join(cells) + " |")

    if len(fp_names) >= 2:
        L.append("\n### Marginal unlock between footprints\n")
        L.append("| gained by | over | lots unlocked | lots lost |")
        L.append("|---|---|---:|---:|")
        for a in fp_names:
            for b in fp_names:
                if a >= b:
                    continue
                fa, fb = head[f"fits_{a}"], head[f"fits_{b}"]
                L.append(f"| {b} | {a} | {int((fb & ~fa).sum()):,} "
                         f"| {int((fa & ~fb).sum()):,} |")

    head_gate = (
        head["frontage_ok"].to_numpy()
        if "frontage_ok" in head.columns
        else np.ones(len(head), dtype=bool)
    )
    for sweep in fps.constant_area_sweeps:
        L.append(f"\n## Fixed-area sweep — {sweep.area_sqft:.0f} sqft footprint\n")
        m = sweep_fit_matrix(head, widths_ft, head_frontier, res, sweep)
        m &= head_gate[:, None]  # min-frontage rules gate sweeps too
        sw = sweep.widths()
        L.append("| width ft | depth ft | fit % (A+B) |")
        L.append("|---:|---:|---:|")
        rates = m.mean(axis=0)
        for w, r in zip(sw, rates):
            L.append(f"| {w:.1f} | {sweep.area_sqft / w:.1f} | {100*r:.1f}% |")
        best_i = int(np.argmax(rates))
        L.append(f"\n**County-wide optimum: {sw[best_i]:.1f} × "
                 f"{sweep.area_sqft / sw[best_i]:.1f} ft — fits "
                 f"{_pct(int(m[:, best_i].sum()), len(head))} of headline lots.**\n")
        L.append("Per-jurisdiction optima:\n")
        for j in sorted(head["jurisdiction"].unique()):
            mask = (head["jurisdiction"] == j).to_numpy()
            if not mask.any():
                continue
            jr = m[mask].mean(axis=0)
            bi = int(np.argmax(jr))
            L.append(f"- {j}: {sw[bi]:.1f} × {sweep.area_sqft / sw[bi]:.1f} ft "
                     f"({100*jr[bi]:.1f}%)")

    L.append("\n## Max-rectangle frontier distribution (tiers A+B)\n")
    L.append("| width ft | median max depth | 25th pct | 75th pct | % supporting ≥25 ft depth |")
    L.append("|---:|---:|---:|---:|---:|")
    for w in (18.0, 20.0, 25.0, 30.0, 40.0):
        if round(w, 4) not in widths_ft:
            continue
        wi = widths_ft.index(round(w, 4))
        depths = head_frontier[:, wi] * res
        L.append(f"| {w:.0f} | {np.median(depths):.1f} | "
                 f"{np.percentile(depths, 25):.1f} | {np.percentile(depths, 75):.1f} | "
                 f"{100 * (depths >= 25).mean():.1f}% |")

    L.append("\n## Blind spots (results are a ceiling)\n")
    L.append("- Private easements (title reports only) are not modeled.")
    L.append("- Portland tree preservation, environmental/historic/design overlays, "
             "steep slopes, floodplains: NOT applied (phase 2).")
    L.append("- Existing structures assumed demolished; building value & year built "
             "are carried per-lot for later filtering.")
    L.append("- On-lot parking feasibility out of scope by design.")
    L.append("- Envelope + raster are conservative (~±" + str(res) + " ft), so the "
             "geometric side slightly UNDER-counts fits; unmodeled overlays "
             "over-count. Net: treat as upper bound.")

    (DATA_DIR / "summary.md").write_text("\n".join(L), encoding="utf-8")
    print(f"wrote {DATA_DIR / 'summary.md'}")

    # Per-lot CSV (compact) — full detail stays in s6_lots.parquet.
    csv_cols = [
        "TLID", "SITEADDR", "jurisdiction", "zone", "tier", "area_sqft",
        "envelope_sqft", "frontage_ft", "YEARBUILT", "BLDGSQFT", "BLDGVAL",
        "TOTALVAL", "split_zone",
    ] + [f"fits_{n}" for n in fp_names] + [f"fits_cov_{n}" for n in fp_names]
    out = lots[csv_cols].copy()
    out.to_csv(DATA_DIR / "lots_results.csv", index=False)
    print(f"wrote {DATA_DIR / 'lots_results.csv'} ({len(out):,} rows)")

    # Spot-check sample: lot + envelope + placed rectangle, in WGS84.
    _write_spot_check(lots, rules, fps, meta, args.spot_check)
    print("s7 done.")


def _write_spot_check(lots, rules, fps, meta, n_sample: int) -> None:
    import shapely
    from pyproj import Transformer

    import s6_fit
    from common import CRS_WGS84, CRS_WORKING

    s3 = read_stage("s3_lots")[["TLID", "geom"]].rename(columns={"geom": "lot_geom"})
    s5 = read_stage("s5_lots")[["TLID", "geom"]].rename(columns={"geom": "env_geom"})
    sample = (
        lots.groupby(["jurisdiction", "tier"], group_keys=False, sort=False)
        .head(2)
        .head(n_sample)
    )
    sample = sample.merge(s3, on="TLID").merge(s5, on="TLID")

    res = meta["grid_resolution_ft"]
    cfg = {
        "res": res,
        "width_cells": [round(w / res) for w in meta["frontier_widths_ft"]],
        "footprints": [(f["name"], f["width_ft"], f["depth_ft"]) for f in meta["footprints"]],
    }
    s6_fit._init_worker(cfg)
    fp0 = fps.footprints[0]

    tr = Transformer.from_crs(CRS_WORKING, CRS_WGS84, always_xy=True)

    def to4326(geom):
        import numpy as np

        def _fn(coords):
            x, y = tr.transform(coords[:, 0], coords[:, 1])
            return np.column_stack([x, y])

        return shapely.transform(geom, _fn)

    feats = []
    for row in sample.itertuples(index=False):
        allow_flip = (
            rules.jurisdictions[row.jurisdiction].orientation_constraint != "axis_required"
        )
        r = s6_fit.fit_lot(
            shapely.to_wkb(row.env_geom),
            json.loads(row.front_bearings_json),
            allow_flip,
            collect_placement=(fp0.width_ft, fp0.depth_ft),
        )
        props = {
            "tlid": row.TLID, "addr": row.SITEADDR, "jurisdiction": row.jurisdiction,
            "zone": row.zone, "tier": row.tier,
        }
        feats.append({"type": "Feature", "properties": {**props, "role": "lot"},
                      "geometry": json.loads(shapely.to_geojson(to4326(row.lot_geom)))})
        if not row.env_geom.is_empty:
            feats.append({"type": "Feature", "properties": {**props, "role": "envelope"},
                          "geometry": json.loads(shapely.to_geojson(to4326(row.env_geom)))})
        if r["placement"]:
            rect = shapely.from_wkb(r["placement"])
            feats.append({"type": "Feature",
                          "properties": {**props, "role": f"fit_{fp0.name}"},
                          "geometry": json.loads(shapely.to_geojson(to4326(rect)))})

    doc = {"type": "FeatureCollection", "features": feats}
    (DATA_DIR / "spot_check.geojson").write_text(json.dumps(doc), encoding="utf-8")
    print(f"wrote {DATA_DIR / 'spot_check.geojson'} ({len(feats)} features)")


if __name__ == "__main__":
    main()
