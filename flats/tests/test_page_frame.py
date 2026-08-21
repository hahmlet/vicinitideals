"""Portland's running footer, which was not furniture to this reader.

Extraction lays the footer out as three lines, two of them carrying two halves
across the gutter, and the order swaps from one side of the spread to the
other::

    110-        10
    Title 33, Planning and Zoning        Chapter 33.110
    1/1/25        Single-Dwelling Zones

The chapter line did the loud damage. "Chapter 33.130" followed by a capital
is shaped exactly like the next chapter starting, so the block reader took it
for one, and Table 120-3's notes list ended at its page break -- notes [4] and
[5] became a block of their own whose region covered nothing, which is why two
markers asking for [5] were orphans and both bodies were unmarked.

The stamp did the quieter kind, arriving as more of the note above it. Five
notes in five chapters carried a page footer inside their bodies, so the digest
of a note recorded the page it happened to be printed on.
"""

from __future__ import annotations

import pytest

from flats.encode.footnotes import TIGHT_STAMP, _near_frame, _page_frame, census
from flats.encode.dispositions import notes as dispositions
from flats.encode.qualified import qualified
from flats.provenance.store import ProvenanceStore

pytestmark = pytest.mark.unit

PORTLAND = "or/multnomah/portland"


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


def _chapter(store: ProvenanceStore, name: str):
    doc = f"{PORTLAND}/{name}.txt"
    return census(store.load(doc).text, layer=PORTLAND, doc=doc)


# --- what the frame looks like ----------------------------------------------


def test_the_chapter_line_in_either_order() -> None:
    assert _page_frame("Title 33, Planning and Zoning        Chapter 33.110")
    assert _page_frame("Chapter 33.130        Title 33, Planning and Zoning")


def test_the_date_line_in_either_order_and_however_many_cells() -> None:
    assert _page_frame("1/1/25        Single-Dwelling Zones")
    assert _page_frame("Multi-Dwelling Zones        3/1/25")
    assert _page_frame("Commercial/Mixed Use   Zones   1/1/25")


def test_but_a_note_that_cites_a_chapter_is_not_a_footer() -> None:
    """The pairing across the gutter is what makes the frame safe to step
    over. A note may well cite a chapter, and one may end on a date; neither
    writes both halves with a column between them."""
    assert not _page_frame("stated in Chapter 33.266, Parking, Loading, and Transportation")
    assert not _page_frame("Chapter 33.110")
    assert not _page_frame("Title 33, Planning and Zoning")


def test_the_closed_up_stamp_needs_the_rest_of_the_frame() -> None:
    """"110-8" is shaped exactly like an ordinance number, and Milwaukie
    prints "45-90" and "10-301" alone on a line meaning the ordinance that
    added the row above. So the tight form is only believed beside the rest of
    the footer."""
    assert TIGHT_STAMP.match("110-8")
    assert TIGHT_STAMP.match("45-90")
    framed = [
        "[3] Additional FAR and height may be allowed. See 33.110.265.F.",
        "110-8",
        "Title 33, Planning and Zoning        Chapter 33.110",
    ]
    assert _near_frame(framed, 1)
    alone = ["Minimum lot area    5,000 sf", "45-90", "Maximum height    35 ft."]
    assert not _near_frame(alone, 1)


# --- what the chapters say now ----------------------------------------------


def test_the_institutional_table_keeps_its_notes_across_the_page_break(
    store: ProvenanceStore,
) -> None:
    got = _chapter(store, "33.120")
    block = next(b for b in got.blocks if b.head == 1936)
    assert [(b.line, b.mark) for b in block.bodies] == [
        (1937, "1"),
        (1939, "2"),
        (1942, "3"),
        (1949, "4"),
        (1951, "5"),
    ]
    assert got.unbodied == ()


def test_five_notes_stop_carrying_the_page_they_were_printed_on(
    store: ProvenanceStore,
) -> None:
    def body(name: str, line: int) -> str:
        return next(b for b in _chapter(store, name).bodies if b.line == line).text

    assert body("33.110", 396).endswith("public agency for right -of-way.")
    assert body("33.110", 477).endswith("See 33.110.265.F.")
    assert body("33.120", 1942).endswith("comply with the setback standard.")
    assert body("33.140", 631).endswith("See 33.140.215.B.")
    assert body("33.150", 574).endswith("there is no minimum setback.")


def test_and_one_of_them_now_runs_on_into_a_caption(store: ProvenanceStore) -> None:
    """33.130's one footnote is the last in its list, and nothing on the far
    side of the page break says the list is over, so it picks up the caption
    of the illustration below. Ending a block at a page break instead is the
    obvious cure and it is wrong: it cost sixteen bodies in Gresham's downtown
    chapter and three in Troutdale, where lists carry on after the break
    without renumbering. Recorded, not fixed."""
    text = next(b for b in _chapter(store, "33.130").bodies if b.line == 668).text
    assert "1 unit per 2,500 square feet of site area." in text
    assert "Example Illustration" in text


def test_every_note_the_frame_was_hiding_is_ruled_and_none_blocks() -> None:
    ruled = {row.quote: row for row in dispositions(PORTLAND)}
    assert ruled[f"{PORTLAND}/33.120.txt#L1951"].state == "dismissed"
    assert ruled[f"{PORTLAND}/33.266.txt#L540"].state == "dismissed"
    assert not [row for row in qualified() if row.blocking]
