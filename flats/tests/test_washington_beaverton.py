"""Beaverton: the readings a reviewer would stop on.

The Beaverton Development Code classifies 28 zoning districts in 10.25 and
prints a use table for each family of them in Chapter 20 (and Chapter 70 for
downtown). Twenty-two admit a triplex or quadplex; six refuse. The draft is
pinned here where it reads against the grain of a quick look, so a later edit
has to argue with it.

- **The two Washington Square districts refuse, although a row says P.**
  Table 20.20.20.A prints N for Triplex and Quadplex in OI-WS and C-WS and
  P2 / P3 for Multi-Dwelling, and Chapter 90 makes attached units a
  multi-dwelling. Note 2 admits only units above a non-residential use; note
  3 only a mixed-use development that is majority commercial at the ground.
  The pod is neither, and the definition itself excludes a number of units a
  zone prohibits.
- **NS admits the pod, but no NS lot can come back GREEN.** Note 1 lets only
  half of any NS district's contiguous area be developed residentially: a
  share of the whole district, which depends on the neighbours. The footnote
  ruling holds it `unmeasured` on `site_specific_limitation`, so the verdict
  is capped.
- **"WAcnty" is the county's zoning, kept after annexation (BDC 10.40.1),**
  and screens as a pocket of the unincorporated layer read off the county's
  own map. "ROW" is street, not a district.
- **UPAA §V.D is recorded, not held.** The city "may, at its discretion"
  keep the county's setbacks, lot sizes, coverage and heights on a partly
  built development annexed after county approval. The first draft carried
  it as a qualifier on every standard it names, which kept every Beaverton
  lot off GREEN. Steph ruled 2026-09-29 that the Beaverton code governs a
  new project, so the qualifier is gone and the clause is a known unknown in
  the layer comment.
- **The quadplex parking maximum is N/A in the four middle-housing zones,**
  and 1.8 a unit everywhere else, the lowest figure of the "Other Zone" row.
- **RMB and RMC carry the 20.30 height plane** as a step-back on the rear
  setback (and RMC's front): 25 feet at the setback line, rising 1:1.
- **Downtown's side and rear setbacks hold the neighbour row, not the
  interior 0.** RC-BC, RC-OT and RC-MU owe them beside "property zoned
  residential and/or Downtown Transition (DT)". An RC-DT neighbour is not
  a residential zone, so a strict figure behind `abuts_residential_zone`
  would hand a lot beside RC-DT the 0. The 0 is the variant, behind
  `abuts_nonresidential_zone`.
"""

from __future__ import annotations

import pytest

from flats.provenance.store import ProvenanceStore
from flats.rules.caps import caps_for
from flats.rules.loader import load_rules
from flats.rules.model import POCKET_ZONE_FROM_MAP, Layer, Status

pytestmark = pytest.mark.unit

BEAVERTON = "or/washington/beaverton"
UNINCORPORATED = "or/washington/_unincorporated"

#: Triplex and Quadplex P (or P with a note) in the zone's own use table.
ONE_LOT = (
    "MR", "RMA", "RMB", "RMC",
    "CM-RM", "CM-MR", "CM-HDR", "CM-CS",
    "NS", "CS", "CC", "GC",
    "RC-E", "TC-MU", "TC-HDR", "SC-MU", "SC-HDR", "SC-S",
    "RC-BC", "RC-OT", "RC-MU", "RC-DT",
)
#: Table 20.20.20.A row 1.C prints N; row 1.F prints P with a note.
WASHINGTON_SQUARE = ("OI-WS", "C-WS")
#: No dwelling use in the table at all (20.15), or N in row 1.C (SC-E).
REFUSED = ("OI", "OI-NC", "IND", "SC-E") + WASHINGTON_SQUARE
#: What UPAA §V.D names -- "setbacks, lot sizes, lot coverage and heights" --
#: as this layer holds it. Beaverton prints no lot coverage standard.
UPAA_FIELDS = (
    "max_height_ft",
    "min_lot_sqft",
    "setback_front_ft",
    "setback_rear_ft",
    "setback_side_ft",
)
#: Table 60.30.10.5.A row 2: "Triplex or Quadplex in RMA, RMB, RMC, or CM-RM
#: Zone (per unit)", N/A in both parking zones.
NO_PARKING_MAXIMUM = ("RMA", "RMB", "RMC", "CM-RM")


@pytest.fixture(scope="module")
def beaverton() -> Layer:
    return load_rules()[BEAVERTON]


def _use(layer: Layer, zone: str):
    return layer.zones[zone].values["quadplex_allowed"]


def _text(quote: str) -> str:
    return " ".join(ProvenanceStore().quote(quote).split())


def test_every_district_the_code_classifies_is_encoded(beaverton: Layer) -> None:
    """10.25 lists 28 districts, SC-E as "SC-E1 & 3"; the map prints SC-E."""
    assert len(beaverton.zones) == 28
    assert set(beaverton.zones) == set(ONE_LOT) | set(REFUSED)
    # The layer is chosen by JURIS_CITY, and BEAVERTON is the county's spelling.
    assert list(beaverton.ingest["juris_city_codes"]) == ["BEAVERTON"]


def test_the_pod_goes_on_one_lot_in_twenty_two_zones(beaverton: Layer) -> None:
    admitted = {z for z in beaverton.zones if _use(beaverton, z).value is True}
    assert admitted == set(ONE_LOT)
    for zone in ONE_LOT:
        assert _use(beaverton, zone).variants == (), zone


