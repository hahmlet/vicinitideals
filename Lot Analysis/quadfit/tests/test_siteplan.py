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
    from common import StallGeometry, _GRESHAM_GEOMETRY, load_footprints

    # Gresham's own stall and aisle, taken from the one place they are written
    # rather than retyped here. Retyping them is how the 20 ft aisle survived:
    # a test that carries its own copy of a number agrees with itself forever.
    geom = StallGeometry(**_GRESHAM_GEOMETRY)
    # The same argument now covers the lane, the curb cut, the building gap and
    # the open-space reserve, which stopped being global constants and became
    # Gresham's own numbers -- so they are read out of the shipped config the
    # way s6s reads them rather than copied in here. The cut is 10 ft, from
    # GDC 7.0420: narrower than the lane, which is legal and is the whole
    # correction (the 18 ft that used to sit here was the townhouse chapter's).
    sp = load_footprints().siteplan
    dw = sp.driveway_for("gresham")
    cfg = {
        "res": res,
        "pods": [("pod56x36", 56.0, 36.0), ("pod80x25", 80.0, 25.0)],
        "min_stalls": 4, "preferred_stalls": 8,
        "cells": {"gresham": {
            "stall_w": geom.stall_width_ft, "stall_d": geom.stall_depth_ft,
            "aisle_two": geom.aisle_two_way_ft, "aisle_one": geom.aisle_one_way_ft,
            "cap": 8,
            "lane": sp.lane_ft_for("gresham"), "cut": sp.curb_cut_ft_for("gresham"),
            "gap": sp.gap_ft_for("gresham"),
            "open_pct": dw.open_space_pct or 0.0,
            "open_sqft": dw.open_space_sqft or 0.0,
            "open_by_zone": dict(dw.open_space_sqft_by_zone),
            "alley_access": bool(dw.alley_access_required),
            "alley_aisle": bool(dw.alley_is_aisle),
            "alley_need": (dw.alley_backout_ft if dw.alley_backout_ft is not None
                           else geom.aisle_one_way_ft),
            "front_rule": dw.front_lot_line_corner,
            "access_rule": dw.corner_access_street,
            "front_ban": bool(dw.parking_front_prohibited),
        }},
        "methods": ["townhome_rear_court", "townhome_rear_court_side_street",
                    "townhome_rear_court_rear_street", "townhome_rear_court_alley",
                    "townhome_rear_court_alley_aisle", "townhome_side_court",
                    "townhome_side_court_alley"],
    }
    s6s_siteplan._init_worker(cfg)
    return s6s_siteplan


def _sp_setup_cities(res: float = 0.5):
    """The same worker, wired for every city s6s can actually dimension.

    `_sp_setup` above is Gresham alone, which is what most of this file wants.
    This one exists for the tests that compare cities, because the point of
    per-city numbers is only visible with two of them side by side.
    """
    import s6s_siteplan
    from common import load_footprints

    sp = load_footprints().siteplan

    def cell(j):
        g, dw = sp.geometry_for(j), sp.driveway_for(j)
        return {
            "stall_w": g.stall_width_ft, "stall_d": g.stall_depth_ft,
            "aisle_one": g.aisle_one_way_ft, "aisle_two": g.aisle_two_way_ft,
            "cap": sp.stall_cap_for(j),
            "lane": sp.lane_ft_for(j), "cut": sp.curb_cut_ft_for(j),
            "gap": sp.gap_ft_for(j),
            "open_pct": (dw.open_space_pct or 0.0) if dw else 0.0,
            "open_sqft": (dw.open_space_sqft or 0.0) if dw else 0.0,
            "open_by_zone": dict(dw.open_space_sqft_by_zone) if dw else {},
            "alley_access": bool(dw and dw.alley_access_required),
            "alley_aisle": bool(dw and dw.alley_is_aisle),
            "alley_need": (dw.alley_backout_ft
                           if dw and dw.alley_backout_ft is not None
                           else g.aisle_one_way_ft),
            "front_rule": dw.front_lot_line_corner if dw else None,
            "access_rule": dw.corner_access_street if dw else None,
            "front_ban": bool(dw and dw.parking_front_prohibited),
        }

    s6s_siteplan._init_worker({
        "res": res,
        "pods": [("pod56x36", 56.0, 36.0), ("pod80x25", 80.0, 25.0)],
        "min_stalls": 4, "preferred_stalls": 8,
        "cells": {j: cell(j) for j in sp.cities_it_can_dimension()},
        "methods": list(sp.layout_methods),
    })
    return s6s_siteplan


def _rect_lot(W: float, D: float):
    """A rectangular lot with the street to the south (front = the y=0 edge).

    Returns (envelope Polygon, front_edges, gross area, lot Polygon). The
    envelope is the lot inset by the Gresham LDR-5 setbacks."""
    lot = box(0.0, 0.0, W, D)
    env = box(SIDE_S, FRONT_S, W - SIDE_S, D - REAR_S)
    front_edges = [[0.0, 0.0, W, 0.0]]  # south edge, bearing 0
    return env, front_edges, W * D, lot


def _run(s6s, env, front_edges, area, bearing=0.0, jurisdiction="gresham",
         zone="", parking_setback_ft=None, front_setback_ft=None,
         alley_edges=None, alley_setback_ft=0.0, alley_width_ft=None,
         bearings=None, street_setback_ft=None, lot_xy=None):
    return s6s.layout_lot(
        shapely.to_wkb(env), [bearing] if bearings is None else bearings,
        front_edges, area,
        FRONT_S if front_setback_ft is None else front_setback_ft,
        jurisdiction, zone, parking_setback_ft, alley_edges, alley_setback_ft,
        alley_width_ft, street_setback_ft, lot_xy)


def _corner_lot(W: float, D: float, notch=None):
    """A rectangular corner lot: the street to the south (W ft of front lot
    line, bearing 0) and a second street up the EAST side (D ft, bearing 90).
    Both street edges are inset by FRONT_S, the way s5 cuts every street
    edge of a corner lot; the west side by SIDE_S and the north by REAR_S.
    `notch` is a box carved out of the envelope. Bearings come in s4's order,
    the longer street first, which is the front the drawing took before
    FOLLOWUPS 5.

    Returns (envelope, front_edges, bearings, gross area)."""
    lot = box(0.0, 0.0, W, D)
    env = box(SIDE_S, FRONT_S, W - FRONT_S, D - REAR_S)
    if notch is not None:
        env = env.difference(notch)
    fe = [[0.0, 0.0, W, 0.0], [W, 0.0, W, D]]
    bearings = [90.0, 0.0] if D > W else [0.0, 90.0]
    return env, fe, bearings, lot.area


def _with_words(s6s, jurisdiction, front_rule, access_rule):
    """The same worker with one city's two corner-lot words replaced, for a
    test about the words rather than the city."""
    s6s._CFG["cells"][jurisdiction]["front_rule"] = front_rule
    s6s._CFG["cells"][jurisdiction]["access_rule"] = access_rule
    return s6s


def _through_lot(W: float, D: float):
    """A rectangular through lot: a street at the south end AND the north
    end, one bearing (s4 clusters mod 180), both ends inset by FRONT_S the
    way s5 cuts every street edge, the sides by SIDE_S.

    Returns (envelope, front_edges, bearings, gross area, corners)."""
    env = box(SIDE_S, FRONT_S, W - SIDE_S, D - FRONT_S)
    fe = [[0.0, 0.0, W, 0.0], [0.0, D, W, D]]
    xy = [(0.0, 0.0), (W, 0.0), (W, D), (0.0, D)]
    return env, fe, [0.0], W * D, xy


def _alley_lot(W: float, D: float, where: str = "rear"):
    """A rectangular lot with the street to the south and an alley on one
    other side. The alley edge is set back as a REAR lot line (s5 does the
    same), so the envelope is inset by REAR_S along it whichever side it is.

    Returns (envelope, front_edges, alley_edges, gross area)."""
    lot = box(0.0, 0.0, W, D)
    fe = [[0.0, 0.0, W, 0.0]]
    if where == "rear":
        env = box(SIDE_S, FRONT_S, W - SIDE_S, D - REAR_S)
        ae = [[0.0, D, W, D]]
    elif where == "right":
        env = box(SIDE_S, FRONT_S, W - REAR_S, D - REAR_S)
        ae = [[W, 0.0, W, D]]
    elif where == "left":
        env = box(REAR_S, FRONT_S, W - SIDE_S, D - REAR_S)
        ae = [[0.0, 0.0, 0.0, D]]
    else:
        raise ValueError(where)
    return env, fe, ae, lot.area


def _run_pdx(s6s, env, fe, ae, area, bearing=0.0, alley_width_ft=20.0):
    """Portland's cell, with the alley edges, the alley setback and the
    alley's measured width handed in the way s6s main() hands them. The
    width defaults to the twenty feet Portland's back-out rule asks, so a
    test about the drawing and not the width owes nothing on the lot."""
    return _run(s6s, env, fe, area, bearing=bearing, jurisdiction="portland",
                zone="R5", parking_setback_ft=10.0,
                alley_edges=ae, alley_setback_ft=REAR_S,
                alley_width_ft=alley_width_ft)


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
    assert sp.scope == "every_city_it_can_dimension"
    assert sp.plat == "one_lot"
    assert sp.layout_methods == ["townhome_rear_court", "townhome_rear_court_side_street",
                                 "townhome_rear_court_rear_street",
                                 "townhome_rear_court_alley", "townhome_rear_court_alley_aisle",
                                 "townhome_side_court", "townhome_side_court_alley"]
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
    # 46 ft lot -> a 36 ft envelope, which the 36 ft-wide pod misses by the
    # half-cell the raster leaves at the edge. So the only pod that seats here
    # is the skinny one, 80 ft deep, and what actually stops the plan is the
    # 39 ft of court left behind it -- 3.5 ft short of one row of stalls and a
    # two-way aisle. `layout_fail` says so; see the two tests that assert it.
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


# ---------------------------------------------------------------------------
# scope — which cities get laid out, and what stops one
# ---------------------------------------------------------------------------


def test_the_cities_laid_out_are_the_ones_that_state_an_aisle():
    """Scope is a consequence of reading, not a cell somebody chose.

    This stage was one cell for as long as one city's stall had been read. Now
    that seven have, the list has to be derived rather than typed — otherwise
    the next city read changes nothing and nobody notices for a month.
    """
    from common import load_footprints

    sp = load_footprints().siteplan
    laid_out = sp.cities_it_can_dimension()

    assert laid_out == sorted(laid_out), "order has to be stable across runs"
    for j in laid_out:
        assert sp.geometry_for(j).lays_out()
    for j in set(sp.geometry) - set(laid_out):
        geom = sp.geometry_for(j)
        assert geom is None or not geom.lays_out(), (
            f"{j} can be dimensioned and is not being laid out"
        )
    # Milwaukie stood here as the live example of the refusal until
    # 2026-08-31, when it and Wilsonville were given an assumed aisle and the
    # declined list went empty. The machinery is still needed -- a code really
    # may state a stall and no aisle -- but it is now held on a constructed
    # geometry rather than on a jurisdiction, for the reason its sibling in
    # test_parking_geometry.py already gives: a test pinned to a live city
    # goes green on a misreading and red when the misreading is corrected.
    from common import StallGeometry

    assert not StallGeometry(stall_width_ft=9, stall_depth_ft=18).lays_out()

    # What replaces it is the stronger claim the empty list makes possible:
    # every aisle in the shipped config is accounted for. Either the city
    # published it, or it is flagged as assumed and names where it came from.
    # There is no third state, and an unexplained number cannot hide in one.
    for j in laid_out:
        geom = sp.geometry_for(j)
        assert geom.aisle_assumed == bool(geom.aisle_cite.strip())
        assert geom.cite or geom.aisle_cite, (
            f"{j} is laid out to an aisle with no source of any kind"
        )


def test_a_stated_maximum_beats_the_marketability_target():
    """Milwaukie caps a quadplex at one space per unit — four, not eight.

    The three tiers are Steph's marketability targets and the law is only ever
    consulted for the floor. It has an opinion about the ceiling too, and where
    it does, the preferred tier is not something that city will permit however
    much room the lot has.
    """
    from common import SiteplanSpec, StallGeometry

    sp = SiteplanSpec(geometry={
        "milwaukie": StallGeometry(stall_width_ft=9.0, stall_depth_ft=18.0,
                                   aisle_one_way_ft=24.0, aisle_two_way_ft=24.0,
                                   max_per_unit=1.0),
        "gresham": StallGeometry(stall_width_ft=8.5, stall_depth_ft=18.5,
                                 aisle_one_way_ft=23.0, aisle_two_way_ft=24.0),
    })
    assert sp.stall_cap_for("milwaukie") == 4   # 1/unit x 4 units
    assert sp.stall_cap_for("gresham") == 8     # no ceiling: the target stands
    assert sp.geometry["milwaukie"].stall_ceiling(4) == 4
    assert sp.geometry["gresham"].stall_ceiling(4) is None
    # 1.35/unit (Portland's multi-dwelling zones) is 5.4 spaces, and a fifth of
    # a stall is not a stall.
    assert StallGeometry(stall_width_ft=9.0, stall_depth_ft=18.0,
                         max_per_unit=1.35).stall_ceiling(4) == 5


def test_the_ceiling_binds_the_layout_and_not_just_the_arithmetic():
    """A lot with room for eight seats four where the city permits four."""
    s6s = _sp_setup()
    s6s._CFG["cells"]["milwaukie_like"] = dict(s6s._CFG["cells"]["gresham"], cap=4)
    env, fe, area, lot = _rect_lot(160.0, 220.0)
    assert _run(s6s, env, fe, area)["stalls_provided"] == 8
    capped = _run(s6s, env, fe, area, jurisdiction="milwaukie_like")
    assert capped["stalls_provided"] == 4
    assert capped["site_plan_ok"] is True  # four stalls is still the floor


def test_oregon_city_stands_down_on_the_other_plat_path():
    """Its parking chapter reaches a quadplex and excludes townhouses.

    OCMC 17.52.010 lists what Chapter 17.52 does not apply to and townhouses
    are on the list; triplexes and quadplexes are not. So the same four units
    are dimensioned on one lot and undimensioned on four, and which one the
    pipeline draws is a decision it has to state rather than inherit.
    """
    from common import load_footprints

    fps = load_footprints()
    sp = fps.siteplan
    assert sp.plat == "one_lot"
    assert sp.geometry["oregon_city"].stands_down_on == ["unit_lots"]
    assert sp.geometry_for("oregon_city") is not None
    assert "oregon_city" in sp.cities_it_can_dimension()

    on_unit_lots = sp.model_copy(update={"plat": "unit_lots"})
    assert on_unit_lots.geometry_for("oregon_city") is None
    assert "oregon_city" not in on_unit_lots.cities_it_can_dimension()


