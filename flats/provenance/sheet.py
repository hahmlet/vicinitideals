"""Where on the printed page an encoded number sits.

Signing checks a number against our *text copy* of the code, and the text copy
is the one place the commonest real error cannot be seen. A standard read off
the right line but the wrong column -- R5's 10 ft filed under R7 -- reads
correctly in the extracted line, because extraction flattened the grid that said
which number belonged to which zone. On the printed table it is obvious.

So the page check shows the printed page itself, with a box drawn on the cell
the quote came from, and asks one question of it. This module finds the box.

How, and why it is safe to be approximate here when the page map refuses to be:

* The page comes from the page map (``pages.py``), which is exact or absent.
* On that page, the quoted line is found among the page's own printed lines --
  words and their positions read from the PDF's text layer with PDFium, a
  second reader independent of the pypdf extraction that made the text copy.
  The two agree on the characters and disagree on spacing, so lines are
  compared with the spaces taken out.
* On that line, every word that states the encoded number is boxed.

Nothing here is a claim. The box is a pointer, and the reviewer looking at it
is the check: a box on the wrong cell is one of the three answers a card offers.
Where a step fails -- no map, the line not found, the number not printed as a
numeral (a "P" in a use table, a density worked out from a lot size) -- the card
says so and falls back to highlighting the quoted lines, or to the bare page.

Superscripts are read as what they are. A footnote marker prints smaller and
higher than the number it qualifies, and PDFium sees both, so "10 ft.⁵" comes
back as the value and a marker ``5``. Those markers are what the follow-up
cards ask about: one card per note that touches the boxed number.
"""

from __future__ import annotations

import difflib
import hashlib
import re
import statistics
import threading
from functools import lru_cache
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from flats.provenance.store import ProvenanceError, ProvenanceStore

#: Rendered page images, keyed by the book's hash and the page. Derived and
#: reproducible, so under ``data/`` beside the books they are drawn from.
PNG_CACHE = Path(__file__).resolve().parents[2] / "data" / "flats" / "sheets"

#: Pixels per PDF point. A US-letter page comes out 1,275 px wide: a table's
#: footnote markers stay legible without a zoom, and a page stays under ~400 KB.
SCALE = 125 / 72

#: A character this much shorter than its line's median is a superscript.
#: Measured on Gresham's setback table, where the markers print at 60-70% of
#: the body size; body glyphs of one font vary by far less than this.
_SUPERSCRIPT = 0.8

#: How closely a printed line must match the quoted one. pypdf and PDFium
#: agree on characters and disagree on spacing and on where a superscript
#: goes, so with spaces removed a true match scores ~0.95 and a neighbouring
#: row of the same table ~0.6.
_MATCH = 0.82


@dataclass(frozen=True, slots=True)
class Box:
    """A rectangle on the rendered page, as fractions of its width and height.

    Fractions rather than points so the page image can be drawn at any size and
    the box laid over it with plain percentages.
    """

    x0: float
    y0: float
    x1: float
    y1: float

    def union(self, other: Box) -> Box:
        return Box(
            min(self.x0, other.x0),
            min(self.y0, other.y0),
            max(self.x1, other.x1),
            max(self.y1, other.y1),
        )

    def pad(self, by: float = 0.003) -> Box:
        return Box(
            max(self.x0 - by, 0.0),
            max(self.y0 - by, 0.0),
            min(self.x1 + by, 1.0),
            min(self.y1 + by, 1.0),
        )

    def css(self) -> str:
        """The box as an absolutely positioned overlay on the page image."""
        return (
            f"left:{self.x0 * 100:.2f}%;top:{self.y0 * 100:.2f}%;"
            f"width:{(self.x1 - self.x0) * 100:.2f}%;height:{(self.y1 - self.y0) * 100:.2f}%"
        )


@dataclass(frozen=True, slots=True)
class Word:
    """A run of characters with no gap in it, as printed."""

    text: str
    box: Box
    #: Printed smaller and higher than its line: a footnote marker.
    sup: bool = False


