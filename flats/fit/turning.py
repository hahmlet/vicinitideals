"""Can a car actually drive into each stall of the court, and out again?
(FOLLOWUPS 36(2), 2026-10-02.)

The court is charged as stalls plus an aisle at the widths the codes state,
and the codes' widths are drawn for a car driving along a LONG aisle. The
pod's court is not that: it is one row of four stalls at the end of a lane
down the building's flank, with a dead end at the far side. Whether a car can
use it is a question no table answers, so this module asks the car.

**The car.** Its body is the parking design vehicle, the 85th-percentile car
of 6 ft 7 in by 17 ft 3 in (Iowa SUDAS Design Manual ch. 8, 8B-1 C.1, 2013
ed.: "has remained within an inch or two of 6 feet, 7 inches wide by 17
feet, 3 inches long" since 1999). Its wheelbase and front overhang are the
AASHTO P car's (11 ft and 3 ft), and so is how tightly it turns:
:data:`TURN_FT` is the P car's 24 ft turning radius of the outer front
wheel. Checked against the ordinary 90-degree module -- 9 x 18 ft stalls on
a 24 ft two-way aisle, the design's own and the commonest figure in the
corpus -- that car backs out of a stall and drives away, a 22 ft aisle does
not let it, and a car half a foot less nimble cannot use the 24 ft aisle at
all: the highway book's design car is exactly the car the stall tables were
drawn for.
``flats/tests/test_turning.py`` pins all three.

**The search.** A hybrid A* over the car's rear-axle pose: arcs of fixed
length at five steering settings, forward or reverse, the car's body tested
against the open ground (:func:`shapely.contains`) at three points along
every arc. ``phases`` is the sequence of directions a manoeuvre may use --
``(-1, 1)`` is "back out once, then drive away", ``(-1, 1, -1, 1)`` a
three-point turn. A path it FINDS is a real path (every pose was tested);
a path it does not find may still exist between the lattice's cells, and
the answer depends on the order the cells are tried. So every question is
put four ways (:data:`SEARCHES`: two lattices, two orders) and is "no" only
when all four say so -- a "no" errs toward refusing, never toward passing.

**What it found (2026-10-02).** On today's court (12 ft lane, 24 ft aisle,
four 9 x 18 stalls, the row against the lane, the 5 ft standoff off the
rear wall unpaved) no stall can be left by backing out once and driving
away, and only the stall by the lane can be used even under Steph's ruling
of 2026-10-02, *"THREE POINT is acceptable for now"* (:func:`usable`): the
row's far end is a dead end with no room to swing. Running the aisle on
past the row's far end -- the dead-end extension a parking designer draws
-- lets a car back into the others; so does an aisle 4 ft deeper, for less
than half the paving (2026-10-03), or stalls 2 ft wider. What each court
shape needs is :mod:`flats.score.turns`, and the screen charges the least
paving the lot holds.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np
import shapely
from shapely.geometry.base import BaseGeometry

#: Parking design vehicle, SUDAS 8B-1 C.1: 17 ft 3 in long, 6 ft 7 in wide.
CAR_LENGTH_FT = 17.25
CAR_WIDTH_FT = 6.583
#: AASHTO P car proportions: wheelbase and front overhang.
WHEELBASE_FT = 11.0
FRONT_OVERHANG_FT = 3.0
REAR_OVERHANG_FT = CAR_LENGTH_FT - WHEELBASE_FT - FRONT_OVERHANG_FT
#: Outer front wheel's turning radius: the AASHTO P car's, checked against the
#: 24 ft aisle (above).
TURN_FT = 24.0

#: Arc length of one search step, and poses tested along it.
STEP_FT = 1.5
SAMPLES = 3
#: The closed set's cells: half a foot, five degrees.
CELL_FT = 0.5
CELL_RAD = math.radians(5.0)

#: Back out once, then drive away -- the move a parking table is drawn for.
BACK_OUT = (-1, 1)
#: The three-point turn.
THREE_POINT = (-1, 1, -1, 1)
#: Drive in, with one back-up to straighten.
DRIVE_IN = (1, -1, 1)
#: Drive past, then back in by a three-point turn.
BACK_IN = (1, -1, 1, -1)
#: Leave a stall backed into, nose first, with one back-up.
DRIVE_OUT = (1, -1, 1)


def axle_radius_ft(turn_ft: float = TURN_FT) -> float:
    """Radius the middle of the rear axle turns on, from the outer front
    wheel's: the wheel stands a wheelbase ahead and half a car outboard."""
    return math.sqrt(turn_ft**2 - WHEELBASE_FT**2) - CAR_WIDTH_FT / 2


