"""The street's pavement width for the crane report (FOLLOWUPS 145, Steph
2026-11-15: A measured where data exists, B estimated off the right-of-way
and always labelled): :mod:`flats.geom.street_width`, and how
:mod:`flats.fit.set_access` labels a 45 t street set-up resting on an
estimate.

Every street and lot here is NOT REAL: a straight centreline on y = 0, the
lot's street lot line on y = 30 (its side of the street is +y).
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest
import shapely
import yaml
from shapely.geometry import LineString, box

from flats.fit import set_access as sa
from flats.fit.set_access import Site
from flats.geom import street_width as sw
from flats.geom.curbs import StreetEdges

#: NOT A REAL STREET: the centreline.
CENTRE = LineString([(-300, 0), (300, 0)])
#: NOT A REAL LOT: north of the street, its lot line 30 ft off the centreline.
OWN_LOT = box(-300, 30, 300, 130)
#: NOT A REAL LOT: across the street, its lot line 26 ft off (a 56 ft right-of-way).
FACING_LOT = box(-300, -130, 300, -26)
RULES = sw.EstimateRules({"default": 12.0, "or/clackamas/oregon-city": 11.0}, {"or/clackamas/oregon-city": 32.0})


def _read(widths: sw.StreetWidths, xs, layer: str | None = None, line: LineString = CENTRE):
    xs = np.asarray(xs, dtype=float)
    pts = np.stack([xs, np.full(len(xs), 30.0)], axis=-1)
    feet = np.stack([xs, np.zeros(len(xs))], axis=-1)
    return widths.read(pts, feet, [line] * len(xs), layer)


def _polys(*geoms) -> sw.StreetWidths:
    return sw.StreetWidths(polys=np.asarray(geoms, dtype=object),
                           poly_key=np.asarray(["roadway_hillsboro"] * len(geoms), dtype=object))


# --- A: measured -------------------------------------------------------------


def test_a_paved_shape_is_read_straight_across_at_the_frontage() -> None:
    curb, width, src = _read(_polys(box(-300, -18, 300, 18)), [0.0, 100.0])
    assert width == pytest.approx([36.0, 36.0])
    # The near curb: the lot line 30 ft out, the pavement's edge at 18 ft.
    assert curb == pytest.approx([12.0, 12.0])
    assert list(src) == ["measured:roadway_hillsboro"] * 2


def test_touching_shapes_join_and_a_one_sided_one_does_not_widen_the_street() -> None:
    # Two shapes meeting on the centreline are one street, 36 ft.
    _, width, _ = _read(_polys(box(-300, -18, 300, 0), box(-300, 0, 300, 18)), [0.0])
    assert width == pytest.approx([36.0])
    # A paved area stuck on one side (a parking court) puts the centreline
    # far off the middle: the cut is not read, never read as 68 ft.
    _, width, src = _read(_polys(box(-300, -18, 300, 18), box(-300, 18, 300, 50)), [0.0])
    assert np.isnan(width).all() and list(src) == [""]


def test_a_cut_into_a_cross_street_is_not_read_and_the_next_one_along_governs() -> None:
    shapes = _polys(box(-300, -18, 300, 18), box(-18, -300, 18, 300))
    _, width, _ = _read(shapes, [5.0, 25.0, 60.0])
    # At x = 5 every cut runs up the cross street and never closes: unread.
    assert np.isnan(width[0])
    # At x = 25 the cut 10 ft back is in the cross street, the other two read 36.
    assert width[1:] == pytest.approx([36.0, 36.0])


def test_edge_lines_count_only_where_both_sides_are_found() -> None:
    both = sw.StreetWidths(
        edges=np.asarray([LineString([(-300, -15), (300, -15)]), LineString([(-300, 15), (300, 15)])], dtype=object),
        edge_key=np.asarray(["pave_edge_oregon_city"] * 2, dtype=object),
    )
    curb, width, src = _read(both, [0.0])
    assert width == pytest.approx([30.0]) and curb == pytest.approx([15.0])
    assert list(src) == ["measured:pave_edge_oregon_city"]
    one = sw.StreetWidths(edges=np.asarray([LineString([(-300, 15), (300, 15)])], dtype=object),
                          edge_key=np.asarray(["pave_edge_oregon_city"], dtype=object))
    _, width, src = _read(one, [0.0])
    assert np.isnan(width).all() and list(src) == [""]


def test_a_width_attribute_is_read_beside_the_foot_and_names_its_dataset() -> None:
    line = [(CENTRE, 40.0)]
    widths = sw.StreetWidths(combined=StreetEdges.build((), line), by_key={"pave_width_washington": StreetEdges.build((), line)})
    curb, width, src = _read(widths, [0.0])
    # Half of 40 ft less the 3 ft centreline margin: the curb 13 ft from the lot line.
    assert width == pytest.approx([40.0]) and curb == pytest.approx([13.0])
    assert list(src) == ["measured:pave_width_washington"]


def test_the_narrowest_source_governs() -> None:
    line = [(CENTRE, 40.0)]
    widths = sw.StreetWidths(
        combined=StreetEdges.build((), line), by_key={"pave_width_washington": StreetEdges.build((), line)},
        polys=np.asarray([box(-300, -18, 300, 18)], dtype=object),
        poly_key=np.asarray(["roadway_hillsboro"], dtype=object),
    )
    _, width, src = _read(widths, [0.0])
    assert width == pytest.approx([36.0]) and list(src) == ["measured:roadway_hillsboro"]


# --- B: estimated ------------------------------------------------------------


def _fabric(*lots, rules: sw.EstimateRules = RULES) -> sw.StreetWidths:
    return sw.StreetWidths(lots=np.asarray(lots, dtype=object), rules=rules)


def test_the_estimate_is_the_right_of_way_less_the_allowance_each_side() -> None:
    curb, width, src = _read(_fabric(OWN_LOT, FACING_LOT), [0.0])
    # 56 ft between the lots, less 12 ft a side (the stated default, [est]).
    assert width == pytest.approx([32.0]) and list(src) == ["estimated:no street standard read, 12 ft a side"]
    assert sw.is_estimated(src).all()
    # The curb the allowance in from the lot's own line.
    assert curb == pytest.approx([12.0])


def test_the_place_sets_the_allowance_and_the_cap() -> None:
    # Oregon City: 11 ft a side (56 - 22 = 34) and no wider than its 32 ft local street.
    _, width, _ = _read(_fabric(OWN_LOT, FACING_LOT), [0.0], layer="or/clackamas/oregon-city")
    assert width == pytest.approx([32.0])
    wide = _fabric(OWN_LOT, box(-300, -130, 300, -40))
    _, width, _ = _read(wide, [0.0], layer="or/clackamas/oregon-city")
    assert width == pytest.approx([32.0])
    _, width, _ = _read(wide, [0.0], layer="or/washington/hillsboro")
    assert width == pytest.approx([70.0 - 24.0])


def test_no_estimate_without_a_facing_lot_on_a_curve_or_where_no_sidewalk_fits() -> None:
    _, width, src = _read(_fabric(OWN_LOT), [0.0])
    assert np.isnan(width).all() and list(src) == [""]
    bend = LineString([(-300, 0), (0, 0), (100, 100)])
    _, width, _ = _read(_fabric(OWN_LOT, FACING_LOT), [0.0], line=bend)
    assert np.isnan(width).all()
    lane = _fabric(box(-300, 15, 300, 130), box(-300, -130, 300, -15))
    pts = np.array([[0.0, 15.0]])
    _, width, _ = lane.read(pts, np.array([[0.0, 0.0]]), [CENTRE])
    assert np.isnan(width).all()


def test_a_measured_width_is_never_replaced_by_an_estimate() -> None:
    widths = sw.StreetWidths(polys=np.asarray([box(-300, -14, 300, 14)], dtype=object),
                             poly_key=np.asarray(["roadway_hillsboro"], dtype=object),
                             lots=np.asarray([OWN_LOT, FACING_LOT], dtype=object), rules=RULES)
    _, width, src = _read(widths, [0.0])
    assert width == pytest.approx([28.0]) and list(src) == ["measured:roadway_hillsboro"]


def test_the_reader_finds_the_foot_and_stops_past_the_reach() -> None:
    read = sw.reader(_fabric(OWN_LOT, FACING_LOT), np.asarray([CENTRE], dtype=object), 50.0)
    curb, width, src = read(np.array([[0.0, 30.0], [0.0, 80.0]]))
    assert width[0] == pytest.approx(32.0) and src[0].startswith(sw.ESTIMATED + ":")
    assert np.isnan(width[1]) and src[1] == ""


def test_the_shipped_register_cites_every_figure() -> None:
    rules = sw.load_rules()
    assert rules.allowance(None) == 12.0 and rules.allowance("or/clackamas/oregon-city") == 11.0
    assert rules.cap("or/clackamas/oregon-city") == 32.0 and rules.cap("or/multnomah/portland") is None
    assert rules.allowance_cite("or/multnomah/portland").startswith("[est]")
    with pytest.raises(ValueError, match="no stored quote"):
        sw.rules_from({"street_width": {"allowance_ft": {"default": {"value": 9, "cite": "a guess"}}}})


# --- the labelling in the report ---------------------------------------------

FULL_LOT = box(0, 0, 120, 40)
FULL_POD = box(20, 7.5, 100, 32.5)
FULL_STREET = ((0.0, 0.0, 120.0, 0.0),)


def _street(source: str, width: float = 36.0, curb: float = 2.0):
    """NOT A REAL STREET: one curb, one width, one source everywhere."""

    def read(pts: np.ndarray):
        n = len(np.asarray(pts).reshape(-1, 2))
        return np.full(n, curb), np.full(n, width), np.full(n, source, dtype=object)

    return read


def _level(_poly) -> float:
    return 0.5


@pytest.fixture(scope="module")
def rules() -> sa.Rules:
    return sa.load_rules()


def _street_attempt(rules: sa.Rules, source: str) -> tuple[sa.Report, sa.Attempt]:
    rep = sa.report(Site(FULL_LOT, FULL_POD, FULL_STREET, _street(source)), rules, grade_of=_level)
    return rep, next(a for a in rep.attempts if a.step == "45t_street")


def test_a_street_set_up_on_an_estimate_says_so(rules: sa.Rules) -> None:
    # Here the street set-up is tried (the pod fills the lot) and fails on
    # reach; its plan still carries where the width came from.
    rep, est = _street_attempt(rules, sa.WIDTH_ESTIMATED)
    assert est.plan.width_source == sa.WIDTH_ESTIMATED and rep.row()["45t_street_width"] == "estimated"
    passed = dataclasses.replace(est, status=sa.PASS)
    assert sa._result_of(passed) == sa.T45_STREET_EST == "45 t in the street (width estimated)"
    rep, real = _street_attempt(rules, "measured:roadway_hillsboro")
    assert real.plan.width_source == rep.row()["45t_street_width"] == "measured:roadway_hillsboro"
    assert sa._result_of(dataclasses.replace(real, status=sa.PASS)) == sa.T45_STREET


def test_an_estimate_too_narrow_fails_and_says_it_is_estimated(rules: sa.Rules) -> None:
    rep = sa.report(Site(FULL_LOT, FULL_POD, FULL_STREET, _street(sa.WIDTH_ESTIMATED, width=24.0)), rules,
                    grade_of=_level)
    assert rep.result == sa.NOT_VIABLE
    assert any("24 ft wide at most (estimated off the right-of-way)" in w for w in rep.why)


def test_estimates_never_place_the_on_site_crane_s_curb_truck(rules: sa.Rules) -> None:
    site = Site(FULL_LOT, FULL_POD, FULL_STREET, _street(sa.WIDTH_ESTIMATED))
    spots, measured = sa.curb_truck_spots(site, rules)
    assert not len(spots) and not measured
    spots, measured = sa.curb_truck_spots(site, rules, estimates=True)
    assert len(spots) and measured and set(spots.place) == {sa.CURB_EST}


def test_a_frontage_past_every_centreline_is_no_curb_left_unmeasured(rules: sa.Rules) -> None:
    """The lookup miss (scout 2026-11-15): a street lot line's end more than
    the reach from any centreline counted as an unmeasured curb, so a lot
    whose curb was read everywhere in front of the street stayed
    undecided."""
    gap = shapely.STRtree([LineString([(0, -20), (60, -20)])])

    def centre(pts: np.ndarray) -> np.ndarray:
        g = shapely.points(np.asarray(pts).reshape(-1, 2))
        d = shapely.distance(g, gap.geometries[0])
        return np.where(d <= 50.0, d, np.nan)

    def street(pts: np.ndarray):
        c = centre(pts)
        return c - 10.0, np.where(np.isfinite(c), 36.0, np.nan)

    site = Site(FULL_LOT, FULL_POD, FULL_STREET, street, street_centre=centre)
    spots, measured = sa.curb_truck_spots(site, rules)
    assert measured and len(spots)
    blind = Site(FULL_LOT, FULL_POD, FULL_STREET, street)
    assert not sa.curb_truck_spots(blind, rules)[1]


# --- each place's street standard (Steph 2026-11-15: "Each city's standard")


SHIPPED = sw.load_rules()


def _row(layer: str | None, *gaps: float):
    return SHIPPED.section_pave(layer, np.asarray(gaps, dtype=float))


def test_each_place_reads_its_own_standard_section() -> None:
    # Gresham DC Table A5.501: Local Queuing 58 / 26, Local Transitional 64 / 32.
    pave, name = _row("or/multnomah/gresham", 58.0, 64.4)
    assert list(pave) == [26.0, 32.0]
    assert name[0] == "Gresham DC A5.501, Local Queuing (58 ft ROW, 26 ft)"
    # Durham DC 3.9.1 (stored code): local street 40 ft, 26 ft paved.
    assert list(_row("or/washington/durham", 40.0)[0]) == [26.0]
    # Estacada EMC 16.116.030: the neighborhood local 40 / 28.
    assert list(_row("or/clackamas/estacada", 39.2)[0]) == [28.0]
    # Multnomah County prints metres: 15.2-17.1 m right-of-way, 9.0 m paved at least.
    pave, _ = _row("or/multnomah/_unincorporated", 50.0)
    assert pave[0] == pytest.approx(9.0 / 0.3048)
    # A right-of-way no section prints takes nothing here.
    assert np.isnan(_row("or/multnomah/gresham", 50.0)[0]).all()


def test_where_several_sections_match_the_narrowest_pavement_is_taken() -> None:
    # Washington County at 50 ft: L-1 24 (interim), NR-5 28, NR-6 32.
    pave, name = _row("or/washington/_unincorporated", 50.0)
    assert pave[0] == 24.0 and "L-1" in name[0]
    # Canby's ranges overlap: Standard Local 50-62 / 34 and Low-Volume 40-60 / 28.
    assert list(_row("or/clackamas/canby", 55.0, 61.5)[0]) == [28.0, 34.0]
    # Wilsonville prints a pavement range (28-32): the narrow end; the LID
    # local (41-52 / 20-28) is narrower still where it overlaps.
    assert list(_row("or/clackamas/wilsonville", 54.0, 50.0)[0]) == [28.0, 20.0]
    # Happy Valley's 53 / 32 and 55 / 34 both lie within a foot of 54.
    assert list(_row("or/clackamas/happy-valley", 54.0)[0]) == [32.0]


def test_the_allowance_is_the_place_s_own_or_derived_or_the_default() -> None:
    # Printed pieces: Cornelius 6 ft parkway + 5 ft walk; Canby 6 ft walk + 0-8 ft buffer (wider end).
    assert SHIPPED.allowance("or/washington/cornelius") == 11.0
    assert SHIPPED.allowance("or/clackamas/canby") == 14.0
    # Derived from tied sections, the widest strip a side (Gresham 58 / 26 and 64 / 32);
    # the plan districts' widened right-of-way does not count.
    assert SHIPPED.allowance("or/multnomah/gresham") == 16.0
    assert SHIPPED.cap("or/multnomah/gresham") == 32.0
    # No standard read (Portland's manual is a draft): the stated default.
    assert SHIPPED.allowance("or/multnomah/portland") == 12.0
    assert SHIPPED.allowance_basis("or/multnomah/portland") == "no street standard read, 12 ft a side [est]"
    assert SHIPPED.allowance_basis("or/washington/cornelius") == "Cornelius PWS 5.04(a) Local Street, 11 ft a side"


def test_the_unmatched_strip_switch_reads_the_widest_or_the_local_street_strip() -> None:
    # Shipped: the widest strip of every tied section (Steph's answer pending).
    assert SHIPPED.allowance("or/washington/_unincorporated") == 16.0  # NR-1 60 / 28
    assert SHIPPED.allowance("or/washington/beaverton") == 13.0  # NR3 50 / 24
    raw = yaml.safe_load(sw.CONFIG.read_text(encoding="utf-8"))
    raw["street_width"]["unmatched_strip"] = "local_street_strip"
    local = sw.rules_from(raw)
    # Ordinary local streets only: Washington County L-1 50 / 24, Beaverton L1-L3,
    # Hillsboro's residential rows, Sherwood's standard residential.
    assert local.allowance("or/washington/_unincorporated") == 13.0
    assert local.allowance("or/washington/beaverton") == 12.0
    assert local.allowance("or/washington/hillsboro") == 11.0
    assert local.allowance("or/washington/sherwood") == 12.0
    # A place with no neighbourhood route is the same either way; printed pieces never move.
    assert local.allowance("or/multnomah/gresham") == SHIPPED.allowance("or/multnomah/gresham") == 16.0
    assert local.allowance("or/washington/cornelius") == 11.0
    assert "local-street sections" in local.allowance_cite("or/washington/_unincorporated")
    raw["street_width"]["unmatched_strip"] = "narrowest"
    with pytest.raises(ValueError, match="unmatched_strip"):
        sw.rules_from(raw)


def test_the_estimate_names_the_section_and_centres_it() -> None:
    # A 58 ft right-of-way in Gresham: the 26 ft Local Queuing pavement, its
    # curb (58 - 26) / 2 = 16 ft in from the lot's line.
    lots = _fabric(OWN_LOT, box(-300, -130, 300, -28), rules=SHIPPED)
    curb, width, src = _read(lots, [0.0], layer="or/multnomah/gresham")
    assert width == pytest.approx([26.0]) and curb == pytest.approx([16.0])
    assert src[0] == "estimated:Gresham DC A5.501, Local Queuing (58 ft ROW, 26 ft)"
    # A 56 ft right-of-way there matches no section: 16 ft a side.
    curb, width, src = _read(_fabric(OWN_LOT, FACING_LOT, rules=SHIPPED), [0.0], layer="or/multnomah/gresham")
    assert width == pytest.approx([24.0]) and curb == pytest.approx([16.0])
    assert src[0] == "estimated:Gresham DC A5.501, 16 ft a side"
    # The default where no standard is read.
    _, width, src = _read(_fabric(OWN_LOT, FACING_LOT, rules=SHIPPED), [0.0], layer="or/multnomah/portland")
    assert width == pytest.approx([32.0]) and src[0] == "estimated:no street standard read, 12 ft a side [est]"


def test_a_section_needs_a_stored_quote_and_a_figure() -> None:
    base = {"allowance_ft": {"default": {"value": 12, "cite": "[est] x"}}}
    with pytest.raises(ValueError, match="no stored quote"):
        sw.rules_from({"street_width": {**base, "sections": {"x": {"standard": "S", "rows": [
            {"name": "a", "row": 50, "pave": 28}]}}}})
    with pytest.raises(ValueError, match="not a figure"):
        sw.rules_from({"street_width": {**base, "sections": {"x": {"standard": "S", "rows": [
            {"name": "a", "row": "fifty", "pave": 28, "quote": "q"}]}}}})


def test_a_failure_on_an_estimate_names_its_standard(rules: sa.Rules) -> None:
    label = "estimated:Gresham DC A5.501, 16 ft a side"
    rep = sa.report(Site(FULL_LOT, FULL_POD, FULL_STREET, _street(label, width=24.0)), rules, grade_of=_level)
    assert any("24 ft wide at most (estimated off the right-of-way: Gresham DC A5.501, 16 ft a side)" in w
               for w in rep.why)
    rep, est = _street_attempt(rules, label)
    assert est.plan.width_source == label and rep.row()["45t_street_width"] == label
    assert sa._result_of(dataclasses.replace(est, status=sa.PASS)) == sa.T45_STREET_EST
