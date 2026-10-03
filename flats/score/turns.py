"""How much dead end a lane-fed rear court needs for a car to use every stall.

Steph's ruling of 2026-10-02 on FOLLOWUPS 36(2), *"THREE POINT is acceptable
for now"*: a stall counts when a car can get into it and out again without
any trip taking more than four moves (:func:`flats.fit.turning.usable`). The
car and the search are :mod:`flats.fit.turning`; this module asks them about
the courts the screen actually charges.

**What is asked.** The rear court reached by a lane down the building's flank
(:func:`flats.score.paper.court_across` with a lane): one row of the charged
stalls behind the aisle, the row's near end against the lane's outer edge, a
dead end at the far one. Where a car cannot use every stall, the aisle runs on
past the far end of the row -- the dead-end extension a parking designer
draws -- and the court is charged that much wider. The least extension, in
whole feet, that lets the car use every stall is :func:`dead_end_ft`; ``None``
where no extension up to :data:`MAX_DEAD_END_FT` does, and the court cannot be
used at all.

**Why a ledger.** The answer depends only on the court's shape -- stall count,
stall width and depth, aisle, lane, standoff -- and the corpus draws a couple
of dozen of them. One search is seconds to minutes, so they are computed once
(``python -m flats.score.turns``) into ``flats/config/court_turns.json``, and
``flats/tests/test_turns.py`` fails when a rule change brings a shape the
ledger does not hold. A shape missing at run time is computed then and there
(:func:`functools.lru_cache`), slow but never wrong.

**Which way a "no" errs.** A path the search finds is real; a path it misses
may exist between its lattice cells. Every question is put four ways
(:data:`flats.fit.turning.SEARCHES`) before a "no" counts, and a "no" that
survives charges more width -- a yellow too many, never a green too many.

**What it does not ask.** A court fed from an alley or a side street (no lane:
the street or the alley is the aisle's way out), a court beside the building
(its aisle runs straight to the street), the column along a side alley, and
the seats past the charged floor that the screen reports beside the colour
(:attr:`flats.score.screen.Screening.stalls_seated`).
"""

from __future__ import annotations

import argparse
import json
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

from flats.fit.turning import TURN_FT, Court, usable

LEDGER = Path(__file__).resolve().parents[1] / "config" / "court_turns.json"

#: The longest dead-end extension asked for: past it the court is not
#: usable, whatever the lot.
MAX_DEAD_END_FT = 24


class Shape(NamedTuple):
    """A lane-fed rear court, as far as the car is concerned."""

    stalls: int
    stall_w_ft: float
    stall_d_ft: float
    aisle_ft: float
    lane_ft: float
    gap_ft: float

    @property
    def key(self) -> str:
        return "|".join(f"{v:g}" for v in self)

    def court(self, extra_ft: float = 0.0) -> Court:
        return Court(
            stalls=self.stalls,
            stall_w_ft=self.stall_w_ft,
            stall_d_ft=self.stall_d_ft,
            aisle_ft=self.aisle_ft,
            gap_ft=self.gap_ft,
            lane_ft=self.lane_ft,
            extra_ft=extra_ft,
        )


def every_stall(shape: Shape, extra_ft: float) -> bool:
    """Whether every stall of ``shape`` is usable with the aisle run
    ``extra_ft`` past the row's far end. The far end's stalls first: they
    are the ones the dead end serves, and the first to fail."""
    court = shape.court(extra_ft)
    return all(usable(court, i) for i in reversed(range(shape.stalls)))


def solve(shape: Shape) -> float | None:
    """The least whole-foot extension that lets the car use every stall.

    Ground only grows with the extension, so the answer is searched by
    halving; an extension the lattice happens to miss between two that pass
    can only make the answer larger, the conservative side."""
    if every_stall(shape, 0.0):
        return 0.0
    if not every_stall(shape, float(MAX_DEAD_END_FT)):
        return None
    lo, hi = 0, MAX_DEAD_END_FT
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if every_stall(shape, float(mid)):
            hi = mid
        else:
            lo = mid
    return float(hi)


def _load() -> dict[str, float | None]:
    if not LEDGER.exists():
        return {}
    data = json.loads(LEDGER.read_text(encoding="utf-8"))
    if data.get("turn_ft") != TURN_FT:
        return {}
    return {row["shape"]: row["dead_end_ft"] for row in data["shapes"]}


_LEDGER = _load()


@lru_cache(maxsize=None)
def _computed(shape: Shape) -> float | None:
    return solve(shape)


def dead_end_ft(shape: Shape) -> float | None:
    """The extension ``shape`` needs (see the module docstring)."""
    if shape.key in _LEDGER:
        return _LEDGER[shape.key]
    return _computed(shape)


def corpus_shapes() -> set[Shape]:
    """Every lane-fed court shape the active designs draw in any encoded zone."""
    from flats.designs.model import load_catalog
    from flats.rules.loader import load_rules
    from flats.rules.resolver import RuleSet
    from flats.score.paper import court_shape

    layers = load_rules()
    rules = RuleSet(layers)
    designs = load_catalog().active()
    out: set[Shape] = set()
    for layer_id, layer in sorted(layers.items()):
        for zone in layer.zones:
            try:
                resolved = rules.resolve(layer_id, zone)
            except Exception:  # noqa: BLE001 -- a zone that does not resolve draws no court
                continue
            for design in designs:
                if (shape := court_shape(design, resolved)) is not None:
                    out.add(shape)
    return out


def _solved(shape: Shape) -> tuple[Shape, float | None]:
    return shape, solve(shape)


def _write(rows: list[dict[str, object]]) -> None:
    LEDGER.write_text(
        json.dumps(
            {
                "rule": "Steph 2026-10-02: THREE POINT is acceptable for now",
                "turn_ft": TURN_FT,
                "fields": list(Shape._fields),
                "shapes": rows,
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--processes", type=int, default=4)
    parser.add_argument("--fresh", action="store_true", help="search every shape again")
    args = parser.parse_args(argv)
    from multiprocessing import Pool

    shapes = sorted(corpus_shapes())
    known = {} if args.fresh else dict(_load())
    todo = [s for s in shapes if s.key not in known]

    def rows() -> list[dict[str, object]]:
        return [{"shape": s.key, "dead_end_ft": known[s.key]} for s in shapes if s.key in known]

    with Pool(max(1, args.processes)) as pool:
        # Written after every answer: a search that dies keeps what it found.
        for shape, answer in pool.imap_unordered(_solved, todo):
            known[shape.key] = answer
            _write(rows())
            print(shape.key, answer, flush=True)
    _write(rows())
    blocked = [r["shape"] for r in rows() if r["dead_end_ft"] is None]
    extended = sum(1 for r in rows() if r["dead_end_ft"])
    print(f"{len(rows())} shapes; extended {extended}; unusable {blocked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
