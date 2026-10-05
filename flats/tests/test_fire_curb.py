"""Where the fire truck stands: 10 ft out from the near curb (FOLLOWUPS 29).

Steph, 2026-10-05: of the readings found in use -- the curb itself, or "10
feet from the edge of the curb" -- the stricter, "with a flag to check
later". Pinned here:

* the curb is where a drawn curb line says, else half a recorded width off
  the centreline less a margin, else unknown -- and unknown is the
  narrowest street a truck may use, its curb 10 ft off the centreline
  (Steph 2026-10-05, "assume narrow"; :mod:`flats.geom.curbs`);
* the hose starts 10 ft out from that curb, never past the street's middle,
  and a width alone never puts it nearer the lot than the old 10 ft
  (:func:`flats.fit.fire.hose_offsets`);
* a drawn curb that would put it nearer the lot than before must agree with
  the recorded width;
* a plan red on the hose alone that clears measured from the curb carries
  FIRE-HOSE-START, and stays red;
* the bridge refuses a snapshot missing a curb or width dataset.
"""

from __future__ import annotations

import dataclasses
import json
import math

import numpy as np
import pytest

pytest.importorskip("shapely")

import shapely  # noqa: E402
from shapely.geometry import LineString  # noqa: E402

from flats.fit import fire  # noqa: E402
from flats.geom import curbs  # noqa: E402
from flats.geom.curbs import Source, StreetEdges  # noqa: E402
from flats.ingest.quadfit import fire_checked, lot_from_row, screen_lot  # noqa: E402
from flats.score import flags as flag_plan  # noqa: E402
from flats.score.screen import Triage  # noqa: E402
from flats.score.slack import Verdict  # noqa: E402
from flats.tests.test_fire import (  # noqa: E402
    X0,
    Y0,
    _coloured,
    bridge_row,
    check,
    facts,
    pod,
    rules,
    run,
)

pytestmark = pytest.mark.unit


def street(y: float, x0: float = -100.0, x1: float = 200.0) -> LineString:
    return LineString([(x0, y), (x1, y)])


def roads(*lines: LineString) -> tuple[shapely.STRtree, np.ndarray]:
    return shapely.STRtree(list(lines)), np.asarray(lines, dtype=object)


#: Two points on a lot line along y = 0, the street to the south.
PTS = np.array([[0.0, 0.0], [50.0, 0.0]])


def offsets(centre_y: float, edges: StreetEdges | None) -> tuple[list[float], list[float]]:
    strict, curb = fire.hose_offsets(PTS, *roads(street(centre_y)), edges)
    return strict.tolist(), curb.tolist()


# --- where the hose starts ------------------------------------------------


def test_with_nothing_measured_the_street_is_the_narrowest_a_truck_may_use() -> None:
    # 30 ft to the centreline of a 20-ft street: its curb 20 ft off the lot
    # line, 10 ft past it is the middle.
    assert offsets(-30.0, None) == ([30.0, 30.0], [20.0, 20.0])
    assert offsets(-30.0, StreetEdges.build()) == ([30.0, 30.0], [20.0, 20.0])
    # Nearer than half the narrowest street: the lot line is the curb.
    assert offsets(-6.0, None) == ([6.0, 6.0], [0.0, 0.0])


def test_the_hose_starts_ten_feet_out_from_a_drawn_curb() -> None:
    # A 36-ft street: the curb 12 ft off the lot line, the middle 30.
    edges = StreetEdges.build(curbs=[street(-12.0)])
    assert offsets(-30.0, edges) == ([22.0, 22.0], [12.0, 12.0])


def test_never_past_the_middle_of_the_street() -> None:
    # A 10-ft lane: 10 ft past its curb is beyond its middle.
    edges = StreetEdges.build(curbs=[street(-25.0)])
    assert offsets(-30.0, edges) == ([30.0, 30.0], [25.0, 25.0])


def test_the_curb_nearest_the_middle_is_the_one_the_truck_stands_outside() -> None:
    # A curb extension, or a cycle track's street-side curb, crossed after
    # the sidewalk's: the truck stands outside both.
    edges = StreetEdges.build(curbs=[street(-8.0), street(-14.0)])
    assert offsets(-30.0, edges)[1] == [14.0, 14.0]


def test_a_curb_the_line_to_the_middle_does_not_cross_is_not_this_streets() -> None:
    # A curb across the centreline (the far side) is no near curb.
    edges = StreetEdges.build(curbs=[street(-45.0)])
    assert offsets(-30.0, edges) == ([30.0, 30.0], [20.0, 20.0])


