"""FD2 pass 1, stage B: the smallest-relief workable position on each green lot.

Report only. The FD2 hand-off asks, where a lot has more than one workable
position, for the one with the smallest ground relief under the 80 x 25 ft
footprint. "Workable" is read as the flatter step's own test
(:mod:`flats.ingest.flatter`): a spot from the fit's listing, at the fit's
angle or another the fitter holds, whose drive in from the street is clear,
which stands within any stated maximum front setback, and on which the whole
screen, run again from the start with the building pinned there, comes back
no worse -- no colour, failed check or flag the live position did not have
(:func:`flats.ingest.flatter._no_worse`) -- and with the building still where
it was pinned.

How: the bridge (:func:`flats.ingest.quadfit.run`) screens the green lots
with two things swapped in each worker (:func:`init_patched`):

* ``flatter_checked`` runs as live, then (first pass) lists every spot and
  ranks it by relief, or (pinned pass) stands the plan on one listed spot;
* ``_work_chunk`` screens each lot once as live, then once per candidate
  (at most :data:`VERIFY_MAX`, flattest first, each at least
  :data:`GAIN_FT` flatter than the live spot), and keeps the first that
  passes.

One JSON line per lot goes to ``<out>/stageB/<pid>.jsonl``. Nothing here is
written anywhere the live map reads.

Where the flatter step itself does not search (the 10 m model, a court not
reached down a lane from the street, a tight or lane-less drawing), this
writes ``not searched`` and why.

Run (on 137, under the heavy lock)::

    PYTHONPATH=<tree>:<tree>/scripts python scripts/flats_fd2_alt.py \\
        --greens /root/fd2_pass1/greens.txt --meta /root/bridge_spliced_rel9_fr/meta.json \\
        --out /root/fd2_pass1 --processes 12
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
import time
from pathlib import Path
from typing import Any

from flats.ingest import flatter as fl
from flats.ingest import fd2
from flats.ingest import quadfit as q

#: Candidates put through the whole screen again, flattest first.
VERIFY_MAX = 3
#: A spot is a candidate only if its relief is lower than the live spot's by this.
GAIN_FT = 0.5

_ORIG_INIT = q._init_worker
_ORIG_FLATTER = q.flatter_checked
_ST: dict[str, Any] = {}


def _ring_key(drawing: dict[str, Any] | None) -> tuple[tuple[float, float], ...] | None:
    ring = (drawing or {}).get("building")
    if not ring:
        return None
    return tuple((round(float(x), 1), round(float(y), 1)) for x, y in ring)


def _relief(ring: Any, streets: Any, z_of: Any) -> float | None:
    try:
        got = fd2.ground_shape(fd2.frame(ring, streets), z_of)
    except ValueError:
        return None
    return got.get("relief_ft")


def _search(s1: Any, lot: Any, terrain: Any, fitter: Any) -> dict[str, Any]:
    """Every listed spot ranked by relief, or why none was searched."""
    import flats_fd2_pass1 as p1

    out: dict[str, Any] = {"searched": False}
    if terrain is None or fitter is None or s1.facts is None or lot.lot_geom is None:
        out["why"] = "no terrain, fitter or lot shape"
        return out
    if s1.facts.outdoor_square_ft is not None:
        out["why"] = "plan measured on an outdoor square"
        return out
    drawing = s1.drawing or {}
    if not (drawing.get("fits") and not drawing.get("tight") and drawing.get("lane")):
        out["why"] = "drawing tight or without a lane"
        return out
    if not fl._lane_in_from_street(s1):
        out["why"] = "court not reached down a lane from the street (alley, side street, beside or column)"
        return out
    street = q._street_lines(lot)
    if not street:
        out["why"] = "no street line"
        return out
    z_of, source, _cell = p1._z_reader(terrain, lot.lot_geom)
    if z_of is None or source != "dem_1m":
        out["why"] = "10 m ground" if source else "no elevation"
        return out
    streets = tuple(dict.fromkeys(street + q._side_street_lines(lot)))
    base = _relief(drawing["building"], streets, z_of)
    if base is None:
        out["why"] = "no ground under the live spot"
        return out
    cap = fl._max_front_ft(s1, street)
    ranked: list[tuple[float, float, Any, Any]] = []
    listed = 0
    per = fl.RANKED_MAX // fl.ANGLES_MAX
    for angle in fl._angles(s1, fitter):
        at = dataclasses.replace(s1, fit=dataclasses.replace(s1.fit, angle_deg=angle))
        listing: list[Any] = []
        q.drawing_for(at, fitter, listing=listing, max_front_ft=cap)
        if len(listing) > per:
            step = (len(listing) - 1) / (per - 1)
            listing = [listing[round(i * step)] for i in range(per)]
        for where in listing:
            drawn = q.drawing_for(at, fitter, where=where)
            if not drawn or not drawn.get("fits") or not drawn.get("building"):
                continue
            listed += 1
            r = _relief(drawn["building"], streets, z_of)
            if r is not None and r <= base - GAIN_FT:
                ranked.append((r, angle, at, drawn))
    ranked.sort(key=lambda t: (t[0], t[1]))
    from flats.ingest import wall_openings as wo

    # A spot whose walls stand nearer a side or rear line than the
    # no-openings floor is moved by the wall-openings step, so it is not
    # put up as a candidate (the pinned re-screen would reject it anyway).
    floor = wo._applies(s1)
    edges = getattr(lot, "edges", None)
    keep = []
    lines = None
    for r, angle, at, drawn in ranked:
        if len(keep) >= VERIFY_MAX:
            break
        if floor is not None and edges is not None:
            gap = wo.gap_ft(drawn["building"], edges.edges, wo._street_edges(s1))
            if gap is not None and gap < floor:
                continue
        if not fl._drive_clear(drawn, at, street):
            continue
        if cap is not None:
            from shapely.geometry import MultiLineString
            lines = lines or MultiLineString([[(x1, y1), (x2, y2)] for x1, y1, x2, y2 in street])
            b = fl._ring(drawn, "building")
            if b is None or b.distance(lines) > cap + fl.FRONT_TOL_FT:
                continue
        keep.append({"relief": r, "angle": angle, "at": at, "drawn": drawn})
    out.update({"searched": True, "base_relief": base, "listed": listed, "flatter_by_gain": len(ranked),
                "candidates": keep})
    return out


def _pinned(s1: Any, at: Any, drawn: Any, lot: Any, terrain: Any, *, rules: Any, policy: Any, relief: Any,
            step_deg: float, roads: Any) -> Any:
    """``s1`` stood on ``drawn``, through the flatter step's own re-check."""
    facts = dataclasses.replace(
        s1.facts, fire_route_ft=None, fire_route_tried=False, fire_route_curb_ft=None,
        fire_route_freed_ft=None, fire_route_row_ft=None, site_grade_pct=None, site_grade_source=None,
        site_grade_tried=False,
    )
    if facts.front_max_tried:
        facts = dataclasses.replace(facts, front_max_streets=q.front_max_streets(dataclasses.replace(at, drawing=drawn)))
    result = q.screen(s1.rules, facts, s1.design, s1.fit, policy=policy, relief=relief, config=s1.config)
    shadow = q._if_signed(s1.rules, facts, s1.design, s1.fit, result, policy=policy, relief=relief, config=s1.config)
    cand = dataclasses.replace(at, fit=s1.fit, drawing=drawn, facts=facts, screening=result, signed=shadow)
    cand = q.fire_checked(cand, lot, roads, policy=policy, relief=relief, fitter=None)
    cand = q.slope_checked(cand, lot, terrain, rules=rules, policy=policy, relief=relief, step_deg=step_deg,
                           roads=roads)
    return dataclasses.replace(cand, room=s1.room)


