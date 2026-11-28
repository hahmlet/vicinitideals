"""FD6 foundation model, build steps 8 and 9: real ground under each drawn building,
old buildings under it, and the grid vs six-readings comparison (FOLLOWUPS 209);
and the slice-4 release routine, ``measure-run``.

Never a colour: nothing here is read by the screen, and only ``load`` writes
to the database (``flats.lot_foundation``). The steps read files in place and
write Parquet:

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

``bundle`` (this PC; FD6 step 10)
    The whole measured record of every lot: the grid record (or, where the grid
    has blank cells, the six readings), the lot-file inputs and the old
    buildings, labelled with the drawing it was measured under. Writes the five
    measured tables (``lots`` / ``lines`` / ``doors`` / ``buildings`` /
    ``stretches``, Parquet, for ``python -m flats.foundation reprice``), the same
    records as ``records.jsonl.gz`` (what ``load`` reads: the app image has no
    pyarrow) and ``meta.json``. No prices.

``measure-run`` (on LXC 137, light; slice 4 -- the release routine)
    Every lot a run's assign output draws a building on (``--colours``, default
    green and yellow), measured from the sources themselves, in one command:
    the drawn ring, its frame and a ground grid (1 m model, else the 10 m one);
    the ground class from the soil survey and the mapped hazards under the
    footprint (FD2 pass 1's rules, :mod:`flats.foundation.inputs`), the frost
    register's depth, the assessor's year built, the street-side face's turn,
    and the RLIS old buildings with the "held" flag. Each record is stamped
    with ``--drawing`` / ``--run`` and the drawn ring and its hash, so the lot
    page can tell when the drawing has moved since. One process; every source
    is cut as it is read to what lies within reach of a drawn footprint, so it
    stays well under 1 GB; nice it to 19. Restartable: the population, the
    lot rows and each part of ``--part`` lots are written once (a part
    atomically), and a re-run with the same arguments carries on from the
    first part not written. Writes the bundle ``load`` and ``python -m
    flats.foundation reprice`` read: ``records.jsonl.gz``, the five measured
    tables, ``status.parquet`` (one row per drawn lot: the facts behind its
    ground class, or why it was not measured) and ``meta.json``.

``load`` (the api container; asyncpg only)
    Upserts ``records.jsonl.gz`` into ``flats.lot_foundation`` by county + tlid,
    in one transaction. Idempotent: loading the same file again changes nothing
    but ``loaded_at``. Touches no lot, result, run, colour or flag::

        docker compose run --rm api python scripts/flats_foundation.py load \\
            --records /app/data/flats/foundation/<name>/records.jsonl.gz [--dry-run]
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
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from flats.foundation import lot as lots_mod  # noqa: E402
from flats.foundation import measure, rows, settings  # noqa: E402
from flats.foundation import ground as grounds  # noqa: E402
from flats.foundation import doors  # noqa: E402
from flats.foundation.frame import SIX_UV, Frame, frame  # noqa: E402
from flats.foundation.place import place  # noqa: E402

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
            pts = fr.world(gx.ravel(), gy.ravel(), s.length_ft, s.width_ft, s.box_ft)
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


# ---------------------------------------------------------------- measure-run (LXC 137; slice 4)

#: What a run's lot-status table holds per lot (one row per drawn lot, measured or not).
STATUS_FIELDS = (
    "county", "tlid", "colour", "layer_id", "ground_source", "cell_m", "ground_class", "fd2_ground_class",
    "alt_ground_class", "ground_class_unread", "soil_no_data", "soil_missing", "mukey", "comp_name", "alt_comp", "slide_mapped",
    "slide_top", "liq_top2", "fema_zone", "fema_source", "flood_100", "frost_register_in", "year_built",
    "front_face_turn_deg", "old_buildings_held", "old_buildings_n", "drawing_hash", "error",
)
POP_COLS = ("TLID", "colour", "layer_id", "jurisdiction", "drawing")
#: Read where the assign output has it: the screen's six-step cap facts (FD8).
POP_OPTIONAL = ("foundation_cap",)


def _rss_mb() -> int:
    import resource

    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024


def county_of(layer_id: str | None) -> str | None:
    """A lot's county from its rules layer id (``<state>/<county>/...``)."""
    parts = (layer_id or "").split("/")
    return parts[1] if len(parts) > 1 and parts[1] else None


