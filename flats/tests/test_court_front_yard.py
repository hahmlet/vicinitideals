"""The parking court is kept out of the front yard (Steph 2026-11-08, rulings.yaml
``2026-11-08-no-front-yard-parking-silent-codes``; FOLLOWUPS 142).

Round 6 guarded the fire retry alone. Every placement now keeps the court out of
the yards :func:`flats.ingest.quadfit.court_yard_lines` names: the first drawing
(:func:`flats.fit.draw._place`), the listing the fire, flatter and front-maximum
searches choose from (:func:`flats.fit.draw._options`), the fire step's redraws,
and the final drawing (:func:`flats.ingest.quadfit.court_yard_checked`), which
holds a plan out of GREEN where nothing tried kept the court clear.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest
import shapely

from flats.encode.load import load_trusted
from flats.fit.draw import _between_boxes, court_between, draw
from flats.fit.rectangle import Fitter
from flats.geom.edges import Edge, EdgeClass, LotEdges, Tier
from flats.ingest.quadfit import (
    court_in_front_yard,
    court_yard_lines,
    lot_from_row,
    screen_lot,
)
from flats.score import relief, slack
from flats.score.screen import COURT_FRONT_YARD
from flats.tests.test_quadfit_bridge import X0, Y0, pod, row

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


# --- the geometry ---------------------------------------------------------------


def test_the_window_test_reads_what_the_drawing_test_reads() -> None:
    """The first drawing's vectorised test (:func:`_between_boxes`) answers
    as :func:`court_between` does, box for box, at any angle to the line."""
    rng = np.random.default_rng(142)
    for _ in range(600):
        bx0, by0 = rng.uniform(0, 100, 2)
        bx1, by1 = bx0 + rng.uniform(5, 60), by0 + rng.uniform(5, 60)
        cx0, cy0 = rng.uniform(-20, 120, 2)
        cx1, cy1 = cx0 + rng.uniform(5, 60), cy0 + rng.uniform(5, 60)
        lines = [tuple(rng.uniform(-50, 200, 4)) for _ in range(int(rng.integers(1, 3)))]
        fast = _between_boxes(
            tuple(np.array([v]) for v in (bx0, by0, bx1, by1)),
            tuple(np.array([v]) for v in (cx0, cy0, cx1, cy1)),
            np.array(lines),
        )[0]
        slow = court_between(
            shapely.box(bx0, by0, bx1, by1), shapely.box(cx0, cy0, cx1, cy1), lines
        )
        assert bool(fast) is slow


#: A 60 x 140 envelope with a street off each end: a through lot.
ENVELOPE = shapely.box(0, 0, 60, 140)
SOUTH = (0.0, -10.0, 60.0, -10.0)
NORTH = (60.0, 150.0, 0.0, 150.0)
EAST = (70.0, 0.0, 70.0, 140.0)


def _fit(envelope=ENVELOPE, *, lane=12.0):
    fitter = Fitter(envelope, angles=(0.0,))
    fit = fitter.fit(36.0, 40.0, allow_flip=False, placement=False, lane_ft=lane)
    return fitter, fit


def _behind(fitter, fit, street, yard=(), listing=None):
    return draw(
        fitter, fit, width_ft=36.0, depth_ft=40.0, lane_ft=12.0, court_depth_ft=30.0,
        court_beyond_ft=10.0, street=street, yard=yard, listing=listing,
    )


def test_an_interior_lot_draws_as_it_did() -> None:
    """One front: the court behind the building is clear of it, and the
    drawing is the one drawn before the yards were read."""
    fitter, fit = _fit()
    plain = _behind(fitter, fit, (SOUTH,))
    kept = _behind(fitter, fit, (SOUTH,), yard=(SOUTH,))
    assert kept.building.equals(plain.building) and kept.court.equals(plain.court)
    assert not court_between(kept.building, kept.court, (SOUTH,))


def test_a_through_lot_with_two_fronts_has_no_clear_window_and_says_so() -> None:
    """Both ends fronts: wherever the building stands, the court behind it
    faces the other street. The nearest window is still drawn, so the caller
    reads the court in the front yard; the listing holds nothing."""
    fitter, fit = _fit()
    got = _behind(fitter, fit, (SOUTH, NORTH), yard=(SOUTH, NORTH))
    assert got is not None and got.fits
    assert court_between(got.building, got.court, (SOUTH, NORTH))
    listed: list = []
    _behind(fitter, fit, (SOUTH, NORTH), yard=(SOUTH, NORTH), listing=listed)
    assert listed == []
    unguarded: list = []
    _behind(fitter, fit, (SOUTH, NORTH), listing=unguarded)
    assert unguarded


def test_the_far_end_named_rear_leaves_the_court_behind() -> None:
    """The owner names the far end the rear (Happy Valley, Milwaukie):
    only the front's yard is kept clear, and the court behind stands."""
    fitter, fit = _fit()
    got = _behind(fitter, fit, (SOUTH, NORTH), yard=(SOUTH,))
    assert not court_between(got.building, got.court, (SOUTH,))
    listed: list = []
    _behind(fitter, fit, (SOUTH, NORTH), yard=(SOUTH,), listing=listed)
    assert listed


