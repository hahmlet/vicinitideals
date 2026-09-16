"""The cul-de-sac, measured, and the two rows it switches.

Happy Valley asks a lot "fronting on cul-de-sac" 35 ft of street where it
asks "all other lots" 50, and Wilsonville lets PDR-3, PDR-4 and RN fall to
24 "when the lot fronts a cul-de-sac". Every one of those rows was refused
in a comment beside the interior number, for one stated reason: nothing
measured the fact. quadfit's s4 measures it since 2026-09-15 -- the front
chords on one circle of a turnaround's radius, turning toward the street,
with a street ending inside the circle -- and :mod:`flats.geom.culdesac`
reads that column into the registry's ``fronts_cul_de_sac``.

Tualatin's relief is on a different line. Tables 40.220 and 41.220 say of
the quadplex row's 50 ft of lot WIDTH -- measured at the centre of the lot,
TDC 31.060 -- "May be reduced to 30 feet if on a cul-de-sac." Held since
the evening of 2026-09-15 on ``min_lot_width_ft``, because a width is not a
frontage and the field has to say which line the number is about.

What these tests hold to: the fact is registered as a measured site fact
that is assumed False where unmeasured; the bridge answers False on
anything but a plain True; every corpus variant it switches is LOWER than
the base it replaces (the fact can only loosen, so the unmeasured default
is the tight side); it switches street frontage and lot width and nothing
else; and where the townhome row also stands on the field the two are
spelled out together so a townhome pod on a bulb does not tie.
"""

from __future__ import annotations

import pandas as pd
import pytest
import yaml

from flats.designs.model import Design
from flats.encode.load import load_trusted
from flats.geom.culdesac import (
    CUL_DE_SAC_FACTS,
    cul_de_sac_facts_from_quadfit,
    observed_cul_de_sac,
)
from flats.rules.conditions import CONDITIONS, ENTAILS
from flats.rules.resolver import RuleSet
from flats.score.configure import configure
from flats.score.screen import LotFacts

pytestmark = pytest.mark.unit

POD = """
version: 1
label: Four-plex pod
typology: townhome_rear_court
footprint: {width_ft: 56, depth_ft: 36}
units: 4
stories: 2
height_ft: 26
parking: {stalls_per_unit: 1.5, config: rear_court}
delivery: {method: modular, crane_required: true, crane_reach_ft: 60}
"""


def pod() -> Design:
    return Design(**{**yaml.safe_load(POD), "id": "pod"})


#: Every zone whose corpus entry states the cul-de-sac FRONTAGE row, with the number.
HELD = {
    "or/clackamas/happy-valley": {
        "R40": 70, "R20": 50, "R15": 50, "R10": 35, "R8.5": 35, "R7": 35, "R5": 35,
    },
    "or/clackamas/wilsonville": {"PDR3": 24, "PDR4": 24, "RN": 24},
}

#: ... and every zone whose entry states the cul-de-sac WIDTH row: Tualatin's
#: two, the same sentence in Table 40.220 (RL) and Table 41.220 (RML).
HELD_WIDTH = {"or/clackamas/tualatin": {"RL": 30, "RML": 30}}

#: The field each layer's relief is written on. A frontage is the street
#: edge; a width is across the middle of the lot; the fact switches both,
#: and which line a number is about is the field it is filed under.
FIELD_OF = {
    "or/clackamas/happy-valley": "min_frontage_ft",
    "or/clackamas/wilsonville": "min_frontage_ft",
    "or/clackamas/tualatin": "min_lot_width_ft",
}

#: ... and the one that takes it by reference: Happy Valley R20CC is `like: R20`.
BY_REFERENCE = {("or/clackamas/happy-valley", "R20CC"): ("R20", 50)}

#: Where the rows are printed: Happy Valley's three tables and Wilsonville's
#: two notes, Tualatin's two tables, then the townhome rows beside them.
CUL_DE_SAC_LINES = ("#L285", "#L475", "#L651", "#L4740", "#L7254", "#L192-L193", "#L503-L504")
TOWNHOME_LINES = ("#L287", "#L477", "#L653", "#L7253", "#L196", "#L497,L500")


# --- the bridge -------------------------------------------------------------


