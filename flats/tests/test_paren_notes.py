"""The city that parenthesises everything, and the three ways it hid.

Fairview writes its use-table notes as "(1) Subject to standards in FMC
19.30.080, Special standards for certain uses." -- a parenthesised number, a
space, a sentence. That is also the shape of every ordinary subsection in this
corpus, which is why the module refuses it on layout alone; thirteen of the
fourteen bare runs in the corpus are lists of criteria hanging off "one or more
of the following:". It marks its cells "X(CU) (1)", with the review type in
brackets and a space before the note, which the marker rule refuses for the
same reason: one space of slack there reads "twenty (20)" at the end of a
wrapped sentence as a footnote, in eleven documents. And its extraction prints
the whole notes block once per column of the table -- seven times -- so the
same six sentences arrive as seven blocks, six of which are bodies nobody
points at.

Together those three read a chapter as thirty-four orphan markers and six
unanswered bodies. What was actually in it: the note that sends a quadplex to
FMC 19.30.040, which is the only citation in this corpus for a constraint
quadfit asserted in every Clackamas city and justified in none of them.
"""

from __future__ import annotations

import pytest

from flats.encode.dispositions import notes as dispositions
from flats.encode.footnotes import census
from flats.encode.qualified import qualified
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

FAIRVIEW = "or/multnomah/fairview"
DOC = f"{FAIRVIEW}/19.30.txt"


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


@pytest.fixture(scope="module")
def chapter(store: ProvenanceStore):
    return census(store.load(DOC).text, layer=FAIRVIEW, doc=DOC)


# --- a spaced parenthesised run -------------------------------------------


RUN = [
    "(1) Subject to standards in FMC 19.30.080.",
    "(2) Subject to additional standards in FMC 19.30.090.",
    "(3) Subject to standards in Chapter 19.490 FMC.",
]

TABLE = [
    "a. Quadplex",
    "X(1)",
    "b. Cottage cluster",
    "X(2)",
    "c. Manufactured home park",
    "X(3)",
]


def test_a_spaced_run_under_a_marked_cell_is_a_notes_block() -> None:
    seen = census("\n".join(TABLE + RUN), doc="d.txt")
    assert [b.mark for b in seen.bodies] == ["1", "2", "3"]
    assert seen.reconciled


def test_but_not_under_a_colon(store: ProvenanceStore) -> None:
    """What the thirteen other runs in the corpus are. A colon says the lines
    below it are the sentence's own list, and a notes block is never introduced
    by the row it answers."""
    lines = ["X(1)", "The site must meet one or more of the following:", *RUN]
    assert census("\n".join(lines), doc="d.txt").bodies == ()


def test_and_not_under_a_line_that_carries_no_marker() -> None:
    """A notes block sits under the table it answers, and a table cell that
    takes a note carries one. Prose above a run means the run is prose."""
    lines = ["The following standards apply to all development.", *RUN]
    assert census("\n".join(lines), doc="d.txt").bodies == ()


def test_and_the_run_has_to_climb_to_three() -> None:
    """Same standard of proof the gapped and glued shapes buy their reading
    with. Two lines is a coincidence a subsection can supply."""
    lines = TABLE + RUN[:2] + ["B. Determination of Similar Use."]
    assert census("\n".join(lines), doc="d.txt").bodies == ()


# --- a cell with a space in it --------------------------------------------


def test_the_cell_that_names_a_review_type_and_a_note() -> None:
    """"X(CU) (1)" is a conditional use subject to note 1, and "X(1) (2)" is
    permitted subject to notes 1 and 2. The parenthesised review type is not a
    marker; the digits are."""
    lines = [
        "a. Kennels",
        "X(CU) (1)",
        "b. Multi-unit dwellings",
        "X(1) (2)",
        "c. Manufactured home park",
        "X(3)",
        *RUN,
    ]
    seen = census("\n".join(lines), doc="d.txt")
    assert seen.reconciled
    assert {b.mark for b in seen.bodies} == {"1", "2", "3"}


def test_and_the_sentence_that_spells_a_number_is_still_not_a_marker() -> None:
    """Why the space is bought by the whole line instead of by the pattern.
    Relaxing the marker itself admits thirty-three of these across twelve
    documents, every one of them a spelled-out dimension."""
    lines = ["The lot must have a width of at least twenty (20)", "feet."]
    assert census("\n".join(lines), doc="d.txt").markers == ()


