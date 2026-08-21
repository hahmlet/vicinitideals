"""The markers that were never there, and the page date that always was.

Portland's Chapter 33.130 reported twenty footnote markers nobody had written
a note for. Nineteen of them were the sentence "landscaped to at least the L1
standard" -- a cross-reference to Chapter 33.248, read as the permission code
"L" with footnote 1 on it. A ledger of invented orphans is worse than useless:
it hides the one real marker underneath them, and it asks somebody to go
looking for nineteen notes that were never written.

The same argument that keeps "A", "N" and "S" out of the permission vocabulary,
made one level down. "L" is a real code and "L1" is a real cell; what says this
is not one is the word in front of it.

Underneath that, a second thing: `RUNNING_HEADER` has carried a literal
backspace character where a word boundary was meant since the declared-note
reader was written, which made its date branch dead. Portland breaks a page in
the middle of a numbered limitation and stamps the break "3/1/25   Employment
and Industrial Zones", and four of its limitations had that stamp sitting in
the middle of the sentence. A ruling is a statement about a sentence, and it
should be a statement about the sentence the codifier wrote.
"""

from __future__ import annotations

import pytest

from flats.encode.footnotes import LANDSCAPE_LEVEL, RUNNING_HEADER, census
from flats.encode.qualified import qualified
from flats.provenance.store import ProvenanceStore

pytestmark = pytest.mark.unit

PORTLAND = "or/multnomah/portland"


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


def _chapter(store: ProvenanceStore, number: str):
    doc = f"{PORTLAND}/{number}.txt"
    return census(store.load(doc).text, layer=PORTLAND, doc=doc)


# --- the code that is not a code -------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "landscaped to at least the L1 standard. Vehicle access is not allowed",
        "must be landscaped to at least the L3 standard for a distance of up to",
        "landscaped to at least the L1 level and/or hard-surfaced for use by",
        "at least the L3 or F2 standards of Chapter 33.248, Landscaping",
        "10 ft. @ L3",
        "5 ft. / L4, or 10",
    ],
)
def test_a_landscaping_standard_is_not_a_marker(line: str) -> None:
    """Six ways the corpus writes it. Every one is a reference to the planting
    standard in another chapter."""
    seen = census("\n".join([line, "Notes:", "1. Something else entirely."]), doc="d.txt")
    assert not [m for m in seen.markers if m.kind == "cell"]


def test_but_a_permission_code_still_is_one() -> None:
    """The refusal is bought by the context, not by the letter. A use-table row
    of codes reads exactly as it did."""
    seen = census(
        "\n".join(
            [
                "Household Living           P          L1         CU         N",
                "Notes:",
                "1. Permitted only above the ground floor.",
            ]
        ),
        doc="d.txt",
    )
    assert [(m.mark, m.kind) for m in seen.markers] == [("1", "cell")]


def test_the_pattern_itself() -> None:
    """What the refusal keys off: the preposition, the slash, the at-sign, or
    the word "standard" behind it."""
    assert LANDSCAPE_LEVEL.search("to the L1 standard") is not None
    assert LANDSCAPE_LEVEL.search("25 ft. / L3 or") is not None
    assert LANDSCAPE_LEVEL.search("10 ft. @ L3") is not None
    assert LANDSCAPE_LEVEL.search("L2 levels of screening") is not None
    assert LANDSCAPE_LEVEL.search("P   L1   CU   N") is None


def test_the_chapter_that_reported_twenty_orphans(store: ProvenanceStore) -> None:
    """One left, and it is honest: a table cell that is nothing but "L3",
    printed under a row labelled Landscape Buffer, with no word in front of it
    to say so."""
    got = _chapter(store, "33.130")
    assert len(got.unbodied) == 1
    assert got.unbodied[0].line == 662


def test_and_the_single_dwelling_chapter_now_reconciles(store: ProvenanceStore) -> None:
    """33.110's only unanswered marker was the same thing."""
    assert _chapter(store, "33.110").unbodied == ()


# --- the page stamp inside a sentence --------------------------------------


def test_a_page_date_ends_a_line_of_note_text() -> None:
    """The branch that reads it has been dead since it was written: a heredoc
    left a backspace character where the word boundary was meant, and nothing
    can follow a backspace."""
    assert RUNNING_HEADER.match("3/1/25")
    assert RUNNING_HEADER.match("10/1/24        Single-Dwelling Zones")
    assert not RUNNING_HEADER.match("3/1/25the rest of a sentence")


def test_the_limitation_that_had_a_page_stamp_in_the_middle_of_it(
    store: ProvenanceStore,
) -> None:
    """33.140's limitation 1 is the one sentence in the chapter that lets
    dwellings into an industrial zone -- a hotel conversion where the units are
    affordable at 60 percent of median income. It read with "3/1/25 Employment
    and Industrial Zones" wedged into the middle of that condition."""
    got = _chapter(store, "33.140")
    first = next(b for b in got.bodies if b.line == 181)
    assert "converted dwelling units are affordable" in first.text
    assert "3/1/25" not in first.text
    assert "Employment and Industrial Zones" not in first.text


def test_no_ruling_was_left_pointing_at_the_old_wording() -> None:
    """Five rulings were written against a sentence with furniture in it. A
    disposition binds to the words, so all five evaporated and all five were
    re-digested against what the codifier actually wrote."""
    assert not [row for row in qualified() if row.blocking]
