"""Geometric fitment: angles, rasterization, and fit-with-a-margin.

The contracts that matter:

* the rotation search covers every distinct orientation and no more — a
  rectangle is unchanged by a half turn, so 180° through 360° is wasted work;
* rounding always shrinks the lot, never the pod, so a reported fit is real;
* a miss reports how far off it was, because the difference between three
  inches and thirty feet is the difference between a phone call and a pass.
"""

from __future__ import annotations

import pytest

shapely = pytest.importorskip("shapely")

from shapely import affinity  # noqa: E402
from shapely.geometry import MultiPolygon  # noqa: E402

from flats.designs.model import Orientation  # noqa: E402
from flats.fit import (  # noqa: E402
    DEFAULT_STEP_DEG,
    SWEEP_SPAN_DEG,
    Fitter,
    angles_for,
    cells_for,
    normalize,
    rasterize,
    sweep,
)
from flats.score.slack import SlackPolicy, Verdict  # noqa: E402

pytestmark = pytest.mark.unit

#: A generous rectangular envelope: 60 ft of frontage, 40 ft deep.
LOT = shapely.box(0, 0, 60, 40)


def fitter(envelope, angles=(0.0,), res: float = 1.0) -> Fitter:
    return Fitter(envelope, angles, res=res)


# --- the angle search -------------------------------------------------


def test_the_sweep_covers_half_a_circle_and_stops() -> None:
    # A rectangle rotated 180° maps onto itself. Testing the far half would
    # re-find placements already found, at double the cost per lot.
    angles = sweep(DEFAULT_STEP_DEG)

    assert len(angles) == int(SWEEP_SPAN_DEG / DEFAULT_STEP_DEG)
    assert angles[0] == 0.0
    assert max(angles) < SWEEP_SPAN_DEG


def test_a_coarse_sweep_is_still_evenly_spaced() -> None:
    assert sweep(45.0) == (0.0, 45.0, 90.0, 135.0)


@pytest.mark.parametrize("bad", [0.0, -5.0, 360.0])
def test_a_nonsense_step_is_refused(bad: float) -> None:
    with pytest.raises(ValueError):
        sweep(bad)


@pytest.mark.parametrize(
    ("raw", "folded"),
    [(190.0, 10.0), (-10.0, 170.0), (360.0, 0.0), (45.0, 45.0)],
)
def test_angles_fold_into_the_distinct_range(raw: float, folded: float) -> None:
    assert normalize(raw) == pytest.approx(folded)


def test_opposite_frontage_bearings_are_one_orientation() -> None:
    # A lot fronting two parallel streets does not get two searches.
    assert angles_for([45.0, 225.0], axis_required=True) == (45.0,)


def test_a_fixed_orientation_searches_only_the_street_bearings() -> None:
    # When the code requires the building to face the street, a pod that does
    # not fit that way does not fit.
    assert angles_for([37.5, 128.0], axis_required=True) == (37.5, 128.0)


def test_a_free_orientation_keeps_the_street_bearing_in_the_search() -> None:
    # 37.5 falls between whole-degree sweep steps; dropping it would lose the
    # one placement most likely to be permittable.
    angles = angles_for([37.5])

    assert 37.5 in angles
    assert len(angles) == len(sweep()) + 1


def test_a_lot_with_no_named_frontage_still_gets_searched() -> None:
    # Being unable to identify the front is not a reason to skip a lot; that is
    # exactly how the predecessor lost 88,947 of them.
    assert angles_for() == sweep()


# --- rasterizing ------------------------------------------------------


@pytest.mark.parametrize(
    ("length", "res", "expected"),
    [(36.0, 0.5, 72), (36.1, 0.5, 73), (0.1, 0.5, 1), (0.0, 0.5, 1)],
)
def test_a_required_size_always_rounds_up(length: float, res: float, expected: int) -> None:
    # Rounding down would let a pod claim to fit in less space than it occupies.
    assert cells_for(length, res) == expected


