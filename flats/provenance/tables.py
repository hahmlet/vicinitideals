"""Tables in the readable code text, proposed by a tool and checked against the page.

A PDF's text layer has no tables in it, only words at positions. Reading the
rows and columns back out is a problem many people are working on, so FLATS
does not do it itself (Steph 2026-10-24): Docling proposes each table
(``scripts/flats_tables_propose.py``, run outside the app) and stores its
cells beside the city's ``sections.json`` as ``tables.proposed.json``, with
the printed evidence: every word inside the table with its box on the page,
and the page's printed vertical rules.

A proposal is never shown on the tool's word. Two checks, neither of which
knows what the right table is -- each tests something any right table must
agree with:

*The page* (positions fixed by the PDF, not by the tool). No cell may hold
printed words from both sides of a printed column rule; no two neighbouring
columns may overlap on the page, nor two neighbouring rows; and every printed
word inside the table must be in some cell. Gresham 4.1415B -- a lost column,
every number one over -- fails all of these.

*The text* (the proved readable lines). The cells, word for word, are the
words of one run of the section's lines on that page and nothing else, and
those lines are the cells read across, line by line, in order. So a table
shown is the same words a citation quotes, and the lines each cell came from
are known: a citation of line 58 lights the cell that holds line 58.

A table that fails either check is shown as its printed lines, marked as a
table not yet confirmed. A pass means no contradiction was found, not that
the table is proved right; how often a passed table is wrong is measured by
people in the page check (FOLLOWUPS 115).

The proved text itself is untouched: tables are a way of showing lines, not
a change to them, so no citation moves.

*Other proposers.* Where Docling's proposal is refused, others are tried on
the same place of the page, each held to the same two checks:
``tables.corrected.json`` -- a table a person (or a reader working from the
page image) wrote out, ``scripts/flats_tables_sheet.py`` round-trips it
through a spreadsheet -- and ``tables.proposed.ruled.json``, the table
pdfplumber cuts along the printed rules. A correction is tried first, so a
person can also replace a table the check passed. A proposal without cell
boxes (a correction) gets them from the page: its cells must be the printed
words read across, line by line, and each cell's box is then its words' box.

*People.* ``tables.reviewed.json`` holds people's verdicts on drawn tables,
each for one reader's table on one page. A table a person found wrong is
refused like any other, and the next reader is tried; one found right says
so beside it. The share found wrong is the checks' miss rate.

*Not tables.* A chapter's list of its sections ("TDC 40.100. Purpose.")
is set out in columns, and Docling proposes it as a table; it is dropped,
as it is printed lines and nothing in it is a table's cell.

*A city printed as several books.* A proposals file is about one book, and
its pages are that book's page numbers. Gresham prints its code as one PDF
per chapter, so page 5 is seventeen different pages. Such a city keeps one
set of files per book, named for it -- ``tables.4.1400.proposed.json`` and
its ``tables.4.1400.proposed.ruled.json``, ``.corrected.json`` and
``.reviewed.json`` -- and a named file's tables are placed only on the
sections printed in the book its ``book`` hash names. The unnamed files keep
their meaning: every section of the city.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from flats.provenance.store import INDEX, Part, ProvenanceStore

#: The proposals file beside a city's ``sections.json``.
PROPOSED = "tables.proposed.json"

#: Other proposers, beside it, tried in this order where Docling's proposal
#: is refused (a correction also where it was not).
CORRECTED = "tables.corrected.json"
RULED = "tables.proposed.ruled.json"

#: People's verdicts on drawn tables, beside them: a table a person found
#: wrong is not drawn, whatever the checks said, and the next reader is tried.
REVIEWED = "tables.reviewed.json"

#: The name of these checks, shown with every table so a change is visible.
CHECK = "tables/1"

#: Slack, in PDF points, for a word that touches a rule or a neighbour.
_TOUCH = 0.6


@dataclass(frozen=True, slots=True)
class Cell:
    row: tuple[int, int]
    col: tuple[int, int]
    #: The cell's words as the proved text spells them.
    text: str
    header: bool
    #: Section lines (1-based) the cell's words come from.
    lines: tuple[int, ...]
    #: Each word as (line, its index among the line's words), in cell order.
    words: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True, slots=True)
class Table:
    """One proposed table, placed on a section's lines and checked."""

    section: str
    page: int
    rows: int
    cols: int
    #: First and last section line the table is printed on; 0, 0 when it
    #: could not be placed.
    first: int
    last: int
    cells: tuple[Cell, ...]
    #: Every way the table disagrees with the page or the text. Empty = shown.
    problems: tuple[str, ...]
    tool: str = ""
    #: The table's box on the page, PDF points from the top left.
    box: tuple[float, ...] = ()
    #: A person compared it with the page and found it right: who and when.
    reviewed: str = ""

    @property
    def shown(self) -> bool:
        return not self.problems and self.first > 0

    def grid(self) -> list[list[Cell | None]]:
        """Rows of cells, a spanning cell at its top-left slot and None under it."""
        out: list[list[Cell | None]] = [[None] * self.cols for _ in range(self.rows)]
        for cell in self.cells:
            out[cell.row[0]][cell.col[0]] = cell
        return out


