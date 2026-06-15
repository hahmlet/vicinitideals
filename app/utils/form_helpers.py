"""Shared form-parsing utilities for model builder service functions."""
from __future__ import annotations

import json
from decimal import Decimal


class _UMRow:
    """Attribute-compatible proxy for unit_mix JSONB dicts."""

    def __init__(self, d: dict) -> None:
        self.__dict__.update(d)

    def __getattr__(self, k: str):
        return None


def _fd(v: str | None) -> Decimal | None:
    """Parse an optional Decimal from a form field. Strips commas tolerantly."""
    if not v or not v.strip():
        return None
    try:
        return Decimal(v.strip().replace(",", ""))
    except Exception:
        return None


def _fi(v: str | None, default: int = 0) -> int:
    """Parse an optional int from a form field."""
    if not v or not v.strip():
        return default
    try:
        return int(v.strip())
    except Exception:
        return default


def _fp(v: str | None, default: list[str] | None = None) -> list[str]:
    """Parse phases from a comma-separated or JSON-array form field."""
    if not v or not v.strip():
        return default or []
    v = v.strip()
    if v.startswith("["):
        try:
            return json.loads(v)
        except Exception:
            pass
    return [p.strip() for p in v.split(",") if p.strip()]
