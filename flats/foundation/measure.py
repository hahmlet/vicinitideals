"""MEASURE layer: everything physical about one lot, computed once from the ground.

No price, no threshold and no foundation sizing is applied here. Every height is
kept as a **drop**: inches below the high point (the highest ground sampled under
the footprint, plus the lump allowance). Because both foundations are set from
that high point (FD6 section 5.2), every wall height, door height, fill depth and
quantity of both methods is the drop plus a setting, so the PRICE layer
(:mod:`flats.foundation.model`, :mod:`flats.foundation.lot`) re-derives them from
this record alone. Re-pricing after a price, a size or a threshold changes needs
the stored record, never the ground.

Only the **geometric** settings (:data:`GEOMETRIC`) are used here: the frame, the
door positions, the sampling and the lump share, and the fill-depth bands. A
record carries them (``geometry``); the price layer refuses a record measured
under different ones ("re-measure").

What is kept (FD6 section 2 and more, for cheap analysis later):

* lot: ground source and cell size, the six readings when there are six, the
  relief given with them and the relief sampled, lump allowance, fall along and
  across the building, the high and low ground, the ground-support inputs
  (ground class, its Urban-land stand-in), frost depth on the lot file, share of
  the pod over a building that stands today, front-face turn;
* per wall line (seven): length, the drop at every station (one per foot), and its
  largest, smallest and mean, and the drop area;
* per door (eight): the drop at the door;
* under the slab (1 ft cells): fill volume, deepest fill, area with fill over each
  of ``fill_bands_in`` (12, 24, 48 in);
* old buildings (FD6 section 5.8, :mod:`flats.foundation.oldbuild`): for each
  building outline under the pod, grown by ``grow_ft``, the stretches of each wall
  line over it (length, whether it reaches a pod corner), the pod floor over it,
  and the year built where held. Attached by :func:`with_old_buildings`.
"""

from __future__ import annotations

import math
import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from flats.foundation.ground import Ground, high_low
from flats.foundation.settings import Settings

#: The settings a measured record depends on. Change one and every record must be
#: re-measured from the ground; change any other and re-pricing the stored records
#: is enough.
GEOMETRIC: tuple[str, ...] = (
    "finished_length_ft",
    "finished_width_ft",
    "length_ft",
    "width_ft",
    "party_x_ft",
    "door_x_ft",
    "station_ft",
    "high_point_along_ft",
    "high_point_across_ft",
    "fill_cell_ft",
    "lump_share",
    "fill_bands_in",
    "grow_ft",
    "corner_within_ft",
)


def geometry_of(s: Settings) -> tuple[tuple[str, object], ...]:
    return tuple((name, getattr(s, name)) for name in GEOMETRIC)


@dataclass(frozen=True, slots=True)
class WallLine:
    name: str
    kind: str  # "long", "end" or "party"
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def length_ft(self) -> float:
        return math.hypot(self.x1 - self.x0, self.y1 - self.y0)

    @property
    def outside(self) -> bool:
        return self.kind != "party"


def wall_lines(s: Settings) -> list[WallLine]:
    """The seven wall lines: front and back (they carry the floors and roof),
    two ends, three party lines -- 285 ft in all on the 80 x 25 ft pod."""
    lines = [
        WallLine("front", "long", 0.0, 0.0, s.length_ft, 0.0),
        WallLine("back", "long", 0.0, s.width_ft, s.length_ft, s.width_ft),
        WallLine("left end", "end", 0.0, 0.0, 0.0, s.width_ft),
        WallLine("right end", "end", s.length_ft, 0.0, s.length_ft, s.width_ft),
    ]
    lines += [WallLine(f"party {x:g}", "party", x, 0.0, x, s.width_ft) for x in s.party_x_ft]
    return lines


def stations(line: WallLine, step_ft: float) -> list[tuple[float, float, float]]:
    """Mid-points along a wall line, with the length each stands for."""
    n = max(1, round(line.length_ft / step_ft))
    seg = line.length_ft / n
    out = []
    for i in range(n):
        f = (i + 0.5) / n
        out.append((line.x0 + (line.x1 - line.x0) * f, line.y0 + (line.y1 - line.y0) * f, seg))
    return out


def door_points(s: Settings) -> list[tuple[str, float, float]]:
    """The eight doors, front then back, left to right."""
    return [(face, x, y) for face, y in (("front", 0.0), ("back", s.width_ft)) for x in s.door_x_ft]


