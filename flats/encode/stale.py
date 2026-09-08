"""Find dismissals whose reason is a claim about *us*, and re-ask it.

A footnote dismissal has to carry a reason in writing, and most of them argue
about the code: this sentence is about a detached house, that one is a land
division procedure, this one loosens a standard we hold at its strict end.
Those arguments are as durable as the page they read.

Some of them argue about **our corpus** instead -- "a district this layer does
not encode", "neither of which is encoded here", "two districts this layer does
not hold". Those are just as legitimate on the day they are written and they
have a property the others do not: *somebody else can falsify them by doing
their job.* Encode the district and the sentence quietly becomes false, the
note stays dismissed, and nothing anywhere is watching.

That is not hypothetical. The blind re-read of 2026-09-07 found three live ones
and, in the register itself, a fourth that a person had already caught by hand::

    This used to be dismissed on the grounds that CC and MC were not encoded
    here, which stopped being true when both were encoded on 2026-08-21 and
    nobody came back to the sentence.

One note, found once, by reading. This module asks the same question of all 784
at once, and it is deliberately cheap: it does not judge whether the dismissal
was right. It asks only whether the reason still says something true about the
corpus it describes.

Three answers, and none of them is a verdict:

``contradicted``   the reason denies encoding and names a zone the layer holds
``repaired``       it says so itself -- somebody already came back to it
``unverifiable``   it denies encoding but names no zone this can check

All three are *reading queues*, and the sizes are the point. ``contradicted``
over-reports on purpose: a reason can name a live zone for a reason of its own
("120 feet from a lot zoned R-6" is a measurement, not a claim that R-6 is
missing), and a person can see that in a second. The opposite error cannot be
seen at all, because a stale reason looks exactly like a sound one. An
``unverifiable`` row is not a bug either. It is a claim written in a shape
nobody can re-ask, which is worth knowing about a claim that decays.

``repaired`` exists because the first run of this check flagged the one note
somebody had *already* fixed by hand -- its reason quotes the false claim in
order to record killing it, and a ledger that keeps asking about work already
done is how a queue stops being read.

**What actually decides whether a row matters is not on the reason at all.**
It is what the note stands over: a false claim about a district where we
already record that a fourplex is forbidden cannot make a lot green wrongly,
because the lot is red on use before any of this is reached. So each row
carries the zones behind it and how many of those permit the building, and the
report leads with the ones that can still bite -- 7 of the 10 contradicted, on
the run this was written for, with the other 3 a wrong sentence over a right
answer.

``bites`` is a screen and not a finding. Reading the 7 by hand the same day,
five turned out to give a *second* ground that survives on its own -- the note
is about cottage clusters, or it loosens a standard, or the pod is not the
building type it names -- and only the Happy Valley buffer at L1019 changes
what a lot must satisfy. That is the ratio to expect, and it is why the column
is called what it is.

Usage:
    uv run python -m flats.encode.stale [--csv out.csv]
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

from flats.encode.dispositions import Ruling, rulings
from flats.rules.loader import load_rules

#: Phrases that turn a reason into a claim about our own files. Kept literal
#: and short: a looser pattern picks up "the code does not state a setback",
#: which is a claim about Oregon and cannot go stale.
_CORPUS_CLAIM = re.compile(
    r"\b(?:"
    r"(?:this |the )?layer (?:does not|doesn't|never) (?:encode|hold|carry|have)"
    r"|(?:is|are|was|were|s)? ?not (?:encoded|held|carried) (?:here|in this layer|by this layer)"
    r"|(?:neither|none) of (?:which|them) (?:is|are) encoded"
    r"|not (?:a|one of the) (?:district|zone)s? (?:this|the) layer"
    r"|(?:we|nobody|nothing) (?:do|does|did) not encode"
    r"|no (?:commercial |residential |industrial )?(?:zone|district)s? (?:is|are) encoded"
    r")",
    re.IGNORECASE,
)

#: A reason that names its own staleness in order to record fixing it. Closed
#: and small on purpose: this is the one place the check is allowed to believe
#: what a reason says about itself, so the vocabulary has to be things nobody
#: writes by accident.
_REPAIRED = re.compile(
    r"\b(?:"
    r"stopped being true"
    r"|no longer (?:true|the case|holds)"
    r"|used to be (?:dismissed|declined|waved)"
    r"|was true (?:when|until)"
    r"|(?:which|that) (?:has since|since) (?:changed|been encoded)"
    r")",
    re.IGNORECASE,
)

#: A zone code as it appears inside prose. Zone names carry '-' and '.', so the
#: usual ``\b`` is not enough on its own -- "R-5" must not match inside "R-50",
#: and the trailing class is what keeps ``NC`` out of "NC-SW".
#:
#: The parenthesis at the end is the other half of the same problem and cost a
#: false reading before it was added: Troutdale prints a Town Center column as
#: "MDR (TC)", which is not the MDR this layer holds, and four reasons that say
#: so correctly were being called contradicted for saying it.
_EDGE = r"(?<![A-Za-z0-9_.\-/])%s(?![A-Za-z0-9_.\-/]|\s*\()"


@dataclass(frozen=True, slots=True)
class Stale:
    layer: str
    quote: str
    reason: str
    #: Zones the reason denies encoding that the layer holds today.
    contradicted: tuple[str, ...]
    #: Every zone the note stands over, and the subset of those in which we
    #: record that a fourplex may be built at all.
    over: tuple[str, ...] = ()
    permitting: tuple[str, ...] = ()
    #: The reason says, in its own words, that somebody came back to it.
    repaired: bool = False

    @property
    def verdict(self) -> str:
        if self.repaired:
            return "repaired"
        return "contradicted" if self.contradicted else "unverifiable"

    @property
    def bites(self) -> bool:
        """Could getting this wrong put a lot in the green column?

        Only if the note reaches somewhere a fourplex is permitted. A note
        standing over nothing, or over nothing but districts where the use is
        already prohibited, is a wrong sentence and not a wrong answer.
        """
        return self.verdict == "contradicted" and bool(self.permitting)


def _named(reason: str, zones: tuple[str, ...]) -> tuple[str, ...]:
    """Which of this layer's own zone codes the reason names.

    Only names the layer actually holds are looked for, so the check can
    never invent a zone -- the worst it can do is stay silent.
    """
    found = []
    for zone in zones:
        if len(zone) < 2:
            # 'R' and 'V' are real Wilsonville zones and match half of English.
            continue
        if re.search(_EDGE % re.escape(zone), reason):
            found.append(zone)
    return tuple(found)


def _standing_over(rows) -> dict[tuple[str, int], set[str]]:
    """``(document, line) -> the zones whose values that note governs``."""
    out: dict[tuple[str, int], set[str]] = {}
    for row in rows:
        for note in row.governing:
            if note.state == "dismissed":
                out.setdefault((note.doc, note.line), set()).add(row.zone)
    return out


def _permits(layer, zone: str) -> bool:
    """Absent is permitted: only a recorded ``False`` closes a district."""
    held = layer.zones.get(zone) if layer else None
    if held is None:
        return True
    value = held.values.get("quadplex_allowed")
    return value is None or value.value is not False


def audit(
    per_layer: dict[str, list[Ruling]] | None = None,
    layers: dict | None = None,
    scope: dict[tuple[str, int], set[str]] | None = None,
) -> list[Stale]:
    """Every dismissal whose reason is a claim about the corpus."""
    per_layer = rulings() if per_layer is None else per_layer
    layers = load_rules(strict=False) if layers is None else layers
    if scope is None:
        from flats.encode.qualified import qualified

        scope = _standing_over(qualified())

    out: list[Stale] = []
    for lid, rows in sorted(per_layer.items()):
        layer = layers.get(lid)
        zones = tuple(sorted(layer.zones)) if layer else ()
        for r in rows:
            if r.state != "dismissed" or not _CORPUS_CLAIM.search(r.reason):
                continue
            doc, _, line = r.quote.partition("#L")
            over = sorted(scope.get((doc, int(line or 0)), set())) if line else []
            out.append(
                Stale(
                    layer=lid,
                    quote=r.quote,
                    reason=" ".join(r.reason.split()),
                    contradicted=_named(r.reason, zones),
                    over=tuple(over),
                    permitting=tuple(z for z in over if _permits(layer, z)),
                    repaired=bool(_REPAIRED.search(r.reason)),
                )
            )
    return out


def render(rows: list[Stale]) -> str:
    from collections import Counter

    counts = Counter(r.verdict for r in rows)
    bites = [r for r in rows if r.bites]
    inert = [r for r in rows if r.verdict == "contradicted" and not r.bites]
    out = [
        f"reasons that are claims about our own files: {len(rows)}",
        f"  contradicted by the layer as it stands: {counts['contradicted']}",
        f"    of those, over land where a fourplex is permitted: {len(bites)}",
        f"  already repaired in their own words:     {counts['repaired']}",
        f"  naming nothing this can re-ask:          {counts['unverifiable']}",
        "",
        f"COULD STILL BE A WRONG GREEN: {len(bites)}",
    ]
    for r in sorted(bites, key=lambda r: (-len(r.permitting), r.quote)):
        out.append(f"  [{r.layer}] {r.quote}")
        out.append(f"      says not encoded, but the layer holds: {', '.join(r.contradicted)}")
        out.append(f"      stands over a fourplex zone: {', '.join(r.permitting)}")
        out.append(f"      reason: {r.reason[:180]}")
    if inert:
        out.append("")
        out.append(f"wrong sentence, right answer (no permitted zone behind it): {len(inert)}")
        for r in sorted(inert, key=lambda r: r.quote):
            out.append(f"  [{r.layer}] {r.quote} -- holds {', '.join(r.contradicted)}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path)
    args = ap.parse_args(argv)
    rows = audit()
    print(render(rows))
    if args.csv:
        import csv

        with args.csv.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(
                [
                    "layer",
                    "quote",
                    "verdict",
                    "bites",
                    "contradicted",
                    "over",
                    "permitting",
                    "reason",
                ]
            )
            for r in rows:
                w.writerow(
                    [
                        r.layer,
                        r.quote,
                        r.verdict,
                        r.bites,
                        ",".join(r.contradicted),
                        ",".join(r.over),
                        ",".join(r.permitting),
                        r.reason,
                    ]
                )
        print("wrote", args.csv)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
