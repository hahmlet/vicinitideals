"""Bound for FOLLOWUPS 5 (n): the pole's lane comes straight out of the pole.

On a flag lot s6s took the pole as the lane (where it is at least the lane's
width) and let the lane start at ANY column of the body's top, while the pod
was placed first-fit at the body's top-left. Where the pole met the body at
the left the lane stood to the pod's right, and the run along the body's
top from the pole to it -- across the front of the building -- was neither
drawn nor charged (92 of the 123 pole lots restored on 2026-09-20). And the
pole was told from a stub by the ENVELOPE's strip, so six wide tracts with a
short street piece were drawn as poles.

Now (`s6s_siteplan._pole_span`, `_pole_lanes`) a pole is read off the lot's
ground at the street, its lane is taken in the pole's own columns, those
columns are closed to the pod before it is placed, and the lane's length
runs from the street. Expected: some 77-100 ft Portland bodies lose the
56-wide pod to the 36-wide; poles whose envelope columns cannot hold the
lane (a tier-C lot's uniform inset over a 12-15 ft pole) are refused; the
six tracts are refused like any stub narrower than the lane.

This replays `layout_lot` twice on every lot the change can reach -- once
with s6s as it stood before (loaded from git, `--before-rev`, default
38932a24, the last commit to touch s6s before this fix) and once as it
stands -- and writes what moved. Its lots come from s6s's own main() run up
to the point where it would lay them out, so the inputs are exactly the
stage's, and it stops before anything is written: NO STAGE OUTPUT IS
TOUCHED. It reads s6_lots, s5o_lots, s4_lots (through s6s), s6s_lots (the
stored drawing, for a replay-fidelity check) and lots_results.csv (each
lot's current colour) from QUADFIT_DATA_DIR, and writes only under --out.

Which lots it replays: in scope, not fed from the alley, and with a front
(`_candidate_fronts`, the city's own front rule) whose street piece is at
least the lane's width and at most half the envelope's extent along it --
the pole test's own arithmetic, asked without a raster (a cell's margin
added), so a lot it clears cannot enter the pole branch. `--all` replays
every lot in scope instead, to check that.

On LXC 137, from the repo, against the run whose drawing is live (the
`QUADFIT_DATA_DIR` of that run; nohup because a county replay takes a
while):

    cd /root/code/vicinitideals && git pull
    QUADFIT_DATA_DIR=data/quadfit_2026-09-18 PYTHONIOENCODING=utf-8 \\
      nohup .venv/bin/python "Lot Analysis/quadfit/bound_pole_lane.py" \\
      --processes 10 --out /root/bound_n > /root/bound_n.log 2>&1 &

Outputs, under --out:

  moves.csv    one row per replayed lot: TLID, city, zone, s4 tier, move,
               the lot's current triage, and before / after: site_plan_ok,
               stalls, method, layout_fail, building, the building's width
               across the front, parking area, driveway length, the court's
               street exposure, and `jog_ft` -- how far along the front the
               drawn lane stands off the street piece (the undrawn run).
  summary.txt  counts by move and city, pod-width changes, the jog before
               and after, the replay-fidelity check, and up to --sample
               LOST lots to read one by one, by tier.

A LOST lot (site_plan_ok true -> false) goes red in s7 whatever its colour
was. A GAINED lot needs s7 to say which colour; this reports its current
one. A REDRAWN lot keeps its verdict with a different plan. The fidelity
check compares the BEFORE replay with the stored s6s_lots: on a run drawn
by the `--before-rev` code they agree on every lot. The live run of
2026-09-28 was drawn before FOLLOWUPS 5 (l) and (o) (5cb2bd75, 38932a24),
so lots those two moved disagree too -- read them against
`bound_street_strip_zero_front.py`'s moves, or pass `--before-rev` the
commit the live run was drawn at to bound the three together.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import math
import subprocess
import sys
from collections import Counter
from multiprocessing import Pool, cpu_count
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL_DIR))

import s6s_siteplan as s6s  # noqa: E402
from common import DATA_DIR, read_stage  # noqa: E402

#: The last commit to touch s6s_siteplan.py before FOLLOWUPS 5 (n).
BEFORE_REV = "38932a24"

_BEFORE = None


def _load_before(path: str):
    spec = importlib.util.spec_from_file_location("s6s_before", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _init(cfg: dict, before_path: str) -> None:
    global _BEFORE
    _BEFORE = _load_before(before_path)
    _BEFORE._init_worker(cfg)
    s6s._init_worker(cfg)


def _write_before(rev: str, out: Path) -> Path:
    src = subprocess.run(["git", "-C", str(TOOL_DIR), "show", f"{rev}:./s6s_siteplan.py"],
                         capture_output=True, text=True, check=True, encoding="utf-8").stdout
    path = out / f"s6s_before_{rev}.py"
    path.write_text(src, encoding="utf-8")
    return path


class _Stop(Exception):
    """Raised from the patched `_finalize` so s6s main() writes nothing."""

    def __init__(self, lots):
        super().__init__("stopped before writing")
        self.lots = lots


def _capture_s6s_inputs(limit: int | None):
    """Run s6s main() up to its layout loop; return (lots, cfg, tasks).

    main() is run single-process with the worker swapped for one that only
    collects the chunks, and `_finalize` swapped for one that raises before
    it writes. Every print main() makes about the cities is still printed.
    """
    got: dict = {"cfg": None, "tasks": []}

    def init(cfg):
        got["cfg"] = cfg

    def collect(chunk):
        got["tasks"].extend(chunk)
        return []

    def stop(lots, *a, **k):
        raise _Stop(lots)

    saved = (s6s._init_worker, s6s._work_chunk, s6s._finalize, sys.argv)
    s6s._init_worker, s6s._work_chunk, s6s._finalize = init, collect, stop
    sys.argv = ["s6s_siteplan.py", "--processes", "1"] + (
        ["--limit", str(limit)] if limit else [])
    try:
        s6s.main()
    except _Stop as e:
        lots = e.lots
    else:  # pragma: no cover -- main() always finalizes
        raise RuntimeError("s6s main() returned without reaching _finalize")
    finally:
        s6s._init_worker, s6s._work_chunk, s6s._finalize, sys.argv = saved
    if got["cfg"] is None:
        raise RuntimeError("s6s main() wrote passthrough columns: siteplan is "
                           "disabled or no city can be dimensioned")
    return lots, got["cfg"], got["tasks"]


def _is_candidate(task, cfg: dict) -> bool:
    """Can the pole branch fire on any front of this lot?

    `layout_lot` enters it where the front's street piece is at least the
    lane's width and at most half the envelope grid's width (plus the
    strip test, which needs the raster, and is left to the replay). The
    grid's width is the envelope's extent along the front, give or take a
    cell, so a margin of two cells keeps every lot the branch can reach.
    """
    import shapely

    (_i, env_wkb, bearings, fedges, _a, _fsb, jur, _z, _psb, aedges, _asb, _aw,
     _ssb, xy) = task
    if not fedges:
        return False
    cells = cfg["cells"]
    cell = cells.get(jur) or next(iter(cells.values()))
    if cell.get("alley_access") and aedges:
        return False
    env = shapely.from_wkb(env_wkb)
    if env is None or env.is_empty:
        return False
    pts = shapely.get_coordinates(env)
    lane, res = cell["lane"], cfg["res"]
    for b, fe, _se in s6s._candidate_fronts(bearings, fedges, cell.get("front_rule"), xy):
        fe_len = sum(math.hypot(e[2] - e[0], e[3] - e[1]) for e in fe)
        width = s6s._extent_along([tuple(p) for p in pts], b) + 2.0 * res
        if lane <= fe_len <= 0.5 * width:
            return True
    return False


def _pick_chunk(args):
    chunk, cfg, everything = args
    return [t for t in chunk if everything or _is_candidate(t, cfg)]


_KEYS = ("site_plan_ok", "stalls_provided", "layout_method", "layout_fail",
         "building_name", "building_w_ft", "parking_area_sqft", "driveway_len_ft",
         "court_street_ft", "jog_ft")


def _summary(r: dict, fedges) -> dict:
    """The scalars, plus two read off the drawing: the building's width
    across the front, and how far along the front the drawn lane stands
    off the street piece it is meant to come from."""
    out = {k: r.get(k) for k in _KEYS}
    g = r.get("geoms") or {}
    b = r.get("front_bearing_deg")
    out["building_w_ft"] = out["jog_ft"] = None
    if b is None or not math.isfinite(b):
        return out
    import shapely

    if "building" in g:
        out["building_w_ft"] = round(s6s._extent_along(
            [tuple(p) for p in shapely.get_coordinates(g["building"])], b), 1)
    if "driveway" in g and r.get("layout_method") in ("townhome_rear_court",
                                                      "townhome_side_court"):
        t = math.radians(b)

        def proj(pts):
            v = [x * math.cos(t) + y * math.sin(t) for x, y in pts]
            return min(v), max(v)

        fe = [e for e in fedges if s6s.bearing_delta(s6s.bearing_deg(*e[:4]), b)
              <= s6s.BEARING_CLUSTER_TOL_DEG]
        if fe:
            f0, f1 = proj([(e[0], e[1]) for e in fe] + [(e[2], e[3]) for e in fe])
            d0, d1 = proj([tuple(p) for p in shapely.get_coordinates(g["driveway"])])
            out["jog_ft"] = round(max(0.0, d0 - f1, f0 - d1), 1)
    return out


def _replay_chunk(chunk):
    out = []
    for task in chunk:
        (idx, env_wkb, b, fe, area, fsb, jur, zone, psb, ae, asb, aw, ssb, xy) = task
        new = s6s.layout_lot(env_wkb, b, fe, area, fsb, jur, zone, psb, ae, asb, aw, ssb, xy)
        old = _BEFORE.layout_lot(env_wkb, b, fe, area, fsb, jur, zone, psb, ae, asb, aw,
                                 ssb, xy)
        out.append((idx, _summary(old, fe), _summary(new, fe)))
    return out


def _move(old: dict, new: dict) -> str:
    if old["site_plan_ok"] and not new["site_plan_ok"]:
        return "lost"
    if new["site_plan_ok"] and not old["site_plan_ok"]:
        return "gained"
    same = all(old[k] == new[k] for k in ("stalls_provided", "layout_method", "layout_fail",
                                           "building_w_ft", "parking_area_sqft",
                                           "driveway_len_ft"))
    return "same" if same else "redrawn"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--processes", type=int, default=max(1, cpu_count() - 2))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--before-rev", default=BEFORE_REV,
                    help="git revision whose s6s_siteplan.py is the BEFORE drawing")
    ap.add_argument("--limit", type=int, help="only the first N in-scope lots (debug)")
    ap.add_argument("--all", action="store_true",
                    help="replay every lot in scope, not just the candidates")
    ap.add_argument("--sample", type=int, default=40,
                    help="LOST lots listed in summary.txt")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    import pandas as pd

    before_path = _write_before(args.before_rev, args.out)
    lots, cfg, tasks = _capture_s6s_inputs(args.limit)
    print(f"bound: {len(tasks):,} lots in scope; picking candidates")

    step = 500
    chunks = [(tasks[i:i + step], cfg, args.all) for i in range(0, len(tasks), step)]
    with Pool(args.processes) as pool:
        picked = [t for out in pool.imap_unordered(_pick_chunk, chunks) for t in out]
    print(f"bound: {len(picked):,} candidates")

    rchunks = [picked[i:i + 50] for i in range(0, len(picked), 50)]
    rows = []
    with Pool(args.processes, initializer=_init, initargs=(cfg, str(before_path))) as pool:
        for n, out in enumerate(pool.imap_unordered(_replay_chunk, rchunks), 1):
            rows.extend(out)
            if n % 20 == 0:
                print(f"  {len(rows):,}/{len(picked):,}")

    try:
        stored = read_stage("s6s_lots", columns=["TLID", "site_plan_ok",
                                                  "stalls_provided", "layout_method"])
        stored = stored.set_index("TLID")
    except (FileNotFoundError, OSError):
        print("bound: no stored s6s_lots; the fidelity check is skipped")
        stored = pd.DataFrame(index=pd.Index([], name="TLID"))
    res_csv = DATA_DIR / "lots_results.csv"
    triage = {}
    if res_csv.exists():
        t = pd.read_csv(res_csv, usecols=["TLID", "triage"], dtype=str)
        triage = dict(zip(t["TLID"], t["triage"]))

    moves, per_city, widths, fidelity_bad = Counter(), Counter(), Counter(), []
    lost: dict[str, list[str]] = {}
    jogs_before, jogs_after = [], []
    fields = (["TLID", "jurisdiction", "zone", "tier", "move", "triage_now"]
              + [f"{k}_before" for k in _KEYS] + [f"{k}_after" for k in _KEYS])
    with open(args.out / "moves.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for idx, old, new in sorted(rows, key=lambda r: r[0]):
            row = lots.iloc[idx]
            tlid, jur = str(row["TLID"]), str(row["jurisdiction"])
            tier = str(row["tier"]) if "tier" in row.index else ""
            mv = _move(old, new)
            moves[mv] += 1
            per_city[(jur, mv)] += 1
            if old["jog_ft"] is not None and old["site_plan_ok"]:
                jogs_before.append(old["jog_ft"])
            if new["jog_ft"] is not None and new["site_plan_ok"]:
                jogs_after.append(new["jog_ft"])
            if (old["site_plan_ok"] and new["site_plan_ok"]
                    and old["building_w_ft"] != new["building_w_ft"]):
                widths[(jur, old["building_w_ft"], new["building_w_ft"])] += 1
            if tlid in stored.index:
                s = stored.loc[tlid]
                s_stalls = pd.to_numeric(s["stalls_provided"], errors="coerce")
                if (bool(s["site_plan_ok"]) != bool(old["site_plan_ok"])
                        or s_stalls != old["stalls_provided"]):
                    fidelity_bad.append(tlid)
            if mv == "lost":
                lost.setdefault(tier, []).append(
                    f"{tlid} {jur} {row['zone']}: {old['layout_method']} "
                    f"{old['stalls_provided']} stalls, jog {old['jog_ft']} ft -> "
                    f"{new['layout_fail'] or new['layout_method']}")
            w.writerow({"TLID": tlid, "jurisdiction": jur, "zone": str(row["zone"]),
                        "tier": tier, "move": mv, "triage_now": triage.get(tlid, ""),
                        **{f"{k}_before": v for k, v in old.items()},
                        **{f"{k}_after": v for k, v in new.items()}})

    def jog_line(name, v):
        moved = sorted(x for x in v if x > 0.0)
        med = moved[len(moved) // 2] if moved else 0.0
        return (f"  {name}: {len(moved):,} of {len(v):,} drawn front-lane plans stand "
                f"off the street piece (median {med:g} ft, max {max(moved, default=0):g})")

    lines = [f"bound FOLLOWUPS 5 (n) on {DATA_DIR}, before = {args.before_rev}",
             f"lots in scope {len(tasks):,}; replayed {len(rows):,}"
             + (" (--all)" if args.all else " (candidates)"), "",
             "by move:"]
    lines += [f"  {mv:8s} {v:7,}" for mv, v in sorted(moves.items())]
    lines += ["", "by city (moved lots only):"]
    lines += [f"  {jur:24s} {mv:8s} {v:7,}" for (jur, mv), v in sorted(per_city.items())
              if mv != "same"]
    lines += ["", "the lane's jog along the front (ok plans, lane from the front street):",
              jog_line("before", jogs_before), jog_line("after", jogs_after)]
    lines += ["", "building width across the front changed, plan ok both ways:"]
    lines += [f"  {jur:24s} {a} -> {b} ft  {v:6,}"
              for (jur, a, b), v in sorted(widths.items(), key=lambda x: -x[1])]
    lines += ["", f"replay fidelity: BEFORE replay disagrees with stored s6s_lots "
                  f"on {len(fidelity_bad):,} of {len(rows):,} lots"
                  + (" (first 20: " + ", ".join(fidelity_bad[:20]) + ")"
                     if fidelity_bad else "")]
    for tier, items in sorted(lost.items()):
        lines += ["", f"LOST, tier {tier or '?'} ({len(items):,}; first {args.sample} -- "
                      f"read each):"]
        lines += [f"  {x}" for x in items[: args.sample]]
    text = "\n".join(lines) + "\n"
    (args.out / "summary.txt").write_text(text, encoding="utf-8")
    print(text)
    print(f"wrote {args.out / 'moves.csv'} and {args.out / 'summary.txt'}")


if __name__ == "__main__":
    main()
