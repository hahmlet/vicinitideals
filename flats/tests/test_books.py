"""Showing the reviewer the actual page, without showing the wrong one.

Rendering a page beside an encoded number is a claim: *this sheet is where that
number is printed*. It only holds if the file rendered is the file the page map
counted. A codifier that reissues a publication renumbers everything after the
insertion, so page 239 of this year's edition and page 239 of last year's are
different sheets — and a viewer that shows the new one under an old citation
manufactures corroboration out of nothing.

So the book is identified by its own bytes, and a mismatch refuses.
"""

from __future__ import annotations

from datetime import date

import pytest

from flats.provenance import books, pages as P
from flats.provenance.store import ProvenanceStore

pytestmark = pytest.mark.unit

BOOK = [
    ["SECTION 4.0100", "RESIDENTIAL DISTRICTS", "[4.0100]-1"],
    ["Minimum front setback 10 feet", "[4.0100]-2"],
]
DATA = b"%PDF-1.7 pretend this is a book"
OTHER = b"%PDF-1.7 a later edition, renumbered"


@pytest.fixture
def stored(monkeypatch, tmp_path):
    """A document with text, a page map, and a cache nobody has filled."""
    monkeypatch.setattr(P, "_pages_of", lambda data, *, extraction="layout": BOOK)
    monkeypatch.setattr(books, "CACHE", tmp_path / "books")
    store = ProvenanceStore(tmp_path / "docs")
    text = "\n".join(line for page in BOOK for line in page) + "\n"
    store.save("or/x/doc.txt", url="https://example.test/x.pdf", text=text, retrieved=date(2026, 8, 15))
    P.write(store, P.index("or/x/doc.txt", DATA, text), extractor="test/1")
    return store


def test_a_book_is_fetched_once_and_kept(stored):
    calls = []

    def get(url):
        calls.append(url)
        return DATA

    first = books.ensure(stored, "or/x/doc.txt", get=get)
    second = books.ensure(stored, "or/x/doc.txt", get=get)

    assert first == second
    assert first.read_bytes() == DATA
    assert calls == ["https://example.test/x.pdf"], "the second view came from the cache"


def test_a_book_that_has_been_reissued_is_refused(stored):
    """The number may still be right. The page number is not.

    Refusing is the only honest answer: nothing here can tell whether the
    reissue moved the sheet the citation names, and rendering it either way
    would present a guess as evidence.
    """
    with pytest.raises(books.BookError, match="has changed"):
        books.ensure(stored, "or/x/doc.txt", get=lambda url: OTHER)


def test_a_stale_cache_is_replaced_rather_than_served(stored):
    """A cached file from before a reissue is the reissue's problem, not a fix."""
    books.save("https://example.test/x.pdf", OTHER)

    with pytest.raises(books.BookError, match="has changed"):
        books.ensure(stored, "or/x/doc.txt", get=lambda url: OTHER)

    assert not books.cache_path("https://example.test/x.pdf").is_file()


def test_a_document_with_no_page_map_shows_no_pages(monkeypatch, tmp_path):
    """No map means no line-to-page claim, so there is no page to render.

    Every HTML-served chapter in the corpus is in this state permanently, and
    the correct behaviour is to keep quoting lines rather than to invent a
    sheet.
    """
    monkeypatch.setattr(books, "CACHE", tmp_path / "books")
    store = ProvenanceStore(tmp_path / "docs")
    store.save("or/x/html.txt", url="https://example.test/c", text="a\nb\n", retrieved=date(2026, 8, 15))

    with pytest.raises(books.BookError, match="no page map"):
        books.ensure(store, "or/x/html.txt", get=lambda url: DATA)


def test_a_map_built_against_older_text_does_not_vouch_for_a_book(stored):
    """Re-fetching the text moves it out from under the map.

    The map's line numbers are then numbers in a document that no longer
    exists, and the book it was built from is the book behind those numbers —
    which is not the same as the book behind the current ones.
    """
    stored.save(
        "or/x/doc.txt",
        url="https://example.test/x.pdf",
        text="something else entirely\n",
        retrieved=date(2026, 8, 15),
    )

    assert books.expected(stored, "or/x/doc.txt") == ""


def test_an_error_page_served_with_a_200_is_not_cached(stored):
    """Codifiers answer a rate limit with HTML and a cheerful status code."""
    with pytest.raises(books.BookError, match="not a PDF"):
        books.ensure(stored, "or/x/doc.txt", get=lambda url: b"<html>slow down</html>")

    assert not books.cache_path("https://example.test/x.pdf").is_file()


def test_one_book_serves_every_document_read_out_of_it(stored):
    """Portland's 33.110 is cited by two jurisdictions; Troutdale's two chapters
    are two slices of one publication. Keying the cache by URL means one file."""
    assert books.cache_path("https://example.test/x.pdf") == books.cache_path(
        "https://example.test/x.pdf"
    )
    assert books.cache_path("https://example.test/x.pdf") != books.cache_path(
        "https://example.test/y.pdf"
    )
