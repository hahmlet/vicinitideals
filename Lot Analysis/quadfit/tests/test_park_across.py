"""s4's ORCA reading (`park_across`, `load_orca`) at real coordinates.

The lot is Troutdale 1N3E25DC-00402 (MU-2, tier B) as s4 traced it on the
2026-09-28 tree, Oregon North state-plane feet; the park is Glenn Otto Park
(ORCA UNITTYPE Park, owner City of Troutdale), release 2026_08, clipped to
40 ft around the lot and simplified to half a foot. The park wraps the lot's
south corner: the whole of its first rear line (the shared boundary) and the
eastern two-fifths of its south side line. The fabric reads MU-2 across both
-- the park sits on a zoned taxlot -- which is why the zone reading could not
say "park" and this one exists. The two east lines face the blank to the
east, which ORCA does not hold either.
"""

from __future__ import annotations

import json
import math

import pytest

pytest.importorskip("shapely")
pytest.importorskip("numpy")

import numpy as np  # noqa: E402
import shapely  # noqa: E402

pytestmark = pytest.mark.unit

EDGES = [
    [7720598.95, 687549.29, 7720543.06, 687521.52, "R"],
    [7720543.06, 687521.52, 7720502.82, 687535.09, "S"],
    [7720502.82, 687535.09, 7720493.85, 687553.16, "F"],
    [7720493.85, 687553.16, 7720610.39, 687611.07, "F"],
    [7720610.39, 687611.07, 7720607.8, 687593.69, "F"],
    [7720607.8, 687593.69, 7720600.03, 687577.02, "R"],
    [7720600.03, 687577.02, 7720598.95, 687549.29, "R"],
]
LOT = shapely.Polygon([(e[0], e[1]) for e in EDGES])
GLENN_OTTO = [
    shapely.from_wkt(
        "POLYGON ((7720527.07 687508.92, 7720524.67 687527.73, 7720543.06 687521.52, "
        "7720598.96 687549.3, 7720598.33 687510.12, 7720602.26 687492.26, 7720602.7 687482.53, "
        "7720650.34 687513.3, 7720650.34 687481.54, 7720528.94 687481.54, 7720538.24 687494.28, "
        "7720527.07 687508.92))"
    ),
    shapely.from_wkt(
        "POLYGON ((7720602.26 687492.26, 7720598.33 687510.12, 7720598.96 687549.3, "
        "7720650.34 687574.93, 7720650.34 687513.3, 7720602.7 687482.53, 7720602.26 687492.26))"
    ),
]


def _samples(lot, edges, offset=2.0):
    """Five points per non-street edge, `offset` feet outside the lot, in
    the (outer_x, outer_y, inner_x, inner_y) form s4's classify_lot writes;
    a street edge is None."""
    from s4_edges import ALLEY_SAMPLES

    out = []
    for x1, y1, x2, y2, cls in edges:
        if cls == "F":
            out.append(None)
            continue
        ln = math.hypot(x2 - x1, y2 - y1)
        nx, ny = (y2 - y1) / ln, -(x2 - x1) / ln
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        if lot.contains(shapely.Point(mx + nx * offset, my + ny * offset)):
            nx, ny = -nx, -ny
        pts = []
        for t in ALLEY_SAMPLES:
            px, py = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
            pts.append((px + nx * offset, py + ny * offset, px - nx * offset, py - ny * offset))
        out.append(pts)
    return out


def _result():
    return {"edges": EDGES, "neighbour_samples": _samples(LOT, EDGES)}


def test_the_park_is_read_across_the_two_lines_it_lies_beside():
    from s4_edges import park_across

    geoms = np.array(GLENN_OTTO, dtype=object)
    kinds = np.array(["Park", "Park"], dtype=object)
    (got,) = park_across([_result()], geoms, kinds)
    assert len(got) == len(EDGES)
    # Street edges are never asked.
    assert [e is None for e in got] == [c == "F" for *_xy, c in EDGES]
    assert got[0] == {"k": ["Park"], "none": 0}, "the shared boundary with the park"
    # Two of five points in the park and three not: still a line across a
    # park, and the count says how much of it was.
    assert got[1] == {"k": ["Park"], "none": 3}
    assert got[5] == {"k": [], "none": 5}
    assert got[6] == {"k": [], "none": 5}


def test_every_kind_seen_is_kept_rather_than_a_vote():
    from s4_edges import park_across

    # The park's west unit retyped, and a natural area laid over the south
    # side line's western points: that line sees both kinds, not a majority.
    wetland = shapely.box(7720500.0, 687525.0, 7720520.0, 687545.0)
    geoms = np.array([*GLENN_OTTO, wetland], dtype=object)
    kinds = np.array(["Park", "Park", "Natural Area"], dtype=object)
    (got,) = park_across([_result()], geoms, kinds)
    assert got[0]["k"] == ["Park"]
    assert got[1]["k"] == ["Natural Area", "Park"]
    assert got[1]["none"] == 1


def test_no_orca_units_reads_every_line_as_in_none():
    from s4_edges import park_across

    (got,) = park_across([_result()], np.array([], dtype=object), np.array([], dtype=object))
    assert [e for e in got if e is not None] == [{"k": [], "none": 5}] * 4


def test_an_untraced_lot_is_an_empty_record():
    from s4_edges import park_across

    geoms = np.array(GLENN_OTTO, dtype=object)
    (got,) = park_across([{"edges": [], "neighbour_samples": []}], geoms, np.array(["Park", "Park"], dtype=object))
    assert got == []


def test_the_raw_file_absent_is_none_and_present_is_its_typed_units(tmp_path):
    from s4_edges import load_orca

    assert load_orca(tmp_path / "rlis_orca.geojson") is None
    path = tmp_path / "rlis_orca.geojson"
    features = [
        {"type": "Feature", "properties": {"UNITTYPE": "Park", "SITENAME": "Glenn Otto Park"},
         "geometry": shapely.geometry.mapping(GLENN_OTTO[0])},
        # No type: a point in it could not say what kind of land it is.
        {"type": "Feature", "properties": {"UNITTYPE": None}, "geometry": shapely.geometry.mapping(GLENN_OTTO[1])},
        {"type": "Feature", "properties": {"UNITTYPE": "Cemetery"}, "geometry": None},
    ]
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    geoms, kinds = load_orca(path)
    assert list(kinds) == ["Park"]
    assert geoms[0].equals(GLENN_OTTO[0])