def flatter_patched(s: Any, lot: Any, terrain: Any, fitter: Any, *, rules: Any, policy: Any, relief: Any,
                    step_deg: float, roads: Any) -> Any:
    s1 = _ORIG_FLATTER(s, lot, terrain, fitter, rules=rules, policy=policy, relief=relief, step_deg=step_deg,
                       roads=roads)
    key = (s1.design.key, _ring_key(s1.drawing))
    mode = _ST.get("mode")
    if mode == "list":
        if key not in _ST["calls"]:
            try:
                _ST["calls"][key] = _search(s1, lot, terrain, fitter)
            except Exception as exc:  # noqa: BLE001 -- a lot's search failing is reported, not fatal
                _ST["calls"][key] = {"searched": False, "why": f"search error {exc!r}"[:160]}
        return s1
    # Every pass of the chain that reaches the live spot (the screen runs it
    # again for other forms and lanes) is stood on the candidate.
    if mode == "pin" and key == _ST["pin_key"]:
        c = _ST["pin"]
        _ST["pinned"] = True
        _ST["pins"] = _ST.get("pins", 0) + 1
        return _pinned(s1, c["at"], c["drawn"], lot, terrain, rules=rules, policy=policy, relief=relief,
                       step_deg=step_deg, roads=roads)
    return s1


def _screen(lot: Any, designs: Any) -> list[Any]:
    W = q._WORKER
    return list(q.screen_lot(lot, designs, rules=W["rules"], policy=W["policy"], relief=W["relief"],
                             step_deg=W["step_deg"], roads=W.get("roads"), terrain=W.get("terrain")))


def _green(results: list[Any]) -> Any:
    for s in results:
        if s.signed.colour.value == "green":  # the map colour (row_for "colour")
            return s
    return None