def test_a_width_places_the_curb_half_its_width_off_the_middle_less_a_margin() -> None:
    # 30 ft wide: the curb 15 - 3 = 12 ft off the middle, 18 ft off the lot.
    edges = StreetEdges.build(widths=[(street(-30.5), 30.0)])
    strict, curb = offsets(-30.0, edges)
    assert strict == pytest.approx([28.0, 28.0])
    assert curb == pytest.approx([18.0, 18.0])


def test_a_width_alone_never_puts_the_truck_nearer_the_lot_than_before() -> None:
    # 70 ft wide: 10 ft past the curb would be 32 ft nearer the lot than
    # the middle; the old 10 ft off the centreline stands.
    edges = StreetEdges.build(widths=[(street(-40.5), 70.0)])
    strict, curb = offsets(-40.0, edges)
    assert strict == pytest.approx([30.0, 30.0])
    assert curb == pytest.approx([8.0, 8.0])


def test_a_curb_farther_out_than_before_needs_the_width_to_agree() -> None:
    # The centreline 40 ft off, a curb drawn 10 ft off the lot line: a
    # 60-ft street, the truck 10 ft nearer the lot than the old offset.
    curb = [street(-10.0)]
    alone = StreetEdges.build(curbs=curb)
    assert offsets(-40.0, alone) == ([40.0, 40.0], [30.0, 30.0])
    agreed = StreetEdges.build(curbs=curb, widths=[(street(-40.5), 60.0)])
    assert offsets(-40.0, agreed) == ([20.0, 20.0], [10.0, 10.0])
    # Recorded 40 ft: the drawn curb is not this street's; the width answers.
    other = StreetEdges.build(curbs=curb, widths=[(street(-40.5), 40.0)])
    strict, near = offsets(-40.0, other)
    assert strict == pytest.approx([33.0, 33.0])
    assert near == pytest.approx([23.0, 23.0])


def test_a_cross_streets_width_line_is_not_this_streets() -> None:
    cross = LineString([(0.0, -80.0), (0.0, 0.0)])
    edges = StreetEdges.build(widths=[(cross, 20.0)])
    assert offsets(-30.0, edges) == ([30.0, 30.0], [20.0, 20.0])


def test_a_width_too_far_from_the_centreline_is_not_this_streets() -> None:
    edges = StreetEdges.build(widths=[(street(-30.0 - curbs.WIDTH_REACH_FT - 1.0), 20.0)])
    assert offsets(-30.0, edges) == ([30.0, 30.0], [20.0, 20.0])


def test_the_narrowest_width_beside_the_foot_answers() -> None:
    edges = StreetEdges.build(widths=[(street(-30.5), 40.0), (street(-31.0), 26.0)])
    # 26 ft: 13 - 3 = 10 ft off the middle, 20 ft off the lot.
    assert offsets(-30.0, edges)[1] == pytest.approx([20.0, 20.0])


def test_a_width_under_ten_feet_is_not_a_street_width() -> None:
    edges = StreetEdges.build(widths=[(street(-30.5), 6.0)])
    assert len(edges.width_ft) == 0
    assert offsets(-30.0, edges) == ([30.0, 30.0], [20.0, 20.0])


def test_past_the_gap_no_reading_reaches_the_street() -> None:
    edges = StreetEdges.build(curbs=[street(-12.0)])
    strict, curb = offsets(-(fire.MAX_GAP_FT + 5.0), edges)
    assert all(math.isinf(v) for v in strict + curb)


def test_what_placed_the_curb_is_said() -> None:
    edges = StreetEdges.build(curbs=[street(-12.0, -100.0, 20.0)], widths=[(street(-30.5), 30.0)])
    feet = np.array([[0.0, -30.0], [50.0, -30.0], [500.0, -30.0]])
    pts = np.array([[0.0, 0.0], [50.0, 0.0], [500.0, 0.0]])
    _, src = edges.near(pts, feet, [street(-30.0)] * 3)
    assert src.tolist() == [Source.curb, Source.width, Source.none]


def test_point_offset_gives_either_reading() -> None:
    tree, geoms = roads(street(-30.0))
    edges = StreetEdges.build(curbs=[street(-12.0)])
    assert fire.point_offset(tree, geoms, edges)(PTS).tolist() == [22.0, 22.0]
    assert fire.point_offset(tree, geoms, edges, reading="curb")(PTS).tolist() == [12.0, 12.0]
    # The two-part street index the bridge held before curbs: nothing measured.
    assert fire.point_offset(tree, geoms)(PTS).tolist() == [30.0, 30.0]
    assert fire.point_offset(tree, geoms, reading="curb")(PTS).tolist() == [20.0, 20.0]
    with pytest.raises(ValueError):
        fire.point_offset(tree, geoms, edges, reading="lot line")


