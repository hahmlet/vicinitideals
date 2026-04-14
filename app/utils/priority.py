"""Priority bucket classification for parcels and listings.

Decision tree:
  Q1: MF-capable zoning?        NO → ineligible  (unknown → unclassified)
  Q2: Multnomah or Clackamas?   NO → out_of_market
  Q3: Portland jurisdiction?    YES → contextual
  Q4: MF/Hotel/MixedUse use?   YES → prime   NO → target
"""

from __future__ import annotations

import enum
import re


class PriorityBucket(str, enum.Enum):
    prime = "prime"
    target = "target"
    contextual = "contextual"
    out_of_market = "out_of_market"
    ineligible = "ineligible"
    unclassified = "unclassified"


# ---------------------------------------------------------------------------
# Zoning code seed lists (jurisdiction-keyed, all uppercase for matching)
# These are best-effort starters — expand over time without schema changes.
# ---------------------------------------------------------------------------

MF_ZONING_CODES: dict[str, set[str]] = {
    "gresham": {
        "R3", "R4", "R-3", "R-4",
        "CMR", "CMU", "CG",
        "MFR", "MF",
        "R3LH", "R4LH",  # limited height variants
    },
    "portland": {
        "RM1", "RM2", "RM3", "RM4",
        "R1", "R2",           # higher-density residential
        "RX",                 # central residential
        "CM1", "CM2", "CM3",  # commercial/mixed
        "CX", "EX", "IR",     # central/employment
        "G1", "G2",           # general industrial (can have residential)
    },
    "clackamas": {
        "MFR", "MF", "RM", "RM-1", "RM-2",
        "R-3", "R-4", "R-5",
        "TOWN", "TN",         # town center / townhome
        "MU", "MUC",          # mixed use
        "CC",                 # community commercial (often allows MF)
    },
    "oregon_city": {
        "RM-1", "RM-2", "RM-3",
        "MF", "MFR",
        "MU", "CC", "DC",
    },
    "lake_oswego": {
        "R-2", "R-3", "RM",
        "MD", "HDR",
        "MU",
    },
    "beaverton": {
        "R-2", "R-3.5", "R-4",
        "MF-1", "MF-2",
        "SC-MU", "TC-MU",
    },
    # Fallback codes common across many OR municipalities
    "_default": {
        "MF", "MFR", "RM", "RM1", "RM2", "RM3", "RM4",
        "CMU", "MU", "MUC",
        "R3", "R4", "R-3", "R-4",
    },
}

# Keywords matched against zoning_description when code lookup fails
MF_ZONING_DESCRIPTION_KEYWORDS: list[str] = [
    "multifamily", "multi-family", "multi family",
    "multiple family", "multiple-family",
    "high density residential", "medium density residential",
    "mixed use residential", "mixed-use residential",
    "apartment", "residential mixed",
    "town center", "urban center",
    "commercial residential",
]

# ---------------------------------------------------------------------------
# Current use / property type keywords for Q4
# ---------------------------------------------------------------------------

MF_CURRENT_USE_KEYWORDS: set[str] = {
    "apartment", "apartments",
    "multifamily", "multi-family", "multi family",
    "hotel", "motel", "inn", "extended stay",
    "mixed use", "mixed-use",
    "residential care", "senior housing", "assisted living",
    "townhouse", "townhomes", "condo", "condominium",
    "duplex", "triplex", "fourplex", "quadplex",
    "student housing",
}

# ---------------------------------------------------------------------------
# Location constants
# ---------------------------------------------------------------------------

METRO_COUNTIES: set[str] = {"multnomah", "clackamas", "washington"}

PORTLAND_JURISDICTIONS: set[str] = {"portland", "city of portland"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify(
    *,
    zoning_code: str | None,
    zoning_description: str | None,
    county: str | None,
    jurisdiction: str | None,
    current_use: str | None,
    property_type: str | None,
) -> PriorityBucket:
    """Run the decision tree and return the appropriate bucket.

    Order: county → Portland → zoning MF check → current use
    County and Portland checks come first so parcels with known location
    but no zoning yet still get a useful classification (contextual /
    out_of_market) rather than falling through to unclassified.
    """
    county_norm = _norm(county)
    juris_norm = _norm(jurisdiction)

    # Q1 — Metro county? (can decide even without zoning)
    if county_norm and county_norm not in METRO_COUNTIES:
        return PriorityBucket.out_of_market

    # Q2 — Portland? (contextual regardless of zoning)
    if juris_norm in PORTLAND_JURISDICTIONS:
        return PriorityBucket.contextual

    # Q3 — MF-capable zoning?
    mf_zone = is_mf_zoning(zoning_code, zoning_description, jurisdiction)
    if mf_zone is False:
        return PriorityBucket.ineligible
    if mf_zone is None:
        return PriorityBucket.unclassified

    # Need county confirmed metro to proceed past zoning check
    if county_norm not in METRO_COUNTIES:
        return PriorityBucket.out_of_market

    # Q4 — MF current use?
    if is_mf_current_use(current_use, property_type):
        return PriorityBucket.prime

    return PriorityBucket.target


def is_mf_zoning(
    code: str | None,
    description: str | None,
    jurisdiction: str | None,
) -> bool | None:
    """Return True (MF), False (not MF), or None (can't determine).

    Matching order:
    1. Exact code lookup in jurisdiction-specific set
    2. Exact code lookup in _default set
    3. Keyword match against description
    4. None if nothing matches
    """
    if not code and not description:
        return None

    code_upper = code.strip().upper() if code else None
    juris_key = _norm(jurisdiction) if jurisdiction else "_default"

    # 1 — Jurisdiction-specific exact match
    if code_upper:
        juris_codes = MF_ZONING_CODES.get(juris_key, set())
        if code_upper in juris_codes:
            return True
        # Also check _default
        if code_upper in MF_ZONING_CODES["_default"]:
            return True
        # Code is present but not in any MF set — check description before declaring False
        if not description:
            return False

    # 2 — Description keyword match
    if description:
        desc_lower = description.strip().lower()
        if any(kw in desc_lower for kw in MF_ZONING_DESCRIPTION_KEYWORDS):
            return True
        # If we had a code but no keyword match, it's not MF
        if code_upper:
            return False

    # No code, description only, no keyword match
    return None


def is_mf_current_use(
    current_use: str | None,
    property_type: str | None,
) -> bool:
    """Return True if current use or property type indicates MF/hotel/mixed use."""
    combined = " ".join(
        part.lower()
        for part in (current_use, property_type)
        if part
    )
    if not combined:
        return False
    return any(kw in combined for kw in MF_CURRENT_USE_KEYWORDS)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _norm(value: str | None) -> str:
    """Lowercase + strip for comparison. Strips trailing ' county' so
    'Multnomah County' matches the same as 'Multnomah'."""
    s = (value or "").strip().lower()
    if s.endswith(" county"):
        s = s[: -len(" county")]
    return s


__all__ = [
    "PriorityBucket",
    "classify",
    "is_mf_zoning",
    "is_mf_current_use",
    "MF_ZONING_CODES",
    "METRO_COUNTIES",
    "PORTLAND_JURISDICTIONS",
]
