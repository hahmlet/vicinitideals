"""One sentence of scope, and twenty-four notes behind it.

Gresham's Downtown use table answers itself the ordinary way -- "Table 4.1120
Notes:" and then a numbered list -- except that it puts a line of scope in
between: "The following describe limitations on use categories marked as
limited or special use review in Table 4.1120." The block reader demanded that
the first line under a heading be numbered, so it walked away from the whole
list, and Table 4.1120 reported twenty-four markers with nothing behind them.

That rule earns its strictness. A "Notes:" heading in this corpus sits over a
legend far more often than over notes: Portland's "The use categories are
described in Chapter 33.920" and Milwaukie's "P = Permitted" are both headed
that way and neither announces a footnote. So the lead-in has to name the table
AND announce a list, once, with note 1 behind it.

Two smaller things fall out of the same document. Gresham stamps its pages
"[4.1100]" and the page number across the gutter, and the running header under
that stamp repeats the chapter -- which is exactly how it can be told from a
real section heading three lines under the same stamp, "[4.1500]" then "4.1508
DEVELOPMENT STANDARDS TABLE". And the table's markers sit in the middle of the
label, not at the end of it: "Maximum Height1,2,3,4 (feet)".
"""

from __future__ import annotations

import pytest

from flats.encode.footnotes import (
    FURNITURE,
    LABEL_MARKER,
    NOTES_LEAD,
    census,
)
from flats.encode.dispositions import notes as dispositions
from flats.encode.qualified import qualified
from flats.provenance.store import ProvenanceStore

pytestmark = pytest.mark.unit

GRESHAM = "or/multnomah/gresham"
DOC = f"{GRESHAM}/4.1100.downtown.txt"


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


@pytest.fixture(scope="module")
def downtown(store: ProvenanceStore):
    return census(store.load(DOC).text, layer=GRESHAM, doc=DOC)


# --- the line of scope -----------------------------------------------------


def test_a_heading_may_say_what_it_covers_before_it_numbers() -> None:
    seen = census(
        "\n".join(
            [
                "Quadplex        L1        NP",
                "Table 4.1120                              Notes:",
                "The following describe limitations on use categories marked as"
                " limited or special use review in Table 4.1120.",
                "1. Plexes are allowed provided density standards are met.",
            ]
        ),
        doc="d.txt",
    )
    assert [b.mark for b in seen.bodies] == ["1"]
    assert seen.reconciled


def test_but_a_legend_is_still_not_a_notes_block() -> None:
    """The shape this reader must keep refusing, in the two forms the corpus
    prints it: a key to the permission codes, and a bulleted description of
    what the table's categories mean."""
    legend = census(
        "\n".join(
            [
                "Notes:",
                "P       =       Permitted/allowed by right",
                "N       =       Not permitted.",
            ]
        ),
        doc="d.txt",
    )
    assert legend.bodies == ()

    described = census(
        "\n".join(
            [
                "Notes:",
                "•     The use categories are described in Chapter 33.920.",
                "•     Regulations that correspond to the bracketed numbers [ ]"
                " are stated in this section.",
            ]
        ),
        doc="d.txt",
    )
    assert described.bodies == ()


def test_the_lead_in_has_to_name_the_table() -> None:
    """Naming the table is what separates a sentence of scope from the first
    line of the prose a caption introduces."""
    assert NOTES_LEAD.search(
        "The following describe limitations on use categories marked as limited"
        " or special use review in Table 4.1120."
    )
    assert not NOTES_LEAD.search("The use categories are described in Chapter 33.920.")
    assert not NOTES_LEAD.search("Table 4.1120 lists the types of land uses.")


# --- the page frame, told apart by its own number --------------------------


def test_a_running_header_repeats_the_chapter_the_stamp_named() -> None:
    """"[4.1100]" then "4.1100 DOWNTOWN PLAN DESIGN DISTRICT" is furniture.
    Read as a section heading it ends the block, and notes 9 to 24 are lost."""
    seen = census(
        "\n".join(
            [
                "Table 4.1120     Notes:",
                "The following describe limitations in Table 4.1120.",
                "1. Golf courses are not permitted.",
                "",
                "                              [4.1100]              -9",
                "City of Gresham Development Code",
                "",
                "                    4.1100 DOWNTOWN PLAN DESIGN DISTRICT",
                "2. Schools are permitted without a Special Use Review.",
            ]
        ),
        doc="d.txt",
    )
    assert [b.mark for b in seen.bodies] == ["1", "2"]


