"""Which rotations to test a pod at.

Two regimes, and the difference is a code question, not a geometry one.

*Free orientation.* Nothing in the code says which way the building faces, so
the pod may sit at any angle. The search space is a sweep — and it is only half
a circle wide, because a rectangle rotated 180° maps onto itself. Testing 180°
through 360° would re-test placements already found, at double the cost.

*Fixed orientation.* The code (or the product) requires the building to face
the street. Then the only candidate angles are the lot's frontage bearings, and
a pod that does not fit facing the street does not fit.

The sweep step is a real accuracy knob, not a performance detail: a step of 5°
can miss a pod that only fits within a 3° window on a skewed lot. Missing it
produces a false RED, which is the failure this project is built to avoid, so
the default is fine-grained and the cost is paid.
"""

from __future__ import annotations

from typing import Iterable

#: A rectangle is unchanged by a half turn, so this is the whole search space.
SWEEP_SPAN_DEG = 180.0

#: 1° steps. At the far end of a 60 ft pod, one degree is about 1 ft of travel —
#: the same order as the raster cell, so a finer step would resolve detail the
#: rasterizer cannot see anyway.
DEFAULT_STEP_DEG = 1.0


def normalize(angle_deg: float) -> float:
    """Fold an angle into [0, 180) — the range where rectangles are distinct."""
    return angle_deg % SWEEP_SPAN_DEG


def sweep(step_deg: float = DEFAULT_STEP_DEG) -> tuple[float, ...]:
    """Evenly spaced angles covering every distinct rectangle orientation."""
    if step_deg <= 0:
        raise ValueError(f"sweep step must be positive, got {step_deg}")
    if step_deg > SWEEP_SPAN_DEG:
        raise ValueError(f"sweep step {step_deg} exceeds the {SWEEP_SPAN_DEG}° search space")
    n = int(SWEEP_SPAN_DEG / step_deg)
    return tuple(round(i * step_deg, 6) for i in range(n))


def angles_for(
    bearings: Iterable[float] = (),
    *,
    axis_required: bool = False,
    step_deg: float = DEFAULT_STEP_DEG,
) -> tuple[float, ...]:
    """Candidate angles for one lot.

    ``bearings`` are the lot's frontage bearings in degrees. When
    ``axis_required``, they are the only candidates; otherwise they are added to
    the sweep so the street-facing placement is always among those tested even
    if it falls between sweep steps. A lot with no frontage bearing still gets
    the sweep — being unable to name the front is not a reason to skip the lot.
    """
    folded = [normalize(b) for b in bearings]
    if axis_required:
        return tuple(sorted(set(folded)))
    return tuple(sorted(set(folded) | set(sweep(step_deg))))
