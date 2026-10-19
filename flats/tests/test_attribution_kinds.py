"""A section disagreement is classified, and all of them are still counted.

Report-only: the class decides how a disagreement is described in the gaps
ledger, never whether it is one.
"""

from __future__ import annotations

from datetime import date

import pytest

from flats.encode.attribution import (
    HEADER_OR_XREF,
    HEADING_OTHER_FILE,
    HEADING_SAME_FILE,
    UNLOCATED,
    Attribution,
    CorpusHeadings,
    classify,
    tally,
)
from flats.provenance.store import ProvenanceStore


@pytest.fixture
def store(tmp_path):
    store = ProvenanceStore(tmp_path)
    store.save(
        "a.txt",
        url="https://example.test/a",
        text="\n".join(
            [
                "19.302 Standards",
                "Setbacks are twenty feet.",
                "§ 19.401 CODE",
                "See Section 19.302 for the table.",
                "Heights are thirty feet.",
                "19.500 Other",
                "text",
            ]
        ),
        retrieved=date(2026, 1, 1),
    )
    store.save(
        "b.txt",
        url="https://example.test/b",
        text="19.900 Elsewhere\ntext",
        retrieved=date(2026, 1, 1),
    )
    return store


def lines_of(store, path="a.txt"):
    return store.load(path).text.splitlines()


def item(quote, claimed, found="19.401"):
    return Attribution("x", "z", "f", quote, claimed, found)


def run(store, one):
    return classify(one, lines_of(store), CorpusHeadings(store))


def test_a_claimed_section_printed_in_the_cited_lines_is_a_header_or_cross_reference(store):
    assert run(store, item("a.txt#L4-L5", "19.302")) == HEADER_OR_XREF


def test_the_printed_section_is_matched_across_spacing_and_marks(store):
    assert run(store, item("a.txt#L3", "19.401 19.999", found="19.302")) == HEADER_OR_XREF


def test_a_longer_number_does_not_count_as_printing_the_claimed_one(store):
    assert run(store, item("a.txt#L5", "19.30")) != HEADER_OR_XREF


def test_a_heading_elsewhere_in_the_same_file_is_its_own_class(store):
    assert run(store, item("a.txt#L5", "19.500")) == HEADING_SAME_FILE


def test_a_heading_only_in_another_file_is_its_own_class(store):
    assert run(store, item("a.txt#L5", "19.900")) == HEADING_OTHER_FILE


def test_a_claimed_section_found_nowhere_is_unlocated(store):
    assert run(store, item("a.txt#L5", "19.777")) == UNLOCATED


def test_an_agreeing_item_has_no_class(store):
    assert run(store, item("a.txt#L5", "19.401")) == ""


def test_every_disagreement_is_counted_and_only_the_header_class_is_harmless():
    kinds = [HEADER_OR_XREF, HEADER_OR_XREF, HEADING_SAME_FILE, HEADING_OTHER_FILE]
    items = [
        Attribution("x", "z", "f", "d#L1", "1.11", "2.22", kind=kind) for kind in kinds
    ] + [Attribution("x", "z", "f", "d#L1", "1.11", "1.11")]

    counts = tally(items)

    assert counts == {
        HEADER_OR_XREF: 2,
        HEADING_SAME_FILE: 1,
        HEADING_OTHER_FILE: 1,
        UNLOCATED: 0,
    }
    assert sum(counts.values()) == 4
    assert [one.probably_harmless for one in items[:3]] == [True, True, False]
