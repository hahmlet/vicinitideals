"""Which end of a THROUGH lot is the front, where the code says (FOLLOWUPS 6(i)).

A through lot has a street along two opposite lines. Until 2026-09-29 both
street ends were cut as fronts in every city -- Portland 33.910's reading
("a through lot has two front lot lines"), and the lenient one wherever the
rear setback is larger than the front. ``front_lot_line_through`` holds each
code's words: ``both`` leaves the lot as cut, ``owner`` names one end the
front and the far one the rear (the better kept), and
``both_unless_no_access`` and unread keep the WORSE of both fronts and
either end rear, since nothing says which is true.
"""

from __future__ import annotations

import json

import pytest
import shapely

from flats.encode.load import load_trusted
from flats.geom.corner import THROUGH_WORST, rear_end, through_ends, through_plans
from flats.geom.edges import EdgeClass, LotEdges, Tier
from flats.geom.envelope import Setbacks, buildable
from flats.ingest.quadfit import lot_from_row, screen_lot
from flats.score import relief, slack
from flats.score.paper import front_lot_line_through_rule
from flats.tests.test_corner import GRESHAM_BEARING, at_gresham
from flats.tests.test_quadfit_bridge import X0, Y0, pod, row

pytestmark = pytest.mark.unit

#: A 50 x 100 lot in state-plane feet with a street across each end.
THROUGH = [
    [X0, Y0, X0 + 50, Y0, "F"],
    [X0 + 50, Y0, X0 + 50, Y0 + 100, "S"],
    [X0 + 50, Y0 + 100, X0, Y0 + 100, "F"],
    [X0, Y0 + 100, X0, Y0, "S"],
]
LOT = shapely.box(X0, Y0, X0 + 50, Y0 + 100)


def through_row(**over: object) -> dict[str, object]:
    return row(
        edges_json=json.dumps(THROUGH),
        lot_wkb=shapely.to_wkb(LOT),
        **over,
    )


def edges_of(raw: list[list[object]], bearings: list[float], tier: Tier = Tier.clean) -> LotEdges:
    from flats.ingest.quadfit import lot_edges

    got = lot_edges({"edges_json": json.dumps(raw), "front_bearings_json": json.dumps(bearings), "tier": "A"})
    assert got is not None
    return LotEdges(tier, got.edges, got.front_bearings, got.frontage_ft, 1.0)


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


# --- the geometry ---------------------------------------------------------------


def test_the_two_ends_are_found_at_real_coordinates_and_the_far_one_renamed_rear() -> None:
    raw, bearings = at_gresham((0, 0, "F"), (50, 0, "S"), (50, 120, "F"), (0, 120, "S"))
    edges = edges_of(raw, bearings)
    low, high = through_ends(edges)
    assert (low, high) == ((0,), (2,))
    named = rear_end(edges, high)
    assert [e.cls for e in named.edges] == [
        EdgeClass.front, EdgeClass.side, EdgeClass.rear, EdgeClass.side
    ]
    # Cut at 10 front / 5 side / 20 rear the envelope is 40 x 90, where both
    # fronts left 40 x 100.
    lot = shapely.Polygon([(e.x1, e.y1) for e in edges.edges])
    yards = Setbacks(front_ft=10.0, side_ft=5.0, rear_ft=20.0)
    assert buildable(lot, named, yards).area == pytest.approx(40 * 90, rel=1e-3)
    assert buildable(lot, edges, yards).area == pytest.approx(40 * 100, rel=1e-3)


def test_nothing_is_named_on_a_lot_that_is_not_a_through_lot() -> None:
    interior, bearings = at_gresham((0, 0, "F"), (50, 0, "S"), (50, 120, "R"), (0, 120, "S"))
    assert through_ends(edges_of(interior, bearings)) is None
    # An alley behind is not a street end.
    alley, _ = at_gresham((0, 0, "F"), (50, 0, "S"), (50, 120, "A"), (0, 120, "S"))
    assert through_ends(edges_of(alley, bearings)) is None
    # A 30 ft jog in one frontage is one street (1S2E15BB-02800).
    jog, _ = at_gresham(
        (0, 0, "F"), (40, 0, "F"), (40, 30, "F"), (80, 30, "S"), (80, 150, "R"), (0, 150, "S")
    )
    assert through_ends(edges_of(jog, bearings)) is None
    # A traced irregular lot is cut at its largest yard; nothing to name.
    through, _ = at_gresham((0, 0, "F"), (50, 0, "S"), (50, 120, "F"), (0, 120, "S"))
    assert through_ends(edges_of(through, bearings, Tier.irregular)) is None
    # A real corner keeps its corner reading.
    corner, _ = at_gresham((0, 0, "F"), (50, 0, "S"), (50, 120, "R"), (0, 120, "F"))
    assert through_ends(edges_of(corner, [GRESHAM_BEARING, GRESHAM_BEARING + 90.0])) is None


