"""Sherwood: the readings a reviewer would stop on.

The Sherwood Zoning and Community Development Code (Title 16) prints one
residential use table (16.12.020) and one dimensional table (16.12.030) for
all five residential districts, and closes each commercial, industrial and
IP use table with "Uses listed in other sections of this code, but not within
this specific table are prohibited". The city's zoning map paints 35 codes;
21 are encoded as zones and 14 are ruled. The draft is pinned here where it
reads against the grain of a quick look, so a later edit has to argue with it.

- **The five residential districts admit the pod on one lot, and so do their
  PUD overlays -- as the plan allows.** 16.40.050 A permits middle housing in
  a Residential PUD "when approved as part of a Final Development Plan", and
  16.40.040 C makes a change of use a major change. Nothing measures what a
  plan approved, so every PUD's permission carries `site_specific_limitation`.
- **The side setback loads as 6, not the 5 the table prints.** 16.68.030 B.1
  sets any wall over 24 feet back "an additional one-half (1/2) foot for every
  one (1) foot in height over twenty four (24) feet". The pod is 26 feet,
  so one more foot. The loader applies the plane; `before_step_back` keeps 5.
  The section's reach (infill lots, or every lot) is read the stricter way.
- **16.68.030 A's floor area ratios are held as `max_far`** in LDR, MDRL,
  MDRH and HDR. VLDR is not on its list.
- **MDRH holds feet only.** Its row prints "35 feet or 2.5 stories", note 3
  takes the lesser, and the stories field takes whole numbers.
- **The quadplex parking maximum is None** in 16.94.020 Table 1, held as an
  exemption, and the minimum is four spaces a building (one a unit).
- **Old Town, open space, the growth-area code and eleven codes painted on
  unannexed land are ruled, not pockets.** Unlike Beaverton (BDC 10.40.1),
  Sherwood gives annexed land an interim city zone (16.04.040), so none of
  them screens under the county's layer.
"""

from __future__ import annotations

import pytest

from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer, Status

pytestmark = pytest.mark.unit

SHERWOOD = "or/washington/sherwood"

#: Triplex and Quadplex P in 16.12.020, with their own dimensional columns.
RESIDENTIAL = ("VLDR", "VLDR_PUD", "LDR", "MDRL", "MDRH", "HDR")
#: A Residential PUD over a base zone, painted with its own code on the map.
PUD_OVER = {
    "LDR_PUD": "LDR",
    "MDRL_PUD": "MDRL",
    "MDRH-PUD": "MDRH",
    "HDR_PUD": "HDR",
}
#: No triplex or quadplex row in the use table, and unlisted uses prohibited.
REFUSED = (
    "OC", "NC", "RC", "GC",
    "OC_PUD", "RC_PUD", "LI_PUD",
    "LI", "GI", "EI", "IP",
)
#: Map codes the layer rules instead of encoding.
RULED = (
    "Old Town", "OS", "UGA", "Unannex",
    "AF-5", "AF-10", "AF-20", "EFU", "FD-10", "FD-20", "R-9",
    "RRFF5", "MG", "MBP",
)
#: 16.68.030 A.1-A.4, in percent of lot area.
FLOOR_AREA = {"LDR": 0.5, "MDRL": 0.55, "MDRH": 0.6, "HDR": 0.65}


@pytest.fixture(scope="module")
def sherwood() -> Layer:
    return load_rules()[SHERWOOD]


def _use(layer: Layer, zone: str):
    return layer.zones[zone].values["quadplex_allowed"]


def _text(quote: str) -> str:
    return " ".join(ProvenanceStore().quote(quote).split())


def test_every_zone_on_the_map_is_encoded_or_ruled(sherwood: Layer) -> None:
    """35 codes on the city's zoning layer: 21 zones and 14 rulings."""
    assert len(sherwood.zones) == 21
    assert set(sherwood.zones) == set(RESIDENTIAL) | set(PUD_OVER) | set(REFUSED)
    assert set(sherwood.zone_rulings) == set(RULED)
    assert not set(sherwood.zones) & set(sherwood.zone_rulings)
    # The layer is chosen by JURIS_CITY, and SHERWOOD is the county's spelling.
    assert list(sherwood.ingest["juris_city_codes"]) == ["SHERWOOD"]


def test_the_pod_goes_on_one_lot_in_the_residential_districts(
    sherwood: Layer,
) -> None:
    admitted = {z for z in sherwood.zones if _use(sherwood, z).value is True}
    assert admitted == set(RESIDENTIAL) | set(PUD_OVER)
    for zone in admitted:
        assert _use(sherwood, zone).variants == (), zone
    assert "Triplex and Quadplex P P P P P" in _text(
        _use(sherwood, "LDR").prov.quote
    )


@pytest.mark.parametrize("zone", ["VLDR_PUD", *PUD_OVER])
def test_a_pud_admits_the_pod_only_as_its_plan_allows(
    sherwood: Layer, zone: str
) -> None:
    use = _use(sherwood, zone)
    assert use.value is True
    assert use.qualified_by == "site_specific_limitation"
    text = _text(use.qualified_quote)
    assert "when approved as part of a Final Development Plan" in text
    assert "change boundaries or uses" in text