# ---------------------------------------------------------------------------
# per-city driveway and open space
# ---------------------------------------------------------------------------


def test_happy_valleys_twenty_foot_driveway_costs_it_lots_gresham_keeps():
    """The one number in the driveway family that takes lots away.

    HV LDC 16.41.030.B.1 improves a two-way drive to twenty feet where every
    other city here says twelve or says nothing, and the lane this typology
    draws is two-way. Eight extra feet of side yard, for the depth of the
    building, is the whole difference on a lot this width.

    Both cities are given the SAME envelope on purpose. Their setbacks differ
    and that is not what is being measured: hold the buildable rectangle still
    and the only thing left moving is the lane.

    Eighty feet wide, not eighty-five: since 2026-09-19 a lot whose envelope
    is 72 ft wide seats a SIDE court beside the end-on pod, and the lane to a
    side court runs inside the court's 24 ft aisle, where twenty feet is no
    harder than twelve -- on the 85 ft lot Happy Valley parks eight that way.
    At 80 the side court does not fit and the rear court's lane is again the
    whole difference."""
    s6s = _sp_setup_cities()
    env, fe, area, _ = _rect_lot(80.0, 120.0)

    r = _run(s6s, env, fe, area, jurisdiction="gresham")
    assert r["site_plan_ok"] and r["layout_method"] == "townhome_rear_court"
    assert not _run(s6s, env, fe, area,
                    jurisdiction="happy_valley")["site_plan_ok"]

    # Fifteen feet wider and Happy Valley resolves too -- the refusal above is
    # the lane and not something structural about the city.
    env, fe, area, _ = _rect_lot(95.0, 120.0)
    assert _run(s6s, env, fe, area, jurisdiction="happy_valley")["site_plan_ok"]


def test_the_open_space_charged_is_the_citys_own_and_greshams_is_greshams():
    """Fifteen percent used to come off every lot in every city.

    It is GDC 7.0420(D)(1), and Happy Valley states no private open space
    standard for this building at all -- its only candidate is a footnote
    hanging on the wrong table, pointing at a section that does not contain
    the phrase. A reserve charged to a city that never asked for one is a lot
    refused for nothing, so what is asserted here is the zero.
    """
    s6s = _sp_setup_cities()
    env, fe, area, _ = _rect_lot(95.0, 120.0)

    gresham = _run(s6s, env, fe, area, jurisdiction="gresham")
    hv = _run(s6s, env, fe, area, jurisdiction="happy_valley")

    assert gresham["open_space_req_sqft"] == pytest.approx(0.15 * area)
    assert hv["open_space_req_sqft"] == 0.0


def test_greshams_curb_cut_is_narrower_than_the_lane_and_that_is_legal():
    """Ten feet at the property line, twelve behind it.

    GDC 7.0420(B)(2)(b)(ii) caps the APPROACH of a garage-less fourplex at ten
    feet, and 7.0431's eighteen -- which is what this stage used to draw
    everywhere -- is the townhouse chapter's combined figure on four lots. The
    approach standard governs the opening where it meets the street and
    nothing behind it, so the cut narrows and the drive stays a drive.
    """
    s6s = _sp_setup_cities()
    env, fe, area, _ = _rect_lot(95.0, 120.0)
    r = _run(s6s, env, fe, area, jurisdiction="gresham")

    assert r["site_plan_ok"]
    assert r["driveway_width_ft"] == 10.0



def test_a_street_setback_pushes_the_court_back_and_only_the_excess_counts():
    """Happy Valley LDC 16.43.030.E.4, and the arithmetic that makes it free.

    The rule measures from the STREET LOT LINE. The envelope handed to this
    stage is already inset from that line by the building setback, so what is
    left to enforce is the difference -- and Happy Valley sets the parking
    setback TO the building setback, which makes the difference zero in every
    district it permits a quadplex in.

    Asserted from both ends. A setback equal to the front yard moves nothing;
    one far beyond it eats the lot from the street inwards, which is the
    behaviour a city printing a bigger number would get.
    """
    s6s = _sp_setup()
    env, fe, area, _ = _rect_lot(95.0, 120.0)

    free = _run(s6s, env, fe, area, parking_setback_ft=FRONT_S)
    none = _run(s6s, env, fe, area)
    assert free["site_plan_ok"] and none["site_plan_ok"]
    assert free["stalls_provided"] == none["stalls_provided"]

    # 80 ft of street setback on a 120 ft lot leaves no room behind the pod.
    assert not _run(s6s, env, fe, area, parking_setback_ft=80.0)["site_plan_ok"]


def test_happy_valleys_own_numbers_cost_it_nothing():
    """Every district Happy Valley permits a quadplex in sets a building back
    at least twenty feet, so a court that clears the building setback clears
    the parking setback by the same sentence that created it.

    This is the claim the encoding makes, checked against the shipped mirror
    rather than against a number typed here: the rule is real, it is wired up,
    and it takes no lot away.
    """
    from common import load_footprints

    sp = load_footprints().siteplan
    s6s = _sp_setup_cities()
    env, fe, area, _ = _rect_lot(95.0, 120.0)

    for zone in ("R40", "R5", "R20CC"):
        asks = sp.parking_street_setback_for("happy_valley", zone)
        assert asks is not None and asks >= 20
        # The envelope this stage is handed was cut to that same setback, so
        # `front_setback_ft` is the parking setback -- that identity IS the
        # rule, and passing FRONT_S here would be testing a lot Happy Valley
        # does not have.
        with_rule = _run(s6s, env, fe, area, jurisdiction="happy_valley",
                         zone=zone, parking_setback_ft=asks,
                         front_setback_ft=asks)
        without = _run(s6s, env, fe, area, jurisdiction="happy_valley",
                       zone=zone, front_setback_ft=asks)
        assert with_rule["site_plan_ok"] == without["site_plan_ok"]
        assert with_rule["stalls_provided"] == without["stalls_provided"]


# ---------------------------------------------------------------------------
# layout_fail — why a lot got no plan
# ---------------------------------------------------------------------------


def test_a_lot_with_a_plan_names_no_failure():
    """The empty string is load-bearing: it is what tells a reader that a blank
    `layout_fail` on a resolved lot is an answer rather than a missing one."""
    s6s = _sp_setup()
    env, fe, area, lot = _rect_lot(100.0, 150.0)
    r = _run(s6s, env, fe, area)
    assert r["site_plan_ok"] is True
    assert r["layout_fail"] == ""


def test_a_lot_too_small_for_the_building_says_so():
    """The product is too big for the land. This is the answer that means the
    lot is out of reach of any typology, and it must not be confused with the
    two below, which are about how we lay a lot out rather than its size."""
    s6s = _sp_setup()
    env, fe, area, lot = _rect_lot(30.0, 40.0)
    r = _run(s6s, env, fe, area)
    assert r["site_plan_ok"] is False
    assert r["layout_fail"] == "no_building"


def test_a_shallow_lot_blames_the_court_not_the_building():
    """`test_b_tightening_shallow_no_rear_room` proves the verdict; this proves
    the *reason*, which is the part that decides whether a second typology
    would pay. The pod fits and the ground behind it will not hold a car."""
    s6s = _sp_setup()
    env, fe, area, lot = _rect_lot(100.0, 70.0)
    r = _run(s6s, env, fe, area)
    assert r["site_plan_ok"] is False
    assert r["layout_fail"] == "court_too_shallow"


def test_a_narrow_lot_blames_the_lane():
    """48 ft of frontage seats the pod and leaves nothing to drive down. That
    is a rule about driveway width, not a fact about the parcel, so it gets its
    own answer: these are the lots a shared-access or tandem reading reaches.

    The wide pod places, carves a two-row court, and then finds 2 ft of gap
    beside itself where the lane wants 12. The skinny pod does leave a lane but
    stops one stage earlier, and the reason reported is the furthest of the two.
    """
    s6s = _sp_setup()
    env, fe, area, lot = _rect_lot(48.0, 150.0)
    r = _run(s6s, env, fe, area)
    assert r["site_plan_ok"] is False
    assert r["layout_fail"] == "no_side_lane"


def test_a_lot_two_feet_short_of_a_court_blames_the_court():
    """The same frontage two feet narrower, and a different answer.

    At 46 ft the wide pod no longer places at all, so the only attempt left is
    the 80 ft-deep skinny pod, and the 39 ft behind it is 3.5 ft short of a
    stall and a two-way aisle. Nothing about the lane is reached or reported.
    These two lots differ by two feet of frontage and belong to different
    piles: this one is answered by a shallower parking bay, the other by a
    narrower driveway, and lumping them together hides both.
    """
    s6s = _sp_setup()
    env, fe, area, lot = _rect_lot(46.0, 150.0)
    r = _run(s6s, env, fe, area)
    assert r["site_plan_ok"] is False
    assert r["layout_fail"] == "court_too_shallow"


def test_a_one_row_court_is_sized_to_the_two_way_aisle():
    """A court reached down one lane is two-way, one row of stalls or two.

    Until 2026-09-17 a one-row court was sized to the city's ONE-way aisle --
    a figure for a court with an exit at the far end -- while the paper lot
    (`flats.score.paper.court_depth`) charged the two-way one, on the reading
    that a car leaves this court the way it came. The two figures differ in
    Gresham (23 / 24) and Wood Village (12 / 24), and in both the county
    drawing was the shallower: 121 plans stood on a court a two-way aisle
    does not fit, 56 of them in Wood Village on 12 ft of pavement behind a
    90-degree stall. This pins the drawing to the paper lot's reading.
    """
    s6s = _sp_setup()
    # Gresham: 18.5 ft stall. Behind the wide pod on a 109 ft lot the court
    # is 42 ft -- a row on the one-way figure (41.5), none on the two-way
    # (42.5). A foot deeper and the row is back, charged at 24. The lot is
    # 80 ft wide so the skinny pod cannot lie broadside and stop one stage
    # later for want of a lane, and so no SIDE court stands beside it
    # end-on (25 + 5 + 42.5 asks 72.5 ft of envelope; 88 ft wide, the lot
    # parked eight beside the pod and the reason reported was gone); the
    # reason reported is the rear court's.
    env, fe, area, lot = _rect_lot(80.0, 109.0)
    r = _run(s6s, env, fe, area)
    assert r["site_plan_ok"] is False and r["layout_fail"] == "court_too_shallow"
    env, fe, area, lot = _rect_lot(80.0, 110.0)
    r = _run(s6s, env, fe, area)
    assert r["site_plan_ok"] is True and r["layout_method"] == "townhome_rear_court"
    minx, miny, maxx, maxy = r["geoms"]["parking_court"].bounds
    assert maxy - miny < 2 * 18.5 + 24.0                       # one row
    assert r["parking_area_sqft"] == pytest.approx(
        r["stalls_provided"] * 8.5 * 18.5 + 24.0 * (maxx - minx))
    # Wood Village prints 12 ft one-way and 24 two-way against the same
    # 9 x 19 stall (WVDC Table 350-3, 90 degrees). A 36 ft court held a row
    # on the 12; it holds none on the 24.
    s6s._CFG["cells"]["wood_village_like"] = dict(
        s6s._CFG["cells"]["gresham"], stall_w=9.0, stall_d=19.0,
        aisle_one=12.0, aisle_two=24.0)
    env, fe, area, lot = _rect_lot(80.0, 102.0)
    r = _run(s6s, env, fe, area, jurisdiction="wood_village_like")
    assert r["site_plan_ok"] is False and r["layout_fail"] == "court_too_shallow"
    env, fe, area, lot = _rect_lot(80.0, 110.0)
    r = _run(s6s, env, fe, area, jurisdiction="wood_village_like")
    assert r["site_plan_ok"] is True
    minx, miny, maxx, maxy = r["geoms"]["parking_court"].bounds
    assert r["parking_area_sqft"] == pytest.approx(
        r["stalls_provided"] * 9.0 * 19.0 + 24.0 * (maxx - minx))


def test_the_reason_is_the_furthest_attempt_not_the_last():
    """Two pods in two orientations each, and the reason reported is the best
    of the four. A lot the wide pod cannot even sit on, but the narrow one can
    while failing later, must report the LATER failure -- otherwise every
    number in this table is dragged toward `no_building` by whichever pod
    happened to be tried last."""
    s6s = _sp_setup()
    # 52 x 90: the 56 ft pod does not fit the 42 ft-wide envelope in either
    # orientation; the 80x25 does, rotated, and then runs out of rear yard.
    env, fe, area, lot = _rect_lot(52.0, 90.0)
    r = _run(s6s, env, fe, area)
    assert r["site_plan_ok"] is False
    assert r["layout_fail"] != "no_building"


def test_a_drawn_plan_short_of_stalls_is_not_a_geometry_failure():
    """A lot that DID lay out and was rejected on stall count is not land that
    cannot hold the product, and pooling the two would overstate the geometric
    ceiling. Gresham reserves 15% of the gross lot as open space, so a small
    gross area against a full envelope rejects a real plan."""
    s6s = _sp_setup()
    env, fe, area, lot = _rect_lot(100.0, 150.0)
    r = _run(s6s, env, fe, 1000.0)   # gross area far below the plan's footprint
    assert r["site_plan_ok"] is False
    assert r["layout_fail"] == "no_open_space"


# ---------------------------------------------------------------------------
# the alley -- PCC 33.266.120.C.3, "all parking and vehicle access to the
# site must be from the alley"
# ---------------------------------------------------------------------------


def test_footprints_yaml_sends_four_cities_driveways_to_the_alley():
    """Portland (PCC 33.266.120.C.3), Gresham (GDC 7.0420(B)(1), "Lots,
    including middle housing without existing access, that abut an alley,
    shall take access from the alley"), Wilsonville (4.113(.14)(D)(4)(c)(i),
    "access must be taken from the alley") and West Linn (48.025(B)(3)(a),
    "direct access to a public street is not permitted") send the driveway
    round the back, and each says so on its own row with the section beside
    it. Pinned as a set: the flag must not leak to a city by default, and a
    city joining needs its sentence read. Milwaukie is NOT here: its one
    alley sentence places a stall, it does not route the driveway. (Until
    2026-09-12 this test said Gresham had no such sentence; it had, in the
    chapter the driveway row already cited. Wilsonville and West Linn joined
    2026-09-13.)"""
    from common import load_footprints

    sp = load_footprints().siteplan
    pdx = sp.driveway_for("portland")
    assert pdx is not None and pdx.alley_access_required is True
    assert "33.266.120.C" in pdx.cite and ".C.3" in pdx.cite
    gre = sp.driveway_for("gresham")
    assert gre is not None and gre.alley_access_required is True
    assert "7.0420(B)(1)" in gre.cite
    wil = sp.driveway_for("wilsonville")
    assert wil is not None and wil.alley_access_required is True
    assert "4.113(.14)(D)(4)(c)(i)" in wil.cite
    wl = sp.driveway_for("west_linn")
    assert wl is not None and wl.alley_access_required is True
    assert "48.025(B)(3)(a)" in wl.cite
    assert {j for j, dw in sp.driveway.items() if dw.alley_access_required} == {
        "portland", "gresham", "wilsonville", "west_linn"}
    assert sp.driveway_for("milwaukie").alley_access_required is not True
    assert "townhome_rear_court_alley" in sp.layout_methods


