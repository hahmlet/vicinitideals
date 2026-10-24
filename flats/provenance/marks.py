"""Superscripts and footnote marks in the readable code text, placed from the book.

The stored text cannot show a raised character: "1" with a raised "3" after it
is "13" on the line, and so is the number thirteen. The book knows the
difference -- the raised one is smaller and sits above the line --
so ``scripts/flats_marks_propose.py`` records every such character, per book,
in ``flats/provenance/marks/<book sha256>.json``, each with the characters
printed either side of it in the order the PDF stores them.

Here each one is found in the stored lines of the page it is printed on, by
that context: the characters before, the mark, the characters after, with the
spaces taken out, must occur exactly once among that page's lines. Found
twice or not at all, the mark is left out -- it is shown as the text always
showed it, never guessed into place.

Like tables, this changes no text and moves no citation: it says which
characters of which line were printed raised. A mark printed right against a
digit (``glued``) is the case that can change a number, so it is listed for
the readers of that line to check.

A footnote is linked to its mark when the book makes the link plain: the note
line starts with the same mark, printed raised, after it; or, failing that, a
"Notes" heading follows the mark and the first line under it starts with the
mark's text. Anything less certain stays unlinked.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Sequence

from flats.provenance import pages as page_map
from flats.provenance.store import ProvenanceError, ProvenanceStore

#: Where the per-book mark files live, beside the store.
MARKS = Path(__file__).resolve().parent / "marks"

#: The name of this placement, shown with the marks so a change is visible.
VERSION = "marks/1"

#: Context widths tried, narrowest first; the first that is unique wins.
_WIDTHS = (8, 12, 16, 24)

#: A notes heading: "Notes:", "Footnotes", "Table 4.0120 Table Notes:".
_NOTES = re.compile(r"^\s*(?:\S.{0,50}\s)?(?:foot)?notes?\s*:?\s*$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Mark:
    """Characters of one stored line that the book prints raised."""

    line: int
    start: int
    end: int
    text: str
    #: Printed against a digit with no space: "1" then a raised "3" reads "13".
    glued: bool
    #: The line of the note this mark refers to, when the book makes it plain.
    note: int = 0
    #: This mark starts its line: it numbers a note rather than pointing to one.
    numbers_note: bool = False


def _norm(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKC", text) if not ch.isspace())


@lru_cache(maxsize=64)
def _book(sha: str, root: Path = MARKS) -> dict[int, tuple[tuple[str, str, str], ...]]:
    path = root / f"{sha}.json"
    if not sha or not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("book") != sha:
        return {}
    return {
        int(n): tuple((m["text"], m["before"], m["after"]) for m in found)
        for n, found in raw["pages"].items()
    }


def _stream(lines: Sequence[str], first: int, last: int) -> tuple[str, list[tuple[int, int]]]:
    """The page's characters, spaces out, each with its (line, column)."""
    chars: list[str] = []
    where: list[tuple[int, int]] = []
    for n in range(first, last + 1):
        for col, ch in enumerate(lines[n - 1]):
            if ch.isspace():
                continue
            for part in unicodedata.normalize("NFKC", ch):
                if not part.isspace():
                    chars.append(part)
                    where.append((n, col))
    return "".join(chars), where


def _only(haystack: str, needle: str) -> int:
    """Where ``needle`` occurs in ``haystack``, if it occurs exactly once; else -1."""
    at = haystack.find(needle)
    if at < 0 or haystack.find(needle, at + 1) >= 0:
        return -1
    return at


def _locate(stream: str, text: str, before: str, after: str) -> int:
    """Where the mark's first character is in the stream, or -1."""
    for width in _WIDTHS:
        b, a = before[-width:], after[:width]
        at = _only(stream, b + text + a)
        if at >= 0:
            return at + len(b)
        if stream.count(b + text + a) == 0:
            break
    # Printed at the end or start of a run the text ordered differently: one
    # side alone, if that is unique.
    for width in _WIDTHS[1:]:
        b = before[-width:]
        if len(b) == width and (at := _only(stream, b + text)) >= 0:
            return at + len(b)
        a = after[:width]
        if len(a) == width and (at := _only(stream, text + a)) >= 0:
            return at
    return -1


def place(lines: Sequence[str], pages: Sequence[tuple[int, int]], book: dict) -> list[Mark]:
    """Every mark of ``book`` found on the lines of the pages it is printed on.

    ``pages`` is the document's (PDF page, first line) list in line order.
    """
    found: list[Mark] = []
    for k, (n, first) in enumerate(pages):
        last = pages[k + 1][1] - 1 if k + 1 < len(pages) else len(lines)
        if last < first or n not in book:
            continue
        stream, where = _stream(lines, first, last)
        for text, before, after in book[n]:
            text_n, before_n, after_n = _norm(text), _norm(before), _norm(after)
            if not text_n:
                continue
            at = _locate(stream, text_n, before_n, after_n)
            if at < 0:
                continue
            span = where[at : at + len(text_n)]
            line = span[0][0]
            if any(ln != line for ln, _ in span):
                continue
            start, end = span[0][1], span[-1][1] + 1
            if lines[line - 1][start:end].replace(" ", "") != text_n:
                continue
            body = lines[line - 1]
            glued = start > 0 and body[start - 1].isdigit() and text_n[0].isdigit()
            # Starting its line and followed by words: it numbers a note.
            numbers = not body[:start].strip() and bool(re.match(r"\s*[^\W\d]", body[end:]))
            found.append(Mark(line, start, end, body[start:end], glued, numbers_note=numbers))
    return _linked(lines, sorted(set(found), key=lambda m: (m.line, m.start)))


