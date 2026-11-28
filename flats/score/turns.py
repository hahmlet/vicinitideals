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

**A deeper standoff is carried, not searched** (FOLLOWUPS 216; Steph
2026-11-27, rulings.yaml ``2026-11-27-deeper-court-passes``). The stair-room
re-placement (:meth:`flats.designs.model.Design.reserving`) raises the
standoff behind the rear wall, which is the same court with a longer straight
lane, and the search's own answers on it depend on how its lattice falls
(passes at 6.25 ft, none at 5.33 ft on the same court). So ``--carry`` takes
each such shape from the searched row it deepens (:func:`measured`): every
fix that row offers is driven on the standard court again, its paths kept,
and each path carried onto the deeper court and tested pose by pose
(:func:`flats.fit.turning.usable_deeper`). A fix that carries for every stall
is the deeper court's; one that does not is not offered. The rows are the
ledger's ``carried`` list. A shape with no searched standard row, a standard
row no fix saves, or no fix that carried is not carried at all: it stays
:data:`UNSEARCHED`, never a pass the standard court does not have and never
an "unusable" the car was not asked about.

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

from flats.fit.turning import TURN_FT, Court, usable, usable_deeper

LEDGER = Path(__file__).resolve().parents[1] / "config" / "court_turns.json"
CARRY_RULE = (
    "Steph 2026-11-27 (rulings.yaml 2026-11-27-deeper-court-passes): a deeper standoff passes "
    "where the standard court's measured paths, carried and checked pose by pose, pass"
)

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


def _data() -> dict[str, object]:
    if not LEDGER.exists():
        return {}
    data = json.loads(LEDGER.read_text(encoding="utf-8"))
    return data if data.get("turn_ft") == TURN_FT else {}


def _load() -> dict[str, dict[str, object]]:
    data = _data()
    held: dict[str, dict[str, object]] = {
        row["shape"]: {
            **{lever: row[lever] for lever in LEVERS if lever in row},
            **({"mixed": dict(row["mixed"])} if "mixed" in row else {}),
        }
        for row in data.get("shapes", [])  # type: ignore[union-attr]
    }
    for row in data.get("carried", []):  # type: ignore[union-attr]
        # A searched row of the same key wins: it was asked directly.
        held.setdefault(
            row["shape"], {"carried": [list(f) for f in row["fixes"]], "from": row["from"]}
        )
    return held


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
    if "carried" in held:
        # A deeper standoff carried from its standard court (the module
        # docstring): the fixes whose paths carried. None carried is not
        # "unusable" -- the car was never asked here -- so it is unsearched.
        found = [Fix(*f) for f in held["carried"]]  # type: ignore[union-attr]
        if not found:
            return UNSEARCHED
        if AS_DRAWN in found:
            return (AS_DRAWN,)
        return _least_first(shape, found)
    if any(held.get(lever) == 0.0 for lever in LEVERS):
        return (AS_DRAWN,)
    found = [Fix(**{lever: held[lever]}) for lever in LEVERS if held.get(lever) is not None]
    for aisle, dead in dict(held.get("mixed") or {}).items():
        if dead is not None:
            found.append(Fix(aisle_ft=float(aisle), dead_end_ft=dead))
    return _least_first(shape, found)


def _least_first(shape: Shape, found: list[Fix]) -> tuple[Fix, ...]:
    # A fix that asks at least as much of every lever as another is never
    # the one a lot holds when the other is not.
    kept = {
        f
        for f in found
        if not any(g != f and all(a <= b for a, b in zip(g, f)) for g in found)
    }
    return tuple(sorted(kept, key=lambda fix: (paving(shape, fix), fix)))


def measured(shape: Shape) -> Shape | None:
    """The searched ledger shape ``shape`` is a deeper standoff of, or None:
    the same court in every field but ``gap_ft``, shallower there, searched
    (not itself carried) and saved by at least one fix -- the deepest such.
    A standard court no fix saves gives a deeper one nothing to carry."""
    best: Shape | None = None
    for key, held in _LEDGER.items():
        if "carried" in held:
            continue
        other = parse(key)
        if other[:5] != shape[:5] or not other.gap_ft < shape.gap_ft:
            continue
        found = fixes(other)
        if isinstance(found, Unsearched) or not found:
            continue
        if best is None or other.gap_ft > best.gap_ft:
            best = other
    return best


def carry(standard: Shape, deeper: list[Shape], fix: Fix) -> list[bool]:
    """For each of ``deeper``, whether ``fix`` lets the car use every stall
    by the standard court's own paths, carried (the module docstring). The
    far end's stalls first, as :func:`every_stall`."""
    court = standard.court(fix)
    alive = list(range(len(deeper)))
    for i in reversed(range(standard.stalls)):
        ok = usable_deeper(court, [deeper[j].court(fix) for j in alive], i)
        alive = [j for j, k in zip(alive, ok) if k]
        if not alive:
            break
    return [j in alive for j in range(len(deeper))]


def _carried(task: tuple[Shape, list[Shape], Fix]) -> tuple[Shape, list[Shape], Fix, list[bool]]:
    standard, deeper, fix = task
    return standard, deeper, fix, carry(standard, deeper, fix)


def parse(key: str) -> Shape:
    """The shape a ledger key names."""
    stalls, *rest = key.split("|")
    return Shape(int(stalls), *(float(v) for v in rest))


