"""Synthetic-lot tests for the quadfit geometry stages (s2/s4/s5/s6)."""

from __future__ import annotations

import math

import pytest

pytest.importorskip("shapely")
pytest.importorskip("numpy")

import numpy as np  # noqa: E402
import shapely  # noqa: E402
from shapely import affinity  # noqa: E402
from shapely.geometry import LineString, Polygon  # noqa: E402
from shapely.strtree import STRtree  # noqa: E402

pytestmark = pytest.mark.unit

STREET_THRESHOLD = 50.0
SIMPLIFY_TOL = 1.5


def _classify(lot, streets):
    from s4_edges import classify_lot

    geoms = np.array(streets, dtype=object)
    return classify_lot(lot, STRtree(geoms), geoms, STREET_THRESHOLD, SIMPLIFY_TOL)


def _square_lot():
    """100x100 lot with a street 30 ft south of its front (south) edge."""
    lot = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    street = LineString([(-60, -30), (160, -30)])
    return lot, [street]


def _fit_setup(res=0.5, widths=(12.0, 90.0, 0.5)):
    import s6_fit

    lo, hi, step = widths
    grid = [round(lo + i * step, 4) for i in range(int((hi - lo) / step) + 1)]
    cfg = {
        "res": res,
        "width_cells": [round(w / res) for w in grid],
        "footprints": [("25x25", 25.0, 25.0), ("18x32", 18.0, 32.0), ("90x90", 90.0, 90.0)],
    }
    s6_fit._init_worker(cfg)
    return s6_fit, grid


# ---------------------------------------------------------------------------
# s4 — edge classification
# ---------------------------------------------------------------------------


def test_square_lot_tier_a_and_edge_classes():
    lot, streets = _square_lot()
    r = _classify(lot, streets)
    assert r["tier"] == "A"
    assert len(r["front_bearings"]) == 1
    assert abs(r["front_bearings"][0] % 180.0) < 1.0
    classes = {cls for *_xy, cls in r["edges"]}
    assert classes == {"F", "R", "S"}
    fronts = [e for e in r["edges"] if e[4] == "F"]
    assert len(fronts) == 1
    assert r["frontage_ft"] == pytest.approx(100, abs=1)


def test_corner_lot_tier_b_two_bearings():
    lot = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    streets = [LineString([(-60, -30), (160, -30)]),  # south
               LineString([(130, -60), (130, 160)])]  # east
    r = _classify(lot, streets)
    assert r["tier"] == "B"
    assert len(r["front_bearings"]) == 2
    deltas = sorted(abs(b % 90) for b in r["front_bearings"])
    assert deltas[0] < 1 and deltas[1] < 1


def test_flag_lot_tier_c():
    # 80x80 body + 12 ft wide x 60 ft long pole down to the street.
    lot = Polygon([
        (0, 60), (34, 60), (34, 0), (46, 0), (46, 60), (80, 60), (80, 140), (0, 140)
    ])
    streets = [LineString([(-60, -30), (160, -30)])]
    r = _classify(lot, streets)
    assert r["tier"] == "C"


def test_landlocked_tier_d():
    lot = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    streets = [LineString([(-60, -500), (160, -500)])]
    r = _classify(lot, streets)
    assert r["tier"] == "D"


def _classify_with_alleys(lot, streets, alleys):
    from s4_edges import classify_lot

    sg = np.array(streets, dtype=object)
    ag = np.array(alleys, dtype=object)
    return classify_lot(
        lot, STRtree(sg), sg, STREET_THRESHOLD, SIMPLIFY_TOL,
        alley_tree=STRtree(ag), alley_geoms=ag,
    )


def _lot_with_an_alley_behind():
    """100x100, street 30 ft south of the front edge, alley 10 ft north of the
    back one -- the ordinary Portland block."""
    lot = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    street = LineString([(-60, -30), (160, -30)])
    alley = LineString([(-60, 110), (160, 110)])
    return lot, [street], [alley]


def test_an_alley_behind_the_lot_is_the_rear_lot_line_not_a_second_front():
    """Portland 33.910: "Street lot line does not include lot lines that abut
    an alley." Gresham 3.0100 and Oregon City 17.04.1000: "A lot line abutting
    an alley is a rear lot line."

    Until 2026-09-11 the alley was in the street file s4 classified against
    and nothing told it apart, so the line along it was ``F``: it was summed
    into the street frontage, it took the front setback, and it was a
    candidate front lot line. Told apart, it is class ``A`` and none of those.
    """
    lot, streets, alleys = _lot_with_an_alley_behind()
    r = _classify_with_alleys(lot, streets, alleys)
    assert r["tier"] == "A", "one street, one frontage direction"
    assert len(r["front_bearings"]) == 1
    classes = [cls for *_xy, cls in r["edges"]]
    assert classes.count("F") == 1 and classes.count("A") == 1
    assert "R" not in classes, "the alley line IS the rear; nothing else is"
    assert r["frontage_ft"] == pytest.approx(100, abs=1), "the street's length only"


