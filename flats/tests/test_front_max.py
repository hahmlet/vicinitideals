"""A stated maximum front setback, held against the drawn building (FOLLOWUPS 147).

Before this, ``setback_front_max_ft`` was read only by the building-frontage
share, the flatter-ground search's cap and Portland's main-street overlay: a
zone that states a maximum and asks no share passed a building drawn 60 ft
back (Tigard 2S103AA00300, RES-B, maximum 20 ft, GREEN). Now the bridge
measures the drawn building's distance from every street
(:func:`flats.ingest.quadfit.front_max_streets`) and the screen holds it to
the maximum (:func:`flats.score.screen._front_max`):

* within the maximum on every street the code may reach -- passes;
* beyond it on every such street, or on any one where the code reaches every
  street (``setback_front_max_streets: every``) -- RED;
* between, where nothing says which street the code reaches, how much of the
  facade must stand within it, or a sidewalk easement may be measured from --
  held out of GREEN with MEASURE-FRONT-MAX-STREET, never passed;
* nothing drawn to measure -- held out of GREEN with MEASURE-FRONT-MAX-DRAWN.

Where the maximum alone holds the plan, the bridge looks for another window
within it (:func:`flats.ingest.quadfit.front_max_checked`).
"""

from __future__ import annotations

import dataclasses
import json
from types import SimpleNamespace

import pytest
import shapely
from shapely.geometry import box

from flats.encode.load import load_trusted
from flats.geom.edges import EdgeClass
from flats.ingest import quadfit
from flats.ingest.quadfit import front_max_streets, lot_from_row, screen_lot
from flats.score import relief, slack
from flats.score.flags import Colour
from flats.score.screen import (
    CHECK_FIELD,
    FRONT_MAX,
    FRONT_MAX_DRAWN,
    FRONT_MAX_STREET,
    _MEASURED_FLAG,
    front_max_owed,
)
from flats.score.slack import Verdict
from flats.tests.test_fire import X0, Y0, bridge_row
from flats.tests.test_round2_rulings import F, R, S, _edges, check, facts, rules, run

pytestmark = pytest.mark.unit

TIGARD = "or/washington/tigard"
PORTLAND = "or/multnomah/portland"
MAX = {"setback_front_max_ft": 20}


def codes(result) -> set[str]:
    return {f.code for f in result.flags}


def streets(*rows: tuple[bool, float, float, float]):
    return tuple(rows)


# --- the screen ---------------------------------------------------------------


def test_the_check_reads_the_maximum_and_has_a_flag_for_each_question() -> None:
    assert CHECK_FIELD[FRONT_MAX] == "setback_front_max_ft"
    assert _MEASURED_FLAG[FRONT_MAX_DRAWN] == "MEASURE-FRONT-MAX-DRAWN"
    assert _MEASURED_FLAG[FRONT_MAX_STREET] == "MEASURE-FRONT-MAX-STREET"


def test_a_building_within_the_maximum_passes() -> None:
    got = run(facts(front_max_streets=streets((True, 20.0, 20.0, 0.0)), front_max_tried=True), rules(**MAX))
    assert check(got, FRONT_MAX).verdict is Verdict.passes
    assert got.colour is Colour.green


def test_the_tigard_lot_drawn_60_ft_back_behind_a_20_ft_maximum_is_red() -> None:
    # 2S103AA00300: one street, the building drawn 60 ft from it.
    got = run(facts(front_max_streets=streets((True, 60.0, 60.0, 0.0)), front_max_tried=True), rules(**MAX))
    c = check(got, FRONT_MAX)
    assert c.verdict is Verdict.fails
    assert c.threshold == 20
    assert got.colour is Colour.red


def test_the_raster_cell_is_not_read_as_a_miss() -> None:
    # Minimum and maximum both 20 (Tigard Table 18.280.1): the raster stands
    # the building a fraction of a foot behind its envelope's edge.
    got = run(facts(front_max_streets=streets((True, 20.6, 20.6, 0.0)), front_max_tried=True), rules(**MAX))
    assert check(got, FRONT_MAX).verdict is Verdict.passes


