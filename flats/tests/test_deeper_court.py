"""A deeper court carried from the standard court's measured paths (FOLLOWUPS 216).

Steph 2026-11-27 (rulings.yaml ``2026-11-27-deeper-court-passes``): where the
stair-room re-placement sets the rear court deeper behind the building, the
deeper court passes wherever the standard court's measured turn passes -- the
car's path carried along the extra straight drive and checked step by step --
and only then. A failed carry, a different shape, or no measured standard
entry stays unsearched (MEASURE-COURT-TURNS), never a pass and never an
"unusable" the car was not asked about.

Only questions the search answers in seconds are asked here (one stall over
the lane, straight in and straight out); the court searches are the ledger's.
"""

from __future__ import annotations

import json
import math

import pytest

from flats.fit import turning
from flats.fit.turning import Court, Pose, carried_in, carried_out, deeper_by, parked_pose, route
from flats.score import turns
from flats.score.turns import AS_DRAWN, Fix, Shape

pytestmark = pytest.mark.unit

#: One stall standing right over a 9 ft lane: the car drives straight in,
#: and backed in drives straight out. Searched in well under a second.
OVER = Court(stalls=1, lane_ft=9.0)
STANDARD = Shape(4, 9.0, 18.0, 24.0, 12.0, 5.0)
DEEPER = STANDARD._replace(gap_ft=6.25)
SAVES = {"aisle_ft": 4.0, "stall_ft": 2.0, "dead_end_ft": 13.0}
NONE_SAVES = {"aisle_ft": None, "stall_ft": None, "dead_end_ft": None}


def straight_in(court: Court) -> list[Pose]:
    stall = court.stall(0)
    goal = parked_pose(stall)
    path = route(court.ground(0), court.street_end(), turning.parked_in(stall, goal.heading), (1,),
                 toward=(goal.x, goal.y))
    assert path is not None
    return path


def straight_out(court: Court) -> list[Pose]:
    start = parked_pose(court.stall(0), nose_out=True)
    path = route(court.ground(0), start, court.gone, (1,), toward=(court.lane_ft / 2, -court.lane_len_ft + 10.0))
    assert path is not None
    return path


def test_the_path_kept_is_the_path_the_search_drove() -> None:
    """``route`` is ``drive`` remembering its way: the same answer, and every
    pose it hands back is on the ground, from the start to an accepted end."""
    path = straight_in(OVER)
    stall = OVER.stall(0)
    assert turning.drive(OVER.ground(0), OVER.street_end(), turning.parked_in(stall, math.pi / 2), (1,))
    assert path[0] == OVER.street_end()
    assert turning._on(OVER.ground(0), path)
    assert turning.parked_in(stall, math.pi / 2)(path[-1])


def test_only_a_deeper_standoff_is_carried() -> None:
    deeper = Court(stalls=1, lane_ft=9.0, gap_ft=6.25)
    assert deeper_by(OVER, deeper) == pytest.approx(1.25)
    assert deeper_by(OVER, OVER) is None
    assert deeper_by(deeper, OVER) is None, "a shallower court is not carried onto"
    assert deeper_by(OVER, Court(stalls=1, lane_ft=10.0, gap_ft=6.25)) is None, "a different lane"
    assert deeper_by(OVER, Court(stalls=1, lane_ft=9.0, gap_ft=6.25, aisle_ft=20.0)) is None


@pytest.mark.parametrize("gap", [5.33, 6.25, 7.17, 8.08, 9.0])
def test_the_standard_court_s_path_carries_onto_the_deeper_court(gap: float) -> None:
    deeper = Court(stalls=1, lane_ft=9.0, gap_ft=gap)
    assert carried_in(straight_in(OVER), OVER, deeper, 0, math.pi / 2)
    assert carried_out(straight_out(OVER), OVER, deeper, 0, nose_out=True)


def test_a_path_that_does_not_start_where_the_deeper_court_does_is_not_carried() -> None:
    deeper = Court(stalls=1, lane_ft=9.0, gap_ft=6.25)
    # Found from somewhere else than the standard court's street end: it
    # does not meet the straight lead-in.
    path = straight_in(OVER)
    late = [Pose(p.x, p.y + 1.5, p.heading) for p in path]
    assert not carried_in(late, OVER, deeper, 0, math.pi / 2)
    # Started from the wrong pose: not the deeper court's parked car.
    assert not carried_out(straight_out(OVER), OVER, deeper, 0, nose_out=False)
    # A court that is not a deeper standoff of the standard one.
    assert not carried_in(path, OVER, Court(stalls=1, lane_ft=10.0, gap_ft=6.25), 0, math.pi / 2)
    assert not carried_in(path, OVER, OVER, 0, math.pi / 2)


