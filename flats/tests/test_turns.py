"""The room a lane-fed court is given so a car can use every stall
(:mod:`flats.score.turns`).

Steph, 2026-10-02: *"THREE POINT is acceptable for now"*. The car of
:mod:`flats.fit.turning` decides, per court shape, how much deeper the
aisle, how much wider the stalls, or how far the aisle must run past the
row's far end before every stall can be used -- or how far past a smaller
deepening -- and the ledger holds the answers.
Steph, 2026-10-03: *"the 13 foot dead end should be almost a last-resort
solution"* -- the fit takes the least paving the lot holds. These tests hold
the ledger to the corpus and the charge to the ledger -- not the answers,
which take minutes a shape to search and are re-searched by
``python -m flats.score.turns``.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
import shapely
import yaml

from flats.designs.model import Design
from flats.fit.rectangle import Fitter
from flats.fit.turning import TURN_FT
from flats.ingest.quadfit import _other_fixes
from flats.score import paper, turns
from flats.score.paper import Alley, court_across, court_depth, court_shape, paved
from flats.score.screen import Triage, fit_for
from flats.score.slack import Verdict
from flats.score.turns import AS_DRAWN, LEDGER, LEVERS, Fix, Shape, corpus_shapes

pytestmark = pytest.mark.unit

POD = """
version: 1
label: Four-plex pod
typology: townhome_rear_court
footprint: {width_ft: 56, depth_ft: 36}
units: 4
stories: 2
height_ft: 26
parking: {stalls_per_unit: 1.5, config: rear_court}
delivery: {method: modular, crane_required: true, crane_reach_ft: 60}
"""

#: The design's own court, and what the car asked of it on 2026-10-03.
OWN = Shape(4, 9.0, 18.0, 24.0, 12.0, 5.0)
DEEPER, WIDER, DEAD_END = Fix(aisle_ft=4.0), Fix(stall_ft=2.0), Fix(dead_end_ft=13.0)
#: A deepening short of the aisle's own answer, and a dead end to go with it.
MIXED = Fix(aisle_ft=2.0, dead_end_ft=6.0)


def pod() -> Design:
    return Design(**{**yaml.safe_load(POD), "id": "pod"})


class Rules:
    """A resolution stub: the numbers, and the fields the code exempts."""

    def __init__(self, *exempted: str, **values: object) -> None:
        self.values = values
        self.exempted = exempted

    def get(self, name: str) -> object:
        return self.values.get(name)


def offer(*found: Fix):
    return lambda shape: found


def test_the_ledger_holds_every_court_the_corpus_draws() -> None:
    """A rule change that brings a new court shape must bring its answers,
    every lever asked: regenerate with ``python -m flats.score.turns``."""
    data = json.loads(LEDGER.read_text(encoding="utf-8"))
    held = {row["shape"]: row for row in data["shapes"]}
    missing = sorted(s.key for s in corpus_shapes() if s.key not in held)
    assert not missing, f"run python -m flats.score.turns: {missing}"
    unasked = sorted(k for k, row in held.items() if set(LEVERS) - set(row))
    assert not unasked, f"run python -m flats.score.turns: {unasked}"
    unmixed = sorted(
        k
        for k, row in held.items()
        if {str(a) for a in turns.mixed_wanted(row)} - set(row.get("mixed", {}))
    )
    assert not unmixed, f"run python -m flats.score.turns: {unmixed}"


def test_the_ledger_was_searched_with_today_s_car() -> None:
    data = json.loads(LEDGER.read_text(encoding="utf-8"))
    assert data["turn_ft"] == TURN_FT
    assert data["fields"] == list(Shape._fields)
    assert data["levers"] == list(LEVERS)
    assert "THREE POINT" in data["rule"]


def test_the_corpus_courts_are_offered_the_ledger_s_fixes_least_paving_first() -> None:
    """Without a stub: every court the corpus draws is offered what the
    ledger holds for it, cheapest first, and a 12 ft lane leaves the row's
    far end too tight for the car as drawn (2026-10-02)."""
    ledger = {
        row["shape"]: row for row in json.loads(LEDGER.read_text(encoding="utf-8"))["shapes"]
    }
    for shape in corpus_shapes():
        found = turns.fixes(shape)
        assert not isinstance(found, turns.Unsearched)
        row = ledger[shape.key]
        if 0.0 in row.values():
            assert found == (AS_DRAWN,)
            continue
        held = {Fix(**{k: v}) for k, v in row.items() if k in LEVERS and v is not None}
        held |= {
            Fix(aisle_ft=float(a), dead_end_ft=d)
            for a, d in row.get("mixed", {}).items()
            if d is not None
        }
        assert set(found) <= held
        # Only a fix that asks at least as much of every lever is dropped.
        for fix in held - set(found):
            assert any(all(a <= b for a, b in zip(kept, fix)) for kept in found)
        cost = [turns.paving(shape, fix) for fix in found]
        assert cost == sorted(cost)
        if shape.lane_ft == 12:
            assert found and AS_DRAWN not in found


def test_the_design_s_own_court_is_not_given_the_dead_end_first() -> None:
    """Steph 2026-10-03: the 13 ft dead end is the last resort. The car
    swings round in an aisle 4 ft deeper (searched 2026-10-03: 25, 26 and
    27 ft were not enough) for less than half the paving; stalls 2 ft wider
    work too, and pave the most."""
    found = turns.fixes(OWN)
    assert not isinstance(found, turns.Unsearched)
    assert found[0] == DEEPER
    assert found.index(DEAD_END) < found.index(WIDER)
    assert all(fix.dead_end_ft < DEAD_END.dead_end_ft for fix in found[1 : found.index(DEAD_END)])
    assert turns.paving(OWN, DEEPER) - turns.paving(OWN, AS_DRAWN) == 4.0 * 36
    assert turns.paving(OWN, DEAD_END) - turns.paving(OWN, AS_DRAWN) == 13.0 * 24


def test_fixes_are_offered_least_paving_first(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        turns, "_LEDGER", {OWN.key: {"aisle_ft": 4.0, "stall_ft": 2.0, "dead_end_ft": 13.0}}
    )
    assert turns.fixes(OWN) == (DEEPER, DEAD_END, WIDER)
    monkeypatch.setattr(
        turns, "_LEDGER", {OWN.key: {"aisle_ft": None, "stall_ft": None, "dead_end_ft": 13.0}}
    )
    assert turns.fixes(OWN) == (DEAD_END,)
    monkeypatch.setattr(turns, "_LEDGER", {OWN.key: {"aisle_ft": 0.0}})
    assert turns.fixes(OWN) == (AS_DRAWN,)


def test_a_smaller_deepening_with_a_shorter_dead_end_is_offered_between(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A lot with a few feet to spare each way holds the two together where
    it holds neither alone. A combination asking at least as much of every
    lever as another fix is never the one a lot holds, and is not offered."""
    monkeypatch.setattr(
        turns,
        "_LEDGER",
        {
            OWN.key: {
                "aisle_ft": 4.0,
                "stall_ft": 2.0,
                "dead_end_ft": 13.0,
                "mixed": {"1": 13.0, "2": 6.0, "3": None},
            }
        },
    )
    assert turns.fixes(OWN) == (DEEPER, MIXED, DEAD_END, WIDER)