def test_each_word_offers_its_own_readings() -> None:
    raw, bearings = at_gresham((0, 0, "F"), (50, 0, "S"), (50, 120, "F"), (0, 120, "S"))
    edges = edges_of(raw, bearings)
    assert through_plans(edges, "both") == ((), False)
    owner, worst = through_plans(edges, "owner")
    assert not worst and len(owner) == 2
    assert all(sum(e.cls is EdgeClass.rear for e in r.edges) == 1 for r in owner)
    for rule in THROUGH_WORST:
        got, worst = through_plans(edges, rule)
        assert worst and len(got) == 3 and got[0] is edges


def test_the_rule_is_read_as_the_code_states_it(corpus) -> None:
    layers = corpus.layers
    want = {
        "or/multnomah/portland": "both",
        "or/multnomah/wood-village": "both",
        "or/clackamas/oregon-city": "both",
        "or/clackamas/wilsonville": "both",
        "or/clackamas/west-linn": "both",
        "or/clackamas/gladstone": "both",
        "or/multnomah/troutdale": "both",
        "or/multnomah/_unincorporated": "both",
        "or/clackamas/_unincorporated": "both_unless_no_access",
        "or/multnomah/gresham": "both_unless_no_access",
        "or/clackamas/happy-valley": "owner",
        "or/clackamas/milwaukie": "owner",
        # Silent in the stored code: screened at the worst reading.
        "or/clackamas/tualatin": None,
        "or/multnomah/fairview": None,
    }
    for layer_id, value in want.items():
        held = layers[layer_id].defaults.get("front_lot_line_through")
        assert (held.value if held is not None else None) == value, layer_id
    assert layers["or/multnomah/fairview"].zones["TCC"].values["front_lot_line_through"].value == "both"


# --- the screen -----------------------------------------------------------------


def screened(corpus, policies, **over: object):
    lot = lot_from_row(through_row(**over), corpus.layers)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    return s


def depth_cut(s) -> float:
    """How much of the lot's 100 ft depth the envelope lost at the two ends."""
    yards = s.envelope.setbacks
    return 100.0 - s.envelope.sqft / (50.0 - 2 * yards.side_ft)


def test_portland_cuts_both_ends_at_the_front_setback(corpus, policies) -> None:
    s = screened(corpus, policies, zone="R5")
    assert front_lot_line_through_rule(s.rules) == "both"
    assert [e.cls for e in s.lot.edges.edges].count(EdgeClass.front) == 2
    assert depth_cut(s) == pytest.approx(2 * s.envelope.setbacks.front_ft, abs=0.5)


def test_happy_valley_names_one_end_the_rear_where_the_rear_is_the_larger(corpus, policies) -> None:
    # HV 16.12: the owner chooses the front AND the rear. SFA states 10 ft
    # front, 15 ft rear: 25 ft of depth, not the 20 both fronts took.
    s = screened(corpus, policies, jurisdiction="happy_valley", zone="SFA")
    assert front_lot_line_through_rule(s.rules) == "owner"
    yards = s.envelope.setbacks
    assert (yards.front_ft, yards.rear_ft) == (10.0, 15.0)
    classes = [e.cls for e in s.lot.edges.edges]
    assert classes.count(EdgeClass.front) == 1 and classes.count(EdgeClass.rear) == 1
    assert depth_cut(s) == pytest.approx(25.0, abs=0.5)


def test_gresham_takes_the_worse_end_as_the_rear(corpus, policies) -> None:
    # GDC 3.0100: both fronts, unless an access control strip makes one the
    # rear -- which nothing measures. LDR-5 is 10 ft front, 20 ft rear.
    s = screened(corpus, policies, jurisdiction="gresham", zone="LDR-5")
    assert front_lot_line_through_rule(s.rules) == "both_unless_no_access"
    yards = s.envelope.setbacks
    assert yards.rear_ft > yards.front_ft
    assert depth_cut(s) == pytest.approx(yards.front_ft + yards.rear_ft, abs=0.5)


def test_an_unread_code_takes_the_worse_end_too(corpus, policies) -> None:
    # Fairview's residential districts state no through-lot rule. R-6 is
    # 10 ft front, 15 ft rear: both fronts was the lenient reading.
    s = screened(corpus, policies, jurisdiction="fairview", zone="R-6")
    assert front_lot_line_through_rule(s.rules) is None
    yards = s.envelope.setbacks
    assert depth_cut(s) == pytest.approx(yards.front_ft + max(yards.front_ft, yards.rear_ft), abs=0.5)
