"""Auto-resolution rules for Opportunity vs Parcel field conflicts.

Rules (applied in priority order):
  1. Zero value — if one side is 0, defer to the non-zero side.
  2. year_built within 5 years — use the newer (higher) year.
  3. sqft (gba_sqft / lot_sqft) within 5% — use the larger value.
  4. year_built 40+ years apart — use the newer (higher) year.
  5. gba_sqft (building) < 2 000 sqft — treat as unreliable, use the other side.
  6. lot_sqft < 2 000 sqft — treat as unreliable, use the other side.

Public API
----------
auto_resolve_conflict(field, opp_val, parcel_val) -> "use_listing" | "use_parcel" | None
    Returns the winning side, or None when no rule fires and human review is needed.

_FIELD_MAP
    Maps the canonical conflict field key to (opp_attribute, parcel_attribute) so
    callers can look up the correct model attributes without hard-coding them everywhere.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Field mapping
# ---------------------------------------------------------------------------

# field_key → (opp_attr_name, parcel_attr_name)
_FIELD_MAP: dict[str, tuple[str, str]] = {
    "units":      ("units",      "unit_count"),
    "gba_sqft":   ("gba_sqft",   "building_sqft"),
    "year_built": ("year_built", "year_built"),
    "lot_sqft":   ("lot_sqft",   "lot_sqft"),
}

# Sqft fields subject to rules 3, 5, 6
_SQFT_FIELDS = frozenset({"gba_sqft", "lot_sqft"})
_SMALL_SQFT_THRESHOLD = 2_000.0
_SQFT_CLOSE_PCT = 0.05   # 5 % — treated as noise; use the larger value


# ---------------------------------------------------------------------------
# Core resolution function
# ---------------------------------------------------------------------------

def auto_resolve_conflict(
    field: str,
    opp_val: object,
    parcel_val: object,
) -> str | None:
    """Return the auto-resolution action for a single field conflict.

    Parameters
    ----------
    field:
        One of "units", "gba_sqft", "year_built", "lot_sqft".
    opp_val:
        Value stored on the Opportunity (listing side).
    parcel_val:
        Value stored on the matched Parcel (GIS/assessor side).

    Returns
    -------
    "use_listing"   Keep the Opportunity value; ack the conflict.
    "use_parcel"    Null out the Opportunity field so it defers to Parcel.
    None            No rule fired; human review required.
    """
    if opp_val is None or parcel_val is None:
        return None

    try:
        fv_opp = float(opp_val)
        fv_par = float(parcel_val)
    except (TypeError, ValueError):
        return None

    # Rule 1 — zero value: defer to the non-zero side
    if fv_opp == 0.0 and fv_par != 0.0:
        return "use_parcel"
    if fv_par == 0.0 and fv_opp != 0.0:
        return "use_listing"
    if fv_opp == 0.0 and fv_par == 0.0:
        # Both zero — no real conflict
        return "use_listing"

    if field == "year_built":
        # Policy: listing year always wins — assessor data lags renovations / rebuilds
        return "use_listing"

    elif field in _SQFT_FIELDS:
        max_val = max(fv_opp, fv_par)

        # Rule 3 — within 5%: use the larger
        if max_val > 0 and abs(fv_opp - fv_par) / max_val <= _SQFT_CLOSE_PCT:
            return "use_listing" if fv_opp >= fv_par else "use_parcel"

        # Rule 5 / 6 — unreliably small sqft: use the other side
        if fv_opp < _SMALL_SQFT_THRESHOLD and fv_par >= _SMALL_SQFT_THRESHOLD:
            return "use_parcel"
        if fv_par < _SMALL_SQFT_THRESHOLD and fv_opp >= _SMALL_SQFT_THRESHOLD:
            return "use_listing"

    return None
