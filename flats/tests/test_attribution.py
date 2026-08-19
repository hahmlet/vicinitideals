"""Does the citation name the section the quoted text is actually in.

The failure this catches is invisible to every other check: the quote resolves,
the text states the number, and the citation names a section the reader will
open to find nothing. Wilsonville's RN zone cited section 4.127 against lines
that are section 4.113 — the citywide setbacks, which apply only "unless
otherwise provided for by a legislative master plan". Right number, wrong
authority.
"""

from __future__ import annotations

import pytest

from flats.encode.attribution import Attribution, claimed_section, section_at

DOC = [
    "§ 4.113 WILSONVILLE CODE",
    "CD4:74Supp. No. 5",
    "(.02) Building Setbacks. The following provisions apply unless otherwise",
    "provided for by the Code or a legislative master plan.",
    "A. For lots over 10,000 square feet:",
    "1. Minimum front yard setback: 20 feet.",
]


@pytest.mark.parametrize(
    "cite, section",
    [
        ("Wilsonville Development Code 4.127 (RN Zone), Table 2", "4.127"),
        ("MMC 19.302 High Density Residential, Table 19.302.4", "19.302"),
        ("Portland City Code 33.110.220", "33.110.220"),
        ("Gresham Development Code, Table 4.0120", "4.0120"),
        # A statute numbers itself the same way a code section does.
        ("ORS 92.031", "92.031"),
        ("", ""),
    ],
)
def test_the_section_a_citation_claims_is_read_off_its_words(cite, section):
    assert claimed_section(cite) == section


def test_the_section_text_is_in_is_read_off_the_running_header():
    """A codifier prints the section on every page.

    That makes the page furniture the most reliable marker in the document: it
    is machine-placed, repeated, and survives a heading being flattened into a
    table cell by extraction.
    """
    assert section_at(DOC, 6) == "4.113"


def test_a_document_with_no_marker_above_the_quote_says_nothing():
    assert section_at(["Minimum front yard setback: 20 feet."], 1) == ""


def test_a_citation_to_a_table_inside_the_section_it_names_agrees():
    """"19.302" against text headed "19.302.4" is the same place, said shorter."""
    item = Attribution("x", "R-HD", "setback_front_ft", "d#L1", "19.302", "19.302.4")

    assert item.agrees


def test_a_citation_to_another_section_disagrees():
    item = Attribution("x", "RN", "setback_front_ft", "d#L1", "4.127", "4.113")

    assert not item.agrees


def test_nothing_is_claimed_when_nothing_can_be_read():
    """Silence is not a finding. A state statute cites no section number at all."""
    assert Attribution("x", "z", "f", "d#L1", "", "4.113").agrees
    assert Attribution("x", "z", "f", "d#L1", "4.113", "").agrees


def test_the_corpus_is_measured_not_asserted():
    """A gate here would fail the build on encoding debt nobody has worked yet.

    What this holds is that the check runs over the real corpus and produces
    findings in the shape the review UI consumes — not that the corpus is clean.
    """
    from flats.encode.attribution import check
    from flats.provenance.store import ProvenanceStore
    from flats.rules.loader import load_rules

    layers = load_rules(strict=False)
    store = ProvenanceStore()

    found = check(layers["or/clackamas/wilsonville"], store)

    assert found, "a fully encoded jurisdiction has values to check"
    assert all(item.quote for item in found)
    # Wilsonville used to be the example of a layer that disagreed: OTR and RN
    # cited only their own zone chapter and quoted the citywide setback
    # section. Both cites name 4.113 now, so the layer is the regression guard
    # for that fix rather than the proof the check can see a miss.
    assert all(item.agrees for item in found), (
        "OTR and RN cite 4.113(.02) alongside their own chapter — a setback "
        "quoted from the citywide section is cited to it"
    )

    # The check is not blind. There is nothing left in the corpus that
    # disagrees, so the guard against a check that has stopped seeing anything
    # has to be a planted miss rather than a real one: every layer's values,
    # re-read against a document they are definitely not in.
    planted = [
        Attribution(item.layer, item.zone, item.field, item.quote, "99.999", item.found)
        for layer in layers.values()
        for item in check(layer, store)
        if item.found
    ]
    assert planted, "no value anywhere resolves to a section — the check went blind"
    assert not any(item.agrees for item in planted)


