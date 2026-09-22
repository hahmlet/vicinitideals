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


def _bulb_lot(radius=45.0):
    """A wedge on a cul-de-sac bulb of ``radius`` about the origin: four
    chords of arc from 250 to 330 degrees, the body 100 ft outward."""
    angs = [math.radians(250 + 20 * k) for k in range(5)]
    arc = [(radius * math.cos(a), radius * math.sin(a)) for a in angs]
    far = radius + 100.0
    return Polygon(arc + [(far * math.cos(angs[-1]), far * math.sin(angs[-1])),
                          (far * math.cos(angs[0]), far * math.sin(angs[0]))])


def _fronts_bulb(lot, streets):
    from shapely.strtree import STRtree

    from s4_edges import dead_ends, fronts_cul_de_sac

    r = _classify(lot, streets)
    ends = dead_ends(streets)
    return fronts_cul_de_sac(r["edges"], STRtree(ends) if ends else None, ends), r


def test_a_lot_on_a_bulb_fronts_a_cul_de_sac_only_where_the_street_ends_in_it():
    """Both halves of Happy Valley's definition. The lot line on "the outer
    radius of a curve" is the same four chords in both cases; what differs
    is the street. A centreline that runs into the bulb and stops is "a
    street ... permanently terminated and provided with a vehicular
    turnaround", and the lot fronts a cul-de-sac. The same centreline
    carried on through -- a knuckle in a winding street, surveyed at the
    same radius, its ends 300 ft away -- is not.
    """
    lot = _bulb_lot()
    on_bulb, r = _fronts_bulb(lot, [LineString([(0, 300), (0, 0)])])
    assert sum(e[4] == "F" for e in r["edges"]) == 4
    assert on_bulb is True

    knuckle, r = _fronts_bulb(lot, [LineString([(0, 300), (0, 0), (-300, 0)])])
    assert sum(e[4] == "F" for e in r["edges"]) == 4, "the same four chords"
    assert knuckle is False


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


def _classify_with_fabric(lot, streets, alleys, lots, rows=()):
    """s4 as it runs since 2026-09-13: the alley centrelines AND the taxlot
    fabric -- this lot, its neighbours (``lots``) and the right-of-way
    polygons (``rows``), which are not private land."""
    from s4_edges import classify_lot

    sg = np.array(streets, dtype=object)
    ag = np.array(alleys, dtype=object)
    lg = np.array([lot, *lots, *rows], dtype=object)
    private = np.array([True] * (1 + len(lots)) + [False] * len(rows))
    return classify_lot(
        lot, STRtree(sg), sg, STREET_THRESHOLD, SIMPLIFY_TOL,
        alley_tree=STRtree(ag), alley_geoms=ag,
        lot_tree=STRtree(lg), lot_geoms=lg, lot_private=private,
    )


def test_the_alleys_width_is_the_gap_to_the_lot_across_it():
    """The alley is the gap in the taxlot fabric between this lot and the
    first private lot beyond, with the centreline inside it. A neighbour
    whose front line is 14 ft behind a 100 x 100 lot's rear line, the
    centreline 7 ft out: the edge is class A and `alley_width_ft` is 14 --
    the typical Portland alley -- whether the file draws the right-of-way
    as a `-STR` polygon in the gap or as nothing at all (179 of Portland's
    alleys are drawn as nothing; the first run demoted every one)."""
    lot = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    street = LineString([(-60, -30), (160, -30)])
    alley = LineString([(-60, 107), (160, 107)])
    behind = shapely.box(0, 114, 100, 214)
    strip = shapely.box(-60, 100, 160, 114)
    for rows in ([], [strip]):
        r = _classify_with_fabric(lot, [street], [alley], [behind], rows)
        assert r["tier"] == "A"
        classes = [cls for *_xy, cls in r["edges"]]
        assert classes.count("A") == 1 and classes.count("F") == 1
        assert r["alley_width_ft"] == pytest.approx(14.0, abs=0.1)
        assert r["alley_edges_demoted"] == 0
    # The same lot the other way round in the file -- clockwise -- measures
    # the same: the ray is cast out of the lot whichever way the ring runs.
    r_cw = _classify_with_fabric(Polygon(list(lot.exterior.coords)[::-1]),
                                 [street], [alley], [behind])
    assert r_cw["alley_width_ft"] == pytest.approx(14.0, abs=0.1)
    # And a lot stacked on this one (a condo file, the same footprint twice)
    # is not the far side of anything.
    r_st = _classify_with_fabric(lot, [street], [alley], [lot, behind])
    assert r_st["alley_width_ft"] == pytest.approx(14.0, abs=0.1)