def test_a_portland_lot_with_an_alley_behind_it_is_reached_from_the_alley():
    """The same pod across the same front and the same court behind it, and
    no lane from the street at all: on a mid-block lot the court stands on
    the alley strip and the only pavement between it and the alley is the
    setback. Nothing drawn touches the front except the building."""
    s6s = _sp_setup_cities()
    env, fe, ae, area = _alley_lot(100.0, 150.0, "rear")
    r = _run_pdx(s6s, env, fe, ae, area)
    assert r["site_plan_ok"] is True
    assert r["layout_method"] == "townhome_rear_court_alley"
    assert r["layout_fail"] == ""
    g = r["geoms"]
    assert "driveway" not in g                      # nothing to pave
    assert r["driveway_len_ft"] == pytest.approx(REAR_S)   # the strip only
    # the court reaches the back of the envelope, where the alley is
    assert g["parking_court"].bounds[3] >= (150.0 - REAR_S) - 1.0
    assert g["parking_court"].bounds[1] >= g["building"].bounds[3] - 0.6
    # and the street-fed reading of the same lot is a different drawing
    r0 = _run_pdx(s6s, env, fe, [], area)
    assert r0["layout_method"] == "townhome_rear_court"
    assert r0["geoms"]["driveway"].bounds[1] <= FRONT_S + 1.0
    assert r0["stalls_provided"] == r["stalls_provided"]


def test_a_lot_too_narrow_for_a_side_lane_lays_out_off_its_alley():
    """The direction the rule cuts most often. 48 ft of frontage seats the
    pod and leaves no room for a lane beside it, which is `no_side_lane` from
    the street in every city -- and on a Portland lot with an alley behind it
    there is no lane beside the pod to draw, so the plan stands."""
    s6s = _sp_setup_cities()
    env, fe, ae, area = _alley_lot(48.0, 150.0, "rear")
    r = _run_pdx(s6s, env, fe, [], area)
    assert r["site_plan_ok"] is False and r["layout_fail"] == "no_side_lane"
    r = _run_pdx(s6s, env, fe, ae, area)
    assert r["site_plan_ok"] is True
    assert r["layout_method"] == "townhome_rear_court_alley"
    assert r["stalls_provided"] >= 4


def test_an_alley_edge_changes_nothing_in_a_city_whose_row_does_not_send_it_there():
    """The flag is per city and defaults off. Happy Valley's row does not
    carry it -- the one alley sentence in its code, LDC 16.22.050.D.4.f, is
    the VTH district's garage rule and reaches no quadplex here -- so an
    alley edge on a Happy Valley lot is a rear lot line and nothing more: the
    plan is the street-fed one, refused for the same reason as without it.
    Gresham used to be the city in this test, on the claim that its code had
    no such sentence; 7.0420(B)(1) is that sentence."""
    s6s = _sp_setup_cities()
    env, fe, ae, area = _alley_lot(48.0, 150.0, "rear")
    r = _run(s6s, env, fe, area, jurisdiction="happy_valley",
             alley_edges=ae, alley_setback_ft=REAR_S)
    assert r["site_plan_ok"] is False
    assert r["layout_fail"] == "no_side_lane"
    assert r["layout_method"] == "none"
    # and the same lot in Gresham, whose row does send it there, lays out
    r = _run(s6s, env, fe, area, jurisdiction="gresham", zone="LDR-5",
             alley_edges=ae, alley_setback_ft=REAR_S)
    assert r["site_plan_ok"] is True
    assert r["layout_method"] == "townhome_rear_court_alley"


def test_a_gresham_lot_with_an_alley_parks_off_it_across_the_alley_column():
    """GDC Table 4.0131 reads rear 15 ft / with alley 8 ft on the quadplex
    row, 7.0420(G)(1) adds five feet of roof plane off either line for a 26
    ft pod, and 7.0420(B)(1) sends the driveway to the alley. A 100 x 100
    LDR-5 lot is too shallow for a court with its own aisle behind the pod
    when the alley line is charged the rear's twenty (28 ft behind the pod;
    the aisle wants 42), and holds that aisle when it is charged the alley
    column's thirteen -- with the thirteen-foot strip, not a lane from the
    street, as the pavement between court and alley. Since 2026-09-13 the
    twenty-foot reading is not refused either: Figure 9.0825A lets the alley
    width count as the aisle, so the shallow court parks its eight against
    the alley and backs out into it, on the drawing that says so by name --
    with the alley's MEASURED width, 20 ft here, counted toward the 23 ft
    one-way aisle and the three-foot difference paved on the lot behind
    the stalls, exactly as the figure's note has it. The thirteen-foot
    reading still prefers the court's own aisle at the same eight -- a plan
    that needs no alley wins the tie."""
    s6s = _sp_setup_cities()
    from common import load_rules
    from s5_envelope import build_envelope, lot_setbacks

    W, D = 100.0, 100.0
    lot = box(0.0, 0.0, W, D)
    edges = [[0, 0, W, 0, "F"], [W, 0, W, D, "S"], [W, D, 0, D, "A"], [0, D, 0, 0, "S"]]
    fe, ae = [[0.0, 0.0, W, 0.0]], [[0.0, D, W, D]]
    zr = load_rules().jurisdictions["gresham"].rule_for("LDR-5")
    sb = lot_setbacks(zr, W * D, "A")
    assert sb["R"] == pytest.approx(20.0) and sb["A"] == pytest.approx(13.0)

    def plan(alley_setback):
        env = build_envelope(lot, edges, {**sb, "A": alley_setback}, "A")
        return env, _run(s6s, env, fe, W * D, jurisdiction="gresham", zone="LDR-5",
                         front_setback_ft=sb["F"],
                         alley_edges=ae, alley_setback_ft=alley_setback,
                         alley_width_ft=20.0)

    env_r, r_rear = plan(sb["R"])          # the alley charged as a plain rear
    assert r_rear["site_plan_ok"] is True
    assert r_rear["layout_method"] == "townhome_rear_court_alley_aisle"
    assert r_rear["stalls_provided"] == 8
    # Eight stalls, and the 3 ft of the 23 ft aisle the 20 ft alley does not
    # cover, paved along the row on the lot.
    assert r_rear["parking_area_sqft"] == pytest.approx(8 * 8.5 * 18.5 + 3.0 * 8 * 8.5)
    env_a, r = plan(sb["A"])               # the alley column, roof plane included
    assert env_a.bounds[3] == pytest.approx(D - 13.0)
    assert env_a.area > env_r.area
    assert r["site_plan_ok"] is True and r["layout_method"] == "townhome_rear_court_alley"
    assert r["stalls_provided"] == 8
    assert "driveway" not in r["geoms"]
    assert r["driveway_len_ft"] == pytest.approx(13.0)      # the strip, nothing else
    court = r["geoms"]["parking_court"]
    assert court.bounds[3] == pytest.approx(D - 13.0, abs=0.6)
    assert lot.buffer(0.01).contains(court)


def test_an_alley_the_court_cannot_reach_is_refused_not_handed_the_street():
    """The other direction, and the one that makes this a rule rather than a
    relief. An overlay carved 45 ft deep along the back of the lot leaves the
    court nowhere near the alley; from the street this lot lays out, and
    Portland does not let it, so it is refused with its own name."""
    s6s = _sp_setup_cities()
    env, fe, ae, area = _alley_lot(100.0, 150.0, "rear")
    env = env.difference(box(0.0, 150.0 - 45.0, 100.0, 150.0))
    r0 = _run_pdx(s6s, env, fe, [], area)
    assert r0["site_plan_ok"] is True                 # the street would serve it
    r = _run_pdx(s6s, env, fe, ae, area)
    assert r["site_plan_ok"] is False
    assert r["layout_method"] == "none"
    assert r["layout_fail"] == "no_alley_lane"


def test_an_unreachable_alley_does_not_speak_before_the_court_has():
    """The ladder is a ladder. A lot too shallow for a court behind the pod
    fails `court_too_shallow` whether or not its alley can be reached; the
    alley's refusal is the fourth rung and must not be reported from the
    first. (The first run on 137 said `no_alley_lane` of 13 lots whose court
    never fit, because the empty mouth set returned early.)"""
    s6s = _sp_setup_cities()
    env, fe, ae, area = _alley_lot(100.0, 70.0, "rear")
    r0 = _run_pdx(s6s, env, fe, [], area)
    assert r0["layout_fail"] == "court_too_shallow"   # the street says so
    # The same lot with its back 30 ft carved away: no cell of the envelope
    # stands on the alley strip, and it still must not be the alley that
    # answers.
    env2 = env.difference(box(0.0, 70.0 - 30.0, 100.0, 70.0))
    r = _run_pdx(s6s, env2, fe, ae, area)
    assert r["site_plan_ok"] is False
    assert r["layout_fail"] in ("no_building", "no_court", "court_too_shallow")
    assert r["layout_fail"] != "no_alley_lane"


def test_a_rear_line_six_degrees_off_the_front_is_still_reached():
    """Real alleys are not drawn parallel to the street. Three R10 lots on the
    first run (11E26AB03500 and its neighbours, 90 x 170, alley across the
    whole back, laid out from the street with eight stalls) were refused from
    the alley because their rear line runs six degrees off the front: in the
    grid the setback strip becomes a staircase one cell wide per row, and a
    test that asked for half a lane's width of strip cells IN ONE ROW could
    not find it. The lane is judged column by column now."""
    import math

    s6s = _sp_setup_cities()
    W, D, slope = 100.0, 150.0, 0.105          # rear rises 10.5 ft across 100
    fe = [[0.0, 0.0, W, 0.0]]
    ae = [[0.0, D, W, D + slope * W]]
    # The envelope: sides and front as ever, the rear a line parallel to the
    # alley and REAR_S off it (a vertical drop of REAR_S / cos(theta)).
    drop = REAR_S / math.cos(math.atan(slope))
    under = shapely.Polygon([(-10.0, D + slope * -10.0 - drop),
                             (W + 10.0, D + slope * (W + 10.0) - drop),
                             (W + 10.0, -10.0), (-10.0, -10.0)])
    env = box(SIDE_S, FRONT_S, W - SIDE_S, D + 50.0).intersection(under)
    area = W * (D + slope * W / 2.0)
    r = _run_pdx(s6s, env, fe, ae, area)
    assert r["site_plan_ok"] is True, r["layout_fail"]
    assert r["layout_method"] == "townhome_rear_court_alley"
    assert r["stalls_provided"] >= 4
    # ...and a rear line the court cannot reach is still refused: the same
    # lot with an overlay carved 45 ft deep along the alley.
    env2 = env.difference(box(0.0, D - 45.0, W, D + 50.0))
    r2 = _run_pdx(s6s, env2, fe, ae, area)
    assert r2["layout_fail"] == "no_alley_lane"


def test_an_alley_that_turns_the_corner_is_reached_at_the_bend():
    """An alley that curves reaches the lot as a chain of short lines, and s5
    cuts the envelope with a square-capped strip along each one. Where the
    lot's boundary is concave -- the alley bends INTO the lot, as it does
    where it rounds the corner of a block -- the caps at every bend leave
    the envelope's corner farther from the alley than the setback, up to
    setback * sqrt(2), so a mouth test that measured the plain distance to
    the alley found a gap at every bend and no lane could cross the arc
    whole. Two Portland lots with a plan from the street (1S1E17CC -12400
    among them) were refused from the alley for it on 2026-09-12. The
    mouths are drawn with s5's own construction now, so the lane finds the
    strip at the bend as well as beside it."""
    import math

    import numpy as np
    from s5_envelope import build_envelope
    from s6_fit import _cell_grid

    s6s = _sp_setup_cities()
    W, D = 100.0, 150.0
    # The alley bites a pocket out of the middle of the back: a circle
    # centred just above the rear line, cut into six chords, so every bend
    # is a reflex corner of the lot. The rear line either side of the pocket
    # is an ordinary rear lot line, so the pocket is the ONLY strip a lane
    # can end on, and no chord is long enough to carry a lane on its own.
    cx, cy, r = 50.0, D + 5.0, math.hypot(20.0, 5.0)
    a0, a1 = (math.degrees(math.atan2(-5.0, 20.0)) % 360,
              math.degrees(math.atan2(-5.0, -20.0)) % 360)
    arc = [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
           for a in np.linspace(a0, a1, 7)]           # (70, D) round to (30, D)
    ring = [(0.0, 0.0), (W, 0.0), (W, D)] + arc + [(0.0, D)]
    lot = shapely.Polygon(ring)
    edges = [[0.0, 0.0, W, 0.0, "F"], [W, 0.0, W, D, "S"], [W, D, *arc[0], "R"]]
    edges += [[*arc[i], *arc[i + 1], "A"] for i in range(6)]
    edges += [[*arc[-1], 0.0, D, "R"], [0.0, D, 0.0, 0.0, "S"]]
    env = build_envelope(lot, edges, {"F": FRONT_S, "S": SIDE_S, "R": REAR_S,
                                      "A": REAR_S}, "A")
    fe = [e[:4] for e in edges if e[4] == "F"]
    ae = [e[:4] for e in edges if e[4] == "A"]
    r_ = _run_pdx(s6s, env, fe, ae, lot.area)
    assert r_["site_plan_ok"] is True, r_["layout_fail"]
    assert r_["layout_method"] == "townhome_rear_court_alley"
    # And the construction itself: under the pocket, every cell of the
    # envelope that touches the boundary is on the alley strip, the corner
    # cells at the five bends included. Those are the ones a round reach
    # misses -- at this bend they stand about 20 ft off the alley against a
    # reach of 16.5 -- and the ones a lane has to cross.
    res = s6s._CFG["res"]
    ok = _cell_grid(env, res)
    minx, miny = env.bounds[:2]
    mouths = s6s._alley_mouths(ok, ae, minx, miny, res, REAR_S + 2.0 * res + 0.5)
    inner = np.zeros_like(ok)
    inner[1:-1, 1:-1] = (ok[1:-1, 1:-1] & ok[:-2, 1:-1] & ok[2:, 1:-1]
                         & ok[1:-1, :-2] & ok[1:-1, 2:])
    rows, cols = np.nonzero(ok & ~inner)
    xs, ys = minx + (cols + 0.5) * res, miny + (rows + 0.5) * res
    under = (xs >= 34.0) & (xs <= 66.0) & (ys >= D - 40.0)
    assert under.sum() >= 30
    missed = [(round(x, 1), round(y, 1)) for x, y, rr, cc in
              zip(xs[under], ys[under], rows[under], cols[under]) if not mouths[rr, cc]]
    assert not missed, missed[:8]


