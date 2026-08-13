"""What the code lets you ask for, and what this module refuses to assume.

Two failures are possible here and they are not symmetric. Claiming relief
exists where it does not costs one wasted review. Claiming it does not exist
where it does deletes an acquisition target and nobody ever learns the lot was
buildable. Every default below leans the first way, and every claim that leans
the other way has to be encoded and cited.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from flats.rules.conditions import Tier
from flats.score.relief import (
    ANY,
    CONFIG_PATH,
    USE,
    ReliefOutcome,
    ReliefPath,
    ReliefPolicy,
    load_policy,
    worst,
)

pytestmark = pytest.mark.unit

WHERE = "or/multnomah/portland"

ADJUSTMENT = ReliefPath(
    "adjustment", Tier.administrative, cap_pct=0.10, cite="PCC 33.805.040", confirmed=True
)
VARIANCE = ReliefPath("variance", Tier.discretionary, cite="PCC 33.805.050", confirmed=True)


def policy(**checks) -> ReliefPolicy:
    return ReliefPolicy({WHERE: checks})


# --- the default: unread is not unavailable ----------------------------


def test_a_jurisdiction_nobody_has_read_is_assumed_to_grant_something() -> None:
    out = ReliefPolicy().for_check("setback_ft", shortfall=1.0, threshold=10.0, jurisdiction=WHERE)

    assert out.available
    assert out.confirmed is False


def test_the_assumption_is_labelled_rather_than_hidden() -> None:
    # It is the right default and it is still a claim, so it says so.
    out = ReliefPolicy().for_check("setback_ft", shortfall=1.0, threshold=10.0, jurisdiction=WHERE)

    assert "unconfirmed" in str(out)


def test_an_explicit_empty_list_is_how_a_code_says_no() -> None:
    # Silence and "we read it and there is nothing" are different statements,
    # and the file has to be able to make the second one.
    out = policy(**{ANY: []}).for_check(
        "setback_ft", shortfall=1.0, threshold=10.0, jurisdiction=WHERE
    )

    assert out.tier is Tier.unavailable
    assert out.condition is None


# --- picking a path ----------------------------------------------------


def test_the_cheapest_path_that_carries_the_miss_wins() -> None:
    out = policy(**{ANY: [ADJUSTMENT, VARIANCE]}).for_check(
        "setback_ft", shortfall=0.5, threshold=10.0, jurisdiction=WHERE
    )

    assert out.tier is Tier.administrative
    assert out.cite == "PCC 33.805.040"


def test_a_miss_past_the_cap_escalates_instead_of_dying() -> None:
    # 3 ft off a 10 ft standard is past a 10% adjustment. That makes it a
    # hearing, not a wall — a variance is granted on findings, not on size.
    out = policy(**{ANY: [ADJUSTMENT, VARIANCE]}).for_check(
        "setback_ft", shortfall=3.0, threshold=10.0, jurisdiction=WHERE
    )

    assert out.tier is Tier.discretionary


def test_a_miss_past_every_capped_path_has_nowhere_left() -> None:
    out = policy(**{ANY: [ADJUSTMENT]}).for_check(
        "setback_ft", shortfall=3.0, threshold=10.0, jurisdiction=WHERE
    )

    assert out.tier is Tier.unavailable


def test_an_uncapped_path_carries_any_miss() -> None:
    assert VARIANCE.carries(shortfall=500.0, threshold=10.0)


def test_a_flat_cap_and_a_percentage_cap_are_alternatives() -> None:
    # Two stated allowances are alternatives, not an intersection: a chapter
    # granting "2 ft or 10%, whichever is greater" grants the greater.
    both = ReliefPath("adjustment", Tier.administrative, cap=2.0, cap_pct=0.10)

    assert both.carries(shortfall=1.8, threshold=10.0), "inside the flat 2 ft"
    assert both.carries(shortfall=4.0, threshold=50.0), "inside 10% of 50"
    assert not both.carries(shortfall=6.0, threshold=50.0)


# --- precedence --------------------------------------------------------


def test_a_named_check_beats_the_catch_all_in_the_same_layer() -> None:
    p = ReliefPolicy({WHERE: {ANY: [VARIANCE], "min_lot_area_sqft": []}})
    named = p.for_check("min_lot_area_sqft", shortfall=1.0, threshold=10.0, jurisdiction=WHERE)
    other = p.for_check("setback_ft", shortfall=1.0, threshold=10.0, jurisdiction=WHERE)

    assert named.tier is Tier.unavailable
    assert other.tier is Tier.discretionary


def test_the_more_specific_layer_wins() -> None:
    # Same precedence as rule resolution, for the same reason: the specific
    # statement is the one somebody wrote on purpose.
    p = ReliefPolicy({"or": {ANY: []}, WHERE: {ANY: [ADJUSTMENT]}})
    out = p.for_check("setback_ft", shortfall=0.5, threshold=10.0, jurisdiction=WHERE)

    assert out.tier is Tier.administrative


def test_a_state_rule_still_reaches_a_city_that_says_nothing() -> None:
    p = ReliefPolicy({"or": {ANY: [VARIANCE]}})
    out = p.for_check("setback_ft", shortfall=0.5, threshold=10.0, jurisdiction=WHERE)

    assert out.tier is Tier.discretionary


# --- the use gate is the exception -------------------------------------


def test_use_defaults_to_no_path_at_all() -> None:
    # Codes enumerate conditional uses. Not being listed is the code speaking.
    assert ReliefPolicy().for_use(WHERE).tier is Tier.unavailable


def test_an_enumerated_conditional_use_is_a_path() -> None:
    p = policy(**{USE: [ReliefPath("conditional_use", Tier.discretionary, cite="PCC 33.815")]})

    assert p.for_use(WHERE).tier is Tier.discretionary


def test_the_dimensional_catch_all_does_not_leak_into_the_use_gate() -> None:
    # "*" covers development standards. It must not quietly grant permission
    # for a use the zone does not allow.
    assert policy(**{ANY: [VARIANCE]}).for_use(WHERE).tier is Tier.unavailable


# --- posture is a filter, never a verdict ------------------------------


def test_posture_says_what_this_team_will_pursue() -> None:
    cautious = ReliefPolicy(posture=Tier.administrative)

    assert cautious.acceptable(Tier.as_of_right)
    assert cautious.acceptable(Tier.administrative)
    assert not cautious.acceptable(Tier.discretionary)


def test_no_posture_accepts_a_wall() -> None:
    assert not ReliefPolicy(posture=Tier.discretionary).acceptable(Tier.unavailable)


# --- combining ---------------------------------------------------------


def test_the_hardest_ask_decides_the_configuration() -> None:
    out = worst(
        [
            ReliefOutcome("a", Tier.administrative, "adjustment"),
            ReliefOutcome("b", Tier.discretionary, "variance"),
        ]
    )

    assert out is not None and out.tier is Tier.discretionary


def test_nothing_failing_means_nothing_to_ask_for() -> None:
    assert worst([]) is None


# --- loading -----------------------------------------------------------


def test_the_shipped_config_loads() -> None:
    loaded = load_policy()

    assert loaded.posture.available


def test_the_shipped_config_assumes_nothing_about_any_jurisdiction() -> None:
    # Every path in here has to come from a chapter somebody read. Until then
    # the file stays empty and the code-level default does the work.
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

    assert raw["jurisdictions"] == {}


def test_a_confirmed_path_without_a_citation_is_refused(tmp_path: Path) -> None:
    # The one claim this module must never carry: "a human checked this" with
    # nothing to check it against.
    path = tmp_path / "relief.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "posture": "discretionary",
                "jurisdictions": {WHERE: {ANY: [{"condition": "adjustment", "confirmed": True}]}},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must cite"):
        load_policy(path)


def test_an_unregistered_condition_fails_at_load(tmp_path: Path) -> None:
    path = tmp_path / "relief.yaml"
    path.write_text(
        yaml.safe_dump({"jurisdictions": {WHERE: {ANY: [{"condition": "waiver"}]}}}),
        encoding="utf-8",
    )

    with pytest.raises(KeyError, match="waiver"):
        load_policy(path)


def test_a_percentage_cap_outside_zero_to_one_is_refused(tmp_path: Path) -> None:
    # "10" meaning ten percent would silently become a 1,000% allowance.
    path = tmp_path / "relief.yaml"
    path.write_text(
        yaml.safe_dump(
            {"jurisdictions": {WHERE: {ANY: [{"condition": "adjustment", "cap_pct": 10}]}}}
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="fraction of the standard"):
        load_policy(path)


def test_a_posture_that_refuses_everything_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "relief.yaml"
    path.write_text(yaml.safe_dump({"posture": "unavailable"}), encoding="utf-8")

    with pytest.raises(ValueError, match="posture"):
        load_policy(path)
