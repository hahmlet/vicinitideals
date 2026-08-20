"""Measured statements in documents we hold that no encoded value cites.

:mod:`flats.encode.crossrefs` asks which chapters our documents point at and we
cannot open. This asks the question one step nearer home, and the answer is
less comfortable: **which sentences in the chapters we did open has nobody
read?**

Milwaukie is the case. Table 19.301.4 prints a 5 ft side yard, which is
encoded, and four rows further down prints "Side yard height plane limit /
a. Height above ground at minimum required side yard depth (ft) 20 / b. Slope
of plane (degrees) 45". A 26 ft building is six feet over that plane, and at 45
degrees it buys those six feet by standing six feet further in. The side yard
for this building is 11 ft, not 5. Both figures were sitting in a document this
store has held since August, on the same page as a number that was encoded, and
nothing reported it — a coverage ledger counts fields, and there is no field
for the slope of a plane.

The check is a subtraction. Every line stating a measure, minus every line an
encoded value quotes, is what nobody read. It is not a list of errors: most of
a code chapter is genuinely not about this building, and the livestock setback
will be in here forever. It is a list of the reading that has not been done,
which is the thing that cannot otherwise be counted.

Two buckets, and they are different work:

``unread``
    The line names a standard this system has a field for, and no encoded value
    quotes it. Usually an exception, a bonus, or a second case beside a number
    that *was* read — Milwaukie's "maximum lot coverage ... is increased by 10
    percentage points" against a coverage figure taken from the table above it.
    A person can act on these today; the field already exists.

``unfielded``
    The line states a measure and names no field at all. The height plane is
    here, and so is everything else the model cannot yet express. These are a
    modelling decision before they are an encoding one, so they are reported
    apart rather than mixed in and skimmed past.

Prose is admitted to the first bucket and refused by the second. A sentence
that moves a field we already screen against is worth reading however long it
is; a long sentence with a number in it and no field behind it is almost always
the poultry.

Run it::

    uv run python -m flats.encode.uncited
    uv run python -m flats.encode.uncited or/clackamas/milwaukie
    uv run python -m flats.encode.uncited --unfielded
"""

from __future__ import annotations

import csv
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

from flats.encode.crossrefs import _HEADING, _cited_lines, _doc_ids
from flats.encode.extract import _subject
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer

#: Where the ledger is written, beside the cross-reference one.
LEDGER = Path(__file__).resolve().parents[2] / "data" / "flats" / "uncited.csv"

#: How near a cited line a statement may stand and still count as read. One
#: line, not twelve: a table row and the row under it are different standards,
#: and Milwaukie's height plane sits four rows below a setback that was
#: encoded. A window wide enough to be generous here would hide the finding
#: this module exists for.
READ_WINDOW = 1

#: Longer than this, a line with no field behind it is prose rather than a
#: standard. Kept only for the `unfielded` bucket, where there is no field to
#: vouch for the line and the alternative is a ledger that is mostly livestock
#: setbacks. A statement that moves a field we do screen against is reported at
#: any length.
PROSE_CHARS = 90

#: The body of a glossary entry. Codes print the term on one line and the
#: sentence defining it on the next, so a definition mentioning a measure looks
#: exactly like a standard stating one. Definitions have their own reader and
#: their own citation form; counting them here would bury the standards.
_DEFINITION = re.compile(r"^(?:means|refers to|shall mean)\b", re.I)

#: A measured statement: a number with a unit, or a label naming the unit its
#: cells are printed in. The second half is what catches a linearised table,
#: where the label line carries "(ft)" and the cells below it are bare digits —
#: which is how eCode360 renders every table in four of these jurisdictions.
MEASURE = re.compile(
    r"\d[\d,]*(?:\.\d+)?\s*(?:ft\.?|feet|foot|%|percent|percentage points|"
    r"sq\.?\s*ft|square feet|stories|storeys|degrees?|units? per acre|du/acre)\b"
    r"|\((?:ft|feet|percent|degrees|square feet|acres|stories|storeys|"
    r"dwelling units per acre|units per acre)\)",
    re.I,
)


@dataclass(frozen=True, slots=True)
class Uncited:
    """One measured statement, and whether the model has a field for it."""

    layer: str
    path: str
    line: int
    #: The section it is printed under, when the document prints headings.
    section: str
    #: The registry field its wording names, or "" when it names none.
    field: str
    text: str
    #: How many times the same wording appears uncited in this document. A
    #: linearised table reprints its caption once per column, and counting
    #: those separately would make the ledger mostly furniture.
    repeats: int = 1

    @property
    def bucket(self) -> str:
        return "unread" if self.field else "unfielded"


def _sections(lines: Sequence[str], owns: set[str]) -> list[str]:
    """The section heading in force at each line, by the document's own rule.

    Same ownership test as the cross-reference ledger: a heading has to belong
    to this document, or a wrapped citation at the start of a line renames
    every section under it.
    """
    out: list[str] = []
    current = ""
    for line in lines:
        m = _HEADING.match(line)
        if m:
            num = m.group("num").rstrip(".")
            if num.partition(".")[0] in owns:
                current = num
        out.append(current)
    return out


