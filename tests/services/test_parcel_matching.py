"""Unit tests for app.services.parcel_matching — all pure-Python, no DB."""
import math
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.parcel_matching import (
    _haversine_m,
    _normalize_street_name,
    _opp_street_number,
    find_matching_parcel,
    link_parcel_if_unlinked,
)


# ── Haversine ─────────────────────────────────────────────────────────────────

def test_haversine_same_point():
    assert _haversine_m(45.5, -122.6, 45.5, -122.6) == pytest.approx(0.0, abs=1e-6)


def test_haversine_known_distance():
    # ~30 m north of origin at lat 45.5° ≈ 0.000270 degrees
    d = _haversine_m(45.5, -122.6, 45.500270, -122.6)
    assert 25.0 < d < 35.0


# ── Street normalisation ──────────────────────────────────────────────────────

def test_normalize_street_name_basic():
    assert _normalize_street_name("Oak Avenue") == "oak avenue"


def test_normalize_street_name_punctuation():
    assert _normalize_street_name("St. John's Rd.") == "st johns rd"


def test_normalize_street_name_none():
    assert _normalize_street_name(None) == ""


# ── Street number extraction ──────────────────────────────────────────────────

def _opp(street=None, address_normalized=None):
    o = MagicMock()
    o.street = street
    o.address_normalized = address_normalized
    return o


def test_opp_street_number_basic():
    assert _opp_street_number(_opp(street="123 Oak Ave")) == 123


def test_opp_street_number_no_number():
    assert _opp_street_number(_opp(street="Oak Ave")) is None


def test_opp_street_number_fallback_to_normalized():
    assert _opp_street_number(_opp(street=None, address_normalized="456 Main St")) == 456


# ── find_matching_parcel — APN hit ────────────────────────────────────────────

def _mock_session_returning(parcel_or_none):
    """Build an AsyncMock session whose execute() returns a MagicMock result.

    AsyncMock auto-creates child attrs as AsyncMock too, so scalar_one_or_none()
    would return a coroutine. We explicitly set execute.return_value to a plain
    MagicMock so synchronous result methods work correctly.
    """
    session = AsyncMock()
    sync_result = MagicMock()
    sync_result.scalar_one_or_none.return_value = parcel_or_none
    sync_result.scalars.return_value.all.return_value = (
        [] if parcel_or_none is None else [parcel_or_none]
    )
    session.execute.return_value = sync_result
    return session


@pytest.mark.asyncio
async def test_find_matching_parcel_apn_hit():
    opp = MagicMock()
    opp.apn_normalized = ["R123456"]
    opp.lat = None
    opp.lng = None
    opp.street = None
    opp.address_normalized = None

    fake_parcel = MagicMock()
    fake_parcel.id = uuid.uuid4()

    session = _mock_session_returning(fake_parcel)
    result = await find_matching_parcel(session, opp)
    assert result is fake_parcel


@pytest.mark.asyncio
async def test_find_matching_parcel_no_apn_no_latlng_no_addr():
    opp = MagicMock()
    opp.apn_normalized = None
    opp.lat = None
    opp.lng = None
    opp.street = None
    opp.address_normalized = None

    session = _mock_session_returning(None)
    result = await find_matching_parcel(session, opp)
    assert result is None


# ── link_parcel_if_unlinked ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_link_parcel_if_unlinked_already_linked():
    opp = MagicMock()
    opp.parcel_id = uuid.uuid4()
    session = AsyncMock()

    result = await link_parcel_if_unlinked(session, opp)
    assert result is False
    # No DB calls needed when already linked
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_link_parcel_if_unlinked_sets_parcel_id():
    parcel_id = uuid.uuid4()
    fake_parcel = MagicMock()
    fake_parcel.id = parcel_id

    opp = MagicMock()
    opp.parcel_id = None
    opp.apn_normalized = ["R999"]
    opp.lat = None
    opp.lng = None
    opp.street = None
    opp.address_normalized = None

    session = _mock_session_returning(fake_parcel)
    result = await link_parcel_if_unlinked(session, opp)
    assert result is True
    assert opp.parcel_id == parcel_id


@pytest.mark.asyncio
async def test_link_parcel_if_unlinked_no_match():
    opp = MagicMock()
    opp.parcel_id = None
    opp.apn_normalized = None
    opp.lat = None
    opp.lng = None
    opp.street = None
    opp.address_normalized = None

    session = _mock_session_returning(None)
    result = await link_parcel_if_unlinked(session, opp)
    assert result is False
    assert opp.parcel_id is None
