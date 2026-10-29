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
from flats.provenance.tables import PROPOSED, RULED, _interleave, boxed, check, contents_list, page_problems, tables

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


def _stored(page: int, name: str = PROPOSED, k: int = 0) -> dict:
    store = ProvenanceStore()
    raw = json.loads((store.root / "or/clackamas/tualatin" / name).read_text(encoding="utf-8"))
    return raw["pages"][str(page)][k]


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


def test_a_garbled_proposal_is_refused_and_the_rules_reading_shown_instead():
    # p303: Docling ran the lot-size FAR rows together; the table cut along
    # the printed rules passes the same checks and is the one drawn.
    store = ProvenanceStore()
    part = store.parts()[SECTION]
    lines = store.load(SECTION).text.splitlines()
    refused = check(_stored(303), part, lines, 303)
    assert not refused.shown and any("overlap" in p for p in refused.problems)
    t = next(t for t in tables()[SECTION] if t.page == 303)
    assert t.shown and t.tool.startswith("pdfplumber") and (t.first, t.last) == (98, 116)


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


CN = "or/clackamas/tualatin/51/51.200.txt"


def _cn():
    store = ProvenanceStore()
    return store.parts()[CN], store.load(CN).text.splitlines()


def test_a_chapter_list_of_sections_is_not_a_table():
    # Docling proposes "TDC | 51.100. | Purpose." rows as a table; the use
    # table on the next page is one.
    assert contents_list(_stored(351))
    assert not contents_list(_stored(352))
    assert all(t.page != 351 for t in tables().get("or/clackamas/tualatin/50/50.310.txt", ()))


def test_a_rule_printed_as_a_thick_short_stroke_is_a_column_rule():
    # Tualatin draws column rules as 0.5 pt strokes 13 pt thick: x = 225, 326.
    xs = {round(r[0]) for r in _stored(352)["rules"]}
    assert {225, 326} <= xs


def test_a_word_docling_put_in_the_next_row_is_refused_and_the_ruled_table_drawn():
    # Table 51-1: Docling moved "limitation, see TDC 51.210(3)." down into
    # Community Services; the rows then overlap on the page.
    part, lines = _cn()
    assert not check(_stored(352), part, lines, 352).shown
    t = next(t for t in tables()[CN] if t.page == 352)
    assert t.shown and t.tool.startswith("pdfplumber") and (t.first, t.last) == (10, 33)
    services = next(c for c in t.cells if c.text.startswith("Permitted uses limited to: General"))
    assert services.text.endswith("see TDC 51.210(3).")


def _by_hand(proposal: dict) -> dict:
    """A proposal as a person writes it: the cells' words, no positions."""
    return {**proposal, "cells": [{**c, "box": None} for c in proposal["cells"]], "tool": "by hand: test"}


def test_a_correction_without_positions_takes_its_boxes_from_the_printed_words():
    part, lines = _cn()
    hand = _by_hand(_stored(352, RULED))
    assert all(c.get("box") for c in boxed(hand)["cells"])
    assert check(hand, part, lines, 352).shown


def test_a_correction_that_repeats_docling_s_mistake_is_refused():
    part, lines = _cn()
    hand = _by_hand(_stored(352, RULED))
    cells = hand["cells"]
    moved = "limitation, see TDC 51.210(3)."
    retail = next(c for c in cells if c["text"].startswith("Permitted uses limited to: General"))
    community = next(c for c in cells if c["text"].startswith("Permitted uses limited to a community"))
    retail["text"] = retail["text"].replace(" " + moved, "")
    community["text"] = moved + " " + community["text"]
    assert not check(hand, part, lines, 352).shown


def test_a_correction_with_a_typo_is_refused():
    part, lines = _cn()
    hand = _by_hand(_stored(352, RULED))
    cell = next(c for c in hand["cells"] if c["text"] == "Community Services")
    cell["text"] = "Community"
    problems = check(hand, part, lines, 352).problems
    assert any("read across" in p for p in problems)



def test_a_table_a_person_found_wrong_is_refused_and_one_found_right_says_so():
    from flats.provenance.tables import _judged

    t = next(t for t in tables()[CN] if t.page == 352)
    said = {"page": 352, "box": list(t.box), "tool": t.tool, "by": "Steph", "date": "2026-10-25"}
    assert _judged(t, [{**said, "verdict": "right"}]).reviewed == "Steph 2026-10-25"
    wrong = _judged(t, [{**said, "verdict": "right"}, {**said, "verdict": "wrong", "note": "rows swapped"}])
    assert not wrong.shown and "Steph 2026-10-25 found it wrong on the page: rows swapped" in wrong.problems
    # A verdict on another reader's table says nothing about this one.
    assert _judged(t, [{**said, "tool": "docling", "verdict": "wrong"}]).shown


def test_a_city_printed_as_several_books_names_one_set_of_files_per_book():
    from pathlib import Path

    from flats.provenance.tables import CORRECTED, REVIEWED, companions

    here = Path("city")
    assert companions(here / PROPOSED) == (here / CORRECTED, here / RULED, here / REVIEWED)
    named = companions(here / "tables.4.1400.proposed.json")
    assert [p.name for p in named] == [
        "tables.4.1400.corrected.json",
        "tables.4.1400.proposed.ruled.json",
        "tables.4.1400.reviewed.json",
    ]


def test_each_book_s_tables_land_only_on_sections_printed_in_that_book():
    # Gresham prints its code as seventeen PDFs, one per chapter, so "page 5"
    # names seventeen pages; each book's proposals sit in their own file.
    from flats.provenance.books import expected

    store = ProvenanceStore()
    city = store.root / "or/multnomah/gresham"
    files = {json.loads(p.read_text(encoding="utf-8"))["book"]: p.name for p in city.glob("tables.*.proposed.json")}
    assert len(files) > 10
    found = {k: v for k, v in tables(store).items() if k.startswith("or/multnomah/gresham/")}
    assert sum(len(v) for v in found.values()) > 50
    for section, drawn in found.items():
        book = expected(store, store.parts()[section].proof)
        assert book in files, section
        raw = json.loads((city / files[book]).read_text(encoding="utf-8"))
        for t in drawn:
            assert str(t.page) in raw["pages"], (section, t.page)
    # Pleasant Valley's residential use table, from its own book, drawn.
    assert any(t.shown and t.page == 5 for t in found["or/multnomah/gresham/4/4.1413.txt"])
