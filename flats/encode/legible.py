"""Make a stored code document readable on screen without editing a byte of it.

Every rule in FLATS cites a line number into these files. Join two wrapped
lines and every citation below the join points one line off -- silently, with
nothing on screen to suggest it, against 600-odd values that were each read and
signed by a person. And the stored bytes hash to a recorded digest, which is the
only thing that notices when a city amends a chapter under us. So the files are
not reflowed, not rewrapped, and not cleaned. They are rendered better.

The whole difficulty is that the ugliness is two different things wearing the
same clothes, and only one of them is noise:

*Prose* arrives ragged because a PDF column was 6.5 inches wide and the
extractor kept every break in it. Horizontal position carries nothing -- the
leading spaces are indentation, the double spaces are justification artefacts --
so squeezing them is lossless and the line reads like a sentence again.

*Grid rows* arrive with runs of twenty spaces because that run **is** the
column boundary. It is the only surviving evidence of which zone a number
belonged to, since layout extraction keeps horizontal geometry precisely so a
cell stays under its own heading. Squeezing a grid row destroys the one thing
that makes it checkable and leaves something that looks tidier and means less.
Lake Oswego's R-5 setback row and Gresham's seven-column corridor table are both
unreadable-but-correct in exactly this way.

So each line is classified and only prose is touched. A grid row is handed back
untouched, marked, for the template to put in a monospace block that scrolls
sideways rather than wrapping -- because wrapping a grid row is the other way to
destroy it, and it is the way a stylesheet does it by accident.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: A run of spaces wide enough to have been a column boundary rather than a
#: gap between words. Three is the same threshold the review card uses to
#: decide whether it is looking at a table, and the two must agree: a line
#: called prose here and a grid there would be squeezed and then flagged as a
#: table the reviewer should read carefully, which is worse than either.
_GAP = re.compile(r"\s{3,}")

#: Two or more spaces mid-sentence. Justification, a double space after a full
#: stop, a soft hyphen that lost its word -- never meaning.
_SQUEEZE = re.compile(r"[ \t]{2,}")

# There is deliberately no hyphen repair here. "street- side" wants joining and
# "require- ments" wants a hyphen removed, and nothing short of a dictionary
# tells them apart -- so a repair would silently print a word the code does not
# contain, on the one screen whose entire job is showing a reviewer what the
# code actually says. Squeezing whitespace cannot be wrong that way.

#: Numbering that opens a line: "A.", "3.", "(2)", "iv.", "a."  Kept at the
#: front rather than squeezed into the sentence, because a reviewer scanning
#: for subsection (d) is scanning the left margin for it.
_MARKER = re.compile(r"^\(?([A-Za-z]|[0-9]{1,3}|[ivxlcIVXLC]{1,6})[).]\s")


@dataclass(frozen=True, slots=True)
class Line:
    """One line of a document, as stored and as it should be shown."""

    #: The line number every citation in FLATS is written against. Never
    #: derived, never renumbered, and identical to the index in the file.
    n: int
    #: Exactly what is on disk.
    raw: str
    #: What to put on screen.
    shown: str
    #: ``grid`` where the spacing is load-bearing, ``prose`` where it is not,
    #: ``blank`` for an empty line.
    kind: str

    @property
    def grid(self) -> bool:
        return self.kind == "grid"


def is_grid(line: str) -> bool:
    """Whether this line's horizontal spacing is carrying column identity.

    Deliberately loose and deliberately biased toward *yes*. Calling a grid row
    prose squeezes away the column boundaries; calling a prose line a grid
    leaves it slightly wide. Only one of those loses information.
    """
    body = line.rstrip()
    if not body.strip():
        return False
    return bool(_GAP.search(body.strip()))


def legible(line: str) -> str:
    """One line of prose, with the extractor's artefacts taken out.

    Never called on a grid row. Everything here is safe only because
    horizontal position in a sentence means nothing.
    """
    body = line.strip()
    if not body:
        return ""
    body = _SQUEEZE.sub(" ", body)
    return body


def read(text: str, first: int = 1) -> list[Line]:
    """A document, or a window of one, classified line by line.

    ``first`` is the real line number of ``text``'s first line, so a window cut
    out of the middle of a chapter still carries the numbering its citations
    are written against.
    """
    out: list[Line] = []
    for offset, raw in enumerate(text.splitlines()):
        n = first + offset
        if not raw.strip():
            out.append(Line(n, raw, "", "blank"))
        elif is_grid(raw):
            out.append(Line(n, raw, raw.rstrip(), "grid"))
        else:
            out.append(Line(n, raw, legible(raw), "prose"))
    return out


def marker(line: str) -> str:
    """The subsection letter or number a line opens with, if it opens with one.

    Pulled out so the template can hang it in the margin. A code is navigated
    by these -- "19.115.040(B)" is three of them -- and a reviewer sent to
    subsection (d) finds it by looking down the left edge, which only works if
    the left edge is where it stayed.
    """
    found = _MARKER.match(line.strip())
    return found.group(0).strip() if found else ""