def test_only_a_plain_true_is_a_bulb() -> None:
    assert observed_cul_de_sac(True) == {"fronts_cul_de_sac": True}
    assert observed_cul_de_sac(False) == {"fronts_cul_de_sac": False}
    # a null from a merge, a string, a number: none of them is a measurement
    assert observed_cul_de_sac(None) == {"fronts_cul_de_sac": False}
    assert observed_cul_de_sac("True") == {"fronts_cul_de_sac": False}
    assert observed_cul_de_sac(1) == {"fronts_cul_de_sac": False}


def test_the_bridge_reads_the_flag_off_s4s_parquet(tmp_path) -> None:
    frame = pd.DataFrame({
        "TLID": ["1N1E27AB  100", "1N1E27AB  200", "1N1E27AB  300"],
        "fronts_cul_de_sac": pd.array([True, False, None], dtype="boolean"),
    })
    path = tmp_path / "s4_lots.parquet"
    frame.to_parquet(path)
    got = cul_de_sac_facts_from_quadfit(path)
    assert got["1N1E27AB  100"] == {"fronts_cul_de_sac": True}
    assert got["1N1E27AB  200"] == {"fronts_cul_de_sac": False}
    assert got["1N1E27AB  300"] == {"fronts_cul_de_sac": False}


def test_a_parquet_from_before_the_column_answers_false_everywhere(tmp_path) -> None:
    frame = pd.DataFrame({"TLID": ["1N1E27AB  100"], "edges_json": ["[]"]})
    path = tmp_path / "s4_lots.parquet"
    frame.to_parquet(path)
    assert cul_de_sac_facts_from_quadfit(path) == {"1N1E27AB  100": {"fronts_cul_de_sac": False}}


# --- the registry -----------------------------------------------------------


def test_the_fact_is_registered_as_a_measured_site_fact() -> None:
    for name in CUL_DE_SAC_FACTS:
        defn = CONDITIONS[name]
        assert defn.kind == "site_fact", name
        assert defn.assume is False, name
        assert "quadfit" in defn.evidence, name
    # It stands alone: no parent, no child, nothing entailed either way.
    assert "fronts_cul_de_sac" not in ENTAILS
    assert not any("fronts_cul_de_sac" in parents for parents in ENTAILS.values())


# --- configure --------------------------------------------------------------


def test_configure_holds_the_fact_when_the_bridge_says_so() -> None:
    got = configure(LotFacts(lot_sqft=5000), pod(), observed=observed_cul_de_sac(True))
    assert "fronts_cul_de_sac" in got.conditions
    assert "fronts_cul_de_sac" not in got.assumed
    assert got.leans_on(CUL_DE_SAC_FACTS) == ()


def test_an_unmeasured_lot_is_assumed_off_the_bulb() -> None:
    got = configure(LotFacts(lot_sqft=5000), pod())
    assert "fronts_cul_de_sac" not in got.conditions
    assert "fronts_cul_de_sac" in got.assumed


# --- the corpus -------------------------------------------------------------


@pytest.fixture(scope="module")
def layers():
    return load_trusted(strict=False).layers


def test_every_cul_de_sac_row_in_the_corpus_is_looser_than_the_row_it_replaces(layers) -> None:
    """The direction lock. The fact is assumed False where unmeasured, which
    is only safe if every variant it switches is LOWER than its base: a
    tighter row keyed to it would be skipped on every unmeasured lot, the
    false-GREEN direction. And it switches street frontage in two cities
    and lot width in one, each on the field that names the line, and
    nothing else -- no other field anywhere is written against a bulb."""
    found: dict[str, dict[str, float]] = {}
    for lid, layer in layers.items():
        for zname, zone in layer.zones.items():
            for fname, held in zone.values.items():
                for v in held.variants:
                    if "fronts_cul_de_sac" not in (v.when or ()):
                        continue
                    assert lid in FIELD_OF and fname == FIELD_OF[lid], (lid, zname, fname)
                    assert not v.exempt, (lid, zname)
                    if tuple(v.when) == ("fronts_cul_de_sac",):
                        # the cul-de-sac row's own line, under the interior number
                        assert float(v.value) < float(held.value), (lid, zname, v.value, held.value)
                        assert v.prov.quote.endswith(CUL_DE_SAC_LINES), (lid, zname, v.prov.quote)
                        found.setdefault(lid, {})[zname] = float(v.value)
                    else:
                        # the townhome row spelled out beside it, quoting its own line;
                        # under the base too, or equal to it where the townhome row
                        # itself is not (Tualatin RL prints "None", held as 0)
                        assert set(v.when) == {"fronts_cul_de_sac", "unit_lots"}, (lid, zname)
                        assert float(v.value) <= float(held.value), (lid, zname, v.value, held.value)
                        assert v.prov.quote.endswith(TOWNHOME_LINES), (lid, zname, v.prov.quote)
    assert found == {
        lid: {z: float(n) for z, n in zones.items()}
        for lid, zones in (HELD | HELD_WIDTH).items()
    }


