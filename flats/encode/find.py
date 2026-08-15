"""Every line in a jurisdiction's code that could be the passage behind a value.

The corroboration readers answer a narrow question — *does a table cell, in this
zone's column, state this number?* — and answer it strictly, because what they
produce gets written into a rule file. Most of the corpus fails that test for
reasons that have nothing to do with whether the code says it: the cell reads
"15/04 feet", the row is written for five housing types at once, the column
header is a range ("R-5 – R-30"), the table lost its geometry to HTML.

A person reading the page settles every one of those in seconds. What they need
is not a stricter reader — it is the page, and the line on it. So this module
answers the loose question the strict readers cannot: *which lines in this
jurisdiction's own documents print this answer at all?*

Nothing here is ever written to a rule file. A match is a lead, and the two
consumers use it as one:

* the gaps ledger, to tell "no stored document states this — go find the
  chapter" apart from "a document states it and no reader would claim it",
  which are an afternoon and two minutes respectively;
* the review UI, to put those lines in front of whoever is doing the reading.

Matching is deliberately loose, and in two shapes. A number is compared by
value rather than by spelling, so 7,500 and 7500.0 are the same standard and a
search for the encoding's spelling does not miss the page's. A boolean has no
digits at all; what it has is the housing type and the words a code grants it
with, which is the sentence somebody would scan for.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Sequence

from flats.rules.fields import FIELDS

#: A number as a document prints one: 7,500 and 7500 and 7500.0.
_PRINTED = re.compile(r"(?<![\d.,])\d[\d,]*(?:\.\d+)?")

#: A line that opens with what it is about, which is how a table row reads. The
#: rank exists because a code names a housing type in twenty paragraphs of
#: definitions before the table that answers the question, and a searcher
#: handed the matches in file order reads the preamble and stops.
_ROW_START = re.compile(
    r"^(?:quad[- ]?plex|four[- ]?plex|minimum|maximum|front|rear|side|street|lot|building)\b",
    re.I,
)

#: The housing types a four-unit attached building is permitted as, and the
#: statutory phrase most Oregon cities adopted instead of listing them.
_TYPE = re.compile(r"quad[- ]?plex|four[- ]?plex|middle housing", re.I)

#: How far under a match to read. A use-table row answers for as many zones as
#: the table has columns, and eleven is the widest in this corpus.
_UNDER = 12

#: How many matching lines to read before giving up on reading them all. A
#: jurisdiction whose code says "lot" nine hundred times is not a search worth
#: finishing, and by then the ranking has found what it was going to find.
_SWEEP = 600


@dataclass(frozen=True, slots=True)
class Passage:
    """One line proposed as the passage behind a value, and where it sits."""

    document: str
    line: int
    text: str
    #: ``path#L12`` — the citation to paste if this is the one.
    quote: str
    #: The short lines directly under it. In a linearised grid this is the row:
    #: "Quadplexes" is the label and its eleven cells are the answer.
    under: tuple[str, ...] = ()

    @property
    def row(self) -> bool:
        """Whether it reads as a table row rather than as prose about one."""
        return bool(_ROW_START.match(self.text))


def _states(line: str, number: float) -> bool:
    """Whether a line prints this number, compared by value not by spelling."""
    for found in _PRINTED.finditer(line):
        raw = found.group(0)
        if raw.startswith("0") and len(raw) > 1 and not raw.startswith("0."):
            # A padded number is a code, not a measurement: OAR 660-046-0220
            # is a citation, and read as 220 it makes every rule quoting the
            # statute look like a document stating a 220-foot standard.
            continue
        try:
            if float(raw.replace(",", "")) == number:
                return True
        except ValueError:
            continue
    return False


def wording(field: str, believed: Any) -> re.Pattern[str] | None:
    """What to look for when the standard is not a number, or None if it is."""
    if field == "quadplex_allowed":
        return _TYPE
    if isinstance(believed, bool) or not isinstance(believed, (int, float)):
        # An enum or a curve: no digits to compare, and no housing type either.
        # What names it in the code are the long words of its own description —
        # "Minimum front setback" hunts "minimum" and "setback", which is the
        # search somebody would run by eye.
        said = FIELDS[field].describe if field in FIELDS else field.replace("_", " ")
        words = {re.escape(w.strip(".,")) for w in said.split() if len(w.strip(".,")) > 4}
        return re.compile("|".join(sorted(words)), re.I) if words else None
    return None


def _under(lines: Sequence[str], at: int) -> tuple[str, ...]:
    """The run of short lines below a match, stopped at the first prose line.

    A run of one-word cells is the row this match labels; the sentence after it
    is the document moving on to the next thing.
    """
    out: list[str] = []
    for line in lines[at : at + _UNDER]:
        text = line.strip()
        if not text:
            continue
        if len(text) > 40:
            break
        out.append(text)
    return tuple(out)


def passages(
    text: str, *, path: str, field: str, believed: Any, limit: int = 60
) -> tuple[list[Passage], int]:
    """Lines in one document that could state this value, best first.

    Ranked before it is cut, which is the difference between a list and a
    useful one, and returned with the number left over — a list that silently
    ends reads as a document that ends there, and somebody would declare a
    missing chapter on the strength of it.
    """
    pattern = wording(field, believed)
    number = None
    if pattern is None and isinstance(believed, (int, float)) and not isinstance(believed, bool):
        number = float(believed)
    if pattern is None and number is None:
        return [], 0

    lines = text.splitlines()
    out: list[Passage] = []
    for n, line in enumerate(lines, 1):
        body = line.strip()
        if not body:
            continue
        if number is not None and not _states(body, number):
            continue
        if pattern is not None and not pattern.search(body):
            continue
        out.append(
            Passage(
                document=path,
                line=n,
                text=body[:400],
                quote=f"{path}#L{n}",
                under=_under(lines, n),
            )
        )
        if len(out) >= _SWEEP:
            break
    # Stable, so within a rank the lines stay in the order the code prints them.
    out.sort(key=lambda one: 0 if one.row else 1)
    return out[:limit], max(0, len(out) - limit)
