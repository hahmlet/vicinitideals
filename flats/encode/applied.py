"""Whether a footnote we said we encoded actually became the rule it claims.

The footnote subsystem runs in one direction. :mod:`flats.encode.footnotes`
captures every note in the store, :mod:`flats.encode.dispositions` records what
was decided about each, and :mod:`flats.encode.qualified` joins them to the
encoding *from the value's side*: for each number we hold, which notes govern
the lines it was read from, and has anybody ruled on them. That direction is
closed -- 1,792 qualified values, nothing blocking.

Nothing runs the other way. A note ruled ``encoded`` carries ``encoded_as``,
and the register's docstring says the point of it out loud: it "carries the
zone and field it became, so the claim is checkable against the encoding
rather than taken on trust." The loader enforces that the sentence is not
empty. It has never checked that the sentence is true. Forty-five footnotes
say they became a rule and the rule has never been looked for.

That asymmetry fails in exactly one direction and it is the unsafe one. A
value losing its footnote shows up here as a note whose rule is gone; a value
that never had one shows up in ``qualified`` as unread and blocks. So the
missing check is the one that catches a variant deleted, renamed, or moved
between zones after somebody closed the note over it -- and variants do get
deleted. The 2026-09-07 second reading removed four party-wall zeros from
Gresham's downtown zones on the strength of GDC 3.0100's own definition. If a
disposition had claimed one of those, nothing would have noticed.

What a claim is checked against
-------------------------------

``encoded_as`` is prose, written by whoever ruled the note, and it is left as
prose on purpose: a schema would have to be imposed retroactively on
forty-five rulings, and re-ruling a footnote is a human act this module does
not get to perform. So it reads what is mechanically readable out of the
sentence -- field names in the registry, conditions in the registry, zone
codes the layer has, and figures -- and checks each against the layer.

Three findings, and the middle one is the reason this is not a boolean:

``confirmed``
    Every readable claim was found, in a zone the note governs.
``elsewhere``
    Found in the layer, but not under this note's own region. Usually a note
    that reaches further than the block it sits under, sometimes a claim
    pointed at the wrong zone. Worth a look; not a defect on its face.
``broken``
    A claim names a field, condition or figure the layer does not have. This
    is the one that means something changed underneath a closed decision.

A sentence naming nothing checkable is ``unreadable`` and counted separately,
because a claim nobody can check is not the same as a claim that failed and
collapsing them would let the register grade itself.

Run it::

    uv run python -m flats.encode.applied
    uv run python -m flats.encode.applied --layer or/multnomah/gresham
    uv run python -m flats.encode.applied --broken
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from typing import Iterable, Sequence

from flats.encode.dispositions import Note, notes
from flats.encode.qualified import qualified
from flats.rules.conditions import CONDITIONS
from flats.rules.fields import FIELDS
from flats.rules.loader import load_rules
from flats.rules.model import LIKE, Layer

#: A figure as a code prints it -- "1,500", "7.5", "20". Trailing units are
#: dropped by the tokeniser, not here, because "20 ft" and "20 percent" are
#: the same claim about the same number.
_NUM = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)(?![\w.])")

#: Words that read as a field or condition name but are the sentence's own
#: grammar. "variant", "variants" and "when" appear in almost every ruling.
_NOISE = frozenset({"variant", "variants", "when", "with", "and", "or", "at", "in", "on"})

#: Figures that are almost never a standard and often a section number or a
#: count of things. A claim resting only on one of these is not checkable.
_WEAK_NUMBERS = frozenset({0.0, 1.0, 2.0, 3.0, 4.0})


@dataclass(frozen=True, slots=True)
class Claim:
    """One readable assertion pulled out of an ``encoded_as`` sentence."""

    kind: str  # "field" | "condition" | "number" | "exempt"
    token: str
    found: str = ""  # where it was found: "<zone>.<field>", or ""
    governed: bool = False

    @property
    def state(self) -> str:
        if not self.found:
            return "broken"
        return "confirmed" if self.governed else "elsewhere"


@dataclass(frozen=True, slots=True)
class Applied:
    """One ``encoded`` footnote and what became of the rule it claims."""

    note: Note
    zones_named: tuple[str, ...]
    claims: tuple[Claim, ...] = ()
    #: Zones this note governs a value in, whether or not the claim matched.
    reaches: tuple[str, ...] = ()

    @property
    def readable(self) -> bool:
        return bool(self.claims)

    @property
    def state(self) -> str:
        if not self.claims:
            return "unreadable"
        states = {claim.state for claim in self.claims}
        if "broken" in states:
            return "broken"
        if "elsewhere" in states:
            return "elsewhere"
        return "confirmed"

    @property
    def failures(self) -> tuple[Claim, ...]:
        return tuple(c for c in self.claims if c.state != "confirmed")

    @property
    def mark(self) -> str:
        """The note's citation, short enough to sit in a column."""
        return f"{self.note.doc.rsplit('/', 1)[-1]}#L{self.note.line}"


