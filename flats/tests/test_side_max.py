"""A stated maximum side setback, held against every side wall of the drawn
building (FOLLOWUPS 170).

Hillsboro's SCR-MD and SCR-HD tables state "Side Yard (all structures) 5
feet" as a MAXIMUM beside the 5 ft minimum. Read until 2026-11-09 as one
wall, which the pod always meets; Steph ruled it both walls, "but we should
first check that parking can't encroach. If they can't, I'm good with yellow
and ask" (rulings.yaml ``2026-11-09-hillsboro-scr-side-max-both``). Nothing in
the code lets a driveway or parking stand in the side yard so the building may
stand farther off, so the bridge measures the drawn building from each side lot
line (:func:`flats.ingest.quadfit.side_max_gaps`) and the screen
(:func:`flats.score.screen._side_max`):

* within the maximum of every side line -- passes, the lot unchanged (the
  narrow alley lot, its court behind, the pod across it end-on);
* beyond it on any side line, or nothing drawn -- held out of GREEN with
  MEASURE-SIDE-MAX-BOTH, never failed (the lot with its drive beside the
  building fits only on the one-wall reading);
* nobody measured -- unrun, raises nothing.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from shapely.geometry import box

from flats.encode.load import load_trusted
from flats.ingest.quadfit import side_max_gaps
from flats.score.flags import Colour
from flats.score.screen import CHECK_FIELD, SIDE_MAX, SIDE_MAX_BOTH, _MEASURED_FLAG
from flats.score.slack import Verdict
from flats.tests.test_round2_rulings import F, R, S, _edges, check, facts, rules, run

pytestmark = pytest.mark.unit

HILLSBORO = "or/washington/hillsboro"
MAX = {"setback_side_max_ft": 5, "setback_side_ft": 5}


def codes(result) -> set[str]:
    return {f.code for f in result.flags}


# --- the screen ---------------------------------------------------------------


def test_the_check_reads_the_maximum_and_has_a_flag_for_the_question() -> None:
    assert CHECK_FIELD[SIDE_MAX] == "setback_side_max_ft"
    assert _MEASURED_FLAG[SIDE_MAX_BOTH] == "MEASURE-SIDE-MAX-BOTH"


def test_the_alley_lot_with_both_walls_within_the_maximum_is_unchanged() -> None:
    # A 40 ft alley lot: the court behind off the alley, the 30 ft end of the
    # pod across the lot, 5 ft to each side line.
    lot = facts(alley_at_rear=True, side_max_gaps=(5.0, 5.0), side_max_tried=True)
    got = run(lot, rules(**MAX))
    assert check(got, SIDE_MAX).verdict is Verdict.passes
    assert "MEASURE-SIDE-MAX-BOTH" not in codes(got)
    assert got.colour is run(lot, rules(setback_side_ft=5)).colour


def test_the_lot_with_its_drive_beside_the_building_is_yellow_and_asks() -> None:
    # No alley: the drive to the court runs down one side, so that wall
    # stands 17 ft off its side line. GREEN on the one-wall reading.
    lot = facts(side_max_gaps=(5.0, 17.0), side_max_tried=True)
    assert run(lot, rules(setback_side_ft=5)).colour is Colour.green
    got = run(lot, rules(**MAX))
    assert check(got, SIDE_MAX) is None
    assert SIDE_MAX in got.unchecked
    assert "MEASURE-SIDE-MAX-BOTH" in codes(got)
    assert got.colour is Colour.yellow


@pytest.mark.parametrize(
    ("gaps", "asks"),
    [
        # SCR-DNC: 10 ft minimum held, 15 ft maximum. A drive beside the
        # building inside 15 ft passes; one that pushes the wall past it asks.
        ((10.0, 14.5), False),
        ((10.0, 22.0), True),
        # Each wall within 15 but the pair 31 apart: no placement holds both.
        ((15.5, 15.5), True),
    ],
)
def test_the_scr_dnc_15_ft_maximum_reads_the_same_way(gaps, asks) -> None:
    dnc = {"setback_side_max_ft": 15, "setback_side_ft": 10}
    got = run(facts(side_max_gaps=gaps, side_max_tried=True), rules(**dnc))
    assert ("MEASURE-SIDE-MAX-BOTH" in codes(got)) is asks
    assert got.colour is (Colour.yellow if asks else Colour.green)


def test_a_wall_far_beyond_the_maximum_is_never_red() -> None:
    got = run(facts(side_max_gaps=(40.0, 40.0), side_max_tried=True), rules(**MAX))
    assert got.colour is Colour.yellow


def test_one_wall_gets_the_raster_cell_but_a_facing_pair_does_not() -> None:
    # One side line (a corner lot): a slide toward it is always open.
    assert check(run(facts(side_max_gaps=(5.8,), side_max_tried=True), rules(**MAX)), SIDE_MAX)
    one = run(facts(side_max_gaps=(6.5,), side_max_tried=True), rules(**MAX))
    assert "MEASURE-SIDE-MAX-BOTH" in codes(one)
    # Two facing lines 11 ft apart in all: a slide toward one is a slide away
    # from the other, so no placement stands both within 5 ft.
    pair = run(facts(side_max_gaps=(5.5, 5.5), side_max_tried=True), rules(**MAX))
    assert check(pair, SIDE_MAX) is None
    assert "MEASURE-SIDE-MAX-BOTH" in codes(pair)


def test_tried_with_nothing_drawn_is_held_never_passed() -> None:
    got = run(facts(side_max_tried=True), rules(**MAX))
    assert check(got, SIDE_MAX) is None
    assert "MEASURE-SIDE-MAX-BOTH" in codes(got)
    assert got.colour is not Colour.green


def test_nobody_measuring_leaves_the_check_unrun_and_raises_nothing() -> None:
    got = run(facts(), rules(**MAX))
    assert check(got, SIDE_MAX) is None
    assert SIDE_MAX in got.unchecked
    assert "MEASURE-SIDE-MAX-BOTH" not in codes(got)


def test_a_lot_with_no_side_line_owes_nothing() -> None:
    got = run(facts(side_max_gaps=(), side_max_tried=True), rules(**MAX))
    assert "MEASURE-SIDE-MAX-BOTH" not in codes(got)
    assert SIDE_MAX not in got.unchecked


def test_a_zone_with_no_side_maximum_is_not_read() -> None:
    got = run(facts(side_max_gaps=(5.0, 17.0), side_max_tried=True), rules(setback_side_ft=5))
    assert check(got, SIDE_MAX) is None
    assert SIDE_MAX not in got.unchecked


# --- the measure --------------------------------------------------------------


def _drawn(building, edges):
    return SimpleNamespace(
        drawing={"fits": True, "building": [list(p) for p in building.exterior.coords]},
        lot=SimpleNamespace(edges=edges),
    )


def test_the_measure_takes_each_side_line() -> None:
    narrow = _edges([(0, 0, 40, 0, F), (40, 0, 40, 120, S), (40, 120, 0, 120, R), (0, 120, 0, 0, S)], [0.0])
    assert side_max_gaps(_drawn(box(5, 10, 35, 90), narrow)) == (5.0, 5.0)
    wide = _edges([(0, 0, 52, 0, F), (52, 0, 52, 120, S), (52, 120, 0, 120, R), (0, 120, 0, 0, S)], [0.0])
    assert sorted(side_max_gaps(_drawn(box(5, 10, 35, 90), wide))) == [5.0, 17.0]


def test_a_side_line_in_pieces_is_one_line_and_a_wrapped_run_too() -> None:
    # The left side line drawn in two pieces, and the ring starting part way
    # along it, so the run wraps the ring's start.
    jog = _edges(
        [
            (0, 60, 0, 0, S),
            (0, 0, 40, 0, F),
            (40, 0, 40, 120, S),
            (40, 120, 0, 120, R),
            (0, 120, 0, 60, S),
        ],
        [0.0],
    )
    assert side_max_gaps(_drawn(box(5, 10, 35, 90), jog)) == (5.0, 5.0)


def test_nothing_drawn_measures_nothing() -> None:
    narrow = _edges([(0, 0, 40, 0, F), (40, 0, 40, 120, S), (40, 120, 0, 120, R), (0, 120, 0, 0, S)], [0.0])
    s = SimpleNamespace(drawing={"fits": False}, lot=SimpleNamespace(edges=narrow))
    assert side_max_gaps(s) is None


# --- the encoding -------------------------------------------------------------


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


@pytest.mark.parametrize("zone", ["SCR-MD", "SCR-HD"])
def test_hillsboro_station_zones_state_the_5_ft_side_maximum(corpus, zone) -> None:
    got = corpus.resolve(HILLSBORO, zone)
    assert got.get("setback_side_max_ft") == 5
    assert got.get("setback_side_ft") == 5


def test_scr_dnc_states_the_15_ft_side_maximum_on_both_walls(corpus) -> None:
    # Steph 2026-11-10, rulings.yaml 2026-11-10-hillsboro-scr-dnc-side-max-both.
    assert corpus.resolve(HILLSBORO, "SCR-DNC").get("setback_side_max_ft") == 15


def test_scr_ld_is_not_encoded_with_one(corpus) -> None:
    # "interior lot line None; along Street or Alley 5 feet": a street-side
    # maximum, not the both-walls question.
    assert corpus.resolve(HILLSBORO, "SCR-LD").get("setback_side_max_ft") is None


# --- the bridge ---------------------------------------------------------------


def _hillsboro_row(wide: float, deep: float) -> dict[str, object]:
    import json

    import shapely

    from flats.tests.test_fire import X0, Y0, bridge_row

    edges = [
        [X0, Y0, X0 + wide, Y0, "F"],
        [X0 + wide, Y0, X0 + wide, Y0 + deep, "S"],
        [X0 + wide, Y0 + deep, X0, Y0 + deep, "R"],
        [X0, Y0 + deep, X0, Y0, "S"],
    ]
    return bridge_row(
        TLID="1N2W99AA  -99999",
        jurisdiction="hillsboro",
        zone="SCR-MD",
        area_sqft=wide * deep,
        lot_depth_ft=deep,
        frontage_ft=wide,
        lot_width_ft=wide,
        edges_json=json.dumps(edges),
        wkb=shapely.to_wkb(box(X0 + 5, Y0 + 5, X0 + wide - 5, Y0 + deep - 10)),
        lot_wkb=shapely.to_wkb(box(X0, Y0, X0 + wide, Y0 + deep)),
    )


def test_the_bridge_measures_the_final_drawing_from_each_side_line(corpus) -> None:
    from flats.ingest.quadfit import lot_from_row, screen_lot
    from flats.score import relief, slack
    from flats.tests.test_fire import DESIGN

    lot = lot_from_row(_hillsboro_row(110.0, 160.0), corpus.layers)
    (s,) = screen_lot(
        lot, [DESIGN], rules=corpus, policy=slack.load_policy(), relief=relief.load_policy(), step_deg=30.0
    )
    assert s.facts.side_max_tried
    if not (s.drawing or {}).get("fits"):
        pytest.skip("nothing drawn on this fixture")
    gaps = s.facts.side_max_gaps
    assert gaps is not None and len(gaps) == 2
    # 110 ft wide, an 80 by 30 ft pod: no placement stands both walls within
    # 5 ft, so the lot asks and is never GREEN on either reading.
    assert sum(gaps) > 10.0
    for r in (s.screening, s.signed):
        assert "MEASURE-SIDE-MAX-BOTH" in codes(r)
        assert r.colour is not Colour.green