@dataclass(frozen=True, slots=True)
class Line:
    """One printed line of a page, words left to right."""

    words: tuple[Word, ...]

    @property
    def box(self) -> Box:
        out = self.words[0].box
        for word in self.words[1:]:
            out = out.union(word.box)
        return out

    @property
    def key(self) -> str:
        return squash(" ".join(w.text for w in self.words))


@dataclass(frozen=True, slots=True)
class Sheet:
    """One page as printed: its lines top to bottom, and its shape."""

    n: int
    lines: tuple[Line, ...]
    #: Width over height of the page as displayed (after any rotation).
    aspect: float = 612 / 792


# --- reading a page ------------------------------------------------------


def squash(text: str) -> str:
    """A line with everything the two readers disagree about taken out.

    Spaces go because pypdf's layout mode pads columns with them and PDFium
    reports none. Case goes because letter-spaced headings come back cased
    either way. Everything outside printable ASCII goes because that is where
    the two readers decode differently: a glyph pypdf could not map is stored
    as a replacement character where PDFium reads "ç", and a bullet or a curly
    quote comes back as a different code point from each.
    """
    return re.sub(r"[^!-~]+", "", text).lower()


def _rotate(u: float, v: float, rotation: int) -> tuple[float, float]:
    """A point on the unrotated page, as it lands on the page as displayed.

    PDFium reports character positions in the page's own coordinates and
    renders the page turned by its ``/Rotate``. A landscape table printed on
    a portrait page turned 90 degrees is common in these codes.
    """
    if rotation == 90:
        return 1 - v, u
    if rotation == 180:
        return 1 - u, 1 - v
    if rotation == 270:
        return v, 1 - u
    return u, v


def _chars(page: Any) -> tuple[list[tuple[str, float, float, float, float, bool]], float]:
    """Every printed character with its box on the page as displayed.

    The last field says a space came before it. Spaces are not kept as
    characters -- PDFium generates them for visual gaps and gives them no
    useful box -- but they are word breaks, and some books (Gresham's downtown
    chapter) set words so tight that the gap alone does not show it.
    """
    left, bottom, right, top = page.get_cropbox()
    width, height = (right - left) or 1.0, (top - bottom) or 1.0
    rotation = page.get_rotation() % 360
    textpage = page.get_textpage()
    out = []
    spaced = False
    try:
        for i in range(textpage.count_chars()):
            char = textpage.get_text_range(i, 1)
            if not char.strip():
                spaced = True
                continue
            # Loose boxes: the font's ascent and descent rather than the ink.
            # With ink boxes a comma sits below its line and a capital above
            # it, and the line grouping below splits one printed row in two.
            l, b, r, t = textpage.get_charbox(i, loose=True)
            corners = [
                _rotate((x - left) / width, (top - y) / height, rotation)
                for x, y in ((l, t), (r, b))
            ]
            xs, ys = [c[0] for c in corners], [c[1] for c in corners]
            out.append((char, min(xs), min(ys), max(xs), max(ys), spaced))
            spaced = False
    finally:
        textpage.close()
    aspect = width / height if rotation in (0, 180) else height / width
    return out, aspect


