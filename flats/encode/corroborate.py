"""Checking an encoded rule file against the words it says it came from.

Encoding produced numbers; nothing so far has asked whether the source still
says them. That question has to be asked before a reviewer signs, because the
expensive failure is not a value a reviewer rejects — it is a value that reads
plausibly, matches the neighbouring zones, and was never in the code at all.

So this reads the stored document again, per zone, and sorts every encoded
value into one of four buckets::

    agrees       the document states this number for this zone
    differs      the document states a different number
    unsupported  nothing in the document was read as this field
    unencoded    the document states a number the file does not carry

Only ``differs`` is a stop-and-read. ``unsupported`` is the normal case for a
standard the readers cannot parse — a coverage curve, a use table, a rule
stated three sections away — and treating it as failure would drown the real
signal. ``unencoded`` is the opposite of the usual worry: a standard the code
states and the screen currently ignores.

What this deliberately does not do is promote anything. Agreement between two
machines is still nobody having read the sentence, and trust in this system
comes only from a signature over the words (see :mod:`flats.encode.verify`).
Corroboration orders the review queue; it does not shorten it.
"""

from __future__ import annotations

import argparse
import enum
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from flats.encode.extract import extract, states_a_rule
from flats.provenance.store import ProvenanceError, ProvenanceStore
from flats.rules.fields import FIELDS
from flats.rules.loader import CONFIG_ROOT, load_rules
from flats.rules.model import Layer, Value

#: Kinds a reader can state as one number. A curve, a boolean and an enum are
#: real standards this cannot check, and saying so is better than a verdict.
CHECKABLE = frozenset({"length_ft", "area_sqft", "ratio", "percent", "count"})


class Verdict(str, enum.Enum):
    agrees = "agrees"
    differs = "differs"
    unsupported = "unsupported"
    unencoded = "unencoded"

    @property
    def blocking(self) -> bool:
        """Whether this verdict has to be resolved before anyone signs."""
        return self is Verdict.differs


@dataclass(frozen=True, slots=True)
class Finding:
    """One field, in one zone, and what the document said about it."""

    layer: str
    zone: str
    field: str
    verdict: Verdict
    encoded: float | int | None = None
    found: tuple[float | int, ...] = ()
    quote: str = ""
    #: Footnotes qualifying what the document states. A number with one of
    #: these is a base case with an exit, not a standard.
    notes: tuple[str, ...] = ()

    @property
    def conditional(self) -> bool:
        return bool(self.notes)

    def __str__(self) -> str:
        found = ", ".join(str(v) for v in self.found) or "-"
        mark = "  [conditional]" if self.conditional else ""
        return (
            f"{self.verdict.value:11} {self.zone:6} {self.field:28} "
            f"file={self.encoded if self.encoded is not None else '-':>8} "
            f"doc={found:>8}  {self.quote}{mark}"
        )


def _scalar(value: Value) -> float | int | None:
    raw = value.value
    return raw if isinstance(raw, (int, float)) and not isinstance(raw, bool) else None


def checkable(name: str, value: Value) -> bool:
    """Whether corroboration can say anything about this value at all.

    A boolean, an enum and a curve are real standards that this reader cannot
    state as one number, so it emits no finding for them. Silence there means
    "not read", never "not stated", and anything counting evidence has to know
    the difference — otherwise ``quadplex_allowed`` reads as a value no
    document supports, when no document was ever consulted about it.
    """
    field = FIELDS.get(name)
    return field is not None and field.kind in CHECKABLE and _scalar(value) is not None


