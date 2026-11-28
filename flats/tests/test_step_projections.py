"""How far into a required yard each city lets the precast steps stand
(FOLLOWUPS 214; :mod:`flats.rules.step_projections`).

Every row is held to its stored code text: the cited file and lines exist,
every quote is on those lines, every printed length is printed there. Then
the reading: a city with no row keeps every setback whole, the tightest
reading of a unit stands, a street yard stays measured from a sidewalk
easement and never nearer than a utility easement, and a unit off the
ground its yards leave lands in a yard and is kept on the next placement.
"""

from __future__ import annotations

import dataclasses
import math
from types import SimpleNamespace

import pytest
import shapely

from flats.designs.model import StairRoom
from flats.foundation import settings as foundation_settings
from flats.geom.envelope import Setbacks
from flats.ingest import foundation_cap as fc
from flats.rules import step_projections as sp

pytestmark = pytest.mark.unit

FS = foundation_settings.load()


def _kept(jurisdiction, zone, risers):
    return sp.kept(jurisdiction, zone, risers, riser_in=FS.riser_in, handrail_risers=FS.handrail_risers)


# --- the printed figures -----------------------------------------------------------


@pytest.mark.parametrize(("printed", "ft"), [
    ("2-1/2 feet", 2.5), ("30 inches", 2.5), ("three feet", 3.0), ("three-foot", 3.0), ("2½ ft.", 2.5),
    ("36 in", 3.0), ("24 inches", 2.0), ("5 ft.", 5.0), ("4 feet", 4.0), ("thirty-six inches", 3.0),
])
def test_a_printed_length_reads_as_printed(printed, ft) -> None:
    assert sp.length_ft(printed) == pytest.approx(ft)


@pytest.mark.parametrize("printed", ["", "feet", "a few feet", "3 meters"])
def test_what_is_not_a_length_is_refused(printed) -> None:
    with pytest.raises(ValueError):
        sp.length_ft(printed)


ROWS = sp.rows()


def test_the_file_holds_the_cities_read() -> None:
    assert {r.jurisdiction for r in ROWS} == {
        "or/multnomah/portland", "or/multnomah/_unincorporated", "or/multnomah/gresham",
        "or/multnomah/troutdale", "or/multnomah/fairview", "or/washington/_unincorporated",
        "or/washington/beaverton", "or/washington/hillsboro", "or/washington/cornelius",
        "or/washington/tigard", "or/washington/durham", "or/washington/king-city", "or/washington/sherwood",
        "or/clackamas/milwaukie", "or/clackamas/sandy", "or/clackamas/_unincorporated", "or/clackamas/canby",
        "or/clackamas/oregon-city", "or/clackamas/wilsonville", "or/clackamas/tualatin",
    }
    assert len({r.id for r in ROWS}) == len(ROWS)
    assert {r.raw.get("kind", sp.STEPS) for r in ROWS} <= set(sp.KINDS)


@pytest.mark.parametrize("row", [r for r in ROWS if r.raw.get("kind") == sp.SILENT], ids=lambda r: r.id)
def test_a_silent_code_lets_the_steps_into_every_yard(row) -> None:
    """Steph 2026-11-27 (2026-11-27-steps-allowed-where-silent)."""
    assert set(row.yards) == set(sp.YARDS) and all(a.entire and a.from_line_ft is None for a in row.yards.values())
    assert row.up_to_in is None and row.over_in is None


@pytest.mark.parametrize("row", ROWS, ids=lambda r: r.id)
def test_every_quote_is_on_the_cited_lines(row) -> None:
    text = sp.cited_text(row.cite).lower()
    assert row.quote, f"{row.id}: no quote"
    for q in row.quote:
        assert " ".join(q.split()).lower() in text, f"{row.id}: {q!r} not at {row.cite}"