def test_where_the_code_says_an_alley_is_a_street_it_is_read_as_one():
    """Clackamas County ZDO 202 ("STREET: See ROAD") and Fairview 19.13
    ("Alley means a narrow street") say the opposite of the other eleven, and
    those two are run against the whole file: the alley is a street edge with
    everything that follows. The same parcel, the other reading."""
    lot, streets, alleys = _lot_with_an_alley_behind()
    r = _classify(lot, streets + alleys)
    classes = [cls for *_xy, cls in r["edges"]]
    assert classes.count("F") == 2 and "A" not in classes
    assert r["frontage_ft"] == pytest.approx(200, abs=1)


def test_a_lot_whose_only_public_way_is_an_alley_keeps_it_as_frontage():
    """Demoting the alley on a lot with nothing else would turn a lot on a
    public way into a landlocked one. Portland 33.910: "Where primary access
    is not possible, the alley may provide primary vehicle access." So it is
    read as it was before alleys were told apart."""
    lot = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    far_street = LineString([(-60, -500), (160, -500)])
    alley = LineString([(-60, 110), (160, 110)])
    r = _classify_with_alleys(lot, [far_street], [alley])
    assert r["tier"] == "A"
    classes = [cls for *_xy, cls in r["edges"]]
    assert classes.count("F") == 1 and "A" not in classes
    assert r["frontage_ft"] == pytest.approx(100, abs=1)


def test_an_alley_edge_takes_the_rear_setback_in_the_envelope():
    """s5 sets the alley line back as a rear lot line. With front 20, rear 5
    and side 5 on a 100x100 lot, an ``A`` rear leaves the same envelope an
    ``R`` rear does, and 15 ft more than an ``F`` one."""
    from s5_envelope import build_envelope

    lot = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    setbacks = {"F": 20.0, "R": 5.0, "S": 5.0}
    setbacks["A"] = setbacks["R"]

    def env_with(rear_cls):
        edges = [
            [0, 0, 100, 0, "F"],
            [100, 0, 100, 100, "S"],
            [100, 100, 0, 100, rear_cls],
            [0, 100, 0, 0, "S"],
        ]
        return build_envelope(lot, edges, setbacks, "A").area

    assert env_with("A") == pytest.approx(env_with("R"))
    assert env_with("A") == pytest.approx(90 * 75)
    assert env_with("F") == pytest.approx(90 * 60)


# ---------------------------------------------------------------------------
# s5 — envelope
# ---------------------------------------------------------------------------


def test_envelope_exact_area_square_lot():
    from s5_envelope import build_envelope

    lot, streets = _square_lot()
    r = _classify(lot, streets)
    env = build_envelope(lot, r["edges"], {"F": 10, "R": 5, "S": 5}, r["tier"])
    # front 10 (south), rear 5 (north), sides 5: 90 wide x 85 deep
    assert env.area == pytest.approx(90 * 85, rel=1e-6)
    minx, miny, maxx, maxy = env.bounds
    assert (minx, miny, maxx, maxy) == pytest.approx((5, 10, 95, 95))


def test_envelope_subset_of_lot_property():
    from s5_envelope import build_envelope

    rng = np.random.default_rng(7)
    for _ in range(20):
        pts = rng.uniform(0, 120, size=(6, 2))
        lot = shapely.convex_hull(shapely.multipoints(pts))
        if lot.geom_type != "Polygon" or lot.area < 2000:
            continue
        streets = [LineString([(-200, -30), (300, -30)])]
        r = _classify(lot, streets)
        env = build_envelope(lot, r["edges"], {"F": 10, "R": 5, "S": 5}, r["tier"])
        assert env.is_empty or env.within(lot.buffer(0.01))


# ---------------------------------------------------------------------------
# s6 — rectangle fit
# ---------------------------------------------------------------------------


def test_fit_square_envelope():
    s6, grid = _fit_setup()
    env = shapely.geometry.MultiPolygon([Polygon([(5, 10), (95, 10), (95, 95), (5, 95)])])
    r = s6.fit_lot(shapely.to_wkb(env), [0.0], True)
    assert r["fits"]["25x25"] == (True, True)
    assert r["fits"]["18x32"][0] is True
    assert r["fits"]["90x90"] == (False, False)
    # Exact-boundary rectangles are rejected (strict interior containment is
    # conservative by design): a hair under the envelope must fit.
    wi = grid.index(89.0)
    assert r["frontier"][wi] * 0.5 == pytest.approx(84.5, abs=1.0)
    # monotone non-increasing
    f = r["frontier"]
    assert all(a >= b for a, b in zip(f, f[1:]))


