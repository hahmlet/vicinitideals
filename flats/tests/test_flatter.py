"""A flatter spot for the pod on the same ground (FOLLOWUPS 57).

A lot whose front rises 10% and whose back is level: the plan stood nearest
the street reads a closer look on the grade, and the level ground behind
holds the same plan. The search moves it there -- and only where every other
check, the fire hose route first, still passes on the new drawing.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

pytest.importorskip("rasterio")

import numpy as np  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import box  # noqa: E402

from flats.encode.load import load_trusted  # noqa: E402
from flats.fit import slope as slope_mod  # noqa: E402
from flats.fit.slope import Terrain  # noqa: E402
from flats.ingest import flatter, quadfit  # noqa: E402
from flats.ingest.quadfit import lot_from_row, screen_lot, with_steep  # noqa: E402
from flats.score import relief, slack  # noqa: E402
from flats.tests.dem import plane, write_dem  # noqa: E402
from flats.tests.test_fire import DESIGN, X0, Y0, bridge_row  # noqa: E402

pytestmark = pytest.mark.unit

WIDTH, DEPTH = 80.0, 120.0
LOT = box(X0, Y0, X0 + WIDTH, Y0 + DEPTH)


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


def row(depth: float = DEPTH, width: float = WIDTH) -> dict[str, object]:
    edges = [
        [X0, Y0, X0 + width, Y0, "F"],
        [X0 + width, Y0, X0 + width, Y0 + depth, "S"],
        [X0 + width, Y0 + depth, X0, Y0 + depth, "R"],
        [X0, Y0 + depth, X0, Y0, "S"],
    ]
    return bridge_row(
        area_sqft=width * depth,
        frontage_ft=width,
        lot_width_ft=width,
        lot_depth_ft=depth,
        edges_json=json.dumps(edges),
        wkb=shapely.to_wkb(box(X0 + 5, Y0 + 10, X0 + width - 5, Y0 + depth - 5)),
        lot_wkb=shapely.to_wkb(box(X0, Y0, X0 + width, Y0 + depth)),
    )


def terrain(tmp_path: Path, z) -> Terrain:
    where = write_dem(tmp_path / "dem" / "tile.tif", LOT.bounds, z)
    return Terrain(where.parent, None)


def front_hill(x, y):
    """10% rising for the first 22 m (72 ft) from the street, level beyond."""
    return np.where(y < 22.0, (22.0 - y) * -0.10, 0.0)


def run(corpus, policies, t: Terrain, *, depth: float = DEPTH):
    lot = with_steep(lot_from_row(row(depth), corpus.layers), t)
    (s,) = screen_lot(
        lot, [DESIGN], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0,
        terrain=t,
    )
    return s


def building_depth(s) -> float:
    """How far the building's near wall stands from the street line, in feet."""
    ring = s.drawing["building"]
    return min(y for _, y in ring) - Y0


def slope_flagged(s) -> bool:
    return any(f.code == "SLOPE-GRADE" for f in s.signed.flags)


@pytest.fixture
def unmoved(monkeypatch):
    monkeypatch.setattr(quadfit, "flatter_checked", lambda s, *a, **k: s)


def test_the_plan_moves_to_level_ground_behind_the_hill(tmp_path, corpus, policies, monkeypatch) -> None:
    t = terrain(tmp_path, front_hill)
    with monkeypatch.context() as m:
        m.setattr(quadfit, "flatter_checked", lambda s, *a, **k: s)
        before = run(corpus, policies, t)
    assert before.facts.site_grade_pct > slope_mod.load_rules().grade_green_max_pct
    assert slope_flagged(before)

    after = run(corpus, policies, t)
    assert after.facts.site_grade_pct <= slope_mod.load_rules().grade_green_max_pct
    assert not slope_flagged(after)
    assert building_depth(after) > building_depth(before)
    assert after.drawing["fits"]
    assert after.facts.fire_route_tried and after.facts.fire_route_ft is not None
    assert after.facts.fire_route_ft <= float(after.rules.get("fire_access_max_ft"))
    assert after.signed.colour.value == "green"


