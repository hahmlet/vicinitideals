"""Cornelius: the readings a reviewer would stop on.

The Cornelius Municipal Code, Title 18 (eCode360, stored chapter by chapter),
names twelve districts the layer holds. Metro's regional zoning layer spells
four of them without the hyphen (R7, A2, C2, M1) and carries three Washington
County codes on a few annexed acres. The draft is pinned here where it reads
against the grain of a quick look, so a later edit has to argue with it.

- **Four districts admit the pod**: R-7, R-10, A-2 and CR each permit
  "Middle housing" outright. R-7's leftover one-dwelling-a-lot ban
  (18.20.040 (B)) is read as superseded (Steph, 2026-10-01: cancelled by
  state law).
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
- **GMU opens only the townhouse path, and only behind the figure**
  (Steph, 2026-10-01). The fourplex on one lot stays refused; townhouses
  are "only permitted within subdistrict A" of Figure 18.75.065-1, an
  image no layer places a lot in, so the path is held behind
  ``inside_mapped_use_area`` and never comes back green. Its density floor
  is 18 per net acre on 18.195's 43,560 sq ft acre: 9,680 sq ft for four.
- **R-7 and R-10 carry a sun warning, not a sun hold** (Steph, 2026-10-01,
  "Green with a warning"): ``solar_shade_limit`` (18.160) puts
  ``solar_shade`` in the screening's warnings and never moves the colour,
  so an R-7 lot that clears everything else is GREEN with the warning on
  it. Covered parking is pinned in ``test_covered_parking.py``.
"""

from __future__ import annotations

import pytest

import dataclasses

from flats.designs.model import load_catalog
from flats.encode.load import load_trusted
from flats.fit.rectangle import Fit
from flats.provenance.store import ProvenanceStore
from flats.rules.conditions import CONDITIONS, condition
from flats.rules.loader import load_rules
from flats.rules.model import Layer, Status
from flats.rules.resolver import Verdict as RuleVerdict
from flats.score.configure import configure
from flats.score.screen import SOLAR_SHADE, LotFacts, Triage, screen
from flats.score.slack import SlackPolicy

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
        assert held.values["quadplex_allowed"].value is False, zone
        if zone == "GMU":
            continue  # the townhouse path, below
        assert set(held.values) == {"quadplex_allowed"}, zone
        assert held.values["quadplex_allowed"].variants == (), zone


def test_gmu_opens_only_the_townhouse_path_and_only_behind_the_figure(
    cornelius: Layer,
) -> None:
    """Steph, 2026-10-01: four homes on one lot stays no (the fourplex is not
    multi-family), and the townhouse row opens -- but only "within subdistrict
    A", drawn on Figure 18.75.065-1, which no map layer carries. Behind
    `inside_mapped_use_area`, which nothing measures, so never GREEN."""
    held = cornelius.zones["GMU"].values
    use = held["quadplex_allowed"]
    (townhouse,) = use.variants
    assert townhouse.value is True
    assert set(townhouse.when) == {"unit_lots", "inside_mapped_use_area"}
    assert condition("inside_mapped_use_area").assume is None
    text = _text(townhouse.prov.quote)
    assert "Single-family attached dwelling units, subject to CMC" in text
    assert "shall only be permitted within subdistrict A" in text
    assert "In subdistrict C, no ground floor residential uses are permitted" in text
    # The per-child-lot standards are on the unit-lot path.
    for name, value in (("min_lot_sqft", 2000), ("min_lot_width_ft", 20)):
        assert held[name].exempt, name
        (lots,) = held[name].variants
        assert (lots.value, lots.when) == (value, ("unit_lots",)), name
    assert held["max_height_ft"].value == 35
    assert held["setback_front_ft"].value == 5
    assert held["setback_rear_ft"].value == 10
    assert held["setback_side_ft"].value == 5
    # Owed, with the reason in the layer: the street side yard, lot depth.
    assert "setback_street_side_ft" not in held
    assert "min_lot_depth_ft" not in held