def test_a_tier_c_lot_is_told_the_setback_its_envelope_was_cut_to():
    """s6s asks s5 (`lot_setbacks`) how far the envelope stands off the
    alley rather than working it out again, so the two cannot disagree. On a
    tier A/B lot that is the alley setback -- zero in Portland's R5, the
    alley column plus the roof plane in Gresham's LDR-5, the rear in a Gresham
    zone whose table prints no alley column. On a tier C lot it is not: s5
    insets an irregular lot uniformly by its LARGEST setback, so the strip
    along its alley is the front yard's width. Seven of the thirteen Portland
    lots refused from the alley on 2026-09-12 were tier C lots told to look
    five feet for a strip that was ten."""
    import s6s_siteplan
    from common import load_rules
    from s5_envelope import lot_setbacks

    rules = load_rules()
    zr = rules.jurisdictions["portland"].rule_for("R5")
    rear = float(zr.effective_setback_rear_ft(lot_area_sqft=5000.0))
    front = float(zr.effective_setback_front_ft(5000.0))
    side = float(zr.effective_setback_side_ft(lot_area_sqft=5000.0))
    assert front > rear > 0, (front, rear)  # the premise: R5 fronts deeper than it backs
    for tier in ("A", "B"):
        assert s6s_siteplan._alley_setback_for(rules, "portland", "R5", 5000.0, tier) == 0.0
        assert lot_setbacks(zr, 5000.0, tier)["A"] == 0.0
    assert s6s_siteplan._alley_setback_for(
        rules, "portland", "R5", 5000.0, "C") == max(front, rear, side)
    # Gresham LDR-5: Table 4.0131's alley column (8) plus the roof plane that
    # 7.0420(G)(1) hangs off the rear setback line, wherever that line is.
    gz = rules.jurisdictions["gresham"].rule_for("LDR-5")
    g_rear = float(gz.effective_setback_rear_ft(lot_area_sqft=5000.0))
    plane = g_rear - float(gz.setback_rear_ft)
    assert plane > 0                                # the roof plane adds to the printed 15
    g_alley = float(gz.setback_alley_ft) + plane
    assert g_alley < g_rear
    assert s6s_siteplan._alley_setback_for(rules, "gresham", "LDR-5", 5000.0, "A") == g_alley
    assert lot_setbacks(gz, 5000.0, "A")["A"] == g_alley
    # Gresham CMF: no alley column on the quadplex row, so the rear, plane and all.
    cz = rules.jurisdictions["gresham"].rule_for("CMF")
    c_rear = float(cz.effective_setback_rear_ft(lot_area_sqft=12000.0))
    assert cz.setback_alley_ft is None
    assert s6s_siteplan._alley_setback_for(rules, "gresham", "CMF", 12000.0, "A") == c_rear


def test_with_no_setback_from_the_alley_the_court_stands_on_the_alley_line():
    """PCC 33.110.220.D.9: no rear setback from a lot line abutting an alley.
    A 100 x 85 Portland R5 lot is too shallow for a court behind the pod
    when the envelope stops the rear setback short of the alley, and holds
    eight stalls when it runs to the alley line -- the court stands on the
    line, the lane is nothing, and nothing drawn leaves the lot. Five feet is
    a car's length short on 6,700 of Portland's 11,519 alley lots. (Since the
    2026-09-13 ruling the five-foot reading parks its eight against the alley
    instead of failing -- a 14 ft alley, the typical one, with six feet of
    back-out room paved on the lot; the zero-foot reading keeps the court's
    own aisle at the same eight, because that plan needs no alley.)"""
    s6s = _sp_setup_cities()
    from common import load_rules
    from s5_envelope import build_envelope, lot_setbacks

    W, D = 100.0, 85.0
    lot = box(0.0, 0.0, W, D)
    edges = [[0, 0, W, 0, "F"], [W, 0, W, D, "S"], [W, D, 0, D, "A"], [0, D, 0, 0, "S"]]
    fe, ae = [[0.0, 0.0, W, 0.0]], [[0.0, D, W, D]]
    zr = load_rules().jurisdictions["portland"].rule_for("R5")
    sb = lot_setbacks(zr, W * D, "A")
    assert sb["A"] == 0.0 and sb["R"] > 0

    def plan(alley_setback):
        env = build_envelope(lot, edges, {**sb, "A": alley_setback}, "A")
        return env, _run(s6s, env, fe, W * D, jurisdiction="portland", zone="R5",
                         parking_setback_ft=10.0, front_setback_ft=sb["F"],
                         alley_edges=ae, alley_setback_ft=alley_setback,
                         alley_width_ft=14.0)

    env_r, r_rear = plan(sb["R"])         # yesterday: the alley charged as a rear
    assert r_rear["layout_method"] == "townhome_rear_court_alley_aisle"
    assert r_rear["stalls_provided"] == 8
    assert r_rear["parking_area_sqft"] == pytest.approx(8 * 9.0 * 18.0 + 6.0 * 8 * 9.0)
    env_0, r = plan(0.0)                  # today: the code's own zero
    assert env_0.bounds[3] == pytest.approx(D)      # the envelope runs to the alley line
    assert env_0.area > env_r.area
    assert r["site_plan_ok"] is True and r["layout_method"] == "townhome_rear_court_alley"
    assert r["stalls_provided"] == 8
    assert r["driveway_len_ft"] == pytest.approx(0.0)
    court = r["geoms"]["parking_court"]
    assert court.bounds[3] == pytest.approx(D, abs=0.6)   # on the alley line
    assert lot.buffer(0.01).contains(court)


def test_a_side_alley_is_reached_out_of_the_courts_side():
    """A lot that fronts the cross street has its alley down one side. The
    court behind the pod runs to that side of the envelope and stands on the
    alley strip there; which side does not matter."""
    s6s = _sp_setup_cities()
    for where in ("right", "left"):
        env, fe, ae, area = _alley_lot(60.0, 150.0, where)
        r = _run_pdx(s6s, env, fe, ae, area)
        assert r["site_plan_ok"] is True, where
        assert r["layout_method"] == "townhome_rear_court_alley", where
        assert "driveway" not in r["geoms"], where
        court = r["geoms"]["parking_court"].bounds
        if where == "right":
            assert court[2] >= (60.0 - REAR_S) - 1.0
        else:
            assert court[0] <= REAR_S + 1.0


def test_a_lane_runs_from_the_court_to_the_alley_where_the_court_stops_short():
    """A notch carved out of the back-left corner keeps the largest court
    20 ft short of the alley. The lane is drawn up the free side of the notch
    from the court's back edge to the alley strip, and its length -- plus the
    setback it then crosses -- is the driveway the lot reports."""
    s6s = _sp_setup_cities()
    env, fe, ae, area = _alley_lot(100.0, 150.0, "rear")
    env = env.difference(box(0.0, 115.0, 60.0, 150.0))
    r = _run_pdx(s6s, env, fe, ae, area)
    assert r["site_plan_ok"] is True
    assert r["layout_method"] == "townhome_rear_court_alley"
    g = r["geoms"]
    assert r["driveway_len_ft"] == pytest.approx(20.0 + REAR_S, abs=1.0)
    d = g["driveway"].bounds
    assert d[0] >= 60.0 - 1.0                          # up the free side
    assert d[1] >= g["parking_court"].bounds[3] - 0.6  # from the court's back
    assert d[3] >= (150.0 - REAR_S) - 1.0              # to the alley strip
    assert g["driveway"].intersection(g["building"]).area < 1.0
    assert g["driveway"].bounds[1] > FRONT_S + 1.0     # not from the street


def test_the_alley_fed_plan_is_rotation_invariant():
    s6s = _sp_setup_cities()
    env, fe, ae, area = _alley_lot(100.0, 150.0, "rear")
    r = _run_pdx(s6s, env, fe, ae, area)
    theta = 37.0

    def rot(e):
        p1 = affinity.rotate(shapely.geometry.Point(e[0], e[1]), theta, origin=(0.0, 0.0))
        p2 = affinity.rotate(shapely.geometry.Point(e[2], e[3]), theta, origin=(0.0, 0.0))
        return [p1.x, p1.y, p2.x, p2.y]

    env_r = affinity.rotate(env, theta, origin=(0.0, 0.0))
    r_rot = _run_pdx(s6s, env_r, [rot(fe[0])], [rot(ae[0])], area, bearing=theta)
    assert r_rot["layout_method"] == r["layout_method"] == "townhome_rear_court_alley"
    assert r_rot["stalls_provided"] == r["stalls_provided"]
    assert r_rot["driveway_len_ft"] == pytest.approx(r["driveway_len_ft"], abs=0.6)


# ---------------------------------------------------------------------------
# the alley as the aisle (Steph's ruling, 2026-09-13)
# ---------------------------------------------------------------------------


def test_footprints_yaml_lets_two_cities_use_the_alley_as_the_aisle():
    """`alley_is_aisle` on exactly the two rows that send the driveway to the
    alley, and never without that flag: a city that does not park off its
    alley has no alley to back into. Gresham's row cites the sentence
    (Figure 9.0825A's note); Portland's is Steph's ruling of 2026-09-13 and
    its comment says so."""
    from common import load_footprints

    sp = load_footprints().siteplan
    on = {j for j, dw in sp.driveway.items() if dw.alley_is_aisle}
    assert on == {"portland", "gresham"}
    for j in on:
        assert sp.driveway_for(j).alley_access_required is True, j
    assert "9.0825A" in sp.driveway_for("gresham").cite
    assert "townhome_rear_court_alley_aisle" in sp.layout_methods
    # The back-out room the alley's measured width is held against: Portland
    # states its twenty (33.266.130.F.1.b(2)); Gresham's row leaves it empty
    # and the one-way aisle stands in, as Figure 9.0825A's note says.
    assert sp.driveway_for("portland").alley_backout_ft == 20
    assert sp.driveway_for("gresham").alley_backout_ft is None


def test_a_typical_portland_alley_lot_parks_against_the_alley_and_backs_into_it():
    """The lot the ruling was made for. 50 x 100, R5, alley across the back:
    40 ft of envelope wide, the pod turned to fit it (36 wide, 56 deep), and
    29 ft left behind the pod -- 13 short of a stall and its aisle, which is
    why 8,228 of Portland's 11,519 alley lots were `court_too_shallow`. With
    the alley as the aisle and a 20 ft alley behind the lot the court needs
    18, and four stalls stand against the alley line and back straight out
    into it: the minimum tier, no lane, no aisle on the lot, and the plan
    named for the drawing it stands on. The width is measured, not trusted:
    `test_the_alleys_width_is_paid_for_on_the_lot` is the same lot on the
    alleys Portland actually has."""
    s6s = _sp_setup_cities()
    from common import load_rules
    from s5_envelope import build_envelope, lot_setbacks

    W, D = 50.0, 100.0
    lot = box(0.0, 0.0, W, D)
    edges = [[0, 0, W, 0, "F"], [W, 0, W, D, "S"], [W, D, 0, D, "A"], [0, D, 0, 0, "S"]]
    fe, ae = [[0.0, 0.0, W, 0.0]], [[0.0, D, W, D]]
    sb = lot_setbacks(load_rules().jurisdictions["portland"].rule_for("R5"), W * D, "A")
    assert sb["A"] == 0.0
    env = build_envelope(lot, edges, sb, "A")
    assert env.bounds == pytest.approx((5.0, 10.0, 45.0, 100.0))

    def plan(alley_edges, width=20.0):
        return _run(s6s, env, fe, W * D, jurisdiction="portland", zone="R5",
                    parking_setback_ft=10.0, front_setback_ft=sb["F"],
                    alley_edges=alley_edges, alley_setback_ft=0.0,
                    alley_width_ft=width)

    r0 = plan([])                                   # from the street: no aisle fits
    assert r0["site_plan_ok"] is False and r0["layout_fail"] == "court_too_shallow"
    r = plan(ae)
    assert r["site_plan_ok"] is True and r["layout_fail"] == ""
    assert r["layout_method"] == "townhome_rear_court_alley_aisle"
    assert r["stalls_provided"] == 4
    assert r["parking_area_sqft"] == pytest.approx(4 * 9.0 * 18.0)   # stalls, no aisle
    g = r["geoms"]
    assert "driveway" not in g
    assert r["driveway_len_ft"] == pytest.approx(0.0)  # the setback is zero
    stalls = [g[k] for k in sorted(g) if k.startswith("stall_")]
    assert len(stalls) == 4
    for st in stalls:
        x0, y0, x1, y1 = st.bounds
        assert y1 == pytest.approx(D, abs=0.6)          # against the alley line
        assert y1 - y0 == pytest.approx(18.0, abs=0.6)  # a stall deep into the lot
        assert x1 - x0 == pytest.approx(9.0, abs=0.6)
        assert lot.buffer(0.01).contains(st)            # on private property
    assert g["parking_court"].bounds[1] >= g["building"].bounds[3] - 0.6
    # The ruling is the city's row and nothing else: with the flag off, the
    # same lot is what it was on 2026-09-12.
    s6s._CFG["cells"]["portland"]["alley_aisle"] = False
    try:
        r_off = plan(ae)
    finally:
        s6s._CFG["cells"]["portland"]["alley_aisle"] = True
    assert r_off["site_plan_ok"] is False and r_off["layout_fail"] == "court_too_shallow"
    # and the drawing turns with the lot
    theta = 37.0

    def rot(e):
        p1 = affinity.rotate(shapely.geometry.Point(e[0], e[1]), theta, origin=(0.0, 0.0))
        p2 = affinity.rotate(shapely.geometry.Point(e[2], e[3]), theta, origin=(0.0, 0.0))
        return [p1.x, p1.y, p2.x, p2.y]

    r_rot = _run(s6s, affinity.rotate(env, theta, origin=(0.0, 0.0)), [rot(fe[0])], W * D,
                 bearing=theta, jurisdiction="portland", zone="R5",
                 parking_setback_ft=10.0, front_setback_ft=sb["F"],
                 alley_edges=[rot(ae[0])], alley_setback_ft=0.0, alley_width_ft=20.0)
    assert r_rot["layout_method"] == "townhome_rear_court_alley_aisle"
    assert r_rot["stalls_provided"] == 4