def test_tried_with_nothing_drawn_is_held_never_passed() -> None:
    got = run(facts(front_max_tried=True), rules(**MAX))
    assert check(got, FRONT_MAX) is None
    assert "MEASURE-FRONT-MAX-DRAWN" in codes(got)
    assert got.colour is not Colour.green


def test_nobody_measuring_leaves_the_check_unrun_and_raises_nothing() -> None:
    got = run(facts(), rules(**MAX))
    assert check(got, FRONT_MAX) is None
    assert FRONT_MAX in got.unchecked
    assert not {"MEASURE-FRONT-MAX-DRAWN", "MEASURE-FRONT-MAX-STREET"} & codes(got)


def test_a_zone_with_a_building_share_is_measured_there_not_here() -> None:
    lot = facts(front_max_streets=streets((True, 60.0, 60.0, 0.0)), front_max_tried=True)
    got = run(lot, rules(building_frontage_min_pct=50, **MAX))
    assert check(got, FRONT_MAX) is None
    assert FRONT_MAX not in got.unchecked


CORNER = streets((True, 12.0, 12.0, 0.0), (False, 45.0, 45.0, 0.0))


def test_a_corner_within_on_one_street_is_a_question_where_nothing_says_which() -> None:
    got = run(facts(corner=True, front_max_streets=CORNER, front_max_tried=True), rules(**MAX))
    assert check(got, FRONT_MAX) is None
    assert "MEASURE-FRONT-MAX-STREET" in codes(got)
    assert got.colour is Colour.yellow


def test_every_street_fails_the_corner_beyond_on_its_side_street() -> None:
    got = run(
        facts(corner=True, front_max_streets=CORNER, front_max_tried=True),
        rules(setback_front_max_streets="every", **MAX),
    )
    c = check(got, FRONT_MAX)
    assert c.verdict is Verdict.fails
    assert c.observed == pytest.approx(44.0)


def test_the_front_alone_passes_the_corner_within_on_its_front() -> None:
    got = run(
        facts(corner=True, front_max_streets=CORNER, front_max_tried=True),
        rules(setback_front_max_streets="front", **MAX),
    )
    assert check(got, FRONT_MAX).verdict is Verdict.passes


def test_two_fronts_leave_the_front_unheld() -> None:
    two = streets((True, 12.0, 12.0, 0.0), (True, 45.0, 45.0, 0.0))
    lot = facts(front_max_streets=two, front_max_tried=True)
    assert front_max_owed(rules(setback_front_max_streets="front", **MAX), lot)[0] == "unheld"


def test_any_one_street_passes_on_the_one_within_and_fails_only_beyond_on_all() -> None:
    one = rules(setback_front_max_streets="one", **MAX)
    assert check(run(facts(corner=True, front_max_streets=CORNER, front_max_tried=True), one), FRONT_MAX).verdict is Verdict.passes
    both = streets((True, 30.0, 30.0, 0.0), (False, 45.0, 45.0, 0.0))
    assert check(run(facts(corner=True, front_max_streets=both, front_max_tried=True), one), FRONT_MAX).verdict is Verdict.fails


def test_corner_every_reads_both_streets_of_a_corner_and_leaves_a_through_lot_unheld() -> None:
    rule = rules(setback_front_max_streets="corner_every", **MAX)
    assert check(run(facts(corner=True, front_max_streets=CORNER, front_max_tried=True), rule), FRONT_MAX).verdict is Verdict.fails
    through = streets((True, 12.0, 12.0, 0.0), (True, 70.0, 70.0, 0.0))
    got = run(facts(front_max_streets=through, front_max_tried=True), rule)
    assert check(got, FRONT_MAX) is None
    assert "MEASURE-FRONT-MAX-STREET" in codes(got)


def test_a_wall_turned_from_the_street_needs_the_share_the_code_states() -> None:
    # Nearest corner 10 ft, far end of the facing wall 40 ft.
    turned = streets((True, 10.0, 40.0, 0.0))
    plain = run(facts(front_max_streets=turned, front_max_tried=True), rules(**MAX))
    assert check(plain, FRONT_MAX) is None
    assert "MEASURE-FRONT-MAX-STREET" in codes(plain)
    # Half the facade within 20: 10 + 0.5 * 30 = 25 > 20 on the stated share.
    half = run(facts(front_max_streets=turned, front_max_tried=True), rules(setback_front_max_facade_pct=50, **MAX))
    assert check(half, FRONT_MAX).verdict is Verdict.fails
    # A third: 10 + 10 = 20, within.
    third = run(facts(front_max_streets=turned, front_max_tried=True), rules(setback_front_max_facade_pct=33, **MAX))
    assert check(third, FRONT_MAX).verdict is Verdict.passes


