"""Gresham's Pleasant Valley plan district, where density decides the lot size.

LDR-PV was encoded in July from the same three tables and MDR-PV, HDR-PV,
NC-PV and PUB-PV were not, which left 416 lots unread against 694 read. The
use table settles two of them outright -- a quadplex is P in all three
residential columns and NP in all three mixed-use ones, and NP again on every
residential row of the Public Land table.

The two that are open are open on very different terms, and neither says so in
its lot-size row. MDR-PV asks 3,000 sq ft and 12 units to the acre, and four
units reach 12 to the acre only up to about 14,520 sq ft -- a window. HDR-PV
asks no minimum lot size at all and then states the highest density floor in
the city, 25 to the acre, which four units reach only up to about 6,970 sq ft;
its 40-unit ceiling puts a floor of about 4,356 under that. So the district
with no stated lot size is the one with the narrowest one, and it is stated
twice, in the other unit, in two different rows.

Article 3 is what makes the ceiling real in one district and not the other.
Middle housing counts toward minimum but not maximum density in a named list
that includes LDR-PV and MDR-PV and does not include HDR-PV -- and the table
agrees with it, printing None in the first two columns of row C and 40 in the
third.
"""

from __future__ import annotations

import pytest

from flats.encode.readiness import readiness_for
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

GRESHAM = "or/multnomah/gresham"
#: The three residential columns of Tables 4.1413/4.1415A/4.1415B, in the order
#: the tables print them. Every row of all three is read against this order.
RESIDENTIAL = ("LDR-PV", "MDR-PV", "HDR-PV")
#: The sub-districts added here whose use table settles them.
BARRED = ("NC-PV", "PUB-PV")
#: Four units, which is the only building this layer screens.
UNITS = 4
#: Square feet in an acre, which is what turns a rate into a lot size.
ACRE = 43560


@pytest.fixture(scope="module")
def gresham() -> Layer:
    return load_rules()[GRESHAM]


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


def test_the_chapter_now_holds_every_sub_district_it_governs(gresham: Layer) -> None:
    assert set(RESIDENTIAL) <= set(gresham.zones)
    assert set(BARRED) <= set(gresham.zones)


def test_the_use_tables_split_the_plan_district_in_half(gresham: Layer) -> None:
    """P down the residential table, NP down the other two."""
    for zone in RESIDENTIAL:
        use = gresham.zones[zone].values["quadplex_allowed"]
        assert use.value is True, zone
        assert use.variants == (), zone
    for zone in BARRED:
        held = gresham.zones[zone]
        assert held.values["quadplex_allowed"].value is False, zone
        assert held.values["quadplex_allowed"].variants == (), zone
        assert set(held.values) == {"quadplex_allowed"}, zone


def test_the_density_floor_is_a_maximum_lot_size(gresham: Layer) -> None:
    """Every residential column states one, and every one of them binds.

    A floor per acre with a fixed unit count is a ceiling on area, and the
    three columns state three very different ceilings -- roughly 32,890 sq ft
    in LDR-PV, 14,520 in MDR-PV and 6,970 in HDR-PV. None of the three is
    anywhere near the minimum lot size printed two rows above it.
    """
    floors = {
        z: gresham.zones[z].values["min_density_du_per_acre"].value
        for z in RESIDENTIAL
    }
    assert floors == {"LDR-PV": 5.3, "MDR-PV": 12, "HDR-PV": 25}

    ceilings = {z: round(UNITS / rate * ACRE) for z, rate in floors.items()}
    assert ceilings == {"LDR-PV": 32875, "MDR-PV": 14520, "HDR-PV": 6970}


