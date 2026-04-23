"""Cross-source field enhancement + conflict logging for manual dedup merges.

Invoked from app/api/routers/dedup.py during POST /dedup/{id}/merge (or /swap).
Behavior for each ENHANCEABLE_FIELD:

  - canonical is NULL, loser has value  → copy loser value → canonical, log 'fill'
  - both non-null and disagree beyond tolerance → log 'conflict', canonical unchanged
  - values agree (within tolerance)     → no log row, no mutation

Values are serialized to text for the log. Numeric comparison uses a relative
tolerance so rounding differences between sources don't register as conflicts.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.models.field_conflict_log import FieldConflictAction, FieldConflictLog
from app.models.project import ScrapedListing

# Explicit allowlist of fields eligible for cross-source enhancement.
# Excludes identity, metadata, and enrichment-source-specific columns.
ENHANCEABLE_FIELDS: tuple[str, ...] = (
    "address_raw",
    "street",
    "street2",
    "city",
    "county",
    "state_code",
    "zip_code",
    "lat",
    "lng",
    "property_type",
    "sub_type",
    "investment_type",
    "investment_sub_type",
    "asking_price",
    "price_per_sqft",
    "price_per_unit",
    "gba_sqft",
    "net_rentable_sqft",
    "lot_sqft",
    "year_built",
    "year_renovated",
    "units",
    "buildings",
    "stories",
    "parking_spaces",
    "class_",
    "zoning",
    "apn",
    "occupancy_pct",
    "tenancy",
    "cap_rate",
    "proforma_cap_rate",
    "noi",
    "proforma_noi",
    "lease_term",
    "remaining_term",
    "rent_bumps",
    "listing_name",
    "description",
)

# Relative tolerance for numeric comparisons (1%).
NUMERIC_TOLERANCE = Decimal("0.01")


def _serialize(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return ",".join(str(v) for v in value)
    return str(value)


def _values_agree(a: Any, b: Any) -> bool:
    if isinstance(a, Decimal) and isinstance(b, Decimal):
        denom = max(abs(a), abs(b), Decimal("1"))
        return abs(a - b) / denom <= NUMERIC_TOLERANCE
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        denom = max(abs(a), abs(b), 1)
        return abs(a - b) / denom <= float(NUMERIC_TOLERANCE)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return [str(x).strip().lower() for x in a] == [str(x).strip().lower() for x in b]
    return _serialize(a) == _serialize(b) or (
        str(a).strip().lower() == str(b).strip().lower()
    )


def diff_fields(canonical: ScrapedListing, loser: ScrapedListing) -> dict[str, Any]:
    """Return {'fills': [...], 'conflicts': [...]} for UI preview without mutation.

    Each entry is a dict with: field_name, canonical_value, loser_value.
    """
    fills: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []

    for field in ENHANCEABLE_FIELDS:
        c_val = getattr(canonical, field, None)
        l_val = getattr(loser, field, None)
        if c_val is None and l_val is not None:
            fills.append({
                "field_name": field,
                "canonical_value": None,
                "loser_value": _serialize(l_val),
            })
        elif c_val is not None and l_val is not None and not _values_agree(c_val, l_val):
            conflicts.append({
                "field_name": field,
                "canonical_value": _serialize(c_val),
                "loser_value": _serialize(l_val),
            })

    return {"fills": fills, "conflicts": conflicts}


def apply_enhancement(
    canonical: ScrapedListing,
    loser: ScrapedListing,
    *,
    merge_candidate_id: UUID | None,
    resolved_by_user_id: UUID | None,
) -> list[FieldConflictLog]:
    """Apply field enhancement in place on canonical; return log rows to add to session.

    - Copies loser values into canonical NULL fields.
    - Emits FieldConflictLog rows for every fill AND every conflict.
    - Does NOT mutate canonical when both values exist (conflict case).
    """
    log_rows: list[FieldConflictLog] = []

    for field in ENHANCEABLE_FIELDS:
        c_val = getattr(canonical, field, None)
        l_val = getattr(loser, field, None)

        if c_val is None and l_val is not None:
            setattr(canonical, field, l_val)
            log_rows.append(FieldConflictLog(
                id=uuid.uuid4(),
                merge_candidate_id=merge_candidate_id,
                canonical_listing_id=canonical.id,
                loser_listing_id=loser.id,
                field_name=field,
                canonical_value=None,
                loser_value=_serialize(l_val),
                canonical_source=canonical.source,
                loser_source=loser.source,
                action=FieldConflictAction.fill.value,
                resolved_by_user_id=resolved_by_user_id,
            ))
        elif c_val is not None and l_val is not None and not _values_agree(c_val, l_val):
            log_rows.append(FieldConflictLog(
                id=uuid.uuid4(),
                merge_candidate_id=merge_candidate_id,
                canonical_listing_id=canonical.id,
                loser_listing_id=loser.id,
                field_name=field,
                canonical_value=_serialize(c_val),
                loser_value=_serialize(l_val),
                canonical_source=canonical.source,
                loser_source=loser.source,
                action=FieldConflictAction.conflict.value,
                resolved_by_user_id=resolved_by_user_id,
            ))

    return log_rows