@pytest.mark.parametrize(
    ("zone", "words"),
    [
        ("OI-WS", "second story and above"),
        ("C-WS", "in conjunction with mixed-use developments"),
    ],
)
def test_washington_square_refuses_though_multi_dwelling_says_p(
    beaverton: Layer, zone: str, words: str
) -> None:
    use = _use(beaverton, zone)
    assert use.value is False
    assert use.variants == ()
    text = _text(use.prov.quote)
    # The quote carries both rows and the note, so the refusal can be read
    # against the permission a reviewer would otherwise find on their own.
    assert "Triplex and Quadplex" in text
    assert "Multi-Dwelling" in text
    assert words in text


def test_refusals_carry_the_use_row_and_nothing_else(beaverton: Layer) -> None:
    for zone in REFUSED:
        held = beaverton.zones[zone]
        assert set(held.values) == {"quadplex_allowed"}, zone
        use = held.values["quadplex_allowed"]
        assert use.value is False, zone
        assert use.variants == (), zone


def test_ns_admits_the_pod_and_its_district_share_caps_the_verdict(
    beaverton: Layer,
) -> None:
    use = _use(beaverton, "NS")
    assert use.value is True
    assert "Only 50% of the contiguous area" in _text(use.prov.quote)
    assert caps_for(BEAVERTON, "NS").get("quadplex_allowed") == (
        "site_specific_limitation",
    )


def test_annexed_county_land_screens_under_the_county_layer(
    beaverton: Layer,
) -> None:
    rulings = beaverton.zone_rulings
    assert set(rulings) == {"WAcnty", "ROW"}

    assert rulings["WAcnty"].outcome == "pocket"
    assert rulings["WAcnty"].of == UNINCORPORATED
    assert rulings["WAcnty"].zone == POCKET_ZONE_FROM_MAP
    assert UNINCORPORATED in load_rules()
    assert "10.40.1" in rulings["WAcnty"].note

    assert rulings["ROW"].outcome == "unencodable"


def test_the_upaa_annexation_condition_is_recorded_not_held(
    beaverton: Layer,
) -> None:
    # Steph 2026-09-29: "We don't care what developments the county approved
    # before because we're doing a new one." No standard the clause names is
    # qualified by it, so a Beaverton lot can come back GREEN.
    for zone in ONE_LOT:
        for field in UPAA_FIELDS:
            value = beaverton.zones[zone].values.get(field)
            if value is None:
                continue
            assert "upaa" not in (value.qualified_quote or ""), (zone, field)
    # The clause stays in the store and in the layer comment as a known
    # unknown: its own words say "any new construction taking place after
    # annexation".
    assert "continue to apply the COUNTY's development standards" in _text(
        "or/washington/beaverton/wc.beaverton-upaa.txt#L282-L287"
    )
    # No lot coverage field to qualify: the code prints none.
    for zone in ONE_LOT:
        held = beaverton.zones[zone].values
        assert not {"max_coverage_pct", "coverage_curve"} & set(held), zone


def test_the_quadplex_parking_maximum(beaverton: Layer) -> None:
    default = beaverton.defaults["parking_max_per_unit"]
    assert default.value == 1.8
    assert "Other Zone" in _text(default.prov.quote)
    for zone in NO_PARKING_MAXIMUM:
        held = beaverton.zones[zone].values["parking_max_per_unit"]
        assert held.exempt is True, zone
        assert "Triplex or Quadplex in RMA, RMB, RMC, or CM-RM Zone" in _text(
            held.prov.quote
        ), zone
    # MR is an "Other Zone" and takes the default.
    assert "parking_max_per_unit" not in beaverton.zones["MR"].values


@pytest.mark.parametrize(
    ("zone", "fields"),
    [
        ("RMB", {"setback_rear_ft"}),
        ("RMC", {"setback_front_ft", "setback_rear_ft"}),
    ],
)
def test_rmb_and_rmc_carry_the_height_plane(
    beaverton: Layer, zone: str, fields: set[str]
) -> None:
    held = beaverton.zones[zone].values
    stepped = {f for f, v in held.items() if v.step_back_at_ft is not None}
    assert stepped == fields
    for field in fields:
        assert held[field].step_back_at_ft == 25
        assert held[field].step_back_rise == 1
        assert "20.30" in held[field].step_back_cite
    assert held["max_height_ft"].value == 35


@pytest.mark.parametrize(
    ("zone", "side", "rear"),
    [("RC-BC", 10, 20), ("RC-OT", 10, 10), ("RC-MU", 10, 20)],
)
def test_downtown_holds_the_setback_owed_beside_rc_dt(
    beaverton: Layer, zone: str, side: int, rear: int
) -> None:
    held = beaverton.zones[zone].values
    for field, figure in (("setback_side_ft", side), ("setback_rear_ft", rear)):
        value = held[field]
        assert value.value == figure, (zone, field)
        assert "Downtown Transition (DT)" in _text(value.prov.quote), (zone, field)
        assert [(v.value, v.when) for v in value.variants] == [
            (0, ("abuts_nonresidential_zone",))
        ], (zone, field)
        assert "Interior side or rear setback" in _text(value.variants[0].prov.quote)
    # RC-DT's own row names only "property zoned Residential", so there the
    # strict figure is the one behind the condition.
    rc_dt = beaverton.zones["RC-DT"].values["setback_rear_ft"]
    assert rc_dt.value == 0
    assert [v.when for v in rc_dt.variants] == [("abuts_residential_zone",)]


def test_nothing_in_the_draft_is_verified(beaverton: Layer) -> None:
    for zone, held in beaverton.zones.items():
        for field, value in held.values.items():
            assert value.status is not Status.verified, (zone, field)
            for variant in value.variants:
                assert variant.status is not Status.verified, (zone, field)
    for field, value in beaverton.defaults.items():
        assert value.status is not Status.verified, field
