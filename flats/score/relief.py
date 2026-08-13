"""Relief — what the code lets you ask for when a lot misses a standard.

A pod one foot over a front setback is not an uncertain lot. It is a certain
lot with an application attached, and Oregon cities grant that application
routinely. Screening it as RED deletes an acquisition target over a foot, which
is the exact failure this project exists to avoid.

So a failing check is not the end of the question. It gets a second one: **does
the code offer a path, and how hard is that path?** The answer is a
:class:`~flats.rules.conditions.Tier` — as-of-right, a staff-level adjustment, a
discretionary variance, or nothing at all. Only the last earns a RED.

Three separations keep this honest.

*Availability is a fact; posture is a policy.* Whether an adjustment exists is
something the code says and we encode. Whether this team will file for one is a
knob. Posture filters a buy list; it never changes a colour, because a lot does
not become illegal by our being in a hurry.

*Unread is not unavailable.* A jurisdiction whose adjustment chapter nobody has
read yet gets :data:`~flats.rules.conditions.ASSUMED_TIER` — relief probably
exists — and the outcome is flagged ``confirmed=False`` so the claim names its
own gap. The opposite default would turn every near-miss in every unencoded
city red overnight.

*Use permission is the exception.* Codes enumerate conditional uses explicitly.
A zone that does not list one has no conditional-use path, so silence there is
evidence of absence in a way that silence about adjustments is not.

Caps are supported because real adjustment chapters have them — "up to 10% of
the standard" — but none are invented here. A cap appears only once somebody
has read the chapter that states it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

from flats.rules.conditions import ASSUMED_TIER, ASSUMED_USE_TIER, Tier, condition

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "relief.yaml"

#: Key under which a jurisdiction states relief for any standard it does not
#: name individually.
ANY = "*"
#: Key for the use gate, which is categorical rather than dimensional.
USE = "use"

#: Emitted when a yellow rests on a relief path nobody has read yet.
RELIEF_UNCONFIRMED = "RELIEF_UNCONFIRMED"


@dataclass(frozen=True, slots=True)
class ReliefPath:
    """One procedure the code offers for one kind of shortfall."""

    #: Registered relief condition — ``adjustment``, ``variance``, ...
    condition: str
    tier: Tier
    #: Largest shortfall this path will carry, in the check's own units.
    #: ``None`` means uncapped, which is the honest default for a variance:
    #: it is granted on findings, not on how small the miss was.
    cap: float | None = None
    #: The same limit stated as a fraction of the standard, e.g. 0.10 for
    #: "up to 10%". Whichever cap is present binds; if both, the larger wins,
    #: because two stated allowances are alternatives, not an intersection.
    cap_pct: float | None = None
    cite: str = ""
    #: False until a human has read the chapter that grants this.
    confirmed: bool = False

    def carries(self, shortfall: float, threshold: float) -> bool:
        """Whether this path covers a miss of this size."""
        if self.cap is None and self.cap_pct is None:
            return True
        limits = [c for c in (self.cap, _pct_cap(self.cap_pct, threshold)) if c is not None]
        return shortfall <= max(limits)


def _pct_cap(cap_pct: float | None, threshold: float) -> float | None:
    return None if cap_pct is None else abs(threshold) * cap_pct


@dataclass(frozen=True, slots=True)
class ReliefOutcome:
    """What it would take to clear one failing check."""

    check: str
    tier: Tier
    #: Registered condition name, or None when no path exists.
    condition: str | None = None
    cite: str = ""
    confirmed: bool = False

    @property
    def available(self) -> bool:
        return self.tier.available

    def __str__(self) -> str:
        if not self.available:
            return f"{self.check}: no relief available"
        mark = "" if self.confirmed else " (unconfirmed)"
        return f"{self.check}: {self.condition} — {self.tier.value}{mark}"


class ReliefPolicy:
    """Which relief each jurisdiction offers, and how far this team will go."""

    def __init__(
        self,
        paths: dict[str, dict[str, list[ReliefPath]]] | None = None,
        *,
        posture: Tier = Tier.discretionary,
    ) -> None:
        self.paths = {k: {c: list(v) for c, v in checks.items()} for k, checks in (paths or {}).items()}
        self.posture = posture

    # -- lookup ---------------------------------------------------------

    def paths_for(self, check: str, jurisdiction: str | None) -> list[ReliefPath] | None:
        """Encoded paths for one check, most specific layer first.

        Walks the layer chain inward — ``or/multnomah/portland`` before
        ``or/multnomah`` before ``or`` — and stops at the first layer that says
        anything about this check. Same precedence as rule resolution, and for
        the same reason: the more specific statement is the one somebody wrote
        on purpose. A layer naming the check beats one that only names ``*``.
        """
        for layer in _layer_chain(jurisdiction):
            block = self.paths.get(layer)
            if not block:
                continue
            if check in block:
                return block[check]
            if ANY in block:
                return block[ANY]
        return None

    def for_check(
        self, check: str, *, shortfall: float, threshold: float, jurisdiction: str | None = None
    ) -> ReliefOutcome:
        """The cheapest path that carries this miss, or none at all."""
        encoded = self.paths_for(check, jurisdiction)
        if encoded is None:
            # Nobody has read this jurisdiction's adjustment chapter. Assume a
            # path exists and say so, rather than deleting the lot.
            return ReliefOutcome(check, ASSUMED_TIER, "variance", confirmed=False)
        carrying = [p for p in encoded if p.carries(shortfall, threshold)]
        if not carrying:
            return ReliefOutcome(check, Tier.unavailable)
        best = min(carrying, key=lambda p: (p.tier.rank, p.condition))
        return ReliefOutcome(check, best.tier, best.condition, best.cite, best.confirmed)

    def for_use(self, jurisdiction: str | None = None) -> ReliefOutcome:
        """Whether a prohibited use has a conditional-use path in this zone.

        Defaults to none. A code lists its conditional uses; if ours does not
        list this one, that is the code answering, not a gap in our reading.
        """
        encoded = self.paths.get(_most_specific(self.paths, jurisdiction), {}).get(USE)
        if not encoded:
            return ReliefOutcome(USE, ASSUMED_USE_TIER)
        best = min(encoded, key=lambda p: (p.tier.rank, p.condition))
        return ReliefOutcome(USE, best.tier, best.condition, best.cite, best.confirmed)

    # -- policy ---------------------------------------------------------

    def acceptable(self, tier: Tier) -> bool:
        """Whether this team would pursue an ask of this depth.

        A buy-list filter only. It never moves a lot between colours: a
        discretionary variance is still a legal path when the posture says we
        will not file for one.
        """
        return tier.available and tier.rank <= self.posture.rank


def worst(outcomes: Iterable[ReliefOutcome]) -> ReliefOutcome | None:
    """The outcome that decides the configuration — the hardest ask in it.

    One hearing makes it a hearing project however many staff-level items sit
    beside it, so the maximum governs rather than the count.
    """
    found = list(outcomes)
    if not found:
        return None
    return max(found, key=lambda o: (o.tier.rank, o.check))


def _layer_chain(jurisdiction: str | None) -> list[str]:
    """``or/multnomah/portland`` -> most specific first, down to ``or``."""
    if not jurisdiction:
        return []
    parts = [p for p in jurisdiction.split("/") if p]
    return ["/".join(parts[: i + 1]) for i in range(len(parts) - 1, -1, -1)]


def _most_specific(paths: dict[str, Any], jurisdiction: str | None) -> str:
    for layer in _layer_chain(jurisdiction):
        if layer in paths:
            return layer
    return ""


def _path(raw: dict[str, Any], where: str) -> ReliefPath:
    name = str(raw.get("condition", ""))
    # An unregistered condition name is a typo that would quietly become a
    # second lever in the batch view, so it fails at load rather than at use.
    condition(name)
    tier = Tier(str(raw.get("tier", ASSUMED_TIER.value)))
    cap = raw.get("cap")
    cap_pct = raw.get("cap_pct")
    if cap_pct is not None and not 0 < float(cap_pct) <= 1:
        raise ValueError(f"{where}: cap_pct is a fraction of the standard, got {cap_pct!r}")
    confirmed = bool(raw.get("confirmed", False))
    cite = str(raw.get("cite", ""))
    if confirmed and not cite:
        # "Confirmed" with nothing to check it against is the one claim this
        # module must never carry: it is what turns a guess into a fact.
        raise ValueError(f"{where}: a confirmed relief path must cite the chapter granting it")
    return ReliefPath(
        condition=name,
        tier=tier,
        cap=None if cap is None else float(cap),
        cap_pct=None if cap_pct is None else float(cap_pct),
        cite=cite,
        confirmed=confirmed,
    )


def load_policy(path: Path | None = None) -> ReliefPolicy:
    source = path or CONFIG_PATH
    raw: Any = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{source}: expected a mapping")

    paths: dict[str, dict[str, list[ReliefPath]]] = {}
    for layer, checks in (raw.get("jurisdictions") or {}).items():
        block: dict[str, list[ReliefPath]] = {}
        for check, entries in (checks or {}).items():
            block[check] = [_path(e, f"{source}:{layer}/{check}") for e in (entries or [])]
        paths[layer] = block

    posture = Tier(str(raw.get("posture", Tier.discretionary.value)))
    if posture is Tier.unavailable:
        raise ValueError(f"{source}: posture 'unavailable' would refuse every ask, including none")
    return ReliefPolicy(paths, posture=posture)


__all__ = [
    "ANY",
    "CONFIG_PATH",
    "RELIEF_UNCONFIRMED",
    "USE",
    "ReliefOutcome",
    "ReliefPath",
    "ReliefPolicy",
    "load_policy",
    "worst",
]
