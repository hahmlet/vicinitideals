"""Open space and landscaping come off the lot less the building AND its pavement.

FOLLOWUPS 7(a), 2026-09-28. Until then the screen read ``open_space_min_pct``
and ``min_landscaped_pct`` against the lot less the building alone -- the rear
court, its aisle and the lane beside the building all counted as garden,
though every code that asks for either says pavement does not -- and it never
read ``open_space_min_sqft`` at all, though Portland states it in eighteen
zones, Milwaukie per ground-floor home and Multnomah LR-7 per dwelling. Both
checks carried the ``optimistic`` label for it.

The county map (quadfit s6s) has always subtracted building, court and
driveway, and found none of its 46,212 drawn plans short on amount. So these
tests are not here because a colour was wrong on the map; they are here
because the screen was answering a looser question than the code asks, which
is the false-GREEN shape whatever it happens to cost. The asymmetry they
defend is the usual one: a leftover is never over-stated, and where the
pavement cannot be drawn the check fails what it can prove and certifies
nothing.
"""

from __future__ import annotations

from datetime import date

import pytest

from flats.designs.model import ParkingConfig, load_catalog
from flats.fit.rectangle import Fit
from flats.rules.model import Provenance, Status
from flats.rules.resolver import Resolved, Verdict as RuleVerdict, ZoneResolution
from flats.score.paper import Alley, court_across, court_depth, paved
from flats.score.relief import ANY, ReliefPolicy
from flats.score.screen import (
    FACT_UNOBSERVED,
    OPTIMISTIC_CHECKS,
    LotFacts,
    Triage,
    screen,
)
from flats.score.slack import SlackPolicy, Verdict

pytestmark = pytest.mark.unit

WHERE = "or/multnomah/portland"
PROV = Provenance(
    cite="PCC 33.110.240",
    url="https://www.portland.gov/code/33/100s/110",
    retrieved=date(2026, 8, 27),
)
POLICY = SlackPolicy(tolerance={"fit_ft": 0.5})
NO_RELIEF = ReliefPolicy({WHERE: {ANY: []}})

DESIGN = load_catalog().latest("pod56x36")

#: Everything a lot needs cleared, generously, with a front setback -- the
#: lane from the street runs across it, so without one the pavement is not
#: known and the leftover checks cannot certify.
CLEAR = {
    "quadplex_allowed": True,
    "min_lot_sqft": 3000,
    "setback_front_ft": 10,
    "min_frontage_ft": 25,
    "min_lot_width_ft": 25,
    "max_coverage_pct": 60,
    "max_far": 2.0,
    "max_height_ft": 35,
    "max_units": 4,
    "parking_min_per_unit": 1.0,
}

LOT = LotFacts(lot_sqft=6000, frontage_ft=60, lot_width_ft=60)

#: The pod broadside with its floor of four stalls, on the design's own
#: geometry: a row 36 ft across and 18 deep, a 24 ft aisle across it, and the
#: 12 ft lane from the street past the 10 ft front yard, the 36 ft building
#: and the 5 ft standoff. The standoff itself is not pavement.
ROW_FT = 4 * DESIGN.parking.stall_width_ft
COURT_SQFT = ROW_FT * DESIGN.parking.stall_depth_ft + DESIGN.parking.aisle_ft * ROW_FT
LANE_SQFT = DESIGN.parking.lane_ft * (10 + 36 + DESIGN.parking.building_gap_ft)
PAVED_SQFT = COURT_SQFT + LANE_SQFT
LEFT_SQFT = LOT.lot_sqft - DESIGN.ground_sqft - PAVED_SQFT
BUILDING_ONLY_SQFT = LOT.lot_sqft - DESIGN.ground_sqft


def rules(exempted: tuple[str, ...] = (), **overrides) -> ZoneResolution:
    values = {**CLEAR, **overrides}
    return ZoneResolution(
        jurisdiction=WHERE,
        zone="R5",
        verdict=RuleVerdict.trusted,
        exempted=exempted,
        values={
            name: Resolved(
                name=name,
                value=value,
                status=Status.verified,
                prov=PROV,
                layer=WHERE,
                origin="zone",
            )
            for name, value in values.items()
            if value is not None
        },
    )


