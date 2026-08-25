"""Synthetic-lot tests for the s6s procedural site-plan generator.

Product = attached townhomes (Gresham §7.0431): one honest typology
`townhome_rear_court` — pod across the front, a single driveway down one SIDE to
a REAR parking court, cars in/out forward (nothing backs onto the street). Each
test builds a carved setback envelope directly (the shape s6s consumes) plus the
lot's front edge and gross area, drives `layout_lot`, and checks the parking
tier, the tightened `site_plan_ok` verdict, and the geometric invariants
(court is in the rear, driveway runs down the side and stays in the lot, nothing
leaves the lot, rotation invariance). All geometry is in feet (EPSG:2913)."""

from __future__ import annotations

import pytest

pytest.importorskip("shapely")
pytest.importorskip("numpy")

import shapely  # noqa: E402
from shapely import affinity  # noqa: E402
from shapely.geometry import box  # noqa: E402

pytestmark = pytest.mark.unit

# Gresham LDR-5 pilot defaults (mirror footprints.yaml `siteplan:` + rules).
FRONT_S, SIDE_S, REAR_S = 10.0, 5.0, 15.0


def _sp_setup(res: float = 0.5):
    import s6s_siteplan
    from common import StallGeometry, _GRESHAM_GEOMETRY

    # Gresham's own stall and aisle, taken from the one place they are written
    # rather than retyped here. Retyping them is how the 20 ft aisle survived:
    # a test that carries its own copy of a number agrees with itself forever.
    geom = StallGeometry(**_GRESHAM_GEOMETRY)
    cfg = {
        "res": res, "gap": 5.0, "drive_travel": 12.0,
        "pods": [("pod56x36", 56.0, 36.0), ("pod80x25", 80.0, 25.0)],
        "open_space_pct": 15.0, "min_stalls": 4, "preferred_stalls": 8,
        "stall_w": geom.stall_width_ft, "stall_d": geom.stall_depth_ft,
        "aisle_two": geom.aisle_two_way_ft, "aisle_one": geom.aisle_one_way_ft,
        "methods": ["townhome_rear_court"],
    }
    s6s_siteplan._init_worker(cfg)
    return s6s_siteplan


def _rect_lot(W: float, D: float):
    """A rectangular lot with the street to the south (front = the y=0 edge).

    Returns (envelope Polygon, front_edges, gross area, lot Polygon). The
    envelope is the lot inset by the Gresham LDR-5 setbacks."""
    lot = box(0.0, 0.0, W, D)
    env = box(SIDE_S, FRONT_S, W - SIDE_S, D - REAR_S)
    front_edges = [[0.0, 0.0, W, 0.0]]  # south edge, bearing 0
    return env, front_edges, W * D, lot


def _run(s6s, env, front_edges, area, bearing=0.0):
    return s6s.layout_lot(shapely.to_wkb(env), [bearing], front_edges, area, FRONT_S)


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------


def test_footprints_yaml_has_siteplan_block():
    from common import load_footprints

    fps = load_footprints()
    assert fps.siteplan is not None
    sp = fps.siteplan
    assert sp.pilot_jurisdiction == "gresham"
    assert sp.pilot_zone == "LDR-5"
    assert sp.layout_methods == ["townhome_rear_court"]
    assert (sp.min_stalls(), sp.target_stalls(), sp.preferred_stalls()) == (4, 6, 8)
    assert sp.tier_for(3) == "fail"
    assert sp.tier_for(4) == "minimum"
    assert sp.tier_for(6) == "target"
    assert sp.tier_for(9) == "preferred"


def test_largest_rect_basics():
    import numpy as np

    from s6s_siteplan import _largest_rect

    ok = np.ones((6, 10), dtype=bool)
    ok[0, :] = False  # top row blocked
    r0, c0, h, w = _largest_rect(ok)
    assert (h, w) == (5, 10)
    assert _largest_rect(np.zeros((4, 4), dtype=bool)) is None


# ---------------------------------------------------------------------------
# layout — tiers + tightening
# ---------------------------------------------------------------------------


def test_a_full_plan_wide_deep_lot():
    """Wide + deep lot: pod at the front, a 12 ft side lane, and a rear court
    with a full set of stalls all fit -> site_plan_ok, preferred tier, the one
    townhome typology."""
    s6s = _sp_setup()
    env, fe, area, lot = _rect_lot(100.0, 150.0)
    r = _run(s6s, env, fe, area)
    assert r["layout_method"] == "townhome_rear_court"
    assert r["site_plan_ok"] is True
    assert 4 <= r["stalls_provided"] <= 8
    assert r["stalls_provided"] == 8          # room for the preferred tier
    assert r["driveway_len_ft"] > 0
    assert r["open_space_ok"] is True


def test_b_tightening_shallow_no_rear_room():
    """Shallow lot: the bare pod rectangle fits (s6 would pass) but there is no
    rear yard left for a parking court -> site_plan_ok False (the tightening)."""
    s6s = _sp_setup()
    env, fe, area, lot = _rect_lot(100.0, 70.0)  # envelope only 45 ft deep
    import s6_fit
    s6_fit._init_worker({"res": 0.5,
                         "width_cells": [round(w / 0.5) for w in (12.0, 56.0)],
                         "footprints": [("pod56x36", 56.0, 36.0)]})
    fit = s6_fit.fit_lot(shapely.to_wkb(env), [0.0], True)
    assert fit["fits"]["pod56x36"][0] is True  # rectangle fits...
    r = _run(s6s, env, fe, area)               # ...but the site plan does not
    assert r["stalls_provided"] < 4
    assert r["site_plan_ok"] is False