def _lengths(row):
    for key in ("up_to", "over"):
        if row.raw.get(key) is not None:
            yield str(row.raw[key])
    for a in row.yards.values():
        for key in ("into", "from_line"):
            v = a.printed.get(key)
            if v is not None and v.strip().lower() != sp.ENTIRE and "percent" not in v:
                yield v


@pytest.mark.parametrize("row", ROWS, ids=lambda r: r.id)
def test_every_printed_figure_is_printed_there(row) -> None:
    """The YAML holds the code's printed figure, not a derived one."""
    text = sp.cited_text(row.cite).lower()
    for v in _lengths(row):
        assert v.lower() in text, f"{row.id}: {v!r} not printed at {row.cite}"
    for a in row.yards.values():
        if a.share is not None:
            assert f"{a.printed['into'].split()[0]} percent" in text


@pytest.mark.parametrize("row", ROWS, ids=lambda r: r.id)
def test_every_zone_a_row_names_reads(row) -> None:
    zones = ["ANY"] if row.zones is None else sorted(row.zones)
    for z in zones:
        _kept(row.jurisdiction, z, range(1, 13))


# --- the reading ---------------------------------------------------------------------

SB = Setbacks(front_ft=10.0, side_ft=5.0, rear_ft=15.0)


def test_a_city_with_no_row_keeps_every_setback_whole() -> None:
    """Gladstone's only uncovered allowance sits under its accessory uses:
    held for Steph, so no row and every setback whole."""
    k = _kept("or/clackamas/gladstone", "R-7.2", range(1, 9))
    assert k.none and k.rows == ()
    assert sp.setbacks_kept(SB, k) == SB


def test_a_zone_the_row_does_not_name_keeps_every_setback_whole() -> None:
    k = _kept("or/washington/cornelius", "R-7", range(1, 9))
    assert k.none


def test_portland_low_steps_take_the_whole_yard_and_a_railing_the_twenty_percent() -> None:
    """33.110: up to 2-1/2 ft anywhere in the setback; above it 20 percent
    of the depth, never nearer than three feet. A unit with a railing is
    read above any printed figure (the tightest reading stands)."""
    low = sp.setbacks_kept(SB, _kept("or/multnomah/portland", "R5", [2]))
    assert (low.front_ft, low.side_ft, low.rear_ft) == (0.0, 0.0, 0.0)
    high = sp.setbacks_kept(SB, _kept("or/multnomah/portland", "R5", [FS.handrail_risers]))
    assert high.front_ft == pytest.approx(8.0)
    assert high.side_ft == pytest.approx(4.0)  # 20 % of 5 ft; three feet from the line does not bind
    assert high.rear_ft == pytest.approx(12.0)


def test_the_tightest_reading_of_every_unit_stands() -> None:
    both = _kept("or/multnomah/portland", "R5", [1, FS.handrail_risers])
    assert sp.setbacks_kept(SB, both).front_ft == pytest.approx(8.0)


def test_a_street_yard_stays_off_the_sidewalk_and_the_utility_easement() -> None:
    k = _kept("or/multnomah/portland", "R5", [1])
    eased = dataclasses.replace(SB, front_ft=12.0)  # 10 ft from a 2 ft sidewalk easement
    assert sp.setbacks_kept(eased, k, sidewalk_ft=2.0).front_ft == pytest.approx(2.0)
    assert sp.setbacks_kept(eased, k, sidewalk_ft=2.0, easement_ft=5.0).front_ft == pytest.approx(5.0)
    # The side yard is no street yard: the easement does not floor it.
    assert sp.setbacks_kept(eased, k, easement_ft=5.0).side_ft == 0.0


def test_a_street_side_the_code_does_not_name_stays_whole() -> None:
    """Milwaukie 19.501.2.B names front, side and rear yards; a street side
    yard is its own yard and keeps its whole setback (the front's, where
    the code does not tell it apart)."""
    k = _kept("or/clackamas/milwaukie", "R-7", [2])
    got = sp.setbacks_kept(SB, k)
    assert got.front_ft == pytest.approx(7.0)
    assert got.street_side_ft == pytest.approx(10.0)
    assert got.side_ft == pytest.approx(3.0)