# --- the page --------------------------------------------------------------


@dataclass(slots=True)
class _Word:
    text: str
    x0: float
    top: float
    x1: float
    bottom: float
    owners: list[int] = field(default_factory=list)

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.top + self.bottom) / 2


def _unique_cells(cells: Sequence[Mapping[str, object]]) -> list[Mapping[str, object]]:
    """Docling repeats a spanning cell in every slot it covers; keep one."""
    seen: set[tuple[int, int, int, int]] = set()
    out = []
    for cell in cells:
        key = (*cell["row"], *cell["col"])  # type: ignore[misc]
        if key in seen:
            continue
        seen.add(key)
        out.append(cell)
    return out


#: A section number standing alone in a cell: "40.100.", "TDC 73C.040".
_SECTION_NO = re.compile(r"^\s*(?:[A-Z]{2,5}\s+)?\d+[A-Z]?\.\d+[A-Z]?\.?\s*$")


def contents_list(proposal: Mapping[str, object]) -> bool:
    """A chapter's list of its sections, which Docling proposes as a table."""
    cells = _unique_cells(proposal["cells"])  # type: ignore[arg-type]
    rows: dict[int, bool] = {}
    for cell in cells:
        r = cell["row"][0]  # type: ignore[index]
        rows[r] = rows.get(r, False) or bool(_SECTION_NO.match(str(cell["text"])))
    return len(rows) >= 3 and sum(rows.values()) >= 0.8 * len(rows)


def _visual_lines(words: Sequence[_Word]) -> list[list[_Word]]:
    """The printed words in reading order: line by line down the page, left to right."""
    out: list[list[_Word]] = []
    for word in sorted(words, key=lambda w: (w.cy, w.x0)):
        if out and abs(word.cy - out[-1][0].cy) < (word.bottom - word.top) / 2:
            out[-1].append(word)
        else:
            out.append([word])
    return [sorted(line, key=lambda w: w.x0) for line in out]


def boxed(proposal: Mapping[str, object]) -> Mapping[str, object] | None:
    """The proposal with every cell's box taken from the printed words it holds.

    For a proposal written without positions (a correction): its cells, in
    reading order, must be the table's printed words read across, line by
    line -- the same reading the text check makes of the stored lines. None
    when they are not.
    """
    cells = _unique_cells(proposal["cells"])  # type: ignore[arg-type]
    if all(c.get("box") for c in cells):
        return proposal
    words = [_Word(*w) for w in proposal["words"]]  # type: ignore[union-attr]
    flat = [(k, w) for k, line in enumerate(_visual_lines(words)) for w in line]
    kept = [(k, w) for k, w in flat if _letters(w.text)]
    order = sorted(range(len(cells)), key=lambda k: (cells[k]["row"][0], cells[k]["col"][0]))  # type: ignore[index]
    got = _interleave([_letters(str(cells[k]["text"])) for k in order], [(k, _letters(w.text)) for k, w in kept])
    if got is None:
        return None
    out = [dict(c) for c in cells]
    for slot, k in enumerate(order):
        mine = [kept[i][1] for i in got[slot]]
        if mine:
            out[k]["box"] = [min(w.x0 for w in mine), min(w.top for w in mine), max(w.x1 for w in mine), max(w.bottom for w in mine)]
    return {**proposal, "cells": out}


