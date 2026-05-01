"""Unit tests for app.services.broker_dedup name-normalization + winner logic."""

from __future__ import annotations

import uuid

import pytest

from app.services.broker_dedup import (
    _names_compatible,
    _normalize_name,
    _pick_winner,
)


# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Phillip Barry", "phillip barry"),
        ("Steven Hunker, CCIM", "steven hunker"),
        ("Jim Wierson II", "jim wierson"),
        ("Curt Arthur, SIOR", "curt arthur"),
        ("Brett Bayne PC", "brett bayne"),
        ("Phillip Caguioa-Moore", "phillip caguioa moore"),
        ("Phillip Caguioa-moore", "phillip caguioa moore"),
        (None, ""),
        ("", ""),
        ("   ", ""),
    ],
)
def test_normalize_name(raw: str | None, expected: str) -> None:
    assert _normalize_name(raw) == expected


# ---------------------------------------------------------------------------
# Name compatibility
# ---------------------------------------------------------------------------

def test_names_compatible_identical() -> None:
    assert _names_compatible("Phillip", "Barry", "Phillip", "Barry") is True


def test_names_compatible_credentials_in_lastname() -> None:
    # Steven Hunker vs "Steven Hunker, CCIM" → match after suffix strip
    assert _names_compatible("Steven", "Hunker", "Steven", "Hunker, CCIM") is True


def test_names_compatible_nickname_expansion() -> None:
    # "Ben"/"Benjamin" share first 3 chars
    assert _names_compatible("Ben", "Murphy", "Benjamin", "Murphy") is True


def test_names_compatible_case_difference() -> None:
    assert _names_compatible(
        "Phillip", "Caguioa-Moore", "Phillip", "Caguioa-moore"
    ) is True


def test_names_compatible_different_people() -> None:
    # Aiden vs Georgie — first 3 chars don't match
    assert _names_compatible(
        "Aiden", "Susak", "Georgie", "Christensen-Riley"
    ) is False


def test_names_compatible_different_last_name() -> None:
    assert _names_compatible("Jane", "Smith", "Jane", "Doe") is False


def test_names_compatible_missing_first() -> None:
    assert _names_compatible(None, "Smith", "Jane", "Smith") is False


# ---------------------------------------------------------------------------
# Winner selection
# ---------------------------------------------------------------------------

class _FakeBroker:
    """Minimal duck-type for _pick_winner."""

    def __init__(
        self,
        listings: int = 0,
        oregon_lookup_status: str | None = None,
        crexi_broker_id: int | None = None,
        license_locked: bool = False,
        broker_id: uuid.UUID | None = None,
    ):
        self.scraped_listings = [None] * listings
        self.oregon_lookup_status = oregon_lookup_status
        self.crexi_broker_id = crexi_broker_id
        self.license_number_locked = license_locked
        self.id = broker_id or uuid.uuid4()


def test_pick_winner_most_listings() -> None:
    a = _FakeBroker(listings=2)
    b = _FakeBroker(listings=5)
    c = _FakeBroker(listings=1)
    assert _pick_winner([a, b, c]) is b


def test_pick_winner_oregon_breaks_tie() -> None:
    a = _FakeBroker(listings=3)
    b = _FakeBroker(listings=3, oregon_lookup_status="success")
    assert _pick_winner([a, b]) is b


def test_pick_winner_crexi_id_breaks_tie() -> None:
    a = _FakeBroker(listings=3, oregon_lookup_status="success")
    b = _FakeBroker(listings=3, oregon_lookup_status="success", crexi_broker_id=123)
    assert _pick_winner([a, b]) is b


def test_pick_winner_locked_breaks_tie() -> None:
    a = _FakeBroker(listings=2, oregon_lookup_status="success", crexi_broker_id=1)
    b = _FakeBroker(
        listings=2, oregon_lookup_status="success", crexi_broker_id=1,
        license_locked=True,
    )
    assert _pick_winner([a, b]) is b
