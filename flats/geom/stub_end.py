"""Which of a lot's street lines abut the END of a street (Hillsboro D.4).

Hillsboro CDC 12.50.110 D.4 (or/washington/hillsboro/12.50/12.50.110.txt#L35):
"Property abutting the end of a public or private street not ending in a
cul-de-sac, or which may be subject to future extension, shall not be
considered as having lot frontage." It takes frontage away on the LINE that
abuts the end, not on the lot: a lot that also fronts a through street keeps
that street's frontage, and a lot on a cul-de-sac bulb is exempt by the
code's own words (FOLLOWUPS 222, t3-hillsboro-stub2).

:mod:`flats.geom.street_end` says only whether a street ends within
:data:`~flats.geom.street_end.REACH_FT` of the lot. This module reads the
same end points (the two networks of
:func:`flats.geom.street_end.street_ends`), each with the direction its
street was running when it stopped, and asks of each of the lot's street
lines (:func:`flats.fit.frontage.street_chains`) whether the street, carried
on past its end, runs into it.

A street line abuts an end where, inside a band :data:`BAND_HALF_FT` either
side of the centreline carried on, it is among the first lines of the lot
the band meets (within :data:`DEPTH_TOL_FT`) and does not run along the
street (:data:`ALONG_COS`: that is the street's side). Then:

* **True** -- met within :data:`ABUT_FT` of the end, square to the street
  (:data:`SQUARE_COS`), at an end of the whole non-alley network (public
  and private alike, as D.4 reads);
* **None** (unknown) -- met farther along (the centreline may be drawn
  short, or another lot may lie between), at an end only the public network
  has (the street may run on as a private road, which D.4 counts as a
  street), or at a slant between square and along;
* **False** -- every other line.

The answer is read edge by edge and summed per street
(:func:`street_lines_off_end_ft`), so a street whose line only partly abuts
an end keeps the rest. The screen (:func:`flats.score.screen.frontage_readings`,
where ``min_frontage_street_end: excluded``) drops True lines from both
readings and None lines from the strict one only, so an unknown line can
hold a lot and never pass or fail it. A lot on a cul-de-sac bulb
(``fronts_cul_de_sac``) keeps every line, by D.4's own exception.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Sequence

from flats.geom.street_end import NOT_PUBLIC, REACH_FT

#: Half the width of the band the street is carried on in, in feet: a local
#: street right-of-way of 50-60 ft, widened so a lot whose end line is offset
#: from the centreline is still met.
BAND_HALF_FT = 40.0

#: Back from the end point the band starts, in feet: a centreline digitised a
#: little past the right-of-way's end still meets the end line.
BACK_FT = 20.0

#: How far along from the end point a line met first is surely the end's.
ABUT_FT = 40.0

#: How much deeper than the first line met another of the lot's street lines
#: may lie and still be the same end line (a jog in it).
DEPTH_TOL_FT = 15.0

#: |cos| of the angle between a line and the street's direction at or below
#: which the line crosses the street square: the end, not the side (60 deg).
SQUARE_COS = 0.5

#: |cos| above which the line runs along the street: its side (30 deg).
ALONG_COS = math.cos(math.radians(30.0))

#: The row key the bridge writes (:func:`stub_end_column`).
ROW_KEY = "stub_ends_json"

#: The fact the Hillsboro frontage minimum is qualified by.
STREET_END_FRONTAGE_FACT = "street_end_frontage_unread"

Ray = tuple[float, float, float, float, bool]


def _end_rays(geoms: Iterable[Any]) -> dict[tuple[int, int], tuple[float, float]]:
    """Each end point exactly one line touches, snapped to the foot, with the
    unit direction the line was running as it reached it."""
    import shapely

    seen: Counter = Counter()
    heading: dict[tuple[int, int], tuple[float, float]] = {}
    for g in geoms:
        if g is None or g.is_empty:
            continue
        parts = shapely.get_parts(g) if g.geom_type != "LineString" else [g]
        for part in parts:
            c = list(part.coords)
            if len(c) < 2:
                continue
            for tip, prev in ((c[0], c[1]), (c[-1], c[-2])):
                key = (round(tip[0]), round(tip[1]))
                seen[key] += 1
                dx, dy = tip[0] - prev[0], tip[1] - prev[1]
                n = math.hypot(dx, dy)
                heading[key] = (dx / n, dy / n) if n > 0 else (0.0, 0.0)
    return {k: heading[k] for k, v in seen.items() if v == 1 and heading[k] != (0.0, 0.0)}


def stub_end_rays(
    geoms: Sequence[Any], types: Sequence[float | int | None], alley: Sequence[bool]
) -> list[Ray]:
    """Every street end as ``(x, y, dx, dy, sure)``: ``sure`` where the whole
    non-alley network ends there, not where only the public part does (the
    same two networks as :func:`flats.geom.street_end.street_ends`)."""
    public, street = [], []
    for g, t, a in zip(geoms, types, alley):
        if a:
            continue
        street.append(g)
        known = t is not None and t == t
        if known and int(t) not in NOT_PUBLIC:
            public.append(g)
    whole = _end_rays(street)
    part = _end_rays(public)
    out = [(float(x), float(y), d[0], d[1], True) for (x, y), d in whole.items()]
    out += [(float(x), float(y), d[0], d[1], False) for (x, y), d in part.items() if (x, y) not in whole]
    return sorted(out)


def rays_near(lots: Sequence[Any], rays: Sequence[Ray]) -> list[str | None]:
    """Each lot's rays within :data:`~flats.geom.street_end.REACH_FT`, as a
    JSON list of ``[x, y, dx, dy, sure]``; None for a lot with no geometry."""
    import numpy as np
    import shapely

    out: list[str | None] = [None if g is None or g.is_empty else "[]" for g in lots]
    if not rays:
        return out
    tree = shapely.STRtree(shapely.points(np.asarray([r[:2] for r in rays], dtype=float)))
    for i, g in enumerate(lots):
        if g is None or g.is_empty:
            continue
        got = []
        for k in tree.query(g, predicate="dwithin", distance=REACH_FT):
            x, y, dx, dy, sure = rays[int(k)]
            got.append([round(x, 1), round(y, 1), round(dx, 4), round(dy, 4), bool(sure)])
        if got:
            out[i] = json.dumps(sorted(got))
    return out


def stub_end_column(frame: Any, streets: Path) -> list[str | None]:
    """``stub_ends_json`` for every row of a bridge frame holding ``lot_wkb``,
    from s1's centrelines (:func:`rays_near`). None everywhere for a file
    without RLIS TYPE, as :func:`flats.geom.street_end.street_end_column`."""
    import pandas as pd
    import pyarrow.parquet as pq
    import shapely

    if "lot_wkb" not in frame.columns:
        return [None] * len(frame)
    if not {"type", "alley", "wkb"} <= set(pq.read_schema(streets).names):
        return [None] * len(frame)
    roads = pd.read_parquet(streets, columns=["type", "alley", "wkb"])
    rays = stub_end_rays(
        shapely.from_wkb(roads["wkb"].to_numpy()),
        pd.to_numeric(roads["type"], errors="coerce").tolist(),
        roads["alley"].fillna(False).astype(bool).tolist(),
    )
    lots = [shapely.from_wkb(w) if isinstance(w, (bytes, bytearray)) else None for w in frame["lot_wkb"]]
    return rays_near(lots, rays)


def decode_rays(raw: object) -> list[Ray] | None:
    """A row's ``stub_ends_json`` back as rays; None where unmeasured or unreadable."""
    if not isinstance(raw, str):
        return None
    try:
        got = json.loads(raw)
        return [(float(r[0]), float(r[1]), float(r[2]), float(r[3]), bool(r[4])) for r in got]
    except (TypeError, ValueError, IndexError, KeyError):
        return None


