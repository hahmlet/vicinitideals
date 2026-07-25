"""s6 — oriented rectangle fitting against the setback envelope.

Per lot: rotate the envelope so the front lot line runs along +x (one rotation
per frontage bearing — corner lots get two), rasterize each envelope part on a
grid_resolution_ft grid using CELL-CORNER containment (a cell counts only if
all four corners are inside — conservative to ±1 cell), build an integral
image, then:

- max-depth-per-width frontier: for each width in the configured grid, the
  deepest rectangle that fits. Computed with a monotone two-pointer walk
  (depth never increases as width grows), so the whole frontier costs ~one
  linear scan of window checks.
- named footprints: direct window checks, both orientations (the 90° flip is
  skipped when the jurisdiction is axis_required).
- coverage: footprint area + accessory allowance vs max_coverage_pct of the
  lot (attribute math, no geometry).

The frontier answers ANY future WxD question and the constant-area sweeps in
s7 without re-running this stage.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from multiprocessing import Pool, cpu_count
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL_DIR))

from common import load_footprints, load_rules, read_stage, write_stage

_CFG: dict = {}


def _init_worker(cfg: dict) -> None:
    global _CFG
    _CFG = cfg


def _cell_grid(part, res: float):
    """Boolean cell grid for one polygon part (corner containment)."""
    import numpy as np
    import shapely

    minx, miny, maxx, maxy = part.bounds
    ncols = max(1, math.ceil((maxx - minx) / res))
    nrows = max(1, math.ceil((maxy - miny) / res))
    if ncols * nrows > 4_000_000:  # pathological giant lot — cap raster size
        return None
    xs = minx + np.arange(ncols + 1) * res
    ys = miny + np.arange(nrows + 1) * res
    X, Y = np.meshgrid(xs, ys)
    shapely.prepare(part)
    inside = shapely.contains_xy(part, X.ravel(), Y.ravel()).reshape(X.shape)
    return inside[:-1, :-1] & inside[1:, :-1] & inside[:-1, 1:] & inside[1:, 1:]


def _integral(cell_ok):
    import numpy as np

    r, c = cell_ok.shape
    S = np.zeros((r + 1, c + 1), dtype=np.int32)
    np.cumsum(np.cumsum(cell_ok, axis=0), axis=1, out=S[1:, 1:])
    return S


def _has_window(S, d_cells: int, w_cells: int) -> bool:
    R, C = S.shape[0] - 1, S.shape[1] - 1
    if d_cells < 1 or w_cells < 1 or d_cells > R or w_cells > C:
        return False
    W = (
        S[d_cells:, w_cells:]
        - S[:-d_cells, w_cells:]
        - S[d_cells:, :-w_cells]
        + S[:-d_cells, :-w_cells]
    )
    return bool((W == d_cells * w_cells).any())


def _frontier(S, width_cells: list[int]) -> list[int]:
    """Max fitting depth (cells) per width (cells); depths are non-increasing."""
    R = S.shape[0] - 1
    depths: list[int] = []
    d = R
    for w in width_cells:
        while d > 0 and not _has_window(S, d, w):
            d -= 1
        depths.append(d)
        if d == 0:
            depths.extend([0] * (len(width_cells) - len(depths)))
            break
    return depths


def _placement(S, d_cells: int, w_cells: int):
    """(row, col) of the first fitting window, or None."""
    import numpy as np

    R, C = S.shape[0] - 1, S.shape[1] - 1
    if d_cells < 1 or w_cells < 1 or d_cells > R or w_cells > C:
        return None
    W = (
        S[d_cells:, w_cells:]
        - S[:-d_cells, w_cells:]
        - S[d_cells:, :-w_cells]
        + S[:-d_cells, :-w_cells]
    )
    hits = np.argwhere(W == d_cells * w_cells)
    return tuple(hits[0]) if len(hits) else None


def fit_lot(env_wkb: bytes, bearings: list[float], allow_flip: bool,
            collect_placement: tuple[float, float] | None = None) -> dict:
    """Fit results for one lot. Called in worker processes."""
    import numpy as np
    import shapely
    from shapely import affinity

    res: float = _CFG["res"]
    width_cells: list[int] = _CFG["width_cells"]
    footprints: list[tuple[str, float, float]] = _CFG["footprints"]

    env = shapely.from_wkb(env_wkb)
    n_widths = len(width_cells)
    out: dict = {
        "frontier": [0] * n_widths,
        "fits": {name: (False, False) for name, _w, _d in footprints},
        "placement": None,
    }
    if env is None or env.is_empty:
        return out

    frames = []  # (S, minx, miny, bearing, origin)
    for b in bearings[:2] or [0.0]:
        origin = env.centroid
        rotated = affinity.rotate(env, -b, origin=origin)
        for part in shapely.get_parts(rotated):
            if part.geom_type != "Polygon" or part.area < 100:
                continue
            cell_ok = _cell_grid(part, res)
            if cell_ok is None or not cell_ok.any():
                continue
            frames.append((_integral(cell_ok), part.bounds[0], part.bounds[1], b, origin))

    if not frames:
        return out

    frontier = np.zeros(n_widths, dtype=np.int32)
    for S, *_ in frames:
        frontier = np.maximum(frontier, np.array(_frontier(S, width_cells), dtype=np.int32))
    out["frontier"] = frontier.tolist()

    for name, w_ft, d_ft in footprints:
        w_c, d_c = math.ceil(w_ft / res), math.ceil(d_ft / res)
        wf = any(_has_window(S, d_c, w_c) for S, *_ in frames)
        df = allow_flip and any(_has_window(S, w_c, d_c) for S, *_ in frames)
        out["fits"][name] = (wf, df)

    if collect_placement is not None:
        w_ft, d_ft = collect_placement
        w_c, d_c = math.ceil(w_ft / res), math.ceil(d_ft / res)
        for orient_w, orient_d, flipped in ((w_c, d_c, False), (d_c, w_c, True)):
            if flipped and not allow_flip:
                continue
            for S, minx, miny, b, origin in frames:
                hit = _placement(S, orient_d, orient_w)
                if hit is not None:
                    row, col = hit
                    x0, y0 = minx + col * res, miny + row * res
                    rect = shapely.box(x0, y0, x0 + orient_w * res, y0 + orient_d * res)
                    out["placement"] = shapely.to_wkb(
                        affinity.rotate(rect, b, origin=origin)
                    )
                    break
            if out["placement"]:
                break
    return out


def _work_chunk(chunk: list[tuple[int, bytes, list[float], bool]]) -> list[tuple[int, dict]]:
    return [(idx, fit_lot(wkb, bearings, flip)) for idx, wkb, bearings, flip in chunk]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--processes", type=int, default=max(1, cpu_count() - 2))
    ap.add_argument("--limit", type=int, help="only first N lots (debug)")
    args = ap.parse_args()

    import numpy as np
    import shapely

    rules = load_rules()
    fps = load_footprints()
    res = rules.defaults.grid_resolution_ft
    frontier_widths = fps.frontier.widths()
    for sweep in fps.constant_area_sweeps:
        for w in (sweep.width_min_ft, sweep.width_max_ft):
            if not (fps.frontier.width_min_ft <= w <= fps.frontier.width_max_ft):
                raise SystemExit(
                    f"sweep width {w} outside frontier grid — widen frontier config")

    cfg = {
        "res": res,
        "width_cells": [round(w / res) for w in frontier_widths],
        "footprints": [(f.name, f.width_ft, f.depth_ft) for f in fps.footprints],
    }

    lots = read_stage("s5_lots")
    if args.limit:
        lots = lots.head(args.limit).copy()
    print(f"s6: fitting {len(lots):,} lots at {res} ft resolution, "
          f"{len(frontier_widths)} frontier widths, {args.processes} processes")

    tasks = []
    for i, row in enumerate(lots.itertuples(index=False)):
        allow_flip = (
            rules.jurisdictions[row.jurisdiction].orientation_constraint
            != "axis_required"
        )
        tasks.append((
            i,
            shapely.to_wkb(row.geom),
            json.loads(row.front_bearings_json),
            allow_flip,
        ))

    chunk_size = 1000
    chunks = [tasks[i : i + chunk_size] for i in range(0, len(tasks), chunk_size)]
    results: list[dict | None] = [None] * len(tasks)
    if args.processes == 1:
        _init_worker(cfg)
        for ch in chunks:
            for idx, r in _work_chunk(ch):
                results[idx] = r
    else:
        with Pool(args.processes, initializer=_init_worker, initargs=(cfg,)) as pool:
            done = 0
            for out in pool.imap_unordered(_work_chunk, chunks):
                for idx, r in out:
                    results[idx] = r
                done += 1
                if done % 20 == 0:
                    print(f"  {done * chunk_size:,}/{len(tasks):,}")

    lots = lots.drop(columns=["geom"])  # envelope not needed downstream
    lots["frontier_json"] = [json.dumps(r["frontier"]) for r in results]
    for name, w_ft, d_ft in cfg["footprints"]:
        wf = np.array([r["fits"][name][0] for r in results])
        df = np.array([r["fits"][name][1] for r in results])
        lots[f"fits_{name}_wf"] = wf
        lots[f"fits_{name}_df"] = df
        lots[f"fits_{name}"] = wf | df
        # Coverage cap check (attribute math).
        cov_ok = []
        for row_area, jkey, zraw in zip(lots["area_sqft"], lots["jurisdiction"], lots["zone_raw"]):
            rule = rules.jurisdictions[jkey].rule_for(zraw)
            if rule is None or rule.max_coverage_pct is None:
                cov_ok.append(True)
            else:
                cap = rule.max_coverage_pct / 100.0 * float(row_area)
                cov_ok.append(w_ft * d_ft + rule.accessory_allowance_sqft <= cap)
        lots[f"fits_cov_{name}"] = lots[f"fits_{name}"] & np.array(cov_ok)

    meta = {
        "grid_resolution_ft": res,
        "frontier_widths_ft": frontier_widths,
        "footprints": [
            {"name": n, "width_ft": w, "depth_ft": d} for n, w, d in cfg["footprints"]
        ],
    }
    from common import DATA_DIR

    (DATA_DIR / "s6_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    write_stage(lots, "s6_lots")
    for name, *_ in cfg["footprints"]:
        print(f"  fits_{name}: {int(lots[f'fits_{name}'].sum()):,} lots "
              f"(coverage-ok {int(lots[f'fits_cov_{name}'].sum()):,})")
    print("s6 done.")


if __name__ == "__main__":
    main()