def test_the_district_that_states_no_lot_size_has_the_tightest_one(
    gresham: Layer,
) -> None:
    """HDR-PV row A reads None, and row C reads 40, which is a floor of 4,356.

    Read together with the 25-unit minimum, HDR-PV is a window between roughly
    4,356 and 6,970 square feet -- narrower than anything else in the chapter,
    and invisible in the row that would normally state it.
    """
    held = gresham.zones["HDR-PV"].values
    assert held["min_lot_sqft"].exempt
    assert held["max_density_du_per_acre"].value == 40
    assert round(UNITS / 40 * ACRE) == 4356
    assert gresham.zones["MDR-PV"].values["min_lot_sqft"].value == 3000
    assert gresham.zones["LDR-PV"].values["min_lot_sqft"].value == 5000


def test_the_maximum_density_reaches_one_column_and_not_the_other_two(
    gresham: Layer,
) -> None:
    """Article 3 names the districts where middle housing escapes the ceiling.

    LDR-PV and MDR-PV are on that list and HDR-PV is not, and row C of Table
    4.1415A says the same thing in numbers: None, None, 40. Two sources
    agreeing is why the exemption is encoded as read rather than as a gap.
    Splitting the plat makes the building townhouses, which the same row caps
    at 25 in both of the exempt columns.
    """
    for zone in ("LDR-PV", "MDR-PV"):
        ceiling = gresham.zones[zone].values["max_density_du_per_acre"]
        assert ceiling.exempt, zone
        assert [(v.value, v.when) for v in ceiling.variants] == [(25, ("unit_lots",))]
    hdr = gresham.zones["HDR-PV"].values["max_density_du_per_acre"]
    assert hdr.value == 40
    assert not hdr.exempt
    assert hdr.variants == ()


def test_gresham_subtracts_four_different_lists_to_get_an_acre(
    gresham: Layer,
) -> None:
    """Two lists for the LDR group and two for everybody else.

    The city writes one pair of subtraction lists for LDR-5, LDR-7, LDR-PV,
    LDR-SW, VLDR-SW, TLDR and TR and a shorter pair for every other district,
    and the minimum and maximum lists differ inside each pair. LDR-PV is
    inside the group and MDR-PV and HDR-PV are outside it, so the same chapter
    produces four denominators and the citation has to say which.
    """
    cites = {
        (z, f): gresham.zones[z].values[f].measured_on_cite
        for z in RESIDENTIAL
        for f in ("min_density_du_per_acre", "max_density_du_per_acre")
        if f in gresham.zones[z].values
    }
    assert len(set(cites.values())) == 4
    for (zone, _field), cite in cites.items():
        assert "Density, Net" in cite, zone
        outside = "outside the LDR group" in cite
        assert outside is (zone != "LDR-PV"), (zone, cite)
    for value in cites:
        held = gresham.zones[value[0]].values[value[1]]
        assert held.measured_on == "net_developable_area"
        assert held.measured_on_quote


def test_the_corner_frontage_is_larger_here_not_smaller(gresham: Layer) -> None:
    """The opposite of the corridor's note 11, on the same city's paper.

    Table 4.1415A asks 35 feet on an interior lot and 40 on a corner in the
    two lower columns -- a corner lot needs MORE street, because it fronts two
    streets. Table 4.0430's note 11 drops the corridor's corner frontage
    instead. Copying either rule across chapters would be wrong.
    """
    for zone in ("LDR-PV", "MDR-PV"):
        frontage = gresham.zones[zone].values["min_frontage_ft"]
        assert frontage.value == 35, zone
        assert [(v.value, v.when) for v in frontage.variants][0] == (
            40,
            ("corner_lot",),
        ), zone
    hdr = gresham.zones["HDR-PV"].values["min_frontage_ft"]
    assert hdr.exempt
    assert [(v.value, v.when) for v in hdr.variants] == [
        (20, ("corner_lot",)),
        (18, ("unit_lots",)),
        (32, ("unit_lots", "corner_lot")),
    ]