# --- the same block printed once per column --------------------------------


def test_a_notes_block_repeated_across_a_colspan_is_read_once() -> None:
    """Fairview's extraction prints the six notes seven times, once per zone
    column. Counted as written they are seven blocks and thirty-six bodies,
    thirty of which nothing points at -- a document that reports itself
    unreconciled for having answered its markers too many times."""
    lines = TABLE + RUN + RUN + RUN
    seen = census("\n".join(lines), doc="d.txt")
    assert len(seen.blocks) == 1
    assert [b.mark for b in seen.bodies] == ["1", "2", "3"]
    assert seen.unmarked == ()


# --- what the chapter says now --------------------------------------------


def test_the_residential_chapter_reconciles(chapter) -> None:
    """Thirty-four orphan markers and six unanswered bodies, before. Two
    blocks -- the use table's six notes and the dimensional table's one -- and
    nothing left over, after."""
    assert chapter.unbodied == ()
    assert chapter.unmarked == ()
    use_table = next(b for b in chapter.blocks if b.head == 181)
    assert [b.mark for b in use_table.bodies] == [str(n) for n in range(1, 7)]


def test_the_note_that_sends_a_quadplex_to_its_design_standards(chapter) -> None:
    """Note (5) is the pod's, and the only one of the six that is. It reaches
    FMC 19.30.040.B, which requires a main entrance within eight feet of the
    longest street-facing wall and facing the street -- a constraint on the
    door, not on the long axis."""
    fifth = next(b for b in chapter.bodies if b.mark == "5" and b.line == 185)
    assert "19.30.040" in fifth.text

    ruled = {(row.doc, row.line): row for row in dispositions(FAIRVIEW)}
    ruling = ruled[(DOC, 185)]
    assert ruling.state == "encoded"
    assert "entrance_only" in ruling.encoded_as

    rules = RuleSet(load_rules())
    for zone in ("R-6", "R-7.5", "R-10", "RM"):
        resolved = rules.resolve(FAIRVIEW, zone)
        assert resolved.values["orientation_constraint"].value == "entrance_only"


def test_the_two_notes_the_glossary_keeps_off_the_pod(store: ProvenanceStore) -> None:
    """Notes (2) and (4) point at sections that carry real numbers -- a 10
    percent common open space floor on multi-unit housing, and the townhouse
    design standards. Reading Fairview's definitions is the whole difference
    between dismissing them and encoding a requirement the pod does not owe."""
    glossary = store.load(f"{FAIRVIEW}/19.13.definitions.txt").text.splitlines()
    assert "five or more dwelling units" in glossary[382]  # multi-unit dwelling
    assert "four dwelling units on a lot or parcel" in glossary[464]  # quadplex
    assert "located on an individual lot or parcel" in glossary[572]  # townhouse

    ruled = {row.line: row for row in dispositions(FAIRVIEW)}
    assert "five or more" in ruled[182].reason
    assert "individual lot" in ruled[184].reason


def test_and_nothing_the_chapter_encodes_is_left_blocked() -> None:
    """Six notes captured is six notes that hold their table's values back
    until somebody rules them. Quadplex_allowed in four zones was blocked the
    moment the block became readable, which is the gate working."""
    assert not [row for row in qualified() if row.blocking]
    assert not [row for row in dispositions(FAIRVIEW) if row.state == "unread"]


def test_and_not_one_encoded_number_moved() -> None:
    """The chapter's dimensional standards were read and encoded long before
    its use-table notes could be. Nothing in the six touches them."""
    rules = RuleSet(load_rules())
    r6 = rules.resolve(FAIRVIEW, "R-6").values
    assert r6["min_lot_sqft"].value == 6000
    assert r6["setback_front_ft"].value == 10
    assert r6["max_height_ft"].value == 35
    assert r6["quadplex_allowed"].value is True
    assert rules.resolve(FAIRVIEW, "RM").values["min_density_du_per_acre"].value == 14
    assert rules.resolve(FAIRVIEW, "R/MH").values["quadplex_allowed"].value is False
