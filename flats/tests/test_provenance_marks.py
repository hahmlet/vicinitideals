"""Raised characters in the readable text (flats.provenance.marks): found by context, never guessed.

A superscript in the stored text is an ordinary character: "15" with a raised
"8" reads "158". What is tested is that a mark is placed only where its
printed context is unique, that one printed against a number is called out,
that a footnote is linked only when the book makes the link plain, and that no
encoded value took a raised mark as a digit.
"""

from __future__ import annotations

from decimal import Decimal

from flats.provenance.marks import Mark, marks, misread, place, run_on
from flats.provenance.store import ProvenanceStore

LINES = [
    "Rear Yard Minimum 15 158 Feet",
    "Front Yard Minimum 20 None",
    "Notes:",
    "8 Applies to lots abutting a residential zone.",
]
# PDF page 7 starts on line 1. The book prints "15" with a raised "8" after it
# (the second 15 on the line), context in the PDF's own order.
BOOK = {7: (("8", "Minimum1515", "FeetFrontYard"),)}


def test_a_mark_is_placed_by_its_printed_context_and_called_out_against_a_number():
    [m] = place(LINES, [(7, 1)], BOOK)
    assert (m.line, m.start, m.end, m.text) == (1, 23, 24, "8")
    assert LINES[0][21:23] == "15" and m.glued
    assert run_on(LINES[0], m) == Decimal(158)


def test_a_footnote_under_a_notes_heading_is_linked():
    [m] = place(LINES, [(7, 1)], BOOK)
    assert m.note == 4


def test_a_mark_whose_context_is_not_unique_is_left_out():
    lines = ["15 158 x", "15 158 x"]
    book = {1: (("8", "15", "x"),)}
    assert place(lines, [(1, 1)], book) == []


def test_a_mark_on_a_page_the_document_does_not_hold_is_left_out():
    assert place(LINES, [(9, 1)], BOOK) == []


def test_a_raised_number_starting_a_line_numbers_the_note_it_starts():
    lines = ["Height 35 feet2", "2 Except on a flag lot."]
    book = {1: (("2", "Height35feet", "2Excepton"), ("2", "Height35feet2", "Excepton"))}
    found = place(lines, [(1, 1)], book)
    pointer = next(m for m in found if m.line == 1)
    numbers = next(m for m in found if m.line == 2)
    assert numbers.numbers_note and pointer.note == 2 and not pointer.glued


def test_run_on_reads_a_plain_line_the_way_a_reader_would():
    m = Mark(line=1, start=5, end=7, text="16", glued=True)
    assert run_on("1,500" + "16", m) == Decimal(150016)
    assert run_on("Front", Mark(1, 5, 6, "1", False)) is None


def test_tualatin_table_58_1_marks_point_to_their_note():
    store = ProvenanceStore()
    path = "or/clackamas/tualatin/58/58.200.txt"
    lines = store.load(path).text.splitlines()
    found = marks(path, store)
    assert found and all(m.text == "1" and lines[m.note - 1].startswith("1. New drive-through") for m in found)


def test_no_encoded_value_took_a_raised_mark_as_a_digit():
    assert misread() == []
