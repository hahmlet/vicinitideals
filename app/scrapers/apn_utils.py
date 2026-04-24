"""APN (Assessor Parcel Number) normalization for cross-source matching.

Different sources and different counties format APNs differently:
  - Multnomah County: R+6digits (e.g. "R313810") — used by both Crexi & LoopNet
  - Clackamas County: 8-digit zero-padded (e.g. "00591309")
  - Washington County: township codes with hyphens (e.g. "091105CA-18700-00",
    "11-10-08-CB-05700-00") — Crexi populates these; LoopNet often doesn't
  - Multi-parcel listings use comma-separated lists; Crexi occasionally uses
    semicolons or spaces as separators

GIS systems typically require APN in the exact county format for queries,
so we keep the raw `apn` column unchanged. For cross-source matching, this
module produces a normalized token set that bridges format differences.

Used at ingest time by every scraper, and at match time by
app/scrapers/dedup.py scorer.
"""

from __future__ import annotations

import re

# Split multi-parcel APN strings on commas, semicolons, or whitespace runs.
_APN_SPLIT_RE = re.compile(r"[,;\s]+")
# Strip everything that's not alphanumeric (removes hyphens, dots, underscores).
_APN_CLEAN_RE = re.compile(r"[^A-Z0-9]")


def normalize_apn(raw: str | None) -> list[str]:
    """Split a raw APN string into a sorted, deduped list of normalized tokens.

    Rules:
      1. Uppercase everything
      2. Split on commas, semicolons, or whitespace (multi-parcel listings)
      3. Strip any non-alphanumeric from each piece (removes hyphens, dots, etc.)
      4. Drop empty tokens
      5. Return sorted + deduplicated list

    Examples:
      normalize_apn("R313810")                            -> ["R313810"]
      normalize_apn("r313810")                            -> ["R313810"]
      normalize_apn("091105CA-18700-00")                  -> ["091105CA1870000"]
      normalize_apn("R113312, R113343, R113344")          -> ["R113312","R113343","R113344"]
      normalize_apn("082W06AB00800,082W06AB00700")        -> ["082W06AB00700","082W06AB00800"]
      normalize_apn("")                                   -> []
      normalize_apn(None)                                 -> []
    """
    if raw is None:
        return []
    s = str(raw).strip().upper()
    if not s:
        return []
    pieces = _APN_SPLIT_RE.split(s)
    tokens: set[str] = set()
    for p in pieces:
        if not p:
            continue
        cleaned = _APN_CLEAN_RE.sub("", p)
        if cleaned:
            tokens.add(cleaned)
    return sorted(tokens)


def apn_match(
    tokens_a: list[str] | None,
    tokens_b: list[str] | None,
) -> bool:
    """Return True if the two normalized APN lists share any token."""
    if not tokens_a or not tokens_b:
        return False
    return bool(set(tokens_a) & set(tokens_b))


__all__ = ["apn_match", "normalize_apn"]
