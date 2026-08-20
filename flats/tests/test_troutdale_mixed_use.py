"""Troutdale's mixed-use districts, where the table is mostly cross-references.

MU-2 and MU-3 are the first columns in this corpus whose dimensional standards
have to be assembled rather than read. Table 3.230.B prints "see 3.235.A" for
lot size, "see 3.235.B" for depth, "see 3.235.C.2" for the side yard and "see
3.235.C.5" for the rear -- four of the eight rows a screen needs, none of them
a number.

Three readings came out of assembling them, and each is pinned below.

The table has three columns and most of its setback rows print two numbers.
The row that explains why is "Minimum setbacks (ft): ... see 3.230.A", whose
lone entry sits in the MU-3 column: MU-3 takes its setbacks from the
NON-residential table, so the pairs belong to MU-1 and MU-2. That table does
not divide the yard into front, side and rear at all -- it states one setback
per neighbour -- so all three of MU-3's yards carry the same number.

3.235.C.2 states two figures for one yard: seven and a half feet of a
two-storey building from an adjoining SIDE yard and fifteen from an adjoining
REAR yard. Which applies is the neighbouring lot's orientation, which is not
in any parcel record, so the fifteen binds and the relief is named rather than
dropped. That is a different unmeasured fact from the neighbour's zoning, and
it needed a condition of its own.

And 3.235.A gives no lot-area standard at all. It says the minimum lot size
"shall be based on the minimum lot width and minimum lot depth standards",
which is a deferral to two rows that are already encoded. 15 by 70 is 1,050
square feet, but that figure appears nowhere in the Development Code and is
not written into a field the code never printed.
"""

from __future__ import annotations

import pytest

from flats.encode.readiness import readiness_for
from flats.provenance.store import ProvenanceStore
from flats.rules import conditions
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

TROUTDALE = "or/multnomah/troutdale"
#: What the pod is, every time it is screened: two storeys, and three of its
#: four side walls are shared.
POD = ("multi_story", "attached_wall")


@pytest.fixture(scope="module")
def troutdale() -> Layer:
    return load_rules()[TROUTDALE]


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


def test_the_two_mixed_use_columns_that_permit_the_building(
    troutdale: Layer,
) -> None:
    """Table 3.220 reads `Quadplex N P P`, and MU-1 was encoded as the N."""
    assert troutdale.zones["MU-2"].values["quadplex_allowed"].value is True
    assert troutdale.zones["MU-3"].values["quadplex_allowed"].value is True
    assert troutdale.zones["MU-1"].values["quadplex_allowed"].value is False


def test_no_lot_area_standard_because_the_code_defers_it(
    troutdale: Layer,
) -> None:
    """3.235.A hands the minimum lot size to the width and depth rows.

    Encoded exempt rather than as 15 x 70. The product is 1,050 square feet
    and it is correct arithmetic, but it is arithmetic -- the figure is in no
    section of the Development Code, and a derived number written into a
    quoted field stops being distinguishable from a read one. The width and
    depth it defers to are both encoded and both screened, so nothing is lost.
    """
    for zone in ("MU-2", "MU-3"):
        held = troutdale.zones[zone].values["min_lot_sqft"]
        assert held.exempt, zone
        assert held.value is None, zone
        assert troutdale.zones[zone].values["min_lot_width_ft"].value == 15, zone
        assert troutdale.zones[zone].values["min_lot_depth_ft"].value == 70, zone
    # And the deferral does not leave the district looking unread.
    for zone in ("MU-2", "MU-3"):
        assert RuleSet(load_rules()).resolve(TROUTDALE, zone).missing_required == ()


def test_the_side_yard_turns_on_the_neighbours_orientation(
    troutdale: Layer, rules: RuleSet
) -> None:
    """Fifteen feet binds, and seven and a half is what a side yard buys.

    3.235.C.2.b.ii asks 7.5 feet of a two-storey building "from an adjoining
    side yard" and 15 "from an adjoining rear yard" -- the same lot line, two
    numbers, decided by which way the lot on the far side faces. Nothing in
    the parcel record answers that, so the larger is the base. A lot at the end
    of a row, backing onto the rear of the lots on the perpendicular street, is
    exactly the case the fifteen is written for.
    """
    side = troutdale.zones["MU-2"].values["setback_side_ft"]
    assert side.value == 15
    relief = {v.when: v.value for v in side.variants}
    assert relief[("abuts_side_yard",)] == 5
    assert relief[("abuts_side_yard", "multi_story")] == 7.5
    # Unmeasured, so the base is what a screen sees today.
    assert conditions.condition("abuts_side_yard").assume is None
    assert rules.resolve(TROUTDALE, "MU-2", ("multi_story",)).values[
        "setback_side_ft"
    ].value == 15


def test_the_orientation_fact_is_not_the_zoning_fact(troutdale: Layer) -> None:
    """`abuts_side_yard` had to be registered; `abuts_nonresidential_zone`
    could not stand in for it.

    3.235.C.2 asks both questions of the same lot line and answers them
    differently: five feet flat against a non-residential or HDR district, and
    5 / 7.5 / 15 against a residential one depending on the neighbour's
    orientation. One is answerable from the zoning layer and the other is not
    answerable from anything this system holds.
    """
    assert conditions.condition("abuts_side_yard").kind == "site_fact"
    assert conditions.condition("abuts_nonresidential_zone").kind == "site_fact"
    side = troutdale.zones["MU-2"].values["setback_side_ft"]
    relief = {v.when: v.value for v in side.variants}
    assert relief[("abuts_nonresidential_zone",)] == 5


