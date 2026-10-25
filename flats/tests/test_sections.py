"""Code text cut one section to a file, and the proof copy it is cut from.

The pilot is Tualatin (2026-10-23, FOLLOWUPS 73): 24 chapters became 183
section files in a folder per chapter, made readable, with one index per city
as the only bookkeeping, and the chapters stayed as the proof copies. These
tests hold the cut to its promises -- a section file is exactly the readable
text of its slice of exactly the fetched text, a citation that moves quotes
the same words on the same page, and anything the cut cannot place is left
where it was rather than guessed at.
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
    addresses,
    chapters,
    check,
    derived,
    held,
    in_proof,
    move_quote,
    printed,
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
KNOWN = {LAYER: RULE}

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

#: A sentence the PDF wrapped: line 2 runs to the margin.
WRAPPED = [
    "TDC 40.100. Purpose.",  # 1
    "The purpose of this zone is to provide housing for the people who live in the town and",  # 2
    "work nearby in its shops and offices.",  # 3
    "TDC 40.200. Uses.",  # 4
    "Quadplexes are permitted outright.",  # 5
]

S100 = f"{LAYER}/40/40.100.txt"
S200 = f"{LAYER}/40/40.200.txt"


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
    assert got[1].file == "40/40.200.txt"
    assert Section("73C.030", 1, 2).chapter == "73C"


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


def test_write_files_sections_by_chapter_and_check_holds_them(tmp_path) -> None:
    store = _store(tmp_path)
    write(store, RULE)
    assert store.load(S200).text == "\n".join(CHAPTER[5:]) + "\n"
    assert check(store, KNOWN) == []
    # the proof copy is not a document a citation names, but it still loads
    assert f"{LAYER}/40.res.txt" not in store.documents()
    assert S200 in store.documents()
    assert store.proofs() == {f"{LAYER}/40.res.txt"}
    assert store.fetched() == [f"{LAYER}/40.res.txt"]
    assert store.section_of(S200) == "40.200"
    assert store.section_of(f"{LAYER}/40.res.txt") is None
    assert store.load(f"{LAYER}/40.res.txt").text.startswith("TDC 40.100.")


def test_a_wrapped_sentence_is_one_line_that_knows_its_printed_lines(tmp_path) -> None:
    store = _store(tmp_path, WRAPPED)
    write(store, RULE)
    lines = store.load(S100).text.splitlines()
    assert lines == [
        "TDC 40.100. Purpose.",
        "The purpose of this zone is to provide housing for the people who live in the town"
        " and work nearby in its shops and offices.",
    ]
    assert held(store, S100, KNOWN) == [(1,), (2, 3)]
    assert printed(store, S100, KNOWN)[1] == (WRAPPED[1], WRAPPED[2])
    assert printed(store, f"{LAYER}/40.res.txt", KNOWN) is None
    # a citation of the sentence reaches the two printed lines it is on
    assert in_proof(store, f"{S100}", [(2, 2)], KNOWN) == (f"{LAYER}/40.res.txt", [(2, 3)])
    where = addresses(store, f"{LAYER}/40.res.txt", KNOWN)
    assert where[3] == (S100, (2,))
    assert where[5] == (S200, (2,))


def test_held_reads_the_file_on_disk_whichever_cleaning_made_it(tmp_path) -> None:
    store = _store(tmp_path, WRAPPED)
    write(store, RULE)
    # The same words as the printed lines, as an older cleaning stored them.
    store.text_path(S100).write_text("\n".join(WRAPPED[:3]) + "\n", encoding="utf-8")
    assert held(store, S100, KNOWN) == [(1,), (2,), (3,)]
    # ... and a stored text that is not the proof copy's words is refused.
    store.text_path(S200).write_text("TDC 40.200. Uses.\nQuadplexes are prohibited.\n",
                                     encoding="utf-8")
    with pytest.raises(ProvenanceError, match="not the proof copy's words"):
        held(store, S200, KNOWN)


def test_check_catches_a_section_file_that_drifted(tmp_path) -> None:
    store = _store(tmp_path)
    write(store, RULE)
    store.text_path(S200).write_text("Quadplexes are prohibited.\n", encoding="utf-8")
    assert any("not the readable text of lines 6-8" in p for p in check(store, KNOWN))


def test_check_catches_a_proof_copy_refetched_under_its_sections(tmp_path) -> None:
    store = _store(tmp_path)
    write(store, RULE)
    _store(tmp_path, [*CHAPTER, "Amended."])
    assert any("changed since it was cut" in p for p in check(store, KNOWN))


def test_check_catches_a_sidecar_beside_a_section_file(tmp_path) -> None:
    store = _store(tmp_path)
    write(store, RULE)
    store.meta_path(S200).write_text("{}", encoding="utf-8")
    assert any("a sidecar beside a section file" in p for p in check(store, KNOWN))


def test_a_quote_moves_to_its_section_and_says_the_same_words(tmp_path) -> None:
    store = _store(tmp_path)
    write(store, RULE)
    before = f"{LAYER}/40.res.txt#L7-L8"
    after = move_quote(before, store, KNOWN)
    assert after == f"{S200}#L2-L3"
    assert store.quote(after) == store.quote(before)


def test_a_quote_across_two_sections_stays_on_the_proof_copy(tmp_path) -> None:
    store = _store(tmp_path)
    write(store, RULE)
    assert move_quote(f"{LAYER}/40.res.txt#L4,L7", store, KNOWN) is None
    # and a line of the contents list belongs to no section
    assert move_quote(f"{LAYER}/40.res.txt#L1", store, KNOWN) is None


def test_prose_citations_are_repointed_and_other_documents_left_alone(tmp_path) -> None:
    store = _store(tmp_path)
    write(store, RULE)
    proof = f"{LAYER}/40.res.txt"
    text = (
        f'quote: "{proof}#L7"\n'
        "note: see 40.res.txt L4-L5, 41.res.txt L7\n"
        'other: "or/elsewhere/40.res.txt#L7"\n'
        f'spans: "{proof}#L4,L7"\n'
    )
    got, moved, kept = repoint_text(text, proof, addresses(store, proof, KNOWN))
    assert f'"{S200}#L2"' in got
    assert "see 40.100.txt L2-L3, 41.res.txt L7" in got
    assert '"or/elsewhere/40.res.txt#L7"' in got
    assert kept == [f"{proof}#L4,L7"]
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
    first = page_map.read(store, S100)
    second = page_map.read(store, S200)
    assert [(p.n, p.line) for p in first.pages] == [(1, 1), (2, 3)]
    assert [(p.n, p.line) for p in second.pages] == [(2, 1), (3, 2)]
    assert second.source_sha256 == "pdf"
    # the pages live in the city's one index, not in a sidecar
    assert not page_map.sidecar(store, S200).exists()
    # rebuilt from the book again, the same answer
    assert repage(store, proof, KNOWN) == 2
    assert page_map.read(store, S200).pages == second.pages


def test_drift_on_a_book_reaches_its_sections_and_a_chapter_is_its_book(tmp_path) -> None:
    store = _store(tmp_path)
    write(store, RULE)
    proof = f"{LAYER}/40.res.txt"
    assert derived([proof], store) == {proof, S100, S200}
    assert chapters([S200], store) == derived([proof], store)
    assert derived(["or/elsewhere/x.txt"], store) == {"or/elsewhere/x.txt"}


def test_folder_tools_skip_the_proof_copy_and_own_the_chapter_folders(tmp_path) -> None:
    store = _store(tmp_path)
    write(store, RULE)
    folder = store.root / LAYER
    assert [p.name for p in ProvenanceStore.owned(folder)] == ["40.100.txt", "40.200.txt"]
    # a chapter folder owns nothing of its own: its files are its city's
    assert ProvenanceStore.owned(folder / "40") == []
    assert ProvenanceStore.cut_names(folder) == {"40.100.txt", "40.200.txt"}
    assert [p.name for p in ProvenanceStore.owned_tree(store.root)] == ["40.100.txt", "40.200.txt"]
    index = json.loads((folder / "sections.json").read_text(encoding="utf-8"))
    assert index["readable"].startswith("readable/")
    rows = index["documents"]["40.res.txt"]["sections"]
    assert [row[:4] for row in rows] == [["40.100", 3, 5, "40/40.100.txt"], ["40.200", 6, 8, "40/40.200.txt"]]
    assert splits(store)[f"{LAYER}/40.res.txt"].sections == (Section("40.100", 3, 5), Section("40.200", 6, 8))


def test_every_cut_in_the_corpus_is_its_slice() -> None:
    """The real store: every section file is exactly its proof copy's readable text."""
    assert check() == []