def test_washington_county_low_steps_get_nothing() -> None:
    """418-1.2 names steps over 30 inches only: a unit at or under it reads
    no row and keeps the whole yard; one above it projects 30 inches into
    the front."""
    j = "or/washington/_unincorporated"
    platform = 4 * FS.riser_in
    assert platform <= 30.0 and FS.handrail_risers == 4
    assert sp.setbacks_kept(SB, _kept(j, "R-5", [3])).front_ft == pytest.approx(10.0)
    got = _kept(j, "R-5", [5])
    assert sp.setbacks_kept(SB, got).front_ft == pytest.approx(7.5)


def test_every_row_that_holds_is_a_permission_and_the_most_generous_stands() -> None:
    """Clackamas VR-5/7: 903.06 keeps a deck 10 feet off the front line;
    note [14] lets a porch 4 feet into the front yard. On a 20 ft front
    the steps take 903.06's 10 ft; on a 12 ft front note [14]'s 8 ft."""
    k = _kept("or/clackamas/_unincorporated", "VR57", [2])
    assert sp.setbacks_kept(dataclasses.replace(SB, front_ft=20.0), k).front_ft == pytest.approx(10.0)
    assert sp.setbacks_kept(dataclasses.replace(SB, front_ft=12.0), k).front_ft == pytest.approx(8.0)
    # A railed unit is taller than 903.06's 30 inches: note [14] alone.
    tall = _kept("or/clackamas/_unincorporated", "VR57", [FS.handrail_risers])
    assert sp.setbacks_kept(dataclasses.replace(SB, front_ft=20.0), tall).front_ft == pytest.approx(16.0)


def test_the_specific_stairs_sentence_governs_the_side_yard() -> None:
    """Gresham 9.0901.A.2 and Troutdale 5.020.B.2 name the stairs for the
    front and rear only: the side yard stays whole."""
    for j, zone, front in (("or/multnomah/gresham", "LDR-7", 0.0), ("or/multnomah/troutdale", "LDR-1", 5.0)):
        got = sp.setbacks_kept(SB, _kept(j, zone, [2, FS.handrail_risers]))
        assert got.front_ft == pytest.approx(front) and got.side_ft == pytest.approx(5.0)


def test_a_silent_zone_takes_the_whole_setback() -> None:
    got = sp.setbacks_kept(SB, _kept("or/washington/tigard", "TMU", [1, 6]))
    assert (got.front_ft, got.side_ft, got.rear_ft) == (0.0, 0.0, 0.0)


@pytest.mark.parametrize(("printed", "ft"), [
    ("ten (10) feet", 10.0), ("five (5) feet", 5.0), ("two and one-half feet", 2.5), ("eighteen inches", 1.5),
])
def test_a_code_s_doubled_numeral_reads_once(printed, ft) -> None:
    assert sp.length_ft(printed) == pytest.approx(ft)


def test_a_share_never_comes_nearer_than_its_floor() -> None:
    a = sp.Allowance(share=0.2, from_line_ft=3.0)
    assert a.kept_ft(10.0) == pytest.approx(8.0)
    assert a.kept_ft(3.5) == pytest.approx(3.0)
    assert a.kept_ft(2.0) == pytest.approx(2.0)  # never more than the setback itself
    assert sp.Allowance(from_line_ft=3.0).kept_ft(10.0) == pytest.approx(3.0)
    assert sp.Allowance(into_ft=2.5).kept_ft(2.0) == 0.0


def test_a_railing_reads_above_every_figure() -> None:
    assert sp.readings_in(3, riser_in=7.25, handrail_risers=4) == (21.75,)
    got = sp.readings_in(4, riser_in=7.25, handrail_risers=4)
    assert got[0] == pytest.approx(29.0) and math.isinf(got[1])


# --- where a unit lands ---------------------------------------------------------------

