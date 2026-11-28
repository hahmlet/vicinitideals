"""Portland's multi-dwelling maximum front setback, held only on a transit
street or in a Pedestrian District (FOLLOWUPS 205 item 1).

Table 120-4 prints "Maximum Setbacks / Transit Street or Pedestrian District"
(RM1-RM3 20 ft, RM4 and RX 10 ft; 33.120.206.txt#L58-L61), and 33.120.220.C.1
holds it on the transit street frontages outside a district and on every
street frontage inside one (#L76-L117). Until 2026-11-27 no screen held it, and 49
GREEN RM lots of run 134 stood their drawn building past it on a mapped
transit street.

* a lot no transit street and no district reaches owes nothing;
* a reached street within the maximum passes;
* beyond it is held out of GREEN, never failed: the porch counted with the
  facade (C.1.a(3)) and the applicant's pick of street can still clear it;
* a lot line nothing calls a street line that may be a transit street, or a
  lot off the maps, is held.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from shapely.geometry import LineString, box

from flats.geom import pdx_transit as pt
from flats.ingest import quadfit
from flats.rules.loader import AREAS_ROOT, load_rules
from flats.rules.resolver import RuleSet
from flats.score.flags import Colour
from flats.score.screen import FRONT_MAX, TRANSIT_OR_DISTRICT, front_max_owed
from flats.score.slack import Verdict
from flats.tests.test_pdx_transit import _map
from flats.tests.test_round2_rulings import SS, F, R, S, _edges, check, facts, rules, run

pytestmark = pytest.mark.unit

PDX = "or/multnomah/portland"
RULE = {
    "setback_front_max_ft": 20,
    "setback_front_max_facade_pct": 50,
    "setback_front_max_streets": TRANSIT_OR_DISTRICT,
}


def codes(result) -> set[str]:
    return {f.code for f in result.flags}


def _run(streets, reach, *, hidden: bool = False):
    lot = facts(
        front_max_streets=streets,
        front_max_tried=True,
        front_max_reach=reach,
        front_max_reach_hidden=hidden,
    )
    return run(lot, rules(**RULE))


# --- the encoding -------------------------------------------------------------


@pytest.mark.parametrize(("zone", "cap"), [("RM1", 20), ("RM2", 20), ("RM3", 20), ("RM4", 10), ("RX", 10), ("CI1", 20)])
def test_table_120_4_maximum_is_held_on_transit_streets_and_districts(zone: str, cap: int) -> None:
    got = RuleSet(load_rules()).resolve(PDX, zone)
    assert got.get("setback_front_max_ft") == cap
    assert got.get("setback_front_max_facade_pct") == 50
    assert got.get("setback_front_max_streets") == TRANSIT_OR_DISTRICT


def test_rmp_prints_no_maximum() -> None:
    assert RuleSet(load_rules()).resolve(PDX, "RMP").get("setback_front_max_ft") is None


# --- the screen ---------------------------------------------------------------


def test_a_lot_no_transit_street_or_district_reaches_owes_nothing() -> None:
    got = _run(((True, 60.0, 60.0, 0.0),), (False,))
    assert front_max_owed(rules(**RULE), facts(front_max_streets=((True, 60.0, 60.0, 0.0),), front_max_reach=(False,)))[0] == "none"
    assert check(got, FRONT_MAX) is None
    assert FRONT_MAX not in got.unchecked
    assert got.colour is Colour.green


def test_nothing_drawn_on_a_lot_no_street_reaches_is_not_held() -> None:
    lot = facts(front_max_streets=None, front_max_tried=True, front_max_reach=(False, False))
    got = run(lot, rules(**RULE))
    assert FRONT_MAX not in got.unchecked
    assert got.colour is Colour.green


def test_nothing_drawn_on_a_reached_lot_is_held() -> None:
    lot = facts(front_max_streets=None, front_max_tried=True, front_max_reach=(True,))
    got = run(lot, rules(**RULE))
    assert "MEASURE-FRONT-MAX-DRAWN" in codes(got)
    assert got.colour is Colour.yellow


def test_a_transit_street_within_the_maximum_passes() -> None:
    # Half the facade within 20 ft: near 15, far 25 -> 20.
    got = _run(((True, 15.0, 25.0, 0.0),), (True,))
    assert check(got, FRONT_MAX).verdict is Verdict.passes
    assert got.colour is Colour.green


@pytest.mark.parametrize("near", [22.5, 60.0])
def test_beyond_it_on_a_transit_street_is_held_never_failed(near: float) -> None:
    got = _run(((True, near, near, 0.0),), (True,))
    assert check(got, FRONT_MAX) is None
    assert "MEASURE-FRONT-MAX-STREET" in codes(got)
    assert not got.binds
    assert got.colour is Colour.yellow


def test_only_the_reached_street_is_measured() -> None:
    # A corner: the transit street within the maximum, the quiet street 60 ft off.
    got = _run(((True, 10.0, 10.0, 0.0), (False, 60.0, 60.0, 0.0)), (True, False))
    assert check(got, FRONT_MAX).verdict is Verdict.passes
    assert got.colour is Colour.green
    # Both reached (a Pedestrian District): the quiet street is held.
    both = _run(((True, 10.0, 10.0, 0.0), (False, 60.0, 60.0, 0.0)), (True, True))
    assert both.colour is Colour.yellow


def test_a_hidden_transit_line_holds_even_a_clear_lot() -> None:
    got = _run(((True, 60.0, 60.0, 0.0),), (False,), hidden=True)
    assert "MEASURE-FRONT-MAX-STREET" in codes(got)
    assert got.colour is Colour.yellow


def test_off_the_maps_every_street_is_held() -> None:
    got = _run(((True, 60.0, 60.0, 0.0),), None)
    assert "MEASURE-FRONT-MAX-STREET" in codes(got)
    assert not got.binds
    assert got.colour is Colour.yellow
    assert _run(((True, 10.0, 10.0, 0.0),), None).colour is Colour.green


# --- the maps -----------------------------------------------------------------


def test_the_held_districts_are_the_whole_layer() -> None:
    import json

    data = json.loads((AREAS_ROOT / pt.PEDESTRIAN).read_text(encoding="utf-8"))
    assert len(data["features"]) == data["source"]["count"] == 43
    d = pt.load_districts()
    assert len(d.names) == 43
    assert {"Hollywood", "Gateway Regional Center", "St. Johns"} <= set(d.names)


LOT = box(0, 0, 80, 120)
INTERIOR = _edges([(0, 0, 80, 0, F), (80, 0, 80, 120, S), (80, 120, 0, 120, R), (0, 120, 0, 0, S)], [0.0])
CORNER = _edges([(0, 0, 80, 0, F), (80, 0, 80, 120, SS), (80, 120, 0, 120, R), (0, 120, 0, 0, S)], [0.0, 90.0])
NO_DISTRICT = pt.Districts((), ())
DISTRICT = pt.Districts(("Hollywood",), (box(70, 100, 500, 500),))
DIVISION = (LineString([(-200, -30), (300, -30)]), "SE DIVISION ST", "TA")


def _chains(edges):
    return quadfit._front_max_chains(edges)


def test_the_reach_reads_each_street_on_the_map() -> None:
    tm = _map(DIVISION)
    assert pt.front_max_reach(tm, NO_DISTRICT, LOT, _chains(INTERIOR), INTERIOR) == ((True,), False)
    assert pt.front_max_reach(_map(), NO_DISTRICT, LOT, _chains(INTERIOR), INTERIOR) == ((False,), False)
    # A corner: Division reaches the front only.
    reach, hidden = pt.front_max_reach(tm, NO_DISTRICT, LOT, _chains(CORNER), CORNER)
    assert sorted(reach) == [False, True] and not hidden


def test_a_lot_touching_a_district_owes_it_on_every_street() -> None:
    reach, _ = pt.front_max_reach(_map(), DISTRICT, LOT, _chains(CORNER), CORNER)
    assert reach == (True, True)


def test_a_transit_street_behind_a_line_nothing_calls_a_street_is_hidden() -> None:
    # Division runs 30 ft past the rear line of a deep lot, beyond the front
    # line's reach: the rear may be its frontage.
    deep = box(0, 0, 80, 200)
    edges = _edges([(0, 0, 80, 0, F), (80, 0, 80, 200, S), (80, 200, 0, 200, R), (0, 200, 0, 0, S)], [0.0])
    behind = (LineString([(-200, 230), (300, 230)]), "SE DIVISION ST", "TA")
    assert pt.front_max_reach(_map(behind), NO_DISTRICT, deep, _chains(edges), edges) == ((False,), True)


def test_off_the_map_nothing_is_read() -> None:
    far = box(9000, 9000, 9080, 9120)
    assert pt.front_max_reach(_map(), NO_DISTRICT, far, _chains(INTERIOR), INTERIOR) == (None, False)
    assert pt.front_max_reach(None, NO_DISTRICT, LOT, _chains(INTERIOR), INTERIOR) == (None, False)


# --- the bridge ---------------------------------------------------------------


def _screened(rule: dict, jurisdiction: str = "portland"):
    return SimpleNamespace(
        rules=rules(**rule),
        lot=SimpleNamespace(jurisdiction=jurisdiction, lot_geom=LOT, edges=INTERIOR, zone="RM1"),
        street_edges=None,
        envelope=None,
    )


def test_the_bridge_reads_the_reach_only_for_this_rule(monkeypatch) -> None:
    monkeypatch.setattr(quadfit.pdx, "transit_map", lambda j: _map(DIVISION) if j == "portland" else None)
    monkeypatch.setattr(pt, "load_districts", lambda: NO_DISTRICT)
    assert quadfit.front_max_reach(_screened(RULE)) == ((True,), False)
    # Another city, or another reading of which streets: nothing read.
    assert quadfit.front_max_reach(_screened(RULE, "gresham")) == (None, False)
    other = {**RULE, "setback_front_max_streets": "every"}
    assert quadfit.front_max_reach(_screened(other)) == (None, False)


def test_the_flatter_search_is_capped_only_where_a_street_is_reached(monkeypatch) -> None:
    from flats.ingest import flatter

    s = SimpleNamespace(rules=rules(**RULE), drawing={"building": [list(p) for p in box(10, 30, 66, 66).exterior.coords]})
    street = ((0.0, 0.0, 80.0, 0.0),)
    monkeypatch.setattr(quadfit, "front_max_reach", lambda s: ((True,), False))
    assert flatter._max_front_ft(s, street) == pytest.approx(30.0)
    monkeypatch.setattr(quadfit, "front_max_reach", lambda s: ((False,), True))
    assert flatter._max_front_ft(s, street) == pytest.approx(30.0)
    monkeypatch.setattr(quadfit, "front_max_reach", lambda s: ((False,), False))
    assert flatter._max_front_ft(s, street) is None