def test_a_named_front_matter_document_cuts_below_its_cover() -> None:
    """Durham, King City and Estacada print a cover, a title and a preface over
    their first heading. A document named in ``front`` keeps them in the proof
    copy and in no section; any other document still refuses."""
    lines = ["DEVELOPMENT CODE", "Adopted by the council.", *CHAPTER[2:]]
    with pytest.raises(ProvenanceError, match="not a contents list"):
        split(lines, RULE, "40.res")
    front = Rule(layer=LAYER, heading=RULE.heading, furniture=RULE.furniture,
                 front=frozenset({"40.res"}))
    got = split(lines, front, "40.res")
    assert got[0] == Section("40.100", 3, 5)


def test_out_of_order_headings_pass_only_where_named_and_each_printed_twice() -> None:
    """Estacada's zone chapters are interleaved (16.12, 16.16, 16.12 ...). The
    order guard is waived for a document named in ``any_order``, and only while
    every heading is printed exactly twice -- contents list and text -- so a
    heading the guard would have caught is still caught."""
    lines = ["TDC 40.200. Uses.", "TDC 40.100. Purpose.",
             "TDC 40.200. Uses.", "x", "TDC 40.100. Purpose.", "y"]
    with pytest.raises(ProvenanceError, match="out of number order"):
        split(lines, RULE, "40.res")
    listed = Rule(layer=LAYER, heading=RULE.heading, any_order=frozenset({"40.res"}))
    assert split(lines, listed, "40.res") == [Section("40.200", 3, 4), Section("40.100", 5, 6)]
    once = ["TDC 40.200. Uses.", "x", "TDC 40.100. Purpose.", "y"]
    with pytest.raises(ProvenanceError, match="out of number order"):
        split(once, listed, "40.res")


