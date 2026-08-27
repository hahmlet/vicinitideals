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
        }},
        "methods": ["townhome_rear_court"],
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
        }

    s6s_siteplan._init_worker({
        "res": res,
        "pods": [("pod56x36", 56.0, 36.0), ("pod80x25", 80.0, 25.0)],
        "min_stalls": 4, "preferred_stalls": 8,
        "cells": {j: cell(j) for j in sp.cities_it_can_dimension()},
        "methods": ["townhome_rear_court"],
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


def _run(s6s, env, front_edges, area, bearing=0.0, jurisdiction="gresham"):
    return s6s.layout_lot(shapely.to_wkb(env), [bearing], front_edges, area,
                          FRONT_S, jurisdiction)


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
    # Both halves of the refusal are live in the shipped config, and a config
    # where neither is would mean the machinery is untested in production.
    assert "milwaukie" in sp.geometry and not sp.geometry["milwaukie"].lays_out()


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
    """
    s6s = _sp_setup_cities()
    env, fe, area, _ = _rect_lot(85.0, 120.0)

    assert _run(s6s, env, fe, area, jurisdiction="gresham")["site_plan_ok"]
    assert not _run(s6s, env, fe, area,
                    jurisdiction="happy_valley")["site_plan_ok"]

    # Ten feet wider and Happy Valley resolves too -- the refusal above is the
    # lane and not something structural about the city.
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
