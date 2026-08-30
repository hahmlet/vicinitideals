"""The city that settles "is a quadplex multifamily?" by counting.

Troutdale is the seventh city this corpus can dimension, and it is the one that
makes the reading trivial where West Linn made it hard. West Linn never defines
"multifamily", so a quadplex becomes multifamily there by elimination and takes
the 24-foot service drive. Troutdale defines it: "Dwelling, Multi-Family. A
building with five (5) or more dwelling units", two lines above "Dwelling,
Quadplex. A building with four (4) dwelling units on a lot or parcel in any
configuration." Four is not five or more. Every multi-family row in Chapter 9
belongs to somebody else, and the pod takes the Triplex and Quadplex row.

The second thing worth pinning is what the middle-housing invalidation does NOT
reach. TDC 8.120.C.1.b.ii voids "design standards other than those in this
Subsection C. that apply only to triplexes, quadplexes, or multifamily
development" -- the sentence that took Milwaukie's aisle table away from this
building. Troutdale's 9.115 opens "The following off-street parking development
and maintenance shall apply in all cases", so it survives, and 3,431 lots get
laid out to a 25-foot aisle instead of nothing at all.

The third is that the same parking requirement is stated twice, in two
chapters, banded on two different measures, by one ordinance. Chapter 9 bands
on the lot's own area; 8.120.B.3.a bands on the ZONE's minimum lot size. The
corpus encodes the first and the state cap disposes of the second, and this
file pins the arithmetic that makes that safe rather than convenient.
"""

from __future__ import annotations

import pytest

from flats.encode.refusals import refusals
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer

pytestmark = pytest.mark.unit

TROUTDALE = "or/multnomah/troutdale"
PARKING = "or/multnomah/troutdale/9.parking.txt"
STANDARDS = "or/multnomah/troutdale/8.development-standards.txt"
DEFINITIONS = "or/multnomah/troutdale/1.020.definitions.txt"

#: The zones that permit this building, and the front setback each one lends to
#: the parking setback under 9.095(D).
QUADPLEX_ZONES = {"MU-2": 15, "MU-3": 20, "LDR-1": 10, "LDR-2": 10, "MDR": 10, "HDR": 20}


@pytest.fixture(scope="module")
def troutdale() -> Layer:
    return load_rules()[TROUTDALE]


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


def _lines(store: ProvenanceStore, doc: str) -> list[str]:
    return store.load(doc).text.splitlines()


def test_a_quadplex_is_not_multifamily_here_and_the_code_says_so_with_a_number(
    store: ProvenanceStore,
) -> None:
    """The definition that does in one line what West Linn took a page to infer.

    This is load-bearing in the opposite direction from West Linn's. There, the
    multifamily branch was the strict one and the reading failed the pod out.
    Here it does not apply at all, which means Table 1's "1 space per dwelling
    unit" multi-family minimum is somebody else's row, and so are 9.090's
    bicycle standards and 9.050's EV conduit -- all three written for
    multi-family developments and all three starting at five units.
    """
    lines = _lines(store, DEFINITIONS)

    assert lines[291].startswith("Dwelling, Multi-Family.")
    assert "five (5) or more dwelling units" in lines[291]
    assert lines[293].startswith("Dwelling, Quadplex.")
    assert "four (4) dwelling units on a lot or parcel" in lines[293]

    # And the pod is four. The count is the whole argument.
    from flats.rules.fields import DWELLINGS

    assert DWELLINGS == 4


