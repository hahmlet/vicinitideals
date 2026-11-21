"""A drawn lane or court past the lot line is not a plan the lot holds
(FOLLOWUPS 201).

Portland 1N1E23CB -21200 (RM4, a through lot) was GREEN on run 128 with its
lane 322 sq ft and its court 203 sq ft past the far street line: the fit took
the side-setback overlap on trust and nothing measured the drawing against the
lot. The contracts:

* a GREEN plan whose lane or court stands more than 1 ft past the lot is
  YELLOW with MEASURE-PLAN-OFF-LOT, naming what and how much;
* a sliver along the line (raster rounding) moves nothing;
* a RED plan stays RED; nothing ever moves toward GREEN.
"""

from __future__ import annotations

import dataclasses

import pytest

shapely = pytest.importorskip("shapely")

from flats.ingest.quadfit import (  # noqa: E402
    PLAN_OFF_LOT,
    lot_from_row,
    plan_on_lot_checked,
    screen_lot,
)
from flats.score import flags as flag_plan  # noqa: E402
from flats.score.screen import CLOSER_LOOK_PLAN_OFF_LOT, Triage  # noqa: E402
from flats.tests.test_quadfit_bridge import (  # noqa: E402
    X0,
    Y0,
    corpus,  # noqa: F401  (fixture)
    pod,
    policies,  # noqa: F401  (fixture)
)
from flats.tests.test_split_zone import D, W, big_row  # noqa: E402

pytestmark = pytest.mark.unit


def _green(corpus, policies):  # noqa: F811
    lot = lot_from_row(big_row(jurisdiction="oregon_city", zone="R-6"), corpus.layers)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)

    def green(x):
        return dataclasses.replace(x, triage=Triage.green, reasons=(), flags=(), binds=())

    return lot, dataclasses.replace(s, screening=green(s.screening), signed=green(s.signed))


def _box(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [list(p) for p in shapely.box(x0, y0, x1, y1).exterior.coords]


def _with(s, **rings):
    drawing = dict(s.drawing or {})
    drawing["fits"] = True
    drawing.update(rings)
    return dataclasses.replace(s, drawing=drawing)


def off_flags(s):
    return [f for f in s.signed.flags if f.code == PLAN_OFF_LOT]


def test_a_lane_drawn_past_the_lot_line_holds_the_lot_yellow(corpus, policies) -> None:  # noqa: F811
    lot, s = _green(corpus, policies)
    # A 12 ft lane running 4 ft past the east lot line for 80 ft: ~320 sq ft.
    lane = _box(X0 + W - 8, Y0, X0 + W + 4, Y0 + 80)
    got = plan_on_lot_checked(_with(s, lane=lane, court=None), lot)

    (flag,) = off_flags(got)
    assert "lane" in flag.source
    assert got.signed.colour is flag_plan.Colour.yellow
    assert CLOSER_LOOK_PLAN_OFF_LOT in got.signed.reasons


def test_a_court_past_the_line_is_held_too(corpus, policies) -> None:  # noqa: F811
    lot, s = _green(corpus, policies)
    court = _box(X0 + 10, Y0 + D - 30, X0 + 70, Y0 + D + 4)
    got = plan_on_lot_checked(_with(s, lane=None, court=court), lot)

    (flag,) = off_flags(got)
    assert "court" in flag.source
    assert got.signed.colour is flag_plan.Colour.yellow


def test_a_sliver_along_the_line_moves_nothing(corpus, policies) -> None:  # noqa: F811
    # Half a foot past the line along 100 ft is 50 sq ft: raster rounding, the
    # class hunt's 11-43 sq ft overhangs.
    lot, s = _green(corpus, policies)
    court = _box(X0 + W - 30, Y0 + 20, X0 + W + 0.5, Y0 + 120)
    got = plan_on_lot_checked(_with(s, lane=None, court=court), lot)

    assert off_flags(got) == []
    assert got.signed.colour is flag_plan.Colour.green


def test_a_plan_on_the_lot_is_untouched(corpus, policies) -> None:  # noqa: F811
    lot, s = _green(corpus, policies)
    inside = _with(s, lane=_box(X0 + 61, Y0, X0 + 73, Y0 + 36), court=_box(X0 + 5, Y0 + 36, X0 + 73, Y0 + 84))
    assert plan_on_lot_checked(inside, lot) is inside


def test_a_plan_that_did_not_fit_is_not_asked(corpus, policies) -> None:  # noqa: F811
    # A drawing that missed the fit runs past the lot where it must; the
    # fit's miss answers it.
    lot, s = _green(corpus, policies)
    missed = _with(s, court=_box(X0 + 5, Y0 + 109, X0 + 73, Y0 + D + 7))
    missed = dataclasses.replace(missed, drawing={**missed.drawing, "fits": False})
    assert plan_on_lot_checked(missed, lot) is missed


def test_a_red_lot_stays_red_with_the_flag(corpus, policies) -> None:  # noqa: F811
    lot, s = _green(corpus, policies)

    def red(x):
        return dataclasses.replace(x, triage=Triage.red)

    s = dataclasses.replace(s, screening=red(s.screening), signed=red(s.signed))
    lane = _box(X0 + W - 8, Y0, X0 + W + 4, Y0 + 80)
    got = plan_on_lot_checked(_with(s, lane=lane), lot)

    assert got.signed.triage is Triage.red
    assert [f.code for f in off_flags(got)] == [PLAN_OFF_LOT]