def population(assign: Path, colours: set[str], out: Path, batch: int = 20000) -> dict[str, Any]:
    """Every lot of a run's assign output with a drawn building and one of
    ``colours``, streamed, in county + TLID order: TLID, county, colour,
    layer_id, jurisdiction, the drawn ring (JSON) and its hash."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    from flats.foundation import record

    recs: list[dict[str, Any]] = []
    n: Counter[str] = Counter()
    pf = pq.ParquetFile(assign)
    want = [*POP_COLS, *(c for c in POP_OPTIONAL if c in pf.schema_arrow.names)]
    for b in pf.iter_batches(batch_size=batch, columns=want):
        cols = {name: b.column(name).to_pylist() for name in want}
        for i, tlid in enumerate(cols["TLID"]):
            colour = cols["colour"][i]
            if colour not in colours:
                continue
            d = cols["drawing"][i]
            ring = (json.loads(d) or {}).get("building") if d else None
            if not ring:
                n[f"{colour} not drawn"] += 1
                continue
            county = county_of(cols["layer_id"][i])
            n[f"{colour} {county}"] += 1
            drawn = json.loads(d) or {}
            cap = json.loads(cols["foundation_cap"][i] or "null") if "foundation_cap" in cols else None
            recs.append({"TLID": tlid, "county": county, "colour": colour, "layer_id": cols["layer_id"][i],
                         "jurisdiction": cols["jurisdiction"][i], "ring": json.dumps(ring),
                         "court": json.dumps(drawn.get("court")), "lane": json.dumps(drawn.get("lane")),
                         # the screen's own door face (FD8), where the run's assign output holds it
                         "door_face_rule": (cap or {}).get("door_face_rule"),
                         "drawing_hash": record.ring_hash(ring)})
    seen = Counter(r["TLID"] for r in recs)
    dup = sorted(t for t, k in seen.items() if k > 1)
    if dup:
        raise SystemExit(f"{len(dup)} TLIDs drawn twice in {assign}, e.g. {dup[:3]}")
    recs.sort(key=lambda r: (str(r["county"]), r["TLID"]))
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    pq.write_table(pa.Table.from_pylist(recs), tmp, compression="zstd")
    os.replace(tmp, out)
    return {"lots": len(recs), "counts": dict(sorted(n.items()))}


def _chunks(seq: list[Any], size: int) -> list[list[Any]]:
    return [seq[i : i + size] for i in range(0, len(seq), size)]


def extract_rows(quadfit_dir: Path, parts: list[list[str]], out: Path) -> dict[str, Any]:
    """The lots' rows of quadfit s4 / s5o, streamed, one small pair of files per
    part (``out/part-NNNN/``), and each lot's box (``out/lot_bounds.parquet``)."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    import shapely

    part_of = {t: k for k, tl in enumerate(parts) for t in tl}
    counts: dict[str, int] = {}
    bounds: list[dict[str, Any]] = []
    pool = pa.default_memory_pool()
    for name in ("s4_lots.parquet", "s5o_lots.parquet"):
        pf = pq.ParquetFile(quadfit_dir / name)
        # One column at a time (a file is one row group, so a batch reader would
        # decode every column of it at once): the rows wanted, then each column cut to them.
        keep = pa.array([i for i, k in enumerate(pf.read(columns=["TLID"]).column("TLID").to_pylist()) if k in part_of],
                        type=pa.int64())
        cols = {}
        for c in pf.schema_arrow.names:
            cols[c] = pf.read(columns=[c]).column(c).take(keep)
            pool.release_unused()
        tab = pa.table(cols)
        del cols
        counts[name] = tab.num_rows
        tl = tab.column("TLID").to_pylist()
        if name == "s4_lots.parquet" and "wkb" in tab.column_names:
            g = shapely.from_wkb(tab.column("wkb").to_numpy(zero_copy_only=False))
            bb = shapely.bounds(g)
            bounds = [{"TLID": t, "x0": float(b[0]), "y0": float(b[1]), "x1": float(b[2]), "y1": float(b[3])}
                      for t, b in zip(tl, bb, strict=True) if all(v == v for v in b)]
        by: dict[int, list[int]] = defaultdict(list)
        for i, t in enumerate(tl):
            by[part_of[t]].append(i)
        for k in range(len(parts)):
            d = out / f"part-{k:04d}"
            d.mkdir(parents=True, exist_ok=True)
            pq.write_table(tab.take(by.get(k, [])), d / name, compression="zstd")
        del tab
        pool.release_unused()
    pq.write_table(pa.Table.from_pylist(bounds), out / "lot_bounds.parquet", compression="zstd")
    (out / "done.json").write_text(json.dumps(counts), encoding="utf-8")
    return counts


def geojson_features(text: str) -> Iterator[dict[str, Any]]:
    """The features of a GeoJSON FeatureCollection one at a time, without
    building the whole document (a 35 MB NFHL file parses to ~10x that)."""
    dec = json.JSONDecoder()
    start = text.find('"features"')
    if start < 0:
        return
    pos = text.index("[", start) + 1
    while True:
        while pos < len(text) and (text[pos].isspace() or text[pos] == ","):
            pos += 1
        if pos >= len(text) or text[pos] == "]":
            return
        obj, pos = dec.raw_decode(text, pos)
        yield obj


def geojson_head(text: str) -> dict[str, Any]:
    """A FeatureCollection's top-level members other than ``features`` (strings
    and numbers only: those before the features, and those after the last
    ``]``), read without parsing the features."""
    import re

    out: dict[str, Any] = {}
    dec = json.JSONDecoder()
    start = text.find('"features"')
    outside = text if start < 0 else text[:start] + " " + text[text.rfind("]") + 1 :]
    for m in re.finditer(r'"(\w+)"\s*:\s*', outside):
        key = m.group(1)
        if key in out or key == "type":
            continue
        try:
            v, _ = dec.raw_decode(m.string, m.end())
        except ValueError:
            continue
        if isinstance(v, (str, int, float)):
            out[key] = v
    return out


