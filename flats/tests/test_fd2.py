"""FD2 pass 1 measures and classes (flats/ingest/fd2.py)."""

from __future__ import annotations

import math

import numpy as np
import pytest
from shapely.geometry import Polygon

from flats.ingest import fd2

# An 80 x 25 building, its front (the long side at y = 0) facing a street
# along y = -20.
RING = [(0, 0), (80, 0), (80, 25), (0, 25), (0, 0)]
STREET = ((-50.0, -20.0, 150.0, -20.0),)


def test_frame_names_front_and_left_from_the_street():
    fr = fd2.frame(RING, STREET)
    # Standing on the street (south) facing north, left is west (x = 0).
    assert fr.fl == (0.0, 0.0) and fr.fr == (80.0, 0.0)
    assert fr.bl == (0.0, 25.0) and fr.br == (80.0, 25.0)
    assert fr.long_ft == pytest.approx(80) and fr.short_ft == pytest.approx(25)
    assert fr.front_known


def test_frame_front_is_the_long_side_nearer_the_street_whatever_the_ring_order():
    ring = [(80, 25), (0, 25), (0, 0), (80, 0)]
    north = ((-50.0, 60.0, 150.0, 60.0),)
    fr = fd2.frame(ring, north)
    # Street to the north: the front is y = 25; facing south, left is east.
    assert {fr.fl, fr.fr} == {(0.0, 25.0), (80.0, 25.0)}
    assert fr.fl == (80.0, 25.0)


def test_frame_rejects_a_ring_that_is_not_four_corners():
    with pytest.raises(ValueError):
        fd2.frame([(0, 0), (1, 0), (0, 1)], STREET)


def _plane(ax: float, by: float, c: float = 100.0):
    return lambda pts: c + ax * np.asarray(pts)[:, 0] + by * np.asarray(pts)[:, 1]


def test_ground_shape_on_a_plane():
    fr = fd2.frame(RING, STREET)
    # Falls 0.05 ft/ft to the east (right) and rises 0.04 ft/ft to the back.
    got = fd2.ground_shape(fr, _plane(-0.05, 0.04))
    assert got["fall_along_ft"] == pytest.approx(4.0, abs=0.01)  # left higher by 80 * 0.05
    assert got["fall_across_ft"] == pytest.approx(-1.0, abs=0.01)  # front lower by 25 * 0.04
    assert got["relief_ft"] == pytest.approx(5.0, abs=0.01)
    assert got["high_end"] == "left" and got["high_side"] == "back"
    assert got["z_front_left"] == pytest.approx(100.0)
    assert got["z_back_right"] == pytest.approx(100.0 - 4.0 + 1.0)


def test_relief_never_below_either_fall():
    fr = fd2.frame(RING, STREET)
    rng = np.random.default_rng(3)
    bumps = rng.normal(size=(30, 90))

    def z(pts):
        p = np.asarray(pts)
        return bumps[np.clip((p[:, 1]).astype(int), 0, 29), np.clip(p[:, 0].astype(int), 0, 89)]

    got = fd2.ground_shape(fr, z)
    assert got["relief_ft"] >= abs(got["fall_along_ft"]) and got["relief_ft"] >= abs(got["fall_across_ft"])


def test_ground_shape_leaves_missing_ground_missing():
    fr = fd2.frame(RING, STREET)
    got = fd2.ground_shape(fr, lambda pts: np.full(len(pts), np.nan))
    assert got["relief_ft"] is None and got["fall_along_ft"] is None and got["high_side"] is None
    assert got["z_front_left"] is None


def test_level_ground_reads_level():
    fr = fd2.frame(RING, STREET)
    got = fd2.ground_shape(fr, _plane(0.0, 0.0))
    assert got["high_side"] == "level" and got["high_end"] == "level" and got["relief_ft"] == 0.0


@pytest.mark.parametrize("relief,label", [
    (0.0, "0-1"), (1.0, "0-1"), (1.01, "1-2"), (3.0, "2-3"), (3.5, "3-4"), (5.9, "4-6"),
    (8.0, "6-8"), (8.01, "over 8"), (None, "missing"), (math.nan, "missing"),
])
def test_relief_class(relief, label):
    assert fd2.relief_class(relief) == label


