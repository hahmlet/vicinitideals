"""Gresham's last seven zones, and what closing a city looks like.

Six of the seven are settled on a use table and own nothing else: NC from the
Commercial chapter, HI and GI from the Industrial one, and CNTH, CNTM and CNRM
from the Civic Neighborhood plan district. Three chapters fetched to read three
cells, which is the shape of most of this work -- GI alone was 284 lots, the
largest unread zone left in the city, and the answer was one word.

The seventh is not. OFR, Office/Residential, is the seventh column of Tables
4.0120, 4.0130 and 4.0131 -- the same three tables LDR-5, LDR-7, TR, TLDR,
MDR-12 and MDR-24 were read from in July. Six columns were encoded and the
seventh was not, in a document that had been in the store the whole time. The
missing zone was never a missing document.

What OFR turns out to state is two lot sizes rather than one. Row A asks 7,200
square feet of SITE and row B asks 3,600 of LOT, both in the same column; a
development on one lot has to satisfy both, so the larger binds. Above them
sits a density floor of 8.71 to the acre, which four units meet only up to
about 20,000 square feet. The district is a window, and none of its three rows
says so.
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
#: The six added here that a use table settles outright.
REFUSED = ("NC", "HI", "GI", "CNTH", "CNTM", "CNRM")
#: Every zone the Gresham zoning layer reports, which the rules now carry in
#: full. Kept as a list rather than a count so that a zone appearing or
#: disappearing says which one.
#: RTC, CC and MC read a bare NP on the quadplex row, and a footnote over the
#: same table region is ruled `unmeasured` against `civic_corridor`. That makes
#: the prohibition levered rather than settled, so the resolver asks these three
#: for the dimensions a permitted zone owes. See
#: test_a_levered_prohibition_owes_its_dimensions_like_any_other.
LEVERED = ("RTC", "CC", "MC")
#: What each of them owes. Table 4.0430 states all five, in columns the
#: extraction shifts badly enough that reading them would be a guess.
OWED = ("max_height_ft", "min_lot_sqft", "setback_front_ft", "setback_rear_ft",
        "setback_side_ft")

ALL_ZONES = (
    "LDR-5", "LDR-7", "TLDR", "TR", "OFR", "MDR-12", "MDR-24",
    "LDR-PV", "MDR-PV", "HDR-PV", "NC-PV", "PUB-PV",
    "VLDR-SW", "LDR-SW", "THR-SW", "RTI-SW", "IND-SW",
    "DCC", "DTM", "DMU", "DEM", "DCL", "DRL-1", "DRL-2",
    "SC", "SC-RJ", "CMF", "CMU", "RTC", "CC", "MC",
    "LDR/GB", "NC", "HI", "GI", "CNTH", "CNTM", "CNRM",
)
UNITS = 4
ACRE = 43560


@pytest.fixture(scope="module")
def gresham() -> Layer:
    return load_rules()[GRESHAM]


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


def test_the_city_is_closed(gresham: Layer) -> None:
    """Thirty-eight zones, and the coverage ledger reports no more.

    Gresham was 24 zones and 2,716 unread lots when this run started. What
    makes the list worth pinning rather than the count is that a zone the GIS
    reports and the rules do not carry is invisible in a count -- it just
    reads as a smaller city.
    """
    assert set(ALL_ZONES) == set(gresham.zones)


def test_six_of_the_last_seven_are_one_cell_each(gresham: Layer) -> None:
    """A settled RED owns the use flag and nothing else.

    Encoding a dimensional standard for a district that refuses the use would
    be reading a table nobody has to satisfy, and it would make the zone look
    thin-but-answered instead of answered.
    """
    for zone in REFUSED:
        held = gresham.zones[zone]
        assert set(held.values) == {"quadplex_allowed"}, zone
        assert held.values["quadplex_allowed"].value is False, zone
        assert held.values["quadplex_allowed"].variants == (), zone


def test_the_seventh_column_was_read_from_a_document_already_held(
    gresham: Layer,
) -> None:
    """OFR sits in the same three tables the other six residential zones do.

    So the gap was not a fetch. Its neighbours in that table were encoded in
    July and it was skipped, which is the failure mode a coverage ledger
    exists to catch: the zone is not missing a source, it is missing a reading.
    """
    ofr = gresham.zones["OFR"]
    assert ofr.values["quadplex_allowed"].value is True
    assert ofr.section == ("4.01", "7.042")
    assert ofr.section == gresham.zones["MDR-12"].section


def test_a_site_size_and_a_lot_size_in_the_same_column(gresham: Layer) -> None:
    """7,200 against 3,600, and the larger is what binds.

    Row A of Table 4.0130 is Minimum Site Size and row B is Minimum Lot Size,
    and OFR is one of two columns that print a number in both. A development
    on one lot is a site of one lot, so it owes the site figure as well --
    which is the reading MDR-24 already takes from the same row.
    """
    assert gresham.zones["OFR"].values["min_lot_sqft"].value == 7200
    assert gresham.zones["MDR-24"].values["min_lot_sqft"].value == 11000
    # And no split-plat escape: the townhouse line of row B reads None, but
    # dividing the lot does not shrink the site.
    assert gresham.zones["OFR"].values["min_lot_sqft"].variants == ()


def test_the_density_floor_closes_the_window_from_above(gresham: Layer) -> None:
    """8.71 to the acre is four units on about 20,000 square feet.

    Read with the 7,200 below it, OFR is a window rather than a floor -- and
    it is the same 8.71 MDR-12 states, in a district whose lot standards are
    twice as demanding.
    """
    floor = gresham.zones["OFR"].values["min_density_du_per_acre"]
    assert floor.value == 8.71
    assert round(UNITS / 8.71 * ACRE) == 20005
    assert gresham.zones["MDR-12"].values["min_density_du_per_acre"].value == 8.71
    ceiling = gresham.zones["OFR"].values["max_density_du_per_acre"]
    assert ceiling.exempt
    assert [(v.value, v.when) for v in ceiling.variants] == [(25, ("unit_lots",))]


def test_the_only_column_that_states_a_lot_depth_for_this_building(
    gresham: Layer,
) -> None:
    """100 feet, interior or corner, where five of the seven columns read None.

    Depth is the standard a screen forgets, because most of this corpus does
    not state one. Splitting the plat does not move it either -- the townhouse
    line prints the same 100.
    """
    depth = gresham.zones["OFR"].values["min_lot_depth_ft"]
    assert depth.value == 100
    assert {v.value for v in depth.variants} == {100}
    assert "min_lot_depth_ft" not in gresham.zones["MDR-12"].values
    assert "min_lot_depth_ft" not in gresham.zones["MDR-24"].values


def test_no_frontage_standard_and_that_is_a_reading(gresham: Layer) -> None:
    """Row G reads NA in this column on both lines, and None for a townhouse.

    Encoded exempt rather than left out, because a missing frontage row and a
    frontage row that says nothing applies look identical from outside and are
    not the same claim.
    """
    frontage = gresham.zones["OFR"].values["min_frontage_ft"]
    assert frontage.exempt
    assert frontage.variants == ()
    assert gresham.zones["MDR-12"].values["min_frontage_ft"].value == 45


def test_the_alley_buys_nothing_here_unless_the_plat_is_split(
    rules: RuleSet,
) -> None:
    """Table 4.0131 reads NA in the Rear With Alley column on the row a
    quadplex takes, and 8 feet on the townhouse row below it.

    So an alley lot in OFR screens against the same 15 feet as any other lot,
    and only the split path reaches the shorter number.
    """
    plain = rules.resolve(GRESHAM, "OFR")
    with_alley = rules.resolve(GRESHAM, "OFR", ("abuts_alley",))
    assert plain.values["setback_rear_ft"].value == 15
    assert with_alley.values["setback_rear_ft"].value == 15
    split = rules.resolve(GRESHAM, "OFR", ("unit_lots", "abuts_alley"))
    assert split.values["setback_rear_ft"].value == 8


def test_every_gresham_zone_owes_nothing_more(rules: RuleSet) -> None:
    for zone in ALL_ZONES:
        if zone in LEVERED:
            continue
        assert rules.resolve(GRESHAM, zone).missing_required == (), zone


def test_a_levered_prohibition_owes_its_dimensions_like_any_other(
    rules: RuleSet,
) -> None:
    """Three corridor districts that used to owe nothing now owe five each.

    A zone whose quadplex row reads a bare NP needs no setbacks: there is no
    path to a building, so there is nothing to measure. That shortcut is only
    sound while the NP is *settled*. RTC, CC and MC sit in the region of a
    footnote ruled `unmeasured` against `civic_corridor` -- read, understood,
    waiting on a corridor map nobody holds -- and an unmeasured fact over a
    prohibition is a prohibition that might not hold. The resolver treats it as
    a lever and asks for the dimensions again, which is right.

    They were exempt until now for the wrong reason. The join that hangs
    footnotes on values read only the first line of a citation and gave up on
    any it could not parse, so these three -- cited to a header line and a cell
    line, comma-separated -- never reached the gate at all. Thirty percent of
    the corpus was in the same position.

    NOT ENCODED, and not because nobody looked. Table 4.0430 states all five
    standards for all seven corridor districts, but its cells wrap across a
    dozen lines each and the extraction shifts fragments between columns; the
    setback rows in particular cannot be assigned to a district by reading the
    text. Encoding them from this document would be a guess wearing a
    citation. The table needs a better extraction first.
    """
    for zone in LEVERED:
        held = rules.resolve(GRESHAM, zone)
        assert held.values["quadplex_allowed"].value is False, zone
        assert held.values["quadplex_allowed"].levers == frozenset({"civic_corridor"}), zone
        assert held.missing_required == OWED, zone


def test_the_new_citations_all_point_at_their_own_sentence(gresham: Layer) -> None:
    ready = readiness_for(gresham, store=ProvenanceStore())
    assert ready.no_evidence == ()
    assert ready.misquoted == ()
