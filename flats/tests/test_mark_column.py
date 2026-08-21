"""A wrapped line that begins with a number is not the next note.

Gresham runs note 6 of Table 4.0131 onto "10 feet in between major structures
(side to side) will be required", and inside an open block a number followed by
a space and a word is a note. Ten is above every mark the list had reached, so
it was taken -- and note 7 on the very next line, going backwards, ended the
block under the restart rule. Table 4.0131 has seven notes and no note ten.

What tells them apart is the column. A codifier aligns the numbers of a notes
list; a wrapped line is indented to clear that column by design. Across the
whole corpus the rule refuses exactly one line, and the ruling that had been
written for that line already said what it was: "the continuation of note 6".
"""

from __future__ import annotations

import pytest

from flats.encode.footnotes import MARK_COLUMN_MIN, MARK_COLUMN_SLACK, census
from flats.encode.dispositions import notes as dispositions
from flats.encode.qualified import qualified
from flats.provenance.store import ProvenanceStore

pytestmark = pytest.mark.unit

GRESHAM = "or/multnomah/gresham"
DOC = f"{GRESHAM}/4.0100.residential.txt"


@pytest.fixture(scope="module")
def residential():
    return census(ProvenanceStore().load(DOC).text, layer=GRESHAM, doc=DOC)


# --- what the column decides ------------------------------------------------


def test_a_wrap_that_starts_with_a_measurement_is_not_a_note() -> None:
    seen = census(
        "\n".join(
            [
                "Table 1 Notes:",
                "1. Front setbacks are measured from the property line.",
                "2. Side setbacks are measured from the property line.",
                "3. Rear setbacks are measured from the property line.",
                "4. A 20-foot minimum distance between major structures is",
                "            10 feet in between major structures (side to side).",
                "5. Maximum setbacks apply in the MDR districts.",
            ]
        ),
        doc="d.txt",
    )
    assert [b.mark for b in seen.bodies] == ["1", "2", "3", "4", "5"]
    fourth = next(b for b in seen.bodies if b.mark == "4")
    assert "10 feet in between" in fourth.text


def test_but_a_note_in_its_own_column_still_is_one() -> None:
    """Same list, same numbers, one indent. The rule is about the column and
    not about what the line happens to say."""
    seen = census(
        "\n".join(
            [
                "Table 1 Notes:",
                "1. Front setbacks are measured from the property line.",
                "2. Side setbacks are measured from the property line.",
                "3. Rear setbacks are measured from the property line.",
                "4. A 20-foot minimum distance between major structures is",
                "10 feet in between major structures (side to side).",
            ]
        ),
        doc="d.txt",
    )
    assert [b.mark for b in seen.bodies] == ["1", "2", "3", "4", "10"]


def test_the_column_is_not_believed_until_enough_notes_agree() -> None:
    """Two notes are not a column. Measured from the first note instead of the
    commonest, this rule refuses five real notes in two documents -- Portland's
    33.120 and Gresham's middle housing design chapter both open a block with
    one indent and settle on another."""
    assert MARK_COLUMN_MIN == 3
    assert MARK_COLUMN_SLACK == 6
    seen = census(
        "\n".join(
            [
                "Table 1 Notes:",
                "1. Front setbacks are measured from the property line.",
                "2. Side setbacks are measured from the property line.",
                "            3. Rear setbacks are measured from the property line.",
            ]
        ),
        doc="d.txt",
    )
    assert [b.mark for b in seen.bodies] == ["1", "2", "3"]


# --- what Table 4.0131 says now ---------------------------------------------


def test_the_setback_table_answers_all_seven(residential) -> None:
    block = next(b for b in residential.blocks if b.head == 418)
    assert [b.mark for b in block.bodies] == ["1", "2", "3", "4", "5", "6", "7"]
    assert [b.line for b in block.bodies] == [419, 421, 426, 427, 428, 430, 433]
    assert residential.unbodied == ()


def test_note_six_keeps_the_figure_that_used_to_be_note_ten(residential) -> None:
    six = next(b for b in residential.bodies if b.line == 430)
    assert "20-" in six.text
    assert "10 feet" in six.text


def test_the_maximum_setback_note_is_readable_at_last(residential) -> None:
    """Note 7 gives MDR-12, MDR-24 and OFR the maximum front and street-side
    setbacks Table 4.0430 states for the Corridor Multi-family district. It is
    marked on the Multi-family heading at L412 and nowhere else, and this layer
    reads the MDR setbacks off L403 -- the row for a single detached dwelling,
    duplex, triplex and quadplex -- so it does not reach the pod. It is the
    reason to check the row before adding a maximum, not a maximum to add."""
    seventh = next(b for b in residential.bodies if b.line == 433)
    assert "Maximum front and street-side setbacks" in seventh.text
    assert "4.0430" in seventh.text
    ruled = {row.quote: row for row in dispositions(GRESHAM)}
    assert ruled[f"{DOC}#L433"].state == "dismissed"


def test_no_ruling_is_left_pointing_at_a_body_that_is_gone() -> None:
    """L431 had a ruling of its own that called it the continuation of note 6.
    It was right, and there is nothing left to rule."""
    ruled = {row.quote for row in dispositions(GRESHAM)}
    assert f"{DOC}#L431" not in ruled
    assert not [row for row in qualified() if row.blocking]
