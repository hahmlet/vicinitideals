"""The Portland pockets are screened on Title 33, because the county adopted it.

Multnomah County and the City of Portland signed an Intergovernmental Agreement
to Transfer Land Use Planning Responsibilities in 2002 (Portland Ordinance
176115; amended 2005 for Pleasant Valley and 2011 for the tree code). Section
I.D: the county "has adopted the city comprehensive plan, zoning ordinance and
other regulations as the County's" for the unincorporated land inside
Portland's Urban Services Boundary, and Section III.C.2.a has the City review
land use, zoning and building permits there "using the City's ... zoning ...
as adopted by the County". The county keeps adopting each Title 33 amendment
(Ord. 1344, 2026, for RICAP 11 among others), and MCC 39.1100(B) says its own
procedures do not apply to "permits reviewed by a city on behalf of the county
pursuant to intergovernmental agreement".

So the pockets' parking is PCC 33.266, not MCC 39.6500 to 39.6600 -- which is
what the page check found when it saw a county sentence on a card for a zone
the county's code never names. RF is left as it was: whether the state
middle-housing path reaches it is a question still waiting on Steph.
"""

from __future__ import annotations

import pytest

from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet
from flats.encode.load import load_trusted

pytestmark = pytest.mark.unit

COUNTY = "or/multnomah/_unincorporated"
PORTLAND = "or/multnomah/portland"
TITLE33_PARKING = f"{COUNTY}/33.266.txt"

#: The Portland-administered pockets this layer screens on Title 33. RF is
#: Portland-administered too, and deliberately absent until Steph rules on it.
POCKETS = ("R5", "R7", "R10", "R20")


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


def test_the_layer_copy_of_title_33_is_the_portland_copy(store: ProvenanceStore) -> None:
    """Line numbers cited here transfer, because the text is the same text."""
    for doc in ("33.266.txt", "33.110.txt"):
        assert store.load(f"{COUNTY}/{doc}").text == store.load(f"{PORTLAND}/{doc}").text


def test_the_pocket_parking_setback_is_title_33s_ten_feet(
    county: Layer, store: ProvenanceStore, corpus: RuleSet
) -> None:
    """33.266.120.C.2.a prints ten feet, stated of spaces, for this building.

    The card used to cite 39.6580(A) and borrow the front yard (10 to 20 ft
    here). The sentence the pockets owe instead prints its own figure, so the
    value is held as printed and no longer follows the building setback.
    """
    lines = _lines(store, TITLE33_PARKING)
    assert lines[267].strip().startswith("33.266.120 Development Standards for Houses")
    assert "fourplexes" in lines[271]
    assert "parking spaces are not allowed within the first 10 feet from a front lot" in lines[302]

    for zone in POCKETS:
        held = county.zones[zone].values["parking_street_setback_ft"]
        assert held.same_as is None
        assert held.value == 10
        assert held.prov.quote.startswith(TITLE33_PARKING)
        assert corpus.resolve(COUNTY, zone).get("parking_street_setback_ft") == 10


def test_rf_keeps_its_county_card_until_steph_rules(county: Layer) -> None:
    """Not a reading -- a hold. RF waits on the middle-housing question."""
    held = county.zones["RF"].values["parking_street_setback_ft"]
    assert held.same_as == "setback_front_ft"
    assert held.prov.cite.startswith("MCC 39.6580(A)")


def test_every_county_parking_default_is_overridden_in_the_pockets(
    county: Layer, corpus: RuleSet
) -> None:
    """No pocket answer may fall through to MCC 39.6500-39.6600.

    A default the pocket does not restate would be the county's sentence on
    Portland's land -- the exact card the page check flagged. So every parking
    and front-line field `defaults:` holds is restated in each pocket.
    """
    parking = {
        name
        for name in county.defaults
        if name.startswith(("parking_", "driveway_", "corner_access", "front_lot_line_"))
    }
    assert parking, "the county defaults hold no parking fields any more"
    for zone in POCKETS:
        missing = parking - set(county.zones[zone].values)
        assert not missing, f"{zone} falls through to the county for {sorted(missing)}"


def test_the_pockets_read_120_and_never_table_266_4(
    county: Layer, store: ProvenanceStore, corpus: RuleSet
) -> None:
    """Rectangle, driveway, front ban and paving cap as 33.266.120 prints them."""
    lines = _lines(store, TITLE33_PARKING)
    assert "A parking space must be at least 9 feet by 18 feet." in lines[317]
    assert "The minimum driveway width on private property is 9 feet." in lines[318]
    assert "Vehicle area is prohibited between the primary structure and the street" in lines[281]
    assert "No more than 40 percent of the land area between the front lot line and the" in lines[293]
    assert "If the lot abuts an alley, all parking and vehicle access to the site" in lines[312]
    assert "except for residential vehicle" in lines[385]
    section_120 = " ".join(lines[267:348]).lower()
    assert "aisle" not in section_120

    for zone in POCKETS:
        got = corpus.resolve(COUNTY, zone)
        assert got.get("parking_stall_width_ft") == 9
        assert got.get("parking_stall_depth_ft") == 18
        assert got.get("driveway_min_width_two_way_ft") == 9
        assert got.get("driveway_min_width_one_way_ft") == 9
        assert got.get("parking_front_prohibited") is True
        assert got.get("parking_front_yard_max_pct") == 40
        assert got.get("parking_alley_access_required") is True
        values = county.zones[zone].values
        for absent in (
            "parking_min_per_unit",
            "parking_aisle_one_way_ft",
            "parking_aisle_two_way_ft",
            "parking_lot_line_buffer_ft",
            "parking_side_prohibited",
        ):
            assert values[absent].exempt, f"{zone}.{absent} should be read as stated-none"


def test_the_pockets_owe_table_110_4s_outdoor_area_per_lot(
    county: Layer, store: ProvenanceStore, corpus: RuleSet
) -> None:
    """250 square feet and a 12-foot square, per lot, RF through R5."""
    lines = _lines(store, f"{COUNTY}/33.110.txt")
    assert lines[434].split()[:6] == ["Standard", "RF", "R20", "R10", "R7", "R5"]
    assert lines[470].count("250 sq. ft.") == 5
    assert "per lot" in lines[902]
    for zone in POCKETS:
        got = corpus.resolve(COUNTY, zone)
        assert got.get("open_space_min_sqft") == 250
        assert got.get("open_space_min_dimension_ft") == 12
