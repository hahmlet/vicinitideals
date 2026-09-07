"""The second reading has one safety property and it is not about accuracy.

If the encoded figure reaches the reader's card, the exercise is worthless: a
reader who can see the answer will find the sentence that supports it, and the
result will be 1,902 agreements that mean nothing. So the assertions here are
mostly about what is *absent* from a card, and about the card reaching far
enough up a wide table to see which column it is standing in -- the defect that
produced every false alarm in the 2026-09-07 run.
"""

from __future__ import annotations

import pytest

from flats.encode.reread import (
    CONTEXT,
    HEADER_LINES,
    _passage,
    _ranges,
    score,
    work_list,
)
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


@pytest.fixture(scope="module")
def built(store: ProvenanceStore):
    return work_list(load_rules(), store)


# --- the blindness invariant ------------------------------------------------


def test_no_card_carries_the_number_it_is_asking_about(built) -> None:
    """The whole exercise rests on this one.

    A card is allowed to contain the encoded figure only where the code's own
    page contains it -- which is the point -- so the check is on the fields the
    card writes ABOUT the value: the zone, the standard's name and the
    condition being encoded. `definition` is excluded because it is the field
    registry's prose, identical in every card for that field and free to carry
    an example figure of its own; `cited_lines` is excluded because it is line
    numbers.
    """
    cards, key, _ = built
    answers = {k["id"]: k for k in key}
    for card in cards:
        encoded = str(answers[card["id"]]["encoded"])
        told = " ".join(str(card[f]) for f in ("zone", "field", "standard", "condition"))
        assert encoded not in told.split(), (card["id"], encoded)


def test_the_card_and_the_answer_share_an_id_and_nothing_else(built) -> None:
    cards, key, _ = built
    assert [c["id"] for c in cards] == [k["id"] for k in key]
    assert len({c["id"] for c in cards}) == len(cards)
    assert not set(cards[0]) & set(key[0]) - {"id", "layer", "zone", "field"}


def test_the_reader_is_told_whether_the_standard_is_a_floor_or_a_ceiling(built) -> None:
    """A reader with the sense backwards reports the wrong number off the right
    sentence, and the score cannot tell that apart from a misreading."""
    cards, _, _ = built
    described = [c for c in cards if c["definition"]]
    assert len(described) > len(cards) * 0.9
    assert any("MAXIMUM" in c["definition"] for c in described)
    assert any("MINIMUM" in c["definition"] for c in described)


# --- reaching the column headings -------------------------------------------


def test_a_card_reaches_the_caption_of_the_table_it_stands_in() -> None:
    """Gresham's Table 4.0131 is why `CONTEXT` is not six.

    Eleven column headings printed one per line, then rows. At six lines of
    context a citation into the body of that table could not see a single
    heading, and three readings came back saying honestly that they could not
    tell which cell was which. Every one of them was a false alarm on a
    correctly encoded number, which is the expensive kind.
    """
    whole = [f"line {n}" for n in range(1, 101)]
    whole[9] = "Table 4.0131 Setbacks"  # L10
    shown = _passage(whole, [(80, 81)], context=6, caption_at=10)
    text = "\n".join(shown)
    assert "Table 4.0131" in text, "the caption is what says which table this is"
    assert ">> L80" in text and ">> L81" in text
    assert "      ..." in text, "the elision has to be visible or the card lies"
    assert "L50" not in text, "the header block comes down, not the whole table"


def test_a_caption_too_far_above_does_not_drag_the_whole_table_in() -> None:
    """A hundred lines of table between the caption and the cited row is a card
    nobody reads, so past `CAPTION_REACH` the caption is reported in
    ``headings`` alone."""
    whole = [f"line {n}" for n in range(1, 400)]
    whole[9] = "Table 4.0131 Setbacks"
    shown = _passage(whole, [(300, 300)], context=6, caption_at=10)
    assert "Table 4.0131" not in "\n".join(shown)
    assert len(shown) <= 2 * 6 + 1


def test_the_default_context_is_wide_enough_for_a_stacked_header() -> None:
    assert CONTEXT >= 11, "Table 4.0131 prints eleven column headings, one per line"
    assert HEADER_LINES >= 11


# --- citation shapes --------------------------------------------------------


@pytest.mark.parametrize(
    "ref, spans",
    [
        ("a/b.txt#L12", [(12, 12)]),
        ("a/b.txt#L12-L18", [(12, 18)]),
        ("a/b.txt#L12,L18-L20", [(12, 12), (18, 20)]),
        ("a/b.txt#L403,L408-L409", [(403, 403), (408, 409)]),
        ("a/b.txt", []),
    ],
)
def test_every_citation_shape_in_the_corpus_parses(ref, spans) -> None:
    """The multi-range shape is the one that has broken four things already."""
    assert _ranges(ref) == spans


# --- scoring ----------------------------------------------------------------


def _key(encoded):
    return [
        {
            "id": "00001",
            "layer": "or/x",
            "zone": "R7",
            "row": "setback_front_ft",
            "field": "setback_front_ft",
            "quote": "or/x/1.txt#L1",
            "encoded": encoded,
        }
    ]


@pytest.mark.parametrize(
    "encoded, answer, verdict",
    [
        (20, {"figure": 20}, "agree"),
        (20, {"figure": 20.0}, "agree"),
        (20, {"figure": 15}, "disagree"),
        (20, {"figure": 15, "alternatives": ["20 ft where an alley abuts"]}, "agree_alt"),
        (20, {"figure": None}, "unread"),
        ("a curve", {"figure": 20}, "unscored"),
        (20, None, "missing"),
    ],
)
def test_the_verdict_says_which_of_six_things_happened(encoded, answer, verdict) -> None:
    answers = {"00001": answer} if answer is not None else {}
    assert score(_key(encoded), answers)[0]["verdict"] == verdict


def test_a_doubt_survives_an_agreement() -> None:
    """Gresham's four downtown districts were caught by a reader who handed
    back the right number and said the passage names a different zone. If a
    flag could not outlive an `agree`, that finding would have been thrown
    away."""
    row = score(
        _key(0),
        {"00001": {"figure": 0, "for_this_zone": False, "note": "row is townhouses only"}},
    )[0]
    assert row["verdict"] == "agree"
    assert "wrong_zone" in row["flags"]
    assert "noted" in row["flags"]


# --- what the corpus actually produces --------------------------------------


def test_the_work_list_covers_the_corpus_and_says_what_it_skipped(built) -> None:
    """Skips are counted rather than dropped: a citation this cannot turn into
    a card is a citation nobody will ever re-read, and that has to be visible."""
    cards, key, skipped = built
    assert len(cards) > 1_500
    assert len(cards) == len(key)
    assert set(skipped) == {"no_quote", "no_number", "drawn", "unresolved", "no_lines"}
    # An unresolvable citation means a document moved under a quote. None are
    # expected; the assertion is what makes a new one loud.
    assert skipped["unresolved"] == 0
    assert skipped["no_lines"] == 0


def test_every_card_shows_the_lines_it_cites(built) -> None:
    cards, _, _ = built
    for card in cards:
        assert any(line.startswith(">>") for line in card["passage"]), card["id"]
