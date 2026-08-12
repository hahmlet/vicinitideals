"""Slack, tolerance, and the three-way verdict a check produces.

**Slack is a measurement.** Every check records how much room the lot had,
whether or not it passed: "clears coverage by 340 sqft", "misses front setback
by 1.4 ft". It costs nothing — the comparison already computes it — and it is
what makes a result rankable. A lot missing by four inches is a different
conversation from one missing by twenty feet, and a screen that returns only
pass/fail cannot tell them apart.

**Tolerance is a policy.** It says how much shortfall is forgiven before a check
counts as a hard failure, and it is a knob rather than a fact about the world.

The two are kept apart because conflating them is how a screen starts lying: a
tolerance baked into the measurement makes the recorded margin wrong for every
downstream consumer, including the design sweep.

**Tolerance never manufactures a GREEN.** A check inside tolerance moves from RED
to REVIEW, never to PASS. This is the recall bias the whole project runs on: a
false red silently deletes an acquisition target and nobody ever learns it
existed, while a false green costs one review. Exclusion has to be unambiguous;
inclusion only has to be plausible.

Everything here is report-time, so sweeping tolerance to see where lot counts
move is seconds rather than a rebuild.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "slack.yaml"


class Verdict(str, enum.Enum):
    """What one check concluded."""

    #: Meets the standard outright.
    passes = "pass"
    #: Fails, but by less than the configured tolerance. Routes to REVIEW.
    tolerated = "tolerated"
    #: Fails beyond tolerance.
    fails = "fail"

    @property
    def blocks(self) -> bool:
        """True when this check cannot produce a GREEN on its own."""
        return self is not Verdict.passes


@dataclass(frozen=True, slots=True)
class CheckResult:
    """One check: what was measured, what was required, and how close it was."""

    check: str
    observed: float
    threshold: float
    #: True when the threshold is a ceiling (height, coverage), False when it is
    #: a floor (minimum lot area, minimum frontage).
    is_maximum: bool
    #: Room to spare, in the check's own units. Negative means it fell short.
    #: Always reported, on passes as well as failures.
    slack: float
    tolerance: float
    verdict: Verdict

    @property
    def shortfall(self) -> float:
        """How far under the standard, or 0.0 when it passes."""
        return max(0.0, -self.slack)


class SlackPolicy:
    """Tolerances, with per-jurisdiction overrides resolved most-specific-first."""

    def __init__(
        self,
        tolerance: dict[str, float] | None = None,
        overrides: dict[str, dict[str, float]] | None = None,
        *,
        report: str = "always",
    ) -> None:
        self.report = report
        self.tolerance = dict(tolerance or {})
        self.overrides = {k: dict(v) for k, v in (overrides or {}).items()}

    def tolerance_for(self, check: str, jurisdiction: str | None = None) -> float:
        """Tolerance for one check in one jurisdiction.

        Walks the layer path outward-in — ``or``, then ``or/multnomah``, then
        ``or/multnomah/portland`` — so a city override beats a county one and a
        county override beats the base. Same precedence as rule resolution, for
        the same reason: the more specific rule is the one someone wrote on
        purpose.
        """
        value = float(self.tolerance.get(check, 0.0))
        for layer in _layer_chain(jurisdiction):
            override = self.overrides.get(layer)
            if override and check in override:
                value = float(override[check])
        return value

    def evaluate(
        self,
        check: str,
        observed: float,
        threshold: float,
        *,
        is_maximum: bool,
        jurisdiction: str | None = None,
    ) -> CheckResult:
        """Measure one check and classify it.

        ``slack`` is signed and in the check's own units: positive is room to
        spare, negative is shortfall. For a ceiling that is ``threshold -
        observed``; for a floor, ``observed - threshold``.
        """
        slack = (threshold - observed) if is_maximum else (observed - threshold)
        tolerance = self.tolerance_for(check, jurisdiction)

        if slack >= 0:
            verdict = Verdict.passes
        elif -slack <= tolerance:
            verdict = Verdict.tolerated
        else:
            verdict = Verdict.fails

        return CheckResult(
            check=check,
            observed=float(observed),
            threshold=float(threshold),
            is_maximum=is_maximum,
            slack=float(slack),
            tolerance=tolerance,
            verdict=verdict,
        )


def _layer_chain(jurisdiction: str | None) -> list[str]:
    """``or/multnomah/portland`` -> ``[or, or/multnomah, or/multnomah/portland]``."""
    if not jurisdiction:
        return []
    parts = [p for p in jurisdiction.split("/") if p]
    return ["/".join(parts[: i + 1]) for i in range(len(parts))]


def binding(results: Iterable[CheckResult]) -> list[CheckResult]:
    """Blocking checks, tightest shortfall first.

    "Tightest first" is what makes the answer actionable — the check at the top
    is the one to argue about, buy a variance for, or redesign around. It is
    also what the binding-constraint histogram counts, which is how a rule that
    is quietly costing thousands of lots becomes visible.
    """
    return sorted(
        (r for r in results if r.verdict.blocks),
        key=lambda r: (r.shortfall, r.check),
    )


def load_policy(path: Path | None = None) -> SlackPolicy:
    raw: Any = yaml.safe_load((path or CONFIG_PATH).read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path or CONFIG_PATH}: expected a mapping")

    tolerance = raw.get("tolerance") or {}
    negative = sorted(k for k, v in tolerance.items() if float(v) < 0)
    if negative:
        # A negative tolerance would tighten the code beyond what it says and
        # turn passing lots red — the exact failure this project cannot have.
        raise ValueError(f"negative tolerance is not meaningful: {negative}")

    return SlackPolicy(
        tolerance=tolerance,
        overrides=raw.get("overrides") or {},
        report=str(raw.get("report", "always")),
    )
