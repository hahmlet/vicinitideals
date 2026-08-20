"""Gresham's Downtown plan district, where the use table decides most of it.

Five sub-districts were unencoded -- DCC, DTM, DMU, DEM and DCL -- and the
chapter that governs them was already in the store, read twice before for
DRL-1 and DRL-2. What kept them out was not a missing document. It was that
Table 4.1120 marks the Quadplex cell ``L1`` in two of them and ``NP`` in
three, and neither marking is a number.

``L1`` is a permission with three gates on it, and the gates are the point:
a plex is allowed on a lot of record 6,500 sq ft or smaller in DTM, or 7,600
in DCC north of NE 8th Street, in either case with 70 feet of street frontage
or less. One of those is measured and two are not, so the base is ``false``
and the permission rides on a variant that cannot fire yet. Encoding it the
other way round -- true, with the gates as a note -- would open two of the
largest districts in the city on a lot area nobody checked.

``NP`` is a decided RED, and the notes on those three zones carry the two rows
that were checked before deciding it: Multi-Family, which Gresham defines as
five units or more, and Townhouse, which the chapter prints a whole setback
row for. The second is not closed by the code so much as by a definition, and
that is written down rather than encoded.
"""

from __future__ import annotations

import pytest

from flats.encode.readiness import readiness_for
from flats.provenance.store import ProvenanceStore
from flats.rules.conditions import condition
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

GRESHAM = "or/multnomah/gresham"
#: Every sub-district of the chapter, in the column order Table 4.1130 prints
#: them -- which is not alphabetical, and which is how the eight-value rows are
#: read: DCC, then the N Main Avenue strip, then the rest.
DOWNTOWN = ("DCC", "DMU", "DTM", "DEM", "DRL-1", "DRL-2", "DCL")
#: The three whose Quadplex cell reads NP.
BARRED = ("DMU", "DEM", "DCL")
#: The two whose Quadplex cell reads L1.
LIMITED = ("DCC", "DTM")


@pytest.fixture(scope="module")
def gresham() -> Layer:
    return load_rules()[GRESHAM]


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


def test_the_chapter_now_holds_every_district_it_governs(gresham: Layer) -> None:
    """The five that were missing are the reason the chapter was reopened."""
    assert set(DOWNTOWN) <= set(gresham.zones)


def test_a_limited_use_is_encoded_shut_and_not_open(gresham: Layer) -> None:
    """L1 is not P, and the difference is three gates.

    The base is what binds, so it is the refusal. A reader who wants to know
    why can find the whole limitation on the one variant hanging off it.
    """
    for zone in LIMITED:
        use = gresham.zones[zone].values["quadplex_allowed"]
        assert use.value is False, zone
        assert len(use.variants) == 1, zone
        assert use.variants[0].value is True, zone


def test_the_gate_that_is_measured_rides_as_a_band(gresham: Layer) -> None:
    """Lot area is the one gate FLATS can answer, and the numbers differ.

    DTM's carve-out reaches 6,500 sq ft and DCC's reaches 7,600. Both sit
    above the 5,000 sq ft this same table asks of a quadplex, so the
    permission is a window rather than a threshold -- which is the shape a
    screen gets wrong by taking either number on its own.
    """
    ceilings = {
        zone: gresham.zones[zone].values["quadplex_allowed"].variants[0].band
        for zone in LIMITED
    }
    assert [b.measure for b in ceilings.values()] == ["lot_sqft", "lot_sqft"]
    assert ceilings["DCC"].at_most == 7600
    assert ceilings["DTM"].at_most == 6500
    assert [gresham.zones[z].values["min_lot_sqft"].value for z in LIMITED] == [
        5000,
        5000,
    ]


