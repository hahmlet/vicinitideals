"""The foundation model (FOLLOWUPS 209; FD6 build steps 1-7).

The answer key is FD6 section 8 (Factory-Sim docs/research/FD6-foundation-model-spec.md):
both test-lot tables, every column and row, to the last figure shown and costs to the
dollar; the eight checks that must hold on any ground; and the build-step checks
(wall lines total 285 ft; every setting loads with a label). None of it needs the
lot file or the Factory-Sim folder (``test_foundation_lot_file.py`` does, and skips
without them).
"""

from __future__ import annotations

import ast
import random
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from flats import foundation
from flats.foundation import cost as costing
from flats.foundation import ground as grounds
from flats.foundation import classify, lot, measure, model, rows, settings, support
from flats.foundation.__main__ import TEST_LOTS, ft_in, main, row_of

S = settings.load()
PKG = Path(foundation.__file__).parent


def _plane(along: float, across: float, base: float = 0.0) -> grounds.Plane:
    return grounds.plane(S, along, across, base)


TEST = {name: (along, across) for name, along, across in TEST_LOTS}

# ---------------------------------------------------------------- FD6 section 8 tables

#: B: tallest wall, concrete showing, concrete cu yd, bars lb, form face sq ft, highest
#: door, risers least-most, risers 8 doors, longest stair ft, guards, cost $
B_TABLE = {
    "flat": ("2 ft 5 in", "1 ft 6 in", "28.1", "642", "1,710", "2 ft 9 in", "5-5", 40, "5.5", 0, "20,449-37,449"),
    "1 ft along": ("3 ft 5 in", "2 ft 6 in", "32.1", "670", "1,995", "3 ft 7 in", "5-6", 44, "6.3", 4, "22,106-42,776"),
    "2 ft along": ("4 ft 5 in", "3 ft 6 in", "36.1", "835", "2,280", "4 ft 6 in", "5-7", 50, "7.2", 6, "23,780-47,395"),
    "2 ft across": ("4 ft 5 in", "3 ft 6 in", "36.1", "849", "2,280", "4 ft 9 in", "5-8", 52, "8.0", 4, "23,706-46,514"),
    "3 ft along, 1 ft across": ("6 ft 5 in", "5 ft 6 in", "44.2", "947", "2,850", "6 ft 4 in", "5-10", 62, "9.7", 7, "26,582-54,157"),
    "4 ft along": ("6 ft 5 in", "5 ft 6 in", "44.2", "928", "2,850", "6 ft 3 in", "5-10", 62, "9.7", 8, "26,695-54,853"),
    "6 ft along": ("8 ft 5 in", "7 ft 6 in", "59.3", "1,121", "3,420", "8 ft 0 in", "6-13", 74, "12.2", 8, "30,569-62,573"),
}

#: A: edge (footing bottom to slab top), concrete cu yd, bars lb, form face sq ft, rock
#: fill tons, highest door, risers least-most, risers 8 doors, longest stair ft, guards,
#: cost $ (dry)
A_TABLE = {
    "flat": ("2 ft 2 in", "48.1", "409", "910", "0", "0 ft 8 in", "1-1", 8, "3.0", 0, "17,011-28,732"),
    "1 ft along": ("3 ft 2 in", "50.9", "409", "1,120", "70", "1 ft 6 in", "2-3", 18, "3.8", 0, "20,622-34,828"),
    "2 ft along": ("4 ft 2 in", "53.7", "545", "1,330", "141", "2 ft 5 in", "2-4", 24, "4.7", 0, "24,238-41,390"),
    "2 ft across": ("4 ft 2 in", "53.7", "504", "1,330", "141", "2 ft 8 in", "1-5", 24, "5.5", 0, "24,397-42,409"),
    "3 ft along, 1 ft across": ("6 ft 2 in", "59.2", "751", "1,750", "281", "4 ft 4 in", "2-7", 37, "7.2", 3, "32,010-57,568"),
    "4 ft along": ("6 ft 2 in", "59.2", "753", "1,750", "281", "4 ft 2 in", "2-7", 36, "7.2", 2, "31,825-56,719"),
    "6 ft along": ("8 ft 2 in", "64.8", "930", "2,170", "422", "5 ft 11 in", "3-10", 50, "9.7", 4, "39,353-71,384"),
}


def _cost(r: model.MethodResult) -> str:
    return f"{costing.dollars(r.cost.low):,}-{costing.dollars(r.cost.high):,}"


@pytest.mark.parametrize("name", list(B_TABLE))
def test_b_table_every_column(name: str) -> None:
    r = model.raised(_plane(*TEST[name]), S)
    got = (
        ft_in(r.tallest_wall_in),
        ft_in(r.showing_max_in),
        f"{r.concrete_yd3:.1f}",
        f"{r.bars_lb:,.0f}",
        f"{r.form_sf:,.0f}",
        ft_in(r.highest_door_in),
        f"{r.risers_least}-{r.risers_most}",
        r.risers_total,
        f"{r.longest_stair_in / 12:.1f}",
        r.guards,
        _cost(r),
    )
    assert got == B_TABLE[name]


