"""The Planned Development overlay, and the sentence that had been missed.

Three articles in MCC Chapter 39 list a Planned Development as a conditional
use -- Orient Rural Center Residential, Rural Residential, and Multiple Use
Agriculture. All three were read as refusals, and two of them were wrong.

MCC 39.5350 is titled PERMITTED USES and opens "In a residential zone, the
following uses may be permitted in a Planned Development overlay: (A) Housing
types may include only duplexes and single family detached or attached
dwellings." Single family ATTACHED is this building. So OR, which lists the PD
without qualification, and RR, which lists it "for single family residences",
both reach the pod through a hearing -- and MUA-20 does not, because 39.5350
scopes itself to residential zones and Multiple Use Agriculture is not one.

What the door costs is the other half of the reading. 39.5320 lets a PD's own
standards displace the base zone's wherever they conflict, and prints no
replacement numbers, so nothing dimensional is relieved by it here. 39.5340(A)
does print one rule: the units a site may hold are the site area over the
underlying district's minimum lot area per dwelling. One acre in OR, five in
RR, four dwellings -- four acres and twenty. Those numbers are why a door being
open is not the same as a lot being buildable.
"""

from __future__ import annotations

import pytest

from flats.encode.readiness import readiness_for
from flats.provenance.store import ProvenanceStore
from flats.rules.conditions import CONDITIONS, Tier
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

UNINC = "or/multnomah/_unincorporated"
POD = ("multi_story", "attached_wall")
PD_DOC = f"{UNINC}/39.pd.txt"
#: The zones whose conditional list names a Planned Development.
LISTS_A_PD = ("OR", "RR", "MUA20")
#: The two 39.5350 reaches, because the two are residential zones.
OPENED_BY_ONE = ("OR", "RR")


@pytest.fixture(scope="module")
def uninc() -> Layer:
    return load_rules()[UNINC]


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


def test_no_zone_opens_without_the_hearing(rules: RuleSet) -> None:
    """A PD is a Planning Commission decision, so nothing fires on a batch run."""
    for zone in LISTS_A_PD:
        res = rules.resolve(UNINC, zone, POD)
        assert res.values["quadplex_allowed"].value is False, zone
        assert res.missing_required == (), zone


def test_the_two_residential_zones_open_with_it(rules: RuleSet) -> None:
    for zone in OPENED_BY_ONE:
        opened = rules.resolve(UNINC, zone, (*POD, "planned_development"))
        assert opened.values["quadplex_allowed"].value is True, zone


def test_the_agricultural_zone_does_not(rules: RuleSet) -> None:
    """39.5350 opens "In a residential zone" and MUA-20 is not one.

    The entry MUA-20 lists is word-for-word the entry RR lists, which is what
    makes the difference worth a test: the two are separated by the scope line
    of a third article, not by anything in either use list.
    """
    shut = rules.resolve(UNINC, "MUA20", (*POD, "planned_development"))
    assert shut.values["quadplex_allowed"].value is False
    assert uninc_note(rules, "MUA20").count("39.5350") >= 1


def uninc_note(rules: RuleSet, zone: str) -> str:
    return rules.layers[UNINC].zones[zone].notes or ""


def test_the_permission_is_quoted_from_the_article_that_prints_it(
    uninc: Layer, store: ProvenanceStore
) -> None:
    """The zone lists a PD; the overlay says what a PD may hold.

    Neither sentence is the rule on its own -- the use list names a procedure
    and the overlay names a housing type -- so the variant quotes the overlay
    and the citation carries both sections.
    """
    for zone in OPENED_BY_ONE:
        variant = uninc.zones[zone].values["quadplex_allowed"].variants[0]
        assert variant.prov.quote.startswith(PD_DOC), zone
        assert "39.5350(A)" in variant.prov.cite, zone

        text = store.quote(variant.prov.quote)
        assert "In a residential zone" in text
        assert "single family detached or attached" in text
        assert "duplexes" in text


def test_the_zone_use_list_is_quoted_with_its_own_pd_entry(
    uninc: Layer, store: ProvenanceStore
) -> None:
    """The base false has to show the entry it is refusing on, not just the closure.

    RR read `false` for a month on a quote that stopped at the allowed-use
    line. The conditional list was in the article the whole time and the
    citation did not reach it, which is how a door stays shut on paper.
    """
    for zone in OPENED_BY_ONE:
        text = store.quote(uninc.zones[zone].values["quadplex_allowed"].prov.quote)
        assert "Planned Development" in text, zone
        assert "39.5300 through 39.5350" in text, zone


def test_a_planned_development_is_a_discretionary_relief() -> None:
    pd = CONDITIONS["planned_development"]
    assert pd.kind == "relief"
    assert pd.tier is Tier.discretionary
    assert "39.5350(A)" in pd.describe or "39.5350" in pd.describe


def test_the_density_rule_is_what_makes_the_door_expensive(rules: RuleSet) -> None:
    """Four units, one acre each in OR and twenty in RR.

    39.5340(A) divides the site by the underlying minimum, so opening the use
    flag without carrying the arithmetic would have reported a one-acre lot in
    OR as buildable for four units. It is not; it is a quarter of the site the
    same overlay requires.
    """
    orient = rules.resolve(UNINC, "OR", (*POD, "planned_development"))
    assert orient.values["min_lot_sqft"].value == 4 * 43_560

    rural = rules.resolve(UNINC, "RR", (*POD, "planned_development"))
    assert rural.values["min_lot_sqft"].value == 4 * 20 * 43_560


def test_the_unmeasured_mile_leaves_the_stricter_acreage_in_force(
    rules: RuleSet,
) -> None:
    """RR states five acres, or twenty within a mile of the UGB.

    Nothing measures that distance, so the twenty binds and the five waits.
    The zone's own note says RR sits overwhelmingly outside the Metro UGB,
    which is a different claim from being a mile clear of it -- and the lot
    somebody would want four units on is exactly the one near the boundary.
    """
    unmeasured = CONDITIONS["beyond_ugb_mile"]
    assert unmeasured.kind == "site_fact"
    assert unmeasured.assume is None

    assert rules.resolve(UNINC, "RR", POD).values["min_lot_sqft"].value == 20 * 43_560
    measured = rules.resolve(UNINC, "RR", (*POD, "beyond_ugb_mile"))
    assert measured.values["min_lot_sqft"].value == 5 * 43_560


def test_the_overlay_relieves_dimensions_and_prints_no_replacement(
    store: ProvenanceStore,
) -> None:
    """39.5320 is the reason no PD variant touches a setback or a height.

    "In the case of a conflict between a standard of the base zone and that of
    the PD, the standard of the PD shall apply" relieves everything and states
    nothing, which is precisely the shape a relief cannot be encoded in.
    """
    text = store.quote(f"{PD_DOC}#L104-L110")
    assert "the standard of the PD shall" in text
    assert "conflict between a standard of the base zone" in text


def test_the_overlay_is_recorded_in_the_zones_it_governs(uninc: Layer) -> None:
    for zone in LISTS_A_PD:
        notes = uninc.zones[zone].notes or ""
        assert "PLANNED DEVELOPMENT" in notes, zone
        assert "660" in notes, zone


def test_the_planned_development_citations_point_at_their_own_sentence(
    uninc: Layer, store: ProvenanceStore
) -> None:
    ready = readiness_for(uninc, store=store)
    assert ready.no_evidence == ()
    assert ready.misquoted == ()
