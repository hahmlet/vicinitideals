"""The county chapter every base zone points at and none of them states.

Twenty-three zone articles in MCC Chapter 39 print one sentence about parking
-- "off-street parking and loading shall be provided as required by MCC 39.6500
through 39.6600" -- and until 2026-08-30 the chapter behind it had never been
opened. It holds a nine by eighteen stall, a twenty-five foot aisle, a twenty
foot driveway and a rule about which yard a car may stand in, and behind those
sat 1,578 pod-fitting lots no site plan could draw on.

Three things here run opposite to the two cities read just before it. Multnomah
County's multi-unit noun starts at THREE dwelling units where Troutdale's and
Gladstone's start at five, so the pod is squarely an Apartment rather than
squeezed into a quadplex row. Its parking chapter needed no scoping argument at
all -- 39.6555(A) excludes single-family and two-family and stops. And its open
space reserve turns on how a use is APPROVED rather than on what it is: a
multiplex is a conditional use in LR-7, a conditional use gets design review,
and design review carries a rule the parking chapter never mentions.

The last of those was found the way it should be found -- by following a
redirect out of the chapter being read, which is the check that exists because
of the Portland aisle.
"""

from __future__ import annotations

import pytest

from flats.encode.load import load_trusted
from flats.encode.refusals import refusals
from flats.provenance.store import ProvenanceStore
from flats.rules.fields import DWELLINGS
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

COUNTY = "or/multnomah/_unincorporated"
PARKING = "or/multnomah/_unincorporated/39.parking.txt"
REVIEW = "or/multnomah/_unincorporated/39.design-review.txt"
DEFINITIONS = "or/multnomah/_unincorporated/39.2000.definitions.txt"

#: Every zone the pod could stand in that now borrows its parking setback.
BORROWERS = ("MR4", "R5", "R7", "R10", "R20", "LR7")


@pytest.fixture(scope="module")
def county() -> Layer:
    return load_rules()[COUNTY]


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


@pytest.fixture(scope="module")
def corpus() -> RuleSet:
    return RuleSet(load_trusted(strict=False).layers)


def _lines(store: ProvenanceStore, doc: str) -> list[str]:
    return store.load(doc).text.splitlines()


def test_the_scope_sentence_needed_no_argument_and_that_is_the_exception(
    store: ProvenanceStore,
) -> None:
    """39.6555(A), and it is the shortest scoping question in this corpus.

    Gladstone's dimensional sections open on developments "subject to design
    review" and had to be reconciled with a broader applicability clause;
    Troutdale's took a definition and a count. This one names the two buildings
    it does not reach and stops, and a quadplex is neither of them in either
    kind of base zone.
    """
    lines = _lines(store, PARKING)

    assert lines[172].startswith("§ 39.6555 DESIGN STANDARDS: SCOPE")
    assert "shall apply to all parking, loading, and" in lines[174]
    assert "maneuvering areas except those serving a single" in lines[175]
    assert "family dwelling on an individual lot in a rural" in lines[176]
    assert "family or a two-family dwelling in an urban" in lines[178]

    assert DWELLINGS == 4


def test_the_multi_unit_noun_starts_one_unit_below_this_building_not_above_it(
    store: ProvenanceStore, county: Layer
) -> None:
    """39.2000, and it is the mirror image of the last two cities read.

    Troutdale and Gladstone both define their multi-unit dwelling as five or
    more households, so a quadplex falls out of the noun and has to be found in
    a row that names it. Multnomah County defines an Apartment as three or
    more, so the pod falls INTO the noun and 39.6590(A)(3) is simply its row.
    Same word-counting motion, opposite result, and the number encoded comes
    from it.
    """
    definitions = _lines(store, DEFINITIONS)
    assert definitions[187].startswith("Apartment – Any building or portion thereof")
    assert "three or more dwelling" in definitions[188]

    rows = _lines(store, PARKING)
    assert rows[482] == "(3) Apartment – One and one-half"
    assert rows[483] == "spaces for each dwelling unit."

    assert county.defaults["parking_min_per_unit"].value == 1.5


