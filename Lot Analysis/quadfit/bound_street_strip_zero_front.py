"""Bound for FOLLOWUPS 5 (l) and (o): which site plans move, and which way.

Two fixes to s6s landed on 2026-09-28 and neither has been run over the
county yet:

(l) THE STREET STRIP STOPS WHERE THE STREET DOES. The cells "on the street"
    were found by buffering each street lot line with SQUARE caps, so the
    strip ran on past the end of a frontage along a neighbour's line; a lane
    could start up to the street setback plus a cell and a half past the end
    of the frontage. A free end is now cut flat; an end another street edge
    continues from keeps its cap (`_alley_mouths`, `joins`).

(o) A ZERO FRONT SETBACK IS THE CODE'S ANSWER. main() read a zero front
    setback as "missing" and put 10 ft in its place. That number moves no
    pod (the envelope is s5's, cut to the real zero); it only tells the
    layout how much of a city's parking street setback the envelope already
    answers, so the fallback forgave Portland's 10 ft on every lot in its
    eight zero-setback zones (`_front_setback_for`).

This replays `layout_lot` twice on every lot either fix can reach -- once as
the code stood before (square caps on every street strip; a zero front
setback read as 10 ft) and once as it stands -- and writes what moved. It
builds its lots by running s6s's own main() up to the point where it would
lay them out, so the inputs are exactly the stage's, then stops before
anything is written: NO STAGE OUTPUT IS TOUCHED. It reads s6_lots, s5o_lots,
s4_lots (through s6s), s6s_lots (the stored drawing, for a replay-fidelity
check) and lots_results.csv (for each lot's current colour) from
QUADFIT_DATA_DIR, and writes only under --out.

Which lots it replays:

  o  in scope, front setback 0, and the city keeps parking off the street
     (`parking_street_setback_for` > 0) -- only there does the number differ;
  l  in scope, and the square-capped street strip reaches envelope ground
     the flat-cut strip does not (a shapely test in county coordinates; the
     envelope's cells lie inside the envelope, so a lot the test clears
     cannot move). `--all` replays every lot in scope instead, to check it.

On LXC 137, from the repo, against the run whose drawing is live (the
`QUADFIT_DATA_DIR` of that run; nohup because a county replay takes a while):

    cd /root/code/vicinitideals && git pull
    QUADFIT_DATA_DIR=data/quadfit_2026-09-18 PYTHONIOENCODING=utf-8 \\
      nohup .venv/bin/python "Lot Analysis/quadfit/bound_street_strip_zero_front.py" \\
      --processes 10 --out /root/bound_l_o > /root/bound_l_o.log 2>&1 &

Outputs, under --out:

  moves.csv    one row per replayed lot: TLID, city, zone, reason (l / o /
               l+o), before and after site_plan_ok, stalls, method,
               layout_fail, parking area, driveway length and the court's
               street exposure (court_street_ft), the lot's current triage, and `move` --
               lost / gained / redrawn / same.
  summary.txt  counts by reason and city, the replay-fidelity check, and
               up to --sample LOST lots per reason to read one by one.

A LOST lot (site_plan_ok true -> false) goes red in s7 whatever its colour
was. A GAINED lot needs s7 to say which colour; this reports its current
one. A REDRAWN lot keeps its verdict with a different plan or stall count.
The fidelity check compares the BEFORE replay with the stored s6s_lots: on a
run drawn by the code before these fixes they should agree on every lot,
and a disagreement means the stored stage is not the one this replays.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import Counter
from multiprocessing import Pool, cpu_count
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL_DIR))

import s6s_siteplan as s6s  # noqa: E402
from common import DATA_DIR, read_stage  # noqa: E402

#: What the code read a zero (or absent) front setback as before (o).
OLD_FALLBACK_FT = 10.0
#: A sliver of envelope smaller than this is float noise at the frontage
#: corner, not ground a cell centre can stand on.
AREA_TOL_SQFT = 0.01

_ORIG_MOUTHS = s6s._alley_mouths


def _square_mouths(ok, alley_edges, minx, miny, res, reach_ft, joins=None):
    """`_alley_mouths` as it stood before (l): every cap square."""
    return _ORIG_MOUTHS(ok, alley_edges, minx, miny, res, reach_ft)


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


def _strip(edges, reach, joins):
    import shapely
    from shapely.geometry import LineString

    pieces = []
    for e in edges:
        (x0, y0), (x1, y1) = (e[0], e[1]), (e[2], e[3])
        n = math.hypot(x1 - x0, y1 - y0)
        if joins is None:
            pieces.append(LineString([(x0, y0), (x1, y1)]).buffer(
                reach, cap_style="square", join_style="mitre"))
            continue
        if n <= 0.0:
            continue
        # The same construction as `_alley_mouths`, asked of whole edges.
        ux, uy = (x1 - x0) / n, (y1 - y0) / n

        def met(px, py, a0=(x0, y0), a1=(x1, y1)):
            for j in joins:
                a, b = (j[0], j[1]), (j[2], j[3])
                if (math.dist(a, a0) <= s6s.JOIN_TOL_FT and math.dist(b, a1) <= s6s.JOIN_TOL_FT) or (
                        math.dist(a, a1) <= s6s.JOIN_TOL_FT and math.dist(b, a0) <= s6s.JOIN_TOL_FT):
                    continue
                if math.dist(a, (px, py)) <= s6s.JOIN_TOL_FT or math.dist(b, (px, py)) <= s6s.JOIN_TOL_FT:
                    return True
            return False

        s0 = reach if met(x0, y0) else 0.0
        s1 = reach if met(x1, y1) else 0.0
        pieces.append(LineString([(x0 - ux * s0, y0 - uy * s0),
                                  (x1 + ux * s1, y1 + uy * s1)]).buffer(
            reach, cap_style="flat", join_style="mitre"))
    return shapely.union_all(pieces) if pieces else None


def _strip_reaches_more(env_wkb, fedges, reach) -> bool:
    """Does any street edge's square-capped piece cover envelope its flat one misses?

    Asked EDGE BY EDGE, not of the union: `layout_lot` draws three strips
    from subsets of the street edges (all of them; this front's; the other
    streets'), and a cap trimmed off one edge can be covered by another edge
    that is in the union and not in the subset. If no single piece changes
    inside the envelope, no union of pieces can.
    """
    import shapely

    if not fedges:
        return False
    env = shapely.from_wkb(env_wkb)
    for e in fedges:
        sq = _strip([e], reach, None)
        fl = _strip([e], reach, fedges)
        if sq is None:
            continue
        extra = sq if fl is None else sq.difference(fl)
        if extra.intersection(env).area > AREA_TOL_SQFT:
            return True
    return False


def _classify(task, res: float, everything: bool) -> str:
    (_i, env_wkb, _b, fedges, _a, fsb, _j, _z, psb, _ae, _asb, _aw, ssb, _xy) = task
    o = bool(psb) and psb > 0 and fsb == 0.0
    reach = (ssb if ssb is not None else fsb) + 2.0 * res + 0.5
    ll = _strip_reaches_more(env_wkb, fedges, reach)
    tag = "+".join(t for t, on in (("l", ll), ("o", o)) if on)
    return tag or ("none" if everything else "")


def _classify_chunk(args):
    chunk, res, everything = args
    out = []
    for t in chunk:
        tag = _classify(t, res, everything)
        if tag:
            out.append((t, tag))
    return out


_KEYS = ("site_plan_ok", "stalls_provided", "layout_method", "layout_fail",
         "parking_area_sqft", "driveway_len_ft", "court_street_ft")


def _summary(r: dict) -> dict:
    return {k: r.get(k) for k in _KEYS}


def _replay_chunk(chunk):
    out = []
    for task, tag in chunk:
        (idx, env_wkb, b, fe, area, fsb, jur, zone, psb, ae, asb, aw, ssb, xy) = task
        new = s6s.layout_lot(env_wkb, b, fe, area, fsb, jur, zone, psb, ae, asb,
                             aw, ssb, xy)
        s6s._alley_mouths = _square_mouths
        try:
            old = s6s.layout_lot(env_wkb, b, fe, area, fsb or OLD_FALLBACK_FT,
                                 jur, zone, psb, ae, asb, aw, ssb, xy)
        finally:
            s6s._alley_mouths = _ORIG_MOUTHS
        out.append((idx, tag, _summary(old), _summary(new)))
    return out


def _move(old: dict, new: dict) -> str:
    if old["site_plan_ok"] and not new["site_plan_ok"]:
        return "lost"
    if new["site_plan_ok"] and not old["site_plan_ok"]:
        return "gained"
    same = all(old[k] == new[k] for k in ("stalls_provided", "layout_method",
                                           "layout_fail"))
    if same and old["parking_area_sqft"] == new["parking_area_sqft"]:
        return "same"
    return "redrawn"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--processes", type=int, default=max(1, cpu_count() - 2))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--limit", type=int, help="only the first N in-scope lots (debug)")
    ap.add_argument("--all", action="store_true",
                    help="replay every lot in scope, not just the candidates")
    ap.add_argument("--sample", type=int, default=25,
                    help="LOST lots per reason listed in summary.txt")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    import pandas as pd

    lots, cfg, tasks = _capture_s6s_inputs(args.limit)
    res = cfg["res"]
    print(f"bound: {len(tasks):,} lots in scope; picking candidates")

    step = 500
    chunks = [(tasks[i:i + step], res, args.all) for i in range(0, len(tasks), step)]
    with Pool(args.processes) as pool:
        picked = [x for out in pool.imap_unordered(_classify_chunk, chunks) for x in out]
    print(f"bound: {len(picked):,} candidates "
          + ", ".join(f"{k} {v:,}" for k, v in Counter(t for _, t in picked).most_common()))

    rchunks = [picked[i:i + 50] for i in range(0, len(picked), 50)]
    rows = []
    with Pool(args.processes, initializer=s6s._init_worker, initargs=(cfg,)) as pool:
        for n, out in enumerate(pool.imap_unordered(_replay_chunk, rchunks), 1):
            rows.extend(out)
            if n % 20 == 0:
                print(f"  {len(rows):,}/{len(picked):,}")

    # What the stored stage drew, and each lot's colour now.
    stored = read_stage("s6s_lots", columns=["TLID", "site_plan_ok",
                                              "stalls_provided", "layout_method"])
    stored = stored.set_index("TLID")
    res_csv = DATA_DIR / "lots_results.csv"
    triage = {}
    if res_csv.exists():
        t = pd.read_csv(res_csv, usecols=["TLID", "triage"], dtype=str)
        triage = dict(zip(t["TLID"], t["triage"]))

    moves, per_city, fidelity_bad, lost = Counter(), Counter(), [], {}
    fields = (["TLID", "jurisdiction", "zone", "reason", "move", "triage_now"]
              + [f"{k}_before" for k in _KEYS]
              + [f"{k}_after" for k in _KEYS])
    with open(args.out / "moves.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for idx, tag, old, new in sorted(rows, key=lambda r: r[0]):
            row = lots.iloc[idx]
            tlid, jur = str(row["TLID"]), str(row["jurisdiction"])
            mv = _move(old, new)
            moves[(tag, mv)] += 1
            per_city[(jur, tag, mv)] += 1
            if tlid in stored.index:
                s = stored.loc[tlid]
                s_stalls = pd.to_numeric(s["stalls_provided"], errors="coerce")
                if (bool(s["site_plan_ok"]) != bool(old["site_plan_ok"])
                        or s_stalls != old["stalls_provided"]):
                    fidelity_bad.append(tlid)
            if mv == "lost":
                lost.setdefault(tag, []).append(
                    f"{tlid} {jur} {row['zone']}: {old['layout_method']} "
                    f"{old['stalls_provided']} stalls -> {new['layout_fail'] or new['layout_method']}")
            w.writerow({"TLID": tlid, "jurisdiction": jur, "zone": str(row["zone"]),
                        "reason": tag, "move": mv, "triage_now": triage.get(tlid, ""),
                        **{f"{k}_before": v for k, v in old.items()},
                        **{f"{k}_after": v for k, v in new.items()}})

    lines = [f"bound FOLLOWUPS 5 (l)+(o) on {DATA_DIR}",
             f"lots in scope {len(tasks):,}; replayed {len(rows):,}"
             + (" (--all)" if args.all else " (candidates)"), "",
             "by reason and move:"]
    for (tag, mv), v in sorted(moves.items()):
        lines.append(f"  {tag:5s} {mv:8s} {v:7,}")
    lines += ["", "by city (moved lots only):"]
    for (jur, tag, mv), v in sorted(per_city.items()):
        if mv != "same":
            lines.append(f"  {jur:24s} {tag:5s} {mv:8s} {v:7,}")
    lines += ["", f"replay fidelity: BEFORE replay disagrees with stored s6s_lots "
                  f"on {len(fidelity_bad):,} of {len(rows):,} lots"
                  + (" (first 20: " + ", ".join(fidelity_bad[:20]) + ")" if fidelity_bad else "")]
    for tag, items in sorted(lost.items()):
        lines += ["", f"LOST, reason {tag} ({len(items):,}; first {args.sample} -- read each):"]
        lines += [f"  {x}" for x in items[: args.sample]]
    text = "\n".join(lines) + "\n"
    (args.out / "summary.txt").write_text(text, encoding="utf-8")
    print(text)
    print(f"wrote {args.out / 'moves.csv'} and {args.out / 'summary.txt'}")


if __name__ == "__main__":
    main()
