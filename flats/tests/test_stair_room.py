"""Room for the precast steps at the doors (FOLLOWUPS 213; Steph 2026-11-20).

rulings.yaml ``2026-11-20-stair-room-reserved``: placement keeps a strip
between each door face and the drawn court or lane as deep as the face's
steps need, and keeps every stair inside the lot.
``2026-11-20-stair-no-room-red-flag``: where there still is no room, RED with
a flag naming the door, what it lands on and by how much.

Covered here: where a unit lands (:func:`flats.ingest.foundation_cap.
stair_room_of`), the room kept (:meth:`flats.designs.model.Design.reserving`,
the fit's wider room, the drawing's strip and lot test), the answer
(:func:`~flats.ingest.foundation_cap.next_room`, ``no_room``, ``reconciled``)
and the screen's loop (:func:`flats.ingest.quadfit.foundation_checked`), worked
once on the answer every search kept (fd8-fix).
"""

from __future__ import annotations

import dataclasses
import json
from types import SimpleNamespace

import pytest
import shapely

from flats.designs.model import StairRoom
from flats.fit.draw import StairLot, draw, stairs_off_lot
from flats.fit.rectangle import Fitter
from flats.foundation import model
from flats.foundation import settings as foundation_settings
from flats.foundation.frame import frame
from flats.ingest import foundation_cap as fc

pytestmark = pytest.mark.unit


# --- where a unit lands ---------------------------------------------------------


def _door(face: str, x_ft: float, units: int) -> model.DoorResult:
    return model.DoorResult(face, x_ft, 30.0, units + 1, 0.0, False, False, 0.0, units=units)


#: An 80 x 25 building with the street along its south face (y = 0).
RING = [[0.0, 0.0], [80.0, 0.0], [80.0, 25.0], [0.0, 25.0], [0.0, 0.0]]
STREET = ((-50.0, -20.0, 150.0, -20.0),)
#: The court flush to the rear wall, the 5 ft standoff inside it.
COURT = [[0.0, 25.0], [92.0, 25.0], [92.0, 72.0], [0.0, 72.0], [0.0, 25.0]]


def _room(doors, *, lot, court=COURT, lane=None, standoff=5.0, beside=False):
    s = foundation_settings.load()
    fr = frame(RING, STREET)
    return fc.stair_room_of(fr, SimpleNamespace(doors=doors), s, lot=lot, court=court, lane=lane,
                            standoff_ft=standoff, beside=beside)


def test_steps_inside_the_standoff_have_room() -> None:
    """Two risers run 53 in: inside the 5 ft standoff off the rear wall, not
    on the stalls -- the court ring is drawn from the wall, standoff and all."""
    s = foundation_settings.load()
    assert model.unit_run_in(2, s) / 12 < 5.0
    got = _room([_door("back", 20.0, 2), _door("front", 20.0, 1)], lot=shapely.box(-10, -15, 100, 90))
    assert got["hits"] == []


def test_a_unit_past_the_standoff_lands_on_the_court_and_names_the_door() -> None:
    s = foundation_settings.load()
    run = model.unit_run_in(4, s) / 12  # 75 in
    got = _room([_door("back", 20.0, 4), _door("back", 60.0, 1)], lot=shapely.box(-10, -15, 100, 90))
    assert [(h["door"], h["hits"]) for h in got["hits"]] == [("back door 1", fc.COURT)]
    assert got["hits"][0]["by_ft"] == pytest.approx(run - 5.0, abs=0.3)
    assert got["need"]["court_ft"] == pytest.approx(run, abs=0.01)
    assert got["need"]["flank_ft"] == 0.0 and got["need"]["lot_ft"] == 0.0


def test_a_unit_past_the_lot_line_and_onto_a_lane() -> None:
    lot = shapely.box(-10, -2, 100, 90)  # the front lot line 2 ft off the wall
    lane = [[30.0, -10.0], [42.0, -10.0], [42.0, -0.05], [30.0, -0.05], [30.0, -10.0]]
    got = _room([_door("front", 10.0, 1), _door("front", 36.0, 1)], lot=lot, lane=lane)
    kinds = {(h["door"], h["hits"]) for h in got["hits"]}
    assert ("front door 1", fc.LOT_LINE) in kinds and ("front door 2", fc.LANE) in kinds
    assert got["need"]["lot_ft"] == pytest.approx(3.5, abs=0.01)
    assert got["need"]["flank_ft"] == pytest.approx(3.5, abs=0.01)


