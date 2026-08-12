"""Slack and tolerance.

The contract that matters most: tolerance may rescue a RED into REVIEW, and may
never turn anything into a GREEN. A false red silently deletes an acquisition
target; a false green costs one review.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flats.score.slack import (
    CONFIG_PATH,
    SlackPolicy,
    Verdict,
    binding,
    dominant,
    load_policy,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def policy() -> SlackPolicy:
    return SlackPolicy(
        tolerance={"setback_ft": 0.0, "fit_ft": 0.5},
        overrides={"or/multnomah/portland": {"fit_ft": 0.25}},
    )


# --- slack is a measurement ------------------------------------------


def test_slack_is_recorded_on_a_pass_too(policy: SlackPolicy) -> None:
    # Not just failures. A lot that clears by 340 sqft and one that clears by 4
    # are different prospects, and ranking needs to know which is which.
    r = policy.evaluate("coverage_pct", observed=38.0, threshold=45.0, is_maximum=True)

    assert r.verdict is Verdict.passes
    assert r.slack == 7.0
    assert r.shortfall == 0.0


def test_slack_sign_follows_the_direction_of_the_standard(policy: SlackPolicy) -> None:
    # A ceiling has room when observed is under it; a floor when observed is over.
    ceiling = policy.evaluate("height_ft", observed=26.0, threshold=30.0, is_maximum=True)
    floor = policy.evaluate("min_lot_area_sqft", observed=4200, threshold=3000, is_maximum=False)

    assert ceiling.slack == 4.0
    assert floor.slack == 1200.0


def test_a_shortfall_is_negative_slack(policy: SlackPolicy) -> None:
    r = policy.evaluate("setback_ft", observed=8.6, threshold=10.0, is_maximum=False)

    assert r.slack == pytest.approx(-1.4)
    assert r.shortfall == pytest.approx(1.4)


def test_exactly_meeting_the_standard_passes(policy: SlackPolicy) -> None:
    # Codes are written as "at least" and "no more than". Meeting the number
    # exactly complies, and rounding it into a failure would be a false red.
    assert policy.evaluate("setback_ft", 10.0, 10.0, is_maximum=False).verdict is Verdict.passes
    assert policy.evaluate("height_ft", 30.0, 30.0, is_maximum=True).verdict is Verdict.passes


# --- tolerance is a policy -------------------------------------------


def test_within_tolerance_is_tolerated_not_passed(policy: SlackPolicy) -> None:
    # The load-bearing rule. Tolerance rescues a RED into REVIEW; it never
    # manufactures a GREEN, because a human still has to look.
    r = policy.evaluate("fit_ft", observed=35.7, threshold=36.0, is_maximum=False)

    assert r.verdict is Verdict.tolerated
    assert r.verdict.blocks, "a tolerated check must still keep the lot out of GREEN"


def test_beyond_tolerance_fails(policy: SlackPolicy) -> None:
    r = policy.evaluate("fit_ft", observed=30.0, threshold=36.0, is_maximum=False)

    assert r.verdict is Verdict.fails


def test_exactly_at_the_tolerance_edge_is_tolerated(policy: SlackPolicy) -> None:
    # The recall bias resolves the boundary: include and review rather than
    # exclude and never know.
    r = policy.evaluate("fit_ft", observed=35.5, threshold=36.0, is_maximum=False)

    assert r.verdict is Verdict.tolerated


def test_zero_tolerance_takes_the_code_number_literally(policy: SlackPolicy) -> None:
    r = policy.evaluate("setback_ft", observed=9.99, threshold=10.0, is_maximum=False)

    assert r.verdict is Verdict.fails


def test_tolerance_does_not_change_the_recorded_slack(policy: SlackPolicy) -> None:
    # Slack is the measurement. If tolerance moved it, every downstream
    # consumer — ranking, the design sweep, the histogram — would be wrong.
    r = policy.evaluate("fit_ft", observed=35.7, threshold=36.0, is_maximum=False)

    assert r.slack == pytest.approx(-0.3)
    assert r.tolerance == 0.5


# --- jurisdiction overrides ------------------------------------------


def test_the_most_specific_layer_wins(policy: SlackPolicy) -> None:
    assert policy.tolerance_for("fit_ft") == 0.5
    assert policy.tolerance_for("fit_ft", "or/multnomah") == 0.5
    assert policy.tolerance_for("fit_ft", "or/multnomah/portland") == 0.25


def test_an_override_only_touches_the_checks_it_names(policy: SlackPolicy) -> None:
    assert policy.tolerance_for("setback_ft", "or/multnomah/portland") == 0.0


def test_an_unknown_check_has_no_tolerance(policy: SlackPolicy) -> None:
    # Silently inventing slack for a check nobody configured would be a false
    # green generator.
    assert policy.tolerance_for("some_new_check") == 0.0


def test_an_override_changes_the_verdict(policy: SlackPolicy) -> None:
    args = dict(observed=35.7, threshold=36.0, is_maximum=False)

    assert policy.evaluate("fit_ft", **args).verdict is Verdict.tolerated
    assert (
        policy.evaluate("fit_ft", jurisdiction="or/multnomah/portland", **args).verdict
        is Verdict.fails
    )


# --- binding attribution ---------------------------------------------


def test_binding_lists_blockers_tightest_first(policy: SlackPolicy) -> None:
    # The top row is the constraint worth arguing about. It is also what the
    # histogram counts, which is how a rule quietly costing thousands of lots
    # becomes visible.
    results = [
        policy.evaluate("setback_ft", 8.0, 10.0, is_maximum=False),  # short by 2
        policy.evaluate("height_ft", 26.0, 30.0, is_maximum=True),  # passes
        policy.evaluate("min_frontage_ft", 49.5, 50.0, is_maximum=False),  # short by 0.5
    ]

    assert [r.check for r in binding(results)] == ["min_frontage_ft", "setback_ft"]


def test_a_tolerated_check_still_counts_as_binding(policy: SlackPolicy) -> None:
    results = [policy.evaluate("fit_ft", 35.7, 36.0, is_maximum=False)]

    assert [r.check for r in binding(results)] == ["fit_ft"]


def test_nothing_binds_when_everything_passes(policy: SlackPolicy) -> None:
    assert binding([policy.evaluate("height_ft", 26.0, 30.0, is_maximum=True)]) == []


# --- attribution -----------------------------------------------------


def test_attribution_compares_proportions_not_raw_numbers(policy: SlackPolicy) -> None:
    # 1,000 square feet short of a lot minimum and 0.02 over an FAR cap are not
    # on the same scale. Ranked by magnitude the FAR would never win; ranked by
    # proportion the answer means something.
    area = policy.evaluate("min_lot_area_sqft", 2000, 3000, is_maximum=False)
    far = policy.evaluate("far", 2.02, 2.0, is_maximum=True)

    assert binding([area, far])[0].check == "far", "tightest first is the work queue"
    worst = dominant([area, far])
    assert worst is not None and worst.check == "min_lot_area_sqft"


def test_nothing_is_charged_when_nothing_blocks(policy: SlackPolicy) -> None:
    assert dominant([policy.evaluate("height_ft", 26.0, 30.0, is_maximum=True)]) is None


def test_a_shortfall_against_a_zero_standard_stays_absolute(policy: SlackPolicy) -> None:
    # Dividing by the standard is meaningless when the standard is zero, so the
    # raw shortfall stands in rather than a division by zero.
    r = policy.evaluate("setback_ft", -2.0, 0.0, is_maximum=False)

    assert r.relative_shortfall == pytest.approx(2.0)


# --- the shipped policy ----------------------------------------------


def test_shipped_config_loads() -> None:
    p = load_policy()

    assert p.report == "always"
    assert p.tolerance_for("setback_ft") == 0.0
    assert p.tolerance_for("fit_ft") == 0.5


def test_shipped_config_forgives_only_measurement_noise() -> None:
    # Tolerance exists for instrument error, not for bending the code. Anything
    # surveyed to the tenth of a foot gets zero.
    p = load_policy()

    for check in ("setback_ft", "coverage_pct", "min_frontage_ft", "height_ft", "far"):
        assert p.tolerance_for(check) == 0.0, f"{check} should take the code number literally"


def test_negative_tolerance_is_refused(tmp_path: Path) -> None:
    # A negative tolerance would tighten the code beyond what it says and turn
    # passing lots red — the one failure mode this project cannot have.
    bad = tmp_path / "slack.yaml"
    bad.write_text("tolerance:\n  setback_ft: -1.0\n", encoding="utf-8")

    with pytest.raises(ValueError, match="negative tolerance"):
        load_policy(bad)


def test_config_path_points_at_the_shipped_file() -> None:
    assert CONFIG_PATH.is_file()
