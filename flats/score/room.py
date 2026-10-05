"""How much bigger the pod could be on this lot, each way (FOLLOWUPS 37(ii)).

The fit check's own room runs one way: how much longer the run the building
and its parking stand on could be, at the width they were searched at. Steph,
2026-10-05: *"If we're getting room left, we need all dimensions. How would
this handle oddly shaped lots?"* So three numbers, each searched on the lot's
own shape (the envelope, every angle the fit was allowed) for the plan the
screen took -- the court behind the building, the column along a side alley,
or the court beside it -- with that plan's parking charged the way the fit
charges it:

- **across**: how much the building's side across the search could grow, at
  the run it needs (:meth:`flats.fit.rectangle.Fitter.widest`);
- **along**: how much its run could grow, at the width it needs -- the fit
  check's own room where the court's depth does not move with the building;
- **both**: how much it could grow both ways at once, by the same amount.

On a rectangle ``both`` is the smaller of the other two. On an odd lot -- a
wedge, an L, a lot that narrows to the rear -- it can be less: room to be
wider up front and room to be longer down the narrow leg, but not the two in
one rectangle. That gap is the tight-shape signal the pod report counts.

:class:`Room` gives the three in the pod's own terms (its width, the side
along the front, and its depth), turned from the orientation the fit took.

Data only: nothing here is read by the colour. Every number is one the lot
was asked at and held (a lower bound, like the fit's own margin): searched in
the orientation the fit took, so a pod that would hold wider only turned the
other way reads the smaller room, and capped at :data:`ROOM_CAP_FT`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from flats.designs.model import Design, Orientation
from flats.fit.rectangle import Fit, Fitter
from flats.rules.resolver import ZoneResolution
from flats.score.paper import Alley, court_across, side_court
from flats.score.screen import (
    _beside_beyond,
    _beside_over,
    _court_beyond_rear,
    _court_over,
    _fix,
)

#: The most room reported, in feet: past it a pod design question is not
#: close, and the search for room both ways stops there.
ROOM_CAP_FT = 40.0


@dataclass(frozen=True, slots=True)
class Room:
    """How much each of the pod's sides could grow and still fit, in feet."""

    #: Its width, the side along the front (:attr:`Footprint.width_ft`).
    width_ft: float
    #: Its depth.
    depth_ft: float
    #: Both at once, by the same amount.
    both_ft: float


@dataclass(frozen=True, slots=True)
class _Plan:
    """The plan the fit took, as a search: the window it asks with the
    building's side across grown by ``s`` and its run grown by ``t``."""

    #: The building's side across plus what its parking adds beside it.
    base_ft: float
    #: The narrowest the window may be whatever the building (the court
    #: behind it, its stalls side by side).
    floor_ft: float
    #: The window's run for the building ``t`` deeper: its depth and what
    #: the court asks past its rear wall.
    run: Callable[[float], float]
    #: How far the court runs past that window onto its ground.
    over: Callable[[float], float]
    #: Where the court's depth past the wall does not move with the
    #: building's: the fit's own room along is then the answer.
    fixed: bool
    angles: tuple[float, ...] | None

    def across(self, s: float) -> float:
        return max(self.base_ft + s, self.floor_ft)


