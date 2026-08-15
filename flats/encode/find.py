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

#: A number as a document prints one: 7,500 and 7500 and 7500.0. Not one glued
#: to the end of a word: "45 feet5" is a height with a footnote marker on it,
#: and read as a 5 it makes that line evidence for every 5-foot standard in the
#: chapter.
_PRINTED = re.compile(r"(?<![A-Za-z\d.,])\d[\d,]*(?:\.\d+)?")

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

#: A line that opens a table or a section, and so says what the rows under it
#: are about. Happy Valley prints the same "Interior side" row three times,
#: once per district group, and the caption above it is the only thing that
#: says which three districts a row answers for.
_CAPTION = re.compile(r"^(?:table\s+[0-9]|[0-9]+(?:\.[0-9]+)+)", re.I)

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
    #: Whether the line says which standard it is about, and not only the
    #: number. "Interior side  15/04 feet" does; "Building height  45 feet"
    #: prints a 15 and a 5 and is neither zone's side setback.
    names: bool = False
    #: Whether the caption above it names the zone this was hunted for. A code
    #: states the same row once per district group, so the caption is what
    #: separates this zone's answer from its neighbour's.
    scoped: bool = False

    @property
    def row(self) -> bool:
        """Whether it reads as a table row rather than as prose about one."""
        return bool(_ROW_START.match(self.text))


def code_of(zone: str) -> str:
    """A zone code in the one shape a rule file and a code document share.

    The files write R40 and the ordinance prints R-40; the same district, and a
    comparison that respected the hyphen would find neither in the other. The
    decimal stays — R8.5 and R85 are two districts.
    """
    return re.sub(r"[^A-Z0-9.]", "", zone.upper())


def names_zone(line: str, zone: str) -> bool:
    """Whether a line names this zone, and not a longer code containing it.

    R-5 sits inside R-50, and a caption for the large-lot districts read as
    naming the small-lot one scopes every row under it to the wrong zone.
    """
    want = code_of(zone)
    if not want:
        return False
    body = ("[- ]?").join(re.escape(c) for c in want)
    return re.search(rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])", line) is not None


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


def _words(said: str) -> list[str]:
    """The words of a field's description long enough to name it in a code."""
    return sorted({w.strip(".,()") for w in said.split() if len(w.strip(".,()")) > 4})


def subject(field: str) -> re.Pattern[str] | None:
    """What a line saying *this standard* says, whatever number follows.

    "Interior side   15/04 feet" and "Building height (maximum)   45 feet" both
    print a 15 and a 5 respectively, and only one of them is a side setback.
    The field's own description is the vocabulary: a line matching none of it
    is a line that prints the number somewhere else in the chapter.
    """
    if field not in FIELDS:
        return None
    words = [re.escape(w) for w in _words(FIELDS[field].describe)]
    return re.compile("|".join(words), re.I) if words else None


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
        words = [re.escape(w) for w in _words(said)]
        return re.compile("|".join(words), re.I) if words else None
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
    text: str,
    *,
    path: str,
    field: str,
    believed: Any,
    zone: str = "",
    limit: int = 60,
    named: bool = False,
) -> tuple[list[Passage], int]:
    """Lines in one document that could state this value, best first.

    Ranked before it is cut, which is the difference between a list and a
    useful one, and returned with the number left over — a list that silently
    ends reads as a document that ends there, and somebody would declare a
    missing chapter on the strength of it.

    ``named`` narrows it to lines that also say which standard they are about,
    which is what the ledger asks: a 5 appears on forty lines of a chapter and
    on one of them it is the side setback. For a reader at a screen the loose
    list is better — the ranking puts the named lines first and the rest are
    there in case the encoding's own vocabulary is what is wrong.
    """
    pattern = wording(field, believed)
    number = None
    if pattern is None and isinstance(believed, (int, float)) and not isinstance(believed, bool):
        number = float(believed)
    if pattern is None and number is None:
        return [], 0

    about = subject(field)
    lines = text.splitlines()
    out: list[Passage] = []
    scoped = False
    for n, line in enumerate(lines, 1):
        body = line.strip()
        if not body:
            continue
        if zone and _CAPTION.match(body):
            # A caption resets the scope whether or not it names the zone: the
            # table it opens is a new set of districts, and inheriting the last
            # one's would rank another group's rows as this zone's.
            scoped = names_zone(body, zone)
        if number is not None and not _states(body, number):
            continue
        if pattern is not None and not pattern.search(body):
            continue
        names = bool(about and about.search(body))
        if named and about is not None and not names:
            continue
        out.append(
            Passage(
                document=path,
                line=n,
                text=body[:400],
                quote=f"{path}#L{n}",
                under=_under(lines, n),
                names=names,
                scoped=scoped,
            )
        )
        if len(out) >= _SWEEP:
            break
    # Sitting under a caption that names the zone outranks naming the standard,
    # which outranks looking like a row. A code prints "Interior side" once per
    # district group and every one of those rows is a side setback; the caption
    # is the only thing that says which group answers for this zone. Stable
    # within a rank, so the lines stay in the order the code prints them.
    out.sort(
        key=lambda one: (
            0 if one.scoped else 1,
            0 if one.names else 1,
            0 if one.row else 1,
        )
    )
    return out[:limit], max(0, len(out) - limit)
