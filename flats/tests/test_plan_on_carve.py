"""A drawn building, lane or court on carved ground is not a plan the lot
holds (carve-overlap, 2026-11-18).

The fit stands the building inside the envelope less the carve and checks the
court's run behind it against the lot less the carve, but the lane and court
it draws into a side setback (``side_yard_lane_overlap_ft``,
``side_yard_court_overlap_ft``) lie outside both and were measured against no
carve. A carve with no flag twin -- Portland's River Environmental overlay
``pdx_river_e`` (ruling 2026-11-18-river-e-clear-stays-green: GREEN only where
"the drawn building, court and lane sit clear of it"), and the CLEARED carves
in :mod:`flats.rules.resource_overlays` -- could then sit under drawn paving on
a GREEN. The contracts:

* a GREEN whose drawn building, lane or court stands more than half a foot
  onto the carve is YELLOW with MEASURE-PLAN-ON-CARVE, naming what and how much;
* a carved GREEN with no fitting drawing is YELLOW too (nothing showed it clear);
* a plan clear of the carve, a lot with no carve, a sliver along the carve's
  edge, and every lot that is not GREEN are untouched; nothing moves toward
  GREEN.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

shapely = pytest.importorskip("shapely")

from flats.ingest.quadfit import (  # noqa: E402
    PLAN_ON_CARVE,
    lot_from_row,
    plan_on_carve_checked,
    screen_lot,
)
from flats.score import flags as flag_plan  # noqa: E402
from flats.score.screen import CLOSER_LOOK_PLAN_ON_CARVE, Triage  # noqa: E402
from flats.tests.test_quadfit_bridge import (  # noqa: E402
    X0,
    Y0,
    corpus,  # noqa: F401  (fixture)
    pod,
    policies,  # noqa: F401  (fixture)
    row,
    walled,
)
from flats.tests.test_split_zone import D, W, big_row  # noqa: E402

pytestmark = pytest.mark.unit


def _greened(s):
    def green(x):
        return dataclasses.replace(x, triage=Triage.green, reasons=(), flags=(), binds=())

    return dataclasses.replace(s, screening=green(s.screening), signed=green(s.signed))


def _green(corpus, policies, carve=None):  # noqa: F811
    lot = lot_from_row(
        big_row(
            jurisdiction="oregon_city",
            zone="R-6",
            carve_wkb=None if carve is None else shapely.to_wkb(carve),
        ),
        corpus.layers,
    )
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    return lot, _greened(s)


def _box(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [list(p) for p in shapely.box(x0, y0, x1, y1).exterior.coords]


def _with(s, **rings):
    drawing = dict(s.drawing or {})
    drawing["fits"] = True
    drawing.update(rings)
    return dataclasses.replace(s, drawing=drawing)


def carve_flags(s):
    return [f for f in s.signed.flags if f.code == PLAN_ON_CARVE]


# A carve along the east side yard, 10 ft wide, the whole depth of the lot.
EAST = shapely.box(X0 + W - 10, Y0, X0 + W, Y0 + 150)


def test_paving_drawn_into_a_side_yard_carve_is_held_on_a_real_drawing(corpus, policies) -> None:  # noqa: F811
    """The finding itself, on the fitter's own drawing: a Portland RM2 lot
    whose lane and court ride the west side setback. A carve laid on exactly
    that strip leaves the fit passing and the paving drawn on it (the gap);
    the check holds such a plan out of GREEN."""
    w, d = 60, 160
    lot = shapely.box(X0, Y0, X0 + w, Y0 + d)
    edges = [
        [X0, Y0, X0 + w, Y0, "F"],
        [X0 + w, Y0, X0 + w, Y0 + d, "S"],
        [X0 + w, Y0 + d, X0, Y0 + d, "R"],
        [X0, Y0 + d, X0, Y0, "S"],
    ]

    def screened(area=None):
        r = row(
            zone="RM2",
            neighbour_zones_json=walled(("portland", "CX")),
            lot_wkb=shapely.to_wkb(lot),
            edges_json=json.dumps(edges),
            area_sqft=float(w * d),
            frontage_ft=float(w),
            lot_width_ft=float(w),
            lot_depth_ft=float(d),
            wkb=shapely.to_wkb(shapely.box(X0 + 5, Y0 + 5, X0 + w - 5, Y0 + d - 5)),
            carve_wkb=None if area is None else shapely.to_wkb(area),
        )
        here = lot_from_row(r, corpus.layers)
        (s,) = screen_lot(here, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
        return here, s

    _, base = screened()
    assert base.drawing is not None and base.drawing["fits"]
    env = base.envelope.geom
    strip = [
        shapely.Polygon(base.drawing[k]).difference(env)
        for k in ("lane", "court")
        if base.drawing.get(k)
    ]
    strip = shapely.union_all([p for p in strip if p.area > 1.0])
    # The plan does draw paving outside the envelope, in the side setback.
    assert strip.area > 100.0

    here, s = screened(strip.buffer(0.01))
    drawn = shapely.union_all(
        [shapely.Polygon(s.drawing[k]) for k in ("lane", "court") if s.drawing and s.drawing.get(k)]
    )
    on_carve = drawn.intersection(here.carve).area
    if s.signed.triage is Triage.green:
        pytest.fail(f"GREEN with {on_carve:.0f} sq ft of paving on the carve")
    if s.drawing and s.drawing.get("fits") and on_carve > 1.0:
        # The fit still passes with the paving on the carve: had the lot been
        # GREEN on its other facts, only the drawing check would hold it.
        got = plan_on_carve_checked(_greened(s), here)
        (flag,) = carve_flags(got)
        assert got.signed.triage is Triage.yellow and got.screening.triage is Triage.yellow
        assert CLOSER_LOOK_PLAN_ON_CARVE in got.signed.reasons
        assert "lane" in flag.source or "court" in flag.source


def test_a_lane_on_the_carve_holds_the_lot_yellow(corpus, policies) -> None:  # noqa: F811
    lot, s = _green(corpus, policies, EAST)
    lane = _box(X0 + W - 14, Y0 + 20, X0 + W - 2, Y0 + 100)
    got = plan_on_carve_checked(_with(s, lane=lane, court=None, building=None), lot)

    (flag,) = carve_flags(got)
    assert "lane" in flag.source
    assert got.signed.colour is flag_plan.Colour.yellow
    assert CLOSER_LOOK_PLAN_ON_CARVE in got.signed.reasons


def test_a_court_or_building_on_the_carve_is_held_too(corpus, policies) -> None:  # noqa: F811
    lot, s = _green(corpus, policies, EAST)
    for part in ("court", "building"):
        ring = _box(X0 + 40, Y0 + 60, X0 + W - 4, Y0 + 100)
        rings = {"lane": None, "court": None, "building": None, part: ring}
        got = plan_on_carve_checked(_with(s, **rings), lot)
        (flag,) = carve_flags(got)
        assert part in flag.source
        assert got.signed.triage is Triage.yellow


def test_a_carved_green_with_nothing_drawn_is_held(corpus, policies) -> None:  # noqa: F811
    lot, s = _green(corpus, policies, EAST)
    for drawing in (None, {**(s.drawing or {}), "fits": False}):
        got = plan_on_carve_checked(dataclasses.replace(s, drawing=drawing), lot)
        (flag,) = carve_flags(got)
        assert "no fitting plan" in flag.source
        assert got.signed.triage is Triage.yellow


def test_a_plan_clear_of_the_carve_is_untouched(corpus, policies) -> None:  # noqa: F811
    lot, s = _green(corpus, policies, EAST)
    clear = _with(
        s,
        building=_box(X0 + 10, Y0 + 10, X0 + 66, Y0 + 46),
        lane=_box(X0 + 66, Y0 + 10, X0 + 78, Y0 + 46),
        court=_box(X0 + 10, Y0 + 46, X0 + W - 10, Y0 + 100),
    )
    assert plan_on_carve_checked(clear, lot) is clear


def test_a_sliver_along_the_carve_edge_moves_nothing(corpus, policies) -> None:  # noqa: F811
    # The court's edge 0.4 ft onto the carve along 54 ft: the raster cell and
    # the drawing's rounding, not paving on the area.
    lot, s = _green(corpus, policies, EAST)
    edge = _with(s, building=None, lane=None, court=_box(X0 + 10, Y0 + 46, X0 + W - 9.6, Y0 + 100))
    got = plan_on_carve_checked(edge, lot)
    assert carve_flags(got) == []
    assert got.signed.triage is Triage.green


def test_a_lot_no_carve_touches_is_not_asked(corpus, policies) -> None:  # noqa: F811
    lot, s = _green(corpus, policies)
    assert lot.carve is None or lot.carve.is_empty
    for drawing in (None, _with(s, lane=_box(X0 + W - 14, Y0, X0 + W - 2, Y0 + 80)).drawing):
        x = dataclasses.replace(s, drawing=drawing)
        assert plan_on_carve_checked(x, lot) is x


def test_a_lot_that_is_not_green_is_untouched(corpus, policies) -> None:  # noqa: F811
    lot, s = _green(corpus, policies, EAST)
    for colour in (Triage.yellow, Triage.red):

        def held(x):
            return dataclasses.replace(x, triage=colour)

        x = dataclasses.replace(s, screening=held(s.screening), signed=held(s.signed))
        x = _with(x, lane=_box(X0 + W - 14, Y0, X0 + W - 2, Y0 + 80))
        assert plan_on_carve_checked(x, lot) is x
        assert plan_on_carve_checked(dataclasses.replace(x, drawing=None), lot).signed.triage is colour


# --- the drive from the street to the parking (FOLLOWUPS 206) -------------
#
# The drawing stops the lane at the building's street face; the run across the
# front yard (or, for a court fed from the side, across the side yard) is
# drawn by flats.fit.front_drive and measured against the carve as the drawn
# parts are. The plan below: the pod 80 x 25 ft, 20 ft back from the street
# (south), its 12-ft lane on the east flank, the court behind.

PLAN = dict(
    room=_box(X0 + 5, Y0 + 20, X0 + 97, Y0 + 90),
    building=_box(X0 + 5, Y0 + 20, X0 + 85, Y0 + 45),
    lane=_box(X0 + 85, Y0 + 20, X0 + 97, Y0 + 45),
    court=_box(X0 + 5, Y0 + 45, X0 + 97, Y0 + 90),
)


def _drawn(s, **rings):
    """``s`` drawn as ``rings``, square to the lot as the rings are: the
    drawing is the fit's, so the fit's angle is the rings' (0 degrees)."""
    return dataclasses.replace(_with(s, **rings), fit=dataclasses.replace(s.fit, angle_deg=0.0))