def test_the_measured_fact_reaches_the_row_and_nothing_else_does(layers) -> None:
    rules = RuleSet(layers)
    every = {(lid, z): n for lid, zones in (HELD | HELD_WIDTH).items() for z, n in zones.items()}
    every |= {key: n for key, (_, n) in BY_REFERENCE.items()}
    for (lid, zname), number in every.items():
        field = FIELD_OF[lid]
        on_bulb = rules.resolve(lid, zname, conditions=("fronts_cul_de_sac", "multi_story"))
        got = on_bulb.values[field]
        assert float(got.value) == number, (lid, zname, got.value)
        assert got.when == ("fronts_cul_de_sac",), (lid, zname, got.when)
        assert not got.ambiguous, (lid, zname)
        off = rules.resolve(lid, zname, conditions=("multi_story",)).values[field]
        assert float(off.value) > number, (lid, zname, off.value)
        assert off.when == () and not off.ambiguous, (lid, zname)
        # ... and the other line is untouched: a width relief leaves the
        # frontage alone and a frontage relief leaves the width alone.
        other = "min_lot_width_ft" if field == "min_frontage_ft" else "min_frontage_ft"
        if other in on_bulb.values:
            assert "fronts_cul_de_sac" not in on_bulb.values[other].when, (lid, zname, other)


def test_r20cc_takes_the_row_by_reference(layers) -> None:
    for (lid, zname), (parent, number) in BY_REFERENCE.items():
        zone = layers[lid].zones[zname]
        assert zone.like is not None and zone.like.zone == parent, (lid, zname)
        assert "min_frontage_ft" not in zone.values, (lid, zname)     # nothing local overrides it
        assert HELD[lid][parent] == number


def test_a_townhome_pod_on_a_bulb_does_not_tie(layers) -> None:
    """Happy Valley's tables print a townhome row below both frontage rows,
    and RN's note I gives townhouses 20 ft beside note J's 24. A pod platted
    as townhouses on a bulb lot matches both one-condition variants at equal
    depth, which `under` refuses to pick between; so wherever the field holds
    a `unit_lots` row it also holds the pair spelled out, and the pair says
    what the townhome row says -- a relief cannot tighten it."""
    rules = RuleSet(layers)
    spelled = 0
    for lid, zones in (HELD | HELD_WIDTH).items():
        for zname in zones:
            held = layers[lid].zones[zname].values[FIELD_OF[lid]]
            alone = [v for v in held.variants if tuple(v.when) == ("unit_lots",)]
            if not alone:
                continue
            both = held.under({"fronts_cul_de_sac", "unit_lots", "multi_story"})
            assert not both.ambiguous, (lid, zname, both.ambiguous)
            assert set(both.when) == {"fronts_cul_de_sac", "unit_lots"}, (lid, zname)
            assert float(both.value) == float(alone[0].value), (lid, zname)
            if lid in HELD:
                assert float(both.value) == 20.0, (lid, zname)      # every frontage townhome row
            spelled += 1
    # Happy Valley's seven and Wilsonville RN on the frontage; Tualatin's two
    # on the width (RL's townhouse row is "None", RML's is 14).
    assert spelled == 7 + 1 + 2
    # ... and the zone that adopts R-20 by reference does not tie either
    for (lid, zname) in BY_REFERENCE:
        got = rules.resolve(
            lid, zname, conditions=("fronts_cul_de_sac", "unit_lots", "multi_story")
        ).values["min_frontage_ft"]
        assert not got.ambiguous and float(got.value) == 20.0, (lid, zname)