from flats.tests.test_stair_room import _door  # noqa: E402

from flats.foundation import model  # noqa: E402
from flats.foundation.frame import frame  # noqa: E402

RING = [[0.0, 0.0], [80.0, 0.0], [80.0, 25.0], [0.0, 25.0], [0.0, 0.0]]
STREET = ((-50.0, -20.0, 150.0, -20.0),)
LOT = shapely.box(-10, -15, 100, 90)


def _room(doors, yards):
    fr = frame(RING, STREET)
    return fc.stair_room_of(fr, SimpleNamespace(doors=doors), FS, lot=LOT, court=None, lane=None,
                            standoff_ft=5.0, beside=False, yards=yards)


def test_a_unit_off_its_ground_lands_in_a_yard() -> None:
    """The building stands at the front setback; the steps may not project:
    the unit is on the lot but in the front yard."""
    ground = shapely.box(-5, 0, 95, 85)  # the front setback line on the wall
    got = _room([_door("front", 20.0, 2)], {0: ground})
    assert [h["hits"] for h in got["hits"]] == [fc.YARD]
    run = model.unit_run_in(2, FS) / 12
    assert got["need"]["lot_ft"] == pytest.approx(run, abs=0.01)
    assert got["need"][fc.YARD_RISERS] == 2


def test_a_unit_on_the_ground_its_yards_leave_has_room() -> None:
    near = shapely.box(-5, 0, 95, 85)
    open_ = shapely.box(-5, -10, 95, 85)  # the steps may use 10 ft of the yard
    got = _room([_door("front", 20.0, 2), _door("front", 60.0, 1)], {0: near, 1: open_, 2: open_})
    assert got["hits"] == [] and fc.YARD_RISERS not in got["need"]


def test_a_count_the_map_does_not_hold_reads_the_whole_setback() -> None:
    near = shapely.box(-5, 0, 95, 85)
    got = _room([_door("front", 20.0, 3)], {0: near, 1: shapely.box(-5, -10, 95, 85)})
    assert [h["hits"] for h in got["hits"]] == [fc.YARD]


def test_no_yards_reads_no_yard() -> None:
    got = _room([_door("front", 20.0, 2)], None)
    assert got["hits"] == []


def test_past_the_lot_line_is_not_also_a_yard() -> None:
    fr = frame(RING, STREET)
    got = fc.stair_room_of(fr, SimpleNamespace(doors=[_door("front", 20.0, 2)]), FS, lot=shapely.box(-10, -1, 100, 90),
                           court=None, lane=None, standoff_ft=5.0, beside=False, yards={0: shapely.box(-5, 0, 95, 85)})
    assert [h["hits"] for h in got["hits"]] == [fc.LOT_LINE]


def test_next_room_keeps_the_yards_a_unit_that_tall_needs(monkeypatch) -> None:
    room = StairRoom(lot_ft=4.5, passes=1)
    s = SimpleNamespace(design=SimpleNamespace(stairs=room), foundation={"stair_room": {
        "hits": [{"door": "front door 1", "risers": 2, "run_ft": 4.42, "hits": fc.YARD, "by_ft": 4.4}],
        "need": {"court_ft": 0.0, "flank_ft": 0.0, "lot_ft": 4.42, fc.YARD_RISERS: 2}}})
    got = fc.next_room(s)
    assert got == StairRoom(lot_ft=4.5, yard_risers=2, passes=2)
    again = SimpleNamespace(design=SimpleNamespace(stairs=got), foundation=s.foundation)
    assert fc.next_room(again) is None



# --- the ground the yards leave ----------------------------------------------------