def test_the_gates_that_are_not_measured_keep_the_permission_shut(
    gresham: Layer,
) -> None:
    """Two registered facts, both assumed unknown, and neither is guessable.

    DTM owes one -- 70 feet of street frontage or less. DCC owes that and the
    NE 8th Street line as well. A condition assumed unknown is never in the
    active set, so the variant is never selected and the district screens
    closed; the day frontage is measured it opens on the lots the note names
    rather than on all of them.
    """
    owed = {
        zone: set(gresham.zones[zone].values["quadplex_allowed"].variants[0].when)
        for zone in LIMITED
    }
    assert owed["DTM"] == {"narrow_frontage"}
    assert owed["DCC"] == {"narrow_frontage", "inside_mapped_use_area"}
    for name in ("narrow_frontage", "inside_mapped_use_area"):
        fact = condition(name)
        assert fact.kind == "site_fact", name
        assert fact.assume is None, name


def test_an_unmeasured_gate_does_not_leak_through_the_band(rules: RuleSet) -> None:
    """A lot of exactly the right size still does not get the permission.

    The band is the half that can be checked, and checking it is not the same
    as clearing the gate. A 6,000 sq ft DTM lot satisfies the area and is
    still refused, because nobody has measured its frontage.
    """
    for zone, area in (("DCC", 7000.0), ("DTM", 6000.0)):
        got = rules.resolve(GRESHAM, zone, (), {"lot_sqft": area})
        assert got.values["quadplex_allowed"].value is False, zone


def test_a_prohibited_district_owes_nothing_else(gresham: Layer) -> None:
    """NP settles the zone, so no dimensional standard is read for it.

    A decided RED and an unread district look identical in a count, which is
    why the flag is written with a citation rather than left out. What keeps
    it honest is that the value carries no variants: nothing can turn it on.
    """
    for zone in BARRED:
        held = gresham.zones[zone]
        assert set(held.values) == {"quadplex_allowed"}, zone
        assert held.values["quadplex_allowed"].value is False, zone
        assert held.values["quadplex_allowed"].variants == (), zone


def test_the_townhouse_path_is_written_down_and_not_encoded(gresham: Layer) -> None:
    """Splitting the plat must not reopen a district Gresham closed.

    Table 4.1120 reads P for Townhouse in all seven columns, and Table 4.1130
    prints a setback row for townhouses in five of them -- so the temptation
    is a ``unit_lots`` variant on the use flag. GDC 3.0100 forbids it: a
    quadplex divided onto individual lots through a Middle Housing Land
    Division is still "considered a quadplex". A variant would fire off the
    design catalog and turn 224 lots green on a reading rather than on a
    sentence.
    """
    for zone in DOWNTOWN:
        use = gresham.zones[zone].values.get("quadplex_allowed")
        assert use is not None, zone
        for variant in use.variants:
            assert "unit_lots" not in variant.when, zone
    for zone in BARRED:
        assert "Middle Housing Land Division" in gresham.zones[zone].notes, zone


def test_the_dimensional_row_is_the_one_headed_in_any_district(
    gresham: Layer,
) -> None:
    """DCC and DTM take the same numbers DRL-1 does, because it is one row.

    Table 4.1130 states its setbacks by street type rather than by district,
    and this row prints identical numbers in all six columns -- so nothing
    here depends on which street the lot fronts, and nothing depends on which
    Downtown district it sits in either. The one standard that does differ is
    lot area, which the table states on its own line.
    """
    shared = (
        "setback_front_ft",
        "setback_side_ft",
        "setback_rear_ft",
        "setback_street_side_ft",
        "setback_garage_entrance_ft",
        "min_lot_width_ft",
        "min_frontage_ft",
        "min_lot_depth_ft",
    )
    reference = {f: gresham.zones["DRL-1"].values[f].value for f in shared}
    assert reference == {
        "setback_front_ft": 10,
        "setback_side_ft": 5,
        "setback_rear_ft": 10,
        "setback_street_side_ft": 10,
        "setback_garage_entrance_ft": 20,
        "min_lot_width_ft": 35,
        "min_frontage_ft": 35,
        "min_lot_depth_ft": 70,
    }
    for zone in LIMITED:
        assert {f: gresham.zones[zone].values[f].value for f in shared} == reference
        assert gresham.zones[zone].values["min_lot_sqft"].value == 5000
    assert gresham.zones["DRL-1"].values["min_lot_sqft"].value == 4000


