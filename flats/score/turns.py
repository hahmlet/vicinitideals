"""What a lane-fed rear court must be given for a car to use every stall.

Steph's ruling of 2026-10-02 on FOLLOWUPS 36(2), *"THREE POINT is acceptable
for now"*: a stall counts when a car can get into it and out again without
any trip taking more than four moves (:func:`flats.fit.turning.usable`). The
car and the search are :mod:`flats.fit.turning`; this module asks them about
the courts the screen actually charges.

**What is asked.** The rear court reached by a lane down the building's flank
(:func:`flats.score.paper.court_across` with a lane): one row of the charged
stalls behind the aisle, the row's near end against the lane's outer edge, a
dead end at the far one. Where a car cannot use every stall, the court is
given more room, one of three ways (a :class:`Fix`), each the least that
works:

- the aisle DEEPER, so the car swings round in front of the row
  (``aisle_ft``, whole feet up to :data:`MAX_AISLE_FT`) -- the lot pays in
  depth;
- every stall WIDER, so the car turns in and out on a shallower angle
  (``stall_ft``, half feet up to :data:`MAX_STALL_FT`) -- the lot pays in
  width;
- the aisle run on past the far end of the row, the DEAD END a parking
  designer draws (``dead_end_ft``, whole feet up to :data:`MAX_DEAD_END_FT`)
  -- in width;
- and between the first and the last, an aisle deepened by less than it
  needs alone plus the shorter dead end that then does (``mixed``, every
  whole foot short of the deeper aisle's answer) -- a lot with a few feet
  to spare each way holds one where it holds neither alone.

Steph 2026-10-03: *"the 13 foot dead end should be almost a last-resort
solution"*. :func:`fixes` hands the screen every fix that works, least paving
first (:func:`paving`), and the fit takes the first one the lot holds. An
empty answer is a court no fix lets a car use: it cannot be used at all.

**Why a ledger.** The answer depends only on the court's shape -- stall count,
stall width and depth, aisle, lane, standoff -- and the corpus draws a couple
of dozen of them. One search is seconds to an hour, so they are computed
once (``python -m flats.score.turns``) into ``flats/config/court_turns.json``,
and ``flats/tests/test_turns.py`` fails when a rule change brings a shape the
ledger does not hold. A shape the ledger misses at screen time -- a lot's own
variant can draw one no zone draws -- is NOT searched there (16 workers
searching would stall a county run for hours): it is :data:`UNSEARCHED`, the
court is left unchecked, and the lot cannot be green on it. ``--shapes``
adds the shapes a bridge run met (its ``turn_shapes.txt``) to the ledger.

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
from pathlib import Path
from typing import NamedTuple

from flats.fit.turning import TURN_FT, Court, usable

LEDGER = Path(__file__).resolve().parents[1] / "config" / "court_turns.json"

#: The longest dead-end extension asked for.
MAX_DEAD_END_FT = 24
#: The most an aisle is deepened.
MAX_AISLE_FT = 12
#: The most a stall is widened, in half feet.
MAX_STALL_FT = 3.0


class Fix(NamedTuple):
    """What a court is given so a car can use every stall: the aisle that
    much deeper, each stall that much wider, the aisle run that far past
    the row's far end. All zero: the court as drawn."""

    aisle_ft: float = 0.0
    stall_ft: float = 0.0
    dead_end_ft: float = 0.0


#: The court as drawn, nothing given.
AS_DRAWN = Fix()


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

    def court(self, fix: Fix = AS_DRAWN) -> Court:
        return Court(
            stalls=self.stalls,
            stall_w_ft=self.stall_w_ft + fix.stall_ft,
            stall_d_ft=self.stall_d_ft,
            aisle_ft=self.aisle_ft + fix.aisle_ft,
            gap_ft=self.gap_ft,
            lane_ft=self.lane_ft,
            extra_ft=fix.dead_end_ft,
        )