def check_zone(
    text: str,
    *,
    layer: str,
    zone: str,
    values: dict[str, Value],
    path: str,
    zoned: bool = False,
    sections: Sequence[str] = (),
    spaced: bool = False,
) -> list[Finding]:
    """Compare one zone's encoded values against the document.

    Only readings written for this zone count as evidence. A table cell is one
    — the column says whose standard it is. A sentence in a fifty-page chapter
    is not: the prose reader has no idea which zone "the maximum height is 20
    feet" belongs to, and letting it contradict an encoded value produces a
    page of disagreements that are all the reader's fault. A report like that
    gets skimmed, and the one real disagreement in it goes by unread.

    ``zoned`` says the document covers exactly one zone — a per-zone slice —
    in which case its sentences are about this zone and do count.

    ``sections`` is the third way a sentence can be zone-keyed, and the one most
    of Oregon needs: a code that states standards in prose under "Section 4.122.
    Residential Zone" binds those paragraphs to a zone by the heading above
    them. The section numbers are declared on the zone (`section:` in the rule
    file) rather than guessed from heading text, because guessing which heading
    means which zone attributes one zone's setback to another — silently, and in
    the direction that turns lots red.
    """
    read = extract(text, path=path, jurisdiction=layer, zone=zone, spaced=spaced)
    wanted = tuple(str(s).strip() for s in sections if str(s).strip())
    by_field: dict[str, list] = {}
    for candidate in read.candidates:
        in_section = bool(candidate.section) and any(
            candidate.section.startswith(prefix) for prefix in wanted
        )
        if candidate.source == "table" or zoned or in_section:
            by_field.setdefault(candidate.field, []).append(candidate)
    for name, candidates in by_field.items():
        # Evidence has a hierarchy. A table cell was *written for* this zone;
        # a stacked pair is a cell that lost its geometry, one rung below;
        # a sentence under the declared section is merely near either. When
        # more than one speaks to a field the highest rung wins outright —
        # Troutdale's declared 3.130 also contains a density/lot-size grid
        # whose every number the prose reader files under lot size, and
        # Gladstone's cottage-cluster sentences would otherwise outvote the
        # base-zone row they are the exception to.
        for rung in ("table", "typed-table", "pair"):
            best = [c for c in candidates if c.source == rung]
            if best:
                by_field[name] = best
                break
    by_field = {
        name: kept
        for name, cands in by_field.items()
        if (kept := _select_housing(cands, name))
    }

    out: list[Finding] = []
    for name, value in sorted(values.items()):
        if name not in FIELDS or FIELDS[name].kind not in CHECKABLE:
            continue
        encoded = _scalar(value)
        if encoded is None:
            continue
        candidates = by_field.get(name, [])
        numbers = tuple(sorted({c.value for c in candidates}))
        if not candidates:
            out.append(Finding(layer, zone, name, Verdict.unsupported, encoded))
            continue
        agrees = any(float(c.value) == float(encoded) for c in candidates)
        if not agrees and not any(_authoritative(c) for c in candidates):
            # Every number here comes from conditional or unclear prose — a
            # scoped variant, an adjustment, a criterion. That text can
            # corroborate a value it happens to state; it cannot contradict
            # one, because none of its numbers is the base standard. The
            # numbers still print, so a reader can see what was dismissed.
            out.append(
                Finding(
                    layer,
                    zone,
                    name,
                    Verdict.unsupported,
                    encoded,
                    numbers,
                    candidates[0].quote,
                    _notes(candidates),
                )
            )
            continue
        match = next((c for c in candidates if float(c.value) == float(encoded)), candidates[0])
        out.append(
            Finding(
                layer,
                zone,
                name,
                Verdict.agrees if agrees else Verdict.differs,
                encoded,
                numbers,
                match.quote,
                _notes(candidates),
            )
        )

    for name, candidates in sorted(by_field.items()):
        if name in values or name not in FIELDS or FIELDS[name].kind not in CHECKABLE:
            continue
        if not any(_authoritative(c) for c in candidates):
            # An unencoded row is an invitation to encode. Conditional-only
            # numbers would invite encoding a scoped variant as the base
            # standard — the exact mistake the notes mechanism exists to stop.
            continue
        numbers = tuple(sorted({c.value for c in candidates}))
        out.append(
            Finding(
                layer,
                zone,
                name,
                Verdict.unencoded,
                None,
                numbers,
                candidates[0].quote,
                _notes(candidates),
            )
        )
    return out


