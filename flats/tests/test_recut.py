"""A re-cut moves every citation onto the new lines without changing its words.

Tualatin's re-cut to ``readable/2`` (2026-10-23) moved 33 citations and
refused none. The rule it held to: a citation moves only when the new quote
holds every word the old one did, on the same printed pages; anything else is
left where it was and reported for a person.
"""

from __future__ import annotations

import re
from datetime import date

from flats.encode.recut import Before, _move_citations
from flats.provenance import pages as page_map
from flats.provenance.sections import Rule, held, write
from flats.provenance.store import ProvenanceStore

LAYER = "or/test/town"
RULE = Rule(layer=LAYER, heading=re.compile(r"^\s*TDC\s+(?P<n>\d+[A-Z]?\.\d+)\.?\s+[A-Z]"))
LONG = "The purpose of this zone is to provide housing for the people who live in the town and"
CHAPTER = [
    "TDC 40.100. Purpose.",
    LONG,
    "work nearby in its shops and offices.",
    "TDC 40.200. Uses.",
    "Quadplexes are permitted outright.",
]
S100 = f"{LAYER}/40/40.100.txt"
KNOWN = {LAYER: RULE}


def _old_cut(tmp_path) -> tuple[ProvenanceStore, Before]:
    """A store whose section file is still the printed lines, as an older cleaning left it."""
    store = ProvenanceStore(tmp_path / "docs")
    store.save(f"{LAYER}/40.res.txt", url="https://example.test/code.pdf",
               text="\n".join(CHAPTER) + "\n", retrieved=date(2026, 10, 23))
    write(store, RULE)
    store.text_path(S100).write_text("\n".join(CHAPTER[:3]) + "\n", encoding="utf-8")
    paths = [p for p, part in store.parts().items() if part.layer == LAYER]
    before = Before(
        layer=LAYER,
        text={p: store.text_path(p).read_text(encoding="utf-8").splitlines() for p in paths},
        held={p: held(store, p, KNOWN) for p in paths},
        pages={p: page_map.read(store, p) for p in paths},
        cards={},
        signed={},
    )
    write(store, RULE)  # the re-cut: lines 2 and 3 become one sentence
    return store, before


def test_a_citation_of_a_wrapped_line_moves_onto_the_sentence(tmp_path) -> None:
    store, before = _old_cut(tmp_path)
    rules = tmp_path / "town.yaml"
    rules.write_text(
        f'a: "{S100}#L3"\n'
        f'b: "{S100}#L2-L3"\n'
        "c: see 40.100.txt L1\n"
        f'd: "{LAYER}/40/40.200.txt#L2"\n',
        encoding="utf-8",
    )
    moved, refused = _move_citations(store, before, [rules], {rules}, write_files=True, known=KNOWN)
    assert refused == []
    text = rules.read_text(encoding="utf-8")
    assert f'a: "{S100}#L2"' in text
    assert f'b: "{S100}#L2"' in text
    assert "c: see 40.100.txt L1" in text  # unchanged: the heading did not move
    assert {(a, b) for _, a, b in moved} == {(f"{S100}#L3", f"{S100}#L2"), (f"{S100}#L2-L3", f"{S100}#L2")}
    # and the moved quote holds the old words
    assert "work nearby" in store.quote(f"{S100}#L2")


def test_a_citation_the_old_file_cannot_hold_is_refused_and_left(tmp_path) -> None:
    store, before = _old_cut(tmp_path)
    rules = tmp_path / "town.yaml"
    rules.write_text(f'a: "{S100}#L9"\n', encoding="utf-8")
    moved, refused = _move_citations(store, before, [rules], {rules}, write_files=True, known=KNOWN)
    assert moved == []
    assert [why for _, _, why in refused] == ["names a line the file does not have"]
    assert rules.read_text(encoding="utf-8") == f'a: "{S100}#L9"\n'


def test_a_bare_name_in_another_citys_file_is_not_this_citys(tmp_path) -> None:
    store, before = _old_cut(tmp_path)
    other = tmp_path / "elsewhere.yaml"
    other.write_text("note: see 40.100.txt L3\n", encoding="utf-8")
    moved, refused = _move_citations(store, before, [other], set(), write_files=True, known=KNOWN)
    assert (moved, refused) == ([], [])
    assert other.read_text(encoding="utf-8") == "note: see 40.100.txt L3\n"


def test_a_first_cut_moves_citations_off_the_fetched_document(tmp_path) -> None:
    """Durham, Rivergrove, King City and Estacada were cut for the first time
    on 2026-10-24: their citations named the fetched chapter itself. To the
    move it is a file whose every line holds its own line."""
    from flats.encode.recut import first_cut

    store = ProvenanceStore(tmp_path / "docs")
    proof = f"{LAYER}/40.res.txt"
    store.save(proof, url="https://example.test/code.pdf",
               text="\n".join(CHAPTER) + "\n", retrieved=date(2026, 10, 23))
    assert first_cut(store, RULE) == [proof]
    before = Before(
        layer=LAYER,
        text={proof: list(CHAPTER)},
        held={proof: [(k,) for k in range(1, len(CHAPTER) + 1)]},
        pages={proof: page_map.read(store, proof)},
        cards={},
        signed={},
    )
    write(store, RULE)
    assert first_cut(store, RULE) == []
    rules = tmp_path / "town.yaml"
    rules.write_text(f'a: "{proof}#L3"\nb: "{proof}#L2,L5"\n', encoding="utf-8")
    moved, refused = _move_citations(store, before, [rules], {rules}, write_files=True, known=KNOWN)
    assert {(a, b) for _, a, b in moved} == {(f"{proof}#L3", f"{S100}#L2")}
    assert [cite for _, cite, _ in refused] == [f"{proof}#L2,L5"]
    text = rules.read_text(encoding="utf-8")
    assert f'a: "{S100}#L2"' in text
    assert f'b: "{proof}#L2,L5"' in text  # spans two sections: left where it was


def test_a_quote_whose_lines_run_out_of_order_is_refused_and_left(tmp_path) -> None:
    """A note in prose may list lines out of order ("#L452,L464,L63", Gladstone):
    that is no quote to move, and it used to stop the whole re-cut."""
    store, before = _old_cut(tmp_path)
    rules = tmp_path / "town.yaml"
    rules.write_text(f'a: "{S100}#L3,L1"\n', encoding="utf-8")
    moved, refused = _move_citations(store, before, [rules], {rules}, write_files=True, known=KNOWN)
    assert moved == []
    assert [why for _, _, why in refused] == ["its spans are out of order"]
    assert rules.read_text(encoding="utf-8") == f'a: "{S100}#L3,L1"\n'
