"""Two balance tracks per debt module: interest-bearing vs payoff.

The spec for reserves and the lease-up principal sweep requires a clean
separation between two notions of "loan balance":

* **Interest-bearing balance** — held flat at the original funded principal
  for the entire modeled period. Period interest accrual and Interest
  Reserve draws read this track. The convention is conservative on
  purpose: lender-side interest is sized as if no paydown ever occurred,
  so reserves cover the full sized interest stream regardless of how
  much principal the deal actually retires through sweeps.

* **Payoff balance** — what the deal owes when it pays off the loan. Starts
  at the original principal and is reduced by every paydown / sweep that
  the spec says should lower the take-out amount but not the interest. Exit
  balloon, prepayment penalty, and take-out math read this track.

Today's v1 already overstates interest after a paydown (see
`debt_paydown.py:13`) because period-level interest is never recomputed
against the swept balance. That convention happens to match the spec — so
this module makes it explicit rather than implicit, and gives later slices
a single place to add a lease-up sweep event without revisiting every
call-site that touches a loan balance.

Behavior-preserving scaffold: existing `_balloon_balance` math is unchanged;
this helper composes it with paydown tracking so the two tracks are
addressable by callers that need them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable
from uuid import UUID

from app.engines.debt_paydown import PaydownEvent


ZERO = Decimal("0")
MONEY_PLACES = Decimal("0.000001")


def _q(value: Decimal) -> Decimal:
    return value.quantize(MONEY_PLACES)


@dataclass
class LoanBalanceTracker:
    """Tracks the two balance series for one debt module.

    Construct one per auto-sized debt module after the principal solve.
    Feed it paydowns / sweeps as the period loop discovers them. Read
    either track at any later point.
    """

    debt_module_id: UUID
    original_principal: Decimal
    paydowns: list[PaydownEvent] = field(default_factory=list)

    def record_paydown(self, event: PaydownEvent) -> None:
        """Record a payoff-only paydown / sweep against this module.

        The contract is payoff-only by construction: nothing here reduces
        the interest-bearing track. Callers that want interest to follow
        the swept balance (not the spec convention) must call a different,
        future API.
        """
        if event.debt_module_id != self.debt_module_id:
            raise ValueError(
                f"Paydown event targets {event.debt_module_id}; "
                f"this tracker is for {self.debt_module_id}"
            )
        if event.amount <= ZERO:
            return
        self.paydowns.append(event)

    def interest_bearing_balance(self) -> Decimal:
        """The balance period interest and IR draws should accrue on.

        Held flat at the original principal regardless of paydowns. This
        is the spec's "DS held flat on the original funded balance" rule
        applied to the underlying balance, not just the DS amount.
        """
        return self.original_principal

    def cumulative_paydowns(self) -> Decimal:
        """Total of all recorded paydowns / sweeps against this module."""
        return _q(sum((p.amount for p in self.paydowns), ZERO))

    def payoff_balance_at(
        self,
        *,
        months_elapsed: int,
        balloon_from_amortization: Decimal,
    ) -> Decimal:
        """Outstanding balance for payoff / refinance math.

        ``balloon_from_amortization`` is the result of the existing
        ``_balloon_balance(original_principal, ...)`` formula — passed in
        so this module stays decoupled from the amortization details and
        callers can keep computing balloons the way they already do.

        Returns ``max(balloon - cumulative_paydowns, 0)``. Both inputs
        are quantized; the result is too.
        """
        del months_elapsed  # carried in the signature so callers think periodically
        net = balloon_from_amortization - self.cumulative_paydowns()
        return _q(max(net, ZERO))


def build_trackers(
    *,
    debt_module_principals: dict[UUID, Decimal],
) -> dict[UUID, LoanBalanceTracker]:
    """Construct one tracker per debt module from the solved principals.

    Returned dict is keyed by ``debt_module_id`` so callers can look up
    by FK during the period loop.
    """
    return {
        module_id: LoanBalanceTracker(
            debt_module_id=module_id, original_principal=_q(principal)
        )
        for module_id, principal in debt_module_principals.items()
    }


def record_paydowns_for_trackers(
    *,
    trackers: dict[UUID, LoanBalanceTracker],
    events: Iterable[PaydownEvent],
) -> None:
    """Fan a list of paydown events out to the right per-module trackers.

    Events targeting a module not in ``trackers`` are dropped — callers
    that need stricter handling should pre-filter or use the per-tracker
    ``record_paydown`` directly.
    """
    for event in events:
        tracker = trackers.get(event.debt_module_id)
        if tracker is None:
            continue
        tracker.record_paydown(event)
