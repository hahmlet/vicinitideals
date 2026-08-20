"""Troutdale's non-residential half, where seven zones are seven cells.

Four residential districts were ported from quadfit in July and eleven were
left unread. Seven of those eleven are settled outright by a use table or, in
one case, by a list that is not a table at all -- 349 lots, and not one
dimensional standard worth reading, because a district that refuses the use
never reaches a setback.

MU-2 and MU-3 print `P` on the same row and were encoded next, off
cross-references into TDC 3.235 -- see test_troutdale_mixed_use.

Two labels are left in the coverage ledger on purpose. NSA (74 lots) is read
and deliberately refused: TDC 3.050 hands zoning authority over those lots to
Multnomah County under MCC chapters 38 and 39, so Troutdale states no standard
for them and neither does this layer. UPAR-10 (1 lot) is a county label the
Development Code never mentions. Neither is a gap in the work -- it is the
ledger reporting the truth, which is what it is for.
"""

from __future__ import annotations

import pytest

from flats.encode.readiness import readiness_for
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

TROUTDALE = "or/multnomah/troutdale"
#: The seven added here, each settled by one cell and owning nothing else.
REFUSED = ("MU-1", "CC", "GC", "IP", "LI", "GI", "OS")
#: Every zone the layer now carries. The four residential ones came from the
#: quadfit port; HDR was already a refusal, on a different table.
ALL_ZONES = (
    "LDR-1", "LDR-2", "MDR", "HDR",
    "MU-1", "MU-2", "MU-3", "CC", "GC", "IP", "LI", "GI", "OS",
)
#: Read and left out on purpose. Kept here so that encoding one of them has to
#: come through this test rather than past it.
LEFT_UNENCODED = ("NSA", "UPAR-10")


@pytest.fixture(scope="module")
def troutdale() -> Layer:
    return load_rules()[TROUTDALE]


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


def test_the_layer_carries_thirteen_zones_and_names_them(troutdale: Layer) -> None:
    assert set(ALL_ZONES) == set(troutdale.zones)
    for zone in LEFT_UNENCODED:
        assert zone not in troutdale.zones, zone


def test_a_settled_refusal_owns_the_use_flag_and_nothing_else(
    troutdale: Layer,
) -> None:
    """Seven zones, seven values.

    Encoding a lot size for a district that refuses the building would be
    reading a table nobody has to satisfy, and it would make the zone look
    thinly answered rather than answered.
    """
    for zone in REFUSED:
        held = troutdale.zones[zone]
        assert set(held.values) == {"quadplex_allowed"}, zone
        assert held.values["quadplex_allowed"].value is False, zone
        assert held.values["quadplex_allowed"].variants == (), zone


def test_one_of_three_mixed_use_columns_refuses_and_two_permit(
    troutdale: Layer,
) -> None:
    """Table 3.220 reads `Quadplex N P P` across MU-1, MU-2, MU-3.

    A screen that assumed the mixed-use family moved together would be wrong
    in both directions at once. MU-1 is the settled RED encoded here; the two
    beside it permit the building and carry a full set of standards.
    """
    assert troutdale.zones["MU-1"].values["quadplex_allowed"].value is False
    assert set(troutdale.zones["MU-1"].values) == {"quadplex_allowed"}
    for open_column in ("MU-2", "MU-3"):
        held = troutdale.zones[open_column]
        assert held.values["quadplex_allowed"].value is True, open_column
        assert len(held.values) > 5, open_column


def test_the_commercial_answer_is_a_catch_all_row_not_a_named_one(
    troutdale: Layer,
) -> None:
    """Table 3.320 never says the word quadplex.

    It states `Residential facilities P` and then `Other residential uses N`,
    and the second row is the one that answers. A reader searching the
    commercial table for the use by name finds nothing and would call the
    district silent; it is not silent, it is closed by a catch-all.
    """
    for zone in ("CC", "GC"):
        held = troutdale.zones[zone].values["quadplex_allowed"]
        assert held.value is False, zone
        assert "3.320" in held.prov.cite, zone


def test_the_industrial_answer_permits_exactly_one_dwelling_and_not_this_one(
    troutdale: Layer,
) -> None:
    """One caretaker unit alongside an existing industrial use, in LI and GI.

    That is a real residential permission in two of the three columns, and it
    reaches a single unit tied to an operating industrial business. The row
    below it -- `All other residential uses` -- reads N in all three. Both
    facts have to be read together or the caretaker line looks like an opening.
    """
    for zone in ("IP", "LI", "GI"):
        assert troutdale.zones[zone].values["quadplex_allowed"].value is False, zone


def test_open_space_is_closed_by_a_list_rather_than_a_table(
    troutdale: Layer,
) -> None:
    """3.520 states permitted uses and conditional uses and stops.

    No dwelling appears on either list. An omission from a closed enumerated
    list is a refusal; an omission from an open one would not be, and the
    difference is the sentence that introduces it -- "The following uses and
    their accessory uses are permitted in the OS district."
    """
    held = troutdale.zones["OS"].values["quadplex_allowed"]
    assert held.value is False
    assert "3.520" in held.prov.cite


def test_the_two_refusals_in_this_city_rest_on_different_tables(
    troutdale: Layer,
) -> None:
    """HDR was ported in July off Table 3.120; these seven are not on it.

    Worth pinning because HDR is the one refusal in Troutdale that is arguable
    -- the Town Center overlay permits a quadplex there and the GIS zonecode
    cannot see the overlay, so the layer takes the conservative reading. The
    seven added here are not arguable in that way: no overlay reopens them.
    """
    hdr = troutdale.zones["HDR"].values["quadplex_allowed"]
    assert hdr.value is False
    assert "3.120" in hdr.prov.cite
    for zone in REFUSED:
        assert "3.120" not in troutdale.zones[zone].values["quadplex_allowed"].prov.cite, zone


def test_every_encoded_troutdale_zone_owes_nothing_more(rules: RuleSet) -> None:
    for zone in ALL_ZONES:
        assert rules.resolve(TROUTDALE, zone).missing_required == (), zone


def test_the_scenic_area_is_refused_rather_than_guessed(troutdale: Layer) -> None:
    """74 lots the city does not zone.

    TDC 3.050 says Multnomah County holds zoning authority over the Troutdale
    lots inside the Columbia River Gorge National Scenic Area and that they
    keep their county district designation. Encoding a Troutdale standard for
    them would be inventing a rule the city does not claim to make, so the
    layer's own notes carry the reading and the zone stays out of the rules.
    """
    assert "NSA" not in troutdale.zones
    assert "National Scenic Area" in troutdale.notes
    assert "Chapters 38 and 39" in troutdale.notes


def test_the_new_citations_all_point_at_their_own_sentence(troutdale: Layer) -> None:
    ready = readiness_for(troutdale, store=ProvenanceStore())
    assert ready.no_evidence == ()
    assert ready.misquoted == ()
