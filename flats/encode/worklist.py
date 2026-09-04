"""The reading ledger, turned into four queues a person can work.

:mod:`flats.encode.uncited` counts every measured statement nothing quotes.
That is a ledger and it is right to be one: one row per statement, 4,693 of
them, which is the honest size of the reading debt. It is a bad worklist for
exactly the same reason, because the unit of work is not a statement. It is a
*decision*, and one decision almost always covers a whole section of code.

The same 4,693 lines are 649 sections. The twenty-five biggest carry 47% of
the ledger. So this module regroups the ledger by section, routes each section
to one of four queues, and leaves the ledger alone.

The routing guesses nothing. Sorting these by keyword was tried and left 43%
of the corpus unclassified, so only two facts decide it, and both are already
known for certain:

``missed``
    The section is in a chapter our encoding already quotes, and a line in it
    names a field the screen holds. Somebody's eye passed over this. The
    question is why we did not take it, and the answer is usually visible in
    one glance: is the number in the line one we already hold?

``condition``
    The same, except the line carries a condition -- "except on a corner lot",
    "for lots greater than 5,000 square feet". The number is not in dispute;
    its applicability is. A different verb, so a different queue.

``chapter``
    Nothing in this chapter has ever been quoted by anything. Not a line to
    check, a door to decide whether to open, and the two finds of 2026-09-04
    both came through one.

``nofield``
    A measure with no field behind it. Bulk. Most of it is answered by one
    ruling on the whole section -- a different building, a different stage, or
    a line that is not a statement at all.

"Is this about our building" and "is this even a sentence" are *answers* given
to a ``nofield`` card, not queues to sort into beforehand. That is why there
are four and not six.

Run it::

    uv run python -m flats.encode.worklist --counts
    uv run python -m flats.encode.worklist missed
    uv run python -m flats.encode.worklist missed --layer or/clackamas/milwaukie
"""

from __future__ import annotations

import hashlib
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from flats.encode.crossrefs import _cited_lines
from flats.encode.triage import _wrap, layer_path
from flats.encode.uncited import Uncited, survey
from flats.provenance.store import ProvenanceStore
from flats.rules.fields import FIELDS
from flats.rules.ledger import read_coverage
from flats.rules.loader import MIN_RULING, load_rules
from flats.rules.model import READING_OUTCOMES, Layer, Reading

#: The four queues, in the order they are worth working. ``missed`` leads
#: because it is the only one that can find a number we hold and hold wrongly.
KINDS: tuple[str, ...] = ("missed", "condition", "chapter", "nofield")

#: What each queue is called in front of a person, and the question it asks.
QUEUES: dict[str, tuple[str, str]] = {
    "missed": (
        "Missed standards",
        "A plain standard for a field we screen on, in a chapter we already "
        "read. Why didn't we take it?",
    ),
    "condition": (
        "Conditions",
        "This changes a number we hold, when something is true of the site. "
        "Is it true of ours?",
    ),
    "chapter": (
        "Unopened chapters",
        "Nobody has ever quoted a line of this chapter. Is there anything in "
        "it for us?",
    ),
    "nofield": (
        "No field for it",
        "We have nowhere to put this. Is it a gap in the model, or not our "
        "problem?",
    ),
}

#: A sentence whose number depends on something being true of the site. The
#: list is deliberately plain -- these are the words Oregon codes actually use
#: to hang a number on a condition, and a clever pattern here would put cards
#: in the wrong queue silently. A card routed to ``condition`` that turns out
#: to be flat is a two-second correction; the reverse is a missed exception.
_CONDITION = re.compile(
    r"\bexcept\b|\bunless\b|\bprovided that\b|\bin lieu\b|\bbonus\b"
    r"|may be (?:reduced|increased|modified|waived|adjusted)"
    r"|\bwhere the\b|\bwhen the\b|\bif the\b"
    r"|\bcorner\b|\balley\b|\bflag lot\b|\bthrough lot\b|\babut\w*\b"
    r"|\btransit\b|\barterial\b|\bcollector\b|\bslope\b"
    r"|for lots?\b|greater than|less than|\bor more\b|\bor less\b",
    re.I,
)

#: A citation, not a measurement. "19.301.4" and "33.120.205.C" are section
#: numbers, and reading them as figures would make every line disagree with
#: everything. Two dots or more is the test: a code numbers by containment and
#: a standard is never written "35.0.0".
_CITATION = re.compile(r"\b\d+(?:\.\d+){2,}\b")

