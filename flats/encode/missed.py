"""Of the standards nobody read, which state a number we hold nowhere.

:mod:`flats.encode.uncited` produces the reading debt: every line in a document
we hold that states a measure and that no encoded value quotes. Its ``unread``
bucket is the sharp end -- a line naming a standard this system *has a field
for*, unquoted. There are about a thousand of them, and read end to end they
are unworkable, because almost all of them are the second column of a table
whose first column we took, or the same standard for a use we do not build.

The lever is arithmetic, and it is the one thing a machine can do here that a
person should not have to: **compare the number on the line against every
number this jurisdiction holds for that field.** A line stating 35 ft for a
height in a city that holds a 35 somewhere is bookkeeping -- our reader took it
off a different row of the same table. A line stating 24 ft for a height in a
city that holds no 24 for height in any zone is a number this corpus has never
seen, and that is either a zone we skipped, an exception nobody encoded, or a
use that is not ours. Two of those three are findings.

So this is **a sort, not a verdict**, and the distinction is load-bearing. An
``unheld`` row is not an error and most of them will close in seconds:

- it is the industrial column of a table we read the residential column of;
- it is a standard for a detached house, a duplex, a school;
- it is an accessory-structure limit, a fence, a sign;
- it is the same standard in a district this layer does not encode.

What it is *not* is invisible, which is what those lines are today. The
opposite error -- a standard we simply never took, sitting in a document we
have held for months -- looks exactly like the nine hundred lines around it,
and that is the failure this ledger is built to make findable. Milwaukie's side
yard height plane was found by hand; nothing was going to find the next one.

Three answers:

``unheld``      the line states a number, and this layer holds none like it for
                that field, in any zone. Read these.
``held``        some number on the line is one we already carry for that field
                somewhere. Bookkeeping -- the standard is in the corpus, on
                another row.
``unnumbered``  the line names a field and states no figure this can compare:
                a cross-reference, a prose condition, a bare exemption.

**What counts as a number is deliberately narrow.** Section numbers, ordinance
numbers, dashed OAR citations and the years in an amendment trail are masked
out before anything is read, and each field's *kind* supplies a plausibility
window -- a height of 40,000 is a floor area that wandered into the sentence,
not a height. Masking too much costs a row to ``unnumbered``, which is a queue
nobody has to work; masking too little costs a false alarm in the one queue
that is supposed to be worth reading.

**What counts as held is the figure a reader will find**, not the figure the
model uses: :func:`flats.encode.readiness._printed` already answers that
question for every derived form this project carries -- per-dwelling areas,
acreages, one-space-per-two-units rates -- and it is reused here rather than
re-derived, so a new form has one place to be taught, exactly as the citation
check does.

Run it::

    uv run python -m flats.encode.missed
    uv run python -m flats.encode.missed or/clackamas/milwaukie
    uv run python -m flats.encode.missed --csv data/flats/missed.csv
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Sequence

from flats.encode.crossrefs import _cited_lines, _doc_ids
from flats.encode.readiness import _printed, _printed_variant
from flats.encode.uncited import Uncited, _sections, survey
from flats.provenance.store import ProvenanceStore
from flats.rules.fields import FIELDS
from flats.rules.loader import load_rules
from flats.rules.model import Layer

#: Spans that carry numbers which are never standards. Masked before any digit
#: is read, because one section number in a sentence is enough to make a line
#: look like it states a figure this layer has never held.
_MASKS: tuple[re.Pattern[str], ...] = (
    # "Section 19.301.4", "Table 4.0131", "§ 33.110", "Ord. 1234"
    re.compile(
        r"(?:§+\s*|\b(?:sections?|tables?|chapters?|figures?|subsections?|titles?"
        r"|exhibits?|appendix|ordinances?|ord|nos?|paragraphs?|items?|notes?"
        r"|maps?|policies|policy|charts?|columns?|rows?)\.?\s*)"
        r"[A-Za-z]?\d+(?:[.\-–—][\dA-Za-z]+)*",
        re.IGNORECASE,
    ),
    # A dotted citation on its own -- "19.301.4". Two dots, because "19.5" is
    # a measurement and this ledger exists to read measurements.
    re.compile(r"\b\d+(?:\.\d+){2,}\b"),
    # An OAR or hyphenated code number -- "660-046-0220", "33-110". Two digits
    # a side, so "3-5 feet" survives: a masked range costs a row to the
    # unnumbered pile, and that pile is where a real standard goes to hide.
    re.compile(r"\b\d{2,}(?:-\d{2,})+\b"),
    # The amendment trail every scanned ordinance ends with.
    re.compile(
        r"\b(?:amend\w*|adopt\w*|repeal\w*|effective|eff|enacted|passed)\b[^.;]{0,40}",
        re.IGNORECASE,
    ),
)

#: A bare number, after masking. Commas are part of it -- "5,000" is one
#: figure -- and a trailing ordinal or letter is not.
_NUMBER = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?![\w.])")

#: The unit a figure of each kind has to be wearing. This is the whole
#: difference between a ledger worth reading and a ledger of every digit in a
#: paragraph: Milwaukie 19.303.4 says a building "can utilize up to 2 of the
#: development incentive bonuses", and 2 is a perfectly plausible number of
#: feet. It is not a height, and the sentence says so by not putting "ft"
#: after it.
#:
#: A standard states its unit. Prose about a standard often does not, and the
#: cost of insisting is a row filed as ``unnumbered`` -- a queue nobody has to
#: work -- rather than a false alarm in the one queue that is meant to be read.
#: Each kind maps to the units it can be printed in, and each unit names its
#: own window above. Order matters only in that the first unit a figure wears
#: is the one it is judged by.
_UNIT: dict[str, tuple[tuple[str, str], ...]] = {
    "length_ft": ((r"(?:ft\b|feet\b|foot\b|')", "ft"),),
    "area_sqft": (
        (r"(?:sq\.?\s*ft|square\s+f(?:ee|oo)t|\bsf\b)", "sqft"),
        (r"acres?\b", "acres"),
    ),
    "percent": ((r"(?:%|percent|percentage)", "percent"),),
    "ratio": ((r"(?:spaces?\b|stalls?\b|per\b|:\s*\d|to\s+1\b)", "ratio"),),
    "count": (
        (r"(?:units?\b|dwellings?\b|stor(?:y|ies)\b|spaces?\b|stalls?\b|bedrooms?\b)", "count"),
    ),
}

#: How far past the figure its unit may sit. Three characters covers the
#: bracketed restatement Oregon ordinances are fond of -- "forty-five (45)
#: feet" -- and stops well short of the next clause.
_GAP = r"[\s\)\.\-–—]{0,3}"

#: What magnitude a figure can plausibly have, **given the unit it is wearing**.
#: A number outside its window is something else in the same sentence -- a floor
#: area beside a height, a lot size beside a coverage percentage -- and
#: comparing it against the wrong field's values manufactures a disagreement.
#:
#: The window belongs to the unit rather than to the kind because one kind can
#: be printed in two units. An area is 5,000 square feet or 80 acres, and 80 is
#: below any floor that would exclude a square footage. Nothing is converted:
#: this ledger compares the figure a reader will find against the figure the
#: file records having found, and both are printed in whatever unit the
#: ordinance chose -- the same bargain :func:`_printed` makes.
#:
#: The windows are wide on purpose. They throw out an obvious category error;
#: they do not judge whether a standard is reasonable.
_WINDOW: dict[str, tuple[Decimal, Decimal]] = {
    "ft": (Decimal("1"), Decimal("400")),
    "sqft": (Decimal("100"), Decimal("10000000")),
    "acres": (Decimal("0.05"), Decimal("2000")),
    "percent": (Decimal("0"), Decimal("100")),
    "ratio": (Decimal("0.01"), Decimal("100")),
    "count": (Decimal("1"), Decimal("500")),
}

#: Kinds this cannot compare at all. A bool has no figure; an enum has no
#: order; a curve is a table and its rows are checked by the column ledger.
_UNCOMPARABLE = frozenset({"bool", "enum", "curve"})

#: How near two figures may be and still count as the same standard. Codes
#: print "twenty-two feet" as 22 and a table prints 22.0; nothing in this
#: corpus distinguishes standards a hundredth of a foot apart.
_TOL = Decimal("0.005")


@dataclass(frozen=True, slots=True)
class Missed:
    """One unread line naming a field, against what its layer holds."""

    layer: str
    field: str
    path: str
    line: int
    section: str
    text: str
    #: Figures on the line that could be a standard of this field.
    stated: tuple[Decimal, ...]
    #: Figures this layer holds for this field, in any zone, as printed.
    held: tuple[Decimal, ...]
    #: The intersection.
    matched: tuple[Decimal, ...]
    repeats: int = 1
    #: Fields an encoded value was read from *in this line's own section*.
    read_here: tuple[str, ...] = ()

    @property
    def verdict(self) -> str:
        if not self.stated:
            return "unnumbered"
        return "held" if self.matched else "unheld"

    @property
    def nearness(self) -> str:
        """How close this line sits to reading somebody already did.

        The single most useful thing known about an unread line, and it costs
        nothing: it is a property of where the line sits, not of what it says.

        ``same_field``      a value of *this very standard* was read from this
                            section. Somebody had the table open, took a row,
                            and left this one. That is the shape of every
                            missed standard this project has found by hand.
        ``read_section``    the section was read, for some other standard.
        ``unread_section``  nothing in this section has ever been quoted. Not a
                            miss so much as a door nobody opened -- real work,
                            different work, and much more of it.

        **A section is only as fine as the document's own headings.** Milwaukie
        prints ``19.301.4`` and the tiers mean what they say; Portland's
        extracted text carries ``33.110`` for a whole chapter and Wilsonville's
        carries ``4``, so there ``same_field`` means "somewhere in this
        chapter", which is a much weaker claim. It is still the right claim to
        make -- it is what the document supports -- but a Portland row at the
        top of the queue has earned less than a Milwaukie one.
        """
        if self.field in self.read_here:
            return "same_field"
        return "read_section" if self.read_here else "unread_section"

    @property
    def novel(self) -> tuple[Decimal, ...]:
        """The figures on this line that appear nowhere in the layer."""
        return tuple(s for s in self.stated if not _near(s, self.held))


def _near(figure: Decimal, among: Sequence[Decimal]) -> bool:
    return any(abs(figure - other) <= _TOL for other in among)


def _figures(text: str, kind: str) -> tuple[Decimal, ...]:
    """Every number in a line that could be a standard of this kind.

    Two gates, and both are needed. The unit gate says the sentence meant this
    number as a measure of this kind; the window says the measure is of a size
    this kind can have. Neither alone is enough -- "25% of the gross floor
    area" wears a unit and is not a height, and a bare 12 in a sentence about
    heights is inside every window there is.
    """
    if kind in _UNCOMPARABLE or kind not in _UNIT:
        return ()
    masked = text
    for mask in _MASKS:
        masked = mask.sub(" ", masked)
    out: list[Decimal] = []
    for pattern, unit in _UNIT[kind]:
        wearing = re.compile(
            rf"(?<![\w.])(\d{{1,3}}(?:,\d{{3}})+|\d+(?:\.\d+)?)(?![\w.]){_GAP}{pattern}",
            re.IGNORECASE,
        )
        low, high = _WINDOW[unit]
        for token in wearing.findall(masked):
            try:
                figure = Decimal(token.replace(",", ""))
            except InvalidOperation:  # pragma: no cover - findall cannot produce this
                continue
            if low <= figure <= high and not _near(figure, out):
                out.append(figure)
    return tuple(out)


def _held(layer: Layer) -> dict[str, tuple[Decimal, ...]]:
    """Every printed figure this layer carries, by field.

    Zones are pooled deliberately. An uncited line rarely says which district
    it belongs to -- it is a table row, or a sentence under a heading -- so
    asking "does this jurisdiction hold this number for this standard at all"
    is the only question the text actually supports. It under-reports, which
    is the direction a queue meant to be read should err in.
    """
    out: dict[str, list[Decimal]] = defaultdict(list)
    for zone in layer.zones.values():
        for name, value in zone.values.items():
            for figure in (_printed(value), *(_printed_variant(v) for v in value.variants)):
                number = _decimal(figure)
                if number is not None and not _near(number, out[name]):
                    out[name].append(number)
    return {name: tuple(sorted(figures)) for name, figures in out.items()}


def _decimal(figure: object) -> Decimal | None:
    if isinstance(figure, bool) or figure is None:
        return None
    if isinstance(figure, (int, float, Decimal)):
        return Decimal(str(figure))
    return None


def _read_sections(
    layer: Layer, store: ProvenanceStore | None = None
) -> dict[str, dict[str, set[str]]]:
    """``path -> section -> the fields an encoded value was read from there``.

    Built from the same two pieces the reading ledger itself is built from --
    the cited lines of a layer and the document's own section headings -- so a
    section is "read" by exactly the evidence that stops a line being uncited,
    and the two can never disagree about what has been quoted.
    """
    store = store or ProvenanceStore()
    cited = _cited_lines(layer)
    out: dict[str, dict[str, set[str]]] = {}
    for path, lines_read in cited.items():
        if path.rsplit("/", 1)[0] != layer.layer:
            continue
        try:
            lines = store.text_path(path).read_text(encoding="utf-8").splitlines()
        except OSError:  # pragma: no cover - a document in the ledger but not on disk
            continue
        sections = _sections(lines, {i.partition(".")[0] for i in _doc_ids([path])})
        here: dict[str, set[str]] = defaultdict(set)
        for line, fields in lines_read.items():
            if 0 < line <= len(sections):
                here[sections[line - 1]].update(fields)
        out[path] = dict(here)
    return out


def audit(
    rows: Sequence[Uncited] | None = None,
    layers: dict[str, Layer] | None = None,
    store: ProvenanceStore | None = None,
    read: dict[str, dict[str, set[str]]] | None = None,
) -> list[Missed]:
    """Every ``unread`` statement, scored against its own layer's figures."""
    layers = load_rules(strict=False) if layers is None else layers
    if rows is None:
        rows = survey(list(layers.values()), store)
    if read is None:
        read = {}
        for layer in layers.values():
            read.update(_read_sections(layer, store))

    held_by_layer = {lid: _held(layer) for lid, layer in layers.items()}
    out: list[Missed] = []
    for row in rows:
        if row.bucket != "unread":
            continue
        definition = FIELDS.get(row.field)
        if definition is None:
            continue
        held = held_by_layer.get(row.layer, {}).get(row.field, ())
        stated = _figures(row.text, definition.kind)
        out.append(
            Missed(
                layer=row.layer,
                field=row.field,
                path=row.path,
                line=row.line,
                section=row.section,
                text=" ".join(row.text.split()),
                stated=stated,
                held=held,
                matched=tuple(s for s in stated if _near(s, held)),
                repeats=row.repeats,
                read_here=tuple(sorted(read.get(row.path, {}).get(row.section, ()))),
            )
        )
    return out