def test_a_rectangle_rasterizes_to_its_full_extent() -> None:
    # Not one cell less. Losing the outer ring to boundary arithmetic would
    # invent a two-foot shortfall on every lot in the county.
    [grid] = rasterize(LOT, 0.0, res=1.0)

    assert (grid.rows, grid.cols) == (40, 60)
    assert grid.has_window(40, 60)
    assert not grid.has_window(41, 60)


def test_the_deepest_window_is_found_by_search() -> None:
    [grid] = rasterize(LOT, 0.0, res=1.0)

    assert grid.max_depth_cells(60) == 40
    assert grid.max_depth_cells(61) == 0


def test_an_empty_envelope_rasterizes_to_nothing() -> None:
    assert rasterize(shapely.Polygon(), 0.0) == []
    assert rasterize(None, 0.0) == []


def test_a_nonsense_resolution_is_refused() -> None:
    with pytest.raises(ValueError):
        rasterize(LOT, 0.0, res=0.0)


def test_disjoint_envelope_parts_stay_separate() -> None:
    # Two 20 ft strips ten feet apart hold no 30 ft rectangle. Rasterizing them
    # into one frame would bridge the gap and report a fit across a setback.
    split = MultiPolygon([shapely.box(0, 0, 20, 40), shapely.box(30, 0, 50, 40)])

    grids = rasterize(split, 0.0, res=1.0)

    assert len(grids) == 2
    assert not any(g.has_window(10, 30) for g in grids)


def test_slivers_are_dropped() -> None:
    sliver = MultiPolygon([shapely.box(0, 0, 60, 40), shapely.box(70, 0, 71, 2)])

    assert len(rasterize(sliver, 0.0, res=1.0)) == 1


def test_a_window_maps_back_to_real_ground() -> None:
    [grid] = rasterize(LOT, 0.0, res=1.0)
    hit = grid.first_window(36, 56)
    assert hit is not None

    rect = grid.to_world(*hit, 36, 56)

    assert rect.area == pytest.approx(56 * 36)
    assert LOT.buffer(1e-6).contains(rect)


# --- fitting a design -------------------------------------------------


def test_a_pod_that_fits_reports_the_room_it_had() -> None:
    fit = fitter(LOT).fit(56, 36)

    assert fit.fits
    assert fit.best_depth_ft == pytest.approx(40.0)
    assert fit.slack_ft == pytest.approx(4.0)
    assert fit.orientation is Orientation.width_facing


def test_a_pod_that_misses_reports_how_far() -> None:
    # 44 ft of depth needed, 40 available. Four feet short is a design change;
    # thirty would not be.
    fit = fitter(LOT).fit(56, 44)

    assert not fit.fits
    assert fit.slack_ft == pytest.approx(-4.0)
    assert fit.placement is None


def test_a_width_the_lot_cannot_hold_reads_as_a_total_miss() -> None:
    # No rectangle of that width exists at any depth, so the depth margin is the
    # whole requirement. It is a blunt number by design: the lot is not close.
    fit = fitter(LOT).fit(80, 20)

    assert not fit.fits
    assert fit.best_depth_ft == 0.0
    assert fit.slack_ft == pytest.approx(-20.0)


def test_turning_the_pod_sideways_can_save_the_lot() -> None:
    deep = shapely.box(0, 0, 40, 60)

    fit = fitter(deep).fit(56, 36)

    assert fit.fits
    assert fit.orientation is Orientation.depth_facing


def test_the_flip_reports_the_run_it_actually_needed() -> None:
    # `depth_ft` and `width_ft` are the design's, unrotated, whichever
    # orientation won. When the flip wins, the run the envelope had to hold is
    # the design's *width*, and a caller reading `depth_ft` as the requirement
    # reads the wrong number by twenty feet.
    deep = shapely.box(0, 0, 40, 50)

    fit = fitter(deep).fit(56, 36)

    assert fit.orientation is Orientation.depth_facing
    assert not fit.fits
    assert fit.depth_ft == 36
    assert fit.required_ft == pytest.approx(56.0)
    assert fit.best_depth_ft == pytest.approx(50.0)