def test_gmu_density_is_per_the_43560_acre(cornelius: Layer) -> None:
    """GMU prints no net acre of its own, so it is 18.195's net acreage on the
    43,560 sq ft "Acre, gross" -- not the 32,670 R-7 and A-2 print. Four
    homes at 18 an acre may spread over no more than 9,680 net sq ft."""
    floor = cornelius.zones["GMU"].values["min_density_du_per_acre"]
    assert floor.value == 18
    assert floor.acre_sqft is None
    assert floor.measured_on == "net_developable_area"
    assert "Minimum density for ground-floor residential uses is 18 units per net acre" in (
        _text(floor.prov.quote)
    )
    assert "means 43,560 square feet" in _text(floor.measured_on_quote)
    assert 4 / floor.value * 43560 == pytest.approx(9680)
    assert cornelius.zones["GMU"].values["max_density_du_per_acre"].exempt


@pytest.mark.parametrize("zone", ["R-7", "R-10"])
def test_the_single_family_zones_carry_the_sun_rule_as_a_warning(zone: str) -> None:
    """Steph, 2026-10-01: flag every R-7 and R-10 lot for the solar balance
    point (18.160), build no shade check -- and then, "Green with a
    warning". The rule is held as ``solar_shade_limit``, quoted from 18.160,
    and the height is left as printed, with no fact behind it that a lot
    could lean on."""
    cornelius = load_rules()[CORNELIUS]
    held = cornelius.zones[zone].values
    assert held["max_height_ft"].value == 35
    assert held["max_height_ft"].qualified_by is None
    flag = held["solar_shade_limit"]
    assert flag.value is True
    assert "all structures in all single-family zones" in _text(flag.prov.quote)
    assert "solar-balance-point" in flag.prov.quote
    # The old carrier is gone, so nothing can lean on it.
    assert "solar_shade_point" not in CONDITIONS


def test_the_sun_warning_stops_at_the_single_family_zones(cornelius: Layer) -> None:
    for zone in ("A-2", "CR", "GMU"):
        assert "solar_shade_limit" not in cornelius.zones[zone].values, zone


def test_an_r7_lot_clearing_everything_else_is_green_with_the_sun_warning() -> None:
    """The ruling's whole point: the warning rides beside the colour. A
    generous R-7 lot, its draft rules signed as the bridge's "if signed"
    column signs them, screens GREEN with no reasons and ``solar_shade`` in
    its warnings; unsigned, it is UNKNOWN on the draft alone and carries the
    same warning."""
    rules = load_trusted(strict=False).rules
    design = load_catalog().latest("pod56x36")
    lot = LotFacts(lot_sqft=12000, frontage_ft=100, lot_width_ft=100, lot_depth_ft=120)
    config = configure(lot, design)
    draft = rules.resolve(CORNELIUS, "R-7", config.conditions, lot=config.measures)
    assert draft.verdict is RuleVerdict.unverified
    signed = dataclasses.replace(draft, verdict=RuleVerdict.trusted, untrusted=())
    room = design.parking.court_depth_ft + 20.0
    fit = Fit(
        fits=True,
        width_ft=56.0,
        depth_ft=36.0,
        best_depth_ft=36.0 + room,
        slack_ft=room,
        across_ft=120.0,
    )
    policy = SlackPolicy(tolerance={"fit_ft": 0.5})

    got = screen(signed, lot, design, fit, policy=policy, relief=None, config=config)
    assert got.triage is Triage.green
    assert got.reasons == ()
    assert got.warnings == (SOLAR_SHADE,)

    unsigned = screen(draft, lot, design, fit, policy=policy, relief=None, config=config)
    assert unsigned.triage is Triage.unknown
    assert unsigned.warnings == (SOLAR_SHADE,)

    # The same lot in A-2 carries no sun warning.
    a2 = rules.resolve(CORNELIUS, "A-2", config.conditions, lot=config.measures)
    assert screen(a2, lot, design, fit, policy=policy, relief=None, config=config).warnings == ()


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