def bodies(x: np.ndarray, y: np.ndarray, heading: np.ndarray) -> np.ndarray:
    """The car's outline at each rear-axle pose."""
    c, s = np.cos(heading), np.sin(heading)
    front = WHEELBASE_FT + FRONT_OVERHANG_FT
    along = np.array([-REAR_OVERHANG_FT, front, front, -REAR_OVERHANG_FT])
    half = CAR_WIDTH_FT / 2
    across = np.array([-half, -half, half, half])
    px = x[:, None] + c[:, None] * along - s[:, None] * across
    py = y[:, None] + s[:, None] * along + c[:, None] * across
    return shapely.polygons(np.stack([px, py], axis=-1))


def _arc(x: float, y: float, t: float, kappa: float, d: float) -> list[tuple[float, float, float]]:
    out = []
    for i in range(1, SAMPLES + 1):
        s = d * i / SAMPLES
        if kappa == 0.0:
            out.append((x + s * math.cos(t), y + s * math.sin(t), t))
        else:
            r = 1.0 / kappa
            nt = t + s * kappa
            out.append((x + r * (math.sin(nt) - math.sin(t)), y - r * (math.cos(nt) - math.cos(t)), nt))
    return out


@dataclass(frozen=True, slots=True)
class Pose:
    """Middle of the rear axle, feet; heading in radians."""

    x: float
    y: float
    heading: float


def drive(
    ground: BaseGeometry,
    start: Pose,
    arrived: Callable[[Pose], bool],
    phases: Sequence[int],
    *,
    turn_ft: float = TURN_FT,
    toward: tuple[float, float] | None = None,
    max_poses: int = 3_000_000,
    fine: bool = False,
    greed: float = 3.0,
) -> bool:
    """Whether the car gets from ``start`` to a pose ``arrived`` accepts
    without leaving ``ground``, using the directions in ``phases`` in order
    (each may be skipped to the next, never gone back to). ``toward`` only
    orders the search, ``greed`` times the straight-line distance to it
    (greedier finds a path in open ground sooner; any path found is as real
    as any other). False also where ``max_poses`` ran out first -- a budget
    set to exhaust every cell a court of the corpus's size holds, so that a
    "no" is the lattice's answer and not the budget's (200,000 was not:
    found 2026-10-02 on West Linn's 24 ft lane).
    ``fine`` halves the step and the closed set's cells -- the second look
    a "no" gets before anything rests on it."""
    return bool(
        _search(ground, start, arrived, phases, turn_ft=turn_ft, toward=toward,
                max_poses=max_poses, fine=fine, greed=greed, keep=False)
    )


def route(
    ground: BaseGeometry,
    start: Pose,
    arrived: Callable[[Pose], bool],
    phases: Sequence[int],
    *,
    turn_ft: float = TURN_FT,
    toward: tuple[float, float] | None = None,
    max_poses: int = 3_000_000,
    fine: bool = False,
    greed: float = 3.0,
) -> list[Pose] | None:
    """The path :func:`drive` finds, or None where it finds none: ``start``,
    then every pose the search tested along each arc it took, in order --
    the last one ``arrived`` accepted. The same search, the same order, the
    same answer; it only remembers the way it came (FOLLOWUPS 216, so a
    measured path can be carried onto a deeper court and tested again)."""
    found = _search(ground, start, arrived, phases, turn_ft=turn_ft, toward=toward,
                    max_poses=max_poses, fine=fine, greed=greed, keep=True)
    return found if isinstance(found, list) else None


