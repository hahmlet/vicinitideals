"""Portland's Constrained Sites overlay over the fourplex allowance.

PCC 33.418.030 lays the "z" over R20 through R2.5 lots any part of which
touches an environmental zone, the flood hazard area, the floodway, a mapped
landslide hazard, the wildfire maps, an industrial sanctuary or the airport
noise contour; 33.418.040.B then switches off 33.110.265.E, "which allows
triplexes and fourplexes in the R20 through R2.5 zones". The state's middle
housing law keeps that: ORS 197A.420(5)(b) lets a city regulate middle housing
"to comply with protective measures adopted pursuant to statewide land use
planning goals" -- the purpose 33.418.010 gives. FLATS read none of it until
2026-10-04 (FOLLOWUPS 42(a)): 7,324 lots GREEN as if signed carried a "z".

The attached house survives the overlay, so four units on four lots after a
land division is a way round. Steph 2026-10-04: red, way in noted -- the path
rides on the bind and is never taken.
"""

from __future__ import annotations

import pytest

from flats.ingest.quadfit import Z_ANSWERS, observed_facts
from flats.provenance.store import ProvenanceStore
from flats.rules.conditions import CONDITIONS, Tier
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.tests.test_quadfit_bridge import row

PDX = "or/multnomah/portland"
MULT = "or/multnomah/_unincorporated"
FACT = "constrained_sites_overlay"
SPLIT = "attached_house_division"

#: 33.418.030: the overlay is applied to these zones and no others. The
#: county's Portland-administered pockets carry the same zones off the same
#: map, minus R2.5, which no pocket is zoned.
OVERLAID = [(PDX, z) for z in ("R20", "R10", "R7", "R5", "R2.5")] + [
    (MULT, z) for z in ("R20", "R10", "R7", "R5")
]


@pytest.fixture(scope="module")
def layers():
    return load_rules()


@pytest.fixture(scope="module")
def rules(layers):
    return RuleSet(layers)


def test_the_overlay_is_a_measured_site_fact_never_assumed() -> None:
    held = CONDITIONS[FACT]
    assert held.kind == "site_fact"
    assert held.assume is None


@pytest.mark.parametrize("layer,zone", OVERLAID)
def test_the_z_takes_the_fourplex_away(rules, layer, zone) -> None:
    assert rules.resolve(layer, zone).get("quadplex_allowed") is True
    assert rules.resolve(layer, zone, conditions=[FACT]).get("quadplex_allowed") is False


@pytest.mark.parametrize("layer,zone", OVERLAID)
def test_the_state_path_does_not_bring_it_back(rules, layer, zone) -> None:
    got = rules.resolve(layer, zone, conditions=[FACT, "state_middle_housing"])
    assert got.get("quadplex_allowed") is False


@pytest.mark.parametrize("layer,zone", OVERLAID)
def test_the_variant_quotes_the_sentence_it_rests_on(layers, layer, zone) -> None:
    held = layers[layer].zones[zone].values["quadplex_allowed"]
    [variant] = [v for v in held.variants if v.when == (FACT,)]
    text = ProvenanceStore().quote(variant.prov.quote)
    assert "applied to lots in the R20, R10, R7, R5 and R2.5 zones" in text
    assert "33.110.265.E which allows triplexes and fourplexes" in text


def test_the_way_round_is_relief_and_never_a_permit() -> None:
    held = CONDITIONS[SPLIT]
    assert held.kind == "relief"
    assert held.tier is Tier.discretionary


@pytest.mark.parametrize("layer,zone", OVERLAID)
def test_the_lot_split_is_the_only_path_the_bind_carries(rules, layer, zone) -> None:
    got = rules.resolve(layer, zone, conditions=[FACT]).values["quadplex_allowed"]
    assert got.value is False
    assert [(set(when), value) for when, value, _ in got.relief] == [({FACT, SPLIT}, True)]


@pytest.mark.parametrize("layer,zone", OVERLAID)
def test_the_path_quotes_the_attached_house_row(layers, layer, zone) -> None:
    held = layers[layer].zones[zone].values["quadplex_allowed"]
    [variant] = [v for v in held.variants if SPLIT in v.when]
    assert "Attached house" in ProvenanceStore().quote(variant.prov.quote)


def test_the_path_is_logged_and_the_lot_stays_red(rules) -> None:
    from dataclasses import replace

    from flats.rules.resolver import Verdict
    from flats.score import flags as fp
    from flats.tests.test_screen import DESIGN, LOT, POLICY, fit, screen

    # As if signed, the colour the lot pages show (the bridge's _if_signed).
    held = rules.resolve(PDX, "R5", conditions=[FACT])
    signed = replace(held, verdict=Verdict.trusted, untrusted=())
    got = screen(signed, LOT, DESIGN, fit(), policy=POLICY)
    [use] = [b for b in got.binds if b.check == "use"]
    assert use.relief == SPLIT
    assert use.relief_tier == "discretionary"
    assert fp.colour(got.binds, got.flags) is fp.Colour.red


def test_no_other_zone_turns_on_the_overlay(layers) -> None:
    held = set(OVERLAID)
    stray = [
        (name, zone, field)
        for name, layer in layers.items()
        for zone, z in layer.zones.items()
        for field, value in z.values.items()
        if any(FACT in v.when for v in getattr(value, "variants", ()) or ())
        and ((name, zone) not in held or field != "quadplex_allowed")
    ]
    assert stray == []


def test_the_state_law_keeps_the_city_protective_measures() -> None:
    text = ProvenanceStore().quote("or/hb.2138.2025.txt#L106-L107")
    assert "protective measures" in text


@pytest.mark.parametrize(
    ("juris", "z", "expected"),
    [
        ("portland", True, True),
        ("portland", False, False),
        ("multnomah_unincorporated", True, True),
        ("portland", None, None),
        ("portland", float("nan"), None),
        ("gresham", True, None),
    ],
)
def test_the_bridge_answers_the_z_off_portlands_map(juris, z, expected) -> None:
    got = observed_facts(row(jurisdiction=juris, has_z_overlay=z))
    assert got.get(FACT) is expected


def test_only_portlands_map_answers() -> None:
    assert Z_ANSWERS == {"portland", "multnomah_unincorporated"}
