"""Set access over a sample of a finished bridge run: which crane sets the
pod on each lot, from where, and what binds (FOLLOWUPS 145, slices 3-4: the
IC-80 from one or both long faces, its trailer on the lot or in the street,
pieces picked there and carried; then the hired 45 t; crane spec S3e).

A REPORT. It reads a run's ``lots.parquet`` and writes beside nothing of
it: no colour, reason, flag or result is touched (Steph 2026-11-14: "Don't
flag any lots by color yet"). For each sampled lot it rebuilds the lot from
the run's own stage files (``meta.json``'s ``s4``/``s5o``), takes the pod
where the screen drew it (the row's ``drawing``), and runs
:func:`flats.fit.set_access.report` with the run's own street data: the
truck centrelines (``roads``: they also place the IC-80's street trailer,
slice 4; no curb is read for it) and the curbs and pavement widths
(``curbs``, the 45 t's street set-up only), and the run's elevation models
(``dem``) for the fall across each IC-80 set-up spot's pads (~3%) and the
45 t's pad (1%); ``--no-grade`` skips it, and level is then unmeasured on
every lot. ``--canopy`` (a GeoTIFF of Metro's Canopy 2019, the cell value
the crown height, ft; EPSG:2913) puts the trees in: canopy in the IC-80's
working ground, swing room or on a carry path blocks it, and each row also
carries the answer with the trees left out (``result_no_trees``).

The street's pavement width (FOLLOWUPS 145, Steph 2026-11-15) is read by
:mod:`flats.geom.street_width`: the fire hose's curbs and widths, plus
Washington County's and Tualatin's width attributes, Hillsboro's paved
shapes and Oregon City's pavement edges, from the run's ``curbs`` snapshot
and any ``--widths`` snapshot (the first holding a dataset gives it); and
where none reads a point, an ESTIMATE off the right-of-way in the taxlot
fabric (``--fabric``, default quadfit s1's ``s1_lots.parquet`` beside
``s4``) less the ``street_width`` allowance of ``set_access.yaml``.
``--no-estimate`` leaves the estimate out. A row's ``width_source`` (and
``45t_street_width``) says ``measured:<dataset>`` or ``estimated:<basis>``
(the street standard, or the stated default, it rests on); a 45 t
street answer on an estimate reads ``45 t in the street (width estimated)``.

Each lot is run once per carry case (slice 4b, ``--combos``): ``spec``
(S3e 3.7 at 9985b64: cassettes flat and crosswise, walls upright) and
``relaxed`` (walls may also be carried flat and crosswise, the switch
``walls_flat_crosswise`` that waits on FOLLOWUPS 215(a)); ``--walls-flat``
runs relaxed alone.
And once per wall-gear case (slice 3c; ``ic80.wall_gear_lb``, spec 3.6):
``light`` (400 lb, the default) or ``heavy`` (800 lb, the far walls then
need both faces); ``--gear both`` runs both. Only the walls take the gear.

Writes into ``--out``:

* ``set_access.csv`` -- one row per lot and gear case: TLID, jurisdiction,
  zone, colour, the gear case and its wall rigging, the wall-load stacking
  order (``stack``), each load's trailer spot (``truck``),
  the result (``IC-80 one face (front|back)`` / ``IC-80 both faces`` /
  ``45 t on site`` / ``45 t in the street`` / ``not viable`` /
  ``unmeasured``), the binding check, the hardest lift with its chart row,
  capacity and percent of chart, the IC-80's wall-rigging limit, each
  step's status, notes ("power lines not checked") and why the earlier
  steps failed.
* ``summary.md`` -- for each case, the lots on each result (IC-80 one
  face, IC-80 both faces, 45 t on site, 45 t in the street, not viable,
  unmeasured) side by side, with and without the trees; the lots the second
  case moves, the stacking orders; then per case the counts by result, how
  the IC-80 works (trailer on the lot or in the street, carried or not),
  what the trees cost, the failing checks of each IC-80 step, by
  jurisdiction, the binding checks and lifts, and the commonest reasons.

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
import dataclasses
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


#: The carry cases (slice 4b): walls may be carried flat and crosswise.
COMBOS: dict[str, bool] = {"spec": False, "relaxed": True}
_COMBO_WORDS = {"spec": "spec", "relaxed": "relaxed (walls carried flat)"}
#: Metro's Canopy 2019 data extent (canopy2019.xml westbc/eastbc/northbc/
#: southbc): a lot outside it has its trees unmeasured.
CANOPY_EXTENT = (-123.153528597, 45.23396470, -122.367487422, 45.70263875)
#: How far round a lot the canopy is read (beyond the IC-80's swing room).
CANOPY_PAD_FT = 40.0
#: A lot inside the extent with no canopy cell this far round it is taken
#: as off the map (no LiDAR there), not as treeless.
CANOPY_SEEN_FT = 500.0


def _cases(combos: tuple[str, ...], gears: tuple[str, ...]) -> dict[str, tuple[str, str, Any]]:
    from flats.fit import set_access as sa

    base = sa.load_rules()
    out = {}
    for c in combos:
        for g in gears:
            rules = sa.with_carry(sa.with_wall_gear(base, g), walls_flat=COMBOS[c])
            out[f"{c}/{g}"] = (c, g, rules)
    return out


def _init(
    meta: dict[str, Any], grade: bool, gears: tuple[str, ...] = ("light",), combos: tuple[str, ...] = ("spec",),
    canopy: str | None = None,
) -> None:
    """Per process: the corpus layers, the street data, the terrain, the
    canopy, and the set-access rules for each case."""
    import shapely

    from flats.fit import fire
    from flats.fit import set_access as sa
    from flats.geom import street_width
    from flats.geom.curbs import load as load_street_edges
    from flats.rules.loader import load_rules

    _W["layers"] = load_rules()
    _W["cases"] = _cases(combos, gears)
    # The truck centrelines exactly as the fire hose takes them (its own
    # curbs and widths decide which unnamed roads count as paved).
    edges = load_street_edges(Path(meta["curbs"])) if meta.get("curbs") else None
    lines, _ = fire.truck_lines(Path(meta["roads"]), edges)
    snaps = [Path(x) for x in (meta.get("curbs"), *(meta.get("widths") or ())) if x]
    fabric = meta.get("fabric")
    widths = street_width.load(snaps, Path(fabric) if fabric else None) if (snaps or fabric) else None
    _W["widths"] = widths
    _W["lines"] = lines
    _W["line_tree"] = shapely.STRtree(lines) if len(lines) else None
    _W["reader"] = None
    _W["centre"] = sa.centre_reader(lines, fire.MAX_GAP_FT)
    _W["terrain"] = None
    if grade and meta.get("dem"):
        from flats.ingest.quadfit import terrain_at

        _W["terrain"] = terrain_at(Path(meta["dem"]))
    _W["canopy"] = None
    if canopy:
        import rasterio
        from pyproj import Transformer

        _W["canopy"] = rasterio.open(canopy)
        _W["to_lonlat"] = Transformer.from_crs(2913, 4326, always_xy=True)


def _trees(lot_geom: Any) -> Any:
    """The canopy round the lot (:class:`flats.fit.set_access.Trees`), from
    the ``--canopy`` raster: every cell with a crown, any height (a crown
    height is the top, not the clearance under it)."""
    import numpy as np
    import shapely
    import shapely.geometry
    from rasterio.features import shapes
    from rasterio.windows import from_bounds

    from flats.fit import set_access as sa

    src = _W["canopy"]
    lon, lat = _W["to_lonlat"].transform(*lot_geom.centroid.coords[0])
    w, s, e, n = CANOPY_EXTENT
    if not (w <= lon <= e and s <= lat <= n):
        return sa.Trees(shapely.Polygon(), covered=False, source="canopy map (Metro 2019)")
    b = lot_geom.bounds
    win = from_bounds(b[0] - CANOPY_SEEN_FT, b[1] - CANOPY_SEEN_FT, b[2] + CANOPY_SEEN_FT, b[3] + CANOPY_SEEN_FT,
                      transform=src.transform).round_offsets().round_lengths()
    z = src.read(1, window=win, masked=True, boundless=True, fill_value=0)
    tf = src.window_transform(win)
    crown = (z.filled(0) > 0)
    if not crown.any():
        return sa.Trees(shapely.Polygon(), covered=False, source="canopy map (Metro 2019), no crown within 500 ft,")
    near = lot_geom.buffer(CANOPY_PAD_FT)
    polys = [shapely.geometry.shape(g) for g, v in shapes(crown.astype(np.uint8), mask=crown, transform=tf) if v]
    canopy = shapely.union_all([q for q in polys if q.intersects(near)]) if polys else shapely.Polygon()
    return sa.Trees(canopy.intersection(near) if not canopy.is_empty else canopy, source="canopy map (Metro 2019)")


def _one(row: dict[str, Any], picked: dict[str, Any]) -> list[dict[str, Any]]:
    """The lot once per case."""
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
        site = sa.site_from_drawing(lot.lot_geom, drawing, street, _reader(picked.get("layer_id")))
        cases = _W["cases"]
        if site is None:
            return [{**base, **_case(k, c), "result": "unmeasured", "why": "no drawn building"} for k, c in cases.items()]
        if not street:
            return [{**base, **_case(k, c), "result": "unmeasured", "why": "no street lot line traced"}
                    for k, c in cases.items()]
        site = dataclasses.replace(
            site, street_centre=_W["centre"], trees=_trees(lot.lot_geom) if _W.get("canopy") is not None else None
        )
        terrain = _W.get("terrain")
        grade_of = None
        if terrain is not None:
            # One read of the ground round the lot grades every pad on it
            # (the 45 t's street pad too); the terrain itself where not held.
            surface = terrain.surface(lot.lot_geom.buffer(60.0))

            def grade_of(poly: Any) -> float | None:
                g = surface.grade([poly]) if surface is not None else None
                if g is None:
                    g = terrain.grade([poly])
                return None if g is None else g.pct

        out = []
        for k, c in cases.items():
            t1 = time.time()
            rep = sa.report(site, c[2], grade_of=grade_of)
            out.append({**base, **_case(k, c), **rep.row(), "seconds": round(time.time() - t1, 2)})
        return out
    except Exception as exc:  # noqa: BLE001 -- one bad lot is reported, not fatal
        why = f"{type(exc).__name__}: {exc}"
        return [{**base, **_case(k, c), "result": "error", "why": why} for k, c in _W.get("cases", {}).items()] or [
            {**base, "result": "error", "why": why, "seconds": round(time.time() - t0, 2)}
        ]


def _reader(layer: Any) -> Any:
    """The lot's street reading (its jurisdiction sets the estimate's
    allowance); None where no street data is held."""
    from flats.fit import fire
    from flats.geom import street_width

    widths = _W.get("widths")
    if widths is None:
        return _W.get("reader")
    return street_width.reader(widths, _W["lines"], fire.MAX_GAP_FT, str(layer) if layer else None,
                               tree=_W["line_tree"])


def _case(key: str, case: tuple[str, str, Any]) -> dict[str, Any]:
    combo, gear, rules = case
    lb = round(rules.ic80.wall_rigging_lb)
    return {
        "case": key, "case_label": f"{_COMBO_WORDS[combo]}, {gear} gear ({lb} lb)", "carry": combo, "gear": gear,
        "wall_rigging_lb": lb,
    }


def _work(batch: list[tuple[dict[str, Any], dict[str, Any]]]) -> list[dict[str, Any]]:
    return [row for r, p in batch for row in _one(r, p)]


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
    "45 t in the street (width estimated)",
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
#: The gear comparison's rows: the ladder's answers, one face taken together.
_GROUPS = ("IC-80 one face", "IC-80 both faces", "45 t on site", "45 t in the street",
           "45 t in the street (width estimated)", "not viable", "unmeasured")


def _group(result: Any) -> str:
    r = str(result)
    return "IC-80 one face" if r.startswith("IC-80 one face") else r


def _table(counter: collections.Counter, head: str) -> list[str]:
    out = [f"| {head} | lots |", "|---|---|"]
    out += [f"| {k} | {v:,} |" for k, v in counter.most_common()]
    return out


def _key(r: dict[str, Any]) -> Any:
    return r.get("case") or r.get("gear")


def _summary(rows: list[dict[str, Any]], meta: dict[str, Any], args: argparse.Namespace, seconds: float) -> str:
    from flats.fit.set_access import NOT_CHECKED

    gears = list(dict.fromkeys(_key(r) for r in rows))
    lots = len({r.get("TLID") for r in rows}) if gears != [None] else len(rows)
    lines = [
        "# Set access sample (FOLLOWUPS 145, report only)",
        "",
        f"Run: `{args.run}` (law on {meta.get('law_on')}); colour `{args.colour}`; "
        f"{lots:,} lots in {seconds / 60:.1f} min.",
        "",
        "Street widths: measured from "
        + (", ".join(f"`{w}`" for w in meta.get("widths") or ()) or "NO width snapshot (--widths not passed)")
        + (f"; estimated off the taxlot fabric `{meta['fabric']}`." if meta.get("fabric") else "; no estimate."),
        "",
        "Not checked on any lot: " + ", ".join(NOT_CHECKED) + ".",
        "",
    ]
    if gears == [None]:
        return "\n".join(lines + _body(rows, "##")) + "\n"
    by_gear = {g: [r for r in rows if _key(r) == g] for g in gears}
    lb = {g: next((r.get("wall_rigging_lb") for r in by_gear[g] if r.get("wall_rigging_lb") is not None), None)
          for g in gears}
    names = [
        next((r["case_label"] for r in by_gear[g] if r.get("case_label")), None)
        or (f"{g} gear ({lb[g]} lb)" if lb[g] is not None else f"{g} gear")
        for g in gears
    ]
    counts = {g: collections.Counter(_group(r.get("result")) for r in by_gear[g]) for g in gears}
    # The answer with the trees left out, where the canopy was read.
    treed = [g for g in gears if any(r.get("result_no_trees") for r in by_gear[g])]
    bare = {g: collections.Counter(_group(r.get("result_no_trees") or r.get("result")) for r in by_gear[g])
            for g in treed}
    cols = [(g, n, counts[g]) for g, n in zip(gears, names)] + [
        (g, f"{n}, no trees", bare[g]) for g, n in zip(gears, names) if g in treed
    ]
    extra = [k for _, _, c in cols for k in c if k not in _GROUPS]
    lines += [
        "## Lots on each result, by case",
        "",
        "Carry (slice 4b): spec = cassettes carried flat and crosswise, walls upright (S3e 3.7); relaxed = "
        "walls may also be carried flat (FOLLOWUPS 215 a). Wall-lifting gear (spec 3.6): light = one face is enough; heavy = the far walls need "
        "both faces. \"no trees\" = the same lots with the canopy left out (what the trees cost).",
        "",
        "| result | " + " | ".join(n for _, n, _ in cols) + " |",
        "|---|" + "---|" * len(cols),
        *(f"| {k} | " + " | ".join(f"{c[k]:,}" for _, _, c in cols) + " |" for k in (*_GROUPS, *dict.fromkeys(extra))),
        "| total | " + " | ".join(f"{len(by_gear[g]):,}" for g, _, _ in cols) + " |",
        "",
    ]
    if len(gears) >= 2:
        a, b = gears[0], gears[1]
        res_b = {r.get("TLID"): _group(r.get("result")) for r in by_gear[b]}
        moves = collections.Counter(
            f"{_group(r.get('result'))} -> {res_b[r.get('TLID')]}"
            for r in by_gear[a]
            if r.get("TLID") in res_b and _group(r.get("result")) != res_b[r.get("TLID")]
        )
        lines += [f"## Lots whose answer moves from {a} to {b}", ""]
        lines += _table(moves, f"{a} -> {b}") if moves else ["(none)"]
        lines.append("")
    stacks = collections.Counter(
        f"{_key(r)}: {r.get('stack')}" for r in rows if str(r.get("result")).startswith("IC-80") and r.get("stack")
    )
    lines += ["## Wall-load stacking order (lots the IC-80 sets)", ""]
    lines += _table(stacks, "gear: stack") if stacks else ["(none)"]
    lines.append("")
    for g, name in zip(gears, names):
        lines += [f"## {name[0].upper()}{name[1:]}", ""]
        lines += _body(by_gear[g], "###")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def _body(rows: list[dict[str, Any]], h: str) -> list[str]:
    table = _table

    def works(r: dict[str, Any]) -> bool:
        return str(r.get("result") or "").startswith(_WORKS)

    seen = {r.get("result") for r in rows}
    # The long-face columns only where a lot's front could not be told.
    cols = [c for c in RESULTS if "long face" not in c or c in seen]
    lines = [
        f"{h} Result",
        "",
        *table(collections.Counter(str(r.get("result")) for r in rows), "result"),
        "",
        f"{h} By jurisdiction",
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
        f"{h} How the IC-80 works (lots it sets): where the trailer stands, and whether pieces are carried",
        "",
        *(table(ways, "trailer") if (ways := collections.Counter(
            str(r.get("ic80_way")) for r in rows if str(r.get("result") or "").startswith("IC-80"))) else ["(none)"]),
        "",
        f"{h} What the trees cost (answer with the canopy -> without it)",
        "",
        *(table(cost, "with trees -> without") if (cost := collections.Counter(
            f"{r.get('result')} -> {r.get('result_no_trees')}" for r in rows
            if r.get("result_no_trees") and r.get("result_no_trees") != r.get("result"))) else ["(none)"]),
        "",
        f"{h} Where the 45 t's street set-up read its width (lots the step was tried on)",
        "",
        *(table(srcs, "45t_street status: width") if (srcs := collections.Counter(
            f"{r.get('45t_street')}: {r.get('45t_street_width') or 'no pad'}" for r in rows
            if r.get("45t_street") and r.get("45t_street") != "not tried")) else ["(none)"]),
        "",
        f"{h} Failing checks of each IC-80 step (every lot; a lot counts once per check)",
        "",
        *_checks(rows),
        "",
        f"{h} Binding check and hardest lift (lots where a crane works)",
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
        f"{h} Commonest reasons (every step before the answer)",
        "",
    ]
    why: collections.Counter = collections.Counter()
    for r in rows:
        for w in str(r.get("why") or "").split("; "):
            if w:
                why[_generic(w)] += 1
    lines += table(why, "reason") if why else ["(none)"]
    return lines


def _checks(rows: list[dict[str, Any]]) -> list[str]:
    steps = ("ic80_front", "ic80_back", "ic80_both")
    got = {s: collections.Counter(c for r in rows for c in str(r.get(f"{s}_checks") or "").split(", ") if c)
           for s in steps}
    names = sorted({c for s in steps for c in got[s]}, key=lambda c: -sum(got[s][c] for s in steps))
    if not names:
        return ["(none)"]
    return [
        "| check | " + " | ".join(steps) + " |",
        "|---|" + "---|" * len(steps),
        *(f"| {c} | " + " | ".join(f"{got[s][c]:,}" for s in steps) + " |" for c in names),
    ]


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
    parser.add_argument(
        "--gear", default="light", choices=["both", "light", "heavy"],
        help="the wall-gear case(s): light 400 lb, heavy 800 lb (ic80.wall_gear_lb); default light",
    )
    parser.add_argument(
        "--combos", default="spec,relaxed",
        help="the carry cases, comma-separated, of " + ", ".join(COMBOS) + " (default spec,relaxed)",
    )
    parser.add_argument("--walls-flat", action="store_true",
                        help="run the relaxed carry case alone: walls may be carried flat and crosswise")
    parser.add_argument("--canopy", type=Path, default=None,
                        help="a GeoTIFF of Metro's Canopy 2019 (EPSG:2913): trees in the IC-80's way")
    for key in ("s4", "s5o", "roads", "curbs", "dem"):
        parser.add_argument(f"--{key}", type=Path, default=None, help=f"override meta.json's {key}")
    parser.add_argument("--widths", type=Path, action="append", default=None,
                        help="another acquire snapshot holding pavement-width datasets (repeatable)")
    parser.add_argument("--fabric", type=Path, default=None,
                        help="the whole taxlot file for the width estimate (default: s1_lots.parquet beside s4)")
    parser.add_argument("--no-estimate", dest="estimate", action="store_false",
                        help="no width estimate off the right-of-way")
    args = parser.parse_args(argv)
    gears = ("light", "heavy") if args.gear == "both" else (args.gear,)
    if args.walls_flat:
        combos: tuple[str, ...] = ("relaxed",)
    else:
        combos = tuple(c.strip() for c in args.combos.split(",") if c.strip())
    bad = [c for c in combos if c not in COMBOS]
    if bad:
        parser.error(f"unknown carry case(s): {', '.join(bad)}")
    canopy = str(args.canopy) if args.canopy else None
    if canopy and not Path(canopy).exists():
        parser.error(f"no canopy file: {canopy}")
    n_cases = len(gears) * len(combos)

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
    meta["widths"] = [str(w) for w in (args.widths or ())]
    for w in meta["widths"]:
        if not Path(w).is_dir():
            parser.error(f"no widths snapshot: {w}")
    fabric = args.fabric or Path(meta["s4"]).parent / "s1_lots.parquet"
    meta["fabric"] = str(fabric) if args.estimate and fabric.exists() else None
    if args.estimate and not meta["fabric"]:
        print(f"set access: no taxlot fabric at {fabric} -- no street width is estimated")

    import pyarrow.parquet as pq

    want = ["TLID", "jurisdiction", "zone", "colour", "drawing", "layer_id"]
    have = set(pq.read_schema(args.run / "lots.parquet").names)
    lots = pd.read_parquet(args.run / "lots.parquet", columns=[c for c in want if c in have])
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
        with ProcessPoolExecutor(
            args.processes, initializer=_init, initargs=(meta, args.grade, gears, combos, canopy)
        ) as pool:
            for got in pool.map(_work, batches):
                out_rows.extend(got)
                print(f"set access: {len(out_rows) // n_cases:,}/{len(pairs):,}", flush=True)
    else:
        _init(meta, args.grade, gears, combos, canopy)
        for i, pair in enumerate(pairs, 1):
            out_rows.extend(_one(*pair))
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
