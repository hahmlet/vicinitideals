"""Where the rel4 lanes meet in the placement steps (FOLLOWUPS 142, 147, 153, 3(c)).

The entrance hold (FOLLOWUPS 153) reads the FIT's angle; the court's turn
(:func:`flats.ingest.quadfit.court_turned`, 142), the maximum front setback's
slide and snap (147), the hose's and the flatter spot's redraws keep only a new
drawing. So the building shown can stand turned, its doors off the street, while
the fit faced it. :func:`flats.ingest.quadfit.entrance_drawn_checked` reads the
drawing finally kept and holds it as the fit's own turn is held; the court's
turn and the front-max slide refuse a drawing that turns the doors (or, for the
slide, puts the court in a front yard or off the alley stretch) where the
drawing they started from did not.
"""

from __future__ import annotations

import dataclasses

import pytest
import shapely
from shapely import affinity

from flats.ingest.quadfit import drawn_door_turned, entrance_drawn_checked
from flats.score.screen import ENTRANCE_TURNED, Triage
from flats.tests.test_court_front_yard import X0, Y0, _green_plan, corpus, policies  # noqa: F401

pytestmark = pytest.mark.unit


def _with_building(s, ring_geom, *, door_face="width"):
    design = s.design.model_copy(update={"door_face": door_face})
    ring = [list(p) for p in ring_geom.exterior.coords]
    return dataclasses.replace(s, design=design, drawing={**s.drawing, "building": ring})


def _plan(corpus):  # noqa: F811
    behind = shapely.box(X0 + 5, Y0 + 60, X0 + 41, Y0 + 90)
    return _green_plan(corpus, behind)


def test_a_drawing_turned_off_the_street_reads_turned(corpus) -> None:  # noqa: F811
    s, _ = _plan(corpus)
    w, d = s.design.footprint.width_ft, s.design.footprint.depth_ft
    facing = shapely.box(X0 + 2, Y0 + 15, X0 + 2 + w, Y0 + 15 + d)
    turned = affinity.rotate(facing, 90.0, origin="centroid")
    leaning = affinity.rotate(facing, 40.0, origin="centroid")
    assert s.rules.get("entrance_faces_street") is None  # unread: unsettled
    assert not drawn_door_turned(_with_building(s, facing))
    assert drawn_door_turned(_with_building(s, turned))
    assert not drawn_door_turned(_with_building(s, leaning))
    # A design that states no door face is never read.
    assert not drawn_door_turned(_with_building(s, turned, door_face=None))


def test_the_kept_drawing_turned_holds_a_green_out_and_lifts(corpus) -> None:  # noqa: F811
    s, policy = _plan(corpus)
    w, d = s.design.footprint.width_ft, s.design.footprint.depth_ft
    facing = shapely.box(X0 + 2, Y0 + 15, X0 + 2 + w, Y0 + 15 + d)
    turned = _with_building(s, affinity.rotate(facing, 90.0, origin="centroid"))
    assert turned.screening.triage is Triage.green
    out = entrance_drawn_checked(turned, policy=policy, relief=None)
    assert out.facts.entrance_drawn_turned
    assert out.screening.triage is not Triage.green
    assert ENTRANCE_TURNED in out.screening.unchecked or any(
        f.code == "ENTRANCE-TURNED" for f in out.screening.flags
    )
    # Never a red on the hold alone.
    assert out.screening.triage is not Triage.red
    # Facing: nothing to hold, and a stale hold lifts.
    clear = _with_building(s, facing)
    assert entrance_drawn_checked(clear, policy=policy, relief=None) is clear
    stale = dataclasses.replace(out, drawing=clear.drawing)
    lifted = entrance_drawn_checked(stale, policy=policy, relief=None)
    assert not lifted.facts.entrance_drawn_turned
    assert lifted.screening.triage is Triage.green