@pytest.mark.parametrize("name", list(B_TABLE))
def test_b_flags_as_stated(name: str) -> None:
    r = model.raised(_plane(*TEST[name]), S)
    assert (model.WALL_OVER in r.flags) == (name == "6 ft along")
    assert (model.GUARD in r.flags) == (r.guards > 0)


@pytest.mark.parametrize("name", list(A_TABLE))
def test_a_table_every_column(name: str) -> None:
    r = model.slab(_plane(*TEST[name]), S)
    got = (
        ft_in(r.tallest_wall_in),
        f"{r.concrete_yd3:.1f}",
        f"{r.bars_lb:,.0f}",
        f"{r.form_sf:,.0f}",
        f"{r.fill_ton:.0f}",
        ft_in(r.highest_door_in),
        f"{r.risers_least}-{r.risers_most}",
        r.risers_total,
        f"{r.longest_stair_in / 12:.1f}",
        r.guards,
        _cost(r),
    )
    assert got == A_TABLE[name]


@pytest.mark.parametrize("name", list(A_TABLE))
def test_a_flags_as_stated(name: str) -> None:
    """Every lot from 2 ft of fall carries "fill over 24 in"; the 6 ft lot also
    "edge holds back over 4 ft"."""
    r = model.slab(_plane(*TEST[name]), S)
    assert (model.FILL_OVER in r.flags) == (name not in ("flat", "1 ft along"))
    assert (model.EDGE_OVER in r.flags) == (name == "6 ft along")
    assert (model.GUARD in r.flags) == (r.guards > 0)


def test_the_script_prints_the_section_8_tables(capsys: pytest.CaptureFixture[str]) -> None:
    main(["--test-lots"])
    out = capsys.readouterr().out
    assert "| 6 ft along | 8 ft 5 in | 7 ft 6 in | 59.3 | 1,121 | 3,420 | 0 | 8 ft 0 in | 6-13 | 74 | 12.2 | 8 | 30,569-62,573 |" in out
    assert "| flat | 2 ft 2 in | 0 ft 8 in | 48.1 | 409 | 910 | 0 | 0 ft 8 in | 1-1 | 8 | 3.0 | 0 | 17,011-28,732 | - |" in out


def test_wet_season_changes_only_the_flat_rock_and_haul_lines() -> None:
    for along, across in TEST.values():
        g = _plane(along, across)
        dry, wet = model.slab(g, S), model.slab(g, S, wet=True)
        for d, w in zip(dry.cost.lines, wet.cost.lines, strict=True):
            assert d.name == w.name
            if d.name in ("rock under the slab", "haul"):
                assert w.low > d.low and w.high > d.high
            else:
                assert (d.low, d.high) == (w.low, w.high)
        assert (dry.concrete_yd3, dry.fill_ton, dry.risers_total) == (wet.concrete_yd3, wet.fill_ton, wet.risers_total)


# ---------------------------------------------------------------- section 6 fixed lines

#: FD6 section 6 "lines that do not follow the ground" (one pod, FD3), whole dollars.
FIXED = {
    ("A dry", "concrete, flat lot"): (7698, 10585),
    ("A dry", "pump"): (900, 1750),
    ("A dry", "bars, flat lot"): (311, 580),
    ("A dry", "rock under the slab"): (3934, 6182),
    ("A wet", "rock under the slab"): (7527, 11829),
    ("A dry", "haul"): (914, 3962),
    ("A wet", "haul"): (1725, 7474),
    # FD6 section 6 prints $119-516: FD3's 285.625 ft run (80 ft 3-3/4 in pod); the
    # reference model runs 285 ft and gives $515. The reference's number wins.
    ("B", "haul"): (119, 515),
    ("A dry", "ground sheet"): (508, 729),
    ("B", "ground sheet"): (139, 531),
    ("A dry", "edge insulation"): (1011, 1180),
    ("A dry", "radon pipes"): (400, 800),
    ("A dry", "fill testing"): (400, 800),
    ("B", "crawlspace vents"): (390, 1050),
    ("B", "12 floor cassettes"): (10000, 15000),
    ("B", "pump"): (900, 1750),
}


@pytest.mark.parametrize("method, line", list(FIXED))
def test_section_6_fixed_lines(method: str, line: str) -> None:
    g = _plane(0, 0)
    r = {"A dry": model.slab(g, S), "A wet": model.slab(g, S, wet=True), "B": model.raised(g, S)}[method]
    ln = r.cost.line(line)
    assert (costing.dollars(ln.low), costing.dollars(ln.high)) == FIXED[(method, line)]


def test_flat_lot_concrete_is_48_1_cu_yd() -> None:
    assert f"{costing.flat_lot(S).slab_concrete_yd3:.1f}" == "48.1"


# ---------------------------------------------------------------- step 1: settings and frame