def _in_band(seg: tuple[float, float, float, float], ray: Ray) -> tuple[float, float] | None:
    """Where segment ``seg`` first meets the band ``ray`` carries its street
    on in: ``(t, |cos|)``, t the distance along from the end point and |cos|
    how nearly the segment runs along the street; None where it does not
    enter the band between -:data:`BACK_FT` and
    :data:`~flats.geom.street_end.REACH_FT`."""
    x, y, dx, dy = ray[:4]
    x1, y1, x2, y2 = seg
    t1, s1 = (x1 - x) * dx + (y1 - y) * dy, -(x1 - x) * dy + (y1 - y) * dx
    t2, s2 = (x2 - x) * dx + (y2 - y) * dy, -(x2 - x) * dy + (y2 - y) * dx
    n = math.hypot(t2 - t1, s2 - s1)
    if n <= 0:
        return None
    lo, hi = 0.0, 1.0
    for f0, f1 in (
        (BAND_HALF_FT - s1, BAND_HALF_FT - s2),
        (BAND_HALF_FT + s1, BAND_HALF_FT + s2),
        (t1 + BACK_FT, t2 + BACK_FT),
        (REACH_FT - t1, REACH_FT - t2),
    ):
        # Keep the u in [lo, hi] where f0 + (f1 - f0) u >= 0.
        if f0 < 0 and f1 < 0:
            return None
        if (f0 < 0) != (f1 < 0):
            u = f0 / (f0 - f1)
            if f0 < 0:
                lo = max(lo, u)
            else:
                hi = min(hi, u)
        if lo > hi:
            return None
    t = min(t1 + (t2 - t1) * lo, t1 + (t2 - t1) * hi)
    return t, abs(t2 - t1) / n