def uncited(layer: Layer, store: ProvenanceStore | None = None) -> list[Uncited]:
    """Every measured statement in this layer's documents that nothing cites."""
    store = store or ProvenanceStore()
    prefix = f"{layer.layer}/"
    paths = [p for p in store.documents() if p.startswith(prefix)]
    if not paths:
        return []

    cited = _cited_lines(layer)
    rows: list[Uncited] = []
    for path in paths:
        lines = store.text_path(path).read_text(encoding="utf-8").splitlines()
        here = cited.get(path, set())
        owns = {i.partition(".")[0] for i in _doc_ids([path])}
        sections = _sections(lines, owns)

        # The same standard, printed again. Milwaukie's Table 19.301.4 runs
        # four lot-size columns and prints "35 ft" once per column on four
        # consecutive lines; the encoding quotes the first. The other three are
        # the same sentence and reporting them as unread is how a ledger
        # becomes furniture — so a line whose wording a cited line already
        # carries counts as read wherever it appears in the document.
        quoted = {
            " ".join(lines[c - 1].split()) for c in here if 0 < c <= len(lines)
        }
        quoted.discard("")

        seen: dict[str, int] = defaultdict(int)
        first: dict[str, Uncited] = {}
        for n, raw in enumerate(lines, start=1):
            text = " ".join(raw.split())
            if not text or not MEASURE.search(text):
                continue
            if text in quoted:
                continue
            if any(abs(n - c) <= READ_WINDOW for c in here):
                continue
            if _DEFINITION.match(text):
                # A glossary body, which has its own subsystem: the definitions
                # reader tags terms, and `measured_on` cites them where a
                # standard leans on one. "Existing trees are measured at a
                # height 4.5 ft" is not an unread height standard.
                continue
            field = _subject(text) or ""
            if not field and len(text) > PROSE_CHARS:
                continue
            seen[text] += 1
            first.setdefault(
                text,
                Uncited(
                    layer=layer.layer,
                    path=path,
                    line=n,
                    section=sections[n - 1],
                    field=field,
                    text=text[:200],
                ),
            )
        for text, count in seen.items():
            row = first[text]
            rows.append(
                Uncited(
                    layer=row.layer,
                    path=row.path,
                    line=row.line,
                    section=row.section,
                    field=row.field,
                    text=row.text,
                    repeats=count,
                )
            )
    rows.sort(key=lambda r: (r.bucket, r.path, r.line))
    return rows


def survey(
    layers: Sequence[Layer] | None = None, store: ProvenanceStore | None = None
) -> list[Uncited]:
    store = store or ProvenanceStore()
    chosen = layers if layers is not None else list(load_rules().values())
    rows: list[Uncited] = []
    for layer in chosen:
        rows.extend(uncited(layer, store))
    return rows


def by_field(rows: Sequence[Uncited]) -> dict[str, int]:
    """How many uncited statements name each field, commonest first.

    The shape of the reading debt. A field with fifty uncited statements
    against it is not fifty errors — it is a standard the corpus talks about
    constantly and quotes rarely, which is where an exception hides.
    """
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        if row.field:
            counts[row.field] += 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def write(rows: Sequence[Uncited], path: Path | None = None) -> Path:
    file = path or LEDGER
    file.parent.mkdir(parents=True, exist_ok=True)
    with file.open("w", encoding="utf-8", newline="") as fh:
        out = csv.writer(fh)
        out.writerow(
            ["layer", "bucket", "field", "path", "line", "section", "repeats", "text"]
        )
        for row in rows:
            out.writerow(
                [
                    row.layer,
                    row.bucket,
                    row.field,
                    row.path,
                    row.line,
                    row.section,
                    row.repeats,
                    row.text,
                ]
            )
    return file


def render(rows: Sequence[Uncited], *, unfielded: bool = False) -> Iterator[str]:
    want = "unfielded" if unfielded else "unread"
    shown = [r for r in rows if r.bucket == want]
    if not shown:
        yield f"no {want} statements — every measure in the store is quoted"
        return

    by_layer: dict[str, list[Uncited]] = defaultdict(list)
    for row in shown:
        by_layer[row.layer].append(row)

    total = len(rows)
    yield (
        f"{len(shown)} {want} statement(s) across {len(by_layer)} jurisdiction(s)"
        f" — of {total} measured line(s) no encoded value quotes"
    )
    yield ""
    for layer in sorted(by_layer, key=lambda name: -len(by_layer[name])):
        group = by_layer[layer]
        yield f"  {layer}   ({len(group)} statement(s))"
        for row in group[:10]:
            where = f"{Path(row.path).name}:{row.line}"
            tag = row.field or f"§{row.section}" if row.section else row.field
            yield f"    {where:<34} {tag:<22} {row.text[:78]}"
        if len(group) > 10:
            yield f"    ... and {len(group) - 10} more"
        yield ""


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):  # pragma: no cover
        sys.stdout.reconfigure(errors="replace")
    args = list(sys.argv[1:] if argv is None else argv)
    unfielded = "--unfielded" in args
    args = [a for a in args if not a.startswith("--")]

    layers = load_rules()
    chosen = [layers[a.strip("/")] for a in args] if args else list(layers.values())
    rows = survey(chosen)
    for line in render(rows, unfielded=unfielded):
        print(line)

    if not args:
        print(f"written -> {write(rows)}")
        top = list(by_field(rows).items())[:8]
        named = ", ".join(f"{f} x{c}" for f, c in top)
        print(f"  most-talked-about, least-quoted: {named}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
