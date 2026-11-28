"""The main entrance within 4 feet of grade (FOLLOWUPS 64 round 5, fg5 F3).

Portland PCC 33.110.230.D (R10 to R2.5) and 33.120.231.D (the multi-dwelling
zones): "the main entrance that meets Subsection C must be within 4 feet of
grade. For the purposes of this Subsection, grade is the average grade
measured at the outer most corners of the street facing façade"
(``flats/config/entrance_grade.yaml`` holds the rules, their quotes and the
zones they reach).

Worked in the screen's foundation pass (:mod:`flats.ingest.foundation_cap`)
on the floor level and the ground model the six-step cap reads: the entrance
stands at the floor, and the floor is the lowest of the foundation methods
open to the lot that clear the cap. The pod is a row of attached houses, each
home its own structure with its own main entrance (33.120.231.D names
attached houses), so the limit is measured per home: the average of the
ground at the two outer corners of that home's street-facing wall
(:func:`entrance_facts`). The whole building's figure (the fourplex reading)
is kept beside it.

* over the limit by more than the ground model's error (the six-step cap's
  ``near_cap_in``) where every exemption is ruled out: RED;
* over it by that error or less, or over it where an exemption is not read:
  YELLOW, never GREEN;
* under it, or exempt: nothing.
"""

from __future__ import annotations

import functools
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

CONFIG = Path(__file__).resolve().parents[1] / "config" / "entrance_grade.yaml"

#: :func:`entrance_facts` states.
OVER = "over"
HELD = "held"
EXEMPT = "exempt"
FITS = "fits"


@dataclass(frozen=True, slots=True)
class Rule:
    section: str
    max_in: float
    quote: str
    says: str
    exemptions: str
    applies_to: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Rules:
    rules: tuple[Rule, ...]
    slope_exempt_pct: float
    slope_band_pct: float
    flood_keys: frozenset[str]


@functools.lru_cache(maxsize=2)
def load(path: Path = CONFIG) -> Rules:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rules = tuple(
        Rule(
            section=str(r["section"]),
            max_in=float(r["max_ft"]) * 12.0,
            quote=str(r["quote"]),
            says=str(r["says"]),
            exemptions=str(r["exemptions"]),
            applies_to=tuple(str(p) for p in r["applies_to"]),
        )
        for r in doc.get("rules") or ()
    )
    return Rules(
        rules=rules,
        slope_exempt_pct=float(doc["slope_exempt_pct"]),
        slope_band_pct=float(doc["slope_band_pct"]),
        flood_keys=frozenset(str(k) for k in doc.get("flood_keys") or ()),
    )


def rule_for(resolution: Any, rules: Rules | None = None) -> Rule | None:
    """The grade rule the zone's main-entrance standard carries, or None:
    the resolved ``entrance_faces_street`` is ``required`` or
    ``required_named`` and its quote lies in a section a rule reaches."""
    rules = load() if rules is None else rules
    try:
        if resolution.get("entrance_faces_street") not in ("required", "required_named"):
            return None
        value = resolution.values.get("entrance_faces_street")
    except AttributeError:
        return None
    quote = str(getattr(getattr(value, "prov", None), "quote", None) or "")
    for rule in rules.rules:
        if any(quote.startswith(p) for p in rule.applies_to):
            return rule
    return None


def exemption(observed: Mapping[str, Any], permits: Sequence[str], rules: Rules | None = None) -> str | None:
    """Whether a flag-lot or flood exemption may reach the lot: ``exempt``
    where it is read to, ``unread`` where it is not ruled out, None where
    both are ruled out. The slope exemption is measured on the ground
    (:func:`slope_state`)."""
    rules = load() if rules is None else rules
    if any(k in rules.flood_keys for k in permits) or observed.get("in_floodplain") is True:
        return "exempt"
    if observed.get("pdx_flag_lot") is not False or observed.get("in_floodplain") is not False:
        return "unread"
    return None


def lot_slope_pct(dem: Any, lot: Any, toward: tuple[float, float], step_ft: float = 5.0) -> float | None:
    """The lot's average slope up or down from the street, in percent: a
    plane fitted to the elevation model over the lot, read along ``toward``
    (the direction from the street into the lot). None where nothing reads
    the lot."""
    import numpy as np
    import shapely

    if dem is None or lot is None or lot.is_empty:
        return None
    part = max(getattr(lot, "geoms", None) or (lot,), key=lambda g: g.area)
    ring = [list(c) for c in part.exterior.coords]
    minx, miny, maxx, maxy = part.bounds
    step = max(step_ft, math.sqrt(max(part.area, 1.0) / 900.0))
    gx, gy = np.meshgrid(np.arange(minx + step / 2, maxx, step), np.arange(miny + step / 2, maxy, step))
    pts = np.c_[gx.ravel(), gy.ravel()]
    if not len(pts):
        return None
    pts = pts[shapely.contains_xy(part, pts[:, 0], pts[:, 1])]
    if len(pts) < 6:
        return None
    z = None
    for coarse in (False, True):
        z_of, _src, _cell = dem.z_reader(ring, coarse=coarse)
        if z_of is None:
            continue
        got = np.asarray(z_of(pts), dtype=float)
        if np.isfinite(got).mean() >= 0.9:
            z = got
            break
    if z is None:
        return None
    ok = np.isfinite(z)
    a = np.c_[np.ones(int(ok.sum())), pts[ok, 0], pts[ok, 1]]
    coef, *_ = np.linalg.lstsq(a, z[ok], rcond=None)
    n = math.hypot(*toward)
    if n <= 0:
        return None
    return abs(float(coef[1]) * toward[0] / n + float(coef[2]) * toward[1] / n) * 100.0