def test_six_spaces_asked_and_four_allowed_and_the_gap_is_a_state_rule(
    corpus: RuleSet,
) -> None:
    """What the county asks, what OAR 660-046 lets it ask, and which way we err.

    One and a half spaces per unit is six for this pod. The state caps
    quadplex parking at four in total, carried in `or/_state.yaml` as
    `preempts: cap`, so the resolver clips six back to one per unit. That cap
    reaches unincorporated county land only where it sits inside an urban
    service district -- a line no parcel record here carries -- so if the test
    fails the true requirement is six and this screen is using four.

    Encoding the row anyway is still strictly better than leaving it out: with
    the field absent the cap resolves alone and the answer is four regardless.
    This test exists to keep that asymmetry visible rather than to defend the
    four.
    """
    asked = 1.5 * DWELLINGS
    assert asked == 6

    for zone in ("LR7", "R20", "MR4"):
        allowed = corpus.resolve(COUNTY, zone).get("parking_min_per_unit")
        assert allowed * DWELLINGS == 4, (
            f"{zone}: the state cap should clip the county's six to four"
        )


def test_the_aisle_ties_troutdale_for_the_widest_in_the_corpus(
    county: Layer, store: ProvenanceStore
) -> None:
    """39.6565(B)(1): twenty-five feet at ninety degrees, stated once.

    Not split by direction, so a one-way rear court is dimensioned off it the
    way Fairview's, West Linn's, Troutdale's and Gladstone's are. A stall row,
    its aisle and a second stall row come to sixty-one feet of depth before a
    driveway reaches them -- the deepest court this corpus asks for, shared
    with Troutdale and four feet more than Gresham.
    """
    lines = _lines(store, PARKING)
    assert lines[259] == " (B) Aisle width shall be not less than:"
    assert lines[260] == "(l) 25 feet for 90 degree parking,"

    assert county.defaults["parking_aisle_one_way_ft"].value == 25
    assert county.defaults["parking_aisle_two_way_ft"].value == 25

    depth = county.defaults["parking_stall_depth_ft"].value
    assert depth + 25 + depth == 61

    widest = {
        layer_id: layer.defaults["parking_aisle_two_way_ft"].value
        for layer_id, layer in load_rules().items()
        if "parking_aisle_two_way_ft" in layer.defaults
    }
    assert sorted(k for k, v in widest.items() if v == max(widest.values())) == [
        COUNTY,
        "or/multnomah/troutdale",
    ]


def test_the_stall_is_the_seventy_percent_row_and_the_rest_may_be_smaller(
    county: Layer, store: ProvenanceStore
) -> None:
    """39.6565(A)(1), and the 70% in front of it is not a qualification.

    "At least 70% of the required off-street parking spaces shall have a
    minimum width of nine feet, a minimum length of 18 feet." The other end of
    that percentage is (A)(2)'s compact allowance -- up to 30% at eight and a
    half by sixteen -- so a court drawn entirely at nine by eighteen satisfies
    the section whatever the ratio, and the compact half is refused as a
    loosening rather than read as a limit.
    """
    lines = _lines(store, PARKING)
    assert "minimum width of nine feet, a minimum" in lines[244]
    assert "length of 18 feet, and a minimum" in lines[245]

    assert county.defaults["parking_stall_width_ft"].value == 9
    assert county.defaults["parking_stall_depth_ft"].value == 18


def test_the_drive_to_a_rear_court_is_twenty_feet_and_there_is_no_one_way_figure(
    county: Layer, store: ProvenanceStore
) -> None:
    """39.6560(A), written for exactly the plat this screen draws.

    "Where a parking or loading area does not abut directly on a public street
    ... there shall be provided an unobstructed driveway not less than 20 feet
    in width for two-way traffic." A rear court behind a building does not abut
    the street. Twenty feet of side yard for the depth of the lot, matching
    Happy Valley, which was the hardest number in this family until West Linn.

    The one-way field stays out on purpose: the sentence conditions the twenty
    on two-way traffic and the chapter never dimensions a single lane.
    """
    lines = _lines(store, PARKING)
    assert "driveway not less than 20 feet in width for two-" in lines[195]

    assert county.defaults["driveway_min_width_two_way_ft"].value == 20
    assert "driveway_min_width_one_way_ft" not in county.defaults