@pytest.mark.parametrize(("zone", "base"), sorted(PUD_OVER.items()))
def test_a_pud_takes_its_base_zones_standards(
    sherwood: Layer, zone: str, base: str
) -> None:
    """16.40.050 C.3: lot size and setbacks consistent with the underlying zone."""
    held = sherwood.zones[zone]
    assert set(held.values) == {"quadplex_allowed"}
    assert held.like is not None
    assert held.like.zone == base


def test_the_residential_districts_are_not_qualified_themselves(
    sherwood: Layer,
) -> None:
    for zone in ("VLDR", "LDR", "MDRL", "MDRH", "HDR"):
        assert _use(sherwood, zone).qualified_by is None, zone


def test_refusals_carry_the_use_row_and_nothing_else(sherwood: Layer) -> None:
    for zone in REFUSED:
        held = sherwood.zones[zone]
        assert set(held.values) == {"quadplex_allowed"}, zone
        use = held.values["quadplex_allowed"]
        assert use.value is False, zone
        assert use.variants == (), zone
        text = _text(use.prov.quote)
        if zone.endswith("_PUD"):
            # 16.40.060 A: what the underlying zone permits outright. C.2's
            # waiver of "type of dwelling unit" is quoted beside it, so the
            # refusal can be read against the door a plan could open.
            assert "permitted outright in the underlying zoning district" in text
            assert "type of dwelling unit" in text
        else:
            assert "not within this specific table are prohibited" in text, zone


@pytest.mark.parametrize("zone", RESIDENTIAL)
def test_the_side_yard_plane_moves_the_five_foot_side_to_six(
    sherwood: Layer, zone: str
) -> None:
    side = sherwood.zones[zone].values["setback_side_ft"]
    assert side.before_step_back == 5
    assert side.step_back_at_ft == 24
    assert side.step_back_rise == 2
    # 26 ft of pod, two feet over 24, a half foot further in for each.
    assert side.value == 6
    assert "16.68.030 B.1" in side.step_back_cite
    assert "one-half ( 1/2) foot for every one (1) foot" in _text(
        side.step_back_quote
    )
    # Note 6 is on the side yard's own quote: no adjustment, no variance.
    assert "are not allowed" in _text(side.prov.quote)


def test_the_floor_area_ratio_is_held_where_16_68_030_lists_it(
    sherwood: Layer,
) -> None:
    for zone, far in FLOOR_AREA.items():
        held = sherwood.zones[zone].values["max_far"]
        assert held.value == far, zone
        assert "16.68.030 Building Design on Infill Lots" in _text(
            held.prov.quote
        ), zone
    assert "max_far" not in sherwood.zones["VLDR"].values
    assert "max_far" not in sherwood.zones["VLDR_PUD"].values


def test_mdrh_holds_feet_only(sherwood: Layer) -> None:
    held = sherwood.zones["MDRH"].values
    assert held["max_height_ft"].value == 35
    assert "max_height_stories" not in held
    text = _text(held["max_height_ft"].prov.quote)
    assert "35 feet or 2.5 stories" in text
    assert "lesser of feet or stories" in text
    for zone, feet, stories in (("LDR", 30, 2), ("MDRL", 30, 2), ("HDR", 40, 3)):
        assert sherwood.zones[zone].values["max_height_ft"].value == feet, zone
        assert sherwood.zones[zone].values["max_height_stories"].value == stories, zone


def test_the_quadplex_parking_standards(sherwood: Layer) -> None:
    minimum = sherwood.defaults["parking_min_per_unit"]
    assert minimum.value == 1
    assert "4 spaces total" in _text(minimum.prov.quote)
    maximum = sherwood.defaults["parking_max_per_unit"]
    assert maximum.exempt is True
    assert "Quadplex" in _text(maximum.prov.quote)
    assert "None None" in _text(maximum.prov.quote)


def test_a_corner_is_two_streets_and_a_drive_counts(sherwood: Layer) -> None:
    corner = sherwood.definitions["corner_lot"]
    assert corner.test == "intersecting_frontages"
    assert corner.alleys_count is False
    assert corner.drives_count is True


def test_no_map_code_is_sent_to_the_county(sherwood: Layer) -> None:
    for code, ruling in sherwood.zone_rulings.items():
        assert ruling.outcome == "unencodable", code
        assert ruling.of is None, code
    assert "16.04.040" in sherwood.zone_rulings["Unannex"].note
    assert "overlay district" in sherwood.zone_rulings["Old Town"].note


def test_nothing_in_the_draft_is_verified(sherwood: Layer) -> None:
    for zone, held in sherwood.zones.items():
        for field, value in held.values.items():
            assert value.status is not Status.verified, (zone, field)
            for variant in value.variants:
                assert variant.status is not Status.verified, (zone, field)
    for field, value in sherwood.defaults.items():
        assert value.status is not Status.verified, field