def test_an_alley_edge_with_a_neighbour_across_it_is_not_on_the_alley():
    """Fifty feet of centreline is not an alley. On the 2026-09-13 probe
    937 class-A edges abutted a neighbour's lot with an address, the alley
    running behind THAT lot, and 82 of them stood under a green that parked
    four cars in the neighbour's yard. With the fabric in hand the test is
    whether the alley lies across the edge: here the neighbour does, and
    the centreline runs 27 ft behind its front line, so the edge is the
    rear lot line it always was."""
    lot = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    street = LineString([(-60, -30), (160, -30)])
    alley = LineString([(-60, 127), (160, 127)])      # 27 ft out: within 50
    neighbour = shapely.box(0, 100, 100, 200)          # but directly across
    r = _classify_with_fabric(lot, [street], [alley], [neighbour])
    assert r["tier"] == "A"
    classes = [cls for *_xy, cls in r["edges"]]
    assert "A" not in classes and classes.count("R") == 1
    assert r["alley_width_ft"] is None
    assert r["alley_edges_demoted"] == 1
    # And a lot whose only public way was that centreline is landlocked,
    # not fronted on the alley behind the neighbour.
    far_street = LineString([(-60, -500), (160, -500)])
    r = _classify_with_fabric(lot, [far_street], [alley], [neighbour])
    assert r["tier"] == "D" and r["alley_edges_demoted"] == 1


def test_a_sliver_between_the_lot_and_the_alley_is_not_the_alley():
    """A 2 ft private sliver along the rear line, the alley behind it: the
    gap to the first private lot is 2 ft, which is no alley's width, and
    the centreline is 9 ft out, past the far side by more than the
    tolerance, so the gap is not the alley and the edge is not on it."""
    lot = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    street = LineString([(-60, -30), (160, -30)])
    alley = LineString([(-60, 109), (160, 109)])
    sliver = shapely.box(0, 100, 100, 102)
    behind = shapely.box(0, 116, 100, 216)
    r = _classify_with_fabric(lot, [street], [alley], [sliver, behind])
    classes = [cls for *_xy, cls in r["edges"]]
    assert "A" not in classes
    assert r["alley_width_ft"] is None and r["alley_edges_demoted"] == 1


def test_a_right_of_way_split_down_the_middle_is_one_alley():
    """Multnomah's `-STR` lots are one per quarter-section, and a section
    line can run down an alley's centre. The ray looks through both halves
    to the lot beyond, so a 7 + 7 alley measures 14, not 7."""
    lot = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    street = LineString([(-60, -30), (160, -30)])
    alley = LineString([(-60, 107), (160, 107)])
    halves = [shapely.box(-60, 100, 160, 107), shapely.box(-60, 107, 160, 114)]
    behind = shapely.box(0, 114, 100, 214)
    r = _classify_with_fabric(lot, [street], [alley], [behind], halves)
    assert r["alley_width_ft"] == pytest.approx(14.0, abs=0.1)


