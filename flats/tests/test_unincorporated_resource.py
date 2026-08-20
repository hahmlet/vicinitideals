"""Multnomah County's four resource base zones, and the one door in them.

MUA-20, CFU, EFU and MUF -- 305 lots, the largest single block left in the
coverage ledger and the least surprising. All four articles open the same way:
"no building, structure or land shall be used ... except for the uses listed in
MCC 39.xxxx through 39.xxxx". That sentence is what makes an absence readable,
and in three of the four the only residential entry on the closed list is a
single family dwelling.

CFU says it twice. Its three dwelling types -- large acreage, template,
heritage tract -- are each defined in the article's own definitions section as
"a type of single family detached dwelling", and detached is the word that ends
it for a building whose four units share three party walls.

EFU is the exception and the reason this file exists. MCC 39.4265(C)(2)(d)
permits an accessory farm dwelling to be "attached multi-unit residential
structures allowed by the applicable state building code or similar types of
farm labor housing" registered with Oregon OSHA. That is the pod's form, named,
in a zone with an 80-acre minimum lot. It cannot fire on an acquisition screen
and it is encoded anyway, because a zone that refuses and a zone nobody read
must not look the same.
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
#: The four resource districts, in the order MCC Chapter 39 Part 4 prints them.
RESOURCE = ("CFU", "EFU", "MUA20", "MUF19")
#: The three whose use list closes with no way out. EFU is not one of them.
CLOSED = ("CFU", "MUA20", "MUF19")


@pytest.fixture(scope="module")
def uninc() -> Layer:
    return load_rules()[UNINC]


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


def test_every_resource_district_refuses_the_pod(rules: RuleSet) -> None:
    for zone in RESOURCE:
        res = rules.resolve(UNINC, zone, POD)
        assert res.values["quadplex_allowed"].value is False, zone
        assert res.missing_required == (), zone


def test_a_closed_zone_owes_the_use_flag_and_nothing_else(uninc: Layer) -> None:
    """No dimensions on the three that close, deliberately.

    All four articles state a lot size, a yard row and a height. Encoding them
    on a zone whose use list already closed would put three answerable-looking
    districts on land nothing can be built on; the numbers are in the notes
    instead, so the next reader can see they were read.

    EFU carries a full envelope because EFU has a door, and a zone with a door
    needs the room behind it measured.
    """
    for zone in CLOSED:
        assert set(uninc.zones[zone].values) == {"quadplex_allowed"}, zone

    efu = set(uninc.zones["EFU"].values)
    assert "max_height_ft" in efu
    assert "min_lot_sqft" in efu
    assert {"setback_front_ft", "setback_side_ft", "setback_rear_ft"} <= efu


def test_the_closed_list_is_what_makes_the_silence_readable(uninc: Layer) -> None:
    """Each citation carries the closure sentence, not just the entry.

    An absence is only evidence where the code says the list is exhaustive.
    Quote the single-family entry alone and the encoding rests on nobody
    having found a quadplex row; quote the closure with it and it rests on
    the county saying there is no other row.
    """
    store = ProvenanceStore()
    for zone in RESOURCE:
        text = store.quote(uninc.zones[zone].values["quadplex_allowed"].prov.quote)
        assert "no building, structure or land shall be used" in text.lower(), zone
        assert "the uses listed in" in text, zone


def test_the_forest_zone_defines_its_way_out_of_the_question(
    uninc: Layer,
) -> None:
    """CFU lists three dwellings and defines all three as detached.

    39.4070(B) is the residential entry and it names sections rather than
    building types -- 39.4085, 39.4090, 39.4095 -- so the answer is only in
    the article's definitions, which is why they are inside the citation.
    """
    text = ProvenanceStore().quote(
        uninc.zones["CFU"].values["quadplex_allowed"].prov.quote
    )
    assert text.lower().count("single") >= 3
    assert "detached dwelling in the CFU zoning" in text
    assert "The following dwellings:" in text


def test_the_farm_zone_prints_this_building_and_the_encoding_says_so(
    uninc: Layer,
) -> None:
    """The one relief in the four, and it is a real sentence in a real code.

    An accessory farm dwelling sited away from the primary farm dwelling may
    be "attached multi-unit residential structures allowed by the applicable
    state building code". Refusing EFU flat would have been the easy read and
    the wrong one.
    """
    held = uninc.zones["EFU"].values["quadplex_allowed"]
    assert held.value is False
    assert len(held.variants) == 1

    variant = held.variants[0]
    assert variant.value is True
    assert set(variant.when) == {"farm_labor_housing", "review_use"}

    text = ProvenanceStore().quote(variant.prov.quote)
    assert "attached" in text
    assert "multi-unit residential structures" in text
    assert "ORS 658.750" in text


def test_the_farm_labor_door_costs_both_a_commitment_and_a_procedure(
    rules: RuleSet,
) -> None:
    """Either half alone leaves the zone shut.

    The commitment without the county's decision is a building nobody
    approved; the decision without the commitment is a permit for a use the
    applicant is not making. Both are registered conditions, neither is
    assumed, so a batch screen never reaches the true.
    """
    assert rules.resolve(UNINC, "EFU", POD).values["quadplex_allowed"].value is False
    assert (
        rules.resolve(UNINC, "EFU", (*POD, "farm_labor_housing"))
        .values["quadplex_allowed"]
        .value
        is False
    )
    assert (
        rules.resolve(UNINC, "EFU", (*POD, "review_use"))
        .values["quadplex_allowed"]
        .value
        is False
    )

    opened = rules.resolve(UNINC, "EFU", (*POD, "farm_labor_housing", "review_use"))
    assert opened.values["quadplex_allowed"].value is True


def test_a_review_use_is_not_a_conditional_use(uninc: Layer) -> None:
    """MCC lists both, in different sections, with different findings.

    39.4225 is REVIEW USES and 39.4230 is CONDITIONAL USES; the EFU relief
    comes from the first. Folding one into the other would report a cost the
    county does not charge, so the registry carries both names.
    """
    review = CONDITIONS["review_use"]
    assert review.kind == "relief"
    assert review.tier is Tier.discretionary
    assert review.name != "conditional_use"

    variant = uninc.zones["EFU"].values["quadplex_allowed"].variants[0]
    assert "conditional_use" not in variant.when


def test_farm_labor_housing_is_elective_and_never_assumed(uninc: Layer) -> None:
    """It is a business decision with a price, not a fact about the parcel.

    Registered farm labor housing needs a working farm, a primary dwelling on
    the tract, farm-worker occupancy, and removal or conversion when the
    housing is no longer required. Nothing about the lot settles any of that.
    """
    elective = CONDITIONS["farm_labor_housing"]
    assert elective.kind == "elective"
    assert elective.assume is None
    assert elective.tier is None
    assert "ORS 658.750" in elective.describe


def test_the_forest_zone_reaches_residential_use_three_ways_and_one_type(
    uninc: Layer,
) -> None:
    """MUF's citation carries all three doors on purpose.

    39.4705(E) on 38 acres, 39.4707(A) in conjunction with a forest use on
    ten, 39.4710(C) as a conditional use on land incapable of sustaining
    either. Three acreages, three procedures, one building -- and quoting one
    of them would leave the encoding looking like it had missed the others.
    """
    text = ProvenanceStore().quote(
        uninc.zones["MUF19"].values["quadplex_allowed"].prov.quote
    )
    # Two of the three print "single-family"; 39.4705(E) hyphenates across the
    # line break, which is why the count is taken on the half that survives.
    assert text.count("family dwelling") == 3
    assert "38 acres or more" in text
    assert "not in conjunction with" in text


def test_the_agriculture_zone_carries_the_largest_block_in_the_ledger(
    uninc: Layer,
) -> None:
    """251 lots, answered by eight lines of code text.

    MUA-20's review and conditional lists reach an accessory dwelling unit
    "attached to or located within" the single family dwelling, which is the
    nearest this zone comes to the pod and is one unit rather than four. The
    note records the dimensions so the reading is checkable.
    """
    text = ProvenanceStore().quote(
        uninc.zones["MUA20"].values["quadplex_allowed"].prov.quote
    )
    assert "single" in text and "family dwelling on a Lot of Record" in text

    notes = uninc.zones["MUA20"].notes or ""
    assert "Twenty-acre minimum lot" in notes
    assert "35 feet of height" in notes


def test_the_farm_zone_states_its_lot_minimum_in_the_unit_the_code_uses(
    uninc: Layer,
) -> None:
    """80 acres, and 3,484,800 square feet appears in the article nowhere.

    Rural Oregon writes lot minimums in acres and only in acres. The file
    carries the acreage a reader can find and the loader does the arithmetic,
    which is the same bargain LR-7 strikes with "5,000 square feet for each
    dwelling unit" two zones down in this layer.
    """
    held = uninc.zones["EFU"].values["min_lot_sqft"]
    assert held.acres == 80
    assert held.value == 80 * 43_560

    text = ProvenanceStore().quote(held.prov.quote)
    assert "80" in text
    assert "3,484,800" not in text and "3484800" not in text


def test_the_farm_zone_yard_row_is_read_across_not_down(uninc: Layer) -> None:
    """One printed line -- "30 10 30 30" -- under "Front Side Street Side Rear".

    Four columns off one row, taken together, because a row read one column at
    a time is how a setback gets attributed to the wrong lot line. The street
    side number matching the front number rather than the side number is what
    makes the ordering checkable.
    """
    efu = uninc.zones["EFU"]
    assert efu.values["setback_front_ft"].value == 30
    assert efu.values["setback_side_ft"].value == 10
    assert efu.values["setback_street_side_ft"].value == 30
    assert efu.values["setback_rear_ft"].value == 30

    text = ProvenanceStore().quote(efu.values["setback_side_ft"].prov.quote)
    assert "Front Side Street Side Rear" in text
    assert "30 10 30 30" in text


def test_the_farm_zone_records_the_waiver_a_buyer_would_want_to_know_about(
    uninc: Layer,
) -> None:
    """39.4240 binds successors in interest, and no field holds it.

    Every single family dwelling approved in EFU comes with a recorded
    document waiving claims alleging injury from farming or forest practices.
    It is not a dimensional standard and it does not change the verdict; it is
    exactly the kind of thing a screen that only emits numbers loses.
    """
    notes = uninc.zones["EFU"].notes or ""
    assert "39.4240" in notes
    assert "waiver" in notes.lower()


def test_the_resource_citations_all_point_at_their_own_sentence(
    uninc: Layer,
) -> None:
    ready = readiness_for(uninc, store=ProvenanceStore())
    assert ready.no_evidence == ()
    assert ready.misquoted == ()
