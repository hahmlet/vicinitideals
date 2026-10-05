"""Gresham's sidewalk easement, taken at its worst (Steph, 2026-10-05).

Table 4.0131 note 1 measures every setback from a sidewalk easement line
where the walk runs on one, and nothing says where it does. So every lot is
read as though it did, as deep as the city's standards could put one: 7 ft
behind a line on a street Metro types local, 20 ft behind any other.
"""

from __future__ import annotations

import json

import pytest
from shapely.geometry import LineString

from flats.geom.sidewalk import (
    DEPTHS,
    SIDEWALK_EASEMENT,
    build,
    depth_for,
    easement_depth_ft,
    easement_shifted,
    observed_sidewalk_easement,
)
from flats.rules.conditions import CONDITIONS

GRESHAM = "or/multnomah/gresham"

# Main St (local, 1500) runs east along y=0; Burnside (arterial, 1300) runs
# north along x=400.
MAIN = LineString([(-200, 0), (400, 0)])
BURNSIDE = LineString([(400, -200), (400, 400)])
STREETS = build([MAIN, BURNSIDE], ["", ""], [1500, 1300])

ON_MAIN = [100.0, 20.0, 200.0, 20.0, "F"]
ON_BURNSIDE = [380.0, 100.0, 380.0, 200.0, "F"]
NOWHERE = [100.0, 300.0, 200.0, 300.0, "F"]
SIDE = [100.0, 20.0, 100.0, 120.0, "S"]


@pytest.fixture(scope="module")
def corpus():
    from flats.rules.loader import load_rules
    from flats.rules.resolver import RuleSet

    return RuleSet(load_rules())


def test_a_local_street_line_takes_the_local_walk() -> None:
    depth = DEPTHS[GRESHAM]
    assert easement_depth_ft([ON_MAIN, SIDE], depth, STREETS) == depth.local_ft == 7.0


def test_any_other_street_and_any_unread_line_takes_the_deepest() -> None:
    depth = DEPTHS[GRESHAM]
    assert easement_depth_ft([ON_BURNSIDE], depth, STREETS) == depth.other_ft == 20.0
    assert easement_depth_ft([NOWHERE], depth, STREETS) == 20.0
    assert easement_depth_ft([ON_MAIN], depth, None) == 20.0
    # A corner takes its deepest line on every street setback.
    assert easement_depth_ft([ON_MAIN, ON_BURNSIDE], depth, STREETS) == 20.0


def test_a_lot_with_no_street_line_is_left_unasked() -> None:
    assert easement_depth_ft([SIDE], DEPTHS[GRESHAM], STREETS) is None
    assert observed_sidewalk_easement(None) == {}
    assert observed_sidewalk_easement(7.0) == {SIDEWALK_EASEMENT: True}


def test_only_gresham_holds_a_depth() -> None:
    assert depth_for(GRESHAM) == DEPTHS[GRESHAM]
    assert depth_for("or/clackamas/wilsonville") is None
    assert depth_for(None) is None
    assert CONDITIONS[SIDEWALK_EASEMENT].assume is None


def test_the_street_setbacks_start_at_the_easement_line(corpus) -> None:
    from flats.score.screen import held_open

    got = corpus.resolve(GRESHAM, "LDR-7", (SIDEWALK_EASEMENT,), lot={"lot_sqft": 10_000})
    assert SIDEWALK_EASEMENT in got.unencoded
    eased = easement_shifted(got, 7.0)
    for name in ("setback_front_ft", "setback_street_side_ft", "setback_garage_entrance_ft"):
        assert eased.get(name) == got.get(name) + 7.0
        assert eased.values[name].shadowed == got.get(name)
    # No sidewalk runs along a rear or interior side line.
    assert eased.get("setback_rear_ft") == got.get("setback_rear_ft")
    assert eased.get("setback_side_ft") == got.get("setback_side_ft")
    # The note has its number: a lot with the fact True is no longer held open on it.
    assert SIDEWALK_EASEMENT not in eased.unencoded

    class Config:
        conditions = (SIDEWALK_EASEMENT,)
        assumed = ()

    assert SIDEWALK_EASEMENT in held_open(got, Config())  # type: ignore[arg-type]
    assert SIDEWALK_EASEMENT not in held_open(eased, Config())  # type: ignore[arg-type]
    assert easement_shifted(got, None) is got