def corpus_shapes() -> set[Shape]:
    """Every lane-fed court shape the active designs draw in any encoded zone."""
    from flats.designs.model import load_catalog
    from flats.rules.loader import load_rules
    from flats.rules.resolver import RuleSet
    from flats.score.paper import court_shape, narrow_lane_rungs

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
                # The narrower drives a ruling lets the second screen try
                # (Portland's 9 ft, rulings.yaml 2026-11-10-portland-driveway-9ft),
                # narrowest first, up to the first the car is known to use or
                # was never asked about: the one the screen draws.
                for rung in narrow_lane_rungs(design, resolved):
                    if (shape := court_shape(design, rung)) is None:
                        break
                    out.add(shape)
                    found = fixes(shape)
                    if isinstance(found, Unsearched) or found:
                        break
    return out


def _solved(
    task: tuple[Shape, str, int, float | None],
) -> tuple[Shape, str, int, float | None]:
    shape, lever, aisle, most = task
    if lever == "mixed":
        return shape, lever, aisle, solve(shape, "dead_end_ft", Fix(aisle_ft=float(aisle)), most)
    return shape, lever, aisle, solve(shape, lever)


def _write(rows: list[dict[str, object]], carried: list[dict[str, object]] | None = None) -> None:
    if carried is None:
        carried = list(_data().get("carried", []))  # type: ignore[call-overload]
    LEDGER.write_text(
        json.dumps(
            {
                "rule": "Steph 2026-10-02: THREE POINT is acceptable for now",
                "turn_ft": TURN_FT,
                "fields": list(Shape._fields),
                "levers": list(LEVERS),
                "shapes": rows,
                "carry_rule": CARRY_RULE,
                "carried": carried,
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
    parser.add_argument(
        "--carry",
        type=Path,
        action="append",
        default=[],
        help="a file of deeper-standoff shape keys, carried from their standard rows, not searched",
    )
    parser.add_argument("--carry-only", action="store_true", help="carry, search nothing")
    args = parser.parse_args(argv)
    wanted: set[Shape] = set()
    for path in args.carry:
        wanted |= {parse(line.strip()) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}
    if args.carry_only:
        carry_main(wanted, list(_data().get("shapes", [])), args.processes)  # type: ignore[call-overload]
        return 0
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
    carry_main(wanted, rows(), args.processes, fresh=args.fresh)
    return 0


def carry_main(
    wanted: set[Shape], rows: list[dict[str, object]], processes: int, *, fresh: bool = False
) -> list[dict[str, object]]:
    """Carry ``wanted`` (and every row already carried) from their standard
    rows into the ledger's ``carried`` list. A row already carried is kept
    while it still carries from the same standard row and that row still
    offers every fix it took; else it is carried again."""
    global _LEDGER
    before = {} if fresh else {row["shape"]: row for row in _data().get("carried", [])}  # type: ignore[union-attr]
    # The file holds the rows as just searched (a searched key wins over a
    # carried one, and a carried row is never a standard).
    _LEDGER = _load()
    searched = {str(r["shape"]) for r in rows}
    kept: dict[str, dict[str, object]] = {}
    for key, row in before.items():
        std = parse(str(row["from"]))
        offered = fixes(std)
        if key in searched or isinstance(offered, Unsearched) or measured(parse(key)) != std:
            continue
        if all(Fix(*f) in offered for f in row["fixes"]):  # type: ignore[union-attr]
            kept[key] = row
    _write(rows, sorted(kept.values(), key=lambda r: str(r["shape"])))
    groups: dict[Shape, list[Shape]] = {}
    for shape in sorted(wanted | {parse(k) for k in before}):
        if shape.key in kept or shape.key in searched:
            continue
        if (std := measured(shape)) is not None:
            groups.setdefault(std, []).append(shape)
        else:
            print(shape.key, "no searched standard row a fix saves: not carried (unsearched)", flush=True)
    offered_by = {std: fixes(std) for std in groups}
    todo = [(std, deeper, fix) for std, deeper in sorted(groups.items()) for fix in offered_by[std]]  # type: ignore[union-attr]
    took: dict[str, list[list[float]]] = {d.key: [] for ds in groups.values() for d in ds}
    failed: dict[str, list[list[float]]] = {d.key: [] for ds in groups.values() for d in ds}
    left = {std: len(offered_by[std]) for std in groups}  # type: ignore[arg-type]

    def out() -> list[dict[str, object]]:
        return sorted(kept.values(), key=lambda r: str(r["shape"]))

    from contextlib import nullcontext
    from multiprocessing import Pool

    with Pool(processes) if processes > 1 else nullcontext() as pool:
        answers = pool.imap_unordered(_carried, todo) if pool is not None else map(_carried, todo)
        # Written as each standard row's fixes are all carried: a row is never
        # half carried (a fix too few could charge a costlier one).
        for std, deeper, fix, ok in answers:
            for d, k in zip(deeper, ok):
                (took if k else failed)[d.key].append(list(fix))
                print(d.key, "from", std.key, list(fix), "carried" if k else "DID NOT CARRY", flush=True)
            left[std] -= 1
            if not left[std]:
                for d in deeper:
                    kept[d.key] = {
                        "shape": d.key,
                        "from": std.key,
                        "fixes": sorted(took[d.key]),
                        "not_carried": sorted(failed[d.key]),
                    }
                _write(rows, out())
    _write(rows, out())
    _LEDGER = _load()
    print(f"{len(out())} carried; {sum(1 for r in out() if not r['fixes'])} with no fix that carried")
    return out()


if __name__ == "__main__":
    raise SystemExit(main())
