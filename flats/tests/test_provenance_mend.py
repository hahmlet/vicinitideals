"""The ligature mend (FOLLOWUPS 116): restore the letters, prove nothing else moved.

Gresham's code stored "fl", "fi", "ff", "ffi" as single Unicode glyphs, so
"floor" read as an underlined 'oor' and no search for the word found it. The
mend writes the glyphs out as letters and proves it three ways before
anything is written. These tests pin each proof: that it accepts the change
it exists for and refuses anything else.
"""

from __future__ import annotations

from datetime import date

import pytest

from flats.provenance import mend
from flats.provenance.store import Document, ProvenanceStore

FL, FI, FF, FFI = "ﬂ", "ﬁ", "ﬀ", "ﬃ"


def test_restore_writes_each_glyph_out_as_its_letters() -> None:
    assert mend.restore(f"{FL}oor area") == "floor area"
    assert mend.restore(f"a{FF}ordable {FFI}rst {FI}xtures") == "affordable ffirst fixtures"
    assert mend.restore("no glyph here") == "no glyph here"
    assert mend.glyphs(f"{FL}oor {FL}at {FF}") == 3


def test_restored_only_accepts_restored_letters_and_nothing_else() -> None:
    old = f"1. Ground {FL}oor height\n2. A{FF}ordable"
    assert mend.restored_only(old, mend.restore(old)) == []

    # A letter that changed beside the restored ones is refused...
    assert mend.restored_only(old, "1. Ground floor heights\n2. Affordable")
    # ...as is a glyph written out as the wrong letters...
    assert mend.restored_only(f"{FL}oor", "fioor")
    # ...a lost letter (the end-letter loss the brief asked to look for)...
    assert mend.restored_only(f"{FL}oor foot", "floor foo")
    # ...and a moved line, which would move every citation below it.
    assert mend.restored_only(old, "1. Ground floor height\n\n2. Affordable")


def test_the_second_reader_witness_tells_order_from_loss() -> None:
    assert mend.witness("a b\nc", "abc", n=1).verdict == "same"
    assert mend.witness("ab\ncd", "cd ab", n=2).verdict == "reordered"
    lost = mend.witness("the foo", "the foot", n=3)
    assert lost.verdict == "differs"
    assert lost.fresh_only == "t"
    # A slice's edge page prints more than the slice holds; that is not a loss...
    assert mend.witness("6.03 DRIVEWAYS", "6.02 X 6.03 DRIVEWAYS", n=4, edge=True).verdict == "within"
    # ...but a letter the page does not print still is, edge or not.
    assert mend.witness("6.03 DRIVEWAYSZ", "6.02 X 6.03 DRIVEWAYS", n=5, edge=True).verdict == "differs"


def test_every_restored_word_must_be_a_word_the_page_prints() -> None:
    page = f"Ground {FL}oor and a{FF}ordable"
    assert mend.words_found(page, "Ground floor and affordable") == (2, [])
    # Spaced differently by the second reader is still the same word.
    assert mend.words_found(page, "Ground fl oor and aff ordable") == (2, [])
    assert mend.words_found(page, "Ground fixtures and affordable") == (1, ["floor"])


def test_a_proof_needs_every_check_to_hold() -> None:
    clean = mend.Mended(path="x.txt", glyphs=1, reextracted=True,
                        pages=[mend.PageCheck(1, "same"), mend.PageCheck(2, "reordered")])
    assert clean.proved
    assert not mend.Mended(path="x.txt", reextracted=False).proved
    assert not mend.Mended(path="x.txt", reextracted=True, missing=["p1 floor"]).proved
    assert not mend.Mended(path="x.txt", reextracted=True, pages=[mend.PageCheck(1, "differs")]).proved
    assert not mend.Mended(path="x.txt", reextracted=True, problems=["line 1"]).proved


def test_a_reading_survives_a_card_that_only_lost_lines() -> None:
    old = f"10\tGround {FL}oor 12 feet\n11\tlighting {FI}xtures 18 feet\n12\t20 percent"
    # The same body, letters restored: the reading stands.
    assert mend.narrowed(old, mend.restore(old))
    # A restored word let the survey see a line was already held: still stands.
    assert mend.narrowed(old, "10\tGround floor 12 feet\n12\t20 percent")
    # A line nobody read: reopened.
    assert not mend.narrowed(old, "10\tGround floor 12 feet\n13\t30 feet")
    # A line that changed by more than its letters: reopened.
    assert not mend.narrowed(old, "10\tGround floor 14 feet")


def _doc(text: str, extractor: str) -> Document:
    return Document(path="x.txt", url="u", retrieved=date(2026, 10, 29), sha256="", text=text,
                    extractor=extractor)


def test_an_older_text_without_glyphs_is_still_current() -> None:
    from flats.provenance.fetch import EXTRACTOR, current

    assert EXTRACTOR == "flats-html-text/9"
    assert current(_doc("floor", EXTRACTOR))
    # /9 changed nothing but glyphs, so a /8 text with none is what /9 stores...
    assert current(_doc("floor", "flats-html-text/8"))
    # ...and one that still holds a glyph is listed for re-extraction.
    assert not current(_doc(f"{FL}oor", "flats-html-text/8"))
    assert not current(_doc("floor", "flats-html-text/7"))


def test_the_pdf_extraction_restores_the_letters(monkeypatch: pytest.MonkeyPatch) -> None:
    import pypdf

    from flats.provenance.fetch import pdf_to_text

    class _Page(dict):
        def __init__(self) -> None:
            super().__init__({"/Contents": object()})

        def extract_text(self, **_: object) -> str:
            return f"Ground {FL}oor area, a{FF}ordable"

    monkeypatch.setattr(pypdf, "PdfReader", lambda _stream: type("R", (), {"pages": [_Page()]})())

    text = pdf_to_text(b"%PDF-not-really")

    assert "Ground floor area, affordable" in text
    assert mend.glyphs(text) == 0


def test_no_stored_document_holds_a_ligature_glyph() -> None:
    # Gresham's three were the only ones in the corpus (1,112 glyphs, mended
    # 2026-10-29). A new one means a document reached the store by a path that
    # does not restore them.
    store = ProvenanceStore()
    held = [p for p in store.fetched() if mend.glyphs(store.load(p).text)]
    assert held == []


def test_gresham_reads_floor_where_the_glyph_stood() -> None:
    store = ProvenanceStore()
    text = store.load("or/multnomah/gresham/4.1100.downtown.txt").text
    assert "floor" in text.lower()
    assert "affordable" in text.lower()
