"""Slope: the steep ground taken off before the pod is placed, and the grade
under the plan that is (FOLLOWUPS 38).

Steph, 2026-10-04: up to 5% under the building and its parking is GREEN, 5
to 15% a closer look, over 15% RED; and "slope-based lot elimination should
happen before pod placement ... measure how much of the lot is sloped like
that and subtract it and see if there's even enough land for the pod."

Pinned here:

* :class:`flats.fit.slope.Terrain` reads a grade over a run, not pixel to
  pixel -- a curb is not a hillside -- and finds the steep part of a lot
  where it is; the coarse model answers where the fine one is missing;
* the ruling's numbers are Steph's, and a coarse reading never makes RED;
* the screen turns each band into its colour, with no relief round a
  hillside, and names a fit lost to the steep ground as the slope's;
* the bridge takes the steep ground off before the fit, and a lot that
  fits only on its steep ground is RED on slope.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

pytest.importorskip("rasterio")

import numpy as np  # noqa: E402
from shapely.geometry import box  # noqa: E402

from flats.encode.load import load_trusted  # noqa: E402
from flats.fit.rectangle import Fit  # noqa: E402
from flats.fit.slope import ONE_M, TEN_M, SlopeRules, Terrain, load_rules  # noqa: E402
from flats.ingest.quadfit import envelope_for, lot_from_row, screen_lot, with_steep  # noqa: E402
from flats.score import flags as flag_plan, relief, slack  # noqa: E402
from flats.score.relief import NO_ZONING_RELIEF  # noqa: E402
from flats.score.screen import (  # noqa: E402
    CLOSER_LOOK_SLOPE,
    FACT_UNOBSERVED,
    SITE_GRADE_CHECK,
    SLOPE_RULING,
    STEEP_GROUND,
    LotFacts,
    Triage,
    screen,
)
from flats.score.slack import Verdict  # noqa: E402
from flats.tests.dem import plane, write_dem  # noqa: E402
from flats.tests.test_fire import DESIGN, X0, Y0, bridge_row, fit, rules  # noqa: E402

pytestmark = pytest.mark.unit

#: A 100 x 100 ft square at real Portland coordinates.
LOT = box(X0, Y0, X0 + 100, Y0 + 100)


def terrain(tmp_path: Path, z, *, res_m: float = 1.0, fine: bool = True) -> Terrain:
    where = tmp_path / ("dem" if fine else "dem10_utm") / "tile.tif"
    write_dem(where, LOT.bounds, z, res_m=res_m)
    if fine:
        return Terrain(where.parent, None)
    return Terrain(None, where.parent)


# --- reading the ground -----------------------------------------------------


@pytest.mark.parametrize("pct", [0.0, 3.0, 8.0, 22.0])
def test_a_plane_reads_its_own_grade(tmp_path: Path, pct: float) -> None:
    got = terrain(tmp_path, plane(pct)).grade([box(X0 + 20, Y0 + 20, X0 + 76, Y0 + 56)])
    assert got is not None and got.source == ONE_M
    assert got.pct == pytest.approx(pct, abs=0.3)


def test_a_curb_is_not_a_hillside(tmp_path: Path) -> None:
    """A 0.3 m step across a flat lot reads 30% pixel to pixel -- the reason
    the 1 m model is read over a run. Over the run it is a gentle rise."""

    def curb(x, y):
        return np.where(x > 15.0, 0.3, 0.0)

    t = terrain(tmp_path, curb)
    raw = np.hypot(*np.gradient(np.array([[0.0, 0.3], [0.0, 0.3]]), 1.0)) * 100
    assert raw.max() >= 15.0
    got = t.steep(LOT, load_rules().steep_over_pct)
    assert got is not None and got.sqft == 0.0


def test_the_steep_part_of_a_lot_is_found_where_it_is(tmp_path: Path) -> None:
    """Flat for the western half, 30% beyond: about half the lot is steep,
    and it is the eastern half."""

    def bank(x, y):
        return np.where(x > 15.0, (x - 15.0) * 0.30, 0.0)

    got = terrain(tmp_path, bank).steep(LOT, 15.0)
    assert got is not None and got.source == ONE_M
    assert 0.35 * LOT.area < got.sqft < 0.65 * LOT.area
    assert got.geom.centroid.x > LOT.centroid.x + 15


def test_the_coarse_model_answers_where_the_fine_one_does_not(tmp_path: Path) -> None:
    t = terrain(tmp_path, plane(10.0), res_m=10.0, fine=False)
    got = t.grade([box(X0 + 20, Y0 + 20, X0 + 76, Y0 + 56)])
    assert got is not None and got.source == TEN_M
    assert got.pct == pytest.approx(10.0, abs=0.5)
    steep = t.steep(LOT, 15.0)
    assert steep is not None and steep.source == TEN_M and steep.sqft == 0.0


def test_ground_no_model_covers_has_no_answer(tmp_path: Path) -> None:
    assert Terrain(None, None).grade([LOT]) is None
    assert Terrain(None, None).steep(LOT, 15.0) is None
    far = box(X0 + 50_000, Y0, X0 + 50_100, Y0 + 100)
    t = terrain(tmp_path, plane(5.0))
    assert t.grade([far]) is None and t.steep(far, 15.0) is None


# --- Steph's ruling -----------------------------------------------------------


def test_the_cut_offs_are_stephs() -> None:
    got = load_rules()
    assert (got.grade_green_max_pct, got.grade_red_over_pct, got.steep_over_pct) == (5.0, 15.0, 15.0)
    assert got.coarse_red_is_closer_look
    assert got.min_bank_ft == 4.0 and got.steep_in_setbacks


@pytest.mark.parametrize(
    "pct, source, band",
    [
        (4.9, ONE_M, "green"),
        (5.0, ONE_M, "green"),
        (5.1, ONE_M, "closer"),
        (15.0, ONE_M, "closer"),
        (15.1, ONE_M, "red"),
        (40.0, TEN_M, "closer"),
    ],
)
def test_each_grade_falls_in_its_band(pct: float, source: str, band: str) -> None:
    assert load_rules().band(pct, source) == band


def test_the_green_line_may_not_sit_over_the_red(tmp_path: Path) -> None:
    bad = tmp_path / "slope.yaml"
    bad.write_text(
        "steep_over_pct: 15\ngrade_green_max_pct: 20\ngrade_red_over_pct: 15\n"
        "run_m: 5\ncoarse_red_is_closer_look: true\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="green line"):
        load_rules.__wrapped__(bad)
    assert isinstance(load_rules(), SlopeRules)


# --- the screen ---------------------------------------------------------------


def run(lot: LotFacts, the_fit: Fit | None = None):
    return screen(
        rules(),
        lot,
        DESIGN,
        the_fit or fit(),
        policy=slack.SlackPolicy(tolerance={"fit_ft": 0.5}),
        relief=relief.load_policy(),
    )


def facts(**over) -> LotFacts:
    return LotFacts(
        lot_sqft=6000, frontage_ft=60, lot_width_ft=60, fire_route_ft=100.0,
        fire_route_tried=True, **over,
    )


def test_a_flat_pad_is_green() -> None:
    got = run(facts(site_grade_pct=3.0, site_grade_source=ONE_M, site_grade_tried=True))
    assert got.triage is Triage.green and got.colour is flag_plan.Colour.green


def test_a_pad_between_the_lines_is_a_closer_look() -> None:
    got = run(facts(site_grade_pct=8.0, site_grade_source=ONE_M, site_grade_tried=True))
    assert got.triage is Triage.yellow and got.reasons == (CLOSER_LOOK_SLOPE,)
    (flag,) = [f for f in got.flags if f.code == "SLOPE-GRADE"]
    assert flag.bounds == (5.0, 8.0)
    assert got.colour is flag_plan.Colour.yellow
    assert not got.binds


def test_a_pad_past_the_red_line_is_red_and_no_relief_softens_it() -> None:
    got = run(facts(site_grade_pct=19.0, site_grade_source=ONE_M, site_grade_tried=True))
    assert got.triage is Triage.red
    (bind,) = [b for b in got.binds if b.check == SITE_GRADE_CHECK]
    assert bind.source == SLOPE_RULING and bind.relief is None
    assert {SITE_GRADE_CHECK, STEEP_GROUND} <= NO_ZONING_RELIEF


def test_the_coarse_model_alone_never_makes_red() -> None:
    got = run(facts(site_grade_pct=19.0, site_grade_source=TEN_M, site_grade_tried=True))
    assert got.triage is Triage.yellow and CLOSER_LOOK_SLOPE in got.reasons
    assert not got.binds


def test_a_pad_looked_for_and_not_read_is_unobserved() -> None:
    got = run(facts(site_grade_tried=True))
    assert FACT_UNOBSERVED in got.reasons and got.triage is Triage.unknown
    assert any(f.code == "MEASURE-SITE-GRADE" for f in got.flags)


def test_a_screen_never_asked_about_slope_is_unchanged() -> None:
    assert run(facts()).triage is Triage.green


def test_a_fit_lost_to_steep_ground_is_the_slopes() -> None:
    short = dataclasses.replace(fit(), best_depth_ft=40.0, slack_ft=4.0)
    # A fit missed on its own is the fit's: here a variance is assumed round it.
    plain = run(facts(), short)
    assert any(b.check == "fit_ft" for b in plain.binds)
    # Missed only because the steep ground came off, it is the hillside's,
    # and no variance flattens a hillside.
    got = run(facts(steep_blocks=True, steep_sqft=3000.0, steep_source=ONE_M), short)
    assert got.triage is Triage.red
    assert [b.check for b in got.binds] == [STEEP_GROUND]
    assert got.binds[0].source == SLOPE_RULING
    # A fit that was met is not renamed, whatever the flag says.
    assert run(facts(steep_blocks=True)).triage is Triage.green


# --- the bridge ---------------------------------------------------------------


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


ROW_LOT = box(X0, Y0, X0 + 80, Y0 + 120)


def bridge_terrain(tmp_path: Path, z) -> Terrain:
    where = write_dem(tmp_path / "dem" / "tile.tif", ROW_LOT.bounds, z)
    return Terrain(where.parent, None)


def screened(corpus, policies, t: Terrain):
    lot = with_steep(lot_from_row(bridge_row(), corpus.layers), t)
    (s,) = screen_lot(
        lot, [DESIGN], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0,
        terrain=t,
    )
    return lot, s


def test_a_flat_lot_is_graded_and_keeps_its_colour(tmp_path, corpus, policies) -> None:
    flat_lot = lot_from_row(bridge_row(), corpus.layers)
    (before,) = screen_lot(
        flat_lot, [DESIGN], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0
    )
    lot, s = screened(corpus, policies, bridge_terrain(tmp_path, plane(2.0)))
    assert lot.steep is None and s.facts.steep_sqft == 0.0
    assert s.facts.site_grade_tried and s.facts.site_grade_pct == pytest.approx(2.0, abs=0.3)
    assert s.signed.triage is before.signed.triage


def test_a_pad_on_an_even_eight_percent_is_a_closer_look(tmp_path, corpus, policies) -> None:
    _, s = screened(corpus, policies, bridge_terrain(tmp_path, plane(8.0)))
    assert s.facts.steep_sqft == 0.0
    assert s.facts.site_grade_pct == pytest.approx(8.0, abs=0.4)
    assert CLOSER_LOOK_SLOPE in s.signed.reasons
    assert any(f.code == "SLOPE-GRADE" for f in s.signed.flags)


def test_steep_ground_comes_off_before_the_pod_is_placed(tmp_path, corpus, policies) -> None:
    """Flat for the front 12 m, 35% behind: the building and its court do
    not fit on the flat strip, and do on the whole lot -- RED on slope."""

    def bank(x, y):
        return np.where(y > 12.0, (y - 12.0) * 0.35, 0.0)

    t = bridge_terrain(tmp_path, bank)
    lot, s = screened(corpus, policies, t)
    assert lot.steep is not None and lot.facts.steep_sqft > 0.4 * ROW_LOT.area
    whole = envelope_for(dataclasses.replace(lot, steep=None), s.rules)
    assert s.envelope.sqft < whole.sqft
    assert s.facts.steep_blocks
    assert any(b.check == STEEP_GROUND for b in s.signed.binds)
    assert s.signed.triage is Triage.red
    assert next(c for c in s.screening.checks if c.check == STEEP_GROUND).verdict is Verdict.fails


# --- banks and setbacks ---------------------------------------------------------


def test_a_short_bank_is_regraded_and_a_tall_one_is_lost(tmp_path: Path) -> None:
    """A front yard raised 0.9 m (about 3 ft) over 4 m reads as a strip of
    steep ground over the run; with a 4 ft floor it is a bank to regrade.
    A 3 m (10 ft) rise is not."""

    def short(x, y):
        return np.clip((x - 14.0) / 4.0, 0.0, 1.0) * 0.9

    def tall(x, y):
        return np.clip((x - 9.0) / 12.0, 0.0, 1.0) * 3.0

    t = terrain(tmp_path / "short", short)
    assert t.steep(LOT, 15.0).sqft > 0
    assert t.steep(LOT, 15.0, min_bank_ft=4.0).sqft == 0.0
    t = terrain(tmp_path / "tall", tall)
    kept = t.steep(LOT, 15.0, min_bank_ft=4.0)
    assert kept.sqft > 0 and kept.sqft == pytest.approx(t.steep(LOT, 15.0).sqft)


def test_the_bank_floor_is_read_and_may_not_be_negative(tmp_path: Path) -> None:
    got = load_rules()
    assert got.min_bank_ft >= 0
    bad = tmp_path / "slope.yaml"
    bad.write_text(
        "steep_over_pct: 15\ngrade_green_max_pct: 5\ngrade_red_over_pct: 15\n"
        "run_m: 5\ncoarse_red_is_closer_look: true\nmin_bank_ft: -1\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="min_bank_ft"):
        load_rules.__wrapped__(bad)


@pytest.mark.parametrize("in_yards", [True, False])
def test_steep_ground_in_the_setbacks_counts_only_when_ruled_so(
    tmp_path, corpus, policies, monkeypatch, in_yards: bool
) -> None:
    import flats.ingest.quadfit as bridge

    lot, s = screened(corpus, policies, bridge_terrain(tmp_path, plane(0.0)))
    flat = envelope_for(lot, s.rules)
    yard = lot.lot_geom.difference(flat.geom.buffer(1.0))
    inside = box(*flat.geom.centroid.buffer(4.0).bounds)
    monkeypatch.setattr(
        bridge, "slope_rules", lambda: dataclasses.replace(load_rules(), steep_in_setbacks=in_yards)
    )
    in_yard = envelope_for(dataclasses.replace(lot, steep=yard), s.rules)
    assert in_yard.geom.area == pytest.approx(flat.geom.area, abs=1.0)
    if in_yards:
        assert in_yard.ground.area < flat.ground.area - 100
    else:
        assert in_yard.ground.area == pytest.approx(flat.ground.area, abs=1.0)
    # Steep ground where the building may stand comes off either way.
    under = envelope_for(dataclasses.replace(lot, steep=inside), s.rules)
    assert under.geom.area < flat.geom.area - 50
    assert under.ground.area < flat.ground.area - 50


# --- net-acre slopes (FOLLOWUPS 30(e)/38(b)) -------------------------------------


def test_the_ground_over_each_grade_is_counted_whole(tmp_path: Path) -> None:
    """Flat for the western 15 m, 30% beyond: about half the lot is over 20
    and 25%, none of it over 35% -- and a 4 ft bank floor does not shrink
    the count, which is the code's figure, not the pod's."""

    def bank(x, y):
        return np.where(x > 15.0, (x - 15.0) * 0.30, 0.0)

    t = terrain(tmp_path, bank)
    got = t.steep(LOT, 15.0, min_bank_ft=4.0, areas_over=(20.0, 25.0, 35.0))
    assert 0.35 * LOT.area < got.areas[20.0] < 0.65 * LOT.area
    assert got.areas[25.0] == pytest.approx(got.areas[20.0], rel=0.1)
    assert got.areas[35.0] == 0.0


def _with_net(lot, net):
    return dataclasses.replace(lot, facts=dataclasses.replace(lot.facts, net_deductions=net))


def test_the_bridge_hands_the_slopes_to_the_net_acre_on_lidar_only(
    tmp_path, corpus, policies
) -> None:
    from flats.rules.net_area import SLOPES

    def bank(x, y):
        return np.where(y > 12.0, (y - 12.0) * 0.35, 0.0)

    row_lot = lot_from_row(bridge_row(), corpus.layers)
    lot = with_steep(_with_net(row_lot, {"floodplain": 0.0}), bridge_terrain(tmp_path / "a", bank))
    assert set(SLOPES) <= set(lot.facts.net_deductions)
    assert lot.facts.net_deductions["slope_25"] > 0.4 * ROW_LOT.area
    assert lot.facts.net_deductions["floodplain"] == 0.0
    # Nothing measured beside it: nothing is started.
    bare = with_steep(_with_net(row_lot, None), bridge_terrain(tmp_path / "b", bank))
    assert bare.facts.net_deductions is None
    # The 10 m model's cells are wider than what it would count.
    where = write_dem(tmp_path / "c" / "dem10" / "t.tif", ROW_LOT.bounds, bank, res_m=10.0)
    coarse = with_steep(_with_net(row_lot, {}), Terrain(None, where.parent))
    assert coarse.facts.steep_source == TEN_M and not coarse.facts.net_deductions
