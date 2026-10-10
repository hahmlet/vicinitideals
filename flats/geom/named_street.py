"""Whether a lot lies within 200 ft of a NAMED street, and where on it a dwelling may stand.

Estacada's North City Residential zone (EMC 16.25.020 (G)) lets a triplex,
fourplex or commonwall row stand outright only "within 200 feet of Eagle
Creek Rd, Hinman Rd, or a street with a major collector classification or
higher classification". Steph, 2026-10-08: the distance machinery the app
already has is to be reused, with the NAMED streets as the origin.

The fact is plain geometry: the taxlot's distance to the nearest centreline
segment of a listed street, at or inside :data:`REACH_FT`.

**The fact is the lot's; the code's test is the dwelling's.** A lot that
touches the 200 ft band can still reach far beyond it (a 12-acre corner lot),
and the code asks for the DWELLING within 200 feet. So the fact only admits
the lot to the check; the ground of the lot beyond the band
(:func:`beyond_reach`) is taken off its placement area in the zones listed in
:data:`BAND_ZONES`, so no building, court or lane is drawn out there.

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

**A second named street: Portland Avenue, Gladstone** (FOLLOWUPS 52, Steph
2026-10-09). GMC 17.18.050(3) puts limits on "developments along Portland
Avenue" in the C-2 zone: a primary entrance facing the avenue and ground-floor
windows over a quarter of the residential ground-floor wall. The same
distance machinery answers ``along_portland_avenue``, with
:data:`AVENUE_REACH_FT` for the reach. "Along" is a lot that touches the
avenue, so the reach is s4's own reach for a street lot line -- 50 ft to a
centreline -- with the slack the corridor reading takes
(:data:`flats.geom.corridor.FRONT_REACH_FT`). Read against the 2026-10-07
file on Gladstone's 138 C-2 lots, the gap it sits in is wide: every lot with
a lot line on the avenue lies 34-45 ft from its centreline (a corner lot on a
side street included); the one lot between is 1050 Portland Ave, 55 ft, whose
corner meets the avenue at the Jersey Street junction; the nearest lot behind
is 84 ft out. A lot within the reach may face the avenue only at a corner;
counting it is the conservative way to be wrong, since a lot the reach
misses would screen green without the entrance the code asks for. Measured
only on the lots of :data:`AVENUE_JURISDICTIONS`: Metro's file has Portland
Avenues elsewhere, and the rule is Gladstone's.
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

#: The (jurisdiction, zone) pairs whose dwelling must stand inside the band.
BAND_ZONES: frozenset[tuple[str, str]] = frozenset({("estacada", "NCR")})

#: The one fact, named the way the registry names it.
NAMED_STREET_FACT = "near_named_street_200ft"

#: Gladstone GMC 17.18.050(3)'s avenue, as (RLIS STREETNAME, RLIS FTYPE).
AVENUE_STREETS: tuple[tuple[str, str], ...] = (("PORTLAND", "AVE"),)

#: How far from the avenue's centreline a lot still touches it: s4's 50 ft
#: street-line reach with the corridor reading's slack (see the module
#: docstring for the gap it sits in).
AVENUE_REACH_FT = 60.0

#: The s4 jurisdictions the avenue is measured for.
AVENUE_JURISDICTIONS: frozenset[str] = frozenset({"gladstone"})

#: The avenue's fact, named the way the registry names it.
AVENUE_FACT = "along_portland_avenue"


def _key(value: object) -> str:
    return " ".join(str(value or "").upper().split())


def named_street_lines(
    names: Sequence[object],
    ftypes: Sequence[object],
    geoms: Sequence[Any],
    listed: Sequence[tuple[str, str]] = STREETS,
) -> list[Any]:
    """The centrelines of the ``listed`` streets."""
    wanted = {(_key(n), _key(t)) for n, t in listed}
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


def observed_avenue(distance_ft: float | None) -> dict[str, bool]:
    """``along_portland_avenue`` for one lot: True at or inside
    :data:`AVENUE_REACH_FT` of the avenue, False beyond, nothing where it was
    never measured (a lot outside :data:`AVENUE_JURISDICTIONS` included)."""
    if distance_ft is None or distance_ft != distance_ft:
        return {}
    return {AVENUE_FACT: distance_ft <= AVENUE_REACH_FT}


def _lot_geoms(frame: Any) -> list[Any]:
    import shapely

    return [shapely.from_wkb(w) if isinstance(w, (bytes, bytearray)) else None for w in frame["lot_wkb"]]


def _lines_in(streets: Path, listed: Sequence[tuple[str, str]] = STREETS) -> list[Any] | None:
    """The ``listed`` streets' centrelines in s1's file; None where the file
    cannot name streets."""
    import pandas as pd
    import pyarrow.parquet as pq
    import shapely

    if not {"name", "ftype", "wkb"} <= set(pq.read_schema(streets).names):
        return None
    roads = pd.read_parquet(streets, columns=["name", "ftype", "wkb"])
    return named_street_lines(
        roads["name"].tolist(), roads["ftype"].tolist(), shapely.from_wkb(roads["wkb"].to_numpy()), listed
    )


def beyond_reach(lot: Any, lines: Sequence[Any]) -> Any:
    """The part of ``lot`` more than :data:`REACH_FT` from every listed line;
    the whole lot where there is no line to measure to (conservative)."""
    import shapely

    if not lines:
        return lot
    band = shapely.union_all(list(lines)).buffer(REACH_FT)
    return lot.difference(band)


def named_street_column(frame: Any, streets: Path) -> list[float | None]:
    """``named_street_ft`` for every row of a bridge frame holding
    ``lot_wkb``, from s1's centrelines. A file without street names measures
    nothing."""
    if "lot_wkb" not in frame.columns:
        return [None] * len(frame)
    lines = _lines_in(streets)
    if lines is None:
        return [None] * len(frame)
    return street_distances(_lot_geoms(frame), lines)


def avenue_column(frame: Any, streets: Path) -> list[float | None]:
    """``avenue_ft`` for every row of a bridge frame: the lot's distance to
    the avenue's centreline on rows of :data:`AVENUE_JURISDICTIONS`, None on
    every other row and wherever the file cannot name streets."""
    out: list[float | None] = [None] * len(frame)
    if "lot_wkb" not in frame.columns or "jurisdiction" not in frame.columns:
        return out
    hit = [i for i, j in enumerate(frame["jurisdiction"]) if str(j) in AVENUE_JURISDICTIONS]
    if not hit:
        return out
    lines = _lines_in(streets, AVENUE_STREETS)
    if lines is None:
        return out
    lots = _lot_geoms(frame)
    for i, d in zip(hit, street_distances([lots[i] for i in hit], lines)):
        out[i] = d
    return out


def beyond_reach_column(frame: Any, streets: Path) -> list[bytes | None]:
    """``reach_off_wkb``: for each row in a :data:`BAND_ZONES` zone, the lot
    ground beyond the band (WKB; empty where the whole lot is inside); None
    for every other row. A street file that names no streets leaves the whole
    lot beyond reach."""
    import shapely

    out: list[bytes | None] = [None] * len(frame)
    if "lot_wkb" not in frame.columns or not {"jurisdiction", "zone"} <= set(frame.columns):
        return out
    hit = [
        i
        for i, (j, z) in enumerate(zip(frame["jurisdiction"], frame["zone"]))
        if (str(j), str(z)) in BAND_ZONES
    ]
    if not hit:
        return out
    lines = _lines_in(streets) or []
    lots = _lot_geoms(frame)
    for i in hit:
        if lots[i] is not None:
            out[i] = shapely.to_wkb(beyond_reach(lots[i], lines))
    return out


__all__ = [
    "AVENUE_FACT",
    "AVENUE_JURISDICTIONS",
    "AVENUE_REACH_FT",
    "AVENUE_STREETS",
    "BAND_ZONES",
    "NAMED_STREET_FACT",
    "REACH_FT",
    "STREETS",
    "avenue_column",
    "beyond_reach",
    "beyond_reach_column",
    "named_street_column",
    "named_street_lines",
    "observed_avenue",
    "observed_named_street",
    "street_distances",
]
