"""Every placement path ends at the court-in-front-yard gate (Steph 2026-11-08,
rulings.yaml ``2026-11-08-no-front-yard-parking-silent-codes``; FOLLOWUPS 142).

The rescreen of 2026-11-10 (0f2620b3) found 36 GREENs whose court stood
between the building and a street: there the check ran in the fire retry
alone. rel4 (ed1d094d) reads the FINAL drawing in
:func:`flats.ingest.quadfit.court_yard_checked`. These tests prove no
placement step can slip past it: each step in turn is made to hand back a
drawing whose court stands in front of the building, and the lot must come
out held (COURT_FRONT_YARD), never GREEN.
"""

from __future__ import annotations

import dataclasses
import json

import pytest
import shapely

from flats.designs.model import load_catalog
from flats.encode.load import load_trusted
from flats.ingest import quadfit
from flats.ingest.quadfit import court_in_front_yard, lot_from_row, screen_lot
from flats.score import relief, slack
from flats.score.flags import Colour
from flats.score.screen import COURT_FRONT_YARD
from flats.tests.test_quadfit_bridge import X0, Y0, row

pytestmark = pytest.mark.unit

#: The steps that stand the plan somewhere, in the order _screen_lot_once runs
#: them. ``drawing_for`` is the first drawing (called inside the module).
STEPS = (
    "drawing_for",
    "court_turned",
    "front_max_checked",
    "fire_checked",
    "slope_checked",
    "flatter_checked",
)


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


def _lot_row(edges, depth: float, width: float = 100.0, **over):
    """A Portland lot ``width`` x ``depth`` ft off the bridge's origin."""
    return row(
        edges_json=json.dumps(edges),
        frontage_ft=width,
        lot_width_ft=width,
        lot_depth_ft=depth,
        area_sqft=width * depth,
        wkb=shapely.to_wkb(shapely.box(X0 + 5, Y0 + 10, X0 + width - 5, Y0 + depth - 5)),
        lot_wkb=shapely.to_wkb(shapely.box(X0, Y0, X0 + width, Y0 + depth)),
        **over,
    )


def _interior(depth: float = 160.0):
    """One street at the south end (1S2E20DB  -05400's kind, read as one front)."""
    w = 100.0
    edges = [
        [X0, Y0, X0 + w, Y0, "F"],
        [X0 + w, Y0, X0 + w, Y0 + depth, "S"],
        [X0 + w, Y0 + depth, X0, Y0 + depth, "R"],
        [X0, Y0 + depth, X0, Y0, "S"],
    ]
    return _lot_row(edges, depth, front_bearings_json="[0.0]")


def _corner(depth: float = 100.0):
    """A 100 x 100 corner with a rear alley (1N1E13CB  -12700's shape)."""
    w = 100.0
    edges = [
        [X0, Y0, X0 + w, Y0, "F"],
        [X0 + w, Y0, X0 + w, Y0 + depth, "F"],
        [X0 + w, Y0 + depth, X0, Y0 + depth, "A"],
        [X0, Y0 + depth, X0, Y0, "S"],
    ]
    return _lot_row(
        edges, depth, front_bearings_json="[0.0, 90.0]",
        alley_cover_json=json.dumps([None, None, "1" * 20, None]), alley_width_ft=14.0,
    )


def _court_ahead(s):
    """``s``'s drawing with the court moved in front of the building, toward
    the first street line :func:`quadfit.court_yard_lines` names."""
    d = s.drawing
    if not d or not d.get("fits") or not d.get("building"):
        return s
    b = shapely.Polygon(d["building"])
    x0, y0, x1, y1 = b.bounds
    # The south street runs along y = Y0: a court below the building's south face.
    court = shapely.box(x0, max(Y0 + 1.0, y0 - 25.0), x1, y0 - 1.0)
    if court.is_empty or court.area <= 0:
        return s
    bad = {**d, "court": [list(p) for p in court.exterior.coords]}
    return dataclasses.replace(s, drawing=bad)


def _spoil(monkeypatch, name: str) -> None:
    real = getattr(quadfit, name)

    def spoiled(*args, **kwargs):
        got = real(*args, **kwargs)
        if name == "drawing_for":
            if not got or not got.get("fits") or not got.get("building"):
                return got
            b = shapely.Polygon(got["building"])
            x0, y0, x1, _ = b.bounds
            court = shapely.box(x0, max(Y0 + 1.0, y0 - 25.0), x1, y0 - 1.0)
            return {**got, "court": [list(p) for p in court.exterior.coords]}
        return _court_ahead(got)

    monkeypatch.setattr(quadfit, name, spoiled)


@pytest.mark.parametrize("shape", [_interior, _corner], ids=["interior", "corner-alley"])
@pytest.mark.parametrize("step", STEPS)
def test_a_court_any_step_stands_before_the_building_is_held(
    corpus, policies, monkeypatch, shape, step
) -> None:
    designs = load_catalog().active()
    kw = dict(rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    (clean,) = screen_lot(lot_from_row(shape(), corpus.layers), designs, **kw)
    if not (clean.drawing and clean.drawing.get("fits")):
        pytest.skip("the lot draws no fitting plan")
    if clean.signed.triage.name == "red" and clean.screening.triage.name == "red":
        pytest.skip("red both ways: the gate does not read it")
    _spoil(monkeypatch, step)
    (got,) = screen_lot(lot_from_row(shape(), corpus.layers), designs, **kw)
    if not (got.drawing and got.drawing.get("fits")):
        pytest.skip("the spoiled plan draws no fitting plan")
    # The spoiled court survives to the drawing shown (no later step moves
    # it back), and the gate reads it there: held, never GREEN.
    assert court_in_front_yard(got)
    assert got.facts.court_front_yard
    assert COURT_FRONT_YARD in got.signed.reasons or COURT_FRONT_YARD in got.screening.reasons
    assert got.signed.colour is not Colour.green
