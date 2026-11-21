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
and the screen's loop (:func:`flats.ingest.quadfit._stair_room`).
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


def test_no_window_with_room_still_draws_the_nearest() -> None:
    """Where no window keeps the steps on the lot the plan is drawn where it
    would stand, and the screen reads the steps there (RED)."""
    lot = shapely.box(-5, -2, 75, 122)
    got = _drawn(stairs=200.0, lot=lot)
    assert got is not None and got.fits
    assert stairs_off_lot(got.building, StairLot(lot, 200.0))


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


def test_the_loop_screens_again_keeping_the_room(green, monkeypatch) -> None:
    from flats.ingest import quadfit

    seen = []

    def fake(lot, designs, **kw):
        seen.append(designs[0])
        return [dataclasses.replace(green, design=designs[0],
                                    foundation={"state": "fits", "stair_room": {"hits": [], "need": NEED}})]

    monkeypatch.setattr(quadfit, "_screen_lot_once", fake)
    kw = dict(rules=None, policy=None, relief=None, step_deg=30.0, roads=None, bound=True, pool=None,
              terrain=object(), room=True)
    out = quadfit._stair_room(_with_hits(green), green.lot, **kw)
    assert [d.stairs for d in seen] == [StairRoom(court_ft=6.25, lot_ft=3.5, passes=1)]
    assert out.design.parking.building_gap_ft == 6.25
    assert out.signed.colour is green.signed.colour
    # Clear steps: nothing screened again.
    seen.clear()
    assert quadfit._stair_room(green, green.lot, **kw) is green and not seen


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
