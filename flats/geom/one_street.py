"""Whether every street line of a lot is the same street, off quadfit's centrelines.

s4 calls an edge a street when its midpoint is within 50 ft of any non-alley
centreline, with no test of name, length or direction, and clusters the
street edges' bearings at 20 degrees. A cul-de-sac bulb, a knuckle, a curved
front or a front with a short sliver edge therefore reads as two street
directions, and :func:`flats.geom.corner.two_streets` (45 degrees) passes it:
the lot is screened as a corner lot when it is ONE street that bends
(FOLLOWUPS 63; 2,311 corner-tier green/yellow lots in run 69).

This module answers the one fact that tells the two apart: do all the lot's
street lines lie on one street? Steph, 2026-10-09: where the code is silent,
take the more conservative reading, with a flag -- one street bending is one
front, not a corner.

**Never True on a doubt.** Every non-alley centreline within
:data:`REACH_FT` (s4's own reach) of the midpoint of any street edge is
counted, so a second street near the lot, or a line with no name, keeps the
corner reading. The answer is True only when exactly one street (name and
type) is within reach of every street edge.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

#: s4's own reach for calling an edge a street (``street_threshold_ft``).
REACH_FT = 50.0

#: s4's class letter for a street edge in ``edges_json``.
STREET_CLASS = "F"


def _key(name: object, ftype: object) -> str:
    n = " ".join(str(name or "").upper().split())
    if n in ("", "NAN", "NONE"):
        return ""
    t = " ".join(str(ftype or "").upper().split())
    return f"{n}|{'' if t in ('NAN', 'NONE') else t}"


def street_midpoints(edges_json: str | None) -> list[tuple[float, float]]:
    """The midpoint of every street edge of one lot's ``edges_json``."""
    out: list[tuple[float, float]] = []
    for e in json.loads(edges_json or "[]"):
        if len(e) >= 5 and e[4] == STREET_CLASS:
            out.append(((float(e[0]) + float(e[2])) / 2, (float(e[1]) + float(e[3])) / 2))
    return out


def one_street_flags(
    edges: Sequence[str | None],
    names: Sequence[object],
    ftypes: Sequence[object],
    alleys: Sequence[object],
    geoms: Sequence[Any],
) -> list[bool | None]:
    """Per lot: True where every street edge lies on one street, False where
    two streets (or a nameless line) are within reach, None where the lot has
    no street edge or no centreline is within reach of one."""
    import numpy as np
    import shapely

    keep = [
        i for i, (g, a) in enumerate(zip(geoms, alleys))
        if g is not None and not g.is_empty and not bool(a)
    ]
    keys = [_key(names[i], ftypes[i]) for i in keep]
    lines = np.asarray([geoms[i] for i in keep], dtype=object)
    out: list[bool | None] = [None] * len(edges)
    if not len(lines):
        return out
    tree = shapely.STRtree(lines)
    owner: list[int] = []
    xs: list[float] = []
    ys: list[float] = []
    for n, ej in enumerate(edges):
        for x, y in street_midpoints(ej):
            owner.append(n)
            xs.append(x)
            ys.append(y)
    if not owner:
        return out
    pts = shapely.points(np.asarray(xs), np.asarray(ys))
    found: dict[int, set[str]] = {}
    reached = [0] * len(pts)
    pairs = tree.query(pts, predicate="dwithin", distance=REACH_FT)
    for p, line in zip(pairs[0], pairs[1]):
        found.setdefault(owner[int(p)], set()).add(keys[int(line)])
        reached[int(p)] += 1
    unreached = {owner[p] for p, c in enumerate(reached) if c == 0}
    for n, got in found.items():
        if n in unreached:
            continue
        out[n] = len(got) == 1 and "" not in got
    return out


def one_street_column(frame: Any, streets: Path) -> list[bool | None]:
    """``one_street`` for every row of a bridge frame holding ``edges_json``,
    from s1's centrelines. A file without street names or the alley column
    measures nothing."""
    import pandas as pd
    import pyarrow.parquet as pq
    import shapely

    if "edges_json" not in frame.columns:
        return [None] * len(frame)
    if not {"name", "ftype", "alley", "wkb"} <= set(pq.read_schema(streets).names):
        return [None] * len(frame)
    roads = pd.read_parquet(streets, columns=["name", "ftype", "alley", "wkb"])
    geoms = list(shapely.from_wkb(roads["wkb"].to_numpy()))
    return one_street_flags(
        frame["edges_json"].tolist(),
        roads["name"].tolist(),
        roads["ftype"].tolist(),
        roads["alley"].fillna(False).tolist(),
        geoms,
    )


__all__ = ["REACH_FT", "one_street_column", "one_street_flags", "street_midpoints"]
