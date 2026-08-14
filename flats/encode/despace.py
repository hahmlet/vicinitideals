"""Repair text a PDF extractor broke into pieces.

Municode serves its Oregon City chapters as a PDF, and the text layer of that
PDF is letter-spaced: kerning pairs come out as spaces, so ``17.08.040`` prints
as ``17. 08 . 04 0``, ten thousand square feet as ``1 0 , 000 squ are f eet``,
and forty percent as ``4 0%``. Nineteen thousand lines of it, stating the
dimensional standards of five zones in a city FLATS covers.

No reader can key on that. ``_MEASURE`` wants a number followed by a unit and
finds ``1`` followed by ``0``; ``_subject`` wants "minimum lot size" and finds
"Mi nimum lot s ize". The whole chapter reads as prose about nothing, which is
why it sat at thirty-five unsupported values with a document declared, fetched
and stored.

Two repairs, both conservative, and the asymmetry between them is the point:

*Numbers* are rejoined by shape. A space between two digits, or either side of
a comma or a decimal point between digits, is not something a code writes — no
standard is "1 0" — so joining is safe wherever the result is a number.

*Words* are rejoined only into a vocabulary. "squ are" becomes "square" because
``square`` is a word this system keys on; "are a" does not become "area" unless
``area`` is one too. Joining by shape alone would run "no more than" into
nonsense, and a repair that invents words is worse than no repair — it would
produce standards nobody wrote, cited to a line that does not say them.

Line count is never changed. A quote is a line number into the stored document,
and a repair that moved lines would silently re-point every citation in the
jurisdiction at the wrong text.
"""

from __future__ import annotations

import re

#: Spaces inside a number: "1 0 , 000", "4 0%", "3 5 feet", "17. 08 . 04 0".
_IN_NUMBER = re.compile(r"(?<=\d)\s+(?=[\d,.])|(?<=[\d][,.])\s+(?=\d)")

#: What a word may be rejoined into. Only terms the readers key on — a subject,
#: a unit, a qualifier, or a housing type — because a join that produces
#: anything else is a guess about a word nothing downstream reads.
_VOCABULARY = frozenset(
    """
    minimum maximum standard standards dimensional except exception excepting
    square feet foot percent acres acre
    lot lots area size width depth frontage coverage height yard yards setback
    setbacks front rear side street corner interior building buildings
    single family detached attached duplex triplex quadplex fourplex townhouse
    townhouses cottage cluster clusters middle housing dwelling dwellings unit
    units density porch garage parking accessory structure structures none all
    """.split()
)

#: The hallmark of a break. A run of tokens is only considered for joining
#: when one of them is too short to be a word on its own — "squ are", "Maxim
#: um", "f eet". Without it "single family" would join wherever the result
#: happened to be a term, which is a repair nobody asked for.
_SHORT = 3


def repair(line: str) -> str:
    """One line of letter-spaced text, put back together.

    Idempotent, and a no-op on text that was never broken: every join is
    licensed either by number shape or by the vocabulary, and text a normal
    extractor produced offers neither.
    """
    while True:
        # Each pass exposes the next break: in "1 0 , 000" the comma is not
        # preceded by a digit until the digits either side of the first space
        # have been joined, and a regex sees the string it was handed.
        repaired = _IN_NUMBER.sub("", line)
        if repaired == line:
            break
        line = repaired
    return _rejoin_words(line)


def _rejoin_words(line: str) -> str:
    out: list[str] = []
    tokens = line.split(" ")
    i = 0
    while i < len(tokens):
        token = tokens[i]
        joined, used = _longest_join(tokens, i)
        if joined is not None:
            out.append(joined)
            i += used
            continue
        out.append(token)
        i += 1
    return " ".join(out)


def _longest_join(tokens: list[str], start: int) -> tuple[str | None, int]:
    """The longest run from ``start`` that spells one word in the vocabulary.

    Longest rather than shortest: "s quare" and "squ are" both have to reach
    ``square``, and stopping at the first two-token match would leave a
    three-token split half-repaired.
    """
    head = tokens[start]
    if not head or not head[-1:].isalpha():
        return None, 0
    best: tuple[str, int] | None = None
    run = head
    short = len(_bare(head)) <= _SHORT
    for k in range(start + 1, min(start + 4, len(tokens))):
        piece = tokens[k]
        if not piece or not _bare(piece).isalpha():
            break
        run += piece
        short = short or len(_bare(piece)) <= _SHORT
        if len(_bare(run)) > 16:
            break
        word, punctuation = _split_trailing(run)
        if short and _in_vocabulary(word):
            best = (word + punctuation, k - start + 1)
    return best if best else (None, 0)


def _bare(token: str) -> str:
    return token.strip(".,;:()-")


def _in_vocabulary(word: str) -> bool:
    """Whether a joined run spells a term the readers key on.

    The tail after a hyphen counts on its own: "Single-fa mily" has to reach
    "Single-family", and only "family" is the word this system knows.
    """
    lowered = word.lower()
    return lowered in _VOCABULARY or lowered.rsplit("-", 1)[-1] in _VOCABULARY


def _split_trailing(word: str) -> tuple[str, str]:
    stripped = word.rstrip(".,;:")
    return stripped, word[len(stripped) :]


def repair_text(text: str) -> str:
    """Every line of a document, repaired, with the line count preserved."""
    return "\n".join(repair(line) for line in text.split("\n"))