def test_a_beside_court_has_no_standoff_and_is_kept_off_as_a_lane() -> None:
    court = [[0.0, -12.0], [80.0, -12.0], [80.0, -0.05], [0.0, -0.05], [0.0, -12.0]]
    got = _room([_door("front", 10.0, 1)], lot=shapely.box(-10, -30, 100, 90), court=court, beside=True)
    assert [h["hits"] for h in got["hits"]] == [fc.COURT]
    assert got["need"]["flank_ft"] > 0 and got["need"]["court_ft"] == 0.0


# --- the room kept --------------------------------------------------------------


def _pod():
    from flats.tests.test_quadfit_bridge import pod

    return pod()


def test_reserving_raises_the_standoff_and_keeps_the_key() -> None:
    d = _pod()
    kept = d.reserving(StairRoom(court_ft=8.0, flank_ft=4.0, lot_ft=3.0, passes=1))
    assert kept.key == d.key and kept != d and hash(kept) != hash(d)
    assert kept.parking.building_gap_ft == 8.0 and kept.flank_reserve_ft == 4.0
    assert kept.parking.court_depth_ft == pytest.approx(d.parking.court_depth_ft + 8.0 - d.parking.building_gap_ft)
    # A standoff already deeper is not cut.
    assert d.reserving(StairRoom(court_ft=1.0)).parking.building_gap_ft == d.parking.building_gap_ft
    assert d.flank_reserve_ft == 0.0 and d.stairs is None


def test_the_fit_asks_the_flank_strip_across() -> None:
    d = _pod()
    fitter = Fitter(shapely.box(0, 0, 200, 200), angles=(0.0,))
    plain = fitter.fit_design(d, axis_required=True, placement=False)
    kept = fitter.fit_design(d.reserving(StairRoom(flank_ft=6.0)), axis_required=True, placement=False)
    assert kept.across_ft == pytest.approx(plain.across_ft + 6.0)


ENVELOPE = shapely.box(0, 0, 70, 120)
SOUTH = ((0.0, -2.0, 70.0, -2.0),)


def _drawn(*, flank=0.0, stairs=None, lot=None):
    fitter = Fitter(ENVELOPE, angles=(0.0,))
    fit = fitter.fit(50.0, 25.0, allow_flip=False, placement=False, lane_ft=12.0 + flank)
    return draw(fitter, fit, width_ft=50.0, depth_ft=25.0, lane_ft=12.0, court_depth_ft=30.0,
                court_beyond_ft=10.0, street=SOUTH, flank_gap_ft=flank,
                stair_lot=None if stairs is None else StairLot(lot, stairs))


def test_the_drawing_keeps_the_strip_between_the_building_and_its_lane() -> None:
    got = _drawn(flank=5.0)
    assert got is not None and got.fits
    b, lane = got.building.bounds, got.lane.bounds
    gap = lane[0] - b[2] if lane[0] >= b[2] else b[0] - lane[2]
    assert gap == pytest.approx(5.0)
    assert got.room.buffer(1e-6).contains(got.lane)


def test_the_drawing_stands_the_building_back_so_its_steps_stay_on_the_lot() -> None:
    lot = shapely.box(-5, -2, 75, 125)  # the front lot line 2 ft off the envelope
    plain = _drawn()
    assert plain.building.bounds[1] == pytest.approx(0.0, abs=0.51)
    assert stairs_off_lot(plain.building, StairLot(lot, 4.0))
    kept = _drawn(stairs=4.0, lot=lot)
    assert kept is not None and kept.fits
    assert kept.building.bounds[1] >= 2.0 - 0.06
    assert not stairs_off_lot(kept.building, StairLot(lot, 4.0))


