"""A ceiling on units per acre is a floor under lot area, said in other units.

Milwaukie caps R-MD at 6.2 dwelling units per acre on a lot of 7,000 sq ft or
more. Four units at that ceiling need 28,000 sq ft, and the lot-size row on
the same table asks 7,000 — so the density row, not the lot size row, decides
the zone. The corpus had a minimum-density pair and no maximum at all, which
made the note that reconciles them unwritable.
"""

from __future__ import annotations

import pytest

from flats.rules.fields import FIELDS
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.score.screen import CHECK_FIELD

pytestmark = pytest.mark.unit

MILWAUKIE = "or/clackamas/milwaukie"


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


def test_the_ceiling_is_registered_as_a_maximum() -> None:
    """A floor and a ceiling on the same axis subtract in opposite directions,
    and slack read the wrong way round turns a failing lot green."""
    field = FIELDS["max_density_du_per_acre"]

    assert field.is_maximum is True
    assert CHECK_FIELD["density_du_per_acre"] == "max_density_du_per_acre"


def test_a_quadplex_on_one_lot_is_exempt_from_the_ceiling(rules: RuleSet) -> None:
    """Footnote 4 exempts duplexes, triplexes, quadplexes and cottage clusters
    outright. It is the sentence that lets a pod exist in R-MD at all, and it
    is exempt rather than a large number: the code states no ceiling here."""
    whole = rules.resolve(MILWAUKIE, "R-MD", lot={"lot_sqft": 8000})

    assert "max_density_du_per_acre" in whole.exempted
    assert "max_density_du_per_acre" not in whole.values


def test_the_same_building_split_onto_four_lots_is_capped(rules: RuleSet) -> None:
    """Split-plat makes the pod four townhouses, and townhouses are held to
    four times the single-detached figure or 25 per acre, whichever is less."""
    for zone in ("R-MD", "R-HD"):
        split = rules.resolve(MILWAUKIE, zone, ("unit_lots",), lot={"lot_sqft": 8000})

        assert split.values["max_density_du_per_acre"].value == 25, zone


def test_a_flag_lot_closes_the_townhouse_path_and_not_the_quadplex_one(
    rules: RuleSet,
) -> None:
    """"Townhouses are not permitted on flag lots" — which is R-MD note 3, and
    says nothing about the same building on a single lot."""
    flag = rules.resolve(MILWAUKIE, "R-MD", ("unit_lots", "flag_lot"))
    whole = rules.resolve(MILWAUKIE, "R-MD", ("flag_lot",))

    assert flag.values["quadplex_allowed"].value is False
    assert whole.values["quadplex_allowed"].value is True


# --- a floor, which nothing could hold until now ------------------------


FAIRVIEW = "or/multnomah/fairview"


def test_the_floor_is_registered_as_a_minimum() -> None:
    """A floor and a ceiling on the same axis subtract in opposite directions,
    and the two are now encoded in the same zone."""
    field = FIELDS["min_density_du_per_acre"]

    assert field.is_maximum is False
    assert CHECK_FIELD["min_density_du_per_acre"] == "min_density_du_per_acre"


def test_fairview_states_both_ends_of_the_same_axis(rules: RuleSet) -> None:
    """Table 19.30.030.A row 3.b is the floor and row 4.b the ceiling. R-10
    prints 3.5 and "None"; RM prints 14 and 21.8."""
    r10 = rules.resolve(FAIRVIEW, "R-10", lot={"lot_sqft": 10000})
    rm = rules.resolve(FAIRVIEW, "RM", lot={"lot_sqft": 10000})

    assert r10.values["min_density_du_per_acre"].value == 3.5
    assert "max_density_du_per_acre" in r10.exempted, "row 4.b prints None in R-10"
    assert rm.values["min_density_du_per_acre"].value == 14

    # RM's 21.8 is written down and is what the split plat is held to. On one
    # lot the state's exemption reaches it first: OAR 660-046-0220(2)(b) bars a
    # Large City from applying a density maximum to a quadplex, and Fairview is
    # inside Metro and over a thousand people.
    assert "max_density_du_per_acre" in rm.exempted
    split = rules.resolve(FAIRVIEW, "RM", ("unit_lots",), lot={"lot_sqft": 10000})
    assert split.values["max_density_du_per_acre"].value == 21.8