def test_a_carried_path_off_the_deeper_court_s_ground_is_not_carried() -> None:
    """Every pose is tested again: a path that leaves the deeper court's own
    ground fails, whatever the standard court said."""
    deeper = Court(stalls=1, lane_ft=9.0, gap_ft=6.25)
    path = straight_in(OVER)
    off = [path[0], *(Pose(p.x + 3.0, p.y, p.heading) for p in path[1:-1]), path[-1]]
    assert not carried_in(off, OVER, deeper, 0, math.pi / 2)


def test_a_departure_angled_near_the_lane_s_edge_steers_up_the_lane() -> None:
    """The run-out up the extra lane: where driving straight on at the last
    heading would graze the lane's edge, the car steers forward up the lane
    (found on the deeper court's ground). Seen 2026-11-27 on
    4|8.5|18|20|12 (+1 ft aisle, 15 ft dead end): a backed-in car leaves
    stall 3 at 7 degrees, 0.8 ft off the lane's middle."""
    standard = Court(stalls=1, lane_ft=12.0)
    deeper = Court(stalls=1, lane_ft=12.0, gap_ft=9.0)
    # Straight out of the stall, then a last pose angled 9 degrees toward
    # the lane's edge, just past the line ``gone`` draws.
    end = Pose(5.8, -11.2, -math.pi / 2 - math.radians(9.0))
    path = [*straight_out(standard)[:-1], end]
    assert standard.gone(end)
    moved = Pose(end.x, end.y + 4.0, end.heading)
    assert turning._on(deeper.ground(0), [moved]) and not deeper.gone(moved)
    assert not turning._on(deeper.ground(0), turning._straight(moved, 4.6)), "straight on grazes the edge"
    assert carried_out(path, standard, deeper, 0, nose_out=True)


def test_usable_deeper_takes_the_way_whose_paths_carry(monkeypatch: pytest.MonkeyPatch) -> None:
    """The car's two ways, as :func:`turning.usable`: here the nose-in way
    finds no path, so the backed-in way's paths are carried."""
    monkeypatch.setattr(turning, "arrival", lambda c, i, phases, nose_out=False: (
        _backed_in(c) if nose_out else None))
    monkeypatch.setattr(turning, "departure", lambda c, i, phases, nose_out=False: (
        straight_out(c) if nose_out else pytest.fail("the nose-in way had no arrival")))
    deepers = [Court(stalls=1, lane_ft=9.0, gap_ft=g) for g in (6.25, 9.0)]
    assert turning.usable_deeper(OVER, deepers, 0) == [True, True]
    assert turning.usable_deeper(OVER, [Court(stalls=1, lane_ft=10.0, gap_ft=6.25)], 0) == [False]


def test_usable_deeper_is_false_where_the_standard_court_gives_no_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(turning, "arrival", lambda *a, **k: None)
    monkeypatch.setattr(turning, "departure", lambda *a, **k: pytest.fail("no arrival, nothing to leave"))
    assert turning.usable_deeper(OVER, [Court(stalls=1, lane_ft=9.0, gap_ft=6.25)], 0) == [False]


def _backed_in(court: Court) -> list[Pose]:
    """A backed-in arrival on ``court``: in straight, then the car turned
    about on the spot is the parked, backed-in car. Not a drive -- only a
    path :func:`carried_in` can test, start to parked end."""
    path = straight_in(court)
    goal = parked_pose(court.stall(0), nose_out=True)
    return [*path, goal]


# -- the ledger --------------------------------------------------------------


@pytest.fixture(autouse=True)
def _ledger_restored(monkeypatch: pytest.MonkeyPatch) -> None:
    """``carry_main`` reloads the module's ledger: put the real one back."""
    monkeypatch.setattr(turns, "_LEDGER", turns._LEDGER)


def test_a_deeper_court_passes_on_a_passing_standard_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    """A carried row offers the standard row's fixes that carried, least
    paving first, as a searched row does."""
    monkeypatch.setattr(turns, "_LEDGER", {
        STANDARD.key: dict(SAVES),
        DEEPER.key: {"carried": [[4.0, 0.0, 0.0], [0.0, 2.0, 0.0], [0.0, 0.0, 13.0]], "from": STANDARD.key},
    })
    assert turns.measured(DEEPER) == STANDARD
    assert turns.fixes(DEEPER) == turns.fixes(STANDARD)
    monkeypatch.setitem(turns._LEDGER, DEEPER.key, {"carried": [[0.0, 0.0, 0.0]], "from": STANDARD.key})
    assert turns.fixes(DEEPER) == (AS_DRAWN,)