def _search(
    ground: BaseGeometry,
    start: Pose,
    arrived: Callable[[Pose], bool],
    phases: Sequence[int],
    *,
    turn_ft: float,
    toward: tuple[float, float] | None,
    max_poses: int,
    fine: bool,
    greed: float,
    keep: bool,
) -> bool | list[Pose]:
    shapely.prepare(ground)
    step_ft, cell_ft, cell_rad = (STEP_FT, CELL_FT, CELL_RAD)
    if fine:
        step_ft, cell_ft, cell_rad = (step_ft / 2, cell_ft / 2, cell_rad / 2)
    k = 1.0 / axle_radius_ft(turn_ft)
    kappas = (-k, -k / 2, 0.0, k / 2, k)
    turns = round(2 * math.pi / cell_rad)

    def h(x: float, y: float) -> float:
        return 0.0 if toward is None else greed * math.hypot(x - toward[0], y - toward[1])

    # Kept only when asked: each expanded pose's parent and the arc that
    # reached it, appended after the six fields the search orders on (a
    # tie past them is the same pose, so the order and answer are unchanged).
    trail: list[tuple[int, float, float, float, float, float]] = []
    frontier: list[tuple] = [(h(start.x, start.y), 0.0, start.x, start.y, start.heading, 0)]
    if keep:
        frontier = [frontier[0] + (-1, 0.0, 0.0)]
    seen: set[tuple[int, int, int, int]] = set()
    while frontier and len(seen) < max_poses:
        item = heapq.heappop(frontier)
        _, cost, x, y, t, phase = item[:6]
        key = (round(x / cell_ft), round(y / cell_ft), round(t / cell_rad) % turns, phase)
        if key in seen:
            continue
        seen.add(key)
        me = -1
        if keep:
            trail.append((item[6], item[7], item[8], x, y, t))
            me = len(trail) - 1
        if phase == len(phases) - 1 and arrived(Pose(x, y, t)):
            return _walk(trail, me, start) if keep else True
        moves = [(phases[phase] * step_ft, kk, phase) for kk in kappas]
        if phase + 1 < len(phases):
            moves += [(phases[phase + 1] * step_ft, kk, phase + 1) for kk in kappas]
        arcs = [_arc(x, y, t, kk, d) for d, kk, _ in moves]
        poses = np.array([p for arc in arcs for p in arc])
        clear = shapely.contains(ground, bodies(poses[:, 0], poses[:, 1], poses[:, 2]))
        clear = clear.reshape(len(moves), SAMPLES).all(axis=1)
        for ok, arc, (d, kk, nphase) in zip(clear, arcs, moves):
            if ok:
                nx, ny, nt = arc[-1]
                step = cost + step_ft + (0.3 if kk else 0.0) + (3.0 if nphase != phase else 0.0)
                pushed = (step + h(nx, ny), step, nx, ny, nt, nphase)
                heapq.heappush(frontier, pushed + (me, d, kk) if keep else pushed)
    return False


def _walk(trail: list[tuple[int, float, float, float, float, float]], end: int, start: Pose) -> list[Pose]:
    """The poses from ``start`` to ``trail[end]``: every arc re-drawn from
    its parent's pose exactly as the search drew and tested it."""
    chain = []
    while end > 0:
        chain.append(end)
        end = trail[end][0]
    out = [start]
    for i in reversed(chain):
        parent, d, kk = trail[i][:3]
        _, _, _, px, py, pt = trail[parent]
        out.extend(Pose(*p) for p in _arc(px, py, pt, kk, d))
    return out


#: The four ways the search is run. Each is incomplete differently -- a
#: path one misses another may find, the fine lattice is not a superset of
#: the coarse one -- and every path any of them finds is real, so a "yes"
#: from any is a yes and a "no" needs all four.
SEARCHES: tuple[tuple[bool, float], ...] = ((False, 3.0), (False, 1.0), (True, 3.0), (True, 1.0))


def finds(
    ground: BaseGeometry,
    start: Pose,
    arrived: Callable[[Pose], bool],
    phases: Sequence[int],
    **kw: object,
) -> bool:
    """:func:`drive` run every way in :data:`SEARCHES`, stopping at the first
    that finds a path."""
    return any(
        drive(ground, start, arrived, phases, fine=fine, greed=greed, **kw)  # type: ignore[arg-type]
        for fine, greed in SEARCHES
    )


def facing(heading: float, want: float, within_deg: float) -> bool:
    return abs(((heading - want + math.pi) % (2 * math.pi)) - math.pi) <= math.radians(within_deg)


