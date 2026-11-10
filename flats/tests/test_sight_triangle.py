"""Clear-vision areas at corners and drives (FOLLOWUPS 161).

The geometry (:mod:`flats.geom.sight_triangle`) on a square corner, a
chamfer and a rounded corner, with the curb at the lot line and out from
it; the registry (every eligible layer declares its rule, every quote is
held by the store); the screen's colours (GREEN clear of the larger area,
YELLOW between, RED inside the area surely kept, a note only for Portland's
driveway zone); and the bridge's two cuts (:func:`flats.ingest.quadfit.
sight_cut`)."""

from __future__ import annotations

import dataclasses
import math
from pathlib import Path
from types import SimpleNamespace

import pytest
from shapely.geometry import Polygon

from flats.geom import sight_triangle as sight
from flats.geom.edges import Edge, EdgeClass, LotEdges, Tier, bearing_deg
from flats.rules.model import SightRule

FRONT, SIDE, REAR, STREET = EdgeClass.front, EdgeClass.side, EdgeClass.rear, EdgeClass.street_side


def _lot(points: list[tuple[float, float]], classes: list[EdgeClass]) -> tuple[Polygon, LotEdges]:
    """A lot from its ring (counter-clockwise) and each edge's class."""
    edges = []
    n = len(points)
    for i in range(n):
        (x1, y1), (x2, y2) = points[i], points[(i + 1) % n]
        edges.append(Edge(x1, y1, x2, y2, math.hypot(x2 - x1, y2 - y1), bearing_deg(x1, y1, x2, y2), classes[i]))
    fronts = [e for e in edges if e.cls in (FRONT, STREET)]
    longest = sorted(fronts, key=lambda e: -e.length_ft)
    other = [
        e.bearing_deg for e in longest
        if abs(((e.bearing_deg - longest[0].bearing_deg + 90) % 180) - 90) > 45
    ]
    bearings = (longest[0].bearing_deg, *other[:1])
    return Polygon(points), LotEdges(
        tier=Tier.corner, edges=tuple(edges), front_bearings=bearings,
        frontage_ft=sum(e.length_ft for e in fronts), convexity=1.0,
    )


def square() -> tuple[Polygon, LotEdges]:
    """100 ft square, streets along its south (x axis) and west (y axis) lines."""
    return _lot([(0, 0), (100, 0), (100, 100), (0, 100)], [FRONT, SIDE, REAR, STREET])


def chamfered(cut: float = 10.0) -> tuple[Polygon, LotEdges]:
    return _lot(
        [(cut, 0), (100, 0), (100, 100), (0, 100), (0, cut)], [FRONT, SIDE, REAR, STREET, STREET]
    )


def rounded(r: float = 10.0, n: int = 4) -> tuple[Polygon, LotEdges]:
    """The corner a quarter circle of radius ``r`` about (r, r), in ``n`` chords."""
    arc = [
        (r - r * math.cos(math.radians(90 * i / n)), r - r * math.sin(math.radians(90 * i / n)))
        for i in range(n + 1)
    ]
    # (r, 0) east to the square's corners, back down the west line to (0, r),
    # and round the arc's chords to (r, 0).
    pts = [(r, 0), (100, 0), (100, 100), (0, 100), *arc[:n]]
    classes = [FRONT, SIDE, REAR, STREET] + [FRONT] * n
    return _lot(pts, classes)


def rule(**kw) -> SightRule:
    base = dict(status="read", legs_ft=(20.0,), basis="lot_line", note="x" * 40)
    return SightRule(**{**base, **kw})


# --- geometry -------------------------------------------------------------


@pytest.mark.parametrize("make", [square, chamfered, rounded])
def test_the_corner_is_where_the_street_lines_meet_extended(make) -> None:
    lot, edges = make()
    (c,) = sight.corners(lot, edges)
    x, y = sight.apex(c)
    assert abs(x) < 1e-6 and abs(y) < 1e-6