def test_a_court_whose_drive_is_not_drawn_still_stands_back_to_keep_the_steps() -> None:
    """fd8b move read F1 (1N1E23BB  -19300, 1N1E28CD  -02700): a court fed
    off a side street, from a rear alley, beside or in a column has a drive
    the drawing does not place (``yard_moves`` False), so its plan is not
    moved back from the street for the yards. The steps stand on the
    building, though: the plan stands back to keep their room, and no further."""
    lot = shapely.box(-5, -2, 75, 125)
    fitter = Fitter(ENVELOPE, angles=(0.0,))
    fit = fitter.fit(50.0, 25.0, allow_flip=False, placement=False, lane_ft=12.0)

    def drawn(stairs):
        return draw(fitter, fit, width_ft=50.0, depth_ft=25.0, lane_ft=12.0, court_depth_ft=30.0,
                    court_beyond_ft=10.0, street=SOUTH, yard=SOUTH, yard_moves=False,
                    stair_lot=None if stairs is None else StairLot(lot, stairs))

    # The first placement (nothing kept) is where it always was: at the street.
    first = drawn(None)
    assert first is not None and first.fits
    assert first.building.bounds[1] == pytest.approx(0.0, abs=0.51)
    kept = drawn(4.0)
    assert kept is not None and kept.fits
    assert not stairs_off_lot(kept.building, StairLot(lot, 4.0))
    # Stood back only as far as the steps need (2 ft past the envelope's front).
    assert 2.0 - 0.06 <= kept.building.bounds[1] <= 2.0 + 1.0


def test_no_window_with_room_still_draws_the_nearest() -> None:
    """Where no window keeps the steps on the lot the plan is drawn where it
    would stand, and the screen reads the steps there (RED)."""
    lot = shapely.box(-5, -2, 75, 122)
    got = _drawn(stairs=200.0, lot=lot)
    assert got is not None and got.fits
    assert stairs_off_lot(got.building, StairLot(lot, 200.0))


def test_a_corner_plan_keeping_its_steps_stands_back_from_both_streets() -> None:
    """FOLLOWUPS 221 F-A (fd8c move read, 1S2E16CB  -04300, Portland CM3):
    on a corner, the plan stood back to keep its steps' room was ranked by
    its distance to the NEAREST street point, so it slid along one street
    and 43 ft away from the other, past the 10 ft maximum front setback.
    Here a corner clip (a lot line, not a street) keeps the north steps'
    strip off the corner: every stair-clear window stands A ft from the
    north street and B ft from the east one with A >= 4 and A + B >= 10.
    Nearest-point ranking took A = 10, B = 0; the farthest street the plan
    faces is least at A = B = 5."""
    w, h = 100.0, 131.6
    lot = shapely.Polygon([(0, 0), (w, 0), (w, h - 6.0), (w - 6.0, h), (0, h)])
    north, east = (0.0, h, w - 6.0, h), (w, 0.0, w, h - 6.0)
    fitter = Fitter(lot, angles=(0.0,))
    fit = fitter.fit(80.0, 30.0, allow_flip=False, placement=False, lane_ft=12.0)

    def drawn(stairs):
        return draw(fitter, fit, width_ft=80.0, depth_ft=30.0, lane_ft=12.0, court_depth_ft=43.0,
                    court_beyond_ft=0.0, street=(north, east),
                    stair_lot=None if stairs is None else StairLot(lot, stairs))

    def gaps(got):
        b = got.building.bounds
        return h - b[3], w - b[2]

    # The first placement keeps no room: it stands against a street, as before.
    first = drawn(None)
    assert first is not None and first.fits
    assert min(gaps(first)) == pytest.approx(0.0, abs=0.6)
    kept = drawn(4.0)
    assert kept is not None and kept.fits
    assert not stairs_off_lot(kept.building, StairLot(lot, 4.0))
    a, b = gaps(kept)
    assert a >= 4.0 - 0.06 and a + b >= 10.0 - 0.6
    assert max(a, b) <= 5.0 + 1.0  # was A = 10 ft, B = 0


# --- the answer -----------------------------------------------------------------