def test_the_middle_housing_invalidation_does_not_reach_the_parking_geometry(
    store: ProvenanceStore,
) -> None:
    """The sentence that killed Milwaukie's aisle, and why it misses here.

    8.120.C.1.b.ii voids standards that apply ONLY to triplexes, quadplexes or
    multifamily development. 9.115 applies "in all cases" and 9.080 carves out
    single- and two-family dwellings rather than middle housing, so neither is
    a standard aimed at this building and neither is voided. Pinned because the
    difference between Troutdale and Milwaukie is one clause of one sentence,
    and getting it backwards either draws a city to nobody's numbers or refuses
    to draw one it could.
    """
    standards = _lines(store, STANDARDS)
    assert "invalid and do not apply to triplexes or quadplexes" in standards[522]
    assert "apply only to triplexes, quadplexes, or multifamily development" in (
        standards[569]
    )

    parking = _lines(store, PARKING)
    assert parking[573].startswith("9.115  Design Requirements for Off-Street Parking.")
    assert parking[575].strip() == (
        "The following off-street parking development and maintenance shall apply "
        "in all cases:"
    )


def test_the_stall_is_nine_by_eighteen_and_the_table_checks_its_own_arithmetic(
    troutdale: Layer, store: ProvenanceStore
) -> None:
    """9.115(A)(1), with 162 square feet printed beside it as the check."""
    assert troutdale.defaults["parking_stall_width_ft"].value == 9
    assert troutdale.defaults["parking_stall_depth_ft"].value == 18

    line = " ".join(_lines(store, PARKING)[579:581])
    assert "nine (9) feet by eighteen (18) feet" in line
    assert "one" in line and "hundred sixty-two (162) square feet" in line
    assert 9 * 18 == 162


def test_twenty_five_feet_is_the_widest_aisle_in_the_corpus() -> None:
    """One figure, no direction split, and nobody asks for more than this.

    Fairview asks 24, Gresham and West Linn 23, Portland 20. Troutdale's 25 is
    the number that decides how many of its 3,431 pod-fitting lots can seat two
    rows of stalls, so it is pinned against the field rather than on its own: a
    later reading that quietly makes some other city wider has to come here and
    say so.

    One did, the next day but one. MCC 39.6565(B)(1) asks 25 feet at ninety
    degrees for unincorporated Multnomah County, and the assertion is now a tie
    rather than a superlative -- which is the check working, not failing. Both
    are one figure stated once and not split by direction, and both make a rear
    court sixty-one feet deep before a driveway reaches it.
    """
    layers = load_rules()
    widest: dict[str, float] = {}
    for layer_id, layer in layers.items():
        for field in ("parking_aisle_one_way_ft", "parking_aisle_two_way_ft"):
            value = layer.defaults.get(field)
            if value is not None and value.value is not None:
                widest[layer_id] = max(widest.get(layer_id, 0), float(value.value))

    assert widest[TROUTDALE] == 25
    assert max(widest.values()) == 25
    assert sorted(k for k, v in widest.items() if v == 25) == [
        "or/multnomah/_unincorporated",
        TROUTDALE,
    ]


def test_the_driveway_is_the_general_figure_not_the_single_family_one(
    troutdale: Layer, store: ProvenanceStore
) -> None:
    """9.080(A) against 9.080(B), and the pod is on the wrong side of (B).

    (A) improves a driveway to an off-street parking area at 20 feet two-way
    and 12 one-way. (B) drops it to 10 for "a single-family or two-family
    dwelling". A quadplex is neither -- 1.020 defines all three by unit count
    -- so the ten never applies, and the branch not taken is pinned here
    because it is the looser one and the one a hurried reading would take.
    """
    assert troutdale.defaults["driveway_min_width_two_way_ft"].value == 20
    assert troutdale.defaults["driveway_min_width_one_way_ft"].value == 12

    lines = _lines(store, PARKING)
    assert lines[435].startswith("9.080  Driveways.")
    general = " ".join(lines[437:441])
    assert "twenty (20) feet for a two-way drive" in general
    assert "twelve (12) feet for a" in general and "one-way drive" in general

    exception = " ".join(lines[442:444])
    assert "single-family or two-family dwelling" in exception
    assert "ten (10)" in exception