def test_c_tightening_too_narrow_for_side_lane():
    """A lot wide enough for the pod but not for the pod PLUS a 12 ft side lane
    to the rear cannot reach rear parking -> site_plan_ok False. This is the
    townhome constraint the earlier front-row model wrongly ignored."""
    s6s = _sp_setup()
    # 46 ft lot -> 36 ft envelope: a 36 ft-wide pod fits, but 36 + 12 > 36, so no
    # side lane; and the 25 ft-wide pod can't seat 4 units across this frontage.
    env, fe, area, lot = _rect_lot(46.0, 150.0)
    r = _run(s6s, env, fe, area)
    assert r["site_plan_ok"] is False


def test_c2_minimum_tier_narrow_but_deep():
    """A narrow but deep lot seats the skinny pod with a side lane and a small
    rear court -> a valid minimum-tier plan."""
    s6s = _sp_setup()
    env, fe, area, lot = _rect_lot(52.0, 160.0)
    r = _run(s6s, env, fe, area)
    assert r["layout_method"] == "townhome_rear_court"
    assert r["site_plan_ok"] is True
    assert r["stalls_provided"] >= 4
    from common import SiteplanSpec
    assert SiteplanSpec().tier_for(r["stalls_provided"]) in ("minimum", "target",
                                                             "preferred")


def test_stalls_capped_at_preferred():
    """A big lot never reports more than the preferred tier (2/unit = 8);
    a 4-plex has no use for more parking than that."""
    s6s = _sp_setup()
    env, fe, area, lot = _rect_lot(160.0, 220.0)
    r = _run(s6s, env, fe, area)
    assert r["stalls_provided"] == 8  # capped at preferred (2/unit)
    from common import SiteplanSpec
    assert SiteplanSpec().tier_for(r["stalls_provided"]) == "preferred"


def test_e_open_space_reservation_binds():
    """A plan that seats pod + stalls + driveway but leaves < 15% of the gross
    lot as open space fails on §7.0431(D)(1). Isolated by passing a small gross
    area against a full-size envelope."""
    s6s = _sp_setup()
    env, fe, _area, lot = _rect_lot(100.0, 150.0)
    small_area = 5000.0  # forces open-space share below 15%
    r = _run(s6s, env, fe, small_area)
    assert r["stalls_provided"] >= 4          # the plan still lays out...
    assert r["open_space_ok"] is False        # ...but open space is short
    assert r["site_plan_ok"] is False


# ---------------------------------------------------------------------------
# geometric invariants
# ---------------------------------------------------------------------------


def test_d_geometry_invariants_and_rotation_invariance():
    s6s = _sp_setup()
    env, fe, area, lot = _rect_lot(100.0, 150.0)
    r = _run(s6s, env, fe, area)
    assert r["site_plan_ok"] is True
    g = r["geoms"]
    assert {"building", "parking_court", "driveway"} <= set(g)

    tol = 0.6  # ~one cell
    env_tol = env.buffer(tol)
    lot_tol = lot.buffer(tol)

    # building + court inside the envelope; nothing drawn leaves the lot
    assert g["building"].within(env_tol)
    assert g["parking_court"].within(env_tol)
    for role, geom in g.items():
        assert geom.within(lot_tol), f"{role} leaves the lot"

    # the court sits in the REAR: its near edge is behind the building
    assert g["parking_court"].bounds[1] >= g["building"].bounds[3] - tol

    # building and parking do not overlap
    assert g["building"].intersection(g["parking_court"]).area < 1.0

    # the driveway runs down the SIDE (not across the front): its footprint does
    # not overlap the building, it touches the street, and it reaches the court
    assert g["driveway"].intersection(g["building"]).area < 1.0
    assert g["driveway"].bounds[1] <= FRONT_S + 1.0            # touches the front
    assert g["driveway"].bounds[3] >= g["parking_court"].bounds[1] - tol  # to court

    # stalls sit in the rear court, inside the envelope
    for role, geom in g.items():
        if role.startswith("stall_"):
            assert geom.within(env_tol)
            assert geom.bounds[1] >= g["building"].bounds[3] - tol

    # rotation invariance: rotate the whole lot 30deg, results must match
    theta = 30.0
    env_r = affinity.rotate(env, theta, origin=(0.0, 0.0))
    fe_r = []
    for x1, y1, x2, y2 in fe:
        p1 = affinity.rotate(shapely.geometry.Point(x1, y1), theta, origin=(0.0, 0.0))
        p2 = affinity.rotate(shapely.geometry.Point(x2, y2), theta, origin=(0.0, 0.0))
        fe_r.append([p1.x, p1.y, p2.x, p2.y])
    r_rot = _run(s6s, env_r, fe_r, area, bearing=theta)
    assert r_rot["stalls_provided"] == r["stalls_provided"]
    assert r_rot["site_plan_ok"] == r["site_plan_ok"]
    assert r_rot["layout_method"] == r["layout_method"]