def test_the_alleys_width_is_paid_for_on_the_lot():
    """33.266.130.F.1.b(2): "there must be a maneuvering area of at least
    20 feet between the end of each parking space and the opposite side of
    the alley. If the alley is less than 20 feet wide, some of this
    maneuvering area will be on-site." The same 50 x 100 R5 lot, 29 ft
    behind the pod, on the alleys Portland actually has (s4 measures them
    across the taxlot fabric; the typical one is 14 ft):

    - 14 ft: the stalls stand six feet in from the alley line, the six feet
      are pavement counted in the parking area, and the court needs 24.
    - 10 ft: ten feet in, the court needs 28 of its 29. Still four cars.
    - 8 ft: the court would need 30. `court_too_shallow` -- an alley two
      feet narrower is a lot one foot too shallow.
    - no width on record: laid out as if the alley were nothing, so the
      court would need 38. Refused, the strict way; it used to pass."""
    s6s = _sp_setup_cities()
    from common import load_rules
    from s5_envelope import build_envelope, lot_setbacks

    W, D = 50.0, 100.0
    lot = box(0.0, 0.0, W, D)
    edges = [[0, 0, W, 0, "F"], [W, 0, W, D, "S"], [W, D, 0, D, "A"], [0, D, 0, 0, "S"]]
    fe, ae = [[0.0, 0.0, W, 0.0]], [[0.0, D, W, D]]
    sb = lot_setbacks(load_rules().jurisdictions["portland"].rule_for("R5"), W * D, "A")
    env = build_envelope(lot, edges, sb, "A")

    def plan(width):
        return _run(s6s, env, fe, W * D, jurisdiction="portland", zone="R5",
                    parking_setback_ft=10.0, front_setback_ft=sb["F"],
                    alley_edges=ae, alley_setback_ft=0.0, alley_width_ft=width)

    for width, on_site in ((14.0, 6.0), (10.0, 10.0)):
        r = plan(width)
        assert r["site_plan_ok"] is True, width
        assert r["layout_method"] == "townhome_rear_court_alley_aisle"
        assert r["stalls_provided"] == 4
        assert r["parking_area_sqft"] == pytest.approx(4 * 9.0 * 18.0 + on_site * 4 * 9.0)
        stalls = [r["geoms"][k] for k in sorted(r["geoms"]) if k.startswith("stall_")]
        assert len(stalls) == 4
        for st in stalls:
            x0, y0, x1, y1 = st.bounds
            assert y1 == pytest.approx(D - on_site, abs=0.6), width   # the room, on the lot
            assert y1 - y0 == pytest.approx(18.0, abs=0.6)
            assert lot.buffer(0.01).contains(st)
    for width in (8.0, None):
        r = plan(width)
        assert r["site_plan_ok"] is False, width
        assert r["layout_fail"] == "court_too_shallow", width
        assert r["layout_method"] == "none", width


def test_a_court_deep_enough_for_its_own_aisle_keeps_it():
    """The alley drawing is taken only where it buys a stall. A 100 x 150 lot
    has 95 ft behind the pod, two rows and an aisle, eight stalls off its
    own pavement; one row against the alley would also be eight, and the
    court's own aisle wins the tie because it trusts no alley width. So the
    count of `townhome_rear_court_alley_aisle` plans is the count that need
    the alley, not the count that could use it."""
    s6s = _sp_setup_cities()
    env, fe, ae, area = _alley_lot(100.0, 150.0, "rear")
    assert s6s._CFG["cells"]["portland"]["alley_aisle"] is True
    r = _run_pdx(s6s, env, fe, ae, area)
    assert r["layout_method"] == "townhome_rear_court_alley"
    assert r["stalls_provided"] == 8
    assert r["parking_area_sqft"] > 8 * 9.0 * 18.0     # the aisle is on the lot


def test_a_side_alley_seats_the_row_along_the_courts_side():
    """A lot that fronts the cross street backs into the alley sideways: the
    stalls stand along the court's alley-side edge, turned so a car's length
    points into the lot and its width runs along the alley. 80 x 105 leaves
    39 ft behind the pod -- no aisle fits, and four cars fit end to end along
    the 39 ft of alley edge. Either side."""
    s6s = _sp_setup_cities()
    for where in ("right", "left"):
        env, fe, ae, area = _alley_lot(80.0, 105.0, where)
        r0 = _run_pdx(s6s, env, fe, [], area)
        assert r0["layout_fail"] == "court_too_shallow", where
        r = _run_pdx(s6s, env, fe, ae, area)
        assert r["site_plan_ok"] is True, where
        assert r["layout_method"] == "townhome_rear_court_alley_aisle", where
        assert r["stalls_provided"] == 4, where
        assert "driveway" not in r["geoms"], where
        assert r["driveway_len_ft"] == pytest.approx(REAR_S)     # the strip only
        stalls = [r["geoms"][k] for k in sorted(r["geoms"]) if k.startswith("stall_")]
        assert len(stalls) == 4
        for st in stalls:
            x0, y0, x1, y1 = st.bounds
            assert x1 - x0 == pytest.approx(18.0, abs=0.6), where   # a car's length inward
            assert y1 - y0 == pytest.approx(9.0, abs=0.6), where
            if where == "right":
                assert x1 == pytest.approx(80.0 - REAR_S, abs=0.6)   # on the strip's edge
            else:
                assert x0 == pytest.approx(REAR_S, abs=0.6)


def test_the_alley_as_the_aisle_needs_the_court_on_the_alley():
    """The ruling adds no reach. A court that cannot touch the alley strip
    has no alley to back into, so the 45 ft overlay that refused the lane
    still refuses it, by the lane's name and never by the new drawing's;
    and a lot whose court never fit is still `court_too_shallow`."""
    s6s = _sp_setup_cities()
    env, fe, ae, area = _alley_lot(100.0, 150.0, "rear")
    env = env.difference(box(0.0, 150.0 - 45.0, 100.0, 150.0))
    r = _run_pdx(s6s, env, fe, ae, area)
    assert r["site_plan_ok"] is False
    assert r["layout_fail"] == "no_alley_lane"
    assert r["layout_method"] == "none"
    env, fe, ae, area = _alley_lot(100.0, 70.0, "rear")     # 15 ft behind the pod
    r = _run_pdx(s6s, env, fe, ae, area)
    assert r["layout_fail"] == "court_too_shallow"


# ---------------------------------------------------------------------------
# which street is the front, and where the lane comes from (FOLLOWUPS 5)
# ---------------------------------------------------------------------------


def test_candidate_fronts_follow_the_citys_definition():
    """The streets a corner lot may face: the shorter one where the code
    fixes the front there, either where it leaves the choice, the longer
    (s4's first) where nobody has read the rule; a lot on one street is one
    entry whatever the word; a curved corner segment near neither bearing
    belongs to no street."""
    s6s = _sp_setup()
    fe = [[0.0, 0.0, 60.0, 0.0], [60.0, 0.0, 60.0, 150.0]]
    short = fe[0]
    long_ = fe[1]
    got = s6s._candidate_fronts([90.0, 0.0], fe, "shortest")
    assert [(b, f, se) for b, f, se in got] == [(0.0, [short], [long_])]
    for word in ("owner", "entrance", "both"):
        got = s6s._candidate_fronts([90.0, 0.0], fe, word)
        assert [b for b, _, _ in got] == [90.0, 0.0], word
        assert got[0][1] == [long_] and got[0][2] == [short], word
        assert got[1][1] == [short] and got[1][2] == [long_], word
    got = s6s._candidate_fronts([90.0, 0.0], fe, None)
    assert [(b, f, se) for b, f, se in got] == [(90.0, [long_], [short])]
    # equal streets under `shortest`: the applicant chooses, both are tried
    sq = [[0.0, 0.0, 80.0, 0.0], [80.0, 0.0, 80.0, 80.0]]
    assert [b for b, _, _ in s6s._candidate_fronts([0.0, 90.0], sq, "shortest")] == [0.0, 90.0]
    # one street: one entry with every edge, whatever the word
    one = [[0.0, 0.0, 60.0, 0.0]]
    assert s6s._candidate_fronts([0.0], one, "shortest") == [(0.0, one, [])]
    assert s6s._candidate_fronts([0.0], one, "owner") == [(0.0, one, [])]
    # a curve at the corner, 45 degrees from both streets, is nobody's
    curve = [55.0, 0.0, 60.0, 5.0]
    got = s6s._candidate_fronts([90.0, 0.0], [fe[0], curve, fe[1]], "owner")
    for _, f, se in got:
        assert curve not in f and curve not in se


def test_a_shortest_city_faces_the_shorter_street_where_it_used_to_face_the_longer():
    """Portland 33.910: the front lot line is the shorter street lot line.
    A 60 x 150 corner lot came to the drawing with the 150 ft street first
    (s4 orders bearings by length) and was laid out facing it; the rule
    turns the pod to the 60 ft street, and only that one is tried."""
    s6s = _sp_setup_cities()
    env, fe, bearings, area = _corner_lot(60.0, 150.0)
    r = _run(s6s, env, fe, area, bearings=bearings, jurisdiction="portland",
             zone="R5", parking_setback_ft=10.0)
    assert r["fronts_tried"] == 1
    assert r["front_bearing_deg"] == 0.0
    assert r["site_plan_ok"] is True
    b = r["geoms"]["building"].bounds
    assert b[1] == pytest.approx(FRONT_S, abs=0.6)     # against the south front
    assert r["layout_method"] == "townhome_rear_court_side_street"
    # the same lot with the rule unread faces the longer street, as before.
    # The lot is 45 ft deep from that street, so no court stands behind the
    # pod; until 2026-09-19 it was refused there, and now it parks BESIDE
    # the pod, a court fronting the long street for sixty feet (the plan the
    # rule turns away from -- the same ground, turned to the short street,
    # is the court behind the pod above)
    r0 = _run(_with_words(s6s, "portland", None, None), env, fe, area,
              bearings=bearings, jurisdiction="portland", zone="R5",
              parking_setback_ft=10.0)
    assert r0["fronts_tried"] == 1
    assert r0["front_bearing_deg"] == 90.0
    assert r0["layout_method"] == "townhome_side_court"
    _with_words(s6s, "portland", "shortest", "any")


def test_where_the_owner_picks_the_front_the_court_least_on_a_street_wins():
    """Gresham 3.0100: the owner designates the front. A 110 x 100 corner
    lot parks eight stalls facing either street, and either way the court,
    trimmed to its one row and aisle, slides off the side street's strip
    with a short lane across it (Gresham lets either street serve): the
    court's edge on a street is zero both ways, so the plan that paves
    least is kept (Steph's third test, HUMAN_TODO 21, then the tie-break)
    -- facing the 100 ft street, the pod's long side along it and the
    court behind, six feet of lane to the south strip -- and the answer is
    the same when the lot is turned 30 degrees. Until 2026-09-19 the court
    was the whole room behind the pod, its side on the side street for the
    room's depth, and the shallower room won."""
    s6s = _sp_setup()
    env, fe, bearings, area = _corner_lot(110.0, 100.0)
    assert bearings == [0.0, 90.0]
    r = _run(s6s, env, fe, area, bearings=bearings)
    assert r["fronts_tried"] == 2
    assert r["site_plan_ok"] is True and r["stalls_provided"] == 8
    assert r["front_bearing_deg"] == 90.0
    assert r["court_street_ft"] == 0.0
    assert r["layout_method"] == "townhome_rear_court_side_street"
    assert "driveway" in r["geoms"]
    assert FRONT_S < r["driveway_len_ft"] <= FRONT_S + 8.0
    court = r["geoms"]["parking_court"].bounds
    assert court[1] >= FRONT_S + 5.0                     # off the south strip
    assert court[2] < 110.0 - FRONT_S - 5.0 - 36.0       # behind the pod's long side
    assert court[3] - court[1] == pytest.approx(8 * 8.5, abs=1.0)   # one row of eight
    assert court[2] - court[0] == pytest.approx(18.0 + 24.0, abs=1.0)
    # the front left to the longest street (unread) faces the 110 ft one:
    # its court hides as well, and paves more
    r_long = _run(_with_words(s6s, "gresham", None, "any"), env, fe, area,
                  bearings=bearings)
    _with_words(s6s, "gresham", "owner", "any")
    assert (r_long["front_bearing_deg"], r_long["court_street_ft"],
            r_long["stalls_provided"]) == (0.0, 0.0, 8)
    lane_w = s6s._CFG["cells"]["gresham"]["lane"]
    def paved(x):
        return x["parking_area_sqft"] + (x["driveway_len_ft"] - FRONT_S) * lane_w
    assert paved(r) < paved(r_long)
    # the other way round, the longer street first, the same plan
    r2 = _run(s6s, env, fe, area, bearings=[90.0, 0.0])
    assert (r2["front_bearing_deg"], r2["layout_method"], r2["stalls_provided"]) == \
        (90.0, "townhome_rear_court_side_street", 8)
    theta = 30.0
    env_r = affinity.rotate(env, theta, origin=(0.0, 0.0))
    fe_r = []
    for x1, y1, x2, y2 in fe:
        p1 = affinity.rotate(shapely.geometry.Point(x1, y1), theta, origin=(0.0, 0.0))
        p2 = affinity.rotate(shapely.geometry.Point(x2, y2), theta, origin=(0.0, 0.0))
        fe_r.append([p1.x, p1.y, p2.x, p2.y])
    r_rot = _run(s6s, env_r, fe_r, area, bearings=[b + theta for b in bearings])
    assert r_rot["front_bearing_deg"] == pytest.approx(r["front_bearing_deg"] + theta)
    assert (r_rot["layout_method"], r_rot["stalls_provided"], r_rot["site_plan_ok"]) == \
        (r["layout_method"], r["stalls_provided"], r["site_plan_ok"])
    assert r_rot["court_street_ft"] == pytest.approx(r["court_street_ft"], abs=4.0)