#: A figure in a sentence. Commas stripped, so "5,000" and "5000" are one
#: number and a table that prints one and prose that prints the other agree.
_FIGURE = re.compile(r"\b\d[\d,]*(?:\.\d+)?\b")


def _numbers(text: str) -> tuple[float, ...]:
    """Every figure a line states, citations removed, in the order written."""
    out: list[float] = []
    for raw in _FIGURE.findall(_CITATION.sub(" ", text)):
        try:
            n = float(raw.replace(",", ""))
        except ValueError:  # pragma: no cover - the pattern cannot produce one
            continue
        if n not in out:
            out.append(n)
    return tuple(out)


def _held(layer: Layer) -> dict[str, frozenset[float]]:
    """Every number this layer holds, by the field that holds it.

    Zone, default and variant alike. Which zone is deliberately not tracked:
    an uncited line does not know its zone, and pretending otherwise would
    invent a comparison. The question this answers is the weaker, true one --
    *is this figure one we already have for this standard anywhere in this
    city* -- and that is enough to sort a duplicate from a disagreement.
    """
    out: dict[str, set[float]] = defaultdict(set)

    def take(field: str, value: object) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return
        out[field].add(float(value))

    for field, value in layer.defaults.items():
        take(field, value.value)
        for variant in value.variants:
            take(field, variant.value)
    for zone in layer.zones.values():
        for field, value in zone.values.items():
            take(field, value.value)
            for variant in value.variants:
                take(field, variant.value)
    return {k: frozenset(v) for k, v in out.items()}


@dataclass(frozen=True, slots=True)
class Line:
    """One uncited statement, with what we hold beside it."""

    line: int
    field: str
    text: str
    repeats: int
    #: The figures the line states.
    numbers: tuple[float, ...]
    #: The figures this layer holds for that field, anywhere.
    held: tuple[float, ...]

    @property
    def conditional(self) -> bool:
        return bool(_CONDITION.search(self.text))

    @property
    def agrees(self) -> bool | None:
        """Whether a figure we already hold appears in this line.

        ``None`` where the comparison cannot be made -- no field, no figure, or
        nothing held for that field. Three-valued on purpose: "we hold nothing
        to compare" and "we hold something and it differs" are opposite
        findings, and a boolean would file the first as agreement.
        """
        if not self.field or not self.numbers or not self.held:
            return None
        return any(n in self.held for n in self.numbers)

    @property
    def shown_held(self) -> str:
        """What we hold, for a person, shortest first."""
        return ", ".join(_num(n) for n in sorted(self.held)[:6])


