"""Code we know exists and have never fetched.

Every other check in this system reasons about documents in the store. This one
reasons about the documents they *point at*. A code chapter is not a self-
contained statement of anything: it says "subject to the standards of Section
7.0420", "except as provided in Chapter 52", "see TDC 36.410", and each of
those is a sentence that can change a number without appearing anywhere near
it.

Gresham is why this exists. Its rear setbacks were read from Table 4.0130 in
the residential chapter, and the sentence that makes a 26 ft building stand
five feet further back lives in 7.0420, a *design standards* chapter nothing in
the encoding cited. It was found by reading, a year late, across roughly 21,000
lots. Nothing reported it, because every check in the system started from a
document we held, and that document was not held.

So the question here is the one nobody was asking: **which sections do our own
documents reference that we cannot open?**

Resolution is deliberately generous. A reference resolves if any document held
for that jurisdiction prints a heading for it -- codes are extracted with
section numbers at the start of a line, and a whole-title fetch (Oregon City's
Title 17 is one file, Wilsonville's Chapter 4 is another) answers for every
section inside it. What survives is a reference to text that is genuinely not
in the store.

Two rankings, and the second is the one to work from:

``mentions``
    How many times the corpus points at it. A chapter referenced twenty times
    is load-bearing somewhere.
``binding``
    The reference stands within a few lines of text an encoded value was read
    from. That is the Gresham shape exactly -- a standard and, beside it, a
    pointer to the rule that qualifies it. These are not "chapters we might
    want"; they are chapters that qualify numbers this screen is using now.

State law (ORS, OAR) is counted separately. It is a different fetch problem
with a different source, and mixing it in would bury a city's own missing
chapter under a hundred boilerplate statutory references.

Run it::

    uv run python -m flats.encode.crossrefs
    uv run python -m flats.encode.crossrefs or/clackamas/tualatin
    uv run python -m flats.encode.crossrefs --binding
"""

from __future__ import annotations

import csv
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from flats.provenance.store import ProvenanceStore, parse_quote
from flats.rules.loader import load_rules
from flats.rules.model import Layer

#: Where the ledger is written, beside the coverage ledger it complements.
LEDGER = Path(__file__).resolve().parents[2] / "data" / "flats" / "crossrefs.csv"

#: How near an encoded citation a reference must stand to count as binding.
#: Wider than a line because a table's "Additional Standards" column and the
#: row it qualifies are printed several lines apart, and narrower than a page
#: because a reference in the next section is about the next section.
BINDING_WINDOW = 12

