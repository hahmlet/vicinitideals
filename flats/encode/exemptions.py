"""The standard that is not there, and whether the page says so.

``exempt: true`` is the strongest thing a rule file can say. Every other value
narrows what a lot may do; this one removes a test entirely, and a lot that
would have failed it comes back GREEN instead. Encoding an exemption where the
code states a standard is the one mistake in this corpus that cannot produce a
false RED -- it produces the other kind, silently, on every lot in the zone.

Which is why the exemption is also the easiest value to get wrong. It is the
answer a reader reaches for when a table cell is blank, when a column prints an
em dash, when a row carries nothing but ``[2]``, and when the sentence that
would have stated the standard is on a page nobody opened. Three of those are
an exemption and one of them is a citation pointing at a pointer.

So this ledger asks one question of every exempt value in the corpus: **does
the text it cites say so?** Not whether the reading was right -- a reading is
argued in the rule file's own prose and this cannot judge it. Whether a
reviewer opening the citation would find the exemption there, or would find a
marker, a dash, or a number.

Five verdicts, and only the first is closed:

*stated*
    The quoted text carries exemption language. "None", "no minimum", "not
    applicable", "NA", "does not apply", "exempt", "applies only to ... in the
    Willamette Historic District". A reviewer opens the citation and reads the
    answer.

*numeric*
    The quoted text prints a figure and no exemption language. Usually
    innocent -- Oregon's zoning tables put three districts on one printed line,
    so quoting the header to say which column a cell came from drags in two
    other columns' numbers. Sometimes not: it is also what a standard nobody
    noticed looks like. A reviewer has to read it either way, which is the
    point.

*marker*
    The quoted text is a footnote reference and nothing else -- ``[2]``,
    ``[2],[3]``. The evidence is one line further down and is not cited. Lake
    Oswego's density exemptions were all seven of these: the note does state
    the exemption, in as many words, and no reviewer signing the card could
    have seen it.

*dash*
    The cited cell is an em dash. That is how these tables print "no standard
    here" and it is real evidence, but it is evidence a regular expression
    cannot distinguish from an extraction that dropped a number, so it is
    counted separately rather than waved through.

*silent*
    Prose, with neither exemption language nor a figure. The rarest and the
    least readable: the citation points at something that answers no question.

The counts are pinned by ``flats/tests/test_exemptions.py``. A new open row is
a test failure and gets explained or fixed, which is the same discipline the
refusals ledger runs on -- a report nobody is obliged to read is a report
nobody reads.

Run it::

    uv run python -m flats.encode.exemptions
    uv run python -m flats.encode.exemptions or/clackamas/lake-oswego
    uv run python -m flats.encode.exemptions --all
"""

from __future__ import annotations

import csv
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer, Value, Variant

#: Where the ledger is written.
LEDGER = Path(__file__).resolve().parents[2] / "data" / "flats" / "exemptions.csv"

#: The ways a code says a standard is not there.
#:
#: Deliberately literal. Every alternative here was read off a page in this
#: corpus, and the ones that look oddly specific are the ones that had to be:
#:
#: * ``no <up to three words> minimum`` catches Portland's "There is no
#:   required minimum lot size", where the adjective sits between the two words
#:   that matter.
#: * ``is not the minimum`` catches Clackamas County's sentence that a
#:   quadplex's district land area "is not the minimum lot area required per
#:   dwelling unit" -- an exemption written as a definition.
#: * ``applies only to`` catches an applicability paragraph, which is how a
#:   standard says it is absent everywhere else. West Linn's building-width cap
#:   exists only inside the Willamette Historic District and says so there.
#:
#: Not here: "shall not exceed", "no more than", "not less than". Those state a
#: standard rather than removing one, and a ledger that read them as exemptions
#: would close every row it exists to open.
#:
#: Also not here, and this one is a decision rather than an oversight: the
#: plural "no setback requirements". This list is not an inventory of English
#: negation and is not trying to be. Nothing here knows which standard a
#: sentence is about, so a phrase that closes a row closes it for every value
#: quoting the same span -- and Fairview quotes the whole of 19.125.040 for
#: three separate fields. "There are no setback requirements for side and rear
#: facades" is a real exemption for two of them and says nothing at all about
#: the third, whose exemption rests on the section listing every standard it
#: has and not listing lot size. Admitting the phrase would close that row on
#: a sentence about something else. An over-scoped bucket costs a re-read; an
#: under-scoped one costs a false GREEN, which is the trade this whole module
#: is here to take.
_EXEMPT = re.compile(
    r"(\bnone\b"
    r"|\bno\s+(?:\w+\s+){0,3}(?:minimum|maximum|min\.|max\.|required|requirement"
    r"|limit|limits|standard|standards|density|cap)\b"
    r"|\bis\s+not\s+(?:the\s+)?(?:\w+\s+){0,2}(?:minimum|maximum)\b"
    r"|\bnot\s+required\b|\bnot\s+applicable\b|\bn/a\b|\bexempt|\bunlimited\b"
    r"|(?:do|does|shall|may|will|is|are)\s+not\s+apply"
    r"|\bnot\s+subject\s+to\b|\bshall\s+not\s+be\s+required\b"
    r"|\bis\s+not\s+applied\b|\bnot\s+established\b|\bno\s+such\b"
    r"|\bapplies\s+only\s+(?:to|in|within)\b)",
    re.I,
)