# --- what the layer actually holds ------------------------------------------


@dataclass(frozen=True, slots=True)
class Held:
    """One number in the encoding, flattened so a claim can be matched to it."""

    zone: str
    field: str
    when: frozenset[str]
    number: float | None
    exempt: bool


#: Every attribute of a value or a variant that carries a figure. The derived
#: forms are here for one reason: they hold what the *sentence* says where
#: ``value`` holds what the field means, and a ruling quotes the sentence. A
#: check that read ``value`` alone would call "1,500 sq ft per unit" broken
#: against a value of 6,000 -- the figure is there, in ``per_dwelling``.
_FIGURES = (
    "value",
    "per_dwelling",
    "sqft_per_unit",
    "per_units",
    "spaces_total",
    "acres",
    "acres_per_dwelling",
    "per_height_ft",
    "floor_ft",
    "reduce_pct",
    "before_step_back",
)

#: A band's bounds are figures a ruling quotes constantly -- "exempt below
#: 11,000 sq ft", "banded over 10,000". They are not the standard's number and
#: they are the number in the sentence, so they count.
_BOUNDS = ("at_least", "at_most", "more_than", "less_than")


def _numbers_of(value) -> Iterable[float]:
    """Every figure a value states, direct, derived, or bounding a band."""
    for attr in _FIGURES:
        raw = getattr(value, attr, None)
        if isinstance(raw, bool) or raw is None:
            continue
        if isinstance(raw, (int, float)):
            yield float(raw)
    band = getattr(value, "band", None)
    if band is not None:
        for attr in _BOUNDS:
            raw = getattr(band, attr, None)
            if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                yield float(raw)


def _held(layer: Layer) -> list[Held]:
    """Every number in a layer, base values and variants alike."""
    out: list[Held] = []

    def add(zone: str, name: str, value, when: frozenset[str]) -> None:
        nums = list(_numbers_of(value)) or [None]
        for num in nums:
            out.append(
                Held(
                    zone=zone,
                    field=name,
                    when=when,
                    number=num,
                    exempt=bool(getattr(value, "exempt", False)),
                )
            )

    for name, value in layer.defaults.items():
        add("(defaults)", name, value, frozenset())
        for variant in value.variants:
            add("(defaults)", name, variant, frozenset(variant.when))
    for zone_code, zone in layer.zones.items():
        for name, value in zone.values.items():
            add(zone_code, name, value, frozenset())
            for variant in value.variants:
                add(zone_code, name, variant, frozenset(variant.when))
        if zone.like is not None:
            add(zone_code, LIKE, zone.like, frozenset())
    return out


# --- reading a claim out of the prose ---------------------------------------


def _tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z_][A-Za-z0-9_.-]*", text)


def _mask(text: str, zones: Sequence[str]) -> str:
    """The sentence with everything that is a name, not a figure, taken out.

    Zone codes are the reason this exists. "MDR-24", "R-7.5" and "LR 12" all
    read as figures to any digit-matcher, and the first run of this module
    reported eleven broken claims of which every single one was a zone code or
    a table number being checked as though it were a standard. A number check
    that cannot tell 24 in "MDR-24" from 24 in "24 ft" is not a check.
    """
    for code in sorted(zones, key=len, reverse=True):
        text = re.sub(rf"(?<![\w-]){re.escape(code)}(?![\w-])", " ", text)
    text = re.sub(r"\b(?:Table|Figure|Sec(?:tion|\.)?|§)\s*[\w.()-]+", " ", text, flags=re.I)
    return re.sub(r"\b\d+[-\u2013]\d+\b", " ", text)


def _zones_named(text: str, layer: Layer) -> tuple[str, ...]:
    """Zone codes the sentence names, longest first so R-2.1 beats R-2.

    A ruling that names its zones is narrowing the search on purpose, and
    honouring that is what keeps "NC min_landscaped_pct = 5" from matching
    the 5 in some other zone's side setback.
    """
    found: list[str] = []
    for code in sorted(layer.zones, key=len, reverse=True):
        if re.search(rf"(?<![\w-]){re.escape(code)}(?![\w-])", text):
            if not any(code in seen for seen in found):
                found.append(code)
    return tuple(found)