def test_wall_lines_total_285_ft_and_there_are_seven() -> None:
    lines = model.wall_lines(S)
    assert len(lines) == 7
    assert sum(ln.length_ft for ln in lines) == pytest.approx(285.0)
    assert [ln.kind for ln in lines].count("party") == 3


def test_eight_doors_front_and_back_of_each_home() -> None:
    r = model.raised(_plane(0, 0), S)
    assert [(d.face, d.x_ft) for d in r.doors] == [(f, x) for f in ("front", "back") for x in (10, 30, 50, 70)]


def test_every_setting_and_price_loads_with_a_label() -> None:
    names = [n for names in settings.SECTIONS.values() for n in names]
    assert len(names) == len(set(names)), "a setting name is used twice"
    for section, sec_names in settings.SECTIONS.items():
        for name in sec_names:
            assert S.sources[f"{section}.{name}"].strip(), f"{section}.{name} has no label"
            assert getattr(S, name) is not None
    for key in settings.PRICES:
        p = S.price(key)
        assert p.source.strip() and p.unit.strip()
        assert p.low <= p.high
    assert len(S.sources) == len(names) + len(settings.PRICES)


def test_recalled_code_rules_stay_labelled_recalled() -> None:
    assert S.sources["doors.guard_over_in"].startswith("[code, recalled, R312]")
    assert S.sources["doors.handrail_risers"].startswith("[code, recalled, R311.7.8]")


def test_section_4_values_as_the_spec_gives_them() -> None:
    assert (S.length_ft, S.width_ft, S.party_x_ft, S.door_x_ft) == (80, 25, (20, 40, 60), (10, 30, 50, 70))
    assert (S.clear_in, S.floor_depth_in, S.embed_in, S.footing_t_in) == (18, 14.75, 18, 7)
    assert (S.footing_w_long_in, S.footing_w_end_in, S.footing_w_party_in) == (18, 12, 14)
    assert (S.stem_outside_in, S.stem_party_in, S.plain_wall_max_in, S.engineered_stem_in) == (8, 10, 96, 10)
    assert (S.vert_bar_spacing_ft, S.vert_bars_extra_per_line, S.level_bars_base) == (4, 2, 2)
    assert (S.level_bar_third_over_in, S.level_bar_fourth_over_in, S.footing_max_slope) == (48, 96, 0.1)
    assert (S.bar_lb_per_ft, S.lap, S.concrete_waste, S.rock_ton_per_yd3) == (0.668, 1.10, 1.07, 1.9)
    assert (S.slab_top_in, S.edge_w_in, S.edge_d_in, S.fill_limit_in, S.unbalanced_limit_in) == (8, 15, 26, 24, 48)
    assert (S.landing_drop_in, S.riser_in, S.tread_in, S.landing_depth_in) == (8, 7.75, 10, 36)
    assert (S.guard_over_in, S.handrail_risers, S.station_ft) == (30, 4, 1)
    p = S.prices
    assert (p["concrete_yd3"].low, p["concrete_yd3"].high) == (Decimal("160"), Decimal("220"))
    assert (p["bar_lb"].low, p["bar_lb"].high) == (Decimal("0.76"), Decimal("1.42"))
    assert (p["form_sf"].low, p["form_sf"].high) == (Decimal("0.5"), Decimal("1.5"))
    assert (p["rock_ton"].low, p["rock_ton"].high) == (Decimal("35"), Decimal("55"))
    assert (p["riser"].low, p["riser"].high) == (Decimal("60"), Decimal("130"))
    assert (p["step_pad"].low, p["step_pad"].high) == (Decimal("60"), Decimal("100"))
    assert (p["rail_ft"].low, p["rail_ft"].high) == (Decimal("15"), Decimal("85"))
    assert (p["pile"].low, p["pile"].high) == (Decimal("550"), Decimal("950"))


def _doc() -> dict:
    return yaml.safe_load(settings.PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "spoil, message",
    [
        (lambda d: d["doors"]["riser_in"].pop("source"), "no source label"),
        (lambda d: d["doors"]["riser_in"].update(source="  "), "no source label"),
        (lambda d: d["doors"].pop("riser_in"), "missing"),
        (lambda d: d["doors"].update(stray={"value": 1, "source": "x"}), "unknown settings"),
        (lambda d: d["prices"]["pile"].pop("source"), "needs source"),
        (lambda d: d["prices"]["pile"].update(low=2000), "above high"),
        (lambda d: d["prices"].pop("rail_ft"), "missing"),
        (lambda d: d["raised"]["clear_in"].update(value="18 in"), "must be a number"),
        (lambda d: d["building"]["door_x_ft"].update(value=[]), "non-empty list"),
        (lambda d: d.update(extra_section={}), "unknown sections"),
    ],
)
def test_the_loader_refuses_a_half_labelled_file(spoil, message: str) -> None:
    doc = _doc()
    spoil(doc)
    with pytest.raises(ValueError, match=message):
        settings.parse(doc)