def test_a_row_of_a_table_is_not_a_heading():
    """What follows the number is what tells the two apart.

    The pattern used to accept a bare space after the section number, which
    matches every table row that opens with a figure. Gresham lost 57 values
    to it in one document: a density row reading "14.52 units per acre" became
    section 14.52, and a row of "9.0100" cross-references became the heading
    for everything printed below it. Both are two lines of a table, and both
    sat above real quotes.
    """
    table = [
        "  Table 4.0130: Development Requirements for Residential Land Use Districts",
        "        All other uses            8.71 units per        6.22 units per",
        "                                  14.52 units per       18.15 units per",
        "        See also                  9.0100                9.0100",
        "        Duplex, Triplex,          35 ft.                40 ft.",
    ]
    assert section_at(table, 5) == ""

    # A real heading still reads, whether it is a running header, a numbered
    # heading, or a bare section number on its own line.
    assert section_at(["§ 4.113 WILSONVILLE CODE", "text"], 2) == "4.113"
    assert section_at(["39.4862  DIMENSIONAL REQUIREMENTS", "text"], 2) == "39.4862"
    assert section_at(["17.16.070", "text"], 2) == "17.16.070"


def test_a_spelled_out_heading_beats_the_page_running_header():
    """Wilsonville writes every heading as "Section 4.124. Title", and the
    pattern could not see that form at all. So the nearest marker above a
    quote was whatever page furniture it sat under, and 4.124's own permitted-
    use list — the line directly below its heading — read as section 4.123.
    Eight values misattributed for the shape of the heading above them.

    A cross-reference is written the same way and is not a heading. What tells
    them apart is what follows: a title, or a subsection in parentheses.
    """
    from flats.encode.attribution import section_at

    page = [
        " § 4.123PLANNING AND LAND DEVELOPMENT",
        "CD4:119",
        "Section 4.124. Standards Applying to all Planned Development Residential Zones.",
        "(.01) Permitted Uses:",
        "C. Duplexes, triplexes, quadplexes, townhouses.",
    ]
    assert section_at(page, 4) == "4.124"
    assert section_at(page, 5) == "4.124"
    assert section_at(page, 2) == "4.123"

    reference = ["Waivers in compliance with Section 4.127(.09)(B)(2)(d);", "text"]
    assert section_at(reference, 2) == ""


def test_a_cross_reference_inside_a_table_cell_is_not_a_heading():
    """Gresham's RTC parking row prints "Section 9.0851" fifty-six columns in.

    Read as a heading, it re-attributed every table note below it — ten CMF
    townhouse standards cited to 4.0430 and reported as sitting in the
    off-street parking chapter. A heading starts at the margin; a cell starts
    wherever its column does, and that is the only thing separating them here.
    """
    lines = [
        "4.0430                              DEVELOPMENT STANDARDS",
        "   L.     Maximum Off-        2 spaces/unit for residential;",
        "                              all other uses see",
        "                                                        Section 9.0851",
        "Table 4.0430 Notes",
        "1. Minimum setbacks for Townhouses:",
    ]

    assert section_at(lines, 6) == "4.0430"


def test_a_quote_is_attributed_to_every_section_it_reads():
    """A multi-span quote sits in several sections and owes all of them.

    Wilsonville's quadplex permission reads the zone's use list and the
    definition of "Middle Housing" in 4.001 together. Checking only the first
    span would let a citation naming one section carry text from two.
    """
    both = Attribution("x", "R", "quadplex_allowed", "d#L1,L900", "4.122 4.001", "4.001 4.122")
    half = Attribution("x", "R", "quadplex_allowed", "d#L1,L900", "4.122", "4.001 4.122")

    assert both.agrees
    assert not half.agrees
