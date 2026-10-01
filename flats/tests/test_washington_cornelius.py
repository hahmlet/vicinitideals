"""Cornelius: the readings a reviewer would stop on.

The Cornelius Municipal Code, Title 18 (eCode360, stored chapter by chapter),
names twelve districts the layer holds. Metro's regional zoning layer spells
four of them without the hyphen (R7, A2, C2, M1) and carries three Washington
County codes on a few annexed acres. The draft is pinned here where it reads
against the grain of a quick look, so a later edit has to argue with it.

- **Four districts admit the pod**: R-7, R-10, A-2 and CR each permit
  "Middle housing" outright. R-7's leftover one-dwelling-a-lot ban
  (18.20.040 (B)) is read as superseded; a question for the owner.
- **Two figures are converted, not copied.** R-7's and A-2's minimum
  densities are "per net acre", and 18.195 defines a net acre as 32,670
  square feet, so the floor is held per 43,560 (``acre_sqft``). A-2's rear
  yard grows "five feet per additional story" and is held for the
  two-storey pod (``plus_per_story_ft``).
- **The fourplex is not multi-family** (Steph, 2026-10-01): A-2's side yard
  and density floor are the figures that are not the multi-family ones.
- **CR's common-wall side is zero**: "shall not be required to have a side
  yard on side(s) where structures are attached".
- **One parking space a unit, no maximum**, a 9 by 20 stall.
- **A corner lot is two streets meeting at 135 degrees or less**, alleys not
  counted, and a private drive is not a street.
"""

from __future__ import annotations

import pytest

from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer, Status

pytestmark = pytest.mark.unit

CORNELIUS = "or/washington/cornelius"

ADMITTED = ("R-7", "R-10", "A-2", "CR")

#: The districts whose use lists hold no dwelling the pod can be, each for its
#: own reason (the zone notes and the layer comments say which).
REFUSED = ("MHP", "C-2", "CC", "CMU", "GMU", "LI", "M-1", "NRO")


@pytest.fixture(scope="module")
def cornelius() -> Layer:
    return load_rules()[CORNELIUS]


def _text(quote: str) -> str:
    return " ".join(ProvenanceStore().quote(quote).split())


def test_every_district_is_held_and_the_map_spellings_ruled(cornelius: Layer) -> None:
    assert set(cornelius.zones) == {*ADMITTED, *REFUSED}
    rulings = dict(cornelius.zone_rulings)
    aliases = {code: r.of for code, r in rulings.items() if r.outcome == "alias"}
    assert aliases == {"R7": "R-7", "A2": "A-2", "C2": "C-2", "M1": "M-1"}
    unencodable = {code for code, r in rulings.items() if r.outcome == "unencodable"}
    # Washington County codes on annexed land; the code keeps no county zoning.
    assert unencodable == {"FD-20", "FD-10", "AF-5"}
    assert list(cornelius.ingest["juris_city_codes"]) == ["CORNELIUS"]


def test_four_districts_admit_the_pod(cornelius: Layer) -> None:
    admitted = {
        z for z, held in cornelius.zones.items() if held.values["quadplex_allowed"].value
    }
    assert admitted == set(ADMITTED)
    for zone in ADMITTED:
        assert "Middle housing" in _text(
            cornelius.zones[zone].values["quadplex_allowed"].prov.quote
        ), zone


def test_the_refusals_hold_the_use_row_only(cornelius: Layer) -> None:
    for zone in REFUSED:
        held = cornelius.zones[zone]
        assert set(held.values) == {"quadplex_allowed"}, zone
        assert held.values["quadplex_allowed"].value is False, zone


def test_r7_and_a2_density_floors_are_per_the_citys_own_acre(cornelius: Layer) -> None:
    """18.195 defines a net acre as 32,670 square feet; "four dwellings per
    net acre" is 5.33 per 43,560. A-2's floor is "eight dwellings per net
    acre for single-family, and 11 for multi-family development", and the
    fourplex is not multi-family (Steph, 2026-10-01): 8, or 10.67 per
    43,560. CR's "11 dwellings per net acre for all other dwelling types"
    does not turn on the word and keeps its 11."""
    r7 = cornelius.zones["R-7"].values["min_density_du_per_acre"]
    assert r7.acre_sqft == 32670
    assert r7.value == pytest.approx(4 * 43560 / 32670, abs=1e-6)
    assert "The minimum density allowed is four dwellings per net acre" in _text(
        r7.prov.quote
    )
    a2 = cornelius.zones["A-2"].values["min_density_du_per_acre"]
    assert a2.acre_sqft == 32670
    assert a2.value == pytest.approx(8 * 43560 / 32670, abs=1e-6)
    assert "eight dwellings per net acre for single-family" in _text(a2.prov.quote)
    # CR prints its own "net acreage" sentence and holds the printed 11.
    cr = cornelius.zones["CR"].values["min_density_du_per_acre"]
    assert cr.value == 11