def test_no_section_4_or_6_number_is_written_in_the_python() -> None:
    """Every float literal in the model other than the frame's unit constants
    (12 in a ft, 27 cu ft a cu yd, 144 sq in a sq ft, 0.5 for a mid-point) is a
    smell: the settings belong in the YAML. (``__main__`` holds only the
    reference model's report bins and quantiles; ``terrain`` is FD2 pass 1's
    elevation reader, copied as it ran -- metres to feet and its 120 ft window;
    ``inputs`` is FD2 pass 1's ground-class rules, copied as they ran -- the
    FD2 hand-off's cut-offs, not section 4 or 6 settings; ``record``'s
    ``SAME_RING_FT`` is how far a stored drawing may sit from the page's and
    still be the same drawing, not a model number.)"""
    allowed = {0.0, 0.5, 1.0, 2.0, 12.0, 27.0, 144.0}
    also = {"record.py": {0.15}}
    for path in PKG.glob("*.py"):
        if path.name in ("__main__.py", "terrain.py", "inputs.py"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, float):
                ok = allowed | also.get(path.name, set())
                assert node.value in ok, f"{path.name}:{node.lineno} hard-codes {node.value}"


def test_the_package_imports_nothing_from_app_or_the_screen() -> None:
    for path in PKG.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module]
            for m in mods:
                assert not m.startswith("app"), f"{path.name} imports {m}"
                assert not m.startswith(("flats.score", "flats.ingest", "flats.fit")), f"{path.name} imports {m}"


# ---------------------------------------------------------------- the ground


def test_six_readings_lump_allowance() -> None:
    g = grounds.six_readings(S, 10.0, 9.5, 9.0, 9.8, 9.2, 8.6, relief_ft=2.0)
    assert g.lump_ft == pytest.approx((2.0 - 1.4) / 2)
    flat = grounds.six_readings(S, 1, 1, 1, 1, 1, 1, relief_ft=0.2)
    assert flat.lump_ft == pytest.approx(0.1)
    none = grounds.six_readings(S, 3, 2, 1, 3, 2, 1, relief_ft=1.0)
    assert none.lump_ft == 0.0, "never less than zero"


def test_six_readings_on_a_plane_are_the_plane() -> None:
    for along, across in TEST.values():
        p = _plane(along, across)
        z = [p(x, y) for y in (0.0, 25.0) for x in (0.0, 40.0, 80.0)]
        six = grounds.six_readings(S, *z)
        for x, y in ((0, 0), (13.3, 7.1), (40, 12.5), (66.6, 25), (80, 25)):
            assert six(x, y) == pytest.approx(p(x, y), abs=1e-12)
        assert model.raised(six, S).cost.low == pytest.approx(model.raised(p, S).cost.low, abs=Decimal("1e-6"))


def test_the_lump_allowance_raises_the_floor_and_every_door() -> None:
    flat = grounds.six_readings(S, 0, 0, 0, 0, 0, 0, relief_ft=1.0)
    assert measure.measure(flat, S).lump_ft == 0.5
    b = model.raised(flat, S)
    assert b.floor_above_high_in == pytest.approx(32.75)
    assert all(d.height_in == pytest.approx(32.75 + 6) for d in b.doors)
    a = model.slab(flat, S)
    assert a.fill_max_in == pytest.approx(6.0)


def _grid_of(g: grounds.Ground, cell_ft: float = 2.5, margin_ft: float = 10.0, cell_m: float | None = 1.0) -> grounds.CellGrid:
    nx = round((S.length_ft + 2 * margin_ft) / cell_ft)
    ny = round((S.width_ft + 2 * margin_ft) / cell_ft)
    z = [[g(-margin_ft + (i + 0.5) * cell_ft, -margin_ft + (j + 0.5) * cell_ft) for i in range(nx)] for j in range(ny)]
    return grounds.CellGrid.of(z, -margin_ft, -margin_ft, cell_ft, cell_m)


@pytest.mark.parametrize("name", list(TEST))
def test_a_cell_grid_of_a_plane_gives_the_plane_results(name: str) -> None:
    p = _plane(*TEST[name])
    grid = _grid_of(p)
    assert grid.lump_ft == 0.0 and grid.source == "cell grid"
    for x, y in ((0, 0), (12.34, 5.6), (80, 25), (41.0, 24.9)):
        assert grid(x, y) == pytest.approx(p(x, y), abs=1e-9)
    for fn in (model.raised, model.slab):
        a, b = fn(grid, S), fn(p, S)
        assert a.tallest_wall_in == pytest.approx(b.tallest_wall_in, abs=1e-9)
        assert a.concrete_yd3 == pytest.approx(b.concrete_yd3, abs=1e-9)
        assert [d.risers for d in a.doors] == [d.risers for d in b.doors]
        assert costing.dollars(a.cost.low) == costing.dollars(b.cost.low)
        assert costing.dollars(a.cost.high) == costing.dollars(b.cost.high)