def test_a_lot_that_is_level_behind_nowhere_is_left_where_it_stood(tmp_path, corpus, policies, monkeypatch) -> None:
    t = terrain(tmp_path, plane(8.0))
    with monkeypatch.context() as m:
        m.setattr(quadfit, "flatter_checked", lambda s, *a, **k: s)
        before = run(corpus, policies, t)
    after = run(corpus, policies, t)
    assert after.drawing == before.drawing
    assert after.facts.site_grade_pct == before.facts.site_grade_pct
    assert slope_flagged(after)


def test_a_spot_the_hose_cannot_reach_is_not_taken(tmp_path, corpus, policies, monkeypatch) -> None:
    """Level ground only far back: the hose route to a building stood there is
    over 150 ft, so the plan stays where it was."""
    deep = lambda x, y: np.where(y < 62.0, (62.0 - y) * -0.10, 0.0)  # noqa: E731
    t = terrain(tmp_path, deep)
    with monkeypatch.context() as m:
        m.setattr(quadfit, "flatter_checked", lambda s, *a, **k: s)
        before = run(corpus, policies, t, depth=260.0)
    tried: list[bool] = []
    real = flatter._no_worse

    def spy(base, cand):
        got = real(base, cand)
        tried.append(got)
        return got

    monkeypatch.setattr(flatter, "_no_worse", spy)
    after = run(corpus, policies, t, depth=260.0)
    assert tried and not any(tried)
    assert after.drawing == before.drawing
    assert slope_flagged(after)


def test_a_stated_maximum_front_setback_caps_the_search(tmp_path, corpus, policies, monkeypatch) -> None:
    t = terrain(tmp_path, front_hill)
    seen: list[float | None] = []
    real = flatter._max_front_ft

    def spy(s, street):
        got = real(s, street)
        seen.append(got)
        return got

    monkeypatch.setattr(flatter, "_max_front_ft", spy)
    run(corpus, policies, t)
    assert seen

    monkeypatch.setattr(flatter, "_max_front_ft", lambda s, street: 20.0)
    capped = run(corpus, policies, t)
    assert building_depth(capped) <= 20.0 + flatter.FRONT_TOL_FT
    assert slope_flagged(capped)


def test_surface_grades_a_pad_as_the_terrain_does(tmp_path) -> None:
    t = terrain(tmp_path, front_hill)
    surface = t.surface(LOT)
    for ground in (
        [box(X0 + 10, Y0 + 10, X0 + 66, Y0 + 46)],
        [box(X0 + 10, Y0 + 80, X0 + 66, Y0 + 112)],
        [box(X0 + 10, Y0 + 30, X0 + 66, Y0 + 60), box(X0 + 10, Y0 + 60, X0 + 66, Y0 + 90)],
    ):
        a, b = t.grade(ground), surface.grade(ground)
        assert a is not None and b is not None
        assert a.source == b.source
        assert b.pct == pytest.approx(a.pct, abs=0.15)


def test_a_drive_across_ground_the_plan_may_not_use_is_not_clear(tmp_path, corpus, policies, unmoved) -> None:
    t = terrain(tmp_path, front_hill)
    s = run(corpus, policies, t)
    street = quadfit._street_lines(s.lot)
    # the same lane stood 60 ft further back, its way in crossing the first 30 ft
    moved = dict(s.drawing, lane=[[x, y + 60.0] for x, y in s.drawing["lane"]])
    assert flatter._drive_clear(s.drawing, s, street)
    blocked = dataclasses.replace(s.lot, carve=box(X0, Y0, X0 + WIDTH, Y0 + 30.0))
    assert not flatter._drive_clear(moved, dataclasses.replace(s, lot=blocked), street)
