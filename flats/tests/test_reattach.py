"""Reading decisions go back on their section only where the words are the same."""

from __future__ import annotations

import pytest

from flats.encode.reattach import NewCard, OldCard, _rekey, plan
from flats.rules.model import Reading

PROOF = "or/test/town/17.10.r-7.txt"


def _reading(fp: str) -> Reading:
    return Reading(queue="missed", outcome="not_here", note="A housing type this screen does not place.",
                   fingerprint=fp)


def test_a_decision_carries_only_onto_the_same_words() -> None:
    old = [
        OldCard("17.10.r-7.txt#17.10.055", PROOF, "17.10.055", "aaaa", frozenset({40, 41})),
        OldCard("17.10.r-7.txt#17.10.060", PROOF, "17.10.060", "bbbb", frozenset({50})),
        OldCard("17.10.r-7.txt#17.10.070", PROOF, "17.10.070", "cccc", frozenset({60})),
        OldCard("17.10.r-7.txt#17.10.080", PROOF, "17.10.080", "dddd", frozenset({70})),
    ]
    new = [
        # the same proof-copy lines: the same words
        NewCard("17.10.055.txt#17.10.055", "1111", PROOF, "17.10.055", frozenset({40, 41})),
        # a sentence now shows a line nobody read
        NewCard("17.10.060.txt#17.10.060", "2222", PROOF, "17.10.060", frozenset({50, 51})),
        NewCard("17.10.070.txt#17.10.070", "3333", PROOF, "17.10.070", frozenset({60})),
    ]
    readings = {
        "17.10.r-7.txt#17.10.055": _reading("aaaa"),
        "17.10.r-7.txt#17.10.060": _reading("bbbb"),
        # already loose before the cut: its card had changed under it
        "17.10.r-7.txt#17.10.070": _reading("old!"),
        # its section has no unread lines now
        "17.10.r-7.txt#17.10.080": _reading("dddd"),
        "17.10.r-7.txt#17.10.090": _reading("eeee"),
    }
    got = plan(readings, old, new)
    assert got.carried == [("17.10.r-7.txt#17.10.055", "17.10.055.txt#17.10.055", "1111")]
    why = dict(got.detached)
    assert "words changed" in why["17.10.r-7.txt#17.10.060"]
    assert "before the cut" in why["17.10.r-7.txt#17.10.070"]
    assert "no section file" in why["17.10.r-7.txt#17.10.080"]
    assert "no such card" in why["17.10.r-7.txt#17.10.090"]
    # once carried, the decision names a card that exists: nothing more to do
    readings["17.10.055.txt#17.10.055"] = readings.pop("17.10.r-7.txt#17.10.055")
    again = plan(readings, old, new)
    assert again.carried == []


def test_a_carried_decision_is_renamed_where_it_stands() -> None:
    lines = [
        "layer: or/test/town",
        "readings:",
        '  "17.10.r-7.txt#17.10.055":',
        "    queue: missed",
        "    outcome: not_here",
        "    note: >-",
        "      A housing type this screen does not place.",
        "    fingerprint: aaaa",
        "",
        '  "17.10.r-7.txt#17.10.060":',
        "    queue: missed",
        "    outcome: not_here",
        "    note: >-",
        "      Not ours.",
        "    fingerprint: bbbb",
        "zones:",
    ]
    got = _rekey(lines, "17.10.r-7.txt#17.10.055", "17.10.055.txt#17.10.055", "1111")
    assert got[2] == '  "17.10.055.txt#17.10.055":'
    assert got[7] == "    fingerprint: 1111"
    assert [a for a, b in zip(lines, got) if a != b] == [lines[2], lines[7]]
    with pytest.raises(ValueError, match="already carries"):
        _rekey(got, "17.10.r-7.txt#17.10.060", "17.10.055.txt#17.10.055", "2222")