def test_the_unflipped_requirement_is_simply_the_depth() -> None:
    fit = fitter(LOT).fit(56, 36)

    assert fit.orientation is Orientation.width_facing
    assert fit.required_ft == pytest.approx(fit.depth_ft)

def test_a_street_facing_requirement_forbids_the_flip() -> None:
    # Some codes fix the orientation. Then the sideways placement is not a
    # placement, and the lot is out.
    deep = shapely.box(0, 0, 40, 60)

    assert not fitter(deep).fit(56, 36, allow_flip=False).fits


def test_a_square_pod_has_only_one_orientation() -> None:
    fit = fitter(LOT).fit(30, 30)

    assert fit.fits
    assert fit.orientation is Orientation.width_facing


def test_a_skewed_lot_is_found_by_the_sweep() -> None:
    # The whole reason the sweep exists: this lot holds the pod at 30°, and at
    # no angle the frontage bearings would have suggested.
    skewed = affinity.rotate(LOT, 30, origin=(0, 0))

    assert not fitter(skewed, angles=(0.0,)).fit(56, 36).fits
    assert fitter(skewed, angles=(0.0, 30.0)).fit(56, 36).fits


def test_the_reported_angle_is_the_one_that_worked() -> None:
    skewed = affinity.rotate(LOT, 30, origin=(0, 0))

    fit = fitter(skewed, angles=(0.0, 30.0)).fit(56, 36)

    assert fit.angle_deg == pytest.approx(30.0)


def test_the_placement_lands_inside_the_envelope() -> None:
    skewed = affinity.rotate(LOT, 30, origin=(0, 0))

    fit = fitter(skewed, angles=(0.0, 30.0)).fit(56, 36)

    assert fit.placement is not None
    assert fit.placement.area == pytest.approx(56 * 36, rel=1e-6)
    assert skewed.buffer(0.01).contains(fit.placement)


def test_the_placement_can_be_skipped() -> None:
    # The batch run scores hundreds of thousands of lots; only the ones a human
    # opens need a drawing.
    fit = fitter(LOT).fit(56, 36, placement=False)

    assert fit.fits
    assert fit.placement is None


def test_an_empty_envelope_fits_nothing() -> None:
    f = Fitter(shapely.Polygon(), (0.0,))

    assert f.empty
    assert not f.fit(56, 36).fits


def test_a_farm_sized_envelope_is_searched_on_a_coarser_grid_not_skipped() -> None:
    # Oregon City 32E05D 01204: an 18-acre commercial lot with no setback
    # rasterized past the cell cap at half a foot and read as fitting nothing.
    farm = shapely.box(0, 0, 1500, 1000)
    f = Fitter(farm, (0.0, 30.0))

    assert f.res > 0.5 and f.res % 0.5 == 0
    assert all(g.integral.size <= 4_000_000 * 1.1 for g in f.grids)
    assert f.fit(56, 36).fits
    # A coarser grid only ever shrinks the lot.
    assert 990 <= Fitter(farm, (0.0,)).fit(56, 36).best_depth_ft <= 1000
    # An infill lot keeps the fine grid.
    assert Fitter(LOT, (0.0,)).res == 0.5


# --- what the parking asks across the lot ------------------------------
#
# Since 2026-09-17 a search can be asked for more than the building: the
# drive lane down one flank of it, or the row of stalls behind it. Pure
# geometry still -- two widths in feet, no zoning -- but it is the width the
# envelope has to hold, and a lot that holds the building and not its cars
# holds no pod.


def test_a_bare_rectangle_is_the_default() -> None:
    fit = fitter(LOT).fit(56, 36)

    assert fit.fits
    assert fit.across_ft == pytest.approx(56.0)


def test_the_lane_is_searched_beside_the_building() -> None:
    # 60 ft of frontage holds a 56 ft building and not the building with a
    # 12 ft lane beside it. Turned end-on the lane fits (36 + 12) but the 56
    # ft run does not, so the lot is out.
    fit = fitter(LOT).fit(56, 36, lane_ft=12)

    assert not fit.fits
    assert fitter(shapely.box(0, 0, 68, 40)).fit(56, 36, lane_ft=12).fits


