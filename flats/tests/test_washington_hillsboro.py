"""Hillsboro: the readings a reviewer would stop on.

The Community Development Code (Municipal Code Title 12) prints a Housing
Types Permitted table in every zone, and a Quadplex row in each. Twenty-two
zones say P or L on one lot, and twenty-one admit the pod; four more say it
only on some of their land; the commercial, industrial and institutional
zones say N. The draft is pinned
here where it reads against the grain of a quick look, so a later edit has to
argue with it.

- **MU-C and the arterials.** 12.24.250 G wants 60 percent of the ground
  floor facing an arterial or collector in non-residential use, which a
  four-unit residential building is not. The base value refuses and the
  one variant admits behind `local_street`.
- **UC-AC, UC-NC and UC-OR and the Retail Focus Frontage Area.** Each zone's
  Quadplex row carries "Not permitted within the Retail Focus Frontage Area
  shown on Figure 12.64.640-A". The figure is a drawing nobody reads, so the
  base refuses and the variant admits behind `inside_mapped_use_area`, the
  mapped area being the land OUTSIDE the retail frontage.
- **SCR-OTC and MU-VTC flag lots.** Table 12.21.750-1 says "flag lots not
  permitted" and the South Hillsboro Plan District says "flag lots are
  prohibited within" MU-VTC (12.65.540). Both are read as reaching a flag
  lot that already exists: the two zones where a flag lot refuses the pod
  rather than widening its frontage.
- **SCC-DT refuses the pod although its row says P.** 12.50.350 D.1:
  "Parking for free-standing residential structures in the SCC-DT zone shall
  be incorporated within the structure". The pod parks in an open court.
- **Two and a half stories is 25 feet** (Steph 2026-09-29). 12.50.140 B.6
  says a residential story is "not more than 10 feet", so the residential
  tables' "2 1/2 stories or 35 feet, whichever is less" is 25, and SCR-OTC's
  "2 stories or 35 feet" is 20. Held through the `stories` form, which
  cites the table for the count and B.6 for the feet.
- **The refusals** carry the use row and nothing else, like the county's.
- **Four map codes are ruled, not encoded.** ANX, the city's label for land
  annexed and not yet zoned, is unencodable until the question of which code
  governs it is answered; CO ("County") is a pocket of the county layer read
  off the county's map; SID I-P and SC-BP are the map's spellings of I-P and
  SCBP.

One smaller fact rides along: Hillsboro sets no parking minimum at all (12.50.310
A.2), and the default says so with a zero the readiness check can read.
"""

from __future__ import annotations

import pytest

from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import POCKET_ZONE_FROM_MAP, Layer, Status

pytestmark = pytest.mark.unit

HILLSBORO = "or/washington/hillsboro"
UNINCORPORATED = "or/washington/_unincorporated"

#: Quadplex P or L on one lot, no condition.
ONE_LOT = (
    "R-10", "R-8.5", "R-7", "R-6", "R-4.5",
    "SCR-LD", "SCR-OTC", "SCR-DNC",
    "MR-1", "MR-2", "MR-3", "SCR-MD", "SCR-HD",
    "SCC-SC", "SCC-MM",
    "MU-N", "MU-VTC", "SCR-V",
    "UC-RM", "UC-MU", "UC-RP",
)
#: Quadplex P in the use table, refused by where the pod parks (12.50.350 D.1).
PARKED_INSIDE = ("SCC-DT",)
#: Height in stories at ten feet a story (12.50.140 B.6): zone -> stories.
IN_STORIES = {
    "R-10": 2.5, "R-8.5": 2.5, "R-7": 2.5, "R-6": 2.5, "R-4.5": 2.5,
    "SCR-LD": 2.5, "SCR-DNC": 2.5, "MR-1": 2.5, "SCR-OTC": 2,
}
#: One-lot zones whose only variant refuses a flag lot.
FLAG_LOT_REFUSED = ("SCR-OTC", "MU-VTC")
#: The Retail Focus Frontage Area refusal (Figure 12.64.640-A).
RETAIL_FRONTAGE = ("UC-AC", "UC-NC", "UC-OR")
#: Quadplex N in the zone's own Housing Types table.
REFUSED = (
    "C-N", "C-G",
    "I-G", "I-P", "I-S", "SCBP", "SCI", "SSID", "ESID", "HSID",
    "SCFI",
)


@pytest.fixture(scope="module")
def hillsboro() -> Layer:
    return load_rules()[HILLSBORO]


def _use(layer: Layer, zone: str):
    return layer.zones[zone].values["quadplex_allowed"]


def test_every_zone_the_code_lists_is_encoded(hillsboro: Layer) -> None:
    assert len(hillsboro.zones) == 37
    assert set(hillsboro.zones) == set(ONE_LOT) | set(PARKED_INSIDE) | {"MU-C"} | set(RETAIL_FRONTAGE) | set(REFUSED)
    # The layer is chosen by JURIS_CITY, and HILLSBORO is the county's spelling.
    assert list(hillsboro.ingest["juris_city_codes"]) == ["HILLSBORO"]