#: ``NA`` standing alone in a table cell. Case-sensitive, and its own pattern
#: rather than an alternative in :data:`_EXEMPT`, because the case is the whole
#: signal: Gresham's floor area ratio row prints it for four of seven districts
#: and a case-insensitive match would take the "na" out of half the words in a
#: paragraph.
_NA = re.compile(r"(?:^|\s)N\.?A\.?(?:$|\s)")

#: A cell holding nothing but a dash. Em, en, hyphen and minus all appear.
_DASH = re.compile(r"^[\s—–−-]+$")

#: A cell holding nothing but footnote markers: ``[2]``, ``[2],[3]``, ``(4)``.
#:
#: The brackets are required. A cell holding a bare number is the cell, and it
#: is exactly the evidence a numeric value should cite; only a reference to a
#: note printed somewhere else is a citation that points at a pointer.
_MARKER = re.compile(r"^\s*(?:[\[(]\s*\d+[a-z]?\s*[\])][\s,;]*)+$")

#: Worst first. A quote spanning several lines takes the first verdict on this
#: list that any of its lines earns, so one line stating the exemption answers
#: for the span -- and, failing that, a printed figure outranks a dash, because
#: a figure is the one that could be a standard nobody noticed.
ORDER = ("stated", "numeric", "marker", "dash", "silent")

#: The verdicts this ledger reports. Everything but ``stated``.
OPEN = tuple(v for v in ORDER if v != "stated")


def verdict(text: str) -> str:
    """What a reviewer opening this citation would find."""
    seen: set[str] = set()
    for line in text.splitlines():
        if not line.strip():
            continue
        if _EXEMPT.search(line) or _NA.search(line):
            seen.add("stated")
        elif _DASH.match(line):
            seen.add("dash")
        elif _MARKER.match(line):
            seen.add("marker")
        elif any(c.isdigit() for c in line):
            seen.add("numeric")
        else:
            seen.add("silent")
    return next((v for v in ORDER if v in seen), "silent")


@dataclass(frozen=True, slots=True)
class Exemption:
    """One value or variant that says a standard is not there."""

    layer: str
    zone: str
    field: str
    #: The conditions the variant fires under, empty on a base value. A variant
    #: exemption is a narrower claim than a base one and reads differently:
    #: Gresham's minimum density is exempt only below 11,000 square feet.
    when: tuple[str, ...]
    #: The citation, verbatim. Empty where the value carries none.
    quote: str
    verdict: str
    #: The cited text, flattened to one line a terminal can print.
    text: str

    @property
    def label(self) -> str:
        conds = f" [{'+'.join(self.when)}]" if self.when else ""
        return f"{self.layer} {self.zone} {self.field}{conds}"


def _text(quote: str | None, store: ProvenanceStore) -> str:
    if not quote:
        return ""
    try:
        return store.quote(quote)
    except Exception as exc:  # a malformed or unresolvable citation
        return f"<{exc}>"


def _row(
    layer: str,
    zone: str,
    field: str,
    when: tuple[str, ...],
    quote: str | None,
    store: ProvenanceStore,
) -> Exemption:
    text = _text(quote, store)
    flat = " | ".join(" ".join(line.split()) for line in text.splitlines() if line.strip())
    return Exemption(
        layer=layer,
        zone=zone,
        field=field,
        when=when,
        quote=quote or "",
        verdict=verdict(text) if text else "silent",
        text=flat[:300],
    )