def _square_edges(size=100.0):
    from flats.geom.edges import Edge, EdgeClass, LotEdges, Tier, bearing_deg

    ring = [(0.0, 0.0), (size, 0.0), (size, size), (0.0, size)]
    classes = [EdgeClass.front, EdgeClass.side, EdgeClass.rear, EdgeClass.side]
    out = tuple(Edge(x1=a[0], y1=a[1], x2=b[0], y2=b[1], length_ft=math.hypot(b[0] - a[0], b[1] - a[1]),
                     bearing_deg=bearing_deg(a[0], a[1], b[0], b[1]), cls=c)
                for a, b, c in zip(ring, ring[1:] + ring[:1], classes, strict=True))
    return LotEdges(tier=Tier.clean, edges=out, front_bearings=(out[0].bearing_deg,), frontage_ft=size,
                    convexity=1.0)


def _screened(jurisdiction, zone, *, setbacks=SB, stairs=None):
    lot = shapely.box(0, 0, 100, 100)
    here = SimpleNamespace(lot_geom=lot, edges=_square_edges(), zone=zone, sidewalk_easement_ft=None,
                           facts=SimpleNamespace(easement_street_ft=None))
    env = SimpleNamespace(geom=shapely.box(5, 10, 95, 85), setbacks=setbacks)
    return SimpleNamespace(envelope=env, rules=SimpleNamespace(jurisdiction=jurisdiction, zone=zone),
                           screened_on=None, lot=here, design=SimpleNamespace(stairs=stairs))


@pytest.fixture
def plain_lines(monkeypatch):
    from flats.ingest import quadfit

    monkeypatch.setattr(quadfit, "dedicated", lambda edges, rules, zone=None: edges)
    monkeypatch.setattr(quadfit, "lot_line_buffer_ft", lambda rules: 0.0)
    return quadfit


def test_the_ground_each_count_may_stand_on(plain_lines) -> None:
    """Portland R5 on a 100 ft square, 10/5/15 ft yards: low steps anywhere
    on the lot, a unit with a railing 20 percent into each yard, a count
    the map does not reach (key 0) kept out of every yard."""
    got = plain_lines.stair_yards_of(_screened("or/multnomah/portland", "R5"))
    assert got.rule == "pdx-33.110-low, pdx-33.110-high"
    assert got.ground[0].area == pytest.approx(90 * 75, rel=0.01)
    assert got.ground[1].area == pytest.approx(100 * 100, rel=0.01)
    assert got.ground[FS.handrail_risers].area == pytest.approx(92 * 80, rel=0.01)
    assert got.ground[1] is got.ground[2]  # one cut per distinct reading


def test_a_silent_city_keeps_every_count_out_of_the_yards(plain_lines) -> None:
    got = plain_lines.stair_yards_of(_screened("or/clackamas/gladstone", "R-7.2"))
    assert got.rule == "none" and len({id(g) for g in got.ground.values()}) == 1
    assert got.ground[0].area == pytest.approx(90 * 75, rel=0.01)


def test_quadfit_envelope_is_the_ground_for_every_count(plain_lines) -> None:
    s = _screened("or/multnomah/portland", "R5", setbacks=None)
    got = plain_lines.stair_yards_of(s)
    assert list(got.ground) == [0] and got.ground[0] is s.envelope.geom


def test_the_kept_strip_stands_on_the_yards_of_every_count_up_to_the_tallest(plain_lines) -> None:
    room = StairRoom(lot_ft=6.0, yard_risers=FS.handrail_risers, passes=1)
    got = plain_lines.stair_lot_of(_screened("or/multnomah/portland", "R5", stairs=room))
    assert got.depth_ft == 6.0 and got.lot.area == pytest.approx(92 * 80, rel=0.01)
    # No yard hit: the lot line, as before FOLLOWUPS 214.
    lot_only = plain_lines.stair_lot_of(_screened("or/multnomah/portland", "R5", stairs=StairRoom(lot_ft=6.0)))
    assert lot_only.lot.area == pytest.approx(100 * 100)
    silent = plain_lines.stair_lot_of(_screened("or/clackamas/gladstone", "R-7.2", stairs=room))
    assert silent.lot.area == pytest.approx(90 * 75, rel=0.01)
