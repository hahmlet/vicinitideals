"""The passage as the city wrote it, with the city's meanings under it.

The rule this module lives or dies by: the text is not edited. Marks go in
the rendering, the stored bytes stay the citation, and the line numbers on
screen are the line numbers in the quote -- otherwise a reviewer reading a
marked passage and a reviewer reading the store are looking at two documents
and only one of them is the code.
"""

from __future__ import annotations

import pytest

from flats.encode.reading import CLOSE, OPEN, ReadingError, for_value, passage
from flats.rules.loader import load_rules

pytestmark = pytest.mark.unit

PORTLAND = "or/multnomah/portland"
CORNER = f"{PORTLAND}/33.910.definitions.txt#L701-L705"


def unmarked(text: str) -> str:
    return text.replace(OPEN, "").replace(CLOSE, "")


def test_the_city_text_is_returned_unedited() -> None:
    """Strip the marks and what is left has to be the stored line, character
    for character. A rendering that reflows or trims is a paraphrase, and a
    paraphrase cannot be a citation."""
    from flats.provenance.store import ProvenanceStore

    stored = ProvenanceStore().quote(CORNER).splitlines()
    shown = passage(CORNER, layer_id=PORTLAND)
    assert [unmarked(text) for _, text in shown.lines] == stored


def test_the_line_numbers_are_the_quotes_line_numbers() -> None:
    shown = passage(CORNER, layer_id=PORTLAND)
    assert shown.lines[0][0] == 701
    assert [n for n, _ in shown.lines] == list(range(701, 701 + len(shown.lines)))


def test_the_words_this_city_defined_are_marked() -> None:
    shown = passage(CORNER, layer_id=PORTLAND)
    marked = {entry.term.lower() for entry in shown.legend}
    assert "corner lot" in marked
    assert "street" in marked
    assert any(f"{OPEN}Corner Lot{CLOSE}" in text for _, text in shown.lines)


def test_the_legend_carries_the_whole_definition_not_its_first_line() -> None:
    """A body captured one line deep stops mid-clause, and a legend of
    half-definitions is worse than none -- it reads as a meaning that was
    consulted. Portland's corner lot runs five lines and the 120-degree curve
    rule, which is the operative half, is on the third."""
    shown = passage(CORNER, layer_id=PORTLAND)
    corner = next(e for e in shown.legend if e.term.lower() == "corner lot")
    assert "120 degrees or less" in corner.text
    assert corner.text.endswith("A corner lot may also be a through lot.")


def test_each_meaning_names_the_line_it_came_from() -> None:
    shown = passage(CORNER, layer_id=PORTLAND)
    for entry in shown.legend:
        assert entry.quote.startswith(f"{PORTLAND}/")
        assert "#L" in entry.quote


def test_a_marked_term_is_listed_once_however_often_it_appears() -> None:
    shown = passage(CORNER, layer_id=PORTLAND)
    terms = [entry.term.lower() for entry in shown.legend]
    assert len(terms) == len(set(terms))


def test_a_reviewer_can_start_from_the_number_rather_than_the_citation() -> None:
    layer = load_rules()[PORTLAND]
    zone, field = next(
        (code, name)
        for code, z in sorted(layer.zones.items())
        for name, value in sorted(z.values.items())
        if value.prov.quote
    )
    shown = for_value(PORTLAND, zone, field)
    assert shown.quote == layer.zones[zone].values[field].prov.quote


def test_a_value_that_does_not_exist_says_so() -> None:
    with pytest.raises(ReadingError, match="no value carrying a quote"):
        for_value(PORTLAND, "NOT-A-ZONE", "setback_front_ft")


def test_a_quote_with_nothing_stored_behind_it_says_so() -> None:
    with pytest.raises(ReadingError, match="nothing stored"):
        passage(f"{PORTLAND}/no-such-document.txt#L1-L2", layer_id=PORTLAND)


def test_the_rendering_puts_the_meanings_in_the_same_buffer_as_the_standard() -> None:
    """The point of the whole module. A human may skim the legend; an agent
    reading this text has already been handed the meanings, so ignoring them
    is a choice somebody made rather than a lookup nobody did."""
    text = passage(CORNER, layer_id=PORTLAND).render()
    assert "Defined by this jurisdiction" in text
    assert "120 degrees or less" in text
    assert "701 |" in text
