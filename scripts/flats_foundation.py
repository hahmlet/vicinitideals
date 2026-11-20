"""FD6 foundation model, build steps 8 and 9: real ground under each drawn building,
old buildings under it, and the grid vs six-readings comparison (FOLLOWUPS 209).

Never a colour: nothing here is read by the screen, and nothing is written to
the database. Three steps, each reading files in place and writing Parquet:

``grid`` (on LXC 137, light: one process, nice, ``GDAL_CACHEMAX`` small)
    For every lot in the lot file: the drawn building (FD5 extract's
    ``greens_assign.parquet``) and its frame (front = the long side nearer the
    street lines, exactly as FD2 pass 1 named it); a 1 ft grid of ground over the
    footprint plus ``grid_margin_ft``, read from the elevation models the way
    pass 1 read its six readings (:mod:`flats.foundation.terrain`); the MEASURE
    layer on that grid (lump allowance zero). Writes, in parts of ``--part``
    lots, ``lots`` / ``lines`` / ``doors`` (the measured record, no prices),
    ``frames`` (the frame's corners, the model used, and a check of the grid
    reader at the six reading points against the lot file's ``z_*``) and
    ``grid`` (the ground itself, hundredths of a foot above the lot's lowest
    cell as int16 bytes, rows front to back, for later analysis; the measured
    record is taken from the unrounded grid).

``old-buildings`` (this PC)
    The buildings standing today under each pod: the RLIS footprints FD5 pass 2
    used, turned into the model frame with the frames from ``grid``, grown and
    cut against the wall lines (:mod:`flats.foundation.oldbuild`). Writes
    ``buildings`` and ``stretches`` (measured, no prices).

``compare`` (this PC)
    Prices every lot twice -- from the lot file's six readings and from the grid
    -- with the same lot-file inputs and old buildings, and prints the
    comparison; writes both assessed tables.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from flats.foundation import lot as lots_mod  # noqa: E402
from flats.foundation import measure, rows, settings  # noqa: E402
from flats.foundation import ground as grounds  # noqa: E402
from flats.foundation.frame import SIX_UV, Frame, frame  # noqa: E402

PART = 1000


def _lot_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _num(v: Any) -> float | None:
    return lots_mod.num(v if isinstance(v, str) or v is None else str(v))


def _write(out: Path, name: str, part: int, recs: list[dict[str, Any]]) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    if not recs:
        return
    d = out / name
    d.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(recs), d / f"part-{part:04d}.parquet", compression="zstd")


def read_parts(d: Path) -> list[dict[str, Any]]:
    import pyarrow as pa
    import pyarrow.parquet as pq

    parts = sorted(d.glob("part-*.parquet"))
    if not parts:
        return []
    return pa.concat_tables([pq.read_table(p) for p in parts], promote_options="default").to_pylist()


# ---------------------------------------------------------------- grid (LXC 137)


def _grid(args: argparse.Namespace) -> None:
    os.environ.setdefault("GDAL_CACHEMAX", "64")
    import numpy as np
    import pyarrow.parquet as pq

    from flats.foundation.terrain import Dem
    from flats.ingest import quadfit
    from flats.rules.loader import load_rules

    t0 = time.time()
    s = settings.load()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    lots = _lot_rows(Path(args.lots))
    if args.limit:
        lots = lots[: args.limit]
    want = {r["TLID"] for r in lots}
    ex = Path(args.extract)
    assign = {
        r["TLID"]: r
        for r in pq.read_table(ex / "greens_assign.parquet", columns=["TLID", "drawing", "colour"]).to_pylist()
        if r["TLID"] in want
    }
    qrows = {r["TLID"]: r for r in quadfit.iter_rows(ex / "s4_lots.parquet", ex / "s5o_lots.parquet", tlids=sorted(want))}
    layers = load_rules()
    dem = Dem(Path(args.dem), Path(args.coarse) if args.coarse else None)
    print(f"lots {len(lots)} assign {len(assign)} rows {len(qrows)} tiles {len(dem.tiles)} coarse {dem.coarse is not None} "
          f"setup {time.time() - t0:.0f}s", flush=True)
    x0, y0, xs, ys = grounds.grid_centres(s)
    gx, gy = np.meshgrid(np.array(xs), np.array(ys))  # rows front to back, each left to right
    buf: dict[str, list[dict[str, Any]]] = defaultdict(list)
    part = 0
    n = Counter()
    for k, r in enumerate(lots):
        tlid, county = r["TLID"], r["county"]
        fr_rec: dict[str, Any] = {"tlid": tlid, "county": county, "error": None}
        try:
            a = assign.get(tlid)
            ring = (json.loads(a["drawing"]) if a and a.get("drawing") else {}).get("building")
            row = qrows.get(tlid)
            if not ring:
                raise LookupError("no drawn building")
            if row is None:
                raise LookupError("lot row not in s4")
            ql = quadfit.lot_from_row(row, layers)
            streets = tuple(dict.fromkeys(quadfit._street_lines(ql) + quadfit._side_street_lines(ql)))
            fr = frame(ring, streets)
            fr_rec.update(
                fl_x=fr.fl[0], fl_y=fr.fl[1], fr_x=fr.fr[0], fr_y=fr.fr[1], bl_x=fr.bl[0], bl_y=fr.bl[1],
                br_x=fr.br[0], br_y=fr.br[1], long_ft=fr.long_ft, short_ft=fr.short_ft, front_known=fr.front_known,
            )
            z_of, src, cell = dem.z_reader(ring)
            if z_of is None:
                raise LookupError("no elevation model covers the footprint")
            fr_rec.update(elev_source=src, cell_m=cell, lot_file_elev_source=r.get("elev_source") or None)
            # The grid reader at the six reading points against the lot file (same frame,
            # same reader: differences only from the lot file's rounding to 0.01 ft).
            six = z_of(fr.at([u for _, u, _ in SIX_UV], [v for _, _, v in SIX_UV]))
            given = [_num(r.get(name)) for name, _, _ in SIX_UV]
            if all(g is not None for g in given) and np.isfinite(six).all():
                g6 = np.array(given, dtype=float)
                fr_rec["six_max_diff_ft"] = float(np.max(np.abs(six - g6)))
                # the other labellings, to show the frame is not turned
                lr = six[[1, 0, 3, 2, 4, 5]]
                fb = six[[2, 3, 0, 1, 5, 4]]
                fr_rec["six_max_diff_lr_ft"] = float(np.max(np.abs(lr - g6)))
                fr_rec["six_max_diff_fb_ft"] = float(np.max(np.abs(fb - g6)))
            pts = fr.world(gx.ravel(), gy.ravel(), s.length_ft, s.width_ft)
            z = np.asarray(z_of(pts), dtype=float).reshape(gy.shape)
            if not np.isfinite(z).all():
                raise ValueError(f"grid has {int((~np.isfinite(z)).sum())} blank cells")
            g = grounds.cell_grid(z.tolist(), s, cell, f"{src} grid")
            m = measure.measure(g, s, tlid=tlid, county=county, inputs={"relief_input_ft": _num(r.get("relief_ft"))})
            lot_row, lines, doors = rows.measured_rows(m)
            buf["lots"].append(lot_row)
            buf["lines"].extend(lines)
            buf["doors"].extend(doors)
            zmin = float(z.min())
            buf["grid"].append(
                {
                    "tlid": tlid,
                    "x0_ft": x0,
                    "y0_ft": y0,
                    "cell_ft": s.grid_step_ft,
                    "nx": len(xs),
                    "ny": len(ys),
                    "z_min_ft": zmin,
                    # hundredths of a foot above z_min, little-endian int16, rows front to back
                    "z_cft_i16": np.clip(np.round((z - zmin) * 100), 0, 32767).astype("<i2").tobytes(),
                }
            )
            n[src] += 1
        except Exception as exc:  # noqa: BLE001 -- recorded per lot, the run goes on
            fr_rec["error"] = f"{type(exc).__name__}: {exc}"
            n["error"] += 1
        buf["frames"].append(fr_rec)
        if (k + 1) % args.part == 0 or k + 1 == len(lots):
            for name, recs in buf.items():
                _write(out, name, part, recs)
            buf = defaultdict(list)
            part += 1
            print(f"{k + 1}/{len(lots)} {dict(n)} {time.time() - t0:.0f}s", flush=True)
    meta = {
        "lots": len(lots),
        "counts": dict(n),
        "seconds": round(time.time() - t0, 1),
        "geometry": dict(measure.geometry_of(s)),
        "grid_step_ft": s.grid_step_ft,
        "grid_margin_ft": s.grid_margin_ft,
        "extract": str(ex),
        "dem": str(args.dem),
        "coarse": str(args.coarse),
        "code": str(REPO),
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=1, default=list), encoding="utf-8")
    print("done", json.dumps(meta["counts"]), flush=True)


# ---------------------------------------------------------------- old buildings (PC)


def _frame_of(r: dict[str, Any]) -> Frame:
    return Frame((r["fl_x"], r["fl_y"]), (r["fr_x"], r["fr_y"]), (r["bl_x"], r["bl_y"]), (r["br_x"], r["br_y"]),
                 r["long_ft"], r["short_ft"], bool(r["front_known"]))


def _footprints(path: Path) -> tuple[list[Any], list[dict[str, Any]]]:
    """FD5 pass 2's footprint reader (scripts/fd5_pass2.py ``_footprints``, branch flats/fd2-pass1)."""
    import shapely
    from shapely.geometry import shape

    geoms, props = [], []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            d = json.loads(line)
            if not d.get("g"):
                continue
            g = shape(d["g"])
            if not g.is_valid:
                g = shapely.make_valid(g)
            geoms.append(g)
            props.append(d.get("p") or {})
    return geoms, props


