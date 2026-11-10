"""Streets a fire truck cannot stand on (FOLLOWUPS 168, flats.fit.fire_roads).

A street under 20 ft between its lots (OFC 503.2.1) and a dead end past
150 ft with no room to turn (OFC 503.2.5 / 503.1.1) are walked, not driven:
the hose starts where the truck can stand and walks the street from there.
A street whose right-of-way is 20 ft or more, through or turned, reads as it
did before.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest
import shapely
from shapely.geometry import LineString, box

from flats.fit import fire, fire_roads

FIXTURE = Path(__file__).parent / "fixtures" / "rocky_ln_21E02DC10300.json"


def _index(pieces):
    geoms = np.asarray([p.geom for p in pieces], dtype=object)
    walks = fire_roads.Walks(
        np.asarray([p.stand for p in pieces]),
        np.asarray([p.walk0 for p in pieces], dtype=float),
        np.asarray([p.walk1 for p in pieces], dtype=float),
    )
    return shapely.STRtree(geoms), geoms, walks


def _main_road_lots(gap_at: tuple[float, float] = (-100.0, 100.0)) -> list:
    """Lots either side of a 50 ft main road along y = 0, x -500..500, the
    north side open between ``gap_at`` for a side street."""
    a, b = gap_at
    return [
        box(-500, -125, 500, -25),
        box(-500, 25, a, 125),
        box(b, 25, 500, 125),
    ]


MAIN = [LineString([(-500, 0), (0, 0)]), LineString([(0, 0), (500, 0)])]


def _build(lane, lots, kinds=None):
    lines = [*MAIN, *lane]
    kinds = kinds or [1400, 1400, *([1500] * len(lane))]
    return fire_roads.build(lines, kinds, [], lots, [True] * len(lots))


def test_a_lane_16_ft_between_its_lots_is_walked_from_the_main_road() -> None:
    lane = [LineString([(0, 0), (0, 300)])]
    lots = [*_main_road_lots(), box(8, 25, 100, 300), box(-100, 25, -8, 300), box(-100, 300, 100, 400)]
    pieces = _build(lane, lots)
    # The last few feet, where the centreline runs onto the lot at the end,
    # are unmeasured and wide -- and cut off beyond the narrow stretch.
    assert {p.why for p in pieces if not p.stand} == {fire_roads.NARROW, fire_roads.CUT_OFF}
    tree, geoms, walks = _index(pieces)
    end = np.array([[8.0, 295.0]])
    walked = fire.hose_offsets(end, tree, geoms, None, walks)
    # Across to the lane (8 ft) and down it to where it is wide enough.
    assert walked[0][0] == pytest.approx(8.0 + 270.0, abs=6.0)
    assert walked[1][0] == walked[0][0]
    # Read as before (every mapped street a truck road), the hose starts
    # in the lane: the false GREEN of lot 21E02DC10300.
    assert fire.hose_offsets(end, tree, geoms)[0][0] == pytest.approx(8.0)


def test_a_lane_20_ft_or_wider_reads_as_before() -> None:
    # The right-of-way is a ceiling on the pavement, not the pavement: at
    # 24 ft nothing is known, and the street keeps its reading. A loop, so
    # no dead end is in play.
    lane = [LineString([(0, 0), (0, 300)]), LineString([(0, 300), (300, 300)]), LineString([(300, 300), (300, 0)])]
    main = [LineString([(-500, 0), (0, 0)]), LineString([(0, 0), (300, 0)]), LineString([(300, 0), (500, 0)])]
    lots = [box(-500, -125, 500, -25), box(12, 25, 288, 288), box(-100, 25, -12, 400), box(312, 25, 500, 400)]
    pieces = fire_roads.build([*main, *lane], [1400, 1400, 1400, 1500, 1500, 1500], [], lots, [True] * 4)
    assert all(p.stand for p in pieces)


def test_a_through_street_is_unchanged() -> None:
    # A grid block: every street through, 50 ft between its lots.
    lines = [
        LineString([(0, 0), (400, 0)]), LineString([(400, 0), (400, 400)]),
        LineString([(400, 400), (0, 400)]), LineString([(0, 400), (0, 0)]),
        LineString([(-400, 0), (0, 0)]), LineString([(400, 0), (800, 0)]),
    ]
    lots = [box(25, 25, 375, 375), box(-400, -125, 800, -25)]
    pieces = fire_roads.build(lines, [1400, 1500, 1500, 1500, 1400, 1400], [], lots, [True, True])
    assert all(p.stand for p in pieces)
    tree, geoms, walks = _index(pieces)
    pts = np.array([[25.0, 200.0], [200.0, 375.0], [375.0, 30.0]])
    before = fire.hose_offsets(pts, tree, geoms)
    after = fire.hose_offsets(pts, tree, geoms, None, walks)
    assert after[0].tolist() == before[0].tolist() and after[1].tolist() == before[1].tolist()


def _dead_end_lots(*, bulb: bool, closed: bool = True) -> list:
    lots = [*_main_road_lots((-25.0, 25.0))]
    lots += [box(25, 25, 100, 400), box(-100, 25, -25, 400)]
    if closed:
        lots.append(box(-100, 400, 100, 500))
    if bulb:
        hole = shapely.Point(0, 400).buffer(50)
        lots = [lot.difference(hole) for lot in lots]
    return lots


def test_a_dead_end_with_no_room_to_turn_is_walked_past_150_ft() -> None:
    lane = [LineString([(0, 0), (0, 400)])]
    pieces = _build(lane, _dead_end_lots(bulb=False))
    walked = [p for p in pieces if not p.stand]
    assert [p.why for p in walked] == [fire_roads.DEAD_END]
    assert walked[0].geom.length == pytest.approx(400.0 - fire_roads.DEAD_END_FT)
    tree, geoms, walks = _index(pieces)
    got = fire.hose_offsets(np.array([[25.0, 390.0], [25.0, 100.0]]), tree, geoms, None, walks)[0]
    # 390 ft in: across 25 ft, back 240 ft to where the truck may stand.
    assert got[0] == pytest.approx(25.0 + 240.0, abs=0.5)
    # 100 ft in, the truck stands beside the lot: the reading of before.
    assert got[1] == pytest.approx(fire.hose_offsets(np.array([[25.0, 100.0]]), tree, geoms)[0][0])


def test_a_dead_end_with_a_bulb_or_an_open_end_reads_as_before() -> None:
    lane = [LineString([(0, 0), (0, 400)])]
    assert all(p.stand for p in _build(lane, _dead_end_lots(bulb=True)))
    # Nothing ahead of the end: the edge of the map, or open land.
    assert all(p.stand for p in _build(lane, _dead_end_lots(bulb=False, closed=False)))


def test_a_dead_end_150_ft_or_shorter_needs_no_turnaround() -> None:
    lane = [LineString([(0, 0), (0, 140)])]
    lots = [*_main_road_lots((-25.0, 25.0)), box(25, 25, 100, 140), box(-100, 25, -25, 140), box(-100, 140, 100, 240)]
    assert all(p.stand for p in _build(lane, lots))


def test_the_pieces_round_trip(tmp_path) -> None:
    lane = [LineString([(0, 0), (0, 400)])]
    pieces = _build(lane, _dead_end_lots(bulb=False))
    tree, geoms, walks = fire_roads.load(fire_roads.write(pieces, tmp_path / "fire_roads.parquet"))
    assert len(geoms) == len(pieces)
    assert walks.stand.tolist() == [p.stand for p in pieces]
    assert walks.walk1.tolist() == [p.walk1 for p in pieces]


def test_rocky_ln_lot_21E02DC10300_is_past_the_hose() -> None:
    # fg-rate-B (2026-11-09): SE Rocky Ln is 16 ft between its lots and
    # dead-ends at this lot about 300 ft from River Rd. The truck stands on
    # River Rd, and the hose is past 150 ft: RED (ruling
    # 2026-10-01-fire-access-150ft-red). Real RLIS coordinates (2026-11-04),
    # shifted to the fixture's origin.
    from flats.ingest.normalize import NOT_A_TAXLOT_RE

    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    tlids = [lot["tlid"] for lot in data["lots"]]
    polys = [shapely.from_wkt(lot["wkt"]) for lot in data["lots"]]
    private = [not NOT_A_TAXLOT_RE.search(t) for t in tlids]
    kinds = [s["type"] for s in data["streets"]]
    lines = [shapely.from_wkt(s["wkt"]) for s in data["streets"]]
    truck = [
        i for i, (k, s) in enumerate(zip(kinds, data["streets"]))
        if k in fire.TRUCK_TYPES and not s["alley"]
    ]
    pieces = fire_roads.build([lines[i] for i in truck], [kinds[i] for i in truck], [], polys, private)
    tree, geoms, walks = _index(pieces)

    lot = polys[[t.replace(" ", "") for t in tlids].index(data["subject"])]
    rocky = [g for g, s in zip(lines, data["streets"]) if s["name"] == "ROCKY"]
    ring = np.asarray(lot.exterior.coords)
    streets = tuple(
        (float(a[0]), float(a[1]), float(b[0]), float(b[1]))
        for a, b in zip(ring[:-1], ring[1:])
        if min(r.distance(LineString([a, b]).centroid) for r in rocky) < 25.0
    )
    assert streets
    building = lot.buffer(-15.0)
    building = shapely.box(*building.centroid.buffer(15.0).bounds)
    assert lot.contains(building)
    limit = 150.0
    before = fire.route_ft(building, lot, streets, fire.point_offset(tree, geoms))
    after = fire.route_ft(building, lot, streets, fire.point_offset(tree, geoms, None, walks))
    assert before is not None and before < limit
    assert after is not None and after > limit
    assert math.isfinite(after)


# --- a city's own length, and the fire marshal's reading (2026-11-10) -------


def test_portland_states_300_ft_and_its_pockets_keep_the_states_150() -> None:
    ruled = fire_roads.rules()
    assert ruled.default_ft == 150.0
    assert ruled.dead_end_ft("or/multnomah/portland") == 300.0
    # The county pockets Portland administers are not the city: Title 31 is
    # city code.
    assert ruled.dead_end_ft("or/multnomah/_unincorporated") == 150.0
    assert ruled.dead_end_ft(None) == 150.0
    assert ruled.lengths == (150.0, 300.0)


def test_canby_gets_its_fire_districts_300_ft() -> None:
    # Steph 2026-11-10 (rulings.yaml 2026-11-10-canby-fire-dead-end-300):
    # the Canby Fire District's Conditions of Construction states 300 ft.
    ruled = fire_roads.rules()
    assert ruled.dead_end_ft("or/clackamas/canby") == 300.0
    # The county around it, and its neighbours, keep the state's 150 ft.
    assert ruled.dead_end_ft("or/clackamas/_unincorporated") == 150.0
    assert ruled.dead_end_ft("or/clackamas/oregon-city") == 150.0
    from flats.provenance.sources import Authority, authority_for

    data = __import__("yaml").safe_load(fire_roads.CONFIG.read_text(encoding="utf-8"))
    assert data["dead_end_ft"]["or/clackamas/canby"]["quote"].startswith("or/clackamas/canby/")
    assert authority_for(
        "https://cfpd.specialdistrict.org/files/1b3c80534/CFD+Conditions+of+Construction+rev10.28.pdf"
    ) is Authority.official
    # Steph 2026-11-10: "Yellow." -- every dead end is released.
    assert ruled.release == frozenset({fire_roads.DEAD_END, fire_roads.DEAD_END_UNSURE})


def test_each_length_reads_the_number_its_stored_line_prints() -> None:
    import yaml

    data = yaml.safe_load(fire_roads.CONFIG.read_text(encoding="utf-8"))
    docs = Path(__file__).resolve().parents[1] / "provenance" / "docs"
    for entry in data["dead_end_ft"].values():
        doc, span = entry["quote"].split("#L")
        first, _, last = span.partition("-L")
        lines = (docs / doc).read_text(encoding="utf-8").splitlines()
        text = " ".join(lines[int(first) - 1 : int(last or first)])
        assert f"{entry['value']} feet" in " ".join(text.split())


def test_a_switch_set_to_anything_else_is_refused(tmp_path) -> None:
    bad = tmp_path / "fire_roads.yaml"
    bad.write_text(
        fire_roads.CONFIG.read_text(encoding="utf-8").replace("long_dead_end: yellow", "long_dead_end: maybe"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="long_dead_end"):
        fire_roads.rules(bad)
    red = tmp_path / "red.yaml"
    red.write_text(
        fire_roads.CONFIG.read_text(encoding="utf-8").replace("long_dead_end: yellow", "long_dead_end: red"),
        encoding="utf-8",
    )
    # The code as written: only an end whose room is unclear stays a question.
    assert fire_roads.rules(red).release == frozenset({fire_roads.DEAD_END_UNSURE})


def test_a_dead_end_is_cut_at_each_places_length() -> None:
    lane = [LineString([(0, 0), (0, 400)])]
    lots = _dead_end_lots(bulb=False)
    by_ft = fire_roads.build_all([*MAIN, *lane], [1400, 1400, 1500], [], lots, [True] * len(lots), lengths=(150.0, 300.0))
    for ft, pieces in by_ft.items():
        (walked,) = [p for p in pieces if not p.stand]
        assert walked.geom.length == pytest.approx(400.0 - ft)
        # Driven to its end, it stands: the fire marshal's reading.
        assert walked.free is True and walked.free0 == walked.free1 == 0.0


def test_the_lengths_and_the_freed_reading_round_trip(tmp_path) -> None:
    lane = [LineString([(0, 0), (0, 400)])]
    lots = _dead_end_lots(bulb=False)
    by_ft = fire_roads.build_all(
        [*MAIN, *lane], [1400, 1400, 1500], [], lots, [True] * len(lots), lengths=(150.0, 300.0)
    )
    every = fire_roads.load_all(fire_roads.write(by_ft, tmp_path / "fire_roads.parquet"))
    assert sorted(every) == [150.0, 300.0]
    net = fire_roads.Network(every, fire_roads.rules())
    assert net.at("or/multnomah/portland") is every[300.0]
    assert net.at("or/clackamas/milwaukie") is every[150.0]
    assert every[150.0].freed.stand.all()
    assert not every[150.0].walks.stand.all()


def test_a_narrow_lane_is_not_freed() -> None:
    # Only the dead ends are the fire marshal's question: a lane under 20 ft
    # stays walked on either reading.
    lane = [LineString([(0, 0), (0, 300)])]
    lots = [*_main_road_lots(), box(8, 25, 100, 300), box(-100, 25, -8, 300), box(-100, 300, 100, 400)]
    pieces = _build(lane, lots)
    walked = [p for p in pieces if not p.stand]
    assert walked and all(p.why in {fire_roads.NARROW, fire_roads.CUT_OFF} for p in walked)
    assert not any(p.free for p in walked)


def test_rocky_ln_stays_red_with_its_dead_end_driven() -> None:
    # SE Rocky Ln is narrow (16 ft) as well as a dead end: the fire
    # marshal's reading drives dead ends, not lanes, so the lot stays RED.
    from flats.ingest.normalize import NOT_A_TAXLOT_RE

    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    tlids = [lot["tlid"] for lot in data["lots"]]
    polys = [shapely.from_wkt(lot["wkt"]) for lot in data["lots"]]
    private = [not NOT_A_TAXLOT_RE.search(t) for t in tlids]
    kinds = [s["type"] for s in data["streets"]]
    lines = [shapely.from_wkt(s["wkt"]) for s in data["streets"]]
    truck = [i for i, (k, s) in enumerate(zip(kinds, data["streets"])) if k in fire.TRUCK_TYPES and not s["alley"]]
    pieces = fire_roads.build([lines[i] for i in truck], [kinds[i] for i in truck], [], polys, private)
    geoms = np.asarray([p.geom for p in pieces], dtype=object)
    freed = fire_roads.Walks(
        np.asarray([p.stand if p.free is None else p.free for p in pieces]),
        np.asarray([p.free0 for p in pieces], dtype=float),
        np.asarray([p.free1 for p in pieces], dtype=float),
    )
    lot = polys[[t.replace(" ", "") for t in tlids].index(data["subject"])]
    rocky = [g for g, s in zip(lines, data["streets"]) if s["name"] == "ROCKY"]
    ring = np.asarray(lot.exterior.coords)
    streets = tuple(
        (float(a[0]), float(a[1]), float(b[0]), float(b[1]))
        for a, b in zip(ring[:-1], ring[1:])
        if min(r.distance(LineString([a, b]).centroid) for r in rocky) < 25.0
    )
    building = shapely.box(*lot.buffer(-15.0).centroid.buffer(15.0).bounds)
    got = fire.route_ft(building, lot, streets, fire.point_offset(shapely.STRtree(geoms), geoms, None, freed))
    assert got is not None and got > 150.0


def test_the_screen_holds_a_lot_reached_only_up_a_long_dead_end_yellow() -> None:
    from flats.score.screen import FACT_UNOBSERVED, Triage
    from flats.tests.test_fire import check, facts, run

    result = run(facts(fire_route_ft=260.0, fire_route_tried=True, fire_route_freed_ft=120.0))
    assert check(result, "fire_access_ft") is None
    assert FACT_UNOBSERVED in result.reasons
    assert result.triage not in (Triage.green, Triage.red)
    assert "FIRE-DEAD-END" in {f.code for f in result.flags}
    # Missed on both readings: RED, as before.
    result = run(facts(fire_route_ft=260.0, fire_route_tried=True, fire_route_freed_ft=170.0))
    assert result.triage is Triage.red
    assert "FIRE-DEAD-END" not in {f.code for f in result.flags}
    # Reached on the code's reading: the freed reading is never read.
    result = run(facts(fire_route_ft=120.0, fire_route_tried=True, fire_route_freed_ft=100.0))
    assert result.triage is Triage.green