def test_a_beside_court_turns_to_the_flank_away_from_a_front() -> None:
    """A court beside the building on a corner whose side street is a front
    too stands on the other flank: the same window, turned round."""
    fitter, fit = _fit(lane=20.0)

    def beside(yard):
        return draw(
            fitter, fit, width_ft=36.0, depth_ft=40.0, lane_ft=0.0, court_depth_ft=0.0,
            court_beyond_ft=0.0, street=(SOUTH,), beside_band_ft=20.0, beside_len_ft=40.0,
            yard=yard, yard_moves=False,
        )

    plain, kept = beside(()), beside((SOUTH, EAST))
    assert plain.court.centroid.x > plain.building.centroid.x
    assert court_between(plain.building, plain.court, (EAST,))
    assert kept.court.centroid.x < kept.building.centroid.x
    assert not court_between(kept.building, kept.court, (SOUTH, EAST))
    # The same distance from the street: not moved back.
    assert kept.building.bounds[1] == pytest.approx(plain.building.bounds[1])


# --- which yards count ----------------------------------------------------------


def _edges(*spec: tuple[float, float, float, float, EdgeClass]) -> LotEdges:
    return LotEdges(
        Tier.clean,
        tuple(Edge(x1, y1, x2, y2, 1.0, 0.0, cls) for x1, y1, x2, y2, cls in spec),
        (0.0,),
        50.0,
        1.0,
    )


class _Rules(dict):
    exempted: tuple[str, ...] = ()


F, S, R, SS = EdgeClass.front, EdgeClass.side, EdgeClass.rear, EdgeClass.street_side
CORNER = _edges((0, 0, 50, 0, F), (50, 0, 50, 100, SS), (50, 100, 0, 100, R), (0, 100, 0, 0, S))
THROUGH_BOTH = _edges((0, 0, 50, 0, F), (50, 0, 50, 100, S), (50, 100, 0, 100, F), (0, 100, 0, 0, S))
THROUGH_OWNER = _edges((0, 0, 50, 0, F), (50, 0, 50, 100, S), (50, 100, 0, 100, R), (0, 100, 0, 0, S))


def _plan(edges, *, ban=None, exempt=False, street_edges=None, access=()):
    rules = _Rules({} if ban is None else {"parking_front_prohibited": ban})
    if exempt:
        rules.exempted = ("parking_front_prohibited",)
    return SimpleNamespace(
        lot=SimpleNamespace(edges=edges, access=access), rules=rules, street_edges=street_edges
    )


def test_the_front_yard_is_every_front_line_and_no_side_street() -> None:
    assert court_yard_lines(_plan(CORNER)) == ((0, 0, 50, 0),)
    assert court_yard_lines(_plan(THROUGH_BOTH)) == ((0, 0, 50, 0), (50, 100, 0, 100))
    assert court_yard_lines(_plan(THROUGH_OWNER, street_edges=THROUGH_BOTH)) == ((0, 0, 50, 0),)


def test_a_ban_on_parking_before_the_building_reaches_every_street() -> None:
    """Portland 33.266.120.C.1.a, Milwaukie 19.505.3.D.4.a: "the street",
    the side street and a through lot's far end named rear included."""
    assert court_yard_lines(_plan(CORNER, ban=True)) == ((0, 0, 50, 0), (50, 0, 50, 100))
    got = court_yard_lines(_plan(THROUGH_OWNER, ban=True, street_edges=THROUGH_BOTH))
    assert got == ((0, 0, 50, 0), (50, 100, 0, 100))
    # Waived, the ban reaches nothing; the ruling keeps the front yard.
    assert court_yard_lines(_plan(CORNER, ban=True, exempt=True)) == ((0, 0, 50, 0),)


def test_a_private_road_makes_a_front_yard_only_where_the_city_counts_it() -> None:
    """Steph 2026-09-30: a private road is a way in for parking and governs
    setbacks only where the city counts it. A road the yards ignore
    (``lot.access``) makes no front yard, so the court may face it; a road the
    city counts is a front edge of that reading and does."""
    road = (0.0, 100.0, 50.0, 100.0)
    lot = _edges((0, 0, 50, 0, F), (50, 0, 50, 100, S), (50, 100, 0, 100, R), (0, 100, 0, 0, S))
    assert court_yard_lines(_plan(lot, access=(road,))) == ((0, 0, 50, 0),)
    counted = _edges((0, 0, 50, 0, F), (50, 0, 50, 100, S), (50, 100, 0, 100, F), (0, 100, 0, 0, S))
    assert court_yard_lines(_plan(counted)) == ((0, 0, 50, 0), (50, 100, 0, 100))
    # where the code bans parking toward the street, the ignored road still is not one
    assert court_yard_lines(_plan(lot, ban=True, access=(road,))) == ((0, 0, 50, 0),)


