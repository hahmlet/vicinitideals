"""Code text a person can read, proved letter for letter against what was fetched.

A PDF extraction is a copy of the printed sheet, not of the sentences on it.
Every printed line is a line of text, so a sentence wrapped over four lines is
four lines; the page's running header and footer sit in the middle of whatever
section the page break fell in; a word broken at the margin is two pieces with
a hyphen; and a kerned capital comes out "T able". A reviewer verifying a
cited sentence reads around all of that, and every tool that reads the text
reads around it too.

:func:`clean` turns a slice of an extraction into readable text: page
furniture out, broken words mended, wrapped lines joined, and one sentence to
a line, so a citation of a sentence names one line and a diff of an amendment
reads as the sentences that changed. :func:`prove` then checks the result
against the extraction it came from, independently of how it was made:

*Every letter, in order.* With the whitespace taken out, the readable text is
the extraction's text exactly, except for hyphens that ended a printed line.
Nothing is added, dropped, reordered or respelt.

*Only furniture is removed.* A removed line matches the jurisdiction's
furniture pattern and sits in the last few lines before a page starts, where
the extraction puts a page's header and footer. The same words anywhere else
are code text and stay.

*No line crosses a page.* A readable line draws on one printed page, so the
page a citation names is still the sheet its words are printed on.

Tables are left as they were printed: their lines are short, and a line is
only joined to the next when it runs to the margin.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

#: The name of the cleaning, stored with every cut so a later change to it is
#: a re-cut and not a silent edit.
VERSION = "readable/2"

#: A printed line at least this long ran to the margin, so the sentence on it
#: carries on to the next line. Tualatin's prose lines run 80-103 characters.
WIDTH = 80

#: How far above a page start the extraction puts that page's header and
#: footer. Measured on Tualatin: two lines, sometimes three.
BAND = 4

#: A capital letter set apart from the rest of its word by kerning: "T able".
#: Not A or I, which are words.
_KERNED = re.compile(r"(?<![A-Za-z])([B-HJ-Z]) ([a-z]+)(?![A-Za-z])")

#: A line that opens a new block rather than carrying on a sentence: an
#: enumerator, a bullet, a caption, or a heading set in capitals.
_OPENS = re.compile(
    r"""^\s*(?:
        \(\s*[0-9]{1,3}\s*\)            # (1)
      | \(\s*[a-zA-Z]{1,5}\s*\)         # (a) (iv) (A)
      | [0-9]{1,3}[.)]\s                # 1.  1)
      | [a-zA-Z][.)]\s                  # a.  A)
      | [•●▪◦–—*-]\s   # bullets and dashes
      | (?:Table|Figure|Map|Exhibit|Chapter|Section|Sections)\b
      | [A-Z][A-Z0-9 ,&()/'-]{5,}$      # A HEADING IN CAPITALS
    )""",
    re.VERBOSE,
)

#: The end of a sentence: a stop, then space, then a capital or an opening
#: bracket or quote.
_STOP = re.compile(r"""[.?!]["')\]]*(?=\s+["'(\[]?[A-Z])""")

#: Words a stop follows without ending the sentence.
_ABBREVIATIONS = frozenset(
    """
    no nos supp ord sec secs ss ch art fig p pp para subd subsec
    st ave rd dr blvd hwy ln ct pl pkwy
    inc co corp ltd llc dept div
    ft sq yd mi ac hr min max approx avg
    e.g i.e u.s s.w s.e n.w n.e sw se nw ne vs v cf viz al
    mr mrs ms dr jr sr
    """.split()
)

#: A word, for the vocabulary: letters, and hyphens between letters.
#: Words a title leaves lower case.
_SMALL = frozenset("a an and as at by for from in of on or the to with".split())

#: An enumerator opening a run-in heading: "(1)", "(a)", "(iv)", "1.".
_ENUMERATOR = re.compile(r"^\s*(?:\([0-9A-Za-z]{1,4}\)|[0-9]{1,2}\.)\s+")


def _run_in(piece: str) -> bool:
    """Whether a sentence-looking piece is a heading the paragraph runs on from.

    "Multi-Use Path (Trail). A path ..." and "(1) Food Stores. Food stores
    must ..." print a title and its text as one paragraph. Cut there, the term
    loses its definition and the label its standard.
    """
    words = _ENUMERATOR.sub("", piece).strip().rstrip(".").split()
    if not words or len(words) > 8:
        return False
    for word in words:
        bare = word.strip("()\"'")
        if bare.lower() in _SMALL:
            continue
        if not re.fullmatch(r"[A-Z][A-Za-z'/&-]*", bare):
            return False
    return True


_WORD = re.compile(r"[A-Za-z]+(?:-[A-Za-z]+)*")


def vocabulary(texts: Iterable[str]) -> Counter[str]:
    """How often each word is printed whole, lower-cased.

    The judge of whether "T able" is "Table" and "sub-" over "ject" is
    "subject": the code's own spelling, counted from the code itself.
    """
    out: Counter[str] = Counter()
    for text in texts:
        out.update(w.lower() for w in _WORD.findall(text))
    return out


@dataclass(frozen=True, slots=True)
class Readable:
    """A slice of an extraction made readable, and where each line came from."""

    lines: tuple[str, ...]
    #: For each line, the extraction lines it is made of (1-based, in order).
    sources: tuple[tuple[int, ...], ...]
    #: Extraction lines left out as page furniture.
    removed: tuple[int, ...]

    @property
    def text(self) -> str:
        return "\n".join(self.lines) + "\n"

    def lines_of(self, raw: Iterable[int]) -> tuple[int, ...]:
        """The readable lines that hold any of these extraction lines."""
        wanted = set(raw)
        return tuple(k for k, src in enumerate(self.sources, start=1) if wanted & set(src))

    def page_starts(self, breaks: Iterable[int]) -> dict[int, int]:
        """Extraction page start -> the first readable line on or after it."""
        out: dict[int, int] = {}
        for brk in sorted(breaks):
            for k, src in enumerate(self.sources, start=1):
                if src and src[0] >= brk:
                    out[brk] = k
                    break
        return out


def _furniture(
    lines: Sequence[str], breaks: Iterable[int], furniture: re.Pattern[str] | None
) -> set[int]:
    if furniture is None:
        return set()
    out: set[int] = set()
    for brk in breaks:
        for k in range(max(1, brk - BAND), min(brk, len(lines) + 1)):
            if furniture.match(lines[k - 1]):
                out.add(k)
    return out


#: One character of readable text and the extraction line it came from; None
#: for a space put in where two lines were joined.
_Char = tuple[str, int | None]


def _mend_kerning(text: str, words: Mapping[str, int]) -> set[int]:
    """Columns of the spaces kerning put inside a word."""
    out: set[int] = set()
    for found in _KERNED.finditer(text):
        whole = (found.group(1) + found.group(2)).lower()
        piece = found.group(2).lower()
        if words.get(whole, 0) >= 3 and words.get(whole, 0) > words.get(piece, 0):
            out.add(found.start() + 1)
    return out


def _line_chars(text: str, n: int, words: Mapping[str, int]) -> list[_Char]:
    drop = _mend_kerning(text, words)
    return [(c, n) for col, c in enumerate(text) if col not in drop]


def _broken_word(upper: str, lower: str) -> tuple[str, str] | None:
    """The two halves of a word a line ends inside and the next finishes."""
    head = re.search(r"([A-Za-z]+)-$", upper.rstrip())
    tail = re.match(r"\s*([a-z]+)", lower)
    if head is None or tail is None:
        return None
    return head.group(1), tail.group(1)


def _carries_on(upper: str, lower: str, heading: re.Pattern[str] | None) -> bool:
    """Whether ``lower`` is the rest of the sentence ``upper`` started.

    Two signs, either enough: ``upper`` ran to the margin, or ``lower`` opens
    in lower case after a line that did not end its sentence -- a table cell
    wrapping ("May be reduced to 30 feet if on" / "a cul-de-sac."). Never when
    ``lower`` opens a block of its own.
    """
    if _OPENS.match(lower) or (heading is not None and heading.match(lower)):
        return False
    upper = upper.rstrip()
    ended = re.search(r"[.:;]$", upper) is not None
    if re.match(r"\s*[a-z]", lower) and not ended:
        return True
    return len(upper) >= WIDTH and not (ended and re.match(r"\s*[A-Z(]", lower))


def _sentences(chars: list[_Char]) -> list[list[_Char]]:
    """One paragraph cut into sentences, each trimmed of its outer spaces."""
    text = "".join(c for c, _ in chars)
    cuts = [0]
    for found in _STOP.finditer(text):
        end = found.end()
        word = re.search(r"([A-Za-z.]+)\.?[\"')\]]*$", text[cuts[-1] : end])
        token = word.group(1).rstrip(".").lower() if word else ""
        if token in _ABBREVIATIONS or (len(token) == 1 and token.isalpha()):
            continue
        if len(text[cuts[-1] : end].split()) < 3:
            # "(2) Exceptions." and "TDC 40.300." are labels, not sentences.
            continue
        if _run_in(text[cuts[-1] : end]):
            continue
        cuts.append(end)
    cuts.append(len(text))
    out = []
    for a, b in zip(cuts, cuts[1:]):
        piece = chars[a:b]
        while piece and piece[0][0].isspace():
            piece = piece[1:]
        while piece and piece[-1][0].isspace():
            piece = piece[:-1]
        if piece:
            out.append(piece)
    return out


def clean(
    lines: Sequence[str],
    *,
    breaks: Iterable[int] = (),
    furniture: re.Pattern[str] | None = None,
    heading: re.Pattern[str] | None = None,
    words: Mapping[str, int] | None = None,
) -> Readable:
    """``lines`` of an extraction as readable text.

    ``breaks`` are the lines (1-based) a printed page starts on; one past the
    last line counts when the slice ends where its book does. ``heading`` is
    the jurisdiction's section heading, which always opens a line.
    """
    words = words or {}
    page_starts = sorted(set(breaks))
    # The first line opens the slice -- a section's heading -- whatever it
    # looks like.
    removed = _furniture(lines, page_starts, furniture) - {1}
    kept = [n for n in range(1, len(lines) + 1) if n not in removed]

    def crosses(a: int, b: int) -> bool:
        return any(a < brk <= b for brk in page_starts)

    paragraphs: list[list[_Char]] = []
    blank: list[int] = []  # paragraphs that are an empty printed line
    previous: int | None = None
    for n in kept:
        text = lines[n - 1]
        chars = _line_chars(text, n, words)
        joined = False
        if previous is not None and paragraphs and not crosses(previous, n) and text.strip():
            upper = lines[previous - 1]
            last = paragraphs[-1]
            broken = _broken_word(upper, text) if upper.strip() else None
            if broken is not None:
                head, tail = broken
                # The margin's hyphen goes; the word's own ("single-family")
                # stays. The code's own spelling decides which this is.
                whole, hyphened = f"{head}{tail}".lower(), f"{head}-{tail}".lower()
                margin = words.get(whole, 0) > words.get(hyphened, 0)
                while last and last[-1][0].isspace():
                    last.pop()
                if margin:
                    last.pop()  # the hyphen
                lead = len(text) - len(text.lstrip())
                last.extend(chars[lead:])
                joined = True
            elif _carries_on(upper, text, heading):
                while last and last[-1][0].isspace():
                    last.pop()
                last.append((" ", None))
                lead = len(text) - len(text.lstrip())
                last.extend(chars[lead:])
                joined = True
        if not joined:
            paragraphs.append(chars)
            if not text.strip():
                blank.append(len(paragraphs) - 1)
        previous = n

    out_lines: list[str] = []
    out_sources: list[tuple[int, ...]] = []
    empty = set(blank)
    for k, paragraph in enumerate(paragraphs):
        if k in empty:
            src = {n for _, n in paragraph if n is not None}
            out_lines.append("")
            # An empty printed line still has a number; keep it, so it is
            # somewhere to point.
            out_sources.append(tuple(sorted(src)) or ())
            continue
        for sentence in _sentences(paragraph):
            out_lines.append("".join(c for c, _ in sentence))
            out_sources.append(tuple(sorted({n for _, n in sentence if n is not None})))
    # An empty line carries no characters, so it is told its number here.
    numbered = iter(n for n in kept if not lines[n - 1].strip())
    fixed: list[tuple[int, ...]] = []
    for line, src in zip(out_lines, out_sources):
        fixed.append((next(numbered),) if line == "" and not src else src)
    return Readable(tuple(out_lines), tuple(fixed), tuple(sorted(removed)))


def _squashed(text: str) -> str:
    return re.sub(r"\s+", "", text)


def prove(
    lines: Sequence[str],
    readable: Readable,
    *,
    breaks: Iterable[int] = (),
    furniture: re.Pattern[str] | None = None,
) -> list[str]:
    """Every way ``readable`` is not the words of ``lines``. Empty is proof.

    Written without :func:`clean`'s workings, so a mistake in one is not
    repeated in the other.
    """
    problems: list[str] = []
    page_starts = sorted(set(breaks))
    allowed = _furniture(lines, page_starts, furniture)
    stray = sorted(set(readable.removed) - allowed)
    if stray:
        problems.append(f"lines {stray} were removed and are not page furniture")
    removed = set(readable.removed)

    # The letters, in order: the extraction's, less only margin hyphens.
    want: list[tuple[str, bool]] = []
    for n, text in enumerate(lines, start=1):
        if n in removed:
            continue
        body = _squashed(text)
        for k, c in enumerate(body):
            margin = c == "-" and k == len(body) - 1 and k > 0 and body[k - 1].isalpha()
            want.append((c, margin))
    got = _squashed("".join(readable.lines))
    i = j = 0
    while i < len(want) and j < len(got):
        c, optional = want[i]
        if c == got[j]:
            i += 1
            j += 1
        elif optional:
            i += 1
        else:
            problems.append(
                f"the text parts from the extraction at {got[max(0, j - 30) : j + 10]!r}"
            )
            return problems
    if j < len(got) or any(not optional for _, optional in want[i:]):
        problems.append("the readable text and the extraction end differently")

    for k, src in enumerate(readable.sources, start=1):
        if any(src[0] < brk <= src[-1] for brk in page_starts) if src else False:
            problems.append(f"readable line {k} runs across a page")
    if len(readable.sources) != len(readable.lines):
        problems.append("a readable line has no source")
    return problems


def align(
    lines: Sequence[str],
    text: Sequence[str],
    *,
    breaks: Iterable[int] = (),
    furniture: re.Pattern[str] | None = None,
) -> tuple[tuple[int, ...], ...] | None:
    """Each line of a readable text that was written earlier, as extraction lines.

    For text already on disk, made by whatever cleaning was current then: its
    letters are the extraction's in order, less the page furniture and the
    margin hyphens, so walking the two side by side says which printed lines
    every readable line came from. That is what lets a citation of the old
    text be re-addressed after a re-cut. None when the letters part.
    """
    removed = _furniture(lines, sorted(set(breaks)), furniture) - {1}
    want: list[tuple[str, bool, int]] = []
    for n, raw in enumerate(lines, start=1):
        if n in removed:
            continue
        body = _squashed(raw)
        for k, c in enumerate(body):
            margin = c == "-" and k == len(body) - 1 and k > 0 and body[k - 1].isalpha()
            want.append((c, margin, n))
    i = 0
    out: list[tuple[int, ...]] = []
    for line in text:
        held: list[int] = []
        for c in _squashed(line):
            while i < len(want) and want[i][0] != c and want[i][1]:
                i += 1
            if i == len(want) or want[i][0] != c:
                return None
            if not held or held[-1] != want[i][2]:
                held.append(want[i][2])
            i += 1
        out.append(tuple(held))
    if any(not optional for _, optional, _n in want[i:]):
        return None
    return tuple(out)


__all__ = ["BAND", "VERSION", "WIDTH", "Readable", "align", "clean", "prove", "vocabulary"]
