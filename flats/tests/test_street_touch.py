"""A street line is a street line only where the street is (FOLLOWUPS 172).

fg-rate-A's blind read of 1N2E35DC -09200 (13214 SE Ankeny Ct, Portland R5):
the screen took the whole 30.7 ft west line for a side street and fed the
court off it, though only 6.3 ft of the line touches the end of SE Ash St and
the rest borders 13143 SE Ash St. s4 now cuts a street line where it stops
abutting the street (``Lot Analysis/quadfit/s4_edges.py`` ``_street_touch``);
here the screen is held to the cut: the court is fed from a side street only
where that street meets the lot along a drive's width
(:func:`flats.fit.frontage.side_street_takes_drive`).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import shapely

from flats.designs.model import load_catalog
from flats.encode.load import load_trusted
from flats.fit.frontage import side_street_takes_drive
from flats.geom.edges import Edge, EdgeClass, LotEdges, Tier, bearing_deg
from flats.ingest.quadfit import lot_from_row, screen_lot
from flats.score import relief, slack
from flats.tests.test_quadfit_bridge import row

pytestmark = pytest.mark.unit

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "Lot Analysis" / "quadfit" / "tests" / "fixtures" / "street_touch_1N2E35DC_09200.json"
)

#: s4's edges for the lot before the cut: the west line whole, a street line.
WHOLE = [
    [7682652.55, 682684.96, 7682626.25, 682594.52, "R"],
    [7682626.25, 682594.52, 7682517.17, 682596.8, "S"],
    [7682517.17, 682596.8, 7682518.28, 682627.46, "F"],
    [7682518.28, 682627.46, 7682625.97, 682703.93, "S"],
    [7682625.97, 682703.93, 7682637.67, 682692.21, "F"],
    [7682637.67, 682692.21, 7682652.55, 682684.96, "F"],
]
#: ... and after it (``test_a_street_end_touching_a_real_lot_line_at_state_plane_coordinates``):
#: 5.9 ft of the west line on the street's end, 24.7 ft a side line.
CUT = [
    WHOLE[0],
    WHOLE[1],
    [7682517.17, 682596.8, 7682517.39, 682602.74, "F"],
    [7682517.39, 682602.74, 7682518.28, 682627.46, "S"],
    WHOLE[3],
    WHOLE[4],
    WHOLE[5],
]
WEST_X = 7_682_520.0


def _edge(x1, y1, x2, y2, cls):
    return Edge(x1, y1, x2, y2, ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5, bearing_deg(x1, y1, x2, y2), cls)


def _corner(side_ft: float, *, named: bool = True) -> LotEdges:
    """A 100 x 100 corner: the front along the south, a street along the
    east line's first ``side_ft`` and a neighbour along the rest."""
    side = EdgeClass.street_side if named else EdgeClass.front
    edges = [
        _edge(0, 0, 100, 0, EdgeClass.front),
        _edge(100, 0, 100, side_ft, side),
        _edge(100, side_ft, 100, 100, EdgeClass.side),
        _edge(100, 100, 0, 100, EdgeClass.rear),
        _edge(0, 100, 0, 0, EdgeClass.side),
    ]
    return LotEdges(Tier.corner, tuple(edges), (0.0, 90.0), 100.0 + side_ft, 1.0)


def test_a_side_street_a_few_feet_long_takes_no_drive() -> None:
    assert not side_street_takes_drive(_corner(6.0), 12.0)
    assert side_street_takes_drive(_corner(12.0), 12.0)
    assert side_street_takes_drive(_corner(100.0), 12.0)
    # A zone that asks a wider drive asks a longer touch (West Linn's 24).
    assert not side_street_takes_drive(_corner(20.0), 24.0)
    # Nothing measured: no side street to drive from.
    assert not side_street_takes_drive(None, 12.0)


def test_with_no_front_named_both_streets_must_take_the_drive() -> None:
    """Every street a front: the court is fed from whichever the building
    does not face, so both must be long enough."""
    assert not side_street_takes_drive(_corner(6.0, named=False), 12.0)
    assert side_street_takes_drive(_corner(60.0, named=False), 12.0)


@pytest.fixture(scope="module")
def screened():
    corpus = load_trusted(strict=False).rules
    policy, rel = slack.load_policy(), relief.load_policy()
    lot = shapely.from_wkt(json.loads(FIXTURE.read_text())["lot"])
    designs = [load_catalog().latest("pod56x36")]

    def run(edges, frontage):
        r = row(
            TLID="1N2E35DC  -09200",
            tier="B",
            area_sqft=round(lot.area, 1),
            frontage_ft=frontage,
            lot_width_ft=80.0,
            lot_depth_ft=105.0,
            edges_json=json.dumps(edges),
            front_bearings_json="[144.48, 87.92]",
            fronts_cul_de_sac=True,
            wkb=shapely.to_wkb(lot.buffer(-5.0)),
            lot_wkb=shapely.to_wkb(lot),
        )
        return screen_lot(
            lot_from_row(r, corpus.layers), designs,
            rules=corpus, policy=policy, relief=rel, step_deg=30.0,
        )

    return run(WHOLE, 63.8), run(CUT, 39.0)


def _fed_from_west(s) -> bool:
    """The plan feeds its court from a side street on the west line."""
    facts = s.facts if s.facts is not None else s.lot.facts
    if not facts.corner or s.lot.edges is None:
        return False
    sides = s.lot.edges.of_class(EdgeClass.street_side)
    return any(max(e.x1, e.x2) < WEST_X for e in sides)


def test_the_whole_west_line_was_read_as_a_side_street_feeding_the_court(screened) -> None:
    """The control: s4's old edges make the west line a side street, and
    some plan screened feeds its court off it (the live answer, run 122)."""
    whole, _cut = screened
    assert any(_fed_from_west(s) for s in whole)


def test_the_court_is_never_fed_off_the_six_feet_of_the_street_end(screened) -> None:
    """Cut, the west line's street is 5.9 ft against the pod's 12 ft lane:
    no plan feeds the court from it. It fits off the cul-de-sac or not at
    all; which, the bound reports."""
    _whole, cut = screened
    assert cut
    assert not any(_fed_from_west(s) for s in cut)
