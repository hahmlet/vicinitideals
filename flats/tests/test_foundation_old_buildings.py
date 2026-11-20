"""FD6 foundation model, slice 2: old buildings under the pod (FD6 5.8, FD7), each
lot's own footing depth, the ground grid and the building frame.

The FD7 numbers are hard-coded from ``FD7_infill_cases.py`` (Factory-Sim
docs/research, read only), run 2026-11-19; a live cross-check against that file
runs when it is on this machine (``FD7_REFERENCE_DIR``) and is skipped otherwise.
"""

from __future__ import annotations

import importlib.util
import math
import os
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from flats.tests.foundation_key import key_settings
from flats.foundation import classify, infill, lot, measure, model, oldbuild, rows, settings
from flats.foundation import ground as grounds
from flats.foundation.frame import SIX_UV, frame

#: The FD6 answer key's dimensions (production carries the framing; see foundation_key).
S = key_settings()
PROD = settings.load()
#: FD7 is written at one 18 in footing depth.
S18 = S.replace(use_frost_register=False)

FD7_DIR = Path(os.environ.get("FD7_REFERENCE_DIR", r"C:\Users\Steph\Repos\Factory-Sim\docs\research"))
FD7 = FD7_DIR / "FD7_infill_cases.py"

#: FD7_infill_cases.py CASES: (name, wall_ft, floor_sf, corner, longest gap ft) and
#: remedies(): bridge, deepen the wall, slab -- (low, high) dollars, or None past reach.
FD7_CASES = [
    ("corner, 2 ft in each way", 4, 4, True, 2, (103.044729, 176.105502), (145.506738, 239.403914), (484.518519, 975.777778)),
    ("corner, 6 ft in each way", 12, 36, True, 6, None, (436.520213, 718.211743), (1160.666667, 2382.0)),
    ("corner block, 12 x 12 ft", 24, 144, True, 12, None, (873.040425, 1436.423485), (3442.666667, 7128.0)),
    ("a 10 ft stretch in the middle of a long wall", 10, 60, False, 10, (157.26037, 260.977708), (363.766844, 598.509785), (1667.777778, 3436.666667)),
    ("one whole end (25 ft wall, 10 ft in)", 45, 250, False, 25, None, (1636.950798, 2693.294034), (5682.407407, 11786.111111)),
    ("one whole long side (80 ft wall, 8 ft in)", 120, 640, False, 80, None, (4365.202127, 7182.117425), (13922.962963, 28924.444444)),
    ("a 28 x 25 ft basement right across the pod", 81, 700, False, 28, None, (2946.511436, 4847.929262), (15190.740741, 31561.111111)),
]


def _box(x0: float, y0: float, x1: float, y1: float) -> oldbuild.Outline:
    return oldbuild.Outline(((((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))),), "B1", 1925)


def _flat_record(**inputs: object) -> measure.Measured:
    return measure.measure(grounds.plane(S, 0, 0), S, tlid="1S1E  -1", inputs=inputs)


def _money(c) -> tuple[float, float]:
    return float(c.low), float(c.high)


# ---------------------------------------------------------------- FD7 cases, priced


@pytest.mark.parametrize("case", FD7_CASES, ids=[c[0] for c in FD7_CASES])
def test_fd7_case_costs(case) -> None:
    _, wall, floor, corner, longest, bridge, deepen, slab = case
    e = infill.Exposure(wall, floor, corner, longest)
    remedy, b = infill.b_cost(e, S18, S18.embed_in)
    if bridge is None:
        assert remedy == infill.DEEPEN
        assert _money(b) == pytest.approx(deepen, abs=1e-5)
    else:
        assert remedy == infill.BRIDGE
        assert _money(b) == pytest.approx(bridge, abs=1e-5)
    assert _money(infill.a_cost(e, S18)) == pytest.approx(slab, abs=1e-5)