#: A section number, with the suffix letter some codes append (Tualatin's
#: Chapter 73A). The letter must end the token — "40.220LOW DENSITY" is table
#: text that lost its space in extraction, not section 40.220L.
_NUM = r"\d[\d.\-]*\d(?:[A-Z](?![A-Za-z]))?|\d(?:[A-Z](?![A-Za-z]))?"
_REF = re.compile(
    #: Three ways a document points somewhere else, and they need different
    #: strictness.
    #:
    #: A spelled-out word may take a bare number: "Chapter 35" is a reference
    #: and there is nothing else it could be.
    rf"(?:(?:Chapters?|Sections?|Subsections?|Titles?|Articles?|Divisions?)"
    rf"\s+(?P<named>{_NUM})"
    #: A city's own abbreviation may not. Every city invents one (TDC, CDC,
    #: FMC, MCC, PCC, GDC) so they are matched generically — and generically
    #: also matches a zone code, which in an extracted table sits directly in
    #: front of a number: "MDR-12, OFR   10 ft." is not a reference to Section
    #: 10. Requiring a dot in the number is what separates the two, because a
    #: section number has one and a table cell does not. ORS and OAR are
    #: excluded here and counted by :func:`state_law`.
    #: The chapter may carry a letter — "TDC 73A.170" — and without it the
    #: whole reference went unread rather than being read loosely: the abbrev
    #: branch failed at the "A", and the other two branches want a keyword or
    #: three dotted groups. Tualatin's accessory-dwelling standards were cited
    #: twice in a held document and appeared in no ledger at all. The letter
    #: must end the chapter token, which is the same rule the named branch
    #: uses and the reason "40.220LOW DENSITY" is still not section 40.220L.
    r"|(?<![A-Za-z])(?!ORS\b|OAR\b)[A-Z]{2,4}\b\s+"
    r"(?P<abbrev>\d+(?:[A-Z](?![A-Za-z]))?\.[\d.\-]*\d)"
    #: And a number with three dotted groups needs no introduction at all — a
    #: decimal never has two dots, and a section number often does.
    r"|(?<![\d.])(?P<dotted>\d+\.\d+\.\d+[\d.]*))"
)
#: State law, counted apart from a city's own chapters.
_STATE = re.compile(r"\b(?:ORS|OAR)\s+(?P<num>[\d][\d.\-]*)")
#: A section heading: the number that opens a line. Extraction puts them there
#: in every document in this store, whether the code prints "17.02.010" or
#: "Section 4.137." or a bare "7.0420" in a contents block.
#: A leading abbreviation is part of the heading in several codes -- Tualatin
#: prints "TDC 40.300. Development Standards." as the section's own title, and
#: reading only line-initial digits would report a city's own chapters as
#: unfetched.
#:
#: So is a section symbol, and missing it is worse than missing an
#: abbreviation. Four jurisdictions print every heading in the form
#: "SECTION-SIGN 19.302.4. Development Standards." — 837 lines across
#: Wilsonville, unincorporated Multnomah, Lake Oswego and Milwaukie — and
#: without it a city reports its own fetched chapters as missing. Milwaukie led
#: the first ledger with 123 binding hits on sections printed in the document
#: the references were read from.
_HEADING = re.compile(
    r"^\s*(?:§\s*)?(?:(?:Section|Chapter)\s+|[A-Z]{2,5}\s+)?"
    r"(?P<num>\d[\d.\-]*\d(?:[A-Z](?![A-Za-z]))?|\d(?:[A-Z](?![A-Za-z]))?)\b"
)


@dataclass(frozen=True, slots=True)
class Dangling:
    """One reference this corpus makes and cannot follow."""

    layer: str
    ref: str
    mentions: int
    binding: int
    #: Where it is written, most-referenced document first.
    sources: tuple[str, ...]
    #: One line of context, so the row can be judged without opening anything.
    sample: str

    @property
    def rank(self) -> tuple[int, int]:
        return (self.binding, self.mentions)


def _doc_ids(paths: Iterable[str]) -> set[str]:
    """The section numbers a filename claims to hold.

    ``40-41.residential`` holds two chapters, ``7.0400.middle-housing-design``
    holds one, and ``4.planning`` holds all of Chapter 4. Read off the leading
    numeric part of the stem, because that is the convention every document in
    the store was named under.
    """
    ids: set[str] = set()
    for path in paths:
        stem = Path(path).stem
        lead = []
        for part in stem.split("."):
            # A trailing letter belongs to the chapter: Tualatin's design
            # standards are Chapter 73A and its condominium rules are 73C, and
            # a reader that stopped at the first non-digit gave that document
            # no sections at all — it claimed nothing and the chapter it held
            # went on reporting as unfetched.
            if not re.fullmatch(r"\d[\d\-]*[A-Z]?", part):
                break
            lead.append(part)
        if not lead:
            continue
        ids |= _spanned(".".join(lead))
    return ids


def _spanned(head: str) -> set[str]:
    """The sections a hyphenated name covers, in whichever group it is in.

    ``40-41`` is two chapters and ``73A.020-060`` is a span within one, and a
    document that names a span answers for everything inside it. The range
    read only in the first group before, so ``36.400-420`` claimed a section
    number that does not exist and answered for none of the three it held.
    """
    groups = head.split(".")
    for i, group in enumerate(groups):
        lo, sep, hi = group.partition("-")
        if not sep or not (lo.isdigit() and hi.isdigit()) or int(lo) > int(hi):
            continue
        # Width preserved: this code prints 73A.030, and 73A.30 is a section
        # of some other city's code.
        wide = len(lo) if lo.startswith("0") else 0
        return {
            ".".join(groups[:i] + [f"{n:0{wide}d}" if wide else str(n)] + groups[i + 1 :])
            for n in range(int(lo), int(hi) + 1)
        }
    return {head}