def test_a_sidewalk_easement_the_maximum_may_be_measured_from_is_a_question() -> None:
    # 24 ft from the line, 7 ft of easement: 17 from the easement line.
    eased = streets((True, 24.0, 24.0, 7.0))
    got = run(facts(front_max_streets=eased, front_max_tried=True), rules(**MAX))
    assert check(got, FRONT_MAX) is None
    assert "MEASURE-FRONT-MAX-STREET" in codes(got)


# --- the measure --------------------------------------------------------------


def _drawn(building, edges, *, dedication: float = 0.0, easement: float | None = None):
    if dedication:
        edges = dataclasses.replace(
            edges,
            edges=tuple(
                dataclasses.replace(e, dedication_ft=dedication)
                if e.cls in (EdgeClass.front, EdgeClass.street_side) else e
                for e in edges.edges
            ),
        )
    lot = SimpleNamespace(edges=edges, zone="RES-B", sidewalk_easement_ft=easement)
    return SimpleNamespace(
        drawing={"fits": True, "building": [list(p) for p in building.exterior.coords]},
        lot=lot,
        envelope=None,
        rules=rules(**MAX),
    )


INTERIOR = _edges([(0, 0, 80, 0, F), (80, 0, 80, 200, S), (80, 200, 0, 200, R), (0, 200, 0, 0, S)], [0.0])
CORNER_EDGES = _edges([(0, 0, 80, 0, F), (80, 0, 80, 200, S), (80, 200, 0, 200, R), (0, 200, 0, 0, S)], [0.0, 90.0])


def test_the_measure_takes_the_nearest_wall_from_each_street() -> None:
    got = front_max_streets(_drawn(box(10, 60, 66, 96), INTERIOR))
    assert got == ((True, 60.0, 60.0, 0.0),)


def test_a_wall_turned_from_the_street_is_measured_at_its_far_end() -> None:
    turned = shapely.affinity.rotate(box(20, 30, 76, 66), 20, origin=(20, 30))
    ((_, near, far, _),) = front_max_streets(_drawn(turned, INTERIOR))
    assert near == pytest.approx(30.0, abs=0.01)
    assert far > near + 15


def test_a_dedicated_strip_moves_the_line_measured_from() -> None:
    s = _drawn(box(10, 30, 66, 66), INTERIOR, dedication=10.0)
    # quadfit's own envelope gave no strip up: the lot's line.
    assert front_max_streets(s)[0][1] == pytest.approx(30.0)
    # FLATS's envelope gave the strip up: measured from the line it leaves.
    s.envelope = SimpleNamespace(source="flats")
    assert front_max_streets(s)[0][1] == pytest.approx(20.0)


def test_the_easement_is_the_lenient_reading_alone() -> None:
    ((_, near, _, slack_ft),) = front_max_streets(_drawn(box(10, 24, 66, 60), INTERIOR, easement=7.0))
    assert (near, slack_ft) == (24.0, 7.0)


def test_nothing_fitting_is_nothing_measured() -> None:
    s = _drawn(box(10, 60, 66, 96), INTERIOR)
    s.drawing["fits"] = False
    assert front_max_streets(s) is None


# --- the corpus ---------------------------------------------------------------


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


@pytest.mark.parametrize("zone", ["RES-A", "RES-B", "RES-C", "RES-D", "RES-E", "MUR", "MU-CBD"])
def test_tigard_holds_every_street_line_to_its_maximum(corpus, zone) -> None:
    got = corpus.resolve(TIGARD, zone)
    assert got.get("setback_front_max_streets") == "every"


def test_tigard_states_the_facade_share_in_its_downtown_and_triangle(corpus) -> None:
    assert corpus.resolve(TIGARD, "MU-CBD").get("setback_front_max_facade_pct") == 50
    tmu = corpus.resolve(TIGARD, "TMU")
    assert tmu.get("setback_front_max_facade_pct") == 70
    # Every street unless met on one and 35 ft from the rest: not run.
    assert tmu.get("setback_front_max_streets") is None


