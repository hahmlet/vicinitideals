"""FOLLOWUPS 105 round 5 (2026-11-10): the chapters fetched on 2026-11-08 with
Steph's OK, read with every reference into and out of them.

* Tigard 18.420 (landscaping and screening). The S-3 row was encoded in round
  3. Its S-4 row (8 ft) reaches the pod in MU-CBD, where 18.650.070.B.3 screens
  parking "When abutting a public right-of-way, pedestrian paths and trails in
  a public easement, or a public park". The street line is already 10 ft; the
  alley and the park lines now carry the 8 ft strip, the park read from ORCA
  through a Tigard ``parks:`` block.
* Canby 16.41.070 (DCO design standards), fetched 2026-11-10 as the next layer
  of 16.41.050 and 16.41.060: measurable design details and commercial-only
  rows. Nothing encoded; a flat roof is allowed.
* Gladstone 17.76 (exceptions): re-read with the references into it. Nothing
  encoded.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flats.encode.load import load_trusted
from flats.ingest.quadfit import observed_facts
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import ORCA_UNIT_TYPES
from flats.rules.resolver import RuleSet
from flats.tests.test_quadfit_bridge import row

pytestmark = pytest.mark.unit

TIGARD = "or/washington/tigard"
CANBY = "or/clackamas/canby"
GLADSTONE = "or/clackamas/gladstone"
FIELD = "parking_lot_line_buffer_ft"
DOCS = Path(__file__).resolve().parents[1] / "provenance" / "docs"


@pytest.fixture(scope="module")
def corpus() -> RuleSet:
    return RuleSet(load_rules(strict=True))


def lines(path: str) -> list[str]:
    return (DOCS / path).read_text(encoding="utf-8").splitlines()


# --- Tigard MU-CBD, the S-4 strip ----------------------------------------------------


@pytest.mark.parametrize(
    "held",
    (("abuts_alley",), ("abuts_park",), ("abuts_alley", "abuts_park")),
)
def test_mu_cbd_keeps_parking_8_ft_off_an_alley_or_a_park(corpus: RuleSet, held: tuple) -> None:
    resolved = corpus.resolve(TIGARD, "MU-CBD", held)
    value = resolved.values[FIELD]
    assert value.value == 8
    assert not value.ambiguous


def test_mu_cbd_owes_no_strip_on_an_ordinary_lot_line(corpus: RuleSet) -> None:
    resolved = corpus.resolve(TIGARD, "MU-CBD", ())
    assert resolved.get(FIELD) is None
    # Both facts move it, so a lot where either is unanswered is not certified.
    assert {"abuts_alley", "abuts_park"} <= resolved.levers


def test_the_street_line_already_holds_the_8_ft(corpus: RuleSet) -> None:
    assert corpus.resolve(TIGARD, "MU-CBD", ()).get("parking_street_setback_ft") >= 8


def test_the_8_is_the_s4_row_and_b3_sends_mu_cbd_parking_there() -> None:
    table = lines(f"{TIGARD}/tdc.18.420.landscaping.txt")
    assert table[255] == "S-4" and table[256] == "8 feet"
    b3 = lines(f"{TIGARD}/18.650/18.650.070.txt")[52]
    assert b3.startswith("When abutting a public right-of-way, pedestrian paths and trails")
    assert "a public park" in b3 and "S-4 standard" in b3


def test_the_variants_quote_the_printed_8_and_carry_b3_as_via(corpus: RuleSet) -> None:
    value = corpus.layers[TIGARD].zones["MU-CBD"].values[FIELD]
    assert value.exempt
    store = ProvenanceStore()
    for variant in value.variants:
        assert variant.value == 8
        assert "8 feet" in store.quote(variant.prov.quote)
        assert "a public park" in store.quote(variant.prov.via)


def test_no_other_tigard_zone_reads_the_park(corpus: RuleSet) -> None:
    for zone in corpus.layers[TIGARD].zones:
        if zone != "MU-CBD":
            assert "abuts_park" not in corpus.resolve(TIGARD, zone, ()).levers, zone


def test_bridgeport_s4_sits_inside_the_20_ft_street_setback(corpus: RuleSet) -> None:
    resolved = corpus.resolve(TIGARD, "MUC", ("tigard_bridgeport_village",))
    assert resolved.get("parking_street_setback_ft") >= 8


# --- Tigard's park -------------------------------------------------------------------


def test_tigards_park_is_land_set_apart_for_the_general_public(corpus: RuleSet) -> None:
    rule = corpus.layers[TIGARD].parks["abuts_park"]
    assert rule.true_for == ("Park",)
    assert set(rule.false_for) == {"Home Owners Association", "School Land"}
    # A cemetery, a golf course, a natural area or a trail parcel may be public
    # parkland or may not: a line across one stays unresolved.
    assert ORCA_UNIT_TYPES - set(rule.true_for) - set(rule.false_for) == {
        "Cemetery",
        "Golf Course",
        "Natural Area",
        "Other",
    }
    text = ProvenanceStore().quote(rule.quote)
    assert "for the general public" in text


@pytest.fixture(scope="module")
def layers():
    return load_trusted(strict=False).rules.layers


def mu_cbd(across: list) -> dict:
    return row(jurisdiction="tigard", zone="MU-CBD", park_across_json=json.dumps(across))


def seen(*kinds: str, none: int = 0) -> dict:
    return {"k": sorted(kinds), "none": none}


def test_the_bridge_reads_a_park_behind_a_downtown_lot(layers) -> None:
    got = observed_facts(mu_cbd([None, seen(none=5), seen("Park", none=2), seen(none=5)]), layers)
    assert got["abuts_park"] is True


def test_the_bridge_clears_a_downtown_lot_with_nothing_across(layers) -> None:
    got = observed_facts(mu_cbd([None, seen(none=5), seen("School Land"), seen(none=5)]), layers)
    assert got["abuts_park"] is False


def test_the_bridge_leaves_a_trail_parcel_unstated(layers) -> None:
    got = observed_facts(mu_cbd([None, seen(none=5), seen("Other", none=1), seen(none=5)]), layers)
    assert "abuts_park" not in got


# --- Canby 16.41.070 and Gladstone 17.76 ---------------------------------------------


def test_canby_16_41_070_is_held_and_declared(corpus: RuleSet) -> None:
    path = DOCS / CANBY / "cmc.16.41.070.txt"
    meta = json.loads(Path(f"{path}.meta.json").read_text(encoding="utf-8"))
    assert meta["url"].endswith("0-0-0-39463")
    ids = {doc.id for doc in corpus.layers[CANBY].code}
    assert "cmc.16.41.070" in ids


def test_canby_dco_allows_the_flat_roof_and_keeps_its_ground_floor_rule_commercial() -> None:
    text = lines(f"{CANBY}/cmc.16.41.070.txt")
    assert text[260].startswith("a. Roof forms may be flat or sloped.")
    assert text[206].startswith("a. The ground floor of the building shall range from 12 feet to 16 feet")
    assert text[209] == "(commercial and mixed use buildings only)"


def test_canby_entries_were_already_held_to_the_street(corpus: RuleSet) -> None:
    assert corpus.resolve(CANBY, "C-1", ()).get("entrance_faces_street") == "required"


def test_gladstone_17_76_holds_four_sections_and_no_height_exception() -> None:
    text = lines(f"{GLADSTONE}/17.76.exceptions.txt")
    assert [t for t in text[6:13] if t] == [
        "17.76.010 Exceptions—Generally.",
        "17.76.020 Nonconforming uses and nonconforming developments.",
        "17.76.030 Lot size requirements.",
        "17.76.040 Setback requirements.",
    ]