def test_a_lot_at_the_alleys_dead_end_is_not_on_it():
    """An alley that ends against a 50 ft rear line touches 14 ft of it.
    The midpoint's ray runs down the alley's length -- 80 ft with no lot
    across it, which is what the 145 chords over 40 ft on the probe were --
    and the rays either side of it start on the flanking neighbours' lot
    lines, a gap of nothing. None of five finds an alley; the lot parks
    nothing in anyone's yard."""
    lot = Polygon([(0, 0), (50, 0), (50, 100), (0, 100)])
    street = LineString([(-60, -30), (160, -30)])
    alley = LineString([(25, 100), (25, 300)])
    strip = shapely.box(18, 100, 32, 300)
    flanks = [shapely.box(-50, 100, 18, 200), shapely.box(32, 100, 100, 200)]
    r = _classify_with_fabric(lot, [street], [alley], flanks, [strip])
    classes = [cls for *_xy, cls in r["edges"]]
    assert "A" not in classes
    assert r["alley_width_ft"] is None and r["alley_edges_demoted"] == 1


def test_a_side_alley_opposite_the_midpoint_is_not_a_hole_in_the_alley():
    """A T: the alley behind the lot has another leaving it opposite the
    lot's midpoint. The midpoint's ray runs up that leg and finds no lot
    within 80 ft, which is not a width; the four rays either side find
    the lots across at 14 ft. Four of five is the alley. (The second run
    wanted the midpoint itself and demoted `1N1E13CB -09300`, a green on a
    10 ft alley, for the T behind it.)"""
    lot = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    street = LineString([(-60, -30), (160, -30)])
    alleys = [LineString([(-60, 107), (160, 107)]), LineString([(50, 107), (50, 400)])]
    across = [shapely.box(-60, 114, 43, 214), shapely.box(57, 114, 160, 214)]
    r = _classify_with_fabric(lot, [street], alleys, across)
    classes = [cls for *_xy, cls in r["edges"]]
    assert classes.count("A") == 1
    assert r["alley_width_ft"] == pytest.approx(14.0, abs=0.1)
    assert r["alley_edges_demoted"] == 0


def test_a_centreline_drawn_short_of_its_right_of_way_is_still_the_alley():
    """RLIS draws a platted alley's centreline shorter than the strip the
    taxlot file holds for it: behind this 50 ft lot the strip runs on and
    the lot across is 16 ft out, but the centreline stops 10 ft before
    the lot's first corner. No ray crosses it; four of the five rays'
    bands along the alley reach it (`ALLEY_CL_ALONG_FT`), so the edge is
    on the alley and the width is 16. (The second run wanted the crossing
    and demoted 170 such lots, 52 of them greens.) Draw the centreline 30
    ft out instead -- inside the lot across, not in the gap -- and no band
    holds it: the strip is not this alley."""
    lot = Polygon([(0, 0), (50, 0), (50, 100), (0, 100)])
    street = LineString([(-60, -30), (160, -30)])
    strip = shapely.box(-300, 100, 300, 116)
    behind = shapely.box(-300, 116, 300, 216)
    short = LineString([(-300, 108), (-10, 108)])
    r = _classify_with_fabric(lot, [street], [short], [behind], [strip])
    classes = [cls for *_xy, cls in r["edges"]]
    assert classes.count("A") == 1
    assert r["alley_width_ft"] == pytest.approx(16.0, abs=0.1)
    elsewhere = LineString([(-300, 130), (300, 130)])
    r = _classify_with_fabric(lot, [street], [elsewhere], [behind], [strip])
    classes = [cls for *_xy, cls in r["edges"]]
    assert "A" not in classes and r["alley_edges_demoted"] == 1


def test_an_alley_along_the_freeway_is_measured_off_its_centreline():
    """Behind the lot a 16 ft strip, and beyond it the freeway: public land
    as far as the ray reaches, no private lot to measure to (72 Portland
    lots back onto I-5 this way, 17 onto the St. Johns rail cut). The lot
    line is on public land and the centreline crosses the ray 8 ft out,
    so the alley is 16 ft wide. Take the strip away -- the lot line on
    private land, the same centreline, nothing across for 80 ft -- and
    there is no alley to stand the centreline in for."""
    lot = Polygon([(0, 0), (50, 0), (50, 100), (0, 100)])
    street = LineString([(-60, -30), (160, -30)])
    alley = LineString([(-300, 108), (300, 108)])
    strip = shapely.box(-300, 100, 300, 116)
    freeway = shapely.box(-300, 116, 300, 400)
    r = _classify_with_fabric(lot, [street], [alley], [], [strip, freeway])
    classes = [cls for *_xy, cls in r["edges"]]
    assert classes.count("A") == 1
    assert r["alley_width_ft"] == pytest.approx(16.0, abs=0.1)
    r = _classify_with_fabric(lot, [street], [alley], [], [])
    classes = [cls for *_xy, cls in r["edges"]]
    assert "A" not in classes and r["alley_edges_demoted"] == 1


