"""Covered parking (``parking_covered_required``): one covered stall a unit.

Cornelius prints the same sentence in every residential zone: "One covered
parking space shall be provided for each dwelling unit either on the
individual lot or in an off-street parking bay within 100 feet". The pod
parks in an open court with nothing over it (Steph, 2026-10-01), so where
the requirement holds, the lot misses it by every unit.

Where it holds is narrower than the sentence. OAR 660-046-0220(2)(e)(D): "A
Large City may allow, but may not require, off-street parking to be provided
as a garage or carport", for a triplex or quadplex. The townhouse rules in
(3) carry no such sentence -- (3)(e) even prices a covered requirement in
height -- so the city's sentence stands on the unit-lot path. Cornelius is
inside Metro, a Large City. So: False on the one-lot quadplex in the four
residential zones, True on the townhouse path; True outright in GMU, where
detached houses are prohibited and the state rule does not reach.
"""

from __future__ import annotations

import pytest
import yaml

from flats.designs.model import Design
from flats.encode.load import load_trusted
from flats.provenance.store import ProvenanceStore
from flats.rules.fields import OPTIONAL_FIELDS, field
from flats.rules.loader import load_rules
from flats.score.screen import CHECK_FIELD, covered_parking_check
from flats.score.slack import SlackPolicy, Verdict

pytestmark = pytest.mark.unit

FIELD = "parking_covered_required"
CORNELIUS = "or/washington/cornelius"
RESIDENTIAL = ("R-7", "R-10", "A-2", "CR")

POD = """
version: 1
label: Four-plex pod
typology: townhome_rear_court
footprint: {width_ft: 56, depth_ft: 36}
units: 4
stories: 2
height_ft: 26
parking: {stalls_per_unit: 1.0, config: rear_court}
delivery: {method: modular, crane_required: true, crane_reach_ft: 60}
"""


def pod(config: str = "rear_court") -> Design:
    body = yaml.safe_load(POD)
    body["parking"]["config"] = config
    return Design(**{**body, "id": "pod"})


class Rules:
    def __init__(self, **values: object) -> None:
        self.values = values

    def get(self, name: str) -> object:
        return self.values.get(name)


def _text(quote: str) -> str:
    return " ".join(ProvenanceStore().quote(quote).split())


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


# --- the rule ------------------------------------------------------------------


def test_the_field_is_optional_a_bool_and_read_by_a_check() -> None:
    assert FIELD in OPTIONAL_FIELDS
    assert field(FIELD).kind == "bool"
    assert CHECK_FIELD["covered_parking"] == FIELD


def test_silence_and_false_run_nothing() -> None:
    policy = SlackPolicy()
    assert covered_parking_check(Rules(), pod(), policy) is None
    assert covered_parking_check(Rules(**{FIELD: False}), pod(), policy) is None


def test_an_open_court_misses_by_every_unit() -> None:
    got = covered_parking_check(Rules(**{FIELD: True}), pod(), SlackPolicy())
    assert got is not None
    assert (got.check, got.observed, got.threshold) == ("covered_parking", 0.0, 4.0)
    assert got.verdict is Verdict.fails


def test_parking_under_the_building_is_covered() -> None:
    got = covered_parking_check(Rules(**{FIELD: True}), pod("tuck_under"), SlackPolicy())
    assert got is not None and got.verdict is Verdict.passes


# --- Cornelius ---------------------------------------------------------------


@pytest.mark.parametrize("zone", RESIDENTIAL)
def test_the_quadplex_is_spared_and_the_townhouse_path_is_not(corpus, zone: str) -> None:
    assert corpus.resolve(CORNELIUS, zone, ()).get(FIELD) is False
    assert corpus.resolve(CORNELIUS, zone, ("unit_lots",)).get(FIELD) is True
    held = load_rules()[CORNELIUS].zones[zone].values[FIELD]
    assert "may not require, off-street parking to be provided as a garage or carport" in (
        _text(held.prov.quote)
    )
    (townhouse,) = held.variants
    assert townhouse.when == ("unit_lots",)
    assert "One covered parking space shall be provided for each" in _text(
        townhouse.prov.quote
    )
    assert townhouse.prov.url.startswith("https://ecode360.com/"), zone


def test_gmu_requires_it_on_every_path(corpus) -> None:
    for conditions in ((), ("unit_lots",)):
        assert corpus.resolve(CORNELIUS, "GMU", conditions).get(FIELD) is True
    held = load_rules()[CORNELIUS].zones["GMU"].values[FIELD]
    assert held.variants == ()
    assert "One covered parking space shall be provided for each dwelling unit" in (
        _text(held.prov.quote)
    )


def test_the_townhouse_path_fails_on_it_in_cornelius(corpus) -> None:
    rules = corpus.resolve(CORNELIUS, "R-7", ("unit_lots",))
    got = covered_parking_check(rules, pod(), SlackPolicy(), CORNELIUS)
    assert got is not None and got.verdict is Verdict.fails
    one_lot = corpus.resolve(CORNELIUS, "R-7", ())
    assert covered_parking_check(one_lot, pod(), SlackPolicy(), CORNELIUS) is None


# --- the blast radius ------------------------------------------------------------


def test_only_cornelius_requires_covered_parking() -> None:
    """Adding a layer that declares this fails its pod lots on a design the
    pod does not have; that is a deliberate act, and this list says so."""
    declaring = set()
    for layer_id, layer in load_rules().items():
        if FIELD in layer.defaults:
            declaring.add(layer_id)
        for zone in layer.zones.values():
            if FIELD in zone.values:
                declaring.add(layer_id)
    assert declaring == {CORNELIUS}