def _num(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else f"{x:g}"


@dataclass(frozen=True, slots=True)
class Card:
    """One section of code, and the decision it wants."""

    layer: str
    path: str
    section: str
    kind: str
    lines: tuple[Line, ...]
    #: Lots in this jurisdiction. The sort, never a filter -- carried forward
    #: from the 2026-08-22 verticals design. A section of a city's code applies
    #: across that city, so the city's lots are the lots behind the card.
    lots: int = 0
    ruling: Reading | None = None

    @property
    def key(self) -> str:
        return f"{self.layer}|{self.path}#{self.section}"

    @property
    def card_key(self) -> str:
        """How the rule files name this card: ``<document>#<section>``."""
        return card_key(self.path, self.section)

    @property
    def doc(self) -> str:
        return self.path.rsplit("/", 1)[-1]

    @property
    def fields(self) -> tuple[str, ...]:
        return tuple(sorted({ln.field for ln in self.lines if ln.field}))

    @property
    def titles(self) -> tuple[str, ...]:
        """The fields, as a person names them."""
        return tuple(
            FIELDS[f].shown if f in FIELDS else f.replace("_", " ")
            for f in self.fields
        )

    @property
    def disagrees(self) -> int:
        """Lines stating a figure we hold a different one for.

        The alarm. A card with one of these is worth opening before a hundred
        that only confirm what we already have.
        """
        return sum(1 for ln in self.lines if ln.agrees is False)

    @property
    def unmeasured(self) -> int:
        """Lines naming a field where we hold nothing to compare against."""
        return sum(1 for ln in self.lines if ln.field and ln.agrees is None)

    @property
    def by_interest(self) -> tuple[Line, ...]:
        """The lines, disagreements first, then the ones we hold nothing for.

        A section can print twenty figures we already have and one we do not,
        and the one is the reason the card exists. Sorted here rather than in
        the template because ``agrees`` is three-valued and Jinja comparing
        ``None`` to a bool raises rather than ordering.
        """
        rank = {False: 0, None: 1, True: 2}
        return tuple(sorted(self.lines, key=lambda ln: (rank[ln.agrees], ln.line)))

    @property
    def moved(self) -> bool:
        """Whether the page moved under a decision already made.

        A ruling with a fingerprint that no longer matches was written about
        text nobody has seen since. It does not keep the card closed; it comes
        back with the drift shown, to be re-ruled in seconds or confirmed in
        one click.

        A ruling carrying no fingerprint at all is not drift. It was written
        by hand before the queues existed and there is nothing to compare.
        """
        return bool(
            self.ruling
            and self.ruling.fingerprint
            and self.ruling.fingerprint != self.fingerprint
        )

    @property
    def open(self) -> bool:
        """Whether this card still wants a decision.

        Three ways to be open, and they are different states worth keeping
        apart in the head: nobody has ruled, somebody ruled and the ruling
        orders work rather than closing (``encode``, ``read_it``,
        ``cant_tell``), or somebody ruled and the section has moved since.
        """
        return self.ruling is None or not self.ruling.closed or self.moved

    @property
    def outcome(self) -> str:
        return self.ruling.outcome if self.ruling is not None else ""

    @property
    def fingerprint(self) -> str:
        """What this section said when it was read.

        A ruling stores this. When a document is re-fetched and the section
        moves, the fingerprint stops matching and the ruling reopens rather
        than silently keeping a card closed against text nobody has seen --
        the same bargain ``FlatsRuleSignature`` strikes over a number and its
        citation, where editing either withdraws the signature.
        """
        body = "\n".join(f"{ln.line}\t{ln.text}" for ln in self.lines)
        return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def _kind(rows: Sequence[Uncited], quoted: bool) -> str:
    """Which queue a section belongs in.

    Precedence, not a score. A section carries lines of more than one shape and
    splitting it would put the same page in two queues; the strongest signal in
    it decides where the whole card goes.
    """
    if not quoted:
        return "chapter"
    fielded = [r for r in rows if r.field]
    if not fielded:
        return "nofield"
    if any(_CONDITION.search(r.text) for r in fielded):
        return "condition"
    return "missed"


def _lots_by_layer() -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for row in read_coverage() or []:
        out[row.jurisdiction] += row.lots
    return dict(out)



#: The regenerated ledger, held for the life of the process. The scan reads
#: every stored document -- two and a half seconds for the corpus, which is
#: fine once and not fine per page load. What changes while somebody works the
#: queue is the *rulings*, and those are read from the loaded layer and the
#: inbox on every call rather than cached, so a decision shows up immediately.
#:
#: Regenerated, never read from ``data/flats/uncited.csv``. A committed
#: artefact is a snapshot of what was true when somebody last ran the command,
#: and a queue built on one asks questions that answered themselves.
_LEDGER: list[Uncited] | None = None


def refresh() -> None:
    """Drop the ledger cache — call after fetching a document into the store."""
    global _LEDGER
    _LEDGER = None


def ledger(
    layers: Mapping[str, Layer] | None = None,
    store: ProvenanceStore | None = None,
) -> list[Uncited]:
    """Every uncited line in the corpus, regenerated once per process."""
    global _LEDGER
    if _LEDGER is None:
        chosen = layers if layers is not None else load_rules()
        _LEDGER = survey(list(chosen.values()), store or ProvenanceStore())
    return _LEDGER


def cards(
    layer: Layer,
    store: ProvenanceStore | None = None,
    rows: Sequence[Uncited] | None = None,
    lots: Mapping[str, int] | None = None,
    overrides: Mapping[str, Reading] | None = None,
) -> list[Card]:
    """This layer's uncited lines, regrouped into section cards.

    ``rows`` is the ledger, regenerated rather than read from
    ``data/flats/uncited.csv``. A committed artefact is a snapshot of what was
    true when somebody last ran the command, and a queue built on one asks
    questions that answered themselves -- the standing rule since three
    ledgers agreed on a number that was wrong.

    ``overrides`` carries rulings that exist outside the rule files: the review
    inbox, where a decision made in a browser lands before the drain writes it
    into the repository. Applied here rather than filtered afterwards, because
    a ruling the feed cannot see is a card the reviewer answers twice.
    """
    store = store or ProvenanceStore()
    if rows is None:
        rows = survey([layer], store)
    rows = [r for r in rows if r.layer == layer.layer]
    if not rows:
        return []

    quoted_docs = set(_cited_lines(layer))
    held = _held(layer)
    by_layer = lots if lots is not None else _lots_by_layer()
    extra = overrides or {}

    grouped: dict[tuple[str, str], list[Uncited]] = defaultdict(list)
    for row in rows:
        grouped[(row.path, row.section)].append(row)

    out: list[Card] = []
    for (path, section), group in grouped.items():
        group = sorted(group, key=lambda r: r.line)
        name = card_key(path, section)
        out.append(
            Card(
                layer=layer.layer,
                path=path,
                section=section,
                kind=_kind(group, path in quoted_docs),
                ruling=extra.get(name) or layer.readings.get(name),
                lines=tuple(
                    Line(
                        line=r.line,
                        field=r.field,
                        text=r.text,
                        repeats=r.repeats,
                        numbers=_numbers(r.text),
                        held=tuple(sorted(held.get(r.field, ()))),
                    )
                    for r in group
                ),
                lots=by_layer.get(layer.layer, 0),
            )
        )
    out.sort(key=_rank)
    return out


def _rank(card: Card) -> tuple[object, ...]:
    """Disagreements first, then consequence, then a stable name.

    The single biggest lever on this queue. A card where the code prints a
    figure we hold a different one for is a finding; a card where they match is
    bookkeeping, and there are far more of the second. Ranking by lots alone
    would bury every finding under Portland.
    """
    return (
        -card.disagrees,
        -card.unmeasured,
        -card.lots,
        card.path,
        card.section,
    )


def feed(
    kind: str,
    layers: Mapping[str, Layer] | None = None,
    store: ProvenanceStore | None = None,
    rows: Sequence[Uncited] | None = None,
    layer: str | None = None,
    field: str | None = None,
    off: Iterable[str] = (),
    include_off: bool = False,
    ruled: bool = False,
    overrides: Mapping[str, Mapping[str, Reading]] | None = None,
) -> list[Card]:
    """One queue, across every jurisdiction, ranked.

    Jurisdictions the screen does not cover are dropped by default. A filter,
    not a ruling: those lines are real and unread, they are simply not review
    work while nobody scores those lots. Left in, they take the top of this
    queue — Lake Oswego's dimensional chapter is the largest single block of
    disagreements in the corpus and none of its lots is ever scored.

    Cards already ruled are hidden unless ``ruled`` asks for them. A card whose
    section has moved since the ruling was written is not "already ruled" and
    comes back regardless: the decision was about words nobody has seen since.
    """
    if kind not in KINDS:
        raise ValueError(f"unknown queue {kind!r}; one of {', '.join(KINDS)}")
    chosen = layers if layers is not None else load_rules()
    store = store or ProvenanceStore()
    if rows is None:
        rows = ledger(chosen, store)
    skip = set(off)
    lots = _lots_by_layer()

    out: list[Card] = []
    for layer_id, obj in chosen.items():
        if layer_id in skip or (layer is not None and layer_id != layer):
            continue
        if not include_off and not obj.eligible and layer_id != layer:
            continue
        here = (overrides or {}).get(layer_id)
        for card in cards(obj, store, rows=rows, lots=lots, overrides=here):
            if card.kind != kind:
                continue
            if field is not None and field not in card.fields:
                continue
            if not ruled and not card.open:
                continue
            out.append(card)
    out.sort(key=_rank)
    return out


def counts(
    layers: Mapping[str, Layer] | None = None,
    store: ProvenanceStore | None = None,
    rows: Sequence[Uncited] | None = None,
) -> dict[str, tuple[int, int]]:
    """Cards and lines behind each queue — what the landing page shows."""
    chosen = layers if layers is not None else load_rules()
    store = store or ProvenanceStore()
    if rows is None:
        rows = ledger(chosen, store)
    lots = _lots_by_layer()

    out: dict[str, list[int]] = {k: [0, 0] for k in KINDS}
    for obj in chosen.values():
        for card in cards(obj, store, rows=rows, lots=lots):
            out[card.kind][0] += 1
            out[card.kind][1] += len(card.lines)
    return {k: (v[0], v[1]) for k, v in out.items()}



@dataclass(frozen=True, slots=True)
class Audit:
    """Whether the queue is still asking questions worth asking.

    A queue that outlives its reasons is worse than no queue: it spends the
    reviewer's attention on things that answered themselves. Three ways that
    happens, and each is a line in this report.
    """

    #: Rulings whose section has no uncited lines left. Somebody encoded the
    #: value, the line stopped being uncited, and the ruling is now about
    #: nothing. Harmless, and worth knowing before reading a stale note.
    settled: tuple[str, ...] = ()
    #: Cards ruled against text that has since moved. These are back in the
    #: queue already; the count is how much re-reading a re-fetch just bought.
    moved: tuple[str, ...] = ()
    #: Open cards per queue, after everything above.
    open_by_queue: tuple[tuple[str, int], ...] = ()

    @property
    def clean(self) -> bool:
        return not self.settled and not self.moved


def audit(
    layers: Mapping[str, Layer] | None = None,
    store: ProvenanceStore | None = None,
    rows: Sequence[Uncited] | None = None,
) -> Audit:
    """Ask the queue whether it would still ask what it is asking.

    Run before working it, not after. The check is cheap and the alternative
    is a morning spent on a chapter somebody finished last week.
    """
    chosen = layers if layers is not None else load_rules()
    store = store or ProvenanceStore()
    if rows is None:
        rows = ledger(chosen, store)

    settled: list[str] = []
    moved: list[str] = []
    open_counts: dict[str, int] = {k: 0 for k in KINDS}

    for layer_id, obj in chosen.items():
        made = cards(obj, store, rows=rows)
        here = {c.card_key: c for c in made}
        for name in obj.readings:
            if name not in here:
                # A ruling with no card behind it. The section still exists in
                # the code; what has gone is the *reason to ask*, because
                # every measured line in it is now quoted by something.
                settled.append(f"{layer_id}  {name}")
        for card in made:
            if card.moved:
                moved.append(f"{layer_id}  {card.card_key}")
            if card.open:
                open_counts[card.kind] += 1

    return Audit(
        settled=tuple(sorted(settled)),
        moved=tuple(sorted(moved)),
        open_by_queue=tuple((k, open_counts[k]) for k in KINDS),
    )


def render(rows: Sequence[Card], *, limit: int = 20) -> str:
    """The queue, for a terminal. The screen is the real surface."""
    if not rows:
        return "nothing in this queue"
    out: list[str] = []
    for card in rows[:limit]:
        head = f"{card.layer}  §{card.section or '-'}  {card.doc}"
        if card.disagrees:
            head += f"   [{card.disagrees} disagree]"
        out.append(head)
        for ln in card.lines[:4]:
            mark = {True: "  =", False: "  !", None: "  ?"}[ln.agrees]
            held = f"  we hold {ln.shown_held}" if ln.held else ""
            out.append(f"  {mark} {ln.line:>5}  {ln.text[:88]}{held}")
        if len(card.lines) > 4:
            out.append(f"        ... and {len(card.lines) - 4} more line(s)")
        out.append("")
    if len(rows) > limit:
        out.append(f"... and {len(rows) - limit} more card(s)")
    return "\n".join(out)


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):  # pragma: no cover
        sys.stdout.reconfigure(errors="replace")
    args = list(sys.argv[1:] if argv is None else argv)

    def opt(name: str) -> str | None:
        if name in args:
            i = args.index(name)
            return args[i + 1] if i + 1 < len(args) else None
        return None

    layers = load_rules()
    store = ProvenanceStore()
    ledger = survey(list(layers.values()), store)

    if "--audit" in args:
        report = audit(layers, store, rows=ledger)
        if report.clean:
            print("every open card is still asking something the corpus has not answered")
        for name in report.settled:
            print(f"SETTLED  {name}  — the lines it ruled on are all quoted now")
        for name in report.moved:
            print(f"MOVED    {name}  — ruled against text that has since changed")
        print()
        for kind, n in report.open_by_queue:
            print(f"{kind:12s} {n:5d} open")
        return 0

    if "--counts" in args or not [a for a in args if not a.startswith("--")]:
        tally = counts(layers, store, rows=ledger)
        total = sum(c for c, _ in tally.values())
        print(f"{'queue':12s} {'cards':>7s} {'lines':>7s}   the question")
        for kind in KINDS:
            cards_n, lines_n = tally[kind]
            print(f"{kind:12s} {cards_n:7d} {lines_n:7d}   {QUEUES[kind][1]}")
        print(f"{'TOTAL':12s} {total:7d} {len(ledger):7d}")
        return 0

    kind = next(a for a in args if not a.startswith("--"))
    rows = feed(
        kind,
        layers,
        store,
        rows=ledger,
        layer=opt("--layer"),
        field=opt("--field"),
        include_off="--include-off" in args,
    )
    title, question = QUEUES[kind]
    lines = sum(len(c.lines) for c in rows)
    print(f"{title}. {len(rows)} to check, {lines} line(s) behind them.")
    print(f"  {question}")
    print()
    print(render(rows))
    return 0