def test_cell_grid_blends_bilinearly_and_holds_its_edges() -> None:
    grid = grounds.CellGrid.of([[0.0, 1.0], [2.0, 4.0]], x0_ft=0.0, y0_ft=0.0, cell_ft=10.0)
    # cell centres at (5, 5), (15, 5), (5, 15), (15, 15)
    assert grid(5, 5) == 0.0 and grid(15, 15) == 4.0
    assert grid(10, 5) == pytest.approx(0.5)
    assert grid(10, 10) == pytest.approx((0 + 1 + 2 + 4) / 4)
    assert grid(-100, -100) == 0.0 and grid(100, 100) == 4.0
    assert grid(10, -50) == pytest.approx(0.5)
    with pytest.raises(ValueError):
        grounds.CellGrid.of([[1.0, 2.0], [3.0]], 0, 0, 1)


def test_a_grid_sees_a_lump_the_six_readings_miss() -> None:
    """The six readings miss a hump in the middle of the back half; the grid does not,
    and the walls round it are taller (FD6 section 8: a grid gives taller walls on some lots)."""

    class Hump(grounds.Ground):
        def __call__(self, x: float, y: float) -> float:
            return max(0.0, 2.0 - ((x - 60) ** 2 + (y - 20) ** 2) ** 0.5 / 4)

    grid = _grid_of(Hump(), cell_ft=1.0)
    six = grounds.six_readings(S, *[Hump()(x, y) for y in (0.0, 25.0) for x in (0.0, 40.0, 80.0)])
    assert model.raised(grid, S).tallest_wall_in > model.raised(six, S).tallest_wall_in + 12


def test_cell_size_is_carried_and_a_coarse_model_is_flagged() -> None:
    fine = lot.run_lot(_grid_of(_plane(1, 0), cell_m=1.0), S)
    coarse = lot.run_lot(_grid_of(_plane(1, 0), cell_m=10.0), S)
    assert fine.cell_m == 1.0 and lot.COARSE not in fine.flags
    assert coarse.cell_m == 10.0 and lot.COARSE in coarse.flags
    assert coarse.ground_source == "cell grid"


# ---------------------------------------------------------------- the eight checks (section 8)


def _random_six(seed: int) -> list[tuple[float, ...]]:
    rnd = random.Random(seed)
    out = []
    for _ in range(12):
        base = rnd.uniform(-50, 500)
        out.append(tuple(base + rnd.uniform(-3, 3) for _ in range(6)) + (rnd.choice([0.0, rnd.uniform(0, 8)]),))
    return out


SIX = _random_six(209)


def _six(vals: tuple[float, ...]) -> grounds.SixReadings:
    *z, relief = vals
    return grounds.six_readings(S, *z, relief_ft=relief if relief else None)


def _totals(r: model.MethodResult) -> tuple:
    return (
        r.tallest_wall_in,
        r.showing_max_in,
        r.average_wall_in,
        r.concrete_yd3,
        r.bars_lb,
        r.form_sf,
        r.fill_ton,
        r.fill_max_in,
        r.floor_above_high_in,
        r.floor_above_low_in,
        r.rail_ft,
        float(r.cost.low),
        float(r.cost.high),
    )


def _counts(r: model.MethodResult) -> tuple:
    return (r.risers_total, r.guards, r.flags)


METHODS = (
    ("B", lambda g: model.raised(g, S)),
    ("B+P", lambda g: model.raised(g, S, piles=True)),
    ("A dry", lambda g: model.slab(g, S)),
    ("A wet", lambda g: model.slab(g, S, wet=True)),
)


@pytest.mark.parametrize("method, fn", METHODS)
@pytest.mark.parametrize("constant", [123.456, -987.6, 0.1])
def test_check_1_adding_a_constant_changes_no_output(method: str, fn, constant: float) -> None:
    for along, across in TEST.values():
        a, b = fn(_plane(along, across)), fn(_plane(along, across, base=constant))
        assert _totals(a) == pytest.approx(_totals(b), abs=1e-6)
        assert _counts(a) == _counts(b)
        assert [(d.risers, d.guard, d.handrail) for d in a.doors] == [(d.risers, d.guard, d.handrail) for d in b.doors]
    for vals in SIX:
        *z, relief = vals
        g1 = grounds.six_readings(S, *z, relief_ft=relief or None)
        g2 = grounds.six_readings(S, *[v + constant for v in z], relief_ft=relief or None)
        a, b = fn(g1), fn(g2)
        assert _totals(a) == pytest.approx(_totals(b), abs=1e-6)
        assert _counts(a) == _counts(b)


def _mirror(vals: tuple[float, ...]) -> tuple[float, ...]:
    fl, fm, fr, bl, bm, br, relief = vals
    return (fr, fm, fl, br, bm, bl, relief)


def _swap(vals: tuple[float, ...]) -> tuple[float, ...]:
    fl, fm, fr, bl, bm, br, relief = vals
    return (bl, bm, br, fl, fm, fr, relief)