# --- the snapshot ---------------------------------------------------------


def _layer(path, features) -> None:
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")


def _line(y: float, **props) -> dict:
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "MultiLineString", "coordinates": [[[-100.0, y], [200.0, y]]]},
    }


def test_a_snapshot_with_no_curbs_or_widths_measures_nothing(tmp_path) -> None:
    assert curbs.load(tmp_path) is None
    every = (*curbs.CURB_KEYS, *curbs.WIDTH_KEYS)
    assert curbs.missing(tmp_path) == every
    assert curbs.missing(None) == every


def test_the_snapshot_is_read_and_a_property_side_curb_skipped(tmp_path) -> None:
    _layer(
        tmp_path / "curbs_portland.geojson",
        [_line(-12.0, CurbType=3110, CurbStyle="STANDARD"), _line(-4.0, CurbType=3110, CurbStyle="INSIDE")],
    )
    _layer(tmp_path / "pave_width_portland.geojson", [_line(-30.0, PaveWidth=36), _line(-30.0, PaveWidth=4)])
    _layer(tmp_path / "road_width_multnomah.geojson", [_line(-300.0, RoadWidth=22.0)])
    edges = curbs.load(tmp_path)
    assert edges is not None
    assert edges.keys == ("curbs_portland", "pave_width_portland", "road_width_multnomah")
    assert len(edges.curb_geoms) == 1
    assert sorted(edges.width_ft.tolist()) == [22.0, 36.0]
    assert curbs.missing(tmp_path) == ("street_width_wilsonville",)


# --- the screen -----------------------------------------------------------


def _flagged(result) -> list:
    return [f for f in result.flags if f.code == "FIRE-HOSE-START"]


def test_red_on_the_stricter_reading_alone_is_flagged_and_stays_red() -> None:
    result = run(facts(fire_route_ft=156.0, fire_route_tried=True, fire_route_curb_ft=146.0))
    assert check(result, "fire_access_ft").verdict is not Verdict.passes
    assert result.triage is Triage.red
    (flag,) = _flagged(result)
    assert flag.bounds == (146.0, 156.0)
    assert flag.key == "or/multnomah/portland"


def test_red_either_way_is_not_flagged() -> None:
    result = run(facts(fire_route_ft=170.0, fire_route_tried=True, fire_route_curb_ft=160.0))
    assert result.triage is Triage.red
    assert _flagged(result) == []


def test_red_on_something_else_too_is_not_flagged() -> None:
    # The flag promises the fire marshal's answer alone would lift the red.
    lot = facts(fire_route_ft=156.0, fire_route_tried=True, fire_route_curb_ft=146.0)
    result = run(lot, rules(min_lot_sqft=8000))
    assert check(result, "min_lot_area_sqft").verdict is Verdict.fails
    assert result.triage is Triage.red
    assert _flagged(result) == []


def test_a_minimum_density_missed_beside_it_still_leaves_the_hose_the_one_bind() -> None:
    # 4 units on 6,000 sq ft is 29 an acre; a minimum of 40 is missed, and
    # a missed minimum density is a flag, never a bind (Steph 2026-10-02).
    lot = facts(fire_route_ft=156.0, fire_route_tried=True, fire_route_curb_ft=146.0)
    result = run(lot, rules(min_density_du_per_acre=40))
    assert check(result, "min_density_du_per_acre").verdict is Verdict.fails
    assert [b.check for b in result.binds] == ["fire_access_ft"]
    assert len(_flagged(result)) == 1


def test_a_route_that_clears_is_not_flagged() -> None:
    result = run(facts(fire_route_ft=140.0, fire_route_tried=True, fire_route_curb_ft=130.0))
    assert result.triage is Triage.green
    assert _flagged(result) == []


def test_the_flag_type_marks_a_red_and_never_holds_a_green() -> None:
    t = flag_plan.registry()["FIRE-HOSE-START"]
    assert t.severity < flag_plan.colour_rules().yellow_at_severity
    assert t.status is flag_plan.TypeStatus.pending


# --- the bridge -----------------------------------------------------------


@pytest.fixture(scope="module")
def corpus():
    from flats.encode.load import load_trusted

    return load_trusted(strict=False).rules


@pytest.fixture(scope="module")
def policies():
    from flats.score import relief, slack

    return slack.load_policy(), relief.load_policy()