class Sources:
    """The per-lot input sources of a measure run, each cut as it is read to
    what lies within reach of a drawn footprint (so one light process holds
    them): the NFHL flood zones, the hazard extract, the soil survey, the RLIS
    footprints (with each lot's "held" flag) and the occupancy years. Cutting
    changes no answer: every answer reads only features within that reach."""

    def __init__(self, args: argparse.Namespace, pop: list[dict[str, Any]],
                 lot_bounds: dict[str, tuple[float, float, float, float]], log: Any) -> None:
        import numpy as np
        import shapely

        self.log = log
        self.pods = np.array([shapely.Polygon(json.loads(r["ring"])) for r in pop], dtype=object)
        self.pod_tree = shapely.STRtree(self.pods)
        self.nfhl_meta: dict[str, Any] | None = None
        self._nfhl(Path(args.nfhl) if args.nfhl else None)
        self._hazards(Path(args.hazards))
        self._soil(Path(args.soil_extract), Path(args.soil_attrs))
        self._footprints(Path(args.footprints), lot_bounds)
        self._occupancy(Path(args.occupancy), {(str(r["county"]), r["TLID"]) for r in pop})

    def _near(self, geoms: Any, distance: float) -> Any:
        """Indices of ``geoms`` within ``distance`` of any drawn footprint."""
        import numpy as np

        if not len(geoms):
            return np.zeros(0, dtype=int)
        return np.unique(self.pod_tree.query(geoms, predicate="dwithin", distance=distance)[0])

    # -- NFHL (FD2 fix-flood)
    def _nfhl(self, path: Path | None) -> None:
        import numpy as np
        import shapely
        from pyproj import Transformer
        from shapely.geometry import shape

        self.nfhl_geoms: list[Any] = []
        self.nfhl_props: list[dict[str, Any]] = []
        self.nfhl_tree: Any = None
        if path is None:
            return
        text = path.read_text(encoding="utf-8")
        tf = Transformer.from_crs(4326, 2913, always_xy=True)
        self.nfhl_geoms, n = [], 0
        for f in geojson_features(text):
            if not f.get("geometry"):
                continue
            n += 1
            g = shapely.make_valid(shapely.transform(shape(f["geometry"]), lambda xy: np.column_stack(
                tf.transform(xy[:, 0], xy[:, 1]))))
            if len(self._near(np.array([g], dtype=object), 1.0)):
                self.nfhl_geoms.append(g)
                self.nfhl_props.append(f.get("properties") or {})
        info = geojson_head(text)
        del text
        self.nfhl_tree = shapely.STRtree(np.array(self.nfhl_geoms, dtype=object)) if self.nfhl_geoms else None
        self.nfhl_meta = {"path": str(path), **info, "features": n, "kept": len(self.nfhl_geoms)}
        self.log(f"nfhl {n} -> {len(self.nfhl_geoms)}")

    def nfhl_hits(self, fp: Any) -> list[dict[str, Any]]:
        import shapely

        if self.nfhl_tree is None:
            return []
        return [self.nfhl_props[i] for i in self.nfhl_tree.query(fp, predicate="intersects")
                if shapely.area(shapely.intersection(fp, self.nfhl_geoms[i])) > 0]

    # -- hazards (FD2 pass 1 _hazards on the same extract)
    def _hazards(self, extract: Path) -> None:
        import importlib.util

        import pyarrow.parquet as pq
        import shapely

        from flats.foundation import inputs as fin
        from flats.ingest.hazards import Feature, RasterLayer, VectorLayer, load_registry

        spec_ = importlib.util.spec_from_file_location("flats_lot_hazards", REPO / "scripts" / "flats_lot_hazards.py")
        mod = importlib.util.module_from_spec(spec_)  # type: ignore[arg-type]
        sys.modules.setdefault("flats_lot_hazards", mod)
        spec_.loader.exec_module(mod)  # type: ignore[union-attr]
        registry = load_registry()
        meta = json.loads((extract / mod.META_FILE).read_text(encoding="utf-8"))
        keys = [k for k in meta["layers"] if k in fin.HAZARD_KEYS or registry.layers[k].kind == "coverage"]
        self.reach_ft = fin.hazard_reach_ft(registry.layers[k].nearest_ft for k in keys)
        self.hazard_meta: dict[str, Any] = {"extract": str(extract), "reach_ft": self.reach_ft, "layers": {}}
        kept: dict[str, list[Any]] = {}
        for key in keys:
            if registry.layers[key].kind == "raster":
                continue
            feats, n = [], 0
            for b in pq.ParquetFile(extract / mod.LAYER_DIR / f"{key}.parquet").iter_batches(batch_size=5000):
                g = shapely.from_wkb(b.column("wkb").to_numpy(zero_copy_only=False))
                n += len(g)
                st, cd, lb, at = (b.column(c).to_pylist() for c in ("state", "code", "label", "attrs"))
                for i in self._near(g, self.reach_ft):
                    feats.append(Feature(st[i], cd[i], lb[i], json.loads(at[i]) if at[i] else {}, g[i]))
            kept[key] = feats
            self.hazard_meta["layers"][key] = {"features": n, "kept": len(feats)}
            self.log(f"hazard {key} {n} -> {len(feats)}")
        self.haz_cov = {k: VectorLayer(registry.layers[k], kept[k]) for k in keys if registry.layers[k].kind == "coverage"}
        self.haz_layers: list[Any] = []
        for key in keys:
            spec = registry.layers[key]
            if spec.kind == "coverage":
                continue
            if spec.coverage and spec.coverage not in self.haz_cov:
                raise SystemExit(f"{key}: its coverage {spec.coverage} is not in the extract")
            if spec.kind == "raster":
                tif = extract / mod.LAYER_DIR / f"{key}.tif"
                path = str(tif) if tif.exists() else meta["layers"][key]["raster"]["path"]
                self.haz_layers.append(RasterLayer(spec, path, working_srid=mod.OUT_SRID))
                self.hazard_meta["layers"][key] = {"raster": path}
            else:
                self.haz_layers.append(VectorLayer(spec, kept[key]))
        self.haz_have = {lay.spec.key for lay in self.haz_layers}
        self.scarps = next((x for x in self.haz_layers if x.spec.key == "landslide_scarps"), None)

    def hazards(self, fp: Any, layer_id: str | None) -> dict[str, Any]:
        from flats.foundation import inputs as fin
        from flats.ingest.hazards import measure_shape

        rows = list(measure_shape(fp, self.haz_layers, self.haz_cov, jurisdiction=layer_id))
        scarp = None
        if self.scarps is not None:
            ring = fp.buffer(fin.SCARP_RING_FT)
            scarp = any(f.geom.intersects(ring) for f in self.scarps.features(ring))
        out = fin.hazard_facts(rows, self.haz_have, scarp_within_100ft=scarp)
        return fin.with_nfhl(out, self.nfhl_hits(fp) if out.get("fema_zone") == "not mapped" else None)

    # -- soil (FD2 pass 1 _soil)
    def _soil(self, extract: Path, attrs: Path) -> None:
        import numpy as np
        import pyarrow.parquet as pq
        import shapely

        geoms, keys, n = [], [], 0
        for b in pq.ParquetFile(extract / "polygons.parquet").iter_batches(batch_size=20000, columns=["mukey", "wkb"]):
            g = shapely.from_wkb(b.column("wkb").to_numpy(zero_copy_only=False))
            n += len(g)
            mk = b.column("mukey").to_pylist()
            for i in self._near(g, 0.0):
                geoms.append(g[i])
                keys.append(str(mk[i]))
        self.soil_geoms = np.array(geoms, dtype=object)
        self.soil_keys = keys
        self.soil_tree = shapely.STRtree(self.soil_geoms)
        self.soil_units = json.loads(attrs.read_text(encoding="utf-8"))["units"]
        self.soil_meta = {"extract": str(extract), "attrs": str(attrs), "polygons": n, "kept": len(geoms)}
        self.log(f"soil {n} -> {len(geoms)}")

    def soil(self, fp: Any) -> dict[str, Any]:
        import shapely

        from flats.foundation import inputs as fin

        area: dict[str, float] = defaultdict(float)
        for i in self.soil_tree.query(fp, predicate="intersects"):
            a = float(shapely.area(shapely.intersection(fp, self.soil_geoms[i])))
            if a > 0:
                area[self.soil_keys[i]] += a
        return fin.soil_facts(area, float(fp.area), self.soil_units)

    # -- RLIS footprints (FD5 pass 2): the old buildings, and "held" round each lot
    def _footprints(self, path: Path, lot_bounds: dict[str, tuple[float, float, float, float]]) -> None:
        import numpy as np
        import shapely
        from shapely.geometry import shape

        from flats.foundation import inputs as fin

        s = settings.load()
        near = (s.grow_ft + 1.0) * 1.5 + 1.0  # past the mitred grow ring round each pod
        tl = list(lot_bounds)
        box_tree = shapely.STRtree(np.array([shapely.box(*fin.held_box(lot_bounds[t])) for t in tl], dtype=object))
        held = np.zeros(len(tl), dtype=bool)
        geoms: list[Any] = []
        props: list[dict[str, Any]] = []
        n = 0
        buf_g: list[Any] = []
        buf_p: list[dict[str, Any]] = []

        def flush() -> None:
            if not buf_g:
                return
            arr = np.array(buf_g, dtype=object)
            # no predicate: boxes meet boxes, exactly FD5 pass 2's STRtree.query(lot.buffer(1500))
            held[np.unique(box_tree.query(arr)[1])] = True
            for i in self._near(arr, near):
                geoms.append(buf_g[i])
                props.append(buf_p[i])
            buf_g.clear()
            buf_p.clear()

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
                p = d.get("p") or {}
                buf_g.append(g)
                buf_p.append({k: p.get(k) for k in ("YEAR_BUILT", "BLDG_ID")})
                n += 1
                if len(buf_g) >= 20000:
                    flush()
        flush()
        self.fp_geoms = geoms
        self.fp_props = props
        self.fp_tree = shapely.STRtree(np.array(geoms, dtype=object)) if geoms else None
        self.held = {t: bool(h) for t, h in zip(tl, held, strict=True)}
        self.fp_meta = {"path": str(path), "footprints": n, "kept": len(geoms), "lots_held": int(held.sum()),
                        "lots": len(tl)}
        self.log(f"footprints {n} -> {len(geoms)}; held round {int(held.sum())} of {len(tl)} lots")

    def old_buildings(self, fr: Frame, s: Any) -> tuple[Any, ...]:
        import shapely

        from flats.foundation import oldbuild

        if self.fp_tree is None:
            return ()
        pod = shapely.Polygon([fr.fl, fr.fr, fr.br, fr.bl])
        idx = self.fp_tree.query(shapely.buffer(pod, s.grow_ft + 1.0, join_style="mitre"), predicate="intersects")
        outs = oldbuild.model_outlines(fr, [self.fp_geoms[i] for i in idx], [self.fp_props[i] for i in idx], s)
        return oldbuild.measure_all(outs, s)

    # -- occupancy years (FD2 pass 1)
    def _occupancy(self, path: Path, want: set[tuple[str, str]]) -> None:
        self.years: dict[tuple[str, str], Any] = {}
        with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                k = ((r.get("county") or "").lower(), r.get("tlid") or "")
                if k in want:
                    self.years[k] = r.get("year_built")
        self.occ_meta = {"path": str(path), "lots": len(self.years)}
        self.log(f"occupancy rows for {len(self.years)} lots")

    def meta(self) -> dict[str, Any]:
        return {"nfhl": self.nfhl_meta, "hazards": self.hazard_meta, "soil": self.soil_meta,
                "footprints": self.fp_meta, "occupancy": self.occ_meta}