@pytest.fixture(scope="module")
def green():
    from flats.score.screen import Triage
    from flats.tests.test_historic_lists import _screened

    s = _screened("1S3E10BC  -99999", zone="R-5", jurisdiction="gresham")
    clean = dataclasses.replace(s.signed, triage=Triage.green, binds=(), flags=(), reasons=())
    return dataclasses.replace(s, signed=clean, screening=clean)


HITS = [{"door": "back door 2", "risers": 4, "run_ft": 6.25, "hits": fc.COURT, "by_ft": 1.25},
        {"door": "front door 1", "risers": 1, "run_ft": 3.5, "hits": fc.LOT_LINE, "by_ft": 1.5}]
NEED = {"court_ft": 6.25, "flank_ft": 0.0, "lot_ft": 3.5}


def _with_hits(s, hits=HITS, need=NEED):
    return dataclasses.replace(s, foundation={"state": "fits", "stair_room": {"hits": hits, "need": need}})


def test_next_room_widens_what_is_kept_and_stops(green) -> None:
    s = _with_hits(green)
    got = fc.next_room(s)
    assert got == StairRoom(court_ft=6.25, flank_ft=0.0, lot_ft=3.5, passes=1)
    # Already keeping that much: another placement would find no more.
    kept = dataclasses.replace(s, design=s.design.reserving(got))
    assert fc.next_room(kept) is None
    # Out of passes.
    last = dataclasses.replace(s, design=s.design.reserving(StairRoom(passes=fc.STAIR_PASSES)))
    assert fc.next_room(last) is None
    assert fc.next_room(green) is None


def test_no_room_is_red_with_the_flag_naming_each_door(green) -> None:
    from flats.score import flags as flag_plan
    from flats.score.flags import Colour

    out = fc.no_room(_with_hits(green))
    for x in (out.signed, out.screening):
        assert x.colour is Colour.red and fc.STAIR_ROOM in x.reasons
        bind = next(b for b in x.binds if b.check == fc.STAIR_CHECK)
        assert bind.shortfall == pytest.approx(1.5)
        (flag,) = [f for f in x.flags if f.code == fc.STAIR_ROOM_FLAG]
        assert "back door 2" in flag.source and "court" in flag.source
        assert "front door 1" in flag.source and "lot line" in flag.source
        assert "2026-11-20-stair-no-room-red-flag" in bind.source
    assert out.foundation["stair_room"]["state"] == "no_room"
    assert fc.STAIR_ROOM_FLAG in flag_plan.registry()
    assert fc.no_room(out).signed == out.signed  # idempotent


def test_a_lot_already_red_is_left_alone(green) -> None:
    from flats.score.screen import Triage

    red = dataclasses.replace(green.signed, triage=Triage.red, binds=(green.signed.binds or ()))
    s = _with_hits(dataclasses.replace(green, signed=red, screening=red))
    out = fc.no_room(s)
    assert out.signed is red and out.screening is red


def test_reconciled_never_makes_a_lot_greener(green) -> None:
    from flats.score import flags as flag_plan
    from flats.score.flags import Colour
    from flats.score.screen import Triage

    yellow_flag = flag_plan.Flag(fc.NEAR_FLAG, flag_plan.LOT, fc.NEAR_REASON, source="x")
    yellow = dataclasses.replace(green.signed, triage=Triage.yellow, flags=(yellow_flag,))
    first = _with_hits(dataclasses.replace(green, signed=yellow, screening=yellow))
    alt = dataclasses.replace(green, design=green.design.reserving(StairRoom(court_ft=6.25, passes=1)),
                              foundation={"state": "fits", "stair_room": {"hits": [], "need": NEED}})
    out = fc.reconciled(first, alt)
    assert out.signed.colour is Colour.yellow and fc.STAIR_MOVED in out.signed.reasons
    assert out.foundation["stair_room"]["state"] == "moved"
    assert out.foundation["stair_room"]["kept"]["court_ft"] == 6.25
    assert flag_plan.severity_of(
        next(f for f in out.signed.flags if f.code == fc.STAIR_MOVED_FLAG), flag_plan.registry()
    ) >= flag_plan.colour_rules().yellow_at_severity
    # A green first placement takes the kept-room plan as it reads.
    plain = fc.reconciled(_with_hits(green), alt)
    assert plain.signed.colour is Colour.green and fc.STAIR_MOVED not in plain.signed.reasons
    # A view red on the first placement stays red, whatever the second reads
    # (found on 137: 11E25AB04400 read red, then yellow kept-room).
    bind = flag_plan.Bind("fit_ft", 80.0, 90.0, 10.0)
    red = dataclasses.replace(green.signed, triage=Triage.red, binds=(bind,))
    half = _with_hits(dataclasses.replace(green, signed=red, screening=yellow))
    mixed = fc.reconciled(half, alt)
    assert mixed.signed is red and mixed.screening.colour is Colour.yellow


