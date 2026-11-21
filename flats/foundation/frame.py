"""The drawn building's own frame: which long side is the front, which end is left.

Copied, unchanged in behaviour, from ``flats/ingest/fd2.py`` (``Frame``,
``frame()``, ``_dist_to_lines()``) on branch ``flats/fd2-pass1`` at 56806fe1, so
the foundation package reads the ground in exactly the frame FD2 pass 1 used for
the lot file's six readings, without importing the ingest package. Added here:
:meth:`Frame.world` and :meth:`Frame.model`, the map between that frame and this
model's (x 0..80 ft left to right seen from the street, y 0..25 ft front to
back).

The street lines a frame needs (to name the front) come from the lot's quadfit
row; the caller supplies them (``scripts/flats_foundation.py``).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

Seg = tuple[float, float, float, float]


@dataclass(frozen=True)
class Frame:
    """The drawn building as four named corners (EPSG:2913 ft).

    ``front`` is the long side nearer the street lot lines (where the front
    doors face); left and right are as seen from the street, looking at the
    building. ``front_known`` is False when no street line was traced (the
    first long side is then called front).
    """

    fl: tuple[float, float]
    fr: tuple[float, float]
    bl: tuple[float, float]
    br: tuple[float, float]
    long_ft: float
    short_ft: float
    front_known: bool

    def at(self, u: Any, v: Any) -> Any:
        """Points at ``u`` (0 left .. 1 right) and ``v`` (0 front .. 1 back)."""
        import numpy as np

        u = np.asarray(u, dtype=float)
        v = np.asarray(v, dtype=float)
        fl, fr, bl = (np.array(p, dtype=float) for p in (self.fl, self.fr, self.bl))
        return fl + u[..., None] * (fr - fl) + v[..., None] * (bl - fl)

    def world(self, x_ft: Any, y_ft: Any, length_ft: float, width_ft: float,
              box_ft: tuple[float, float] | None = None) -> Any:
        """Model (x, y) -> world points. Without ``box_ft`` the model's
        ``length_ft`` x ``width_ft`` spans the drawn rectangle (x / length along
        the drawn front, y / width across). With ``box_ft`` = (length, width)
        of the drawn rectangle, the model's footprint sits centred inside it
        (the framing inside the finished faces, DECISIONS N-finished)."""
        import numpy as np

        bl_ft, bw_ft = box_ft if box_ft is not None else (length_ft, width_ft)
        x = np.asarray(x_ft, dtype=float) + (bl_ft - length_ft) / 2
        y = np.asarray(y_ft, dtype=float) + (bw_ft - width_ft) / 2
        return self.at(x / bl_ft, y / bw_ft)

    def model(self, pts: Any, length_ft: float, width_ft: float, box_ft: tuple[float, float] | None = None) -> Any:
        """World points (N, 2) -> model (x, y) (N, 2), the inverse of :meth:`world`."""
        import numpy as np

        bl_ft, bw_ft = box_ft if box_ft is not None else (length_ft, width_ft)
        p = np.asarray(pts, dtype=float).reshape(-1, 2)
        fl, fr, bl = (np.array(q, dtype=float) for q in (self.fl, self.fr, self.bl))
        m = np.column_stack([fr - fl, bl - fl])  # columns: along, across
        uv = np.linalg.solve(m, (p - fl).T).T
        return np.column_stack([uv[:, 0] * bl_ft - (bl_ft - length_ft) / 2, uv[:, 1] * bw_ft - (bw_ft - width_ft) / 2])


def _dist_to_lines(x: float, y: float, lines: Sequence[Seg]) -> float:
    best = math.inf
    for x1, y1, x2, y2 in lines:
        dx, dy = x2 - x1, y2 - y1
        n = dx * dx + dy * dy
        t = 0.0 if n == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / n))
        best = min(best, math.hypot(x - (x1 + t * dx), y - (y1 + t * dy)))
    return best


def frame(ring: Sequence[Sequence[float]], streets: Sequence[Seg]) -> Frame:
    """Name the corners of a drawn rectangle (closed or open ring)."""
    import numpy as np

    pts = [(float(p[0]), float(p[1])) for p in ring]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) != 4:
        raise ValueError(f"the building ring has {len(pts)} corners, not 4")
    sides = [(pts[i], pts[(i + 1) % 4]) for i in range(4)]
    lengths = [math.dist(a, b) for a, b in sides]
    # The two long sides: 0/2 or 1/3.
    first = 0 if lengths[0] + lengths[2] >= lengths[1] + lengths[3] else 1
    long_sides = [sides[first], sides[first + 2]]
    long_ft = (lengths[first] + lengths[first + 2]) / 2
    short_ft = (lengths[first + 1] + lengths[(first + 3) % 4]) / 2
    front_known = bool(streets)
    if front_known:
        mids = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in long_sides]
        d = [_dist_to_lines(mx, my, streets) for mx, my in mids]
        front, back = (long_sides[0], long_sides[1]) if d[0] <= d[1] else (long_sides[1], long_sides[0])
    else:
        front, back = long_sides
    fa, fb = np.array(front[0]), np.array(front[1])
    fmid = (fa + fb) / 2
    bmid = (np.array(back[0]) + np.array(back[1])) / 2
    inward = bmid - fmid
    # Facing the building from the street is facing ``inward``; left of that
    # is ``inward`` turned a quarter anticlockwise.
    left = np.array([-inward[1], inward[0]])
    if float(np.dot(fa - fmid, left)) >= 0:
        fl, fr = fa, fb
    else:
        fl, fr = fb, fa
    ba, bb = np.array(back[0]), np.array(back[1])
    bl, br = (ba, bb) if float(np.dot(ba - fl, fr - fl)) < float(np.dot(bb - fl, fr - fl)) else (bb, ba)
    return Frame(
        fl=(float(fl[0]), float(fl[1])),
        fr=(float(fr[0]), float(fr[1])),
        bl=(float(bl[0]), float(bl[1])),
        br=(float(br[0]), float(br[1])),
        long_ft=float(long_ft),
        short_ft=float(short_ft),
        front_known=front_known,
    )


#: FD2 pass 1's six reading points, (u, v) in the frame, in its column order.
SIX_UV = (
    ("z_front_left", 0.0, 0.0),
    ("z_front_right", 1.0, 0.0),
    ("z_back_left", 0.0, 1.0),
    ("z_back_right", 1.0, 1.0),
    ("z_front_mid", 0.5, 0.0),
    ("z_back_mid", 0.5, 1.0),
)