def test_two_districts_share_one_setback_row_and_one_of_them_leaves_it(
    gresham: Layer,
) -> None:
    """Table 4.1415B prints "LDR-PV, MDR-PV" over a single set of numbers.

    The quadplex row is shared outright. The Townhouse row below it is not:
    it drops MDR-PV's street-side setback to 5 feet and leaves LDR-PV's at 8,
    which is two districts on one row moving by different amounts and the sort
    of thing a shared encoding hides.

    The rear yard is the other way round -- one printed figure, two answers.
    7.0420(G)(1) names LDR-PV and not MDR-PV, so the roof plane pushes a 26 ft
    box five feet further back in the first and nowhere in the second, and two
    districts sharing a table cell end up five feet apart.
    """
    shared = (
        "setback_front_ft",
        "setback_side_ft",
        "setback_garage_entrance_ft",
    )
    for field in shared:
        held = gresham.zones["LDR-PV"].values[field]
        mirror = gresham.zones["MDR-PV"].values[field]
        assert held.value == mirror.value, field

    rear = gresham.zones["LDR-PV"].values["setback_rear_ft"]
    assert rear.before_step_back == gresham.zones["MDR-PV"].values["setback_rear_ft"].value
    assert rear.value == rear.before_step_back + 5
    assert gresham.zones["LDR-PV"].values["setback_street_side_ft"].value == 10
    assert gresham.zones["MDR-PV"].values["setback_street_side_ft"].value == 10
    split = {
        z: [
            (v.value, v.when)
            for v in gresham.zones[z].values["setback_street_side_ft"].variants
        ]
        for z in ("LDR-PV", "MDR-PV")
    }
    assert split == {
        "LDR-PV": [(8, ("unit_lots",))],
        "MDR-PV": [(5, ("unit_lots",))],
    }


def test_the_alley_is_the_looser_column_by_ten_feet_in_one_district(
    gresham: Layer,
) -> None:
    """HDR-PV asks 15 feet at the rear without an alley and 5 with one.

    Everywhere else in the chapter the two rear columns are close -- 10 and 8
    in the two lower columns. Here the gap is ten feet, and the base is the
    largest rear setback in the plan district, which makes the alley the
    difference between a pod fitting and not.
    """
    rear = gresham.zones["HDR-PV"].values["setback_rear_ft"]
    assert rear.value == 15
    assert [(v.value, v.when) for v in rear.variants] == [
        (5, ("abuts_alley",)),
        (10, ("unit_lots",)),
        (5, ("unit_lots", "abuts_alley")),
    ]
    # HDR-PV and MDR-PV are outside 7.0420(G)(1)'s list and read the table as
    # printed; LDR-PV is inside it and carries the same two figures five feet
    # deeper.
    for zone in ("LDR-PV", "MDR-PV"):
        held = gresham.zones[zone].values["setback_rear_ft"]
        printed = (
            held.before_step_back or held.value,
            held.variants[0].before_step_back or held.variants[0].value,
        )
        assert printed == (10, 8), zone
    assert gresham.zones["LDR-PV"].values["setback_rear_ft"].value == 15
    assert gresham.zones["MDR-PV"].values["setback_rear_ft"].value == 10


def test_an_alley_actually_loosens_the_rear_when_it_is_named(
    rules: RuleSet,
) -> None:
    """The variant is not decoration -- resolving with the fact moves the number."""
    without = rules.resolve(GRESHAM, "HDR-PV")
    with_alley = rules.resolve(GRESHAM, "HDR-PV", ("abuts_alley",))
    assert without.values["setback_rear_ft"].value == 15
    assert with_alley.values["setback_rear_ft"].value == 5


def test_every_pleasant_valley_district_owes_nothing_more(rules: RuleSet) -> None:
    for zone in (*RESIDENTIAL, *BARRED):
        assert rules.resolve(GRESHAM, zone).missing_required == (), zone


def test_the_new_citations_all_point_at_their_own_sentence(gresham: Layer) -> None:
    ready = readiness_for(gresham, store=ProvenanceStore())
    assert ready.no_evidence == ()
    assert ready.misquoted == ()