def _group(
    chars: Sequence[tuple[str, float, float, float, float, bool]], aspect: float
) -> tuple[Line, ...]:
    """Characters into printed lines, and each line into words.

    A character joins the line whose vertical middle it overlaps by half its
    height. A superscript overlaps its line well past that, so it stays on the
    row it qualifies -- which is the row a reader would say it is on. A gap
    wider than a fifth of the line's text height starts a new word; a change
    between body and superscript size does too, so a marker never fuses onto
    the number it follows.
    """
    rows: list[dict[str, Any]] = []
    for char in chars:
        _c, _x0, y0, _x1, y1, _sp = char
        middle, height = (y0 + y1) / 2, y1 - y0
        for row in reversed(rows[-12:]):
            if abs(row["mid"] - middle) < min(row["h"], height) * 0.5:
                row["chars"].append(char)
                break
        else:
            rows.append({"mid": middle, "h": height, "chars": [char]})

    lines = []
    for row in sorted(rows, key=lambda r: r["mid"]):
        chars_in = sorted(row["chars"], key=lambda c: c[1])
        body = statistics.median(c[4] - c[2] for c in chars_in)
        words: list[list[Any]] = []
        last: tuple[float, bool] | None = None
        for text, x0, y0, x1, y1, spaced in chars_in:
            sup = (y1 - y0) < body * _SUPERSCRIPT
            # Gaps measured in page heights on both axes, so a wide page's
            # fractions do not read as narrower gaps than a tall one's.
            gap = (x0 - last[0]) * aspect if last else 0.0
            if last is None or spaced or gap > body * 0.2 or sup != last[1]:
                words.append([text, x0, y0, x1, y1, sup])
            else:
                w = words[-1]
                w[0] += text
                w[3], w[2], w[4] = max(w[3], x1), min(w[2], y0), max(w[4], y1)
            last = (x1, sup)
        lines.append(
            Line(tuple(Word(w[0], Box(w[1], w[2], w[3], w[4]), w[5]) for w in words))
        )
    return tuple(lines)


def read(book: Path, n: int) -> Sheet:
    """Page ``n`` (1-based) of a book, as printed lines of positioned words.

    Cached: a card, the card after it and the note cards between them read
    the same table page. Keyed by the file's modification time as well as its
    path, because the book cache replaces a re-published edition in place.
    """
    return _read(book, n, book.stat().st_mtime_ns)


#: PDFium is not thread-safe, and the web app reads pages from a thread pool:
#: two requests opening books at once fail with "Data format error" on a good
#: file. Every call into it goes through this one lock.
_PDFIUM = threading.Lock()


@lru_cache(maxsize=128)
def _read(book: Path, n: int, _edition: int) -> Sheet:
    import pypdfium2 as pdfium

    with _PDFIUM:
        pdf = pdfium.PdfDocument(str(book))
        try:
            if not 1 <= n <= len(pdf):
                raise ProvenanceError(f"{book.name} has no page {n}")
            page = pdf[n - 1]
            try:
                chars, aspect = _chars(page)
            finally:
                page.close()
        finally:
            pdf.close()
    return Sheet(n=n, lines=_group(chars, aspect), aspect=aspect)


def render(book: Path, n: int) -> Path:
    """Page ``n`` of a book as a PNG, drawn once and kept.

    Keyed by the book's own hash, so a re-published edition can never be
    served a picture of the edition before it.
    """
    import pypdfium2 as pdfium

    digest = hashlib.sha256(book.read_bytes()).hexdigest()[:16]
    target = PNG_CACHE / f"{digest}-{n}.png"
    if target.is_file():
        return target
    with _PDFIUM:
        pdf = pdfium.PdfDocument(str(book))
        try:
            if not 1 <= n <= len(pdf):
                raise ProvenanceError(f"{book.name} has no page {n}")
            page = pdf[n - 1]
            try:
                image = page.render(scale=SCALE).to_pil()
            finally:
                page.close()
        finally:
            pdf.close()
    PNG_CACHE.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".tmp")
    image.save(partial, format="PNG", optimize=True)
    partial.replace(target)
    return target


# --- finding the number --------------------------------------------------


_NUMERAL = re.compile(r"^[($\[]?(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(?:\s*(%))?")
_FRACTIONS = {"½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 1 / 3, "⅔": 2 / 3}

#: Numbers the older codes spell out -- Oregon City states nearly every
#: standard in words ("Minimum building height: Sixty feet.").
_UNITS = {
    w: n
    for n, w in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve "
        "thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
    )
}
_TENS = {
    w: 10 * n
    for n, w in enumerate(
        "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
    )
    if w != "_"
}