def test_a_drive_across_a_carved_front_yard_holds_the_lot_yellow(corpus, policies) -> None:  # noqa: F811
    # Under the lane's run to the street, clear of the building, lane and court.
    front = shapely.box(X0 + 80, Y0, X0 + W, Y0 + 15)
    lot, s = _green(corpus, policies, front)
    got = plan_on_carve_checked(_drawn(s, **PLAN), lot)

    (flag,) = carve_flags(got)
    assert "drive" in flag.source
    assert "lane" not in flag.source and "court" not in flag.source
    assert got.signed.triage is Triage.yellow and got.screening.triage is Triage.yellow
    assert CLOSER_LOOK_PLAN_ON_CARVE in got.signed.reasons


def test_a_carve_at_the_back_or_beside_the_drive_leaves_the_lot_green(corpus, policies) -> None:  # noqa: F811
    for carve in (
        shapely.box(X0, Y0 + 120, X0 + W, Y0 + D),  # behind the court
        shapely.box(X0, Y0, X0 + 40, Y0 + 15),  # the front yard, west of the drive
    ):
        lot, s = _green(corpus, policies, carve)
        plan = _drawn(s, **PLAN)
        assert plan_on_carve_checked(plan, lot) is plan


def _corner(corpus, policies, carve, *, lot_wkb=None):  # noqa: F811
    """A 100 x 150 corner lot: the street along the south and the east."""
    edges = [
        [X0, Y0, X0 + W, Y0, "F"],
        [X0 + W, Y0, X0 + W, Y0 + D, "F"],
        [X0 + W, Y0 + D, X0, Y0 + D, "R"],
        [X0, Y0 + D, X0, Y0, "S"],
    ]
    lot = lot_from_row(
        row(
            jurisdiction="oregon_city",
            zone="R-6",
            area_sqft=W * D,
            frontage_ft=W,
            lot_width_ft=W,
            lot_depth_ft=D,
            edges_json=json.dumps(edges),
            lot_wkb=shapely.to_wkb(lot_wkb or shapely.box(X0, Y0, X0 + W, Y0 + D)),
            carve_wkb=shapely.to_wkb(carve),
        ),
        corpus.layers,
    )
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    return lot, _greened(s)


