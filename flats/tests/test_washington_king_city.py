"""King City: the readings a reviewer would stop on.

The King City Community Development and Zoning Code (Municipal Code Title 16)
has two kinds of district. The older ones (16.84 to 16.112) share one
housing-type table, 16.84.010, with no triplex or fourplex row. The Kingston
Terrace District (16.114, Ordinance 2023-04) has its own use, density and
dimensional tables, lists "Duplex, Triplex, Fourplex" as allowed outright in
all four of its neighbourhood zones, and exempts itself from the older
districts' chapters and from the citywide parking chapter. The draft is
pinned here where it reads against the grain of a quick look, so a later edit
has to argue with it.

- **Only the four Kingston Terrace zones admit the pod.** The six older
  residential districts are refused on 16.84.010, which is a question for the
  owner (King City is a Large City under OAR 660-046), not a settled answer.
- **The lot sizes are the printed figures.** Table 16.114-4 glues note 16 to
  Town Center's and Beef Bend's 1,500 ("1,50016"); the note says the figure
  "may be reduced to 1,000", read the stricter way.
- **Rural Character's side yard is 10, not the 5 the table prints**: note 19,
  10 feet for a two-story building, and the pod is two stories.
- **There is no parking minimum and no maximum** in Kingston Terrace
  (16.114.130 C.1 and Table 16.114-13).
- **Coverage is held as building coverage**, which is looser than the code:
  King City's cap counts buildings and impervious surfaces together.
- **The five county codes on the city's map are pockets of the county
  layer.** 16.80.050 A keeps an annexed area's county zoning until the city
  rezones it.
"""

from __future__ import annotations

import pytest

from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer, Status

pytestmark = pytest.mark.unit

KING_CITY = "or/washington/king-city"
COUNTY = "or/washington/_unincorporated"

#: The Kingston Terrace neighbourhood zones: Fourplex Y in Table 16.114-2.
KINGSTON_TERRACE = ("KTTC", "KTBB", "KTC", "KTRC")
#: 16.84.010 has no triplex or fourplex row for these six.
OLDER_RESIDENTIAL = ("R-9", "R-12", "R-15", "R-24", "SF", "AT")
#: Permitted-use lists naming no triplex or fourplex.
OTHER_REFUSED = ("NMU", "LC", "CF", "ROS")
#: The map's other spellings of held districts.
ALIASES = {
    "R9": "R-9",
    "R12": "R-12",
    "Town Center": "KTTC",
    "Beef Bend Neighborhood": "KTBB",
    "Central Neighborhood": "KTC",
    "Rural Character Neighborhood": "KTRC",
}
#: County codes kept on annexed land under 16.80.050 A.
POCKETS = {
    "R-6 (WC)": "R-6",
    "R-9 (WC)": "R-9",
    "R-15 (WC)": "R-15",
    "CBD (WC)": "CBD",
    "INST (WC)": "INST",
}
#: Table 16.114-3, minimum net density, units per net acre.
DENSITY = {"KTTC": 22, "KTBB": 18, "KTC": 10, "KTRC": 8}


@pytest.fixture(scope="module")
def king_city() -> Layer:
    return load_rules()[KING_CITY]


def _use(layer: Layer, zone: str):
    return layer.zones[zone].values["quadplex_allowed"]


def _text(quote: str) -> str:
    return " ".join(ProvenanceStore().quote(quote).split())


def test_every_code_on_the_maps_is_encoded_or_ruled(king_city: Layer) -> None:
    """14 districts from 16.80.020, and 12 rulings for the maps' other codes."""
    assert set(king_city.zones) == (
        set(KINGSTON_TERRACE) | set(OLDER_RESIDENTIAL) | set(OTHER_REFUSED)
    )
    assert set(king_city.zone_rulings) == (
        set(ALIASES) | set(POCKETS) | {"Neighborhood Mixed Use"}
    )
    assert not set(king_city.zones) & set(king_city.zone_rulings)
    assert list(king_city.ingest["juris_city_codes"]) == ["KING CITY"]


def test_only_kingston_terrace_admits_the_pod(king_city: Layer) -> None:
    admitted = {z for z in king_city.zones if _use(king_city, z).value is True}
    assert admitted == set(KINGSTON_TERRACE)
    for zone in KINGSTON_TERRACE:
        use = _use(king_city, zone)
        assert use.variants == (), zone
        assert use.qualified_by is None, zone
        text = _text(use.prov.quote)
        assert "Duplex, Triplex, Fourplex1 Y Y Y Y" in text, zone
        assert "exempt from development plan review" in text, zone


def test_the_older_districts_refuse_on_the_housing_type_table(
    king_city: Layer,
) -> None:
    """No triplex or fourplex row, and multi-dwelling is five or more units."""
    for zone in OLDER_RESIDENTIAL:
        held = king_city.zones[zone]
        assert set(held.values) == {"quadplex_allowed"}, zone
        use = held.values["quadplex_allowed"]
        assert use.value is False, zone
        text = _text(use.prov.quote)
        assert "R-9 R-12 R-15 R-24 SF AT" in text, zone
        assert "Duplex P P P P P P" in text, zone
        assert "Multi-dwelling N P P P N P" in text, zone
        assert "Triplex" not in text and "Fourplex" not in text, zone


