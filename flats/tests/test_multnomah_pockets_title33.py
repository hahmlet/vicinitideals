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
the county's code never names. RF joined them on 2026-11-09, when Steph
ruled it farm land outside the state middle-housing law in the city and the
pockets alike (rulings.yaml 2026-11-09-rf-is-farm-land): a Title 33 zone that
refuses the pod at the use gate, with nothing left to hold the county's
chapter on it.
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

#: The Portland-administered pockets this layer screens on Title 33 that
#: allow the pod, and so carry the plan-district hold.
POCKETS = ("R5", "R7", "R10", "R20")
#: Every Portland-administered pocket zone, parking and outdoor area included.
#: RF refuses the pod at the use gate but still owes no county sentence.
TITLE33_ZONES = POCKETS + ("RF",)


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
    """33.266.120.C.2 prints ten feet, stated of spaces, for this building.

    The card used to cite 39.6580(A) and borrow the front yard (10 to 20 ft
    here). The sentence the pockets owe instead prints its own figure, so the
    value is held as printed and no longer follows the building setback.
    """
    # 2026-11-10 (a): line pins re-pointed onto the 11/1/26 reprint (RICAP 11, FOLLOWUPS 165):
    # L268/L272/L303 -> L272/L276/L309-L310. The reprint moved the rule from
    # C.2.a ("Generally, parking spaces are not allowed ...") up into C.2 itself
    # ("Except as follows, parking spaces are not allowed within the first 10 /
    # feet from a front lot line"), so the phrase now wraps across two lines.
    lines = _lines(store, TITLE33_PARKING)
    assert lines[271].strip().startswith("33.266.120 Development Standards for Houses")
    assert "fourplexes" in lines[275]
    c2 = " ".join(ln.strip() for ln in lines[308:310])
    assert "parking spaces are not allowed within the first 10 feet from a front lot" in c2

    for zone in TITLE33_ZONES:
        held = county.zones[zone].values["parking_street_setback_ft"]
        assert held.same_as is None
        assert held.value == 10
        assert held.prov.quote.startswith(TITLE33_PARKING)
        assert corpus.resolve(COUNTY, zone).get("parking_street_setback_ft") == 10


def test_rf_takes_the_title_33_card_after_the_farm_land_ruling(
    county: Layer, corpus: RuleSet
) -> None:
    """Steph 2026-11-09: RF is farm land, in the pockets as in the city.

    The county card was a hold while the state middle-housing route was an
    open question. With the route closed, pocket RF is Portland's RF zone
    administered under Title 33, and its parking card is 33.266.120's.
    """
    held = county.zones["RF"].values["parking_street_setback_ft"]
    assert held.same_as is None
    assert held.value == 10
    assert held.prov.quote.startswith(TITLE33_PARKING)
    got = corpus.resolve(COUNTY, "RF")
    assert got.get("quadplex_allowed") is False
    assert got.values["quadplex_allowed"].relief == ()


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
    for zone in TITLE33_ZONES:
        missing = parking - set(county.zones[zone].values)
        assert not missing, f"{zone} falls through to the county for {sorted(missing)}"


def test_the_pockets_read_120_for_the_rectangle_and_the_drive(
    county: Layer, store: ProvenanceStore, corpus: RuleSet
) -> None:
    """Rectangle, driveway, front ban and paving cap as 33.266.120 prints them.

    The aisle is NOT here: 120 states none, and since 2026-11-09 the pockets
    take Steph's 20 ft (below), as Portland does.
    """
    # 2026-11-10 (a): line pins re-pointed onto the 11/1/26 reprint (RICAP 11, FOLLOWUPS 165):
    # same words, new lines (33.266.120 now runs L272-L361).
    lines = _lines(store, TITLE33_PARKING)
    assert "A parking space must be at least 9 feet by 18 feet." in lines[330]
    assert "The minimum driveway width on private property is 9 feet." in lines[331]
    assert "Vehicle area is prohibited between the primary structure and the street" in lines[285]
    assert "No more than 40 percent of the land area between the front lot line and the" in lines[300]
    assert "If the lot abuts an alley, all parking and vehicle access to the site" in lines[325]
    assert "except for residential vehicle" in lines[398]
    section_120 = " ".join(lines[271:361]).lower()
    assert "aisle" not in section_120

    for zone in TITLE33_ZONES:
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
            "parking_lot_line_buffer_ft",
            "parking_side_prohibited",
        ):
            assert values[absent].exempt, f"{zone}.{absent} should be read as stated-none"


def test_the_pockets_owe_table_110_4s_outdoor_area_per_lot(
    county: Layer, store: ProvenanceStore, corpus: RuleSet
) -> None:
    """250 square feet and a 12-foot square, per lot, RF through R5."""
    # 2026-11-10 (a): line pins re-pointed onto the 11/1/26 reprint (RICAP 11, FOLLOWUPS 165):
    # L435/L471/L903 -> L426/L462/L859, same words.
    lines = _lines(store, f"{COUNTY}/33.110.txt")
    assert lines[425].split()[:6] == ["Standard", "RF", "R20", "R10", "R7", "R5"]
    assert lines[461].count("250 sq. ft.") == 5
    assert "per lot" in lines[858]
    for zone in TITLE33_ZONES:
        got = corpus.resolve(COUNTY, zone)
        assert got.get("open_space_min_sqft") == 250
        assert got.get("open_space_min_dimension_ft") == 12