def test_an_eight_foot_strip_is_the_narrowest_alley():
    """`ALLEY_WIDTH_MIN_FT` is tested on the width as reported, to a tenth:
    a strip that measures 7.98 ft is an 8 ft alley (a block of eight in
    NE Portland), and one that measures 7.9 is not."""
    lot = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    street = LineString([(-60, -30), (160, -30)])
    alley = LineString([(-60, 104), (160, 104)])
    r = _classify_with_fabric(lot, [street], [alley], [shapely.box(0, 107.98, 100, 208)])
    assert r["alley_width_ft"] == pytest.approx(8.0, abs=0.01)
    r = _classify_with_fabric(lot, [street], [alley], [shapely.box(0, 107.9, 100, 208)])
    assert r["alley_width_ft"] is None and r["alley_edges_demoted"] == 1


def test_a_gap_too_wide_to_be_an_alley_is_not_one():
    """The far side 60 ft out with the centreline 7 ft out is a ray across
    the alley and on through the street beyond, not a 60 ft alley: past
    `ALLEY_WIDTH_MAX_FT` nothing is a width."""
    lot = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    street = LineString([(-60, -30), (160, -30)])
    alley = LineString([(-60, 107), (160, 107)])
    behind = shapely.box(0, 160, 100, 260)
    r = _classify_with_fabric(lot, [street], [alley], [behind])
    classes = [cls for *_xy, cls in r["edges"]]
    assert "A" not in classes
    assert r["alley_width_ft"] is None and r["alley_edges_demoted"] == 1


# ---------------------------------------------------------------------------
# s4 -- the zone across each lot line
# ---------------------------------------------------------------------------


def _across(lot, streets, alleys, fabric, rows=()):
    """`classify_lot` and then `neighbour_zones` on one lot, the way s4's main
    runs them: ``fabric`` is a list of (polygon, jurisdiction, zone_raw,
    split_zone) for every private neighbour; ``rows`` are right-of-way
    polygons. The lot itself is in the fabric, zoned like a Portland CM2 lot."""
    from s4_edges import classify_lot, neighbour_zones

    sg = np.array(streets, dtype=object)
    ag = np.array(alleys, dtype=object)
    polys = [lot, *[f[0] for f in fabric], *rows]
    lg = np.array(polys, dtype=object)
    private = np.array([True] * (1 + len(fabric)) + [False] * len(rows))
    juris = np.array(["portland", *[f[1] for f in fabric], *[None] * len(rows)], dtype=object)
    zone = np.array(["CM2", *[f[2] for f in fabric], *[None] * len(rows)], dtype=object)
    split = np.array([False, *[f[3] for f in fabric], *[False] * len(rows)])
    tree = STRtree(lg)
    r = classify_lot(
        lot, STRtree(sg), sg, STREET_THRESHOLD, SIMPLIFY_TOL,
        alley_tree=STRtree(ag) if len(ag) else None, alley_geoms=ag if len(ag) else None,
        lot_tree=tree, lot_geoms=lg, lot_private=private,
    )
    across = neighbour_zones([r], tree, lg, private, juris, zone, split)[0]
    return r, across