def exemptions(layer: Layer, store: ProvenanceStore | None = None) -> list[Exemption]:
    """Every exempt value and variant in one layer."""
    store = store or ProvenanceStore()
    rows: list[Exemption] = []

    def take(zone: str, field: str, held: Value | Variant, when: tuple[str, ...]) -> None:
        if not held.exempt:
            return
        rows.append(_row(layer.layer, zone, field, when, held.prov.quote, store))

    for field, value in layer.defaults.items():
        take("(default)", field, value, ())
        for variant in value.variants:
            take("(default)", field, variant, tuple(variant.when))
    for name, zone in layer.zones.items():
        for field, value in zone.values.items():
            take(name, field, value, ())
            for variant in value.variants:
                take(name, field, variant, tuple(variant.when))

    rows.sort(key=lambda r: (ORDER.index(r.verdict), r.zone, r.field))
    return rows


def survey(
    layers: Sequence[Layer] | None = None, store: ProvenanceStore | None = None
) -> list[Exemption]:
    store = store or ProvenanceStore()
    chosen = layers if layers is not None else list(load_rules().values())
    rows: list[Exemption] = []
    for layer in chosen:
        rows.extend(exemptions(layer, store))
    rows.sort(key=lambda r: (ORDER.index(r.verdict), r.layer, r.zone, r.field))
    return rows


def counts(rows: Sequence[Exemption]) -> dict[str, int]:
    """How many of each verdict, every key present even at zero."""
    out = dict.fromkeys(ORDER, 0)
    for row in rows:
        out[row.verdict] += 1
    return out


def write(rows: Sequence[Exemption], path: Path | None = None) -> Path:
    file = path or LEDGER
    file.parent.mkdir(parents=True, exist_ok=True)
    # lineterminator is not cosmetic. csv writes CRLF by default, so this
    # ledger regenerated on Windows rewrote every row it had and buried the
    # real change -- 264 new rows inside a 19,082-line diff, 2026-09-03. A
    # ledger nobody can read the diff of is a ledger nobody checks.
    with file.open("w", encoding="utf-8", newline="") as fh:
        out = csv.writer(fh, lineterminator="
")
        out.writerow(["layer", "zone", "field", "when", "verdict", "quote", "text"])
        for row in rows:
            out.writerow(
                [
                    row.layer,
                    row.zone,
                    row.field,
                    "+".join(row.when),
                    row.verdict,
                    row.quote,
                    row.text,
                ]
            )
    return file


def render(rows: Sequence[Exemption], *, show_all: bool = False) -> Iterator[str]:
    tally = counts(rows)
    open_rows = [r for r in rows if r.verdict != "stated"]

    yield (
        f"{len(rows)} exempt value(s): "
        + ", ".join(f"{tally[v]} {v}" for v in ORDER if tally[v])
    )
    yield ""

    if not open_rows:
        yield (
            "every exemption in this corpus cites text that states it -- a "
            "reviewer opening any of these citations reads the answer"
        )
        return

    by_layer: dict[str, list[Exemption]] = defaultdict(list)
    for row in open_rows:
        by_layer[row.layer].append(row)

    yield (
        f"{len(open_rows)} citation(s) a reviewer could not read the exemption "
        f"out of, across {len(by_layer)} jurisdiction(s)"
    )
    yield ""
    for name in sorted(by_layer):
        yield f"  {name}"
        shown: set[str] = set()
        for row in by_layer[name]:
            conds = f" [{'+'.join(row.when)}]" if row.when else ""
            yield f"    {row.verdict:<8} {row.zone:<12} {row.field}{conds}"
            # The same citation carries the same text for every zone quoting
            # it. Printing it once keeps a nine-zone table to nine lines.
            if show_all or row.quote not in shown:
                shown.add(row.quote)
                yield f"             {row.quote}"
                yield f"             {row.text[:180]}"
        yield ""


def main(argv: Sequence[str] | None = None) -> int:
    # Code documents carry characters a Windows console cannot encode, and a
    # ledger that crashes on a sample line is a ledger nobody runs.
    if hasattr(sys.stdout, "reconfigure"):  # pragma: no cover
        sys.stdout.reconfigure(errors="replace")
    args = list(sys.argv[1:] if argv is None else argv)
    show_all = "--all" in args
    args = [a for a in args if not a.startswith("--")]

    layers = load_rules()
    chosen = [layers[a.strip("/")] for a in args] if args else list(layers.values())
    rows = survey(chosen)
    for line in render(rows, show_all=show_all):
        print(line)

    if not args:
        print(f"written -> {write(rows)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