#: The use classifications a 4-unit attached townhome pod can be permitted
#: under. Both are real and jurisdiction-dependent: Gresham's quadfit-era
#: values model the pod as a quadplex on one lot, while Troutdale's table
#: family files the same building under "Townhouse dwellings". Selection
#: keeps every row either classification claims; when the two paths state
#: different numbers, both survive, the field reads as multi-value, and
#: attach refuses — the plat-path choice is a decision, not a coin flip.
#: "Middle housing" is the third: ORS 197.758's class name, which contains
#: the quadplex by statute, so a standard written for it is written for the
#: pod whichever plat path the pod takes.
#: "Attached" is the fourth: Lake Oswego states one block of setbacks for
#: "Primary Dwelling (Attached)" and another for "(Detached)", and never names
#: a quadplex in either. Four dwellings sharing three walls are attached on any
#: reading of that word, so the attached block is the pod's block — and the
#: detached one, which states different numbers, is provably not.
_POD_TYPES = frozenset({"quadplex", "townhouse", "all", "middle_housing", "attached"})

#: Fields measured on the lot the pod occupies. A townhouse is by definition
#: a dwelling on its own lot, so a townhouse-typed number for one of these —
#: "For townhouses the minimum lot size is 1,500 square feet" — describes the
#: individual unit lot after platting, not the parcel the screen is judging.
#: The registry names min_lot_sqft "minimum lot area for a fourplex": the
#: fourplex path is the one-lot path the screen models, and a per-unit-lot
#: number is another denominator, not pod evidence. Setbacks, height, and
#: coverage bind the building the same either way and are unaffected.
_UNIT_LOT_FIELDS = frozenset({"min_lot_sqft", "min_lot_width_ft", "min_frontage_ft"})


def _select_housing(candidates: Sequence, field: str = "") -> list:
    """The candidates that speak for the pod when a table stratifies by type.

    Untyped candidates pass through untouched — most tables state one number
    per zone and this function is not about them. A typed candidate survives
    when its types intersect the pod's. "All other uses" is the subtle one:
    quadplexes are usually in it *implicitly*, so it speaks for the pod —
    until some row of the same field names the pod's own class, at which
    point "other" provably excludes it and the row falls silent. Gladstone
    prints middle housing at 3,600 sq ft and other uses at 7,200: read
    together they are two numbers for one field, and only one of them was
    written about a quadplex. A row naming only other types (a duplex's lot
    width) never counts: it is not evidence for or against the pod's
    standard, and letting it corroborate one turns the check into a
    coincidence detector.
    """
    # "Attached" goes the same way as a townhouse on a lot-size field, and for
    # the same reason: West Linn states 5,000 sq ft for a single-family
    # detached unit and 4,500 for an attached one, and the attached number is
    # the lot a single unit sits on once the project is platted — not the
    # parcel a four-unit building is being screened against. On setbacks,
    # height and coverage it stays the pod's: those bind the building.
    unit_lot = {"townhouse", "attached"}
    pod_types = _POD_TYPES - unit_lot if field in _UNIT_LOT_FIELDS else _POD_TYPES
    typed = [c for c in candidates if getattr(c, "housing_type", "")]
    if not typed:
        return list(candidates)
    named = pod_types - {"all"}
    explicit_pod = any(set(c.housing_type.split("+")) & named for c in typed)
    kept = []
    for c in typed:
        types = set(c.housing_type.split("+"))
        if types & pod_types:
            kept.append(c)
        elif "default" in types and not explicit_pod:
            kept.append(c)
    return kept + [c for c in candidates if not getattr(c, "housing_type", "")]


def _authoritative(candidate) -> bool:
    """Whether this reading may contradict an encoded value.

    A table cell or a stacked pair was written for the zone — structure keys
    it. A sentence earns the same standing only by stating a base standard
    (:func:`states_a_rule`): conditional prose corroborates, never contradicts.

    A banded cell is written for the zone and for one range of lot sizes, and
    the encoded value it is being compared against is written for neither. It
    can show that the file picked one column of four; it cannot show the file
    is wrong, because there is no single number it could be wrong about.
    """
    if getattr(candidate, "band", ""):
        return False
    return candidate.source in ("table", "typed-table", "pair") or states_a_rule(
        candidate.text
    )


