"""Two parking-court leftovers (FOLLOWUPS 3(c), 33(c)).

3(c) -- Steph 2026-09-28 (rulings.yaml ``2026-09-28-partial-alley``): a rear
alley that runs only PART of the rear line is the court's travel lane only
where it abuts the court and is long enough. The fit used to compare the
covered run's length alone; now the court has to stand against it
(:class:`flats.fit.draw.AlleyStretch`): the fit keeps the alley as the aisle
only where some window does (:func:`flats.fit.draw.stretch_window`), the
drawing prefers such a window, and the final drawing is read
(:func:`flats.ingest.quadfit.alley_court_checked`).

33(c) -- where the envelope is s5o's, the court's ground was the whole lot
less the carve. A lot whose rear alone is in doubt now has its ground cut
from the front and side yards; every other s5o-envelope lot is held out of
GREEN (``court_ground_unread``).
"""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import numpy as np
import pytest
import shapely
from shapely import affinity

from flats.fit.draw import AlleyStretch, _on_stretch, court_on_stretch, draw, stretch_window
from flats.fit.rectangle import Fit, Fitter

pytestmark = pytest.mark.unit


def _stretch(*lines, row=36.0, reach=11.0) -> AlleyStretch:
    got = AlleyStretch.of((tuple(lines),), row, reach)
    assert got is not None
    return got


# --- the geometry ---------------------------------------------------------------

BUILDING = shapely.box(0, 0, 48, 40)
COURT = shapely.box(0, 40, 48, 65)


def test_the_court_stands_on_the_stretch_only_where_it_covers_the_row() -> None:
    """Far edge at y=65; the alley line 10 ft behind it. A 45 ft stretch
    under the whole court serves a 36 ft row; a 30 ft one does not; a
    stretch beside the court's far edge, not behind it, does not either."""
    assert court_on_stretch(BUILDING, COURT, _stretch((0.0, 75.0, 45.0, 75.0)))
    assert not court_on_stretch(BUILDING, COURT, _stretch((0.0, 75.0, 30.0, 75.0)))
    # Half a foot short is the walk's own step: still served.
    assert court_on_stretch(BUILDING, COURT, _stretch((0.0, 75.0, 35.6, 75.0)))
    # Under only 20 ft of the court: the row's end stalls back into the yard.
    assert not court_on_stretch(BUILDING, COURT, _stretch((28.0, 75.0, 100.0, 75.0)))
    # Too far behind the court: no back-out into it.
    assert not court_on_stretch(BUILDING, COURT, _stretch((0.0, 80.0, 45.0, 80.0), reach=11.0))


def test_the_reading_is_the_same_at_any_angle_and_either_axis() -> None:
    stretch_on = _stretch((0.0, 75.0, 45.0, 75.0))
    stretch_off = _stretch((0.0, 75.0, 30.0, 75.0))
    for angle in (0.0, 17.0, 90.0, 133.0, 250.0):
        b = affinity.rotate(BUILDING, angle, origin=(0, 0))
        c = affinity.rotate(COURT, angle, origin=(0, 0))

        def turned(s: AlleyStretch) -> AlleyStretch:
            lines = [
                affinity.rotate(shapely.LineString([(x1, y1), (x2, y2)]), angle, origin=(0, 0))
                for x1, y1, x2, y2 in s.lines
            ]
            return AlleyStretch.of(
                (tuple((*ln.coords[0], *ln.coords[1]) for ln in lines),), s.row_ft, s.reach_ft
            )

        assert court_on_stretch(b, c, turned(stretch_on)), angle
        assert not court_on_stretch(b, c, turned(stretch_off)), angle


def test_a_run_carried_across_a_bend_is_one_run() -> None:
    """Two stretches meeting at a bend are one run, as
    :func:`flats.geom.alley.usable_run_ft` walks them; a gap makes two."""
    bent = AlleyStretch.of((((0.0, 75.0, 20.0, 75.0), (20.0, 75.0, 40.0, 75.0)),), 36.0, 11.0)
    gapped = AlleyStretch.of((((0.0, 75.0, 20.0, 75.0), (22.0, 75.0, 40.0, 75.0)),), 36.0, 11.0)
    assert bent.chain == (0, 0) and gapped.chain == (0, 1)
    assert court_on_stretch(BUILDING, COURT, bent)
    assert not court_on_stretch(BUILDING, COURT, gapped)
    assert AlleyStretch.of(((),), 36.0, 11.0) is None