def test_the_chapter_states_no_maximum_and_absence_is_the_encoding(
    county: Layer, store: ProvenanceStore
) -> None:
    """`exempt: true` would be a claim the county never made.

    Gladstone prints "Max: None" against the row in a chapter that splits the
    city in two for the purpose of the maxima -- a ceiling read and found
    empty. Multnomah County never had the thought: the word "maximum" occurs
    nowhere in 39.6500 through 39.6600, there is no ceiling table and no
    exempt space type. Absence is the honest encoding, and `or/_state.yaml`
    holds no parking ceiling either, so it resolves to none.
    """
    text = "\n".join(_lines(store, PARKING)).lower()
    for never in ("maximum", "shall not exceed", "no more than"):
        assert never not in text, f"the parking chapter does say {never!r}"

    assert "parking_max_per_unit" not in county.defaults


def test_the_county_never_wrote_hb_2001_into_its_zoning_code(
    store: ProvenanceStore, county: Layer
) -> None:
    """No quadplex, no triplex, no middle housing, anywhere in Chapter 39.

    Every city in this corpus restated the state's middle-housing rules in its
    own words somewhere, which is where most of the encoded parking quantities
    came from. The county did not, and that is consistent with OAR
    660-046-0020(8) reaching unincorporated land only inside an urban service
    district boundary. It is also why 39.6590(A)(3)'s Apartment row is the only
    row there is: there is no middle-housing row to prefer over it.
    """
    words = ("middle housing", "quadplex", "fourplex", "triplex")
    for doc in county.code:
        if not doc.id.startswith("39."):
            continue
        text = store.load(f"{COUNTY}/{doc.id}.txt").text.lower()
        for word in words:
            assert word not in text, f"{doc.id} says {word!r} after all"


def test_the_parking_setback_borrows_the_front_yard_and_the_ten_foot_floor_is_inert(
    county: Layer, store: ProvenanceStore, corpus: RuleSet
) -> None:
    """39.6580(A) states it, and 39.8045(C)(3)(b) floors it at ten.

    The first sentence carries no number -- "any required yard which abuts upon
    a street lot line shall not be used for a parking or loading space" -- so it
    is borrowed with `same_as`, the third city in this corpus to state the rule
    that way. The redirect out of 39.6585(A) prints a ten-foot landscaped strip
    for the same edge, and the smallest front setback in this layer is R5's ten:
    equal, not larger. So no `floor_ft` is carried, and this is the test that
    goes red the day a zone here drops under ten.
    """
    lines = _lines(store, PARKING)
    assert lines[432].startswith(" (A) Any required yard which abuts upon a")
    assert "shall not be used for a parking or" in lines[433]

    strip = _lines(store, REVIEW)
    assert "adjacent to a street by a landscaped" in strip[289]
    assert "strip at least 10 feet in width, and" in strip[290]

    for zone in BORROWERS:
        held = county.zones[zone].values["parking_street_setback_ft"]
        assert held.same_as == "setback_front_ft"
        assert held.floor_ft is None
        resolved = corpus.resolve(COUNTY, zone).get("parking_street_setback_ft")
        assert resolved >= 10, (
            f"{zone}: the borrowed setback is {resolved} ft and the landscaped "
            "strip 39.6585(A) redirects to asks ten -- the floor is no longer "
            "inert and belongs in the value"
        )


