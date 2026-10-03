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
AASHTO P car's (11 ft and 3 ft). How tightly it turns is CALIBRATED, not
looked up: :data:`TURN_FT` is the turning radius of the outer front wheel
for which the ordinary 90-degree module -- 9 x 18 ft stalls on a 24 ft
two-way aisle, the design's own and the commonest figure in the corpus --
lets a car back out of a stall and drive away, and a 22 ft aisle does not.
That is the car the stall tables were drawn for; AASHTO's highway P car
(24 ft) cannot back out of that module at all, which is why it is not used.
``flats/tests/test_turning.py`` pins both halves of the calibration.

**The search.** A hybrid A* over the car's rear-axle pose: arcs of fixed
length at five steering settings, forward or reverse, the car's body tested
against the open ground (:func:`shapely.contains`) at three points along
every arc. ``phases`` is the sequence of directions a manoeuvre may use --
``(-1, 1)`` is "back out once, then drive away", ``(-1, 1, -1, 1)`` a
three-point turn. A path it FINDS is a real path (every pose was tested);
a path it does not find may still exist between the lattice's cells, so a
"no" errs toward refusing, never toward passing.

**What it found (2026-10-02), and why it is not wired in.** On today's court
(12 ft lane, 24 ft aisle, four 9 x 18 stalls, the row against the lane, the
5 ft standoff off the rear wall unpaved): no stall can be left by backing
out once and driving away -- the turn from the aisle into a 12 ft lane at
the building's corner is a few inches from fitting, and the stalls at the
two ends of a dead-end row have no room to swing. With a three-point turn
allowed every stall can be left, and every stall but the far dead-end one
can be entered nose first. Which of those the screen should demand is
Steph's ruling (FOLLOWUPS 36(2)); until then nothing here moves a verdict.
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
#: Outer front wheel's turning radius, calibrated on the 24 ft aisle (above).
TURN_FT = 22.0

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
    max_poses: int = 200_000,
) -> bool:
    """Whether the car gets from ``start`` to a pose ``arrived`` accepts
    without leaving ``ground``, using the directions in ``phases`` in order
    (each may be skipped to the next, never gone back to). ``toward`` only
    orders the search. False also where ``max_poses`` ran out first."""
    shapely.prepare(ground)
    k = 1.0 / axle_radius_ft(turn_ft)
    kappas = (-k, -k / 2, 0.0, k / 2, k)
    turns = round(2 * math.pi / CELL_RAD)

    def h(x: float, y: float) -> float:
        return 0.0 if toward is None else math.hypot(x - toward[0], y - toward[1])

    frontier = [(h(start.x, start.y), 0.0, start.x, start.y, start.heading, 0)]
    seen: set[tuple[int, int, int, int]] = set()
    while frontier and len(seen) < max_poses:
        _, cost, x, y, t, phase = heapq.heappop(frontier)
        key = (round(x / CELL_FT), round(y / CELL_FT), round(t / CELL_RAD) % turns, phase)
        if key in seen:
            continue
        seen.add(key)
        if phase == len(phases) - 1 and arrived(Pose(x, y, t)):
            return True
        moves = [(phases[phase] * STEP_FT, kk, phase) for kk in kappas]
        if phase + 1 < len(phases):
            moves += [(phases[phase + 1] * STEP_FT, kk, phase + 1) for kk in kappas]
        arcs = [_arc(x, y, t, kk, d) for d, kk, _ in moves]
        poses = np.array([p for arc in arcs for p in arc])
        clear = shapely.contains(ground, bodies(poses[:, 0], poses[:, 1], poses[:, 2]))
        clear = clear.reshape(len(moves), SAMPLES).all(axis=1)
        for ok, arc, (_, kk, nphase) in zip(clear, arcs, moves):
            if ok:
                nx, ny, nt = arc[-1]
                step = cost + STEP_FT + (0.3 if kk else 0.0) + (3.0 if nphase != phase else 0.0)
                heapq.heappush(frontier, (step + h(nx, ny), step, nx, ny, nt, nphase))
    return False


def facing(heading: float, want: float, within_deg: float) -> bool:
    return abs(((heading - want + math.pi) % (2 * math.pi)) - math.pi) <= math.radians(within_deg)


def parked_in(stall: BaseGeometry, nose: float) -> Callable[[Pose], bool]:
    """Square in ``stall`` (within 3 degrees of ``nose``), wholly inside it."""

    def ok(p: Pose) -> bool:
        if not facing(p.heading, nose, 3.0):
            return False
        return bool(stall.contains(bodies(np.array([p.x]), np.array([p.y]), np.array([p.heading]))[0]))

    return ok


def parked_pose(stall: BaseGeometry) -> Pose:
    """Nose-in, centred, a quarter foot off the stall's far end -- for a
    stall standing north of its aisle (``+y``)."""
    x0, _, x1, y1 = stall.bounds
    return Pose((x0 + x1) / 2, y1 - 0.25 - WHEELBASE_FT - FRONT_OVERHANG_FT, math.pi / 2)


@dataclass(frozen=True, slots=True)
class Court:
    """The pod's rear court in its own frame: ``x`` across the lot with the
    lane on the ``+`` side, ``y`` into the lot, the building's rear wall on
    ``y = 0``. The lane runs ``lane_ft`` wide from ``x = 0`` back to the
    street; the standoff (``gap_ft``) is open ground for the lane only; the
    aisle runs behind the standoff across the row, ``extra_ft`` past it at
    each end; the row of ``stalls`` stands behind the aisle, its outer end
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
        aisle = shapely.box(
            min(left, 0.0), self.gap_ft, self.lane_ft + self.extra_ft, self.gap_ft + self.aisle_ft
        )
        return shapely.union_all([lane, aisle, self.stall(i)])

    def street_end(self) -> Pose:
        """Coming down the lane toward the court."""
        return Pose(self.lane_ft / 2, -self.lane_len_ft + REAR_OVERHANG_FT + 1.0, math.pi / 2)

    def gone(self, p: Pose) -> bool:
        """Driving up the lane toward the street, nose first."""
        return p.y < -self.lane_len_ft + 25.0 and facing(p.heading, -math.pi / 2, 10.0)


def leaves(court: Court, i: int, phases: Sequence[int] = BACK_OUT, **kw: object) -> bool:
    """Whether a car parked nose-in in stall ``i`` gets up the lane nose first."""
    toward = (court.lane_ft / 2, -court.lane_len_ft + 10.0)
    return drive(court.ground(i), parked_pose(court.stall(i)), court.gone, phases, toward=toward, **kw)  # type: ignore[arg-type]


def arrives(court: Court, i: int, phases: Sequence[int] = DRIVE_IN, **kw: object) -> bool:
    """Whether a car coming down the lane gets into stall ``i`` nose first."""
    stall = court.stall(i)
    goal = parked_pose(stall)
    return drive(
        court.ground(i),
        court.street_end(),
        parked_in(stall, math.pi / 2),
        phases,
        toward=(goal.x, goal.y),
        **kw,  # type: ignore[arg-type]
    )