def _spelled(word: str) -> float | None:
    """A number spelled as one word: "Twenty", "fifty-eight", "Eighty-five"."""
    parts = re.sub(r"[^a-z-]", "", word.lower()).split("-")
    if len(parts) == 1:
        found = _UNITS.get(parts[0], _TENS.get(parts[0]))
        return None if found is None else float(found)
    if len(parts) == 2 and parts[0] in _TENS and parts[1] in _UNITS and 0 < _UNITS[parts[1]] < 10:
        return float(_TENS[parts[0]] + _UNITS[parts[1]])
    return None


def numeral(text: str) -> tuple[float, bool] | None:
    """The number a printed word states, and whether it is a percentage.

    Only a word that *starts* with a numeral states a number. "LDR-5" names a
    zone, and a 5 read out of it is how a zone code gets boxed as a setback.
    "10ft." and "5,000" state numbers; "2½" does too, and so does "Sixty".
    """
    word = text.strip()
    found = _NUMERAL.match(word)
    if not found:
        if word[:1] in _FRACTIONS:
            return _FRACTIONS[word[0]], False
        spelled = _spelled(word)
        return None if spelled is None else (spelled, False)
    whole = float(found.group(1).replace(",", "") + (found.group(2) or ""))
    rest = word[found.end():]
    if rest[:1] in _FRACTIONS:
        whole += _FRACTIONS[rest[0]]
    return whole, bool(found.group(3)) or rest.startswith("%")


def _equal(read_off: tuple[float, bool] | None, value: float) -> bool:
    if read_off is None:
        return False
    number, percent = read_off
    if abs(number - value) < 1e-9:
        return True
    return percent and abs(number / 100 - value) < 1e-9


def states(word: Word, value: Any) -> bool:
    """Whether a printed word states this encoded value.

    A percentage matches a share stored either way (50 or 0.5), because the
    rule files hold both forms and a reviewer is asking about the page.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)) or word.sup:
        return False
    if _equal(numeral(word.text), value):
        return True
    # "20/25" -- Wilsonville prints two standards in one cell, one per lot
    # type. Either half states a number; the reviewer reads which from the
    # column heading.
    return "/" in word.text and any(
        _equal(numeral(part), value) for part in word.text.split("/")[1:]
    )


#: Characters a letter-spaced numeral is broken into.
_DIGITISH = re.compile(r"^[\d,.]+$")


def hits(line: Line, value: Any, aspect: float = 1.0) -> list[tuple[int, int]]:
    """Where on a printed line the encoded number is stated, as word spans.

    Usually one word. Letter-spaced books break a numeral into several --
    Oregon City prints "10,000" as "1 0 , 000" -- so runs of digit-only words
    set closer than a column gap are tried joined as well. A column gap is
    wider than a character; letter spacing is narrower.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return []
    words = line.words
    out: list[tuple[int, int]] = []
    i = 0
    while i < len(words):
        if states(words[i], value):
            out.append((i, i))
            i += 1
            continue
        if not words[i].sup and _DIGITISH.match(words[i].text):
            height = words[i].box.y1 - words[i].box.y0
            text, j = words[i].text, i
            while j + 1 < len(words) and j - i < 6:
                nxt = words[j + 1]
                gap = (nxt.box.x0 - words[j].box.x1) * aspect
                if nxt.sup or gap > height * 0.9 or not re.match(r"^[\d,.]", nxt.text):
                    break
                j += 1
                text += nxt.text
                if _equal(numeral(text), value) and not (
                    j + 1 < len(words)
                    and _DIGITISH.match(words[j + 1].text)
                    and (words[j + 1].box.x0 - words[j].box.x1) * aspect <= height * 0.9
                ):
                    out.append((i, j))
                    break
            if out and out[-1][0] == i:
                i = out[-1][1] + 1
                continue
        i += 1
    return out