def test_both_refused_parking_setbacks_are_swallowed_by_the_narrowest_yard(
    county: Layer, store: ProvenanceStore
) -> None:
    """Three feet of curb and five feet of planting, along every other lot line.

    39.6570(B)(2) wants a four-inch curb at least three feet off the lot line;
    39.8045(C)(3)(b), one section and one redirect away, wants five feet of
    landscaping along the same line. This model holds one parking setback and it
    is measured from a street, so the side and rear halves of both are refused.

    They are inert only because the smallest side and rear yards in this layer
    are five feet -- EQUAL to the larger of the two, which is the narrowest
    margin any refusal in this corpus rests on. A zone here with a four-foot
    side yard would make the refusal cost something, and this is where it shows.
    """
    strip = _lines(store, REVIEW)
    assert "any other lot line by a landscaped" in strip[291]
    assert "strip at least 5 feet in width." in strip[292]

    for name, zone in county.zones.items():
        for field in ("setback_side_ft", "setback_rear_ft"):
            value = zone.values.get(field)
            if value is None or value.value is None:
                continue
            assert float(value.value) >= 5, (
                f"{name}.{field} is {value.value}, under the five feet of "
                "planting a parking area owes every non-street lot line -- the "
                "side/rear halves of 39.6570(B)(2) and 39.8045(C)(3)(b) are "
                "refused in this layer and would now be binding"
            )


def test_lr7_owes_an_open_space_reserve_because_of_how_its_use_is_approved(
    county: Layer, store: ProvenanceStore
) -> None:
    """Four links, no judgement in any of them, and no other zone owes it.

    39.4856(C) makes a multiplex a CONDITIONAL use in LR-7. 39.8020(A) applies
    design review to conditional uses in any base zone. 39.8020(B) would let a
    use needing fewer than four new spaces off with four criteria, and this one
    needs six under 39.6590, so 39.8020(C) applies all of 39.8045. And
    39.8045(A)(2) asks shared outdoor recreation space of any apartment
    residential development.

    MR-4 permits the pod outright, so design review never starts there; the
    Portland-administered pockets are governed by PCC. LR-7 is the only zone in
    this layer where the chain closes.
    """
    review = _lines(store, REVIEW)
    assert "through 39.8050 shall apply to all conditional" in review[44]
    assert "and community service uses, and to specified" in review[45]
    assert "require the creation of fewer than four new" in review[48]
    assert "Design Review Approval Criteria listed in MCC" in review[56]
    assert "guests in any apartment residential" in review[252]

    # Six under the county's own row, which is what 39.8020(B) measures.
    assert county.defaults["parking_min_per_unit"].value * DWELLINGS == 6

    lr7 = county.zones["LR7"]
    assert lr7.values["quadplex_allowed"].value is False
    assert [v.when for v in lr7.values["quadplex_allowed"].variants] == [("conditional_use",)]

    reserve = lr7.values["open_space_min_sqft"]
    assert reserve.per_dwelling == 300
    assert reserve.value == 1200

    for elsewhere in ("MR4", "R5", "R7", "R10", "R20"):
        assert "open_space_min_sqft" not in county.zones[elsewhere].values


def test_the_loading_space_rounds_itself_out_of_existence(
    store: ProvenanceStore,
) -> None:
    """39.6595(D) against 39.6550(B), and the answer is zero.

    An Apartment use owes "one loading space for each 50 dwelling units". Four
    units is eight hundredths of a space, and 39.6550(B) disregards "any
    fraction up to and including one-half". So the twelve by twenty-five foot
    rectangle in 39.6565(C)(1) is never drawn -- which matters, because it is
    larger than any parking stall in this corpus and there is no field that
    would have stopped it.
    """
    lines = _lines(store, PARKING)
    assert lines[668].startswith(" (D) Apartment Uses shall have at least: One")
    assert lines[669] == "loading space for each 50 dwelling units."
    assert "up to and including one-half shall be" in lines[168]
    assert "disregarded" in lines[169]

    owed = DWELLINGS / 50
    assert owed <= 0.5
    assert round(owed - 0.5) <= 0


def test_the_chapter_refused_nearly_twice_what_it_kept() -> None:
    """Eleven refusals against six values, out of one chapter and one redirect.

    The most lopsided reading in this corpus so far, and the ratio is the
    point rather than the count: a county chapter written for every building in
    the county states a great deal this model has no field for, and none of it
    was quietly dropped. Counted here as well as in the corpus-wide census so
    that a refusal deleted from this layer fails a test named after this layer.
    """
    mine = [r for r in refusals() if r.kind == "comments" and r.where == COUNTY]
    parking = [r for r in mine if "39.6" in r.text or "39.80" in r.text]
    assert len(parking) == 11
    assert len(load_rules()[COUNTY].defaults) == 6
