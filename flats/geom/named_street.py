"""Whether a lot lies within 200 ft of a NAMED street, read off quadfit's centrelines.

Estacada's North City Residential zone (EMC 16.25.020 (G)) lets a triplex,
fourplex or commonwall row stand outright only "within 200 feet of Eagle
Creek Rd, Hinman Rd, or a street with a major collector classification or
higher classification". Steph, 2026-10-08: the distance machinery the app
already has is to be reused, with the NAMED streets as the origin.

The answer is plain geometry: the taxlot's distance to the nearest centreline
segment of a listed street, at or inside :data:`REACH_FT`.

**What the fact is not.** It is the *named* half of the sentence only. The
code's other half -- any street classed a major collector or higher -- needs
the city's functional-class map, which FLATS does not hold for Estacada (the
Transportation System Plan map is not in the corpus). A lot near an unlisted
collector is answered False here and screens RED: the conservative way to be
wrong, never a false GREEN. Add the collector's name to :data:`STREETS` when
the TSP names one.

**Matching** is on RLIS's own two columns, ``name`` (STREETNAME, no prefix)
and ``ftype``. Eagle Creek Road is ``EAGLE CREEK`` / ``RD`` and Hinman Road
``HINMAN`` / ``RD``; ``EAGLE CREEK LN`` and ``LOOP`` (private streets in the
same neighbourhood) are different streets and do not match. Read against the
2026-10-07 three-county file: 40 Eagle Creek Rd and 5 Hinman Rd segments.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

#: How far from a listed street a lot still counts as "within 200 feet".
#: The code's own number; the file is in feet.
REACH_FT = 200.0

#: The streets EMC 16.25.020 names, as (RLIS STREETNAME, RLIS FTYPE).
STREETS: tuple[tuple[str, str], ...] = (
    ("EAGLE CREEK", "RD"),
    ("HINMAN", "RD"),
)

#: The one fact, named the way the registry names it.
NAMED_STREET_FACT = "near_named_street_200ft"


def _key(value: object) -> str:
    return " ".join(str(value or "").upper().split())


def named_street_lines(names: Sequence[object], ftypes: Sequence[object], geoms: Sequence[Any]) -> list[Any]:
    """The centrelines of the listed streets."""
    wanted = {(_key(n), _key(t)) for n, t in STREETS}
    return [
        g
        for n, t, g in zip(names, ftypes, geoms)
        if g is not None and not g.is_empty and (_key(n), _key(t)) in wanted
    ]


def street_distances(lot_geoms: Sequence[Any], lines: Sequence[Any]) -> list[float | None]:
    """Each lot's distance in feet to the nearest listed line (None: no lot
    geometry, or no listed street in the file to measure to)."""
    import numpy as np
    import shapely

    if not lines:
        return [None] * len(lot_geoms)
    tree = shapely.STRtree(np.asarray(lines, dtype=object))
    out: list[float | None] = [None] * len(lot_geoms)
    have = [i for i, g in enumerate(lot_geoms) if g is not None and not g.is_empty]
    if not have:
        return out
    (lots, _), dist = tree.query_nearest(
        np.asarray([lot_geoms[i] for i in have], dtype=object), return_distance=True, all_matches=False
    )
    for k, d in zip(lots, dist):
        out[have[int(k)]] = float(d)
    return out


def observed_named_street(distance_ft: float | None) -> dict[str, bool]:
    """The fact for one lot, as ``configure`` takes it: True at or inside
    :data:`REACH_FT`, False beyond, nothing where it was never measured."""
    if distance_ft is None or distance_ft != distance_ft:
        return {}
    return {NAMED_STREET_FACT: distance_ft <= REACH_FT}


def named_street_column(frame: Any, streets: Path) -> list[float | None]:
    """``named_street_ft`` for every row of a bridge frame holding
    ``lot_wkb``, from s1's centrelines. A file without street names measures
    nothing."""
    import pandas as pd
    import pyarrow.parquet as pq
    import shapely

    if "lot_wkb" not in frame.columns:
        return [None] * len(frame)
    if not {"name", "ftype", "wkb"} <= set(pq.read_schema(streets).names):
        return [None] * len(frame)
    roads = pd.read_parquet(streets, columns=["name", "ftype", "wkb"])
    lines = named_street_lines(
        roads["name"].tolist(), roads["ftype"].tolist(), shapely.from_wkb(roads["wkb"].to_numpy())
    )
    lots = [shapely.from_wkb(w) if isinstance(w, (bytes, bytearray)) else None for w in frame["lot_wkb"]]
    return street_distances(lots, lines)


__all__ = [
    "NAMED_STREET_FACT",
    "REACH_FT",
    "STREETS",
    "named_street_column",
    "named_street_lines",
    "observed_named_street",
    "street_distances",
]
