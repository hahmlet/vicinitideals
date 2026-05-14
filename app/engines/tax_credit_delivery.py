"""
tax_credit_delivery.py — Equity tax-credit delivery schedule helpers.

For LIHTC, HTC, OZ and other credit-equity vehicles that deliver capital
over multiple years post-PIS rather than as a single close-date lump.

vehicle.delivery_schedule JSON: [{year_offset_from_pis: int, pct: Decimal}, ...]
  - pct values must sum to 100 (or close; any remainder lands in last entry)
  - year_offset 0 = PIS year, 1 = one year after PIS, etc.

If delivery_schedule is null/empty, a single inflow event is emitted at
the scenario's active_from date (or close-milestone date when available).

Returned dicts are NOT persisted here — caller (cashflow.py) persists them
as CapitalDrawEvent rows with allocation_reason="tax_credit_delivery".
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

log = logging.getLogger(__name__)

ZERO = Decimal("0")
HUNDRED = Decimal("100")


@dataclass
class DeliveryEvent:
    deliver_date: date
    amount: Decimal
    year_offset: int


def generate_delivery_events(
    amount: Decimal,
    delivery_schedule: list[dict] | None,
    pis_date: date,
    fallback_date: date | None = None,
) -> list[DeliveryEvent]:
    """Compute delivery events for an equity vehicle.

    Args:
        amount:            Total equity amount to deliver.
        delivery_schedule: List of {year_offset_from_pis, pct} dicts, or None.
        pis_date:          Date of Placed-In-Service (e.g. operation_stabilized milestone).
        fallback_date:     Date used for single-event delivery when schedule is absent.

    Returns:
        List of DeliveryEvent. Amounts sum to ``amount`` within rounding;
        any remainder allocated to the last event.
    """
    if amount <= ZERO:
        return []

    if not delivery_schedule:
        # Single lump at fallback_date (or pis_date if no fallback)
        deliver_on = fallback_date or pis_date
        return [DeliveryEvent(deliver_date=deliver_on, amount=amount, year_offset=0)]

    events: list[DeliveryEvent] = []
    total_allocated = ZERO

    for i, entry in enumerate(delivery_schedule):
        offset = int(entry.get("year_offset_from_pis", entry.get("year_offset", 0)))
        pct = Decimal(str(entry.get("pct", 0)))

        # Last entry: allocate remainder to avoid rounding drift
        if i == len(delivery_schedule) - 1:
            event_amount = amount - total_allocated
        else:
            event_amount = (amount * pct / HUNDRED).quantize(Decimal("0.000001"))

        if event_amount <= ZERO:
            continue

        deliver_date = date(pis_date.year + offset, pis_date.month, pis_date.day)
        events.append(DeliveryEvent(deliver_date=deliver_date, amount=event_amount, year_offset=offset))
        total_allocated += event_amount

    if not events:
        # Degenerate schedule — fall back to single event
        log.warning("tax_credit_delivery: empty schedule after processing, falling back to single event")
        return [DeliveryEvent(deliver_date=fallback_date or pis_date, amount=amount, year_offset=0)]

    return events