def page_problems(proposal: Mapping[str, object]) -> list[str]:
    """Every way a proposed table contradicts the printed page."""
    problems: list[str] = []
    found = boxed(proposal)
    if found is None:
        return ["its cells are not the printed words read across, line by line"]
    cells = _unique_cells(found["cells"])  # type: ignore[arg-type]
    words = [_Word(*w) for w in proposal["words"]]  # type: ignore[union-attr]
    rules = [tuple(r) for r in proposal["rules"]]  # type: ignore[union-attr]
    held: dict[int, list[_Word]] = {}
    for k, cell in enumerate(cells):
        box = cell.get("box")
        if not box:
            continue
        left, top, right, bottom = box  # type: ignore[misc]
        for word in words:
            if left - 1 <= word.cx <= right + 1 and top - 1 <= word.cy <= bottom + 1:
                word.owners.append(k)
                held.setdefault(k, []).append(word)

    orphans = [w.text for w in words if not w.owners]
    if orphans:
        problems.append(f"{len(orphans)} printed word(s) in the table are in no cell: {' '.join(orphans[:6])}")
    doubles = [w.text for w in words if len(set(w.owners)) > 1]
    if doubles:
        problems.append(f"{len(doubles)} printed word(s) are in two cells: {' '.join(doubles[:6])}")

    # A cell across a printed column rule. A cell spanning columns crosses the
    # rules between them by design, so only single-column cells are tested.
    for k, cell in enumerate(cells):
        col = cell["col"]
        if col[1] - col[0] > 1 or k not in held:  # type: ignore[index]
            continue
        mine = held[k]
        lo, hi = min(w.x0 for w in mine), max(w.x1 for w in mine)
        for x, rtop, rbottom in rules:
            if not lo + _TOUCH < x < hi - _TOUCH:
                continue
            band = [w for w in mine if w.bottom > rtop and w.top < rbottom]
            if any(w.x1 <= x + _TOUCH for w in band) and any(w.x0 >= x - _TOUCH for w in band):
                problems.append(f"a cell holds words from both sides of a printed column line: {str(cell['text'])[:40]!r}")
                break

    # Neighbouring columns may not overlap on the page, nor neighbouring rows:
    # the gutter between them is what says which column a word is in.
    def extent(axis: str) -> dict[int, tuple[float, float]]:
        out: dict[int, tuple[float, float]] = {}
        for k, cell in enumerate(cells):
            span = cell[axis]
            if span[1] - span[0] != 1 or k not in held:  # type: ignore[index]
                continue
            mine = held[k]
            lo = min(w.x0 if axis == "col" else w.top for w in mine)
            hi = max(w.x1 if axis == "col" else w.bottom for w in mine)
            at = span[0]  # type: ignore[index]
            old = out.get(at)
            out[at] = (lo, hi) if old is None else (min(old[0], lo), max(old[1], hi))
        return out

    for axis, name in (("col", "column"), ("row", "row")):
        spans = extent(axis)
        for at in sorted(spans):
            if at + 1 in spans and spans[at][1] > spans[at + 1][0] + _TOUCH:
                problems.append(f"{name}s {at + 1} and {at + 2} overlap on the page")
    return problems


# --- the text --------------------------------------------------------------


#: Every dash a code prints, one for matching: Docling reads an em dash cell
#: as a hyphen.
_DASHES = "-‐‑‒–—―−"


def _tokens(text: str) -> list[str]:
    """Words for matching: dashes out of words, so 'Cover- age', 'Cover-age' and 'Coverage' agree.

    A dash standing alone ("Flag Lots  --") is a word of its own, the same
    whichever dash was printed.
    """
    joined = re.sub(rf"(?<=[A-Za-z])[{_DASHES}]\s+(?=[a-z])", "", text)
    out = []
    for word in joined.split():
        bare = re.sub(rf"[{_DASHES}]", "", word)
        out.append(bare if bare else "—")
    return out