def fit(design=DESIGN) -> Fit:
    """Room to spare on the fit, searched as wide as the parking asks."""
    depth_ft = 36.0
    best = depth_ft + design.parking.court_depth_ft + 4.0
    return Fit(
        fits=True,
        width_ft=56.0,
        depth_ft=depth_ft,
        best_depth_ft=best,
        slack_ft=best - depth_ft,
        across_ft=max(56.0 + design.parking.lane_width_ft, design.court_width_ft),
    )


def run(rule_set, *, design=DESIGN, lot=LOT, relief=None):
    return screen(rule_set, lot, design, fit(design), policy=POLICY, relief=relief)


def check(result, name):
    return next(c for c in result.checks if c.check == name)


def test_the_arithmetic_this_file_rests_on() -> None:
    # About 2,100 sq ft of court and lane on a 6,000 sq ft lot: the old
    # leftover credited a third of the lot's open ground to asphalt.
    assert PAVED_SQFT == 2124
    assert LEFT_SQFT == 1860
    assert BUILDING_ONLY_SQFT == 3984


# --- the leftover is the lot less the building AND the pavement ---------


def test_the_court_and_its_lane_do_not_count_as_landscaping() -> None:
    # The test that would have caught it. Forty percent of 6,000 is 2,400:
    # the lot less the building leaves 3,984 and passed; less the court and
    # the lane it leaves 1,860 and does not.
    result = run(rules(min_landscaped_pct=40), relief=NO_RELIEF)

    got = check(result, "landscaped_pct")
    assert got.observed == pytest.approx(LEFT_SQFT / 6000 * 100)
    assert got.verdict is Verdict.fails
    assert result.triage is Triage.red
    assert result.head == "landscaped_pct"


def test_the_court_and_its_lane_do_not_count_as_open_space() -> None:
    result = run(rules(open_space_min_pct=40), relief=NO_RELIEF)

    got = check(result, "open_space_pct")
    assert got.observed == pytest.approx(LEFT_SQFT / 6000 * 100)
    assert got.verdict is Verdict.fails
    assert result.triage is Triage.red


def test_a_lot_with_room_past_its_pavement_is_still_green() -> None:
    # Thirty percent is 1,800 and the lot leaves 1,860: clears, and says by
    # how much, and nothing about it is labelled a favourable guess any more.
    result = run(rules(open_space_min_pct=30, min_landscaped_pct=30))

    assert result.triage is Triage.green
    assert check(result, "open_space_pct").verdict is Verdict.passes
    assert check(result, "landscaped_pct").verdict is Verdict.passes
    assert result.optimistic == ()


def test_neither_leftover_check_is_labelled_optimistic_now_it_is_honest() -> None:
    assert not {"open_space_pct", "landscaped_pct", "open_space_sqft"} & OPTIMISTIC_CHECKS


# --- the area form is read at all ----------------------------------------


def test_open_space_stated_as_an_area_is_a_check_and_not_a_silence() -> None:
    # Portland's 250 sq ft, Milwaukie's 96 a home, Multnomah LR-7's 300 a
    # home: encoded in twenty zones and read by nothing until this.
    ok = run(rules(open_space_min_sqft=250))
    short = run(rules(open_space_min_sqft=2000), relief=NO_RELIEF)

    assert ok.triage is Triage.green
    got = check(ok, "open_space_sqft")
    assert (got.observed, got.threshold) == (pytest.approx(LEFT_SQFT), 250.0)
    assert short.triage is Triage.red
    assert short.head == "open_space_sqft"


def test_the_area_and_the_share_are_two_standards_and_both_are_met() -> None:
    # A city stating both means both: clearing the share does not excuse the
    # area, and the area is the one this lot misses.
    result = run(rules(open_space_min_pct=10, open_space_min_sqft=1900), relief=NO_RELIEF)

    assert check(result, "open_space_pct").verdict is Verdict.passes
    assert check(result, "open_space_sqft").verdict is Verdict.fails
    assert result.triage is Triage.red