def test_a_square_corner_keeps_the_whole_triangle_and_a_curb_out_moves_it_off() -> None:
    lot, edges = square()
    (c,) = sight.corners(lot, edges)
    assert sight.triangle(c, 20, 20).intersection(lot).area == pytest.approx(200.0)
    # The curb 5 ft out on both streets: the apex at (-5, -5), the far side
    # x + y = 10 -- 50 sq ft left on the lot.
    assert sight.triangle(c, 20, 20, 5.0).intersection(lot).area == pytest.approx(50.0)


def test_a_rounded_or_chamfered_corner_keeps_less_than_the_square() -> None:
    for make in (chamfered, rounded):
        lot, edges = make()
        (c,) = sight.corners(lot, edges)
        kept = sight.triangle(c, 20, 20).intersection(lot).area
        assert 100.0 < kept < 200.0


def test_a_lot_line_rule_keeps_one_area_and_a_curb_rule_two() -> None:
    lot, edges = square()
    same = sight.corner_areas(lot, edges, rule())
    assert same.low.area == pytest.approx(same.high.area) == pytest.approx(200.0)
    curb = sight.corner_areas(lot, edges, rule(basis="curb"))
    assert curb.high.area == pytest.approx(200.0)
    # 20 ft legs from a curb 15 ft out never reach the lot.
    assert curb.low.is_empty or curb.low.area < 1e-6
    from flats.score.screen import SIGHT_CORNER_CURB, SIGHT_CORNER_UNSETTLED

    assert curb.reason == SIGHT_CORNER_CURB
    # Figures a street class picks between: the smaller is sure, the larger may be.
    options = sight.corner_areas(lot, edges, rule(legs_ft=(10.0, 25.0)))
    assert options.low.area == pytest.approx(50.0) and options.high.area == pytest.approx(312.5)
    assert options.reason == SIGHT_CORNER_UNSETTLED


def test_an_unsettled_rule_keeps_nothing_for_sure() -> None:
    from flats.score.screen import SIGHT_CORNER_UNSETTLED

    lot, edges = square()
    got = sight.corner_areas(lot, edges, rule(status="unsettled", legs_ft=(40.0,)))
    assert got.low.is_empty and got.high.area == pytest.approx(800.0)
    assert got.reason == SIGHT_CORNER_UNSETTLED


def test_no_rule_none_an_excepted_zone_and_a_lot_with_one_street_keep_nothing() -> None:
    lot, edges = square()
    assert sight.corner_areas(lot, edges, None) is None
    assert sight.corner_areas(lot, edges, rule(status="none")) is None
    assert sight.corner_areas(lot, edges, rule(except_zones=("CMU",)), "CMU") is None
    one, one_edges = _lot([(0, 0), (100, 0), (100, 100), (0, 100)], [FRONT, SIDE, REAR, SIDE])
    assert sight.corners(one, dataclasses.replace(one_edges, front_bearings=(90.0,))) == ()


def test_a_zone_figure_overrides_the_rule_figure() -> None:
    lot, edges = square()
    got = sight.corner_areas(lot, edges, rule(legs_ft=(30.0,), zone_legs_ft={"C-1": (15.0,)}), "C-1")
    assert got.high.area == pytest.approx(112.5)


def test_an_asymmetric_rule_is_drawn_both_ways_and_kept_where_both_agree() -> None:
    lot, edges = square()
    got = sight.corner_areas(lot, edges, rule(kind="asymmetric", legs_ft=(110.0, 15.0)))
    assert got.high.area > 1400.0
    assert got.low.area < got.high.area


def test_a_sight_distance_wedge_reaches_far_along_both_streets() -> None:
    lot, edges = square()
    w = rule(kind="wedge", legs_ft=(), sight_ft=(280.0,), eye_back_ft=14.5, basis="travel_lane")
    got = sight.corner_areas(lot, edges, w)
    assert got.high.area > 1000.0
    # The curb 15 ft out puts the eye at the lot line: nothing sure on the lot.
    assert got.low.area < 1.0