def _page_lines(part: Part, page: int, length: int) -> tuple[int, int] | None:
    """The section lines printed on one book page, or None if it has none."""
    starts = list(part.pages)
    for k, (n, line) in enumerate(starts):
        if n == page:
            end = starts[k + 1][1] - 1 if k + 1 < len(starts) else length
            # Two pages starting on the same line: this page has no line of its own.
            return (line, end) if end >= line else None
    return None


#: How many choices the line-by-line reading may try before giving up.
_BUDGET = 50_000


def _interleave(cells: Sequence[str], words: Sequence[tuple[int, str]]) -> list[list[int]] | None:
    """Which of ``words`` each cell holds, if the lines are exactly the cells read across.

    ``cells`` are each cell's letters, spaces and dashes out, in reading
    order; ``words`` the lines' words the same way, each with its line. Each
    line, left to right, takes its words from the cells in turn: a word goes
    to a cell whose letters still to come start with it -- one already under
    way first, else the next not yet started. Letters, not words, because the
    tool and the text do not always agree on spaces ("Saleof", "T able"). When
    a choice leads nowhere the next is tried. None when no reading uses every
    word and finishes every cell.
    """
    at = [0] * len(cells)
    lines_of: list[list[int]] = [[] for _ in cells]
    budget = [_BUDGET]

    def walk(i: int) -> bool:
        if i == len(words):
            return all(at[k] == len(cells[k]) for k in range(len(cells)))
        budget[0] -= 1
        if budget[0] < 0:
            return False
        _n, word = words[i]
        started = [k for k in range(len(cells)) if 0 < at[k] < len(cells[k])]
        fresh = [k for k in range(len(cells)) if at[k] == 0 and cells[k]]
        for k in started + fresh[:1] + fresh[1:]:
            if cells[k].startswith(word, at[k]):
                at[k] += len(word)
                lines_of[k].append(i)
                if walk(i + 1):
                    return True
                at[k] -= len(word)
                lines_of[k].pop()
        return False

    import sys

    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(max(limit, len(words) + 1000))
    try:
        found = walk(0)
    finally:
        sys.setrecursionlimit(limit)
    return lines_of if found else None


def _letters(text: str) -> str:
    return "".join(_tokens(text))


def place(
    proposal: Mapping[str, object], part: Part, lines: Sequence[str], page: int
) -> tuple[int, int, list[list[tuple[int, int, str]]]] | None:
    """The run of section lines on ``page`` that is exactly this table's words.

    Returns (first, last, each unique cell's words as the lines print them,
    with the line each came from and its index among that line's words),
    1-based, or None.
    """
    found = _page_lines(part, page, len(lines))
    if found is None:
        return None
    lo, hi = found
    cells = _unique_cells(proposal["cells"])  # type: ignore[arg-type]
    letters = [_letters(str(c["text"])) for c in cells]
    want = Counter("".join(letters))
    if not want:
        return None
    line_letters = [_letters(lines[n - 1]) for n in range(lo, hi + 1)]
    # Cells in reading order, so a word two cells could take goes to the upper-left one.
    order = sorted(range(len(cells)), key=lambda k: (cells[k]["row"][0], cells[k]["col"][0]))  # type: ignore[index]
    ordered = [letters[k] for k in order]
    for a in range(len(line_letters)):
        have: Counter[str] = Counter()
        for b in range(a, len(line_letters)):
            have.update(line_letters[b])
            if any(have[c] > want[c] for c in set(line_letters[b])):
                break
            if have != want:
                continue
            raw = [(lo + a + m, i, w) for m in range(b - a + 1) for i, w in enumerate(lines[lo + a + m - 1].split())]
            words = [(n, _letters(w)) for n, _i, w in raw]
            keep = [i for i, (_n, w) in enumerate(words) if w]
            got = _interleave(ordered, [words[i] for i in keep])
            if got is None:
                continue
            back: list[list[tuple[int, int, str]]] = [[] for _ in cells]
            for slot, k in enumerate(order):
                back[k] = [raw[keep[i]] for i in got[slot]]
            return lo + a, lo + b, back
    return None