def test_the_window_test_reads_what_the_drawing_test_reads() -> None:
    """The vectorised test the placement uses answers as the drawing's
    does, court for court."""
    rng = np.random.default_rng(3)
    for _ in range(400):
        x0 = rng.uniform(-20, 60)
        across, deep, court = rng.uniform(20, 60), rng.uniform(20, 45), rng.uniform(15, 35)
        b = shapely.box(x0, 0, x0 + across, deep)
        c = shapely.box(x0, deep, x0 + across, deep + court)
        lines = []
        for _ in range(int(rng.integers(1, 3))):
            a = rng.uniform(-40, 120)
            y = deep + court + rng.uniform(-3, 15)
            lines.append((a, y, a + rng.uniform(5, 70), y + rng.uniform(-2, 2)))
        s = AlleyStretch.of((tuple(lines),), rng.uniform(18, 45), rng.uniform(1, 12))
        fast = _on_stretch(
            np.array([x0]), np.array([x0 + across]), np.array([deep + court]), s,
            np.asarray(s.lines),
        )[0]
        assert bool(fast) is court_on_stretch(b, c, s)


# --- the placement --------------------------------------------------------------

#: A 100 x 75 envelope, the street south, a rear alley along the lot's
#: north line (y = 75) on its eastern 45 ft only.
ENVELOPE = shapely.box(0, 0, 100, 75)
SOUTH = (0.0, -10.0, 100.0, -10.0)
EAST_STRETCH = _stretch((55.0, 75.0, 100.0, 75.0))
WEST_STUB = _stretch((0.0, 75.0, 30.0, 75.0))


def _fit():
    fitter = Fitter(ENVELOPE, angles=(0.0,))
    fit = fitter.fit(36.0, 40.0, allow_flip=False, placement=False, lane_ft=12.0)
    return fitter, fit


def _drawn(fitter, fit, stretch=None, listing=None):
    return draw(
        fitter, fit, width_ft=36.0, depth_ft=40.0, lane_ft=12.0, court_depth_ft=25.0,
        court_beyond_ft=25.0, street=(SOUTH,), stretch=stretch, listing=listing,
    )


def test_the_court_is_drawn_against_the_stretch() -> None:
    fitter, fit = _fit()
    plain = _drawn(fitter, fit)
    kept = _drawn(fitter, fit, EAST_STRETCH)
    assert not court_on_stretch(plain.building, plain.court, EAST_STRETCH)
    assert kept.fits and court_on_stretch(kept.building, kept.court, EAST_STRETCH)
    listed: list = []
    _drawn(fitter, fit, EAST_STRETCH, listing=listed)
    assert listed
    for where in listed:
        got = draw(
            fitter, fit, width_ft=36.0, depth_ft=40.0, lane_ft=12.0, court_depth_ft=25.0,
            court_beyond_ft=25.0, street=(SOUTH,), where=where,
        )
        assert court_on_stretch(got.building, got.court, EAST_STRETCH)


def test_no_window_on_a_stub_shorter_than_the_row() -> None:
    """A 30 ft stub serves no 36 ft row: no window stands the court on it,
    the drawing keeps the nearest window, and the caller reads it off."""
    fitter, fit = _fit()
    kw = dict(width_ft=36.0, depth_ft=40.0, court_depth_ft=25.0, court_beyond_ft=25.0)
    assert stretch_window(fitter, fit, stretch=EAST_STRETCH, **kw)
    assert not stretch_window(fitter, fit, stretch=WEST_STUB, **kw)
    got = _drawn(fitter, fit, WEST_STUB)
    assert got.fits and not court_on_stretch(got.building, got.court, WEST_STUB)


def test_without_a_stretch_the_drawing_is_unchanged() -> None:
    fitter, fit = _fit()
    a, b = _drawn(fitter, fit), _drawn(fitter, fit, None)
    assert a.building.equals(b.building) and a.court.equals(b.court)


# --- which courts lean on the stretch -----------------------------------------