def test_the_court_is_searched_behind_the_building_never_beside_the_lane() -> None:
    # The court sits behind both the building and its lane, so the width
    # asked is the wider of building-plus-lane and court, never their sum:
    # 68 ft holds a 56 ft building, its 12 ft lane and a 54 ft court, and
    # 80 is not asked.
    fit = fitter(shapely.box(0, 0, 68, 40)).fit(56, 36, lane_ft=12, court_width_ft=54)

    assert fit.fits
    assert fit.across_ft == pytest.approx(68.0)


def test_a_court_wider_than_the_building_sets_the_width_end_on() -> None:
    # End-on the building is 36 and its lane makes 48; a 54 ft court is the
    # wider figure and the one the envelope has to hold.
    fit = fitter(shapely.box(0, 0, 55, 60)).fit(56, 36, lane_ft=12, court_width_ft=54)

    assert fit.fits
    assert fit.orientation is Orientation.depth_facing
    assert fit.across_ft == pytest.approx(54.0)
    assert not fitter(shapely.box(0, 0, 53, 60)).fit(56, 36, lane_ft=12, court_width_ft=54).fits


def test_the_placement_is_as_wide_as_the_search() -> None:
    # The rectangle placed is what was looked for: the building with its lane,
    # at the building's depth. The court's own depth is the screen's business.
    fit = fitter(shapely.box(0, 0, 70, 40)).fit(56, 36, lane_ft=12)

    assert fit.placement is not None
    assert fit.placement.area == pytest.approx(68 * 36, rel=1e-6)


def test_a_design_carries_its_own_lane_and_court_into_the_search() -> None:
    # `fit_design` charges what the design draws unless a city's figures are
    # passed in: the pod's 12 ft lane and six 9 ft stalls. 60 x 40 holds the
    # bare 56 x 36 and not the pod with its parking.
    from flats.designs.model import load_catalog

    pod = load_catalog().latest("pod56x36")
    f = fitter(LOT)

    assert f.fit(56, 36).fits
    assert not f.fit_design(pod).fits
    assert f.fit_design(pod, lane_ft=0.0, court_width_ft=0.0).fits


# --- reusing the raster across designs --------------------------------


def test_one_raster_answers_for_the_whole_catalog() -> None:
    # Rasterizing is the expensive step and it does not depend on the design.
    # This is what makes screening ten pod designs cost about what one costs.
    f = fitter(LOT)

    assert f.fit(56, 36).fits
    assert f.fit(80, 25).fits is False
    assert f.fit(25, 80).fits is False
    assert f.fit(50, 40).fits


def test_the_frontier_is_non_increasing() -> None:
    # Wider rectangles can never go deeper, so the frontier answers any future
    # width-by-depth question about this lot without re-rasterizing it.
    depths = fitter(LOT).frontier([20, 30, 40, 50, 60, 70])

    assert list(depths) == sorted(depths, reverse=True)
    assert depths[-1] == 0.0


# --- the seam with the slack policy -----------------------------------


def test_a_miss_inside_one_cell_routes_to_review_not_red() -> None:
    # The rasterizer can understate a lot by a cell. The fit_ft tolerance is set
    # to exactly one cell width so that artifact costs a review, never a lot.
    policy = SlackPolicy(tolerance={"fit_ft": 0.5})
    fit = fitter(LOT, res=0.5).fit(56, 40.3)

    result = policy.evaluate(
        "fit_ft", observed=fit.best_depth_ft, threshold=fit.depth_ft, is_maximum=False
    )

    assert not fit.fits
    assert result.verdict is Verdict.tolerated
    assert result.verdict.blocks


def test_a_real_shortfall_stays_red() -> None:
    policy = SlackPolicy(tolerance={"fit_ft": 0.5})
    fit = fitter(LOT, res=0.5).fit(56, 44)

    result = policy.evaluate(
        "fit_ft", observed=fit.best_depth_ft, threshold=fit.depth_ft, is_maximum=False
    )

    assert result.verdict is Verdict.fails
