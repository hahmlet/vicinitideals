"""Measurements become a verdict.

Four asymmetries define this module and every test here defends one of them:

* an unverified rule set can never produce RED — a bad number in a YAML file
  must not delete an acquisition target;
* tolerance rescues a lot into UNKNOWN and never certifies one into GREEN --
  except the fit, which inside its tolerance either way is GREEN with a
  ``tight_fit`` flag (Steph 2026-09-25: every acquisition is surveyed);
* a required standard nobody encoded blocks GREEN rather than being assumed
  satisfied;
* a miss the code offers a path around is YELLOW, not RED. A pod one foot over
  a setback is an adjustment application, not a dead lot, and only a standard
  with no procedure at all kills one.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

pytest.importorskip("shapely")

import shapely  # noqa: E402

from flats.designs.model import Orientation, Plat, StallBands, load_catalog  # noqa: E402
from flats.fit.rectangle import Fit, Fitter  # noqa: E402
from flats.geom.edges import Tier as GeometryTier  # noqa: E402
from flats.rules.conditions import Tier  # noqa: E402
from flats.rules.model import Provenance, Status  # noqa: E402
from flats.rules.resolver import Resolved, Verdict as RuleVerdict, ZoneResolution  # noqa: E402
from flats.score.relief import (  # noqa: E402
    ANY,
    RELIEF_UNCONFIRMED,
    USE,
    ReliefPath,
    ReliefPolicy,
)
from flats.score.configure import configure  # noqa: E402
from flats.score.screen import (  # noqa: E402
    COURT_WIDTH_UNMEASURED,
    FACT_ASSUMED,
    FACT_UNOBSERVED,
    GEOMETRY_UNREADABLE,
    NO_FRONTAGE,
    STANDARD_NOT_ENCODED,
    USE_NOT_ENCODED,
    USE_PROHIBITED,
    LotFacts,
    Triage,
    backlog,
    fit_for,
    histogram,
    screen,
    seats,
)
from flats.score.slack import SlackPolicy, Verdict  # noqa: E402

pytestmark = pytest.mark.unit

WHERE = "or/multnomah/portland"
PROV = Provenance(
    cite="PCC 33.110.220",
    url="https://www.portland.gov/code/33/100s/110",
    retrieved=date(2026, 8, 12),
)
POLICY = SlackPolicy(tolerance={"fit_ft": 0.5})

#: A jurisdiction that has read its own code and found no procedure at all.
#: An explicit empty list is how a code says "not waivable"; silence means the
#: opposite, which is the whole point of the default.
NO_RELIEF = ReliefPolicy({WHERE: {ANY: []}})

#: A jurisdiction whose adjustment chapter somebody has actually read.
READ = ReliefPolicy(
    {
        WHERE: {
            ANY: [
                ReliefPath(
                    "adjustment",
                    Tier.administrative,
                    cap_pct=0.10,
                    cite="PCC 33.805.040",
                    confirmed=True,
                ),
                ReliefPath(
                    "variance", Tier.discretionary, cite="PCC 33.805.050", confirmed=True
                ),
            ]
        }
    }
)

DESIGN = load_catalog().latest("pod56x36")

#: Every standard a lot needs cleared, set generously so each test can break
#: exactly one of them.
CLEAR = {
    "quadplex_allowed": True,
    "min_lot_sqft": 3000,
    "min_frontage_ft": 25,
    "min_lot_width_ft": 25,
    "max_coverage_pct": 60,
    "max_far": 2.0,
    "max_height_ft": 35,
    "max_units": 4,
    "parking_min_per_unit": 1.0,
}

LOT = LotFacts(lot_sqft=6000, frontage_ft=60, lot_width_ft=60)


def rules(
    verdict: RuleVerdict = RuleVerdict.trusted,
    exempted: tuple[str, ...] = (),
    **overrides,
) -> ZoneResolution:
    values = {**CLEAR, **overrides}
    return ZoneResolution(
        jurisdiction=WHERE,
        zone="R5",
        verdict=verdict,
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


#: What this design's own parking asks of the lot, behind the building. The
#: screen charges the part of it a rear setback does not already provide, and
#: `CLEAR` states no rear setback, so the whole court is charged here.
COURT_FT = DESIGN.parking.court_depth_ft
#: And across it, broadside: the building with its lane beside it (56 + 12)
#: or the court at the design's floor -- four stalls, 36 ft since version 2
#: -- whichever is wider. `CLEAR` asks one stall per home, the floor, and
#: states no stall width, driveway or cap, so this is the design's own
#: figure. A synthetic fit has to say it was searched this wide, or the
#: screen -- rightly -- will not take its depth as evidence.
ACROSS_FT = max(56.0 + DESIGN.parking.lane_width_ft, DESIGN.court_width_ft)


def fit(*, over_ft: float = 4.0, depth_ft: float = 36.0, across_ft: float | None = ACROSS_FT) -> Fit:
    """A synthetic fit, stated as room to spare rather than as a raw depth.

    ``over_ft`` is feet of envelope beyond everything the pod needs -- itself
    *and* its parking court. Negative is a shortfall of that many feet, which
    is how every failing-fit test here says what it means. Writing these as
    absolute depths hid the arithmetic and made them silently wrong the day the
    court started being charged.
    """
    best_depth_ft = depth_ft + COURT_FT + over_ft
    return Fit(
        fits=best_depth_ft >= depth_ft,
        width_ft=56.0,
        depth_ft=depth_ft,
        best_depth_ft=best_depth_ft,
        slack_ft=best_depth_ft - depth_ft,
        across_ft=across_ft,
    )


def run(rule_set=None, lot=LOT, f=None, relief=None):
    return screen(
        rule_set or rules(), lot, DESIGN, f or fit(), policy=POLICY, relief=relief
    )


# --- the happy path ---------------------------------------------------


def test_a_clean_lot_under_verified_rules_is_green() -> None:
    result = run()

    assert result.triage is Triage.green
    assert result.reasons == ()
    assert result.binding == ()


def test_green_means_no_application_at_all() -> None:
    result = run()

    assert result.ask is Tier.as_of_right
    assert result.needs_ask is False
    assert result.relief == ()


def test_every_check_reports_its_margin_even_when_it_passes() -> None:
    assert all(c.verdict is Verdict.passes for c in run().checks)


# --- an unverified rule may not delete a lot --------------------------


def test_unverified_rules_are_unknown_not_a_verdict() -> None:
    result = run(rules(RuleVerdict.unverified))

    assert result.triage is Triage.unknown
    assert result.reasons == ("RULE_UNVERIFIED",)


def test_unverified_rules_cannot_produce_a_red() -> None:
    # The single most important rule in this module. A draft number that is
    # simply wrong would otherwise erase real acquisition targets silently,
    # and nobody would ever learn the lots existed.
    result = run(rules(RuleVerdict.unverified, min_lot_sqft=99_000), relief=NO_RELIEF)

    assert result.triage is Triage.unknown
    assert any(c.verdict is Verdict.fails for c in result.checks), "the miss is still recorded"


def test_an_unencoded_zone_is_unknown_with_its_reason() -> None:
    result = run(rules(RuleVerdict.zone_not_encoded))

    assert result.triage is Triage.unknown
    assert result.reasons == ("ZONE_NOT_ENCODED",)


def test_an_unencoded_jurisdiction_is_unknown() -> None:
    result = run(rules(RuleVerdict.jurisdiction_not_encoded))

    assert result.triage is Triage.unknown
    assert result.reasons == ("JURISDICTION_NOT_ENCODED",)


# --- the use gate -----------------------------------------------------


def test_a_zone_that_forbids_the_use_is_red() -> None:
    # Categorical, not a margin: no amount of slack makes a prohibited use
    # permitted. And unlike a dimensional standard, silence about a
    # conditional-use path means there is none — codes enumerate them.
    result = run(rules(quadplex_allowed=False))

    assert result.triage is Triage.red
    assert result.reasons == (USE_PROHIBITED,)
    assert result.ask is Tier.unavailable


def test_a_conditional_use_path_turns_a_prohibition_yellow() -> None:
    # Where the code does list the use as conditional, the zone is not a wall.
    allows_cup = ReliefPolicy(
        {
            WHERE: {
                USE: [
                    ReliefPath(
                        "conditional_use",
                        Tier.discretionary,
                        cite="PCC 33.815",
                        confirmed=True,
                    )
                ]
            }
        }
    )
    result = run(rules(quadplex_allowed=False), relief=allows_cup)

    assert result.triage is Triage.yellow
    assert result.ask is Tier.discretionary
    assert USE_PROHIBITED in result.reasons


def test_a_prohibition_nobody_verified_is_still_only_unknown() -> None:
    result = run(rules(RuleVerdict.unverified, quadplex_allowed=False))

    assert result.triage is Triage.unknown


def test_an_unencoded_use_permission_blocks_green() -> None:
    # Silence about whether fourplexes are allowed is not permission.
    result = run(rules(quadplex_allowed=None))

    assert result.triage is Triage.unknown
    assert USE_NOT_ENCODED in result.reasons


# --- failing a verified standard --------------------------------------


def test_a_miss_the_code_can_waive_is_yellow_not_red() -> None:
    # The correction this module exists for. A lot short of the minimum area
    # has a path — an adjustment, a variance — and burying it in RED deletes
    # exactly the deal the screen is supposed to find.
    result = run(rules(min_lot_sqft=8000))

    assert result.triage is Triage.yellow
    assert result.head == "min_lot_area_sqft"
    assert result.dominant == "min_lot_area_sqft"


def test_a_miss_with_no_procedure_at_all_is_red() -> None:
    result = run(rules(min_lot_sqft=8000), relief=NO_RELIEF)

    assert result.triage is Triage.red
    assert result.ask is Tier.unavailable


def test_an_unread_adjustment_chapter_is_assumed_to_exist_and_says_so() -> None:
    # A false red silently deletes an acquisition target; a false yellow costs
    # one review. So the default assumes relief exists — and flags the claim.
    result = run(rules(min_lot_sqft=8000))

    assert result.triage is Triage.yellow
    assert RELIEF_UNCONFIRMED in result.reasons
    assert result.relief[0].confirmed is False


def test_a_read_chapter_drops_the_unconfirmed_flag() -> None:
    # 300 sqft short of 6,300 is inside the adjustment chapter's 10%, so the
    # cheapest path that carries the miss is the staff-level one.
    result = run(rules(min_lot_sqft=6300), relief=READ)

    assert RELIEF_UNCONFIRMED not in result.reasons
    assert result.relief[0].cite == "PCC 33.805.040"


def test_the_size_of_the_miss_picks_the_tier() -> None:
    # Portland's adjustment carries 10%; past that it takes a hearing. Same
    # colour either way, but not the same project.
    small = run(rules(min_lot_sqft=6300), relief=READ)  # 300 short of 6,300 — 4.8%
    large = run(rules(min_lot_sqft=9000), relief=READ)  # 3,000 short — 33%

    assert small.ask is Tier.administrative
    assert large.ask is Tier.discretionary
    assert small.triage is large.triage is Triage.yellow


def test_the_hardest_ask_governs_the_configuration() -> None:
    # One hearing makes it a hearing project however many staff-level items
    # sit beside it.
    result = run(rules(min_lot_sqft=9000, min_frontage_ft=62), relief=READ)

    assert result.ask is Tier.discretionary


def test_posture_never_changes_a_colour() -> None:
    # Whether this team will file for a variance is a buy-list question. A lot
    # does not become illegal because we are in a hurry.
    cautious = ReliefPolicy(READ.paths, posture=Tier.as_of_right)
    result = run(rules(min_lot_sqft=9000), relief=cautious)

    assert result.triage is Triage.yellow
    assert cautious.acceptable(result.ask) is False


def test_a_pod_that_swallows_the_lot_is_charged_to_coverage() -> None:
    # A 2,016 sqft footprint on a 2,000 sqft lot fails several standards at
    # once. Lot area is short by a third; coverage is over by two thirds. The
    # ledger names the one that would still be fatal after the others were
    # fixed.
    result = run(lot=LotFacts(lot_sqft=2000, frontage_ft=60, lot_width_ft=60))

    assert result.dominant == "coverage_pct"


def test_the_tightest_constraint_leads() -> None:
    # Short on frontage by 5 ft and on lot width by 15. The frontage line is
    # the one worth arguing about.
    result = run(
        rules(min_frontage_ft=50, min_lot_width_ft=60),
        lot=LotFacts(lot_sqft=6000, frontage_ft=45, lot_width_ft=45),
    )

    assert result.head == "min_frontage_ft"
    assert [c.check for c in result.binding] == ["min_frontage_ft", "min_lot_width_ft"]
    # Proportionally the width is the worse problem, so that is what the lot is
    # charged to even though frontage is the nearer miss.
    assert result.dominant == "min_lot_width_ft"


def test_a_pod_too_big_for_the_envelope_still_reports_its_shortfall() -> None:
    result = run(f=fit(over_ft=-6.0))

    assert result.head == "fit_ft"
    assert result.fit_slack_ft == pytest.approx(-6.0)
    assert result.triage is Triage.yellow


def test_a_fit_inside_its_tolerance_either_way_is_green_and_flagged_tight() -> None:
    # One raster cell of shortfall is our instrument, not the lot, and the
    # county's lot lines are coarser still. Steph, 2026-09-25: "plus or minus
    # 6 in it goes into the green category. Every acquisition is going to
    # have a survey anyways. However, some sort of flag to be brought to the
    # human's attention" -- so a fit within the tolerance EITHER WAY is
    # green, and says it is tight. The edge counts: -0.5 and +0.5 are in.
    for over in (-0.5, -0.3, 0.0, 0.3, 0.5):
        result = run(f=fit(over_ft=over))
        assert result.triage is Triage.green, over
        assert result.tight_fit is True, over
        assert result.reasons == (), over
    # The miss is still recorded as the tightest check, not hidden.
    assert run(f=fit(over_ft=-0.3)).head == "fit_ft"
    # Past the tolerance on the pass side: green, not tight.
    clear = run(f=fit(over_ft=1.0))
    assert clear.triage is Triage.green and clear.tight_fit is False
    # Past it on the miss side: a definite miss, never green, not tight.
    short = run(f=fit(over_ft=-0.6))
    assert short.triage is not Triage.green and short.tight_fit is False


def test_tolerance_on_any_other_check_never_manufactures_a_green() -> None:
    # The fit's exception is the fit's alone: a stall count a quarter short
    # (parking_stalls tolerance 0.25) still holds the lot out of GREEN.
    policy = SlackPolicy(tolerance={"fit_ft": 0.5, "coverage_pct": 1.0})
    result = screen(
        rules(max_coverage_pct=33.0), LOT, DESIGN, fit(), policy=policy, relief=None
    )
    coverage = next(c for c in result.checks if c.check == "coverage_pct")
    assert coverage.verdict is Verdict.tolerated
    assert result.triage is Triage.unknown
    assert result.tight_fit is False


def test_a_policy_with_no_fit_tolerance_flags_nothing_tight() -> None:
    result = screen(rules(), LOT, DESIGN, fit(over_ft=0.0), policy=SlackPolicy(), relief=None)
    assert result.triage is Triage.green and result.tight_fit is False


def test_a_definite_miss_outranks_a_fuzzy_one() -> None:
    # A lot that definitely fails one standard and might fail another is not
    # unanswerable — it needs an application. The doubt can only add asks.
    result = run(rules(min_lot_sqft=8000), f=fit(over_ft=-0.3))

    assert result.triage is Triage.yellow


# --- the ground the cars need, and which way the pod stood ------------


def test_a_lot_deep_enough_for_the_building_and_not_its_parking_fails() -> None:
    # The pod parks six cars in a rear court. An envelope that holds the
    # building and nothing behind it holds no pod at all, and until 2026-09-08
    # this screen called that lot GREEN.
    result = run(f=fit(over_ft=-COURT_FT + 4.0), relief=NO_RELIEF)

    assert result.head == "fit_ft"
    assert result.triage is Triage.red


def test_the_standoff_off_the_rear_wall_is_inside_the_courts_charge() -> None:
    # The county drawing keeps 5 ft between the rear wall and the first
    # stall, and until 2026-09-17 this screen seated the stall on the wall:
    # an envelope with room for the stall and the aisle and not the standoff
    # holds no court we would draw. Short by the standoff is short.
    gap = DESIGN.parking.building_gap_ft
    asked = next(c for c in run(f=fit(), relief=NO_RELIEF).checks if c.check == "fit_ft")

    assert gap == 5.0
    assert asked.threshold == pytest.approx(36.0 + COURT_FT)
    assert COURT_FT == gap + DESIGN.parking.stall_depth_ft + DESIGN.parking.aisle_ft
    assert run(f=fit(over_ft=-gap + 1.0), relief=NO_RELIEF).triage is Triage.red
    # A city's wider buffer deepens the charge the way its wider aisle does;
    # a narrower one (Fairview's 4) does not shallow it.
    assert run(rules(parking_building_buffer_ft=8), f=fit(over_ft=0.0), relief=NO_RELIEF).triage is Triage.red
    assert run(rules(parking_building_buffer_ft=8), f=fit(over_ft=3.0)).triage is Triage.green
    assert run(rules(parking_building_buffer_ft=4), f=fit(over_ft=0.0)).triage is Triage.green


def test_a_required_rear_yard_is_ground_the_court_can_park_on() -> None:
    # The envelope already has the rear setback taken off it, and every Oregon
    # code read for this lets you park in a rear yard. So the setback and the
    # court overlap rather than stack, and a zone asking for 20 ft of rear yard
    # charges only the 20-odd feet of court that reaches past it.
    tight = fit(over_ft=-20.0)

    assert run(f=tight, relief=NO_RELIEF).triage is Triage.red
    assert run(rules(setback_rear_ft=25), f=tight).triage is Triage.green


def test_a_rear_yard_deeper_than_the_court_is_not_a_credit() -> None:
    # The overlap can cancel the court and it can never go further: a 60 ft
    # rear yard does not hand the building back depth it never had.
    deep = rules(setback_rear_ft=60)
    fits = next(c for c in run(deep, f=fit(over_ft=-COURT_FT)).checks if c.check == "fit_ft")

    assert fits.threshold == pytest.approx(36.0)


def test_the_court_is_charged_against_the_strip_the_envelope_really_lost() -> None:
    # quadfit's s5 cuts ITS zone table's rear setback off the envelope; the
    # corpus can resolve another number for the same lot. A Portland CM2 lot
    # with a commercial neighbour: the rules say 0 ft, the envelope was cut
    # at 10 -- that strip is there whatever the rules say, so the charge is
    # the one a 10 ft rear yard gets, not the whole court. Charging the whole
    # court took 10 ft off 14,782 rows the day the neighbour was read
    # (2026-09-22) and turned every gain the reading made into a loss.
    cut_at_ten = LotFacts(lot_sqft=6000, frontage_ft=60, lot_width_ft=60, envelope_rear_ft=10.0)
    tight = fit(over_ft=-8.0)

    assert run(rules(setback_rear_ft=0), f=tight, relief=NO_RELIEF).triage is Triage.red
    assert run(rules(setback_rear_ft=0), lot=cut_at_ten, f=tight).triage is Triage.green
    assert run(rules(setback_rear_ft=10), lot=cut_at_ten, f=tight).triage is Triage.green
    # The other way round: the rules tighten past the cut (Oregon City's 20
    # ft against a house, on an envelope cut at 0). The wall has to stand 20
    # ft off a line the envelope runs to, and the court behind it -- so the
    # charge is the larger of the court and the yard, less nothing.
    cut_at_zero = LotFacts(lot_sqft=6000, frontage_ft=60, lot_width_ft=60, envelope_rear_ft=0.0)

    def asked(rule_set, lot):
        return next(c for c in run(rule_set, lot=lot, f=fit()).checks if c.check == "fit_ft").threshold

    assert asked(rules(setback_rear_ft=20), cut_at_zero) == pytest.approx(36.0 + COURT_FT)
    assert asked(rules(setback_rear_ft=60), cut_at_zero) == pytest.approx(36.0 + 60.0)
    # A lot that says nothing about its cut was cut with the rules' number,
    # which is the old arithmetic exactly.
    assert asked(rules(setback_rear_ft=20), LOT) == pytest.approx(36.0 + COURT_FT - 20.0)
    assert asked(rules(setback_rear_ft=20), LotFacts(lot_sqft=6000, frontage_ft=60, lot_width_ft=60, envelope_rear_ft=20.0)) == pytest.approx(36.0 + COURT_FT - 20.0)


#: A lot with the alley along its rear line, 14 ft wide as s4 measured it
#: (the typical Portland alley), and the two sentences that make the alley
#: the court's way in and its aisle: Portland's C.3 and the 20 ft back-out
#: room of 33.266.130.F.1.b(2) (Steph's ruling, 2026-09-13).
ALLEY_LOT = LotFacts(
    lot_sqft=6000, frontage_ft=60, lot_width_ft=60, alley_at_rear=True, alley_width_ft=14.0
)
ALLEY_FED = {"parking_alley_access_required": True, "parking_alley_backout_ft": 20}


def test_an_alley_fed_court_backs_out_into_the_alley() -> None:
    # FOLLOWUPS 4(b): the row of stalls along the alley backs straight out
    # into it, so the court is the standoff, a stall, and whatever the
    # alley's width leaves short of the back-out room -- 5 + 18 + 6 on a 14
    # ft alley, where the street-fed court is 5 + 18 + 24. No lane down the
    # building's flank either: the court is reached from behind.
    gap, stall = DESIGN.parking.building_gap_ft, DESIGN.parking.stall_depth_ft
    at_building = fit(across_ft=56.0)

    def fit_check(rule_set, lot):
        got = run(rule_set, lot=lot, f=at_building)
        return got, next(c for c in got.checks if c.check == "fit_ft")

    got, asked = fit_check(rules(**ALLEY_FED), ALLEY_LOT)
    assert asked.threshold == pytest.approx(36.0 + gap + stall + 6.0)
    assert "fit_across_ft" not in got.unchecked

    # An alley with no width on record counts for nothing: the whole 20 ft
    # is paved on the lot. Still shallower than the court's own 24 ft aisle.
    unmeasured = replace(ALLEY_LOT, alley_width_ft=None)
    assert fit_check(rules(**ALLEY_FED), unmeasured)[1].threshold == pytest.approx(
        36.0 + gap + stall + 20.0
    )
    # Back-out room deeper than the court's own aisle is never taken: the
    # court keeps its aisle, as s6s keeps it where the alley buys nothing.
    deep = rules(parking_alley_access_required=True, parking_alley_backout_ft=40)
    assert fit_check(deep, unmeasured)[1].threshold == pytest.approx(36.0 + COURT_FT)
    # Access from the alley and no word that the alley is the aisle
    # (Wilsonville, West Linn): the whole court, and still no street lane.
    got, asked = fit_check(rules(parking_alley_access_required=True), ALLEY_LOT)
    assert asked.threshold == pytest.approx(36.0 + COURT_FT)
    assert "fit_across_ft" not in got.unchecked


def test_an_alley_the_code_does_not_route_to_changes_nothing() -> None:
    # The alley counts only where the code sends the driveway to it; a lot
    # with no alley at the rear is the street-fed court whatever the city
    # says; and on either, a search at the building's width alone is the
    # hole in the measurement it always was.
    at_building = fit(across_ft=56.0)
    for rule_set, lot in (
        (rules(parking_alley_backout_ft=20), ALLEY_LOT),
        (rules(**ALLEY_FED), LOT),
        (rules(**ALLEY_FED), replace(ALLEY_LOT, alley_at_rear=False)),
    ):
        got = run(rule_set, lot=lot, f=at_building)
        asked = next(c for c in got.checks if c.check == "fit_ft")
        assert asked.threshold == pytest.approx(36.0 + COURT_FT)
        assert "fit_across_ft" in got.unchecked


def test_an_alley_fed_lot_seats_its_stalls_without_a_lane_or_an_aisle() -> None:
    # 56 x 65: the building and a court of standoff, stall and 6 ft of
    # back-out paving, no wider than the building. Street-fed it seats
    # nothing -- it needs 83 deep and 68 across; fed from a 14 ft alley it
    # seats six, the most 56 ft holds at 9 ft a stall.
    fitter = Fitter(shapely.box(0, 0, 56, 65), (0.0,), res=1.0)
    alley = ALLEY_LOT.alley

    assert alley is not None and alley.width_ft == 14.0
    assert fit_for(fitter, DESIGN, rules()).stalls == 0
    assert fit_for(fitter, DESIGN, rules(**ALLEY_FED)).stalls == 0
    assert fit_for(fitter, DESIGN, rules(**ALLEY_FED), alley=alley).stalls == 6
    assert LOT.alley is None


#: The same alley along a SIDE lot line (s4's alley edge named side by
#: bearing). Steph, 2026-09-25: "Alleys along side yards is important."
SIDE_ALLEY_LOT = replace(ALLEY_LOT, alley_at_rear=False, alley_at_side=True)


def test_a_side_alley_feeds_the_court_without_a_street_lane() -> None:
    # The court spans the lot behind the building and its end meets the side
    # alley, so a code that sends the driveway to the alley asks no lane down
    # the building's flank -- a search at the building's own width is the
    # whole question, as it is for a rear alley.
    at_building = fit(across_ft=56.0)
    for rule_set in (rules(**ALLEY_FED), rules(parking_alley_access_required=True)):
        got = run(rule_set, lot=SIDE_ALLEY_LOT, f=at_building)
        assert "fit_across_ft" not in got.unchecked
        # The rear-alley back-out court is not a side alley's: the row
        # behind the building still needs its own aisle.
        asked = next(c for c in got.checks if c.check == "fit_ft")
        assert asked.threshold == pytest.approx(36.0 + COURT_FT)
    # A code that does not send the driveway to the alley keeps the lane.
    got = run(rules(parking_alley_backout_ft=20), lot=SIDE_ALLEY_LOT, f=at_building)
    assert "fit_across_ft" in got.unchecked


def test_a_side_alley_stands_the_stalls_in_a_column_that_backs_out_into_it() -> None:
    # 56 x 78: the building (36 deep broadside) and 42 ft behind it. The row
    # court needs 5 + 18 + 24 = 47 behind the building; street-fed it also
    # needs 68 across. Four stalls standing along a 14 ft side alley, nose
    # to the court's far side and backing out into the alley, need 5 + 4 x 9
    # = 41 deep and 18 + 6 across -- inside the building's 36 ft side.
    fitter = Fitter(shapely.box(0, 0, 56, 78), (0.0,), res=1.0)
    side = SIDE_ALLEY_LOT.alley
    assert side is not None and side.at_side and not side.at_rear

    assert fit_for(fitter, DESIGN, rules(**ALLEY_FED)).stalls == 0
    rear = fit_for(fitter, DESIGN, rules(**ALLEY_FED), alley=ALLEY_LOT.alley)
    assert rear.column is False
    got = fit_for(fitter, DESIGN, rules(**ALLEY_FED), alley=side)
    assert got.column is True
    assert got.stalls == 4, "a fifth stall is 9 ft deeper: 86 > 78"
    result = screen(rules(**ALLEY_FED), SIDE_ALLEY_LOT, DESIGN, got, policy=POLICY, relief=None)
    check = next(c for c in result.checks if c.check == "fit_ft")
    assert check.threshold == pytest.approx(36.0 + 5.0 + 36.0)
    assert check.slack == pytest.approx(1.0)
    assert "fit_across_ft" not in result.unchecked
    assert result.triage is Triage.green

    # No back-out room stated (Wilsonville, West Linn): no column, the row
    # court with its own aisle -- 83 deep, which 78 does not hold.
    plain = fit_for(fitter, DESIGN, rules(parking_alley_access_required=True), alley=side)
    assert plain.column is False and plain.stalls == 0
    # An alley with no width on record leaves 20 ft to pave; 18 + 20 = 38
    # is wider than the building's narrow side, so the column is not offered.
    unmeasured = replace(SIDE_ALLEY_LOT, alley_width_ft=None).alley
    assert fit_for(fitter, DESIGN, rules(**ALLEY_FED), alley=unmeasured).column is False


def test_a_pod_that_only_fits_end_on_is_measured_against_the_run_it_needed() -> None:
    # The flip searches the envelope at the pod's *depth* and needs its
    # *width*, so a Fit whose recorded depth_ft is the smaller dimension must
    # not be read as the requirement. 50 ft of found run against a 36 ft
    # dimension read as a comfortable pass on a lot with no 56 ft run anywhere.
    end_on = Fit(
        fits=False,
        width_ft=56.0,
        depth_ft=36.0,
        best_depth_ft=50.0,
        slack_ft=-6.0,
        orientation=Orientation.depth_facing,
        # End-on the building and its lane (48) are wider than the four-stall
        # court (36); searched at what the zone asks.
        across_ft=36.0 + DESIGN.parking.lane_width_ft,
    )

    assert end_on.required_ft == pytest.approx(56.0)
    assert run(f=end_on, relief=NO_RELIEF).triage is Triage.red


def test_the_slack_reported_is_the_one_the_check_used() -> None:
    # `Fit.slack_ft` knows nothing about parking or orientation. The number a
    # developer argues with has to be the number the verdict turned on.
    result = run(f=fit(over_ft=7.0))

    assert result.fit_slack_ft == pytest.approx(7.0)


# --- the court across the lot, and the lane that reaches it -----------------
#
# Until 2026-09-17 the fit searched the envelope for the building's own width
# and the screen took whatever depth it found. A row of stalls behind a 36 ft
# end of building, and a 12 ft lane beside a 56 ft front (68): the envelope
# has to hold THAT, and a search for the building alone on a lot too narrow
# for its cars reads as a fit. The paper lot and the county pipeline both
# charge it; these pin the screen doing the same, and refusing a fit that did
# not.
#
# How many stalls the row is charged at changed on 2026-09-18. Until then it
# was the design's target -- six, a 54 ft row wider than the pod's end -- and
# 4,977 of the county map's 20,125 greens, seating four or five, could never
# have been green here. Steph: "same as the county map. 4 is enough to sell."
# So the floor is charged (one per home, raised by the zone's legal minimum,
# cut by its cap), and how many more the lot seats is counted and reported
# beside the colour, in the county map's bands.


def test_a_fit_searched_at_the_building_alone_is_not_evidence() -> None:
    # A Fit built around the bare footprint never looked for the lane or the
    # court. The lot may well hold them -- nobody asked -- so this is a hole
    # in the measurement, reported as one, and never a RED.
    bare = fit(over_ft=10.0, across_ft=None)

    result = run(f=bare, relief=NO_RELIEF)

    assert result.triage is Triage.unknown
    assert COURT_WIDTH_UNMEASURED in result.reasons
    assert "fit_across_ft" in result.unchecked


def test_a_fit_searched_at_what_the_zone_asks_is_evidence() -> None:
    assert run(f=fit(over_ft=10.0, across_ft=ACROSS_FT)).triage is Triage.green
    # Searched wider than asked is still evidence: a run found at 80 ft
    # across is a run found at 68.
    assert run(f=fit(over_ft=10.0, across_ft=80.0)).triage is Triage.green


def test_a_city_that_widens_the_court_or_the_lane_stales_a_narrower_search() -> None:
    # Happy Valley's 20 ft two-way driveway makes the building and its lane 76
    # broadside; a fit searched at 68 measured a rectangle this zone does not
    # accept. Same for a stall width that makes the court the wider figure.
    wide_lane = rules(driveway_min_width_two_way_ft=20)
    assert run(wide_lane, f=fit(over_ft=10.0)).triage is Triage.unknown
    assert run(wide_lane, f=fit(over_ft=10.0, across_ft=76.0)).triage is Triage.green

    # Same for a legal minimum that makes the court the wider figure: two per
    # home is eight stalls, 72 ft, over the 68. A wider stall alone does not
    # -- four at 12 ft are 48, still inside the building and its lane.
    two_per_home = rules(parking_min_per_unit=2.0)
    assert COURT_WIDTH_UNMEASURED in run(two_per_home, f=fit(over_ft=10.0)).reasons
    assert run(rules(parking_stall_width_ft=12), f=fit(over_ft=10.0)).triage is Triage.green


def test_the_floor_is_charged_and_a_legal_minimum_above_it_widens_the_search() -> None:
    # End-on the building with its lane (48) is wider than the four-stall
    # court (36), so a fit searched at 48 end-on is enough at the floor --
    # where the six-stall target charged until 2026-09-18 would have needed
    # 54. Clackamas MR-1 asks 1.5 per home: that IS six, the row is 54 again,
    # and the same fit is stale there. A cap at one per home (Milwaukie)
    # changes nothing about the charge -- four is four.
    end_on = Fit(
        fits=True,
        width_ft=56.0,
        depth_ft=36.0,
        best_depth_ft=56.0 + COURT_FT + 4.0,
        slack_ft=COURT_FT + 4.0,
        orientation=Orientation.depth_facing,
        across_ft=48.0,
    )

    at_floor = run(rules(), f=end_on)
    assert at_floor.triage is Triage.green
    assert at_floor.stalls_charged == 4
    assert run(rules(parking_max_per_unit=1), f=end_on).triage is Triage.green
    raised = run(rules(parking_min_per_unit=1.5), f=end_on)
    assert raised.stalls_charged == 6
    assert COURT_WIDTH_UNMEASURED in raised.reasons


def test_fit_for_searches_the_envelope_at_what_the_zone_asks() -> None:
    # A 45 x 120 envelope holds the 36 ft end of the building with room to
    # spare and holds neither the 48 ft of building-and-lane end-on nor the
    # 68 broadside. The bare search says the pod fits; the one the screen
    # asks for says it does not, and the screen then has a real miss to
    # score rather than a hole.
    fitter = Fitter(shapely.box(0, 0, 45, 120), (0.0,), res=1.0)

    bare = fitter.fit(56, 36)
    asked = fit_for(fitter, DESIGN, rules())

    assert bare.fits and bare.orientation is Orientation.depth_facing
    assert not asked.fits
    assert asked.best_depth_ft == 0.0, "nothing that wide anywhere"
    assert asked.across_ft >= 48.0
    assert asked.stalls == 0, "not even the floor's row holds"
    result = screen(rules(), LOT, DESIGN, asked, policy=POLICY, relief=NO_RELIEF)
    assert result.triage is Triage.red
    assert result.head == "fit_ft"
    assert COURT_WIDTH_UNMEASURED not in result.reasons
    assert (result.stalls_charged, result.stalls_seated, result.parking_band) == (4, 0, None)


def test_fit_for_reads_the_citys_figures_not_only_the_designs() -> None:
    # Where the law asks 1.5 per home the row is six stalls: 55 ft across
    # holds it end-on at the design's 9 ft (54) and not at Gladstone's 9.5
    # (57). The zone's numbers -- the minimum and the stall -- travel into
    # the search, which is the whole reason `fit_for` exists.
    fitter = Fitter(shapely.box(0, 0, 55, 120), (0.0,), res=1.0)

    assert fit_for(fitter, DESIGN, rules(parking_min_per_unit=1.5)).fits
    wider = fit_for(fitter, DESIGN, rules(parking_min_per_unit=1.5, parking_stall_width_ft=9.5))
    assert not wider.fits
    assert wider.best_depth_ft == 0.0, "57 end-on and 68 broadside; 55 holds neither"


def test_a_design_that_parks_on_the_street_is_searched_at_its_footprint() -> None:
    street = DESIGN.model_copy(
        update={"parking": DESIGN.parking.model_copy(update={"stalls_per_unit": StallBands.one(0)})}
    )
    fitter = Fitter(shapely.box(0, 0, 60, 120), (0.0,), res=1.0)

    got = fit_for(fitter, street, rules(parking_min_per_unit=0))

    assert got.fits
    assert got.across_ft == pytest.approx(56.0)
    assert got.orientation is Orientation.width_facing
    assert got.stalls is None, "no court to count"
    result = screen(rules(parking_min_per_unit=0), LOT, street, got, policy=POLICY)
    assert (result.stalls_charged, result.stalls_seated, result.parking_band) == (0, None, None)


# --- the seat count beside the colour ---------------------------------------
#
# The colour charges the floor. How many more the lot seats -- floor to
# preferred, four to eight on the pod -- is counted by `seats`, carried on the
# fit, and reported by the screen in the county map's bands: minimum (4-5),
# target (6-7), preferred (8). A row no wider than the building and its lane
# is free; each wider one is one yes/no over the grids.


def counted(width_ft: float, depth_ft: float, rule_set=None, **over):
    """Fit and screen the pod on a box this wide and this deep."""
    fitter = Fitter(shapely.box(0, 0, width_ft, depth_ft), (0.0,), res=1.0)
    zone = rule_set or rules(**over)
    got = fit_for(fitter, DESIGN, zone)
    return screen(zone, LOT, DESIGN, got, policy=POLICY, relief=NO_RELIEF)


def test_the_seat_count_walks_from_the_floor_to_the_preferred() -> None:
    # Broadside the building and its lane are 68 ft, which seats seven at 9
    # ft for free; the eighth is a 72 ft row and a question the envelope has
    # to answer. End-on (48) the sixth stall is the first that costs width.
    seven = counted(68, 120)
    eight = counted(72, 120)
    five = counted(50, 120)

    assert (seven.triage, seven.stalls_charged, seven.stalls_seated, seven.parking_band) == (
        Triage.green, 4, 7, "target"
    )
    assert (eight.stalls_seated, eight.parking_band) == (8, "preferred")
    # 50 ft holds the pod end-on with its lane (48) and a fifth stall (45),
    # not a sixth (54); broadside (68) it holds nothing.
    assert (five.triage, five.stalls_seated, five.parking_band) == (Triage.green, 5, "minimum")


def test_the_seats_are_counted_at_the_depth_the_court_needs() -> None:
    # A row is only a seat if the court it sits in fits behind the building:
    # broadside the pod and its court are 83 ft deep, end-on 103. A 72 x 90
    # box seats eight broadside and nothing end-on; at 80 deep it seats
    # nothing at all, and the fit fails with it.
    assert counted(72, 90).stalls_seated == 8
    short = counted(72, 80)
    assert short.triage is Triage.red and short.head == "fit_ft"
    assert (short.stalls_seated, short.parking_band) == (0, None)
    # A required rear yard is ground the court parks on, for the count as
    # for the colour: 20 ft of it leaves 27 of court to find, so 70 deep is
    # enough where it was not.
    with_yard = counted(72, 70, setback_rear_ft=20)
    assert with_yard.triage is Triage.green
    assert with_yard.stalls_seated == 8
    assert counted(72, 70).stalls_seated == 0


def test_the_seat_count_parks_in_the_strip_the_envelope_lost_too() -> None:
    # 72 x 70 seats nothing with the whole court charged and eight when 20
    # ft of rear yard is ground the court parks on -- and the same eight
    # when that 20 ft is what the envelope was cut with rather than what the
    # rules resolve, since the strip is there either way.
    fitter = Fitter(shapely.box(0, 0, 72, 70), (0.0,), res=1.0)

    assert fit_for(fitter, DESIGN, rules()).stalls == 0
    assert fit_for(fitter, DESIGN, rules(), carved_rear_ft=20.0).stalls == 8
    assert fit_for(fitter, DESIGN, rules(setback_rear_ft=20), carved_rear_ft=20.0).stalls == 8
    assert fit_for(fitter, DESIGN, rules(setback_rear_ft=20), carved_rear_ft=0.0).stalls == 0


def test_a_cap_cuts_the_count_and_never_the_colour() -> None:
    # Milwaukie caps this building at one stall per home. A lot that would
    # seat eight is still green -- four is enough to sell -- and the count
    # stops where the code does, so the band is the floor's. Portland's 1.35
    # is five cells, and the same band.
    milwaukie = counted(72, 120, parking_max_per_unit=1)
    portland = counted(72, 120, parking_max_per_unit=1.35)

    assert milwaukie.triage is Triage.green
    assert (milwaukie.stalls_charged, milwaukie.stalls_seated, milwaukie.parking_band) == (4, 4, "minimum")
    assert (portland.stalls_seated, portland.parking_band) == (5, "minimum")


def test_a_cap_below_the_floor_refuses_the_lot_the_way_the_county_map_does() -> None:
    # Portland's EX permits half a stall per home: two on a fourplex. The
    # charge is cut to two, and a court of two is not this product, so the
    # lot fails on the cap -- quadfit's too_few_stalls -- rather than
    # screening green on a row the code will not permit. Portland states no
    # minimum, so this cannot ride on the stall-count check; it is its own.
    # The count beside the colour is the two, and it has no band.
    ex = counted(72, 120, parking_min_per_unit=None, parking_max_per_unit=0.5)

    assert ex.triage is Triage.red and ex.head == "parking_cap"
    assert (ex.stalls_charged, ex.stalls_seated, ex.parking_band) == (2, 2, None)
    cap = next(c for c in ex.checks if c.check == "parking_cap")
    assert (cap.observed, cap.threshold) == (2.0, 4.0)
    # A cap at the floor is not below it; and a design that parks on the
    # street has no floor a cap can undercut.
    assert counted(72, 120, parking_max_per_unit=1).triage is Triage.green
    street = DESIGN.model_copy(
        update={"parking": DESIGN.parking.model_copy(update={"stalls_per_unit": StallBands.one(0)})}
    )
    fitter = Fitter(shapely.box(0, 0, 60, 120), (0.0,), res=1.0)
    zone = rules(parking_min_per_unit=0, parking_max_per_unit=0.5)
    on_street = screen(zone, LOT, street, fit_for(fitter, street, zone), policy=POLICY, relief=NO_RELIEF)
    assert on_street.triage is Triage.green
    assert "parking_cap" not in {c.check for c in on_street.checks}
    # Where the adjustment chapter has been read, an application, not a wall.
    fitter = Fitter(shapely.box(0, 0, 72, 120), (0.0,), res=1.0)
    zone = rules(parking_min_per_unit=None, parking_max_per_unit=0.5)
    asked = screen(zone, LOT, DESIGN, fit_for(fitter, DESIGN, zone), policy=POLICY, relief=READ)
    assert asked.triage is Triage.yellow
    assert asked.ask is Tier.discretionary


def test_a_legal_minimum_raises_the_floor_the_count_starts_from() -> None:
    # Clackamas MR-1 asks 1.5 per home: six is the charge, so a 50 ft lot
    # that seats five at the design's floor is short here, and a 72 ft lot
    # counts from six to eight.
    short = counted(50, 120, parking_min_per_unit=1.5)
    assert short.triage is Triage.red and short.head == "fit_ft"
    assert (short.stalls_charged, short.stalls_seated) == (6, 0)

    wide = counted(72, 120, parking_min_per_unit=1.5)
    assert (wide.stalls_charged, wide.stalls_seated, wide.parking_band) == (6, 8, "preferred")


def test_a_code_that_fixes_the_buildings_face_counts_one_orientation() -> None:
    # The five a 50 ft lot seats are end-on. Where the code makes the pod
    # face the street it cannot turn, and broadside 50 holds no row at all.
    fitter = Fitter(shapely.box(0, 0, 50, 120), (0.0,), res=1.0)

    assert seats(fitter, DESIGN, rules()) == 5
    assert seats(fitter, DESIGN, rules(), axis_required=True) == 0
    assert fit_for(fitter, DESIGN, rules(orientation_constraint="axis_required")).stalls == 0

# --- a ceiling counted in storeys instead of feet ---------------------


def test_a_storey_limit_is_checked_like_any_other_ceiling() -> None:
    """Gresham caps SC at ten storeys and prints no height in feet anywhere.

    A limit stated in the other unit is still a limit, so it runs as its own
    check rather than being converted -- GDC 3.0100 defines a story by the
    floor surfaces bounding it and never says how tall one is, so there is no
    conversion that is not an invention.
    """
    result = run(rules(max_height_stories=10))

    assert result.triage is Triage.green
    counted = [c for c in result.checks if c.check == "stories"]
    assert [c.verdict for c in counted] == [Verdict.passes]
    assert counted[0].threshold == 10
    assert counted[0].observed == 2


def test_a_pod_over_the_storey_count_fails_on_it() -> None:
    """And it can bind on its own, with the feet still clearing.

    A two-storey pod is 26 feet, so a one-storey district refuses it while
    every height in feet this corpus holds would let it through.
    """
    result = run(rules(max_height_stories=1))

    assert result.triage is not Triage.green
    failed = {c.check for c in result.checks if c.verdict is not Verdict.passes}
    assert failed == {"stories"}


def test_both_ceilings_run_where_a_zone_states_both() -> None:
    """Two standards, not two spellings of one -- each has to be cleared."""
    result = run(rules(max_height_ft=20, max_height_stories=10))

    assert result.triage is not Triage.green
    failed = {c.check for c in result.checks if c.verdict is not Verdict.passes}
    assert failed == {"height_ft"}


# --- standards nobody encoded ----------------------------------------


def test_a_missing_required_standard_blocks_green() -> None:
    # Skipping a check the code plainly imposes would manufacture GREENs.
    result = run(rules(parking_min_per_unit=None))

    assert result.triage is Triage.unknown
    assert STANDARD_NOT_ENCODED in result.reasons
    assert "parking_stalls" in result.unchecked


def test_a_standard_the_code_exempts_is_an_answer_not_a_gap() -> None:
    """``exempt: true`` is an encoding: the code was read and states no such
    standard. Portland has no parking minimum, and the first county run
    (2026-09-17) found every Portland lot UNKNOWN / STANDARD_NOT_ENCODED on
    that silence -- uncertifiable however many numbers were signed, on a
    standard nobody could ever encode because it does not exist.
    """
    result = run(rules(parking_min_per_unit=None, exempted=("parking_min_per_unit",)))

    assert result.triage is Triage.green
    assert STANDARD_NOT_ENCODED not in result.reasons
    # Still reported as unchecked: nothing was measured, and the ledger of
    # what the screen did not compare is not the ledger of what is missing.
    assert "parking_stalls" in result.unchecked


def test_a_height_stated_in_storeys_alone_is_not_a_missing_height() -> None:
    """The other silence that is an answer: Gresham SC caps at ten storeys and
    prints no height in feet. The resolver counts that as answered; the
    screen has to agree or the zone can never be certified.
    """
    result = run(rules(max_height_ft=None, max_height_stories=10))

    assert result.triage is Triage.green
    assert STANDARD_NOT_ENCODED not in result.reasons
    assert "height_ft" in result.unchecked


def test_a_gap_rides_along_on_a_yellow_instead_of_hiding_it() -> None:
    # The encoding backlog is counted from reasons, not from the colour, so a
    # lot can need an adjustment AND still be missing a standard.
    result = run(rules(min_lot_sqft=8000, parking_min_per_unit=None))

    assert result.triage is Triage.yellow
    assert STANDARD_NOT_ENCODED in result.reasons


def test_a_standard_the_code_simply_does_not_impose_is_not_a_gap() -> None:
    # Plenty of zones have no FAR at all. Treating that silence as a gap would
    # bury the real gaps under thousands of false ones.
    result = run(rules(max_far=None))

    assert result.triage is Triage.green
    assert "far" in result.unchecked


def test_an_unmeasurable_lot_width_does_not_block_green() -> None:
    result = run(lot=LotFacts(lot_sqft=6000, frontage_ft=60))

    assert result.triage is Triage.green
    assert "min_lot_width_ft" in result.unchecked


# --- geometry confidence ----------------------------------------------


def test_a_lot_with_no_street_found_is_unknown_not_dropped() -> None:
    result = run(
        lot=LotFacts(lot_sqft=6000, frontage_ft=0, lot_width_ft=60, geometry=GeometryTier.landlocked)
    )

    assert result.triage is Triage.unknown
    assert NO_FRONTAGE in result.reasons
    # And the frontage standard is not scored against a number nobody measured.
    assert "min_frontage_ft" in result.unchecked


def test_an_unreadable_shape_is_unknown() -> None:
    result = run(
        lot=LotFacts(lot_sqft=6000, frontage_ft=60, lot_width_ft=60, geometry=GeometryTier.irregular)
    )

    assert result.triage is Triage.unknown
    assert GEOMETRY_UNREADABLE in result.reasons


def test_a_corner_lot_is_still_screenable() -> None:
    # The stricter setbacks were already taken when the envelope was cut; the
    # corner itself is not a reason for doubt.
    result = run(
        lot=LotFacts(lot_sqft=6000, frontage_ft=60, lot_width_ft=60, geometry=GeometryTier.corner)
    )

    assert result.triage is Triage.green


def test_a_lot_with_no_area_cannot_be_screened() -> None:
    result = run(lot=LotFacts(lot_sqft=0))

    assert result.triage is Triage.unknown
    assert result.reasons == (GEOMETRY_UNREADABLE,)


# --- the trickier standards -------------------------------------------


def test_a_tiered_coverage_table_is_read_by_tier() -> None:
    # Portland's Table 110-5 is tiered, not flat. On a 6,000 sqft lot the
    # second tier allows 2,500 sqft; the pod's 2,016 clears it.
    curve = [[0, 1500, 20.0], [5000, 2500, 10.0]]
    result = run(rules(max_coverage_pct=None, coverage_curve=curve))

    coverage = next(c for c in result.checks if c.check == "coverage_pct")
    assert coverage.threshold == pytest.approx(2600 / 6000 * 100)
    assert result.triage is Triage.green


def test_a_tiered_table_can_still_fail() -> None:
    curve = [[0, 800, 5.0]]
    result = run(rules(max_coverage_pct=None, coverage_curve=curve), relief=NO_RELIEF)

    assert result.triage is Triage.red
    assert result.head == "coverage_pct"


def test_minimum_density_only_bites_above_its_trigger() -> None:
    # A four-unit pod on a lot that requires six is out — but only once the lot
    # is big enough for the requirement to apply.
    small = run(rules(min_density_trigger_lot_sqft=10_000, min_units_at_trigger=6))
    big = run(
        rules(min_density_trigger_lot_sqft=5_000, min_units_at_trigger=6),
        lot=LotFacts(lot_sqft=6000, frontage_ft=60, lot_width_ft=60),
        relief=NO_RELIEF,
    )

    assert small.triage is Triage.green
    assert big.triage is Triage.red
    assert big.head == "min_units"


def test_parking_charges_the_floor_raised_by_the_law_not_the_target() -> None:
    # The pod is built with one stall per home and sold with more. A code
    # asking one is met by the floor. A code asking two raises the charge to
    # eight -- a 72 ft row, wider than the 68 the synthetic fit was searched
    # at -- and the room for that row is the fit's question, never a count
    # the design "provides" or falls short of.
    ok = run(rules(parking_min_per_unit=1.0))
    raised = run(rules(parking_min_per_unit=2.0), relief=NO_RELIEF)
    wide = run(rules(parking_min_per_unit=2.0), f=fit(over_ft=4.0, across_ft=72.0))

    assert ok.triage is Triage.green
    assert ok.stalls_charged == 4
    assert raised.triage is Triage.unknown
    assert COURT_WIDTH_UNMEASURED in raised.reasons
    assert raised.stalls_charged == 8
    assert wide.triage is Triage.green
    stalls = next(c for c in wide.checks if c.check == "parking_stalls")
    assert (stalls.observed, stalls.threshold, stalls.verdict) == (8.0, 8.0, Verdict.passes)


def test_only_a_cap_below_the_minimum_fails_the_stall_count() -> None:
    # A code at war with itself: two per home required, one per home
    # permitted. The charge is cut to the cap and the count check says so.
    at_war = run(rules(parking_min_per_unit=2.0, parking_max_per_unit=1.0), relief=NO_RELIEF)

    assert at_war.triage is Triage.red
    assert at_war.head == "parking_stalls"
    assert at_war.stalls_charged == 4


def test_open_space_is_flagged_as_a_favourable_approximation() -> None:
    # Leftover area is an upper bound on qualifying open space — real codes
    # impose dimensions and location. The check runs, and says so.
    result = run(rules(open_space_min_pct=20))

    assert result.optimistic == ("open_space_pct",)
    assert result.triage is Triage.green


def test_landscaping_is_a_check_and_not_a_comment() -> None:
    # Four jurisdictions encoded min_landscaped_pct and the screen read none of
    # them. Portland asks 30 percent in RM1; a pod leaving twenty screened
    # GREEN on a standard it missed by a third.
    ok = run(rules(min_landscaped_pct=20))
    short = run(rules(min_landscaped_pct=70), relief=NO_RELIEF)

    assert ok.triage is Triage.green
    assert short.triage is Triage.red
    assert short.head == "landscaped_pct"


def test_landscaping_says_it_is_a_favourable_approximation() -> None:
    # Optimistic twice over: leftover area is an upper bound on what could be
    # landscaped, and every code that asks for landscaping also says driveways
    # and parking do not count towards it.
    assert run(rules(min_landscaped_pct=20)).optimistic == ("landscaped_pct",)


# --- the rule-cost ledger ---------------------------------------------


def test_the_histogram_ranks_what_is_costing_lots() -> None:
    # The point is not the total. It is seeing that one line in a code costs
    # thousands of lots, which turns a number into an argument worth having.
    results = [
        run(f=fit(over_ft=-16.0)),
        run(f=fit(over_ft=-16.0)),
        run(rules(min_lot_sqft=8000)),
    ]

    assert histogram(results).ranked() == [("fit_ft", 2), ("min_lot_area_sqft", 1)]


def test_a_clean_run_charges_nothing_to_any_rule() -> None:
    assert histogram([run(), run()]).ranked() == []


# --- the encoding backlog ---------------------------------------------


def test_the_backlog_counts_our_work_not_the_lots_problems() -> None:
    # Review is not a destination. Every reason code here is something we can
    # close by encoding, fetching, or verifying — and the count is what says
    # whether that is happening.
    results = [
        run(rules(parking_min_per_unit=None)),
        run(rules(parking_min_per_unit=None)),
        run(rules(quadplex_allowed=None)),
    ]

    assert backlog(results)[STANDARD_NOT_ENCODED] == 2
    assert backlog(results)[USE_NOT_ENCODED] == 1


def test_a_clean_run_has_no_backlog() -> None:
    assert backlog([run(), run()]) == {}


# --- an exception nobody resolved -------------------------------------


def test_two_exceptions_that_tie_send_the_lot_to_our_backlog() -> None:
    # Not the developer's queue: nothing they elect or apply for fixes this.
    # The encoding does not say which of two numbers governs, so we own it.
    result = run(rules(RuleVerdict.ambiguous), relief=READ)

    assert result.triage is Triage.unknown
    assert result.reasons == ("RULE_AMBIGUOUS",)


def test_an_ambiguous_rule_set_cannot_delete_a_lot() -> None:
    # Same asymmetry as an unverified standard, and for the same reason: a
    # false RED silently removes an acquisition target and nobody ever looks
    # at it again.
    result = run(rules(RuleVerdict.ambiguous), f=fit(over_ft=-16.0), relief=NO_RELIEF)

    assert result.triage is Triage.unknown


def test_ambiguity_is_counted_as_encoding_work() -> None:
    assert backlog([run(rules(RuleVerdict.ambiguous))])["RULE_AMBIGUOUS"] == 1


# --- what the answer rested on ---------------------------------------
#
# A batch run assumes half a dozen things about every parcel — no corner, no
# alley, no slope — because there is nobody to ask. The assumptions are fine.
# Certifying a lot GREEN on one is not, and neither is downgrading every lot
# for holding assumptions that no standard in its zone turns on.


def levered(*names: str, **overrides) -> ZoneResolution:
    """A rule set where one standard states a different number under `names`."""
    got = rules(**overrides)
    got.values["min_lot_sqft"] = Resolved(
        name="min_lot_sqft",
        value=3000,
        status=Status.verified,
        prov=PROV,
        layer=WHERE,
        origin="zone",
        levers=frozenset(names),
    )
    return got


def test_a_lot_clears_green_with_assumptions_nothing_turns_on() -> None:
    # The default state of every batch lot. If this went yellow the screen
    # would be useless: no lot anywhere would ever be certified.
    config = configure(LOT, DESIGN)

    got = screen(rules(), LOT, DESIGN, fit(), policy=POLICY, config=config)

    assert got.triage is Triage.green


def test_an_assumption_a_standard_turns_on_costs_the_green() -> None:
    # Here the zone states a different lot minimum for corners, and nobody
    # looked at whether this lot is one. The number used may be the wrong one,
    # so the lot is our question, not the developer's.
    config = configure(LOT, DESIGN)

    got = screen(levered("corner_lot"), LOT, DESIGN, fit(), policy=POLICY, config=config)

    assert got.triage is Triage.unknown
    assert FACT_ASSUMED in got.reasons


def test_observing_the_fact_restores_the_green() -> None:
    # The fix for the case above is data, and the screen has to reflect that:
    # once the corner layer answers, the same lot certifies.
    config = configure(LOT, DESIGN, observed={"corner_lot": False})

    got = screen(levered("corner_lot"), LOT, DESIGN, fit(), policy=POLICY, config=config)

    assert got.triage is Triage.green


def test_a_standard_turning_on_a_fact_nobody_will_guess_is_unknown() -> None:
    # Sewer. No layer answered and the registry refuses to assume, so the
    # standard's own number is in doubt.
    config = configure(LOT, DESIGN)

    got = screen(levered("public_sewer"), LOT, DESIGN, fit(), policy=POLICY, config=config)

    assert got.triage is Triage.unknown
    assert FACT_UNOBSERVED in got.reasons


def test_without_a_configuration_nothing_changes() -> None:
    # Passing one is how a caller opts into the report. Omitting it must not
    # silently invent guesses the caller never made.
    got = screen(levered("corner_lot"), LOT, DESIGN, fit(), policy=POLICY)

    assert got.triage is Triage.green
    assert FACT_ASSUMED not in got.reasons


def test_a_pod_alone_can_miss_the_density_floor_on_a_big_lot() -> None:
    """Four units on two acres is two per acre, where Fairview R-10 asks 3.5.
    Every other standard clears by a mile — the lot is enormous — so until the
    floor could be written down this screened GREEN with nothing compared."""
    two_acres = LotFacts(lot_sqft=87_120, frontage_ft=200, lot_width_ft=200)

    result = run(rules(min_density_du_per_acre=3.5), lot=two_acres)

    floor = next(c for c in result.checks if c.check == "min_density_du_per_acre")
    assert floor.verdict is Verdict.fails
    assert result.triage is not Triage.green


def test_a_zone_that_states_no_density_floor_is_not_measured_against_one() -> None:
    """Most zones state none, and a missing floor is not a floor of zero."""
    result = run(rules(), lot=LotFacts(lot_sqft=87_120, frontage_ft=200, lot_width_ft=200))

    assert not any(c.check == "min_density_du_per_acre" for c in result.checks)
    assert "min_density_du_per_acre" in result.unchecked


def _per_net_acre(field: str, value: float) -> ZoneResolution:
    """The same standard, stated per net acre rather than per lot acre."""
    held = rules(**{field: value})
    held.values[field] = replace(held.values[field], measured_on="net_developable_area")
    return held


def test_a_floor_per_net_acre_fails_on_the_lot_and_the_failure_is_not_an_answer() -> None:
    """Fairview, Happy Valley, Milwaukie and Troutdale measure density on the
    lot less rights-of-way, floodplain, slopes and Goal 5 resources. Nothing
    surveys that. Four units on two acres is two per acre against a floor of
    3.5 — but net area is never more than gross, so a smaller denominator
    could clear the same floor, and RED here would be arithmetic nobody did."""
    two_acres = LotFacts(lot_sqft=87_120, frontage_ft=200, lot_width_ft=200)

    result = run(_per_net_acre("min_density_du_per_acre", 3.5), lot=two_acres)

    assert not any(c.check == "min_density_du_per_acre" for c in result.checks)
    assert "min_density_du_per_acre" in result.unchecked
    assert FACT_UNOBSERVED in result.reasons
    assert result.triage is Triage.unknown


def test_a_floor_per_net_acre_cleared_on_the_whole_lot_is_cleared_for_certain() -> None:
    """The half of the question a bound settles. Deducting anything from the
    lot only raises the density achieved, so a floor met on the gross area is
    met on any net area — and this is the common case, because minimum density
    only bites on large lots."""
    small = LotFacts(lot_sqft=6_000, frontage_ft=60, lot_width_ft=60)

    result = run(_per_net_acre("min_density_du_per_acre", 3.5), lot=small)

    floor = next(c for c in result.checks if c.check == "min_density_du_per_acre")
    assert floor.verdict is Verdict.passes
    assert FACT_UNOBSERVED not in result.reasons
    assert result.triage is Triage.green


def test_a_ceiling_per_net_acre_is_settled_the_other_way_round() -> None:
    """A maximum exceeded on the whole lot is exceeded on any net area, so the
    failure stands. Cleared on the whole lot it is open, because the true
    denominator is smaller and the true density higher."""
    small = LotFacts(lot_sqft=6_000, frontage_ft=60, lot_width_ft=60)
    big = LotFacts(lot_sqft=40_000, frontage_ft=150, lot_width_ft=150)

    over = run(_per_net_acre("max_density_du_per_acre", 25), lot=small, relief=NO_RELIEF)
    under = run(_per_net_acre("max_density_du_per_acre", 25), lot=big)

    assert over.head == "density_du_per_acre", "4 units on 6,000 sq ft is 29 per acre"
    assert over.triage is Triage.red
    assert "density_du_per_acre" in under.unchecked
    assert FACT_UNOBSERVED in under.reasons


def test_a_ratio_may_name_a_denominator_too() -> None:
    """Not only densities take a subtraction.

    West Linn prints one sentence in all nine of its zone chapters — "Type I
    and II lands shall not be counted toward lot area when determining
    allowable floor area ratio" — so the ratio that governs there is the pod's
    floor area over something smaller than the lot. Divided by the whole lot
    the FAR comes out LOW, which is the direction that certifies, so a screen
    that ran it anyway would hand out GREENs on exactly the wooded and steep
    parcels the sentence was written for.

    The bound settles the other half unchanged: 4,032 sq ft of floor on 6,000
    of lot is 0.67 against a 0.60 ceiling, and shrinking the denominator only
    raises it.
    """
    small = LotFacts(lot_sqft=6_000, frontage_ft=60, lot_width_ft=60)
    big = LotFacts(lot_sqft=40_000, frontage_ft=150, lot_width_ft=150)

    over = run(_per_net_acre("max_far", 0.60), lot=small, relief=NO_RELIEF)
    under = run(_per_net_acre("max_far", 0.60), lot=big)

    assert over.head == "far"
    assert over.triage is Triage.red
    assert not any(c.check == "far" for c in under.checks)
    assert "far" in under.unchecked
    assert FACT_UNOBSERVED in under.reasons


def test_a_ratio_measured_on_the_lot_still_simply_runs() -> None:
    """Most cities define FAR against the lot and say so — West Linn's own
    glossary works the example on "the total lot size". Marking every ratio
    would decline a check this project can run."""
    big = LotFacts(lot_sqft=40_000, frontage_ft=150, lot_width_ft=150)

    result = run(rules(max_far=0.60), lot=big)

    ratio = next(c for c in result.checks if c.check == "far")
    assert ratio.verdict is Verdict.passes
    assert FACT_UNOBSERVED not in result.reasons


def test_portland_states_its_floor_per_lot_and_it_runs() -> None:
    """Table 120-4 says "of site area", which is the whole lot. The
    distinction is worth carrying because one city in the corpus is on the
    other side of it."""
    two_acres = LotFacts(lot_sqft=87_120, frontage_ft=200, lot_width_ft=200)

    result = run(rules(min_density_du_per_acre=17.424), lot=two_acres)

    floor = next(c for c in result.checks if c.check == "min_density_du_per_acre")
    assert floor.verdict is Verdict.fails


# --- the split path ---------------------------------------------------


#: The same catalog entry costed for the split path. Pydantic, so a copy
#: rather than a dataclass replace.
SPLIT = DESIGN.model_copy(update={"plat": Plat.unit_lots})


def _split(**overrides) -> ZoneResolution:
    """A resolution whose lot standards came from a ``unit_lots`` variant.

    Which is how a rule file states a townhouse lot standard for a
    conventional subdivision, and those numbers are per child lot.
    """
    base = rules(**overrides)
    for name in ("min_lot_sqft", "min_lot_width_ft"):
        base.values[name] = replace(base.values[name], when=("unit_lots",))
    return base


def test_a_per_lot_standard_is_asked_of_the_parcel_four_times_over() -> None:
    """A 1,500 sq ft floor carried on a ``unit_lots`` variant is one child
    lot's, and four of them sit side by side on the parent. The paper fit has
    always read it that way; the screen was comparing the parent against a
    single child's number, which passes any lot big enough for one townhouse
    and calls a four-unit project GREEN on it."""
    small = LotFacts(lot_sqft=5_000, frontage_ft=60, lot_width_ft=60)

    result = screen(
        _split(min_lot_sqft=1_500), small, SPLIT, fit(), policy=POLICY
    )

    area = next(c for c in result.checks if c.check == "min_lot_area_sqft")
    assert area.threshold == 6_000
    assert area.verdict is Verdict.fails


def test_the_same_lot_on_one_lot_is_measured_against_the_number_as_written() -> None:
    """The other half of the same rule, and the reason nothing in production
    moves: a design that does not split the plat reads the base standard
    exactly as the table prints it."""
    small = LotFacts(lot_sqft=5_000, frontage_ft=60, lot_width_ft=60)

    result = screen(rules(min_lot_sqft=1_500), small, DESIGN, fit(), policy=POLICY)

    area = next(c for c in result.checks if c.check == "min_lot_area_sqft")
    assert area.threshold == 1_500
    assert area.verdict is Verdict.passes


def test_a_split_plat_with_nothing_stating_a_townhouse_lot_standard_is_unchecked() -> None:
    """Neither a ``unit_lots`` variant nor ORS 92.031's parent-standards flag,
    so nothing in the encoding says what the parent has to be. Reporting the
    standard as one we do not hold is the honest answer, and the one that
    blocks GREEN rather than assuming it."""

    result = screen(rules(), LOT, SPLIT, fit(), policy=POLICY)

    assert "min_lot_area_sqft" in result.unchecked
    assert "min_lot_width_ft" in result.unchecked
    assert result.triage is Triage.unknown


def test_the_statute_lets_the_parent_read_its_own_zone_unchanged() -> None:
    """ORS 92.031(2)(b) judges a middle housing land division against the
    regulations applicable to the original lot, and a layer that has read that
    says so with ``land_division_parent_standards``. Then the split path asks
    the parent for exactly what the one-lot path asks."""

    result = screen(
        rules(land_division_parent_standards=True, min_lot_sqft=3_000),
        LOT,
        SPLIT,
        fit(),
        policy=POLICY,
    )

    area = next(c for c in result.checks if c.check == "min_lot_area_sqft")
    assert area.threshold == 3_000
    assert area.verdict is Verdict.passes
