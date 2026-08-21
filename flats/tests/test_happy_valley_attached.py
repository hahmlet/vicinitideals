"""The three districts the city built for this building, and the two that refuse it.

Happy Valley's Chapter 16.22 runs to six use tables. The July port read the
first four -- FU-10, the very low density trio, the low density trio, R-5 and
MUR-S -- and stopped at the fifth, which is where the city puts attached
housing. SFA, MUR-A and VTH permit a quadplex outright and hold it to a lot
minimum of 2,000 or 3,000 square feet, against R-40's 40,000. That is the
densest by-right ground for this pod in the city, and none of it was in the
file.

Two findings in the slice are worth pinning beyond the numbers.

VTH states density as an area per primary unit rather than units per acre --
2,000 square feet at the maximum, 3,000 at the minimum -- and the quadplex
exemption that lifts density off the pod in SFA and MUR-A is marked on their
cells only. So four units in VTH need 8,000 square feet of net developable
area, four times the lot minimum printed two rows down. Reading the lot row
alone would have cleared a 2,000 square foot lot.

And MUR-M and MUR-X answer the other way. Their use table is a closed list
with no "uses similar to" row, and its residential rows are attached dwellings
-- townhouses, attached duplex, rowhouses -- and multifamily, which 16.12
defines as five or more families. Four units on one lot is neither, in a
chapter that names "Four-family dwelling (quadplex)" as its own row everywhere
else. Split onto unit lots the same table says yes, and that is the only
condition under which 16.22.060-2's "Variable" dimensions would matter -- they
are set "through the master plan process or design review application", which
is the one thing in this layer that cannot be encoded at all.
"""

from __future__ import annotations

import pytest

from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

HAPPY_VALLEY = "or/clackamas/happy-valley"

#: The three districts of Table 16.22.050, in the column order the table prints.
ATTACHED = ("SFA", "MURA", "VTH")

#: An acre, for turning an area-per-unit into the units-per-acre the field holds.
SQFT_PER_ACRE = 43560.0


@pytest.fixture(scope="module")
def happy_valley() -> Layer:
    return load_rules()[HAPPY_VALLEY]


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


# -- the permission ----------------------------------------------------------


def test_a_quadplex_is_permitted_outright_in_all_three(happy_valley: Layer) -> None:
    """A bare P in every column, with no footnote on the cell and no child-lot
    note over this table -- that one is printed over the three lower-density
    use tables only."""
    for zone in ATTACHED:
        held = happy_valley.zones[zone].values["quadplex_allowed"]
        assert held.value is True, zone
        assert held.variants == (), zone


def test_the_lot_minimum_is_a_fifth_of_what_the_encoded_zones_asked(
    happy_valley: Layer,
) -> None:
    for zone, sqft in (("SFA", 2000), ("MURA", 3000), ("VTH", 2000)):
        assert happy_valley.zones[zone].values["min_lot_sqft"].value == sqft, zone
    assert happy_valley.zones["R40"].values["min_lot_sqft"].value == 40000


def test_lot_width_and_depth_are_answered_rather_than_missing(
    happy_valley: Layer,
) -> None:
    """Both cells read "None" in all three columns. A stated absence is a
    standard somebody read, which is not the same as one nobody encoded."""
    for zone in ATTACHED:
        for field in ("min_lot_width_ft", "min_lot_depth_ft"):
            held = happy_valley.zones[zone].values[field]
            assert held.exempt, f"{zone}.{field}"
            assert held.value is None, f"{zone}.{field}"


# -- the density that does not lift ------------------------------------------


def test_the_quadplex_density_exemption_reaches_two_of_the_three(
    happy_valley: Layer,
) -> None:
    """Note 2 -- "duplexes, triplexes, quadplexes ... are exempt from the
    density standards" -- is marked on the SFA and MUR-A cells. Both halves,
    not the maximum alone: the sentence says "the density standards"."""
    for zone in ("SFA", "MURA"):
        for field in ("min_density_du_per_acre", "max_density_du_per_acre"):
            assert happy_valley.zones[zone].values[field].exempt, f"{zone}.{field}"


def test_but_not_the_one_whose_cells_carry_a_different_footnote(
    happy_valley: Layer,
) -> None:
    """VTH's density cells reference note 9, not note 2. So the pod is held to
    them, and they are the binding standard in the district by a factor of
    four over the lot minimum printed two rows below."""
    values = happy_valley.zones["VTH"].values
    ceiling = values["max_density_du_per_acre"]
    floor = values["min_density_du_per_acre"]

    assert not ceiling.exempt
    assert not floor.exempt
    assert ceiling.sqft_per_unit == 2000
    assert floor.sqft_per_unit == 3000
    assert ceiling.value == pytest.approx(SQFT_PER_ACRE / 2000)
    assert floor.value == pytest.approx(SQFT_PER_ACRE / 3000)

    # Four units at the ceiling need 8,000 sq ft of net developable area. The
    # lot minimum is 2,000.
    assert values["min_lot_sqft"].value == 2000


def test_the_density_is_measured_on_something_smaller_than_the_lot(
    happy_valley: Layer, store: ProvenanceStore
) -> None:
    """"du/net acre" and "sf/primary unit" alike run against net developable
    area, by note 1's reference to 16.63.020(F). That is a survey, so the
    screen settles the half it can and defers the other."""
    for zone in ATTACHED:
        held = happy_valley.zones[zone].values["max_density_du_per_acre"]
        assert held.measured_on == "net_developable_area", zone
        assert "16.63.020(F)(1)" in (held.measured_on_cite or ""), zone
        assert "Constrained land includes" in store.quote(held.measured_on_quote), zone