def _plan(
    design: Design,
    rules: ZoneResolution,
    fit: Fit,
    side: float,
    deep: float,
    *,
    carved_rear_ft: float | None,
    alley: Alley | None,
    corner: bool,
    frontage_ft: float | None,
    street_deg: tuple[float, ...],
) -> _Plan | None:
    """``fit``'s plan, charged as :func:`flats.score.screen.fit_for` and the
    fit check charge it."""
    if fit.beside:
        court = side_court(design, rules, alley, corner=corner, frontage_ft=frontage_ft)
        if court is None or not street_deg:
            return None
        return _Plan(
            base_ft=side + court.band_ft,
            floor_ft=0.0,
            run=lambda t: deep + t + _beside_beyond(court, deep + t, rules, carved_rear_ft),
            over=lambda t: _beside_over(court, deep + t, rules, carved_rear_ft),
            fixed=False,
            angles=street_deg,
        )
    if fit.column:
        lane = court_across(design, rules, alley, corner=corner).lane_ft
        beyond = _court_beyond_rear(design, rules, carved_rear_ft, alley, column=True)
        over = _court_over(design, rules, carved_rear_ft, alley, column=True)
        return _Plan(
            base_ft=side + lane,
            floor_ft=0.0,
            run=lambda t: deep + t + beyond,
            over=lambda _t: over,
            fixed=True,
            angles=None,
        )
    fix = _fix(fit)
    court = court_across(design, rules, alley, corner=corner, fix=fix)
    beyond = _court_beyond_rear(design, rules, carved_rear_ft, alley, corner=corner, fix=fix)
    over = _court_over(design, rules, carved_rear_ft, alley, corner=corner, fix=fix)
    return _Plan(
        base_ft=side + court.lane_ft,
        floor_ft=court.width_ft,
        run=lambda t: deep + t + beyond,
        over=lambda _t: over,
        fixed=True,
        angles=None,
    )


def _most(ok: Callable[[float], bool], hi: float, step: float) -> float:
    """The most of ``[0, hi]`` that ``ok`` holds at, in ``step``s: ``hi``
    itself first (on a lot with room to spare the first answer), then the
    steps below it. ``ok(0)`` is taken as held -- the fit that was found."""
    if hi <= 0:
        return 0.0
    if ok(hi):
        return hi
    lo, top = 0, math.ceil(hi / step - 1e-9) - 1
    while lo < top:
        mid = (lo + top + 1) // 2
        if ok(mid * step):
            lo = mid
        else:
            top = mid - 1
    return lo * step


def room_for(
    fitter: Fitter,
    design: Design,
    rules: ZoneResolution,
    fit: Fit,
    *,
    carved_rear_ft: float | None = None,
    alley: Alley | None = None,
    corner: bool = False,
    frontage_ft: float | None = None,
    street_deg: tuple[float, ...] = (),
) -> Room | None:
    """How much bigger the pod ``fit`` placed could be, each way.

    The arguments are the ones :func:`flats.score.screen.fit_for` was given
    for ``fit``. ``None`` where the fit did not pass outright (a near miss,
    inside the tolerance or not, has no room to report) or the plan it took
    cannot be read back.
    """
    if fitter.empty or fit.orientation is None or fit.across_ft is None:
        return None
    w, d = design.footprint.width_ft, design.footprint.depth_ft
    if fit.orientation is Orientation.width_facing:
        side, deep = w, d
    else:
        side, deep = d, w
    plan = _plan(
        design, rules, fit, side, deep,
        carved_rear_ft=carved_rear_ft, alley=alley, corner=corner,
        frontage_ft=frontage_ft, street_deg=street_deg,
    )
    if plan is None or abs(plan.across(0.0) - fit.across_ft) > 1e-6:
        # Not the search this fit came from: its room would be some other
        # plan's.
        return None
    step = fitter.res

    def holds(s: float, t: float) -> bool:
        return fitter.holds(plan.across(s), plan.run(t), angles=plan.angles, over_ft=plan.over(t))

    if plan.fixed:
        along = fit.best_depth_ft - plan.run(0.0)
        if along < 0:
            return None
        along = min(along, ROOM_CAP_FT)
    else:
        if not holds(0.0, 0.0):
            return None
        along = _most(lambda t: holds(0.0, t), ROOM_CAP_FT, step)
    widest = fitter.widest(plan.run(0.0), angles=plan.angles, over_ft=plan.over(0.0))
    across = min(max(0.0, widest - plan.base_ft), ROOM_CAP_FT)
    both = _most(lambda u: holds(u, u), min(across, along), step)
    if fit.orientation is Orientation.width_facing:
        return Room(width_ft=across, depth_ft=along, both_ft=both)
    return Room(width_ft=along, depth_ft=across, both_ft=both)
