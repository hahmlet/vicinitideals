"""The maximum front setback, street by named street, on real lots (FOLLOWUPS 147 round 4).

The bound of 0f5a2a52 left 25 false GREENs: a run of lot line along two named
streets read as one street, because the top two directions were under the
corner test's 45 degrees or were not the two streets, and the building was
measured only from the nearer. Steph's ruling of 2026-10-09 makes one street
NAME on one unbroken run the bend, so two names are never one.

The fixture is real: Metro's taxlot polygons and street centrelines (RLIS
2026-11), the edges quadfit's s4 cuts from them, and the building the bridge
drew on each lot.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import shapely
from shapely.geometry import LineString, Polygon

from flats.designs.model import load_catalog
from flats.encode.load import load_trusted
from flats.geom import street_names
from flats.geom.corridor import Lines
from flats.geom.edges import EdgeClass
from flats.ingest import quadfit
from flats.ingest.quadfit import (
    front_max_corner,
    front_max_streets,
    lot_edges,
    lot_from_row,
    screen_lot,
)
from flats.score import relief, slack
from flats.score.flags import Colour
from flats.score.screen import FRONT_MAX, front_max_owed
from flats.score.slack import Verdict
from flats.tests.test_fire import bridge_row
from flats.tests.test_round2_rulings import F, R, S, _edges, check, facts, rules, run

pytestmark = pytest.mark.unit

FIXTURE = Path(__file__).parent / "fixtures" / "front_max_real_lots.json"
LOTS = json.loads(FIXTURE.read_text(encoding="utf-8"))["lots"]
PORTLAND = "or/multnomah/portland"
TIGARD = "or/washington/tigard"
FAIRVIEW = "or/multnomah/fairview"


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


def centrelines(tlid: str) -> Lines:
    held = LOTS[tlid]["centrelines"]
    return Lines.build([LineString(c) for _, c in held], [n for n, _ in held])


def row_of(tlid: str) -> dict:
    row = dict(LOTS[tlid]["row"])
    row["lot_wkb"] = shapely.from_wkb(row.pop("lot_wkb_hex")).wkb
    row["street_names_json"] = json.dumps(
        street_names.read(json.loads(row["edges_json"]), centrelines(tlid))
    )
    return row


def edges_of(tlid: str):
    return lot_edges(row_of(tlid))


def drawn(tlid: str, design: str):
    edges = edges_of(tlid)
    return SimpleNamespace(
        drawing={"fits": True, "building": LOTS[tlid]["drawn"][design]},
        lot=SimpleNamespace(edges=edges, zone=LOTS[tlid]["row"]["zone"], sidewalk_easement_ft=None),
        street_edges=None,
        envelope=None,
        rules=rules(setback_front_max_ft=20),
    )


def screened(tlid: str, design: str, rule):
    s = drawn(tlid, design)
    lot = facts(
        corner=False,
        front_max_streets=front_max_streets(s),
        front_max_tried=True,
        front_max_corner=front_max_corner(s),
    )
    return lot, run(lot, rule)


def names_of(chains) -> list[set[str | None]]:
    return [{e.street_name for e in chain} for chain in chains]


# --- reading the names --------------------------------------------------------


@pytest.mark.parametrize(
    ("tlid", "named"),
    [
        ("1S135DC02000", {"91ST AVE", "LINCOLN AVE"}),
        ("1S1E20CB08200", {"HUME ST", "GARDEN HOME RD"}),
        ("1N2E19AD11600", {"CULLY BLVD", "60TH AVE"}),
        ("1N1W12BD06400", {"SALEM AVE", "BURLINGTON AVE"}),
    ],
)
def test_each_street_line_reads_the_street_it_lies_on(tlid, named) -> None:
    got = {e.street_name for e in edges_of(tlid).edges} - {None}
    assert got == named


def test_a_street_named_two_ways_round_the_city_is_one_name() -> None:
    line = Lines.build([LineString([(0, 30), (500, 30)])], ["N LOMBARD ST"])
    other = Lines.build([LineString([(0, 30), (500, 30)])], ["NE LOMBARD ST"])
    edge = (100, 0, 200, 0, "F")
    assert street_names.line_name(edge, line) == street_names.line_name(edge, other) == "LOMBARD ST"


def test_a_chord_no_centreline_runs_beside_is_unread() -> None:
    line = Lines.build([LineString([(0, 30), (500, 30)])], ["SE POWELL BLVD"])
    assert street_names.line_name((100, 0, 120, 40, "F"), line) is None


# --- two names are two streets ------------------------------------------------


def test_tigard_91st_and_lincoln_are_two_streets_under_the_corner_angle() -> None:
    """The lot of the finding: 32 degrees apart, one unbroken run."""
    edges = edges_of("1S135DC02000")
    chains = quadfit._front_max_chains(edges)
    assert any("91ST AVE" in n for n in names_of(chains))
    assert any("LINCOLN AVE" in n for n in names_of(chains))
    assert not any({"91ST AVE", "LINCOLN AVE"} <= n for n in names_of(chains))


@pytest.mark.parametrize(
    "tlid",
    ["1S1E20CB08200", "1N2E19AD11600", "1N1W12BD06400", "1N2E17CD02100", "1N1W12AB01300"],
)
def test_portland_two_named_streets_meeting_are_a_corner(tlid, corpus) -> None:
    rule = corpus.resolve(PORTLAND, LOTS[tlid]["row"]["zone"])
    assert quadfit._front_max_reading(edges_of(tlid))[1] is True
    lot = facts(
        corner=False,
        front_max_streets=((True, 5.0, 5.0, 0.0), (True, 90.0, 90.0, 0.0)),
        front_max_tried=True,
        front_max_corner=True,
    )
    assert front_max_owed(rule, lot)[0] == "every"


@pytest.mark.parametrize(
    "tlid",
    [
        "1N1E36BC12005",
        "1N1W12AB04800",
        "1N1W12AB06400",
        "1S2E01DC01701",
        "2N1E34CA01300",
        "2N1E34CA01500",
    ],
)
def test_three_named_streets_are_not_merged_into_a_corner(tlid) -> None:
    chains, corner = quadfit._front_max_reading(edges_of(tlid))
    assert len(chains) >= 3
    assert corner is False


def test_a_third_line_with_no_name_does_not_undo_the_corner() -> None:
    """1S3E06CD05200: Division and 170th, and a line no centreline runs beside."""
    chains, corner = quadfit._front_max_reading(edges_of("1S3E06CD05200"))
    assert corner is True
    assert len(chains) == 3
    assert {None} in names_of(chains)


# --- one name stays one street ------------------------------------------------


@pytest.mark.parametrize(
    ("tlid", "name"),
    [("1S1E20DD08000", "BARBUR CT"), ("2S101AB01900", "72ND AVE")],
)
def test_one_name_on_one_run_stays_one_street(tlid, name) -> None:
    """Ruling 2026-10-09-bend-is-one-street, on a bend and a jog."""
    chains, corner = quadfit._front_max_reading(edges_of(tlid))
    assert len(chains) == 1
    assert name in names_of(chains)[0]
    assert corner is False


def test_a_bend_of_one_name_is_not_cut_at_its_turn() -> None:
    bend = _edges(
        [(0, 0, 100, 0, F), (100, 0, 180, 40, F), (180, 40, 180, 200, S), (180, 200, 0, 200, R), (0, 200, 0, 0, S)],
        [0.0],
    )
    named = lot_of(bend, {0: "HILL RD", 1: "HILL RD"})
    assert len(quadfit._front_max_chains(named)) == 1


def lot_of(edges, names: dict[int, str]):
    return dataclasses.replace(
        edges,
        edges=tuple(
            dataclasses.replace(e, street_name=names.get(i)) for i, e in enumerate(edges.edges)
        ),
    )


# --- nothing read -------------------------------------------------------------


def test_long_legs_turning_with_no_name_read_are_two_streets() -> None:
    """Without names the turn decides: unread is the conservative answer."""
    turn = _edges(
        [(0, 0, 100, 0, F), (100, 0, 180, 60, F), (180, 60, 180, 200, S), (180, 200, 0, 200, R), (0, 200, 0, 0, S)],
        [0.0],
    )
    assert len(quadfit._front_max_chains(turn)) == 2


def test_a_small_turn_with_no_name_read_stays_one_street() -> None:
    gentle = _edges(
        [(0, 0, 100, 0, F), (100, 0, 200, 20, F), (200, 20, 200, 200, S), (200, 200, 0, 200, R), (0, 200, 0, 0, S)],
        [0.0],
    )
    assert len(quadfit._front_max_chains(gentle)) == 1


# --- the corner's chord -------------------------------------------------------


def test_the_corners_chord_counts_toward_neither_street() -> None:
    """A building beside the chord is not therefore near either street."""
    rounded = _edges(
        [
            (0, 100, 0, 10, F),
            (0, 10, 10, 0, F),
            (10, 0, 100, 0, F),
            (100, 0, 100, 100, S),
            (100, 100, 0, 100, R),
        ],
        [90.0, 0.0],
    )
    named = lot_of(rounded, {0: "OAK ST", 2: "ELM ST"})
    chains = quadfit._front_max_chains(named)
    assert len(chains) == 2
    assert all(len(c) == 1 for c in chains)


def test_a_stub_of_a_street_holds_but_never_fails() -> None:
    stub = _edges(
        [(0, 0, 100, 0, F), (100, 0, 100, 10, F), (100, 10, 100, 200, S), (100, 200, 0, 200, R), (0, 200, 0, 0, S)],
        [0.0, 90.0],
    )
    named = lot_of(stub, {0: "OAK ST", 1: "ELM ST"})
    s = SimpleNamespace(
        drawing={"fits": True, "building": [[10, 5], [50, 5], [50, 40], [10, 40], [10, 5]]},
        lot=SimpleNamespace(edges=named, zone="X", sidewalk_easement_ft=None),
        street_edges=None,
        envelope=None,
        rules=rules(setback_front_max_ft=20),
    )
    measured = front_max_streets(s)
    assert measured is not None and len(measured) == 2
    got = run(
        facts(front_max_streets=measured, front_max_tried=True),
        rules(setback_front_max_streets="every", setback_front_max_ft=20),
    )
    assert check(got, FRONT_MAX) is None
    assert got.colour is Colour.yellow


# --- a maximum that may not reach the lot ---------------------------------------


@pytest.mark.parametrize(
    ("layer", "zone"),
    [(PORTLAND, "CI2"), (FAIRVIEW, "R-6"), (FAIRVIEW, "R-7.5")],
)
def test_a_miss_on_a_maximum_that_turns_on_an_unheld_fact_is_held_not_failed(corpus, layer, zone) -> None:
    rule = corpus.resolve(layer, zone)
    far = run(facts(front_max_streets=((True, 200.0, 200.0, 0.0),), front_max_tried=True), rule)
    assert check(far, FRONT_MAX) is None
    assert FRONT_MAX in far.unchecked
    assert far.colour is not Colour.green
    cap = float(rule.get("setback_front_max_ft"))
    near = run(facts(front_max_streets=((True, cap, cap, 0.0),), front_max_tried=True), rule)
    assert check(near, FRONT_MAX).verdict is Verdict.passes


# --- the drawn building, on the real lot ----------------------------------------


def test_tigard_1s135dc02000_drawn_at_91st_fails_on_lincoln(corpus) -> None:
    rule = corpus.resolve(TIGARD, "RES-C")
    for design in LOTS["1S135DC02000"]["drawn"]:
        lot, got = screened("1S135DC02000", design, rule)
        near = sorted(row[1] for row in lot.front_max_streets)
        assert near[0] <= 21 < near[-1]
        assert check(got, FRONT_MAX).verdict is Verdict.fails


def test_tigard_1s135dc02000_is_red_through_the_whole_screen(corpus) -> None:
    """The lot of the finding, GREEN on the bound of 0f5a2a52, end to end."""
    held = row_of("1S135DC02000")
    lot_geom = shapely.from_wkb(held["lot_wkb"])
    raw = json.loads(held["edges_json"])
    row = bridge_row(
        TLID="1S135DC02000",
        jurisdiction="tigard",
        zone="RES-C",
        tier=held["tier"],
        area_sqft=held["area_sqft"],
        frontage_ft=held["frontage_ft"],
        lot_width_ft=held["frontage_ft"],
        edges_json=held["edges_json"],
        front_bearings_json=held["front_bearings_json"],
        street_names_json=held["street_names_json"],
        # The street is wide enough to give up no strip, as measured on the run.
        road_widths_json=json.dumps(
            [[*e[:4], 100.0, True, None, {}] for e in raw if e[4] in ("F", "S")]
        ),
        wkb=shapely.to_wkb(lot_geom.buffer(-15)),
        lot_wkb=held["lot_wkb"],
    )
    lot = lot_from_row(row, corpus.layers)
    for s in screen_lot(
        lot,
        list(load_catalog())[:1],
        rules=corpus,
        policy=slack.load_policy(),
        relief=relief.load_policy(),
        step_deg=15.0,
    ):
        assert s.signed.colour is Colour.red, s.design.id
        assert check(s.signed, FRONT_MAX).verdict is Verdict.fails, s.design.id


def test_a_building_within_the_maximum_of_both_named_streets_passes() -> None:
    corner = _edges(
        [(0, 0, 100, 0, F), (100, 0, 140, 60, F), (140, 60, 140, 200, S), (140, 200, 0, 200, R), (0, 200, 0, 0, S)],
        [0.0],
    )
    named = lot_of(corner, {0: "OAK ST", 1: "ELM ST"})
    building = Polygon([(70, 5), (105, 5), (105, 30), (70, 30)])
    s = SimpleNamespace(
        drawing={"fits": True, "building": [list(p) for p in building.exterior.coords]},
        lot=SimpleNamespace(edges=named, zone="X", sidewalk_easement_ft=None),
        street_edges=None,
        envelope=None,
        rules=rules(setback_front_max_ft=30),
    )
    measured = front_max_streets(s)
    assert measured is not None and len(measured) == 2
    got = run(
        facts(front_max_streets=measured, front_max_tried=True),
        rules(setback_front_max_streets="every", setback_front_max_ft=40),
    )
    assert check(got, FRONT_MAX).verdict is Verdict.passes


def test_a_maximum_qualified_by_a_fact_that_does_not_lift_it_still_fails(corpus) -> None:
    """Oregon City's 5 ft is qualified by a water feature: a different question."""
    rule = corpus.resolve("or/clackamas/oregon-city", "MUC-2")
    assert rule.values["setback_front_max_ft"].unencoded
    got = run(facts(front_max_streets=((True, 200.0, 200.0, 0.0),), front_max_tried=True), rule)
    assert check(got, FRONT_MAX).verdict is Verdict.fails


