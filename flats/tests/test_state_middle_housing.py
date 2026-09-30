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
    ("or/multnomah/portland", "RF"),
    (MULT, "RF"),
    (MULT, "LR5"),
    (MULT, "LR10"),
    ("or/clackamas/happy-valley", "FU10"),
}

#: Ruled out: a future-urbanization holding zone on county land
#: (ORS 197A.015(12)(e)), rural zoning that is not urban (12)(b), a hazard
#: district adopted under Goal 7 (OAR 660-046-0010(3)(c)), a pre-2021 master
#: plan (0205(2)(b)(B)), an agricultural holding zone (197A.420(1)(j)(D)).
REFUSED = {
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


def test_portland_rf_carries_the_house_minimum_the_state_path_needs(layers) -> None:
    # OAR 660-046-0220(2)(a)(B): a quadplex's minimum lot is capped at the
    # detached house's, which Table 110-3 sends to Table 610-2 -- 52,000 in
    # RF. Without it the opened zone could only ever screen as unencoded.
    from flats.rules.resolver import RuleSet

    got = RuleSet(layers).resolve("or/multnomah/portland", "RF")
    assert got.missing_required == ()
    assert got.get("min_lot_sqft") == 52000
    text = ProvenanceStore().quote(got.values["min_lot_sqft"].prov.quote)
    assert "52,000" in text