def test_the_pairs_that_could_tie_are_spelled_out(rules: RuleSet) -> None:
    """A two-storey building on an alley lot matches two variants at once.

    `multi_story` puts the rear yard at 20 and `abuts_alley` puts it at 5, both
    one condition deep, and the model refuses a tie rather than guessing --
    which would send the lot to UNKNOWN. There is nothing to guess: 3.235.C.5.b
    states the five with no storey step at all, so the pair is encoded.
    """
    for held, rear in (
        ((), 15),
        (("multi_story",), 20),
        (("multi_story", "abuts_alley"), 5),
        (("multi_story", "abuts_nonresidential_zone"), 10),
    ):
        res = rules.resolve(TROUTDALE, "MU-2", held)
        assert res.values["setback_rear_ft"].value == rear, held
        assert not getattr(res.values["setback_rear_ft"], "ambiguous", ()), held


def test_the_shared_wall_owes_no_yard_whatever_is_behind_it(
    rules: RuleSet,
) -> None:
    """The Building Side row of 3.230.B reads 0 in all three columns.

    Without it the pod is charged a side setback on each of its three interior
    walls. Paired against the neighbour's zoning for the same reason the rear
    variants are paired against the storey count.
    """
    for zone in ("MU-2", "MU-3"):
        assert rules.resolve(TROUTDALE, zone, POD).values["setback_side_ft"].value == 0
        both = rules.resolve(TROUTDALE, zone, (*POD, "abuts_nonresidential_zone"))
        assert both.values["setback_side_ft"].value == 0, zone
        assert not getattr(both.values["setback_side_ft"], "ambiguous", ()), zone


def test_the_front_yard_is_four_numbers_and_the_pod_takes_one(
    troutdale: Layer, rules: RuleSet
) -> None:
    """15 feet to the front façade, 10 with alley access, and a 20-foot garage.

    The porch rows -- 10 and 5 -- are a shallower standard for a projecting
    porch and are not the building line. The garage figure is stated only on
    the without-alley line, which is what a code does when the garage comes off
    the alley instead.
    """
    held = troutdale.zones["MU-2"].values
    assert held["setback_front_ft"].value == 15
    assert held["setback_garage_entrance_ft"].value == 20
    alley = rules.resolve(TROUTDALE, "MU-2", ("multi_story", "abuts_alley"))
    assert alley.values["setback_front_ft"].value == 10


def test_the_east_district_takes_its_setbacks_from_the_other_table(
    troutdale: Layer, rules: RuleSet
) -> None:
    """MU-3's residential setback cell reads "see 3.230.A".

    3.230.A is the NON-residential table and it names no front, side or rear:
    it states one setback by what the lot abuts -- 20 feet against a
    residential district, 0 against a non-residential one. So all three yards
    carry the same number, which is the opposite shape from MU-2 next door.
    """
    held = troutdale.zones["MU-3"].values
    assert (
        held["setback_front_ft"].value,
        held["setback_side_ft"].value,
        held["setback_rear_ft"].value,
    ) == (20, 20, 20)
    open_side = rules.resolve(TROUTDALE, "MU-3", ("abuts_nonresidential_zone",))
    assert open_side.values["setback_front_ft"].value == 0
    assert open_side.values["setback_rear_ft"].value == 0
    # MU-2 does not behave that way: screened as the pod actually is, its
    # three yards are three different numbers off three different rows.
    mu2 = rules.resolve(TROUTDALE, "MU-2", POD).values
    assert (
        mu2["setback_front_ft"].value,
        mu2["setback_side_ft"].value,
        mu2["setback_rear_ft"].value,
    ) == (15, 0, 20)


def test_the_district_that_fixes_the_building_line_rather_than_bounding_it(
    troutdale: Layer,
) -> None:
    """A 20-foot minimum front setback and a 20-foot maximum, in one column.

    Read together they leave one legal front setback in MU-3 on a lot abutting
    a residential district. `setback_front_max_ft` is stated nowhere else in
    this city.
    """
    held = troutdale.zones["MU-3"].values
    assert held["setback_front_max_ft"].value == 20
    assert held["setback_front_ft"].value == 20
    assert "setback_front_max_ft" not in troutdale.zones["MU-2"].values


def test_the_east_district_grants_no_height_by_right(troutdale: Layer) -> None:
    """3.235.D: everything up to 55 feet takes a Type II site development
    review, and 55 to 75 takes a Type IV.

    55 is encoded because it is the figure the section names, but it is an
    envelope rather than a permission -- a GREEN in MU-3 means the building
    fits, not that it can be permitted over the counter. Recorded in the zone's
    notes so the difference is readable where the number is.
    """
    assert troutdale.zones["MU-3"].values["max_height_ft"].value == 55
    assert troutdale.zones["MU-2"].values["max_height_ft"].value == 35
    notes = troutdale.zones["MU-3"].notes or ""
    assert "Type II" in notes
    assert "25 feet" in notes, "the minimum building height has to be recorded too"


def test_the_deferred_depth_carries_its_two_exceptions(troutdale: Layer) -> None:
    """Seventy feet, ninety on an alley easement inside the lot, and none at
    all inside one downtown block.

    Neither exception can fire -- both rest on facts nobody measures -- and
    both are written down so the numbers are not lost when somebody does.
    """
    depth = troutdale.zones["MU-2"].values["min_lot_depth_ft"]
    assert depth.value == 70
    by_when = {v.when: v for v in depth.variants}
    assert by_when[("abuts_alley", "access_easement")].value == 90
    assert by_when[("inside_mapped_use_area",)].exempt


def test_the_new_citations_all_point_at_their_own_sentence(troutdale: Layer) -> None:
    ready = readiness_for(troutdale, store=ProvenanceStore())
    assert ready.no_evidence == ()
    assert ready.misquoted == ()