def test_ft_bin_is_by_size():
    assert fd2.ft_bin(-2.5) == "2-3" and fd2.ft_bin(0.0) == "0-1" and fd2.ft_bin(1.0) == "0-1"
    assert fd2.ft_bin(None) == "missing"


def test_setback_line_and_street_rise():
    lot = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    fronts = ((0.0, 0.0, 100.0, 0.0),)
    line = fd2.setback_line(lot, fronts, 10.0)
    pts = fd2.geom_points(line)
    assert np.allclose(pts[:, 1], 10.0) and pts[:, 0].min() == pytest.approx(0) and pts[:, 0].max() == pytest.approx(100)
    z = _plane(0.01, 0.5)  # rises 5 ft in the 10 ft to the setback; street highest at x = 100 (1 ft)
    rise = fd2.street_rise(z(fd2.line_points(fronts)), z(pts))
    assert rise == pytest.approx(5.0 - 1.0)
    assert fd2.street_rise(np.array([]), np.array([1.0])) is None


def test_soil_layer_reads_the_1_to_5_ft_layer():
    hz = [
        {"hzdept_r": 0, "hzdepb_r": 20, "unified": "OL", "lep_r": 9.0, "frag3to10_r": 20, "fraggt10_r": 0},
        {"hzdept_r": 20, "hzdepb_r": 80, "unified": "ML", "lep_r": 3.0, "frag3to10_r": 0, "fraggt10_r": 0},
        {"hzdept_r": 80, "hzdepb_r": 200, "unified": "CL", "lep_r": 4.5, "frag3to10_r": 2, "fraggt10_r": 1},
    ]
    got = fd2.soil_layer(hz)
    # 1-5 ft is 30.5-152.4 cm: ML over 49.5 cm, CL over 72.4 cm.
    assert got["unified_1_5ft"] == "CL" and got["unified_1_5ft_all"] == "ML,CL"
    assert got["lep_1_5ft_pct"] == 4.5  # the surface 9.0 lies above the layer
    assert got["organic_1_5ft"] is False
    assert got["frag_gt3in_pct"] == 20  # fragments are read from the surface down
    assert fd2.soil_layer([])["unified_1_5ft"] is None and fd2.soil_layer([])["organic_1_5ft"] is None


def test_restrictions_split_bedrock_and_pan():
    rows = [{"reskind": "Lithic bedrock", "resdept_r": 140}, {"reskind": "Fragipan", "resdept_r": 90},
            {"reskind": "Abrupt textural change", "resdept_r": 40}]
    got = fd2.restrictions(rows)
    assert got["restriction_cm"] == 40 and got["restriction_kind"] == "Abrupt textural change"
    assert got["bedrock_cm"] == 140 and got["pan_cm"] == 90 and got["pan_kind"] == "Fragipan"


def test_high_water():
    months = [{"monthseq": 1, "month": "January", "wet_top_cm": 30}, {"monthseq": 2, "month": "February", "wet_top_cm": 30},
              {"monthseq": 3, "month": "March", "wet_top_cm": 60}, {"monthseq": 7, "month": "July", "wet_top_cm": None}]
    assert fd2.high_water(months) == (30, "January,February")
    assert fd2.high_water([]) == (None, None)


def _firm(**over):
    base = {"slide_mapped": False, "slide_top": False, "liq_top2": False, "flood_100": False, "soil_no_data": False,
            "restrictions_known": True, "bedrock_cm": None, "pan_cm": None, "frag_gt3in_pct": 0.0,
            "lep_1_5ft_pct": 1.5, "hydric": "No", "organic_1_5ft": False, "water_cm": None,
            "water_months_held": True, "drainage": "Well drained"}
    base.update(over)
    return base


@pytest.mark.parametrize("over,want", [
    ({}, "FIRM"),
    ({"slide_top": True, "liq_top2": True}, "HAZ-SLIDE"),
    ({"liq_top2": True, "flood_100": True}, "HAZ-LIQ"),
    ({"flood_100": True, "soil_no_data": True}, "FLOOD"),
    ({"soil_no_data": True}, "NO-DATA"),
    ({"soil_no_data": None}, "NO-DATA"),
    ({"bedrock_cm": 152.4, "frag_gt3in_pct": 40}, "ROCK"),
    ({"bedrock_cm": 153.0}, "FIRM"),
    ({"frag_gt3in_pct": 15.0}, "COBBLE"),
    ({"lep_1_5ft_pct": 6.0}, "SWELL"),
    ({"hydric": "Yes"}, "SOFT"),
    ({"organic_1_5ft": True}, "SOFT"),
    ({"water_cm": 60.96}, "WET-FINE"),
    ({"water_cm": 61.0}, "FIRM"),
    ({"drainage": "Somewhat poorly drained"}, "WET-FINE"),
    ({"drainage": "Moderately well drained"}, "FIRM"),
])
def test_ground_class_first_match_wins(over, want):
    assert fd2.ground_class(_firm(**over))[0] == want


