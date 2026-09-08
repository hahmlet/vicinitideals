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

Two answers, and neither is a verdict:

``contradicted``   the reason denies encoding and names a zone the layer holds
``unverifiable``   it denies encoding but names no zone this can check

Both are *reading queues*, and the sizes are the point -- fourteen and thirty-
five out of 784. ``contradicted`` over-reports on purpose: a reason can name a
live zone for a reason of its own ("120 feet from a lot zoned R-6" is a
measurement, not a claim that R-6 is missing), and a person can see that in a
second. The opposite error cannot be seen at all, because a stale reason looks
exactly like a sound one. An ``unverifiable`` row is not a bug either. It is a
claim written in a shape nobody can re-ask, which is worth knowing about a
claim that decays.

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

    @property
    def verdict(self) -> str:
        return "contradicted" if self.contradicted else "unverifiable"


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


def audit(
    per_layer: dict[str, list[Ruling]] | None = None,
    layers: dict | None = None,
) -> list[Stale]:
    """Every dismissal whose reason is a claim about the corpus."""
    per_layer = rulings() if per_layer is None else per_layer
    layers = load_rules(strict=False) if layers is None else layers

    out: list[Stale] = []
    for lid, rows in sorted(per_layer.items()):
        layer = layers.get(lid)
        zones = tuple(sorted(layer.zones)) if layer else ()
        for r in rows:
            if r.state != "dismissed" or not _CORPUS_CLAIM.search(r.reason):
                continue
            out.append(
                Stale(
                    layer=lid,
                    quote=r.quote,
                    reason=" ".join(r.reason.split()),
                    contradicted=_named(r.reason, zones),
                )
            )
    return out


def render(rows: list[Stale]) -> str:
    bad = [r for r in rows if r.contradicted]
    out = [
        f"reasons that are claims about our own files: {len(rows)}",
        f"  contradicted by the layer as it stands: {len(bad)}",
        f"  naming nothing this can re-ask:         {len(rows) - len(bad)}",
        "",
    ]
    for r in sorted(bad, key=lambda r: (r.layer, r.quote)):
        out.append(f"[{r.layer}] {r.quote}")
        out.append(f"   says not encoded, but the layer holds: {', '.join(r.contradicted)}")
        out.append(f"   reason: {r.reason[:200]}")
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
            w.writerow(["layer", "quote", "verdict", "contradicted", "reason"])
            for r in rows:
                w.writerow(
                    [r.layer, r.quote, r.verdict, ",".join(r.contradicted), r.reason]
                )
        print("wrote", args.csv)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
