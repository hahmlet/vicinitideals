"""A drive lane's gap to a lot line, against Beaverton S12's 3 or 6 ft
(FOLLOWUPS 201 add-on G).

fg4-rate-B lot 41, 1S112CC06300 (Beaverton RMC, interior, about 99.9 ft
wide): the lane was drawn about 1 ft off the east line, GREEN on run 128.
BDC Table 60.05.60.2 S12: "driveways may be located as close as 3 or 6 feet
from property lines depending on sidewalk type classified by the EDM"
(``beaverton/60.05/60.05.60.txt#L397-L399``); the sidewalk type is not held.
The contracts:

* a plan that clears 6 ft, as drawn or slid away from the line as far as its
  building's side setback and its court allow, is untouched;
* one that clears only 3 ft is YELLOW with ACCESS-DRIVEWAY-SIDEWALK-TYPE;
* one that misses 3 ft too, with the slide measured, is RED (DRIVEWAY_LOT_LINE);
  with no slide measured it is YELLOW, never RED;
* outside RMA / RMB / RMC / CM-RM in Beaverton nothing is asked.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

shapely = pytest.importorskip("shapely")

from flats.geom import driveway_lot_line as dll  # noqa: E402
from flats.geom.edges import Edge, EdgeClass, LotEdges, Tier, bearing_deg  # noqa: E402
from flats.ingest.quadfit import DRIVEWAY_LOT_LINE_FLAG, DRIVEWAY_SIDEWALK, driveway_lot_line_checked  # noqa: E402
from flats.score.screen import (  # noqa: E402
    CLOSER_LOOK_DRIVEWAY_LOT_LINE,
    CLOSER_LOOK_DRIVEWAY_SIDEWALK,
    DRIVEWAY_LOT_LINE,
    Triage,
)
from flats.tests.test_plan_on_lot import _green  # noqa: E402
from flats.tests.test_quadfit_bridge import (  # noqa: E402
    corpus,  # noqa: F401  (fixture)
    policies,  # noqa: F401  (fixture)
)

pytestmark = pytest.mark.unit

STORE = Path(__file__).resolve().parents[1] / "provenance" / "docs"


def _edge(x1, y1, x2, y2, cls):
    length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
    return Edge(x1, y1, x2, y2, length, bearing_deg(x1, y1, x2, y2), cls)


def _lot(*, west: bool = True) -> LotEdges:
    """100 x 150, street along the south; ``west`` False drops the west line
    (nothing opposite the east line to slide toward)."""
    edges = [
        _edge(0, 0, 100, 0, EdgeClass.front),
        _edge(100, 0, 100, 150, EdgeClass.side),
        _edge(100, 150, 0, 150, EdgeClass.rear),
    ]
    if west:
        edges.append(_edge(0, 150, 0, 0, EdgeClass.side))
    return LotEdges(Tier.clean, tuple(edges), (90.0,), 100.0, 1.0)


def _plan(building_x0: float, lane_x0: float):
    building = shapely.box(building_x0, 20, building_x0 + 80, 45)
    lane = shapely.box(lane_x0, 0, lane_x0 + 9, 60)
    court = shapely.box(building_x0, 60, lane_x0 + 9, 120)
    return building, lane, court


def test_the_figures_are_the_code_s_printed_ones() -> None:
    place = dll.place_for("or/washington/beaverton", "RMC")
    assert place is not None and place.figures_ft == (3.0, 6.0)
    path, lines = place.quote.split("#L")
    text = (STORE / path).read_text(encoding="utf-8").splitlines()
    first, last = (int(n) for n in lines.split("-L"))
    said = " ".join(text[first - 1 : last])
    assert "as close as 3 or 6 feet from property lines depending on sidewalk type" in said
    assert dll.place_for("or/washington/beaverton", "R5") is None
    assert dll.place_for("or/washington/hillsboro", "RMC") is None


def test_the_gap_and_the_slide_are_measured() -> None:
    building, lane, court = _plan(10, 91)  # lane 0 ft off east, room 5 ft west
    gap = dll.measure(_lot(), lane, building, court, building_clear_ft=5, court_clear_ft=5)
    assert gap is not None
    assert gap.drawn_ft == pytest.approx(0.0)
    assert gap.reach_ft == pytest.approx(5.0)
    # Nothing opposite: the slide is not measured.
    gap = dll.measure(_lot(west=False), lane, building, court, building_clear_ft=5, court_clear_ft=5)
    assert gap is not None and gap.reach_ft is None


def _beaverton(
    corpus,  # noqa: F811
    policies,  # noqa: F811
    building_x0: float,
    lane_x0: float,
    *,
    west: bool = True,
    zone="RMC",
    layer="or/washington/beaverton",
    edges: LotEdges | None = None,
):
    _, s = _green(corpus, policies)
    some = next(iter(s.rules.values.values()))
    side = dataclasses.replace(some, name="setback_side_ft", value=5.0)
    rules = dataclasses.replace(s.rules, values={**s.rules.values, "setback_side_ft": side})
    lot = dataclasses.replace(s.lot, layer_id=layer, zone=zone, edges=edges or _lot(west=west))
    building, lane, court = _plan(building_x0, lane_x0)

    def ring(g):
        return [list(p) for p in g.exterior.coords]

    drawing = {**(s.drawing or {}), "fits": True, "building": ring(building), "lane": ring(lane), "court": ring(court)}
    return dataclasses.replace(s, lot=lot, rules=rules, drawing=drawing)


def flags(s):
    return [f.code for f in s.signed.flags if f.code == DRIVEWAY_SIDEWALK]


def test_a_plan_that_slides_to_six_feet_is_untouched(corpus, policies) -> None:  # noqa: F811
    s = _beaverton(corpus, policies, 10, 90)  # 1 ft drawn, 5 ft room: 6
    assert driveway_lot_line_checked(s) is s


def test_a_plan_clear_only_at_three_feet_is_yellow(corpus, policies) -> None:  # noqa: F811
    # The rate-B lot: fits by 1.9 ft at 3, misses by 1.1 ft at 6.
    s = _beaverton(corpus, policies, 8.9, 90)  # 1 ft drawn, 3.9 ft room: 4.9
    got = driveway_lot_line_checked(s)
    assert flags(got) == [DRIVEWAY_SIDEWALK]
    assert got.signed.triage is Triage.yellow and got.screening.triage is Triage.yellow
    assert CLOSER_LOOK_DRIVEWAY_SIDEWALK in got.signed.reasons


def test_a_plan_short_of_three_feet_fails(corpus, policies) -> None:  # noqa: F811
    s = _beaverton(corpus, policies, 5, 90)  # 1 ft drawn, no room
    got = driveway_lot_line_checked(s)
    assert got.signed.triage is Triage.red
    assert DRIVEWAY_LOT_LINE in got.signed.reasons
    assert [b.check for b in got.signed.binds if b.check == DRIVEWAY_LOT_LINE] == [DRIVEWAY_LOT_LINE]


def test_with_no_slide_measured_it_is_yellow_not_red(corpus, policies) -> None:  # noqa: F811
    s = _beaverton(corpus, policies, 5, 90, west=False)
    got = driveway_lot_line_checked(s)
    assert got.signed.triage is Triage.yellow
    assert flags(got) == [DRIVEWAY_SIDEWALK]


def test_other_zones_are_not_asked(corpus, policies) -> None:  # noqa: F811
    s = _beaverton(corpus, policies, 5, 90, zone="R5")
    assert driveway_lot_line_checked(s) is s


# --- Gladstone (FOLLOWUPS 205): PWDS 5.0070(D)(5) plus Drawings 503A/503B ---


def test_gladstone_s_figures_are_the_cut_s_5_ft_plus_its_printed_wings() -> None:
    place = dll.place_for("or/clackamas/gladstone", "R-7.2")
    assert place is not None and dll.place_for("or/clackamas/gladstone", "C-2") is place  # every zone
    assert place.figures_ft == (8.0, 11.0)  # 5 + 3' (503A), 5 + 6' (503B)
    assert place.lines == frozenset({"side"}) and place.miss == "yellow"
    path, line = place.quote.split("#L")
    said = (STORE / path).read_text(encoding="utf-8").splitlines()[int(line) - 1]
    assert "Curb cuts shall be a minimum of 5 ft. from the property line, unless a shared driveway is installed" in said
    body = __import__("yaml").safe_load(dll.CONFIG.read_text(encoding="utf-8"))["places"]["or/clackamas/gladstone"]
    assert [(w["value"], w["drawing"], w["page"]) for w in body["wings_ft"]] == [(3, "503A", 54), (6, "503B", 55)]
    text = (STORE / path).read_text(encoding="utf-8").splitlines()
    assert "top of approach wing" in " ".join(text[441:444])  # 5.0070(A), L442-L444
    assert "503A, 503B, 504A and 504B" in text[452]  # 5.0070(C), L453
    # Beaverton is untouched by the new options.
    beav = dll.place_for("or/washington/beaverton", "RMC")
    assert beav is not None and beav.lines == dll.LINES and beav.miss == "red"


def _gladstone(corpus, policies, building_x0, lane_x0, **kw):  # noqa: F811
    return _beaverton(corpus, policies, building_x0, lane_x0, zone="R-7.2", layer="or/clackamas/gladstone", **kw)


def test_gladstone_clear_at_eleven_feet_is_untouched(corpus, policies) -> None:  # noqa: F811
    s = _gladstone(corpus, policies, 10, 85)  # 6 ft drawn, 5 ft room: 11
    assert driveway_lot_line_checked(s) is s


def test_gladstone_clear_only_at_eight_feet_is_yellow_on_the_sidewalk_type(corpus, policies) -> None:  # noqa: F811
    s = _gladstone(corpus, policies, 8, 85)  # 6 ft drawn, 3 ft room: 9
    got = driveway_lot_line_checked(s)
    assert flags(got) == [DRIVEWAY_SIDEWALK]
    assert got.signed.triage is Triage.yellow and got.screening.triage is Triage.yellow
    assert CLOSER_LOOK_DRIVEWAY_SIDEWALK in got.signed.reasons


def test_gladstone_short_of_eight_feet_is_yellow_never_red(corpus, policies) -> None:  # noqa: F811
    s = _gladstone(corpus, policies, 5, 90)  # 1 ft drawn, no room: the slide is measured
    got = driveway_lot_line_checked(s)
    assert got.signed.triage is Triage.yellow and got.screening.triage is Triage.yellow
    assert CLOSER_LOOK_DRIVEWAY_LOT_LINE in got.signed.reasons
    assert [f.code for f in got.signed.flags if f.code == DRIVEWAY_LOT_LINE_FLAG] == [DRIVEWAY_LOT_LINE_FLAG]
    assert DRIVEWAY_LOT_LINE not in got.signed.reasons
    assert not [b for b in got.signed.binds if b.check == DRIVEWAY_LOT_LINE]


def test_gladstone_s_miss_never_reads_the_fit_s_tolerance(corpus, policies) -> None:  # noqa: F811
    # rel11: the half-foot tolerance (bvt-drive-side) only ever spares a RED.
    # Gladstone's miss is YELLOW on its own flag whatever the shortfall, so a
    # plan 0.4 ft short of 8 answers the same with the policy as without it.
    policy = policies[0]
    s = _gladstone(corpus, policies, 11.6, 90)  # 1 ft drawn, 6.6 ft room: 7.6
    got = driveway_lot_line_checked(s, policy)
    assert got.signed.triage is Triage.yellow and got.screening.triage is Triage.yellow
    held = [f for f in got.signed.flags if f.code == DRIVEWAY_LOT_LINE_FLAG]
    assert len(held) == 1 and "tolerance" not in held[0].source
    assert flags(got) == [] and DRIVEWAY_LOT_LINE not in got.signed.reasons
    assert got.signed == driveway_lot_line_checked(s).signed


def test_gladstone_measures_side_lines_only(corpus, policies) -> None:  # noqa: F811
    # The rear line a foot off the lane is no curb cut's neighbour: with the
    # side lines far, the plan stands.
    edges = LotEdges(
        Tier.clean,
        (
            _edge(0, 0, 100, 0, EdgeClass.front),
            _edge(100, 0, 100, 61, EdgeClass.side),
            _edge(100, 61, 0, 61, EdgeClass.rear),
            _edge(0, 61, 0, 0, EdgeClass.side),
        ),
        (90.0,),
        100.0,
        1.0,
    )
    s = _gladstone(corpus, policies, 5, 40, edges=edges)  # lane 40-49: 40+ ft off each side
    assert driveway_lot_line_checked(s) is s


# --- bvt-drive-side: other placements, the slide's stop, the reason shown ------
#
# rel10 move read (rel10-full-moves.findings.md, findings 1 and 2): 31 Beaverton
# greens and 52 yellows went RED on the one drawn plan, slid; no other placement
# was tried. The plan is now stood elsewhere where another spot keeps the gap
# (``driveway_lot_line_placed``), measured on that drawing, never on a slide.


def test_the_slide_stops_at_the_first_stretch_of_the_far_side() -> None:
    # 99 ft wide for 60 ft, then 115 ft: the building at the front meets the
    # 99 ft stretch first. Slid toward the farthest line it was credited room
    # it does not have (a GREEN the plan could not stand on).
    edges = LotEdges(
        Tier.clean,
        (
            _edge(0, 0, 99, 0, EdgeClass.front),
            _edge(99, 0, 99, 60, EdgeClass.side),
            _edge(99, 60, 115, 60, EdgeClass.side),
            _edge(115, 60, 115, 260, EdgeClass.side),
            _edge(115, 260, 0, 260, EdgeClass.rear),
            _edge(0, 260, 0, 0, EdgeClass.side),
        ),
        (90.0,),
        99.0,
        1.0,
    )
    building = shapely.box(12, 10, 92, 35)
    lane = shapely.box(0, 10, 12, 35)
    court = shapely.box(0, 35, 92, 88)
    gap = dll.measure(edges, lane, building, court, building_clear_ft=5, court_clear_ft=5)
    assert gap is not None
    assert gap.drawn_ft == pytest.approx(0.0)
    assert gap.reach_ft == pytest.approx(2.0)  # 99 - 92 - 5, not 115 - 92 - 5


def _screened(corpus, pts, labels, zone: str = "RMC"):  # noqa: F811
    import json

    from flats.designs.model import load_catalog
    from flats.ingest.quadfit import lot_from_row, screen_lot
    from flats.score import relief, slack
    from flats.tests.test_fire import X0, Y0, bridge_row

    pts = [(X0 + x, Y0 + y) for x, y in pts]
    poly = shapely.Polygon(pts)
    whole = shapely.to_wkb(poly)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    row = bridge_row(
        TLID="1S199AA99999", jurisdiction="beaverton", zone=zone, area_sqft=poly.area,
        lot_depth_ft=max(ys) - min(ys), frontage_ft=max(xs) - min(xs),
        lot_width_ft=max(xs) - min(xs),
        edges_json=json.dumps([[*pts[i], *pts[(i + 1) % len(pts)], labels[i]] for i in range(len(pts))]),
        wkb=whole, lot_wkb=whole,
        # Mid-block on a local street; these tests are not about spacing.
        driveway_spacing="clear",
    )
    lot = lot_from_row(row, corpus.layers)
    (s,) = screen_lot(
        lot, load_catalog().active(), rules=corpus, policy=slack.load_policy(),
        relief=relief.load_policy(), step_deg=30.0,
    )
    return s


def _drawn_gap(s) -> float:
    from flats.ingest.quadfit import _driveway_measured

    got = _driveway_measured(s, s.drawing)
    assert got is not None
    return got[1].drawn_ft


def test_a_plan_with_another_spot_that_keeps_six_feet_stands_there(corpus) -> None:  # noqa: F811
    # The front 60 ft is 99 ft wide: there the 80 ft pod, its 12 ft lane and a
    # 5 ft side yard leave 2 ft for the drive (RED on the drawn plan, slid).
    # Behind, 115 ft: the fit's other placements are tried, and the plan
    # stands where its DRAWN lane is 6 ft off the line, every other check kept.
    s = _screened(
        corpus,
        [(0, 0), (99, 0), (99, 60), (115, 60), (115, 260), (0, 260)],
        ["F", "S", "S", "S", "R", "S"],
    )
    assert s.fit.fits
    assert s.signed.colour.value != "red" and s.screening.colour.value != "red"
    assert DRIVEWAY_LOT_LINE not in s.signed.reasons
    assert flags(s) == []
    assert _drawn_gap(s) + 0.1 >= 6.0


def test_a_lot_too_narrow_for_the_drive_either_way_stays_red(corpus) -> None:  # noqa: F811
    # 99 ft square to the street the whole way: 5 + 80 + 12 leaves 2 ft for the
    # drive on whichever flank it runs; no placement keeps 3.
    s = _screened(corpus, [(0, 0), (99, 0), (99, 220), (0, 220)], ["F", "S", "R", "S"])
    assert s.signed.colour.value == "red"
    assert DRIVEWAY_LOT_LINE in s.signed.reasons
    assert [b.check for b in s.signed.binds if b.check == DRIVEWAY_LOT_LINE] == [DRIVEWAY_LOT_LINE]


def test_a_sideways_plan_lost_on_its_drive_is_shown_red_on_the_drive(corpus) -> None:  # noqa: F811
    # 43 ft wide (1S115CD10900 / 10901, 1S128AB11200): the pod misses facing
    # the street; turned sideways it fits, but its drive keeps about 1 ft. RED
    # either way -- the reason shown is the drive, not the street-facing fit.
    s = _screened(corpus, [(0, 0), (43, 0), (43, 220), (0, 220)], ["F", "S", "R", "S"], zone="RMA")
    assert s.signed.colour.value == "red"
    assert s.fit.fits
    assert DRIVEWAY_LOT_LINE in s.signed.reasons


def test_a_miss_of_three_feet_inside_the_fit_s_half_foot_is_yellow(corpus, policies) -> None:  # noqa: F811
    # 2.6 ft at most against 3 (a 100 ft lot the plan needs exactly 100 ft of,
    # drawn on the fit's raster): inside slack.yaml's fit_ft tolerance, REVIEW
    # not RED; never a pass (the 6 ft figure still holds it out of GREEN).
    policy = policies[0]
    assert policy.tolerance_for("fit_ft", "or/washington/beaverton") == pytest.approx(0.5)
    s = _beaverton(corpus, policies, 6.6, 90)  # 1 ft drawn, 1.6 ft room: 2.6
    got = driveway_lot_line_checked(s, policy)
    assert got.signed.triage is Triage.yellow and got.screening.triage is Triage.yellow
    assert flags(got) == [DRIVEWAY_SIDEWALK]
    assert DRIVEWAY_LOT_LINE not in got.signed.reasons
    # Without the policy (the check alone), and past the half foot, still RED.
    assert driveway_lot_line_checked(s).signed.triage is Triage.red
    s = _beaverton(corpus, policies, 6.4, 90)  # 2.4 ft: short by 0.6
    assert driveway_lot_line_checked(s, policy).signed.triage is Triage.red