def check(
    proposal: Mapping[str, object], part: Part, lines: Sequence[str], page: int, tool: str = ""
) -> Table:
    """One proposal, placed on the section and checked against page and text."""
    problems = page_problems(proposal)
    placed = place(proposal, part, lines, page)
    cells = _unique_cells(proposal["cells"])  # type: ignore[arg-type]
    if placed is None:
        problems.append("its words are not exactly the words of the section's lines on this page")
        first = last = 0
        held: list[list[tuple[int, int, str]]] = [[] for _ in cells]
    else:
        first, last, held = placed
    out = tuple(
        Cell(
            row=tuple(c["row"]),  # type: ignore[arg-type]
            col=tuple(c["col"]),  # type: ignore[arg-type]
            text=" ".join(w for _n, _i, w in held[k]) if held[k] else " ".join(str(c["text"]).split()),
            header=bool(c.get("header")),
            lines=tuple(sorted({n for n, _i, _w in held[k]})),
            words=tuple((n, i) for n, i, _w in held[k]),
        )
        for k, c in enumerate(cells)
    )
    return Table(
        section=part.path,
        page=page,
        rows=int(proposal["rows"]),  # type: ignore[arg-type]
        cols=int(proposal["cols"]),  # type: ignore[arg-type]
        first=first,
        last=last,
        cells=out,
        problems=tuple(problems),
        tool=tool,
        box=tuple(proposal.get("box") or ()),  # type: ignore[arg-type]
    )


def tables(store: ProvenanceStore | None = None) -> dict[str, tuple[Table, ...]]:
    """Every proposed table in the store, checked, keyed by section file."""
    store = store or ProvenanceStore()
    return dict(_tables(store.root))


def _overlaps(a: Sequence[float], b: Sequence[float]) -> bool:
    """Two boxes on a page share most of the smaller one."""
    width = min(a[2], b[2]) - max(a[0], b[0])
    height = min(a[3], b[3]) - max(a[1], b[1])
    if width <= 0 or height <= 0:
        return False
    smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return smaller > 0 and width * height >= 0.5 * smaller


def companions(proposed: Path) -> tuple[Path, Path, Path]:
    """The corrected, ruled and reviewed files that go with a proposals file.

    ``tables.proposed.json`` -> ``tables.corrected.json`` ...; a file named
    for one book, ``tables.4.1400.proposed.json``, -> ``tables.4.1400.corrected.json`` ...
    """
    prefix = proposed.name[: -len("proposed.json")]
    here = proposed.parent
    return here / f"{prefix}corrected.json", here / f"{prefix}proposed.ruled.json", here / f"{prefix}reviewed.json"


def _book(path: Path) -> str:
    if not path.is_file():
        return ""
    return str(json.loads(path.read_text(encoding="utf-8")).get("book", ""))


