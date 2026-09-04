"""The driveway width Milwaukie prints in a chapter about streets.

This file previously recorded, in as many words, that "Milwaukie has no
encodable driveway approach width, which is why the field is absent rather
than exempt". The reasoning behind that was sound and stopped one sentence
short. MMC 19.607.1.E.1 holds a driveway to "the width of the approved
approach", which is a rule about the shape of a driveway whose width is fixed
somewhere else, and somewhere else is not in Chapter 19.600. It is in Chapter
12.16, Access Management -- Title 12, streets and public places, not zoning --
and Title 19 points at it by name three times before giving up on it.

The absence was not hidden. The cross-reference ledger had been reporting
12.16 as BINDING beside "max. maneuvering-area width" for as long as the
ledger has existed, which is the whole reason that ledger counts mentions
against fields rather than just listing them.

What the chapter turns out to hold, for a four-unit pod:

* a driveway apron 12 ft wide on a local street, 16 on a collector or
  arterial, 20 at the most on any of them -- the tightest approach ceiling in
  this corpus, against 36 in Oregon City and West Linn;
* an apron kept 5 ft off the side property line in residential districts,
  which no field in the registry can hold and which takes 5 ft off any pod
  that runs its drive up the side of the lot;
* a requirement that every backing movement happen on site, with the
  exception written for single detached uses only.

The last two are refusals recorded in the layer file. The first is encoded,
and these tests pin it.
"""

from __future__ import annotations

import pytest

from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer

pytestmark = pytest.mark.unit

MILWAUKIE = "or/clackamas/milwaukie"
ACCESS = "or/clackamas/milwaukie/12.16.access-management.txt"
VISION = "or/clackamas/milwaukie/12.24.clear-vision.txt"


@pytest.fixture(scope="module")
def milwaukie() -> Layer:
    return load_rules()[MILWAUKIE]


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


def test_the_apron_width_is_encoded_from_the_row_that_names_a_plex(
    milwaukie: Layer,
) -> None:
    """12.16.040.E.3 states the width by use class and names plex development
    in the first three words, so no judgement is needed about which row a
    four-unit building takes -- the failure mode of most parking tables in
    this corpus."""
    floor = milwaukie.defaults["driveway_approach_min_width_ft"]
    ceiling = milwaukie.defaults["driveway_approach_max_width_ft"]

    assert floor.value == 16
    assert ceiling.value == 20
    assert not floor.exempt and not ceiling.exempt


def test_the_wider_minimum_is_the_base_and_the_narrower_one_the_variant(
    milwaukie: Layer,
) -> None:
    """Street classification is measured for no parcel in this corpus, so one
    of the two figures has to stand as the default. For a MINIMUM the wider
    number is the conservative one: a lot that clears a 16 ft requirement
    clears a 12 ft one, and defaulting to 12 would pass lots on collectors
    that the city would not.

    Same choice, same direction, as this layer's parking minimum, which takes
    the arterial figure of 0.5 spaces per unit as its base for the same
    unmeasured reason.
    """
    floor = milwaukie.defaults["driveway_approach_min_width_ft"]

    assert [(v.value, v.when) for v in floor.variants] == [(12, ("local_street",))]
    assert floor.value > floor.variants[0].value


def test_the_cited_line_is_the_sentence_that_states_all_three_numbers(
    store: ProvenanceStore,
) -> None:
    line = store.load(ACCESS).text.splitlines()[259]

    assert line.startswith("Plex development")
    assert "twelve (12) feet on local or neighborhood streets" in line
    assert "sixteen (16) feet on collector or arterial streets" in line
    assert "maximum driveway apron width of twenty (20) feet on all streets" in line


def test_title_19_points_at_this_chapter_and_does_not_restate_it(
    store: ProvenanceStore,
) -> None:
    """The half of the absence claim that was true, kept under test.

    Three sentences in the zoning title send the reader to 12.16 and none of
    them carries the number. If a later re-extraction or a code amendment ever
    puts an apron width into Title 19, this goes red and the encoding above
    has to be re-argued rather than silently outranked.
    """
    pointers = {
        "19.200.definitions": "See Chapter 12.16 Access Management for definitions",
        "19.500.supplementary": "in accordance with Chapters 12.16 and 12.24",
        "19.600.parking": "access spacing standards of Chapter 12.16",
    }
    for chapter, sentence in pointers.items():
        text = store.load(f"{MILWAUKIE}/{chapter}.txt").text
        assert sentence in text, chapter
        assert "driveway apron width" not in text, chapter


def test_the_clearance_from_the_side_line_is_refused_not_encoded(
    milwaukie: Layer, store: ProvenanceStore,
) -> None:
    """12.16.040.B.4 is a real constraint with nowhere to go.

    Every driveway field in the registry is a width; this one is a distance
    between a driveway and a lot line, and encoding it as a width would make
    the screen enforce the wrong thing. Recorded as a refusal so it is counted
    as a known gap rather than read as a clear side yard.
    """
    assert "driveway apron must be at least five (5) feet from the side property line" in (
        store.load(ACCESS).text
    )
    assert not any(
        field.startswith("driveway") and "side" in field
        for field in milwaukie.defaults
    )


def test_the_clear_vision_chapter_states_no_triangle(store: ProvenanceStore) -> None:
    """The other chapter that sentence points at, and why it is stored empty.

    12.24 bans any structure over 3 ft at every driveway and every corner and
    forbids a variance from it in as many words. Then 12.24.040.A says how big
    the area is by not saying: "that area described in the most recent edition
    of the 'AASHTO Policy on Geometric Design of Highways and Streets'". The
    manual is not in this corpus, its answer depends on a design speed nothing
    here measures, and there is no line of Milwaukie code to cite for a number.

    The chapter is stored regardless. Eight mentions pointing at a chapter
    nobody opened and eight pointing at one that turns out to delegate are
    different states, and the ledger can only tell them apart if the reading
    happened. This test exists to go red if an amendment ever puts a triangle
    into the code, because that is the day this becomes encodable.
    """
    text = store.load(VISION).text

    assert "AASHTO Policy on Geometric Design of Highways and Streets" in text
    assert "shall not be modified by variance" in text
    for shape in ("clear vision area of", "vision clearance triangle", "feet along"):
        assert shape not in text