def test_a_corner_lot_that_parks_only_facing_the_other_street_faces_it():
    """A 60 x 150 lot in a city that leaves the front to the owner. Facing
    the 150 ft street (s4's first) the court behind the pod is 15 ft deep
    and parks nothing behind it; facing the 60 ft street the narrow pod
    stands across it, the court behind is 64 ft deep and seats two rows,
    and the side street reaches it. Until 2026-09-19 the lot parked only
    facing the short street. The ground beside the pod along the long
    street is the same ground, and since the side court it parks eight
    either way -- so the ruling's third test decides, and the plan kept
    stands on the least street of the two. With the rule unread the long
    street is the only front tried, and the lot that used to be refused
    parks beside the pod."""
    s6s = _sp_setup()
    env, fe, bearings, area = _corner_lot(60.0, 150.0)
    assert bearings == [90.0, 0.0]
    r = _run(s6s, env, fe, area, bearings=bearings)
    assert r["fronts_tried"] == 2
    assert r["site_plan_ok"] is True and r["stalls_provided"] == 8
    r_long = _run(_with_words(s6s, "gresham", None, None), env, fe, area, bearings=bearings)
    r_short = _run(_with_words(s6s, "gresham", "shortest", "any"), env, fe, area,
                   bearings=bearings, lot_xy=[(0, 0), (60, 0), (60, 150), (0, 150)])
    assert (r_long["fronts_tried"], r_long["front_bearing_deg"]) == (1, 90.0)
    assert r_long["layout_method"] == "townhome_side_court" and r_long["stalls_provided"] == 8
    assert (r_short["fronts_tried"], r_short["front_bearing_deg"]) == (1, 0.0)
    assert r_short["layout_method"] == "townhome_rear_court_side_street"
    least = min((r_long, r_short), key=lambda x: round(x["court_street_ft"] / 5.0))
    assert (r["front_bearing_deg"], r["layout_method"]) == \
        (least["front_bearing_deg"], least["layout_method"])
    _with_words(s6s, "gresham", "owner", "any")


def test_the_lane_comes_from_the_street_the_city_names():
    """`corner_access_street` decides where the lane may come from on a
    corner lot: `any` lets the side street serve (and it wins, paving
    nothing but the strip); `side` takes the front street's lane away;
    unread keeps the lane from the front street as before. On a lot with
    ONE street the word changes nothing -- there is no side street to
    send the lane to."""
    s6s = _sp_setup()
    env, fe, bearings, area = _corner_lot(110.0, 100.0)
    for word, method in (("any", "townhome_rear_court_side_street"),
                         ("lowest_class", "townhome_rear_court_side_street"),
                         ("side", "townhome_rear_court_side_street"),
                         (None, "townhome_rear_court")):
        r = _run(_with_words(s6s, "gresham", "owner", word), env, fe, area, bearings=bearings)
        assert r["site_plan_ok"] is True, word
        assert r["layout_method"] == method, word
    r = _run(_with_words(s6s, "gresham", "owner", None), env, fe, area, bearings=bearings)
    d = r["geoms"]["driveway"].bounds
    assert d[1] <= FRONT_S + 1.0                          # from the south street
    assert r["driveway_len_ft"] > FRONT_S
    # one street, the word `side`: the front lane is the only lane, and stays
    env1, fe1, area1, _ = _rect_lot(100.0, 150.0)
    r1 = _run(_with_words(s6s, "gresham", "owner", "side"), env1, fe1, area1)
    assert r1["site_plan_ok"] is True
    assert r1["layout_method"] == "townhome_rear_court"
    assert r1["fronts_tried"] == 1
    _with_words(s6s, "gresham", "owner", "any")


def test_more_parking_is_not_a_goal_the_plan_that_paves_least_wins_a_tie():
    """Steph, 2026-09-19: "optimize for sufficient, but minimal parking".
    On a 105 x 140 lot both pods seat the preferred eight; the 25 ft deep
    pod puts the court eleven feet nearer the street, so its lane is eleven
    feet shorter, and it is the plan kept. Before the ruling the first
    plan with the most stalls was kept -- the 36 ft pod, first in the list."""
    s6s = _sp_setup()
    env, fe, area, _ = _rect_lot(105.0, 140.0)
    r = _run(s6s, env, fe, area)
    assert r["site_plan_ok"] is True and r["stalls_provided"] == 8
    assert r["building_name"] == "pod80x25"
    assert r["driveway_len_ft"] == pytest.approx(25.0 + 5.0 + FRONT_S, abs=0.6)
    assert r["court_street_ft"] == 0.0                    # behind the building


def test_the_plan_kept_is_chosen_by_the_ruling_in_its_order():
    """Steph's ruling of 2026-09-19 (HUMAN_TODO 21) as the sort key every
    plan is ranked on: green first; then the higher stall band; then the
    court least on a street; then the court's own aisle over the alley's
    width; then the least pavement. Never the most stalls."""
    s6s = _sp_setup()
    rank = s6s._plan_rank
    own, alley = "townhome_rear_court", "townhome_rear_court_alley_aisle"
    side = "townhome_side_court"
    assert rank(True, 1, 60.0, own, 5000.0) > rank(False, 3, 0.0, own, 1000.0)   # green
    assert rank(True, 3, 75.0, own, 5000.0) > rank(True, 1, 0.0, own, 1000.0)    # band
    assert rank(True, 3, 40.0, own, 5000.0) > rank(True, 3, 45.0, own, 1000.0)   # exposure
    assert rank(True, 3, 40.0, own, 5000.0) > rank(True, 3, 40.0, alley, 1000.0)  # own aisle
    assert rank(True, 3, 40.0, own, 3000.0) > rank(True, 3, 40.0, own, 3500.0)   # pavement
    # the rear court over the side court over the alley's width, on a tie
    assert rank(True, 3, 40.0, own, 5000.0) > rank(True, 3, 40.0, side, 1000.0)
    assert rank(True, 3, 40.0, side, 5000.0) > rank(True, 3, 40.0, alley, 1000.0)
    assert rank(True, 3, 40.0, side, 1000.0) > rank(True, 3, 40.0, "townhome_side_court_alley", 5000.0)
    # a side court that is greener, a band up, or on less street beats it
    assert rank(True, 1, 0.0, side, 5000.0) > rank(False, 3, 0.0, own, 1000.0)
    assert rank(True, 3, 40.0, side, 5000.0) > rank(True, 2, 0.0, own, 1000.0)
    assert rank(True, 3, 40.0, side, 5000.0) > rank(True, 3, 45.0, own, 1000.0)
    # under five feet of exposure is the raster's corner cells, not a preference
    assert rank(True, 3, 40.4, own, 3000.0) == rank(True, 3, 39.6, own, 3000.0)
    assert rank(True, 3, 43.5, own, 3000.0) == rank(True, 3, 44.5, own, 3000.0)


def test_the_corner_summary_survives_a_lot_with_no_street_bearing():
    """The September run crashed on its last line: `front_bearings_json` is
    "[]" on 8,964 lots s4 found no front for -- an empty list, not an empty
    string -- and the summary read `[0]` of it. The parquet was already
    written; only the line was lost. Counted, not crashed."""
    s6s = _sp_setup()
    line = s6s._corner_summary(
        bearings_json=["[90.0, 0.0]", "[]", "[45.0]", "[10.0, 100.0]", "", "[0.0]"],
        jurisdiction=["gresham", "gresham", "portland", "clackamas", "portland", "gresham"],
        fronts_tried=[2, 0, 1, 2, 0, 2],
        front_deg=[0.0, float("nan"), 45.0, 10.0, float("nan"), 180.0],
        method=["townhome_rear_court_side_street", "none", "townhome_rear_court",
                "townhome_rear_court", "none", "townhome_rear_court_rear_street"],
        cities=["clackamas", "gresham", "portland"],
        through=[False, False, False, False, False, True])
    assert line.startswith("s6s: 2 corner lots drawn to each street")
    assert "1 chose the street s4 did not list first" in line
    assert "1 plans take the lane in from the side street" in line
    assert "clackamas 1/0/0, gresham 1/1/1" in line
    # the through lot, drawn to each of its ends, is counted on its own line
    lines = s6s._through_summary(
        jurisdiction=["gresham", "gresham", "portland", "clackamas", "portland", "gresham"],
        through=[False, False, False, False, True, True],
        site_ok=[True, False, True, True, False, True],
        method=["townhome_rear_court_side_street", "none", "townhome_side_court",
                "townhome_rear_court", "none", "townhome_rear_court_rear_street"],
        lfail=["", "no_building", "", "", "no_court", ""],
        cities=["clackamas", "gresham", "portland"], banned=["portland"])
    assert lines[0].startswith("s6s: 2 through lots")
    assert "1 draw a plan, 1 of them with the lane from the far street" in lines[0]
    assert "gresham 1/1/1, portland 1/0/0" in lines[0]
    assert lines[1].startswith("s6s: 1 plans park BESIDE the building")
    assert lines[2] == ("s6s: portland refuses the rear court on its 1 through lots "
                        "(parking_front_prohibited): 0 draw a side court, 0 draw a plan "
                        "the lot is graded on, 1 draw nothing")
    # nothing drawn to two fronts: no line at all
    assert s6s._corner_summary(["[]"], ["portland"], [0], [float("nan")], ["none"],
                               ["portland"]) is None


def test_the_shorter_street_is_the_shorter_lot_line_not_the_shorter_edge_sum():
    """Portland 33.910 makes the SHORTER street lot line the front. The
    September run of 2026-09-19 read the length of each street as the sum of
    its front edges and faced 738 lots the wrong way: 1S2E11CA-01400 has
    streets at both 72 ft ends and along one 135 ft side, so the ends summed
    to 144 and the side "won"; 1S2E15BB-02800's frontage jogs, and the 30 ft
    step of the jog "won" over the 66 ft end it is part of. A lot line runs
    corner to corner: its length is the lot's extent along the bearing."""
    s6s = _sp_setup()
    cf = s6s._candidate_fronts
    # streets at both ends and along the east side; s4 lists the ends' sum first
    W, D = 72.0, 135.0
    fe = [[0.0, 0.0, W, 0.0], [0.0, D, W, D], [W, 0.0, W, D]]
    xy = [(0.0, 0.0), (W, 0.0), (W, D), (0.0, D)]
    kept = cf([0.0, 90.0], fe, "shortest", xy)
    assert [b for b, _, _ in kept] == [0.0, 0.0]                  # the 72 ft ends, each tried
    assert [len(f) for _, f, _ in kept] == [1, 1]                 # one end faces ...
    assert [len(se) for _, _, se in kept] == [2, 2]               # ... the other and the side serve
    assert [b for b, _, _ in cf([0.0, 90.0], fe, "shortest")] == [90.0]   # the sum, as before
    # a jogged frontage: 36 ft east, 30 ft north, 30 ft east along the south end
    jog = [[0.0, 0.0, 36.0, 0.0], [36.0, 0.0, 36.0, 30.0], [36.0, 30.0, 66.0, 30.0]]
    jxy = [(0.0, 0.0), (36.0, 0.0), (36.0, 30.0), (66.0, 30.0), (66.0, 132.0), (0.0, 132.0)]
    assert [b for b, _, _ in cf([0.0, 90.0], jog, "shortest", jxy)] == [0.0]
    assert [b for b, _, _ in cf([0.0, 90.0], jog, "shortest")] == [90.0]   # the 30 ft step
    # and the drawing: the three-street lot faces an end and parks behind
    # the pod; read the other way it is 72 ft deep from the side street, no
    # court stands behind the pod, and only the court beside it parks
    s6s = _with_words(s6s, "gresham", "shortest", "any")
    env = box(SIDE_S, FRONT_S, W - FRONT_S, D - FRONT_S)
    r = _run(s6s, env, fe, W * D, bearings=[0.0, 90.0], lot_xy=xy)
    assert r["fronts_tried"] == 2 and r["front_bearing_deg"] == 0.0
    assert r["site_plan_ok"] is True and r["through_lot"] is True
    assert r["layout_method"].startswith("townhome_rear_court")
    r0 = _run(s6s, env, fe, W * D, bearings=[0.0, 90.0])
    assert r0["front_bearing_deg"] == 90.0 and r0["through_lot"] is False
    assert r0["layout_method"] == "townhome_side_court"
    _with_words(s6s, "gresham", "owner", "any")


def test_a_street_that_bends_is_one_street_not_a_corner():
    """s4 clusters front edges at twenty degrees, so a crescent or a
    cul-de-sac approach comes out as two bearings 20-40 degrees apart. The
    first bound run (2026-09-19) read those as corner lots: on 1S1E07DC-04600
    the 16 ft clip at the bend was the "shorter street", the pod was turned
    to face it, and a lot that parks eight was refused for want of a lane.
    Two bearings closer than `CORNER_MIN_DEG` are one street, every front
    edge in it, whatever the city's corner word says."""
    s6s = _sp_setup()
    cf = s6s._candidate_fronts
    assert s6s.CORNER_MIN_DEG == 45.0
    # the front runs 80 ft east, then bends 25 degrees for another 40 ft
    fe = [[0.0, 0.0, 80.0, 0.0], [80.0, 0.0, 116.3, 16.9]]
    xy = [(0.0, 0.0), (80.0, 0.0), (116.3, 16.9), (116.3, 120.0), (0.0, 120.0)]
    for rule in ("shortest", "owner", "both", None):
        kept = cf([0.0, 25.0], fe, rule, xy)
        assert len(kept) == 1
        assert kept[0][0] == 0.0 and len(kept[0][1]) == 2 and kept[0][2] == []
    # at a right angle the same words see two streets
    fe2 = [[0.0, 0.0, 80.0, 0.0], [80.0, 0.0, 80.0, 40.0]]
    xy2 = [(0.0, 0.0), (80.0, 0.0), (80.0, 120.0), (0.0, 120.0)]
    assert len(cf([0.0, 90.0], fe2, "owner", xy2)) == 2
    assert len(cf([0.0, 90.0], fe2, "shortest", xy2)) == 1
    assert cf([0.0, 90.0], fe2, "shortest", xy2)[0][0] == 0.0     # 80 ft < 120 ft


# ---------------------------------------------------------------------------
# the side court, and the through lot (FOLLOWUPS 5 iii/iv)
# ---------------------------------------------------------------------------


