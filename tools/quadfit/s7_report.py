"""s7 — POLICY gates + aggregation: per-lot table, summary.md, spot-check.

s6 output is a pure-geometry superset (every lot with a computable envelope,
both orientations tested). This stage applies everything configurable:

- jurisdiction eligibility (rules.yaml `eligible` toggles)
- Portland Constrained Sites z overlay (PCC 33.418)
- per-zone quadplex minimum lot area / minimum frontage
- orientation constraints (axis_required disables the 90° flip)
- coverage caps (percent or curve)
- large-lot subdivision screen (footprints.yaml `split` block)

So toggling a jurisdiction, adjusting a threshold, or changing the parking
buffer needs ONLY this stage re-run:  uv run --extra gis python tools/quadfit/s7_report.py

Headline statistics use tiers A+B only (clean geometry); tier C (irregular,
conservative envelope) is reported separately; tier D is excluded. frontier_json
holds max-depth-per-width in CELLS at s6_meta grid resolution.

Outputs: summary.md · lots_results.csv (all geometry-universe lots, with
policy_exclusion column) · conversion_candidates.csv (eligible, fits, NOT a
split candidate) · split_candidates.csv (eligible, >= min_quads if split) ·
spot_check.geojson.
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
Z_OVERLAY_JURISDICTIONS = ("portland", "multnomah_unincorporated")


def _pct(n: int, d: int) -> str:
    return f"{100.0 * n / d:.1f}%" if d else "n/a"


def policy_gates(lots, rules):
    """Per-lot policy columns from the CURRENT rules.yaml.

    Returns (gates DataFrame aligned to lots, policy funnel rows). The funnel
    counts first-hit exclusions in a fixed order over the geometry universe.
    """
    import numpy as np
    import pandas as pd

    n = len(lots)
    elig_j = np.zeros(n, dtype=bool)
    z_ok = np.ones(n, dtype=bool)
    min_lot_ok = np.ones(n, dtype=bool)
    frontage_ok = np.ones(n, dtype=bool)
    flip_allowed = np.ones(n, dtype=bool)
    cov_cap = np.full(n, np.nan)
    accessory = np.zeros(n)

    has_z = (
        lots["has_z_overlay"].to_numpy()
        if "has_z_overlay" in lots.columns
        else np.zeros(n, dtype=bool)
    )
    for i, (jkey, zraw, area, frontage, hz) in enumerate(zip(
        lots["jurisdiction"], lots["zone_raw"], lots["area_sqft"],
        lots["frontage_ft"], has_z,
    )):
        j = rules.jurisdictions[jkey]
        rule = j.rule_for(zraw)
        elig_j[i] = j.eligible
        if jkey in Z_OVERLAY_JURISDICTIONS and hz:
            z_ok[i] = False
        if rule is None:
            continue
        if rule.min_lot_sqft is not None and float(area) < rule.min_lot_sqft:
            min_lot_ok[i] = False
        if rule.min_frontage_ft is not None and float(frontage) < rule.min_frontage_ft:
            frontage_ok[i] = False
        constraint = rule.orientation_constraint or j.orientation_constraint
        flip_allowed[i] = constraint != "axis_required"
        cap = rule.coverage_cap_sqft(float(area))
        if cap is not None:
            cov_cap[i] = cap
        accessory[i] = rule.accessory_allowance_sqft

    gates = pd.DataFrame({
        "elig_jurisdiction": elig_j, "z_ok": z_ok, "min_lot_ok": min_lot_ok,
        "frontage_ok": frontage_ok, "flip_allowed": flip_allowed,
        "cov_cap": cov_cap, "accessory": accessory,
    }, index=lots.index)

    # First-hit policy funnel + per-lot exclusion label.
    steps = [
        ("jurisdiction_disabled", ~gates["elig_jurisdiction"]),
        ("z_overlay_constrained_site", ~gates["z_ok"]),
        ("lot_below_zone_min_area", ~gates["min_lot_ok"]),
        ("below_min_frontage", ~gates["frontage_ok"]),
    ]
    exclusion = pd.Series("", index=lots.index)
    remaining = pd.Series(True, index=lots.index)
    funnel = []
    for name, bad in steps:
        hit = remaining & bad
        exclusion[hit] = name
        remaining &= ~bad
        funnel.append({"step": name, "dropped": int(hit.sum()),
                       "remaining": int(remaining.sum())})
    gates["policy_exclusion"] = exclusion
    gates["eligible"] = remaining
    return gates, funnel


def quads_if_split(lots, gates, rules, split):
    """Vector of carve-count estimates (0 where ineligible / nothing fits).

    Each carved lot must supply split.per_quad_lot_sqft() of buildable
    envelope AND satisfy the zone's quadplex minimum lot area. Interior-lot
    setback loss from new lot lines is NOT modeled (stated approximation).
    """
    import numpy as np

    per_quad = split.per_quad_lot_sqft()
    out = np.zeros(len(lots), dtype=int)
    for i, (jkey, zraw, area, env) in enumerate(zip(
        lots["jurisdiction"], lots["zone_raw"], lots["area_sqft"],
        lots["envelope_sqft"],
    )):
        rule = rules.jurisdictions[jkey].rule_for(zraw)
        if rule is None:
            continue
        denom = max(per_quad, rule.min_lot_sqft or 0.0)
        out[i] = min(
            int(float(area) // denom), int(float(env) // per_quad)
        )
    return np.where(gates["eligible"].to_numpy(), out, 0)


def sweep_fit_matrix(df, widths_ft, frontier_cells, res, sweep, flip_allowed):
    """Boolean matrix lots x sweep-widths for a constant-area sweep.

    Both orientations, matching the named-footprint treatment: width-facing
    (W along the front line, depth D = area/W into the lot) OR — where
    orientation policy allows — flipped (D along the front, W into the lot).
    The flip reads the frontier at the smallest grid width >= D (conservative).
    """
    import bisect

    import numpy as np

    cols = []
    for w in sweep.widths():
        d_needed = sweep.area_sqft / w
        try:
            w_idx = widths_ft.index(round(w, 4))
        except ValueError:
            cols.append(np.zeros(len(df), dtype=bool))
            continue
        wf = frontier_cells[:, w_idx] >= math.ceil(d_needed / res)
        d_idx = bisect.bisect_left(widths_ft, round(d_needed, 4))
        if d_idx < len(widths_ft):
            flipped = flip_allowed & (
                frontier_cells[:, d_idx] >= math.ceil(w / res)
            )
        else:
            flipped = np.zeros(len(df), dtype=bool)
        cols.append(wf | flipped)
    return np.column_stack(cols)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spot-check", type=int, default=36)
    args = ap.parse_args()

    import numpy as np

    rules = load_rules()
    fps = load_footprints()
    meta = json.loads((DATA_DIR / "s6_meta.json").read_text(encoding="utf-8"))
    res = meta["grid_resolution_ft"]
    widths_ft = [round(w, 4) for w in meta["frontier_widths_ft"]]
    fps_meta = meta["footprints"]
    fp_names = [f["name"] for f in fps_meta]

    lots = read_stage("s6_lots")
    struct_funnel = json.loads((DATA_DIR / "funnel.json").read_text(encoding="utf-8"))

    gates, pol_funnel = policy_gates(lots, rules)
    lots = lots.join(gates)

    # Orientation policy + coverage, from raw wf/df geometry results.
    for f in fps_meta:
        name, w_ft, d_ft = f["name"], f["width_ft"], f["depth_ft"]
        wf = lots[f"fits_{name}_wf"].to_numpy()
        df_ = lots[f"fits_{name}_df"].to_numpy() & lots["flip_allowed"].to_numpy()
        lots[f"fits_{name}"] = wf | df_
        lots[f"flip_only_{name}"] = df_ & ~wf
        cap = lots["cov_cap"].to_numpy()
        cov_ok = np.isnan(cap) | (w_ft * d_ft + lots["accessory"].to_numpy() <= cap)
        lots[f"fits_cov_{name}"] = lots[f"fits_{name}"] & cov_ok

    elig = lots[lots["eligible"]]
    frontier_cells_e = np.array(
        [json.loads(s) for s in elig["frontier_json"]], dtype=np.int32
    )
    head_mask = elig["tier"].isin(HEADLINE_TIERS).to_numpy()
    head = elig[head_mask]
    head_frontier = frontier_cells_e[head_mask]

    any_fit = np.zeros(len(head), dtype=bool)
    for name in fp_names:
        any_fit |= head[f"fits_{name}"].to_numpy()
    head = head.assign(_any=any_fit)

    # Split screen (attribute math — see footprints.yaml `split`).
    split = fps.split
    if split is not None:
        elig_any = np.zeros(len(elig), dtype=bool)
        for name in fp_names:
            elig_any |= elig[f"fits_{name}"].to_numpy()
        q = quads_if_split(elig, gates.loc[elig.index], rules, split)
        q = np.where(elig_any, q, 0)  # parent must host at least one quad shape
        elig = elig.assign(quads_if_split=q,
                           split_candidate=q >= split.min_quads)

    L: list[str] = []
    L.append("# Quadfit — Multnomah County quadplex buildability\n")
    L.append(f"Grid resolution {res} ft · headline universe = tiers A+B "
             f"({len(head):,} of {len(elig):,} eligible lots; geometry universe "
             f"{len(lots):,}). Results are an **upper bound** — see Blind spots.\n")

    unverified = [
        (k, z.zone) for k, j in rules.jurisdictions.items() if j.eligible
        for z in j.zones if z.confidence != "verified"
    ]
    if unverified:
        L.append(f"\n> ⚠ {len(unverified)} zone rules still `needs_verification`: "
                 + ", ".join(f"{k}:{z}" for k, z in unverified) + "\n")
    disabled = [k for k, j in rules.jurisdictions.items() if not j.eligible and j.zones]
    if disabled:
        L.append(f"\n> Jurisdictions disabled by policy: {', '.join(disabled)} "
                 "(re-enable with `eligible: true` + s7 re-run only)\n")

    L.append("\n## Exclusion funnel\n")
    L.append("| step | dropped | remaining |")
    L.append("|---|---:|---:|")
    L.append(f"| {struct_funnel[0]['step']} | | {struct_funnel[0]['count']:,} |")
    for row in struct_funnel[1:]:
        L.append(f"| {row['step']} | {row['dropped']:,} | {row['remaining']:,} |")
    for row in pol_funnel:
        L.append(f"| {row['step']} (policy) | {row['dropped']:,} | {row['remaining']:,} |")

    L.append("\n## Eligible universe\n")
    L.append("| jurisdiction | lots | tier A | B | C | D |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for j, grp in elig.groupby("jurisdiction"):
        t = grp["tier"].value_counts()
        L.append(f"| {j} | {len(grp):,} | {t.get('A',0):,} | {t.get('B',0):,} "
                 f"| {t.get('C',0):,} | {t.get('D',0):,} |")

    L.append("\n## Footprint fit rates (headline: tiers A+B)\n")
    L.append("| footprint | fits | fit % | +coverage ok | flip-only | tier C fits |")
    L.append("|---|---:|---:|---:|---:|---:|")
    tier_c = elig[elig["tier"] == "C"]
    for name in fp_names:
        fits = int(head[f"fits_{name}"].sum())
        cov = int(head[f"fits_cov_{name}"].sum())
        flip_only = int(head[f"flip_only_{name}"].sum())
        c_fits = int(tier_c[f"fits_{name}"].sum())
        L.append(f"| {name} | {fits:,} | {_pct(fits, len(head))} | {cov:,} "
                 f"| {flip_only:,} | {c_fits:,}/{len(tier_c):,} |")

    L.append("\n### By jurisdiction\n")
    L.append("| jurisdiction | " + " | ".join(fp_names) + " | any |")
    L.append("|---|" + "---:|" * (len(fp_names) + 1))
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

    for sweep in fps.constant_area_sweeps:
        L.append(f"\n## Fixed-area sweep — {sweep.area_sqft:.0f} sqft footprint\n")
        m = sweep_fit_matrix(head, widths_ft, head_frontier, res, sweep,
                             head["flip_allowed"].to_numpy())
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

    if split is not None:
        sc = elig[elig["split_candidate"]]
        conv = elig[~elig["split_candidate"] & (
            np.logical_or.reduce([elig[f"fits_{n}"].to_numpy() for n in fp_names])
        )]
        L.append("\n## Large-lot subdivision screen\n")
        L.append(f"Per carved quadplex lot: {split.quad_ground_sqft:,.0f} sqft "
                 f"buildable + {split.units_per_quad} units × "
                 f"{split.parking_slots_per_unit} slots × "
                 f"{split.parking_sqft_per_slot:,.0f} sqft = "
                 f"**{split.per_quad_lot_sqft():,.0f} sqft each** (stalls only, "
                 "no travel lanes; new interior lot-line setbacks not modeled; "
                 "zone quadplex minimum lot area also enforced per carved lot). "
                 "Conversion lots (below) carry NO parking requirement.\n")
        L.append(f"- **Split candidates (≥{split.min_quads} quads): {len(sc):,} lots** "
                 f"→ theoretical {int(sc['quads_if_split'].sum()):,} quadplexes "
                 f"({int(sc['quads_if_split'].sum()) * split.units_per_quad:,} units)")
        L.append(f"- 1-for-1 conversion candidates (fit, not split-worthy): {len(conv):,} lots\n")
        L.append("| jurisdiction | split lots | theoretical quads |")
        L.append("|---|---:|---:|")
        for j, grp in sc.groupby("jurisdiction"):
            L.append(f"| {j} | {len(grp):,} | {int(grp['quads_if_split'].sum()):,} |")
        L.append("\nTop 15 by carve count:\n")
        L.append("| TLID | address | jurisdiction / zone | lot sqft | buildable sqft | quads |")
        L.append("|---|---|---|---:|---:|---:|")
        for row in sc.sort_values("quads_if_split", ascending=False).head(15).itertuples(index=False):
            L.append(f"| {row.TLID} | {row.SITEADDR or '—'} | {row.jurisdiction} / "
                     f"{row.zone} | {row.area_sqft:,.0f} | {row.envelope_sqft:,.0f} "
                     f"| {row.quads_if_split} |")

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
    L.append("- Portland tree preservation, environmental/historic/design overlays "
             "beyond the z gate, steep slopes, floodplains: NOT applied (phase 2).")
    L.append("- Existing structures assumed demolished; building value & year built "
             "are carried per-lot for later filtering.")
    L.append("- Conversion lots: on-lot parking out of scope by design. Split lots: "
             "parking buffer is stalls-only (no travel lanes, no geometry check).")
    L.append("- Split screen ignores subdivision road/utility/frontage requirements "
             "and new interior-lot-line setbacks — treat as a lead list, not a yield.")
    L.append("- Envelope + raster are conservative (~±" + str(res) + " ft), so the "
             "geometric side slightly UNDER-counts fits; unmodeled overlays "
             "over-count. Net: treat as upper bound.")

    (DATA_DIR / "summary.md").write_text("\n".join(L), encoding="utf-8")
    print(f"wrote {DATA_DIR / 'summary.md'}")

    # Per-lot CSVs. Master = whole geometry universe with policy_exclusion.
    csv_cols = [
        "TLID", "SITEADDR", "jurisdiction", "zone", "tier", "area_sqft",
        "envelope_sqft", "frontage_ft", "YEARBUILT", "BLDGSQFT", "BLDGVAL",
        "TOTALVAL", "split_zone", "policy_exclusion", "eligible",
    ] + [f"fits_{n}" for n in fp_names] + [f"fits_cov_{n}" for n in fp_names]
    lots[csv_cols].to_csv(DATA_DIR / "lots_results.csv", index=False)
    print(f"wrote {DATA_DIR / 'lots_results.csv'} ({len(lots):,} rows)")

    if split is not None:
        sub_cols = [
            "TLID", "SITEADDR", "jurisdiction", "zone", "tier", "area_sqft",
            "envelope_sqft", "frontage_ft", "YEARBUILT", "BLDGSQFT", "BLDGVAL",
            "TOTALVAL",
        ]
        sc = elig[elig["split_candidate"]].sort_values("quads_if_split", ascending=False)
        sc[sub_cols + ["quads_if_split"]].to_csv(
            DATA_DIR / "split_candidates.csv", index=False)
        conv_mask = ~elig["split_candidate"] & np.logical_or.reduce(
            [elig[f"fits_{n}"].to_numpy() for n in fp_names])
        elig[conv_mask][sub_cols + [f"fits_{n}" for n in fp_names]].to_csv(
            DATA_DIR / "conversion_candidates.csv", index=False)
        print(f"wrote split_candidates.csv ({int(elig['split_candidate'].sum()):,}) "
              f"+ conversion_candidates.csv ({int(conv_mask.sum()):,})")

    _write_spot_check(elig, fps, meta, args.spot_check)
    print("s7 done.")


def _write_spot_check(lots, fps, meta, n_sample: int) -> None:
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
        r = s6_fit.fit_lot(
            shapely.to_wkb(row.env_geom),
            json.loads(row.front_bearings_json),
            bool(row.flip_allowed),
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
