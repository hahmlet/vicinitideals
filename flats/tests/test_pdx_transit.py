"""Portland's transit streets, off the city's TSP map, for the "m" overlay's
transit-street rules (flats/geom/pdx_transit.py, FOLLOWUPS 78 / 109)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import shapely
from shapely.geometry import LineString, box

from flats.geom import pdx_overlays as pdx
from flats.geom import pdx_transit as pt
from flats.rules.loader import AREAS_ROOT
from flats.tests.test_pdx_overlays import (
    LANE,
    MACADAM,
    MAIN,
    NEAR,
    REAR_COURT,
    STREET_LOT,
    _plan,
    _street_edges,
    snapshot,
)

DOCS = Path(__file__).resolve().parents[1] / "provenance" / "docs"

#: Two far segments that stretch the map's extent over the test lots
#: (0..80 x 0..120) without coming near them.
PINS = [
    (LineString([(-5000, -5000), (-4990, -5000)]), "FAR ST", "TA"),
    (LineString([(5000, 5000), (5010, 5000)]), "FAR ST", "TA"),
]


def _map(*transit, unclassified=()):
    return pt.TransitMap.build([*PINS, *transit], unclassified)


def _flags(reading, transit, *, plat="unit_lots", drawing=None, edges=None, on=date(2026, 11, 8), **kw):
    return pdx.flags_for(
        reading, zone="CM2", plat=plat, units=4, height_ft=26.0, max_setback_ft=10.0,
        lot=kw.get("lot", STREET_LOT), edges=edges if edges is not None else _street_edges(),
        drawing=drawing, on=on, transit=transit,
    )


def _codes(flags):
    return [f.code for f in flags]


def test_the_held_map_is_the_whole_transit_classification() -> None:
    # 33.910: "Transit Street. A street that is classified in the
    # Transportation System Plan as: A Major Transit Priority Street, Transit
    # Access Street, or Community Transit Street; or A Regional Transitway ..."
    text = (DOCS / "or/multnomah/portland/33.910.definitions.txt").read_text(encoding="utf-8").splitlines()
    assert "Major Transit Priority Street, Transit Access Street, or Community Transit Street" in text[1378]
    traced = json.loads((AREAS_ROOT / pt.TRACED).read_text(encoding="utf-8"))
    loose = json.loads((AREAS_ROOT / pt.UNCLASSIFIED).read_text(encoding="utf-8"))
    assert {f["properties"]["Transit"] for f in traced["features"]} <= set(pt.CLASS_WORDS)
    assert {f["properties"]["Transit"] for f in loose["features"]} <= {None, "UNK"}
    # The layer census (2026-11-08) counts exactly the transit segments held.
    assert len(traced["features"]) == traced["source"]["count"] == 7417
    assert "TA+MTP+RT+RTMTP = 7417" in loose["source"]["note"]
    assert len(loose["features"]) == loose["source"]["count"] == 210


def test_a_street_line_reads_transit_clear_or_maybe() -> None:
    front = _street_edges().edges[0]  # (0, 0) -> (80, 0)
    # The street the line abuts, 30 ft out and parallel: transit.
    got, hits = _map((LineString([(-200, -30), (300, -30)]), "SE DIVISION ST", "TA")).line(front)
    assert got == pt.TRANSIT and len(hits) == 1
    # Nothing within 150 ft: clear.
    assert _map().line(front)[0] == pt.CLEAR
    # A cross street at the corner, square to the line: still clear.
    assert _map((LineString([(110, -300), (110, 300)]), "SE 50TH AVE", "MTP")).line(front)[0] == pt.CLEAR
    # A parallel transit street 120 ft out could be the street (a divided one): maybe.
    assert _map((LineString([(-200, -120), (300, -120)]), "SE DIVISION ST", "TA")).line(front)[0] == pt.MAYBE
    # A segment the plan gives no class, beside the line: maybe.
    loose = _map(unclassified=[LineString([(-200, -30), (300, -30)])])
    assert loose.line(front)[0] == pt.MAYBE


def test_a_main_street_lot_off_every_transit_street_owes_none_of_the_rules() -> None:
    tm = _map()
    got = pt.read(tm, STREET_LOT, _street_edges())
    assert (got.fronts, got.near, got.streets) == (pt.CLEAR, pt.CLEAR, (pt.CLEAR,))
    # 33.415.200 (from 2029 too), 300.B and 330.B all key on a transit
    # street: none is raised, even with nothing drawn to measure.
    for on in (date(2026, 11, 8), date(2029, 1, 1)):
        # (33.415.320's facade rule is not a transit-street rule: it stays.)
        assert _codes(_flags(MAIN, tm, drawing=None, on=on)) == [pdx.MAIN_STREET_SETBACK_FLAG]
    # Without the map every street is still taken as one.
    codes = _codes(_flags(MAIN, None, drawing=None))
    assert {pdx.MAIN_STREET_TRANSIT_FLAG, pdx.MAIN_STREET_VEHICLE_FLAG, pdx.MAIN_STREET_ACTIVE_USE_FLAG} <= set(codes)


def test_a_lot_on_a_transit_street_is_asked_and_told_which() -> None:
    tm = _map((LineString([(-200, -30), (300, -30)]), "SE DIVISION ST", "TA"))
    flags = _flags(MAIN, tm, drawing=_plan(NEAR, LANE, REAR_COURT))
    by = {f.code: f for f in flags}
    assert set(by) == {pdx.MAIN_STREET_TRANSIT_FLAG, pdx.MAIN_STREET_ACTIVE_USE_FLAG}
    assert "SE DIVISION ST (Transit Access Street)" in by[pdx.MAIN_STREET_TRANSIT_FLAG].source
    assert by[pdx.MAIN_STREET_ACTIVE_USE_FLAG].severity == pdx.ACTIVE_USE_NOTICE_SEVERITY


def test_the_townhouse_ban_reads_100_ft_from_the_drawn_houses() -> None:
    # A transit street 200 ft past the lot's front: within the 250 ft the
    # widest street could put its edge 100 ft from the lot, so asked.
    tm = _map((LineString([(-500, -200), (500, -200)]), "NE SANDY BLVD", "MTP"))
    assert pt.read(tm, STREET_LOT, _street_edges()).near == pt.MAYBE
    assert pdx.MAIN_STREET_TRANSIT_FLAG in _codes(_flags(MAIN, tm))
    # Houses drawn at the back of a deep lot, past 250 ft: the ban cannot reach them.
    deep = box(0, 0, 80, 400)
    houses = box(4, 300, 60, 336)
    got = pt.read(tm, deep, None, houses)
    assert got.near == pt.CLEAR and got.fronts == pt.MAYBE


def test_the_vehicle_cap_reads_only_the_transit_street() -> None:
    from flats.tests.test_round2_rulings import F, R, S, _edges

    # A corner lot: the front (y = 0) and a side street (x = 80).
    corner = _edges([(0, 0, 80, 0, F), (80, 0, 80, 120, F), (80, 120, 0, 120, R), (0, 120, 0, 0, S)], [0.0, 90.0])
    # The houses along the side street, a court 40% of the front: past
    # Inner's 30% on the front, nothing on the side street.
    plan = _plan(box(40, 10, 76, 110), None, box(4, 0, 36, 60))
    side = _map((LineString([(110, -500), (110, 500)]), "N WILLIAMS AVE", "MTP"))
    front = _map((LineString([(-500, -30), (500, -30)]), "N WILLIAMS AVE", "MTP"))
    assert pt.read(side, STREET_LOT, corner).streets == (pt.CLEAR, pt.TRANSIT)
    assert pdx.MAIN_STREET_VEHICLE_FLAG not in _codes(_flags(MAIN, side, plat="one_lot", drawing=plan, edges=corner))
    assert pdx.MAIN_STREET_VEHICLE_FLAG in _codes(_flags(MAIN, front, plat="one_lot", drawing=plan, edges=corner))
    assert pdx.MAIN_STREET_VEHICLE_FLAG in _codes(_flags(MAIN, None, plat="one_lot", drawing=plan, edges=corner))


def test_a_line_the_map_cannot_settle_is_never_read_clear() -> None:
    edges = _street_edges()
    # A transit street 55 ft past the rear line (175 ft from the front): the
    # rear might be a street line nothing drew.
    behind = _map((LineString([(-500, 175), (500, 175)]), "SE HAWTHORNE BLVD", "TA"))
    got = pt.read(behind, STREET_LOT, edges)
    assert got.streets == (pt.CLEAR,) and got.fronts == pt.MAYBE
    codes = _codes(_flags(MAIN, behind, plat="one_lot", drawing=None))
    assert pdx.MAIN_STREET_VEHICLE_FLAG in codes and pdx.MAIN_STREET_ACTIVE_USE_FLAG in codes
    # A lot off the map's extent, or no lot: not read.
    assert pt.read(behind, box(9000, 9000, 9080, 9120), edges) is None
    assert pt.read(None, STREET_LOT, edges) is None


def test_the_map_reads_only_the_city() -> None:
    assert isinstance(pdx.transit_map("portland"), pt.TransitMap)
    assert pdx.transit_map("multnomah_unincorporated") is None
    assert pdx.transit_map(None) is None


def _macadam_row():
    from flats.tests.test_quadfit_bridge import row

    pts = list(MACADAM.exterior.coords)
    cls = ["S", "F", "S", "R", "R"]  # the east line is on S Macadam Ave
    edges = [[*pts[i], *pts[i + 1], cls[i]] for i in range(len(pts) - 1)]
    return row(
        TLID="1S1E22BA  -02300", zone="CM2", area_sqft=8907.0, lot_wkb=shapely.to_wkb(MACADAM),
        edges_json=json.dumps(edges), front_bearings_json="[92.7]",
    )


def _screen(tmp_path):
    from flats.encode.load import load_trusted
    from flats.ingest.quadfit import lot_from_row, screen_lot
    from flats.score import relief, slack
    from flats.tests.test_quadfit_bridge import pod

    corpus = load_trusted(strict=False).rules
    r = _macadam_row()
    pdx.with_overlays([r], snapshot(tmp_path))
    (s,) = screen_lot(
        lot_from_row(r, corpus.layers), [pod()], rules=corpus, policy=slack.load_policy(),
        relief=relief.load_policy(), step_deg=30.0,
    )
    return s


def test_macadam_fronts_its_major_transit_priority_street(tmp_path) -> None:
    # 1S1E22BA -02300 (6805 S Macadam, CM2 "d,m"): the city's map classes
    # S Macadam Ave a Major Transit Priority Street.
    s = _screen(tmp_path)
    flags = s.forms["townhomes"].get("flags", [])
    (ban,) = [f for f in flags if f["code"] == pdx.MAIN_STREET_TRANSIT_FLAG]
    assert "S MACADAM AVE (Major Transit Priority Street)" in ban["source"]


def test_a_screened_lot_off_every_transit_street_drops_the_rules(tmp_path, monkeypatch) -> None:
    # The same lot with the map's segments all far away: no transit rule.
    far = pt.TransitMap.build(
        [(LineString([(x, y), (x + 10, y)]), "FAR ST", "TA") for x, y in ((7_600_000, 650_000), (7_700_000, 730_000))]
    )
    monkeypatch.setattr(pt, "load", lambda *a, **k: far)
    s = _screen(tmp_path)
    for form in ("townhomes", "apartment"):
        codes = [f["code"] for f in s.forms[form].get("flags", [])]
        assert pdx.MAIN_STREET_TRANSIT_FLAG not in codes
        assert pdx.MAIN_STREET_ACTIVE_USE_FLAG not in codes
        assert pdx.MAIN_STREET_VEHICLE_FLAG not in codes