def paving(shape: Shape, fix: Fix) -> float:
    """The court's paving given ``fix``, in square feet: the stalls, and the
    aisle along the row or the lane's mouth, whichever is longer -- the
    court :func:`flats.score.paper.paved` charges."""
    row = shape.stalls * (shape.stall_w_ft + fix.stall_ft)
    aisle = shape.aisle_ft + fix.aisle_ft
    return row * shape.stall_d_ft + aisle * max(row + fix.dead_end_ft, shape.lane_ft)


def every_stall(shape: Shape, fix: Fix = AS_DRAWN) -> bool:
    """Whether every stall of ``shape`` given ``fix`` is usable. The far
    end's stalls first: the first to fail."""
    court = shape.court(fix)
    return all(usable(court, i) for i in reversed(range(shape.stalls)))


#: Each way of giving a court room: the :class:`Fix` field it sets, then
#: its step and its most, in feet. The order breaks a tie in paving.
LEVERS: dict[str, tuple[float, float]] = {
    "aisle_ft": (1.0, float(MAX_AISLE_FT)),
    "stall_ft": (0.5, MAX_STALL_FT),
    "dead_end_ft": (1.0, float(MAX_DEAD_END_FT)),
}


def solve(
    shape: Shape, lever: str = "dead_end_ft", base: Fix = AS_DRAWN, most: float | None = None
) -> float | None:
    """The least ``lever`` (a :class:`Fix` field, in its own steps) that,
    added to ``base``, lets the car use every stall: 0 where ``base``
    already does, ``None`` where not even ``most`` (the lever's own most
    when omitted) does.

    Room only grows with each lever, so the answer is searched by halving.
    A value the lattice happens to miss between two that pass can only make
    the answer larger, the conservative side -- and the answer returned is
    always one the car was seen to drive."""
    if every_stall(shape, base):
        return 0.0
    step, top = LEVERS[lever]
    top = top if most is None else most

    def given(v: float) -> Fix:
        return base._replace(**{lever: getattr(base, lever) + v})

    if not every_stall(shape, given(top)):
        return None
    lo, hi = 0, round(top / step)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if every_stall(shape, given(mid * step)):
            hi = mid
        else:
            lo = mid
    return hi * step


def mixed_wanted(held: dict[str, object]) -> list[int]:
    """The deepenings short of the aisle's own answer a mixed fix is asked
    for: every whole foot from 1, where the aisle alone and the dead end
    alone both answer and neither is zero."""
    aisle, dead = held.get("aisle_ft"), held.get("dead_end_ft")
    if not isinstance(aisle, float) or not isinstance(dead, float) or not aisle or not dead:
        return []
    return list(range(1, int(aisle)))


def _load() -> dict[str, dict[str, float | None]]:
    if not LEDGER.exists():
        return {}
    data = json.loads(LEDGER.read_text(encoding="utf-8"))
    if data.get("turn_ft") != TURN_FT:
        return {}
    return {
        row["shape"]: {
            **{lever: row[lever] for lever in LEVERS if lever in row},
            **({"mixed": dict(row["mixed"])} if "mixed" in row else {}),
        }
        for row in data["shapes"]
    }


_LEDGER = _load()


class Unsearched:
    """A court shape the ledger does not hold: the car was not asked."""

    def __repr__(self) -> str:
        return "UNSEARCHED"


UNSEARCHED = Unsearched()


