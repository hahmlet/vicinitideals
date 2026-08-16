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

    # The check is not blind: somewhere in the corpus a value still cites a
    # section its text is not in, and this is what stops the assertion above
    # from passing because nothing was measured.
    misses = [
        item
        for layer in layers.values()
        for item in check(layer, store)
        if not item.agrees
    ]
    assert misses, "no layer disagrees anywhere — the check went blind"
