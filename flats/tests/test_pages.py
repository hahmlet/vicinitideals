"""The page map: what makes a citation quotable to somebody outside this system.

The map is derived by walking the stored text against a fresh page-by-page
extraction, so what these tests hold to is the walk: it lands on the right page,
it survives a chapter sliced out of the middle of a book, and it refuses rather
than approximates when the two texts have drifted apart. A page number that is
off by one is worse than no page number, because it sends a planner to the wrong
sheet with our name on it.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from flats.provenance import pages as P
from flats.provenance.store import ProvenanceError, ProvenanceStore


def _book(monkeypatch, pages: list[list[str]]) -> None:
    """Stand in for the PDF extraction with a known book."""
    monkeypatch.setattr(P, "_pages_of", lambda data, *, extraction="layout": pages)


BOOK = [
    ["SECTION 4.0100", "RESIDENTIAL DISTRICTS", "", "[4.0100]-1"],
    ["4.0113 TRANSITION RESIDENTIAL", "Minimum lot area 3,000 sq ft", "[4.0100]-2"],
    ["Minimum front setback 10 feet", "", "[4.0100]-3"],
]


def test_a_line_maps_to_the_page_it_was_printed_on(monkeypatch):
    _book(monkeypatch, BOOK)
    text = "\n".join(line for page in BOOK for line in page if line.strip()) + "\n"

    built = P.index("x.txt", b"%PDF-", text)

    assert [p.n for p in built.pages] == [1, 2, 3]
    assert [p.line for p in built.pages] == [1, 4, 7]
    assert built.at(5).n == 2, "a line in the middle of page 2"
    assert built.at(9).n == 3, "the last line"


def test_the_printed_label_is_read_off_the_page(monkeypatch):
    _book(monkeypatch, BOOK)
    text = "\n".join(line for page in BOOK for line in page if line.strip()) + "\n"

    built = P.index("x.txt", b"%PDF-", text)

    # What a code cites is the sheet's own number, not the PDF's page count.
    assert [p.label for p in built.pages] == ["[4.0100]-1", "[4.0100]-2", "[4.0100]-3"]
    assert built.pages[1].cite == "p. [4.0100]-2"


def test_a_page_with_no_printed_number_says_which_pdf_page_it_is():
    assert P.Page(n=7, line=1).cite == "PDF page 7"


def test_a_chapter_sliced_out_of_a_book_still_lands_on_the_right_page(monkeypatch):
    """Documents are declared with start/end markers, so the store holds a slice."""
    _book(monkeypatch, BOOK)
    text = "\n".join(line for page in BOOK[1:] for line in page if line.strip()) + "\n"

    built = P.index("x.txt", b"%PDF-", text)

    assert [p.n for p in built.pages] == [2, 3], "the slice starts on page 2 of the book"
    assert built.at(1).n == 2


def test_a_slice_that_starts_mid_line_still_maps(monkeypatch):
    """Documents are cut at a phrase, not at a line break.

    Multnomah County's LR-7 chapter is declared to start at "39.4848 PURPOSE",
    which sits partway along a line, so the stored document's first line is a
    fragment of the source's. Requiring an exact match at the ends refuses a
    document that is perfectly intact.
    """
    _book(monkeypatch, BOOK)
    text = "TRANSITION RESIDENTIAL\nMinimum lot area 3,000 sq ft\n[4.0100]-2\nMinimum front\n"

    built = P.index("x.txt", b"%PDF-", text)

    assert [p.n for p in built.pages] == [2, 3]


def test_a_span_across_a_page_break_names_both_pages(monkeypatch):
    """A table straddling a break is the normal case, not an edge one."""
    _book(monkeypatch, BOOK)
    text = "\n".join(line for page in BOOK for line in page if line.strip()) + "\n"

    built = P.index("x.txt", b"%PDF-", text)

    assert [p.n for p in built.span(5, 8)] == [2, 3]
    assert [p.n for p in built.span(5, 6)] == [2], "one page, named once"


def test_a_source_that_has_moved_on_is_refused_not_approximated(monkeypatch):
    _book(monkeypatch, BOOK)
    text = "SECTION 4.0100\nRESIDENTIAL DISTRICTS\nMinimum lot area 4,000 sq ft\n"

    with pytest.raises(ProvenanceError, match="no longer matches"):
        P.index("x.txt", b"%PDF-", text)


def test_a_map_of_text_that_has_since_been_refetched_is_not_returned(tmp_path, monkeypatch):
    """The map is bound to the text it was built from.

    Serving it after a re-fetch would put a confident page number against a
    sentence that has moved, which is the one failure this whole file exists to
    prevent.
    """
    _book(monkeypatch, BOOK)
    store = ProvenanceStore(tmp_path)
    text = "\n".join(line for page in BOOK for line in page if line.strip()) + "\n"
    store.save("x.txt", url="https://example.gov/x.pdf", text=text, retrieved=date.today())
    P.write(store, P.index("x.txt", b"%PDF-", text), extractor="flats-html-text/3")
    assert P.read(store, "x.txt") is not None

    store.save(
        "x.txt",
        url="https://example.gov/x.pdf",
        text=text.replace("3,000", "4,000"),
        retrieved=date.today(),
    )

    assert P.read(store, "x.txt") is None, "an amended document has no map until it is remade"


def test_the_sidecar_is_readable_by_something_that_is_not_this_module(tmp_path, monkeypatch):
    _book(monkeypatch, BOOK)
    store = ProvenanceStore(tmp_path)
    text = "\n".join(line for page in BOOK for line in page if line.strip()) + "\n"
    store.save("x.txt", url="https://example.gov/x.pdf", text=text, retrieved=date.today())

    P.write(store, P.index("x.txt", b"%PDF-", text), extractor="flats-html-text/3")

    raw = json.loads(P.sidecar(store, "x.txt").read_text(encoding="utf-8"))
    assert raw["pages"][0] == {"n": 1, "line": 1, "label": "[4.0100]-1"}
    assert raw["extractor"] == "flats-html-text/3"


@pytest.mark.parametrize(
    "furniture, label",
    [
        ("[4.0100]-2", "[4.0100]-2"),
        ("[4.0100]                          -2", "[4.0100]-2"),
        ("Page 12", "12"),
        ("33-14", "33-14"),
        ("Page 3 of 44", "3"),
        ("Minimum lot area 3,000 square feet", ""),
        ("10", "10"),
        ("28-5 (Oregon City 4/01)", "28-5"),
        ("9 Oregon City Supp. No. 31", "9"),
        ("2 8 - 5 ( O r e g o n C i t y 4 / 0 1 )", "28-5"),
        ("5 Minimum lot area shall be 3,000 square feet", ""),
    ],
)
def test_page_furniture_is_told_apart_from_a_standard(furniture, label):
    """A bare number in a table is a standard; one in the footer is a page.

    The distinction is positional, which is why only the first and last few
    lines of a page are ever read this way.
    """
    assert P._label(["body text"] * 8 + [furniture]) == label