def test_a_through_lot_in_a_ban_city_parks_beside_the_building_or_not_at_all():
    """Portland 33.266.120.C.1.a: no vehicle area between the primary
    structure and the street unless entirely behind the front and side
    street building lines -- and a through lot has two front lot lines
    (33.910), so the court behind the pod stands in the second front yard
    and is refused. What is left is the court BESIDE the pod, no farther
    back than its rear wall, the lane from the front street straight into
    its aisle: an 84 x 160 through lot parks eight that way. Seventy feet
    wide there is no room beside the pod and the lot draws nothing. The
    same 84 ft lot in Gresham, which states no ban, keeps the court behind
    the pod. Milwaukie bans too (19.505.3.D.4.a) and caps at four."""
    s6s = _sp_setup_cities()
    env, fe, bearings, area, xy = _through_lot(84.0, 160.0)
    r = _run(s6s, env, fe, area, bearings=bearings, jurisdiction="portland",
             zone="R5", parking_setback_ft=10.0, lot_xy=xy)
    assert r["through_lot"] is True and r["fronts_tried"] == 2
    assert r["site_plan_ok"] is True and r["stalls_provided"] == 8
    assert r["layout_method"] == "townhome_side_court"
    b = r["geoms"]["building"].bounds
    c = r["geoms"]["parking_court"].bounds
    # beside the pod, not behind it: the court's rows lie within the pod's
    assert c[1] >= b[1] - 0.6 and c[3] <= b[3] + 0.6
    assert c[0] >= b[2] + 5.0 - 0.6 or c[2] <= b[0] - 5.0 + 0.6
    # its stalls stand against the side lot line, one row, the aisle by the wall
    assert c[2] == pytest.approx(84.0 - SIDE_S, abs=0.6) or c[0] == pytest.approx(SIDE_S, abs=0.6)
    assert c[2] - c[0] == pytest.approx(18.0 + 24.0, abs=0.6)
    d = r["geoms"]["driveway"].bounds
    assert d[1] <= FRONT_S + 1.0 and d[3] >= c[1] - 0.6        # from the street to the court
    assert d[0] >= c[0] - 0.6 and d[2] <= c[2] + 0.6            # into the aisle
    assert r["driveway_len_ft"] == pytest.approx(FRONT_S + (c[1] - FRONT_S), abs=0.6)
    assert r["parking_area_sqft"] == pytest.approx(8 * 9.0 * 18.0 + 24.0 * (c[3] - c[1]), abs=1.0)
    assert r["court_street_ft"] >= 40.0                          # its front edge on the near street
    # too narrow beside the pod: refused, where the rear court used to be drawn
    env, fe, bearings, area, xy = _through_lot(70.0, 160.0)
    r = _run(s6s, env, fe, area, bearings=bearings, jurisdiction="portland",
             zone="R5", parking_setback_ft=10.0, lot_xy=xy)
    assert r["site_plan_ok"] is False and r["through_lot"] is True
    assert r["layout_fail"] in ("no_court", "court_too_shallow")
    # no ban in Gresham: the court behind the pod stays
    env, fe, bearings, area, xy = _through_lot(84.0, 160.0)
    r = _run(s6s, env, fe, area, bearings=bearings, jurisdiction="gresham", lot_xy=xy)
    assert r["site_plan_ok"] is True and r["through_lot"] is True
    assert r["layout_method"] in ("townhome_rear_court", "townhome_rear_court_rear_street",
                                  "townhome_side_court")
    # Milwaukie: banned, capped at four, still a side court
    r = _run(s6s, env, fe, area, bearings=bearings, jurisdiction="milwaukie", lot_xy=xy)
    assert r["site_plan_ok"] is True and r["layout_method"] == "townhome_side_court"
    assert r["stalls_provided"] == 4


def test_the_far_street_serves_a_through_lot_where_the_city_names_no_street():
    """In a city that names no street a lot must take access from, a
    through lot's court may open onto the street at its far end across
    that street's setback strip -- the side-street lane's construction on
    the far end's edges, its own name. The two-row court behind the wide
    pod on a 70 x 160 Gresham through lot stands against the pod, off the
    far strip (its edge on a street is zero), with a short lane out of its
    back across the strip: less paved than the lane down the pod's side
    from the front, so it wins; the same lot with the access word unread
    takes the lane from the front street down the side of the pod, as
    before."""
    s6s = _sp_setup()
    env, fe, bearings, area, xy = _through_lot(70.0, 160.0)
    r = _run(s6s, env, fe, area, bearings=bearings, lot_xy=xy)
    assert r["through_lot"] is True and r["fronts_tried"] == 2
    assert r["site_plan_ok"] is True and r["stalls_provided"] == 8
    assert r["layout_method"] == "townhome_rear_court_rear_street"
    assert r["court_street_ft"] == 0.0
    assert "driveway" in r["geoms"]
    assert FRONT_S < r["driveway_len_ft"] < FRONT_S + 25.0
    c = r["geoms"]["parking_court"].bounds
    assert c[3] - c[1] == pytest.approx(18.0 + 24.0 + 18.0, abs=1.0)   # two rows
    assert c[2] - c[0] == pytest.approx(4 * 8.5, abs=1.0)
    assert FRONT_S + 5.0 < c[1] and c[3] < 160.0 - FRONT_S - 5.0    # off both strips
    d = r["geoms"]["driveway"].bounds
    assert d[1] >= c[3] - 0.6 and d[3] >= 160.0 - FRONT_S - 1.6      # back to the far strip
    r0 = _run(_with_words(s6s, "gresham", "owner", None), env, fe, area,
              bearings=bearings, lot_xy=xy)
    assert r0["layout_method"] == "townhome_rear_court"
    assert r0["driveway_len_ft"] > FRONT_S
    _with_words(s6s, "gresham", "owner", "any")


def test_each_end_of_a_through_lot_is_tried_as_the_front():
    """`_through_ends` splits one street cluster's edges across the bearing
    where the widest gap between them is at least THROUGH_MIN_FT and, with
    the corners in hand, half the lot's extent across it; each end is then
    an entry with the other end among the streets that serve. A jogged
    frontage's 30 ft step is no far end; a street that bends 25 degrees
    over a long edge is no far end either."""
    s6s = _sp_setup()
    cf = s6s._candidate_fronts
    assert s6s.THROUGH_MIN_FT == 40.0
    W, D = 70.0, 160.0
    fe = [[0.0, 0.0, W, 0.0], [0.0, D, W, D]]
    xy = [(0.0, 0.0), (W, 0.0), (W, D), (0.0, D)]
    for rule in ("shortest", "owner", "both", None):
        got = cf([0.0], fe, rule, xy)
        assert [(b, f, se) for b, f, se in got] == [(0.0, [fe[0]], [fe[1]]),
                                                  (0.0, [fe[1]], [fe[0]])], rule
    assert len(cf([0.0], fe, "owner")) == 2                      # without the corners too
    # the jog: two edges 30 ft apart across the bearing are one frontage
    jog = [[0.0, 0.0, 36.0, 0.0], [36.0, 30.0, 66.0, 30.0]]
    jxy = [(0.0, 0.0), (36.0, 0.0), (36.0, 30.0), (66.0, 30.0), (66.0, 132.0), (0.0, 132.0)]
    assert len(cf([0.0], jog, "owner", jxy)) == 1
    # the bend: a 150 ft edge 25 degrees off puts its midpoint 32 ft across
    # the bearing, under half the lot's 120 ft depth
    bend = [[0.0, 0.0, 80.0, 0.0], [80.0, 0.0, 216.0, 63.4]]
    bxy = [(0.0, 0.0), (80.0, 0.0), (216.0, 63.4), (216.0, 183.4), (0.0, 120.0)]
    assert len(cf([0.0, 25.0], bend, "owner", bxy)) == 1
    # and the drawing on a lot with a street at each end and one side
    env, fe2, bearings, area = _corner_lot(70.0, 160.0)
    fe2 = fe2 + [[0.0, 160.0, 70.0, 160.0]]
    env = box(SIDE_S, FRONT_S, 70.0 - FRONT_S, 160.0 - FRONT_S)
    r = _run(s6s, env, fe2, area, bearings=[90.0, 0.0])
    assert r["through_lot"] is True and r["fronts_tried"] == 3     # two ends and the side


def test_the_side_court_rescues_a_wide_shallow_lot():
    """A 110 x 90 Gresham lot: 65 ft deep inside its setbacks, the court
    behind either pod is 24 or 35 ft, too shallow to park in, and until
    2026-09-19 the lot was refused `court_too_shallow`. The narrow pod
    stands end-on and a court beside it, one row of stalls against the
    side lot line and the aisle along the pod's wall, seats seven; the
    lane comes down from the street straight into the aisle. Turned thirty
    degrees, the same plan."""
    s6s = _sp_setup()
    env, fe, area, lot = _rect_lot(110.0, 90.0)
    r = _run(s6s, env, fe, area)
    assert r["site_plan_ok"] is True and r["layout_fail"] == ""
    assert r["layout_method"] == "townhome_side_court"
    assert r["stalls_provided"] == 7
    assert r["building_name"] == "pod56x36"
    b = r["geoms"]["building"].bounds
    c = r["geoms"]["parking_court"].bounds
    assert b[2] - b[0] == pytest.approx(36.0, abs=0.6)          # end-on
    assert c[0] >= b[2] + 5.0 - 0.6                              # beside it, off the wall
    assert c[2] - c[0] == pytest.approx(18.5 + 24.0, abs=0.6)   # one row and the aisle
    assert c[3] - c[1] == pytest.approx(7 * 8.5, abs=0.6)       # as long as its stalls
    stalls = [r["geoms"][k].bounds for k in r["geoms"] if k.startswith("stall_")]
    assert len(stalls) == 7
    assert all(sb[2] == pytest.approx(c[2], abs=0.01) for sb in stalls)   # against the outer edge
    assert all(sb[2] - sb[0] == pytest.approx(18.5, abs=0.01) for sb in stalls)
    d = r["geoms"]["driveway"].bounds
    assert d[1] <= FRONT_S + 1.0 and d[3] >= c[1] - 0.6
    assert d[0] >= c[0] - 0.6 and d[2] <= c[0] + 24.0 + 0.6     # within the aisle
    assert lot.contains(r["geoms"]["parking_court"]) and lot.contains(r["geoms"]["driveway"])
    assert r["parking_area_sqft"] == pytest.approx(7 * 8.5 * 18.5 + 24.0 * (c[3] - c[1]), abs=1.0)
    # rotation invariance
    theta = 30.0
    env_r = affinity.rotate(env, theta, origin=(0.0, 0.0))
    p1 = affinity.rotate(shapely.geometry.Point(0.0, 0.0), theta, origin=(0.0, 0.0))
    p2 = affinity.rotate(shapely.geometry.Point(110.0, 0.0), theta, origin=(0.0, 0.0))
    r_rot = _run(s6s, env_r, [[p1.x, p1.y, p2.x, p2.y]], area, bearing=theta)
    assert (r_rot["layout_method"], r_rot["stalls_provided"]) == ("townhome_side_court", 7)
    assert r_rot["parking_area_sqft"] == pytest.approx(r["parking_area_sqft"], abs=1.0)


def test_the_rear_court_keeps_a_tie_with_the_side_court():
    """A 100 x 150 Gresham lot parks eight behind the pod and eight beside
    it. Behind the pod the court touches no street; beside it the court's
    front edge stands on the front strip -- and had it not, the rear court
    is the arrangement every code here describes and keeps the tie
    (`_plan_rank`). The lot draws what it drew before the side court."""
    s6s = _sp_setup()
    env, fe, area, _ = _rect_lot(100.0, 150.0)
    r = _run(s6s, env, fe, area)
    assert r["site_plan_ok"] is True and r["stalls_provided"] == 8
    assert r["layout_method"] == "townhome_rear_court"
    assert r["court_street_ft"] == 0.0


def test_the_rear_court_is_trimmed_to_the_rows_it_parks():
    """The rear court is the rows it seats and the aisle between them, not
    the room behind the pod: on a 100 x 150 Gresham lot two rows of four,
    34 ft wide and 18 + 24 + 18 deep, against the pod's back wall and the
    gap, with the lane down the pod's side meeting one end of it -- and
    the pavement and the open space charged for that court alone, the way
    the paper lot charges it. A one-row court turns its aisle toward the
    lane, its stalls along its back. `_court_places` names the room's four
    corners once each, the near-left first."""
    s6s = _sp_setup()
    cell = s6s._CFG["cells"]["gresham"]
    sw, sd, aisle, gap, lane = (cell["stall_w"], cell["stall_d"], cell["aisle_two"],
                                cell["gap"], cell["lane"])
    env, fe, area, _ = _rect_lot(100.0, 150.0)
    r = _run(s6s, env, fe, area)
    assert r["layout_method"] == "townhome_rear_court" and r["stalls_provided"] == 8
    c = r["geoms"]["parking_court"].bounds
    b = r["geoms"]["building"].bounds
    assert c[2] - c[0] == pytest.approx(4 * sw, abs=1.0)
    assert c[3] - c[1] == pytest.approx(2 * sd + aisle, abs=1.0)
    assert c[1] == pytest.approx(b[3] + gap, abs=1.0)                # against the pod
    assert r["parking_area_sqft"] == pytest.approx(8 * sw * sd + aisle * 4 * sw, abs=40.0)
    lane_len = r["driveway_len_ft"] - FRONT_S
    assert r["open_space_sqft"] == pytest.approx(
        area - 56.0 * 36.0 - r["parking_area_sqft"] - lane_len * lane, abs=60.0)
    d = r["geoms"]["driveway"].bounds
    assert d[3] >= c[1] - 0.6                                        # reaches the court
    assert c[0] - 0.6 <= d[0] and d[2] <= c[2] + 0.6                # at one end of it
    stalls = [r["geoms"][k].bounds for k in r["geoms"] if k.startswith("stall_")]
    assert len(stalls) == 8
    assert sorted({round(s[1], 1) for s in stalls}) == pytest.approx(
        [c[1], c[3] - sd], abs=0.6)                                  # a row each side of the aisle
    # one row: 100 x 112 leaves 46 ft behind the pod, one row and its aisle;
    # the aisle is at the court's front where the lane arrives, the stalls
    # along its back
    env, fe, area, _ = _rect_lot(100.0, 112.0)
    r1 = _run(s6s, env, fe, area)
    assert r1["layout_method"] == "townhome_rear_court" and r1["stalls_provided"] == 8
    c1 = r1["geoms"]["parking_court"].bounds
    assert c1[3] - c1[1] == pytest.approx(sd + aisle, abs=1.0)
    assert c1[2] - c1[0] == pytest.approx(8 * sw, abs=1.0)
    stalls1 = [r1["geoms"][k].bounds for k in r1["geoms"] if k.startswith("stall_")]
    assert all(s[1] == pytest.approx(c1[3] - sd, abs=0.6) for s in stalls1)
    assert s6s._court_places(10, 20, 100, 80, 40, 30) == [(10, 20), (10, 70), (70, 20), (70, 70)]
    assert s6s._court_places(10, 20, 40, 30, 40, 30) == [(10, 20)]
    assert s6s._court_places(10, 20, 100, 30, 40, 30) == [(10, 20), (70, 20)]


