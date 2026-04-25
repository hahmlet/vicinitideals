"""Normalization helpers for broker and brokerage names.

These don't try to be perfect — they clean up the common ALL-CAPS-from-source
case while preserving short acronyms (JLL, CBRE, NAI) and mixed-case input.
Punctuation that legitimately appears in firm names (``/``, ``&``, ``,`` ``.``
``'`` ``-``) is preserved because Python's ``str.title()`` only affects
alphabetic characters.
"""

from __future__ import annotations

import re

_WHITESPACE_RE = re.compile(r"\s+")

# Strings entirely composed of uppercase letters and shorter than this many
# alphabetic characters are assumed to be intentional acronyms and left alone
# (e.g. "JLL", "CBRE", "NAI", "RE/MAX" would still be touched by length but
# slash protects "MAX" half).
_ACRONYM_MAX_LETTERS = 4


def normalize_name(value: str | None) -> str | None:
    """Trim, collapse whitespace, and Title-Case ALL-CAPS strings.

    - ``None`` or whitespace-only input → ``None``
    - Any lowercase letter present → return as-is (just trimmed/collapsed)
    - All uppercase, more than 4 alphabetic chars → Title-Case
    - Otherwise (short acronyms, no letters) → return as-is
    """
    if value is None:
        return None
    cleaned = _WHITESPACE_RE.sub(" ", value).strip()
    if not cleaned:
        return None
    has_lower = any(ch.islower() for ch in cleaned)
    if has_lower:
        return cleaned
    letter_count = sum(1 for ch in cleaned if ch.isalpha())
    if letter_count > _ACRONYM_MAX_LETTERS:
        return cleaned.title()
    return cleaned


__all__ = ["normalize_name"]
