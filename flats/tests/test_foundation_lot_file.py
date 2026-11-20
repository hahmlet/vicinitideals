"""FD6 foundation model: per-lot cross-check against the reference model on the
whole lot file.

SKIPPED unless both the lot file (``fd2_lots.csv``, which is in no repo) and the
FD6 reference model (``FD6_foundation_model.py`` in the read-only Factory-Sim
research folder) are on this machine. Override the paths with ``FLATS_FD_LOTS``
and ``FD6_REFERENCE_DIR``. Nothing is written: the lot file is read in place and
the reference is imported without writing bytecode.

Two comparisons, per lot, of tallest wall, risers at all eight doors, and cost
low and high for A dry, A wet and B:

* with ``tolerance_in = 0`` (raw float comparisons, as the reference) and
* with the shipped ``tolerance_in`` (1e-6 in, so float noise never flips a
  threshold),

the only results that differ are on lots sitting exactly on a threshold -- a
door exactly 30 in above its landing, a riser count exactly on a 7.75 in
multiple (lot-file readings are to 0.01 ft, so exact ties are common) -- where
float noise in one model or the other decides. Every differing result is
checked to be on such a tie, and the count and size are bounded.
"""

from __future__ import annotations

import csv
import importlib.util
import os
import sys
from pathlib import Path

import pytest

from flats.foundation import lot, settings

LOTS = Path(os.environ.get("FLATS_FD_LOTS", r"C:\Users\Steph\Repos\vicinitideals-worktrees\fd2-pass1-data\fd2_lots.csv"))
REF_DIR = Path(os.environ.get("FD6_REFERENCE_DIR", r"C:\Users\Steph\Repos\Factory-Sim\docs\research"))
REF = REF_DIR / "FD6_foundation_model.py"

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not (LOTS.is_file() and REF.is_file()), reason="lot file or FD6 reference model not on this machine"),
]

METHODS = ("B", "A dry", "A wet")


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


@pytest.fixture(scope="module")
def compared() -> dict[str, object]:
    ref = _reference()
    p = ref.Params()
    s = settings.load()
    s0 = s.replace(tolerance_in=0.0)
    with LOTS.open(newline="", encoding="utf-8") as fh:
        lot_rows = list(csv.DictReader(fh))
    out: dict[str, object] = {"lots": 0, "missing_mismatch": [], "diff0": [], "diff": []}
    for row in lot_rows:
        g = ref.lot_ground(row)
        m = lot.measure_row(row, s)
        if (g is None) != (m is None):
            out["missing_mismatch"].append(row["TLID"])  # type: ignore[union-attr]
            continue
        if m is None:
            continue
        out["lots"] += 1  # type: ignore[operator]
        ground, lump = g
        theirs = {"B": ref.raised(ground, p, lump), "A dry": ref.slab(ground, p, lump), "A wet": ref.slab(ground, p, lump, wet=True)}
        for key, st in (("diff0", s0), ("diff", s)):
            mine = lot.assess(m, st)
            for name in METHODS:
                a, b = mine[name], theirs[name]
                d = (
                    abs(a.tallest_wall_in - b.wall_max_in),
                    abs(a.risers_total - sum(b.risers)),
                    abs(float(a.cost.low) - b.cost[0]),
                    abs(float(a.cost.high) - b.cost[1]),
                )
                if max(d) > 1e-6:
                    out[key].append((row["TLID"], name, d))  # type: ignore[union-attr]
                    if not _on_a_tie(a, s):
                        out.setdefault("untied_" + key, []).append((row["TLID"], name))  # type: ignore[union-attr]
    out.setdefault("untied_diff0", [])
    out.setdefault("untied_diff", [])
    return out


def _on_a_tie(r, s: settings.Settings, eps: float = 1e-6) -> bool:
    """A door, or the tallest wall, exactly on a threshold, where float noise decides."""
    for d in r.doors:
        step = (d.height_in - s.landing_drop_in) / s.riser_in
        if abs(d.height_in - s.landing_drop_in - s.guard_over_in) < eps or abs(step - round(step)) < eps:
            return True
    return any(abs(r.tallest_wall_in - t) < eps for t in (s.level_bar_third_over_in, s.level_bar_fourth_over_in))


def test_every_lot_the_reference_models_is_modelled(compared) -> None:
    assert compared["missing_mismatch"] == []
    assert compared["lots"] > 9000


@pytest.mark.parametrize("key", ["diff0", "diff"])
def test_only_exact_threshold_ties_differ_from_the_reference(compared, key) -> None:
    diffs = compared[key]
    worst = [max(d[2][i] for d in diffs) if diffs else 0.0 for i in range(4)]
    print(f"\n[{key}] {len(diffs)} method results differ on {compared['lots']} lots; largest wall {worst[0]:.2e} in, "
          f"risers {worst[1]:.0f}, cost low ${worst[2]:.2f}, high ${worst[3]:.2f}; not on a tie: {compared['untied_' + key]}")
    assert worst[0] < 1e-9, "a tie never moves a wall"
    assert worst[1] <= 2
    assert worst[2] <= 300 and worst[3] <= 1500  # two 8.5 ft guard rails, or two risers
    assert len(diffs) <= 0.005 * 3 * compared["lots"]
    assert compared["untied_" + key] == []
