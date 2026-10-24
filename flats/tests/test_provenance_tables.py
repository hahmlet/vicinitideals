"""Tables in the readable text (flats.provenance.tables): a tool proposes, the page and the proved lines check.

The checks know nothing of the right answer, so what is tested is that each
one catches the kind of wrong it is there for -- a word slid across a column
rule, a word left out, a word the lines do not hold -- and lets a right table
through. Tualatin is the city whose proposals are stored (FOLLOWUPS 115).
"""

from __future__ import annotations

import copy
import json

from flats.provenance.store import ProvenanceStore
from flats.provenance.tables import PROPOSED, _interleave, check, page_problems, tables

SECTION = "or/clackamas/tualatin/40/40.300.txt"


def _cell(row, col, text, box):
    return {"row": [row, row + 1], "col": [col, col + 1], "text": text, "header": False, "box": box}


def _proposal(cells, words, rules=()):
    return {"rows": 2, "cols": 2, "cells": cells, "words": words, "rules": list(rules)}


# Two columns split by a printed rule at x=100; one row.
_WORDS = [["Front", 10, 10, 40, 20], ["15", 110, 10, 120, 20], ["feet", 122, 10, 140, 20]]
_RULE = [[100, 0, 30]]


def test_a_right_two_column_row_has_no_page_problem():
    cells = [_cell(0, 0, "Front", [5, 5, 95, 25]), _cell(0, 1, "15 feet", [105, 5, 195, 25])]
    assert page_problems(_proposal(cells, _WORDS, _RULE)) == []


def test_a_cell_across_a_printed_column_rule_is_caught():
    # Gresham 4.1415B: a lost column, so one cell holds both sides of the rule.
    cells = [_cell(0, 0, "Front 15 feet", [5, 5, 195, 25])]
    problems = page_problems(_proposal(cells, _WORDS, _RULE))
    assert any("both sides of a printed column line" in p for p in problems)


def test_a_printed_word_in_no_cell_is_caught():
    cells = [_cell(0, 0, "Front", [5, 5, 95, 25]), _cell(0, 1, "15", [105, 5, 121, 25])]
    problems = page_problems(_proposal(cells, _WORDS, _RULE))
    assert any("in no cell" in p and "feet" in p for p in problems)


def test_overlapping_neighbour_columns_are_caught():
    words = [["Front", 10, 10, 60, 20], ["15", 50, 30, 70, 40]]
    cells = [_cell(0, 0, "Front", [5, 5, 62, 25]), {**_cell(1, 1, "15", [48, 28, 72, 42])}]
    problems = page_problems(_proposal(cells, words))
    assert any("columns 1 and 2 overlap" in p for p in problems)


def test_lines_read_across_are_split_back_into_cells_even_when_spaces_disagree():
    # Docling glues "Sale of" into "Saleof"; the lines are the row read across.
    cells = ["Saleof", "15feet"]
    words = [(1, "Sale"), (1, "15"), (2, "of"), (2, "feet")]
    assert _interleave(cells, words) == [[0, 2], [1, 3]]
    assert _interleave(cells, [(1, "Sale"), (1, "16"), (2, "of"), (2, "feet")]) is None


def _stored(page: int) -> dict:
    store = ProvenanceStore()
    raw = json.loads((store.root / "or/clackamas/tualatin" / PROPOSED).read_text(encoding="utf-8"))
    return raw["pages"][str(page)][0]


def test_table_40_3_is_shown_with_each_cell_on_its_printed_lines():
    found = {t.page: t for t in tables()[SECTION]}
    t = found[302]
    assert t.shown and (t.first, t.last) == (66, 97)
    lines = ProvenanceStore().load(SECTION).text.splitlines()
    # Every cell's words are on the lines it names, and no line is left out.
    used = set()
    for cell in t.cells:
        for word in cell.text.split():
            assert any(word in lines[n - 1].split() for n in cell.lines), (cell, word)
        used.update(cell.lines)
    assert used == set(range(66, 98))
    front = next(c for c in t.cells if c.text == "15 feet" and c.row[0] == 3)
    assert front.col[0] == 1


def test_a_garbled_page_is_held_not_shown():
    # p303: Docling ran the lot-size FAR rows together.
    t = next(t for t in tables()[SECTION] if t.page == 303)
    assert not t.shown and any("overlap" in p for p in t.problems)


def test_a_word_the_lines_do_not_hold_holds_the_table():
    store = ProvenanceStore()
    part = store.parts()[SECTION]
    lines = store.load(SECTION).text.splitlines()
    proposal = _stored(302)
    assert check(proposal, part, lines, 302).shown
    wrong = copy.deepcopy(proposal)
    cell = next(c for c in wrong["cells"] if c["text"].strip() == "15 feet")
    cell["text"] = "16 feet"
    held = check(wrong, part, lines, 302)
    assert not held.shown
    assert any("not exactly the words" in p for p in held.problems)