def _door_key(d: model.DoorResult) -> tuple:
    return (d.risers, d.guard, d.handrail, round(d.height_in, 9), d.stair_run_in, round(d.rail_ft, 9))


@pytest.mark.parametrize("method, fn", METHODS)
def test_check_2_end_for_end_and_front_for_back(method: str, fn) -> None:
    planes = [(_plane(al, ac), _plane(-al, ac, base=-al), _plane(al, -ac, base=-ac)) for al, ac in TEST.values()]
    cases = planes + [(_six(v), _six(_mirror(v)), _six(_swap(v))) for v in SIX]
    for g, mirrored, swapped in cases:
        r, m, sw = fn(g), fn(mirrored), fn(swapped)
        assert _totals(r) == pytest.approx(_totals(m), rel=1e-9, abs=1e-9)
        assert _totals(r) == pytest.approx(_totals(sw), rel=1e-9, abs=1e-9)
        assert _counts(r) == _counts(m) == _counts(sw)
        front, back = [_door_key(d) for d in r.doors[:4]], [_door_key(d) for d in r.doors[4:]]
        assert [_door_key(d) for d in m.doors[:4]] == front[::-1]
        assert [_door_key(d) for d in m.doors[4:]] == back[::-1]
        assert [_door_key(d) for d in sw.doors[:4]] == back
        assert [_door_key(d) for d in sw.doors[4:]] == front


@pytest.mark.parametrize("method, fn", METHODS)
def test_check_3_more_fall_is_never_less(method: str, fn) -> None:
    def key(r: model.MethodResult) -> tuple:
        return (r.tallest_wall_in, r.concrete_yd3, r.risers_total, float(r.cost.low), float(r.cost.high))

    for across in (0.0, 0.5, 1.0, 2.0):
        prev = None
        for step in range(0, 33):
            r = key(fn(_plane(step * 0.25, across)))
            if prev is not None:
                assert all(b >= a - 1e-9 for a, b in zip(prev, r)), (across, step * 0.25, prev, r)
            prev = r
    for along in (0.0, 1.0, 3.0):
        prev = None
        for step in range(0, 25):
            r = key(fn(_plane(along, step * 0.25)))
            if prev is not None:
                assert all(b >= a - 1e-9 for a, b in zip(prev, r)), (along, step * 0.25, prev, r)
            prev = r


def test_check_4_flat_lot_29_in_everywhere_and_the_same_risers_at_every_door() -> None:
    b = model.raised(_plane(0, 0), S)
    assert all(w == pytest.approx(29.0) for line in b.lines for w in line.walls_in)
    assert len({d.risers for d in b.doors}) == 1
    a = model.slab(_plane(0, 0), S)
    assert len({d.risers for d in a.doors}) == 1


def test_check_5_tallest_minus_showing_is_11_in_on_every_outside_line() -> None:
    grounds_ = [_plane(*v) for v in TEST.values()] + [_six(v) for v in SIX]
    for g in grounds_:
        for line in model.raised(g, S).lines:
            if line.kind != "party":
                assert line.tallest_in - line.showing_max_in == pytest.approx(11.0)


def test_check_6_floor_above_the_high_point_and_no_door_lower() -> None:
    grounds_ = [_plane(*v) for v in TEST.values()] + [_six(v) for v in SIX]
    for g in grounds_:
        b, a = model.raised(g, S), model.slab(g, S)
        assert b.floor_above_high_in == pytest.approx(32.75)
        assert a.floor_above_high_in == pytest.approx(8.0)
        assert a.floor_above_low_in >= a.floor_above_high_in and b.floor_above_low_in >= b.floor_above_high_in
        assert min(d.height_in for d in b.doors) >= 32.75 - 1e-9
        assert min(d.height_in for d in a.doors) >= 8.0 - 1e-9


def test_check_7_halving_the_station_spacing_moves_no_quantity_by_more_than_half_a_percent() -> None:
    fine = S.replace(station_ft=S.station_ft / 2, fill_cell_ft=S.fill_cell_ft / 2)
    fixed = [(10.0, 9.4, 9.9, 9.0, 8.7, 9.6, 1.5), (100.0, 101.2, 100.4, 99.8, 100.9, 100.1, 0.0)]
    grounds_ = [_plane(*v) for v in TEST.values()] + [_six(v) for v in fixed]
    for g in grounds_:
        for fn in (model.raised, model.slab):
            a, b = fn(g, S), fn(g, fine)
            for qa, qb in ((a.concrete_yd3, b.concrete_yd3), (a.bars_lb, b.bars_lb), (a.form_sf, b.form_sf), (a.fill_ton, b.fill_ton)):
                if qa:
                    assert abs(qb - qa) / qa <= 0.005, (fn.__name__, qa, qb)
                else:
                    assert qb == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize("method, fn", METHODS)
