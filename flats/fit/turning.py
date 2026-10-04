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
    shapely.prepare(ground)
    step_ft, cell_ft, cell_rad = (STEP_FT, CELL_FT, CELL_RAD)
    if fine:
        step_ft, cell_ft, cell_rad = (step_ft / 2, cell_ft / 2, cell_rad / 2)
    k = 1.0 / axle_radius_ft(turn_ft)
    kappas = (-k, -k / 2, 0.0, k / 2, k)
    turns = round(2 * math.pi / cell_rad)

    def h(x: float, y: float) -> float:
        return 0.0 if toward is None else greed * math.hypot(x - toward[0], y - toward[1])

    frontier = [(h(start.x, start.y), 0.0, start.x, start.y, start.heading, 0)]
    seen: set[tuple[int, int, int, int]] = set()
    while frontier and len(seen) < max_poses:
        _, cost, x, y, t, phase = heapq.heappop(frontier)
        key = (round(x / cell_ft), round(y / cell_ft), round(t / cell_rad) % turns, phase)
        if key in seen:
            continue
        seen.add(key)
        if phase == len(phases) - 1 and arrived(Pose(x, y, t)):
            return True
        moves = [(phases[phase] * step_ft, kk, phase) for kk in kappas]
        if phase + 1 < len(phases):
            moves += [(phases[phase + 1] * step_ft, kk, phase + 1) for kk in kappas]
        arcs = [_arc(x, y, t, kk, d) for d, kk, _ in moves]
        poses = np.array([p for arc in arcs for p in arc])
        clear = shapely.contains(ground, bodies(poses[:, 0], poses[:, 1], poses[:, 2]))
        clear = clear.reshape(len(moves), SAMPLES).all(axis=1)
        for ok, arc, (_, kk, nphase) in zip(clear, arcs, moves):
            if ok:
                nx, ny, nt = arc[-1]
                step = cost + step_ft + (0.3 if kk else 0.0) + (3.0 if nphase != phase else 0.0)
                heapq.heappush(frontier, (step + h(nx, ny), step, nx, ny, nt, nphase))
    return False


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