def _limit(s, ft: float):
    """``s`` with the hose's limit moved, so a test lot can sit either side of it."""
    old = s.rules.values["fire_access_max_ft"]
    values = {**s.rules.values, "fire_access_max_ft": dataclasses.replace(old, value=ft)}
    return dataclasses.replace(s, rules=dataclasses.replace(s.rules, values=values))


def _bridge(corpus, policies):
    lot = lot_from_row(bridge_row(), corpus.layers)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    tree, geoms = roads(street(Y0 - 30.0, X0 - 200.0, X0 + 300.0))
    return lot, _coloured(s, Triage.green), tree, geoms


def _hose_flags(s) -> list[str]:
    return [f.code for f in s.signed.flags if f.code == "FIRE-HOSE-START"]


def test_the_bridge_measures_the_curb_reading_only_where_the_strict_one_misses(corpus, policies) -> None:
    lot, green, tree, geoms = _bridge(corpus, policies)
    # Nothing measured: the middle of a street 30 ft off (offset 30).
    narrow = fire_checked(green, lot, (tree, geoms, None), policy=policies[0], relief=policies[1])
    middle = narrow.facts.fire_route_ft
    assert narrow.facts.fire_route_curb_ft is None
    edges = StreetEdges.build(curbs=[street(Y0 - 12.0, X0 - 200.0, X0 + 300.0)])

    # A curb drawn 12 ft off the lot line: 8 ft nearer than the middle
    # (22 against 30), 18 nearer measured from the curb: a limit 9 ft short
    # of the middle's route.
    tight = _limit(green, middle - 9.0)
    got = fire_checked(tight, lot, (tree, geoms, edges), policy=policies[0], relief=policies[1])
    assert got.facts.fire_route_ft == pytest.approx(middle - 8.0, abs=0.01)
    assert got.facts.fire_route_curb_ft == pytest.approx(middle - 18.0, abs=0.01)
    assert got.signed.triage is Triage.red
    assert _hose_flags(got) == ["FIRE-HOSE-START"]

    # Where the strict route clears, the curb reading is not measured.
    roomy = _limit(green, middle - 5.0)
    got = fire_checked(roomy, lot, (tree, geoms, edges), policy=policies[0], relief=policies[1])
    assert got.facts.fire_route_ft == pytest.approx(middle - 8.0, abs=0.01)
    assert got.facts.fire_route_curb_ft is None


def test_an_unmeasured_street_red_on_the_middle_alone_is_flagged(corpus, policies) -> None:
    # Nothing measured: the strict route from the middle, the curb reading
    # from the narrowest street's curb, 10 ft nearer -- the old offset.
    lot, green, tree, geoms = _bridge(corpus, policies)
    middle = fire_checked(green, lot, (tree, geoms), policy=policies[0], relief=policies[1]).facts.fire_route_ft
    got = fire_checked(_limit(green, middle - 5.0), lot, (tree, geoms), policy=policies[0], relief=policies[1])
    assert got.facts.fire_route_ft == pytest.approx(middle, abs=0.01)
    assert got.facts.fire_route_curb_ft == pytest.approx(middle - 10.0, abs=0.01)
    assert got.signed.triage is Triage.red
    assert _hose_flags(got) == ["FIRE-HOSE-START"]


def test_the_bridge_refuses_a_snapshot_without_the_curbs_and_widths(tmp_path) -> None:
    from flats.ingest import quadfit

    s1 = tmp_path / "s1_streets.parquet"
    s1.write_bytes(b"")
    snap = tmp_path / "snapshot"
    snap.mkdir()
    (snap / "curbs_portland.geojson").write_text("{}", encoding="utf-8")
    raw = tmp_path / "raw"
    (raw / "dem").mkdir(parents=True)
    (raw / "dem" / "tile.tif").write_bytes(b"")
    kw = dict(s4=tmp_path / "s4_lots.parquet", roads=s1, dem=raw, sources=snap)
    with pytest.raises(FileNotFoundError, match="pave_width_portland"):
        quadfit.run(tmp_path / "out", **kw)
    with pytest.raises(FileNotFoundError, match="curbs_portland"):
        quadfit.run(tmp_path / "out", **{**kw, "sources": None})
    for key in (*curbs.CURB_KEYS, *curbs.WIDTH_KEYS):
        (snap / f"{key}.geojson").write_text("{}", encoding="utf-8")
    # Past the curbs, to the lots the run reads (none here).
    with pytest.raises(Exception) as past:
        quadfit.run(tmp_path / "out", **kw)
    assert "fire truck" not in str(past.value)