def slope_state(pct: float | None, rules: Rules | None = None) -> str | None:
    """``exempt`` (the lot averages 20 percent or more past the error),
    ``unread`` (unmeasured, or within the error of 20 percent), or None (it
    plainly does not)."""
    rules = load() if rules is None else rules
    if pct is None:
        return "unread"
    if pct >= rules.slope_exempt_pct + rules.slope_band_pct:
        return "exempt"
    if pct > rules.slope_exempt_pct - rules.slope_band_pct:
        return "unread"
    return None


def entrance_facts(
    ground: Any,
    *,
    length_ft: float,
    homes: int,
    per_home: bool,
    facade_y: float,
    floors: Sequence[tuple[str, float]],
    rule: Rule,
    near_in: float,
    exempt: str | None,
    slope_of: Callable[[], float | None],
    rules: Rules | None = None,
) -> dict[str, Any]:
    """The limit on one drawn building, as plain facts.

    ``ground(x, y)`` is the ground (ft) in the measured frame, whose
    street-facing wall runs along ``y = facade_y`` from ``x = 0`` to
    ``length_ft``. ``floors`` holds the floor (ft, the ground's datum) on
    each foundation method the lot may be built on, the one it is screened
    on first: the entrance stands at the floor, and the state is the worst
    of them. ``per_home`` measures each of ``homes`` attached homes as its
    own structure (the townhouse form); otherwise the building is one
    structure (the fourplex), its grade the average at the wall's two ends.
    ``exempt`` is :func:`exemption`'s answer; ``slope_of`` reads the lot's
    slope, asked only where the limit is passed."""
    rules = load() if rules is None else rules
    homes = max(1, int(homes))
    xs = [length_ft * k / homes for k in range(homes + 1)]
    zs = [float(ground(x, facade_y)) for x in xs]
    grades = [(zs[k] + zs[k + 1]) / 2.0 for k in range(homes)] if per_home else [(zs[0] + zs[-1]) / 2.0]

    def worst(floor_z: float) -> tuple[int, float]:
        hs = [abs(floor_z - g) * 12.0 for g in grades]
        k = max(range(len(hs)), key=lambda i: hs[i])
        return k, hs[k]

    method, floor_z = max(floors, key=lambda f: f[1])
    at, height = worst(floor_z)
    low_method, low_z = floors[0]
    _, first = worst(low_z)
    over_by = height - rule.max_in
    who = f"home {at + 1} of {homes}" if per_home else "the building"
    where = (f"{who}: the entrance, at the floor on {method}, stands {height:.1f} in from the average of the "
             f"ground at the outer corners of its street-facing wall")
    base: dict[str, Any] = {
        "section": rule.section, "quote": rule.quote, "limit_in": rule.max_in, "height_in": round(height, 1),
        "over_by_in": round(over_by, 1), "per_home": per_home, "home": at + 1 if per_home else None,
        "homes": homes, "method": method, "screened_in": round(first, 1), "exemption": exempt,
        "slope_pct": None,
    }
    limit = f"{rule.section}'s {rule.max_in / 12:g} ft ({rule.max_in:g} in) limit"
    if over_by <= 0:
        return {**base, "state": FITS, "words": f"main entrance: within {limit} ({where})"}
    pct = slope_of()
    slope = slope_state(pct, rules)
    base["slope_pct"] = None if pct is None else round(pct, 1)
    if "exempt" in (exempt, slope):
        why = "a 20 percent average slope from the street" if slope == "exempt" else "the combined flood hazard area"
        return {**base, "state": EXEMPT, "exemption": "exempt",
                "words": f"main entrance: over {limit} by {over_by:.1f} in ({where}), but the lot is exempt on "
                         f"{why} ({rule.exemptions})"}
    unread = "unread" in (exempt, slope)
    base["exemption"] = "unread" if unread else None
    if over_by <= near_in or unread or first <= rule.max_in:
        if over_by <= near_in:
            why = "ground heights are good to an inch or two"
        elif first <= rule.max_in:
            why = (f"on {low_method}, the floor the lot is screened on, it is within; the ground class is not "
                   f"read, and ground that needs {method} would put it over")
        else:
            parts = []
            if exempt == "unread":
                parts.append("whether it is a flag lot or in the combined flood hazard area")
            if slope == "unread":
                parts.append("whether it slopes 20 percent or more from the street"
                             + ("" if pct is None else f" (it reads {pct:.1f} percent)"))
            why = f"{' or '.join(parts)} is not read, and either exempts it ({rule.exemptions})"
        return {**base, "state": HELD,
                "words": f"main entrance: over {limit} by {over_by:.1f} in ({where}); {why}, so yellow, not red"}
    return {**base, "state": OVER,
            "words": f"main entrance: over {limit} by {over_by:.1f} in ({where}), and no exemption reaches the "
                     f"lot (it slopes {pct:.1f} percent from the street)"}


__all__ = ["CONFIG", "EXEMPT", "FITS", "HELD", "OVER", "Rule", "Rules", "entrance_facts", "exemption", "load",
           "lot_slope_pct", "rule_for", "slope_state"]