def test_deepening_follows_the_lots_own_footing_depth() -> None:
    # 12 in footing: 6.0 ft of old backfill under it, not 5.5 (FD7 run with FILL_UNDER_FOOTING_FT = 6.0).
    _, b = infill.b_cost(infill.Exposure(120, 640, False, 80), S18, 12.0)
    assert _money(b) == pytest.approx((4749.854364, 7812.271751), abs=1e-5)


def _fd7():
    name = "_fd7_infill_cases"
    if name in sys.modules:
        return sys.modules[name]
    before, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    sys.path.insert(0, str(FD7_DIR))
    try:
        spec = importlib.util.spec_from_file_location(name, FD7)
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        sys.modules[name] = mod
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    finally:
        sys.path.remove(str(FD7_DIR))
        sys.dont_write_bytecode = before
    return mod


@pytest.mark.skipif(not FD7.is_file(), reason="FD7 reference script not on this machine")
def test_fd7_cases_against_the_live_reference() -> None:
    ref = _fd7()
    assert ref.bridge(29.0, 0.62)["span_ft"] == pytest.approx(S.bridge_run_ft, abs=0.005)
    assert ref.bridge(29.0, 0.62)["cantilever_ft"] == pytest.approx(S.bridge_corner_ft, abs=0.005)
    assert ref.BASEMENT_FLOOR_FT == S.basement_floor_ft and ref.DEEP_STEM_FT * 12 == pytest.approx(S.deep_stem_in)
    for c in ref.CASES:
        r = ref.remedies(c)
        e = infill.Exposure(c.wall_ft, c.floor_sf, c.corner, c.longest_gap_ft)
        remedy, b = infill.b_cost(e, S18, S18.embed_in)
        want = r["bridge with the wall"] if remedy == infill.BRIDGE else r["deepen the wall to the old floor"]
        assert (r["bridge with the wall"] is not None) == (remedy == infill.BRIDGE), c.name
        assert _money(b) == pytest.approx(want, abs=1e-6), c.name
        assert _money(infill.a_cost(e, S18)) == pytest.approx(r["SLAB: tested rock under the whole patch"], abs=1e-6), c.name


# ---------------------------------------------------------------- hand-drawn outlines, measured


def test_a_corner_clipped_by_2_ft() -> None:
    b = oldbuild.measure_one(_box(-10, -10, -1, -1), S)  # grown 3 ft: reaches 2 ft into the pod
    assert b is not None
    got = sorted((st.line, round(st.length_ft, 9), st.corner) for st in b.stretches)
    assert got == [("front", 2.0, True), ("left end", 2.0, True)]
    assert (b.wall_ft, b.floor_sf, b.corner, b.longest_ft) == pytest.approx((4.0, 4.0, True, 2.0))
    assert b.year_built == 1925 and b.area_sf == pytest.approx(81.0)
    e = infill.Exposure.of(b)
    remedy, cost = infill.b_cost(e, S18, 18.0)
    assert remedy == infill.BRIDGE and _money(cost) == pytest.approx(FD7_CASES[0][5], abs=1e-5)


def test_a_whole_long_side() -> None:
    b = oldbuild.measure_one(_box(-5, -10, 85, 5), S)  # grown to y = 8 across the whole front
    assert b is not None
    by = {st.line: st.length_ft for st in b.stretches}
    assert by == pytest.approx({"front": 80.0, "left end": 8.0, "right end": 8.0, "party 20": 8.0, "party 40": 8.0, "party 60": 8.0})
    assert (b.wall_ft, b.floor_sf, b.longest_ft) == pytest.approx((120.0, 640.0, 80.0))
    remedy, cost = infill.b_cost(infill.Exposure.of(b), S18, 18.0)
    assert remedy == infill.DEEPEN and _money(cost) == pytest.approx(FD7_CASES[5][6], abs=1e-5)
    assert _money(infill.a_cost(infill.Exposure.of(b), S18)) == pytest.approx(FD7_CASES[5][7], abs=1e-5)


