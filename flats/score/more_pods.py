"""The minimum floor area rule's rough count of the pods it needs."""

from __future__ import annotations

import math


def clearly_cannot_fit(
    required_floor_sqft: float,
    one_pod_floor_sqft: float,
    footprint_sqft: float,
    buildable_sqft: float | None,
) -> bool:
    """Whether even an area-only packing cannot hold the required pods."""
    values = (required_floor_sqft, one_pod_floor_sqft, footprint_sqft)
    if buildable_sqft is None or any(not math.isfinite(value) or value <= 0 for value in values):
        return False
    if not math.isfinite(buildable_sqft) or buildable_sqft < 0:
        return False
    pods = max(2, math.ceil(required_floor_sqft / one_pod_floor_sqft))
    return buildable_sqft < pods * footprint_sqft