def work_patched(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    W = q._WORKER
    out: list[dict[str, Any]] = []
    for row in rows:
        t0 = time.time()
        lot = q.lot_from_row(row, W["rules"].layers, W["corridors"])
        lot = q.with_steep(lot, W.get("terrain"))
        _ST.clear()
        _ST.update({"mode": "list", "calls": {}})
        base = _screen(lot, W["designs"])
        _ST["mode"] = None
        out.extend(q.row_for(s) for s in base)
        rec: dict[str, Any] = {"TLID": lot.tlid}
        win = _green(base)
        if win is None:
            rec.update({"alt_status": "not searched", "alt_why": "not green in this re-screen",
                        "colour_now": base[0].signed.colour.value if base else None})
        else:
            key = (win.design.key, _ring_key(win.drawing))
            rec.update({"design": win.design.key, "live_ring": json.dumps((win.drawing or {}).get("building"))})
            got = _ST["calls"].get(key)
            if got is None:
                rec.update({"alt_status": "not searched",
                            "alt_why": "position set after the flatter step (wall openings or a later check)"})
            elif not got.get("searched"):
                rec.update({"alt_status": "not searched", "alt_why": got.get("why")})
            else:
                rec.update({"alt_status": "searched", "base_relief_ft": got["base_relief"],
                            "listed": got["listed"], "flatter_by_gain": got["flatter_by_gain"],
                            "candidates": len(got["candidates"]), "tried": 0, "rejects": []})
                for c in got["candidates"]:
                    rec["tried"] += 1
                    _ST.clear()
                    _ST.update({"mode": "pin", "pin_key": key, "pin": c, "pinned": False})
                    again = _screen(lot, [win.design])
                    pinned = bool(_ST.get("pinned"))
                    c["pins"] = _ST.get("pins", 0)
                    _ST.clear()
                    fin = next((s for s in again if s.design.key == win.design.key), None)
                    if not _accept(fin, c, win, rec, pinned):
                        continue
                    rec.update({"alt_relief_ft": c["relief"], "alt_angle_deg": c["angle"],
                                "alt_ring": json.dumps(c["drawn"].get("building")), "differs": True})
                    break
                else:
                    rec.update({"alt_relief_ft": got["base_relief"], "differs": False})
        rec["seconds"] = round(time.time() - t0, 2)
        with open(Path(os.environ["FD2_ALT_OUT"]) / f"{os.getpid()}.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
    return out


def _accept(fin: Any, c: dict[str, Any], win: Any, rec: dict[str, Any], pinned: bool) -> bool:
    if not pinned:
        rec["rejects"].append("pin not applied")
        return False
    if fin is None:
        rec["rejects"].append("design gone")
        return False
    if _ring_key(fin.drawing) != _ring_key(c["drawn"]):
        where = "live spot" if _ring_key(fin.drawing) == _ring_key(win.drawing) else "another spot"
        rec["rejects"].append(f"moved after pinning to {where} ({c.get('pins')} passes pinned,"
                              f" colour {fin.signed.colour.value})")
        return False
    if not fl._no_worse(win, fin):
        rec["rejects"].append("worse: " + ",".join(sorted(
            ({x.check for x in fin.signed.binds} - {x.check for x in win.signed.binds})
            | ({f.code for f in fin.signed.flags} - {f.code for f in win.signed.flags})
            | ({x.check for x in fin.screening.binds} - {x.check for x in win.screening.binds})
            | ({f.code for f in fin.screening.flags} - {f.code for f in win.screening.flags})))[:120]
            + f" colour {fin.signed.triage.value}")
        return False
    return True


def init_patched(*initargs: Any) -> None:
    """The bridge worker's own set-up, then the two swaps above."""
    _ORIG_INIT(*initargs)
    q.flatter_checked = flatter_patched
    q._work_chunk = work_patched


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--greens", required=True, help="one TLID per line")
    p.add_argument("--meta", required=True, help="the live bridge's meta.json")
    p.add_argument("--out", required=True)
    p.add_argument("--processes", type=int, default=12)
    p.add_argument("--limit", type=int, default=0)
    a = p.parse_args(argv)
    meta = json.loads(Path(a.meta).read_text(encoding="utf-8"))
    tlids = [ln.strip() for ln in Path(a.greens).read_text(encoding="utf-8").splitlines() if ln.strip()]
    if a.limit:
        tlids = tlids[: a.limit]
    out = Path(a.out)
    alt = out / "stageB"
    alt.mkdir(parents=True, exist_ok=True)
    for old in alt.glob("*.jsonl"):
        old.unlink()
    os.environ["FD2_ALT_OUT"] = str(alt)  # inherited by the forkserver's workers
    # The live run's law day, not today's.
    import flats.rules.loader as loader
    on = dt.date.fromisoformat(meta["law_on"])
    loader.law_on = lambda *_a, **_k: on
    # By reference from the importable module, not __main__, so the
    # forkserver's workers find it (scripts/ on PYTHONPATH).
    import flats_fd2_alt as me
    q._init_worker = me.init_patched

    def opt(k: str) -> Path | None:
        return Path(meta[k]) if meta.get(k) else None

    t0 = time.time()
    q.run(out / "stageB_bridge", s4=Path(meta["s4"]), s5o=Path(meta["s5o"]), results=None,
          processes=a.processes, tlids=tlids, step_deg=float(meta["step_deg"]), sources=opt("sources"),
          transit=opt("transit"), roads=opt("roads"), dem=opt("dem"), curbs=opt("curbs"),
          institutional=opt("institutional"), cache=None, plats=opt("plats"), fabric=opt("fabric"))
    print(json.dumps({"lots": len(tlids), "seconds": round(time.time() - t0, 1)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
