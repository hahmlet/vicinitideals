"""The Portland pockets are screened on Title 33, because the county adopted it.

Multnomah County and the City of Portland signed an Intergovernmental Agreement
to Transfer Land Use Planning Responsibilities in 2002 (Portland Ordinance
176115; amended 2005 for Pleasant Valley and 2011 for the tree code). Section
I.D: the county "has adopted the city comprehensive plan, zoning ordinance and
other regulations as the County's" for the unincorporated land inside
Portland's Urban Services Boundary, and Section III.C.2.a has the City review
land use, zoning and building permits there "using the City's ... zoning ...
as adopted by the County". The county keeps adopting each Title 33 amendment
(Ord. 1344, 2026, for RICAP 11 among others), and MCC 39.1100(B) says its own
procedures do not apply to "permits reviewed by a city on behalf of the county
pursuant to intergovernmental agreement".

So the pockets' parking is PCC 33.266, not MCC 39.6500 to 39.6600 -- which is
what the page check found when it saw a county sentence on a card for a zone
the county's code never names. RF is left as it was: whether the state
middle-housing path reaches it is a question still waiting on Steph.
"""

from __future__ import annotations

import pytest

from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet
from flats.encode.load import load_trusted

pytestmark = pytest.mark.unit

COUNTY = "or/multnomah/_unincorporated"
PORTLAND = "or/multnomah/portland"
TITLE33_PARKING = f"{COUNTY}/33.266.txt"

#: The Portland-administered pockets this layer screens on Title 33. RF is
#: Portland-administered too, and deliberately absent until Steph rules on it.
POCKETS = ("R5", "R7", "R10", "R20")


@pytest.fixture(scope="module")
def county() -> Layer:
    return load_rules()[COUNTY]


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


@pytest.fixture(scope="module")
def corpus() -> RuleSet:
    return RuleSet(load_trusted(strict=False).layers)


def _lines(store: ProvenanceStore, doc: str) -> list[str]:
    return store.load(doc).text.splitlines()


def test_the_layer_copy_of_title_33_is_the_portland_copy(store: ProvenanceStore) -> None:
    """Line numbers cited here transfer, because the text is the same text."""
    for doc in ("33.266.txt", "33.110.txt"):
        assert store.load(f"{COUNTY}/{doc}").text == store.load(f"{PORTLAND}/{doc}").text


def test_the_pocket_parking_setback_is_title_33s_ten_feet(
    county: Layer, store: ProvenanceStore, corpus: RuleSet
) -> None:
    """33.266.120.C.2.a prints ten feet, stated of spaces, for this building.

    The card used to cite 39.6580(A) and borrow the front yard (10 to 20 ft
    here). The sentence the pockets owe instead prints its own figure, so the
    value is held as printed and no longer follows the building setback.
    """
    lines = _lines(store, TITLE33_PARKING)
    assert lines[267].strip().startswith("33.266.120 Development Standards for Houses")
    assert "fourplexes" in lines[271]
    assert "parking spaces are not allowed within the first 10 feet from a front lot" in lines[302]

    for zone in POCKETS:
        held = county.zones[zone].values["parking_street_setback_ft"]
        assert held.same_as is None
        assert held.value == 10
        assert held.prov.quote.startswith(TITLE33_PARKING)
        assert corpus.resolve(COUNTY, zone).get("parking_street_setback_ft") == 10


def test_rf_keeps_its_county_card_until_steph_rules(county: Layer) -> None:
    """Not a reading -- a hold. RF waits on the middle-housing question."""
    held = county.zones["RF"].values["parking_street_setback_ft"]
    assert held.same_as == "setback_front_ft"
    assert held.prov.cite.startswith("MCC 39.6580(A)")