def _headings(text: str, owns: set[str]) -> set[str]:
    """Section numbers this document prints at the start of a line and owns.

    The ownership test is what keeps a cross-reference from being read as a
    heading. Extracted table text wraps, and Tualatin's residential chapter
    prints a bare ``TDC 36.410.`` at the start of eight lines — every one of
    them a pointer to a chapter this store does not hold. Taken as headings
    they answer for themselves, and the single reference most worth chasing in
    that city reports as fetched.

    So a heading has to belong here: its first dotted component must match the
    document's own. A chapter file answers for every section inside it, which
    is what makes a whole-title fetch work, and answers for nothing outside it,
    which is what makes this check work at all.
    """
    found: set[str] = set()
    for line in text.splitlines():
        m = _HEADING.match(line)
        if not m:
            continue
        num = m.group("num").rstrip(".")
        if num.partition(".")[0] in owns:
            found.add(num)
    return found


def _resolves(ref: str, ids: set[str], headings: set[str]) -> bool:
    """Whether some held document answers for this reference.

    Generous on purpose. A whole-title fetch answers for every section inside
    it, so a reference resolves when a document *claims* the chapter and the
    number is printed in it, or when any document prints the number at all --
    and a bare chapter reference resolves when we hold anything under it.
    """
    if ref in headings or ref in ids:
        return True
    # "Chapter 52" against a store holding 52.010, 52.020, ...
    return any(h.startswith(f"{ref}.") for h in headings) or any(
        i == ref or i.startswith(f"{ref}.") for i in ids
    )


def _cited_lines(layer: Layer) -> dict[str, set[int]]:
    """Per document, every line an encoded value in this layer was read from."""
    lines: dict[str, set[int]] = defaultdict(set)

    def take(quote: str | None) -> None:
        if not quote:
            return
        try:
            ref = parse_quote(quote)
        except Exception:
            return
        lines[ref.path].update(ref.numbers)

    for value in layer.defaults.values():
        take(value.prov.quote)
    for zone in layer.zones.values():
        if zone.like is not None:
            take(zone.like.prov.quote)
        for value in zone.values.items and zone.values.values():
            take(value.prov.quote)
            take(value.step_back_quote)
            take(value.measured_on_quote)
            take(value.qualified_quote)
            for variant in value.variants:
                take(variant.prov.quote)
    return lines


def _near(line: int, cited: set[int]) -> bool:
    return any(abs(line - c) <= BINDING_WINDOW for c in cited)


def dangling(layer: Layer, store: ProvenanceStore | None = None) -> list[Dangling]:
    """Every reference this layer's documents make that the store cannot open."""
    store = store or ProvenanceStore()
    prefix = f"{layer.layer}/"
    paths = [p for p in store.documents() if p.startswith(prefix)]
    if not paths:
        return []

    texts = {p: store.text_path(p).read_text(encoding="utf-8") for p in paths}
    ids = _doc_ids(paths)
    headings: set[str] = set()
    for path, text in texts.items():
        headings |= _headings(
            text, {i.partition(".")[0] for i in _doc_ids([path])}
        )
    cited = _cited_lines(layer)

    mentions: dict[str, int] = defaultdict(int)
    binding: dict[str, int] = defaultdict(int)
    sources: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    sample: dict[str, str] = {}

    for path, text in texts.items():
        here = cited.get(path, set())
        for n, line in enumerate(text.splitlines(), start=1):
            for m in _REF.finditer(line):
                ref = (
                    m.group("named") or m.group("abbrev") or m.group("dotted")
                ).rstrip(".")
                if not ref or ref.isdigit() and len(ref) < 2:
                    continue
                if _resolves(ref, ids, headings):
                    continue
                mentions[ref] += 1
                sources[ref][Path(path).name] += 1
                if _near(n, here):
                    binding[ref] += 1
                sample.setdefault(ref, line.strip()[:160])

    out = [
        Dangling(
            layer=layer.layer,
            ref=ref,
            mentions=count,
            binding=binding[ref],
            sources=tuple(
                name
                for name, _ in sorted(
                    sources[ref].items(), key=lambda kv: (-kv[1], kv[0])
                )
            ),
            sample=sample[ref],
        )
        for ref, count in mentions.items()
    ]
    out.sort(key=lambda d: (-d.rank[0], -d.rank[1], d.ref))
    return out


