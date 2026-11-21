"""How close the drawn drive lane comes to a lot line that is not a street,
against a code's floor on it (FOLLOWUPS 201 add-on G).

Beaverton BDC Table 60.05.60.2 S12: "driveways may be located as close as 3
or 6 feet from property lines depending on sidewalk type classified by the
EDM" (``beaverton/60.05/60.05.60.txt#L397-L399``). The sidewalk type is not
held, so the figure is an unmeasured site fact: the screen asks the larger
figure for GREEN. The figures live in ``flats/config/driveway_lot_line.yaml``.

:func:`measure` reads one drawing: the lane's gap to the nearest such line,
and how far the plan could slide away from that line before the building
(its side setback) or the court (its own clearance) meets the first line
opposite (any stretch of the far side, so a jog stops the slide).
A plan drawn hugging a line with room to spare is not held for where the
drawing happened to put it.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from flats.geom.edges import EdgeClass, LotEdges, bearing_delta

CONFIG = Path(__file__).resolve().parents[1] / "config" / "driveway_lot_line.yaml"

#: Lines within this many degrees of the nearest line are taken as the one
#: opposite it, the line the plan slides toward.
PARALLEL_DEG = 30.0


#: What a place may say a plan short of its smaller figure is: RED (the
#: standard fails, Beaverton) or YELLOW (the code offers a way out the screen
#: cannot weigh -- Gladstone's shared driveway, PWDS 5.0070(D)(5)).
MISSES = frozenset({"red", "yellow"})
#: The lot lines a place's figures keep the lane off, by edge class.
LINES = frozenset({"side", "rear"})


@dataclass(frozen=True, slots=True)
class Place:
    zones: frozenset[str]
    figures_ft: tuple[float, ...]
    unmeasured: str
    quote: str
    #: Edge classes measured to (default side and rear lines).
    lines: frozenset[str] = LINES
    #: What a plan short of the smaller figure is (see :data:`MISSES`).
    miss: str = "red"


def _figures(place: str, body: Any) -> tuple[float, ...]:
    """The figures as printed, or derived from what is printed: a curb cut's
    ``offset_ft`` off the line plus each approach wing it may have
    (``wings_ft``), since the cut is measured wing to wing and the screen
    draws only the lane, the throat between the wings."""
    if "figures_ft" in body:
        return tuple(sorted(float(f) for f in body["figures_ft"]))
    offset = float(body["offset_ft"]["value"])
    wings = [float(w["value"]) for w in body["wings_ft"]]
    if not wings:
        raise ValueError(f"{place}: wings_ft is empty")
    return tuple(sorted(offset + w for w in wings))


@functools.lru_cache(maxsize=1)
def load(path: Path = CONFIG) -> dict[str, Place]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: dict[str, Place] = {}
    for place, body in (doc.get("places") or {}).items():
        lines = frozenset(str(x) for x in body.get("lines") or LINES)
        miss = str(body.get("miss") or "red")
        if not lines <= LINES or not lines:
            raise ValueError(f"{place}: lines must be among {sorted(LINES)}")
        if miss not in MISSES:
            raise ValueError(f"{place}: miss must be one of {sorted(MISSES)}")
        out[str(place)] = Place(
            zones=frozenset(str(z).upper() for z in body.get("zones") or ()),
            figures_ft=_figures(str(place), body),
            unmeasured=" ".join(str(body.get("unmeasured") or "").split()),
            quote=str(body["quote"]),
            lines=lines,
            miss=miss,
        )
    return out


def place_for(layer_id: str | None, zone: str | None) -> Place | None:
    """The floor that reaches a lot in ``zone`` of ``layer_id``, or None."""
    got = load().get(str(layer_id or ""))
    if got is None or (got.zones and str(zone or "").upper() not in got.zones):
        return None
    return got


@dataclass(frozen=True, slots=True)
class Gap:
    #: The drawn lane's gap to the nearest lot line that is not a street.
    drawn_ft: float
    #: The most that gap could be with the plan slid away from that line;
    #: None where no line opposite it was found (nothing measured the slide).
    reach_ft: float | None


def measure(
    edges: LotEdges,
    lane: Any,
    building: Any,
    court: Any | None,
    *,
    building_clear_ft: float,
    court_clear_ft: float,
    lines_of: frozenset[str] = LINES,
) -> Gap | None:
    """The lane's :class:`Gap`, or None where the lot has no line that is not
    a street or an alley (nothing to keep the drive off). ``lines_of`` names
    the edge classes measured to (``side``, ``rear``)."""
    from shapely import get_coordinates
    from shapely.geometry import LineString

    classes = tuple(c for c in (EdgeClass.side, EdgeClass.rear) if c.value in lines_of)
    lines = [
        (e, LineString(((e.x1, e.y1), (e.x2, e.y2))))
        for e in edges.edges
        if e.cls in classes and not e.alley
    ]
    if not lines:
        return None
    gaps = [lane.distance(line) for _, line in lines]
    i = min(range(len(lines)), key=gaps.__getitem__)
    near_edge, near = lines[i]
    # Offsets square off the near line, positive toward the plan: a line is
    # opposite where it stands past the far side of the building (and the
    # court), so a piece of the near side itself (collinear, not touching)
    # is never one. The slide stops at the FIRST such line: on a lot with a
    # jog, a farther stretch of the far side is not room the building has
    # (bvt-drive-side; the farthest line alone over-credited a stepped lot).
    ux, uy = near_edge.x2 - near_edge.x1, near_edge.y2 - near_edge.y1
    norm = (ux * ux + uy * uy) ** 0.5 or 1.0
    nx, ny = -uy / norm, ux / norm
    centre = building.centroid
    if (centre.x - near_edge.x1) * nx + (centre.y - near_edge.y1) * ny < 0:
        nx, ny = -nx, -ny

    def offset(x: float, y: float) -> float:
        return (x - near_edge.x1) * nx + (y - near_edge.y1) * ny

    plan = [building] + ([court] if court is not None and not court.is_empty else [])
    beyond = max(offset(float(x), float(y)) for g in plan for x, y in get_coordinates(g))
    opposite = [
        line
        for j, (e, line) in enumerate(lines)
        if j != i
        and bearing_delta(e.bearing_deg, near_edge.bearing_deg) <= PARALLEL_DEG
        and line.distance(near) > 0
        and max(offset(*line.coords[0]), offset(*line.coords[-1])) > beyond
    ]
    if not opposite:
        return Gap(gaps[i], None)
    room = min(building.distance(line) for line in opposite) - building_clear_ft
    if court is not None and not court.is_empty:
        room = min(room, min(court.distance(line) for line in opposite) - court_clear_ft)
    return Gap(gaps[i], gaps[i] + max(0.0, room))