def test_check_8_low_never_above_high_and_the_total_is_the_sum_of_its_lines(method: str, fn) -> None:
    grounds_ = [_plane(*v) for v in TEST.values()] + [_six(v) for v in SIX]
    for g in grounds_:
        c = fn(g).cost
        assert all(ln.low <= ln.high for ln in c.lines)
        assert c.low <= c.high
        assert c.low == sum((ln.low for ln in c.lines), Decimal(0))
        assert c.high == sum((ln.high for ln in c.lines), Decimal(0))
        assert all(isinstance(ln.low, Decimal) and isinstance(ln.high, Decimal) for ln in c.lines)


# ---------------------------------------------------------------- doors (5.5)


@pytest.mark.parametrize(
    "height_in, risers, run_in",
    [(8.0, 1, 36), (8.1, 2, 36), (15.75, 2, 36), (15.76, 3, 46), (32.75, 5, 66), (38.0, 5, 66), (96.0, 13, 146)],
)
def test_risers_and_stair_run(height_in: float, risers: int, run_in: float) -> None:
    assert model.risers_at(height_in, S) == risers
    assert S.landing_depth_in + max(0, risers - 2) * S.tread_in == run_in


def test_guard_and_rail_rules() -> None:
    # 1 ft along: B doors from 32.75 in (left) to ~43 in (right): guard over 38 in
    b = model.raised(_plane(1, 0), S)
    for d in b.doors:
        assert d.guard == (d.height_in - 8 > 30)
        assert d.handrail == (d.risers >= 4)
        if d.guard:
            assert d.rail_ft == pytest.approx((2 * d.stair_run_in + 36) / 12)
        elif d.handrail:
            assert d.rail_ft == pytest.approx(d.stair_run_in / 12)
        else:
            assert d.rail_ft == 0
    # exactly 30 in up is not "over 30 in": no guard at the tie
    exact = grounds.six_readings(S, 0, 0, 0, 0, 0, 0, relief_ft=(38.0 - 32.75) / 12 * 2)
    assert all(not d.guard for d in model.raised(exact, S).doors)


def test_a_steps_price_a_pad_per_door_and_every_riser_after_the_first() -> None:
    a = model.slab(_plane(2, 0), S)
    assert a.cost.line("step pads").quantity == 8
    assert a.cost.line("steps").quantity == sum(d.risers - 1 for d in a.doors)
    b = model.raised(_plane(2, 0), S)
    assert b.cost.line("steps").quantity == b.risers_total


# ---------------------------------------------------------------- B results


def test_b_line_results_hold_every_station() -> None:
    b = model.raised(_plane(3, 1), S)
    by = {ln.name: ln for ln in b.lines}
    assert set(by) == {"front", "back", "left end", "right end", "party 20", "party 40", "party 60"}
    assert len(by["front"].walls_in) == 80 and len(by["party 40"].walls_in) == 25
    assert by["front"].level_bars == 3  # tallest over 4 ft
    assert b.average_wall_in == pytest.approx(
        sum(w * ln.length_ft / len(ln.walls_in) for ln in b.lines for w in ln.walls_in) / 285.0
    )
    assert b.simplifications == model.B_SIMPLIFICATIONS


def test_b_over_8_ft_takes_the_thicker_wall_and_a_fourth_bar() -> None:
    b = model.raised(_plane(6, 0), S)
    right = next(ln for ln in b.lines if ln.name == "right end")
    assert right.over_standard and right.thickness_in == S.engineered_stem_in and right.level_bars == 4
    left = next(ln for ln in b.lines if ln.name == "left end")
    assert not left.over_standard and left.thickness_in == S.stem_outside_in


def test_footing_steps_reported_where_the_ground_falls_over_1_in_10() -> None:
    assert not any(ln.footing_steps for ln in model.raised(_plane(6, 0), S).lines)  # 6 in 80
    steep = model.raised(_plane(0, 3), S)  # 3 in 25 across
    assert {ln.name for ln in steep.lines if ln.footing_steps} == {"left end", "right end", "party 20", "party 40", "party 60"}


# ---------------------------------------------------------------- ground support and B+P (5.7)


@pytest.mark.parametrize(
    "row, group",
    [
        ({"ground_class": "FIRM"}, support.ORDINARY),
        ({"ground_class": "ROCK"}, support.ORDINARY),
        ({"ground_class": "SOFT"}, support.PILES),
        ({"ground_class": "SWELL"}, support.PILES),
        ({"ground_class": "HAZ-SLIDE"}, support.OWN_LOOK),
        ({"ground_class": "FLOOD"}, support.OWN_LOOK),
        ({"ground_class": "NO-DATA", "alt_ground_class": "WET-FINE"}, support.ORDINARY),
        ({"ground_class": "NO-DATA", "alt_ground_class": ""}, support.NOT_SORTED),
        ({"ground_class": "SOMETHING"}, support.NOT_SORTED),
        ({}, support.NOT_SORTED),
    ],
)
def test_ground_support_groups_as_fd4_bin_of(row: dict, group: str) -> None:
    assert support.group_of(row, S) == group