def test_an_uncut_document_is_left_whole(tmp_path) -> None:
    """King City 16.24's definitions name a section whose heading is printed
    only in the contents list; ``uncut`` leaves that document whole."""
    store = _store(tmp_path)
    uncut = Rule(layer=LAYER, heading=RULE.heading, furniture=RULE.furniture,
                 uncut=frozenset({"40.res"}))
    assert write(store, uncut) == []
    assert store.proofs() == set()
    assert f"{LAYER}/40.res.txt" in store.documents()


def test_a_three_part_number_files_under_its_chapter() -> None:
    assert Section("16.114.130", 1, 2).chapter == "16.114"
    assert Section("16.114.130", 1, 2).file == "16.114/16.114.130.txt"


ARTICLES = [
    "ARTICLE 1",  # 1  the first article's heading, above the first section
    "GENERAL PROVISIONS",  # 2
    "TDC 1.010. Title.",  # 3
    "This code is the town code.",  # 4
    "ARTICLE 2",  # 5  the next article, printed under 1.010
    "SCOPE AND COMPLIANCE",  # 6
    "TDC 2.010. Scope.",  # 7
    "Every lot is subject to it.",  # 8
]


def _opening(**extra) -> Rule:
    from flats.provenance.sections import Opening

    opens = extra.pop("opens", (Opening("Article", re.compile(r"^\s*ARTICLE\s+(?P<n>\d+)\s*$")),))
    return Rule(layer=LAYER, heading=RULE.heading, front=frozenset({"1.code"}), opens=opens, **extra)


def test_an_article_heading_is_a_page_of_its_own_in_reading_order() -> None:
    """Rivergrove printed "ARTICLE 3 / PLANNING COMMISSION AND HEARINGS
    OFFICER" as the closing lines of 2.090, and its first article's heading
    was in no file at all. Each becomes a small page named for the heading,
    between the sections, and the section ends above it."""
    got = split(ARTICLES, _opening(), "1.code")
    assert got == [
        Section("Article 1", 1, 2, "1/article-1.txt"),
        Section("1.010", 3, 4),
        Section("Article 2", 5, 6, "2/article-2.txt"),
        Section("2.010", 7, 8),
    ]
    assert got[0].page and not got[1].page
    # without the rule, the heading stays where it was printed
    plain = Rule(layer=LAYER, heading=RULE.heading, front=frozenset({"1.code"}))
    assert split(ARTICLES, plain, "1.code") == [Section("1.010", 3, 6), Section("2.010", 7, 8)]