def test_the_other_districts_refuse_on_their_permitted_uses(
    king_city: Layer,
) -> None:
    for zone in OTHER_REFUSED:
        held = king_city.zones[zone]
        assert set(held.values) == {"quadplex_allowed"}, zone
        assert held.values["quadplex_allowed"].value is False, zone
        text = _text(held.values["quadplex_allowed"].prov.quote)
        assert "Permitted uses in the" in text or "permitted uses" in text, zone
        assert "Fourplex" not in text and "fourplex" not in text, zone


def test_the_glued_lot_size_is_the_printed_figure(king_city: Layer) -> None:
    for zone, area in (("KTTC", 1500), ("KTBB", 1500), ("KTC", 2400), ("KTRC", 2400)):
        assert king_city.zones[zone].values["min_lot_sqft"].value == area, zone
    text = _text(king_city.zones["KTTC"].values["min_lot_sqft"].prov.quote)
    assert "15 1,50016 1,50016 2,400 2,400" in text
    # Note 16 is quoted beside it, and its "may be" is not taken.
    assert "may be reduced to 1,000 square feet" in text


def test_rural_character_takes_the_two_story_side_yard(king_city: Layer) -> None:
    side = king_city.zones["KTRC"].values["setback_side_ft"]
    assert side.value == 10
    assert "10 feet for two-story structures" in _text(side.prov.quote)
    for zone in ("KTTC", "KTBB", "KTC"):
        held = king_city.zones[zone].values["setback_side_ft"]
        assert held.value == 3, zone
        assert "0 or 3" in _text(held.prov.quote), zone


def test_the_front_yard_is_a_range(king_city: Layer) -> None:
    for zone in KINGSTON_TERRACE:
        held = king_city.zones[zone].values
        assert held["setback_front_ft"].value == 10, zone
        assert held["setback_front_max_ft"].value == 26, zone
        assert "10/26 10/26 10/26 10/26" in _text(held["setback_front_ft"].prov.quote)


def test_density_and_height(king_city: Layer) -> None:
    for zone, floor in DENSITY.items():
        held = king_city.zones[zone].values
        assert held["min_density_du_per_acre"].value == floor, zone
        assert "max_density_du_per_acre" not in held, zone
    assert "22 18 10 8" in _text(
        king_city.zones["KTTC"].values["min_density_du_per_acre"].prov.quote
    )
    assert king_city.zones["KTTC"].values["max_height_ft"].exempt is True
    for zone, feet in (("KTBB", 45), ("KTC", 35), ("KTRC", 35)):
        assert king_city.zones[zone].values["max_height_ft"].value == feet, zone


def test_coverage_is_held_as_building_coverage(king_city: Layer) -> None:
    for zone, cap in (("KTTC", 90), ("KTBB", 90), ("KTC", 90), ("KTRC", 80)):
        held = king_city.zones[zone].values["max_coverage_pct"]
        assert held.value == cap, zone
        assert "looser than the code" in held.prov.cite, zone
        assert "buildings and impervious surfaces" in _text(held.prov.quote), zone


def test_no_parking_minimum_or_maximum(king_city: Layer) -> None:
    minimum = king_city.defaults["parking_min_per_unit"]
    assert minimum.value == 0
    assert "no minimum vehicle parking requirements" in _text(minimum.prov.quote)
    maximum = king_city.defaults["parking_max_per_unit"]
    assert maximum.exempt is True
    assert "Duplex, Triplex, Fourplex Not Applicable" in _text(maximum.prov.quote)


def test_the_stall_row_is_the_ninety_degree_standard(king_city: Layer) -> None:
    held = king_city.defaults
    assert held["parking_stall_width_ft"].value == 9
    assert held["parking_stall_depth_ft"].value == 16
    assert held["parking_aisle_one_way_ft"].value == 16
    assert held["parking_aisle_two_way_ft"].value == 20
    assert "90 ° Standard 9.0 ft. 8.5 ft. 16.0 ft. 20.0 ft. 16.0 ft." in _text(
        held["parking_aisle_two_way_ft"].prov.quote
    )


def test_a_corner_is_two_public_streets(king_city: Layer) -> None:
    corner = king_city.definitions["corner_lot"]
    assert corner.test == "intersecting_frontages"
    assert corner.alleys_count is False
    assert corner.drives_count is False
    assert king_city.defaults["front_lot_line_corner"].value == "both"


def test_the_maps_other_codes(king_city: Layer) -> None:
    rulings = king_city.zone_rulings
    for code, zone in ALIASES.items():
        assert rulings[code].outcome == "alias", code
        assert rulings[code].of == zone, code
    county = load_rules()[COUNTY]
    for code, zone in POCKETS.items():
        assert rulings[code].outcome == "pocket", code
        assert rulings[code].of == COUNTY, code
        assert rulings[code].zone == zone, code
        assert "16.80.050 A" in rulings[code].note, code
        # The county district the pocket names is one the county layer holds.
        assert zone in county.zones, code
    nmu = rulings["Neighborhood Mixed Use"]
    assert nmu.outcome == "unencodable"
    assert nmu.of is None


def test_nothing_in_the_draft_is_verified(king_city: Layer) -> None:
    for zone, held in king_city.zones.items():
        for field, value in held.values.items():
            assert value.status is not Status.verified, (zone, field)
            for variant in value.variants:
                assert variant.status is not Status.verified, (zone, field)
    for field, value in king_city.defaults.items():
        assert value.status is not Status.verified, field
