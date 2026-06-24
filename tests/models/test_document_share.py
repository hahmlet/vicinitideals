"""``DocumentShare.is_active`` — the single gate for guest-link validity.

A link is usable only while it is not revoked and not past its optional expiry.
These use transient ``DocumentShare()`` instances with no DB session.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.document import DocumentShare

pytestmark = pytest.mark.unit


def _now() -> datetime:
    return datetime.now(timezone.utc)


def test_active_when_not_revoked_and_no_expiry():
    assert DocumentShare(revoked=False, expires_at=None).is_active(_now()) is True


def test_inactive_when_revoked():
    now = _now()
    assert DocumentShare(revoked=True, expires_at=None).is_active(now) is False
    # Revoked beats a still-future expiry.
    assert DocumentShare(revoked=True, expires_at=now + timedelta(days=1)).is_active(now) is False


def test_inactive_when_expired():
    now = _now()
    assert DocumentShare(revoked=False, expires_at=now - timedelta(seconds=1)).is_active(now) is False


def test_active_before_expiry():
    now = _now()
    assert DocumentShare(revoked=False, expires_at=now + timedelta(days=1)).is_active(now) is True
