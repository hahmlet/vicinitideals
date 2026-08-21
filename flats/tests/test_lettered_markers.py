"""The table whose notes run A through P, and the cells that point at them.

Wilsonville's Frog Pond chapter is the document behind a hundred and
seventy-five encoded values, and it stated fifty-one footnotes with thirteen
markers in the whole file. Forty-three notes nobody pointed at -- the townhouse
minimum lot size, the quadplex minimum in R-5 and R-7, the exemption of a
shared townhouse wall from the side setback, the combined side yard on a wide
lot -- because every one of them is marked with a letter and nothing in the
census read a letter as a marker.

A bare capital is the weakest marker shape there is, so it is not read on its
own authority. It is emitted provisional and kept only where the block
governing that line states a note by that letter, which is the same bargain a
lone permission code already makes. A document with no lettered block reads
none of them, and a stray letter can never invent an orphan -- it can only
satisfy a body the same block already states.
"""

from __future__ import annotations

import pytest

from flats.encode.dispositions import notes as dispositions
from flats.encode.footnotes import LETTER_CELL, LETTER_GLUED, census
from flats.encode.qualified import qualified
from flats.provenance.store import ProvenanceStore

pytestmark = pytest.mark.unit

WILSONVILLE = "or/clackamas/wilsonville"
DOC = f"{WILSONVILLE}/4.planning.txt"


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


@pytest.fixture(scope="module")
def planning(store: ProvenanceStore):
    return census(store.load(DOC).text, layer=WILSONVILLE, doc=DOC)


# --- the two shapes a lettered marker wears -------------------------------


def test_the_letter_alone_in_its_cell() -> None:
    """An HTML extraction puts every cell on its own line, so a column head
    carrying two notes arrives as the three characters "A,B" -- and a run the
    extractor broke across lines arrives as "I," and then "J, N"."""
    assert LETTER_CELL.match("H").group("n") == "H"
    assert LETTER_CELL.match("A,B").group("n") == "A,B"
    assert LETTER_CELL.match("I,").group("n") == "I"
    assert LETTER_CELL.match("O,P").group("n") == "O,P"


def test_and_the_letter_welded_to_its_value() -> None:
    """"18G" is eighteen feet subject to note G. The value has to come first,
    which is what keeps the zone code and the street name out."""
    assert LETTER_GLUED.match("18G").group("n") == "G"
    assert LETTER_GLUED.match("10D").group("n") == "D"
    assert LETTER_GLUED.match("1J").group("n") == "J"
    assert LETTER_GLUED.match("40%E").group("n") == "E"
    assert LETTER_GLUED.match("S3") is None
    assert LETTER_GLUED.match("SW") is None
    assert LETTER_GLUED.match("60'") is None
    assert LETTER_GLUED.match("4,000") is None


# --- what makes it safe ----------------------------------------------------


ROW = "R-10 Large Lot 8,000 60' 40% E 40 35 20 F 20 M 18G 20"


def test_a_letter_is_read_only_where_a_note_answers_it() -> None:
    """The same row, in a document with a lettered block and in one without.
    A capital letter is a shape prose wears by accident, so it earns its
    reading from the block or it does not get one."""
    lettered = census(
        "\n".join([ROW, "Notes:", "E. Maximum lot coverage may be increased by 10%."]),
        doc="d.txt",
    )
    assert [m.mark for m in lettered.markers] == ["E"]

    numbered = census(
        "\n".join([ROW, "Notes:", "1. Maximum lot coverage may be increased by 10%."]),
        doc="d.txt",
    )
    assert not numbered.markers


def test_and_a_stray_letter_cannot_invent_an_orphan() -> None:
    """The direction this fails in matters. A letter the block does not state
    is dropped, so the worst an over-generous reading can do is satisfy a body
    the block already states -- never manufacture a marker with nothing behind
    it, which is the report that sends somebody looking for a missing note."""
    seen = census(
        "\n".join([ROW, "Notes:", "E. Maximum lot coverage may be increased by 10%."]),
        doc="d.txt",
    )
    assert seen.unbodied == ()
    assert seen.unmarked == ()


# --- what the chapter says now ---------------------------------------------


def test_the_frog_pond_tables_point_at_their_own_notes(planning) -> None:
    """Thirteen markers against fifty-one notes, before. The two that are
    still unanswered are a table title's superscript and a "feet4" whose notes
    are in a document this corpus does not hold -- the honest direction."""
    assert len(planning.markers) > 150
    assert len(planning.unmarked) == 4
    assert {m.mark for m in planning.unbodied} == {"21", "4"}


def test_the_standards_that_were_hiding_in_the_lettered_notes(planning) -> None:
    """Table 8A's notes are the townhouse and quadplex lot standards, and
    nothing in the table cells says so except a letter."""
    text = {b.mark: b.text for b in planning.bodies if 7237 < b.line < 7280}
    assert "minimum lot size in all sub-districts is 1,500 square feet" in text["B"]
    assert "quadplexes and cottage clusters is 7,000 square feet" in text["C"]
    assert "minimum lot width is 20 feet" in text["I"]
    assert "minimum combined side yard setbacks" in text["M"]


# --- the digit welded to its own first word --------------------------------


def test_a_note_welded_to_its_first_word_is_still_a_note(planning) -> None:
    """"2No additional off-street parking is required for middle housing" is
    note 2, and it read as the tail of note 1 -- one body, one ruling, and a
    parking standard nobody could rule on separately. Parking is a standard
    this screen does read."""
    parking = {b.line: b.text for b in planning.bodies if 5289 < b.line < 5293}
    assert parking[5290] == "1/1,000 sf min. for court facilities"
    assert parking[5291].startswith("No additional off-street parking")


def test_and_the_lake_oswego_height_exceptions_it_also_found(store) -> None:
    """The same shape, in the other document that wears it: two notes under
    the height-exception list, both pointing at a section of the code for the
    maximum. Neither was captured, and neither is answered by a marker -- the
    superscripts on "solar energy system1" survive extraction as a digit the
    marker rules read only after a unit."""
    doc = "or/clackamas/lake-oswego/50.04.dimensional.txt"
    seen = census(store.load(doc).text, layer="or/clackamas/lake-oswego", doc=doc)
    found = {b.mark: b.text for b in seen.bodies if 2410 < b.line < 2415}
    assert found["1"].startswith("See LOC § 50.04.003.4.b.ii")
    assert found["2"].startswith("See LOC § 50.04.003.4.b.iii")


def test_every_wilsonville_note_that_governs_a_value_is_ruled() -> None:
    """Splitting one body into two split the ruling that covered both. The
    gate is a ratchet: nothing in the corpus may be blocked when the suite
    runs."""
    ruled = {row.quote for row in dispositions(WILSONVILLE) if row.state != "unread"}
    assert f"{DOC}#L5290" in ruled
    assert f"{DOC}#L5291" in ruled
    assert not [row for row in qualified() if row.blocking]