def test_ground_class_names_what_it_could_not_check():
    g, unread, pan = fd2.ground_class(_firm(liq_top2=None, lep_1_5ft_pct=None, hydric="Unranked"))
    assert g == "FIRM" and unread == ["HAZ-LIQ", "SWELL", "SOFT"]
    assert pan is False
    # A missing slide map never sorts a lot as safe silently.
    g, unread, _ = fd2.ground_class(_firm(slide_mapped=None))
    assert g == "FIRM" and "HAZ-SLIDE" in unread
    # Monthly rows held but no wet layer: water is read as "none"; with no
    # monthly rows at all a well-drained soil still leaves WET-FINE unchecked.
    assert fd2.ground_class(_firm())[1] == []
    assert fd2.ground_class(_firm(water_months_held=False)) == ("FIRM", ["WET-FINE"], False)
    assert fd2.ground_class(_firm(water_months_held=False, drainage="Poorly drained"))[:2] == ("WET-FINE", [])


def test_pan():
    assert fd2.ground_class(_firm(pan_cm=106.68))[2] is True
    assert fd2.ground_class(_firm(pan_cm=107.0))[2] is False
    assert fd2.ground_class(_firm(restrictions_known=False))[2] is None


def test_visitability_portland():
    got = fd2.visitability("or/multnomah/portland", "R5", 5.0, 1.0)
    assert got["visit_status"] == "applies" and got["visit_exempt"] is False
    assert got["visit_cite"].endswith("33.110.265.txt#L72")
    assert fd2.visitability("or/multnomah/portland", "R5", 20.0, 1.0)["visit_exempt"] is True
    assert fd2.visitability("or/multnomah/portland", "R2.5", 2.0, 3.01)["visit_exempt"] is True
    assert fd2.visitability("or/multnomah/portland", "R7", 2.0, 3.0)["visit_exempt"] is False
    missing = fd2.visitability("or/multnomah/portland", "R7", None, None)
    assert missing["visit_exempt"] is False and "missing" in missing["visit_exempt_why"]
    assert fd2.visitability("or/multnomah/portland", "RM1", 2.0, 0.0)["visit_status"] == "none_in_zone_chapter"
    assert fd2.visitability("or/clackamas/milwaukie", "R-5", 2.0, 0.0)["visit_status"] == "not_read"


def test_frost_register_and_state_figure():
    # Gresham's 18 in is practice; the state figure below 2,500 ft is 12 (note e).
    got = fd2.frost("gresham", 300.0, 18.0, "multnomah")
    assert got["frost_register_in"] == 18 and got["frost_state_in"] == 12 and got["frost_disagree"] is True
    assert got["frost_hub_in"] == 18.0  # the hub's printed figure is kept as read
    got = fd2.frost("portland", 200.0, 18.0, "multnomah")
    assert got["frost_register_in"] == 12 and got["frost_disagree"] is False
    assert fd2.frost("tualatin", 420.0, 12.0, "washington")["frost_above_stated_band"] is True
    assert fd2.frost("estacada", 400.0, 18.0, "clackamas")["frost_disagree"] is None
    assert fd2.frost("canby", 150.0, 18.0, "clackamas")["frost_state_in"] == 12


def test_frost_state_elevation_note():
    assert fd2.frost_state("multnomah", 2600.0)["frost_state_in"] == 18
    assert fd2.frost_state("clackamas", 2500.0)["frost_state_in"] == 18
    assert fd2.frost_state("clackamas", None)["frost_state_in"] == 18  # unread: deeper printed figure
    assert fd2.frost_state("washington", 3000.0)["frost_state_in"] == 12
    assert fd2.frost_state("lane", 100.0)["frost_state_in"] is None
