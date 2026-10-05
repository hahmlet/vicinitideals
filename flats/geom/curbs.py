"""Where a street's near curb is, from published curb lines and pavement
widths (FOLLOWUPS 29).

The fire hose's 150 ft (OFC 503.1.1) starts where the truck stands, and no
Oregon fire guide says where on the street that is. Steph, 2026-10-05,
chose the stricter of the readings found in use: "10 feet from the edge of
the curb" (one Southern California template: Colton, Roseville, Riverside
County and others), past a lane of parked cars rather than at the curb.
:mod:`flats.fit.fire` applies the rule; this module says where the curb is.

RLIS holds street centrelines and no widths, so where nothing here reaches,
the truck still stands 10 ft off the centreline, as before. Three kinds of
source say more, each in the acquire snapshot (``flats/config/pipeline.yaml``,
``curbs_*`` and ``*_width_*``):

* **Drawn curbs** (Portland PBOT: blockface, corner and shoulder lines). The
  near curb of a point on a street lot line is where the straight line from
  it to the foot of its centreline crosses a curb -- the crossing NEAREST the
  centreline where it crosses several (a curb extension, a cycle track's
  street-side curb, a corner return): the truck stands outside all of them,
  so the farther one is the stricter answer. A property-side curb is not a
  street's edge and is skipped.
* **Pavement widths** (Portland PBOT's pavement segments, Multnomah County's
  county roads, Wilsonville's streets): the curb taken half the width off the
  centreline less :data:`WIDTH_MARGIN_FT`, the width line read where it runs
  beside the centreline's foot (within :data:`WIDTH_REACH_FT`, within
  :data:`PARALLEL_DEG` of its bearing; the narrowest where two are). The
  margin is how far RLIS's centreline strays from the pavement's middle:
  on 6,887 Portland points where both curbs are drawn and agree with the
  recorded width, half the width overstates the real half by 3.3 ft or
  less at 95 in 100 (checked 2026-10-05).
* **Nothing**: no curb crossed and no width beside the foot.

**A drawn curb that would put the truck farther out than today must agree
with the width.** The old 10 ft off the centreline is the answer on a
street 40 ft wide; a curb more than 20 ft off the centreline moves the
truck nearer the lot than any answer before it, and a stray line drawn
where the real curb has a gap would do the same. So such a curb is kept
only where a width is recorded beside it and twice its distance off the
centreline is within :data:`AGREE_FT` of that width; otherwise the width
answers. A width alone never moves the truck nearer the lot than today
(:func:`flats.fit.fire.hose_offsets`): it is a step stricter where it
says the street is narrow, and nothing where it says wide.
"""

from __future__ import annotations

import enum
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import shapely
from shapely.geometry.base import BaseGeometry

#: Snapshot datasets holding drawn curb lines.
CURB_KEYS: tuple[str, ...] = ("curbs_portland",)
#: Snapshot datasets holding pavement widths -> the width field (ft).
WIDTH_KEYS: dict[str, str] = {
    "pave_width_portland": "PaveWidth",
    "road_width_multnomah": "RoadWidth",
    "street_width_wilsonville": "Width",
}
#: CurbStyle values that are not a street's edge (PBOT "Property Side Curb").
SKIP_STYLES: frozenset[str] = frozenset({"INSIDE"})
#: A recorded width under this is not a street's (PBOT holds 1,027 such).
MIN_WIDTH_FT = 10.0
#: How far from the centreline's foot a width line may run and still be
#: the same street's.
WIDTH_REACH_FT = 15.0
#: How far off the centreline's bearing a width line may run and still be
#: the same street's (a cross street's line meets the foot square on).
PARALLEL_DEG = 20.0
#: Taken off half a recorded width: RLIS's centreline is not the
#: pavement's middle (module docstring).
WIDTH_MARGIN_FT = 3.0
#: How far a drawn curb's street width may differ from the recorded one
#: and still be read as the same street where it moves the truck nearer
#: the lot than today.
AGREE_FT = 4.0
#: The truck's old offset, off the centreline: a drawn curb farther from
#: the centreline than twice this moves it nearer the lot than before.
_TODAY_FT = 10.0
#: Half the length of the run a bearing is read over.
_BEARING_FT = 3.0


class Source(enum.IntEnum):
    """What placed a point's near curb."""

    none = 0
    curb = 1
    width = 2