def test_a_mixed_fix_is_asked_only_between_two_answers() -> None:
    assert turns.mixed_wanted({"aisle_ft": 4.0, "stall_ft": 2.0, "dead_end_ft": 13.0}) == [1, 2, 3]
    assert turns.mixed_wanted({"aisle_ft": None, "stall_ft": None, "dead_end_ft": 20.0}) == []
    assert turns.mixed_wanted({"aisle_ft": 1.0, "stall_ft": 0.5, "dead_end_ft": 1.0}) == []
    assert turns.mixed_wanted(dict.fromkeys(LEVERS, 0.0)) == []


def test_a_deeper_aisle_is_charged_as_depth_and_paved(monkeypatch: pytest.MonkeyPatch) -> None:
    rules = Rules(setback_front_ft=10)
    monkeypatch.setattr(paper, "fixes", offer(AS_DRAWN))
    plain = court_across(pod(), rules)
    plain_depth = court_depth(pod(), rules)[0]
    plain_paved = paved(pod(), rules, deep_ft=36.0)
    monkeypatch.setattr(paper, "fixes", offer(DEEPER, DEAD_END))
    across = court_across(pod(), rules)
    assert across.fix == DEEPER and across.fixes == (DEEPER, DEAD_END)
    assert across.width_ft == plain.width_ft and across.dead_end_ft == 0.0
    assert court_depth(pod(), rules)[0] == plain_depth + 4.0
    extended = paved(pod(), rules, deep_ft=36.0)
    assert plain_paved is not None and extended is not None
    assert extended - plain_paved == pytest.approx(4.0 * plain.width_ft)