def test_a_whole_end() -> None:
    b = oldbuild.measure_one(_box(-10, -10, 7, 35), S)
    assert b is not None
    assert (b.wall_ft, b.floor_sf, b.longest_ft) == pytest.approx((45.0, 250.0, 25.0))
    # FD7 labels this case "not a corner"; past either reach it is deepened, so the cost agrees.
    remedy, cost = infill.b_cost(infill.Exposure.of(b), S18, 18.0)
    assert remedy == infill.DEEPEN and _money(cost) == pytest.approx(FD7_CASES[4][6], abs=1e-5)


def test_no_overlap() -> None:
    assert oldbuild.measure_one(_box(-20, -20, -3.5, 40), S) is None  # grown edge stops 0.5 ft short
    assert oldbuild.measure_all([_box(100, 0, 120, 25), _box(-10, -10, -1, -1)], S)[0].wall_ft == pytest.approx(4.0)


def test_a_building_fully_under_the_pod() -> None:
    b = oldbuild.measure_one(_box(30, 5, 50, 20), S)  # grown [27, 53] x [2, 23]
    assert b is not None
    assert [(st.line, round(st.length_ft, 9), st.corner) for st in b.stretches] == [("party 40", 21.0, False)]
    assert b.floor_sf == pytest.approx(26 * 21) and b.area_sf == pytest.approx(300.0)
    remedy, cost = infill.b_cost(infill.Exposure.of(b), S18, 18.0)
    assert remedy == infill.DEEPEN and _money(cost) == pytest.approx((763.910372, 1256.870549), abs=1e-5)
    assert _money(infill.a_cost(infill.Exposure.of(b), S18)) == pytest.approx((11936.777778, 24793.666667), abs=1e-5)


def test_a_building_between_party_lines_touches_no_wall() -> None:
    b = oldbuild.measure_one(_box(25, 8, 33, 16), S)  # grown [22, 36] x [5, 19]
    assert b is not None and b.stretches == () and b.floor_sf == pytest.approx(14 * 14)
    e = infill.Exposure.of(b)
    remedy, cost = infill.b_cost(e, S18, 18.0)
    assert remedy == infill.NO_WALL and cost.low == 0 and infill.a_cost(e, S18).low > 0


# ---------------------------------------------------------------- the price layer: conditional, outside the total


def _with_old(m: measure.Measured, *boxes: oldbuild.Outline) -> measure.Measured:
    return measure.with_old_buildings(m, True, oldbuild.measure_all(boxes, S))


def test_the_conditional_cost_never_enters_the_main_total() -> None:
    bare = _flat_record(year_built=1925, frost_register_in=12.0)
    over = _with_old(bare, _box(-5, -10, 85, 5), _box(30, 5, 50, 20))
    a, b = lot.assess(bare, S), lot.assess(over, S)
    for name in ("B", "B+P", "A dry", "A wet"):
        assert a[name].cost.lines == b[name].cost.lines, name
        assert a[name].flags == b[name].flags
    assert b.infill.total("B", "low") > 0 and b.infill.total("A", "high") > 0
    assert not a.infill.any and a.infill.total("B", "high") == 0
    assert lot.WALL_CROSSES_OLD in b.flags and lot.WALL_CROSSES_OLD not in a.flags
    item = next(i for i in b.challenges if i.code == classify.WALL_OVER_OLD)
    assert item.value == pytest.approx(80.0) and "basement" in item.words
    assert classify.WALL_OVER_OLD not in {i.code for i in a.challenges}


def test_weighted_by_year_built() -> None:
    old = _box(-5, -10, 85, 5)
    for year, share in ((1925, 0.80), (1939, 0.80), (1940, 0.39), (1959, 0.39), (1960, 0.14), (2001, 0.14), (None, 0.28)):
        r = lot.assess(_with_old(_flat_record(year_built=year), old), S)
        assert r.infill.basement_share == share
        for method in ("B", "A"):
            for prices in ("low", "high"):
                assert r.infill.weighted(method, prices) == r.infill.total(method, prices) * Decimal(str(share))
    assert infill.year_band(1939, S) == "before 1940" and infill.year_band(1959, S) == "1940-1959"
    assert infill.year_band(1960, S) == "1960 on" and infill.year_band(None, S) == "not held"
    labels = [S.sources[f"old_buildings.{k}"] for k in ("share_before_1940", "share_1940_1959", "share_1960_on", "share_not_held")]
    assert all("American Housing Survey" in t for t in labels)