_FROST: dict[tuple[str | None, str | None], Any] = {}


def frost_in(layer_id: str | None, county: str | None) -> Any:
    """The live frost register's figure for a place, as FD2 pass 1 read it
    (``flats.frost.describe(layer_id, county)["inches"]``), cached."""
    from flats import frost as register

    key = (layer_id, (county or "").lower() or None)
    if key not in _FROST:
        _FROST[key] = register.describe(layer_id, county).get("inches")
    return _FROST[key]


def _status(p: Mapping[str, Any], **kw: Any) -> dict[str, Any]:
    st: dict[str, Any] = dict.fromkeys(STATUS_FIELDS)
    st.update(county=p["county"], tlid=p["TLID"], colour=p["colour"], layer_id=p["layer_id"],
              drawing_hash=p["drawing_hash"], **kw)
    return st


_RULESETS: dict[int, Any] = {}


def _zone_rules(layers: Any, layer_id: str, zone: str | None) -> Any:
    """The zone's resolved standards (for ``entrance_faces_street``), or None."""
    from flats.rules.resolver import RuleSet

    if not zone:
        return None
    rs = _RULESETS.get(id(layers))
    if rs is None:
        rs = _RULESETS[id(layers)] = RuleSet(layers)
    try:
        return rs.resolve(layer_id, zone)
    except Exception:  # noqa: BLE001 -- an unresolved zone keeps the street-side rule
        return None