def test_reconciled_red_elsewhere_is_red_on_the_steps(green) -> None:
    from flats.score import flags as flag_plan
    from flats.score.flags import Colour
    from flats.score.screen import Triage

    bind = flag_plan.Bind("fit_ft", 80.0, 90.0, 10.0)
    red = dataclasses.replace(green.signed, triage=Triage.red, binds=(bind,))
    alt = dataclasses.replace(green, signed=red, screening=red)
    out = fc.reconciled(_with_hits(green), alt)
    assert out.signed.colour is Colour.red and fc.STAIR_ROOM in out.signed.reasons
    assert "fit_ft" in next(b for b in out.signed.binds if b.check == fc.STAIR_CHECK).source
    # The kept-room plan red on its own steps' room answers for itself.
    own = fc.no_room(_with_hits(green))
    assert fc.reconciled(_with_hits(green), own) is own


# --- the screen's loop ----------------------------------------------------------


def _yellow(s, code="MEASURE-COURT-TURNS"):
    from flats.score import flags as flag_plan
    from flats.score.screen import Triage

    flag = flag_plan.Flag(code, flag_plan.LOT, "COURT_TURNS", source="x")
    v = dataclasses.replace(s.signed, triage=Triage.yellow, flags=(*s.signed.flags, flag))
    return dataclasses.replace(s, signed=v, screening=v)


def _loop(monkeypatch, first, alt_of):
    """``foundation_checked`` on ``first`` with the cap faked: the first
    placement's steps land (HITS), a placement keeping room has them clear;
    the whole screen again (``_screen_lot_plain``) answers ``alt_of(design)``."""
    from flats.ingest import quadfit

    seen = []

    def plain(lot, designs, **kw):
        seen.append(designs[0])
        return [dataclasses.replace(alt_of(designs[0]), design=designs[0])]

    def cap(s, **kw):
        hits = HITS if s.design.stairs is None else []
        return dataclasses.replace(s, foundation={"state": "fits", "stair_room": {"hits": hits, "need": NEED}})

    monkeypatch.setattr(quadfit, "_screen_lot_plain", plain)
    monkeypatch.setattr(fc, "checked", cap)
    kw = dict(rules=None, policy=None, relief=None, step_deg=30.0, roads=None, terrain=object())
    (out,) = quadfit.foundation_checked(first.lot, [first.design], [first], **kw)
    return out, seen


def test_the_loop_screens_again_keeping_the_room(green, monkeypatch) -> None:
    from flats.ingest import quadfit

    out, seen = _loop(monkeypatch, green, lambda d: green)
    assert [d.stairs for d in seen] == [StairRoom(court_ft=6.25, lot_ft=3.5, passes=1)]
    assert out.design.parking.building_gap_ft == 6.25
    assert out.signed.colour is green.signed.colour
    assert fc.STAIR_MOVED not in out.signed.reasons  # same colour: nothing moved
    # No terrain: the cap is off and nothing is screened again.
    assert quadfit.foundation_checked(green.lot, [green.design], [green], rules=None, policy=None,
                                      relief=None, terrain=None) == [green]


def test_a_better_re_placement_is_held_with_the_flag(green, monkeypatch) -> None:
    """11E25AA02800 (fd8 bound): first YELLOW, the plan with room kept GREEN
    (the narrow-lane reading) -- held YELLOW, FOUNDATION-STAIR-MOVED."""
    from flats.score.flags import Colour

    out, seen = _loop(monkeypatch, _yellow(green), lambda d: green)
    assert len(seen) == 1
    for x in (out.signed, out.screening):
        assert x.colour is Colour.yellow and fc.STAIR_MOVED in x.reasons
        assert any(f.code == fc.STAIR_MOVED_FLAG and "held" in f.source for f in x.flags)