def test_a_heading_naming_the_sections_own_chapter_is_not_a_page() -> None:
    """Sherwood prints "Chapter 16.10" under the heading of 16.10.010."""
    from flats.provenance.sections import Opening

    lines = ["TDC 16.10.010. Purpose.", "Chapter 16.10", "Words.", "Chapter 16.20", "TITLE"]
    rule = Rule(
        layer=LAYER,
        heading=re.compile(r"^TDC (?P<n>16\.\d+\.\d+)\. [A-Z]"),
        opens=(Opening("Chapter", re.compile(r"^Chapter (?P<n>16\.\d+)$")),),
    )
    got = split(lines, rule, "16.code")
    assert got == [Section("16.10.010", 1, 3), Section("Chapter 16.20", 4, 5, "16.10/chapter-16.20.txt")]


def test_a_contents_list_printed_above_the_heading_opens_its_page() -> None:
    """Sherwood prints the next chapter's "Sections:" list ABOVE its "Chapter
    16.108" line; ``lead_in`` starts the page there, not one line under it."""
    from flats.provenance.sections import Opening

    lines = ["TDC 16.10.010. Purpose.", "Words.", "Sections:", "TDC 16.20.010. Uses.",
             "Chapter 16.20", "TDC 16.20.010. Uses.", "More words."]
    rule = Rule(
        layer=LAYER,
        heading=re.compile(r"^TDC (?P<n>16\.\d+\.\d+)\. [A-Z]"),
        opens=(Opening("Chapter", re.compile(r"^Chapter (?P<n>16\.\d+)$")),),
        lead_in=re.compile(r"^Sections:$"),
    )
    got = split(lines, rule, "16.code")
    assert got == [
        Section("16.10.010", 1, 2),
        Section("Chapter 16.20", 3, 5, "16.20/chapter-16.20.txt"),
        Section("16.20.010", 6, 7),
    ]


def test_a_title_only_heading_is_a_page_only_over_a_section() -> None:
    """Tualatin's "COMPLIANCE AND ENFORCEMENT" over 31.105; a line in capitals
    that is not over a section stays where it is."""
    from flats.provenance.sections import Opening

    lines = ["TDC 31.100. Purpose.", "SHOUTED LINE IN TEXT", "Words.",
             "COMPLIANCE AND ENFORCEMENT", "TDC 31.105. Enforcement.", "More."]
    rule = Rule(
        layer=LAYER,
        heading=RULE.heading,
        opens=(Opening("Title", re.compile(r"^(?P<title>[A-Z][A-Z ]{6,}[A-Z])$"), above=True),),
    )
    got = split(lines, rule, "31.code")
    assert got == [
        Section("31.100", 1, 3),
        Section("Compliance and Enforcement", 4, 4, "31/compliance-and-enforcement.txt"),
        Section("31.105", 5, 6),
    ]


def test_heading_pages_are_written_indexed_and_read_back(tmp_path) -> None:
    store = _store(tmp_path, lines=ARTICLES, name="1.code.txt")
    rule = _opening()
    write(store, rule)
    assert check(store, {LAYER: rule}) == []
    page = f"{LAYER}/2/article-2.txt"
    assert store.load(page).text == "ARTICLE 2\nSCOPE AND COMPLIANCE\n"
    assert store.part_of(page).number == "Article 2"
    cut = splits(store)[f"{LAYER}/1.code.txt"]
    assert [s.file for s in cut.sections] == ["1/article-1.txt", "1/1.010.txt", "2/article-2.txt", "2/2.010.txt"]
    assert store.load(f"{LAYER}/1/1.010.txt").text == "TDC 1.010. Title.\nThis code is the town code.\n"


def test_two_pages_filed_as_one_refuse() -> None:
    from flats.provenance.sections import titled

    lines = ["TDC 1.010. Title.", "x", "ARTICLE 3", "TDC 2.010. A.", "y", "ARTICLE 3", "TDC 2.020. B.", "z"]
    with pytest.raises(ProvenanceError, match="two pages would be filed"):
        split(lines, _opening(), "1.code")
    assert titled("PLANNING COMMISSION AND HEARINGS OFFICER") == "Planning Commission and Hearings Officer"
    assert titled("MEDIUM LOW DENSITY RESIDENTIAL ZONE (RML)") == "Medium Low Density Residential Zone (RML)"
    assert titled("Commercial Standards (Reserved).") == "Commercial Standards (Reserved)."