#: Closest first. A queue is worked from the top, so the order here is the
#: only editorial judgement this module makes, and it is made once.
NEARNESS = ("same_field", "read_section", "unread_section")


def by_figure(rows: Iterable[Missed]) -> list[tuple[str, str, Decimal, int, str]]:
    """``(layer, field, figure, lines, nearness)`` for unheld figures.

    The ranking that makes this workable, and it has two keys in this order:

    First, how near the line sits to reading already done. A figure printed in
    a section somebody took *this same standard* out of is a skipped row; the
    same figure in a chapter nobody has opened is a different job, and mixing
    the two is what makes a thousand-line ledger unreadable.

    Second, how many lines print it. One line printing an unheld number is
    usually another use's column; eleven lines printing the *same* unheld
    number for the same standard is a table nobody took.
    """
    counts: Counter[tuple[str, str, Decimal]] = Counter()
    nearest: dict[tuple[str, str, Decimal], int] = {}
    for row in rows:
        if row.verdict != "unheld":
            continue
        rank = NEARNESS.index(row.nearness)
        for figure in row.novel:
            key = (row.layer, row.field, figure)
            counts[key] += row.repeats
            nearest[key] = min(nearest.get(key, len(NEARNESS)), rank)
    return [
        (layer, field, figure, n, NEARNESS[nearest[(layer, field, figure)]])
        for (layer, field, figure), n in sorted(
            counts.items(),
            key=lambda kv: (nearest[kv[0]], -kv[1], kv[0][0], kv[0][1], kv[0][2]),
        )
    ]


