"""Where rel5's three lanes meet rel4's court placement (2026-11-08).

rel4 (ed1d094d) moves the drawing after the fit: ``court_turned`` turns a
plan whose court stood in a front yard, the front-max slide moves it toward
the street, and ``court_yard_checked`` reads the drawing finally kept. rel5
adds three standards that the drawing must still keep wherever it ends up:

* Tigard RES-A/B/C: the 5 ft S-3 strip between the court and every non-street
  lot line (FOLLOWUPS 105 round 3, tdc.18.420.landscaping.txt#L252-L255);
* Oregon City R-2 beside R-10/R-8/R-6: a 10 ft side yard and a 10 ft strip
  (Table 17.12.040 note 1, 17.zoning.txt#L4615-L4618; FOLLOWUPS 2(a));
* Gresham LDR-7 at the end of a Minor Access Street: the building within 25 ft
  of every street line (Table 4.0131 note 5, 4.0130.txt#L179; FOLLOWUPS 37 iii).

Each test screens a lot shaped so the court placement steps have work to do
(a through lot, whose far end is a front yard too) and requires the drawing
kept to honour both the new standard and the front-yard gate.
"""

from __future__ import annotations

import dataclasses
import json

import pytest
import shapely

from flats.encode.load import load_trusted
from flats.ingest.quadfit import _screen_lot_once, court_in_front_yard, lot_from_row
from flats.score import flags as flag_plan, relief, slack
from flats.tests.test_quadfit_bridge import X0, Y0, pod4, row

pytestmark = pytest.mark.unit

EPS = 0.05


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


def _edges(w: float, d: float, through: bool) -> list[list[object]]:
    return [
        [X0, Y0, X0 + w, Y0, "F"],
        [X0 + w, Y0, X0 + w, Y0 + d, "S"],
        [X0 + w, Y0 + d, X0, Y0 + d, "F" if through else "R"],
        [X0, Y0 + d, X0, Y0, "S"],
    ]


def _lot(
    jurisdiction: str, zone: str, w: float, d: float, *, through: bool, row_over=None, **observed
):
    edges = _edges(w, d, through)
    r = row(
        TLID="9S999AA  -99999",
        jurisdiction=jurisdiction,
        zone=zone,
        area_sqft=w * d,
        frontage_ft=w,
        lot_width_ft=w,
        lot_depth_ft=d,
        edges_json=json.dumps(edges),
        front_bearings_json="[0.0, 180.0]" if through else "[0.0]",
        wkb=shapely.to_wkb(shapely.box(X0 + 5, Y0 + 10, X0 + w - 5, Y0 + d - 10)),
        lot_wkb=shapely.to_wkb(shapely.box(X0, Y0, X0 + w, Y0 + d)),
        **(row_over or {}),
    )
    lot = lot_from_row(r)
    if observed:
        lot = dataclasses.replace(lot, observed={**lot.observed, **observed})
    return lot, edges


def _screen(lot, corpus, policies):
    (s,) = _screen_lot_once(
        lot, [pod4()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0,
        bound=False,
    )
    return s


def _lines(edges, codes: set[str]) -> list[shapely.LineString]:
    return [shapely.LineString([(e[0], e[1]), (e[2], e[3])]) for e in edges if e[4] in codes]


def _drawn(s, key: str):
    d = s.drawing or {}
    if not d.get("fits") or not d.get(key):
        return None
    return shapely.Polygon(d[key])


def _held_to(s, edges, *, strip: float, side: float | None = None) -> None:
    """The kept drawing's court stands ``strip`` off every non-street line,
    its building ``side`` off the side lines, and a GREEN's court stands in
    no front yard."""
    court = _drawn(s, "court")
    building = _drawn(s, "building")
    if court is None or building is None:
        pytest.skip("the lot draws no fitting plan with a court")
    for line in _lines(edges, {"S", "R"}):
        assert court.distance(line) >= strip - EPS, (court.distance(line), strip)
    if side is not None:
        for line in _lines(edges, {"S"}):
            assert building.distance(line) >= side - EPS, (building.distance(line), side)
    if s.signed.colour is flag_plan.Colour.green:
        assert not court_in_front_yard(s)


@pytest.mark.parametrize("zone", ["RES-A", "RES-B", "RES-C"])
@pytest.mark.parametrize("through", [False, True], ids=["interior", "through"])
def test_tigard_s3_strip_holds_on_the_drawing_court_placement_keeps(
    corpus, policies, zone: str, through: bool
) -> None:
    lot, edges = _lot("tigard", zone, 110.0, 300.0 if through else 220.0, through=through)
    s = _screen(lot, corpus, policies)
    assert s.rules.get("parking_lot_line_buffer_ft") == 5
    _held_to(s, edges, strip=5.0)


@pytest.mark.parametrize("through", [False, True], ids=["interior", "through"])
def test_oregon_city_r2_beside_single_family_holds_ten_feet_on_the_drawing(
    corpus, policies, through: bool
) -> None:
    lot, edges = _lot(
        "oregon_city", "R-2", *((150.0, 250.0) if through else (120.0, 150.0)), through=through,
        abuts_lower_density_zone=True,
    )
    s = _screen(lot, corpus, policies)
    assert s.rules.get("setback_side_ft") == 10
    assert s.rules.get("parking_lot_line_buffer_ft") == 10
    _held_to(s, edges, strip=10.0, side=10.0)


def test_oregon_city_r2_beside_r5_keeps_five(corpus, policies) -> None:
    lot, _ = _lot(
        "oregon_city", "R-2", 120.0, 150.0, through=False, abuts_lower_density_zone=False
    )
    s = _screen(lot, corpus, policies)
    assert s.rules.get("setback_side_ft") == 5
    assert s.rules.get("parking_lot_line_buffer_ft") == 5


@pytest.mark.parametrize("through", [False, True], ids=["interior", "through"])
def test_gresham_street_end_maximum_and_the_front_yard_gate_together(
    corpus, policies, through: bool
) -> None:
    # At the end of a Minor Access Street the building must stand within
    # 25 ft of EVERY street line (no line named). On a 200 ft deep through lot
    # no drawing can, so the lot is never GREEN; on the interior lot the
    # front-max slide may stand the plan forward, and its court must still
    # be out of the front yard on a GREEN.
    lot, edges = _lot(
        "gresham", "LDR-7", 100.0, 200.0, through=through,
        at_street_end=True, row_over={"sidewalk_easement_ft": 7.0, "street_end_ft": 10.0},
    )
    s = _screen(lot, corpus, policies)
    assert s.rules.get("setback_front_max_ft") == 25
    if through:
        assert s.signed.colour is not flag_plan.Colour.green
        return
    building = _drawn(s, "building")
    if s.signed.colour is flag_plan.Colour.green:
        assert building is not None
        for line in _lines(edges, {"F"}):
            assert building.distance(line) <= 25 + EPS
        assert not court_in_front_yard(s)
