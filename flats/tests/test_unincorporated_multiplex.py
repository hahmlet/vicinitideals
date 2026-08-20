"""MR-4, C-3, UF-20, CFU-2, R5 -- and the word the county never defines.

Five labels, 22 lots, and one of them is the only zone in Multnomah County's
own code that permits this building outright. MCC 39.4975 is PRIMARY USES and
(B) is a single line: "A multiplex dwelling structure." No conditional use, no
hearing, no locational rule of the kind LR-5 carries four articles up.

Which makes the definition load-bearing, and it is not obvious. MCC 39.2000
defines a Multi-Plex Dwelling Structure as "a row house or town house apartment
structure" and stops. A Row House is "a one-story apartment structure having
three or more dwelling units" -- the pod is two storeys, so it is not that half.
An Apartment is "any building or portion thereof used for or containing three or
more dwelling units", which the pod is. And "town house" has no entry in the
glossary at all.

So the pod reaches the multiplex row through the undefined half of a two-part
definition. That reading is almost certainly right, and it is still a reading.
These tests hold the chain in place so that if somebody later finds a town house
definition -- in the county's code or in a state statute that reaches it -- the
three zones it decides fail together rather than drifting apart.
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
POD = ("multi_story", "attached_wall")
GLOSSARY = f"{UNINC}/39.2000.definitions.txt"
#: The three zones whose answer turns on what a multiplex is.
DECIDED_BY_THE_CHAIN = ("MR4", "LR5", "LR7")


@pytest.fixture(scope="module")
def uninc() -> Layer:
    return load_rules()[UNINC]


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


def test_the_medium_density_zone_permits_the_pod_outright(rules: RuleSet) -> None:
    """No condition supplied, and the answer is still yes.

    Every other true in this layer needs something: LR-5 needs a hearing and a
    corner lot, EFU needs a farm and a review use, the Portland pockets need
    Table 110-2 to say Yes. MR-4 needs nothing, which is what makes it the one
    county article a batch screen can return GREEN on.
    """
    res = rules.resolve(UNINC, "MR4", POD)
    assert res.values["quadplex_allowed"].value is True
    assert res.missing_required == ()


def test_the_permission_is_a_primary_use_not_a_conditional_one(
    uninc: Layer, store: ProvenanceStore
) -> None:
    """39.4975 is the primary list, and the citation carries the heading.

    A quadplex line quoted without its heading could be sitting under CONDITIONAL
    USES two sections down and read identically. The heading is the difference
    between a lot that can be built on and a lot that can be applied for.
    """
    held = uninc.zones["MR4"].values["quadplex_allowed"]
    assert held.variants == ()

    text = store.quote(held.prov.quote)
    assert "PRIMARY USES" in text
    assert "(B) A multiplex dwelling structure;" in text
    # The closure wraps after "no", so the half that survives is the half to
    # assert on -- the same wrap CFU's closure takes two articles earlier.
    assert "building, structure or land shall be used" in text.lower()
    assert "the uses listed in MCC 39.4975 through 39.4985" in text


def test_the_multiplex_definition_runs_through_an_undefined_word(
    store: ProvenanceStore,
) -> None:
    """Row house is the half the pod fails; town house is the half nobody wrote.

    The glossary defines a Multi-Plex as one of two things. The first is defined
    and excludes this building on storey count. The second is not defined
    anywhere in Chapter 39, so the permission MR-4 grants rests on the ordinary
    meaning of two words rather than on the county's own vocabulary.
    """
    multiplex = store.quote(f"{GLOSSARY}#L929-L930")
    assert "row house" in multiplex
    assert "town house apartment structure" in multiplex

    row_house = store.quote(f"{GLOSSARY}#L1097-L1098")
    assert "one-story apartment structure" in row_house

    apartment = store.quote(f"{GLOSSARY}#L188-L190")
    assert "three or more dwelling" in apartment

    # Glossary entries print their term capitalised, then an en dash. "Town
    # House" never appears in that position; the only occurrence of the phrase
    # in the whole chapter is inside the Multi-Plex definition itself.
    glossary = store.text_path(GLOSSARY).read_text(encoding="utf-8")
    assert "Town House" not in glossary
    assert glossary.count("town house") == 1


def test_the_chain_is_written_into_every_zone_it_decides(uninc: Layer) -> None:
    """Three zones, one reading, and the reading is stated in all three.

    A note in MR-4 alone would leave LR-5 and LR-7 looking like they had settled
    the question independently. They have not -- they inherit it, and a reader
    who overturns the definition has to be able to find every zone that moves.
    """
    for zone in DECIDED_BY_THE_CHAIN:
        notes = uninc.zones[zone].notes or ""
        assert "town house" in notes.lower(), zone
        assert "MULTIPLEX" in notes, zone


def test_the_older_note_claiming_this_was_settled_is_gone(uninc: Layer) -> None:
    """LR-7 used to say the word townhouse appears nowhere in its article.

    True of MCC 39.4848 through 39.4868, and irrelevant -- the definition lives
    in 39.2000, four parts earlier, and reaches every article in the chapter.
    A claim that is locally true and globally wrong is worse than no claim.
    """
    notes = uninc.zones["LR7"].notes or ""
    assert "39.2000" in notes
    assert "39.4848 through 39.4868" in notes


def test_the_medium_density_lot_minimum_is_the_lowest_of_the_three(
    uninc: Layer,
) -> None:
    """4,000 per unit against LR-5's 4,500 and LR-7's 5,000.

    All three state the figure per dwelling and none of them prints the product,
    which is the bargain the derived form exists for: the file carries the number
    a reader can find and the loader multiplies.
    """
    stated = {
        zone: uninc.zones[zone].values["min_lot_sqft"] for zone in DECIDED_BY_THE_CHAIN
    }
    assert stated["MR4"].per_dwelling == 4000
    assert stated["MR4"].value == 16000
    assert stated["MR4"].per_dwelling < stated["LR5"].per_dwelling
    assert stated["LR5"].per_dwelling < stated["LR7"].per_dwelling


def test_the_neighbour_yard_rule_is_recorded_rather_than_encoded(
    uninc: Layer,
) -> None:
    """39.4990(K) can turn a 5-foot side yard into a 26-foot one.

    An apartment structure in MR-4 owes a yard equal to its own height against
    any adjacent LR base zone lot line. Two facts stop it being encoded and both
    are missing rather than ignored: nothing here holds the neighbour's zoning,
    and whether four attached units are an "apartment structure" turns on the
    same undefined vocabulary the use flag does.
    """
    assert uninc.zones["MR4"].values["setback_side_ft"].value == 5

    notes = uninc.zones["MR4"].notes or ""
    assert "39.4990(K)" in notes
    assert "adjacent LR base zone lot line" in notes


def test_the_retail_zone_forbids_a_residence_in_one_sentence(
    uninc: Layer, store: ProvenanceStore
) -> None:
    """C-3 does not need an absence read. It says it.

    68 enumerated retail uses and then 39.4737(H), which is the cheapest kind of
    certainty in this corpus -- a prohibition rather than a silence. The
    caretaker exception is one unit for somebody who works there.
    """
    held = uninc.zones["C3"].values["quadplex_allowed"]
    assert held.value is False
    assert held.variants == ()

    text = store.quote(held.prov.quote)
    assert "No new residence shall be permitted in" in text
    assert "janitor or night watchperson" in text


def test_the_holding_zone_permits_two_dwellings_and_both_are_detached(
    uninc: Layer, store: ProvenanceStore
) -> None:
    """UF-20 is land waiting to be rezoned, and it waits by keeping the list short.

    39.4751(A) is a single-family detached dwelling; 39.4752(A) is a second
    single-family dwelling for farm help on the same lot. Two dwellings, neither
    of them four units, and the closure sentence above them is what makes the
    absence of anything else evidence.
    """
    held = uninc.zones["UF20"].values["quadplex_allowed"]
    assert held.value is False
    assert set(uninc.zones["UF20"].values) == {"quadplex_allowed"}

    text = store.quote(held.prov.quote)
    assert "except for" in text and "the uses listed in" in text
    # 39.4751(A) hyphenates "single-family" across the line break; the half that
    # survives the wrap is the half worth counting.
    assert "family detached dwelling on a lot" in text
    assert "housing of help required" in text

    notes = uninc.zones["UF20"].notes or ""
    assert "Twenty acres" in notes


def test_the_forest_variant_incorporates_by_the_codes_own_sentence(
    uninc: Layer, store: ProvenanceStore
) -> None:
    """CFU-2 is not an article. 39.4050(C) says so, and the `like` quotes it.

    An incorporation is a rule like any other and owes the same evidence. The
    difference between a `like` somebody can check and a `like` somebody guessed
    from the label is exactly this sentence.
    """
    zone = uninc.zones["CFU2"]
    assert zone.like is not None
    assert zone.like.zone == "CFU"
    assert zone.like.wins == "local"
    assert zone.values == {}

    text = store.quote(zone.like.prov.quote)
    assert "CFU-2" in text
    assert "expressly stated otherwise" in text


def test_the_incorporated_zone_answers_exactly_as_its_parent(rules: RuleSet) -> None:
    parent = rules.resolve(UNINC, "CFU", POD)
    child = rules.resolve(UNINC, "CFU2", POD)
    assert child.values["quadplex_allowed"].value is False
    assert (
        child.values["quadplex_allowed"].value
        is parent.values["quadplex_allowed"].value
    )
    assert child.missing_required == ()


def test_the_last_portland_pocket_reads_the_same_table_row_as_the_others(
    uninc: Layer, store: ProvenanceStore
) -> None:
    """R5 is the fifth of six columns on one printed line of Table 110-2.

    R20, R10 and R7 were encoded off this row at the port and R5 was not, for no
    better reason than that nobody had reached it. Citing the identical span is
    the check that the same row was read the same way rather than four times
    from memory.
    """
    row = "or/multnomah/_unincorporated/33.110.txt#L313"
    for zone in ("R20", "R10", "R7", "R5"):
        held = uninc.zones[zone].values["quadplex_allowed"]
        assert held.value is True, zone
        assert held.prov.quote == row, zone

    text = store.quote(row)
    assert text.split()[0] == "Fourplex"
    assert text.split()[1:] == ["No", "Yes", "Yes", "Yes", "Yes", "Yes"]


def test_the_last_pocket_has_the_loosest_lot_minimum_in_the_layer(
    uninc: Layer,
) -> None:
    """3,000 square feet, against 4,200 in R7 and 12,000 in R20.

    Table 110-7 is a fourplex-specific standard rather than the zone's general
    lot size, which is why it is small enough to look like a mistake. Thirteen
    lots carry the label.
    """
    sizes = {
        zone: uninc.zones[zone].values["min_lot_sqft"].value
        for zone in ("R5", "R7", "R10", "R20")
    }
    assert sizes["R5"] == 3000
    assert sorted(sizes, key=lambda zone: sizes[zone]) == ["R5", "R7", "R10", "R20"]


def test_the_adjustment_with_an_expiry_date_is_not_encoded(uninc: Layer) -> None:
    """Table 110-7 offers 10 percent off, and only until January 2032.

    A relief that stops existing on a date is a different thing from a relief,
    and nothing in the value model holds a date. Encoding it as an ordinary
    variant would have made a lot look buildable in 2033 on a rule that expired.
    """
    assert uninc.zones["R5"].values["min_lot_sqft"].variants == ()


def test_the_multiplex_citations_all_point_at_their_own_sentence(
    uninc: Layer, store: ProvenanceStore
) -> None:
    ready = readiness_for(uninc, store=store)
    assert ready.no_evidence == ()
    assert ready.misquoted == ()
