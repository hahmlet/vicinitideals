"""A citation left on a chapter's proof copy is governed by its sections' notes.

A citation that spans two sections, or takes in a page footer, cannot move
into one section file, so the cut leaves it on the proof copy -- and the proof
copy is not censused: its words are, once, in its sections. Until FOLLOWUPS 123
such a citation stood under no footnote at all, which is the under-scoped
direction, the false-GREEN path. These pin the mechanism: the proof-copy lines
are followed into the section files that hold them, and the notes over those
lines in those files are the notes over the value -- in the join, and on the
second-reading card.
"""

from __future__ import annotations

import pytest

from flats.encode import dispositions, footnotes
from flats.encode.qualified import _cited_lines, over, qualified
from flats.encode.reread import _notes_over
from flats.provenance import sections
from flats.provenance.store import ProvenanceStore

pytestmark = pytest.mark.unit

#: Cut cities with notes blocks in their section files; three keep it quick.
LAYERS = ("or/multnomah/troutdale", "or/washington/tigard", "or/multnomah/portland")


@pytest.fixture(scope="module")
def corpus():
    store = ProvenanceStore()
    censuses: dict = {}
    per_doc: dict = {}
    for layer in LAYERS:
        censuses.update({c.doc: c for c in footnotes.survey(layer)})
        for note in dispositions.notes(layer):
            per_doc.setdefault(note.doc, []).append(note)
    return store, censuses, per_doc


def _probes(store, censuses, per_doc):
    """(proof copy, proof lines, the notes that must govern them) -- one per
    section file whose notes block has a ruled note over a non-empty region."""
    proofs = store.proofs()
    for doc, census in sorted(censuses.items()):
        part = store.part_of(doc)
        if part is None or part.proof not in proofs:
            continue
        held = sections.held(store, doc)
        for block in census.blocks:
            low, high = block.region
            want = {
                (n.doc, n.line)
                for n in per_doc.get(doc, [])
                if (n.doc, n.line) in {(b.doc, b.line) for b in block.bodies}
            }
            lines = [n for k in range(low + 1, high + 1) if k <= len(held) for n in held[k - 1]]
            if want and lines:
                yield part.proof, lines[:1], want
                break


def test_proof_copy_lines_map_back_to_the_section_lines_that_hold_them(corpus) -> None:
    store, censuses, _ = corpus
    probes = 0
    for doc in sorted(d for d, c in censuses.items() if c.blocks):
        part = store.part_of(doc)
        if part is None:
            continue
        for k, src in enumerate(sections.held(store, doc), start=1):
            if src:
                assert k in sections.in_sections(store, part.proof, src[:1])[doc]
                probes += 1
                break
    assert probes > 20


def test_a_proof_copy_citation_takes_the_notes_of_the_section_its_lines_are_in(corpus) -> None:
    store, censuses, per_doc = corpus
    probes = list(_probes(store, censuses, per_doc))
    assert len({p.rsplit("/", 1)[0] for p, _l, _w in probes}) == len(LAYERS)
    for proof, lines, want in probes:
        got = {(n.doc, n.line) for n in over(proof, lines, censuses, per_doc, store)}
        assert want <= got, f"{proof}#L{lines[0]}: lost {sorted(want - got)}"


def test_a_citation_spanning_two_sections_takes_the_notes_of_both(corpus) -> None:
    store, censuses, per_doc = corpus
    by_proof: dict[str, list] = {}
    for proof, lines, want in _probes(store, censuses, per_doc):
        by_proof.setdefault(proof, []).append((lines, want))
    pairs = [rows[:2] for rows in by_proof.values() if len(rows) >= 2]
    assert pairs, "no chapter with notes in two of its sections"
    for (la, wa), (lb, wb) in pairs:
        proof = next(p for p, rows in by_proof.items() if rows[:2] == [(la, wa), (lb, wb)])
        got = {(n.doc, n.line) for n in over(proof, la + lb, censuses, per_doc, store)}
        assert wa | wb <= got


def test_the_second_reading_card_carries_the_section_notes(corpus) -> None:
    store, censuses, per_doc = corpus
    proof, lines, _want = next(_probes(store, censuses, per_doc))
    text, _acts = _notes_over(proof, censuses, [(lines[0], lines[0])], per_doc, store)
    assert text and all(t.startswith("[note ") for t in text)


def test_a_document_never_cut_maps_to_no_sections() -> None:
    store = ProvenanceStore()
    assert sections.in_sections(store, "or/nowhere/never-cut.txt", [1, 2, 3]) == {}


def test_values_cited_on_a_proof_copy_are_governed_in_the_corpus_join() -> None:
    """The live join: some values in the cut cities cite a proof copy and now
    stand under their sections' notes. Zero would mean the follow broke."""
    proofs = ProvenanceStore().proofs()
    rows = [r for r in qualified("or/multnomah/troutdale") if _cited_lines(r.quote)[0] in proofs]
    assert rows
    assert all(n.doc not in proofs for r in rows for n in r.governing)