def test_fit_rotation_invariance():
    s6, grid = _fit_setup()
    env = shapely.geometry.MultiPolygon([Polygon([(5, 10), (95, 10), (95, 95), (5, 95)])])
    rot = affinity.rotate(env, 33.0, origin="centroid")
    r0 = s6.fit_lot(shapely.to_wkb(env), [0.0], True)
    r1 = s6.fit_lot(shapely.to_wkb(rot), [33.0], True)
    assert r0["fits"]["25x25"] == r1["fits"]["25x25"]
    assert r0["fits"]["90x90"] == r1["fits"]["90x90"]
    wi = grid.index(60.0)
    assert abs(r0["frontier"][wi] - r1["frontier"][wi]) <= 2  # ±1 cell tolerance


def test_fit_flip_gating():
    """Deep narrow envelope: 20 wide x 40 deep. 18x32 fits width-facing;
    32x18 would need the flip."""
    s6, _ = _fit_setup()
    env = shapely.geometry.MultiPolygon([Polygon([(0, 0), (20, 0), (20, 40), (0, 40)])])
    r = s6.fit_lot(shapely.to_wkb(env), [0.0], True)
    wf, df = r["fits"]["18x32"]
    assert wf is True
    # 25x25 cannot fit in 20-wide either orientation
    assert r["fits"]["25x25"] == (False, False)
    # axis_required: flip disabled
    r2 = s6.fit_lot(shapely.to_wkb(env), [0.0], False)
    assert r2["fits"]["18x32"][1] is False


def test_fit_flip_only_case():
    """Envelope 35 wide x 20 deep: 18x32 fits ONLY via the 90° flip
    (32 along front, 18 deep)."""
    s6, _ = _fit_setup()
    env = shapely.geometry.MultiPolygon([Polygon([(0, 0), (35, 0), (35, 20), (0, 20)])])
    r = s6.fit_lot(shapely.to_wkb(env), [0.0], True)
    wf, df = r["fits"]["18x32"]
    assert wf is False and df is True


def test_fit_monotone_in_size_property():
    """If a rectangle fits, every smaller rectangle fits (same orientation)."""
    s6, grid = _fit_setup()
    poly = Polygon([(0, 0), (60, 0), (60, 44), (30, 44), (30, 70), (0, 70)])
    env = shapely.geometry.MultiPolygon([poly])
    r = s6.fit_lot(shapely.to_wkb(env), [0.0], True)
    f = r["frontier"]
    assert all(a >= b for a, b in zip(f, f[1:]))


def test_placement_inside_envelope():
    s6, _ = _fit_setup()
    env = shapely.geometry.MultiPolygon([Polygon([(5, 10), (95, 10), (95, 95), (5, 95)])])
    r = s6.fit_lot(shapely.to_wkb(env), [0.0], True, collect_placement=(25.0, 25.0))
    rect = shapely.from_wkb(r["placement"])
    assert rect.within(env.buffer(0.6))  # within half-cell tolerance
    assert rect.area == pytest.approx(625, rel=1e-6)


# ---------------------------------------------------------------------------
# s2 — majority zone
# ---------------------------------------------------------------------------


def test_z_overlay_any_portion_but_not_boundary_touch():
    """PCC 33.418: flag lots with ANY portion inside a z polygon; a shared
    boundary with a neighboring z polygon must NOT count."""
    from s2_assign import flag_z_overlay

    z = Polygon([(50, -100), (200, -100), (200, 200), (50, 200)])
    overlapping = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])  # 50 ft inside
    adjacent = Polygon([(-100, 0), (50, 0), (50, 100), (-100, 100)])  # touches x=50
    clear = Polygon([(-300, 0), (-200, 0), (-200, 100), (-300, 100)])
    flags = flag_z_overlay([overlapping, adjacent, clear], [z])
    assert flags.tolist() == [True, False, False]


def test_majority_zone_split_lot():
    from s2_assign import assign_majority_zone

    lot = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    za = Polygon([(-10, -10), (60, -10), (60, 110), (-10, 110)])   # covers 60%
    zb = Polygon([(60, -10), (200, -10), (200, 110), (60, 110)])  # covers 40%
    zones, fracs = assign_majority_zone([lot], [za, zb], ["A", "B"])
    assert zones[0] == "A"
    assert fracs[0] == pytest.approx(0.6, abs=0.01)
