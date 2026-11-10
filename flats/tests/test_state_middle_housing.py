"""The state's middle housing law over zones whose codes still refuse the pod.

ORS 197A.420(2), as HB 2138 (2025) words it, has every county, every city of
25,000 or more and every city over 1,000 inside Metro allow all middle housing
types "on each lot or parcel zoned for residential use". Fourteen residential
zones in Multnomah and Clackamas allow a detached house and refuse a quadplex;
each was read against the law's exceptions (Steph 2026-09-30, FOLLOWUPS 21(b))
and the state path is offered only where none applies -- as relief, never as a
permit, so it can move a lot off RED but never to GREEN.
"""

from __future__ import annotations

import pytest

from flats.provenance.store import ProvenanceStore
from flats.rules.conditions import CONDITIONS, Tier
from flats.rules.loader import load_rules

MULT = "or/multnomah/_unincorporated"
CLACK = "or/clackamas/_unincorporated"

#: Offered: no exception reaches the whole zone.
OPENED = {
    (MULT, "LR5"),
    (MULT, "LR10"),
    ("or/clackamas/happy-valley", "FU10"),
}

#: Ruled out: a future-urbanization holding zone on county land
#: (ORS 197A.015(12)(e)), rural zoning that is not urban (12)(b), a hazard
#: district adopted under Goal 7 (OAR 660-046-0010(3)(c)), a pre-2021 master
#: plan (0205(2)(b)(B)), an agricultural holding zone (197A.420(1)(j)(D)),
#: and Portland's RF in the city and its pockets -- farm land outside the
#: statute (Steph 2026-11-09, rulings.yaml 2026-11-09-rf-is-farm-land).
REFUSED = {
    ("or/multnomah/portland", "RF"),
    (MULT, "RF"),
    (MULT, "UF20"),
    (CLACK, "FU10"),
    (CLACK, "RRFF5"),
    (CLACK, "RA1"),
    (CLACK, "RA2"),
    ("or/multnomah/gresham", "LDR/GB"),
    ("or/clackamas/wilsonville", "RN"),
    ("or/clackamas/wilsonville", "FDAHR"),
}


@pytest.fixture(scope="module")
def layers():
    return load_rules()


def _state_variants(layers, layer: str, zone: str):
    held = layers[layer].zones[zone].values["quadplex_allowed"]
    return [v for v in held.variants if "state_middle_housing" in v.when]


def test_the_state_path_is_relief_and_never_a_permit() -> None:
    held = CONDITIONS["state_middle_housing"]
    assert held.kind == "relief"
    assert held.tier is Tier.discretionary


@pytest.mark.parametrize("layer,zone", sorted(OPENED))
def test_a_zone_no_exception_reaches_is_offered_the_state_path(layers, layer, zone) -> None:
    held = layers[layer].zones[zone].values["quadplex_allowed"]
    assert held.value is False  # the local code still says no
    [variant] = _state_variants(layers, layer, zone)
    assert variant.value is True
    text = ProvenanceStore().quote(variant.prov.quote)
    assert "on each lot or parcel zoned for residential use" in text
    assert "Allows the development of a detached single-unit dwelling" in text


@pytest.mark.parametrize("layer", sorted({layer for layer, _ in OPENED}))
def test_county_land_must_also_be_urban_unincorporated(layers, layer) -> None:
    for held_layer, zone in OPENED:
        if held_layer != layer:
            continue
        [variant] = _state_variants(layers, layer, zone)
        county = layer.endswith("/_unincorporated")
        assert ("in_sewer_district" in variant.when) is county, zone
        if county:
            text = ProvenanceStore().quote(variant.prov.quote)
            assert "maintains the land" in text  # ORS 197A.015(12)(e)


@pytest.mark.parametrize("layer,zone", sorted(REFUSED))
def test_a_zone_an_exception_reaches_stays_closed(layers, layer, zone) -> None:
    assert _state_variants(layers, layer, zone) == []


#: The plain-words reason the ruling asks the lot page to show.
FARM_LAND = "the city treats RF as farm land, outside the state law"


@pytest.mark.parametrize("layer", ["or/multnomah/portland", MULT])
def test_rf_is_farm_land_and_says_so(layers, layer) -> None:
    # Steph 2026-11-09 (FOLLOWUPS 173): RF is farm land outside ORS 197A.420
    # / HB 2138, in the city and in the Portland-administered pockets. The
    # local No stands with no relief, the cite says why in plain words, and
    # the `via` is the city's own ordinance saying RF is not subject to it.
    from flats.rules.resolver import RuleSet

    held = layers[layer].zones["RF"].values["quadplex_allowed"]
    assert held.value is False
    assert held.variants == ()
    assert FARM_LAND in held.prov.cite
    store = ProvenanceStore()
    table = " ".join(store.quote(held.prov.quote).split())
    assert "Fourplex" in table
    why = " ".join(store.quote(held.prov.via).split())
    assert "generally an agricultural zone and not subject to ORS197A.420" in why
    assert "not subject to ORS 197A.420 or HB 2138" in why
    assert "not subject to HB 2138" in why

    got = RuleSet(layers).resolve(layer, "RF").values["quadplex_allowed"]
    assert got.value is False
    assert got.relief == ()


def test_the_ordinance_is_stored_as_adopted_with_its_pages() -> None:
    # Ordinance 192241, As Adopted, October 21, 2026, effective 2027-01-01:
    # the three RF passages sit on printed pages 12, 30 and 58.
    from flats.provenance.pages import read

    doc = "or/multnomah/portland/amended/ord192241.txt"
    store = ProvenanceStore()
    head = " ".join(" ".join(store.load(doc).text.splitlines()[:40]).split())
    assert "As Adopted" in head and "October 21, 2026" in head
    assert "Effective January 1, 2027" in head
    book = read(store, doc)
    assert book is not None
    for line, page in ((318, "12"), (940, "30"), (1835, "58")):
        assert book.at(line).label == page
