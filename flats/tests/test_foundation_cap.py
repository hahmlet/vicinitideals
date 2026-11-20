"""The six-step cap inside the screen pass (FD8; Steph 2026-11-20).

:func:`flats.ingest.foundation_cap.checked` runs last in ``_screen_lot_once``,
after the sewer: RED only when every method open to the lot fails the cap,
YELLOW where the best is within 2 in over, where the ground class is unread
and B is over, or where the ground could not be read; a note within 2 in
under and where the steps would run off the lot. Never makes a lot GREEN.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from flats.foundation import cap as caps
from flats.ingest import foundation_cap as fc

pytestmark = pytest.mark.unit

STREET = ((7649990.0, 680000.0, 7650070.0, 680000.0),)


class _Plane:
    """A fake elevation model: ground rising ``rise`` ft per ft north."""

    def __init__(self, rise: float, *, blank: bool = False) -> None:
        self.rise, self.blank = rise, blank

    def z_reader(self, ring, *, coarse: bool = False):
        if self.blank:
            return None, None, None
        return (lambda pts: 100.0 + self.rise * (np.asarray(pts, dtype=float).reshape(-1, 2)[:, 1] - 680000.0)), "dem_1m", 1.0


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    fc._CACHE.clear()
    monkeypatch.setattr(fc, "dem_of", lambda terrain: terrain)
    yield
    fc._CACHE.clear()


@pytest.fixture(scope="module")
def green():
    from flats.score.screen import Triage
    from flats.tests.test_historic_lists import _screened

    s = _screened("1S3E10BC  -99999", zone="R-5", jurisdiction="gresham")
    clean = dataclasses.replace(s.signed, triage=Triage.green, binds=(), flags=(), reasons=())
    return dataclasses.replace(s, signed=clean, screening=clean)


def _checked(s, terrain, classes=("B", None)):
    import shapely

    return fc.checked(s, terrain=terrain, streets=lambda: STREET, lot_geom=shapely.box(7649950, 679950, 7650100, 680100),
                      classes=classes, tlid="1S3E10BC  -99999")


def test_no_elevation_model_leaves_the_lot_alone(green) -> None:
    out = fc.checked(green, terrain=None, streets=lambda: STREET, lot_geom=None, classes=None)
    assert out is green


def test_flat_ground_fits_and_keeps_green(green) -> None:
    from flats.score.flags import Colour

    out = _checked(green, _Plane(0.0))
    assert out.foundation["state"] == caps.FITS
    assert out.signed.colour is Colour.green and not out.signed.flags
    assert out.foundation["door_face_rule"]


def test_steep_ground_is_red_with_the_cap_reason_and_names_the_door(green) -> None:
    from flats.score.flags import Colour

    out = _checked(green, _Plane(0.3))
    assert out.foundation["state"] == caps.RED
    assert out.signed.colour is Colour.red and out.screening.colour is Colour.red
    assert fc.FOUNDATION_STEPS_CAP in out.signed.reasons
    bind = next(b for b in out.signed.binds if b.check == fc.CHECK)
    assert bind.source.startswith("foundation: a door needs more than six steps on every method")
    assert "door" in bind.source and "2026-11-20" in bind.source
    assert bind.threshold == 51.5 and bind.shortfall > 2.0
    again = fc.checked(out, terrain=_Plane(0.3), streets=lambda: STREET, lot_geom=None, classes=("B", None))
    assert again.signed.binds == out.signed.binds and again.signed.reasons == out.signed.reasons


def test_unread_ground_is_yellow_never_green(green) -> None:
    from flats.score.flags import Colour

    out = _checked(green, _Plane(0.0, blank=True))
    assert out.foundation["state"] == fc.UNMEASURED
    assert out.signed.colour is Colour.yellow
    assert [f.code for f in out.signed.flags] == [fc.UNMEASURED_FLAG]


def _facts(state: str, **more):
    return {"state": state, "words": f"foundation: {state}", "height_in": 53.0, "cap_in": 51.5,
            "over_by_in": 1.5, **more}


@pytest.mark.parametrize(
    ("state", "flag", "reason"),
    [
        (caps.NEAR, fc.NEAR_FLAG, fc.NEAR_REASON),
        (caps.CLASS_UNREAD, fc.CLASS_UNREAD_FLAG, fc.CLASS_UNREAD_REASON),
        (fc.UNMEASURED, fc.UNMEASURED_FLAG, fc.UNMEASURED_REASON),
    ],
)
def test_held_states_turn_green_yellow_at_or_over_the_line(green, state, flag, reason) -> None:
    from flats.score import flags as flag_plan
    from flats.score.flags import Colour

    out = fc._apply(green.signed, _facts(state))
    assert out.colour is Colour.yellow and reason in out.reasons
    assert [f.code for f in out.flags] == [flag]
    line = flag_plan.colour_rules().yellow_at_severity
    assert flag_plan.severity_of(out.flags[0], flag_plan.registry()) >= line
    assert fc._apply(out, _facts(state)) == out  # idempotent


@pytest.mark.parametrize("facts", [_facts(caps.CLOSE), _facts(caps.FITS, stair_reach=["front door 1"])])
def test_notes_do_not_move_the_colour(green, facts) -> None:
    from flats.score import flags as flag_plan
    from flats.score.flags import Colour

    out = fc._apply(green.signed, facts)
    assert out.colour is Colour.green and out.flags
    line = flag_plan.colour_rules().yellow_at_severity
    assert all(flag_plan.severity_of(f, flag_plan.registry()) < line for f in out.flags)


def test_nothing_becomes_green_and_red_stays_unattributed(green) -> None:
    from flats.score.screen import Triage

    yellow = dataclasses.replace(green.signed, triage=Triage.yellow)
    assert fc._apply(yellow, _facts(caps.FITS)).triage is Triage.yellow
    red = dataclasses.replace(green.signed, triage=Triage.red)
    assert fc._apply(red, _facts(caps.RED)) is red


def test_every_flag_is_in_the_register() -> None:
    from flats.score import flags as flag_plan

    reg = flag_plan.registry()
    for code in (*fc.YELLOW_FLAGS, *fc.NOTE_FLAGS):
        assert code in reg, code


def test_the_row_carries_the_cap_facts(green) -> None:
    import json

    from flats.ingest.quadfit import row_for

    out = _checked(green, _Plane(0.3))
    got = json.loads(row_for(out)[fc.ROW_COLUMN])
    assert got["state"] == caps.RED and got["door"]


def test_classes_are_matched_whole_with_spaces(tmp_path) -> None:
    import pandas as pd

    p = tmp_path / "status.parquet"
    pd.DataFrame({"tlid": ["1S3E10BC  -99999", "1S3E10BC"], "ground_class": ["B", "D"],
                  "alt_ground_class": [None, "C"]}).to_parquet(p)
    rows = [{"TLID": "1S3E10BC  -99999"}, {"TLID": "1S3E10BC -99999"}]
    assert fc.with_classes(rows, p) == 1
    assert fc.classes_of(rows[0]) == ("B", None) and fc.classes_of(rows[1]) is None