@pytest.mark.parametrize("zone", ["CR", "CM1", "CM2", "CM3", "CX"])
def test_portland_reads_both_streets_of_a_corner_and_half_the_facade(corpus, zone) -> None:
    got = corpus.resolve(PORTLAND, zone)
    assert got.get("setback_front_max_streets") == "corner_every"
    assert got.get("setback_front_max_facade_pct") == 50


def test_portland_ce_leaves_its_streets_unread(corpus) -> None:
    got = corpus.resolve(PORTLAND, "CE")
    assert got.get("setback_front_max_facade_pct") == 50
    assert got.get("setback_front_max_streets") is None


# --- the bridge ---------------------------------------------------------------


DEEP = 220.0
WIDE = 110.0


def tigard_row() -> dict[str, object]:
    edges = [
        [X0, Y0, X0 + WIDE, Y0, "F"],
        [X0 + WIDE, Y0, X0 + WIDE, Y0 + DEEP, "S"],
        [X0 + WIDE, Y0 + DEEP, X0, Y0 + DEEP, "R"],
        [X0, Y0 + DEEP, X0, Y0, "S"],
    ]
    return bridge_row(
        TLID="2S103AA  -99999",
        jurisdiction="tigard",
        zone="RES-B",
        area_sqft=WIDE * DEEP,
        lot_depth_ft=DEEP,
        frontage_ft=WIDE,
        lot_width_ft=WIDE,
        edges_json=json.dumps(edges),
        wkb=shapely.to_wkb(box(X0 + 5, Y0 + 20, X0 + WIDE - 5, Y0 + DEEP - 25)),
        lot_wkb=shapely.to_wkb(box(X0, Y0, X0 + WIDE, Y0 + DEEP)),
    )


def screened(corpus, policies):
    lot = lot_from_row(tigard_row(), corpus.layers)
    (s,) = screen_lot(lot, [quadfit_design()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    return s


def quadfit_design():
    from flats.tests.test_fire import DESIGN

    return DESIGN


def test_the_bridge_measures_the_drawn_building_against_the_maximum(corpus, policies) -> None:
    s = screened(corpus, policies)
    assert s.facts.front_max_tried
    assert s.facts.front_max_streets
    assert check(s.signed, FRONT_MAX) is not None or FRONT_MAX in s.signed.unchecked


def test_a_building_drawn_far_back_is_moved_within_the_maximum(corpus, policies, monkeypatch) -> None:
    real = quadfit.drawing_for
    pushed = {"done": False}

    def back(s, fitter, **kw):
        got = real(s, fitter, **kw)
        if kw or pushed["done"] or not got or not got.get("fits"):
            return got
        # The first drawing, at the street end, stood 40 ft further back.
        pushed["done"] = True
        moved = dict(got)
        for key in ("building", "lane", "court"):
            if got.get(key):
                moved[key] = [[x, y + 40.0] for x, y in got[key]]
        return moved

    monkeypatch.setattr(quadfit, "drawing_for", back)
    s = screened(corpus, policies)
    assert pushed["done"]
    ((_, near, _, _),) = s.facts.front_max_streets
    assert near <= 20.0 + 1.0
    assert check(s.signed, FRONT_MAX).verdict is Verdict.passes


def test_a_building_drawn_far_back_with_nowhere_else_is_red(corpus, policies, monkeypatch) -> None:
    real = quadfit.drawing_for

    def back(s, fitter, **kw):
        if "listing" in kw:
            return None  # no other window
        got = real(s, fitter, **kw)
        if kw or not got or not got.get("fits"):
            return got
        moved = dict(got)
        for key in ("building", "lane", "court"):
            if got.get(key):
                moved[key] = [[x, y + 40.0] for x, y in got[key]]
        return moved

    monkeypatch.setattr(quadfit, "drawing_for", back)
    s = screened(corpus, policies)
    c = check(s.signed, FRONT_MAX)
    assert c is not None and c.verdict is Verdict.fails
    assert s.signed.colour is Colour.red