def span_box(line: Line, span: tuple[int, int]) -> Box:
    out = line.words[span[0]].box
    for word in line.words[span[0] + 1 : span[1] + 1]:
        out = out.union(word.box)
    return out


def _ratio(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def _within(lines: Sequence[Line], want: str) -> Line | None:
    """The run of printed words that is the stored line, inside a longer line.

    A table whose cells wrap is read two ways: pypdf gives the label cell's
    "Rear Yard 20 feet" a line of its own, PDFium prints it on one line with
    the next cell's "waived for townhouses ...". The stored line is then a
    whole-word run inside the printed one. Taken only when exactly one run on
    the page spells it, and handed back as that run alone, so the box and the
    row label are read from the cell and not from its neighbour.
    """
    if len(want) < 8:
        return None
    found: list[Line] = []
    for line in lines:
        keys = [squash(w.text) for w in line.words]
        for a in range(len(keys)):
            run = ""
            for b in range(a, len(keys)):
                run += keys[b]
                if len(run) >= len(want):
                    if run == want and keys[a]:
                        found.append(Line(tuple(line.words[a : b + 1])))
                    break
    return found[0] if len(found) == 1 else None


def _side_by_side(sheet: Sheet) -> list[Line]:
    """Pairs of printed lines that pypdf may have read as one.

    A table cell centres its text vertically, so "Side" in the label column
    and "5 feet" in the value column can sit a few points apart -- two lines
    to PDFium, one to pypdf's looser grouping. Two neighbouring lines whose
    words do not overlap left to right, and which sit within most of a line
    height of each other, are offered joined as well.
    """
    out = []
    for upper, lower in zip(sheet.lines, sheet.lines[1:]):
        a, b = upper.box, lower.box
        height = max(a.y1 - a.y0, b.y1 - b.y0)
        if b.y0 - a.y1 > height * 0.6:
            continue
        overlap = any(
            w.box.x0 < v.box.x1 and w.box.x1 > v.box.x0
            for w in upper.words
            for v in lower.words
        )
        if not overlap:
            out.append(Line(tuple(sorted(upper.words + lower.words, key=lambda w: w.box.x0))))
    return out


def find(sheet: Sheet, stored: str, before: str = "", after: str = "") -> Line | None:
    """The printed line that is this stored line, or None.

    Exact after squashing is the common case. Otherwise the closest line
    above the match threshold. Where two printed lines tie -- a table repeats
    rows ("Façade: 10  Façade: 10") -- the lines either side decide it, and if
    they cannot, nothing is returned: a tie is a guess.
    """
    want = squash(stored)
    if len(want) < 3:
        return None
    lines = list(sheet.lines)
    scored = sorted(
        ((_ratio(want, line.key), i) for i, line in enumerate(lines)),
        reverse=True,
    )
    if not scored or scored[0][0] < _MATCH:
        # Only now the joined pairs: they are a repair for a split row, and
        # offered up front they would compete with the rows that are whole.
        joined = _side_by_side(sheet)
        best = sorted(((_ratio(want, line.key), i) for i, line in enumerate(joined)), reverse=True)
        if best and best[0][0] >= _MATCH and (len(best) == 1 or best[1][0] < best[0][0] - 0.03):
            return joined[best[0][1]]
        return _within(lines, want)
    tied = [i for score, i in scored if score > scored[0][0] - 0.03]
    if len(tied) == 1:
        return lines[tied[0]]
    around = []
    for i in tied:
        prev = lines[i - 1].key if i > 0 else ""
        nxt = lines[i + 1].key if i + 1 < len(lines) else ""
        around.append((_ratio(squash(before), prev) + _ratio(squash(after), nxt), i))
    around.sort(reverse=True)
    if around[0][0] - around[1][0] < 0.2:
        return None
    return lines[around[0][1]]


@dataclass(frozen=True, slots=True)
class Marker:
    """A footnote marker printed on the boxed number, its row or its column."""

    mark: str
    #: "number", "row" or "column": where on the table the marker is printed,
    #: which is what a reader needs to judge its reach.
    on: str
    box: Box


def _marks(text: str) -> list[str]:
    """The note numbers one superscript word carries: "6,7" is two notes."""
    return [m for m in re.split(r"[,\s]+", text.strip()) if m]


def markers(sheet: Sheet, line: Line, spans: Sequence[tuple[int, int]]) -> list[Marker]:
    """The footnote markers that bear on the boxed words.

    Three places, the three a reader checks: a marker printed straight after
    the number; one on the row's label (before the first number on the row);
    and one printed in the column heading above the number, found by looking
    up the page for superscripts sitting over the number's horizontal span.
    """
    out: list[Marker] = []
    words = line.words
    for _first, last in spans:
        # Straight after the number, or after its unit: "10 ft.⁵" prints the
        # marker on the unit. Stops at the next number, whose marker it is.
        for word in words[last + 1 : last + 4]:
            if word.sup:
                out += [Marker(m, "number", word.box) for m in _marks(word.text)]
                break
            if numeral(word.text):
                break
    first_numeral = next(
        (i for i, w in enumerate(words) if not w.sup and numeral(w.text)), len(words)
    )
    for word in words[:first_numeral]:
        if word.sup:
            out += [Marker(m, "row", word.box) for m in _marks(word.text)]
    above = [ln for ln in sheet.lines if ln.box.y1 <= line.box.y0]
    for span in spans:
        box = span_box(line, span)
        for printed in reversed(above[-8:]):
            for word in printed.words:
                if word.sup and word.box.x0 < box.x1 and word.box.x1 > box.x0:
                    out += [Marker(m, "column", word.box) for m in _marks(word.text)]
    seen: set[str] = set()
    unique = []
    for marker in out:
        if marker.mark not in seen:
            seen.add(marker.mark)
            unique.append(marker)
    return unique


@dataclass(frozen=True, slots=True)
class Found:
    """What a card can show for one cited line."""

    line_no: int
    page: int
    #: The printed line, or None where it could not be found on its page.
    line: Line | None = None
    #: Word spans on it that state the encoded number.
    hits: tuple[tuple[int, int], ...] = ()


@dataclass
class Placed:
    """Everything a card draws on the page for one number.

    ``status`` is what the card says about its own box, in words a reviewer
    can act on -- the card's honesty about how much it found.
    """

    status: str
    pages: list[int] = field(default_factory=list)
    #: page -> [(box, kind)] where kind is "value", "line" or "note".
    boxes: dict[int, list[tuple[Box, str]]] = field(default_factory=dict)
    markers: list[Marker] = field(default_factory=list)
    marker_page: int | None = None
    aspect: dict[int, float] = field(default_factory=dict)

    @property
    def first(self) -> int | None:
        for page, boxes in self.boxes.items():
            if any(kind == "value" for _b, kind in boxes):
                return page
        return self.pages[0] if self.pages else None


#: What a card says about its own box. Keys are stable; the words are for
#: the reviewer and may change.
PLACED = {
    "boxed": "the box is where we read the number",
    "column": "the number is printed more than once on the quoted line -- the box is the one under this zone's heading",
    "several": "the number is printed more than once on the quoted line -- every one is boxed",
    "lines": "the number is not printed as a numeral on the quoted line -- the whole line is marked",
    "unfound": "we could not find the quoted line on the printed page -- the page is shown unmarked",
    "no_map": "this document has no page map yet, so there is no page to show",
    "html": "this code is published as a web page, not a printed book",
}


def under_heading(
    sheet: Sheet, line: Line, spans: Sequence[tuple[int, int]], zone: str
) -> list[tuple[int, int]]:
    """The hits printed under this zone's column heading, where there is one.

    Most dimensional tables print one column per zone, so a row states the
    same number several times and only one of them is this zone's. The
    heading is looked for above the row on the same page; a hit belongs to it
    when the two overlap horizontally. Where the table prints zones as rows
    instead, no heading is found and every hit stays boxed -- the reviewer
    reads the column off the page, which is the check.
    """
    want = squash(zone)
    if not want or want.startswith("("):
        return list(spans)
    boxes = [(span, span_box(line, span)) for span in spans]
    above = [ln for ln in sheet.lines if ln.box.y1 <= line.box.y0]
    for printed in reversed(above[-30:]):
        for word in printed.words:
            if word.sup or squash(word.text).strip(",;:*") != want:
                continue
            under = [s for s, b in boxes if b.x0 < word.box.x1 and b.x1 > word.box.x0]
            if len(under) == 1:
                return under
    return list(spans)


def place(
    sheets: dict[int, Sheet],
    found_on: Iterable[tuple[int, int, str, str, str]],
    value: Any,
    *,
    zone: str = "",
) -> Placed:
    """Box a number on the pages its quote spans.

    ``found_on`` is (line number, page, stored text, the stored line before,
    the stored line after) for each cited line -- the page from the map, the
    text from the store, the neighbours to break a tie between repeated rows.
    """
    found: list[Found] = []
    columned = False
    for line_no, page, stored, before, after in found_on:
        sheet = sheets.get(page)
        printed = find(sheet, stored, before, after) if sheet else None
        spans = tuple(hits(printed, value, sheet.aspect)) if sheet and printed else ()
        narrowed = False
        if sheet and printed and len(spans) > 1:
            under = under_heading(sheet, printed, spans, zone)
            narrowed = len(under) < len(spans)
            spans = tuple(under)
        columned = columned or narrowed
        found.append(Found(line_no, page, printed, spans))

    pages = sorted({f.page for f in found})
    placed = Placed(status="unfound", pages=pages)
    placed.aspect = {n: sheets[n].aspect for n in pages if n in sheets}
    with_hits = [f for f in found if f.hits]
    for f in found:
        if f.line is None:
            continue
        kind_boxes = placed.boxes.setdefault(f.page, [])
        if f.hits:
            kind_boxes += [(span_box(f.line, span).pad(), "value") for span in f.hits]
        else:
            kind_boxes.append((f.line.box.pad(0.002), "line"))
    if with_hits:
        total = sum(len(f.hits) for f in with_hits)
        placed.status = ("column" if columned else "boxed") if total == 1 else "several"
        first = with_hits[0]
        placed.markers = markers(sheets[first.page], first.line, first.hits)
        placed.marker_page = first.page
    elif any(f.line for f in found):
        placed.status = "lines"
    return placed


# --- the notes -----------------------------------------------------------


def note_line(text: Sequence[str], mark: str, after: int, *, reach: int = 600) -> int | None:
    """The stored line where note ``mark`` is printed, after the table citing it.

    Notes follow their table, numbered at the start of a line: "5. Where an
    alley..." or "(5) Where..." or a bare "5 Where...". Searched forward from
    the cited line, a few hundred lines at most -- the next table's note 5 is
    not this table's.
    """
    shape = re.compile(rf"^\s*(?:\(?{re.escape(mark)}[.)]|{re.escape(mark)}\s+[A-Z])")
    for n in range(after, min(after + reach, len(text)) + 1):
        if shape.match(text[n - 1]):
            return n
    return None


#: The start of any numbered note: "5.", "(5)", "12)".
_NOTE_START = re.compile(r"^\s*\(?\d{1,2}[.)]\s")


def starts_note(line: str) -> bool:
    """Whether a stored line opens a numbered note -- where the one before ends."""
    return bool(_NOTE_START.match(line))


def lines_of(store: ProvenanceStore, document: str) -> list[str]:
    try:
        return store.load(document).text.split("\n")
    except (ProvenanceError, OSError):
        return []


#: The most cited lines a card looks for on the page. A citation naming a
#: whole section is not boxable in any useful sense, and finding each of its
#: lines is a second of work per card for nothing a reviewer can use.
_MOST_LINES = 40


#: How far into the page from the top or bottom edge a running head or foot
#: may sit, as a share of the page height.
_MARGIN = 0.1


def _running_key(line: Line) -> str:
    """A line's letters alone: what a running head keeps from page to page.

    The page number and section number change; "Oregon City Supp. No." and
    "City of Gresham Development Code" do not. A line of nothing but numbers
    keys as "#", so a bare page number matches the next page's.
    """
    letters = "".join(ch for ch in squash(" ".join(w.text for w in line.words)) if ch.isalpha())
    return letters or "#"


@lru_cache(maxsize=256)
def _running(book: Path, n: int) -> tuple[Box, ...]:
    """The running heads and feet printed on page ``n``.

    A citation that crosses a page break quotes the foot of one page and the
    head of the next, because the text copy has them inline. They are not
    rules, and drawing them as rules says the code put a standard in its page
    footer. A line counts as running when it sits near the top or bottom edge
    and a line with the same letters sits at the same height on a page nearby.
    """
    sheet = read(book, n)
    edge = [ln for ln in sheet.lines if ln.box.y1 < _MARGIN or ln.box.y0 > 1 - _MARGIN]
    if not edge:
        return ()
    near: list[Sheet] = []
    for m in (n - 2, n - 1, n + 1, n + 2):
        if m < 1:
            continue
        try:
            near.append(read(book, m))
        except Exception:  # noqa: BLE001 — past the last page
            continue
    out = []
    for line in edge:
        key = _running_key(line)
        for other in near:
            if any(
                abs(o.box.y0 - line.box.y0) < 0.012 and _running_key(o) == key
                for o in other.lines
            ):
                out.append(line.box)
                break
    return tuple(out)


def _is_running(line: Line, running: Sequence[Box]) -> bool:
    box = line.box
    return any(
        abs(r.y0 - box.y0) < 0.004 and box.x0 < r.x1 and r.x0 < box.x1 for r in running
    )


def locate(
    store: ProvenanceStore,
    document: str,
    ranges: Sequence[tuple[int, int]],
    value: Any,
    *,
    zone: str = "",
    get: Any = None,
) -> Placed:
    """Box an encoded number on the printed pages its citation names.

    The page comes from the document's page map and the book from the cache
    that map pins. With no map there is no page to show, and the card says so
    rather than guessing one -- a box on the wrong sheet is the failure this
    whole check exists to catch.
    """
    from flats.provenance import books, pages as page_map

    index = page_map.read(store, document)
    if index is None:
        return Placed(status="no_map")
    text = lines_of(store, document)
    cited: list[tuple[int, int, str, str, str]] = []
    for first, last in ranges:
        for n in range(first, last + 1):
            if not (1 <= n <= len(text)) or not text[n - 1].strip():
                continue
            page = index.at(n)
            if page is None:
                continue
            before = next((text[k - 1] for k in range(n - 1, 0, -1) if text[k - 1].strip()), "")
            after = next(
                (text[k - 1] for k in range(n + 1, len(text) + 1) if text[k - 1].strip()), ""
            )
            cited.append((n, page.n, text[n - 1], before, after))
    cited = cited[:_MOST_LINES]
    if not cited:
        return Placed(status="unfound")
    try:
        book = books.ensure(store, document, get=get)
    except books.BookError:
        return Placed(status="no_map")
    sheets = {n: read(book, n) for n in sorted({c[1] for c in cited})}
    kept = []
    for entry in cited:
        running = _running(book, entry[1])
        found = find(sheets[entry[1]], entry[2], entry[3], entry[4]) if running else None
        # A table continued across pages repeats its heading rows at the same
        # height, which reads exactly like a running head. Never drop the line
        # the number itself is printed on.
        if (
            found is None
            or not _is_running(found, running)
            or hits(found, value, sheets[entry[1]].aspect)
        ):
            kept.append(entry)
    if not kept:
        return Placed(status="unfound")
    return place(sheets, kept, value, zone=zone)