def test_the_drive_mouth_and_its_triangles() -> None:
    lot, edges = _lot([(0, 0), (100, 0), (100, 100), (0, 100)], [FRONT, SIDE, REAR, SIDE])
    edges = dataclasses.replace(edges, front_bearings=(90.0,))
    lane = Polygon([(40, 0), (52, 0), (52, 60), (40, 60)])
    m = sight.drive_mouth(lane, lot, edges)
    assert m.cx == pytest.approx(46.0) and m.cy == pytest.approx(0.0) and m.half_ft == pytest.approx(6.0)
    edge = sight.driveway_area(m, rule(kind="edge", legs_ft=(15.0,)))
    assert edge.intersection(lot).area == pytest.approx(2 * 112.5)
    building = Polygon([(55, 10), (90, 10), (90, 50), (55, 50)])
    assert sight.reaches(edge, building, lot)
    assert not sight.reaches(edge, Polygon([(55, 16), (90, 16), (90, 50), (55, 50)]), lot)
    # The apex at the front setback line (West Linn 42.050, the pod read as single-family).
    apex = sight.driveway_area(
        m, rule(kind="apex", legs_ft=(), base_ft=30.0, depth_from="front_setback"), front_setback_ft=20.0
    )
    assert apex.intersection(lot).area == pytest.approx(600.0)
    # A curb 5 ft out shrinks a curb-basis triangle on the lot.
    out = sight.driveway_area(m, rule(kind="edge", legs_ft=(15.0,), basis="curb"), 5.0)
    assert out.intersection(lot).area < edge.intersection(lot).area


# --- registry -------------------------------------------------------------


@pytest.fixture(scope="module")
def layers():
    from flats.encode.load import load_trusted

    return load_trusted(strict=False).rules.layers


def test_every_eligible_city_declares_its_clear_vision_rule(layers) -> None:
    eligible = {k for k, v in layers.items() if "/" in k and v.eligible}
    assert eligible and all(layers[k].clear_vision is not None for k in eligible), sorted(
        k for k in eligible if layers[k].clear_vision is None
    )
    assert layers["or/multnomah/portland"].clear_vision.corner.status == "none"
    drive = layers["or/multnomah/portland"].clear_vision.driveway
    assert drive.note_only and drive.exempt_at_lot_line
    assert layers["or/washington/durham"].clear_vision.corner.status == "none"
    unsettled = {
        k for k in eligible if layers[k].clear_vision.corner.status == "unsettled"
    }
    assert unsettled == {
        "or/clackamas/_unincorporated", "or/clackamas/gladstone",
        "or/clackamas/oregon-city", "or/multnomah/_unincorporated", "or/washington/hillsboro",
        "or/washington/king-city",
    }
    assert layers["or/multnomah/gresham"].clear_vision.corner.legs_ft == (40.0,)
    assert layers["or/washington/beaverton"].clear_vision.corner.legs_ft == (15.0,)
    # Steph 2026-11-10: Milwaukie takes the held AASHTO figures, read, the curb middle way.
    milwaukie = layers["or/clackamas/milwaukie"].clear_vision.corner
    assert milwaukie.status == "read" and milwaukie.sight_ft == (280.0, 450.0)
    assert milwaukie.eye_back_ft == 14.5 and milwaukie.basis == "travel_lane"
    assert layers["or/clackamas/west-linn"].clear_vision.driveway.depth_from == "front_setback"


def test_every_clear_vision_quote_is_held_by_the_store(layers) -> None:
    store = Path(__file__).resolve().parents[1] / "provenance" / "docs"

    def norm(t: str) -> str:
        return " ".join(t.replace("–", "-").replace("- ", "-").split())

    seen = 0
    for layer_id, layer in layers.items():
        cv = layer.clear_vision
        for r in (cv.corner, cv.driveway) if cv is not None else ():
            if r is None or r.quote is None:
                continue
            doc, _, rng = r.quote.partition("#L")
            a, _, b = rng.partition("-L")
            lines = (store / doc).read_text(encoding="utf-8").split("\n")
            assert norm(r.says) in norm(" ".join(lines[int(a) - 1 : int(b or a)])), layer_id
            seen += 1
    assert seen >= 20


