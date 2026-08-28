"""A note that wraps onto a citation is not the next section starting.

Gresham runs note 3 of Table 4.1415A onto a second line -- "Section 10.1520 of
the Community Development Code." -- and the block reader took the word
"Section" at the start of a line for the next section of the code. Note 3
stopped mid-sentence at "compliance with", and notes 4 through 7 were never
captured at all. Among them is the one that attaches Pleasant Valley's building
height transition standards to the HDR-PV height row.

The floor still has to exist: an unrecognised line is read as the continuation
of the previous note, so without something explicit a block runs into whatever
follows it. What separates the two is the word after the number. A heading
reads "Section 4.1416 Building Height and Height Transition Standards", or
"Section 845, Triplexes"; a wrapped citation reads "of", "in", "and".
"""

from __future__ import annotations

import pytest

from flats.encode.footnotes import ENDS_BLOCK, census
from flats.encode.dispositions import notes as dispositions
from flats.encode.qualified import qualified
from flats.provenance.store import ProvenanceStore

pytestmark = pytest.mark.unit

GRESHAM = "or/multnomah/gresham"
DOC = f"{GRESHAM}/4.1400.pleasant-valley.txt"


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


@pytest.fixture(scope="module")
def pleasant_valley(store: ProvenanceStore):
    return census(store.load(DOC).text, layer=GRESHAM, doc=DOC)


# --- what the word after the number decides ---------------------------------


def test_a_heading_still_ends_a_block() -> None:
    assert ENDS_BLOCK.match("Section 4.1416 Building Height and Height Transition")
    assert ENDS_BLOCK.match("Section 845, Triplexes, Quadplexes, Townhouses")
    assert ENDS_BLOCK.match("Chapter 19.600 Off-Street Parking and Loading")
    assert ENDS_BLOCK.match("Section 9.0100")


def test_but_a_wrapped_citation_does_not() -> None:
    assert not ENDS_BLOCK.match("Section 10.1520 of the Community Development Code.")
    assert not ENDS_BLOCK.match("Section 33.920 and the standards it states")
    assert not ENDS_BLOCK.match("Chapter 27 in the Oregon Fire Code")


def test_the_note_that_wraps_keeps_its_second_line() -> None:
    seen = census(
        "\n".join(
            [
                "Table 4.1415A Notes",
                "1. Minimum net density does not apply to affordable housing.",
                "2. A reduction in the minimum street frontage may be approved"
                " when the applicant can document compliance with",
                "Section 10.1520 of the Community Development Code.",
                "3. A height bonus applies to affordable housing development.",
            ]
        ),
        doc="d.txt",
    )
    assert [b.mark for b in seen.bodies] == ["1", "2", "3"]
    second = next(b for b in seen.bodies if b.mark == "2")
    assert "Section 10.1520 of the Community Development Code." in second.text


# --- what Pleasant Valley says now ------------------------------------------


def test_the_plan_district_table_answers_all_seven(pleasant_valley) -> None:
    # 349 until the 2026-08-27 republication put two footnote markers on lines
    # of their own above this table and pushed everything below down two.
    block = next(b for b in pleasant_valley.blocks if b.head == 351)
    assert [b.mark for b in block.bodies] == ["1", "2", "3", "4", "5", "6", "7"]
    assert pleasant_valley.unbodied == ()


def test_the_height_transition_note_is_readable_at_last(pleasant_valley) -> None:
    """Note 5 was argued out in the layer's own prose when HDR-PV was encoded,
    from the document rather than from a body, because there was no body. It
    still cannot bind -- 4.1416(B) allows 35 feet at the minimum setback and a
    foot of height per additional foot, and the pod is 26 -- but the ruling now
    points at the sentence instead of at a line the census could not see."""
    # 353 until Gresham republished the PDF on 2026-08-27; two markers landed on
    # their own lines above this one and pushed it down two. Moved by hand --
    # `--repoint` migrates citations, and an assertion is not a citation.
    fifth = next(b for b in pleasant_valley.bodies if b.line == 357)
    assert "Building height transition standards apply" in fifth.text
    assert "LDR -PV sub-district" in fifth.text
    ruled = {row.quote: row for row in dispositions(GRESHAM)}
    assert ruled[f"{DOC}#L357"].state == "dismissed"


def test_every_new_note_is_ruled_and_none_blocks() -> None:
    ruled = {row.quote: row for row in dispositions(GRESHAM)}
    # 350, 353, 354 and 356 until the 2026-08-27 republication moved them.
    for line in (354, 357, 358, 360):
        assert ruled[f"{DOC}#L{line}"].state == "dismissed"
    assert not [row for row in qualified() if row.blocking]