# --- writing a decision back into the rule files ----------------------------

#: Where the ``readings`` block goes when a file has none: beside the other
#: layer-wide bookkeeping rather than after two thousand lines of zones.
_AFTER = ("zones:", "defaults:", "code:", "definitions:", "crossrefs:")

NEWLINE = chr(10)


def card_key(path: str, section: str) -> str:
    """How a section is named in the rule files: ``<document>#<section>``.

    The document without its layer prefix, because the file it is written in
    already says which layer this is, and a key repeating it would be a second
    place for the two to disagree.
    """
    return f"{path.rsplit('/', 1)[-1]}#{section}"


def _entry(key: str, queue: str, outcome: str, note: str, fingerprint: str) -> list[str]:
    body = [
        f'  "{key}":',
        f"    queue: {queue}",
        f"    outcome: {outcome}",
        "    note: >-",
        *_wrap(" ".join(note.split())),
    ]
    if fingerprint:
        body.append(f"    fingerprint: {fingerprint}")
    return body


def _entry_key(line: str) -> str:
    """The card a ``readings`` entry line names, or empty.

    Entries sit at one indent under the block; anything deeper belongs to the
    entry above it.
    """
    if not line.startswith("  ") or line.startswith("   "):
        return ""
    head = line.strip().split(":", 1)[0].strip()
    return head.strip('"').strip("'")


