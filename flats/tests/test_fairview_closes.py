"""Fairview's three settled refusals, and the sentence that makes them readable.

LI, GI and CC -- 105 lots -- are closed to a four-unit attached townhome, and
each is closed a different way. LI has no residential use category at all and
then prohibits new housing in words. GI has a Residential category one row
long, marked `P`, that reaches a single caretaker unit and shuts the door on
everything else in the same sentence. CC has a Residential row with three
entries and the pod is none of them.

What they share is a clause at the top of every commercial and industrial
chapter in this code: "Only land uses that are specifically listed in Table
19.xx.020.A, and land uses that are approved as 'similar' to those in Table
19.xx.020.A, may be permitted." Without it, a use missing from a table is an
absence nobody read. With it, the absence IS the answer -- and that is why the
clause is quoted alongside the table in all three zones rather than assumed.

The trap here is the `P`. GI and CC both print one, and a screen that matched
on the mark instead of reading the row would open two industrial and corridor
districts to housing they refuse.
"""

from __future__ import annotations

import pytest

from flats.encode.readiness import readiness_for
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

FAIRVIEW = "or/multnomah/fairview"
#: Added here. Each is one cell plus the closed-list clause, and owns nothing
#: else -- a district that refuses the use never reaches a setback.
REFUSED = ("LI", "GI", "CC")
#: Ported from quadfit in July. Left alone by this slice.
PORTED = (
    "R-6", "R-7.5", "R-10", "RM", "RM/TOZ", "R/SFLD", "VSF", "VTH", "R/MH",
)


@pytest.fixture(scope="module")
def fairview() -> Layer:
    return load_rules()[FAIRVIEW]


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


def test_the_layer_carries_twelve_zones_and_names_them(fairview: Layer) -> None:
    assert set(REFUSED) | set(PORTED) == set(fairview.zones)


def test_a_settled_refusal_owns_the_use_flag_and_nothing_else(
    fairview: Layer,
) -> None:
    for zone in REFUSED:
        held = fairview.zones[zone]
        assert set(held.values) == {"quadplex_allowed"}, zone
        assert held.values["quadplex_allowed"].value is False, zone
        assert held.values["quadplex_allowed"].variants == (), zone


def test_the_industrial_refusal_is_stated_twice_and_only_one_is_a_table(
    fairview: Layer,
) -> None:
    """LI's Table 19.80.020.A has four categories and none of them is housing.

    Industrial, Commercial, Civic and Semi-Public, Other. An omission from a
    closed list already refuses the use, but this chapter does not stop there:
    19.80.020.C says it out loud -- "The following uses are expressly
    prohibited: new housing". The citation carries both, because the second
    sentence is what turns an inference into a reading.
    """
    held = fairview.zones["LI"].values["quadplex_allowed"]
    assert held.value is False
    assert "19.80.020.C" in held.prov.cite

    store = ProvenanceStore()
    text = store.quote(held.prov.quote)
    assert "expressly prohibited" in text
    assert "new housing" in text


def test_the_general_industrial_permission_is_one_caretaker_unit(
    fairview: Layer,
) -> None:
    """Table 19.85.020.A row 2 is Residential, it is marked P, and it refuses.

    "One caretaker unit shall be permitted for each development... Other
    residential uses are not permitted." A real residential permission that
    reaches exactly one unit tied to an industrial development, and the same
    sentence closes the district. Read the P alone and the zone looks open.
    """
    held = fairview.zones["GI"].values["quadplex_allowed"]
    assert held.value is False

    text = ProvenanceStore().quote(held.prov.quote)
    assert "One caretaker unit" in text
    assert "Other residential uses are not permitted" in text


def test_the_corridor_residential_row_lists_three_things_and_none_is_the_pod(
    fairview: Layer,
) -> None:
    """Row 4 of Table 19.70.020.A: mixed use, existing manufactured homes,
    residential care. A stand-alone four-unit townhome is not on the list.

    This is the difference from Wood Village's NC zone next door, where the
    table's own row is the broad Household Living category and a later section
    then narrows it to mixed use developments -- there the use category is
    admitted and a condition is recorded. Here the category never admits the
    building, so there is no relief to record: the pod cannot elect its way
    onto a list it is not on.
    """
    held = fairview.zones["CC"].values["quadplex_allowed"]
    assert held.value is False
    assert held.variants == ()

    text = ProvenanceStore().quote(held.prov.quote)
    assert "Residential mixed use" in text
    assert "Manufactured homes" in text
    assert "Residential care homes" in text


def test_every_refusal_quotes_the_closed_list_clause(fairview: Layer) -> None:
    """The load-bearing sentence, and the reason each quote spans two places.

    Every one of these three citations reaches the chapter's opening clause as
    well as the table row. Drop it and all three refusals become "the table
    does not mention it", which is not a reading of anything.
    """
    store = ProvenanceStore()
    for zone in REFUSED:
        text = store.quote(fairview.zones[zone].values["quadplex_allowed"].prov.quote)
        assert "Only land uses" in text, zone
        assert "may be permitted" in text, zone
        assert "similar" in text, zone


def test_the_closed_list_reading_is_written_down_where_it_can_be_argued_with(
    fairview: Layer,
) -> None:
    for zone in REFUSED:
        notes = fairview.zones[zone].notes or ""
        assert "closed list" in notes.lower(), zone


def test_the_corridor_special_standards_are_recorded_not_encoded(
    fairview: Layer,
) -> None:
    """Two more CC standards that would refuse the pod, deliberately unencoded.

    19.70.090.E.1 wants nonresidential uses on the ground floor along 75
    percent of the street-facing facade, which a fixed two-storey townhome
    cannot supply. E.2 prohibits residential mixed-use development east of NE
    223rd Avenue but for one corner. The first is a facade-length test and the
    second is a line on a map; neither can change an answer that is already no,
    so both belong in the notes rather than in a field nothing measures.
    """
    notes = fairview.zones["CC"].notes or ""
    assert "19.70.090" in notes
    assert "223rd" in notes


def test_every_encoded_fairview_zone_owes_nothing_more(rules: RuleSet) -> None:
    for zone in (*REFUSED, *PORTED):
        assert rules.resolve(FAIRVIEW, zone).missing_required == (), zone


def test_the_new_citations_all_point_at_their_own_sentence(fairview: Layer) -> None:
    ready = readiness_for(fairview, store=ProvenanceStore())
    assert ready.no_evidence == ()
    assert ready.misquoted == ()
