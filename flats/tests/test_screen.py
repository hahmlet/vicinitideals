"""Measurements become a verdict.

Four asymmetries define this module and every test here defends one of them:

* an unverified rule set can never produce RED — a bad number in a YAML file
  must not delete an acquisition target;
* tolerance rescues a lot into UNKNOWN and never certifies one into GREEN;
* a required standard nobody encoded blocks GREEN rather than being assumed
  satisfied;
* a miss the code offers a path around is YELLOW, not RED. A pod one foot over
  a setback is an adjustment application, not a dead lot, and only a standard
  with no procedure at all kills one.
"""

from __future__ import annotations

from datetime import date

import pytest

pytest.importorskip("shapely")

from flats.designs.model import load_catalog  # noqa: E402
from flats.fit.rectangle import Fit  # noqa: E402
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
from flats.score.screen import (  # noqa: E402
    GEOMETRY_UNREADABLE,
    NO_FRONTAGE,
    STANDARD_NOT_ENCODED,
    USE_NOT_ENCODED,
    USE_PROHIBITED,
    LotFacts,
    Triage,
    backlog,
    histogram,
    screen,
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


def rules(verdict: RuleVerdict = RuleVerdict.trusted, **overrides) -> ZoneResolution:
    values = {**CLEAR, **overrides}
    return ZoneResolution(
        jurisdiction=WHERE,
        zone="R5",
        verdict=verdict,
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


def fit(*, best_depth_ft: float = 40.0, depth_ft: float = 36.0) -> Fit:
    return Fit(
        fits=best_depth_ft >= depth_ft,
        width_ft=56.0,
        depth_ft=depth_ft,
        best_depth_ft=best_depth_ft,
        slack_ft=best_depth_ft - depth_ft,
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
    result = run(f=fit(best_depth_ft=30.0))

    assert result.head == "fit_ft"
    assert result.fit_slack_ft == pytest.approx(-6.0)
    assert result.triage is Triage.yellow


def test_a_miss_inside_measurement_noise_is_unknown_not_red() -> None:
    # One raster cell of shortfall. That is our instrument, not the lot: we do
    # not know whether it misses at all, which is a different thing from
    # knowing it misses and needing permission.
    result = run(f=fit(best_depth_ft=35.7))

    assert result.triage is Triage.unknown
    assert result.head == "fit_ft"


def test_tolerance_never_manufactures_a_green() -> None:
    result = run(f=fit(best_depth_ft=35.7))

    assert result.triage is not Triage.green


def test_a_definite_miss_outranks_a_fuzzy_one() -> None:
    # A lot that definitely fails one standard and might fail another is not
    # unanswerable — it needs an application. The doubt can only add asks.
    result = run(rules(min_lot_sqft=8000), f=fit(best_depth_ft=35.7))

    assert result.triage is Triage.yellow


# --- standards nobody encoded ----------------------------------------


def test_a_missing_required_standard_blocks_green() -> None:
    # Skipping a check the code plainly imposes would manufacture GREENs.
    result = run(rules(parking_min_per_unit=None))

    assert result.triage is Triage.unknown
    assert STANDARD_NOT_ENCODED in result.reasons
    assert "parking_stalls" in result.unchecked


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


def test_parking_compares_what_the_design_provides_to_what_the_code_demands() -> None:
    # The pod carries 1.5 stalls per unit. A code asking 2.0 outruns it.
    ok = run(rules(parking_min_per_unit=1.0))
    short = run(rules(parking_min_per_unit=2.0), relief=NO_RELIEF)

    assert ok.triage is Triage.green
    assert short.triage is Triage.red
    assert short.head == "parking_stalls"


def test_open_space_is_flagged_as_a_favourable_approximation() -> None:
    # Leftover area is an upper bound on qualifying open space — real codes
    # impose dimensions and location. The check runs, and says so.
    result = run(rules(open_space_min_pct=20))

    assert result.optimistic == ("open_space_pct",)
    assert result.triage is Triage.green


# --- the rule-cost ledger ---------------------------------------------


def test_the_histogram_ranks_what_is_costing_lots() -> None:
    # The point is not the total. It is seeing that one line in a code costs
    # thousands of lots, which turns a number into an argument worth having.
    results = [
        run(f=fit(best_depth_ft=20.0)),
        run(f=fit(best_depth_ft=20.0)),
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
    result = run(rules(RuleVerdict.ambiguous), f=fit(best_depth_ft=20.0), relief=NO_RELIEF)

    assert result.triage is Triage.unknown


def test_ambiguity_is_counted_as_encoding_work() -> None:
    assert backlog([run(rules(RuleVerdict.ambiguous))])["RULE_AMBIGUOUS"] == 1
