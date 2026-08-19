"""Every word a jurisdiction bothered to define, captured before we need it.

The register in ``definitions.py`` asks one question of each jurisdiction --
does it define *this* term -- and answers it well. That shape does not scale
to the question underneath: which of a city's words are load-bearing? We
cannot know in advance. A city that wrote a definition wrote it because the
word does work somewhere in its code, and choosing which of their definitions
to honour is the same error as choosing a universal meaning, only smaller.

So this reads the whole chapter. Every entry, its term, its words and the line
a reviewer can open, with no judgement about relevance -- the same discipline
the footnote census runs on, for the same reason. Capture is mechanical and
total; deciding which entries matter is a later, recorded step.

Two jobs stay separate on purpose:

*Capture* is what this module does. It is cheap and it is a parse.

*Test* -- a computable check against a real lot, like the corner-lot geometry
in ``rules/definitions.py`` -- is only needed for terms that must be
*evaluated*. Most defined terms never need one. They need to be **known**, so
that when the word turns up in a standard the reader sees this city's meaning
and the encoder cannot substitute the general one.

Capture that claims to be complete has to be checkable, and a definitions
chapter hands us an invariant for free: it is alphabetical. An entry that
sorts before the one above it is either something that is not an entry, or the
tell that a real entry above it was missed and its body absorbed a heading. So
each chapter reports its own ``disorder``, and a chapter with a lot of it is
not a chapter we have read -- it is one we have skimmed.

Run it::

    uv run python -m flats.encode.glossary
    uv run python -m flats.encode.glossary --layer or/multnomah/gresham
    uv run python -m flats.encode.glossary --terms or/multnomah/gresham
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Sequence

from flats.encode.definitions import CHAPTER, _stored
from flats.rules.loader import load_rules
from flats.rules.model import Layer

#: An entry opens its own line: an optional bullet or list marker, the term,
#: a separator, then the body. The term is a noun phrase, so it is bounded --
#: a line of prose that happens to contain a period is not an entry, and the
#: length cap is what says so.
ENTRY = re.compile(
    # A bullet and whatever the extraction padded after it. Portland's chapter
    # sets a bullet at the left margin and the term forty spaces later, so a
    # fixed-width prefix reads its entire glossary as prose.
    r"^(?:[•·▪◦*(\-–—]\s*){0,2}"
    r"(?:\(?[0-9ivxIVX]{1,5}[.)]\s+)?"  # a list marker, if the code numbers them
    r"(?:\d{1,3}\.\d{2,4}(?:\.\d{1,4})?\s+)?"  # or a section number
    r"[\"“]?(?P<term>[A-Z][A-Za-z0-9'’/()\-]*(?:[ ,](?:[A-Za-z0-9'’/()\-]+)){0,6})[\"”]?"
    r"(?P<sep>\s*[.:]\s+|\s*[–—-]\s+|\s+(?:means|shall mean|refers to|is defined as)\s+)"
    r"(?P<body>\S.*)$"
)

#: The stacked form: the term alone on its line, the body beneath it. Milwaukie
#: and Happy Valley's codifier sets every entry this way, and a rule that only
#: knows the inline form reads their entire chapters as prose.
STACKED = re.compile(
    r"^[\"“]?(?P<term>[A-Z][A-Za-z0-9'’/()\-]*(?:[ ,](?:[A-Za-z0-9'’/()\-]+)){0,6})"
    r"[\"”]?\s*[.:]?$"
)

#: What a body has to open with to be a meaning rather than a pointer or a
#: standard. Same rule the corner-lot matcher earned the hard way: a definition
#: opens with a noun phrase, a cross-reference opens with "see", and a standard
#: opens with a preposition or a quantifier.
NOT_A_DEFINITION = re.compile(
    r"^(?:see|on|for|in|where|when|if|no|all|each|every|except|the following)\b", re.I
)

#: Shorter than this and the "body" is a heading, a page number, or the tail of
#: a wrapped line rather than somebody's meaning. Measured after whitespace is
#: collapsed: a layout extraction pads across the column, and "[3.0100- 2]"
#: spread over sixty characters is a page stamp, not a definition.
MIN_BODY = 40

#: Shorter than this and the "term" is a list marker. Gresham's chapter opens
#: with "A  Overlay District Terms and Definitions", and A, B, C and D are not
#: words this city defined. Real short terms -- Lot, Use, Yard -- clear it.
MIN_TERM = 3

#: The codifier's apparatus, which is set exactly like an entry and is not
#: one. Gladstone prints "History  Ord. 1131 2, 1990; Repealed by Ord. 1323"
#: under every repealed section -- sixty of them, each a perfectly formed
#: term-separator-body line about the ordinance rather than about a word.
APPARATUS = re.compile(
    r"^(?:history|editor.?s? note|cross[- ]reference|code reviser|prior history"
    r"|amended|repealed|ord\.?|formerly|renumbered|statutory reference)\b",
    re.I,
)

#: The codifier's page stamp, which sits between entries and looks like a body
#: once the column padding is collapsed out of it.
FURNITURE = re.compile(r"^\[[^\]]*\]$|^\(\d+\)$|^Page \d+", re.I)

#: A term that opens with a pointer is the tail of somebody else's entry.
_CROSS_REFERENCE = re.compile(r"^(?:see|also|and|or|of|the)\b", re.I)

_SPACE = re.compile(r"\s+")


def _collapse(text: str) -> str:
    return _SPACE.sub(" ", text).strip()

#: Longer than this and the "term" is a sentence.
MAX_TERM = 60


@dataclass(frozen=True, slots=True)
class Entry:
    """One defined term, as the jurisdiction wrote it."""

    layer: str
    doc: str
    line: int
    term: str
    text: str
    #: How it was set: inline on one line, or the term alone above its body.
    shape: str = "inline"

    @property
    def quote(self) -> str:
        return f"{self.doc}#L{self.line}"

    @property
    def key(self) -> str:
        """The term as it sorts: case-folded, punctuation dropped."""
        return re.sub(r"[^a-z0-9 ]", "", self.term.lower()).strip()


@dataclass(frozen=True, slots=True)
class Chapter:
    """One jurisdiction's definitions chapter, as read."""

    layer: str
    doc: str
    entries: tuple[Entry, ...]
    #: Entries that sort before the entry above them. A chapter is
    #: alphabetical; disorder is where capture is doubtful.
    disorder: tuple[Entry, ...]
    #: Lines in the stored document, so thinness can be measured.
    lines: int = 0

    @property
    def orderly(self) -> bool:
        return len(self.disorder) <= max(1, len(self.entries) // 20)

    @property
    def density(self) -> float:
        """Entries per hundred lines of chapter."""
        return 100.0 * len(self.entries) / self.lines if self.lines else 0.0

    @property
    def thin(self) -> bool:
        """Too few entries for the size of the chapter to be a full reading.

        Disorder catches entries we invented. Nothing catches entries we
        missed -- a chapter set in a shape the matcher does not know reads as
        a handful of perfectly ordered entries and looks like success. Density
        is the other direction: a definitions chapter is mostly definitions,
        so a thousand lines yielding thirty of them is a shape nobody has
        taught this module yet.
        """
        return self.lines > 200 and self.density < 3.0

    @property
    def read_whole(self) -> bool:
        return self.orderly and not self.thin


def _misfiled(term: str, body: str) -> bool:
    """Whether this "body" is really the next entry, or a pointer to another.

    Portland's chapter wraps a long term across two lines and pads a bullet
    forty spaces from the margin, which produces two ways to file one term's
    meaning under another term's name: a heading whose line beneath is the
    *next* entry rather than its own body, and a term that is only the first
    word of itself. Both leave the same trace -- a body that is a well-formed
    entry in its own right -- and both are worse than missing the entry, so
    the trace is fatal.
    """
    if _CROSS_REFERENCE.match(term):
        return True
    inside = ENTRY.match(body)
    return inside is not None and MIN_TERM <= len(inside.group("term")) <= MAX_TERM


def _entries(text: str, *, layer: str, doc: str) -> list[Entry]:
    lines = text.splitlines()
    out: list[Entry] = []
    for i, raw in enumerate(lines):
        stripped = raw.strip()
        if not stripped:
            continue
        inline = ENTRY.match(stripped)
        if inline is not None and MIN_TERM <= len(inline.group("term")) <= MAX_TERM:
            body = _collapse(inline.group("body"))
            if (
                len(body) >= MIN_BODY
                and not NOT_A_DEFINITION.match(body)
                and not APPARATUS.match(inline.group("term"))
                and not APPARATUS.match(body)
                and not _misfiled(inline.group("term"), body)
            ):
                out.append(
                    Entry(
                        layer=layer,
                        doc=doc,
                        line=i + 1,
                        term=inline.group("term").strip(),
                        text=body,
                    )
                )
                continue
        stacked = STACKED.match(stripped)
        if stacked is None or not MIN_TERM <= len(stacked.group("term")) <= MAX_TERM:
            continue
        body = _collapse(_below(lines, i))
        if len(body) < MIN_BODY or NOT_A_DEFINITION.match(body):
            continue
        if APPARATUS.match(stacked.group("term")) or APPARATUS.match(body):
            continue
        if _misfiled(stacked.group("term"), body):
            continue
        if STACKED.match(body) or FURNITURE.match(body):
            # The line beneath is another term, or the page stamp between two
            # of them. Either way this entry's body is somewhere we did not
            # look, and inventing one from the next heading would put one
            # term's meaning under another term's name.
            continue
        out.append(
            Entry(
                layer=layer,
                doc=doc,
                line=i + 1,
                term=stacked.group("term").strip(),
                text=body,
                shape="stacked",
            )
        )
    return out


def _below(lines: Sequence[str], i: int) -> str:
    """The first non-blank line under an entry, which is its body."""
    for line in lines[i + 1 : i + 3]:
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _disorder(entries: Sequence[Entry]) -> list[Entry]:
    """The smallest set of entries whose removal leaves the chapter in order.

    The obvious version -- flag anything sorting below the highest key so far
    -- is worthless here, because a chapter's front matter sits above its
    entries and one stray heading keyed "general" condemns every real entry
    from A to F. What is wanted is the *fewest* offenders, so this takes the
    longest non-decreasing run of keys and calls everything outside it
    disorder. A chapter is alphabetical; whatever cannot fit that is either
    not an entry or the tell that a real one above it was missed.
    """
    return [e for run in _runs(entries) for e in _out_of_order(run)]


#: Entries a run needs before a backwards key can be read as a second
#: glossary rather than as one entry filed in the wrong place.
_ALPHABET = 3


def _runs(entries: Sequence[Entry]) -> list[list[Entry]]:
    """A chapter's alphabetical runs, because some chapters have several.

    Gresham's definitions open with a general glossary and then start over for
    overlay districts, renewable energy, trees and temporary uses -- four more
    alphabets under one chapter number. Measured as one sequence each restart
    reads as a hundred broken entries, which is a measurement of our reading
    and not of theirs. A restart is a key that sorts backwards, *stays*
    forwards after -- the entries following it continue from where it began --
    and leaves an alphabet behind it. That last clause is what keeps one stray
    heading above the entries from reading as a one-entry glossary of its own:
    one entry is not an alphabet, it is the offender this measure names.
    """
    runs: list[list[Entry]] = [[]]
    for i, entry in enumerate(entries):
        current = runs[-1]
        if (
            len(current) >= _ALPHABET
            and entry.key < current[-1].key
            and _sustained(entries, i)
        ):
            runs.append([entry])
            continue
        current.append(entry)
    return [run for run in runs if run]


def _sustained(entries: Sequence[Entry], i: int) -> bool:
    """Whether the entries after ``i`` carry on from it in order."""
    window = entries[i : i + 5]
    if len(window) < 3:
        return False
    forward = sum(1 for a, b in zip(window, window[1:]) if a.key <= b.key)
    return forward >= len(window) - 2


def _out_of_order(entries: Sequence[Entry]) -> list[Entry]:
    keys = [e.key for e in entries]
    # Patience sorting: tails[i] is the smallest key ending a run of length
    # i+1, and `where` remembers each entry's predecessor so the run can be
    # walked back out.
    tails: list[int] = []
    where: list[int] = [-1] * len(keys)
    for i, key in enumerate(keys):
        low, high = 0, len(tails)
        while low < high:
            mid = (low + high) // 2
            if keys[tails[mid]] <= key:
                low = mid + 1
            else:
                high = mid
        where[i] = tails[low - 1] if low else -1
        if low == len(tails):
            tails.append(i)
        else:
            tails[low] = i

    keep: set[int] = set()
    cursor = tails[-1] if tails else -1
    while cursor >= 0:
        keep.add(cursor)
        cursor = where[cursor]
    return [e for i, e in enumerate(entries) if i not in keep]


def read(layer: Layer) -> Chapter | None:
    """One jurisdiction's definitions chapter, if it declared one and we hold it."""
    stored = {p.stem: p for p in _stored(layer.layer)}
    for doc in layer.code:
        if not CHAPTER.search(f"{doc.id} {doc.title}"):
            continue
        path = stored.get(doc.id)
        if path is None:
            return None
        name = f"{layer.layer}/{path.name}"
        text = path.read_text(encoding="utf-8", errors="replace")
        entries = _entries(text, layer=layer.layer, doc=name)
        return Chapter(
            layer=layer.layer,
            doc=name,
            entries=tuple(entries),
            disorder=tuple(_disorder(entries)),
            lines=len(text.splitlines()),
        )
    return None


def chapters(layer_id: str | None = None) -> list[Chapter]:
    """Every definitions chapter in the corpus that is on disk."""
    out: list[Chapter] = []
    for identifier, layer in sorted(load_rules().items()):
        if layer_id and identifier != layer_id:
            continue
        chapter = read(layer)
        if chapter is not None:
            out.append(chapter)
    return out


def render(rows: Sequence[Chapter], *, terms: bool = False) -> str:
    """The glossary as text, for a terminal or a commit message."""
    if terms:
        return "\n".join(
            f"{e.quote:<56} {e.shape:<8} {e.term:<34} {e.text[:70]}"
            for row in rows
            for e in row.entries
        )
    width = max((len(r.layer) for r in rows), default=20)
    lines = [
        f"{r.layer:<{width}}  {len(r.entries):>4} entries  "
        f"{len(r.disorder):>3} out of order  {r.density:>5.1f}/100 lines"
        f"{'' if r.orderly else '  SKIMMED'}{'  THIN' if r.thin else ''}"
        for r in rows
    ]
    lines.append("")
    lines.append(
        f"chapters={len(rows)}  entries={sum(len(r.entries) for r in rows)}  "
        f"read_whole={sum(1 for r in rows if r.read_whole)}  "
        f"skimmed={sum(1 for r in rows if not r.orderly)}  "
        f"thin={sum(1 for r in rows if r.thin)}"
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    layer = args[args.index("--layer") + 1] if "--layer" in args else None
    if "--terms" in args:
        layer = layer or args[args.index("--terms") + 1]
        print(render(chapters(layer), terms=True))
        return 0
    print(render(chapters(layer)))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["Chapter", "Entry", "chapters", "read", "render"]