def _old(args: argparse.Namespace) -> None:
    import shapely
    from shapely.strtree import STRtree

    from flats.foundation import oldbuild

    t0 = time.time()
    s = settings.load()
    frames = [r for r in read_parts(Path(args.grid) / "frames") if r.get("fl_x") is not None]
    held = {r["TLID"]: (r.get("bldg_fp_held") or "").strip().lower() == "true" for r in _lot_rows(Path(args.lots))}
    geoms, props = _footprints(Path(args.footprints))
    tree = STRtree(geoms)
    print(f"frames {len(frames)} footprints {len(geoms)} {time.time() - t0:.0f}s", flush=True)
    bl_rows, st_rows, lot_rows = [], [], []
    for r in frames:
        fr = _frame_of(r)
        pod = shapely.Polygon([fr.fl, fr.fr, fr.br, fr.bl])
        idx = tree.query(shapely.buffer(pod, s.grow_ft + 1.0, join_style="mitre"), predicate="intersects")
        outs = oldbuild.model_outlines(fr, [geoms[i] for i in idx], [props[i] for i in idx], s)
        found = oldbuild.measure_all(outs, s)
        m = measure.Measured(  # a carrier for the rows only
            tlid=r["tlid"], county=r["county"], ground_source="", cell_m=None, readings=None, relief_input_ft=None,
            relief_sampled_ft=0.0, lump_ft=0.0, fall_along_ft=0.0, fall_across_ft=0.0, high_z=0.0, low_z=0.0,
            low_drop_in=0.0, lines=(), doors=(), fill_volume_ft3=0.0, fill_max_in=0.0, fill_area_over_sf=(),
            ground_class=None, alt_ground_class=None, frost_register_in=None, bldg_overlap_share=None,
            front_face_turn_deg=None, geometry=(), old_buildings_held=held.get(r["tlid"], False), old_buildings=found,
        )
        b, st = rows.old_building_rows(m)
        bl_rows += b
        st_rows += st
        lot_rows.append({"tlid": r["tlid"], "county": r["county"], "old_buildings_held": m.old_buildings_held, "old_buildings_n": len(found)})
    out = Path(args.out)
    _write(out, "old_lots", 0, lot_rows)
    _write(out, "buildings", 0, bl_rows)
    _write(out, "stretches", 0, st_rows)
    print(f"lots {len(lot_rows)} with an old building {sum(1 for x in lot_rows if x['old_buildings_n'])} "
          f"buildings {len(bl_rows)} stretches {len(st_rows)} {time.time() - t0:.0f}s", flush=True)


