from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from vicinitideals.schemas.broker import BrokerCreate
from vicinitideals.schemas.scraped_listing import ScrapedListingCreate
from vicinitideals.scrapers.crexi import CrxiScraper, _broker_key, _parse_summary_details


class _FakeResponse:
    def __init__(self, payload: dict | list):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self) -> None:
        return None


class _FakeAsyncSession:
    last_impersonate: str | None = None
    search_skips: list[int] = []
    sleep_calls: list[float] = []

    def __init__(self, *args, impersonate: str | None = None, headers=None, **kwargs):
        _FakeAsyncSession.last_impersonate = impersonate
        self.headers = headers or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, url: str, json: dict | None = None, **kwargs):
        assert url == "https://api.crexi.com/assets/search"
        skip = (json or {}).get("skip", 0)
        _FakeAsyncSession.search_skips.append(skip)
        if skip == 0:
            return _FakeResponse(
                {
                    "data": [
                        {"id": 101, "urlSlug": "gresham-101"},
                        {"id": 102, "urlSlug": "gresham-102"},
                    ],
                    "totalCount": 3,
                }
            )
        if skip == 2:
            return _FakeResponse({"data": [{"id": 103, "urlSlug": "gresham-103"}], "totalCount": 3})
        raise AssertionError(f"Unexpected skip value: {skip}")

    async def get(self, url: str, **kwargs):
        if url.endswith("/101"):
            return _FakeResponse(
                {
                    "id": 101,
                    "urlSlug": "gresham-101",
                    "name": "Gresham 12-Unit",
                    "description": "Value-add multifamily deal.",
                    "status": "Active",
                    "propertyType": "Multifamily",
                    "propertySubType": ["Apartment Building"],
                    "investmentType": "Value Add",
                    "locations": [
                        {
                            "address": "123 Main St",
                            "city": "Gresham",
                            "county": "Multnomah",
                            "state": "OR",
                            "zip": "97030",
                            "lat": 45.5,
                            "lng": -122.43,
                        }
                    ],
                    "summaryDetails": [
                        {"key": "Price", "valueType": "Money", "value": "$1,250,000"},
                        {"key": "CapRate", "valueType": "Percentage", "value": "6.25"},
                        {"key": "Occupancy", "valueType": "Percentage", "value": "95.5"},
                        {"key": "Units", "valueType": "IntegerType", "value": "12"},
                        {"key": "Tenancy", "valueType": "Text", "value": "Value Add"},
                        {"key": "OccupancyDate", "valueType": "Date", "value": "2026-03-01T00:00:00Z"},
                        {"key": "PriceSqFtLand", "valueType": "Range", "value": "20-24"},
                        {"key": "LotSize", "valueType": "Text", "value": "0.50 AC"},
                        {"key": "BrokerCoOp", "valueType": "Text", "value": "Yes"},
                    ],
                }
            )
        if url.endswith("/102"):
            return _FakeResponse(
                {
                    "id": 102,
                    "urlSlug": "gresham-102",
                    "name": "Gresham 8-Unit",
                    "propertyType": "Multifamily",
                    "propertySubType": ["Apartment Building"],
                    "locations": [{"address": "200 Oak St", "city": "Gresham", "state": "OR", "zip": "97030"}],
                    "summaryDetails": [
                        {"key": "Price", "valueType": "Money", "value": "$950,000"},
                        {"key": "Units", "valueType": "IntegerType", "value": "8"},
                    ],
                }
            )
        if url.endswith("/103"):
            return _FakeResponse(
                {
                    "id": 103,
                    "urlSlug": "gresham-103",
                    "name": "Portland 16-Unit",
                    "propertyType": "Multifamily",
                    "propertySubType": ["Apartment Building"],
                    "locations": [{"address": "300 Pine St", "city": "Portland", "state": "OR", "zip": "97205"}],
                    "summaryDetails": [
                        {"key": "Price", "valueType": "Money", "value": "$2,100,000"},
                        {"key": "Units", "valueType": "IntegerType", "value": "16"},
                    ],
                }
            )
        if url.endswith("/101/brokers"):
            return _FakeResponse(
                [
                    {
                        "id": 5001,
                        "globalId": "broker-5001",
                        "firstName": "Sandra",
                        "lastName": "Matthews",
                        "thumbnailUrl": "https://example.com/sandra.jpg",
                        "brokerage": {"name": "Realty One Group"},
                        "numberOfAssets": 2,
                        "isPlatinum": True,
                    }
                ]
            )
        if url.endswith("/102/brokers"):
            return _FakeResponse(
                [
                    {
                        "id": 5001,
                        "globalId": "broker-5001",
                        "firstName": "Sandra",
                        "lastName": "Matthews",
                        "thumbnailUrl": "https://example.com/sandra.jpg",
                        "brokerage": {"name": "Realty One Group"},
                        "numberOfAssets": 2,
                        "isPlatinum": True,
                    },
                    {
                        "id": 5002,
                        "globalId": "broker-5002",
                        "firstName": "Jordan",
                        "lastName": "Lee",
                        "thumbnailUrl": "https://example.com/jordan.jpg",
                        "brokerage": {"name": "NW Apartments"},
                        "numberOfAssets": 9,
                        "isPlatinum": False,
                    },
                ]
            )
        if url.endswith("/103/brokers"):
            return _FakeResponse([])
        raise AssertionError(f"Unexpected URL: {url}")