def test_a_corner_with_a_line_only_questioned_is_still_a_corner(corpus) -> None:
    """1S1E21BA09600: two streets read and a third measured only as a question."""
    rule = corpus.resolve(PORTLAND, "CM2")
    streets = ((True, 5.1, 5.1, 5.1), (True, 5.8, 6.0, 0.0), (True, 154.6, 157.8, 0.0))
    lot = facts(corner=True, front_max_streets=streets, front_max_tried=True)
    assert front_max_owed(rule, lot)[0] == "every"
    assert check(run(lot, rule), FRONT_MAX).verdict is Verdict.fails


def test_three_held_streets_on_a_corner_stay_unheld(corpus) -> None:
    rule = corpus.resolve(PORTLAND, "CM2")
    streets = ((True, 5.1, 5.1, 0.0), (True, 5.8, 6.0, 0.0), (True, 154.6, 157.8, 0.0))
    lot = facts(corner=True, front_max_streets=streets, front_max_tried=True)
    assert front_max_owed(rule, lot)[0] == "unheld"


# --- the names reach the row -----------------------------------------------------


def test_the_bridge_reads_names_only_with_the_snapshot_and_more_than_one_street(monkeypatch, tmp_path) -> None:
    lines = centrelines("1S135DC02000")
    monkeypatch.setattr(street_names, "load", lambda sources: lines)
    two = {"edges_json": LOTS["1S135DC02000"]["row"]["edges_json"]}
    one = {"edges_json": json.dumps([[0, 0, 50, 0, "F"], [50, 0, 50, 90, "S"]])}
    assert quadfit.with_street_names([two, one], tmp_path) == 1
    assert "street_names_json" not in one
    assert {m[4] for m in json.loads(two["street_names_json"])} >= {"91ST AVE", "LINCOLN AVE"}
    assert quadfit.with_street_names([dict(two)], None) == 0


