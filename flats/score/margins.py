"""How much room each standard a lot passes had to spare (FOLLOWUPS 37(ii)).

The screen measures every check's slack, pass or fail
(:mod:`flats.score.slack`), but the bridge kept only the fit's, and the
misses as binds. The pod design report (``/flats/flags/report``) asks the
other question: on the lots the pod passes, which limits come close, and
which would stop a bigger or a taller pod first. That needs the room on the
passes too, so the bridge writes it here, beside the answer.

**Data only.** Nothing the colour reads comes from this module: the screen
hands over checks it already made, and the record is written next to them.
Storing it moves no lot.

The record is ``{check: [observed, threshold, slack]}`` over every check the
lot passes, each in the check's own units (feet, percent of the lot, a ratio,
homes an acre), rounded to :data:`DIGITS` places; ``''`` when nothing passed.
A list rather than an object because the county carries it on every lot and
design, and the keys of an object are stored on every row.

What a change to the pod does to a measurement is :func:`after`. Only the
checks a bigger footprint or a taller building move are modelled; every other
standard (the lot's own size, width and depth, density, the parking) is the
same whatever the pod's size, and reads as unmoved.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from flats.score.slack import CheckResult, Verdict

#: Decimal places the record keeps: a thousandth of a foot, of a percent, of
#: a ratio -- finer than anything measured, and short on the wire.
DIGITS = 3


@dataclass(frozen=True, slots=True)
class Margin:
    """One standard a lot passed, and how close it came."""

    check: str
    #: What the lot and pod measured, and the limit, in the check's units.
    observed: float
    threshold: float
    #: Room to spare in the same units; never negative on a pass.
    slack: float

    @property
    def share(self) -> float | None:
        """The room as a share of the limit, so feet and ratios compare:
        0.05 is five percent of the limit to spare. None on a limit of 0."""
        if self.threshold == 0:
            return None
        return self.slack / abs(self.threshold)


def passing(checks: Iterable[CheckResult]) -> tuple[CheckResult, ...]:
    """The checks a lot passes outright -- not those inside a tolerance,
    which are misses the flag record already carries."""
    return tuple(c for c in checks if c.verdict is Verdict.passes)


def _num(v: float) -> float:
    out = round(float(v), DIGITS)
    return 0.0 if out == 0 else out


def record(checks: Iterable[CheckResult]) -> dict[str, list[float]]:
    """The record for one lot and design (see the module docstring)."""
    return {
        c.check: [_num(c.observed), _num(c.threshold), _num(c.slack)]
        for c in passing(checks)
        if math.isfinite(c.observed) and math.isfinite(c.threshold)
    }


def dumps(checks: Iterable[CheckResult]) -> str:
    """The bridge column: compact JSON, ``''`` when nothing passed."""
    got = record(checks)
    return json.dumps(got, separators=(",", ":"), sort_keys=True) if got else ""


def loads(raw: Any) -> dict[str, Margin]:
    """A stored record back to :class:`Margin` per check; ``{}`` for none.
    Takes the JSON text or the decoded mapping (a ``jsonb`` column comes
    back either way, depending on the driver)."""
    if raw is None or raw == "":
        return {}
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, Mapping):
        raise ValueError(f"margins: expected a mapping, got {type(raw).__name__}")
    out: dict[str, Margin] = {}
    for check, value in raw.items():
        observed, threshold, slack = (float(v) for v in value)
        out[str(check)] = Margin(str(check), observed, threshold, slack)
    return out


# --- what a bigger or taller pod does to a measurement ----------------------
#
# The footprint is a rectangle (:class:`flats.designs.model.Footprint`), so a
# pod grown along one side adds that many feet times the other side. Each
# check below moves with it one of three ways:
#
# * ``scales`` -- the building over the land: coverage, and floor area over
#   the lot (FAR is the footprint times the storeys, over the same area
#   whether that area is the lot or a net acre), so the measurement grows in
#   proportion to the footprint;
# * ``adds`` -- buildings and paving together over the lot (King City's
#   impervious cap): the extra footprint, as a share of the lot, is added;
# * ``takes`` -- what is left of the lot for open space or landscaping: the
#   extra footprint is taken off, as a share of the lot or in square feet.

#: Check name -> (how the footprint moves it, whether the limit is a ceiling).
FOOTPRINT: dict[str, tuple[str, bool]] = {
    "coverage_pct": ("scales", True),
    "far": ("scales", True),
    "impervious_pct": ("adds_pct", True),
    "landscaped_pct": ("takes_pct", False),
    "open_space_pct": ("takes_pct", False),
    "open_space_sqft": ("takes_sqft", False),
}

#: Check name -> whether the limit is a ceiling, for the checks a taller
#: building moves foot for foot. Storeys are counted, not measured, so a
#: few feet taller leaves them where they are.
HEIGHT: dict[str, bool] = {"height_ft": True, "min_height_ft": False}


@dataclass(frozen=True, slots=True)
class Change:
    """A change to the pod, as the report tries it on a lot.

    ``extra_sqft`` is the footprint added (negative: taken off) on a
    footprint of ``ground_sqft``, on a lot of ``lot_sqft``; ``taller_ft``
    the height added. A lot whose area is not known moves only the checks
    that need no area."""

    extra_sqft: float = 0.0
    ground_sqft: float = 0.0
    lot_sqft: float | None = None
    taller_ft: float = 0.0


def grown(step_ft: float, run_ft: float | None, width_ft: float, depth_ft: float) -> float | None:
    """The footprint a pod gains when the side the fit measured along the
    lot (``run_ft``, :attr:`flats.fit.rectangle.Fit.required_ft`) grows by
    ``step_ft``: the step times the other side. None where the fit
    recorded no run."""
    if run_ft is None:
        return None
    other = width_ft if abs(run_ft - depth_ft) <= abs(run_ft - width_ft) else depth_ft
    return step_ft * other


def after(check: str, observed: float, change: Change) -> float | None:
    """What ``check`` measures after ``change``; None where the change does
    not move it, or moves it by an amount not known here."""
    if change.taller_ft and check in HEIGHT:
        return observed + change.taller_ft
    how = FOOTPRINT.get(check, (None, True))[0]
    if not change.extra_sqft or how is None:
        return None
    if how == "scales":
        if change.ground_sqft <= 0:
            return None
        return observed * (change.ground_sqft + change.extra_sqft) / change.ground_sqft
    if how == "takes_sqft":
        return observed - change.extra_sqft
    if not change.lot_sqft or change.lot_sqft <= 0:
        return None
    pct = change.extra_sqft / change.lot_sqft * 100.0
    return observed + pct if how == "adds_pct" else observed - pct


def ceiling(check: str) -> bool:
    """Whether ``check``'s limit is a ceiling; for the checks :func:`after`
    moves."""
    if check in HEIGHT:
        return HEIGHT[check]
    return FOOTPRINT[check][1]


def shortfall(check: str, observed: float, threshold: float) -> float:
    """How far ``observed`` misses ``threshold``; 0 on a pass."""
    slack = (threshold - observed) if ceiling(check) else (observed - threshold)
    return max(0.0, -slack)


__all__ = [
    "Change",
    "DIGITS",
    "FOOTPRINT",
    "HEIGHT",
    "Margin",
    "after",
    "ceiling",
    "dumps",
    "grown",
    "loads",
    "passing",
    "record",
    "shortfall",
]