def test_a_bad_clear_vision_block_is_a_load_problem() -> None:
    from flats.rules.loader import _parse_clear_vision

    problems: list[str] = []
    assert _parse_clear_vision({"corner": {"status": "read", "source": "b.txt#L1", "note": "x" * 40}}, where="w", problems=problems) is None
    assert problems and "legs_ft" in problems[0]
    problems = []
    _parse_clear_vision({"corner": {"status": "maybe"}}, where="w", problems=problems)
    assert problems
    ok = _parse_clear_vision(
        {"corner": {"status": "unsettled", "legs_ft": [20, 40], "note": "y" * 40}}, where="w", problems=[]
    )
    assert ok.corner.legs_ft == (20.0, 40.0) and ok.driveway is None


# --- the screen's colours ---------------------------------------------------


def _screen(**facts):
    from flats.score.screen import LotFacts, screen
    from flats.tests.test_screen import DESIGN, POLICY, fit, rules

    lot = LotFacts(lot_sqft=6000, frontage_ft=60, lot_width_ft=60, **facts)
    return screen(rules(), lot, DESIGN, fit(), policy=POLICY)


def test_a_fit_clear_of_the_larger_area_is_green() -> None:
    from flats.score.screen import Triage

    assert _screen().triage is Triage.green


@pytest.mark.parametrize("reason, code", [
    ("SIGHT_CORNER_CURB", "SIGHT-CORNER-CURB"),
    ("SIGHT_CORNER_UNSETTLED", "SIGHT-CORNER-UNSETTLED"),
])
def test_a_fit_only_inside_the_larger_corner_area_is_yellow_with_its_flag(reason, code) -> None:
    from flats.score.screen import Triage

    held = _screen(sight_corner_doubt=reason, sight_cite="TDC 18.930")
    assert held.triage is Triage.yellow and reason in held.reasons
    assert any(f.code == code for f in held.flags)


def test_a_drive_area_reaching_the_building_is_yellow_and_portlands_is_a_note() -> None:
    from flats.score.screen import SIGHT_DRIVEWAY, Triage

    held = _screen(sight_driveway_doubt=True)
    assert held.triage is Triage.yellow and SIGHT_DRIVEWAY in held.reasons
    assert any(f.code == "SIGHT-DRIVEWAY" for f in held.flags)
    noted = _screen(sight_driveway_note=True)
    assert noted.triage is Triage.green
    assert any(f.code == "SIGHT-DRIVEWAY-NOTE" for f in noted.flags)


# --- the bridge's cuts --------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class _Here:
    facts: object


def _cuts(r: SightRule, env_geom: Polygon):
    from flats.ingest.quadfit import Envelope, sight_cut
    from flats.score.screen import LotFacts

    lot_geom, edges = square()
    lot = SimpleNamespace(
        clear_vision=SimpleNamespace(corner=r, driveway=None), lot_geom=lot_geom, edges=edges, zone="R"
    )
    here = _Here(LotFacts(lot_sqft=10000))
    return sight_cut(here, lot, Envelope(env_geom, None, "flats"))


def test_the_bridge_cuts_green_yellow_and_red_corner_lots() -> None:
    # GREEN: the ground already clear of the larger area -- one cut, unchanged.
    clear = Polygon([(30, 30), (90, 30), (90, 90), (30, 90)])
    ((env, here),) = _cuts(rule(basis="curb"), clear)
    assert env.geom.area == pytest.approx(clear.area) and here.facts.sight_corner_doubt is None
    # YELLOW: the ground reaches into the curb-at-the-lot-line triangle only.
    near = Polygon([(5, 5), (90, 5), (90, 90), (5, 90)])
    (hi, _), (lo, doubt) = _cuts(rule(basis="curb"), near)
    assert hi.geom.area < lo.geom.area == pytest.approx(near.area)
    from flats.score.screen import SIGHT_CORNER_CURB

    assert doubt.facts.sight_corner_doubt == SIGHT_CORNER_CURB
    # RED: the area surely kept covers the whole of a small ground.
    tiny = Polygon([(1, 1), (14, 1), (1, 14)])
    ((env, _),) = _cuts(rule(legs_ft=(40.0,)), tiny)
    assert env.geom.is_empty
