"""Whether a street ends at the lot, read off quadfit's street centrelines.

Gresham's Table 4.0131 note 5: "For townhouses, single detached dwellings,
and plexes, the maximum setback from the end of a Minor Access Street is 25
feet. For cottage clusters, townhouses, single detached dwellings, and
plexes, the minimum setback from the end of a Minor Access Street is 5
feet." The note sits over the whole setback block, so until 2026-10-04 it
capped every Gresham setback on every lot behind a fact nobody measured --
the street's functional class -- and ~20,000 lots carried it as a question.

The class is the wrong question. The note is about the END of a street, and
whether any street ends at a lot is plain from the centrelines: a street that
stops short of meeting another street leaves an end point that exactly one
segment touches (the same reading as quadfit's cul-de-sac test,
``s4_edges.dead_ends``). A lot with no such point within :data:`REACH_FT`
cannot be at the end of a Minor Access Street, whatever that street's class,
and the note does not reach it. That is the only answer this module gives.

**Never True.** A street ending near a lot does not say the lot is AT that
end, nor that the street is a Minor Access Street, and the note's own
numbers (5 and 25) are not in the corpus: an answer of True would lift the
cap and screen the lot against the very row the note replaces. Near an end,
the fact stays unknown and the cap stays.

**Ends are counted generously**, because every extra end only keeps a cap:

* over the public streets alone (:data:`NOT_PUBLIC` dropped), so a public
  street that runs on as a private road, a driveway or an unimproved
  right-of-way ends where the public part ends;
* and over every non-alley line, so a private road's own dead end counts
  too, in case the street file calls a public street private;
* a line of unknown type is not public, so it can end a street but never
  continue one.

Alleys are left out of both, as in s4: an alley meeting a street is not the
street's continuation, so a street that runs into an alley ends there.

What it does not see: a street whose centreline was drawn short of where it
really ends, by more than :data:`REACH_FT`, and a new street not yet in the
file. The reach is set wide for the first (a bulb's centreline stops at the
throat, ~30 ft from its centre, and the lots on it are ~50 ft beyond); a lot
on a street not in the file has no frontage in s4 and fails on that.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Sequence

#: RLIS TYPE codes that do not carry a public street on: alley (1600),
#: private named road (1700), unnamed private road or driveway (1800),
#: unimproved and unmaintained local access (2000, Portland only).
NOT_PUBLIC: frozenset[int] = frozenset({1600, 1700, 1800, 2000})

#: How far from the taxlot a street end still counts as possibly the lot's
#: own. Generous on purpose: a lot this far from every end is not at one.
REACH_FT = 150.0

#: The one fact, named the way the registry names it.
STREET_END_FACT = "at_street_end"


def _ends(geoms: Iterable[Any]) -> set[tuple[int, int]]:
    """End points that exactly one line touches, snapped to the foot."""
    import shapely

    seen: Counter = Counter()
    for g in geoms:
        if g is None or g.is_empty:
            continue
        parts = shapely.get_parts(g) if g.geom_type != "LineString" else [g]
        for part in parts:
            c = part.coords
            seen[(round(c[0][0]), round(c[0][1]))] += 1
            seen[(round(c[-1][0]), round(c[-1][1]))] += 1
    return {k for k, v in seen.items() if v == 1}


def street_ends(geoms: Sequence[Any], types: Sequence[float | int | None], alley: Sequence[bool]) -> list[tuple[int, int]]:
    """Every point where a street may end, as (x, y) in the file's feet.

    ``types`` is RLIS TYPE per line (None or NaN where unknown) and ``alley``
    s1's alley flag; see the module docstring for why two networks are read.
    """
    public, street = [], []
    for g, t, a in zip(geoms, types, alley):
        if a:
            continue
        street.append(g)
        known = t is not None and t == t  # NaN is unknown
        if known and int(t) not in NOT_PUBLIC:
            public.append(g)
    return sorted(_ends(public) | _ends(street))


def end_distances(lot_geoms: Sequence[Any], ends: Sequence[tuple[int, int]]) -> list[float | None]:
    """Each lot's distance in feet to the nearest street end (None: no lot
    geometry, or no ends at all to measure to)."""
    import numpy as np
    import shapely

    if not ends:
        return [None] * len(lot_geoms)
    points = shapely.points(np.asarray(ends, dtype=float))
    tree = shapely.STRtree(points)
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


def observed_street_end(distance_ft: float | None) -> dict[str, bool]:
    """The street-end fact for one lot, as ``configure`` takes it.

    False where every street end lies beyond :data:`REACH_FT`; nothing at
    all otherwise -- including where the distance was never measured -- so
    the fact stays unknown and the note's cap stays on.
    """
    if distance_ft is None or distance_ft != distance_ft or distance_ft <= REACH_FT:
        return {}
    return {STREET_END_FACT: False}


def street_end_column(frame: Any, streets: Path) -> list[float | None]:
    """``street_end_ft`` for every row of a bridge frame holding ``lot_wkb``,
    from s1's centrelines. A file without RLIS TYPE measures nothing: with
    no way to tell a public street from a driveway, every end is unknown."""
    import pandas as pd
    import pyarrow.parquet as pq
    import shapely

    if "lot_wkb" not in frame.columns:
        return [None] * len(frame)
    names = set(pq.read_schema(streets).names)
    if not {"type", "alley", "wkb"} <= names:
        return [None] * len(frame)
    roads = pd.read_parquet(streets, columns=["type", "alley", "wkb"])
    ends = street_ends(
        shapely.from_wkb(roads["wkb"].to_numpy()),
        pd.to_numeric(roads["type"], errors="coerce").tolist(),
        roads["alley"].fillna(False).astype(bool).tolist(),
    )
    lots = [shapely.from_wkb(w) if isinstance(w, (bytes, bytearray)) else None for w in frame["lot_wkb"]]
    return end_distances(lots, ends)


__all__ = [
    "NOT_PUBLIC",
    "REACH_FT",
    "STREET_END_FACT",
    "end_distances",
    "observed_street_end",
    "street_end_column",
    "street_ends",
]