def _linked(lines: Sequence[str], marks: list[Mark]) -> list[Mark]:
    notes = [m for m in marks if m.numbers_note]
    out = []
    for m in marks:
        if m.numbers_note:
            out.append(m)
            continue
        target = next((x.line for x in notes if _label(x.text) == _label(m.text) and x.line > m.line), 0)
        if not target:
            target = _under_notes(lines, m)
        out.append(Mark(m.line, m.start, m.end, m.text, m.glued, target))
    return out


def _label(text: str) -> str:
    """A mark's first label: "1,2" points to note 1 first."""
    return re.split(r"[,;]", text.strip())[0].strip()


def _under_notes(lines: Sequence[str], mark: Mark) -> int:
    """The first line under a "Notes" heading after the mark that starts with its text."""
    label = _label(mark.text)
    if not label:
        return 0
    pattern = re.compile(rf"^\s*\(?{re.escape(label)}[.)]?\s+\S")
    for n in range(mark.line + 1, min(len(lines), mark.line + 600) + 1):
        if _NOTES.match(lines[n - 1]):
            for m in range(n + 1, min(len(lines), n + 80) + 1):
                if pattern.match(lines[m - 1]):
                    return m
            return 0
    return 0


def marks(path: str, store: ProvenanceStore | None = None) -> tuple[Mark, ...]:
    """The raised characters of one stored document, placed on its lines."""
    store = store or ProvenanceStore()
    return _marks(store.root, path)


@lru_cache(maxsize=512)
def _marks(root: Path, path: str) -> tuple[Mark, ...]:
    store = ProvenanceStore(root)
    index = page_map.read(store, path)
    if index is None or not index.source_sha256:
        return ()
    book = _book(index.source_sha256)
    if not book:
        return ()
    try:
        lines = store.load(path).text.splitlines()
    except ProvenanceError:
        return ()
    return tuple(place(lines, [(p.n, p.line) for p in index.pages], book))


def report(store: ProvenanceStore | None = None) -> str:
    """Every placed mark printed against a digit, with its line: the ones that can change a number."""
    store = store or ProvenanceStore()
    rows = []
    for path in sorted(store.documents()):
        found = marks(path, store)
        if not found:
            continue
        lines = store.load(path).text.splitlines()
        for m in found:
            if m.glued:
                body = lines[m.line - 1]
                rows.append(f"{path}#L{m.line}  {body[:m.start].strip()[-30:]}[{m.text}]{body[m.end:].strip()[:30]}")
    return "\n".join(rows)


def run_on(line: str, mark: Mark) -> Decimal | None:
    """The number a reader of the plain line would see: "15" and a raised "8" as 158."""
    host = re.search(r"[\d,.]*\d$", line[: mark.start])
    digits = re.match(r"\d+", mark.text)
    if not host or not digits:
        return None
    try:
        return Decimal((host.group(0) + digits.group(0)).replace(",", ""))
    except InvalidOperation:
        return None


def misread(store: ProvenanceStore | None = None) -> list[str]:
    """Encoded values that took a raised mark as a digit of their number.

    A value cited to a line where "15" carries a raised "8" must not be 158.
    Every citation the rule set carries is walked, as the readiness ladder
    walks them; one row per value whose number is the printed number with
    the mark run on.
    """
    from flats.encode.readiness import _quoted_parts
    from flats.provenance.store import parse_quote
    from flats.rules.loader import load_rules

    store = store or ProvenanceStore()
    glued: dict[tuple[str, int], list[Decimal]] = {}
    for path in store.documents():
        found = [m for m in marks(path, store) if m.glued]
        if not found:
            continue
        lines = store.load(path).text.splitlines()
        for m in found:
            wrong = run_on(lines[m.line - 1], m)
            if wrong is not None:
                glued.setdefault((path, m.line), []).append(wrong)
    rows = []
    for layer_id, layer in load_rules().items():
        for zone, field, quote, number, _drawn in _quoted_parts(layer):
            if not quote or number is None:
                continue
            try:
                ref = parse_quote(quote)
                value = Decimal(str(number))
            except (ProvenanceError, InvalidOperation):
                continue
            for n in ref.numbers:
                if value in glued.get((ref.path, n), ()):
                    rows.append(f"{layer_id} {zone} {field} = {number}: {ref.path}#L{n} prints it with a raised mark run on")
    return rows


__all__ = ["MARKS", "VERSION", "Mark", "marks", "misread", "place", "report", "run_on"]


if __name__ == "__main__":  # pragma: no cover
    print(report())
