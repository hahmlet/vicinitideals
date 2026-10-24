"""Squiggles in the code library: a cue under a misread word, not a queue.

Steph (2026-10-24): the word processor's wavy line under oddly spelled words,
so a reader browsing a page notices them. These hold the rules that keep it
quiet: English and the codes' own vocabulary pass, codes and short words are
never judged, and a word broken at a line end reads as the word.
"""

from __future__ import annotations

from flats.provenance.spelling import odd_words


def _odd(text: str, **kw) -> list[str]:
    return [text[a:b] for a, b in odd_words(text, **kw)]


def test_words_run_together_or_split_are_underlined() -> None:
    assert _odd("The setback from thelot line.") == ["thelot"]
    # "T avern": the capital split off by the extraction leaves "avern"
    assert _odd("A T avern or cocktail lounge.") == ["avern"]


def test_english_and_the_codes_own_vocabulary_pass() -> None:
    # "woonerf" and "rowhouse" are in no dictionary but in several cities' codes
    assert _odd("A rowhouse on a woonerf needs no setback.") == []


def test_codes_capitals_and_short_words_are_never_judged() -> None:
    assert _odd("Zone RML, see ORS 197A and McLoughlin Blvd; xq ok.") == []


def test_a_word_broken_at_a_line_end_reads_as_the_word() -> None:
    assert _odd("not neces-sarily located") == []
    # a real hyphenated word with a misread part is still caught
    assert _odd("a two-storey thelot-wide wall") == ["thelot"]


def test_a_word_the_caller_knows_is_accepted() -> None:
    assert _odd("A minimarty here.", known=["minimarty"]) == []
    assert _odd("A minimarty here.") == ["minimarty"]
