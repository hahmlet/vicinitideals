"""The loose search: which lines could be the passage behind a held-out value.

The strict readers decide what gets written into a rule file, and they refuse
most of this corpus for reasons that have nothing to do with what the code
says — a cell reading "15/04 feet", a row written for five housing types, a
column headed with a range. This search refuses nothing. It exists so that a
person can be pointed at the line, and so the ledger can tell the two
afternoons apart: fetching a chapter nobody has, and reading one that is
already sitting in the store.
"""

from __future__ import annotations

import pytest

from flats.encode.find import passages

pytestmark = pytest.mark.unit

DOC = "or/clackamas/happy-valley/16.22.residential.txt"


def find(text: str, *, field: str, believed, limit: int = 60):
    return passages(text, path=DOC, field=field, believed=believed, limit=limit)


def test_a_number_is_matched_by_value_and_not_by_spelling() -> None:
    """A code prints 7,500 and a rule file stores 7500.

    Matching the spelling would miss the page the value came off, and the
    ledger would report a standard as unsourced with the sentence stating it
    two lines from a citation somebody already wrote.
    """
    text = "Minimum lot area: 7,500 sq. ft. per dwelling"

    found, _ = find(text, field="min_lot_sqft", believed=7500)

    assert [one.line for one in found] == [1]
    assert found[0].quote == f"{DOC}#L1"


def test_a_number_inside_a_longer_one_is_not_a_match() -> None:
    """OAR 660-046-0220 is a citation, not a 220-foot standard."""
    found, _ = find("as provided in OAR 660-046-0220", field="min_frontage_ft", believed=220)

    assert found == []


def test_a_permission_is_hunted_by_its_housing_type() -> None:
    """A boolean has no digits. What it has is the sentence somebody scans for."""
    text = "Quadplexes\nP7,8\nX\nAccessory structures are permitted outright\n"

    found, _ = find(text, field="quadplex_allowed", believed=True)

    assert [one.text for one in found] == ["Quadplexes"]


def test_a_row_outranks_the_prose_that_mentions_it() -> None:
    """Twenty paragraphs of definitions come before the table that answers it.

    Handed the matches in file order a searcher reads the preamble and stops,
    which is how a use table two hundred lines down goes unread in a document
    that was fetched, stored and searched.
    """
    text = "\n".join(
        [
            "Middle housing is defined in ORS 197.758.",
            "A middle housing land division is subject to Section 845.",
            "Quadplex   P   P   NP",
        ]
    )

    found, _ = find(text, field="quadplex_allowed", believed=True)

    assert found[0].line == 3
    assert found[0].row


def test_the_cells_under_a_flattened_row_travel_with_it() -> None:
    """In a linearised grid the match is the label and the answer is below it."""
    text = "Quadplexes\nP7,8\nP7,8\nX\nThe development of a quadplex is subject to Section 845.\n"

    found, _ = find(text, field="quadplex_allowed", believed=True)

    assert found[0].under == ("P7,8", "P7,8", "X")


def test_a_cut_list_says_how_much_it_cut() -> None:
    """A list that silently ends reads as a document that ends there.

    Which is how somebody comes to declare a chapter missing on the evidence of
    a page that was only ever showing them the top of a pile.
    """
    text = "\n".join(f"Lot size minimum 5,000 sq. ft. ({n})" for n in range(10))

    found, dropped = find(text, field="min_lot_sqft", believed=5000, limit=4)

    assert len(found) == 4
    assert dropped == 6