def state_law(layer: Layer, store: ProvenanceStore | None = None) -> dict[str, int]:
    """ORS and OAR references, counted apart from a city's own chapters."""
    store = store or ProvenanceStore()
    prefix = f"{layer.layer}/"
    counts: dict[str, int] = defaultdict(int)
    held = {Path(p).stem for p in store.documents() if p.startswith("or/")}
    for path in store.documents():
        if not path.startswith(prefix):
            continue
        text = store.text_path(path).read_text(encoding="utf-8")
        for m in _STATE.finditer(text):
            num = m.group("num").rstrip(".")
            if not any(stem.endswith(num) for stem in held):
                counts[num] += 1
    return dict(counts)


def survey(
    layers: Sequence[Layer] | None = None, store: ProvenanceStore | None = None
) -> list[Dangling]:
    store = store or ProvenanceStore()
    chosen = layers if layers is not None else list(load_rules().values())
    rows: list[Dangling] = []
    for layer in chosen:
        rows.extend(dangling(layer, store))
    rows.sort(key=lambda d: (-d.rank[0], -d.rank[1], d.layer, d.ref))
    return rows


def write(rows: Sequence[Dangling], path: Path | None = None) -> Path:
    file = path or LEDGER
    file.parent.mkdir(parents=True, exist_ok=True)
    with file.open("w", encoding="utf-8", newline="") as fh:
        out = csv.writer(fh)
        out.writerow(["layer", "ref", "mentions", "binding", "sources", "sample"])
        for row in rows:
            out.writerow(
                [
                    row.layer,
                    row.ref,
                    row.mentions,
                    row.binding,
                    " ".join(row.sources),
                    row.sample,
                ]
            )
    return file


def render(rows: Sequence[Dangling], *, binding_only: bool = False) -> Iterator[str]:
    shown = [r for r in rows if r.binding] if binding_only else list(rows)
    if not shown:
        yield "no unfetched references — every section this corpus points at is in the store"
        return

    by_layer: dict[str, list[Dangling]] = defaultdict(list)
    for row in shown:
        by_layer[row.layer].append(row)

    total_binding = sum(1 for r in shown if r.binding)
    yield (
        f"{len(shown)} unfetched reference(s) across {len(by_layer)} jurisdiction(s)"
        f" — {total_binding} standing beside a number this screen uses"
    )
    yield ""
    for layer in sorted(by_layer, key=lambda l: (-max(r.rank for r in by_layer[l])[0], l)):
        group = by_layer[layer]
        yield f"  {layer}   ({sum(r.mentions for r in group)} mention(s))"
        for row in group[:12]:
            mark = f"BINDING x{row.binding}" if row.binding else ""
            yield f"    {row.ref:<14} {row.mentions:>3} mention(s)  {mark}"
            yield f"       in {row.sources[0]}: {row.sample}"
        if len(group) > 12:
            yield f"    ... and {len(group) - 12} more"
        yield ""


def main(argv: Sequence[str] | None = None) -> int:
    # Code documents carry ligatures and dashes a Windows console cannot
    # encode, and a ledger that crashes on a sample line is a ledger nobody
    # runs. The CSV keeps the characters; the terminal gets what it can print.
    if hasattr(sys.stdout, "reconfigure"):  # pragma: no cover
        sys.stdout.reconfigure(errors="replace")
    args = list(sys.argv[1:] if argv is None else argv)
    binding_only = "--binding" in args
    args = [a for a in args if not a.startswith("--")]

    layers = load_rules()
    chosen = [layers[a.strip("/")] for a in args] if args else list(layers.values())
    rows = survey(chosen)
    for line in render(rows, binding_only=binding_only):
        print(line)

    if not args:
        print(f"\nwritten -> {write(rows)}")
        for layer in chosen:
            state = state_law(layer)
            if state:
                top = sorted(state.items(), key=lambda kv: -kv[1])[:4]
                named = ", ".join(f"{n} x{c}" for n, c in top)
                print(f"  state law unfetched  {layer.layer}: {named}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