def test_several_buildings_add_up() -> None:
    m = _with_old(_flat_record(), _box(-10, -10, -1, -1), _box(30, 5, 50, 20))
    r = lot.assess(m, S18.replace(basement_min_sf=0.0))  # FD7's key counts the 81 sq ft outline
    assert [bc.b_remedy for bc in r.infill.buildings] == [infill.BRIDGE, infill.DEEPEN]
    assert float(r.infill.total("B", "low")) == pytest.approx(103.044729 + 763.910372, abs=1e-5)
    assert r.infill.longest_ft == pytest.approx(21.0)


# ---------------------------------------------------------------- each lot's own footing depth


def test_the_frost_register_sets_the_footing_depth() -> None:
    shallow = _flat_record(frost_register_in=12.0)
    deep = _flat_record(frost_register_in=18.0)
    none = _flat_record()
    assert model.embed_of(shallow, S) == 12.0 and model.embed_of(deep, S) == 18.0 and model.embed_of(none, S) == S.embed_in
    assert model.embed_of(shallow, S18) == S18.embed_in, "switched off, every lot takes embed_in"
    r12, r18 = lot.assess(shallow, S), lot.assess(deep, S)
    assert r12.embed_in_used == 12.0 and r18.embed_in_used == 18.0
    assert r18["B"].tallest_wall_in - r12["B"].tallest_wall_in == pytest.approx(6.0)
    assert r12["B"].cost.low < r18["B"].cost.low and r12["A dry"].cost.low < r18["A dry"].cost.low
    assert lot.assess(deep, S)["B"].cost.lines == lot.assess(deep, S18)["B"].cost.lines
    # A's edge follows the footing: 12 + 8 in.
    assert model.lot_settings(shallow, S).edge_d_in == pytest.approx(20.0)
    # Doors and floor levels do not depend on the footing.
    assert [d.risers for d in r12["B"].doors] == [d.risers for d in r18["B"].doors]


# ---------------------------------------------------------------- storage


def test_old_building_rows_round_trip() -> None:
    m = _with_old(_flat_record(year_built=1951, frost_register_in=12.0), _box(-10, -10, -1, -1), _box(30, 5, 50, 20))
    lot_row, lines, doors = rows.measured_rows(m)
    bldgs, stretches = rows.old_building_rows(m)
    assert lot_row["year_built"] == 1951 and lot_row["old_buildings_n"] == 2 and lot_row["old_buildings_held"] is True
    assert len(bldgs) == 2 and len(stretches) == 3 and all(r["tlid"] == "1S1E  -1" for r in bldgs + stretches)
    back = rows.from_measured_rows(lot_row, lines, doors, bldgs, stretches)
    assert back == m
    one, _, _ = rows.assessed_rows(lot.assess(back, S))
    assert one["old_year_band"] == "1940-1959" and one["old_basement_share"] == 0.39
    assert Decimal(one["old_weighted_b_low"]) == Decimal(one["old_if_basement_b_low"]) * Decimal("0.39")
    assert one["embed_in_used"] == 12.0


def test_grow_is_geometric() -> None:
    m = _flat_record()
    with pytest.raises(ValueError, match="grow_ft"):
        lot.assess(m, S.replace(grow_ft=2.0))


# ---------------------------------------------------------------- the ground grid and the frame


def test_the_grid_covers_the_footprint_and_its_margin() -> None:
    x0, y0, xs, ys = grounds.grid_centres(S)
    assert (x0, y0) == (-S.grid_margin_ft, -S.grid_margin_ft)
    assert len(xs) == 100 and len(ys) == 45 and xs[0] == -9.5 and xs[-1] == 89.5 and ys[-1] == 34.5