def test_the_townhouse_row_governs_the_split_plat(rules: RuleSet) -> None:
    """Row 4.c does carry a ceiling where row 4.b prints None, so the same
    building on four lots is capped where on one lot it is not."""
    split = rules.resolve(FAIRVIEW, "R-10", ("unit_lots",), lot={"lot_sqft": 10000})

    assert split.values["max_density_du_per_acre"].value == 17.6


HAPPY_VALLEY = "or/clackamas/happy-valley"
TROUTDALE = "or/multnomah/troutdale"


def test_a_zone_that_states_no_floor_is_exempt_not_zero(rules: RuleSet) -> None:
    """Happy Valley prints "None" in R-5's minimum density cell and 6 du/net
    acre in MUR-S's. Two columns of one row, and only one of them is a test."""
    r5 = rules.resolve(HAPPY_VALLEY, "R5")
    murs = rules.resolve(HAPPY_VALLEY, "MURS")

    assert "min_density_du_per_acre" in r5.exempted
    assert "min_density_du_per_acre" not in r5.values
    assert murs.values["min_density_du_per_acre"].value == 6


def test_troutdale_exempts_the_pod_from_density_entirely(rules: RuleSet) -> None:
    """3.140.B.4 switches maximum density off for duplex, triplex, quadplex and
    cottage cluster projects. That also disposes of the minimum, which 3.140.A.2
    states as eighty percent of the maximum: eighty percent of a standard this
    housing type is exempt from has no operand, so no floor is encoded."""
    for zone in ("LDR-1", "LDR-2", "MDR", "HDR"):
        held = rules.resolve(TROUTDALE, zone)

        assert "max_density_du_per_acre" in held.exempted, zone
        assert "min_density_du_per_acre" not in held.values, zone


def test_the_townhouse_multiple_is_encoded_only_where_it_is_printed(
    rules: RuleSet,
) -> None:
    """3.140.B.3 gives LDR-1 and LDR-2 four times the detached density and MDR
    three times it — multiples of a figure this layer does not encode, so
    neither is written down. HDR falls to "all other districts", where 25 is
    printed."""
    hdr = rules.resolve(TROUTDALE, "HDR", ("unit_lots",))

    assert hdr.values["max_density_du_per_acre"].value == 25
    for zone in ("LDR-1", "LDR-2", "MDR"):
        split = rules.resolve(TROUTDALE, zone, ("unit_lots",))
        assert "max_density_du_per_acre" in split.exempted, zone


PORTLAND_MD = "or/multnomah/portland"
GLADSTONE = "or/clackamas/gladstone"
TUALATIN = "or/clackamas/tualatin"


def test_a_ceiling_stated_by_housing_type_is_read_on_the_pod_s_row(
    rules: RuleSet,
) -> None:
    """Tualatin's Tables 40-3 and 41-3 print a maximum density per housing
    type: "None" against Quadplex, 25 units per acre against Townhouse. Two
    rows, two plat paths, one table."""
    for zone in ("RL", "RML"):
        whole = rules.resolve(TUALATIN, zone)
        split = rules.resolve(TUALATIN, zone, ("unit_lots",))

        assert "max_density_du_per_acre" in whole.exempted, zone
        assert split.values["max_density_du_per_acre"].value == 25, zone


def test_a_chapter_that_prints_no_density_row_borrows_none(rules: RuleSet) -> None:
    """Gladstone's R-7.2 chapter prints None against Middle housing. Chapter
    17.12 prints no maximum density row at all, and borrowing R-7.2's across
    chapters would cite a sentence about another district."""
    assert "max_density_du_per_acre" in rules.resolve(GLADSTONE, "R7.2").exempted
    assert "max_density_du_per_acre" not in rules.resolve(GLADSTONE, "R5").values

    # Read off the resolved stack R5 now looks exempt too, because the state
    # exempts every quadplex, so the question this test asks has to be put to
    # the city's own file: chapter 17.12 states nothing either way.
    city = load_rules()[GLADSTONE]
    assert "max_density_du_per_acre" not in city.zones["R5"].values
    assert "max_density_du_per_acre" in city.zones["R7.2"].values


