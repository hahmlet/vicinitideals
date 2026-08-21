"""The notes that fell down the gap between two pages.

Troutdale's Chapter 3 is a scanned code, and its dimensional tables carry
fourteen notes. Four of them make a setback depend on where the driveway is --
front yard 20 feet instead of 10 if access is taken from the front, rear yard 0
feet with an alley and 10 without -- which is exactly the shape of qualifier a
screen must not read past. Not one of the fourteen was pointed at by anything,
and three of them were never captured at all.

Three separate failures, none of which reported itself as a failure:

* the markers are **spelled out**. Troutdale prints "10 or 20" in the cell and
  "see note 2" on the line under it. No bracket, no superscript, nothing the
  marker rules recognise -- so the document reported fourteen bodies and zero
  markers, and a document with no markers has nothing to reconcile against.
* the block **ends at the page frame**. Notes 1 and 2 print at the foot of one
  page and notes 3, 4 and 5 at the head of the next, with the running header
  "3.130     TROUTDALE DEVELOPMENT CODE" between them -- which is shaped
  exactly like a section heading, and ending a block at a section heading is
  right everywhere else.
* the note **wraps onto "(20 feet)."**, which an unbalanced bracket rule reads
  as note 20. Twenty is above every mark the list has reached, so it is
  accepted as the next note, and the two real notes below it are then refused
  for restarting the numbering.
"""

from __future__ import annotations

import pytest

from flats.encode.dispositions import notes as dispositions
from flats.encode.footnotes import BLOCK_NOTE, census
from flats.encode.qualified import qualified
from flats.provenance.store import ProvenanceStore

pytestmark = pytest.mark.unit

TROUTDALE = "or/multnomah/troutdale"
DOC = f"{TROUTDALE}/3.zoning-districts.txt"


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


@pytest.fixture(scope="module")
def chapter(store: ProvenanceStore):
    return census(store.load(DOC).text, layer=TROUTDALE, doc=DOC)


# --- a marker with no bracket ---------------------------------------------


TABLE = [
    "Dimensional Standard              LDR-1        LDR-2",
    "   Front yard                          10 or 20      10 or 20",
    "                                       see note 1    see note 1",
    "   Rear yard                                 15            15",
    "Table Notes",
    "1. Front yard setback is 20 feet if driveway access is taken from front yard.",
]


def test_a_marker_the_codifier_spelled_out() -> None:
    """"see note 1" is as much a marker as "[1]" and needs no layout to prove
    it -- there is nothing else the phrase can mean. Read anywhere on a line,
    like the bracket, and counted once per line like every other kind: two
    columns carrying the same note is one occurrence of it here."""
    seen = census("\n".join(TABLE), doc="d.txt")
    assert [m.mark for m in seen.markers] == ["1"]
    assert seen.reconciled


# --- a block that crosses a page ------------------------------------------


FRAME = [
    "                              TDC3-7",
    "3.130                         TROUTDALE DEVELOPMENT CODE",
    "",
    "Dimensional Standard              LDR-1        LDR-2",
]


def test_a_notes_block_continues_past_the_page_frame() -> None:
    """The stamp, the running header and the table's reprinted column header.
    Ending at any of the three loses every note below the break."""
    lines = [
        *TABLE[:3],
        "   Rear yard                           15 or 20      15 or 20",
        "                                       see note 2    see note 2",
        "Table Notes",
        "1. Front yard setback is 20 feet if driveway access is taken from front yard.",
        *FRAME,
        "2. Rear yard setback is 20 feet if driveway access is taken from a side yard.",
    ]
    seen = census("\n".join(lines), doc="d.txt")
    assert [b.mark for b in seen.bodies] == ["1", "2"]
    assert seen.reconciled


def test_and_the_reprinted_header_is_not_note_text() -> None:
    """A note that swallows the column header reads back as a sentence with a
    table in the middle of it, and its digest no longer matches the ruling
    somebody wrote against the sentence."""
    lines = [
        *TABLE,
        *FRAME,
        "2. Rear yard setback is 20 feet if driveway access is taken from a side yard.",
    ]
    seen = census("\n".join(lines), doc="d.txt")
    assert seen.bodies[0].text.endswith("taken from front yard.")


def test_but_an_all_capitals_heading_still_ends_the_block() -> None:
    """Half the running header is shaped exactly like a real section heading:
    Gresham writes "4.0130      RESIDENTIAL LAND USE DISTRICT STANDARDS" and
    means it. What tells them apart is the page stamp -- a frame has one over
    it, a heading has a blank line."""
    lines = [
        *TABLE,
        "",
        "4.0130                        RESIDENTIAL LAND USE DISTRICT STANDARDS",
        "",
        "The development standards listed in Table 4.0130 are applicable to all",
        "development within the Residential Land Use Districts.",
    ]
    seen = census("\n".join(lines), doc="d.txt")
    assert seen.bodies[0].text.endswith("taken from front yard.")


# --- a bracket that does not close ----------------------------------------


def test_a_wrapped_line_is_not_a_note_just_for_starting_with_a_number() -> None:
    """"(20 feet)." is the tail of a sentence. Read as note 20 it is above
    every mark the list has reached, so it is accepted -- and then notes 4 and
    5 are refused for restarting the numbering below it."""
    assert BLOCK_NOTE.match("(4) Townhomes are exempt").group("n") == "4"
    assert BLOCK_NOTE.match("[3] Additional FAR").group("n") == "3"
    assert BLOCK_NOTE.match("2. Zero lot line dwellings").group("n") == "2"
    assert BLOCK_NOTE.match("9 Except for middle housing") is not None
    assert BLOCK_NOTE.match("(20 feet).") is None


# --- what the chapter says now --------------------------------------------


def test_the_zoning_chapter_reconciles(chapter) -> None:
    """Fourteen bodies and no markers at all, before -- which the census could
    only report as fourteen notes nobody points at. Seventeen and seventeen,
    after, and nothing left over either way."""
    assert len(chapter.bodies) == 17
    assert len(chapter.markers) == 17
    assert chapter.unbodied == ()
    assert chapter.unmarked == ()


def test_the_three_notes_that_were_never_captured(chapter) -> None:
    """Notes 3, 4 and 5 of the first dimensional table, printed after the page
    break. Two of them attach to columns this layer encodes."""
    below = {b.line: b.text for b in chapter.bodies if 315 <= b.line <= 318}
    assert "Rear yard setbacks for duplexes are 15 feet" in below[315]
    assert "(20 feet)" in below[315]
    assert "20 feet if driveway access is taken from a side yard" in below[317]
    assert "Street side yard setback is 20 feet" in below[318]


def test_every_note_in_the_chapter_is_ruled_and_none_blocks() -> None:
    """The driveway-conditional setbacks all belong to Table 3.130.A, which is
    single-family and duplex. The pod is a quadplex and its numbers come from
    3.130.B, whose encoded columns print bare figures with no marker on
    them -- which is the reason, and it is only writable because the notes are
    captured."""
    ruled = list(dispositions(TROUTDALE))
    assert not [row for row in ruled if row.state == "unread"]
    assert not [row for row in qualified() if row.blocking]
