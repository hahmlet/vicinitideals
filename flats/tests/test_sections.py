"""Code text cut one section to a file, and the proof copy it is cut from.

The pilot is Tualatin (2026-10-23, FOLLOWUPS 73): 24 chapters became 183
section files, every citation was re-pointed, and the chapters stayed as the
proof copies. These tests hold the cut to its three promises -- a section
file is exactly its slice of exactly the fetched text, a citation that moves
quotes the same words on the same page, and anything the cut cannot place is
left where it was rather than guessed at.
"""

from __future__ import annotations

import json
import re
from datetime import date

import pytest

from flats.provenance import pages as page_map
from flats.provenance.sections import (
    Rule,
    Section,
    Split,
    chapters,
    check,
    derived,
    move_quote,
    repage,
    repoint_text,
    split,
    splits,
    write,
)
from flats.provenance.store import ProvenanceError, ProvenanceStore

LAYER = "or/test/town"
RULE = Rule(
    layer=LAYER,
    heading=re.compile(r"^\s*TDC\s+(?P<n>\d+[A-Z]?\.\d+)\.?\s+[A-Z]"),
    furniture=re.compile(r"^\s*TDC\s+\d+[A-Z]?\.\d+\.?\s+TOWN CODE"),
)

CHAPTER = [
    "TDC 40.100. Purpose.",  # 1  contents list
    "TDC 40.200. Uses.",  # 2
    "TDC 40.100. Purpose.",  # 3  the text starts here
    "The purpose of this zone is housing.",  # 4
    "TDC 40.100. TOWN CODE  page 2",  # 5  a running header, not a heading
    "TDC 40.200. Uses.",  # 6
    "Quadplexes are permitted outright.",  # 7
    "Table 40-1",  # 8
]


def _store(tmp_path, lines=CHAPTER, name="40.res.txt"):
    store = ProvenanceStore(tmp_path)
    store.save(
        f"{LAYER}/{name}",
        url="https://example.test/code.pdf",
        text="\n".join(lines) + "\n",
        retrieved=date(2026, 10, 23),
    )
    return store


def test_a_section_starts_at_the_last_printing_of_its_heading() -> None:
    got = split(CHAPTER, RULE, "40.res")
    assert got == [Section("40.100", 3, 5), Section("40.200", 6, 8)]


def test_a_running_header_does_not_cut() -> None:
    plain = Rule(layer=LAYER, heading=RULE.heading)
    with pytest.raises(ProvenanceError, match="printed 3 times"):
        split(CHAPTER, plain, "40.res")


def test_text_above_the_first_heading_must_be_named() -> None:
    lines = ["continued from the last chapter.", *CHAPTER[2:]]
    with pytest.raises(ProvenanceError, match="not a contents list"):
        split(lines, RULE, "40.res")
    named = Rule(layer=LAYER, heading=RULE.heading, furniture=RULE.furniture,
                 lead={"40.res": "40.050"})
    assert split(lines, named, "40.res")[0] == Section("40.050", 1, 1)


def test_a_contents_entry_with_no_heading_below_it_refuses() -> None:
    lines = ["TDC 40.300. Lots.", *CHAPTER]
    with pytest.raises(ProvenanceError, match="40.300"):
        split(lines, RULE, "40.res")


def test_headings_out_of_number_order_refuse() -> None:
    lines = ["TDC 40.200. Uses.", "x", "TDC 40.100. Purpose.", "y"]
    with pytest.raises(ProvenanceError, match="out of number order"):
        split(lines, RULE, "40.res")


def test_write_cuts_exact_slices_and_check_holds_them(tmp_path) -> None:
    store = _store(tmp_path)
    write(store, RULE)
    assert store.load(f"{LAYER}/40.200.txt").text == "\n".join(CHAPTER[5:]) + "\n"
    assert check(store) == []
    # the proof copy is not a document a citation names, but it still loads
    assert f"{LAYER}/40.res.txt" not in store.documents()
    assert f"{LAYER}/40.200.txt" in store.documents()
    assert store.proofs() == {f"{LAYER}/40.res.txt"}
    assert store.fetched() == [f"{LAYER}/40.res.txt"]
    assert store.section_of(f"{LAYER}/40.200.txt") == "40.200"
    assert store.section_of(f"{LAYER}/40.res.txt") is None
    assert store.load(f"{LAYER}/40.res.txt").text.startswith("TDC 40.100.")


def test_check_catches_a_section_file_that_drifted(tmp_path) -> None:
    store = _store(tmp_path)
    write(store, RULE)
    store.text_path(f"{LAYER}/40.200.txt").write_text("Quadplexes are prohibited.\n", encoding="utf-8")
    assert any("not lines 6-8" in p for p in check(store))