def test_the_dead_end_is_charged_as_width_and_paved_as_aisle(monkeypatch: pytest.MonkeyPatch) -> None:
    rules = Rules(setback_front_ft=10)
    monkeypatch.setattr(paper, "fixes", offer(AS_DRAWN))
    plain_depth = court_depth(pod(), rules)[0]
    plain = paved(pod(), rules, deep_ft=36.0)
    monkeypatch.setattr(paper, "fixes", offer(DEEPER, Fix(dead_end_ft=6.0)))
    across = court_across(pod(), rules, fix=Fix(dead_end_ft=6.0))
    assert across.dead_end_ft == 6.0
    assert across.width_ft == across.stalls * across.stall_ft + 6.0
    assert across.turns
    assert court_depth(pod(), rules, fix=across.fix)[0] == plain_depth
    extended = paved(pod(), rules, deep_ft=36.0, fix=across.fix)
    assert plain is not None and extended is not None
    assert extended - plain == pytest.approx(6.0 * pod().parking.aisle_ft)


def test_wider_stalls_are_charged_across_the_row(monkeypatch: pytest.MonkeyPatch) -> None:
    rules = Rules()
    monkeypatch.setattr(paper, "fixes", offer(AS_DRAWN))
    plain = court_across(pod(), rules)
    monkeypatch.setattr(paper, "fixes", offer(WIDER))
    across = court_across(pod(), rules)
    assert across.stall_ft == plain.stall_ft + 2.0
    assert across.width_ft == plain.width_ft + 2.0 * across.stalls


def test_a_fix_the_ledger_does_not_offer_is_not_taken(monkeypatch: pytest.MonkeyPatch) -> None:
    """A fit recorded under another ledger cannot charge a fix the car was
    not seen to drive: the court takes the least paving one that works."""
    monkeypatch.setattr(paper, "fixes", offer(DEAD_END))
    assert court_across(pod(), Rules(), fix=DEEPER).fix == DEAD_END


def test_a_court_no_fix_saves_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paper, "fixes", offer())
    across = court_across(pod(), Rules())
    assert not across.turns
    assert across.fix == AS_DRAWN


@pytest.mark.parametrize(
    ("envelope", "taken"),
    [
        # The pod's six stalls are a 54 ft row. 60 ft across holds it end-on
        # (wider than 36 + 12), not the row and its 13 ft dead end (67), nor
        # the pod broadside (56 + 12); 107 deep holds the pod's 56 and the
        # deeper court (5 + 18 + 28).
        ((60, 107), DEEPER),
        # 84 deep holds the pod broadside (36) and the court as drawn (47),
        # not one 2 ft deeper (49) or 4 (51); 80 across holds 56 + 12 and the
        # row with its dead end.
        ((80, 84), DEAD_END),
        # 105 deep is 2 ft short of the deeper court, 60 across 7 ft short of
        # the dead end; the court 2 ft deeper (5 + 18 + 26) with a 6 ft dead
        # end (54 + 6) fits both ways.
        ((60, 105), MIXED),
    ],
)
def test_the_fit_takes_the_least_paving_fix_the_lot_holds(
    monkeypatch: pytest.MonkeyPatch, envelope: tuple[float, float], taken: Fix
) -> None:
    monkeypatch.setattr(paper, "fixes", offer(DEEPER, MIXED, DEAD_END))
    fitter = Fitter(shapely.box(0, 0, *envelope), (0.0,), res=1.0)
    fit = fit_for(fitter, pod(), Rules())
    assert fit.court_fix == taken
    assert fit.slack_ft - (court_depth(pod(), Rules(), fix=taken)[0]) >= 0


def test_a_lot_no_fix_fits_keeps_the_nearest_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    """60 x 100: the deeper court is 7 ft short end-on; the dead end does
    not fit across at all. The near miss is the deeper aisle's."""
    monkeypatch.setattr(paper, "fixes", offer(DEEPER, DEAD_END))
    fitter = Fitter(shapely.box(0, 0, 60, 100), (0.0,), res=1.0)
    fit = fit_for(fitter, pod(), Rules())
    assert fit.court_fix == DEEPER
    assert fit.slack_ft - court_depth(pod(), Rules(), fix=DEEPER)[0] == pytest.approx(-7.0)


def test_the_shape_is_what_the_car_drives() -> None:
    """The lane less its walkway; the stall without its share of islands."""
    rules = Rules(
        driveway_min_width_two_way_ft=30,
        driveway_walkway_ft=5,
        parking_island_sqft_per_space=25,
        parking_stall_depth_ft=18.5,
        parking_aisle_two_way_ft=22,
    )
    shape = court_shape(pod(), rules)
    assert shape is not None
    assert shape[1:] == (9.0, 18.5, 22.0, 30.0, 5.0)
    assert shape.stalls == court_across(pod(), rules, turning=False).stalls