def test_four_units_on_a_lot_is_the_ceiling_and_the_pod_sits_on_it(
    rules: RuleSet,
) -> None:
    """"This code does not allow for the creation of more than four dwelling
    units on a lot, including accessory dwelling units. Cottage clusters and
    townhomes are exempt." """
    whole = rules.resolve(GLADSTONE, "R7.2")
    split = rules.resolve(GLADSTONE, "R7.2", ("unit_lots",))

    assert whole.values["max_units"].value == 4
    assert "max_units" in split.exempted, "townhomes are exempt, and the split plat is that path"


# --- which acre the rate is per -----------------------------------------


def test_the_cities_that_say_net_acre_say_so_in_the_rule_file(rules: RuleSet) -> None:
    """Four of the five cities printing a density row measure it on a net
    acre. That is a survey of the parcel, not an attribute of it, so the
    number is encoded and the denominator is named as missing."""
    for layer, zone in (
        (FAIRVIEW, "RM"),
        (HAPPY_VALLEY, "MURS"),
        (MILWAUKIE, "R-MD"),
        (TROUTDALE, "HDR"),
    ):
        held = rules.resolve(layer, zone, ("unit_lots",), lot={"lot_sqft": 8000})
        rates = [
            held.values[f]
            for f in ("min_density_du_per_acre", "max_density_du_per_acre")
            if f in held.values
        ]

        assert rates, f"{layer} {zone} states a density somewhere"
        for rate in rates:
            assert rate.measured_on == "net_developable_area", f"{layer} {zone} {rate.name}"
            # Not a lever. A lever says this number could move; this says the
            # comparison rests on a quantity nobody surveyed, and the screen
            # answers it from a bound where a bound is enough.
            assert "net_developable_area" not in rate.levers


def test_portland_measures_its_floor_on_the_lot_and_says_nothing(rules: RuleSet) -> None:
    """Table 120-4 states "sq. ft. of site area", which is the lot. Marking it
    would decline a check this project can actually run."""
    rm1 = rules.resolve(PORTLAND_MD, "RM1").values["min_density_du_per_acre"]

    assert rm1.measured_on is None


OREGON_CITY = "or/clackamas/oregon-city"


def test_oregon_city_encodes_the_floor_and_leaves_the_ceiling_alone(
    rules: RuleSet,
) -> None:
    """Tables 17.08.050 and 17.10.050 state both ends, and only one of them
    can be written down. Note B.2 counts a duplex, triplex or quadplex as ONE
    dwelling unit for maximum net density and lets total units count toward
    the minimum — so the floor is the pod's four and the ceiling is a
    numerator this screen has no way to produce. Encoding 4.4 against four
    units would turn every R-10 lot RED on a rule the city does not apply that
    way."""
    floors = {
        zone: rules.resolve(OREGON_CITY, zone).values["min_density_du_per_acre"].value
        for zone in ("R-10", "R-8", "R-6", "R-5", "R-3.5")
    }

    assert floors == {"R-10": 3.5, "R-8": 4.4, "R-6": 5.8, "R-5": 7.0, "R-3.5": 10}
    city = load_rules()[OREGON_CITY]
    for zone in floors:
        held = rules.resolve(OREGON_CITY, zone)
        assert "max_density_du_per_acre" not in held.values, zone
        # The city file is where the omission lives; the resolved stack shows
        # the state's quadplex exemption over it either way.
        assert "max_density_du_per_acre" not in city.zones[zone].values, zone
        assert held.values["min_density_du_per_acre"].measured_on == "net_developable_area"


GRESHAM = "or/multnomah/gresham"


def test_gresham_states_the_pod_s_two_plat_paths_as_separate_rows(
    rules: RuleSet,
) -> None:
    """Table 4.0130 row D prints "Duplex, Triplex, Quadplex, Cottage Cluster"
    and "Townhouse" as two rows. Five of the six districts print None against
    the first and 25 units per acre against the second, so the building on one
    lot has no ceiling and the same building on four lots does."""
    for zone in ("LDR-5", "LDR-7", "TR", "TLDR", "MDR-12"):
        whole = rules.resolve(GRESHAM, zone, lot={"lot_sqft": 12_000})
        split = rules.resolve(GRESHAM, zone, ("unit_lots",), lot={"lot_sqft": 12_000})

        assert "max_density_du_per_acre" in whole.exempted, zone
        assert split.values["max_density_du_per_acre"].value == 25, zone