# No lane: the court behind the building is fed across the east side yard
# from the side street.
SIDE_FED = dict(
    room=_box(X0 + 5, Y0 + 20, X0 + 85, Y0 + 90),
    building=_box(X0 + 5, Y0 + 20, X0 + 85, Y0 + 45),
    lane=None,
    court=_box(X0 + 5, Y0 + 45, X0 + 85, Y0 + 90),
)


def test_a_side_fed_court_on_a_corner_measures_the_run_to_the_side_street(corpus, policies) -> None:  # noqa: F811
    # The side yard between the court and the side street, carved: held.
    lot, s = _corner(corpus, policies, shapely.box(X0 + 88, Y0 + 50, X0 + W, Y0 + 85))
    got = plan_on_carve_checked(_drawn(s, **SIDE_FED), lot)
    (flag,) = carve_flags(got)
    assert "drive" in flag.source
    assert got.signed.triage is Triage.yellow

    # The other side yard, and the rear, carved: no drive runs there (the
    # side street is reached to the east), so nothing is held.
    for carve in (
        shapely.box(X0, Y0 + 50, X0 + 4, Y0 + 85),
        shapely.box(X0 + 5, Y0 + 110, X0 + 85, Y0 + D),
    ):
        lot, s = _corner(corpus, policies, carve)
        plan = _drawn(s, **SIDE_FED)
        assert plan_on_carve_checked(plan, lot) is plan