def _read(path: Path) -> tuple[str, dict[int, list[Mapping[str, object]]]]:
    if not path.is_file():
        return "", {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return str(raw.get("tool", "")), {int(k): v for k, v in raw["pages"].items()}


@lru_cache(maxsize=4)
def _tables(root: Path) -> tuple[tuple[str, tuple[Table, ...]], ...]:
    store = ProvenanceStore(root)
    parts = store.parts()
    by_dir: dict[str, list[Part]] = {}
    for part in parts.values():
        by_dir.setdefault(part.layer, []).append(part)
    out: dict[str, list[Table]] = {}
    books: dict[str, str] = {}
    for proposed in sorted(root.rglob("tables*.proposed.json")):
        directory = proposed.parent.relative_to(root).as_posix()
        if not (proposed.parent / INDEX).is_file():
            continue
        corrected_path, ruled_path, reviewed_path = companions(proposed)
        docling = _read(proposed)
        corrected = _read(corrected_path)
        ruled = _read(ruled_path)
        candidates = by_dir.get(directory, [])
        if proposed.name != PROPOSED:
            # Named for one book: its page numbers are that book's alone.
            from flats.provenance.books import expected

            book = _book(proposed)
            for part in candidates:
                if part.proof not in books:
                    books[part.proof] = expected(store, part.proof)
            candidates = [p for p in candidates if book and books[p.proof] == book]
        texts: dict[str, list[str]] = {}
        reviews = _reviews(reviewed_path)

        def placed(proposal: Mapping[str, object], page: int, tool: str, on_page: list[Part]) -> Table | None:
            best: Table | None = None
            for part in on_page:
                lines = texts.setdefault(part.path, store.load(part.path).text.splitlines())
                table = check(proposal, part, lines, page, str(proposal.get("tool") or tool))
                if best is None or (table.first and not best.first):
                    best = table
            return best

        for page in sorted(set(docling[1]) | set(corrected[1])):
            on_page = [p for p in candidates if any(n == page for n, _ in p.pages)]
            slots = [p for p in docling[1].get(page, []) if not contents_list(p)]
            # A correction where Docling proposed nothing is a table of its own.
            slots += [c for c in corrected[1].get(page, []) if not any(_overlaps(c["box"], d["box"]) for d in slots)]  # type: ignore[arg-type]
            for slot in slots:
                first: Table | None = None
                chosen: list[Table] = []
                tried: list[str] = []
                for tool, pages in (corrected, docling, ruled):
                    found = [p for p in pages.get(page, []) if _overlaps(p["box"], slot["box"])]  # type: ignore[arg-type]
                    if not found:
                        continue
                    checked = [_judged(t, reviews) for t in (placed(p, page, tool, on_page) for p in found) if t is not None]
                    if not checked:
                        continue
                    first = first or checked[0]
                    if all(t.shown for t in checked):
                        chosen = checked
                        break
                    tried.append(tool)
                if chosen:
                    for table in chosen:
                        out.setdefault(table.section, []).append(table)
                elif first is not None:
                    if len(tried) > 1:
                        first = Table(**{**_fields(first), "problems": (*first.problems, f"also refused: {', '.join(tried[1:])}")})
                    out.setdefault(first.section, []).append(first)
    return tuple((k, tuple(sorted(v, key=lambda t: (t.page, t.first)))) for k, v in sorted(out.items()))


def _reviews(path: Path) -> tuple[Mapping[str, object], ...]:
    if not path.is_file():
        return ()
    return tuple(json.loads(path.read_text(encoding="utf-8"))["reviews"])


def _judged(table: Table, reviews: Sequence[Mapping[str, object]]) -> Table:
    """The table with the latest verdict a person gave on it, if any."""
    mine = [
        r
        for r in reviews
        if r["page"] == table.page and r["tool"] == table.tool and table.box and _overlaps(r["box"], table.box)  # type: ignore[arg-type]
    ]
    if not mine:
        return table
    last = mine[-1]
    who = f"{last['by']} {last['date']}"
    if last["verdict"] == "wrong":
        note = f": {last['note']}" if last.get("note") else ""
        return Table(**{**_fields(table), "problems": (*table.problems, f"{who} found it wrong on the page{note}")})
    return Table(**{**_fields(table), "reviewed": who})


def _fields(table: Table) -> dict[str, object]:
    return {name: getattr(table, name) for name in Table.__slots__}  # type: ignore[attr-defined]


def report(store: ProvenanceStore | None = None) -> str:
    """One line per table: shown or not, and why."""
    rows = []
    for section, found in tables(store).items():
        for t in found:
            mark = "SHOWN" if t.shown else "HELD "
            where = f"L{t.first}-L{t.last}" if t.first else "unplaced"
            why = "; ".join(t.problems)
            reader = (t.tool.split() or ["?"])[0]
            rows.append(f"{mark} {section} p{t.page} {t.rows}x{t.cols} {where} [{reader}] {why}".rstrip())
    return "\n".join(rows)


__all__ = [
    "CHECK",
    "CORRECTED",
    "PROPOSED",
    "REVIEWED",
    "RULED",
    "Cell",
    "Table",
    "boxed",
    "check",
    "contents_list",
    "page_problems",
    "place",
    "report",
    "tables",
]


if __name__ == "__main__":  # pragma: no cover
    print(report())