def test_the_one_district_that_prints_a_figure_against_the_pod_s_own_row(
    rules: RuleSet,
) -> None:
    """MDR-24 prints 24.2 against both rows, which is the district's own
    maximum rather than the townhouse 25 every other column carries."""
    whole = rules.resolve(GRESHAM, "MDR-24", lot={"lot_sqft": 12_000})
    split = rules.resolve(GRESHAM, "MDR-24", ("unit_lots",), lot={"lot_sqft": 12_000})

    # Both rows print 24.2, and both are cancelled on the whole-building path
    # by the state's quadplex exemption; the district's own figure is what the
    # split plat is held to, and 24.2 rather than the 25 its neighbours carry.
    assert "max_density_du_per_acre" in whole.exempted
    assert load_rules()[GRESHAM].zones["MDR-24"].values[
        "max_density_du_per_acre"
    ].value == 24.2
    assert split.values["max_density_du_per_acre"].value == 24.2


def test_table_note_5_switches_the_floor_off_below_eleven_thousand_feet(
    rules: RuleSet,
) -> None:
    """"This does not apply to lots of record less than 11,000 square feet in
    size." The mark sits in MDR-24's column, not TR's — it was ruled against
    the wrong column while nothing on the row was encoded."""
    small = rules.resolve(GRESHAM, "MDR-24", lot={"lot_sqft": 10_000})
    large = rules.resolve(GRESHAM, "MDR-24", lot={"lot_sqft": 11_000})

    assert "min_density_du_per_acre" in small.exempted
    assert "min_density_du_per_acre" not in small.values
    assert large.values["min_density_du_per_acre"].value == 12.1


WEST_LINN = "or/clackamas/west-linn"


def test_west_linn_prints_its_ceiling_in_a_column_the_header_names(
    rules: RuleSet,
) -> None:
    """Table 05.020's third column is "Dwelling Units per Net Acre", and the
    table puts R-5 and R-4.5 on one line and R-3 and R-2.1 on another. The
    quote carries the header with the row, because 8.7 on its own does not say
    which of a line's six numbers it is."""
    city = load_rules()[WEST_LINN].zones

    assert city["R-5"].values["max_density_du_per_acre"].value == 8.7
    assert city["R-4.5"].values["max_density_du_per_acre"].value == 9.68
    assert city["R-2.1"].values["max_density_du_per_acre"].value == 20.74
    for zone in ("R-40", "R-20", "R-15", "R-10", "R-7", "R-5", "R-4.5", "R-3", "R-2.1"):
        held = city[zone].values["max_density_du_per_acre"]
        assert held.measured_on == "net_developable_area", zone
        assert held.prov.quote.startswith("or/clackamas/west-linn/05.density.txt#L29,")


def test_the_zone_west_linn_never_restated_is_the_one_the_state_carries(
    rules: RuleSet,
) -> None:
    """The reason the state layer exists. Four units on a 5,000 sq ft R-5 lot
    is 34.8 units to the acre against a printed 8.7, so read straight the zone
    is a wall -- and OAR 660-046-0220(2)(b) says a Large City may not apply a
    density maximum to a quadplex. West Linn is inside Metro and never wrote
    that sentence into its own code, so nothing but the state layer removes
    it. Split onto four lots the pod is townhouses and the 8.7 is the answer.
    """
    whole = rules.resolve(WEST_LINN, "R-5", lot={"lot_sqft": 5000})
    split = rules.resolve(WEST_LINN, "R-5", ("unit_lots",), lot={"lot_sqft": 5000})

    assert "max_density_du_per_acre" in whole.exempted
    assert whole.get("max_density_du_per_acre") is None
    assert split.get("max_density_du_per_acre") == 8.7


