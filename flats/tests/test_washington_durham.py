"""Durham: the readings a reviewer would stop on.

The City of Durham Development Code (revised November 13, 2025) is one PDF of
twelve chapters. Chapter 2 names eight districts; Metro's regional zoning
layer carries five of them (SDR, MDR, IP, OP, NR) and none of the three
overlays. The draft is pinned here where it reads against the grain of a
quick look, so a later edit has to argue with it.

- **Only SDR admits the pod.** 2.8.1.6 permits "Middle housing" outright,
  and 12.2.29 makes a quadplex "four attached dwelling units on a lot".
- **MDR refuses, conservatively.** Its use list has no middle housing row;
  the nearest, "Multiple residential units within a commonly-owned
  structure, including but not limited to residential condominia", reads as
  condominium, and Table 9.10.9 sends MDR development to a Type 2 review on
  a discretionary criterion. A question for the owner, not a settled answer.
- **The rear yard is 20 feet on one lot**, the code's figure for "detached
  dwelling units", held conservatively though 12.2.29 calls a quadplex's
  units attached (a question for the owner). Townhouse lots take the 15
  for "attached units".
- **"Minimum base density" is read as a floor**: one dwelling per 10,000
  square feet, held as ``sqft_per_unit``.
- **The drive is 30 feet two-way or 20 one-way**, 3.7.1.4.2's row for 3 to
  49 units, not Table 3.7.1.8's "10-30" for SDR (Doubts, in the handoff).
- **One parking space a unit, no maximum** (Table 3.7.5).
- **The townhouse road is held as variants**: 7.12.6's 1,500 square feet,
  7.12.7's 18 units an acre, 7.12.8's zero internal sides, and 7.12.9's
  single side approach on a corner.
"""

from __future__ import annotations

import pytest

from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer, Status

pytestmark = pytest.mark.unit

DURHAM = "or/washington/durham"

#: The districts of Chapter 2 that list no dwelling the pod can be. MDDO, BPO
#: and NRO are overlays Metro's map did not carry on 2026-09-29.
REFUSED = ("MDR", "MDDO", "IP", "OP", "BPO", "NR", "NRO")


@pytest.fixture(scope="module")
def durham() -> Layer:
    return load_rules()[DURHAM]


def _text(quote: str) -> str:
    return " ".join(ProvenanceStore().quote(quote).split())


def test_every_district_of_chapter_2_is_held(durham: Layer) -> None:
    """Eight zone blocks and no map rulings: every code Metro prints for
    Durham is a district the code names."""
    assert set(durham.zones) == {"SDR", *REFUSED}
    assert dict(durham.zone_rulings) == {}
    assert list(durham.ingest["juris_city_codes"]) == ["DURHAM"]


def test_only_sdr_admits_the_pod(durham: Layer) -> None:
    admitted = {
        z for z, held in durham.zones.items() if held.values["quadplex_allowed"].value
    }
    assert admitted == {"SDR"}
    use = durham.zones["SDR"].values["quadplex_allowed"]
    assert use.variants == ()
    text = _text(use.prov.quote)
    assert "2.8.1 Uses permitted outright in the SDR district include:" in text
    assert "2.8.1.6 Middle housing" in text
    assert "requires only ministerial review" in text


def test_mdr_refuses_on_the_condominium_noun(durham: Layer) -> None:
    held = durham.zones["MDR"]
    assert set(held.values) == {"quadplex_allowed"}
    use = held.values["quadplex_allowed"]
    assert use.value is False
    text = _text(use.prov.quote)
    assert (
        "Multiple residential units within a commonly-owned structure, including "
        "but not limited to residential condominia"
    ) in text
    assert "Middle housing" not in text
    assert "read as condominium" in use.prov.cite
    assert "Type 2" in use.prov.cite


def test_the_other_districts_list_no_dwelling_the_pod_can_be(durham: Layer) -> None:
    for zone in REFUSED:
        held = durham.zones[zone]
        assert set(held.values) == {"quadplex_allowed"}, zone
        assert held.values["quadplex_allowed"].value is False, zone
        assert "Middle housing" not in _text(
            held.values["quadplex_allowed"].prov.quote
        ), zone


def test_the_sdr_lot(durham: Layer) -> None:
    held = durham.zones["SDR"].values
    assert held["min_lot_sqft"].value == 10000
    assert "The minimum lot area in the SDR district shall be 10,000 square feet" in (
        _text(held["min_lot_sqft"].prov.quote)
    )
    (lots,) = held["min_lot_sqft"].variants
    assert (lots.value, lots.when) == (1500, ("unit_lots",))
    assert "The minimum lot size for a townhouse shall be 1,500 square feet" in _text(
        lots.prov.quote
    )
    assert held["min_frontage_ft"].value == 20
    assert "shall be 20 feet for all residential uses" in _text(
        held["min_frontage_ft"].prov.quote
    )
    assert held["max_height_ft"].value == 35