def _claims(note: Note, layer: Layer, held: Sequence[Held], reaches: set[str]) -> list[Claim]:
    """The readable assertions in one ruling, each resolved against the layer."""
    text = note.encoded_as
    zones_named = _zones_named(text, layer)
    scope = set(zones_named) if zones_named else None

    def governed(row: Held) -> bool:
        return row.zone in reaches or row.zone == "(defaults)"

    def rows(fields: set[str] | None = None) -> list[Held]:
        """Candidate rows, the ones this note governs first.

        Order is the whole of the ``elsewhere`` verdict. Resolving a claim to
        the first row that happens to match would grade a note by iteration
        order of the zone dict, so a note that *is* confirmed somewhere it
        governs would report ``elsewhere`` on a coincidence in another zone.
        """
        out = [
            row
            for row in held
            if (scope is None or row.zone in scope)
            and (fields is None or row.field in fields)
        ]
        out.sort(key=lambda row: not governed(row))
        return out

    out: list[Claim] = []
    seen: set[tuple[str, str]] = set()

    def record(kind: str, token: str, hit: Held | None) -> None:
        if (kind, token) in seen:
            return
        seen.add((kind, token))
        out.append(
            Claim(
                kind=kind,
                token=token,
                found=f"{hit.zone}.{hit.field}" if hit else "",
                governed=bool(hit and governed(hit)),
            )
        )

    words = [w for w in _tokens(text) if w not in _NOISE]
    named: set[str] = set()

    for word in words:
        if word in FIELDS:
            named.add(word)
            record("field", word, next((r for r in rows() if r.field == word), None))

    for word in words:
        if word in CONDITIONS:
            record("condition", word, next((r for r in rows() if word in r.when), None))

    if re.search(r"\bexempt\b", text, re.I):
        record("exempt", "exempt", next((r for r in rows() if r.exempt), None))

    # Figures are checked last, only where the sentence named a field, and
    # only against that field. A number checked against the whole layer is not
    # a check either way round: any 5 anywhere confirms "5 ft", and a band
    # bound reads as broken because no base value carries it.
    if named:
        candidates = rows(named)
        for raw in _NUM.findall(_mask(text, zones_named)):
            num = float(raw.replace(",", ""))
            if num in _WEAK_NUMBERS:
                continue
            record("number", raw, next((r for r in candidates if r.number == num), None))

    return out


# --- the ledger -------------------------------------------------------------


def applied(layer_id: str | None = None) -> list[Applied]:
    """Every footnote ruled ``encoded``, with its claim checked."""
    layers = load_rules()
    rows = qualified(layer_id)

    # note quote -> the zones that note governs a value in. The join is on
    # the note's own citation rather than its text, because two blocks in one
    # document can print the same sentence and they are different notes.
    reach: dict[str, set[str]] = {}
    for row in rows:
        for note in row.governing:
            reach.setdefault(note.quote, set()).add(row.zone)

    out: list[Applied] = []
    for note in notes(layer_id):
        if note.state != "encoded":
            continue
        layer = layers.get(note.ruled_in) or layers.get(note.layer)
        if layer is None:
            continue
        held = _held(layer)
        reaches = reach.get(note.quote, set())
        out.append(
            Applied(
                note=note,
                zones_named=_zones_named(note.encoded_as, layer),
                claims=tuple(_claims(note, layer, held, reaches)),
                reaches=tuple(sorted(reaches)),
            )
        )
    return out


def render(rows: Sequence[Applied], *, broken_only: bool = False) -> str:
    lines: list[str] = []
    for row in sorted(rows, key=lambda r: (r.note.layer, r.note.doc, r.note.line)):
        if broken_only and row.state == "confirmed":
            continue
        lines.append(f"{row.note.layer:<30} {row.mark:<22} {row.state}")
        for claim in row.claims:
            if claim.state == "confirmed":
                continue
            where = claim.found or "nothing in the layer"
            lines.append(f"{'':<30}   {claim.kind} {claim.token!r} -> {where}")
        if not row.claims:
            lines.append(f"{'':<30}   {row.note.encoded_as[:90]!r}")
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.state] = counts.get(row.state, 0) + 1
    lines.append("")
    lines.append(
        "encoded=%d  " % len(rows)
        + "  ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layer", default=None)
    parser.add_argument(
        "--broken",
        action="store_true",
        help="only the rulings whose claim no longer resolves",
    )
    args = parser.parse_args(argv)
    rows = applied(args.layer)
    print(render(rows, broken_only=args.broken))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
