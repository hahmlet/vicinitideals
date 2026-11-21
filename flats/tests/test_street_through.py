"""A street drawn through the lot near the plan holds a GREEN (rel11 move read
G2), and the records a bound names Fix 5 and Fix C moves by (G1).

Clackamas unincorporated 21E11AB01100 (R7) went GREEN on rel11 with WALTER
(RLIS TYPE 1500) running 160 ft through the lot and the drawn court 25.8 ft
from it. The contracts:

* a GREEN whose drawn building, lane or court comes within 50 ft of a street
  centreline running through the lot is YELLOW with
  MEASURE-STREET-THROUGH-LOT, naming the street;
* the frontage street is never counted: its centreline outside the lot, or
  along the front line of a lot drawn to the centre of the road;
* an alley or a private drive is no street; a plan far from the street, and
  every lot that is not GREEN, are untouched; nothing moves toward GREEN;
* EDGE-SAG and DEDICATION-JOG are records below the yellow line: the colour
  never moves, and on a GREEN EDGE-SAG needs the plan on the lot and its
  building inside the envelope.
"""

from __future__ import annotations

import dataclasses
import json
from types import SimpleNamespace

import pytest

shapely = pytest.importorskip("shapely")

from shapely.geometry import LineString  # noqa: E402

from flats.geom import street_through  # noqa: E402
from flats.geom.envelope import edge_sags  # noqa: E402
from flats.ingest.quadfit import (  # noqa: E402
    DEDICATION_JOG,
    EDGE_SAG,
    STREET_THROUGH,
    lot_from_row,
    marks_checked,
    screen_lot,
    street_through_checked,
)
from flats.score import flags as flag_plan  # noqa: E402
from flats.score.screen import CLOSER_LOOK_STREET_THROUGH_LOT, Triage  # noqa: E402
from flats.tests.test_quadfit_bridge import (  # noqa: E402
    X0,
    Y0,
    corpus,  # noqa: F401  (fixture)
    pod,
    policies,  # noqa: F401  (fixture)
    row,
)
from flats.tests.test_split_zone import D, W, big_row  # noqa: E402

pytestmark = pytest.mark.unit

LOT = shapely.box(X0, Y0, X0 + W, Y0 + D)
FRONT = ((X0, Y0, X0 + W, Y0),)


def _streets(*lines: tuple[LineString, str | None, int]) -> street_through.Streets:
    geoms = [g for g, _, _ in lines]
    return street_through.Streets(
        shapely.STRtree(geoms), geoms, tuple(n for _, n, _ in lines), tuple(t for _, _, t in lines)
    )


