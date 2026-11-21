"""Street centrelines that run through a lot, near the drawn plan (rel11 move
read G2).

A taxlot can be cut by a street it does not own: Clackamas unincorporated
21E11AB01100 (R7) has WALTER (RLIS TYPE 1500, a local street) running 160 ft
through it, and the plan the fit drew stood its parking court 25.8 ft from
that centreline -- inside any local street's right-of-way. Nothing else in the
screen reads a centreline inside the lot: the street lines, their half-widths
and the dedication strip are all read off the lot's own lines
(:mod:`flats.geom.dedication`).

What is counted, so that an ordinary frontage street is not:

* a centreline that is not an alley or a private road or drive (RLIS TYPE
  1600, 1700, 1800: :data:`NOT_STREET`). Every other type is counted, the
  unimproved (2000), forest (9000) and unclassed (8224) lines too: a public
  way not read is taken as one (the conservative answer);
* only the part of it more than :data:`INSET_FT` inside every lot line, and
  more than :data:`FRONT_LINE_FT` from every street lot line: a frontage
  street's centreline runs outside the lot, or, on a lot drawn to the centre
  of the road, along its front line, where the dedication strip reads it;
* only where that part runs at least :data:`MIN_INSIDE_FT`;
* only where the drawn building, lane or court comes within
  :data:`REACH_FT` of it -- so near that the plan may stand on its road land.

Only measures: :func:`flats.ingest.quadfit.street_through_checked` holds the
lot out of GREEN with ``MEASURE-STREET-THROUGH-LOT``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

#: RLIS TYPE codes that are no street: alley (1600), private named road
#: (1700), unnamed private road or driveway (1800) -- the same three
#: :data:`flats.geom.street_end.NOT_PUBLIC` and
#: :data:`flats.geom.dedication.PRIVATE_TYPES` name, less the unimproved and
#: unclassed lines, which are counted here because unread is the
#: conservative answer.
NOT_STREET: frozenset[int] = frozenset({1600, 1700, 1800})

#: How far from a centreline its road land may run: half of a 100 ft
#: right-of-way. A screening allowance, not a code's figure -- no code read
#: here states the right-of-way of a street drawn through a lot -- set wide so
#: that any street's road land is inside it (the conservative answer). Sized
#: on the rel11 bridge (2026-11-21): 30, 40 and 50 ft hold the same three
#: GREENs.
REACH_FT = 50.0

#: A centreline this near a lot line runs along it, not through the lot.
INSET_FT = 5.0
#: A centreline this near a street lot line is that street's own (a lot drawn
#: to the centre of its road), read by the dedication strip.
FRONT_LINE_FT = 10.0
#: The least run inside the lot that counts as crossing it.
MIN_INSIDE_FT = 10.0


@dataclass(frozen=True)
class Streets:
    """Street centrelines, indexed (:func:`load`)."""

    tree: Any
    geoms: Any
    names: tuple[str | None, ...]
    types: tuple[int | None, ...]


@dataclass(frozen=True)
class Crossing:
    """One street centreline through the lot near the plan."""

    name: str | None
    type: int | None
    #: Feet of the centreline counted inside the lot.
    inside_ft: float
    #: Feet from the nearest drawn shape to that part (0 where it crosses one).
    gap_ft: float

    def words(self) -> str:
        what = self.name.title() if self.name else "an unnamed street"
        kind = f"RLIS TYPE {self.type}" if self.type is not None else "type unread"
        return (
            f"{what} ({kind}) runs {self.inside_ft:.0f} ft through the lot, "
            f"{self.gap_ft:.1f} ft from the drawn plan (within {REACH_FT:g} ft: "
            "the plan may stand on its road land)"
        )


def _type(v: object) -> int | None:
    try:
        return int(float(v))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def load(path: Path) -> Streets | None:
    """quadfit s1's street centrelines (``name``, ``type``, ``alley``,
    ``wkb``) that are streets (:data:`NOT_STREET` and s1's ``alley`` flag
    left out), indexed; None where the file holds none."""
    import pandas as pd
    import shapely

    frame = pd.read_parquet(path, columns=["name", "type", "alley", "wkb"])
    kinds = [_type(v) for v in frame["type"]]
    alley = frame["alley"].fillna(False).astype(bool).to_numpy()
    keep = [i for i, k in enumerate(kinds) if k not in NOT_STREET and not alley[i]]
    if not keep:
        return None
    geoms = shapely.from_wkb(frame["wkb"].to_numpy()[keep])
    names = tuple(
        None if (n is None or (isinstance(n, float) and n != n)) else str(n)
        for n in frame["name"].to_numpy()[keep]
    )
    return Streets(shapely.STRtree(geoms), geoms, names, tuple(kinds[i] for i in keep))


def crossings(
    lot: Any,
    street_lines: Iterable[Sequence[float]],
    plan: Sequence[Any] | None,
    streets: Streets,
) -> list[Crossing]:
    """Every centreline of ``streets`` that runs through ``lot`` (a polygon)
    within reach of the ``plan``'s shapes (building, lane, court polygons).

    ``street_lines`` are the lot's street lot lines ``(x1, y1, x2, y2)``.
    ``plan`` None or empty: nothing was drawn, so every centreline counted
    inside the lot is returned, its gap 0 (nothing showed the plan clear of
    it)."""
    from shapely.geometry import LineString
    from shapely.ops import unary_union

    if lot is None or lot.is_empty:
        return []
    found = streets.tree.query(lot)
    if not len(found):
        return []
    inner = lot.buffer(-INSET_FT)
    if inner.is_empty:
        return []
    fronts = [LineString([(x1, y1), (x2, y2)]) for x1, y1, x2, y2 in street_lines]
    near = unary_union([f.buffer(FRONT_LINE_FT) for f in fronts]) if fronts else None
    shapes = [p for p in (plan or ()) if p is not None and not p.is_empty]
    out: list[Crossing] = []
    for i in found:
        part = streets.geoms[i].intersection(inner)
        if near is not None and not part.is_empty:
            part = part.difference(near)
        if part.is_empty or part.length < MIN_INSIDE_FT:
            continue
        gap = min((float(p.distance(part)) for p in shapes), default=0.0)
        if gap > REACH_FT:
            continue
        out.append(
            Crossing(streets.names[i], streets.types[i], round(float(part.length), 1), round(gap, 1))
        )
    return sorted(out, key=lambda c: (c.gap_ft, -c.inside_ft))


__all__ = [
    "FRONT_LINE_FT",
    "INSET_FT",
    "MIN_INSIDE_FT",
    "NOT_STREET",
    "REACH_FT",
    "Crossing",
    "Streets",
    "crossings",
    "load",
]