@pytest.mark.parametrize("code", [fc.NEAR_FLAG, fc.CLASS_UNREAD_FLAG, fc.UNMEASURED_FLAG])
def test_a_first_held_only_on_its_own_doors_reads_the_new_green(green, monkeypatch, code) -> None:
    """FOLLOWUPS 221 F-B (1S2E04BA  -15800, 1S2E09BA  -08500, 1S1E12CA  -03600
    first YELLOW on FOUNDATION-NEAR-CAP; 1N1E35DC  -04200 on
    FOUNDATION-CLASS-UNREAD): the first placement was held only on its own
    doors' foundation reading, and the cap, worked again at the new doors,
    is clear. Nothing the first colour stood on is left: GREEN, unflagged."""
    from flats.score.flags import Colour

    out, _ = _loop(monkeypatch, _yellow(green, code), lambda d: green)
    for x in (out.signed, out.screening):
        assert x.colour is Colour.green
        assert fc.STAIR_MOVED not in x.reasons
        assert not any(f.code == fc.STAIR_MOVED_FLAG for f in x.flags)
    assert out.foundation["stair_room"]["state"] == "moved"


def test_a_first_held_on_its_doors_and_more_is_still_held(green, monkeypatch) -> None:
    """F-B's release reaches only the first placement's own foundation
    reading: held on anything else as well (its court's turns), the new
    GREEN is held YELLOW, as before."""
    from flats.score.flags import Colour

    first = _yellow(_yellow(green, fc.NEAR_FLAG))
    out, _ = _loop(monkeypatch, first, lambda d: green)
    for x in (out.signed, out.screening):
        assert x.colour is Colour.yellow
        assert any(f.code == fc.STAIR_MOVED_FLAG and "held" in f.source for f in x.flags)


def test_a_worse_re_placement_reads_worse_with_the_flag(green, monkeypatch) -> None:
    """11E25AA01700 (fd8 bound): first GREEN, the plan with room kept YELLOW
    on its court's turns -- YELLOW as it reads, and FOUNDATION-STAIR-MOVED
    names why (the bound's 1,326 green -> yellow moves named nothing)."""
    from flats.score.flags import Colour

    out, _ = _loop(monkeypatch, green, lambda d: _yellow(green))
    for x in (out.signed, out.screening):
        assert x.colour is Colour.yellow and fc.STAIR_MOVED in x.reasons
        assert any(f.code == "MEASURE-COURT-TURNS" for f in x.flags)
        assert any(f.code == fc.STAIR_MOVED_FLAG and "stands" in f.source for f in x.flags)


def test_a_same_colour_re_placement_on_another_reason_carries_the_flag(green, monkeypatch) -> None:
    """fd8b move read F2 (8 lots): first YELLOW on the cap (NEAR-CAP), the
    plan with room kept YELLOW on its court's turns. The colour is the same
    but what holds it is not: FOUNDATION-STAIR-MOVED says the plan moved."""
    from flats.score.flags import Colour

    first = _yellow(green, code=fc.NEAR_FLAG)
    out, _ = _loop(monkeypatch, first, lambda d: _yellow(green))
    for x in (out.signed, out.screening):
        assert x.colour is Colour.yellow and fc.STAIR_MOVED in x.reasons
        (flag,) = [f for f in x.flags if f.code == fc.STAIR_MOVED_FLAG]
        assert "MEASURE-COURT-TURNS" in flag.source and fc.NEAR_FLAG in flag.source
    # Held on the same thing after the move: nothing to attribute.
    same, _ = _loop(monkeypatch, _yellow(green), lambda d: _yellow(green))
    assert fc.STAIR_MOVED not in same.signed.reasons
    assert not any(f.code == fc.STAIR_MOVED_FLAG for f in same.signed.flags)