def parked_in(stall: BaseGeometry, nose: float) -> Callable[[Pose], bool]:
    """Square in ``stall`` (within 3 degrees of ``nose``), wholly inside it."""

    def ok(p: Pose) -> bool:
        if not facing(p.heading, nose, 3.0):
            return False
        return bool(stall.contains(bodies(np.array([p.x]), np.array([p.y]), np.array([p.heading]))[0]))

    return ok


def parked_pose(stall: BaseGeometry, *, nose_out: bool = False) -> Pose:
    """Centred, a quarter foot off the stall's far end -- for a stall
    standing north of its aisle (``+y``). Nose in unless ``nose_out``: then
    backed in, its rear bumper at that end."""
    x0, _, x1, y1 = stall.bounds
    if nose_out:
        return Pose((x0 + x1) / 2, y1 - 0.25 - REAR_OVERHANG_FT, -math.pi / 2)
    return Pose((x0 + x1) / 2, y1 - 0.25 - WHEELBASE_FT - FRONT_OVERHANG_FT, math.pi / 2)


@dataclass(frozen=True, slots=True)
class Court:
    """The pod's rear court in its own frame: ``x`` across the lot with the
    lane on the ``+`` side, ``y`` into the lot, the building's rear wall on
    ``y = 0``. The lane runs ``lane_ft`` wide from ``x = 0`` back to the
    street; the standoff (``gap_ft``) is open ground for the lane only; the
    aisle runs behind the standoff across the row and ``extra_ft`` past its
    far end; the row of ``stalls`` stands behind the aisle, its outer end
    against the lane's outer edge."""

    stalls: int = 4
    stall_w_ft: float = 9.0
    stall_d_ft: float = 18.0
    aisle_ft: float = 24.0
    gap_ft: float = 5.0
    lane_ft: float = 12.0
    lane_len_ft: float = 36.0
    extra_ft: float = 0.0

    def stall(self, i: int) -> BaseGeometry:
        """Stall ``i``, counted from the lane's end of the row."""
        right = self.lane_ft - i * self.stall_w_ft
        y = self.gap_ft + self.aisle_ft
        return shapely.box(right - self.stall_w_ft, y, right, y + self.stall_d_ft)

    def ground(self, i: int) -> BaseGeometry:
        """Where the car may be while stall ``i`` is its own and the rest are taken."""
        lane = shapely.box(0.0, -self.lane_len_ft, self.lane_ft, self.gap_ft)
        left = self.lane_ft - self.stalls * self.stall_w_ft - self.extra_ft
        aisle = shapely.box(min(left, 0.0), self.gap_ft, self.lane_ft, self.gap_ft + self.aisle_ft)
        return shapely.union_all([lane, aisle, self.stall(i)])

    def street_end(self) -> Pose:
        """Coming down the lane toward the court."""
        return Pose(self.lane_ft / 2, -self.lane_len_ft + REAR_OVERHANG_FT + 1.0, math.pi / 2)

    def gone(self, p: Pose) -> bool:
        """Driving up the lane toward the street, nose first."""
        return p.y < -self.lane_len_ft + 25.0 and facing(p.heading, -math.pi / 2, 10.0)


def leaves(
    court: Court, i: int, phases: Sequence[int] = BACK_OUT, *, nose_out: bool = False, **kw: object
) -> bool:
    """Whether a car parked in stall ``i`` gets up the lane nose first."""
    toward = (court.lane_ft / 2, -court.lane_len_ft + 10.0)
    start = parked_pose(court.stall(i), nose_out=nose_out)
    return finds(court.ground(i), start, court.gone, phases, toward=toward, **kw)


def arrives(
    court: Court, i: int, phases: Sequence[int] = DRIVE_IN, *, nose_out: bool = False, **kw: object
) -> bool:
    """Whether a car coming down the lane gets into stall ``i`` -- nose
    first, or backed in where ``nose_out``."""
    stall = court.stall(i)
    goal = parked_pose(stall, nose_out=nose_out)
    return finds(
        court.ground(i),
        court.street_end(),
        parked_in(stall, goal.heading),
        phases,
        toward=(goal.x, goal.y),
        **kw,
    )


