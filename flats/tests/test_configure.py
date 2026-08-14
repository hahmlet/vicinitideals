"""Assembling the configuration a screening run answers under.

The rule layer resolves against condition names and lot measurements. Where
those come from was, until now, up to whoever called it — which is how a
two-storey pod gets screened against a single-storey setback: not by an error,
but by a name nobody remembered to pass.

What these tests hold to is that the assembly is one function, that it believes
its three sources differently, and that it says out loud which parts of its
answer are guesses.
"""

from __future__ import annotations

import pytest
import yaml

from flats.designs.model import Design
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.score.configure import configure
from flats.score.screen import LotFacts

pytestmark = pytest.mark.unit

POD = """
version: 1
label: Four-plex pod
typology: townhome_rear_court
footprint: {width_ft: 56, depth_ft: 36}
units: 4
stories: 2
height_ft: 26
parking: {stalls_per_unit: 1.5, config: rear_court}
delivery: {method: modular, crane_required: true, crane_reach_ft: 60}
"""


def pod(**over) -> Design:
    return Design(**{**yaml.safe_load(POD), "id": "pod", **over})


def test_the_design_brings_its_own_conditions() -> None:
    # The whole reason this module exists: the storey count travels with the
    # building, and every pod in the catalog is two storeys.
    assert "multi_story" in configure(LotFacts(lot_sqft=6000), pod()).conditions
    assert "multi_story" not in configure(LotFacts(lot_sqft=6000), pod(stories=1)).conditions


def test_an_observation_is_believed_over_the_assumption() -> None:
    got = configure(LotFacts(lot_sqft=6000), pod(), observed={"corner_lot": True})

    assert "corner_lot" in got.conditions
    assert "corner_lot" not in got.assumed


def test_an_unobserved_site_fact_is_assumed_and_named() -> None:
    # Assuming is allowed; assuming silently is not. FLATS_PLAN 13: a verdict
    # resting on one of these may not be GREEN.
    got = configure(LotFacts(lot_sqft=6000), pod())

    assert "corner_lot" not in got.conditions
    assert "corner_lot" in got.assumed


def test_a_fact_the_registry_will_not_guess_is_neither_held_nor_denied() -> None:
    # Sewer is the case this exists for. Assuming a main is there manufactures
    # GREENs; assuming it is not deletes acquisition targets. Neither, and the
    # name goes where the screen can see it.
    got = configure(LotFacts(lot_sqft=6000), pod())

    assert "public_sewer" not in got.conditions
    assert "public_sewer" not in got.assumed
    assert "public_sewer" in got.unknown


def test_a_negative_observation_is_an_answer_not_a_gap() -> None:
    got = configure(LotFacts(lot_sqft=6000), pod(), observed={"public_sewer": False})

    assert "public_sewer" not in got.conditions
    assert "public_sewer" not in got.unknown


def test_an_election_is_never_inferred() -> None:
    assert "affordable" not in configure(LotFacts(lot_sqft=6000), pod()).conditions
    assert "affordable" in configure(
        LotFacts(lot_sqft=6000), pod(), elect=["affordable"]
    ).conditions


def test_relief_may_not_be_smuggled_in_as_a_condition() -> None:
    # Resolving a lot against the setback it wants rather than the one the code
    # states is the error this refusal exists for. Relief is priced after a
    # standard is missed, not folded into which standard applies.
    with pytest.raises(ValueError, match="relief"):
        configure(LotFacts(lot_sqft=6000), pod(), observed={"adjustment": True})


def test_an_elective_is_not_something_observed() -> None:
    with pytest.raises(ValueError, match="elective"):
        configure(LotFacts(lot_sqft=6000), pod(), observed={"affordable": True})


def test_an_unregistered_name_is_refused() -> None:
    with pytest.raises(KeyError, match="affordability"):
        configure(LotFacts(lot_sqft=6000), pod(), observed={"affordability": True})


def test_measurements_travel_in_the_units_the_bands_are_written_in() -> None:
    got = configure(LotFacts(lot_sqft=6000, lot_width_ft=50), pod())

    assert got.measures == {"lot_sqft": 6000.0, "lot_width_ft": 50.0}


def test_an_unmeasured_width_is_absent_rather_than_zero() -> None:
    # A band on lot width must see "not measured", not "zero feet wide" — the
    # first is ambiguous and the second is a lot in the smallest column.
    got = configure(LotFacts(lot_sqft=6000), pod())

    assert "lot_width_ft" not in got.measures


def test_a_guess_only_counts_where_a_standard_turns_on_it() -> None:
    # Every batch run assumes half a dozen site facts. Downgrading a lot for
    # holding an assumption nothing depends on would bury real GREENs.
    got = configure(LotFacts(lot_sqft=6000), pod())

    assert got.leans_on({"multi_story"}) == ()
    assert got.leans_on({"corner_lot", "affordable"}) == ("corner_lot",)
    assert "public_sewer" in got.leans_on({"public_sewer"})


def test_the_configuration_resolves_wilsonville_the_way_the_code_reads() -> None:
    # End to end against the shipped rules: a two-storey pod on a 6,000 sq ft
    # lot in Wilsonville's R zone is bound by the small-lot, two-storey column
    # — 15 front, 7 side, 20 rear — and none of those is the number printed
    # first in 4.113(.02).
    rules = RuleSet(load_rules(strict=False))
    got = configure(LotFacts(lot_sqft=6000, lot_width_ft=60), pod())

    resolved = rules.resolve(
        "or/clackamas/wilsonville", "R", got.conditions, got.measures
    )

    assert resolved.values["setback_front_ft"].value == 15
    assert resolved.values["setback_side_ft"].value == 7
    assert resolved.values["setback_rear_ft"].value == 20


def test_a_bigger_lot_resolves_to_the_other_column() -> None:
    rules = RuleSet(load_rules(strict=False))
    got = configure(LotFacts(lot_sqft=12000, lot_width_ft=80), pod())

    resolved = rules.resolve(
        "or/clackamas/wilsonville", "R", got.conditions, got.measures
    )

    assert resolved.values["setback_side_ft"].value == 10
    assert resolved.values["setback_front_ft"].value == 20