def stub_end_edges(ring: Sequence[Any], street: Sequence[Any], rays: Sequence[Ray]) -> dict[int, bool | None]:
    """The street edges (``street``, by ``id``) that abut a street end: True
    or None (unknown), as the module docstring sets out; an edge not in the
    result abuts none. ``ring`` is every edge of the lot, any kind, each
    with ``x1 y1 x2 y2``: a side or rear line met first shields the street
    lines behind it."""
    mine = {id(e) for e in street}
    out: dict[int, bool | None] = {}
    for ray in rays:
        hits: list[tuple[float, float, int]] = []
        for e in ring:
            got = _in_band((e.x1, e.y1, e.x2, e.y2), ray)
            if got is None or got[1] > ALONG_COS:
                continue  # outside the band, or the street's own side
            hits.append((got[0], got[1], id(e)))
        if not hits:
            continue
        first = min(h[0] for h in hits)
        for t, cos, key in hits:
            if key not in mine or t > first + DEPTH_TOL_FT or out.get(key) is True:
                continue
            sure = ray[4] and cos <= SQUARE_COS and first <= ABUT_FT
            out[key] = True if sure else None
    return out


def street_lines_off_end_ft(
    ring: Sequence[Any],
    chains: Sequence[Sequence[Any]],
    rays: Sequence[Ray] | None,
    *,
    cul_de_sac: bool = False,
) -> tuple[tuple[float, float], ...] | None:
    """Each street (``chains``, in :func:`flats.fit.frontage.street_chains`
    order) as ``(strict_ft, lenient_ft)``: its length without the lines that
    abut a street end (:func:`stub_end_edges`) -- strict without the True
    and the unknown ones, lenient without the True ones only. A street with
    none keeps its whole length on both. None where unmeasured: no rays
    read, or no street to answer for. A cul-de-sac lot keeps every street
    whole (D.4: "not ending in a cul-de-sac")."""
    if rays is None or not chains:
        return None
    ends = {} if cul_de_sac else stub_end_edges(ring, [e for c in chains for e in c], rays)
    out = []
    for chain in chains:
        strict = sum(e.length_ft for e in chain if id(e) not in ends)
        lenient = sum(e.length_ft for e in chain if ends.get(id(e), False) is not True)
        out.append((float(strict), float(lenient)))
    return tuple(out)


def observed_street_end_frontage(
    street_end_ft: float | None, cul_de_sac: bool, lines: tuple[tuple[float, float], ...] | None
) -> dict[str, bool]:
    """The D.4 fact for one lot, as ``configure`` takes it: False where no
    street ends within reach (``street_end_ft`` beyond
    :data:`~flats.geom.street_end.REACH_FT`), on a cul-de-sac bulb, or where
    every street line was read (``lines`` not None: the screen then measures
    the frontage without the ends). Nothing otherwise -- unknown, never True
    -- so the frontage minimum it qualifies holds the lot out of GREEN."""
    far = street_end_ft is not None and street_end_ft == street_end_ft and street_end_ft > REACH_FT
    if far or cul_de_sac or lines is not None:
        return {STREET_END_FRONTAGE_FACT: False}
    return {}


__all__ = [
    "ABUT_FT",
    "ALONG_COS",
    "BACK_FT",
    "BAND_HALF_FT",
    "DEPTH_TOL_FT",
    "ROW_KEY",
    "SQUARE_COS",
    "STREET_END_FRONTAGE_FACT",
    "decode_rays",
    "observed_street_end_frontage",
    "rays_near",
    "street_lines_off_end_ft",
    "stub_end_column",
    "stub_end_edges",
    "stub_end_rays",
]