def test_the_curb_cut_is_capped_and_never_floored(
    troutdale: Layer, store: ProvenanceStore
) -> None:
    """8.120.C.5.a caps all approaches at 32 feet per frontage. Nothing floors.

    The mirror image of West Linn, which states both ends and is the only city
    here where a pod cannot economise its opening down to a single-car width.
    Absence is the claim being made, so it is checked against the corpus rather
    than left implicit.
    """
    assert troutdale.defaults["driveway_approach_max_width_ft"].value == 32
    assert "driveway_approach_min_width_ft" not in troutdale.defaults

    line = " ".join(_lines(store, STANDARDS)[605:608])
    assert "total width of all driveway approaches must not exceed thirty-two (32)" in (
        line
    )
    # The sentence wraps mid-phrase in the PDF text, so the halves are checked
    # separately rather than stitched into a phrase the page does not carry.
    assert "feet per" in line and "frontage, as measured at the property line" in line


def test_front_parking_is_capped_at_half_the_frontage_and_not_banned(
    troutdale: Layer, store: ProvenanceStore
) -> None:
    """A ban and a cap are not the same rule, and this one is a cap.

    8.120.C.4.b reads like Portland's outright ban until the next two
    subsections except a parking area separated from the street by a dwelling
    OR one at half the street frontage or less. Encoding the ban would invent a
    red on a lot the code lets through, so `parking_front_prohibited` stays
    empty and the fifty percent is what binds.

    The cross-reference in (b) points at "Subsections a. and b. of this
    Subsection C.4." -- a. is "garages and carports are not required" and b. is
    the ban itself. Troutdale re-lettered the state model code's a/b pair to
    c/d and left the pointer behind. Pinned so that a later reader who notices
    the broken pointer does not conclude the exceptions are unreachable.
    """
    assert troutdale.defaults["parking_area_max_frontage_pct"].value == 50
    assert "parking_front_prohibited" not in troutdale.defaults

    lines = _lines(store, STANDARDS)
    assert "shall not be located between a building and a" in lines[597]
    assert "Subsections a. and b. of this Subsection C.4." in lines[599]
    assert lines[596].strip().startswith("a.")
    assert lines[600].strip().startswith("c.")
    assert lines[602].strip().startswith("d.")
    assert "fifty percent (50%) of the street frontage" in lines[603]


def test_the_quantity_bands_are_the_states_and_never_exceed_its_cap(
    troutdale: Layer,
) -> None:
    """Table 1 copies OAR 660-046-0220(2)(e)(B) band for band.

    Four counts on four lot-size bands, and the corpus already holds the state
    version as a `preempts: cap`. If Troutdale's copy ever drifted above the
    cap -- or a future edit flattened the bands the way the state's own
    encoding was once flattened -- the city would be asking for more than any
    Large City may ask, and this is where that shows up.
    """
    city = troutdale.defaults["parking_min_per_unit"]
    state = load_rules()["or"].defaults["parking_min_per_unit"]

    assert city.spaces_total == 4
    assert state.spaces_total == 4

    def bands(value: object) -> list[tuple[float | None, float | None, float]]:
        out = [(None, None, float(value.spaces_total))]
        for variant in value.variants:
            band = variant.band
            out.append((band.at_least, band.less_than, float(variant.spaces_total)))
        return sorted(out, key=lambda row: row[2])

    assert bands(city) == bands(state)
    assert [row[2] for row in bands(city)] == [1, 2, 3, 4]