def usable(court: Court, i: int, **kw: object) -> bool:
    """Whether stall ``i`` can be used under Steph's rule of 2026-10-02,
    *"THREE POINT is acceptable for now"*: no trip in or out takes more
    than four moves. Parked nose in, that is drive in with one back-up to
    straighten (:data:`DRIVE_IN`) and leave by a three-point turn
    (:data:`THREE_POINT`); backed in, drive past and back in with a
    three-point turn (:data:`BACK_IN`) and leave nose first with one
    back-up (:data:`DRIVE_OUT`). Either way of parking will do."""
    if arrives(court, i, DRIVE_IN, **kw) and leaves(court, i, THREE_POINT, **kw):
        return True
    return arrives(court, i, BACK_IN, nose_out=True, **kw) and leaves(
        court, i, DRIVE_OUT, nose_out=True, **kw
    )


# -- A deeper court, by the standard court's measured path (FOLLOWUPS 216) --
#
# Steph 2026-11-27 (rulings.yaml ``2026-11-27-deeper-court-passes``): the
# stair-room re-placement sets the court further back off the rear wall, and
# the search's own answers on that court depend on its lattice. A court whose
# only difference is the deeper standoff is the same court with the lane run
# on straight: every piece of it stands ``dy`` further into the lot, and the
# lane reaches back to the same street end. So the path the car was SEEN to
# drive on the standard court, moved ``dy`` into the lot, lies on the deeper
# court's ground; the car only drives the extra lane straight first (coming
# in) or last (going out). That is what is checked here, pose by pose against
# the deeper court's own ground -- never assumed.

#: The spacing the carried straight drive is tested at: the search's own
#: spacing between tested poses.
CARRY_STEP_FT = STEP_FT / SAMPLES


def deeper_by(standard: Court, deeper: Court) -> float | None:
    """How much deeper ``deeper``'s standoff is than ``standard``'s, where that
    is the only difference between them; None otherwise."""
    if deeper.gap_ft <= standard.gap_ft:
        return None
    if Court(**{**_fields(deeper), "gap_ft": standard.gap_ft}) != standard:
        return None
    return deeper.gap_ft - standard.gap_ft


def _fields(court: Court) -> dict[str, float]:
    return {f: getattr(court, f) for f in Court.__dataclass_fields__}


def _straight(start: Pose, length_ft: float) -> list[Pose]:
    """Poses along a straight forward drive of ``length_ft`` from ``start``
    (``start`` excluded, the far end included)."""
    n = max(1, math.ceil(length_ft / CARRY_STEP_FT - 1e-9))
    c, s = math.cos(start.heading), math.sin(start.heading)
    return [
        Pose(start.x + c * length_ft * j / n, start.y + s * length_ft * j / n, start.heading)
        for j in range(1, n + 1)
    ]


def _on(ground: BaseGeometry, poses: Sequence[Pose]) -> bool:
    shapely.prepare(ground)
    xs = np.array([p.x for p in poses])
    ys = np.array([p.y for p in poses])
    ts = np.array([p.heading for p in poses])
    return bool(shapely.contains(ground, bodies(xs, ys, ts)).all())


def _moved(path: Sequence[Pose], dy: float) -> list[Pose]:
    return [Pose(p.x, p.y + dy, p.heading) for p in path]


def _same(a: Pose, b: Pose) -> bool:
    return math.isclose(a.x, b.x, abs_tol=1e-6) and math.isclose(a.y, b.y, abs_tol=1e-6) and (
        math.isclose(a.heading, b.heading, abs_tol=1e-9)
    )


def carried_in(path: Sequence[Pose], standard: Court, deeper: Court, i: int, nose: float) -> bool:
    """Whether ``path`` (an arrival found on ``standard``) carries onto
    ``deeper``, the same court ``dy`` deeper (:func:`deeper_by`): the car drives straight up the lane
    from the deeper court's street end the extra ``dy``, then the path moved
    ``dy`` into the lot, every pose on the deeper court's ground, and ends
    parked in the deeper court's stall ``i``. The lead-in is forward, the
    direction every arrival's first move takes (:data:`DRIVE_IN`,
    :data:`BACK_IN`), so no move is added."""
    if (dy := deeper_by(standard, deeper)) is None:
        return False
    start = deeper.street_end()
    lead = _straight(start, dy)
    moved = _moved(path, dy)
    if not _same(lead[-1], moved[0]):
        return False
    poses = [start, *lead, *moved[1:]]
    return _on(deeper.ground(i), poses) and parked_in(deeper.stall(i), nose)(moved[-1])