def render(rows: Sequence[Missed], *, top: int = 40) -> str:
    counts = Counter(r.verdict for r in rows)
    near = Counter(r.nearness for r in rows if r.verdict == "unheld")
    ranked = by_figure(rows)
    out = [
        f"unread statements naming a field we screen on: {len(rows)}",
        f"  states a figure this layer holds nowhere: {counts['unheld']}",
        f"  states a figure the layer already carries: {counts['held']}",
        f"  states no comparable figure:               {counts['unnumbered']}",
        "",
        "of the unheld, where the line sits:",
        f"  in a section we took THIS standard from: {near['same_field']}",
        f"  in a section we read, for something else: {near['read_section']}",
        f"  in a section nothing has ever been quoted from: {near['unread_section']}",
        "",
        f"FIGURES THIS CORPUS HAS NEVER HELD: {len(ranked)}",
        "(a sort, not a finding -- most are another use's column; read from the top)",
        "",
    ]
    shown_tier = ""
    for layer, field, figure, lines, nearness in ranked[:top]:
        if nearness != shown_tier:
            shown_tier = nearness
            out.append(f"--- {nearness} ---")
        shown = format(figure.normalize(), "f")
        out.append(f"  {lines:>3} lines  [{layer}] {field} = {shown}")
        example = next(
            r
            for r in rows
            if r.layer == layer
            and r.field == field
            and figure in r.novel
            and r.nearness == nearness
        )
        out.append(f"           {example.path}#L{example.line}  ({example.section})")
        out.append(f"           {example.text[:150]}")
    if len(ranked) > top:
        out.append(f"  ... and {len(ranked) - top} more")
    return "\n".join(out)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("layer", nargs="*", help="restrict to these layer ids")
    ap.add_argument("--csv", type=Path)
    ap.add_argument("--top", type=int, default=40)
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        # Extracted PDF text carries ligatures -- 'fl' as one glyph -- that a
        # Windows console cannot encode, and a ledger that dies printing the
        # evidence it found is worse than one that prints a question mark.
        sys.stdout.reconfigure(errors="replace")

    layers = load_rules(strict=False)
    if args.layer:
        layers = {lid: layer for lid, layer in layers.items() if lid in set(args.layer)}
    rows = audit(layers=layers)
    print(render(rows, top=args.top))
    if args.csv:
        import csv

        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(
                ["layer", "field", "verdict", "nearness", "path", "line", "section",
                 "stated", "novel", "held", "repeats", "text"]
            )
            order = {n: i for i, n in enumerate(NEARNESS)}
            for r in sorted(
                rows,
                key=lambda r: (r.verdict != "unheld", order[r.nearness], r.layer, r.path, r.line),
            ):
                w.writerow(
                    [
                        r.layer,
                        r.field,
                        r.verdict,
                        r.nearness,
                        r.path,
                        r.line,
                        r.section,
                        ",".join(format(f.normalize(), "f") for f in r.stated),
                        ",".join(format(f.normalize(), "f") for f in r.novel),
                        ",".join(format(f.normalize(), "f") for f in r.held),
                        r.repeats,
                        r.text,
                    ]
                )
        print("wrote", args.csv)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
