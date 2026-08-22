"""The cross-reference that reported a footnote nobody wrote.

A codifier pointing at its own subsection writes a chain of brackets::

    ... and (B)(1)
    ... not subject to the limits in Subsection (C)(2) and (C)(3) below.

`PAREN_LABEL_MARKER` reads a bracketed number welded to the end of a cell as a
marker, which is the right reading for Wood Village's "Minimum Lot Size(1)".
On a chain it reads the last bracket as a marker welded to the bracket before
it, and `PAREN_CITATION` cannot subtract the chain because it is anchored to a
dotted section number that a bare subsection does not have.

Four lines in the corpus end that way, and every one of them was an orphan --
a marker asking for a note that was never written. Two of the four are the
only fault in their document, so subtracting the chain reconciles Gresham's
affordable housing chapter and Multnomah's community forest chapter outright.
"""

from __future__ import annotations

import pytest

from flats.encode.footnotes import PAREN_SUBSECTION, census
from flats.provenance.store import ProvenanceStore

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


# --- what the chain is -------------------------------------------------------


def test_the_shapes_a_codifier_writes() -> None:
    assert PAREN_SUBSECTION.search("and (B)(1)")
    assert PAREN_SUBSECTION.search("in Subsection (C)(2) and (C)(3) below.")
    assert PAREN_SUBSECTION.search("Standards of Section 7.0512          (B)(1)")
    assert PAREN_SUBSECTION.search("845.03(B)(2)(d)")


def test_but_the_brackets_have_to_touch() -> None:
    """Fairview writes "X(CU) (1)" with a space and means a conditional use
    subject to note 1; `LONE_PAREN_CELL` reads it. A codifier writing a
    subsection chain does not put a space in the middle of one."""
    assert not PAREN_SUBSECTION.search("X(CU) (1)")
    assert not PAREN_SUBSECTION.search("Minimum Lot Size(1)")
    assert not PAREN_SUBSECTION.search("None(2)")


# --- what it costs and what it clears ----------------------------------------


def test_the_two_documents_it_reconciles_outright(store: ProvenanceStore) -> None:
    """Each held exactly one fault: a marker on a cross-reference, in a chapter
    with no notes block at all."""
    for doc in (
        "or/multnomah/gresham/10.1700.affordable.txt",
        "or/multnomah/_unincorporated/39.cfu.txt",
    ):
        got = census(store.load(doc).text, doc=doc)
        assert got.blocks == ()
        assert got.markers == ()
        assert got.reconciled, doc


def test_and_the_two_orphans_it_clears_from_the_middle_housing_chapter(
    store: ProvenanceStore,
) -> None:
    """"not subject to the limits in Subsection (C)(2) and (C)(3) below" asked
    for notes 2 and 3. The block states 1, 3 and 4, so note 2 was an orphan
    outright and note 3 was answered by a sentence that is not pointing at it.

    Note 3 therefore joins note 4 as an unmarked body, which is the honest
    report: the only line in the chapter that carried its number was a
    cross-reference. One marker is left in the document, the label at L821,
    and it answers note 1."""
    doc = "or/multnomah/gresham/7.0400.middle-housing-design.txt"
    got = census(store.load(doc).text, doc=doc)
    assert got.unbodied == ()
    assert [(m.line, m.mark) for m in got.markers] == [(821, "1")]
    assert [(b.line, b.mark) for b in got.unmarked] == [(832, "3"), (850, "4")]


def test_no_real_marker_pays_for_it(store: ProvenanceStore) -> None:
    """Four lines in the corpus change and all four are cross-references. The
    fourth is Gresham's Rockwood chapter, where extraction put a column gap
    between a section number and its subsection -- "Standards of Section
    7.0512          (B)(1)" -- so `PAREN_CITATION` could not span it either.
    Its notes block was reconciled before and is reconciled after."""
    doc = "or/multnomah/gresham/7.0500.rockwood-design.txt"
    got = census(store.load(doc).text, doc=doc)
    assert [(m.line, m.mark) for m in got.markers] == [
        (2197, "1"),
        (3642, "1"),
        (3643, "2"),
        (3647, "3"),
        (3654, "3"),
    ]
    assert got.reconciled
