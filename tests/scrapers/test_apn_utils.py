"""Unit tests for app/scrapers/apn_utils.normalize_apn."""

from __future__ import annotations

import pytest

from app.scrapers.apn_utils import apn_match, normalize_apn


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Basic case-fold
        ("R313810", ["R313810"]),
        ("r313810", ["R313810"]),
        # Strip punctuation (Washington County township format)
        ("091105CA-18700-00", ["091105CA1870000"]),
        ("11-10-08-CB-05700-00", ["111008CB0570000"]),
        # Multi-parcel — comma, semicolon, whitespace separators
        ("R113312, R113343, R113344", ["R113312", "R113343", "R113344"]),
        ("082W06AB00800,082W06AB00700", ["082W06AB00700", "082W06AB00800"]),
        ("073W26DD15801; 073W26DD15800", ["073W26DD15800", "073W26DD15801"]),
        ("R123 R456", ["R123", "R456"]),
        # Empty / None / whitespace only
        (None, []),
        ("", []),
        ("   ", []),
        (",,,", []),
        # Dedupe within a single APN string
        ("R313810, R313810", ["R313810"]),
        # Clackamas zero-padded digits (both sources use this same format)
        ("00591309", ["00591309"]),
        # Leading/trailing whitespace
        ("  R313810  ", ["R313810"]),
    ],
)
def test_normalize_apn(raw: str | None, expected: list[str]) -> None:
    assert normalize_apn(raw) == expected


def test_normalize_apn_returns_sorted() -> None:
    # Sort enables deterministic storage and display
    assert normalize_apn("R999, R111, R555") == ["R111", "R555", "R999"]


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (["R313810"], ["R313810"], True),
        (["R313810"], ["r313810"], False),  # caller expected to normalize first
        (["R113312", "R113343"], ["R113343", "R999"], True),  # overlap in R113343
        (["R111"], ["R222"], False),
        ([], ["R313810"], False),
        (None, ["R313810"], False),
        (["R313810"], None, False),
        (None, None, False),
    ],
)
def test_apn_match(
    a: list[str] | None, b: list[str] | None, expected: bool
) -> None:
    assert apn_match(a, b) is expected
