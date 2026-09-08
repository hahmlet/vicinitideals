"""The dismissal re-read has one safety property and it is not accuracy.

If our reason for waving a footnote away reaches the reader's card, the
exercise is worthless: shown "detached dwellings only", a reader agrees with
it. So most of the assertions here are about what is *absent* from a card.

The awkward part, and the reason this file needs a real comparison rather than
a substring check: a good dismissal usually **quotes the note it dismisses**
before arguing about it. So the quoted half is on the card by design and the
argued half must never be, and telling them apart is the test.
"""

from __future__ import annotations

import json
import re

import pytest

from flats.encode.waved import DIRECTION, REACH, _standards, render, score, work_list

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def built():
    return work_list()


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", " ".join(text.lower().split()))


# --- the blindness invariant ------------------------------------------------


def test_no_card_carries_the_argument_we_made_about_the_note(built) -> None:
    """A reason may quote the note; it may never show the reasoning.

    Compared on the *tail* of the reason, which is where the argument lives --
    "... a different building type, and this layer does not encode it" -- and
    excluding anything already visible in the note or the passage, which is the
    half a dismissal is entitled to quote.
    """
    cards, key, _ = built
    reasons = {k["id"]: k["reason"] for k in key}
    leaked = []
    for card in cards:
        reason = _norm(reasons.get(card["id"], ""))
        if len(reason) < 50:
            continue
        page = _norm(card["note"] + " " + " ".join(card["passage"]))
        tail = reason[-60:]
        if tail in _norm(json.dumps(card)) and tail not in page:
            leaked.append(card["id"])
    assert not leaked, f"the dismissal's reasoning is visible on {leaked[:5]}"


def test_the_card_and_the_answer_share_an_id_and_nothing_else(built) -> None:
    cards, key, _ = built
    assert [c["id"] for c in cards] == [k["id"] for k in key]
    assert len(set(k["id"] for k in key)) == len(key)
    # The mark and the scope are on both halves on purpose -- a reader needs
    # to know which note this is and what it stands over. `reason` is the
    # answer and is the one field that must not cross.
    for card in cards:
        assert "reason" not in card
        assert "ruled_in" not in card


def test_no_key_row_is_missing_the_thing_being_checked(built) -> None:
    """A dismissal with no reason cannot exist -- ``dispositions`` refuses it --
    so a blank one here would mean this module lost it on the way."""
    _, key, _ = built
    assert all(k["reason"].strip() for k in key)


# --- what is on the card ----------------------------------------------------


def test_every_card_shows_the_note_and_what_it_stands_over(built) -> None:
    cards, _, _ = built
    for card in cards:
        assert card["note"].strip(), card["id"]
        assert card["governs"], card["id"]
        assert card["values_governed"] >= 1
        assert any(line.startswith(">>") for line in card["passage"]), card["id"]


def test_a_card_is_one_footnote_not_one_value(built) -> None:
    """The same sentence over eleven zones is one decision.

    Re-reading it eleven times would buy eleven copies of one answer, so the
    cards must be far fewer than the values behind them.
    """
    cards, key, _ = built
    behind = sum(k["values_governed"] for k in key)
    assert behind > len(cards) * 2
    identity = {(c["document"], c["cited_lines"], c["mark"]) for c in cards}
    assert len(identity) == len(cards)


def test_the_scope_line_names_a_zone_and_a_standard(built) -> None:
    cards, _, _ = built
    for line in cards[0]["governs"]:
        zone, _, standards = line.partition(": ")
        assert zone and standards


def test_standards_collapse_by_zone_and_sort() -> None:
    got = _standards(
        [("R-5", "max_height_ft"), ("R-5", "max_height_ft"), ("R-2", "setback_rear_ft")]
    )
    assert len(got) == 2
    assert got[0].startswith("R-2: ")
    assert got[1].startswith("R-5: ")


# --- scoring ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("reaches", "verdict"),
    [
        ("not_ours", "agree"),
        ("some_zones", "narrower"),
        ("reaches", "disagree"),
        ("", "missing"),
    ],
)
def test_the_verdict_is_about_the_dismissal_not_about_a_number(reaches, verdict) -> None:
    key = [{"id": "1", "reason": "x", "values_governed": 1, "doc": "d", "line": 1, "mark": "1"}]
    rows = score(key, {"1": {"reaches": reaches}} if reaches else {})
    assert rows[0]["verdict"] == verdict


@pytest.mark.parametrize(
    ("reaches", "direction", "alarming"),
    [
        ("reaches", "stricter", True),
        ("some_zones", "stricter", True),
        ("reaches", "looser", False),
        ("reaches", "neither", False),
        ("not_ours", "stricter", False),
        ("not_ours", "", False),
    ],
)
def test_only_a_restriction_we_waved_away_is_alarming(reaches, direction, alarming) -> None:
    """Dismissing a relaxation costs lots and never correctness.

    The trade this project makes everywhere, so it must not be reported as a
    fault or the real ones drown.
    """
    key = [{"id": "1", "reason": "x", "values_governed": 1, "doc": "d", "line": 1, "mark": "1"}]
    rows = score(key, {"1": {"reaches": reaches, "direction": direction}})
    assert rows[0]["alarming"] is alarming


def test_an_unanswered_card_is_missing_and_never_an_agreement() -> None:
    key = [{"id": str(n), "reason": "x", "values_governed": 1, "doc": "d", "line": 1, "mark": "1"} for n in range(3)]
    rows = score(key, {"1": {"reaches": "not_ours"}})
    assert [r["verdict"] for r in rows] == ["missing", "agree", "missing"]


def test_the_vocabularies_are_closed() -> None:
    assert set(REACH) == {"not_ours", "reaches", "some_zones"}
    assert set(DIRECTION) == {"stricter", "looser", "neither"}


def test_render_leads_with_the_restrictions_we_waved_away() -> None:
    key = [
        {"id": "1", "reason": "a relaxation", "values_governed": 9, "doc": "d", "line": 1, "mark": "4"},
        {"id": "2", "reason": "not our use", "values_governed": 2, "doc": "d", "line": 2, "mark": "5"},
    ]
    rows = score(
        key,
        {
            "1": {"reaches": "reaches", "direction": "stricter", "note": "reaches a fourplex"},
            "2": {"reaches": "not_ours", "direction": ""},
        },
    )
    text = render(rows)
    assert "WAVED AWAY BUT RESTRICTIVE: 1" in text
    assert "d#L1" in text
    assert "d#L2" not in text