def test_a_zone_stating_no_open_space_area_runs_no_such_check() -> None:
    result = run(rules())

    assert all(c.check != "open_space_sqft" for c in result.checks)
    assert "open_space_sqft" not in result.unchecked
    assert result.triage is Triage.green


# --- unknown pavement is conservative -------------------------------------


def _side_drive():
    return DESIGN.model_copy(
        update={
            "parking": DESIGN.parking.model_copy(update={"config": ParkingConfig.side_drive})
        }
    )


def test_a_design_whose_pavement_nothing_draws_is_never_certified_on_its_leftover() -> None:
    # Nothing here draws a side drive, so its pavement is unknown. The lot
    # less the building clears the standard, and that is not evidence: the
    # drive may take the difference. Held out of GREEN on the fact.
    design = _side_drive()
    assert paved(design, rules(), deep_ft=36.0) is None

    result = run(rules(open_space_min_sqft=250), design=design)

    assert result.triage is Triage.unknown
    assert FACT_UNOBSERVED in result.reasons
    assert "open_space_sqft" in result.unchecked
    assert all(c.check != "open_space_sqft" for c in result.checks)


def test_a_standard_missed_with_nothing_paved_is_missed_whatever_is_paved() -> None:
    # The lot less the building is an upper bound on the leftover, so a miss
    # against it is certain whatever the pavement turns out to be, and it
    # stands as a failure rather than a question.
    result = run(rules(min_landscaped_pct=70), design=_side_drive(), relief=NO_RELIEF)

    got = check(result, "landscaped_pct")
    assert got.observed == pytest.approx(BUILDING_ONLY_SQFT / 6000 * 100)
    assert got.verdict is Verdict.fails
    assert result.triage is Triage.red


def test_a_lane_across_a_front_yard_nobody_encoded_is_unknown_not_free() -> None:
    # The lane runs from the street across the front setback. Unstated, its
    # length is not known, and zero would be the generous guess.
    result = run(rules(setback_front_ft=None, open_space_min_pct=20))

    assert "open_space_pct" in result.unchecked
    assert FACT_UNOBSERVED in result.reasons
    assert result.triage is Triage.unknown


def test_a_front_yard_the_code_waives_is_a_lane_that_starts_at_the_building() -> None:
    # Exempt is an answer, not a hole: no front yard, nothing to cross.
    waived = rules(setback_front_ft=None, exempted=("setback_front_ft",))

    got = paved(DESIGN, waived, deep_ft=36.0)

    assert got == pytest.approx(COURT_SQFT + DESIGN.parking.lane_ft * (36 + 5))


# --- what counts as pavement ----------------------------------------------


def test_the_standoff_behind_the_building_is_not_pavement() -> None:
    # The 5 ft between the rear wall and the first stall is walk, downspouts
    # and doors -- Fairview makes it a landscape strip -- and s6s leaves it in
    # the leftover too. Only the lane running past it is paved.
    court, _ = court_depth(DESIGN, rules())
    assert court == DESIGN.parking.building_gap_ft + 18 + 24

    assert paved(DESIGN, rules(), deep_ft=36.0) == pytest.approx(PAVED_SQFT)


def test_the_court_is_the_charged_row_and_grows_with_the_zones_cell() -> None:
    # Two stalls a home and a 10 ft stall: eight stalls at 10 ft, an 80 ft
    # row. The pavement is the row the lot is charged for, not the design's.
    zone = rules(parking_min_per_unit=2.0, parking_stall_width_ft=10)
    across = court_across(DESIGN, zone)
    assert (across.stalls, across.width_ft) == (8, 80.0)

    got = paved(DESIGN, zone, deep_ft=36.0)

    assert got == pytest.approx(80 * 18 + 24 * 80 + LANE_SQFT)


def test_a_design_that_parks_on_the_street_paves_nothing() -> None:
    street = DESIGN.model_copy(
        update={
            "parking": DESIGN.parking.model_copy(update={"config": ParkingConfig.street_only})
        }
    )

    assert paved(street, rules(), deep_ft=36.0) == 0.0