def test_a_carried_row_with_no_fix_that_carried_is_unsearched_not_unusable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(turns, "_LEDGER", {DEEPER.key: {"carried": [], "from": STANDARD.key}})
    assert turns.fixes(DEEPER) is turns.UNSEARCHED


def test_a_deeper_court_with_a_failing_or_missing_standard_entry_stays_unmeasured(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    ledger = tmp_path / "court_turns.json"
    monkeypatch.setattr(turns, "LEDGER", ledger)
    other = Shape(2, 9.0, 18.0, 20.0, 9.0, 5.0)
    rows = [{"shape": STANDARD.key, **SAVES}, {"shape": other.key, **NONE_SAVES}]
    turns._write(rows, [])
    monkeypatch.setattr(turns, "carry", lambda std, deeper, fix: [True] * len(deeper))
    fails = other._replace(gap_ft=6.25)
    missing = Shape(4, 9.0, 18.0, 20.0, 10.0, 6.25)
    shallower = STANDARD._replace(gap_ft=4.0)
    out = turns.carry_main({DEEPER, fails, missing, shallower}, rows, processes=1)
    assert [r["shape"] for r in out] == [DEEPER.key]
    assert out[0]["from"] == STANDARD.key
    assert turns.fixes(DEEPER) == turns.fixes(STANDARD)
    for shape in (fails, missing, shallower):
        assert turns.measured(shape) is None
        assert turns.fixes(shape) is turns.UNSEARCHED
    data = json.loads(ledger.read_text(encoding="utf-8"))
    assert [r["shape"] for r in data["shapes"]] == [STANDARD.key, other.key], "searched rows untouched"


def test_a_fix_that_does_not_carry_is_not_offered(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(turns, "LEDGER", tmp_path / "court_turns.json")
    rows = [{"shape": STANDARD.key, **SAVES}]
    turns._write(rows, [])
    monkeypatch.setattr(turns, "carry", lambda std, deeper, fix: [fix != Fix(aisle_ft=4.0)] * len(deeper))
    out = turns.carry_main({DEEPER}, rows, processes=1)
    assert out[0]["not_carried"] == [[4.0, 0.0, 0.0]]
    assert Fix(aisle_ft=4.0) not in turns.fixes(DEEPER)
    assert set(turns.fixes(DEEPER)) == {Fix(stall_ft=2.0), Fix(dead_end_ft=13.0)}
    # None carries: unsearched, not "no fix saves it".
    monkeypatch.setattr(turns, "carry", lambda std, deeper, fix: [False] * len(deeper))
    turns.carry_main({DEEPER}, rows, processes=1, fresh=True)
    assert turns.fixes(DEEPER) is turns.UNSEARCHED


def test_a_carried_row_is_kept_while_its_standard_row_still_offers_its_fixes(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(turns, "LEDGER", tmp_path / "court_turns.json")
    rows = [{"shape": STANDARD.key, **SAVES}]
    turns._write(rows, [])
    monkeypatch.setattr(turns, "carry", lambda std, deeper, fix: [True] * len(deeper))
    turns.carry_main({DEEPER}, rows, processes=1)
    monkeypatch.setattr(turns, "carry", lambda *a: pytest.fail("carried again"))
    assert [r["shape"] for r in turns.carry_main(set(), rows, processes=1)] == [DEEPER.key]
    # The standard row searched again and no longer saved by the dead end:
    # the carried row rests on an answer the ledger no longer gives.
    changed = [{"shape": STANDARD.key, **SAVES, "dead_end_ft": None}]
    turns._write(changed)
    monkeypatch.setattr(turns, "carry", lambda std, deeper, fix: [True] * len(deeper))
    out = turns.carry_main(set(), changed, processes=1)
    assert Fix(dead_end_ft=13.0) not in turns.fixes(DEEPER)
    assert out[0]["fixes"] == [[0.0, 2.0, 0.0], [4.0, 0.0, 0.0]]


def test_the_ledger_s_carried_rows_rest_on_searched_rows_that_offer_them() -> None:
    """Every carried row in the committed ledger is a deeper standoff of a
    searched row, and offers no fix that row does not."""
    data = json.loads(turns.LEDGER.read_text(encoding="utf-8"))
    searched = {r["shape"] for r in data["shapes"]}
    for row in data.get("carried", []):
        deeper, std = turns.parse(row["shape"]), turns.parse(row["from"])
        assert row["from"] in searched and row["shape"] not in searched
        assert deeper[:5] == std[:5] and deeper.gap_ft > std.gap_ft
        offered = turns.fixes(std)
        assert not isinstance(offered, turns.Unsearched) and offered
        assert all(Fix(*f) in offered for f in row["fixes"])
        assert sorted(row["fixes"] + row["not_carried"]) == sorted(list(f) for f in offered)