def test_only_a_court_backing_out_into_a_partial_alley_needs_the_stretch() -> None:
    from flats.ingest.quadfit import alley_stretch
    from flats.tests.test_screen import ALLEY_FED, ALLEY_LOT, DESIGN, rules

    runs = (((0.0, 75.0, 60.0, 75.0),),)
    part = dataclasses.replace(ALLEY_LOT, alley_rear_whole=False, alley_rear_run_ft=60.0)
    fit = Fit(fits=True, width_ft=56, depth_ft=36, best_depth_ft=90, slack_ft=10, across_ft=68)
    lot = SimpleNamespace(facts=part, rear_runs=runs)
    got = alley_stretch(lot, DESIGN, rules(**ALLEY_FED), None, fit)
    assert got is not None and got.row_ft == pytest.approx(36.0)
    # The alley runs the whole line: anywhere along it will do.
    whole = SimpleNamespace(facts=ALLEY_LOT, rear_runs=runs)
    assert alley_stretch(whole, DESIGN, rules(**ALLEY_FED), None, fit) is None
    # The run too short: the court keeps its own aisle, and needs no stretch.
    short = SimpleNamespace(facts=dataclasses.replace(part, alley_rear_run_ft=20.0), rear_runs=runs)
    assert alley_stretch(short, DESIGN, rules(**ALLEY_FED), None, fit) is None
    # The code does not let the alley be the aisle.
    assert alley_stretch(lot, DESIGN, rules(parking_alley_access_required=True), None, fit) is None
    # A column or beside court is another plan.
    assert alley_stretch(lot, DESIGN, rules(**ALLEY_FED), None, dataclasses.replace(fit, column=True)) is None


# --- the net on the final drawing -----------------------------------------------


def test_a_court_drawn_off_the_stretch_holds_a_green_out(monkeypatch) -> None:
    from flats.encode.load import load_trusted
    from flats.ingest import quadfit
    from flats.score.screen import ALLEY_COURT_OFF_STRETCH, Triage
    from flats.tests.test_court_front_yard import _green_plan
    from flats.tests.test_quadfit_bridge import X0, Y0

    corpus = load_trusted(strict=False).rules
    court = shapely.box(X0 + 5, Y0 + 50, X0 + 41, Y0 + 80)
    s, policy = _green_plan(corpus, court)
    assert s.screening.triage is Triage.green
    # No partial alley: nothing to read.
    assert quadfit.alley_court_checked(s, policy=policy, relief=None) is s
    off = _stretch((X0 + 60.0, Y0 + 85.0, X0 + 120.0, Y0 + 85.0), row=36.0, reach=6.0)
    on = _stretch((X0 + 0.0, Y0 + 85.0, X0 + 60.0, Y0 + 85.0), row=36.0, reach=6.0)
    monkeypatch.setattr(quadfit, "alley_stretch", lambda *a, **k: off)
    held = quadfit.alley_court_checked(s, policy=policy, relief=None)
    assert held.facts.alley_court_off_stretch
    assert held.screening.triage is not Triage.green
    assert ALLEY_COURT_OFF_STRETCH in held.screening.reasons
    assert any(f.code == "PARKING-ALLEY-COURT-OFF-STRETCH" for f in held.screening.flags)
    # The court shown on the stretch: a hold set before lifts.
    monkeypatch.setattr(quadfit, "alley_stretch", lambda *a, **k: on)
    lifted = quadfit.alley_court_checked(held, policy=policy, relief=None)
    assert not lifted.facts.alley_court_off_stretch
    assert lifted.screening.triage is Triage.green
    # Nothing fitting drawn where the stretch is needed: read as off it.
    bare = dataclasses.replace(s, drawing=None)
    assert quadfit.court_off_stretch(bare)


# --- 33(c): the court's ground on s5o's envelope ---------------------------------


def test_an_s5o_envelope_holds_the_court_out_of_green() -> None:
    from flats.score.screen import COURT_GROUND_UNREAD, LotFacts, Triage, screen
    from flats.tests.test_screen import DESIGN, POLICY, fit, rules

    facts = LotFacts(lot_sqft=6000, frontage_ft=60, lot_width_ft=60)
    clear = screen(rules(), facts, DESIGN, fit(), policy=POLICY)
    assert clear.triage is Triage.green
    held = screen(
        rules(), dataclasses.replace(facts, court_ground_unread=True), DESIGN, fit(), policy=POLICY
    )
    assert held.triage is not Triage.green
    assert COURT_GROUND_UNREAD in held.reasons
    assert any(f.code == "PARKING-COURT-GROUND-UNREAD" for f in held.flags)


def test_the_fallback_envelope_says_its_yards_are_unread_and_the_flats_one_does_not() -> None:
    from flats.ingest.quadfit import envelope_for
    from flats.tests import test_rear_alley_part as part

    corpus = part.load_trusted(strict=False).rules
    lot = part.lot_from_row(part.row(None), corpus.layers)
    got = part.resolved(corpus, lot, rear_alley=False)
    env = envelope_for(lot, got)
    assert env.source == "flats" and env.yards_read
    bare = envelope_for(dataclasses.replace(lot, edges=None), got)
    assert bare.source == "quadfit" and not bare.yards_read
    # The court's ground there is the lot less the carve: wider than the
    # yards would leave, which is why the lot is held.
    assert bare.ground.area > env.ground.area
    assert bare.court_in_unread_yards and not env.court_in_unread_yards
    # With no lot polygon there is no ground past s5o's envelope: the court
    # is held inside the envelope, out of every yard s5o cut, so no hold.
    shapeless = envelope_for(dataclasses.replace(lot, lot_geom=None), got)
    assert shapeless.source == "quadfit" and shapeless.ground is None
    assert not shapeless.court_in_unread_yards