def _box(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [list(p) for p in shapely.box(x0, y0, x1, y1).exterior.coords]


def _greened(s):
    def green(x):
        return dataclasses.replace(x, triage=Triage.green, reasons=(), flags=(), binds=())

    return dataclasses.replace(s, screening=green(s.screening), signed=green(s.signed))


def _green(corpus, policies, **over):  # noqa: F811
    lot = lot_from_row(big_row(jurisdiction="oregon_city", zone="R-6", **over), corpus.layers)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    return lot, _greened(s)


def _with(s, **rings):
    drawing = dict(s.drawing or {})
    drawing["fits"] = True
    drawing.update(rings)
    return dataclasses.replace(s, drawing=drawing)


#: The plan in the west half of the lot: building at the front, court behind.
PLAN = {
    "building": _box(X0 + 5, Y0 + 20, X0 + 30, Y0 + 100),
    "lane": _box(X0 + 30, Y0 + 20, X0 + 42, Y0 + 100),
    "court": _box(X0 + 5, Y0 + 100, X0 + 42, Y0 + 140),
}
#: WALTER's case: a local street run north-south through the lot.
THROUGH = LineString([(X0 + 70, Y0 - 40), (X0 + 70, Y0 + D + 40)])


def held(s):
    return [f for f in s.signed.flags if f.code == STREET_THROUGH]


# --- the measure ------------------------------------------------------------


def test_a_street_through_the_lot_near_the_court_is_found() -> None:
    plan = [shapely.Polygon(r) for r in PLAN.values()]
    (got,) = street_through.crossings(LOT, FRONT, plan, _streets((THROUGH, "WALTER", 1500)))
    assert got.name == "WALTER" and got.type == 1500
    assert got.gap_ft == pytest.approx(28.0)
    assert got.inside_ft == pytest.approx(D - 5 - 10, abs=0.2)
    assert "Walter" in got.words() and "1500" in got.words()


def test_the_frontage_street_is_never_counted() -> None:
    plan = [shapely.Polygon(r) for r in PLAN.values()]
    for line in (
        LineString([(X0 - 50, Y0 - 30), (X0 + W + 50, Y0 - 30)]),  # across the line, off the lot
        LineString([(X0 - 50, Y0 + 2), (X0 + W + 50, Y0 + 2)]),  # a lot drawn to the road's centre
        LineString([(X0 - 50, Y0 + 8), (X0 + W + 50, Y0 + 8)]),  # ... traced a little off it
    ):
        assert street_through.crossings(LOT, FRONT, plan, _streets((line, "MAPLE", 1500))) == []


def test_a_street_beyond_reach_of_the_plan_or_only_nicking_the_lot_is_not_counted() -> None:
    plan = [shapely.Polygon(r) for r in PLAN.values()]
    far = LineString([(X0 + 93, Y0 - 40), (X0 + 93, Y0 + D + 40)])  # 51 ft from the lane
    nick = LineString([(X0 + W - 12, Y0 + D + 5), (X0 + W + 5, Y0 + D - 12)])  # a corner cut
    assert street_through.crossings(LOT, FRONT, plan, _streets((far, "FOX", 1500))) == []
    assert street_through.crossings(LOT, FRONT, plan, _streets((nick, "FOX", 1500))) == []


def test_nothing_drawn_counts_every_street_through_the_lot() -> None:
    (got,) = street_through.crossings(LOT, FRONT, None, _streets((THROUGH, "WALTER", 1500)))
    assert got.gap_ft == 0.0


def test_load_leaves_out_alleys_and_private_drives_and_keeps_unread_ways(tmp_path) -> None:
    pd = pytest.importorskip("pandas")
    lines = [THROUGH] * 6
    frame = pd.DataFrame(
        {
            "name": ["A", "B", "C", "D", "E", None],
            "type": [1500, 1600, 1700, 1800, 2000, 8224],
            "alley": [False, True, False, False, False, False],
            "wkb": [shapely.to_wkb(g) for g in lines],
        }
    )
    path = tmp_path / "s1_streets.parquet"
    frame.to_parquet(path)
    got = street_through.load(path)
    assert got is not None
    assert got.types == (1500, 2000, 8224)
    assert got.names == ("A", "E", None)


# --- the hold ----------------------------------------------------------------


def test_a_green_with_a_street_through_near_its_plan_is_held_yellow(corpus, policies) -> None:  # noqa: F811
    lot, s = _green(corpus, policies)
    got = street_through_checked(_with(s, **PLAN), lot, _streets((THROUGH, "WALTER", 1500)))
    (flag,) = held(got)
    assert "Walter" in flag.source
    assert got.signed.colour is flag_plan.Colour.yellow and got.screening.colour is flag_plan.Colour.yellow
    assert got.signed.triage is Triage.yellow
    assert CLOSER_LOOK_STREET_THROUGH_LOT in got.signed.reasons


def test_a_green_with_nothing_drawn_and_a_street_through_is_held(corpus, policies) -> None:  # noqa: F811
    lot, s = _green(corpus, policies)
    got = street_through_checked(dataclasses.replace(s, drawing=None), lot, _streets((THROUGH, "WALTER", 1500)))
    (flag,) = held(got)
    assert "no fitting plan" in flag.source


def test_untouched_without_streets_off_the_plan_or_on_a_lot_not_green(corpus, policies) -> None:  # noqa: F811
    lot, s = _green(corpus, policies)
    x = _with(s, **PLAN)
    assert street_through_checked(x, lot, None) is x
    far = LineString([(X0 + 93, Y0 - 40), (X0 + 93, Y0 + D + 40)])
    assert street_through_checked(x, lot, _streets((far, "FOX", 1500))) is x
    for colour in (Triage.yellow, Triage.red):
        flag = flag_plan.Flag("MEASURE-PLAN-OFF-LOT", flag_plan.LOT, "CLOSER_LOOK_PLAN_OFF_LOT")

        def hold(r, colour=colour, flag=flag):
            return dataclasses.replace(r, triage=colour, flags=(flag,))

        y = dataclasses.replace(x, screening=hold(x.screening), signed=hold(x.signed))
        assert y.signed.colour is not flag_plan.Colour.green
        assert street_through_checked(y, lot, _streets((THROUGH, "WALTER", 1500))) is y


# --- the records -------------------------------------------------------------


#: The front line bows 1.2 ft into the lot between its traced ends.
BOWED = shapely.Polygon(
    [(X0, Y0), (X0 + W / 2, Y0 + 1.2), (X0 + W, Y0), (X0 + W, Y0 + D), (X0, Y0 + D)]
)


def _edges(*rows):
    return SimpleNamespace(
        edges=tuple(SimpleNamespace(x1=x1, y1=y1, x2=x2, y2=y2) for x1, y1, x2, y2, _ in rows)
    )


def test_edge_sags_reads_the_bow_on_each_edge() -> None:
    edges = _edges(
        (X0, Y0, X0 + W, Y0, "front"),
        (X0 + W, Y0, X0 + W, Y0 + D, "side"),
        (X0 + W, Y0 + D, X0, Y0 + D, "rear"),
        (X0, Y0 + D, X0, Y0, "side"),
    )
    got = edge_sags(BOWED, edges)
    assert got[0] == pytest.approx(1.2, abs=0.01)
    assert got[1:] == (0.0, 0.0, 0.0)


def _bowed(corpus, policies):  # noqa: F811
    edges = [
        [X0, Y0, X0 + W, Y0, "F"],
        [X0 + W, Y0, X0 + W, Y0 + D, "S"],
        [X0 + W, Y0 + D, X0, Y0 + D, "R"],
        [X0, Y0 + D, X0, Y0, "S"],
    ]
    r = row(
        jurisdiction="oregon_city",
        zone="R-6",
        area_sqft=BOWED.area,
        frontage_ft=W,
        lot_width_ft=W,
        lot_depth_ft=D,
        edges_json=json.dumps(edges),
        lot_wkb=shapely.to_wkb(BOWED),
    )
    lot = lot_from_row(r, corpus.layers)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    # A plan drawn inside the envelope, whatever the test pod's own drawing.
    c = s.envelope.geom.centroid
    inside = _box(c.x - 10, c.y - 10, c.x + 10, c.y + 10)
    return lot, _with(_greened(s), building=inside, lane=None, court=None)


def test_a_bowed_lot_carries_edge_sag_and_keeps_its_colour(corpus, policies) -> None:  # noqa: F811
    lot, s = _bowed(corpus, policies)
    assert s.envelope is not None and s.envelope.source == "flats"
    got = marks_checked(s, lot)
    (flag,) = [f for f in got.signed.flags if f.code == EDGE_SAG]
    assert flag.bounds == (0.0, pytest.approx(1.2, abs=0.01))
    assert got.signed.colour is s.signed.colour
    assert got.signed.triage is s.signed.triage and got.signed.reasons == s.signed.reasons


def test_a_bow_of_a_ten_thousandth_of_a_foot_still_marks_the_lot(corpus, policies) -> None:  # noqa: F811
    # rel11: 1N1E09DA -00500 bowed 0.00013 ft and Fix 5 still re-placed its plan.
    lot, s = _bowed(corpus, policies)
    faint = shapely.Polygon(
        [(X0, Y0), (X0 + W / 2, Y0 + 0.0002), (X0 + W, Y0), (X0 + W, Y0 + D), (X0, Y0 + D)]
    )
    got = marks_checked(s, dataclasses.replace(lot, lot_geom=faint))
    (flag,) = [f for f in got.signed.flags if f.code == EDGE_SAG]
    assert 0.0 < flag.bounds[1] <= 0.0002


def test_a_green_with_its_building_off_the_envelope_carries_no_edge_sag(corpus, policies) -> None:  # noqa: F811
    lot, s = _bowed(corpus, policies)
    off = _with(s, building=_box(X0 - 3, Y0 + 20, X0 + 22, Y0 + 100))
    assert not [f for f in marks_checked(off, lot).signed.flags if f.code == EDGE_SAG]
    # Not GREEN, the record is raised whatever the drawing.
    flag = flag_plan.Flag("MEASURE-PLAN-OFF-LOT", flag_plan.LOT, "CLOSER_LOOK_PLAN_OFF_LOT")
    yellow = dataclasses.replace(
        off,
        screening=dataclasses.replace(off.screening, flags=(flag,)),
        signed=dataclasses.replace(off.signed, flags=(flag,)),
    )
    assert [f for f in marks_checked(yellow, lot).signed.flags if f.code == EDGE_SAG]


def test_a_straight_lot_carries_no_edge_sag(corpus, policies) -> None:  # noqa: F811
    lot, s = _green(corpus, policies)
    assert marks_checked(s, lot) is s


def test_a_row_the_jog_reading_measured_carries_dedication_jog(corpus, policies) -> None:  # noqa: F811
    jog = [[X0, Y0, X0 + W, Y0]]
    lot, s = _green(corpus, policies, road_jogs_json=json.dumps(jog))
    assert lot.road_jogs == 1
    got = marks_checked(s, lot)
    (flag,) = [f for f in got.signed.flags if f.code == DEDICATION_JOG]
    assert flag.bounds == (1.0, 1.0)
    assert got.signed.colour is s.signed.colour
