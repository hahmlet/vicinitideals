"""The quadfit port and the backlog it feeds.

Two contracts. The port must lose nothing — a field quadfit encoded that FLATS
silently drops is the same class of failure as an unencoded zone, just quieter.
And nothing may arrive trusted: quadfit verified against one citation per row,
which does not carry over.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from flats.encode.port_quadfit import COUNTY, FIELD_MAP, layer_id_for, port, port_zone
from flats.rules.fields import FIELDS
from flats.rules.loader import load_rules
from flats.rules.model import Status
from flats.rules.resolver import RuleSet, Verdict

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG = REPO_ROOT / "flats" / "config" / "jurisdictions"


@pytest.fixture(scope="module")
def dry() -> dict:
    return port(write=False)


# --- the port ---------------------------------------------------------


def test_nothing_is_dropped(dry: dict) -> None:
    # Every quadfit column either maps to a registered field or is deliberately
    # skipped. An unported field is data loss, and it is silent, so it is a test.
    assert dry["unported"] == []


def test_every_quadfit_zone_arrives(dry: dict) -> None:
    assert dry["stats"]["zones"] == 96
    assert dry["stats"]["layers"] == len(COUNTY) == 18


def test_field_map_targets_are_registered() -> None:
    unknown = sorted(set(FIELD_MAP.values()) - set(FIELDS))
    assert unknown == [], f"FIELD_MAP points at unregistered fields: {unknown}"


def test_quadfit_verification_does_not_carry_over() -> None:
    # 73 of 96 rows were `verified` in quadfit against a coarser standard.
    values = [
        v
        for layer in RuleSet(load_rules()).layers.values()
        for zone in layer.zones.values()
        for v in zone.values.values()
    ]
    assert values, "no values loaded — the port did not write"
    assert {v.status for v in values} == {Status.draft}


def test_quadfit_confidence_survives_for_queue_ordering() -> None:
    # The port drops the trust but keeps the signal: rows quadfit called
    # verified are quick confirmations, the rest is real work.
    text = (CONFIG / "or" / "multnomah" / "portland.yaml").read_text(encoding="utf-8")
    assert "quadfit confidence:" in text


@pytest.mark.parametrize(
    "jurisdiction,expected",
    [
        ("portland", "or/multnomah/portland"),
        ("wood_village", "or/multnomah/wood-village"),
        ("multnomah_unincorporated", "or/multnomah/_unincorporated"),
        ("clackamas_unincorporated", "or/clackamas/_unincorporated"),
        ("oregon_city", "or/clackamas/oregon-city"),
    ],
)
def test_layer_id_mapping(jurisdiction: str, expected: str) -> None:
    assert layer_id_for(jurisdiction) == expected


def test_unmapped_jurisdiction_fails_loudly() -> None:
    with pytest.raises(KeyError):
        layer_id_for("beaverton")


def test_zone_citation_becomes_cite_default() -> None:
    row = {
        "zone": "R5",
        "source": "PCC 33.110.220",
        "source_url": "https://example.gov/33110",
        "confidence": "verified",
        "setback_front_ft": 10,
    }

    block, unported = port_zone(row, "2026-07-24")

    assert block["cite_default"]["cite"] == "PCC 33.110.220"
    assert block["setback_front_ft"] == 10
    assert unported == []


def test_unmapped_column_is_reported_not_swallowed() -> None:
    row = {"zone": "R5", "confidence": "verified", "some_new_standard": 42}

    block, unported = port_zone(row, "2026-07-24")

    assert unported == ["some_new_standard=42"]
    assert "UNPORTED" in block["notes"]


# --- what the port produced ------------------------------------------


def test_written_config_loads_through_the_real_loader() -> None:
    # The port writes YAML by hand; the loader is the only judge of whether it
    # is valid. Round-tripping is the whole point of doing this as a port.
    rules = RuleSet(load_rules())

    assert len(rules.layers) == 19  # 18 jurisdictions + the state layer
    assert sum(len(l.zones) for l in rules.layers.values()) == 102


def test_state_parking_preemption_reaches_a_city_zone() -> None:
    res = RuleSet(load_rules()).resolve("or/multnomah/portland", "R5")

    parking = res.values["parking_min_per_unit"]
    assert parking.value == 1.0
    assert parking.layer == "or", "state cap must win over any local standard"


def test_ported_zones_are_unverified_not_trusted() -> None:
    res = RuleSet(load_rules()).resolve("or/multnomah/portland", "R5")

    assert res.verdict is Verdict.unverified
    assert res.chain == ("or/multnomah/portland", "or")


def test_unencoded_zone_is_surfaced_not_dropped() -> None:
    # RM1 was the 14,426-lot hole this rebuild exists to close, and Chapter
    # 33.120 closed it. What the test is for outlives the example: a zone the
    # GIS reports and the rules do not carry must come back saying so, rather
    # than resolving off the state layer and reading like a thin encoding.
    res = RuleSet(load_rules()).resolve("or/multnomah/portland", "RM1")
    assert res.verdict is not Verdict.zone_not_encoded, "33.120 is encoded"

    res = RuleSet(load_rules()).resolve("or/multnomah/portland", "CM2")

    assert res.verdict is Verdict.zone_not_encoded


def test_ineligible_jurisdictions_kept_their_flag() -> None:
    off = {
        p.stem
        for p in CONFIG.rglob("*.yaml")
        if yaml.safe_load(p.read_text(encoding="utf-8")).get("eligible") is False
    }
    assert off == {"johnson-city", "lake-oswego", "rivergrove", "maywood-park"}


def test_ingest_metadata_survives_for_the_gis_stage() -> None:
    layer = yaml.safe_load((CONFIG / "or" / "multnomah" / "portland.yaml").read_text(encoding="utf-8"))

    assert layer["ingest"]["zoning_layer"]
    assert layer["ingest"]["zone_field"]