def test_check_catches_a_proof_copy_refetched_under_its_sections(tmp_path) -> None:
    store = _store(tmp_path)
    write(store, RULE)
    _store(tmp_path, [*CHAPTER, "Amended."])
    assert any("changed since it was cut" in p for p in check(store))


def test_a_quote_moves_to_its_section_and_says_the_same_words(tmp_path) -> None:
    store = _store(tmp_path)
    write(store, RULE)
    cuts = splits(store)
    before = f"{LAYER}/40.res.txt#L7-L8"
    after = move_quote(before, cuts)
    assert after == f"{LAYER}/40.200.txt#L2-L3"
    assert store.quote(after) == store.quote(before)


def test_a_quote_across_two_sections_stays_on_the_proof_copy(tmp_path) -> None:
    store = _store(tmp_path)
    write(store, RULE)
    assert move_quote(f"{LAYER}/40.res.txt#L4,L7", splits(store)) is None
    # and a line of the contents list belongs to no section
    assert move_quote(f"{LAYER}/40.res.txt#L1", splits(store)) is None


def test_prose_citations_are_repointed_and_other_documents_left_alone() -> None:
    cut = Split(f"{LAYER}/40.res.txt", "x", (Section("40.100", 3, 5), Section("40.200", 6, 8)))
    text = (
        f'quote: "{LAYER}/40.res.txt#L7"\n'
        "note: see 40.res.txt L4-L5, 41.res.txt L7\n"
        'other: "or/elsewhere/40.res.txt#L7"\n'
        f'spans: "{LAYER}/40.res.txt#L4,L7"\n'
    )
    got, moved, kept = repoint_text(text, cut)
    assert f'"{LAYER}/40.200.txt#L2"' in got
    assert "see 40.100.txt L2-L3, 41.res.txt L7" in got
    assert '"or/elsewhere/40.res.txt#L7"' in got
    assert kept == [f"{LAYER}/40.res.txt#L4,L7"]
    assert len(moved) == 2


def test_a_section_page_map_is_its_books_offset(tmp_path) -> None:
    store = _store(tmp_path)
    proof = f"{LAYER}/40.res.txt"
    book = page_map.PageIndex(
        path=proof,
        sha256=store.load(proof).sha256,
        extractor="test",
        pages=(page_map.Page(1, 1, "1"), page_map.Page(2, 5, "2"), page_map.Page(3, 7, "3")),
        source_sha256="pdf",
    )
    page_map.write(store, book, extractor="test")
    write(store, RULE)
    first = page_map.read(store, f"{LAYER}/40.100.txt")
    second = page_map.read(store, f"{LAYER}/40.200.txt")
    assert [(p.n, p.line) for p in first.pages] == [(1, 1), (2, 3)]
    assert [(p.n, p.line) for p in second.pages] == [(2, 1), (3, 2)]
    assert second.source_sha256 == "pdf"
    # rebuilt from the book again, the same answer
    assert repage(store, proof) == 2
    assert page_map.read(store, f"{LAYER}/40.200.txt").pages == second.pages


def test_drift_on_a_book_reaches_its_sections_and_a_chapter_is_its_book(tmp_path) -> None:
    store = _store(tmp_path)
    write(store, RULE)
    proof = f"{LAYER}/40.res.txt"
    assert derived([proof], store) == {proof, f"{LAYER}/40.100.txt", f"{LAYER}/40.200.txt"}
    assert chapters([f"{LAYER}/40.200.txt"], store) == derived([proof], store)
    assert derived(["or/elsewhere/x.txt"], store) == {"or/elsewhere/x.txt"}


def test_folder_tools_skip_the_proof_copy(tmp_path) -> None:
    store = _store(tmp_path)
    write(store, RULE)
    folder = store.root / LAYER
    assert [p.name for p in ProvenanceStore.owned(folder)] == ["40.100.txt", "40.200.txt"]
    assert ProvenanceStore.cut_names(folder) == {"40.100.txt", "40.200.txt"}
    assert [p.name for p in ProvenanceStore.owned_tree(store.root)] == ["40.100.txt", "40.200.txt"]
    index = json.loads((folder / "sections.json").read_text(encoding="utf-8"))
    assert index["documents"]["40.res.txt"]["sections"] == [["40.100", 3, 5], ["40.200", 6, 8]]


def test_every_cut_in_the_corpus_is_its_slice() -> None:
    """The real store: every section file is exactly its proof copy's lines."""
    assert check() == []