def test_the_zone_across_each_non_street_line_is_read_off_the_fabric():
    """Portland 33.130.215.B.2 asks, of every lot line that is not a street
    lot line, what zone the lot across it is in. A 100 x 100 CM2 lot with
    the street south: R5 behind it, CM2 to the east, and to the west a
    neighbour the rules have never zoned. The street edge is not asked;
    the other three are answered per line, with what was found and what
    was not, and this lot is nobody's own neighbour."""
    lot = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    street = LineString([(-60, -30), (160, -30)])
    behind = (shapely.box(0, 100, 100, 200), "portland", "R5", False)
    east = (shapely.box(100, 0, 200, 100), "portland", "CM2", False)
    west = (shapely.box(-100, 0, 0, 100), "portland", None, False)
    r, across = _across(lot, [street], [], [behind, east, west])
    classes = [cls for *_xy, cls in r["edges"]]
    assert len(across) == len(r["edges"]) == 4
    by_class = dict(zip(classes, across))
    assert by_class["F"] is None, "the street is what is across a street edge"
    assert by_class["R"] == {"z": [["portland", "R5"]], "split": 0, "none": 0}
    sides = [a for cls, a in zip(classes, across) if cls == "S"]
    assert {"z": [["portland", "CM2"]], "split": 0, "none": 0} in sides
    assert {"z": [], "split": 5, "none": 0} in sides, "an unzoned neighbour is not a zone"
    # Clockwise in the file, the same answers: the points are cast out of
    # the lot whichever way the ring runs.
    r_cw, across_cw = _across(Polygon(list(lot.exterior.coords)[::-1]), [street], [], [behind, east, west])
    assert sorted(str(a) for a in across_cw) == sorted(str(a) for a in across)


def test_a_zoning_line_meeting_the_rear_line_reads_as_both_zones():
    """The rear neighbour is two lots, R5 for the western 40 ft and CM2 for
    the rest: two of five points find R5, three find CM2, and BOTH are
    reported. The reader decides what a line that is partly residential
    means; s4 does not vote."""
    lot = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    street = LineString([(-60, -30), (160, -30)])
    fabric = [
        (shapely.box(0, 100, 40, 200), "portland", "R5", False),
        (shapely.box(40, 100, 100, 200), "portland", "CM2", False),
        (shapely.box(100, 0, 200, 100), "portland", "CM2", False),
        (shapely.box(-100, 0, 0, 100), "portland", "CM2", False),
    ]
    r, across = _across(lot, [street], [], fabric)
    rear = [a for (*_xy, cls), a in zip(r["edges"], across) if cls == "R"][0]
    assert rear == {"z": [["portland", "CM2"], ["portland", "R5"]], "split": 0, "none": 0}


def test_a_split_zone_neighbour_and_public_land_are_not_answers():
    """A neighbour whose own majority zone covers under 90 % of it says
    nothing about the shared line, and a park drawn as right-of-way, or a
    gap in the fabric, is no zoned lot: both are counted as what they are,
    not read as a zone, so the reader can refuse to certify on them."""
    lot = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    street = LineString([(-60, -30), (160, -30)])
    fabric = [
        (shapely.box(0, 100, 100, 200), "portland", "R5", True),   # split
        (shapely.box(100, 0, 200, 100), "portland", "CM2", False),
    ]
    park = shapely.box(-100, 0, 0, 100)
    r, across = _across(lot, [street], [], fabric, rows=[park])
    by_class = {}
    for (*_xy, cls), a in zip(r["edges"], across):
        by_class.setdefault(cls, []).append(a)
    assert by_class["R"] == [{"z": [], "split": 5, "none": 0}]
    assert {"z": [], "split": 0, "none": 5} in by_class["S"], "the park"
    assert {"z": [["portland", "CM2"]], "split": 0, "none": 0} in by_class["S"]
    # A stacked lot on the same footprint (a condo file) is not a neighbour.
    stacked = [(lot, "portland", "CM2", False), *fabric]
    r2, across2 = _across(lot, [street], [], stacked, rows=[park])
    assert sorted(str(a) for a in across2) == sorted(str(a) for a in across)