def test_b_plus_p_drops_the_footing_and_adds_34_piles() -> None:
    for along, across in TEST.values():
        g = _plane(along, across)
        b, bp = model.raised(g, S), model.raised(g, S, piles=True)
        footing_ft3 = sum(
            {"long": S.footing_w_long_in, "end": S.footing_w_end_in, "party": S.footing_w_party_in}[ln.kind]
            * S.footing_t_in
            / 144
            * ln.length_ft
            for ln in model.wall_lines(S)
        )
        assert b.concrete_yd3 - bp.concrete_yd3 == pytest.approx(footing_ft3 / 27 * S.concrete_waste)
        assert bp.piles == 34 and b.piles == 0
        piles = bp.cost.line("screw piles")
        assert (piles.low, piles.high) == (Decimal(34 * 550), Decimal(34 * 950))
        assert bp.tallest_wall_in == b.tallest_wall_in and _counts(bp) == _counts(b)
        assert bp.method == "B+P"


def test_each_group_is_compared_on_its_own_methods() -> None:
    g = _plane(2, 0)
    ordinary = lot.run_lot(g, S, group=support.ORDINARY)
    assert ordinary.applicable == ("A dry", "A wet", "B") and not ordinary.flags
    assert {(c.prices, c.against) for c in ordinary.cheaper} == {("low", "A dry"), ("high", "A dry"), ("low", "A wet"), ("high", "A wet")}
    for c in ordinary.cheaper:
        a = ordinary[c.against].cost
        b = ordinary["B"].cost
        av, bv = (a.low, b.low) if c.prices == "low" else (a.high, b.high)
        assert c.by == abs(av - bv) and c.cheaper == ("B" if bv < av else "A")
    piles = lot.run_lot(g, S, group=support.PILES)
    assert piles.applicable == ("B+P",) and piles.cheaper == ()
    own = lot.run_lot(g, S, group=support.OWN_LOOK)
    assert own.applicable == ("B",) and support.NOT_STANDARD in own.flags
    unsorted = lot.run_lot(g, S, group=support.NOT_SORTED)
    assert support.GROUND_NOT_SORTED in unsorted.flags
    with pytest.raises(ValueError):
        lot.run_lot(g, S, group="bedrock")


# ---------------------------------------------------------------- one lot-file row


def _row(**over: str) -> dict[str, str]:
    row = {
        "TLID": "1S2E02CC  -07100",
        "county": "multnomah",
        "z_front_left": "100.0",
        "z_front_mid": "99.5",
        "z_front_right": "99.0",
        "z_back_left": "99.6",
        "z_back_mid": "99.1",
        "z_back_right": "98.6",
        "relief_ft": "1.6",
        "elev_cell_m": "1.0",
        "ground_class": "FIRM",
        "alt_ground_class": "",
        "front_face_turn_deg": "12.0",
    }
    row.update(over)
    return row


def test_from_row_keeps_the_tlid_whole_and_holds_every_item_of_section_2() -> None:
    r = lot.from_row(_row(), S)
    assert r is not None
    assert r.tlid == "1S2E02CC  -07100"
    assert r.group == support.ORDINARY and r.cell_m == 1.0 and r.ground_source == "six readings"
    assert r.lump_ft == pytest.approx((1.6 - 1.4) / 2)
    for name in ("B", "B+P", "A dry", "A wet"):
        m = r[name]
        assert m.floor_above_high_in > 0 and m.floor_above_low_in >= m.floor_above_high_in  # item 1
        assert m.lines and all(ln.walls_in for ln in m.lines)  # item 2
        assert m.tallest_wall_in >= m.average_wall_in > 0
        assert m.concrete_yd3 > 0 and m.bars_lb > 0 and m.form_sf > 0  # item 3
        assert len(m.doors) == 8  # item 4
        assert m.risers_total >= 8 and m.longest_stair_in >= 36  # item 5
        assert m.cost.lines and m.cost.low < m.cost.high  # item 6
        assert isinstance(m.flags, tuple)  # item 7
    assert r.cheaper  # item 8


def test_from_row_missing_reading_is_none_and_flags_come_from_the_row() -> None:
    assert lot.from_row(_row(z_back_mid=""), S) is None
    assert lot.from_row(_row(relief_ft="nan"), S) is None
    coarse = lot.from_row(_row(elev_cell_m="10.0", front_face_turn_deg="80"), S)
    assert coarse is not None
    assert lot.COARSE in coarse.flags and lot.FRONT_GUESS in coarse.flags


def test_settings_replace_is_how_a_value_changes() -> None:
    wet = S.replace(embed_in=12.0)
    assert wet.embed_in == 12.0 and S.embed_in == 18.0
    flat = _plane(0, 0)
    assert model.raised(flat, wet).tallest_wall_in == pytest.approx(29.0 - 6.0)
    assert replace(S, riser_in=8.0).riser_in == 8.0