def test_a_red_re_placement_is_red_on_the_steps(green, monkeypatch) -> None:
    from flats.score import flags as flag_plan
    from flats.score.flags import Colour
    from flats.score.screen import Triage

    bind = flag_plan.Bind("fit_ft", 80.0, 90.0, 10.0)
    red = dataclasses.replace(green.signed, triage=Triage.red, binds=(bind,))
    out, _ = _loop(monkeypatch, green, lambda d: dataclasses.replace(green, signed=red, screening=red))
    assert out.signed.colour is Colour.red and fc.STAIR_ROOM in out.signed.reasons
    assert out.design.stairs is None  # the first placement, red on its steps' room


def test_the_cap_is_never_worked_inside_a_search(green, monkeypatch) -> None:
    """fd8 bound, 11E25AA00301 / 1S112BD01300: the cap worked inside
    ``_screen_lot_once`` turned the side-door reading red, so
    :func:`side_door_checked` kept the street-facing miss -- RED on
    ``fit_ft`` with no foundation reason. Every search now chooses without
    the cap, and the cap reds the plan the search kept, by name."""
    from flats.foundation import cap as caps
    from flats.ingest import quadfit
    from flats.score import flags as flag_plan
    from flats.score.flags import Colour
    from flats.score.screen import Triage

    def boom(*a, **kw):
        raise AssertionError("the six-step cap was worked inside a search")

    monkeypatch.setattr(fc, "checked", boom)
    # The street-facing plan missed its fit; the side-door plan fits, yellow.
    miss = flag_plan.Bind("fit_ft", 60.0, 80.0, 20.0)
    red = dataclasses.replace(green.signed, triage=Triage.red, binds=(miss,))
    street = dataclasses.replace(green, signed=red, screening=red)
    side = _yellow(green, code="ENTRANCE-SIDE-DOOR")
    monkeypatch.setattr(quadfit, "_street_fit_missed", lambda s, d: (60.0, 80.0))
    monkeypatch.setattr(quadfit, "door_bearings", lambda lot: (0.0,))
    monkeypatch.setattr(quadfit, "_screen_lot_plain", lambda lot, designs, **kw: [side])
    kw = dict(rules=None, policy=None, relief=None, step_deg=30.0, roads=None, terrain=object())
    (kept,) = quadfit.side_door_checked(green.lot, [green.design], [street], **kw)
    assert kept is side

    # The cap, worked once on what the search kept, names itself.
    def over(s, **kw):
        facts = {"state": caps.RED, "height_in": 60.0, "cap_in": 51.5, "over_by_in": 8.5, "words": "w",
                 "stair_room": {"hits": [], "need": NEED}}
        return dataclasses.replace(s, foundation=facts, screening=fc._apply(s.screening, facts),
                                   signed=fc._apply(s.signed, facts))

    monkeypatch.setattr(fc, "checked", over)
    (out,) = quadfit.foundation_checked(green.lot, [green.design], [kept], **kw)
    assert out.signed.colour is Colour.red and fc.FOUNDATION_STEPS_CAP in out.signed.reasons
    assert [b.check for b in out.signed.binds] == [fc.CHECK]


def test_a_real_screen_never_works_the_cap_inside(monkeypatch) -> None:
    """The whole real screen of a lot, the cap patched to fail if worked: no
    pass inside :func:`screen_lot` works it (only :func:`foundation_checked`,
    off without terrain), and the answer keeps the reading it stood on."""
    from flats.ingest.quadfit import lot_from_row, screen_lot
    from flats.score import relief, slack
    from flats.tests.test_historic_lists import _corpus
    from flats.tests.test_quadfit_bridge import row

    def boom(*a, **kw):
        raise AssertionError("the six-step cap was worked inside a search")

    monkeypatch.setattr(fc, "checked", boom)
    corpus = _corpus()
    x0, y0, w, d = 7_650_000.0, 680_000.0, 160.0, 200.0
    lot = shapely.box(x0, y0, x0 + w, y0 + d)
    edges = [[x0, y0, x0 + w, y0, "F"], [x0 + w, y0, x0 + w, y0 + d, "S"],
             [x0 + w, y0 + d, x0, y0 + d, "R"], [x0, y0 + d, x0, y0, "S"]]
    r = row(TLID="1S3E10BC  -99999", zone="R-5", jurisdiction="gresham", area_sqft=w * d,
            frontage_ft=w, lot_width_ft=w, lot_depth_ft=d, edges_json=json.dumps(edges),
            lot_wkb=shapely.to_wkb(lot), wkb=shapely.to_wkb(shapely.box(x0 + 5, y0 + 2, x0 + w - 5, y0 + d - 5)))
    (s,) = screen_lot(lot_from_row(r, corpus.layers), [_pod()], rules=corpus, policy=slack.load_policy(),
                      relief=relief.load_policy(), step_deg=30.0)
    assert s.screened_on is not None and s.screened_on.tlid == s.lot.tlid


