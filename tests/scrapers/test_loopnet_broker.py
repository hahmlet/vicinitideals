"""Unit tests for app/scrapers/loopnet_broker."""

from __future__ import annotations

import pytest

from app.scrapers.loopnet_broker import (
    extract_brokers_from_sale_details,
    parse_broker_slug,
    split_full_name,
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        # Standard pattern with listing ID + anchor
        (
            "https://www.loopnet.com/commercial-real-estate-brokers/profile/jeffrey-weitz/mzwstflb/38985870#RealEstateAgent",
            "mzwstflb",
        ),
        # Without trailing listing ID
        (
            "https://www.loopnet.com/commercial-real-estate-brokers/profile/thomas-tsai/zxz0drxb/",
            "zxz0drxb",
        ),
        # Mixed-case slug → lowercased
        (
            "https://www.loopnet.com/commercial-real-estate-brokers/profile/jane-doe/AbCd1234/",
            "abcd1234",
        ),
        # Missing/garbage URLs
        (None, None),
        ("", None),
        ("https://www.loopnet.com/Listing/123/", None),
        # Slug must be 4-20 chars; "y" fails the length floor
        ("https://example.com/profile/x/y/z/", None),
        # Accepts any host as long as slug pattern matches
        ("https://example.com/profile/jane-doe/abcd1234/", "abcd1234"),
    ],
)
def test_parse_broker_slug(url: str | None, expected: str | None) -> None:
    assert parse_broker_slug(url) == expected


def test_extract_brokers_from_sale_details_basic() -> None:
    sd = {
        "broker": [
            {
                "type": "RealEstateAgent",
                "name": "Jordan Carter",
                "url": "https://www.loopnet.com/commercial-real-estate-brokers/profile/jordan-carter/abc12345/12345#RealEstateAgent",
                "image": "https://x.com/jordan.jpg",
                "worksFor": {
                    "type": "Organization",
                    "name": "Kidder Mathews",
                    "logo": "https://x.com/km.png",
                    "url": "https://www.loopnet.com/company/kidder-mathews/portland-or/8rfzmd0l/",
                },
            },
            {
                "type": "RealEstateAgent",
                "name": "Second Broker",
                "url": "https://www.loopnet.com/commercial-real-estate-brokers/profile/second-broker/def67890/",
                "image": None,
                "worksFor": {"name": "Other Co", "logo": None, "url": None},
            },
        ],
    }
    out = extract_brokers_from_sale_details(sd)
    assert len(out) == 2
    assert out[0]["loopnet_broker_id"] == "abc12345"
    assert out[0]["name"] == "Jordan Carter"
    assert out[0]["firm_name"] == "Kidder Mathews"
    assert out[1]["loopnet_broker_id"] == "def67890"
    assert out[1]["firm_name"] == "Other Co"


def test_extract_brokers_handles_missing_or_malformed() -> None:
    assert extract_brokers_from_sale_details({}) == []
    assert extract_brokers_from_sale_details({"broker": None}) == []
    assert extract_brokers_from_sale_details({"broker": "not a list"}) == []
    out = extract_brokers_from_sale_details({"broker": [None, "string", {"name": "OK"}]})
    assert len(out) == 1
    assert out[0]["name"] == "OK"
    assert out[0]["loopnet_broker_id"] is None


@pytest.mark.parametrize(
    ("full", "first", "last"),
    [
        ("Jordan Carter", "Jordan", "Carter"),
        ("Jim Wierson II", "Jim", "Wierson II"),
        ("Greg Nesting", "Greg", "Nesting"),
        ("Madonna", "Madonna", None),
        ("  Jane   Smith  ", "Jane", "Smith"),
        (None, None, None),
        ("", None, None),
    ],
)
def test_split_full_name(full: str | None, first: str | None, last: str | None) -> None:
    assert split_full_name(full) == (first, last)
