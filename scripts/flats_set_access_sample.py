"""Set access over a sample of a finished bridge run: which crane sets the
pod on each lot, from where, and what binds (FOLLOWUPS 145, slice 3: the
IC-80 from one or both long faces, then the hired 45 t; crane spec S3e).

A REPORT. It reads a run's ``lots.parquet`` and writes beside nothing of
it: no colour, reason, flag or result is touched (Steph 2026-11-14: "Don't
flag any lots by color yet"). For each sampled lot it rebuilds the lot from
the run's own stage files (``meta.json``'s ``s4``/``s5o``), takes the pod
where the screen drew it (the row's ``drawing``), and runs
:func:`flats.fit.set_access.report` with the run's own street data: the
truck centrelines (``roads``) and the curbs and pavement widths (``curbs``),
and the run's elevation models (``dem``) for the fall across the IC-80's
working strip and the 45 t's pad (both must be within 1%; ``--no-grade``
skips it, and level is then unmeasured on every lot).

Writes into ``--out``:

* ``set_access.csv`` -- one row per lot: TLID, jurisdiction, zone, colour,
  the result (``IC-80 one face (front|back)`` / ``IC-80 both faces`` /
  ``45 t on site`` / ``45 t in the street`` / ``not viable`` /
  ``unmeasured``), the binding check, the hardest lift with its chart row,
  capacity and percent of chart, the IC-80's wall-rigging limit, each
  step's status, notes ("power lines not checked") and why the earlier
  steps failed.
* ``summary.md`` -- the counts by result, by jurisdiction, the binding
  checks and lifts, and the commonest reasons.

Run on LXC 137 when its heavy lock is free (never on production), e.g.::

    cd /root/vicinitideals && uv run python scripts/flats_set_access_sample.py \\
        --run <RUN_DIR> --colour green --per-jurisdiction 40 \\
        --out /root/set_access_sample_$(date +%F) --processes 4

``--colour any`` with ``--per-jurisdiction`` gives a stratified sample of
every lot the pod was drawn on; ``--tlids FILE`` (one TLID per line) runs
named lots. Some 0.1-6 s a lot on one process.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_W: dict[str, Any] = {}


def _init(meta: dict[str, Any], grade: bool) -> None:
    """Per process: the corpus layers, the street data, the terrain."""
    from flats.fit import fire
    from flats.fit import set_access as sa
    from flats.geom.curbs import load as load_street_edges
    from flats.rules.loader import load_rules

    _W["layers"] = load_rules()
    edges = load_street_edges(Path(meta["curbs"])) if meta.get("curbs") else None
    lines, _ = fire.truck_lines(Path(meta["roads"]), edges)
    _W["reader"] = sa.street_reader(edges, lines, fire.MAX_GAP_FT) if edges is not None else None
    _W["terrain"] = None
    if grade and meta.get("dem"):
        from flats.ingest.quadfit import terrain_at

        _W["terrain"] = terrain_at(Path(meta["dem"]))


def _one(row: dict[str, Any], picked: dict[str, Any]) -> dict[str, Any]:
    from flats.fit import set_access as sa
    from flats.ingest import quadfit

    base = {
        "TLID": picked["TLID"],
        "jurisdiction": picked.get("jurisdiction"),
        "zone": picked.get("zone"),
        "colour": picked.get("colour"),
    }
    t0 = time.time()
    try:
        lot = quadfit.lot_from_row(row, _W["layers"])
        street = tuple(dict.fromkeys(quadfit._street_lines(lot) + quadfit._side_street_lines(lot)))
        drawing = json.loads(picked["drawing"])
        site = sa.site_from_drawing(lot.lot_geom, drawing, street, _W["reader"])
        if site is None:
            return {**base, "result": "unmeasured", "why": "no drawn building"}
        if not street:
            return {**base, "result": "unmeasured", "why": "no street lot line traced"}
        terrain = _W.get("terrain")
        grade_of = None
        if terrain is not None:

            def grade_of(poly: Any) -> float | None:
                g = terrain.grade([poly])
                return None if g is None else g.pct

        rep = sa.report(site, grade_of=grade_of)
        return {**base, **rep.row(), "seconds": round(time.time() - t0, 2)}
    except Exception as exc:  # noqa: BLE001 -- one bad lot is reported, not fatal
        return {**base, "result": "error", "why": f"{type(exc).__name__}: {exc}"}


def _work(batch: list[tuple[dict[str, Any], dict[str, Any]]]) -> list[dict[str, Any]]:
    return [_one(r, p) for r, p in batch]


def _pick(lots: Any, args: argparse.Namespace) -> Any:
    """The sampled rows: one per TLID, the pod drawn and fitting."""
    import pandas as pd

    frame = lots[lots["drawing"].notna()].copy()
    frame = frame[frame["drawing"].map(lambda d: bool(json.loads(d).get("fits")))]
    if args.colour != "any":
        frame = frame[frame["colour"] == args.colour]
    frame = frame.drop_duplicates("TLID")
    if args.tlids:
        wanted = {ln.strip() for ln in Path(args.tlids).read_text(encoding="utf-8").splitlines() if ln.strip()}
        return frame[frame["TLID"].isin(wanted)]
    if args.per_jurisdiction:
        parts = [
            g.sample(min(len(g), args.per_jurisdiction), random_state=args.seed)
            for _, g in frame.groupby("jurisdiction", sort=True)
        ]
        frame = pd.concat(parts) if parts else frame.iloc[:0]
    if args.sample and len(frame) > args.sample:
        frame = frame.sample(args.sample, random_state=args.seed)
    return frame


#: The summary's result columns, in the viability order.
RESULTS = (
    "IC-80 one face (front)",
    "IC-80 one face (back)",
    "IC-80 one face (long face 1)",
    "IC-80 one face (long face 2)",
    "IC-80 both faces",
    "45 t on site",
    "45 t in the street",
    "not viable",
    "unmeasured",
    "error",
)
_SHORT = {
    "IC-80 one face (front)": "IC-80 front",
    "IC-80 one face (back)": "IC-80 back",
    "IC-80 one face (long face 1)": "IC-80 face 1",
    "IC-80 one face (long face 2)": "IC-80 face 2",
}
_WORKS = ("IC-80", "45 t")


def _summary(rows: list[dict[str, Any]], meta: dict[str, Any], args: argparse.Namespace, seconds: float) -> str:
    from flats.fit.set_access import NOT_CHECKED

    def table(counter: collections.Counter, head: str) -> list[str]:
        out = [f"| {head} | lots |", "|---|---|"]
        out += [f"| {k} | {v:,} |" for k, v in counter.most_common()]
        return out

    def works(r: dict[str, Any]) -> bool:
        return str(r.get("result") or "").startswith(_WORKS)

    seen = {r.get("result") for r in rows}
    # The long-face columns only where a lot's front could not be told.
    cols = [c for c in RESULTS if "long face" not in c or c in seen]
    lines = [
        "# Set access sample (FOLLOWUPS 145, report only)",
        "",
        f"Run: `{args.run}` (law on {meta.get('law_on')}); colour `{args.colour}`; "
        f"{len(rows):,} lots in {seconds / 60:.1f} min.",
        "",
        "Not checked on any lot: " + ", ".join(NOT_CHECKED) + ".",
        "",
        "## Result",
        "",
        *table(collections.Counter(str(r.get("result")) for r in rows), "result"),
        "",
        "## By jurisdiction",
        "",
        "| jurisdiction | " + " | ".join(_SHORT.get(c, c) for c in cols) + " |",
        "|---|" + "---|" * len(cols),
    ]
    by: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for r in rows:
        by[str(r.get("jurisdiction"))][str(r.get("result"))] += 1
    for j in sorted(by):
        c = by[j]
        lines.append(f"| {j} | " + " | ".join(str(c[k]) for k in cols) + " |")
    lines += [
        "",
        "## Binding check and hardest lift (lots where a crane works)",
        "",
        *table(
            collections.Counter(
                f"{r.get('result')}: {r.get('binding_check')} ({r.get('hardest_lift')}, "
                f"{r.get('pct_of_chart')}% at {r.get('chart_row_ft')} ft)"
                for r in rows
                if works(r)
            ),
            "result: binding",
        ),
        "",
        "## Commonest reasons (every step before the answer)",
        "",
    ]
    why: collections.Counter = collections.Counter()
    for r in rows:
        for w in str(r.get("why") or "").split("; "):
            if w:
                why[_generic(w)] += 1
    lines += table(why, "reason") if why else ["(none)"]
    return "\n".join(lines) + "\n"


def _generic(reason: str) -> str:
    """A reason with its numbers taken out, so like reasons count together."""
    import re

    return re.sub(r"\d[\d,]*(?:\.\d+)?", "#", reason)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", type=Path, required=True, help="a bridge run directory (lots.parquet, meta.json)")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--colour", default="green", choices=["green", "yellow", "red", "any"])
    parser.add_argument("--sample", type=int, default=None, help="at most this many lots")
    parser.add_argument("--per-jurisdiction", type=int, default=None, help="at most this many lots per jurisdiction")
    parser.add_argument("--tlids", type=Path, default=None, help="a file of TLIDs, one per line")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--processes", type=int, default=1)
    parser.add_argument(
        "--no-grade", dest="grade", action="store_false",
        help="do not read the strip's and pad's fall off the run's elevation models (level is then unmeasured)",
    )
    for key in ("s4", "s5o", "roads", "curbs", "dem"):
        parser.add_argument(f"--{key}", type=Path, default=None, help=f"override meta.json's {key}")
    args = parser.parse_args(argv)

    import pandas as pd

    from flats.ingest import quadfit

    meta = json.loads((args.run / "meta.json").read_text(encoding="utf-8"))
    for key in ("s4", "s5o", "roads", "curbs", "dem"):
        if getattr(args, key) is not None:
            meta[key] = str(getattr(args, key))
    for key in ("s4", "s5o", "roads"):
        if not meta.get(key) or not Path(meta[key]).exists():
            parser.error(f"no {key} file: {meta.get(key)} (pass --{key})")
    if not meta.get("curbs"):
        print("set access: no curbs snapshot -- every street set-up and curb truck is unmeasured")

    lots = pd.read_parquet(args.run / "lots.parquet", columns=["TLID", "jurisdiction", "zone", "colour", "drawing"])
    picked = _pick(lots, args)
    if not len(picked):
        parser.error("no lot matches the sample")
    by_tlid = {str(p["TLID"]): p for p in picked.to_dict("records")}
    rows = list(quadfit.iter_rows(Path(meta["s4"]), Path(meta["s5o"]), tlids=list(by_tlid)))
    pairs = [(r, by_tlid[str(r["TLID"])]) for r in rows if str(r["TLID"]) in by_tlid]
    print(f"set access: {len(pairs):,} lots of {len(picked):,} sampled found in {meta['s4']}")

    t0 = time.time()
    out_rows: list[dict[str, Any]] = []
    if args.processes > 1:
        from concurrent.futures import ProcessPoolExecutor

        size = max(1, math.ceil(len(pairs) / (args.processes * 8)))
        batches = [pairs[i : i + size] for i in range(0, len(pairs), size)]
        with ProcessPoolExecutor(args.processes, initializer=_init, initargs=(meta, args.grade)) as pool:
            for got in pool.map(_work, batches):
                out_rows.extend(got)
                print(f"set access: {len(out_rows):,}/{len(pairs):,}", flush=True)
    else:
        _init(meta, args.grade)
        for i, pair in enumerate(pairs, 1):
            out_rows.append(_one(*pair))
            if i % 25 == 0:
                print(f"set access: {i:,}/{len(pairs):,}", flush=True)
    seconds = time.time() - t0

    args.out.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for r in out_rows:
        fields.extend(k for k in r if k not in fields)
    with (args.out / "set_access.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(out_rows)
    (args.out / "summary.md").write_text(_summary(out_rows, meta, args, seconds), encoding="utf-8")
    print(f"set access: wrote {args.out / 'set_access.csv'} and summary.md in {seconds / 60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
