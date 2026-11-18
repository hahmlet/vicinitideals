"""A drive reaches the court only where a street meets the lot along its
width (FOLLOWUPS 201).

Portland 1N2E25DA -10200 (R7, 16001 NE San Rafael St) touches its street
along 8.0 ft -- a strip lot of its own, 1N2E25DA -10300, holds the rest of its
street side off -- and 33.266.120.D.2 asks a 9 ft driveway on private
property. It was GREEN on run 128. The contracts:

* a GREEN plan on a lot whose longest street line is shorter than the
  narrowest drive allowed is YELLOW with ACCESS-DRIVE-TOUCH, never RED;
* the narrowest drive is the ruled narrow lane where one is held (Portland's
  9 ft), else the reading's own drive;
* a lot fed from an alley is not asked (the alley is the lane);
* a RED plan stays RED; nothing ever moves toward GREEN.
"""

from __future__ import annotations

import dataclasses

import pytest

pytest.importorskip("shapely")

from flats.geom.edges import Edge, EdgeClass, LotEdges, Tier, bearing_deg  # noqa: E402
from flats.ingest.quadfit import DRIVE_TOUCH, drive_touch_checked  # noqa: E402
from flats.score import flags as flag_plan  # noqa: E402
from flats.score.screen import CLOSER_LOOK_DRIVE_TOUCH, Triage  # noqa: E402
from flats.tests.test_plan_on_lot import _green, _with  # noqa: E402
from flats.tests.test_quadfit_bridge import (  # noqa: E402
    corpus,  # noqa: F401  (fixture)
    policies,  # noqa: F401  (fixture)
)

pytestmark = pytest.mark.unit


def _edge(x1, y1, x2, y2, cls, *, alley=False):
    length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
    return Edge(x1, y1, x2, y2, length, bearing_deg(x1, y1, x2, y2), cls, alley=alley)


def _touching(touch_ft: float, *, alley: bool = False) -> LotEdges:
    """A 100 x 150 lot meeting its street along the south line's first
    ``touch_ft`` and a neighbour's strip along the rest (the San Rafael
    case); an alley along the north line when ``alley``."""
    edges = [
        _edge(0, 0, touch_ft, 0, EdgeClass.front),
        _edge(touch_ft, 0, 100, 0, EdgeClass.side),
        _edge(100, 0, 100, 150, EdgeClass.side),
        _edge(100, 150, 0, 150, EdgeClass.rear, alley=alley),
        _edge(0, 150, 0, 0, EdgeClass.side),
    ]
    return LotEdges(Tier.clean, tuple(edges), (90.0,), touch_ft, 1.0)


def _on(s, touch_ft: float, **kw):
    return dataclasses.replace(_with(s), street_edges=_touching(touch_ft, **kw))


def touch_flags(s):
    return [f for f in s.signed.flags if f.code == DRIVE_TOUCH]


def test_eight_feet_of_street_holds_the_lot_yellow(corpus, policies) -> None:  # noqa: F811
    _, s = _green(corpus, policies)
    got = drive_touch_checked(_on(s, 8.0))

    (flag,) = touch_flags(got)
    assert "8.0 ft" in flag.source
    assert got.signed.colour is flag_plan.Colour.yellow
    assert got.screening.triage is Triage.yellow
    assert CLOSER_LOOK_DRIVE_TOUCH in got.signed.reasons


def test_a_street_line_as_wide_as_the_drive_is_untouched(corpus, policies) -> None:  # noqa: F811
    _, s = _green(corpus, policies)
    wide = _on(s, 100.0)
    assert drive_touch_checked(wide) is wide


def test_a_ruled_narrow_lane_is_the_width_asked(corpus, policies) -> None:  # noqa: F811
    # Portland's 9 ft (rulings.yaml 2026-11-10-portland-driveway-9ft): a
    # 10 ft touch takes the narrow drive though not the pod's 12 ft lane.
    _, s = _green(corpus, policies)
    some = next(iter(s.rules.values.values()))
    narrow = dataclasses.replace(some, name="driveway_lane_narrow_ft", value=9.0)
    rules = dataclasses.replace(s.rules, values={**s.rules.values, "driveway_lane_narrow_ft": narrow})
    s = dataclasses.replace(s, rules=rules)

    ten = _on(s, 10.0)
    assert drive_touch_checked(ten) is ten
    assert touch_flags(drive_touch_checked(_on(s, 8.0)))


def test_without_the_narrow_lane_ten_feet_is_held(corpus, policies) -> None:  # noqa: F811
    _, s = _green(corpus, policies)
    assert s.rules.get("driveway_lane_narrow_ft") is None
    assert touch_flags(drive_touch_checked(_on(s, 10.0)))


def test_an_alley_lot_is_not_asked(corpus, policies) -> None:  # noqa: F811
    _, s = _green(corpus, policies)
    alleyed = _on(s, 8.0, alley=True)
    assert drive_touch_checked(alleyed) is alleyed


def test_a_red_lot_stays_red_with_the_flag(corpus, policies) -> None:  # noqa: F811
    _, s = _green(corpus, policies)

    def red(x):
        return dataclasses.replace(x, triage=Triage.red)

    s = dataclasses.replace(s, screening=red(s.screening), signed=red(s.signed))
    got = drive_touch_checked(_on(s, 8.0))
    assert got.signed.triage is Triage.red
    assert [f.code for f in touch_flags(got)] == [DRIVE_TOUCH]