def test_a_grid_of_a_plane_measures_as_the_plane() -> None:
    plane = grounds.plane(S, 3.0, 1.5, 100.0)
    _, _, xs, ys = grounds.grid_centres(S)
    g = grounds.cell_grid([[plane(x, y) for x in xs] for y in ys], S, 1.0, "dem_1m grid")
    assert g.lump_ft == 0.0 and g.source == "dem_1m grid" and g.cell_m == 1.0
    a, b = measure.measure(plane, S), measure.measure(g, S)
    for la, lb in zip(a.lines, b.lines, strict=True):
        assert lb.drops_in == pytest.approx(la.drops_in, abs=1e-9)
    assert b.fill_volume_ft3 == pytest.approx(a.fill_volume_ft3, abs=1e-6)
    assert b.ground_source == "dem_1m grid"


def test_a_blank_cell_is_refused() -> None:
    _, _, xs, ys = grounds.grid_centres(S)
    z = [[0.0] * len(xs) for _ in ys]
    z[3][7] = math.nan
    with pytest.raises(ValueError, match="blank"):
        grounds.cell_grid(z, S, 1.0, "dem_1m grid")


def test_the_frame_maps_model_to_world_and_back() -> None:
    # An 80 x 25 rectangle turned 30 degrees; the street runs along its lower long side.
    c, s_ = math.cos(math.radians(30)), math.sin(math.radians(30))

    def rot(x: float, y: float) -> tuple[float, float]:
        return (1000 + x * c - y * s_, 2000 + x * s_ + y * c)

    ring = [rot(0, 0), rot(80, 0), rot(80, 25), rot(0, 25), rot(0, 0)]
    street = (*rot(-50, -20), *rot(130, -20))
    fr = frame(ring, [street])
    assert fr.front_known and fr.long_ft == pytest.approx(80.0) and fr.short_ft == pytest.approx(25.0)
    # Seen from the street (looking "up" into the lot), left is the low-x end.
    assert fr.fl == pytest.approx(rot(0, 0)) and fr.fr == pytest.approx(rot(80, 0)) and fr.bl == pytest.approx(rot(0, 25))
    pts = [(0.0, 0.0), (80.0, 25.0), (12.5, 7.0), (-10.0, 35.0)]
    world = fr.world([p[0] for p in pts], [p[1] for p in pts], S.length_ft, S.width_ft)
    assert tuple(world[2]) == pytest.approx(rot(12.5, 7.0))
    back = fr.model(world, S.length_ft, S.width_ft)
    assert back.ravel().tolist() == pytest.approx([v for p in pts for v in p], abs=1e-9)
    assert [name for name, _, _ in SIX_UV] == ["z_front_left", "z_front_right", "z_back_left", "z_back_right", "z_front_mid", "z_back_mid"]


def test_world_footprints_become_model_outlines() -> None:
    import shapely

    ring = [(0, 0), (80, 0), (80, 25), (0, 25), (0, 0)]
    fr = frame(ring, [(-10, -5, 90, -5)])
    outs = oldbuild.model_outlines(fr, [shapely.box(-10, -10, -1, -1)], [{"BLDG_ID": 7, "YEAR_BUILT": 0}], S)
    assert outs[0].bldg_id == "7" and outs[0].year_built is None
    b = oldbuild.measure_one(outs[0], S)
    assert b is not None and b.wall_ft == pytest.approx(4.0)


def test_outlines_under_400_sq_ft_are_left_out_of_the_basement_case() -> None:
    """FD8 2c: a shed or a detached garage has no basement."""
    small, big = _box(-10, -10, -1, -1), _box(30, 5, 55, 25)  # 81 and 500 sq ft
    m = _with_old(_flat_record(), small, big)
    assert S.basement_min_sf == 400 and len(m.old_buildings) == 2
    r = lot.assess(m, S18)
    assert len(r.infill.buildings) == 1 and r.infill.buildings[0].exposure.floor_sf > 0
    assert "400 sq ft" in " ".join(infill.SIMPLIFICATIONS)
