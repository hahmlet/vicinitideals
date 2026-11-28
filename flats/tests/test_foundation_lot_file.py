"""FD6 foundation model: per-lot cross-check against the reference model on the
whole lot file.

SKIPPED unless both the lot file (``fd2_lots.csv``, which is in no repo) and the
FD6 reference model (``FD6_foundation_model.py`` in the read-only Factory-Sim
research folder) are on this machine. Override the paths with ``FLATS_FD_LOTS``
and ``FD6_REFERENCE_DIR``. Nothing is written: the lot file is read in place and
the reference is imported without writing bytecode.

The reference is the one re-issued for FD8 version 3 and FD9 (precast units,
the six-step cap, the ground at each unit's foot, the guard box, the stepped
footing). It no longer carries ``as_flats_built``, so this file compares the
production settings (``settings.load()``, one ``embed_in`` footing depth on every
lot as the reference: ``use_frost_register`` off) with its ``Params()`` -- the
pairing :func:`flats.tests.test_foundation_fd8.test_fd9_the_eleven_test_lots_door_by_door`
matches door by door on the eleven test lots (2026-11-21, replacing the
per-riser ``as_flats_built`` check).

Per lot, for B, A dry and A wet: the tallest wall, every door's unit risers,
railing sides and guard, over the cap, cost low and high; and the lot's cap
state, best method and margin on the ordinary-footing methods. Two runs:

* At the reference's own tolerance (0.01 in on every "over" test) every wall,
  door and cap state agrees on every lot. Cost differs only where a wall or a
  slab edge sits within that tolerance of a level-bar or upright threshold,
  which the reference tests with a bare ``>`` and FLATS with its tolerance;
  every such lot is checked to be on that tie.
* At the shipped tolerance (1e-6 in, so float noise never adds a riser) a
  result differs from the reference only on a lot with a door within 0.01 in
  of a step-pad, riser, guard or cap-band threshold (at the wall or at the
  foot of a unit either model tried), or a wall line within 0.01 in of a bar
  threshold or of a one-step fall: the reference's tolerance decides those
  (lot-file readings are to 0.01 ft, so near-ties are common). The count is
  bounded.
"""

from __future__ import annotations

import csv
import importlib.util
import os
import sys
from pathlib import Path

import pytest

from flats.foundation import cap as caps
from flats.foundation import lot, settings, support

LOTS = Path(os.environ.get("FLATS_FD_LOTS", r"C:\Users\Steph\Repos\vicinitideals-worktrees\fd2-pass1-data\fd2_lots.csv"))
REF_DIR = Path(os.environ.get("FD6_REFERENCE_DIR", r"C:\Users\Steph\Repos\Factory-Sim\docs\research"))
REF = REF_DIR / "FD6_foundation_model.py"

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not (LOTS.is_file() and REF.is_file()), reason="lot file or FD6 reference model not on this machine"),
]

#: FLATS method -> the reference's name for it.
METHODS = {"B": "B", "A dry": "A", "A wet": "A wet"}


def _reference():
    name = "_fd6_reference_model"
    if name in sys.modules:
        return sys.modules[name]
    before, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    sys.path.insert(0, str(REF_DIR))
    try:
        spec = importlib.util.spec_from_file_location(name, REF)
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        sys.modules[name] = mod
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    finally:
        sys.path.remove(str(REF_DIR))
        sys.dont_write_bytecode = before
    return mod


def _theirs(ref, row, p) -> dict[str, object] | None:
    got = ref.lot_ground(row, p)
    if got is None:
        return None
    ground, lump = got
    r = {"B": ref.raised(ground, p, lump), "A": ref.slab(ground, p, lump), "A wet": ref.slab(ground, p, lump, wet=True)}
    state, best, over_by = ref.cap_state(r, ref.OPEN["ordinary footing"], p)
    return {"ground": ground, "lump": lump, "methods": r, "cap": (state, best, over_by)}


def _mine(row, s: settings.Settings) -> dict[str, object] | None:
    m = lot.measure_row(row, s)
    if m is None:
        return None
    r = lot.assess(m, s)
    c = caps.cap_of({"A dry": r["A dry"], "B": r["B"]}, support.ORDINARY, s)
    return {"methods": r.methods, "cap": (c.state, c.best, c.over_by_in)}


def _key(mine, theirs) -> dict[str, tuple]:
    """What is compared, per part: ``walls+doors`` (no money) and ``cost``."""
    out: dict[str, tuple] = {}
    for name, rname in METHODS.items():
        a, b = mine["methods"][name], theirs["methods"][rname]
        out[f"{name} walls+doors"] = (
            round(a.tallest_wall_in, 6) - round(b.wall_max_in, 6),
            tuple(d.units for d in a.doors) == tuple(d.units for d in b.doors),
            tuple(d.rail_sides for d in a.doors) == tuple(d.sides for d in b.doors),
            tuple(d.guard for d in a.doors) == tuple(d.guard for d in b.doors),
            a.over_cap == b.over_cap,
        )
        if a.over_cap or b.over_cap:
            out[f"{name} cost"] = (0.0, 0.0)
        else:
            out[f"{name} cost"] = (abs(float(a.cost.low) - b.cost[0]), abs(float(a.cost.high) - b.cost[1]))
    mstate, mbest, mover = mine["cap"]
    rstate, rbest, rover = theirs["cap"]
    out["cap"] = (_STATE[rstate] == mstate, METHODS[mbest] == rbest, abs(mover - rover) < 1e-6)
    return out


#: The reference's cap states -> FLATS's.
_STATE = {"red": caps.RED, "near the cap: yellow": caps.NEAR, "close under the cap: note": caps.CLOSE, "fits": caps.FITS}