def fixes(shape: Shape) -> tuple[Fix, ...] | Unsearched:
    """Every fix that lets a car use every stall of ``shape``, least paving
    first (see the module docstring): ``(AS_DRAWN,)`` where the court needs
    none, empty where none works, :data:`UNSEARCHED` where the ledger does
    not hold the shape. A lever the ledger was not asked about is not
    offered: a fix too few, never one too many."""
    held = _LEDGER.get(shape.key)
    if held is None:
        return UNSEARCHED
    if any(held.get(lever) == 0.0 for lever in LEVERS):
        return (AS_DRAWN,)
    found = [Fix(**{lever: held[lever]}) for lever in LEVERS if held.get(lever) is not None]
    for aisle, dead in dict(held.get("mixed") or {}).items():
        if dead is not None:
            found.append(Fix(aisle_ft=float(aisle), dead_end_ft=dead))
    # A fix that asks at least as much of every lever as another is never
    # the one a lot holds when the other is not.
    kept = {
        f
        for f in found
        if not any(g != f and all(a <= b for a, b in zip(g, f)) for g in found)
    }
    return tuple(sorted(kept, key=lambda fix: (paving(shape, fix), fix)))


def parse(key: str) -> Shape:
    """The shape a ledger key names."""
    stalls, *rest = key.split("|")
    return Shape(int(stalls), *(float(v) for v in rest))


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


def _solved(
    task: tuple[Shape, str, int, float | None],
) -> tuple[Shape, str, int, float | None]:
    shape, lever, aisle, most = task
    if lever == "mixed":
        return shape, lever, aisle, solve(shape, "dead_end_ft", Fix(aisle_ft=float(aisle)), most)
    return shape, lever, aisle, solve(shape, lever)


def _write(rows: list[dict[str, object]]) -> None:
    LEDGER.write_text(
        json.dumps(
            {
                "rule": "Steph 2026-10-02: THREE POINT is acceptable for now",
                "turn_ft": TURN_FT,
                "fields": list(Shape._fields),
                "levers": list(LEVERS),
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
    parser.add_argument(
        "--shapes",
        type=Path,
        action="append",
        default=[],
        help="a file of shape keys, one a line (a bridge run's turn_shapes.txt), searched too",
    )
    args = parser.parse_args(argv)
    from multiprocessing import Pool

    found = set(corpus_shapes())
    for path in args.shapes:
        found |= {parse(line.strip()) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}
    shapes = sorted(found)
    known: dict[str, dict[str, object]] = {} if args.fresh else _load()
    for held in known.values():
        if any(held.get(lever) == 0.0 for lever in LEVERS):
            # The court as drawn works: every lever is zero, nothing to ask.
            held.update(dict.fromkeys(LEVERS, 0.0))

    def rows() -> list[dict[str, object]]:
        return [{"shape": s.key, **known[s.key]} for s in shapes if s.key in known]

    with Pool(max(1, args.processes)) as pool:
        # The levers alone first: the mixed fixes are asked between them.
        for phase in ("levers", "mixed"):
            if phase == "levers":
                todo = [
                    (s, lever, 0, None)
                    for s in shapes
                    for lever in LEVERS
                    if lever not in known.get(s.key, {})
                ]
            else:
                todo = []
                for s in shapes:
                    held = known[s.key]
                    asked = dict(held.get("mixed") or {})  # type: ignore[call-overload]
                    for aisle in mixed_wanted(held):
                        if str(aisle) not in asked:
                            todo.append((s, "mixed", aisle, held["dead_end_ft"]))
            # Written after every answer: a search that dies keeps what it found.
            for shape, lever, aisle, answer in pool.imap_unordered(_solved, todo):
                held = known.setdefault(shape.key, {})
                if lever == "mixed":
                    mixed = dict(held.get("mixed") or {})  # type: ignore[call-overload]
                    mixed[str(aisle)] = answer
                    held["mixed"] = dict(sorted(mixed.items(), key=lambda kv: int(kv[0])))
                else:
                    held[lever] = answer
                    if answer == 0.0:
                        held.update(dict.fromkeys(LEVERS, 0.0))
                _write(rows())
                print(shape.key, lever, aisle or "", answer, flush=True)
    _write(rows())
    blocked = [r["shape"] for r in rows() if all(r.get(lever) is None for lever in LEVERS)]
    fixed = sum(1 for r in rows() if r.get("dead_end_ft"))
    print(f"{len(rows())} shapes; needing a fix {fixed}; unusable {blocked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