def test_the_pod_goes_on_one_lot_in_twenty_one_zones(hillsboro: Layer) -> None:
    admitted = {z for z in hillsboro.zones if _use(hillsboro, z).value is True}
    assert admitted == set(ONE_LOT)
    assert len(ONE_LOT) == 21
    for zone in ONE_LOT:
        if zone in FLAG_LOT_REFUSED:
            continue
        assert _use(hillsboro, zone).variants == (), zone


def test_mu_c_admits_the_pod_only_off_an_arterial(hillsboro: Layer) -> None:
    use = _use(hillsboro, "MU-C")
    assert use.value is False
    assert [(v.value, v.when) for v in use.variants] == [(True, ("local_street",))]


def test_the_retail_frontage_zones_admit_only_outside_it(hillsboro: Layer) -> None:
    store = ProvenanceStore()
    for zone in RETAIL_FRONTAGE:
        use = _use(hillsboro, zone)
        assert use.value is False, zone
        assert [(v.value, v.when) for v in use.variants] == [
            (True, ("inside_mapped_use_area",))
        ], zone
        text = " ".join(store.quote(use.prov.quote).split())
        assert "Retail Focus Frontage" in text, zone


@pytest.mark.parametrize(
    ("zone", "words"),
    [
        ("SCR-OTC", "flag lots not permitted"),
        ("MU-VTC", "flag lots are prohibited within the Mixed-Use"),
    ],
)
def test_two_zones_refuse_a_flag_lot(hillsboro: Layer, zone: str, words: str) -> None:
    assert set(FLAG_LOT_REFUSED) == {"SCR-OTC", "MU-VTC"}
    use = _use(hillsboro, zone)
    assert use.value is True
    assert [(v.value, v.when) for v in use.variants] == [(False, ("flag_lot",))]
    text = " ".join(ProvenanceStore().quote(use.variants[0].prov.quote).split())
    assert words in text


def test_refusals_carry_the_use_row_and_nothing_else(hillsboro: Layer) -> None:
    store = ProvenanceStore()
    for zone in REFUSED:
        held = hillsboro.zones[zone]
        assert set(held.values) == {"quadplex_allowed"}, zone
        use = held.values["quadplex_allowed"]
        assert use.value is False, zone
        assert use.variants == (), zone
        text = store.quote(use.prov.quote)
        assert "Quadplex N" in text, zone
        assert f"Housing Types Permitted in the {zone} Zone" in text, zone


def test_the_map_codes_that_are_not_zones_are_ruled(hillsboro: Layer) -> None:
    rulings = hillsboro.zone_rulings
    assert set(rulings) == {"ANX", "CO", "SID I-P", "SC-BP"}

    assert rulings["ANX"].outcome == "unencodable"
    assert "ORS 215.130" in rulings["ANX"].note

    assert rulings["CO"].outcome == "pocket"
    assert rulings["CO"].of == UNINCORPORATED
    assert rulings["CO"].zone == POCKET_ZONE_FROM_MAP
    assert UNINCORPORATED in load_rules()

    assert (rulings["SID I-P"].outcome, rulings["SID I-P"].of) == ("alias", "I-P")
    assert (rulings["SC-BP"].outcome, rulings["SC-BP"].of) == ("alias", "SCBP")
    for code in ("SID I-P", "SC-BP"):
        assert rulings[code].of in hillsboro.zones, code


def test_hillsboro_sets_no_parking_minimum(hillsboro: Layer) -> None:
    parking = hillsboro.defaults["parking_min_per_unit"]
    assert parking.value == 0
    text = " ".join(ProvenanceStore().quote(parking.prov.quote).split())
    assert "does not have standards which require" in text


def test_nothing_in_the_draft_is_verified(hillsboro: Layer) -> None:
    for zone, held in hillsboro.zones.items():
        for field, value in held.values.items():
            assert value.status is not Status.verified, (zone, field)
            for variant in value.variants:
                assert variant.status is not Status.verified, (zone, field)


def test_scc_dt_refuses_a_building_that_parks_outside_itself(hillsboro: Layer) -> None:
    use = _use(hillsboro, "SCC-DT")
    assert use.value is False
    assert use.variants == ()
    text = " ".join(ProvenanceStore().quote(use.prov.quote).split())
    assert "shall be incorporated within the structure" in text


@pytest.mark.parametrize(("zone", "stories"), sorted(IN_STORIES.items()))
def test_two_and_a_half_stories_is_twenty_five_feet(
    hillsboro: Layer, zone: str, stories: float
) -> None:
    height = hillsboro.zones[zone].values["max_height_ft"]
    assert height.stories == stories
    assert height.story_ft == 10
    assert height.value == stories * 10
    store = ProvenanceStore()
    assert "not more than 10 feet" in " ".join(store.quote(height.story_ft_quote).split())
    assert "stories" in store.quote(height.prov.quote)


def test_the_commercial_half_story_keeps_its_feet(hillsboro: Layer) -> None:
    # B.6 names the single-dwelling and multi-dwelling zones; the commercial
    # "35 feet or 2½ stories" row is not one of them.
    for zone, zone_rules in hillsboro.zones.items():
        height = zone_rules.values.get("max_height_ft")
        if height is not None and height.stories is not None:
            assert zone in IN_STORIES, zone
