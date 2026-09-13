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
        }},
        "methods": ["townhome_rear_court", "townhome_rear_court_alley"],
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
        }

    s6s_siteplan._init_worker({
        "res": res,
        "pods": [("pod56x36", 56.0, 36.0), ("pod80x25", 80.0, 25.0)],
        "min_stalls": 4, "preferred_stalls": 8,
        "cells": {j: cell(j) for j in sp.cities_it_can_dimension()},
        "methods": ["townhome_rear_court", "townhome_rear_court_alley"],
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
         alley_edges=None, alley_setback_ft=0.0):
    return s6s.layout_lot(
        shapely.to_wkb(env), [bearing], front_edges, area,
        FRONT_S if front_setback_ft is None else front_setback_ft,
        jurisdiction, zone, parking_setback_ft, alley_edges, alley_setback_ft)


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


def _run_pdx(s6s, env, fe, ae, area, bearing=0.0):
    """Portland's cell, with the alley edges and the alley setback handed in
    the way s6s main() hands them."""
    return _run(s6s, env, fe, area, bearing=bearing, jurisdiction="portland",
                zone="R5", parking_setback_ft=10.0,
                alley_edges=ae, alley_setback_ft=REAR_S)


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
    assert sp.layout_methods == ["townhome_rear_court", "townhome_rear_court_alley"]
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
    # 39 ft of court left behind it -- 2.5 ft short of one row of stalls and a
    # one-way aisle. `layout_fail` says so; see the two tests that assert it.
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
    the 80 ft-deep skinny pod, and the 39 ft behind it is 2.5 ft short of a
    stall and a one-way aisle. Nothing about the lane is reached or reported.
    These two lots differ by two feet of frontage and belong to different
    piles: this one is answered by a shallower parking bay, the other by a
    narrower driveway, and lumping them together hides both.
    """
    s6s = _sp_setup()
    env, fe, area, lot = _rect_lot(46.0, 150.0)
    r = _run(s6s, env, fe, area)
    assert r["site_plan_ok"] is False
    assert r["layout_fail"] == "court_too_shallow"


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


def test_footprints_yaml_sends_two_cities_driveways_to_the_alley():
    """Portland (PCC 33.266.120.C.3) and Gresham (GDC 7.0420(B)(1), "Lots,
    including middle housing without existing access, that abut an alley,
    shall take access from the alley") send the driveway round the back, and
    each says so on its own row with the section beside it. Pinned as a set:
    the flag must not leak to a city by default, and a city joining needs its
    sentence read. (Until 2026-09-12 this test said Gresham had no such
    sentence; it had, in the chapter the driveway row already cited.)"""
    from common import load_footprints

    sp = load_footprints().siteplan
    pdx = sp.driveway_for("portland")
    assert pdx is not None and pdx.alley_access_required is True
    assert "33.266.120.C" in pdx.cite and ".C.3" in pdx.cite
    gre = sp.driveway_for("gresham")
    assert gre is not None and gre.alley_access_required is True
    assert "7.0420(B)(1)" in gre.cite
    assert {j for j, dw in sp.driveway.items() if dw.alley_access_required} == {
        "portland", "gresham"}
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
    LDR-5 lot is too shallow for a court behind the pod when the alley line
    is charged the rear's twenty, and parks eight off the alley when it is
    charged the alley column's thirteen -- with the thirteen-foot strip, not
    a lane from the street, as the pavement between court and alley."""
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
                         alley_edges=ae, alley_setback_ft=alley_setback)

    env_r, r_rear = plan(sb["R"])          # the alley charged as a plain rear
    assert r_rear["site_plan_ok"] is False and r_rear["layout_fail"] == "court_too_shallow"
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
    a car's length short on 6,700 of Portland's 11,519 alley lots."""
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
                         alley_edges=ae, alley_setback_ft=alley_setback)

    env_r, r_rear = plan(sb["R"])         # yesterday: the alley charged as a rear
    assert r_rear["site_plan_ok"] is False and r_rear["layout_fail"] == "court_too_shallow"
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