def test_a_code_without_the_note_is_untouched(corpus) -> None:
    got = corpus.resolve("or/multnomah/portland", "R5", (), lot={"lot_sqft": 5_000})
    eased = easement_shifted(got, 20.0)
    assert eased.get("setback_front_ft") == got.get("setback_front_ft")


def test_the_bridge_takes_the_depth_and_the_screen_measures_from_it(monkeypatch, tmp_path, corpus) -> None:
    import flats.ingest.quadfit as bridge

    monkeypatch.setattr(bridge, "load_streets", lambda sources, bounds: STREETS)
    rows = [
        {"TLID": "local", "jurisdiction": "gresham", "edges_json": json.dumps([ON_MAIN, SIDE])},
        {"TLID": "arterial", "jurisdiction": "gresham", "edges_json": json.dumps([ON_BURNSIDE])},
        {"TLID": "elsewhere", "jurisdiction": "milwaukie", "edges_json": json.dumps([ON_MAIN])},
    ]
    assert bridge.with_sidewalk_easement(rows, tmp_path) == 2
    got = {r["TLID"]: r for r in rows}
    assert got["local"]["sidewalk_easement_ft"] == 7.0
    assert got["arterial"]["sidewalk_easement_ft"] == 20.0
    assert "sidewalk_easement_ft" not in got["elsewhere"]
    assert bridge.observed_facts(got["local"])[SIDEWALK_EASEMENT] is True
    assert SIDEWALK_EASEMENT not in bridge.observed_facts(got["elsewhere"])
    assert bridge.with_sidewalk_easement(rows, None) == 0

    eased = bridge._Eased(corpus, 7.0)
    plain = corpus.resolve(GRESHAM, "LDR-7", (SIDEWALK_EASEMENT,), lot={"lot_sqft": 10_000})
    moved = eased.resolve(GRESHAM, "LDR-7", (SIDEWALK_EASEMENT,), lot={"lot_sqft": 10_000})
    assert moved.get("setback_front_ft") == plain.get("setback_front_ft") + 7.0


def test_without_the_street_file_the_fact_stays_unasked(monkeypatch, tmp_path) -> None:
    import flats.ingest.quadfit as bridge

    monkeypatch.setattr(bridge, "load_streets", lambda sources, bounds: None)
    rows = [{"TLID": "local", "jurisdiction": "gresham", "edges_json": json.dumps([ON_MAIN])}]
    assert bridge.with_sidewalk_easement(rows, tmp_path) == 0
    assert SIDEWALK_EASEMENT not in bridge.observed_facts(rows[0])


def test_a_screened_gresham_lot_is_cut_from_the_easement_line() -> None:
    from flats.encode.load import load_trusted
    from flats.ingest.quadfit import lot_from_row, screen_lot
    from flats.score import relief, slack
    from flats.tests.test_quadfit_bridge import pod4, row
    from flats.tests.test_worst_bound import BIG

    rules = load_trusted(strict=False).rules
    policy, grant = slack.load_policy(), relief.load_policy()

    def screened(**over):
        lot = lot_from_row(row(**{**BIG, "jurisdiction": "gresham", "zone": "LDR-7", **over}))
        (s,) = screen_lot(lot, [pod4()], rules=rules, policy=policy, relief=grant, step_deg=30.0)
        return s

    before, after = screened(), screened(sidewalk_easement_ft=7.0)
    assert after.rules.get("setback_front_ft") == before.rules.get("setback_front_ft") + 7.0
    codes = lambda s: {f.code for f in s.screening.flags}  # noqa: E731
    assert "FACT-SIDEWALK-EASEMENT" in codes(before)
    assert "FACT-SIDEWALK-EASEMENT" not in codes(after)