# --- the screen -----------------------------------------------------------------


def _through(depth: float, far: str):
    edges = [
        [X0, Y0, X0 + 60, Y0, "F"],
        [X0 + 60, Y0, X0 + 60, Y0 + depth, "S"],
        [X0 + 60, Y0 + depth, X0, Y0 + depth, far],
        [X0, Y0 + depth, X0, Y0, "S"],
    ]
    return row(
        edges_json=json.dumps(edges),
        front_bearings_json="[0.0, 180.0]" if far == "F" else "[0.0]",
        frontage_ft=60.0,
        lot_width_ft=60.0,
        lot_depth_ft=depth,
        area_sqft=60.0 * depth,
        wkb=shapely.to_wkb(shapely.box(X0 + 5, Y0 + 10, X0 + 55, Y0 + depth - 10)),
        lot_wkb=shapely.to_wkb(shapely.box(X0, Y0, X0 + 60, Y0 + depth)),
    )


def test_a_through_lot_whose_court_faces_the_far_front_is_held_out_of_green(
    corpus, policies
) -> None:
    """Portland makes both ends of a through lot fronts (33.910): the court
    behind the building stands in the far street's front yard, nothing at
    60 ft wide turns it clear, and the lot is held out of GREEN. The same
    lot with a rear line behind carries no hold."""
    from flats.score.flags import Colour

    kw = dict(rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    (through,) = screen_lot(lot_from_row(_through(160.0, "F"), corpus.layers), [pod()], **kw)
    (interior,) = screen_lot(lot_from_row(_through(160.0, "R"), corpus.layers), [pod()], **kw)
    assert interior.drawing and interior.drawing["fits"]
    assert not court_in_front_yard(interior)
    assert COURT_FRONT_YARD not in interior.screening.reasons
    if not (through.drawing and through.drawing.get("fits")):
        pytest.skip("the through lot draws no fitting plan")
    assert court_in_front_yard(through)
    assert through.facts.court_front_yard
    assert through.signed.colour is not Colour.green
    assert any(f.code == "PARKING-COURT-FRONT-YARD" for f in through.screening.flags)


def _green_plan(corpus, court):
    from flats.fit.rectangle import Fit
    from flats.ingest.quadfit import Screened
    from flats.score.screen import LotFacts, screen
    from flats.score.slack import SlackPolicy
    from flats.tests.test_rear_court_setback import screen_rules

    rules = screen_rules(yard_prohibited=False, doubt=None)
    lot = lot_from_row(row(), corpus.layers)
    design = pod()
    fit = Fit(fits=True, width_ft=56, depth_ft=36, best_depth_ft=120, slack_ft=84, across_ft=100, stalls=6)
    facts = LotFacts(lot_sqft=20_000, frontage_ft=100, lot_width_ft=100, lot_depth_ft=200)
    policy = SlackPolicy(tolerance={"fit_ft": 0.5})
    first = screen(rules, facts, design, fit, policy=policy)
    ring = [list(p) for p in shapely.box(X0 + 5, Y0 + 15, X0 + 41, Y0 + 50).exterior.coords]
    drawing = {"fits": True, "building": ring, "court": [list(p) for p in court.exterior.coords]}
    s = Screened(
        lot=lot, design=design, rules=rules, config=None, fit=fit, screening=first, signed=first,
        angles=1, step_deg=5.0, envelope=None, front_deg=0.0, drawing=drawing, facts=facts,
    )
    return s, policy


def test_the_court_finally_drawn_in_the_front_yard_holds_a_green_out(corpus) -> None:
    from flats.ingest.quadfit import court_yard_checked
    from flats.score.screen import Triage

    ahead = shapely.box(X0 + 5, Y0 + 2, X0 + 41, Y0 + 12)
    s, policy = _green_plan(corpus, ahead)
    assert s.screening.triage is Triage.green
    out = court_yard_checked(s, policy=policy, relief=None)
    assert out.facts.court_front_yard
    assert out.screening.triage is not Triage.green
    assert COURT_FRONT_YARD in out.screening.reasons
    assert any(f.code == "PARKING-COURT-FRONT-YARD" for f in out.screening.flags)
    # Behind the building: nothing to hold, and a hold set before lifts.
    behind = shapely.box(X0 + 5, Y0 + 50, X0 + 41, Y0 + 80)
    clear, _ = _green_plan(corpus, behind)
    assert court_yard_checked(clear, policy=policy, relief=None) is clear
    import dataclasses

    stale = dataclasses.replace(out, drawing=clear.drawing)
    lifted = court_yard_checked(stale, policy=policy, relief=None)
    assert not lifted.facts.court_front_yard
    assert lifted.screening.triage is Triage.green


def test_the_reason_has_words() -> None:
    from app.api.routers.ui_flats import _REASON_WORDS

    assert COURT_FRONT_YARD in _REASON_WORDS
