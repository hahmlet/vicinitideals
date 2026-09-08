"""Which use tables lost cells on the way into the store.

A use table linearises to runs of consecutive lines, each holding one verdict
cell: ``P``, ``C``, ``X``, ``L[1],C[2]``. If extraction kept every cell, every
run in a table would be exactly as long as the table is wide, and a cell could
be assigned to a column by counting. Where run lengths vary inside one table,
cells were dropped, and a dropped cell is worse than a missing one -- it shifts
every cell after it, so a permission read off such a table can silently be the
neighbouring zone's.

Lake Oswego is why this exists. ``LOC 50.03.002`` says in its own preamble that
"a blank cell in a use table indicates that the land use is prohibited", and
the extractor drops blanks: ``Cemetery`` arrives as one cell, ``Group care
home`` as two, ``Residential use at R-5 density or greater`` as eleven -- all
against sixteen column heads. The prohibitions are not merely lost, they are
lost *invisibly*, which is the failure this project keeps finding: a blind
reader reports the corpus clean.

The check is deliberately blunt and reports a **ratio, not a verdict**. One
document can hold four tables of four different widths -- ZDO 315 holds Table
315-1 at eleven columns and Table 315-4 at seven -- so a mixture of run lengths
is normal and only lengths *below* a table's own modal width mean anything. The
threshold is not tuned: the corpus separates cleanly into one ragged document
and the rest at zero.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "provenance" / "docs"

#: One use-table cell. A verdict letter, the slashed pairs Oregon codifiers
#: write for "permitted or conditional", any footnote markers, and the
#: comma-joined compounds a limited use takes ("L[1],C[2]"). Getting the
#: compounds wrong is not harmless: a cell this pattern misses breaks a run in
#: half and reports two short rows where the page has one whole one.
_VERDICT = r"(?:P|C|A|N|X|L|CU|NP|SUR|L/SUR|CPUD)(?:/(?:P|C|A|N|X|L|CU|NP))*"
_MARKS = r"(?:\s*\[[0-9,\s]+\])*"
CELL = re.compile(rf"^{_VERDICT}{_MARKS}(?:\s*,\s*{_VERDICT}{_MARKS})*$")

#: Shorter than this and a run is as likely to be prose as a table row.
MIN_RUN = 3

#: Fewer runs than this and there is no modal width to compare against.
MIN_RUNS_PER_DOC = 5


@dataclass(frozen=True)
class Document:
    """One stored document and how ragged its use-table rows are."""

    path: Path
    runs: tuple[int, ...]

    @property
    def widest(self) -> int:
        """The modal run length -- the table's width, as the store has it."""
        return Counter(self.runs).most_common(1)[0][0]

    @property
    def short(self) -> int:
        return sum(1 for n in self.runs if n < self.widest)

    @property
    def ragged(self) -> float:
        return self.short / len(self.runs)

    @property
    def name(self) -> str:
        return self.path.relative_to(DOCS).as_posix()


def runs(lines: list[str]) -> list[int]:
    """The length of every run of consecutive cell lines, longest kept whole."""
    found: list[int] = []
    length = 0
    for line in lines:
        if CELL.match(line.strip()):
            length += 1
            continue
        if length >= MIN_RUN:
            found.append(length)
        length = 0
    if length >= MIN_RUN:
        found.append(length)
    return found


def scan(root: Path | None = None) -> list[Document]:
    """Every stored document that holds enough table rows to judge, worst first."""
    root = root or DOCS
    found: list[Document] = []
    for path in sorted(root.rglob("*.txt")):
        lengths = runs(path.read_text(encoding="utf-8", errors="replace").splitlines())
        if len(lengths) < MIN_RUNS_PER_DOC:
            continue
        found.append(Document(path=path, runs=tuple(lengths)))
    found.sort(key=lambda d: (-d.ragged, d.name))
    return found


def render(documents: list[Document] | None = None) -> str:
    documents = scan() if documents is None else documents
    lines = [f"{'ragged':>7}  {'short':>5}  {'rows':>5}  {'width':>5}  document"]
    for document in documents:
        lines.append(
            f"{document.ragged:7.0%}  {document.short:5d}  "
            f"{len(document.runs):5d}  {document.widest:5d}  {document.name}"
        )
    return "\n".join(lines)


def main() -> None:
    print(render())


if __name__ == "__main__":
    main()