def test_the_chapter_eight_banding_is_refused_and_the_state_cap_covers_it(
    store: ProvenanceStore,
) -> None:
    """The same requirement, twice, on two measures, by one ordinance.

    8.120.B.3.a bands on the ZONE's minimum lot size; 9.010 Table 1 bands on
    the lot's own area. No `Band.measure` can hold the first -- LOT_MEASURES is
    lot_sqft, lot_width_ft and lot_depth_ft, and a zone minimum is a property
    of the district. Leaving it out is only safe because of the arithmetic
    below: 8.120 asks for MORE than Table 1 exactly when the lot is smaller
    than its own zone's minimum, and in that case it is asking for more than
    OAR 660-046-0220(2)(e)(B) permits, so the state cap already disposes of it.
    Where the zone minimum is the lower of the two, Table 1 is the stricter
    city standard and is the one encoded.
    """
    standards = _lines(store, STANDARDS)
    assert "In zones with a minimum lot size of less than five thousand (5,000)" in (
        standards[531]
    )
    assert "A minimum of four (4) off-street parking spaces per quadplex" in (
        standards[541]
    )

    parking = _lines(store, PARKING)
    assert parking[86].strip() == "Triplex and Quadplex"
    for offset, count in ((87, "1 space total"), (88, "2 spaces total"), (89, "3 spaces total")):
        assert count in parking[offset]
    assert "4 spaces total per quadplex" in parking[92]

    # Chapter 8's bands, by the zone minimum they key on. Troutdale's zones are
    # 10,000 / 7,000 / 5,000 and two mixed-use columns that state no area
    # standard at all -- a minimum of nothing, which is under 5,000.
    def chapter_eight(zone_min: float) -> int:
        if zone_min < 5000:
            return 2
        if zone_min < 7000:
            return 3
        return 4

    def table_one(lot_sqft: float) -> int:
        if lot_sqft < 3000:
            return 1
        if lot_sqft < 5000:
            return 2
        if lot_sqft < 7000:
            return 3
        return 4

    for zone_min in (0, 5000, 7000, 10000):
        for lot_sqft in (2500, 4000, 6000, 8000, 20000):
            if chapter_eight(zone_min) > table_one(lot_sqft):
                # The only region the two disagree in, and the state cap --
                # which is table_one -- is what a Large City may ask there.
                assert lot_sqft < zone_min or zone_min == 0


def test_the_refused_ledger_carries_every_standard_this_model_cannot_hold(
    troutdale: Layer,
) -> None:
    """Seven refusals against ten encoded values, and the ratio is the reading.

    The CFEC waiver is the big one: a lot within half a mile of a frequent
    transit corridor, or in the Town Center Overlay and a quarter mile beyond
    it, owes ZERO off-street parking and Table 1 never reaches it. Both are
    read off a delineation map no parcel record here carries, so every
    Troutdale lot is screened against the non-CFEC table -- conservative, and
    on the lots it is wrong about it charges the pod four stalls it does not
    owe.
    """
    mine = [
        refusal
        for refusal in refusals()
        if refusal.kind == "comments" and TROUTDALE in refusal.where
    ]
    # Six from this reading, plus the continuously-curved corner-lot figure
    # that was already here from the definitions read.
    assert len(mine) == 8

    text = " ".join(refusal.text for refusal in mine)
    for marker in (
        "banded on a differen",       # 8.120.B.3.a's zone-minimum measure
        "compact spaces",             # 9.115(A)(2)
        "not less than the full",     # 9.080(A)'s approach coupling
        "8.120.C.5.b and .c",         # spacing, classification, alley
        "9.095(A)",                   # the neighbour's setback
        "CFEC waiver",                # 9.005 and 9.035
        "on-street credit",           # 9.040 and 8.120.B.3.b
    ):
        assert marker in text, marker


def test_the_parking_setback_borrows_and_prints_no_figure_of_its_own(
    troutdale: Layer, store: ProvenanceStore
) -> None:
    """9.095(D) states a rule with no number in it, in six zones at once.

    The ten feet printed in the same sentence is an industrial-district floor
    and reaches none of the zones that permit this building, so unlike Happy
    Valley's 16.43.030.E.4 there is no floor to carry -- the borrowing is the
    whole of the standard. Every zone's answer equals its own front setback,
    which is the envelope the site plan already lays out inside, so the rule
    costs nothing and is still the law.
    """
    for zone, front in QUADPLEX_ZONES.items():
        values = troutdale.zones[zone].values
        value = values["parking_street_setback_ft"]
        assert value.same_as == "setback_front_ft"
        assert value.floor_ft is None
        assert values["setback_front_ft"].value == front

    line = _lines(store, PARKING)[539]
    assert "the same distance as required" in line
    assert not any(char.isdigit() for char in line.split("D.")[1])