def test_but_a_different_number_under_the_same_stamp_is_a_real_heading() -> None:
    """"[4.1500]" then "4.1508 DEVELOPMENT STANDARDS TABLE" is the next section
    starting. Reading it as furniture ran Springwater's last note on into the
    standards below it."""
    seen = census(
        "\n".join(
            [
                "Notes:",
                "1. No more than one cottage cluster per parent parcel.",
                "",
                "[4.1500]-7",
                "City of Gresham Development Code  (06/26)",
                "STANDARDS",
                "4.1508  DEVELOPMENT STANDARDS TABLE",
                "The development standards listed in Table 4.1508 apply.",
            ]
        ),
        doc="d.txt",
    )
    assert "DEVELOPMENT STANDARDS TABLE" not in seen.bodies[0].text


def test_a_publisher_line_split_from_its_date_is_still_furniture() -> None:
    """Extraction puts "City of Gresham Development Code" and "(06/2026)" on
    separate lines. Anchored whole, because a note may legitimately end "all
    other applicable requirements of the Community Development Code"."""
    assert FURNITURE.search("City of Gresham Development Code")
    assert FURNITURE.search("(06/2026)")
    assert not FURNITURE.search(
        "consistent with all other applicable requirements of the Community"
        " Development Code, including but not limited to Section 7.0400"
    )


# --- the marker in the middle of the label ---------------------------------


def test_a_label_may_put_its_unit_after_the_marker() -> None:
    assert LABEL_MARKER.search("Maximum Height1,2,3,4 (feet)").group("n") == "1,2,3,4"
    assert LABEL_MARKER.search("projects (based)1, 5, 6").group("n") == "1, 5, 6"
    assert LABEL_MARKER.search("Minimum lot area1,2").group("n") == "1,2"
    assert LABEL_MARKER.search("Table 16.22.020-2") is None
    assert LABEL_MARKER.search("MUR-M3") is None


# --- what the chapter says now ---------------------------------------------


def test_the_downtown_use_table_answers_itself(downtown) -> None:
    """Twenty-four notes where there were none, and the twenty-four markers on
    the table above them stop being orphans."""
    use_table = next(b for b in downtown.blocks if b.head == 307)
    assert [b.mark for b in use_table.bodies] == [str(n) for n in range(1, 25)]
    # The five that were left over belonged to the material palette, whose
    # heading names itself "Table 4.1152(B)(8) Notes:" -- brackets the table
    # identifier did not admit until they were let in. Nothing is orphaned now.
    assert downtown.unbodied == ()


def test_the_two_tables_stop_answering_each_other(downtown) -> None:
    """One block for the whole chapter meant Table 4.1130's notes 1 to 16 were
    "marked" by Table 4.1120's markers 1 to 16, a hundred and fifty lines away.
    Two blocks, two regions, and the dimensional table's own missing
    superscripts are now visible as unmarked bodies rather than hidden by the
    use table's."""
    heads = sorted(b.head for b in downtown.blocks)
    # 4473 is the material palette, a third block and a third region. It was
    # invisible while a table identifier could not carry brackets.
    assert heads == [307, 527, 4473]
    assert [b.region for b in downtown.blocks if b.head == 307] == [(0, 306)]
    assert [b.region for b in downtown.blocks if b.head == 527] == [(365, 526)]


def test_the_note_that_lets_a_plex_onto_a_downtown_lot(downtown) -> None:
    """Note 1 is the whole content of the L1 in the Quadplex row. It had been
    read by hand and encoded against a line range, because there was no body to
    quote; there is one now."""
    first = next(b for b in downtown.bodies if b.line == 309)
    assert "6,500 square feet or smaller" in first.text
    assert "7,600 square feet or smaller" in first.text
    ruled = {row.quote: row for row in dispositions(GRESHAM)}
    assert ruled[f"{DOC}#L309"].state == "encoded"


def test_every_new_note_is_ruled_and_none_blocks() -> None:
    assert not [
        row
        for row in dispositions(GRESHAM)
        if row.state == "unread" and row.quote.startswith(f"{DOC}#L3")
    ]
    assert not [row for row in qualified() if row.blocking]