@dataclass(frozen=True)
class StreetEdges:
    """The curb lines and width lines of one acquire snapshot, indexed."""

    curb_geoms: np.ndarray
    width_geoms: np.ndarray
    width_ft: np.ndarray
    #: The snapshot datasets read, for the run's record.
    keys: tuple[str, ...] = ()
    _curbs: Any = field(init=False, repr=False, compare=False, default=None)
    _widths: Any = field(init=False, repr=False, compare=False, default=None)

    def __post_init__(self) -> None:
        if len(self.curb_geoms):
            object.__setattr__(self, "_curbs", shapely.STRtree(self.curb_geoms))
        if len(self.width_geoms):
            object.__setattr__(self, "_widths", shapely.STRtree(self.width_geoms))

    @classmethod
    def build(
        cls,
        curbs: Sequence[BaseGeometry] = (),
        widths: Sequence[tuple[BaseGeometry, float]] = (),
        keys: Sequence[str] = (),
    ) -> StreetEdges:
        kept = [(g, float(w)) for g, w in widths if g is not None and w is not None and float(w) >= MIN_WIDTH_FT]
        return cls(
            np.asarray([g for g in curbs if g is not None], dtype=object),
            np.asarray([g for g, _ in kept], dtype=object),
            np.asarray([w for _, w in kept], dtype=float),
            tuple(keys),
        )

    def near(
        self, points: np.ndarray, feet: np.ndarray, lines: Sequence[BaseGeometry]
    ) -> tuple[np.ndarray, np.ndarray]:
        """How far each point is from its street's near curb, and what said so.

        ``points`` are on street lot lines, ``feet`` the nearest point of the
        centreline ``lines[i]`` to each. NaN and :attr:`Source.none` where
        nothing here reaches the point.
        """
        n = len(points)
        out = np.full(n, np.nan)
        src = np.full(n, Source.none, dtype=np.int8)
        if not n:
            return out, src
        points = np.asarray(points, dtype=float).reshape(-1, 2)
        feet = np.asarray(feet, dtype=float).reshape(-1, 2)
        gap = np.hypot(*(feet - points).T)
        curb = self._crossed(points, feet, gap)
        width = self._width(feet, np.asarray(lines, dtype=object))
        # A drawn curb farther off the centreline than today's offset must
        # agree with the recorded width (module docstring).
        off = gap - curb
        bold = off > 2 * _TODAY_FT
        agrees = np.isfinite(width) & (np.abs(2 * off - width) <= AGREE_FT)
        use_curb = np.isfinite(curb) & (~bold | agrees)
        out[use_curb] = curb[use_curb]
        src[use_curb] = Source.curb
        use_width = ~use_curb & np.isfinite(width)
        out[use_width] = np.maximum(gap[use_width] - (width[use_width] / 2 - WIDTH_MARGIN_FT), 0.0)
        src[use_width] = Source.width
        return out, src

    def _crossed(self, points: np.ndarray, feet: np.ndarray, gap: np.ndarray) -> np.ndarray:
        """The distance from each point to the curb its line to the
        centreline crosses nearest the centreline; NaN where none."""
        out = np.full(len(points), np.nan)
        tree = self._curbs
        live = gap > 1e-6
        if tree is None or not live.any():
            return out
        rows = np.flatnonzero(live)
        segs = shapely.linestrings(np.stack([points[rows], feet[rows]], axis=1))
        si, ci = tree.query(segs, predicate="intersects")
        if not len(si):
            return out
        hit = shapely.intersection(segs[si], self.curb_geoms[ci])
        back = shapely.distance(shapely.points(feet[rows][si]), hit)
        nearest = np.full(len(rows), np.inf)
        np.minimum.at(nearest, si, back)
        found = np.isfinite(nearest)
        out[rows[found]] = gap[rows[found]] - nearest[found]
        return out

    def _width(self, feet: np.ndarray, lines: np.ndarray) -> np.ndarray:
        """The narrowest recorded width running beside each foot; NaN where none."""
        out = np.full(len(feet), np.nan)
        tree = self._widths
        if tree is None or not len(feet):
            return out
        pts = shapely.points(feet)
        fi, wi = tree.query(pts, predicate="dwithin", distance=WIDTH_REACH_FT)
        if not len(fi):
            return out
        own = _bearing(lines[fi], pts[fi])
        theirs = _bearing(self.width_geoms[wi], pts[fi])
        turn = np.abs(own - theirs) % 180.0
        turn = np.minimum(turn, 180.0 - turn)
        ok = turn <= PARALLEL_DEG
        narrow = np.full(len(feet), np.inf)
        np.minimum.at(narrow, fi[ok], self.width_ft[wi[ok]])
        found = np.isfinite(narrow)
        out[found] = narrow[found]
        return out


def _bearing(lines: np.ndarray, near: np.ndarray) -> np.ndarray:
    """Each line's direction (degrees, 0-180) where it passes nearest ``near``."""
    at = shapely.line_locate_point(lines, near)
    length = shapely.length(lines)
    a = shapely.line_interpolate_point(lines, np.maximum(at - _BEARING_FT, 0.0))
    b = shapely.line_interpolate_point(lines, np.minimum(at + _BEARING_FT, length))
    (ax, ay), (bx, by) = shapely.get_coordinates(a).T, shapely.get_coordinates(b).T
    return np.degrees(np.arctan2(by - ay, bx - ax)) % 180.0


def _dataset_path(sources: Path, manifest: dict[str, Any], key: str) -> Path:
    entry = (manifest.get("datasets") or {}).get(key) or {}
    return sources / str(entry.get("file") or f"{key}.geojson")


def load(sources: Path) -> StreetEdges | None:
    """The curbs and widths an acquire snapshot holds; None where it holds
    none of them (every street then keeps the old offset)."""
    from shapely.geometry import shape

    from flats.ingest.delta import iter_features

    manifest_path = sources / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    keys: list[str] = []
    curbs: list[BaseGeometry] = []
    for key in CURB_KEYS:
        path = _dataset_path(sources, manifest, key)
        if not path.is_file():
            continue
        keys.append(key)
        for f in iter_features(path):
            props = f.get("properties") or {}
            if f.get("geometry") and str(props.get("CurbStyle") or "") not in SKIP_STYLES:
                curbs.append(shape(f["geometry"]))
    widths: list[tuple[BaseGeometry, float]] = []
    for key, field in WIDTH_KEYS.items():
        path = _dataset_path(sources, manifest, key)
        if not path.is_file():
            continue
        keys.append(key)
        for f in iter_features(path):
            w = (f.get("properties") or {}).get(field)
            if f.get("geometry") and isinstance(w, (int, float)) and math.isfinite(w):
                widths.append((shape(f["geometry"]), float(w)))
    if not keys:
        return None
    return StreetEdges.build(curbs, widths, keys)


__all__ = [
    "AGREE_FT",
    "CURB_KEYS",
    "MIN_WIDTH_FT",
    "PARALLEL_DEG",
    "SKIP_STYLES",
    "WIDTH_KEYS",
    "WIDTH_MARGIN_FT",
    "WIDTH_REACH_FT",
    "Source",
    "StreetEdges",
    "load",
]