def test_a_lot_whose_rear_alone_is_unread_gets_its_ground_from_the_yards() -> None:
    """A rear line on the alley and one off it, the alley's rear exempt and
    no second resolution handed in: the envelope stays s5o's, but the court's
    ground needs no rear, so it is cut from the front and side yards."""
    from flats.ingest.quadfit import envelope_for
    from flats.tests import test_rear_alley_part as part

    corpus = part.load_trusted(strict=False).rules
    edges = [list(e) for e in part.STUB_EDGES]
    # Two rear legs: the west line split, its south half on the alley.
    x1, y1, x2, y2 = (float(v) for v in edges[2][:4])
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    edges[2:3] = [[x1, y1, mx, my, "A"], [mx, my, x2, y2, "R"]]
    import json

    lot = part.lot_from_row(
        part.row(None, edges_json=json.dumps(edges), alley_cover_json=None), corpus.layers
    )
    lot = dataclasses.replace(lot, observed={**lot.observed, "alley_at_rear": True})
    got = part.resolved(corpus, lot, rear_alley=True)
    if "setback_rear_ft" not in got.exempted:
        pytest.skip("the corpus does not exempt this rear on the alley")
    from flats.ingest.quadfit import rear_off_alley

    if not rear_off_alley(lot.edges):
        pytest.skip("the edges do not read as a rear on and off the alley")
    env = envelope_for(lot, got)
    assert env.source == "quadfit" and env.yards_read
    assert env.ground.area < lot.lot_geom.area - 1.0


# --- end to end, on a real partial-alley lot --------------------------------------


def _part_lot(cover: str):
    import json

    from flats.tests import test_rear_alley_part as part

    corpus = part.load_trusted(strict=False).rules
    lot = part.lot_from_row(part.row(json.dumps([None, None, cover, None])), corpus.layers)
    return corpus, lot, part.pod()


def _screened(corpus, lot, design):
    from flats.ingest.quadfit import screen_lot
    from flats.score import relief, slack

    (s,) = screen_lot(
        lot, [design], rules=corpus, policy=slack.load_policy(), relief=relief.load_policy(),
        step_deg=15.0,
    )
    return s


def test_a_partial_alley_long_enough_is_the_aisle_and_the_court_is_drawn_on_it() -> None:
    """1S2E05AB -11900 with the alley along the southern 14 of 18 cover rays:
    a 61 ft run for a 54 ft row. The court backs out into it, and is drawn
    against it."""
    from flats.ingest.quadfit import alley_stretch, court_off_stretch

    corpus, lot, design = _part_lot("1" * 14 + "0" * 4)
    s = _screened(corpus, lot, design)
    assert s.lot.facts.alley_rear_run_ft and s.lot.facts.alley_rear_run_ft > 54.0
    assert alley_stretch(s.lot, s.design, s.rules, s.envelope, s.fit) is not None
    assert s.drawing and s.drawing["fits"]
    assert not court_off_stretch(s)
    assert not s.facts.alley_court_off_stretch


def test_no_window_against_the_stretch_and_the_court_keeps_its_own_aisle(monkeypatch) -> None:
    """Where no window stands the court against the covered run, the alley
    is no aisle: the run a court can stand behind is none, and the fit is
    charged the court's own aisle."""
    from flats.ingest import quadfit

    corpus, lot, design = _part_lot("1" * 14 + "0" * 4)
    monkeypatch.setattr(quadfit, "_court_reaches_stretch", lambda *a, **k: False)
    s = _screened(corpus, lot, design)
    assert s.lot.facts.alley_rear_run_ft == 0.0
    assert quadfit.alley_stretch(s.lot, s.design, s.rules, s.envelope, s.fit) is None
    assert not quadfit.court_off_stretch(s)


def test_the_reasons_have_words() -> None:
    from app.api.routers.ui_flats import _REASON_WORDS
    from flats.score.screen import ALLEY_COURT_OFF_STRETCH, COURT_GROUND_UNREAD

    assert ALLEY_COURT_OFF_STRETCH in _REASON_WORDS
    assert COURT_GROUND_UNREAD in _REASON_WORDS