def test_a_lot_shape_short_of_the_street_line_is_extended_to_it(corpus, policies) -> None:  # noqa: F811
    from flats.fit.front_drive import corridors

    # The lot polygon stops 10 ft short of the street line its lines record;
    # the carve lies only in that strip, under the lane's run to the street.
    short = shapely.box(X0, Y0 + 10, X0 + W, Y0 + D)
    lot, s = _corner(corpus, policies, shapely.box(X0 + 84, Y0, X0 + W - 4, Y0 + 8), lot_wkb=short)
    plan = _drawn(s, **PLAN)
    edges = s.street_edges or lot.edges
    (drive,) = corridors(
        plan.drawing,
        short,
        angle_deg=plan.fit.angle_deg,
        lines=[(e.x1, e.y1, e.x2, e.y2) for e in edges.edges],
    )
    assert drive.bounds[1] == pytest.approx(Y0, abs=0.2)
    assert drive.area == pytest.approx(12 * 20, abs=3.0)

    got = plan_on_carve_checked(plan, lot)
    (flag,) = carve_flags(got)
    assert "drive" in flag.source
    assert got.signed.triage is Triage.yellow


def test_the_drive_is_drawn_however_the_fit_angle_reads(corpus, policies) -> None:  # noqa: F811
    from flats.fit.front_drive import corridors

    lot = shapely.box(X0, Y0, X0 + W, Y0 + D)
    for angle in (None, 0.0, 90.0, 30.0):
        (drive,) = corridors({**PLAN, "fits": True}, lot, angle_deg=angle)
        assert drive.bounds == pytest.approx((X0 + 85, Y0, X0 + 97, Y0 + 20), abs=0.2)
    # Nothing fitting, no building, or nothing parked: no drive.
    assert corridors({**PLAN, "fits": False}, lot) == ()
    assert corridors({**PLAN, "fits": True, "building": None}, lot) == ()
    assert corridors({**PLAN, "fits": True, "lane": None, "court": None}, lot) == ()