def test_a_corner_lots_court_slides_off_the_side_street():
    """A 60 x 150 Gresham corner lot, the pod across the 60 ft street: the
    two-row court behind it is 34 ft wide in a 45 ft room, so it stands
    against the west side, off the side street's strip (its edge on a
    street is zero), and the lane runs out of the aisle between its rows
    across the strip to the side street -- Steph's third test over the
    court that stands on the strip with no lane at all. Before the court
    was trimmed (2026-09-19) this lot drew a side court along the long
    street, exposed for 62 ft, because the room's side ran 64 ft along the
    side street."""
    s6s = _sp_setup()
    cell = s6s._CFG["cells"]["gresham"]
    sd = cell["stall_d"]
    env, fe, bearings, area = _corner_lot(60.0, 150.0)
    r = _run(s6s, env, fe, area, bearings=bearings)
    assert r["site_plan_ok"] is True and r["stalls_provided"] == 8
    assert r["front_bearing_deg"] == 0.0
    assert r["layout_method"] == "townhome_rear_court_side_street"
    assert r["court_street_ft"] == 0.0
    c = r["geoms"]["parking_court"].bounds
    assert c[2] <= 60.0 - FRONT_S - 5.0                              # off the east strip
    assert c[0] == pytest.approx(SIDE_S, abs=1.0)                    # against the west side
    d = r["geoms"]["driveway"].bounds
    assert d[0] >= c[2] - 0.6 and d[2] >= 60.0 - FRONT_S - 1.6       # court's side to the strip
    assert c[1] + sd - 0.6 <= d[1] and d[3] <= c[3] - sd + 0.6       # out of the aisle band
    assert r["driveway_len_ft"] == pytest.approx(FRONT_S + (60.0 - FRONT_S - c[2]), abs=1.6)


def test_a_court_in_a_big_room_slides_to_the_mouth_mid_side():
    """A 300 x 400 Gresham lot with a 20 ft stub of side street meeting its
    east side at 250-270 ft, the access word `side` (the lane must come
    from that street): the room behind the pod is 285 x 340 and the
    trimmed court at its four corners is nowhere near the stub, so until
    2026-09-20 the lot drew a side court exposed for 62 ft along the front
    instead (the bound's five non-through losses were this: a 10-acre
    Oregon City corner lot, an alley mouth mid-side of a Portland CM3
    room). The whole room's lane says where the mouth is and the court
    slides under it: against the east side over the stub's rows, no lane
    to pave, its edge on the street the stub's reach and no more."""
    s6s = _sp_setup()
    W, D = 300.0, 400.0
    env = box(SIDE_S, FRONT_S, W - FRONT_S, D - REAR_S)
    fe = [[0.0, 0.0, W, 0.0], [W, 250.0, W, 270.0]]
    r = _run(_with_words(s6s, "gresham", None, "side"), env, fe, W * D,
             bearings=[0.0, 90.0])
    _with_words(s6s, "gresham", None, "any")
    assert r["site_plan_ok"] is True and r["stalls_provided"] == 8
    assert r["layout_method"] == "townhome_rear_court_side_street"
    c = r["geoms"]["parking_court"].bounds
    assert c[2] == pytest.approx(W - FRONT_S, abs=0.6)               # on the east strip
    assert c[1] < 260.0 < c[3]                                       # over the stub
    assert r["driveway_len_ft"] == pytest.approx(FRONT_S)            # the strip only
    assert 0.0 < r["court_street_ft"] < 45.0                         # the stub's reach
    # the whole room's lane names the placement: a lane up from the back
    # puts the court under its columns, a lane out of a side over its rows
    assert s6s._court_places(10, 20, 100, 80, 40, 30, (110, 45, 20, 4), 4) == [
        (10, 20), (10, 70), (70, 20), (70, 70), (70, 45)]
    assert s6s._court_places(10, 20, 100, 80, 40, 30, (50, 100, 4, 30), 4, (0, 8)) == [
        (10, 20), (10, 70), (70, 20), (70, 70), (46, 70), (50, 70)]


def test_a_bent_front_still_carries_the_lane_beside_the_pod():
    """A 100 x 115 Gresham lot whose front lot line steps back 15 ft east
    of x = 70: the pod fits only in the deeper pocket west of the step,
    and the lane beside it runs down the ground east of the step, where
    the envelope's edge is 15 ft behind the pod's front row. Until
    2026-09-20 the lane had to be free from the pod's front row, so that
    ground could carry none and the lot drew a side court exposed on the
    front instead (283 Portland through lots lost their side courts to the
    same test); now each column runs from its own edge on the front
    street's strip, the rear court hides at zero exposure, and the lane is
    drawn from the recessed edge, not across the street."""
    s6s = _sp_setup()
    W, D = 100.0, 115.0
    lot = shapely.Polygon([(0, 0), (70, 0), (70, 15), (W, 15), (W, D), (0, D)])
    env = shapely.Polygon([(SIDE_S, FRONT_S), (70, FRONT_S), (70, 15 + FRONT_S),
                           (W - SIDE_S, 15 + FRONT_S), (W - SIDE_S, D - REAR_S),
                           (SIDE_S, D - REAR_S)])
    fe = [[0.0, 0.0, 70.0, 0.0], [70.0, 15.0, W, 15.0]]
    r = _run(s6s, env, fe, lot.area)
    assert r["site_plan_ok"] is True and r["stalls_provided"] == 8
    assert r["layout_method"] == "townhome_rear_court"
    assert r["court_street_ft"] == 0.0
    b = r["geoms"]["building"].bounds
    assert b[1] == pytest.approx(FRONT_S, abs=0.6) and b[2] <= 70.0   # in the pocket
    d = r["geoms"]["driveway"].bounds
    assert d[0] >= b[2] - 0.6 and d[2] > 70.0                         # beside the pod, past the step
    assert d[1] == pytest.approx(15.0 + FRONT_S, abs=0.6)             # from the recessed edge
    c = r["geoms"]["parking_court"].bounds
    assert d[3] >= c[1] - 0.6                                         # to the court
    assert r["driveway_len_ft"] == pytest.approx(FRONT_S + (c[1] - d[1]), abs=0.6)


def test_the_side_court_keeps_off_the_side_street_in_a_ban_city():
    """Portland's exception allows only spaces "entirely behind the front
    and side street building lines": on a corner lot the side court may
    not stand on the side-street side of the pod. A 100 x 90 corner lot,
    the long street the front (the rule unread), the pod end-on at the
    west: the only court beside it is on the east, where the side street
    is, and Portland draws nothing; Gresham, which states no ban, draws
    it there, exposed along the side street; and with the side street on
    the WEST the same court in Portland is on the interior side and
    allowed."""
    s6s = _sp_setup_cities()
    W, D = 100.0, 90.0
    env = box(SIDE_S, FRONT_S, W - FRONT_S, D - REAR_S)
    fe = [[0.0, 0.0, W, 0.0], [W, 0.0, W, D]]
    s6s = _with_words(s6s, "portland", None, "any")
    r = _run(s6s, env, fe, W * D, bearings=[0.0, 90.0], jurisdiction="portland",
             zone="R5", parking_setback_ft=10.0)
    assert r["site_plan_ok"] is False
    assert r["layout_fail"] in ("no_court", "court_too_shallow")
    g = _run(_with_words(s6s, "gresham", None, "any"), env, fe, W * D,
             bearings=[0.0, 90.0], jurisdiction="gresham")
    assert g["site_plan_ok"] is True and g["layout_method"] == "townhome_side_court"
    assert g["court_street_ft"] > 40.0
    c = g["geoms"]["parking_court"].bounds
    assert c[2] >= W - FRONT_S - 0.6                             # on the east strip
    # mirrored: the side street on the west, the pod still at the west,
    # the court beside it on the east is now the interior side
    env_m = box(FRONT_S, FRONT_S, W - SIDE_S, D - REAR_S)
    fe_m = [[0.0, 0.0, W, 0.0], [0.0, 0.0, 0.0, D]]
    m = _run(s6s, env_m, fe_m, W * D, bearings=[0.0, 90.0], jurisdiction="portland",
             zone="R5", parking_setback_ft=10.0)
    assert m["site_plan_ok"] is True and m["layout_method"] == "townhome_side_court"
    c = m["geoms"]["parking_court"].bounds
    assert c[2] <= W - SIDE_S + 0.6 and c[0] > FRONT_S + 20.0     # nowhere near the west street
    _with_words(s6s, "portland", "shortest", "any")
    _with_words(s6s, "gresham", "owner", "any")


def test_an_alley_fed_lot_reaches_its_side_court_from_the_alley():
    """Portland sends the driveway to the alley; a through lot there with
    an alley down one side is refused the rear court like any through lot
    and reaches the court beside the pod from the alley -- the court stands
    on the alley strip, so nothing is paved for a lane."""
    s6s = _sp_setup_cities()
    W, D = 96.0, 160.0
    env = box(SIDE_S, FRONT_S, W - REAR_S, D - FRONT_S)          # alley on the east, set back as a rear line
    fe = [[0.0, 0.0, W, 0.0], [0.0, D, W, D]]
    ae = [[W, 0.0, W, D]]
    r = _run(s6s, env, fe, W * D, bearings=[0.0], jurisdiction="portland", zone="R5",
             parking_setback_ft=10.0, alley_edges=ae, alley_setback_ft=REAR_S,
             alley_width_ft=20.0, lot_xy=[(0, 0), (W, 0), (W, D), (0, D)])
    assert r["through_lot"] is True
    assert r["site_plan_ok"] is True
    assert r["layout_method"] == "townhome_side_court_alley"
    c = r["geoms"]["parking_court"].bounds
    assert c[2] >= W - REAR_S - 0.6                              # against the alley strip
    assert "driveway" not in r["geoms"]



def test_a_corner_lot_cut_to_the_deeper_street_setback_still_finds_its_front_lane():
    """A 100 x 150 Gresham corner lot cut 15 ft from BOTH streets (s5 cuts
    every street edge of a corner lot to the larger of the front and
    street-side setbacks) in a city that names the front street the only
    one the lane may come from. The lane starts on the front street's
    strip, and until 2026-09-20 that strip was sought at the FRONT
    setback's reach -- 10 ft, where the envelope's edge stands 15 ft off
    the street -- so no lane could start and the lot was refused
    `no_side_lane` (161 corner lots on the bound of 2026-09-20). The strip
    is now found where the envelope was cut, and the lane's crossing is
    that setback, not the front's."""
    s6s = _sp_setup()
    W, D, ssb = 100.0, 150.0, 15.0
    _, fe, _, area = _corner_lot(W, D)
    env = box(SIDE_S, ssb, W - ssb, D - REAR_S)
    r = _run(_with_words(s6s, "gresham", None, "front"), env, fe, area,
             bearings=[0.0, 90.0], street_setback_ft=ssb)
    _with_words(s6s, "gresham", "owner", "any")
    assert r["site_plan_ok"] is True and r["stalls_provided"] == 8
    assert r["layout_method"] == "townhome_rear_court"
    d = r["geoms"]["driveway"].bounds
    assert d[1] == pytest.approx(ssb, abs=0.6)                        # from the envelope's edge
    c = r["geoms"]["parking_court"].bounds
    assert r["driveway_len_ft"] == pytest.approx(ssb + (c[1] - d[1]), abs=0.6)


def _flag_lot(pole_w: float, sliver: bool = False):
    """A Gresham flag lot: a pole `pole_w` ft wide and 30 ft long up the
    west side to a 90 x 120 body. The pole is setback ground end to end
    (the envelope starts at the body's front setback) unless `sliver`,
    when what the side setbacks leave of the pole -- `pole_w` less twice
    SIDE_S -- stays in the envelope; the only front edge is the pole's end
    on the street.

    Returns (envelope, front_edges, gross area)."""
    lot = shapely.Polygon([(0, 0), (pole_w, 0), (pole_w, 30), (90, 30), (90, 150), (0, 150)])
    env = box(SIDE_S, 30 + FRONT_S, 90 - SIDE_S, 150 - REAR_S)
    if sliver:
        env = env.union(box(SIDE_S, FRONT_S, pole_w - SIDE_S, 30 + FRONT_S + 1.0))
    return env, [[0.0, 0.0, pole_w, 0.0]], lot.area


@pytest.mark.parametrize("sliver", [False, True])
def test_a_flag_lots_pole_is_the_lane_where_it_is_wide_enough(sliver):
    """A flag lot whose 20-ft pole holds no envelope cell at all, or (with
    5-ft side setbacks) a 10-ft sliver of one narrower than Gresham's 12-ft
    lane: the lane from the front street's strip could never start there
    (421 flag lots lost on the bound of 2026-09-20 to the fix that made
    the lane start on the strip, and 122 more with a sliver on the next).
    A pole at least the lane's width IS the lane; the drawn lane resumes
    at the body's top, beside the pod, and the pole's length is not
    counted -- it never was."""
    s6s = _sp_setup()
    env, fe, area = _flag_lot(20.0, sliver)
    r = _run(s6s, env, fe, area)
    assert r["site_plan_ok"] is True and r["stalls_provided"] == 8
    assert r["layout_method"] == "townhome_rear_court"
    b = r["geoms"]["building"].bounds
    d = r["geoms"]["driveway"].bounds
    assert d[1] == pytest.approx(30.0 + FRONT_S, abs=0.6)             # from the body's top
    assert d[0] >= b[2] - 0.6 or d[2] <= b[0] + 0.6                    # beside the pod
    c = r["geoms"]["parking_court"].bounds
    assert d[3] >= c[1] - 0.6
    assert r["driveway_len_ft"] == pytest.approx(FRONT_S + (c[1] - d[1]), abs=0.6)


def test_a_flag_lots_pole_narrower_than_the_lane_refuses_the_lot():
    """The same lot on a 10-ft pole: Gresham's lane is 12 ft, so no lane
    reaches the body and the lot is refused `no_side_lane`. The drawing
    before 2026-09-20 parked this lot over a pole it never measured."""
    s6s = _sp_setup()
    for sliver in (False, True):
        env, fe, area = _flag_lot(10.0, sliver)
        r = _run(s6s, env, fe, area)
        assert r["site_plan_ok"] is False
        assert r["layout_fail"] == "no_side_lane"
        assert "driveway" not in r["geoms"]


def test_a_stub_front_that_misses_the_columns_beside_the_pod_is_refused():
    """An L-shaped lot: a 40-ft stub on the street, the 160-ft body behind
    the neighbour. The stub's strip holds envelope cells, so it is not a
    pole, and the lane must run straight down from that strip -- but the
    pod stands across the stub, and no column beside the pod reaches the
    street, so the lot is refused `no_side_lane`. The drawing before
    2026-09-20 parked it over the neighbour's ground; a lane down the
    stub with the pod slid east of it is FOLLOWUPS 5 (k), and this test
    is the one to flip when it lands."""
    s6s = _sp_setup()
    lot = shapely.Polygon([(0, 0), (40, 0), (40, 30), (160, 30), (160, 150), (0, 150)])
    env = shapely.Polygon([(SIDE_S, FRONT_S), (40 - SIDE_S, FRONT_S),
                           (40 - SIDE_S, 30 + FRONT_S), (160 - SIDE_S, 30 + FRONT_S),
                           (160 - SIDE_S, 150 - REAR_S), (SIDE_S, 150 - REAR_S)])
    r = _run(s6s, env, [[0.0, 0.0, 40.0, 0.0]], lot.area)
    assert r["site_plan_ok"] is False and r["layout_fail"] == "no_side_lane"