def test_a_court_without_a_lane_is_not_asked() -> None:
    """The alley or the side street is the way out; the lane's court is
    the only one the car is driven through."""
    rules = Rules(parking_alley_access_required=True)
    alley = Alley(at_rear=True, rear_whole=True, width_ft=16.0)
    across = court_across(pod(), rules, alley)
    assert across.lane_ft == 0.0
    assert across.turn_shape is None and across.fix == AS_DRAWN


def test_a_shape_missing_from_the_ledger_is_not_searched_at_screen_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A search is minutes to an hour; 16 workers meeting a lot's own
    variant shape stalled a county run (2026-10-03). The ledger answers or
    nobody does."""
    monkeypatch.setattr(turns, "_LEDGER", {})
    monkeypatch.setattr(turns, "solve", lambda *a: pytest.fail("searched at screen time"))
    assert turns.fixes(OWN) is turns.UNSEARCHED
    assert turns.parse(OWN.key) == OWN


def test_a_court_nobody_drove_is_unchecked_and_never_green(monkeypatch: pytest.MonkeyPatch) -> None:
    from flats.score.screen import FACT_UNOBSERVED, Triage
    from flats.tests.test_fire import check, facts, run

    monkeypatch.setattr(paper, "fixes", lambda shape: turns.UNSEARCHED)
    result = run(facts(fire_route_ft=140.0, fire_route_tried=True))
    assert check(result, "court_turns") is None
    assert "court_turns" in result.unchecked
    assert FACT_UNOBSERVED in result.reasons
    assert result.triage is not Triage.green


def test_a_court_the_car_cannot_use_is_red_and_no_relief_softens_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No fix lets a car use every stall: the lot fails on the court, and a
    variance does not widen a turn."""
    from flats.score.slack import Verdict
    from flats.score.screen import Triage
    from flats.tests.test_fire import check, facts, run

    monkeypatch.setattr(paper, "fixes", offer())
    result = run(facts(fire_route_ft=140.0, fire_route_tried=True))
    got = check(result, "court_turns")
    assert got is not None and got.verdict is Verdict.fails
    assert result.triage is Triage.red
    assert any(c.check == "court_turns" for c in result.binding)


def test_a_court_the_car_can_use_adds_no_check(monkeypatch: pytest.MonkeyPatch) -> None:
    from flats.score.screen import Triage
    from flats.tests.test_fire import check, facts, run

    monkeypatch.setattr(paper, "fixes", offer(AS_DRAWN))
    result = run(facts(fire_route_ft=140.0, fire_route_tried=True))
    assert check(result, "court_turns") is None
    assert result.triage is Triage.green


def _shadow(triage: str, *failing: str) -> SimpleNamespace:
    return SimpleNamespace(
        triage=Triage(triage),
        checks=tuple(SimpleNamespace(check=c, verdict=Verdict.fails) for c in failing),
    )


def _fitted(fix: Fix, **flags: bool) -> SimpleNamespace:
    return SimpleNamespace(court_fix=fix, beside=flags.get("beside", False), column=False)


@pytest.mark.parametrize(
    ("failing", "retried"),
    [
        (("open_space_shape",), True),
        (("landscaped_pct", "impervious_pct"), True),
        # The court that does not fit was every fix's nearest miss already.
        (("fit_ft",), False),
        # A rule the court's shape does not move fails whatever the court.
        (("open_space_shape", "height_ft"), False),
    ],
)
def test_a_fix_that_fits_but_fails_the_yard_tries_the_next(
    failing: tuple[str, ...], retried: bool
) -> None:
    """1S2E10DC-05500 (2026-10-03): the 16 ft dead end fits and leaves no
    outdoor square; another fix the car drove may. The next is taken only
    where it passes every rule."""
    asked: list[Fix] = []

    def refit(menu):
        asked.extend(menu)
        return _fitted(menu[0])

    def screened(fit):
        return "facts", "result", _shadow("green" if fit.court_fix == WIDER else "yellow")

    start = _fitted(DEAD_END)
    got = _other_fixes(
        start, "f", "r", _shadow("yellow", *failing), screened, refit, (DEEPER, DEAD_END, WIDER)
    )
    if retried:
        assert asked == [WIDER]
        assert got[0].court_fix == WIDER and got[3].triage is Triage.green
    else:
        assert asked == []
        assert got[0] is start


def test_no_other_fix_passing_keeps_the_least_paving() -> None:
    start = _fitted(DEEPER)
    got = _other_fixes(
        start,
        "f",
        "r",
        _shadow("yellow", "open_space_shape"),
        lambda fit: ("facts", "result", _shadow("yellow", "open_space_shape")),
        lambda menu: _fitted(menu[0]),
        (DEEPER, DEAD_END, WIDER),
    )
    assert got[0] is start