def test_where_the_alley_is_the_aisle_the_back_out_room_is_paved_and_no_lane_is() -> None:
    # Portland's shape: the driveway goes to the alley, and a car backing out
    # needs 20 ft of which a 14 ft alley gives 14. Four stalls 18 deep plus
    # the 6 ft short, across the 36 ft row; no aisle, no lane.
    zone = rules(parking_alley_access_required=True, parking_alley_backout_ft=20)
    alley = Alley(14.0, at_rear=True, rear_whole=True)

    got = paved(DESIGN, zone, alley, deep_ft=36.0)

    assert got == pytest.approx(ROW_FT * (18 + 6))
    # FOLLOWUPS 3(d): an alley along part of the rear line reaches the court
    # but is not its aisle -- the court and its own aisle are paved, and
    # still no lane.
    stub = Alley(14.0, at_rear=True)
    assert paved(DESIGN, zone, stub, deep_ft=36.0) == pytest.approx(COURT_SQFT)


def test_a_column_along_a_side_alley_paves_its_stalls_and_the_back_out_room() -> None:
    # The stalls turned end-on along the alley line, backing straight out
    # into it: four cells 9 ft along, each 18 deep plus the 6 ft the alley
    # leaves short. No aisle of the lot's own and no lane.
    zone = rules(parking_alley_access_required=True, parking_alley_backout_ft=20)
    alley = Alley(14.0, at_rear=False, at_side=True)

    got = paved(DESIGN, zone, alley, column=True, deep_ft=36.0)

    assert got == pytest.approx(ROW_FT * (18 + 6))


def test_a_court_reached_off_a_side_alley_paves_its_aisle_across_that_yard() -> None:
    # No back-out figure, so the court keeps its own aisle, and from a side
    # alley that aisle runs on across the yard on that line to reach it.
    zone = rules(
        parking_alley_access_required=True, setback_side_ft=5, setback_rear_ft=10
    )
    alley = Alley(16.0, at_rear=False, at_side=True)

    got = paved(DESIGN, zone, alley, deep_ft=36.0)

    # The deeper of side and rear where the code states no alley-side yard.
    assert got == pytest.approx(COURT_SQFT + 24 * 10)


def test_a_corner_court_reached_off_the_side_street_paves_the_drive_across_its_yard() -> None:
    zone = rules(corner_access_street="any", setback_street_side_ft=8)

    got = paved(DESIGN, zone, corner=True, deep_ft=36.0)

    assert got == pytest.approx(COURT_SQFT + DESIGN.parking.lane_ft * 8)


def test_the_lane_is_as_long_as_the_building_stands_deep_in_the_orientation_that_won() -> None:
    # End-on the pod is 56 deep, and the lane beside it is 20 ft longer.
    broadside = paved(DESIGN, rules(), deep_ft=36.0)
    end_on = paved(DESIGN, rules(), deep_ft=56.0)

    assert end_on - broadside == pytest.approx(DESIGN.parking.lane_ft * 20)


# --- a cap on buildings AND paving (King City Table 16.114-4) ------------

COVERED_SQFT = DESIGN.ground_sqft + PAVED_SQFT


def test_the_court_and_its_lane_count_against_a_cap_on_paving() -> None:
    # 2,016 of building and 2,124 of court and lane is 69 percent of 6,000:
    # under a 60 percent building-coverage cap it is a pass, under a 60
    # percent cap on buildings and paving a miss.
    assert COVERED_SQFT == 4140
    short = run(rules(max_impervious_pct=60), relief=NO_RELIEF)
    ok = run(rules(max_impervious_pct=80))

    got = check(short, "impervious_pct")
    assert got.observed == pytest.approx(69.0)
    assert got.verdict is Verdict.fails
    assert short.triage is Triage.red
    assert check(ok, "impervious_pct").verdict is Verdict.passes
    assert ok.triage is Triage.green


def test_unknown_paving_certifies_no_cap_but_a_building_over_it_fails() -> None:
    design = _side_drive()
    loose = run(rules(max_impervious_pct=80), design=design)
    tight = run(rules(max_impervious_pct=30), design=design, relief=NO_RELIEF)

    assert "impervious_pct" in loose.unchecked
    assert loose.triage is Triage.unknown
    # 2,016 of building alone is 33.6 percent: over 30 whatever is paved.
    assert check(tight, "impervious_pct").verdict is Verdict.fails
