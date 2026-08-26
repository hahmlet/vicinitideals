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

from dataclasses import replace
from datetime import date

import pytest

pytest.importorskip("shapely")

from flats.designs.model import Plat, load_catalog  # noqa: E402
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
from flats.score.configure import configure  # noqa: E402
from flats.score.screen import (  # noqa: E402
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
