"""Which street lines and directions a front door may face (FOLLOWUPS 64
round 5, batch A).

Where the code makes the doors face a street
(:func:`flats.score.paper.door_limit`) the fit stands the door face within
the code's angle of a street direction the lot abuts
(:func:`flats.ingest.quadfit.door_bearings`), and the drawing is read for a
wall held toward a street line (:func:`flats.ingest.quadfit._door_lines`).

* fg5 #35, 1S201DD04000 (Washington County R-9): a 2 ft jog where the
  frontage steps was its own street direction, 39 degrees off the street,
  and a door 82 degrees off the street passed facing it. A street direction
  needs :data:`~flats.ingest.quadfit.DOOR_LINE_MIN_FT` of street line.
* 1S123AB00100: a frontage bowed into short pieces keeps every direction it
  bends through; only a lone short piece is dropped (coordinator 2026-11-28).
* fg5 #22, 1S212AB00801 (Washington County R-5): the north line is an 8 ft
  street stub, a 98 ft side line and 107 ft that only a private drive on a
  zero-value tract makes a street. The doors faced the north line. A door
  may face a drive only where the code counts it, and Washington County's
  does not for this (coordinator 2026-11-28). Where no public street serves
  the lot, though, the drive is its street for the doors (Steph 2026-11-28).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from flats.ingest.quadfit import (
    CURVE_TURN_MAX_DEG,
    DOOR_LINE_MIN_FT,
    _curved,
    _door_lines,
    _door_streets,
    door_bearings,
    lot_edges,
    street_directions,
)
from flats.rules.loader import _parse_private_drives
from flats.rules.model import PrivateDriveRuling

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
WASHCO = ROOT / "flats/config/jurisdictions/or/washington/_unincorporated.yaml"
WASHCO_LAYER = "or/washington/_unincorporated"

#: s4's rows for the three lots (data/quadfit_ow/s4_lots.parquet, run 134).
JOG = {
    "TLID": "1S201DD04000",
    "jurisdiction": "washington_unincorporated",
    "edges_json": json.dumps([
        [7594890.97, 679297.07, 7594888.74, 679230.8, "R"],
        [7594888.74, 679230.8, 7594589.11, 679248.5, "S"],
        [7594589.11, 679248.5, 7594587.8, 679250.2, "F"],
        [7594587.8, 679250.2, 7594589.51, 679314.28, "F"],
        [7594589.51, 679314.28, 7594890.97, 679297.07, "S"],
    ]),
    "front_bearings_json": "[88.47, 127.6]",
    "street_kind_json": json.dumps([None, None, "street", "street", None]),
}
BOWED = {
    "TLID": "1S123AB00100",
    "jurisdiction": "washington_unincorporated",
    "edges_json": json.dumps([
        [7619697.81, 668058.99, 7619922.95, 668052.69, "S"],
        [7619922.95, 668052.69, 7619919.93, 667966.8, "R"],
        [7619919.93, 667966.8, 7619702.35, 667949.07, "S"],
        [7619702.35, 667949.07, 7619696.11, 667986.9, "F"],
        [7619696.11, 667986.9, 7619706.66, 668000.77, "F"],
        [7619706.66, 668000.77, 7619709.41, 668015.08, "F"],
        [7619709.41, 668015.08, 7619706.08, 668029.26, "F"],
        [7619706.08, 668029.26, 7619697.27, 668040.87, "F"],
        [7619697.27, 668040.87, 7619697.81, 668058.99, "F"],
    ]),
    "front_bearings_json": "[94.23, 52.72]",
    "street_kind_json": json.dumps([None, None, None] + ["street"] * 6),
}
TRACT = {
    "TLID": "1S212AB00801",
    "jurisdiction": "washington_unincorporated",
    "edges_json": json.dumps([
        [7593250.2, 678754.49, 7593258.19, 678754.05, "F"],
        [7593258.19, 678754.05, 7593356.04, 678748.61, "S"],
        [7593356.04, 678748.61, 7593462.89, 678742.68, "F"],
        [7593462.89, 678742.68, 7593459.88, 678652.69, "R"],
        [7593459.88, 678652.69, 7593246.95, 678664.66, "R"],
        [7593246.95, 678664.66, 7593250.2, 678754.49, "F"],
    ]),
    "front_bearings_json": "[176.82, 87.93]",
    "street_kind_json": json.dumps(["street", None, "drive", None, None, "street"]),
}


def _ruling(street: bool, doors: bool | None = None) -> PrivateDriveRuling:
    return PrivateDriveRuling(street=street, doors=doors, quote="x#L1", says="x", note="x")


def _layers(ruling: PrivateDriveRuling | None) -> dict[str, Any]:
    return {WASHCO_LAYER: SimpleNamespace(private_drives=ruling, neighbours={})}


def _lot(row: dict[str, Any], layers: dict[str, Any] | None = None) -> SimpleNamespace:
    edges = lot_edges(row, None, (), layers)
    assert edges is not None
    return SimpleNamespace(edges=edges, front_bearings=edges.front_bearings)


def _near(got: tuple[float, ...], want: float) -> bool:
    return any(abs(b - want) < 0.5 for b in got)


# --- a street direction needs street line behind it -----------------------------


def test_a_two_foot_jog_is_no_street_direction() -> None:
    lot = _lot(JOG, _layers(None))
    assert lot.front_bearings == (88.47, 127.6)
    assert street_directions(lot) == (88.47,)
    got = door_bearings(lot)
    assert _near(got, 88.47) and not _near(got, 127.6)
    # The jog's 2 ft line is no line a wall is credited against, as drawn.
    assert len(_door_lines(lot)) == 1


def test_a_bowed_frontage_keeps_every_direction_it_bends_through() -> None:
    lot = _lot(BOWED, _layers(None))
    # Five touching pieces of 14.6-18.1 ft, no joint turning more than 39
    # degrees: one curved frontage 79 ft long (coordinator 2026-11-28, fg5 Q2).
    assert CURVE_TURN_MAX_DEG == 45.0
    assert len(_curved(_door_streets(lot.edges))) == 5
    # 94 degrees: pieces of 38, 18, 15 and 15 ft within 20 degrees of it.
    # 52.7 degrees: one 17 ft piece, but a piece of the curve.
    assert street_directions(lot) == (94.23, 52.72)
    # Every piece of the frontage is a door line.
    lines = _door_lines(lot)
    got = sorted(round(((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5) for x1, y1, x2, y2 in lines)
    assert got == [15, 15, 15, 17, 18, 38]


def test_a_lone_jog_is_no_curve() -> None:
    # The 2 ft jog touches only the 64 ft line: no run of short pieces.
    lot = _lot(JOG, _layers(None))
    assert _curved(_door_streets(lot.edges)) == frozenset()


def test_short_pieces_too_short_together_are_no_curve() -> None:
    # Two touching stubs, 10 and 8.9 ft (18.9 ft in all), are no curved frontage.
    row = {
        "TLID": "T",
        "jurisdiction": "washington_unincorporated",
        "edges_json": json.dumps([
            [0.0, 0.0, 100.0, 0.0, "R"],
            [100.0, 0.0, 100.0, 100.0, "S"],
            [100.0, 100.0, 16.0, 100.0, "F"],
            [16.0, 100.0, 8.0, 106.0, "F"],
            [8.0, 106.0, 0.0, 110.0, "F"],
            [0.0, 110.0, 0.0, 0.0, "S"],
        ]),
        "front_bearings_json": "[90.0]",
        "street_kind_json": json.dumps([None, None, "street", "street", "street", None]),
    }
    lot = _lot(row, _layers(None))
    lines = _door_streets(lot.edges)
    assert sorted(round(e.length_ft, 1) for e in lines if e.length_ft < 20) == [8.9, 10.0]
    assert _curved(lines) == frozenset()
    assert len(_door_lines(lot)) == 1


def test_a_corner_is_no_curve() -> None:
    # Two touching 15 ft pieces 90 degrees apart turn a corner, not a bend.
    row = {
        "TLID": "T",
        "jurisdiction": "washington_unincorporated",
        "edges_json": json.dumps([
            [0.0, 0.0, 15.0, 0.0, "F"],
            [15.0, 0.0, 15.0, 15.0, "F"],
            [15.0, 15.0, 0.0, 0.0, "S"],
        ]),
        "front_bearings_json": "[90.0, 0.0]",
        "street_kind_json": json.dumps(["street", "street", None]),
    }
    lot = _lot(row, _layers(None))
    assert _curved(_door_streets(lot.edges)) == frozenset()


def test_door_line_minimum_is_twenty_feet() -> None:
    assert DOOR_LINE_MIN_FT == 20.0


def test_a_lot_with_no_traced_edges_keeps_its_front_bearings() -> None:
    lot = SimpleNamespace(edges=None, front_bearings=(10.0, 80.0))
    assert street_directions(lot) == (10.0, 80.0)
    assert door_bearings(lot) == (10.0, 80.0)
    assert _door_lines(lot) == ()


# --- a door faces a private drive only where the code counts it ------------------


def test_a_tract_drive_is_no_door_street_in_washington_county() -> None:
    lot = _lot(TRACT, _layers(_ruling(True, doors=False)))
    drive = lot.edges.edges[2]
    assert drive.length_ft > 100 and not drive.door_street
    assert drive.public_road is False
    # North (176.8 degrees): 8 ft of street stub, the drive no door street:
    # no direction. West (87.9 degrees): 90 ft of public street.
    assert street_directions(lot) == (87.93,)
    got = door_bearings(lot)
    assert _near(got, 87.93) and not _near(got, 176.82)
    assert len(_door_lines(lot)) == 1


def test_a_drive_the_code_counts_is_a_door_street() -> None:
    lot = _lot(TRACT, _layers(_ruling(True)))
    assert lot.edges.edges[2].door_street
    assert _near(door_bearings(lot), 176.82) and _near(door_bearings(lot), 87.93)
    assert len(_door_lines(lot)) == 3


@pytest.mark.parametrize("layers", [None, _layers(None), _layers(_ruling(False))])
def test_a_drive_no_code_counts_is_no_door_street(layers: dict[str, Any] | None) -> None:
    lot = _lot(TRACT, layers)
    assert not lot.edges.edges[2].door_street
    assert not _near(door_bearings(lot), 176.82)


def test_a_drive_on_other_land_is_never_a_door_street() -> None:
    row = {**TRACT, "street_kind_json": json.dumps(["street", None, "drive_off_lot", None, None, "street"])}
    lot = _lot(row, _layers(_ruling(True)))
    assert not lot.edges.edges[2].door_street


#: The tract lot with no public street: every street line a drive.
DRIVE_ONLY = {**TRACT, "street_kind_json": json.dumps(["drive", None, "drive", None, None, "drive"])}


@pytest.mark.parametrize("layers", [None, _layers(None), _layers(_ruling(False)), _layers(_ruling(True, doors=False))])
def test_where_only_a_drive_serves_the_lot_the_drive_is_its_street_for_doors(
    layers: dict[str, Any] | None,
) -> None:
    # Steph 2026-11-28 (rulings 2026-11-28-private-drive-is-the-street-for-doors):
    # "If the only paved surface approaching the home is a private drive,
    # that is the street", whatever the code says of private drives.
    lot = _lot(DRIVE_ONLY, layers)
    assert all(e.door_street for e in lot.edges.edges if e.cls.value in ("front", "street_side"))
    assert _near(door_bearings(lot), 176.82) and _near(door_bearings(lot), 87.93)


def test_a_public_street_on_the_lot_keeps_the_doors_on_it() -> None:
    # 1S212AB00801: public street on the west and a stub on the north, so the
    # Washington County drive is still no door street (fix 4 stands).
    lot = _lot(TRACT, _layers(_ruling(True, doors=False)))
    assert not lot.edges.edges[2].door_street


def test_a_doubtful_drive_is_no_door_street_even_with_no_public_street() -> None:
    row = {**TRACT, "street_kind_json": json.dumps(["drive_off_lot", None, "drive_on_lot", None, None, "drive_off_lot"])}
    lot = _lot(row, None)
    assert not any(e.door_street for e in lot.edges.edges if e.cls.value in ("front", "street_side"))


def test_the_ruling_is_registered() -> None:
    raw = yaml.safe_load((ROOT / "flats/config/rulings.yaml").read_text(encoding="utf-8"))
    got = [r for r in raw if r.get("id") == "2026-11-28-private-drive-is-the-street-for-doors"]
    assert len(got) == 1 and got[0]["kind"] == "ruling"
    assert "only paved surface approaching the home" in got[0]["ruling"]
    assert "flats/ingest/quadfit.py" in got[0]["encoded_in"]


def test_a_line_with_no_kind_on_record_stays_a_door_street() -> None:
    row = {**TRACT, "street_kind_json": None}
    lot = _lot(row, None)
    assert all(e.door_street for e in lot.edges.edges)


# --- the rulings ----------------------------------------------------------------


def test_washington_countys_ruling_counts_private_streets_but_not_for_doors() -> None:
    raw = yaml.safe_load(WASHCO.read_text(encoding="utf-8"))["private_drives"]
    problems: list[str] = []
    got = _parse_private_drives(raw, where="washington", problems=problems)
    assert not problems
    assert got is not None and got.street and got.doors is False and not got.faces_doors


def test_doors_follow_street_unless_set() -> None:
    assert _ruling(True).faces_doors
    assert not _ruling(False).faces_doors
    assert not _ruling(True, doors=False).faces_doors


def test_doors_true_needs_street_true() -> None:
    problems: list[str] = []
    raw = {"street": False, "doors": True, "quote": "x#L1", "says": "x", "note": "x" * 400}
    assert _parse_private_drives(raw, where="x", problems=problems) is None
    assert problems and "doors" in problems[0]
