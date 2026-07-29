"""Synthetic-lot tests for the s6s procedural site-plan generator.

Each test builds a carved setback envelope directly (the shape s6s consumes),
plus the lot's front edge and gross area, then drives `layout_lot` and checks
the parking tier, the tightened `site_plan_ok` verdict, and geometric
invariants (non-overlap, containment, driveway reaches the street, rotation
invariance). All geometry is in feet (EPSG:2913 convention)."""

from __future__ import annotations

import pytest

pytest.importorskip("shapely")
pytest.importorskip("numpy")

import shapely  # noqa: E402
from shapely import affinity  # noqa: E402
from shapely.geometry import LineString, Polygon, box  # noqa: E402

pytestmark = pytest.mark.unit

# Gresham LDR-5 pilot defaults (mirror footprints.yaml `siteplan:` + rules).
FRONT_S, SIDE_S, REAR_S = 10.0, 5.0, 15.0


def _sp_setup(res: float = 0.5):
    import s6s_siteplan

    cfg = {
        "res": res, "gap": 5.0, "drive_travel": 12.0,
        "pods": [("pod56x36", 56.0, 36.0), ("pod80x25", 80.0, 25.0)],
        "open_space_pct": 15.0, "min_stalls": 4, "preferred_stalls": 8,
        "stall_w": 8.5, "stall_d": 18.5, "aisle_two": 24.0, "aisle_one": 20.0,
        "methods": ["driveway_frontage", "central_lot"],
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


def test_a_target_tier_full_plan():
    """67x106 lot: 6 front stalls off the street apron, pod set back behind
    them, open space to spare -> site_plan_ok, target tier, front typology."""
    s6s = _sp_setup()
    env, fe, area, lot = _rect_lot(67.0, 106.0)
    r = _run(s6s, env, fe, area)
    assert r["stalls_provided"] == 6
    assert r["layout_method"] == "driveway_frontage"
    assert r["site_plan_ok"] is True
    assert r["driveway_len_ft"] > 0
    assert r["open_space_ok"] is True
    from common import SiteplanSpec
    assert SiteplanSpec().tier_for(r["stalls_provided"]) == "target"


def test_b_tightening_pod_fits_no_parking_room():
    """Shallow lot: the pod rectangle fits (s6 would pass) but there is no
    room for the pod AND parking either in front or behind -> site_plan_ok
    False (the tightening)."""
    s6s = _sp_setup()
    env, fe, area, lot = _rect_lot(67.0, 70.0)  # envelope only 45 ft deep
    # sanity: the bare pod DOES fit the envelope (necessary-but-insufficient).
    import s6_fit
    s6_fit._init_worker({"res": 0.5,
                         "width_cells": [round(w / 0.5) for w in (12.0, 56.0)],
                         "footprints": [("pod56x36", 56.0, 36.0)]})
    fit = s6_fit.fit_lot(shapely.to_wkb(env), [0.0], True)
    assert fit["fits"]["pod56x36"][0] is True  # rectangle fits...
    r = _run(s6s, env, fe, area)               # ...but the site plan does not
    assert r["stalls_provided"] < 4
    assert r["site_plan_ok"] is False


def test_c_minimum_tier_narrow_lot():
    """Narrow deep lot: only 4 front stalls fit across the 37 ft width ->
    minimum tier, still a valid plan (front typology, no side corridor
    needed)."""
    s6s = _sp_setup()
    env, fe, area, lot = _rect_lot(47.0, 127.0)
    r = _run(s6s, env, fe, area)
    assert r["stalls_provided"] == 4
    assert r["layout_method"] == "driveway_frontage"
    assert r["site_plan_ok"] is True
    from common import SiteplanSpec
    assert SiteplanSpec().tier_for(r["stalls_provided"]) == "minimum"


def test_stalls_capped_at_preferred():
    """A big lot never reports more than the preferred tier (2/unit = 8);
    a 4-plex has no use for more parking than that."""
    s6s = _sp_setup()
    env, fe, area, lot = _rect_lot(140.0, 200.0)
    r = _run(s6s, env, fe, area)
    assert r["stalls_provided"] == 8  # capped at preferred (2/unit)
    from common import SiteplanSpec
    assert SiteplanSpec().tier_for(r["stalls_provided"]) == "preferred"


def test_e_open_space_reservation_binds():
    """A plan that seats the pod + 6 stalls + driveway but leaves < 15% of the
    gross lot as open space fails on §7.0420(D). Isolated by passing a small
    gross area against a full-size envelope."""
    s6s = _sp_setup()
    env, fe, _area, lot = _rect_lot(67.0, 106.0)
    small_area = 3000.0  # forces open-space share below 15%
    r = _run(s6s, env, fe, small_area)
    assert r["stalls_provided"] == 6          # the plan still lays out...
    assert r["open_space_ok"] is False        # ...but open space is short
    assert r["site_plan_ok"] is False


# ---------------------------------------------------------------------------
# geometric invariants
# ---------------------------------------------------------------------------


def test_d_geometry_invariants_and_rotation_invariance():
    s6s = _sp_setup()
    env, fe, area, lot = _rect_lot(67.0, 106.0)
    r = _run(s6s, env, fe, area)
    g = r["geoms"]
    assert "building" in g and "parking_court" in g

    # building and parking do not overlap
    assert g["building"].intersection(g["parking_court"]).area < 1.0

    # building + court + stalls stay inside the envelope (half-cell tolerance),
    # and NOTHING drawn ever leaves the lot (the earlier out-of-lot driveway bug)
    env_tol = env.buffer(0.6)
    lot_tol = lot.buffer(0.6)
    assert g["building"].within(env_tol)
    assert g["parking_court"].within(env_tol)
    for role, geom in g.items():
        assert geom.within(lot_tol), f"{role} leaves the lot"
        if role.startswith("stall_") or role == "parking_court":
            assert geom.within(env_tol)

    # the plan reaches the street (scalar) and parking sits against the front
    assert r["driveway_len_ft"] > 0
    assert g["parking_court"].bounds[1] <= 11.0  # court front at the envelope front

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