@dataclass(frozen=True, slots=True)
class LineMeasure:
    name: str
    kind: str
    length_ft: float
    #: Drop (in) below the high point at each station, in station order.
    drops_in: tuple[float, ...]
    drop_max_in: float
    drop_min_in: float
    #: Mean of the station drops.
    drop_mean_in: float
    #: Sum of drop x the length each station stands for (ft x in).
    drop_area_ftin: float

    @property
    def outside(self) -> bool:
        return self.kind != "party"


@dataclass(frozen=True, slots=True)
class DoorMeasure:
    face: str
    x_ft: float
    drop_in: float


@dataclass(frozen=True, slots=True)
class Stretch:
    """One stretch of one wall line over an old building's grown outline (model ft)."""

    line: str
    kind: str
    x0: float
    y0: float
    x1: float
    y1: float
    length_ft: float
    #: An end of the stretch is at a pod corner (within ``corner_within_ft``).
    corner: bool


@dataclass(frozen=True, slots=True)
class OldBuilding:
    """One building standing today whose outline, grown by ``grow_ft``, reaches the pod."""

    #: The footprint's own id (RLIS ``BLDG_ID``), or None.
    bldg_id: str | None
    #: The footprint's own year built (RLIS ``YEAR_BUILT``; None when 0 / not held).
    #: Information only: the basement likelihood uses the lot's year (pass 2's source).
    year_built: int | None
    #: The footprint's area (sq ft), before growing.
    area_sf: float
    #: Pod floor over the grown outline (sq ft).
    floor_sf: float
    stretches: tuple[Stretch, ...]

    @property
    def wall_ft(self) -> float:
        return sum(st.length_ft for st in self.stretches)

    @property
    def longest_ft(self) -> float:
        return max((st.length_ft for st in self.stretches), default=0.0)

    @property
    def corner(self) -> bool:
        return any(st.corner for st in self.stretches)


@dataclass(frozen=True)
class Measured:
    """One lot, measured. Flat and storable: see :mod:`flats.foundation.rows`."""

    tlid: str | None
    county: str | None
    ground_source: str
    cell_m: float | None
    #: The six readings (ft) when the ground came from six readings, else None.
    readings: tuple[float, ...] | None
    relief_input_ft: float | None
    #: Highest minus lowest ground sampled under the footprint (lump not included).
    relief_sampled_ft: float
    lump_ft: float
    #: Mean ground at the left end minus at the right end (+ = falls to the right).
    fall_along_ft: float
    #: Mean ground along the front minus along the back (+ = falls to the back).
    fall_across_ft: float
    high_z: float  # sampled high point, lump not included (ft, the ground's datum)
    low_z: float
    #: Lowest ground's drop below the high point with the lump allowance (in).
    low_drop_in: float
    lines: tuple[LineMeasure, ...]
    doors: tuple[DoorMeasure, ...]
    fill_volume_ft3: float
    fill_max_in: float
    #: Footprint area (sq ft) with fill deeper than each of ``fill_bands_in``.
    #: "Fill" here, as in ``fill_volume_ft3`` / ``fill_max_in``, is the reference
    #: model's rock fill: ground below the (lumped) high point. The depth to the
    #: slab's underside is this plus ``slab_top_in - slab_t_in`` (4 in today).
    fill_area_over_sf: tuple[float, ...]
    # ground-support and other lot inputs (decided in the price layer)
    ground_class: str | None
    alt_ground_class: str | None
    frost_register_in: float | None
    bldg_overlap_share: float | None
    front_face_turn_deg: float | None
    geometry: tuple[tuple[str, object], ...]
    #: The lot's year built (assessor, the lot file's ``year_built``), or None.
    year_built: int | None = None
    #: Building outlines were looked for (the footprint layer covers the lot):
    #: False means "not held", not "no old building".
    old_buildings_held: bool = False
    old_buildings: tuple[OldBuilding, ...] = ()

    def line(self, name: str) -> LineMeasure:
        return next(ln for ln in self.lines if ln.name == name)


#: The lot-file fields a record keeps but does not measure.
INPUT_FIELDS = ("relief_input_ft", "ground_class", "alt_ground_class", "frost_register_in", "bldg_overlap_share", "front_face_turn_deg", "year_built")


def with_inputs(m: Measured, inputs: Mapping[str, object]) -> Measured:
    """The record with its lot-file inputs replaced (a grid measured on one machine,
    its lot-file fields joined on another). Only the fields named are changed."""
    conv = {
        "ground_class": _str,
        "alt_ground_class": _str,
        "year_built": _year,
    }
    changes = {k: conv.get(k, _opt)(v) for k, v in inputs.items() if k in INPUT_FIELDS}
    unknown = set(inputs) - set(INPUT_FIELDS)
    if unknown:
        raise ValueError(f"not lot-file inputs: {sorted(unknown)}")
    return dataclasses.replace(m, **changes)


