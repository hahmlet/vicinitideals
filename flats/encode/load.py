"""The one load path the screen is allowed to use.

Three passes, in this order, because they answer three different questions:

1. **Parse.** What do the rule files say? Everything arrives ``draft``.
2. **Promote.** Did somebody read this value against its source? Only a
   matching signature in the verification log says yes.
3. **Demote.** Is what they read still there? A value whose evidence moved,
   vanished or was edited goes ``stale`` no matter who signed it.

Promotion and demotion are separate because a value can pass one and fail the
other, and the review queue needs to know which. Doing them in one pass would
collapse "nobody has read this" into "this was read and the ground moved" —
different work for the person fixing it.

The result is that trust cannot be typed. A hand-written ``status: verified``
in a YAML file is refused at parse (see :mod:`flats.rules.loader`), and the
only way to a trusted value is a signature over the value, its citation and its
quote. Everything else lands in REVIEW, which costs a look; the alternative
costs an acquisition target nobody hears about.
"""

from __future__ import annotations

from dataclasses import dataclass, field as _dc_field
from pathlib import Path
from typing import Iterable

from flats.encode.dispute import Answered, DisputeLog, apply_disputes
from flats.encode.verify import Orphan, VerificationLog, apply_verifications
from flats.provenance.staleness import Staleness, apply_staleness
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer, Status
from flats.rules.resolver import RuleSet


@dataclass(frozen=True, slots=True)
class Trusted:
    """Loaded rules plus everything that stopped a value from being trusted."""

    rules: RuleSet
    #: Verifications whose value has since changed or disappeared. Work queue.
    orphans: tuple[Orphan, ...] = ()
    #: Values demoted because their evidence moved. Work queue.
    stale: tuple[Staleness, ...] = ()
    #: Disputes whose value has since changed -- somebody acted on the
    #: rejection. Work queue, and the only place a lifted dispute is visible.
    answered: tuple[Answered, ...] = ()
    #: Stored documents whose local bytes no longer match their hash.
    tampered: tuple[str, ...] = ()
    #: Rule-file problems, populated only when loaded non-strict.
    problems: tuple[str, ...] = ()
    counts: dict[str, int] = _dc_field(default_factory=dict)

    @property
    def layers(self) -> dict[str, Layer]:
        return self.rules.layers

    @property
    def clean(self) -> bool:
        """Nothing to hand a reviewer. Not the same as everything verified."""
        return not (
            self.orphans or self.stale or self.tampered or self.problems or self.answered
        )

    def summary(self) -> list[str]:
        """Lines fit for a terminal or the top of a coverage report."""
        total = sum(self.counts.values()) or 1
        pct = 100 * self.counts.get(Status.verified.value, 0) / total
        out = [
            f"{sum(self.counts.values())} value(s) across {len(self.layers)} layer(s)",
            "  " + ", ".join(f"{k}={v}" for k, v in sorted(self.counts.items())),
            f"  verified: {pct:.1f}%",
        ]
        if self.tampered:
            out.append(f"  TAMPERED evidence: {', '.join(self.tampered)}")
        if self.orphans:
            out.append(f"  orphaned verifications: {len(self.orphans)}")
        if self.stale:
            out.append(f"  stale values: {len(self.stale)}")
        disputed = self.counts.get(Status.disputed.value, 0)
        if disputed:
            out.append(f"  disputed values: {disputed}")
        if self.answered:
            out.append(f"  disputes answered by an edit: {len(self.answered)}")
        if self.problems:
            out.append(f"  rule-file problems: {len(self.problems)}")
        return out


def tally(layers: dict[str, Layer]) -> dict[str, int]:
    """Count values by status across the hierarchy."""
    counts: dict[str, int] = {}
    for layer in layers.values():
        blocks = [layer.defaults] + [z.values for z in layer.zones.values()]
        for block in blocks:
            for value in block.values():
                counts[value.status.value] = counts.get(value.status.value, 0) + 1
    return counts


def load_trusted(
    root: Path | None = None,
    *,
    log: VerificationLog | None = None,
    disputes: DisputeLog | None = None,
    store: ProvenanceStore | None = None,
    invalidated: Iterable[str] | None = None,
    strict: bool = True,
    require_quote: bool = True,
) -> Trusted:
    """Load the hierarchy with trust applied. The pipeline calls this, not ``load_rules``.

    ``invalidated`` is the set of document paths a drift check found changed
    upstream; local tampering is detected here without a network. Both demote
    the values that cite them.
    """
    layers = load_rules(root, strict=strict)
    problems: tuple[str, ...] = ()
    if not strict:
        problems = tuple(getattr(load_rules, "last_problems", ()) or ())

    store = store if store is not None else ProvenanceStore()
    tampered = tuple(store.tampered())
    bad = set(invalidated or ()) | set(tampered)

    layers, orphans = apply_verifications(layers, log if log is not None else VerificationLog.load())
    # Between promotion and staleness. A rejection recorded after a signature
    # is somebody disagreeing with the signature and has to outrank it; and
    # staleness only demotes `verified`, so a disputed value is not told it is
    # also stale -- one reason a number is untrusted is enough to act on.
    layers, disputed = apply_disputes(layers, disputes if disputes is not None else DisputeLog.load())
    layers, stale = apply_staleness(layers, bad, store=store, require_quote=require_quote)

    return Trusted(
        rules=RuleSet(layers),
        orphans=tuple(orphans),
        stale=tuple(stale),
        answered=tuple(disputed),
        tampered=tampered,
        problems=problems,
        counts=tally(layers),
    )