def test_the_eight_column_rows_are_read_in_the_right_order(gresham: Layer) -> None:
    """The second column of Table 4.1130 is a strip, not a district.

    Every row of the table's first half prints eight values against seven
    sub-district headings, because DCC is split into the district and the
    N Main Avenue frontage. Read as seven, each number lands one column left
    of where it belongs and the whole table is wrong by one -- so the heights
    are pinned here as the check on the reading.
    """
    heights = {
        z: gresham.zones[z].values["max_height_ft"].value
        for z in DOWNTOWN
        if "max_height_ft" in gresham.zones[z].values
    }
    assert heights == {"DCC": 85, "DTM": 85, "DRL-1": 35, "DRL-2": 50}
    fars = {
        z: gresham.zones[z].values["max_far"].value
        for z in DOWNTOWN
        if "max_far" in gresham.zones[z].values
    }
    assert fars == {"DCC": 3.0, "DTM": 3.0, "DRL-1": 1.0, "DRL-2": 1.0}


def test_every_downtown_district_states_a_density_floor(gresham: Layer) -> None:
    """A floor per acre is not met by being small enough to build on.

    Four units on a 5,000 sq ft lot is 35 units to the acre and clears
    anything the chapter asks. The same four on a half acre is eight, which
    fails DTM's 20 and DCC's 17 outright. Both DRL blocks were encoded
    without this row for four months.
    """
    floors = {
        z: gresham.zones[z].values["min_density_du_per_acre"].value
        for z in DOWNTOWN
        if "min_density_du_per_acre" in gresham.zones[z].values
    }
    assert floors == {"DCC": 17, "DTM": 20, "DRL-1": 8.7, "DRL-2": 8.7}


def test_the_one_downtown_ceiling_that_binds_this_building(gresham: Layer) -> None:
    """DRL-1 caps a quadplex at 12.45 units per acre, and that is a lot size.

    Read against the 8.7 floor above it, four units fit only between roughly
    14,000 and 20,000 sq ft of net area -- while the lot-size row of the same
    table asks 4,000. Most of the district is therefore too SMALL for the pod
    on one lot, which is the opposite of what every other standard here
    suggests, and it was invisible until the row was read. Splitting the plat
    escapes it: the cell states 25 for a townhouse.
    """
    ceiling = gresham.zones["DRL-1"].values["max_density_du_per_acre"]
    assert ceiling.value == 12.45
    assert not ceiling.exempt
    assert [(v.value, v.when) for v in ceiling.variants] == [(25, ("unit_lots",))]
    assert gresham.zones["DRL-2"].values["max_density_du_per_acre"].exempt


def test_the_rate_says_which_acre_it_is_per(gresham: Layer) -> None:
    """Gresham subtracts two different lists, one for the floor and one for
    the ceiling, so the denominator travels on the value rather than the layer.
    """
    for zone in ("DCC", "DTM", "DRL-1", "DRL-2"):
        floor = gresham.zones[zone].values["min_density_du_per_acre"]
        assert floor.measured_on == "net_developable_area", zone
        assert "minimum-density" in floor.measured_on_cite, zone
        assert floor.measured_on_quote, zone
    ceiling = gresham.zones["DRL-1"].values["max_density_du_per_acre"]
    assert "maximum-density" in ceiling.measured_on_cite


def test_the_new_citations_all_point_at_their_own_sentence(gresham: Layer) -> None:
    """Nothing added here is a number the cited lines do not print.

    Table 4.1130 glues its footnote markers onto its figures -- 8.7 units per
    acre is stored as "8.71" and 12.45 as "12.458" -- so this passing at all
    depends on the chapter having been declared as one that does that.
    """
    ready = readiness_for(gresham, store=ProvenanceStore())
    assert ready.no_evidence == ()
    assert ready.misquoted == ()
