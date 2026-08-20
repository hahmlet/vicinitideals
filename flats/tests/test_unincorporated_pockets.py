"""County land wearing Portland's labels, and two table cells that lie.

Multnomah County administers pockets inside Portland's urban planning area, and
those pockets carry Portland's zone codes. The single-dwelling ones -- RF, R20,
R10, R7, R5 -- have read PCC 33.110 since the port. Three more were sitting in
the coverage ledger with nobody assigned to them: OS, EG2 and IG2, 36 lots
between them.

Two of the three are worth a test for a reason that has nothing to do with 36
lots. Portland's Table 140-1 gives Household Living an ``L[1]`` in the EG2
column and a ``CU [2]`` in the IG2 column, and both look like doors. Note [1]
allows housing only when "an existing hotel or motel is converted to dwelling
units". Note [2] sends houseboats to Chapter 33.236 and then says "Household
and Group Living in other structures is prohibited". A screen that read the
cells and skipped the notes would call an industrial lot a conditional-use
opportunity.
"""

from __future__ import annotations

import pytest

from flats.encode.readiness import readiness_for
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

UNINC = "or/multnomah/_unincorporated"
PORTLAND = "or/multnomah/portland"
POD = ("multi_story", "attached_wall")
POCKETS = ("OS", "EG2", "IG2")


@pytest.fixture(scope="module")
def layers() -> dict[str, Layer]:
    return load_rules()


@pytest.fixture(scope="module")
def uninc(layers: dict[str, Layer]) -> Layer:
    return layers[UNINC]


@pytest.fixture(scope="module")
def rules(layers: dict[str, Layer]) -> RuleSet:
    return RuleSet(layers)


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


def test_every_pocket_refuses_and_owes_nothing_else(
    uninc: Layer, rules: RuleSet
) -> None:
    for zone in POCKETS:
        res = rules.resolve(UNINC, zone, POD)
        assert res.values["quadplex_allowed"].value is False, zone
        assert res.missing_required == (), zone
        assert set(uninc.zones[zone].values) == {"quadplex_allowed"}, zone


def test_the_open_space_cell_is_a_bare_prohibition(
    uninc: Layer, store: ProvenanceStore
) -> None:
    """Table 100-1 gives Household Living an N and nothing beside it.

    No bracket, no conditional-use column, no footnote. The cheapest answer in
    the corpus, and the citation carries the header row so the column being
    read is visible.
    """
    text = store.quote(uninc.zones["OS"].values["quadplex_allowed"].prov.quote)
    assert "OS Zone" in text
    assert "Household Living" in text
    assert "CU" not in text


def test_the_employment_cell_is_a_hotel_conversion_not_a_permission(
    uninc: Layer, store: ProvenanceStore
) -> None:
    """L[1] reads as a yes until note [1] says what the limit is."""
    text = store.quote(uninc.zones["EG2"].values["quadplex_allowed"].prov.quote)
    assert "Limited use" in text
    assert "existing hotel or motel is converted to dwelling units" in text
    assert "EG2" in text


def test_the_industrial_cell_is_a_houseboat_not_a_conditional_use(
    uninc: Layer, store: ProvenanceStore
) -> None:
    """CU [2] is the most inviting thing a screen can find, and note [2] ends it.

    "Household and Group Living in houseboats and houseboat moorages in I zones
    are regulated by Chapter 33.236, Floating Structures. Household and Group
    Living in other structures is prohibited." A townhome on land is the other
    structures.
    """
    text = store.quote(uninc.zones["IG2"].values["quadplex_allowed"].prov.quote)
    assert "houseboat" in text
    assert "in other structures is prohibited" in text
    assert "IG2" in text


def test_the_pocket_answers_the_same_way_the_city_layer_does(
    layers: dict[str, Layer]
) -> None:
    """Same table, same column, so the two layers must not disagree.

    They are separate encodings citing separate copies of the same chapter --
    the convention this layer already follows for 33.110 -- which is exactly
    the arrangement in which a drift would go unnoticed.
    """
    for zone in POCKETS:
        here = layers[UNINC].zones[zone].values["quadplex_allowed"]
        there = layers[PORTLAND].zones[zone].values["quadplex_allowed"]
        assert here.value == there.value, zone
        assert here.prov.quote.split("#")[1] == there.prov.quote.split("#")[1], zone


def test_the_label_this_file_assigned_is_recorded_as_assigned(uninc: Layer) -> None:
    """Four of the 28 OS lots have Gresham addresses, not Portland ones.

    The reading is that county land inside a city's planning area carries that
    city's label. It holds for 25 of them by address and is an inference for
    the other four, and an inference that changes no answer is still one
    somebody should be able to find.
    """
    notes = uninc.zones["OS"].notes or ""
    assert "Gresham" in notes
    assert "Portland-administered pocket" in notes


def test_the_pocket_citations_point_at_their_own_sentence(
    uninc: Layer, store: ProvenanceStore
) -> None:
    ready = readiness_for(uninc, store=store)
    assert ready.no_evidence == ()
    assert ready.misquoted == ()