def _splice(
    lines: list[str], key: str, queue: str, outcome: str, note: str, fingerprint: str
) -> list[str]:
    """Put one ruling into the file's lines, replacing any already there."""
    entry = _entry(key, queue, outcome, note, fingerprint)

    start = next((i for i, ln in enumerate(lines) if ln.rstrip() == "readings:"), None)
    if start is None:
        at = next(
            (i for i, ln in enumerate(lines) if any(ln.startswith(k) for k in _AFTER)),
            len(lines),
        )
        return lines[:at] + ["readings:", *entry, ""] + lines[at:]

    stop = start + 1
    while stop < len(lines) and (
        not lines[stop].strip() or lines[stop].startswith((" ", "\t", "#"))
    ):
        stop += 1

    body = lines[start + 1 : stop]
    here = next((i for i, ln in enumerate(body) if _entry_key(ln) == key), None)
    if here is None:
        body = body + entry
    else:
        end = here + 1
        while end < len(body) and (not body[end].strip() or body[end].startswith("    ")):
            end += 1
        body = body[:here] + entry + body[end:]

    return lines[: start + 1] + body + lines[stop:]


def rule(
    layer_id: str,
    key: str,
    queue: str,
    outcome: str,
    note: str,
    fingerprint: str = "",
) -> Path:
    """Record one reading decision in the jurisdiction file, or raise.

    Raises rather than writing a file the loader will reject: the loader
    accumulates problems across the whole corpus and refuses the set, so one
    bad splice takes every jurisdiction down with it. The file is written,
    re-read, and rolled back if the ruling did not take.
    """
    if queue not in READING_OUTCOMES:
        raise ValueError(
            f"unknown queue {queue!r}; one of {', '.join(sorted(READING_OUTCOMES))}"
        )
    if outcome not in READING_OUTCOMES[queue]:
        raise ValueError(
            f"{outcome!r} is not an answer the {queue} queue asks for; one of "
            f"{', '.join(sorted(READING_OUTCOMES[queue]))}"
        )
    note = " ".join(note.split())
    if len(note) < MIN_RULING:
        raise ValueError(
            f"a ruling needs at least {MIN_RULING} characters of reasoning; "
            f"got {len(note)}"
        )

    path = layer_path(layer_id)
    if not path.exists():
        raise FileNotFoundError(path)

    before = path.read_text(encoding="utf-8")
    spliced = _splice(before.splitlines(), key, queue, outcome, note, fingerprint)
    path.write_text(NEWLINE.join(spliced) + NEWLINE, encoding="utf-8")
    try:
        load_rules.cache_clear()  # type: ignore[attr-defined]
    except AttributeError:
        pass
    try:
        got = load_rules()[layer_id].readings.get(key)
        if got is None or got.outcome != outcome:
            raise ValueError(f"ruling did not take on {layer_id} {key}")
    except Exception:
        path.write_text(before, encoding="utf-8")
        try:
            load_rules.cache_clear()  # type: ignore[attr-defined]
        except AttributeError:
            pass
        raise
    return path


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