def test_an_alley_line_is_read_across_the_alley():
    """Portland 33.910: an alley line is not a street lot line, so
    33.130.215.B.2 asks what it abuts. The zoning map runs to the
    centreline, so what a lot line on an alley abuts is the far side of
    the alley: the sample is cast the alley's measured width and two feet
    out, into the lot beyond. R5 across a 14 ft alley reads R5; the
    right-of-way strip in the gap, where the file draws one, is looked
    through and not counted."""
    lot = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    street = LineString([(-60, -30), (160, -30)])
    alley = LineString([(-60, 107), (160, 107)])
    behind = (shapely.box(0, 114, 100, 214), "portland", "R5", False)
    flank_e = (shapely.box(100, 0, 200, 100), "portland", "CM2", False)
    flank_w = (shapely.box(-100, 0, 0, 100), "portland", "CM2", False)
    strip = shapely.box(-60, 100, 160, 114)
    for rows in ([], [strip]):
        r, across = _across(lot, [street], [alley], [behind, flank_e, flank_w], rows)
        classes = [cls for *_xy, cls in r["edges"]]
        assert classes.count("A") == 1 and r["alley_width_ft"] == pytest.approx(14.0, abs=0.1)
        a = across[classes.index("A")]
        assert a == {"z": [["portland", "R5"]], "split": 0, "none": 0}


def test_a_neighbour_in_another_city_is_named_with_its_city():
    """The city line runs down the rear lot line: the lot behind is
    Gresham's, in Gresham's zone. It is reported as such, and it is the
    reader's business that Portland's list of residential zones says
    nothing about Gresham's codes."""
    lot = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    street = LineString([(-60, -30), (160, -30)])
    fabric = [
        (shapely.box(0, 100, 100, 200), "gresham", "LDR-7", False),
        (shapely.box(100, 0, 200, 100), "portland", "CM2", False),
        (shapely.box(-100, 0, 0, 100), "portland", "CM2", False),
    ]
    r, across = _across(lot, [street], [], fabric)
    rear = [a for (*_xy, cls), a in zip(r["edges"], across) if cls == "R"][0]
    assert rear == {"z": [["gresham", "LDR-7"]], "split": 0, "none": 0}


def test_a_landlocked_lot_has_no_lines_to_ask():
    lot = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    far_street = LineString([(-60, -500), (160, -500)])
    r, across = _across(lot, [far_street], [], [])
    assert r["tier"] == "D" and across == []


def test_without_the_fabric_the_centreline_alone_decides():
    """The fabric is optional: a caller without it (the two cities whose
    code says an alley is a street never pass alleys at all, and a stage
    run before 2026-09-13 passed no polygons) gets the centreline test
    alone, no width and no demotion."""
    lot, streets, alleys = _lot_with_an_alley_behind()
    r = _classify_with_alleys(lot, streets, alleys)
    classes = [cls for *_xy, cls in r["edges"]]
    assert classes.count("A") == 1
    assert r["alley_width_ft"] is None and r["alley_edges_demoted"] == 0


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


def test_s5_writes_down_the_strip_it_cut_off_each_edge_class():
    """``env_setbacks_json`` is what `build_envelope` really took: the class's
    own setback on a traced A/B lot, the largest of the four on every class
    where the inset is uniform (tier C, or nothing traced), nothing on a tier
    D lot that keeps no envelope. FLATS charges its parking court against
    this strip rather than against the setback its own rules resolve."""
    from s5_envelope import build_envelope, cuts_made

    lot = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    setbacks = {"F": 20.0, "R": 5.0, "S": 5.0, "A": 0.0}
    edges = [[0, 0, 100, 0, "F"], [100, 0, 100, 100, "S"],
             [100, 100, 0, 100, "R"], [0, 100, 0, 0, "S"]]

    assert cuts_made(setbacks, edges, "A") == setbacks
    assert cuts_made(setbacks, edges, "B") == setbacks
    uniform = {"F": 20.0, "R": 20.0, "S": 20.0, "A": 20.0}
    assert cuts_made(setbacks, edges, "C") == uniform
    assert cuts_made(setbacks, [], "A") == uniform
    assert cuts_made(setbacks, edges, "D") is None
    # And the record matches the geometry: a tier C lot really is inset by
    # the largest number on every side.
    env_c = build_envelope(lot, edges, setbacks, "C")
    assert env_c.bounds == pytest.approx((20.0, 20.0, 80.0, 80.0))
    env_a = build_envelope(lot, edges, setbacks, "A")
    assert env_a.bounds == pytest.approx((5.0, 20.0, 95.0, 95.0))