def test_west_linn_leaves_its_floor_off_because_the_code_never_prints_one(
    rules: RuleSet,
) -> None:
    """05.025.A.3 states the minimum as seventy percent of the maximum, which
    makes every one of the nine floors a product the code does not print.
    Typing 6.09 against R-5 would cite a sentence for a number the sentence
    does not contain, so the field is absent -- a check that does not run
    rather than a lot wrongly called RED."""
    city = load_rules()[WEST_LINN].zones
    for zone in ("R-40", "R-10", "R-5", "R-2.1"):
        assert "min_density_du_per_acre" not in city[zone].values, zone


CLACKAMAS = "or/clackamas/_unincorporated"


def test_the_county_states_the_quadplex_exemption_in_its_own_words(
    rules: RuleSet,
) -> None:
    """1012.04, and worth having beside the state layer rather than instead of
    it: "for a duplex, triplex, quadplex, or cottage cluster in the R-5 ...
    VR-5/7 District ... DLA is not the minimum lot area required per dwelling
    unit". District land area is the whole of the density standard here --
    1012.05 divides net site area by it -- so a building DLA does not measure
    has no ceiling.

    That sentence names four housing types and townhouses is not one of them,
    and Table 315-3 gives townhouses a third and a quarter of the DLA instead.
    So the county stands down on the split plat exactly where the state does,
    for its own reason.
    """
    city = load_rules()[CLACKAMAS].zones["R5"].values["max_density_du_per_acre"]

    assert city.exempt is True
    assert city.unless == ("unit_lots",)
    assert city.prov.quote == "or/clackamas/_unincorporated/zdo.1012.txt#L73"
    assert "max_density_du_per_acre" in rules.resolve(CLACKAMAS, "R5").exempted


def test_the_pod_s_lot_size_in_unincorporated_clackamas_is_section_845s(
    rules: RuleSet,
) -> None:
    """Nine zones had no minimum lot size at all, because Table 315-2 prints a
    pair -- "5,000/4,000 square feet" -- that is district land area over the
    detached-dwelling minimum, and 1012.02(H) waives the district figure for a
    middle housing land division anyway. Section 845.01 states the one that
    reaches this building: "7,000 square feet for a quadplex or a cottage
    cluster", the same number in every district."""
    zones = load_rules()[CLACKAMAS].zones

    for zone in ("R5", "R7", "R8.5", "R10", "R15", "R20", "R30", "VR57", "VR45"):
        held = zones[zone].values["min_lot_sqft"]
        assert held.value == 7000, zone
        assert held.prov.quote == "or/clackamas/_unincorporated/zdo.845.txt#L3,L7", zone


HAPPY_VALLEY = "or/clackamas/happy-valley"


def test_each_happy_valley_district_states_its_own_townhouse_ceiling(
    rules: RuleSet,
) -> None:
    """Six districts printed one and nobody had written it down, because until
    the reader learned "units per acre" no field was held in that unit and a
    density could not be found by machine at all.

    The point of the row is that the numbers differ: 4.4 in R-40 through 24.9
    in R-7, against the 25 R-5 carries. A corpus with one townhouse number
    would have put nearly six times the real ceiling on R-40.
    """
    ceilings = {
        zone: rules.resolve(HAPPY_VALLEY, zone, ("unit_lots",)).get(
            "max_density_du_per_acre"
        )
        for zone in ("R40", "R20", "R15", "R10", "R8.5", "R7", "R5")
    }

    assert ceilings == {
        "R40": 4.4,
        "R20": 8.7,
        "R15": 11.6,
        "R10": 17.4,
        "R8.5": 20.5,
        "R7": 24.9,
        "R5": 25,
    }

    # On one lot the pod is a quadplex, and the quadplex row of these tables
    # is "Lot size (minimum and maximum density)" -- an area, carried as
    # min_lot_sqft, not a rate.
    for zone in ceilings:
        whole = rules.resolve(HAPPY_VALLEY, zone)
        assert "max_density_du_per_acre" in whole.exempted, zone
        assert (
            load_rules()[HAPPY_VALLEY].zones[zone].values["max_density_du_per_acre"]
            .measured_on
            == "net_developable_area"
        ), zone
