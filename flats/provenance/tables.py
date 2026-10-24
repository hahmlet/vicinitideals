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


def page_problems(proposal: Mapping[str, object]) -> list[str]:
    """Every way a proposed table contradicts the printed page."""
    problems: list[str] = []
    cells = _unique_cells(proposal["cells"])  # type: ignore[arg-type]
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
    )


def tables(store: ProvenanceStore | None = None) -> dict[str, tuple[Table, ...]]:
    """Every proposed table in the store, checked, keyed by section file."""
    store = store or ProvenanceStore()
    return dict(_tables(store.root))


@lru_cache(maxsize=4)
def _tables(root: Path) -> tuple[tuple[str, tuple[Table, ...]], ...]:
    store = ProvenanceStore(root)
    parts = store.parts()
    by_dir: dict[str, list[Part]] = {}
    for part in parts.values():
        by_dir.setdefault(part.layer, []).append(part)
    out: dict[str, list[Table]] = {}
    for proposed in sorted(root.rglob(PROPOSED)):
        directory = proposed.parent.relative_to(root).as_posix()
        if not (proposed.parent / INDEX).is_file():
            continue
        raw = json.loads(proposed.read_text(encoding="utf-8"))
        tool = str(raw.get("tool", ""))
        candidates = by_dir.get(directory, [])
        for page_key, found in sorted(raw["pages"].items(), key=lambda kv: int(kv[0])):
            page = int(page_key)
            on_page = [p for p in candidates if any(n == page for n, _ in p.pages)]
            for proposal in found:
                best: Table | None = None
                for part in on_page:
                    lines = store.load(part.path).text.splitlines()
                    table = check(proposal, part, lines, page, tool)
                    if table.first and (best is None or not best.first):
                        best = table
                    elif best is None:
                        best = table
                if best is not None:
                    out.setdefault(best.section, []).append(best)
    return tuple((k, tuple(v)) for k, v in sorted(out.items()))


def report(store: ProvenanceStore | None = None) -> str:
    """One line per table: shown or not, and why."""
    rows = []
    for section, found in tables(store).items():
        for t in found:
            mark = "SHOWN" if t.shown else "HELD "
            where = f"L{t.first}-L{t.last}" if t.first else "unplaced"
            why = "; ".join(t.problems)
            rows.append(f"{mark} {section} p{t.page} {t.rows}x{t.cols} {where} {why}")
    return "\n".join(rows)


__all__ = ["CHECK", "PROPOSED", "Cell", "Table", "check", "page_problems", "place", "report", "tables"]


if __name__ == "__main__":  # pragma: no cover
    print(report())