def carried_out(
    path: Sequence[Pose], standard: Court, deeper: Court, i: int, *, nose_out: bool = False
) -> bool:
    """Whether ``path`` (a departure found on ``standard``) carries onto
    ``deeper``, the same court ``dy`` deeper (:func:`deeper_by`): it starts parked in the deeper
    court's stall ``i``, runs moved ``dy`` into the lot, then the car keeps
    driving forward as it was heading until it is up the lane
    (:meth:`Court.gone`), every pose on the deeper court's ground. The
    run-out is forward, the direction every departure's last move takes
    (:data:`THREE_POINT`, :data:`DRIVE_OUT`), so no move is added."""
    if (dy := deeper_by(standard, deeper)) is None:
        return False
    moved = _moved(path, dy)
    if not _same(moved[0], parked_pose(deeper.stall(i), nose_out=nose_out)):
        return False
    end = moved[-1]
    tail: list[Pose] = []
    if not deeper.gone(end):
        # Forward at the path's last heading (within 10 degrees of straight
        # up the lane) until past the line ``gone`` draws, plus one step.
        down = -math.sin(end.heading)
        if down <= 0:
            return False
        need = (end.y - (-deeper.lane_len_ft + 25.0)) / down + CARRY_STEP_FT
        tail = _straight(end, need)
        if not deeper.gone(tail[-1]):
            return False
    return _on(deeper.ground(i), [*moved, *tail])


#: The two ways a stall is used (:func:`usable`): arrive, leave, backed in.
WAYS: tuple[tuple[Sequence[int], Sequence[int], bool], ...] = (
    (DRIVE_IN, THREE_POINT, False),
    (BACK_IN, DRIVE_OUT, True),
)


def arrival(court: Court, i: int, phases: Sequence[int], *, nose_out: bool = False) -> list[Pose] | None:
    """The path :func:`arrives` finds, the first of :data:`SEARCHES` to find one."""
    stall = court.stall(i)
    goal = parked_pose(stall, nose_out=nose_out)
    for fine, greed in SEARCHES:
        found = route(
            court.ground(i), court.street_end(), parked_in(stall, goal.heading), phases,
            toward=(goal.x, goal.y), fine=fine, greed=greed,
        )
        if found is not None:
            return found
    return None


def departure(court: Court, i: int, phases: Sequence[int], *, nose_out: bool = False) -> list[Pose] | None:
    """The path :func:`leaves` finds, the first of :data:`SEARCHES` to find one."""
    toward = (court.lane_ft / 2, -court.lane_len_ft + 10.0)
    start = parked_pose(court.stall(i), nose_out=nose_out)
    for fine, greed in SEARCHES:
        found = route(court.ground(i), start, court.gone, phases, toward=toward, fine=fine, greed=greed)
        if found is not None:
            return found
    return None


def usable_deeper(standard: Court, deepers: Sequence[Court], i: int) -> list[bool]:
    """For each court of ``deepers``, whether stall ``i`` is usable there by
    the paths the car was seen to drive on ``standard`` (:func:`usable`'s two
    ways, each trip's path carried by :func:`carried_in` and
    :func:`carried_out`). False for a court that differs from ``standard`` in
    anything but a deeper standoff, and wherever the standard court gave no
    path or a path did not carry: never a pass the standard court does not
    have."""
    out = [False] * len(deepers)
    carries = [deeper_by(standard, d) is not None for d in deepers]
    for arrive_phases, leave_phases, nose_out in WAYS:
        todo = [j for j, ok in enumerate(carries) if ok and not out[j]]
        if not todo:
            break
        came = arrival(standard, i, arrive_phases, nose_out=nose_out)
        if came is None:
            continue
        nose = parked_pose(standard.stall(i), nose_out=nose_out).heading
        todo = [j for j in todo if carried_in(came, standard, deepers[j], i, nose)]
        if not todo:
            continue
        went = departure(standard, i, leave_phases, nose_out=nose_out)
        if went is None:
            continue
        for j in todo:
            out[j] = carried_out(went, standard, deepers[j], i, nose_out=nose_out)
    return out