def test_a_screen_keeping_room_draws_it(green) -> None:
    """The kept room runs through the real screen: the fit, the drawing and
    every check after them, with the strip and the standoff drawn."""
    from flats.ingest.quadfit import lot_from_row, screen_lot
    from flats.score import relief, slack
    from flats.tests.test_historic_lists import _corpus
    from flats.tests.test_quadfit_bridge import row

    corpus = _corpus()
    x0, y0, w, d = 7_650_000.0, 680_000.0, 160.0, 200.0
    lot = shapely.box(x0, y0, x0 + w, y0 + d)
    edges = [[x0, y0, x0 + w, y0, "F"], [x0 + w, y0, x0 + w, y0 + d, "S"],
             [x0 + w, y0 + d, x0, y0 + d, "R"], [x0, y0 + d, x0, y0, "S"]]
    r = row(TLID="1S3E10BC  -99999", zone="R-5", jurisdiction="gresham", area_sqft=w * d,
            frontage_ft=w, lot_width_ft=w, lot_depth_ft=d, edges_json=json.dumps(edges),
            lot_wkb=shapely.to_wkb(lot), wkb=shapely.to_wkb(shapely.box(x0 + 5, y0 + 2, x0 + w - 5, y0 + d - 5)))
    kept = _pod().reserving(StairRoom(court_ft=8.0, flank_ft=6.0, lot_ft=6.0, passes=1))
    (s,) = screen_lot(lot_from_row(r, corpus.layers), [kept], rules=corpus, policy=slack.load_policy(),
                      relief=relief.load_policy(), step_deg=30.0)
    assert s.design.stairs == kept.stairs
    assert s.drawing and s.drawing.get("fits")
    b = shapely.Polygon(s.drawing["building"])
    if s.drawing.get("lane"):
        assert b.distance(shapely.Polygon(s.drawing["lane"])) == pytest.approx(6.0, abs=0.2)
    assert not stairs_off_lot(b, StairLot(lot, 6.0))


def test_a_kept_room_plan_red_on_a_variance_miss_is_red_on_the_steps(green, monkeypatch) -> None:
    """fd8 bound, 1S1E19CC  -10100 / 1S1E16CC  -05900 / 1N1E36BA  -05700: the
    kept-room plan missed its fit with a variance path -- triage YELLOW,
    colour RED -- and passed as it read, red with only FOUNDATION-NEAR-CAP or
    -CLASS-UNREAD on it. It is RED on the steps' room, by name."""
    from flats.score import flags as flag_plan
    from flats.score.flags import Colour
    from flats.score.screen import Triage

    miss = flag_plan.Bind("fit_ft", 100.0, 120.0, 20.0, relief="variance", relief_tier="discretionary")
    soft = dataclasses.replace(green.signed, triage=Triage.yellow, binds=(miss,))
    assert soft.colour is Colour.red and soft.triage is Triage.yellow
    alt = dataclasses.replace(green, signed=soft, screening=dataclasses.replace(soft, binds=()))
    out = fc.reconciled(_with_hits(green), alt)
    assert out.design.stairs is None
    for x in (out.signed, out.screening):
        assert x.colour is Colour.red and fc.STAIR_ROOM in x.reasons
    # Through the loop too.
    out, _ = _loop(monkeypatch, green, lambda d: alt)
    assert out.signed.colour is Colour.red and fc.STAIR_ROOM in out.signed.reasons