def with_old_buildings(m: Measured, held: bool, buildings: Sequence[OldBuilding]) -> Measured:
    """The record with its old buildings attached (measured by :mod:`flats.foundation.oldbuild`)."""
    return dataclasses.replace(m, old_buildings_held=bool(held), old_buildings=tuple(buildings))


def _fall(ground: Ground, s: Settings) -> tuple[float, float]:
    ny = max(1, round(s.width_ft / s.high_point_across_ft))
    nx = max(1, round(s.length_ft / s.high_point_along_ft))
    ys = [j * s.width_ft / ny for j in range(ny + 1)]
    xs = [i * s.length_ft / nx for i in range(nx + 1)]
    along = sum(ground(0.0, y) - ground(s.length_ft, y) for y in ys) / len(ys)
    across = sum(ground(x, 0.0) - ground(x, s.width_ft) for x in xs) / len(xs)
    return along, across


def measure(
    ground: Ground,
    s: Settings,
    *,
    tlid: str | None = None,
    county: str | None = None,
    inputs: Mapping[str, object] | None = None,
) -> Measured:
    """Measure one lot from its ground. ``inputs`` carries the lot-file fields the
    record keeps but does not measure: ``relief_input_ft``, ``ground_class``,
    ``alt_ground_class``, ``frost_register_in``, ``bldg_overlap_share``,
    ``front_face_turn_deg``, ``year_built``."""
    inputs = dict(inputs or {})
    high, low = high_low(ground, s)
    top = high + ground.lump_ft
    lines = []
    for line in wall_lines(s):
        pts = stations(line, s.station_ft)
        drops = [(top - ground(x, y)) * 12 for x, y, _ in pts]
        lines.append(
            LineMeasure(
                name=line.name,
                kind=line.kind,
                length_ft=line.length_ft,
                drops_in=tuple(drops),
                drop_max_in=max(drops),
                drop_min_in=min(drops),
                drop_mean_in=sum(drops) / len(drops),
                drop_area_ftin=sum(d * seg for (_, _, seg), d in zip(pts, drops, strict=True)),
            )
        )
    doors = tuple(DoorMeasure(face, x, (top - ground(x, y)) * 12) for face, x, y in door_points(s))
    nx = max(1, round(s.length_ft / s.fill_cell_ft))
    ny = max(1, round(s.width_ft / s.fill_cell_ft))
    cell_area = (s.length_ft / nx) * (s.width_ft / ny)
    fill_ft3 = 0.0
    fill_max = 0.0
    over = [0.0] * len(s.fill_bands_in)
    for i in range(nx):
        for j in range(ny):
            d = top - ground((i + 0.5) * s.length_ft / nx, (j + 0.5) * s.width_ft / ny)
            fill_ft3 += d * cell_area
            fill_max = max(fill_max, d * 12)
            for k, band in enumerate(s.fill_bands_in):
                if d * 12 > band + s.tolerance_in:
                    over[k] += cell_area
    along, across = _fall(ground, s)
    readings = getattr(ground, "readings", None)
    return Measured(
        tlid=tlid,
        county=county,
        ground_source=ground.source,
        cell_m=ground.cell_m,
        readings=tuple(readings) if readings is not None else None,
        relief_input_ft=_opt(inputs.get("relief_input_ft")),
        relief_sampled_ft=high - low,
        lump_ft=ground.lump_ft,
        fall_along_ft=along,
        fall_across_ft=across,
        high_z=high,
        low_z=low,
        low_drop_in=(top - low) * 12,
        lines=tuple(lines),
        doors=doors,
        fill_volume_ft3=fill_ft3,
        fill_max_in=fill_max,
        fill_area_over_sf=tuple(over),
        ground_class=_str(inputs.get("ground_class")),
        alt_ground_class=_str(inputs.get("alt_ground_class")),
        frost_register_in=_opt(inputs.get("frost_register_in")),
        bldg_overlap_share=_opt(inputs.get("bldg_overlap_share")),
        front_face_turn_deg=_opt(inputs.get("front_face_turn_deg")),
        geometry=geometry_of(s),
        year_built=_year(inputs.get("year_built")),
    )


def _opt(v: object) -> float | None:
    return None if v is None else float(v)  # type: ignore[arg-type]


def _str(v: object) -> str | None:
    return None if v is None or v == "" else str(v)


def _year(v: object) -> int | None:
    """A year built; blank, zero or not a number is None (not held)."""
    try:
        y = int(float(v))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return y if y > 0 else None