def _agrees(part: str, v: tuple) -> bool:
    if part.endswith("walls+doors"):
        return abs(v[0]) < 1e-6 and all(v[1:])
    if part.endswith("cost"):
        return max(v) <= 0.005
    return all(v)


def _bar_tie(ref, theirs, p, eps: float) -> bool:
    """A wall line or slab edge within ``eps`` of a wall threshold: the level
    bars (5 ft, 8 ft), the plain-wall limit and the uprights in the slab edge,
    which the reference tests with a bare ``>``, and a line falling one footing
    step (8 in), which it tests at its own tolerance."""
    g, high = theirs["ground"], ref.high_low(theirs["ground"], p)[0] + theirs["lump"]
    bars = (p.level_bar_third_over_in, p.level_bar_fourth_over_in, p.plain_wall_max_in)
    b_offset = p.clear_in + p.embed_in - p.footing_t_in
    edge_d = p.embed_in + p.slab_top_in
    for line in ref.wall_lines(p):
        raw = [(high - g(x, y)) * 12 for x, y, _ in ref.stations(line, p.station_ft)]
        if abs(max(raw) - min(raw) - p.footing_step_in) < eps:
            return True  # the stepped footing: a line falling one step, or half a step more wall
        wall = max(ref.stepped(raw, p))
        if any(abs(wall + b_offset - t) < eps for t in bars):
            return True
        if line.kind != "party":
            # the slab is set on the same highest ground, so its drops are the wall's
            if any(abs(wall + edge_d - t) < eps for t in bars) or abs(max(raw) - p.uprights_fill_over_in) < eps:
                return True
    return False


def _near_tie(ref, mine, theirs, p, eps: float) -> bool:
    """A door within ``eps`` of a step-pad, riser, guard or cap-band threshold
    (at the wall or at the foot of a unit either model tried: the reference's
    tested height is the foot it stopped at, FLATS's the next one out), or a
    wall on a bar tie."""
    cap = p.landing_drop_in + p.cap_risers * p.riser_in
    doors = [d for r in mine["methods"].values() for d in r.doors]
    doors += [d for r in theirs["methods"].values() for d in r.doors]
    for d in doors:
        for h in (d.height_in, d.cap_height_in):
            if h is None:
                continue
            over = (h - p.landing_drop_in) % p.riser_in
            if min(over, p.riser_in - over) < eps or any(abs(h - t) < eps for t in (cap - p.near_cap_in, cap + p.near_cap_in)):
                return True
        if d.platform_in is not None and abs(d.platform_in - p.guard_over_in) < eps:
            return True
    return _bar_tie(ref, theirs, p, eps)


@pytest.fixture(scope="module")
def compared() -> dict[str, object]:
    ref = _reference()
    p = ref.Params()
    shipped = settings.load().replace(use_frost_register=False)
    at_theirs = shipped.replace(tolerance_in=p.tolerance_in)
    with LOTS.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out: dict[str, list] = {"missing_mismatch": [], "lots": [], "at_theirs": [], "untied_at_theirs": [], "shipped": [],
                            "untied_shipped": []}
    for row in rows:
        theirs = _theirs(ref, row, p)
        mine_t = _mine(row, at_theirs)
        if (theirs is None) != (mine_t is None):
            out["missing_mismatch"].append(row["TLID"])
            continue
        if theirs is None:
            continue
        out["lots"].append(row["TLID"])
        for part, v in _key(mine_t, theirs).items():
            if not _agrees(part, v):
                out["at_theirs"].append((row["TLID"], part, v))
                if not part.endswith("cost") or not _bar_tie(ref, theirs, p, p.tolerance_in):
                    out["untied_at_theirs"].append((row["TLID"], part, v))
        mine_s = _mine(row, shipped)
        for part, v in _key(mine_s, theirs).items():
            if not _agrees(part, v):
                out["shipped"].append((row["TLID"], part, v))
                if not _near_tie(ref, mine_s, theirs, p, p.tolerance_in + 1e-6):
                    out["untied_shipped"].append((row["TLID"], part, v))
    return out


def test_every_lot_the_reference_models_is_modelled(compared) -> None:
    assert compared["missing_mismatch"] == []
    assert len(compared["lots"]) > 9000


def test_at_the_references_tolerance_only_bar_ties_differ(compared) -> None:
    diffs = compared["at_theirs"]
    print(f"\n[0.01 in] {len(diffs)} results differ on {len(compared['lots'])} lots: {diffs[:6]}")
    # 2026-11-21: 18 results (9 lots, A dry and A wet), $14-$84 low: one level bar
    assert compared["untied_at_theirs"] == [], "every wall, door and cap state agrees; a cost differs only on a bar tie"
    assert all(max(v) <= 150 for _, part, v in diffs), "a tie moves one level bar or a line's uprights, not more"
    assert len(diffs) <= 0.005 * 3 * len(compared["lots"])


def test_at_the_shipped_tolerance_only_near_ties_differ(compared) -> None:
    diffs = compared["shipped"]
    lots = {t for t, _, _ in diffs}
    print(f"\n[shipped] {len(diffs)} results on {len(lots)} of {len(compared['lots'])} lots differ: {diffs[:6]}")
    assert compared["untied_shipped"] == [], "a lot differs only where a door or wall is within 0.01 in of a threshold"
    # 2026-11-21: 701 results on 295 of the 9,514 lots; readings to 0.01 ft put
    # many doors within 0.01 in of a riser step at the wall or at a unit's foot
    assert len(lots) <= 0.05 * len(compared["lots"])