def measure_lot(p: Mapping[str, Any], row: Mapping[str, Any] | None, src: Sources, dem: Any, layers: Any, s: Any,
                grid: tuple[Any, Any], *, drawing: str, run: str, measured_at: str
                ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """One drawn lot: its measured record (None when it cannot be measured) and
    its status row. The ground grid is the 1 m model's, else (blank cells, or
    no 1 m tile) the 10 m model's (:func:`flats.foundation.place.place`)."""
    import shapely

    from flats.foundation import inputs as fin
    from flats.foundation import record
    from flats.ingest import quadfit

    tlid, county, layer_id = p["TLID"], p["county"], p["layer_id"]
    ring = json.loads(p["ring"])
    if row is None:
        return None, _status(p, error="LookupError: lot row not in s4")
    ql = quadfit.lot_from_row(dict(row), layers)
    streets = tuple(dict.fromkeys(quadfit._street_lines(ql) + quadfit._side_street_lines(ql)))
    # Which face takes the front doors (FD8, Steph 2026-11-20): the screen's
    # answer where the assign output holds it, else worked here the same way.
    rule = p.get("door_face_rule")
    if rule:
        required = rule == doors.REQUIRED
    else:
        required = doors.entrance_required(_zone_rules(layers, layer_id, ql.zone))
    placed = place(ring, streets, dem, s, required=required, court=json.loads(p.get("court") or "null"),
                   lane=json.loads(p.get("lane") or "null"), lot=ql.lot_geom, tlid=tlid, county=county, grid=grid)
    if placed.measured is None:
        return None, _status(p, error=placed.error)
    m, fr = placed.measured, placed.street_frame
    fp = shapely.Polygon(ring)
    soil = src.soil(fp)
    haz = src.hazards(fp, layer_id)
    turn = fin.front_face(fr.fl, fr.fr, fr.bl, fr.br, streets)["front_face_turn_deg"]
    ins, facts = fin.model_inputs(soil, haz, frost_in=frost_in(layer_id, county),
                                  year=src.years.get((str(county), tlid)), turn_deg=turn)
    m = measure.with_inputs(m, ins)
    held = src.held.get(tlid, False)
    m = measure.with_old_buildings(m, held, src.old_buildings(placed.frame, s))
    doc = record.document(m, drawing=drawing, measured_at=measured_at, run=run, ring=ring)
    st = _status(p, **facts)
    st.update(ground_source=m.ground_source, cell_m=m.cell_m, ground_class=ins["ground_class"],
              alt_ground_class=ins["alt_ground_class"], frost_register_in=ins["frost_register_in"],
              year_built=ins["year_built"], front_face_turn_deg=ins["front_face_turn_deg"],
              old_buildings_held=held, old_buildings_n=len(m.old_buildings))
    return doc, st


def _measure_run(args: argparse.Namespace) -> None:
    """``measure-run``: see the module docstring."""
    os.environ.setdefault("GDAL_CACHEMAX", "64")
    import shutil
    from datetime import datetime, timezone

    import numpy as np
    import pyarrow as pa
    import pyarrow.parquet as pq

    from flats.foundation import record
    from flats.foundation.terrain import Dem
    from flats.ingest import quadfit
    from flats.rules.loader import load_rules

    t0 = time.time()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    logf = (out / "run.log").open("a", encoding="utf-8")

    def log(msg: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {msg} [{time.time() - t0:.0f}s, peak {_rss_mb()} MB]"
        print(line, flush=True)
        logf.write(line + "\n")
        logf.flush()

    s = settings.load()
    run_json = out / "run.json"
    want = {"assign": str(args.assign), "quadfit": str(args.quadfit), "colours": args.colours, "part": args.part,
            "drawing": args.drawing, "run": args.run, "limit": args.limit, "geometry_hash": record.settings_hash(s)}
    if run_json.exists():
        have = json.loads(run_json.read_text(encoding="utf-8"))
        if {k: have.get(k) for k in want} != want:
            raise SystemExit(f"{out} holds another run ({have}); use a new --out")
        measured_at = have["measured_at"]
    else:
        measured_at = args.measured_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
        run_json.write_text(json.dumps({**want, "measured_at": measured_at}, indent=1), encoding="utf-8")
    pop_path = out / "population.parquet"
    if not pop_path.exists():
        log("population " + json.dumps(population(Path(args.assign), set(args.colours.split(",")), pop_path)))
        pa.default_memory_pool().release_unused()
    pop = pq.read_table(pop_path).to_pylist()
    if args.limit:
        pop = pop[: args.limit]
    parts = _chunks(pop, args.part)
    rows_dir = out / "rows"
    if not (rows_dir / "done.json").exists():
        log("rows " + json.dumps(extract_rows(Path(args.quadfit), [[p["TLID"] for p in c] for c in parts], rows_dir)))
    pdir = out / "parts"
    pdir.mkdir(exist_ok=True)
    todo = [k for k in range(len(parts)) if not (pdir / f"part-{k:04d}").exists()]
    log(f"lots {len(pop)} parts {len(parts)} to do {len(todo)}")
    if todo:
        lb = {r["TLID"]: (r["x0"], r["y0"], r["x1"], r["y1"])
              for r in pq.read_table(rows_dir / "lot_bounds.parquet").to_pylist()}
        src = Sources(args, pop, lb, log)
        (out / "sources.json").write_text(json.dumps(src.meta(), indent=1, default=str), encoding="utf-8")
        layers = load_rules()
        dem = Dem(Path(args.dem), Path(args.coarse) if args.coarse else None)
        _x0, _y0, xs, ys = grounds.grid_centres(s)
        gx, gy = np.meshgrid(np.array(xs), np.array(ys))  # rows front to back, each left to right
        log(f"sources loaded; 1 m tiles {len(dem.tiles)}, 10 m model {dem.coarse is not None}")
        for k in todo:
            rd = rows_dir / f"part-{k:04d}"
            qrows = {r["TLID"]: r for r in quadfit.iter_rows(rd / "s4_lots.parquet", rd / "s5o_lots.parquet")}
            docs, stats = [], []
            n: Counter[str] = Counter()
            for p in parts[k]:
                try:
                    doc, st = measure_lot(p, qrows.get(p["TLID"]), src, dem, layers, s, (gx, gy),
                                          drawing=args.drawing, run=args.run, measured_at=measured_at)
                except Exception as exc:  # noqa: BLE001 -- recorded per lot, the run goes on
                    doc, st = None, _status(p, error=f"{type(exc).__name__}: {exc}"[:300])
                if doc is not None:
                    docs.append(doc)
                n["error" if st["error"] else str(st["ground_source"])] += 1
                stats.append(st)
            tmp = pdir / f".tmp-{k:04d}"
            if tmp.exists():
                shutil.rmtree(tmp)
            tmp.mkdir()
            record.write_jsonl(tmp / "records.jsonl.gz", docs)
            tables: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for doc in docs:
                for name, recs in record.table_rows(doc).items():
                    tables[name].extend(recs)
            for name in record.TABLES:
                if tables[name]:
                    pq.write_table(pa.Table.from_pylist(tables[name]), tmp / f"{name}.parquet", compression="zstd")
            pq.write_table(pa.Table.from_pylist(stats), tmp / "status.parquet", compression="zstd")
            os.replace(tmp, pdir / f"part-{k:04d}")
            del docs, tables
            log(f"part {k + 1}/{len(parts)} {dict(n)}")
        del src
    merge_run(out, len(parts), log)
    logf.close()


def merge_run(out: Path, n_parts: int, log: Any) -> dict[str, Any]:
    """Join a measure run's parts into the bundle: ``records.jsonl.gz``, the five
    measured tables (``lots/`` ... Parquet), ``status.parquet`` and ``meta.json``."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    from flats.foundation import record

    pdir = out / "parts"
    parts = [pdir / f"part-{k:04d}" for k in range(n_parts)]
    missing = [p.name for p in parts if not p.exists()]
    if missing:
        raise SystemExit(f"parts not measured: {missing[:5]}")
    import shutil

    # Gzip members joined end to end are one gzip file (``read_jsonl`` reads them through).
    n = 0
    tmp = out / "records.jsonl.gz.tmp"
    with tmp.open("wb") as fh:
        for p in parts:
            with (p / "records.jsonl.gz").open("rb") as part:
                shutil.copyfileobj(part, fh)
            n += sum(1 for _ in record.read_jsonl(p / "records.jsonl.gz"))
    os.replace(tmp, out / "records.jsonl.gz")
    for name in record.TABLES:
        d = out / name
        d.mkdir(exist_ok=True)
        for old in d.glob("part-*.parquet"):
            old.unlink()
        for k, p in enumerate(parts):
            if (p / f"{name}.parquet").exists():
                shutil.copyfile(p / f"{name}.parquet", d / f"part-{k:04d}.parquet")
    status = pa.concat_tables([pq.read_table(p / "status.parquet") for p in parts], promote_options="default")
    pq.write_table(status, out / "status.parquet", compression="zstd")
    st = status.to_pylist()
    run = json.loads((out / "run.json").read_text(encoding="utf-8"))
    src = json.loads((out / "sources.json").read_text(encoding="utf-8")) if (out / "sources.json").exists() else None
    ok = [r for r in st if not r["error"]]
    meta = {
        "records": n,
        "lots": len(st),
        "errors": dict(Counter(str(r["error"]).split(":")[0] for r in st if r["error"])),
        "by_colour_county": dict(sorted(Counter(f"{r['colour']} {r['county']}" for r in ok).items())),
        "ground_source": dict(Counter(str(r["ground_source"]) for r in ok)),
        "ground_class": dict(Counter(str(r["ground_class"]) for r in ok)),
        "drawing": run["drawing"],
        "run": run["run"],
        "measured_at": run["measured_at"],
        "model_version": record.MODEL_VERSION,
        "record_version": record.RECORD_VERSION,
        "geometry_hash": run["geometry_hash"],
        "assign": run["assign"],
        "quadfit": run["quadfit"],
        "sources": src,
        "code": str(REPO),
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=1, default=str), encoding="utf-8")
    log(f"merged {n} records of {len(st)} lots; errors {meta['errors']}")
    return meta


# ---------------------------------------------------------------- bundle (PC) and load (api container)


def _bundle(args: argparse.Namespace) -> None:
    from datetime import datetime, timezone

    from flats.foundation import record

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
    old = Path(args.old)
    by_b: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_s: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in read_parts(old / "buildings"):
        by_b[r["tlid"]].append(r)
    for r in read_parts(old / "stretches"):
        by_s[r["tlid"]].append(r)
    old_held = {r["tlid"]: r["old_buildings_held"] for r in read_parts(old / "old_lots")}
    meta_path = g / "meta.json"
    grid_meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    measured_at = args.measured_at or datetime.fromtimestamp(meta_path.stat().st_mtime, timezone.utc).isoformat(
        timespec="seconds"
    )
    docs, n = [], Counter()
    for row in _lot_rows(Path(args.lots)):
        tlid = row["TLID"]
        gl = glots.get(tlid)
        if gl is not None:
            m = rows.from_measured_rows(gl, by_lines[tlid], by_doors[tlid])
            m = measure.with_inputs(m, lots_mod.inputs_of(row))
        else:
            m = lots_mod.measure_row(row, s)
        if m is None:
            n["no grid and no six readings"] += 1
            continue
        held = bool(old_held.get(tlid, False))
        m = measure.with_old_buildings(m, held, rows.old_buildings_from_rows(by_b.get(tlid, []), by_s.get(tlid, [])))
        n[m.ground_source] += 1
        docs.append(record.document(m, drawing=args.drawing, measured_at=measured_at))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tables: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for d in docs:
        for name, recs in record.table_rows(d).items():
            tables[name].extend(recs)
    for name in record.TABLES:
        _write(out, name, 0, tables[name])
    written = record.write_jsonl(out / "records.jsonl.gz", docs)
    meta = {
        "records": written,
        "counts": dict(n),
        "drawing": args.drawing,
        "measured_at": measured_at,
        "model_version": record.MODEL_VERSION,
        "record_version": record.RECORD_VERSION,
        "geometry_hash": record.settings_hash(s),
        "grid": str(g),
        "grid_meta": grid_meta,
        "old": str(old),
        "seconds": round(time.time() - t0, 1),
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=1, default=list), encoding="utf-8")
    print(json.dumps({k: v for k, v in meta.items() if k != "grid_meta"}, indent=1), flush=True)


def _dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


_UPSERT = """
INSERT INTO flats.lot_foundation
    (county, tlid, record_version, model_version, geometry_hash, drawing, ground_source, cell_m, measured_at,
     loaded_at, record)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, now(), $10::jsonb)
ON CONFLICT (county, tlid) DO UPDATE SET
    record_version = EXCLUDED.record_version, model_version = EXCLUDED.model_version,
    geometry_hash = EXCLUDED.geometry_hash, drawing = EXCLUDED.drawing, ground_source = EXCLUDED.ground_source,
    cell_m = EXCLUDED.cell_m, measured_at = EXCLUDED.measured_at, loaded_at = now(), record = EXCLUDED.record
"""


def _load_row(doc: dict[str, Any]) -> tuple[Any, ...]:
    from datetime import datetime

    lot, on = doc["lot"], doc["measured_on"]
    if not lot.get("county") or not lot.get("tlid"):
        raise ValueError("a record without county and tlid")
    when = datetime.fromisoformat(str(on["measured_at"]))
    return (
        lot["county"],
        lot["tlid"],
        int(doc["record_version"]),
        str(doc["model_version"]),
        str(doc["geometry_hash"]),
        str(on["drawing"]),
        str(on["ground_source"]),
        on.get("cell_m"),
        when,
        json.dumps(doc, separators=(",", ":"), allow_nan=False),
    )


async def load(records_path: Path, db_url: str, *, dry_run: bool = False, batch_size: int = 500) -> dict[str, Any]:
    """Upsert every record of ``records.jsonl.gz`` into ``flats.lot_foundation`` by
    county + tlid, in one transaction (rolled back on ``dry_run``)."""
    import asyncpg

    from flats.foundation import record

    report: dict[str, Any] = {"records": str(records_path), "dry_run": dry_run}
    conn = await asyncpg.connect(_dsn(db_url))
    try:
        tx = conn.transaction()
        await tx.start()
        try:
            before = await conn.fetchval("SELECT count(*) FROM flats.lot_foundation")
            batch: list[tuple[Any, ...]] = []
            read = 0
            for doc in record.read_jsonl(Path(records_path)):
                batch.append(_load_row(doc))
                read += 1
                if len(batch) >= batch_size:
                    await conn.executemany(_UPSERT, batch)
                    batch = []
            if batch:
                await conn.executemany(_UPSERT, batch)
            after = await conn.fetchval("SELECT count(*) FROM flats.lot_foundation")
            in_copy = await conn.fetchval(
                "SELECT count(*) FROM flats.lot_foundation f "
                "JOIN flats.lots l ON l.county = f.county AND l.tlid = f.tlid "
                "JOIN flats.snapshots s ON s.id = l.snapshot_id AND s.status = 'current'"
            )
            report.update(written=read, new=after - before, rows_in_table=after, in_current_copy=in_copy)
        except BaseException:
            await tx.rollback()
            raise
        if dry_run:
            await tx.rollback()
        else:
            await tx.commit()
    finally:
        await conn.close()
    return report


def _load(args: argparse.Namespace) -> None:
    import asyncio

    db_url = args.db_url
    if db_url is None:
        from app.config import settings as app_settings

        db_url = app_settings.database_url
    print(json.dumps(asyncio.run(load(Path(args.records), db_url, dry_run=args.dry_run)), indent=1, default=str))


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
    b = sub.add_parser("bundle", help="the whole measured record of every lot, for the app and reprice (this PC)")
    b.add_argument("--grid", required=True)
    b.add_argument("--old", required=True)
    b.add_argument("--lots", required=True)
    b.add_argument("--drawing", required=True, help="the drawings the pods were measured under")
    b.add_argument("--measured-at", default=None, help="ISO time (default: the grid run's meta.json time)")
    b.add_argument("--out", required=True)
    mr = sub.add_parser("measure-run", help="measure every drawn lot of a run, from the sources (LXC 137)")
    mr.add_argument("--assign", required=True, help="the run's assign output (lots.parquet)")
    mr.add_argument("--quadfit", required=True, help="quadfit data dir holding s4_lots / s5o_lots parquet")
    mr.add_argument("--dem", required=True, help="1 m tiles (quadfit raw/dem)")
    mr.add_argument("--coarse", help="10 m model (quadfit raw/dem10_utm)")
    mr.add_argument("--hazards", required=True, help="FD2 hazard extract (flats_lot_hazards.py extract)")
    mr.add_argument("--soil-extract", required=True, help="soil extract dir holding polygons.parquet")
    mr.add_argument("--soil-attrs", required=True, help="FD2 soil_attrs.json")
    mr.add_argument("--occupancy", required=True, help="occupancy.csv.gz (year built)")
    mr.add_argument("--footprints", required=True, help="RLIS footprints.geojsonl.gz")
    mr.add_argument("--nfhl", help="FEMA NFHL layer 28 GeoJSON (FD2 fix-flood)")
    mr.add_argument("--drawing", required=True, help="the label of the drawings measured (e.g. the release)")
    mr.add_argument("--run", required=True, help="the run label (e.g. run 128)")
    mr.add_argument("--colours", default="green,yellow")
    mr.add_argument("--measured-at", default=None, help="ISO time (default: now, kept across restarts)")
    mr.add_argument("--out", required=True)
    mr.add_argument("--limit", type=int, default=0)
    mr.add_argument("--part", type=int, default=PART)
    ld = sub.add_parser("load", help="upsert records.jsonl.gz into flats.lot_foundation (api container)")
    ld.add_argument("--records", required=True)
    ld.add_argument("--db-url", default=None, help="default: app settings' database_url")
    ld.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    {"grid": _grid, "old-buildings": _old, "compare": _compare, "bundle": _bundle, "measure-run": _measure_run,
     "load": _load}[args.cmd](args)


if __name__ == "__main__":
    main()