def test_the_base_density_is_read_as_a_floor(durham: Layer) -> None:
    floor = durham.zones["SDR"].values["min_density_du_per_acre"]
    assert floor.sqft_per_unit == 10000
    assert (
        "The minimum base density for the SDR district shall be 10,000 square "
        "feet per dwelling"
    ) in _text(floor.prov.quote)
    ceiling = durham.zones["SDR"].values["max_density_du_per_acre"]
    assert ceiling.value == 18
    assert "shall be 18 dwelling units per gross acre" in _text(ceiling.prov.quote)


def test_the_yards(durham: Layer) -> None:
    held = durham.zones["SDR"].values
    assert held["setback_front_ft"].value == 20
    assert held["setback_side_ft"].value == 10
    assert held["setback_street_side_ft"].value == 20
    (wall,) = held["setback_side_ft"].variants
    assert (wall.value, wall.when) == (0, ("attached_wall",))
    text = _text(held["setback_front_ft"].prov.quote)
    assert "shall be 10 feet from the side and 20 feet from the corner" in text


def test_the_rear_yard_is_the_detached_figure_until_the_owner_says(
    durham: Layer,
) -> None:
    """20 on one lot, the stricter of 3.1.3's two figures; the 15 for
    "attached units" is the reading a quadplex's definition invites, and it
    is put to the owner rather than taken."""
    rear = durham.zones["SDR"].values["setback_rear_ft"]
    assert rear.value == 20
    assert (
        "shall be 20 feet for detached dwelling units and 15 feet for attached units"
        in _text(rear.prov.quote)
    )
    assert "conservatively" in rear.prov.cite
    (lots,) = rear.variants
    assert (lots.value, lots.when) == (15, ("unit_lots",))
    assert "7.12.8" in lots.prov.cite


def test_parking_is_one_a_unit_and_no_maximum(durham: Layer) -> None:
    minimum = durham.defaults["parking_min_per_unit"]
    assert minimum.value == 1
    assert "Single Dwelling and Middle Housing, Attached or 1 / No maximum Detached" in (
        _text(minimum.prov.quote)
    )
    assert durham.defaults["parking_max_per_unit"].exempt is True
    # No stall or aisle is stated anywhere in Chapter 3, and none is held.
    for field in (
        "parking_stall_width_ft",
        "parking_stall_depth_ft",
        "parking_aisle_one_way_ft",
        "parking_aisle_two_way_ft",
    ):
        assert field not in durham.defaults, field


def test_the_drive_is_the_three_to_forty_nine_unit_row(durham: Layer) -> None:
    held = durham.defaults
    assert held["driveway_min_width_two_way_ft"].value == 30
    assert held["driveway_min_width_one_way_ft"].value == 20
    assert (
        "for 3 to 49 dwelling units, 1 two-way at least 30 feet wide or 2 one -way "
        "each at least 20 feet wide"
    ) in _text(held["driveway_min_width_two_way_ft"].prov.quote)
    assert held["driveway_approach_max_width_ft"].value == 40


def test_a_corner_townhouse_project_takes_the_side(durham: Layer) -> None:
    access = durham.defaults["corner_access_street"]
    assert access.value == "any"
    (side,) = access.variants
    assert (side.value, side.when) == ("side", ("unit_lots",))
    assert (
        "A townhouse project that includes a corner lot shall take access from a "
        "single driveway approach on the side of the corner lot"
    ) in _text(side.prov.quote)
    assert durham.defaults["front_lot_line_corner"].value == "both"
    # No corner lot is defined (12.1 sends it to Webster's), and none is held.
    assert dict(durham.definitions) == {}


def test_open_space_is_five_percent_of_the_site(durham: Layer) -> None:
    held = durham.zones["SDR"].values["open_space_min_pct"]
    assert held.value == 5
    assert "shall occupy not less than 5% of the gross site area" in _text(
        held.prov.quote
    )


def test_nothing_in_the_draft_is_verified(durham: Layer) -> None:
    for zone, held in durham.zones.items():
        for field, value in held.values.items():
            assert value.status is not Status.verified, (zone, field)
            for variant in value.variants:
                assert variant.status is not Status.verified, (zone, field)
    for field, value in durham.defaults.items():
        assert value.status is not Status.verified, field
