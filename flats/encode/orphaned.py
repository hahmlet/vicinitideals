"""A unit word with nothing in front of it, where a number used to be.

Every blind spot this project has found is the same shape: the reader reports
the corpus clean because the thing that went missing left no hole. A dropped
use-table cell shifts its neighbours (:mod:`flats.encode.ragged`); a spelled
number the vocabulary cannot say is simply not a number; a short table header
files one district's answer under another's. This is the same failure in prose.

Happy Valley's ``16.22.050`` is why it exists, found on 2026-09-09 working the
reading queue::

    No side or rear yard setback shall be required for any detached accessory
    structure that is 100 square feet or less in area and does not exceed a
    height of feet.

A height of *feet*. The next two subsections say "eight feet in height" and
"greater than eight feet and up to 20 feet", so the missing word is `eight`
and the sentence still reads as English -- which is exactly the problem. No
extraction check fires, no number is misquoted, and any reader who is looking
for figures rather than reading the sentence sees a subsection with one
standard in it instead of two.

What makes this checkable is that a code never writes a bare unit after a word
that introduces a measurement. "of feet", "than feet", "at least percent",
"exceed inches" are not English a drafter produces; they are English a lost
numeral produces. Three things have to be excluded before that is true, and
each of them is a real sentence in this corpus rather than a hypothetical:

**A number at the end of the line above.** Gresham's downtown and civic-
neighborhood chapters set their standards in two columns, and a wrapped line
puts the numeral and its unit on separate rows -- "no more than 2" then "feet
above or below the sidewalk elevation". Four of the five candidates in the
corpus are this, and all four are correctly extracted.

**A counting noun.** "the number of stories", "the amount of buildable
acreage", "a variety of types of spaces" -- here "of" introduces a count, not
a measurement, and the noun that governs it may sit at the end of the previous
line.

**Countable nouns generally.** ``units`` and ``spaces`` cannot be in the unit
vocabulary at all. They are ordinary English plurals and admitting them takes
this check from one hit to 132, every one of them a sentence about how many
dwellings or stalls something has. Only words that can *only* be a dimension
earn a place: feet, inches, percent, stories, acres.

The corpus separates as cleanly as it does for ragged tables -- exactly one
document, and every other candidate excluded by one of the three rules above
-- which is why this can be a test rather than a report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "provenance" / "docs"

#: Words that can only be a dimension. Deliberately short: see the module
#: docstring on why ``units`` and ``spaces`` are absent and must stay absent.
_UNIT = r"(?:feet|foot|inches|inch|square\s+feet|percent|stories|acres)"

#: Words a drafter puts immediately before a magnitude. ``to`` is not among
#: them -- "converted to square feet" and "convert the area to acres" are
#: conversions rather than measurements, and they are the only thing it found.
_LEAD = r"(?:of|than|least|exceed|exceeds)"

#: Nouns after which "of <unit>" is a count and not a measurement.
_COUNT = r"(?:number|amount|total|quantity|percentage|share|count|fraction|variety|types?)"

ORPHAN = re.compile(rf"\b({_LEAD})\s+({_UNIT})\b", re.IGNORECASE)

#: A magnitude at the end of a line. Spelled numbers stop at ``hundred`` on
#: purpose: this is asking whether a wrapped line ended mid-measurement, and a
#: standard whose number wraps is written in the small numbers codes use.
_TRAILING = re.compile(
    r"(?:\d|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve"
    r"|fifteen|twenty|thirty|forty|fifty|hundred))\W*$",
    re.IGNORECASE,
)

_COUNTING = re.compile(rf"\b{_COUNT}\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class Orphan:
    """One unit word that appears to have lost its number."""

    path: Path
    line: int
    text: str

    @property
    def name(self) -> str:
        return self.path.relative_to(DOCS).as_posix()

    @property
    def cite(self) -> str:
        return f"{self.name}#L{self.line}"


def orphans(lines: list[str]) -> list[int]:
    """The 1-indexed lines of one document that state a unit with no number."""
    found: list[int] = []
    for i, line in enumerate(lines):
        for match in ORPHAN.finditer(line):
            before = line[: match.start()]
            previous = lines[i - 1] if i else ""
            # The noun that turns "of" into a count can sit at the end of the
            # line above, so the two are tested as one run of text.
            if _COUNTING.search((previous + " " + before).rstrip()):
                continue
            if _TRAILING.search(before) or _TRAILING.search(previous):
                continue
            found.append(i + 1)
    return found


def scan(root: Path | None = None) -> list[Orphan]:
    """Every stored line whose unit word lost its measurement."""
    root = root or DOCS
    found: list[Orphan] = []
    for path in sorted(root.rglob("*.txt")):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        found += [Orphan(path=path, line=n, text=lines[n - 1].strip()) for n in orphans(lines)]
    return found


def render(found: list[Orphan] | None = None) -> str:
    found = scan() if found is None else found
    if not found:
        return "no orphaned units"
    return "\n".join(f"{o.cite}\n    {o.text}" for o in found)


def main() -> None:
    print(render())


if __name__ == "__main__":
    main()