def test_a_zero_alley_setback_runs_the_envelope_to_the_alley_line():
    """PCC 33.110.220.D.9 / 33.120.220.B.3.g: no side or rear setback from a
    lot line abutting an alley. s5 takes the ``A`` number it is handed and
    nothing else -- at zero the envelope reaches the alley line, at the rear's
    five it stops five short. ``lot_setbacks`` hands the zero for the zones
    that state it, Gresham's alley column with the rear roof plane on top of
    it (7.0420(G)(1) puts the 21 ft roof "at the rear setback line", and with
    an alley that line is the alley column's), and the rear for every other."""
    from common import load_rules
    from s5_envelope import build_envelope, lot_setbacks

    lot = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    edges = [[0, 0, 100, 0, "F"], [100, 0, 100, 100, "S"],
             [100, 100, 0, 100, "A"], [0, 100, 0, 0, "S"]]
    base = {"F": 20.0, "R": 5.0, "S": 5.0}
    env0 = build_envelope(lot, edges, {**base, "A": 0.0}, "A")
    env5 = build_envelope(lot, edges, {**base, "A": 5.0}, "A")
    assert env0.area == pytest.approx(90 * 80)
    assert env0.bounds[3] == pytest.approx(100.0)   # on the alley line
    assert env5.area == pytest.approx(90 * 75)
    assert env5.bounds[3] == pytest.approx(95.0)

    rules = load_rules()
    pdx = lot_setbacks(rules.jurisdictions["portland"].rule_for("R5"), 5000.0, "A")
    assert pdx["A"] == 0.0 and pdx["R"] > 0
    # Gresham LDR-5: Table 4.0131 reads rear 15 / with alley 8, and the 26 ft
    # pod owes five more feet of roof plane off either line -- 20 and 13.
    gre_rule = rules.jurisdictions["gresham"].rule_for("LDR-5")
    gre = lot_setbacks(gre_rule, 5000.0, "A")
    assert gre_rule.setback_rear_ft == 15 and gre_rule.setback_alley_ft == 8
    assert gre["R"] == pytest.approx(20.0) and gre["A"] == pytest.approx(13.0)
    assert gre_rule.effective_setback_alley_ft(height_ft=21.0) == pytest.approx(8.0)
    # HDR-PV states no roof plane, so its alley five is five; CMF states no
    # alley column on the quadplex row, so its alley line is its rear line.
    hdr = rules.jurisdictions["gresham"].rule_for("HDR-PV")
    assert lot_setbacks(hdr, 5000.0, "A")["A"] == pytest.approx(5.0)
    cmf = rules.jurisdictions["gresham"].rule_for("CMF")
    cmf_sb = lot_setbacks(cmf, 12000.0, "A")
    assert cmf.setback_alley_ft is None and cmf_sb["A"] == cmf_sb["R"] == pytest.approx(15.0)
    # and the envelope on a Gresham alley lot runs to 13 ft of the alley, not 20
    env_g = build_envelope(lot, edges, {**base, "R": gre["R"], "A": gre["A"]}, "A")
    assert env_g.bounds[3] == pytest.approx(100.0 - 13.0)
    # Tier C is one uniform inset by the LARGEST of the four; the alley's zero
    # never shrinks it, and the strict side is said so in s5's docstring.
    assert max(lot_setbacks(rules.jurisdictions["portland"].rule_for("R5"), 5000.0, "C").values()) == pdx["F"]


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
