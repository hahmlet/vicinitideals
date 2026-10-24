"""Words the readable text spells oddly: a cue for a reader, not a review queue.

The extraction splits words ("dri v ewa y s"), runs them together
("thelot") and drops letters. Steph (2026-10-24) asked for the word
processor's squiggle under such words in the code library -- something to
notice while browsing, nothing anyone must work through. A reader who agrees
says so with the page's "Suggest a correction" box.

A word is known when an English word list has it (pyspellchecker's, ~160k
words) or when the codes themselves use it: a lower-case word printed in two
or more jurisdictions' codes is the trade's vocabulary ("woonerf",
"rowhouse"), and a capitalised word printed twice anywhere in the codes is
a name (a street, a district, a neighbouring city). What is left is underlined; a false
squiggle costs a glance, so the rules lean toward saying nothing:

- words under three letters, all-capital words (zone codes, acronyms) and
  words with a capital after the first letter (names like "McLoughlin") are
  never underlined;
- a hyphenated word is judged by its parts, unless the parts run together
  are a word: that is a word broken at a printed line end ("neces-sarily"),
  which reads right.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from functools import lru_cache
from typing import Iterable

from flats.provenance.store import ProvenanceStore

#: A word as the readable text prints it: letters, hyphens between letters.
WORD = re.compile(r"[A-Za-z]+(?:-[A-Za-z]+)*")

#: Shorter words are abbreviations and section letters more often than words.
SHORTEST = 3


@lru_cache(maxsize=1)
def _english() -> frozenset[str]:
    from spellchecker import SpellChecker

    return frozenset(SpellChecker(distance=1).word_frequency.dictionary)


@lru_cache(maxsize=1)
def _corpus() -> tuple[frozenset[str], frozenset[str]]:
    """(lower-case words printed in 2+ jurisdictions, capitalised words printed twice or more)."""
    store = ProvenanceStore()
    where: dict[str, set[str]] = defaultdict(set)
    names: Counter[str] = Counter()
    # A cut chapter's proof copy repeats its sections word for word; counted
    # twice, every name printed once would pass as printed twice.
    proofs = set(store.proofs())
    for path in store.documents():
        if path in proofs:
            continue
        layer = store.layer_of(path)
        try:
            text = store.text_path(path).read_text(encoding="utf-8")
        except OSError:
            continue
        for word in WORD.findall(text):
            for part in word.split("-"):
                if part.islower():
                    where[part].add(layer)
                elif part[0].isupper() and part[1:].islower():
                    names[part] += 1
    shared = frozenset(w for w, layers in where.items() if len(layers) >= 2)
    return shared, frozenset(w for w, n in names.items() if n >= 2)


def _odd(part: str, english: frozenset[str], shared: frozenset[str], names: frozenset[str]) -> bool:
    if len(part) < SHORTEST or part.isupper() or not part[1:].islower():
        return False
    low = part.lower()
    if low in english or low in shared:
        return False
    return not (part[0].isupper() and part in names)


def odd_words(text: str, known: Iterable[str] = ()) -> list[tuple[int, int]]:
    """(start, end) of each word in ``text`` to underline, in order.

    ``known`` adds words to accept (for tests and callers with their own list).
    """
    english = _english()
    extra = frozenset(w.lower() for w in known)
    if extra:
        english = english | extra
    shared, names = _corpus()
    out = []
    for m in WORD.finditer(text):
        parts = m.group().split("-")
        if len(parts) > 1 and "".join(parts).lower() in english:
            continue
        at = m.start()
        for part in parts:
            if _odd(part, english, shared, names):
                out.append((at, at + len(part)))
            at += len(part) + 1
    return out


def warm() -> None:
    """Load the word list and count the corpus ahead of the first page."""
    _english()
    _corpus()


__all__ = ["SHORTEST", "WORD", "odd_words", "warm"]