# ---------------------------------------------------------------- compare (PC)


def _q(vals: list[float], p: float) -> float:
    if not vals:
        return math.nan
    v = sorted(vals)
    i = (len(v) - 1) * p
    lo, hi = math.floor(i), math.ceil(i)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)


def _dist_row(name: str, vals: list[float], fmt: str = "{:,.1f}") -> str:
    if not vals:
        return f"| {name} | 0 | | | | | | | |"
    cells = [fmt.format(x) for x in (min(vals), _q(vals, 0.01), _q(vals, 0.10), _q(vals, 0.5), _q(vals, 0.9), _q(vals, 0.99), max(vals), sum(vals) / len(vals))]
    return f"| {name} | {len(vals)} | " + " | ".join(cells) + " |"


def _flags(res: Any) -> set[str]:
    out = set(res.flags)
    for name in ("B", "A dry"):
        out |= {f"{name}:{f}" for f in res[name].flags}
    return out


def _compare(args: argparse.Namespace) -> None:
    from flats.foundation import model

    t0 = time.time()
    s = settings.load()
    g = Path(args.grid)
    by_lines: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_doors: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in read_parts(g / "lines"):
        by_lines[r["tlid"]].append(r)
    for r in read_parts(g / "doors"):
        by_doors[r["tlid"]].append(r)
    glots = {r["tlid"]: r for r in read_parts(g / "lots")}
    frames = {r["tlid"]: r for r in read_parts(g / "frames")}
    old = Path(args.old)
    by_b: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_s: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in read_parts(old / "buildings"):
        by_b[r["tlid"]].append(r)
    for r in read_parts(old / "stretches"):
        by_s[r["tlid"]].append(r)
    old_held = {r["tlid"]: r["old_buildings_held"] for r in read_parts(old / "old_lots")}
    lot_rows = _lot_rows(Path(args.lots))
    print(f"read {len(glots)} grid lots, {len(lot_rows)} lot-file rows {time.time() - t0:.0f}s", flush=True)

    pairs = []
    a6_rows, ag_rows = [], []
    missing = Counter()
    for row in lot_rows:
        tlid = row["TLID"]
        m6 = lots_mod.measure_row(row, s)
        gl = glots.get(tlid)
        if m6 is None:
            missing["no six readings"] += 1
        if gl is None:
            missing["no grid: " + str((frames.get(tlid) or {}).get("error") or "not run")] += 1
        if m6 is None or gl is None:
            continue
        olds = rows.old_buildings_from_rows(by_b.get(tlid, []), by_s.get(tlid, []))
        held = bool(old_held.get(tlid, False))
        m6 = measure.with_old_buildings(m6, held, olds)
        mg = rows.from_measured_rows(gl, by_lines[tlid], by_doors[tlid])
        mg = measure.with_old_buildings(measure.with_inputs(mg, lots_mod.inputs_of(row)), held, olds)
        r6, rg = lots_mod.assess(m6, s), lots_mod.assess(mg, s)
        pairs.append((row, m6, mg, r6, rg))
        a6_rows.append(rows.assessed_rows(r6)[0])
        ag_rows.append(rows.assessed_rows(rg)[0])
    out = Path(args.out)
    _write(out, "assessed_six", 0, a6_rows)
    _write(out, "assessed_grid", 0, ag_rows)
    print(f"priced {len(pairs)} lots twice {time.time() - t0:.0f}s; not compared {dict(missing)}", flush=True)

    rep: list[str] = []
    w = rep.append
    w("# Foundation model: ground grid vs six readings (FD6 build step 8)\n")
    w(f"Lots compared: {len(pairs)} of {len(lot_rows)}; not compared: {dict(missing)}.")
    w(f"Settings: frost register {'on' if s.use_frost_register else 'off'}; grid {s.grid_step_ft:g} ft cells, "
      f"{s.grid_margin_ft:g} ft margin; lump allowance on the grid 0.\n")
    fr_rows = [frames[p[0]["TLID"]] for p in pairs]
    diffs = [r["six_max_diff_ft"] for r in fr_rows if r.get("six_max_diff_ft") is not None]
    turned = sum(1 for r in fr_rows if r.get("six_max_diff_ft") is not None and min(r["six_max_diff_lr_ft"], r["six_max_diff_fb_ft"]) < r["six_max_diff_ft"] - 0.02)
    src_match = sum(1 for r in fr_rows if r.get("elev_source") == r.get("lot_file_elev_source"))
    w(f"Grid reader at the six points vs the lot file: largest difference median {_q(diffs, 0.5):.3f} ft, "
      f"99th {_q(diffs, 0.99):.3f} ft, max {max(diffs) if diffs else math.nan:.3f} ft; lots where another labelling "
      f"fits better: {turned}; elevation model the same as the lot file's: {src_match} of {len(fr_rows)}.\n")

    def group(pred) -> list[tuple]:
        return [p for p in pairs if pred(p)]

    fine = group(lambda p: (p[2].cell_m or 0) <= s.coarse_cell_over_m)
    coarse = group(lambda p: (p[2].cell_m or 0) > s.coarse_cell_over_m)
    hdr = "| change, grid minus six readings | lots | min | 1st | 10th | median | 90th | 99th | max | mean |\n|---|---|---|---|---|---|---|---|---|---|"
    for label, ps in (("1 m ground model", fine), ("10 m ground model (coarse, reported apart)", coarse)):
        w(f"\n## {label}: {len(ps)} lots\n")
        w(hdr)
        w(_dist_row("B tallest wall (in)", [p[4]["B"].tallest_wall_in - p[3]["B"].tallest_wall_in for p in ps]))
        w(_dist_row("B risers, all 8 doors", [float(p[4]["B"].risers_total - p[3]["B"].risers_total) for p in ps], "{:,.0f}"))
        w(_dist_row("A risers, all 8 doors", [float(p[4]["A dry"].risers_total - p[3]["A dry"].risers_total) for p in ps], "{:,.0f}"))
        w(_dist_row("A deepest fill (in)", [p[4]["A dry"].fill_max_in - p[3]["A dry"].fill_max_in for p in ps]))
        for name in ("A dry", "A wet", "B"):
            for prices in ("low", "high"):
                w(_dist_row(f"{name} cost {prices} ($)", [float(getattr(p[4][name].cost, prices) - getattr(p[3][name].cost, prices)) for p in ps], "{:,.0f}"))
        w(_dist_row("relief sampled (ft)", [p[2].relief_sampled_ft - p[1].relief_sampled_ft for p in ps], "{:,.2f}"))
        # flags
        changed = [p for p in ps if _flags(p[3]) != _flags(p[4])]
        gained, lost = Counter(), Counter()
        for p in changed:
            f6, fg = _flags(p[3]), _flags(p[4])
            gained.update(fg - f6)
            lost.update(f6 - fg)
        w(f"\nLots whose flags change: {len(changed)} of {len(ps)}.")
        for f in sorted(set(gained) | set(lost)):
            w(f"- {f}: gained on {gained[f]}, lost on {lost[f]}")
        cheaper = sum(1 for p in ps if (p[3].style.cheaper_low, p[3].style.cheaper_high) != (p[4].style.cheaper_low, p[4].style.cheaper_high))
        w(f"- the cheaper of A and B changes on {cheaper} lots")
        # lump allowance
        excess = [p[2].high_z - p[1].high_z for p in ps]  # true high above the six readings' high
        allow = [p[1].lump_ft for p in ps]
        err = [a - e for a, e in zip(allow, excess, strict=True)]  # + = allowance too big
        with_lump = [(a, e) for a, e in zip(allow, excess, strict=True) if a > 0]
        w("\nLump allowance (six readings) vs the high ground the grid finds above the six readings' high point:")
        w(hdr.replace("change, grid minus six readings", "ft"))
        w(_dist_row("grid high above six-reading high", excess, "{:,.2f}"))
        w(_dist_row("lump allowance given", allow, "{:,.2f}"))
        w(_dist_row("allowance minus what was there", err, "{:,.2f}"))
        if with_lump:
            small = sum(1 for a, e in with_lump if e > a + 0.05)
            big = sum(1 for a, e in with_lump if e < a - 0.05)
            w(f"- lots given an allowance: {len(with_lump)}; it was too small (by over 0.05 ft) on {small}, too big on {big}, "
              f"within 0.05 ft on {len(with_lump) - small - big}; sum allowed {sum(a for a, _ in with_lump):,.0f} ft vs "
              f"found {sum(max(e, 0) for _, e in with_lump):,.0f} ft")
        none = [e for a, e in zip(allow, excess, strict=True) if a == 0]
        if none:
            w(f"- lots given no allowance: {len(none)}; grid high over 0.25 ft above the six readings on {sum(1 for e in none if e > 0.25)}")

    # movers
    def move(p) -> float:
        return max(abs(float(p[4][n].cost.high - p[3][n].cost.high)) for n in ("A dry", "B"))

    w("\n## The 20 largest movers (largest change in A dry or B high cost)\n")
    w("| TLID | county | cell m | B wall six -> grid (in) | A fill six -> grid (in) | A dry high $ change | B high $ change | high: six+lump vs grid (ft) | low: six vs grid (ft) | reason |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for p in sorted(pairs, key=move, reverse=True)[:20]:
        row, m6, mg, r6, rg = p
        top6 = m6.high_z + m6.lump_ft
        lump_err = top6 - mg.high_z  # + : six readings put the high point too high
        dip = m6.low_z - mg.low_z  # + : the grid finds lower ground
        reasons = []
        if (mg.cell_m or 0) > s.coarse_cell_over_m:
            reasons.append("coarse grid")
        if lump_err > 0.25:
            reasons.append(f"lump allowance {lump_err:.1f} ft too big")
        elif lump_err < -0.25:
            reasons.append(f"a hump {-lump_err:.1f} ft past the lump allowance")
        if dip > 0.25:
            reasons.append(f"a dip {dip:.1f} ft below the six readings")
        if not reasons:
            fill6, fillg = m6.fill_volume_ft3 / 27, mg.fill_volume_ft3 / 27
            reasons.append(f"shape between the readings (fill {fill6:.0f} -> {fillg:.0f} cu yd)")
        w(f"| {row['TLID']} | {row['county']} | {mg.cell_m:g} | {r6['B'].tallest_wall_in:.0f} -> {rg['B'].tallest_wall_in:.0f} | "
          f"{r6['A dry'].fill_max_in:.0f} -> {rg['A dry'].fill_max_in:.0f} | "
          f"{float(rg['A dry'].cost.high - r6['A dry'].cost.high):+,.0f} | {float(rg['B'].cost.high - r6['B'].cost.high):+,.0f} | "
          f"{top6 - m6.low_z:.1f} vs {mg.high_z - m6.low_z:.1f} | {dip:+.1f} | {'; '.join(reasons)} |")

    # old buildings
    w("\n## Old buildings under the pod (FD6 5.8; conditional, not in any total)\n")
    held_n = sum(1 for p in pairs if p[4].infill.held)
    crossed = [p for p in pairs if p[4].infill.wall_crossed]
    floor_only = [p for p in pairs if p[4].infill.any and not p[4].infill.wall_crossed]
    w(f"Lots with footprints held: {held_n} of {len(pairs)}. A wall over an old building: {len(crossed)} lots; "
      f"floor over one but no wall: {len(floor_only)}.")
    remedies = Counter(bc.b_remedy for p in crossed for bc in p[4].infill.buildings)
    nb = Counter(len(p[4].infill.buildings) for p in crossed)
    w(f"Old buildings on those lots: {sum(remedies.values())} ({dict(sorted(nb.items()))} buildings per lot); "
      f"B remedy per building: {dict(remedies)}.")
    w("\n| figure ($) | lots | min | 1st | 10th | median | 90th | 99th | max | mean |\n|---|---|---|---|---|---|---|---|---|---|")
    for method in ("B", "A"):
        for prices in ("low", "high"):
            w(_dist_row(f"{method} if it had a basement, {prices}", [float(p[4].infill.total(method, prices)) for p in crossed], "{:,.0f}"))
            w(_dist_row(f"{method} weighted by year built, {prices}", [float(p[4].infill.weighted(method, prices)) for p in crossed], "{:,.0f}"))
    w(_dist_row("longest stretch (ft)", [p[4].infill.longest_ft for p in crossed]))
    w(_dist_row("wall over old buildings (ft)", [p[4].infill.wall_ft for p in crossed]))
    bands = Counter(p[4].infill.year_band for p in crossed)
    w(f"\nYear built on those lots: {dict(bands)}.")
    w(f"Frost depth used: {dict(Counter(model.embed_of(p[2], s) for p in pairs))} (in: lots).")
    text = "\n".join(rep) + "\n"
    (out / "compare.md").write_text(text, encoding="utf-8")
    print(text)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("grid", help="measure every lot on a ground grid (LXC 137)")
    g.add_argument("--lots", required=True, help="lot file (fd2_lots.csv), read in place")
    g.add_argument("--extract", required=True, help="FD5 extract: greens_assign / s4_lots / s5o_lots parquet")
    g.add_argument("--dem", required=True, help="1 m tiles (quadfit raw/dem)")
    g.add_argument("--coarse", help="10 m model (quadfit raw/dem10_utm)")
    g.add_argument("--out", required=True)
    g.add_argument("--limit", type=int, default=0)
    g.add_argument("--part", type=int, default=PART)
    o = sub.add_parser("old-buildings", help="old buildings under each pod (this PC)")
    o.add_argument("--grid", required=True, help="the grid step's output (its frames)")
    o.add_argument("--lots", required=True)
    o.add_argument("--footprints", required=True, help="RLIS footprints.geojsonl.gz")
    o.add_argument("--out", required=True)
    c = sub.add_parser("compare", help="price both ways and compare (this PC)")
    c.add_argument("--grid", required=True)
    c.add_argument("--old", required=True)
    c.add_argument("--lots", required=True)
    c.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    {"grid": _grid, "old-buildings": _old, "compare": _compare}[args.cmd](args)


if __name__ == "__main__":
    main()