def test_parse_summary_details_handles_supported_value_types() -> None:
    summary = _parse_summary_details(
        [
            {"key": "Price", "valueType": "Money", "value": "$1,250,000"},
            {"key": "CapRate", "valueType": "Percentage", "value": "6.25"},
            {"key": "Units", "valueType": "IntegerType", "value": "12"},
            {"key": "Tenancy", "valueType": "Text", "value": "Value Add"},
            {"key": "BrokerCoOp", "valueType": "Text", "value": "Yes"},
            {"key": "RentBumps", "valueType": "Array", "value": ["Annual", "3%"]},
            {"key": "OccupancyDate", "valueType": "Date", "value": "2026-03-01T00:00:00Z"},
            {"key": "PriceSqFtLand", "valueType": "Range", "value": "20-24"},
        ]
    )

    assert summary["Price"] == Decimal("1250000")
    assert summary["CapRate"] == Decimal("0.0625")
    assert summary["Units"] == 12
    assert summary["Tenancy"] == "Value Add"
    assert summary["BrokerCoOp"] is True
    assert summary["RentBumps"] == ["Annual", "3%"]
    assert summary["OccupancyDate"] == datetime(2026, 3, 1, 0, 0, tzinfo=UTC)
    assert summary["PriceSqFtLand"] == Decimal("22")


@pytest.mark.asyncio
async def test_fetch_all_paginates_maps_listings_and_deduplicates_brokers(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_sleep(delay: float) -> None:
        _FakeAsyncSession.sleep_calls.append(delay)

    monkeypatch.setattr("vicinitideals.scrapers.crexi.AsyncSession", _FakeAsyncSession)
    monkeypatch.setattr("vicinitideals.scrapers.crexi.asyncio.sleep", _fake_sleep)

    scraper = CrxiScraper(page_size=2, batch_size=2, batch_delay_seconds=0.3)
    listings, brokers = await scraper.fetch_all()

    assert _FakeAsyncSession.last_impersonate == "chrome136"
    assert _FakeAsyncSession.search_skips == [0, 2]
    assert _FakeAsyncSession.sleep_calls == [0.3]

    assert all(isinstance(item, ScrapedListingCreate) for item in listings)
    assert len(listings) == 3

    first = listings[0]
    assert first.source == "crexi"
    assert first.source_id == "101"
    assert first.source_url == "https://www.crexi.com/properties/gresham-101"
    assert first.listing_name == "Gresham 12-Unit"
    assert first.asking_price == Decimal("1250000")
    assert first.cap_rate == Decimal("0.0625")
    assert first.occupancy_pct == Decimal("0.955")
    assert first.units == 12
    assert first.tenancy == "Value Add"
    assert first.price_per_sqft_land == Decimal("22")
    assert first.broker_co_op is True
    assert first.lot_sqft == Decimal("21780.000000")

    assert all(isinstance(item, BrokerCreate) for item in brokers)
    assert len(brokers) == 2
    assert {broker.crexi_broker_id for broker in brokers} == {5001, 5002}
    assert brokers[0].first_name == "Sandra"
    assert brokers[0].brokerage_name == "Realty One Group"
    assert brokers[0].is_platinum is True
    assert brokers[1].brokerage_name == "NW Apartments"
    assert _broker_key({"id": 5001, "globalId": "broker-5001"}) == "crexi:5001"
