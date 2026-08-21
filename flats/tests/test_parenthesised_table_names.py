"""A table that names itself with brackets still announces its notes.

Gresham writes "Table 4.1152(B)(8) Notes:" and "Table 4.1220(A) Notes:", and
the identifier this reader allowed in front of the word had no brackets in it,
so the heading was not a heading. Worse where the caption cell spans the grid:
the extraction puts "Table 4.1220(" at one end of a line and "A) Notes:" at the
other, with twenty spaces of column between them.

Thirteen blocks were invisible -- ten in the Civic Neighborhood chapter, one in
Downtown, one in Rockwood and one in Springwater -- and every marker on the
tables above them was an orphan with nothing to point at. A document that
cannot see a notes block reports itself clean, which is the whole danger.
"""

from __future__ import annotations

import pytest

from flats.encode.footnotes import NOTES_HEAD, census
from flats.encode.dispositions import notes as dispositions
from flats.encode.qualified import qualified
from flats.provenance.store import ProvenanceStore

pytestmark = pytest.mark.unit

GRESHAM = "or/multnomah/gresham"
CN = f"{GRESHAM}/4.1200.civic-neighborhood.txt"
DOWNTOWN = f"{GRESHAM}/4.1100.downtown.txt"
ROCKWOOD = f"{GRESHAM}/7.0500.rockwood-design.txt"
SPRINGWATER = f"{GRESHAM}/4.1500.springwater.txt"


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


def _seen(store: ProvenanceStore, doc: str):
    return census(store.load(doc).text, layer=GRESHAM, doc=doc)


@pytest.fixture(scope="module")
def civic(store: ProvenanceStore):
    return _seen(store, CN)


# --- what a table is allowed to call itself ---------------------------------


def test_the_bracketed_identifier_is_a_notes_head() -> None:
    assert NOTES_HEAD.match("Table 4.1152(B)(8) Notes:")
    assert NOTES_HEAD.match("Table 4.1220(A) Notes:")
    assert NOTES_HEAD.match("Table 4.1508 (continued) Notes:")


def test_and_so_is_the_column_the_extraction_puts_inside_it() -> None:
    """A caption cell spanning the grid is where the whitespace comes from."""
    assert NOTES_HEAD.match("Table 4.1220(                    A) Notes:")
    assert NOTES_HEAD.match("Table 4.1230(   B) NOTES:")


def test_the_plain_shapes_are_untouched() -> None:
    assert NOTES_HEAD.match("Notes:")
    assert NOTES_HEAD.match("Table 4.0130 Notes:")
    assert NOTES_HEAD.match("NOTES:  NOTES:")


def test_a_sentence_that_merely_mentions_notes_is_not_a_head() -> None:
    assert not NOTES_HEAD.match("See Table 4.1152(B)(8) Notes: below for detail.")
    assert not NOTES_HEAD.match("Table 4.1220(A) Residential Uses")


# --- what the four documents say now ----------------------------------------


def test_civic_neighborhood_reads_ten_blocks_instead_of_one(civic) -> None:
    """Nine of the ten were the split caption; the tenth is the material
    palette in 4.1152(B)(8). Between them they carry thirty-one notes."""
    assert [b.head for b in civic.blocks] == [
        209,
        225,
        246,
        264,
        281,
        298,
        331,
        382,
        2887,
        4495,
    ]
    assert len(civic.bodies) == 31


def test_the_use_table_notes_are_readable(civic) -> None:
    first = next(b for b in civic.bodies if b.line == 210)
    assert "temporary health hardship" in first.text.lower()
    third = next(b for b in civic.bodies if b.line == 212)
    # The PDF sets "Affordable" with an ff ligature, so match past it.
    assert "ordable housing development is permitted" in third.text.lower()


def test_the_setback_note_that_would_bind_if_a_setback_were_encoded(civic) -> None:
    """Note 2 of Table 4.1230(B) defines side setback as the interior side and
    not the common wall. This layer encodes no Civic Neighborhood setback --
    the Quadplex row refuses the building first -- so the note is ruled read
    rather than encoded. It is the one to come back to if that changes."""
    note = next(b for b in civic.bodies if b.line == 384)
    assert "common wall" in note.text


def test_downtown_and_rockwood_reconcile(store: ProvenanceStore) -> None:
    """Both were reporting orphans with no block in sight: the material
    palettes name themselves 4.1152(B)(8) and 7.0512(B)(7)."""
    assert _seen(store, DOWNTOWN).unbodied == ()
    assert _seen(store, ROCKWOOD).unbodied == ()


def test_springwaters_continued_table_answers_its_own_marker(
    store: ProvenanceStore,
) -> None:
    """"Table 4.1508 (continued) Notes:" carries note 5, whose marker is the
    glued "10 ft.5" in the THR-SW row. LDR-SW's row above it has no such
    marker, which is why the note is dismissed rather than encoded."""
    seen = _seen(store, SPRINGWATER)
    assert 359 in [b.head for b in seen.blocks]
    fifth = next(b for b in seen.bodies if b.line == 360)
    assert "70 ft" in fifth.text
    assert seen.unbodied == ()


def test_the_one_orphan_left_in_civic_neighborhood_is_a_diagram_reference(
    civic,
) -> None:
    """Line 657 reads "(see Diagrams C1 and C2 for example)" inside the Wallula
    Avenue street standards, and a letter glued to a digit is one of the shapes
    a table cell marks a footnote with. The list it sits in prints no notes
    head at all, so there is nothing for it to point at. Recorded, not fixed:
    the fix belongs to the marker patterns, not to this one."""
    assert [(m.line, m.mark) for m in civic.unbodied] == [(657, "2")]


# --- the gate ---------------------------------------------------------------


def test_every_newly_visible_note_is_ruled_and_none_blocks() -> None:
    ruled = {row.quote: row for row in dispositions(GRESHAM)}
    for line in (210, 211, 212, 226, 247, 333, 341, 384, 389, 397, 4497, 4501):
        assert ruled[f"{CN}#L{line}"].state == "dismissed"
    for line in (4474, 4476):
        assert ruled[f"{DOWNTOWN}#L{line}"].state == "dismissed"
    for line in (3666, 3669):
        assert ruled[f"{ROCKWOOD}#L{line}"].state == "dismissed"
    assert ruled[f"{SPRINGWATER}#L360"].state == "dismissed"
    assert not [row for row in qualified() if row.blocking]


def test_one_ruling_covers_a_sentence_printed_twice(civic) -> None:
    """Rulings bind by digest. The Burnside/Division limitation is printed
    under Table 4.1220(B) and again under 4.1220(D); the stucco definition is
    printed in all three material palettes. Each is ruled once."""
    from flats.encode.dispositions import digest

    burnside = {b.line: digest(b.text) for b in civic.bodies if b.line in (227, 265)}
    assert len(set(burnside.values())) == 1