def test_a2_rear_yard_grows_per_storey_and_the_side_is_not_multi_family(
    cornelius: Layer,
) -> None:
    """The rear rule is every structure's: "No rear yard shall be less than
    10 feet ... plus five feet per additional story". The side rule splits
    single-family from multi-family, and the fourplex is not multi-family
    (Steph, 2026-10-01), so the side is the plain 5 -- the draft held the
    multi-family 10."""
    held = cornelius.zones["A-2"].values
    rear, side = held["setback_rear_ft"], held["setback_side_ft"]
    assert (rear.value, rear.plus_per_story_ft) == (15, 5)
    assert (side.value, side.plus_per_story_ft) == (5, None)
    assert side.variants == ()
    assert "No rear yard shall be less than 10 feet in depth for a single-story" in (
        _text(rear.prov.quote)
    )
    assert "For single-family residences, the minimum width of side yards" in (
        _text(side.prov.quote)
    )
    assert held["setback_street_side_ft"].value == 10


def test_max_density_does_not_bind_the_pod(cornelius: Layer) -> None:
    for zone in ("R-7", "A-2", "CR"):
        assert cornelius.zones[zone].values["max_density_du_per_acre"].exempt, zone
    r7 = cornelius.zones["R-7"].values["max_density_du_per_acre"]
    assert "Maximum density does not apply to duplexes, triplexes, quadplexes" in (
        _text(r7.prov.quote)
    )
    (lots,) = r7.variants
    assert (lots.value, lots.when) == (20, ("unit_lots",))


def test_crs_common_wall_side_is_zero(cornelius: Layer) -> None:
    side = cornelius.zones["CR"].values["setback_side_ft"]
    assert side.value == 5
    (wall,) = side.variants
    assert (wall.value, wall.when) == (0, ("attached_wall",))
    assert "shall not be required to have a side yard" in _text(wall.prov.quote)


def test_the_r10_lot(cornelius: Layer) -> None:
    held = cornelius.zones["R-10"].values
    assert held["min_lot_sqft"].value == 10000
    assert held["min_lot_width_ft"].value == 80
    assert held["min_lot_depth_ft"].value == 80
    assert held["setback_front_ft"].value == 25
    assert held["setback_rear_ft"].value == 25
    assert held["setback_side_ft"].value == 10
    assert held["setback_street_side_ft"].value == 20


def test_parking_is_one_a_unit_and_no_maximum(cornelius: Layer) -> None:
    minimum = cornelius.defaults["parking_min_per_unit"]
    assert minimum.value == 1
    assert "Middle Housing 1.0/DU" in _text(minimum.prov.quote)
    assert cornelius.defaults["parking_max_per_unit"].exempt is True
    assert cornelius.defaults["parking_stall_width_ft"].value == 9
    assert cornelius.defaults["parking_stall_depth_ft"].value == 20
    # The aisle is "of sufficient width" (18.145.050): no figure, none held.
    for field in ("parking_aisle_one_way_ft", "parking_aisle_two_way_ft"):
        assert field not in cornelius.defaults, field


def test_a_corner_is_135_degrees_and_a_private_drive_is_not_a_street(
    cornelius: Layer,
) -> None:
    corner = cornelius.definitions["corner_lot"]
    assert corner.max_intersection_angle_deg == 135
    assert corner.alleys_count is False
    assert "135" in _text(corner.quote)
    assert cornelius.private_drives.street is False
    assert "which provides for public use" in _text(cornelius.private_drives.quote)
    assert cornelius.defaults["front_lot_line_corner"].value == "shortest"


def test_nothing_in_the_draft_is_verified(cornelius: Layer) -> None:
    for zone, held in cornelius.zones.items():
        for field, value in held.values.items():
            assert value.status is not Status.verified, (zone, field)
            for variant in value.variants:
                assert variant.status is not Status.verified, (zone, field)
    for field, value in cornelius.defaults.items():
        assert value.status is not Status.verified, field