# -- the envelope ------------------------------------------------------------


def test_the_setbacks_are_the_same_shape_in_every_column(happy_valley: Layer) -> None:
    """Ten front, fifteen rear, five interior side. Only the street side
    moves, and only for VTH."""
    for zone in ATTACHED:
        values = happy_valley.zones[zone].values
        assert values["setback_front_ft"].value == 10, zone
        assert values["setback_rear_ft"].value == 15, zone
        assert values["setback_side_ft"].value == 5, zone
    assert happy_valley.zones["SFA"].values["setback_street_side_ft"].value == 8
    assert happy_valley.zones["MURA"].values["setback_street_side_ft"].value == 8
    assert happy_valley.zones["VTH"].values["setback_street_side_ft"].value == 5


def test_the_party_wall_zero_needs_a_lot_line_to_run_along(
    happy_valley: Layer,
) -> None:
    """Note 5 gives the zero to townhomes, and 16.12 defines a townhouse as a
    dwelling on its own lot sharing walls with dwellings on another. Four
    units on one lot have no interior lot line for it to apply to, so the
    variant carries `unit_lots` beside `attached_wall` -- the same correction
    the eight lower-density zones took."""
    for zone in ATTACHED:
        variant = next(
            v
            for v in happy_valley.zones[zone].values["setback_side_ft"].variants
            if v.value == 0
        )
        assert variant.when == ("attached_wall", "unit_lots"), zone


def test_only_one_district_in_the_city_caps_the_street_setback(
    happy_valley: Layer,
) -> None:
    """VTH prints "Setback (maximum from street right-of-way or designated
    accessway): 18 feet" where SFA and MUR-A print "None". A site plan that
    pushes the building back to win parking depth fails here and nowhere else
    in Happy Valley."""
    assert happy_valley.zones["VTH"].values["setback_front_max_ft"].value == 18
    for zone in ("SFA", "MURA", "R5", "R7", "MURS"):
        assert "setback_front_max_ft" not in happy_valley.zones[zone].values, zone


def test_the_heights_climb_with_the_district(happy_valley: Layer) -> None:
    for zone, feet in (("SFA", 45), ("MURA", 65), ("VTH", 35)):
        assert happy_valley.zones[zone].values["max_height_ft"].value == feet, zone


def test_the_three_owe_no_required_standard(rules: RuleSet) -> None:
    """The point of the slice. A zone missing a required field is a check that
    never runs, and these carried every one of them unencoded until now."""
    for zone in ATTACHED:
        assert rules.resolve(HAPPY_VALLEY, zone).missing_required == (), zone


# -- and the two that refuse -------------------------------------------------


def test_the_multifamily_districts_have_no_row_for_this_building(
    happy_valley: Layer, store: ProvenanceStore
) -> None:
    for zone in ("MURM", "MURX"):
        held = happy_valley.zones[zone].values["quadplex_allowed"]
        assert held.value is False, zone
        text = store.quote(held.prov.quote)
        assert "Attached dwellings, (townhouses, attached duplex, rowhouses)" in text
        assert "Multifamily dwellings" in text
        assert "quadplex" not in text.lower(), zone


def test_but_the_same_table_permits_the_units_on_their_own_lots(
    happy_valley: Layer,
) -> None:
    for zone in ("MURM", "MURX"):
        variant = next(
            v
            for v in happy_valley.zones[zone].values["quadplex_allowed"].variants
            if v.when == ("unit_lots",)
        )
        assert variant.value is True, zone


def test_which_is_when_the_dimensions_would_matter_and_there_are_none(
    rules: RuleSet, happy_valley: Layer
) -> None:
    """Table 16.22.060-2 prints "Variable" for lot size, width, depth,
    coverage and every setback, because note 2 says they "shall be determined
    through the master plan process or design review application".

    So these missing required fields are not encoding debt. They are the
    answer: a site here is a design-review question rather than a screening
    one, and the note says so where a reviewer will meet it.
    """
    for zone in ("MURM", "MURX"):
        missing = rules.resolve(HAPPY_VALLEY, zone).missing_required
        assert "min_lot_sqft" in missing, zone
        assert "setback_front_ft" in missing, zone
    assert "master plan process or design review" in happy_valley.zones["MURM"].notes
    # MUR-X's answer is blunter still: the dimensional table is headed MUR-M1,
    # MUR-M2 and MUR-M3, so this district has no column in it to be Variable.
    assert "carries no MUR-X column at all" in happy_valley.zones["MURX"].notes


def test_mur_x_states_its_own_column_rather_than_borrowing_mur_m(
    happy_valley: Layer,
) -> None:
    """The two share a use table and part company below it: 16.22.060-2 is
    headed MUR-M1, MUR-M2 and MUR-M3 and carries no MUR-X column at all. So
    MUR-M's 65 feet is not carried across -- it is printed in a table this
    district is not named in."""
    assert happy_valley.zones["MURX"].like is None
    assert happy_valley.zones["MURM"].values["max_height_ft"].value == 65
    assert "max_height_ft" not in happy_valley.zones["MURX"].values