def test_with_no_centrelines_the_turn_decides(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(street_names, "load", lambda sources: None)
    row = {"edges_json": LOTS["1S135DC02000"]["row"]["edges_json"]}
    assert quadfit.with_street_names([row], tmp_path) == 0
    assert "street_names_json" not in row


# --- the slide on a real lot ------------------------------------------------------


def test_the_slide_on_the_real_tigard_lot_the_raster_left_past_the_line() -> None:
    """1S136CB02900, the lot of finding 4, with its front lines 20 ft in."""
    edges = edges_of("1S136CB02900")
    lot = shapely.from_wkb(row_of("1S136CB02900")["lot_wkb"])
    fronts = [e for e in edges.edges if e.cls.value == "front"]
    keep = lot
    for e in fronts:
        keep = keep.difference(LineString([(e.x1, e.y1), (e.x2, e.y2)]).buffer(20.0, cap_style="flat"))
    longest = max(fronts, key=lambda e: e.length_ft)
    # Measured from that street alone: the slide answers to the street it misses.
    edges = dataclasses.replace(
        edges,
        edges=tuple(
            e if e is longest or e.cls.value != "front" else dataclasses.replace(e, cls=EdgeClass.side)
            for e in edges.edges
        ),
    )
    line = LineString([(longest.x1, longest.y1), (longest.x2, longest.y2)])
    # A pod square to the long front, 21.13 ft in from it, mid-way along.
    ux, uy = (longest.x2 - longest.x1) / longest.length_ft, (longest.y2 - longest.y1) / longest.length_ft
    px, py = -uy, ux
    middle = line.interpolate(0.5, normalized=True)
    if not lot.contains(shapely.Point(middle.x + px, middle.y + py)):
        px, py = -px, -py
    def pod(off: float) -> list[list[float]]:
        ring = []
        for a, b in ((-28, off), (28, off), (28, off + 36), (-28, off + 36), (-28, off)):
            ring.append([round(middle.x + ux * a + px * b, 1), round(middle.y + uy * a + py * b, 1)])
        return ring
    ring = pod(21.13)
    assert keep.covers(Polygon(ring))
    s = SimpleNamespace(
        drawing={"fits": True, "building": ring, "room": ring},
        lot=SimpleNamespace(edges=edges, zone="RES-B", sidewalk_easement_ft=None),
        street_edges=None,
        envelope=SimpleNamespace(geom=keep, source="quadfit"),
        rules=rules(setback_front_max_ft=20),
    )
    slid = quadfit._front_max_flush(s, SimpleNamespace(ground=None))
    assert slid is not None
    moved = Polygon(slid["building"])
    assert keep.buffer(0.1).covers(moved)
    assert moved.distance(line) == pytest.approx(20.0, abs=0.2)
