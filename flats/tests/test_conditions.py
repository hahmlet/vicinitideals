"""The condition vocabulary, and what it refuses to let anyone say.

A registry earns its keep by rejecting things. These tests are mostly about
what cannot be written: an unregistered name, a relief with no tier, a site
fact asserted where an observation was needed.
"""

from __future__ import annotations

import pytest

from flats.rules.conditions import (
    ASSUMED,
    ASSUMED_TIER,
    ASSUMED_USE_TIER,
    CONDITIONS,
    ConditionDef,
    Tier,
    condition,
    deepest,
    design_facts,
    electives,
    reliefs,
    site_facts,
)

pytestmark = pytest.mark.unit


# --- the registry ------------------------------------------------------


def test_every_condition_is_named_once() -> None:
    # The kinds partition the registry: a condition nobody can place in one of
    # them is one nothing downstream knows how to ask about.
    assert len(CONDITIONS) == len(electives()) + len(site_facts()) + len(
        design_facts()
    ) + len(reliefs())


def test_an_unregistered_condition_is_refused_by_name() -> None:
    # The refusal is the point. A screen that accepts "affordability" beside
    # "affordable" splits one lever in two, and the batch view offers both.
    with pytest.raises(KeyError, match="affordability"):
        condition("affordability")


def test_every_condition_says_how_it_is_established() -> None:
    # A condition nobody can evidence is a checkbox, not a screen input.
    assert all(c.describe and c.evidence for c in CONDITIONS.values())


def test_relief_is_a_condition_like_any_other() -> None:
    # Filing for an adjustment is a choice with a cost, exactly like electing
    # affordability. Modelling it as a special case inside the scoring stage is
    # what produced a traffic light that called a one-foot miss RED.
    assert {c.name for c in reliefs()} == {
        "adjustment",
        "variance",
        "conditional_use",
        # Multnomah County's resource districts run a third category between
        # permitted and conditional, with its own sections and its own
        # findings. Folding it into `conditional_use` would report a cost the
        # county does not charge.
        "review_use",
        # And a fourth thing again: a Planned Development is not permission for
        # a use, it is permission to replace the base zone's standards with a
        # plan. MCC 39.5350(A) is the only sentence in Chapter 39 that names an
        # attached dwelling for a rural residential zone, and it is inside that
        # overlay rather than inside any zone's use list.
        "planned_development",
    }


# --- what a definition may not claim -----------------------------------


def test_a_relief_without_a_tier_is_rejected() -> None:
    with pytest.raises(ValueError, match="must state its tier"):
        ConditionDef("appeal", "relief", "…")


def test_only_relief_carries_a_tier() -> None:
    with pytest.raises(ValueError, match="only relief"):
        ConditionDef("affordable_2", "elective", "…", tier=Tier.administrative)


def test_only_a_site_fact_can_be_assumed() -> None:
    # Assuming the developer elected affordability would invent a covenant.
    with pytest.raises(ValueError, match="only a site fact"):
        ConditionDef("mixed_use_2", "elective", "…", assume=False)


# --- tiers -------------------------------------------------------------


def test_tiers_run_from_no_ask_to_no_path() -> None:
    ranks = [t.rank for t in (Tier.as_of_right, Tier.administrative, Tier.discretionary, Tier.unavailable)]

    assert ranks == sorted(ranks)


def test_only_unavailable_closes_the_door() -> None:
    assert not Tier.unavailable.available
    assert all(t.available for t in (Tier.as_of_right, Tier.administrative, Tier.discretionary))


def test_as_of_right_is_not_an_ask() -> None:
    assert Tier.as_of_right.needs_ask is False
    assert Tier.administrative.needs_ask is True
    assert Tier.discretionary.needs_ask is True
    # Nor is a wall: there is nothing to apply for.
    assert Tier.unavailable.needs_ask is False


def test_the_hardest_ask_governs() -> None:
    # Two staff-level asks are still a staff-level project; one hearing is not.
    assert deepest([Tier.administrative, Tier.administrative]) is Tier.administrative
    assert deepest([Tier.administrative, Tier.discretionary]) is Tier.discretionary


def test_nothing_to_ask_for_costs_nothing() -> None:
    assert deepest([]) is Tier.as_of_right


# --- the recall-biased defaults ----------------------------------------


def test_an_unread_chapter_is_assumed_to_grant_something() -> None:
    # A false red silently deletes an acquisition target and nobody learns it
    # existed. A false yellow costs one review.
    assert ASSUMED_TIER.available


def test_a_use_the_code_does_not_list_has_no_path() -> None:
    # The exception. Codes enumerate conditional uses, so silence there is
    # evidence of absence in a way that silence about adjustments is not.
    assert ASSUMED_USE_TIER is Tier.unavailable


def test_an_assumed_site_fact_is_marked_as_ours_not_observed() -> None:
    assert "corner_lot" in ASSUMED
    # Sewer is never assumed: it is the one site fact that flipped thousands of
    # Clackamas lots, so guessing at it would be guessing at the answer.
    assert "public_sewer" not in ASSUMED


def test_a_design_fact_is_about_the_building_not_the_lot() -> None:
    # Storey count decides Wilsonville's side setback, and no survey of the
    # parcel answers it. Registering it as a site fact would put it in the
    # batch view's list of things to observe, where nobody could ever observe
    # it; registering it as elective would offer the user a lever that is
    # really a different pod.
    names = [c.name for c in design_facts()]

    assert "multi_story" in names
    assert condition("multi_story").kind == "design_fact"
    assert "multi_story" not in [c.name for c in site_facts()]
    assert "multi_story" not in [c.name for c in electives()]


def test_a_design_fact_is_never_assumed() -> None:
    # ASSUMED is what a GREEN may not rest on. A design fact is read off the
    # catalog entry, so it is known outright and does not belong there.
    assert "multi_story" not in ASSUMED
    with pytest.raises(ValueError, match="site fact"):
        ConditionDef("two_storey", "design_fact", "x", assume=True)