def _notes(candidates: Sequence) -> tuple[str, ...]:
    """What qualifies these numbers — footnotes, and the lot bands they sit in.

    A band belongs here for the same reason a footnote does: it is the reason
    the number beside it is not the zone's standard, and the reason nothing
    may quote it against an unconditional value. It prints as the token that
    addresses the variant, so the note doubles as the fix.
    """
    seen: list[str] = []
    for candidate in candidates:
        marks = list(candidate.notes)
        band = getattr(candidate, "band", "")
        if band:
            marks.append(f"lot band {band}")
        for note in marks:
            if note not in seen:
                seen.append(note)
    return tuple(seen)


def check_layer(
    text: str,
    layer: Layer,
    *,
    path: str,
    zones: Sequence[str] = (),
    zoned: bool = False,
) -> list[Finding]:
    """Compare every zone of one jurisdiction against one document.

    Whether the document's text needs repairing before anything reads it is
    the layer's own declaration — ``spaced: true`` on the ``code:`` entry —
    found here by matching the stored path back to the entry that fetched it.
    """
    wanted = set(zones) if zones else set(layer.zones)
    stem = path.rsplit("/", 1)[-1].removesuffix(".txt")
    spaced = any(doc.id == stem and doc.spaced for doc in layer.code)
    out: list[Finding] = []
    unread = layer.unread()
    for code, zone in sorted(layer.zones.items()):
        if code in wanted:
            # Read what the zone holds and what it is missing in one pass. The
            # unread half is the half this search exists to close.
            values = dict(zone.values)
            values.update({f: v for (z, f), v in unread.items() if z == code})
            out.extend(
                check_zone(
                    text,
                    layer=layer.layer,
                    zone=code,
                    values=values,
                    path=path,
                    zoned=zoned,
                    sections=zone.section,
                    spaced=spaced,
                )
            )
    return out


def tally(findings: Iterable[Finding]) -> dict[str, int]:
    counts = {v.value: 0 for v in Verdict}
    for finding in findings:
        counts[finding.verdict.value] += 1
    return counts


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="flats-corroborate",
        description="Read a stored document back against an encoded rule file.",
    )
    parser.add_argument("layer", help="layer id, e.g. or/multnomah/portland")
    parser.add_argument("--doc", required=True, help="store path of the document to read")
    parser.add_argument("--zone", action="append", default=[], help="limit to these zones")
    parser.add_argument("--rules", type=Path, default=CONFIG_ROOT)
    parser.add_argument("--docs", type=Path, default=None, help="provenance store root")
    parser.add_argument(
        "--zoned-doc",
        action="store_true",
        help="the document covers exactly one zone, so its sentences count as "
        "evidence for it — without this only tables do",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="print only differences — the findings that block a signature",
    )
    args = parser.parse_args(argv)

    layers = load_rules(args.rules, strict=False)
    layer = layers.get(args.layer)
    if layer is None:
        print(f"no such layer: {args.layer}", file=sys.stderr)
        return 2
    try:
        doc = ProvenanceStore(args.docs).load(args.doc)
    except (ProvenanceError, FileNotFoundError) as exc:
        print(f"{args.doc}: {exc}", file=sys.stderr)
        return 2

    findings = check_layer(
        doc.text, layer, path=args.doc, zones=args.zone, zoned=args.zoned_doc
    )
    for finding in findings:
        if args.quiet and finding.verdict is not Verdict.differs:
            continue
        print(f"  {finding}")

    counts = tally(findings)
    print(
        f"{args.layer} against {args.doc}: "
        + ", ".join(f"{n} {name}" for name, n in counts.items() if n)
    )
    if counts[Verdict.differs.value]:
        # A file and its source disagreeing is the one outcome nobody should
        # be able to walk past, so it is the only one that fails the command.
        print(
            f"  {counts[Verdict.differs.value]} value(s) disagree with the document — "
            f"read them before signing anything in this layer",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