def test_a_pocket_inside_a_portland_plan_district_is_held(
    county: Layer, store: ProvenanceStore
) -> None:
    """33.500.040 puts the plan district above the base zone, and it is unread here.

    Johnson Creek Basin, Northwest Hills and Pleasant Valley reach pocket lots.
    The Portland layer's lot-by-lot plan-district trace never included them,
    so the whole outline holds the lot until the districts are read for it.
    """
    # 2026-11-10 (a): line pins re-pointed onto the 11/1/26 reprint (RICAP 11, FOLLOWUPS 165):
    # L32/L34 -> L33/L35, same words.
    lines = _lines(store, f"{PORTLAND}/33.500.txt")
    assert lines[32].strip().startswith("33.500.040 Relationship to Other Regulations")
    assert "the plan district regulations control" in lines[34]

    area = county.drawn_areas["plan_district_unmeasured"]
    assert area.condition == "pdx_plan_district_unmeasured"
    assert set(area.zones) == set(POCKETS)
    assert area.file == "or/multnomah/portland/plan-districts.geojson"
    for zone in POCKETS:
        held = county.zones[zone].values["quadplex_allowed"].qualified_by
        assert held == "pdx_plan_district_unmeasured"
    assert county.zones["RF"].values["quadplex_allowed"].qualified_by is None


def test_the_pockets_take_stephs_portland_parking_rulings(
    county: Layer, store: ProvenanceStore, corpus: RuleSet
) -> None:
    """2026-11-09, "Extend both" (rulings.yaml 2026-11-09-multco-pockets-portland-parking).

    The court is drawn on a 20 ft aisle (2026-09-30-portland-aisle-20ft, Table
    266-4 at 90 degrees) and an alley-fed plan backs out into the alley with
    20 ft of room (2026-09-13-portland-alley-is-aisle, 33.266.130.F.1.b(2)),
    the same values the Portland layer holds. RF is on Title 33 too since
    2026-11-09-rf-is-farm-land, but outside this ruling's scope.
    """
    # 2026-11-10 (a): line pins re-pointed onto the 11/1/26 reprint (RICAP 11, FOLLOWUPS 165):
    # L516/L525/L485-L486 -> L530/L539/L499-L500, same words; the values'
    # quotes (L398-L399,L508-L509,L530-L532,L539 and L499-L502) were checked
    # against the reprint on the same day.
    lines = _lines(store, TITLE33_PARKING)
    assert lines[529].strip() == "Table 266-4"
    row = lines[538].split()
    assert row[0] == "90°" and row.count("20") == 2
    assert "vehicles back out into an alley" in lines[498]
    assert "maneuvering area of at least 20 feet" in lines[499]

    portland = load_rules()[PORTLAND].defaults
    for zone in POCKETS:
        values = county.zones[zone].values
        got = corpus.resolve(COUNTY, zone)
        for field in (
            "parking_aisle_one_way_ft",
            "parking_aisle_two_way_ft",
            "parking_alley_backout_ft",
        ):
            assert values[field].value == portland[field].value == 20, f"{zone}.{field}"
            assert values[field].prov.quote.startswith(TITLE33_PARKING)
            assert "Steph" in values[field].prov.cite
            assert got.get(field) == 20

    # 2026-11-10: RF no longer keeps the county's chapter (25 ft, MCC 39.6565).
    # Since rulings.yaml 2026-11-09-rf-is-farm-land (FOLLOWUPS 173, merged in
    # rel7 after this test was written) pocket RF is on Title 33's card like the
    # others, but the "Extend both" ruling is scoped to R5-R20, so RF's aisle is
    # Title 33's stated none (33.266.120 names no aisle; 130.B excludes it)
    # rather than Steph's 20 ft. RF refuses the pod at the use gate, so no
    # colour rests on it.
    rf_values = county.zones["RF"].values
    for field in ("parking_aisle_one_way_ft", "parking_aisle_two_way_ft"):
        assert rf_values[field].exempt and rf_values[field].value is None, field
        assert rf_values[field].prov.quote.startswith(TITLE33_PARKING), field
        assert "Steph" not in rf_values[field].prov.cite, field
    rf = corpus.resolve(COUNTY, "RF")
    assert rf.get("parking_aisle_two_way_ft") is None
    assert rf.get("parking_alley_backout_ft") is None


def test_a_pocket_court_is_drawn_as_portlands_is(corpus: RuleSet) -> None:
    """A pocket fixture: the court the screen charges, street-fed and alley-fed.

    Street-fed it is a stall and a 20 ft aisle, not the design's 24. On a lot
    whose alley runs the whole rear line it is a stall plus what a 14 ft alley
    leaves short of 20 ft of back-out (6 ft). Both match Portland's lot for lot.
    """
    from flats.designs.model import load_catalog
    from flats.score.paper import Alley, court_depth

    design = load_catalog().latest("pod56x36")
    alley = Alley(width_ft=14.0, at_rear=True, rear_whole=True)
    city = corpus.resolve(PORTLAND, "R5")
    for zone in POCKETS:
        got = corpus.resolve(COUNTY, zone)
        street, used = court_depth(design, got)
        assert "parking_aisle_two_way_ft" in used
        assert street == court_depth(design, city)[0]
        assert street < design.parking.court_depth_ft

        fed, used = court_depth(design, got, alley)
        assert "parking_alley_backout_ft" in used
        assert fed == court_depth(design, city, alley)[0]
        assert fed == pytest.approx(street - 20.0 + 6.0)
