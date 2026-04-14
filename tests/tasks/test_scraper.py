from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from unittest.mock import patch
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from vicinitideals.models.base import Base
from vicinitideals.models.broker import Broker, Brokerage
from vicinitideals.models.ingestion import DedupCandidate, DedupStatus, IngestJob, SavedSearchCriteria
from vicinitideals.models.org import Organization, User
from vicinitideals.models.project import Project, ScrapedListing
from vicinitideals.schemas.broker import BrokerCreate
from vicinitideals.schemas.scraped_listing import ScrapedListingCreate
from vicinitideals.tasks.scraper import (
    _build_listing_values,
    _scrape_crexi,
    _scrape_listings,
    upsert_brokers,
    upsert_scraped_listings,
)


@pytest.fixture
async def test_session_factory(tmp_path):
    test_engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'stage1c_scraper.db'}",
        future=True,
    )
    session_factory = async_sessionmaker(
        bind=test_engine,
        expire_on_commit=False,
        autoflush=False,
    )

    async with test_engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=cast(
                    list,
                    [
                        Organization.__table__,
                        User.__table__,
                        Project.__table__,
                        Brokerage.__table__,
                        Broker.__table__,
                        IngestJob.__table__,
                        SavedSearchCriteria.__table__,
                        ScrapedListing.__table__,
                        DedupCandidate.__table__,
                    ],
                ),
            )
        )

    async with session_factory() as session:
        org = Organization(name="Stage 1C Test Org", slug=f"stage1c-{uuid4().hex[:8]}")
        session.add(org)
        await session.flush()
        session.add(User(org_id=org.id, name="Stage 1C Test User"))
        await session.commit()

    try:
        yield session_factory
    finally:
        await test_engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("username", "password", "expect_proxy"),
    [
        ("testuser", "testpass", True),
        ("", "", False),
    ],
)
async def test_scrape_listings_proxy_routing_and_persistence(
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory,
    username: str,
    password: str,
    expect_proxy: bool,
) -> None:
    unique_suffix = uuid4().hex
    listing_url = f"https://example.com/listings/{unique_suffix}"
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "vicinitideals.tasks.scraper.settings.lxc134_scrapling_url",
        "http://scrapling.test",
    )
    monkeypatch.setattr(
        "vicinitideals.tasks.scraper.settings.proxyon_residential_username",
        username,
    )
    monkeypatch.setattr(
        "vicinitideals.tasks.scraper.settings.proxyon_residential_password",
        password,
    )
    monkeypatch.setattr(
        "vicinitideals.tasks.scraper.settings.proxyon_residential_host",
        "residential.proxyon.io",
    )
    monkeypatch.setattr(
        "vicinitideals.tasks.scraper.settings.proxyon_residential_port",
        1111,
    )

    monkeypatch.setattr("vicinitideals.tasks.scraper.AsyncSessionLocal", test_session_factory)

    async def fake_post(self, url: str, *, json=None, **kwargs):  # type: ignore[no-untyped-def]
        captured["url"] = url
        captured["json"] = json
        request = httpx.Request("POST", url, json=json)
        return httpx.Response(
            200,
            json=[
                {
                    "listing_url": listing_url,
                    "address": "123 Main St, Gresham, OR 97030",
                    "asking_price": "1000000",
                    "unit_count": 8,
                }
            ],
            request=request,
        )

    job_id: str | None = None
    with patch("httpx.AsyncClient.post", new=fake_post):
        job_id = await _scrape_listings(
            source="loopnet",
            search_params={"city": "Gresham"},
            triggered_by="pytest",
        )

    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload["source"] == "loopnet"
    assert payload["search_params"] == {"city": "Gresham"}

    if expect_proxy:
        assert payload["proxy"] == {
            "http": "http://testuser:testpass@residential.proxyon.io:1111",
            "https": "http://testuser:testpass@residential.proxyon.io:1111",
        }
    else:
        assert "proxy" not in payload

    assert job_id is not None
    job_uuid = UUID(job_id)

    async with test_session_factory() as session:
        ingest_job = await session.get(IngestJob, job_uuid)
        listings = list(
            (
                await session.execute(
                    select(ScrapedListing).where(ScrapedListing.ingest_job_id == job_uuid)
                )
            ).scalars()
        )

        assert ingest_job is not None
        assert ingest_job.status == "completed"
        assert ingest_job.records_fetched == 1
        assert ingest_job.records_new == 1
        assert len(listings) == 1
        assert listings[0].listing_url == listing_url

        await session.execute(delete(ScrapedListing).where(ScrapedListing.ingest_job_id == job_uuid))
        await session.execute(delete(IngestJob).where(IngestJob.id == job_uuid))
        await session.commit()


def test_build_listing_values_maps_crexi_detail_payload_fields() -> None:
    values = _build_listing_values(
        source="crexi",
        ingest_job_id=uuid4(),
        listing_payload={
            "id": 987654,
            "urlSlug": "gresham-multifamily-opportunity",
            "name": "Gresham Multifamily Opportunity",
            "description": "Strong in-place cash flow with value-add upside.",
            "status": "On-Market",
            "activatedOn": "2026-03-15T12:00:00Z",
            "updatedOn": "2026-03-20T08:30:00Z",
            "locations": [
                {
                    "address": "123 Main St",
                    "city": "Gresham",
                    "county": "Multnomah",
                    "state": "OR",
                    "zip": "97030",
                    "lat": 45.5001,
                    "lng": -122.4302,
                }
            ],
            "propertyType": "Multifamily",
            "propertySubType": ["Apartment Building"],
            "investmentType": "ValueAdd",
            "summaryDetails": {
                "Price": "$1,250,000",
                "PricePerItem": "$156,250",
                "PricePerSqFt": "$208.33",
                "SquareFootage": "6000",
                "LotSize": "0.50 AC",
                "Units": "8",
                "YearBuilt": "1986",
                "CapRate": "6.77%",
                "Occupancy": "95%",
                "Apn": "R123456",
                "BrokerCoOp": "Yes",
                "NetRentableArea": "5800",
                "NOI": "$84,625",
            },
        },
    )

    assert values["source"] == "crexi"
    assert values["source_id"] == "987654"
    assert values["source_url"] == "https://www.crexi.com/properties/gresham-multifamily-opportunity"
    assert values["listing_name"] == "Gresham Multifamily Opportunity"
    assert values["street"] == "123 Main St"
    assert values["city"] == "Gresham"
    assert values["state_code"] == "OR"
    assert values["zip_code"] == "97030"
    assert values["property_type"] == "Multifamily"
    assert values["sub_type"] == ["Apartment Building"]
    assert str(values["asking_price"]) == "1250000"
    assert str(values["price_per_unit"]) == "156250"
    assert str(values["price_per_sqft"]) == "208.33"
    assert values["units"] == 8
    assert str(values["lot_sqft"]) == "21780.000000"
    assert str(values["occupancy_pct"]) == "0.95"
    assert str(values["cap_rate"]) == "0.0677"
    assert values["broker_co_op"] is True
    assert values["apn"] == "R123456"
    assert values["status"] == "On-Market"


@pytest.mark.asyncio
async def test_upsert_brokers_and_scraped_listings_refresh_existing_crexi_rows(
    test_session_factory,
) -> None:
    async with test_session_factory() as session:
        ingest_job = IngestJob(source="crexi", triggered_by="pytest", status="running")
        session.add(ingest_job)
        await session.flush()

        broker_id_map = await upsert_brokers(
            [
                BrokerCreate(
                    crexi_broker_id=5001,
                    crexi_global_id="broker-5001",
                    first_name="Sandra",
                    last_name="Matthews",
                    brokerage_name="Realty One Group",
                    thumbnail_url="https://example.com/broker-5001.jpg",
                    number_of_assets=2,
                    is_platinum=True,
                )
            ],
            session,
        )
        assert list(broker_id_map) == [5001]

        listing = ScrapedListingCreate(
            source="crexi",
            source_id="101",
            source_url="https://www.crexi.com/properties/gresham-101",
            listing_name="Gresham 12-Unit",
            status="Active",
            raw_json={
                "id": 101,
                "urlSlug": "gresham-101",
                "status": "Active",
                "name": "Gresham 12-Unit",
                "locations": [{"address": "123 Main St", "city": "Gresham", "state": "OR", "zip": "97030"}],
                "summaryDetails": {
                    "Price": "$1,250,000",
                    "PricePerSqFt": "$208.33",
                    "PricePerItem": "$104,166.67",
                    "CapRate": "6.25%",
                    "Occupancy": "95%",
                    "NOI": "$84,625",
                },
                "brokers": [{"id": 5001}],
            },
        )

        upserted, skipped = await upsert_scraped_listings(
            [listing],
            broker_id_map=broker_id_map,
            session=session,
            ingest_job_id=ingest_job.id,
        )
        assert (upserted, skipped) == (1, 0)

        stored = (
            await session.execute(
                select(ScrapedListing).where(
                    ScrapedListing.source == "crexi",
                    ScrapedListing.source_id == "101",
                )
            )
        ).scalar_one()
        assert stored.broker_id == broker_id_map[5001]
        assert stored.first_seen_at is not None

        preserved_first_seen = datetime(2024, 1, 2, 9, 30)
        old_last_seen = datetime(2024, 1, 2, 10, 0)
        stored.first_seen_at = preserved_first_seen
        stored.last_seen_at = old_last_seen
        await session.flush()

        refreshed_broker_map = await upsert_brokers(
            [
                BrokerCreate(
                    crexi_broker_id=5001,
                    crexi_global_id="broker-5001",
                    first_name="Sandra",
                    last_name="Matthews",
                    brokerage_name="Realty One Capital",
                    thumbnail_url="https://example.com/broker-5001-new.jpg",
                    number_of_assets=9,
                    is_platinum=True,
                )
            ],
            session,
        )
        assert refreshed_broker_map[5001] == broker_id_map[5001]

        refreshed_listing = ScrapedListingCreate(
            source="crexi",
            source_id="101",
            source_url="https://www.crexi.com/properties/gresham-101",
            listing_name="Gresham 12-Unit",
            status="Pending",
            raw_json={
                "id": 101,
                "urlSlug": "gresham-101",
                "status": "Pending",
                "name": "Gresham 12-Unit",
                "locations": [{"address": "123 Main St", "city": "Gresham", "state": "OR", "zip": "97030"}],
                "summaryDetails": {
                    "Price": "$1,300,000",
                    "PricePerSqFt": "$216.67",
                    "PricePerItem": "$108,333.33",
                    "CapRate": "6.50%",
                    "Occupancy": "96%",
                    "NOI": "$88,000",
                },
                "brokers": [{"id": 5001}],
            },
        )

        upserted, skipped = await upsert_scraped_listings(
            [refreshed_listing],
            broker_id_map=refreshed_broker_map,
            session=session,
            ingest_job_id=ingest_job.id,
        )
        assert (upserted, skipped) == (0, 1)

        broker = (
            await session.execute(select(Broker).where(Broker.crexi_broker_id == 5001))
        ).scalar_one()
        brokerage = (
            await session.execute(select(Brokerage).where(Brokerage.name == "Realty One Capital"))
        ).scalar_one()
        await session.refresh(stored)

        assert broker.number_of_assets == 9
        assert broker.thumbnail_url == "https://example.com/broker-5001-new.jpg"
        assert broker.brokerage_id == brokerage.id
        assert brokerage.crexi_name == "Realty One Capital"
        assert stored.asking_price == Decimal("1300000")
        assert stored.status == "Pending"
        assert stored.first_seen_at == preserved_first_seen
        assert stored.last_seen_at is not None and stored.last_seen_at != old_last_seen


@pytest.mark.asyncio
async def test_scrape_crexi_returns_ingest_summary(
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory,
) -> None:
    monkeypatch.setattr("vicinitideals.tasks.scraper.AsyncSessionLocal", test_session_factory)

    async def fake_fetch_all(self) -> tuple[list[ScrapedListingCreate], list[BrokerCreate]]:
        return (
            [
                ScrapedListingCreate(
                    source="crexi",
                    source_id="201",
                    source_url="https://www.crexi.com/properties/gresham-201",
                    listing_name="Gresham 20-Unit",
                    status="Active",
                    raw_json={
                        "id": 201,
                        "urlSlug": "gresham-201",
                        "status": "Active",
                        "name": "Gresham 20-Unit",
                        "locations": [{"address": "200 Oak St", "city": "Gresham", "state": "OR", "zip": "97030"}],
                        "summaryDetails": {"Price": "$2,000,000", "Units": "20"},
                        "brokers": [{"id": 6001}],
                    },
                )
            ],
            [
                BrokerCreate(
                    crexi_broker_id=6001,
                    crexi_global_id="broker-6001",
                    first_name="Jordan",
                    last_name="Lee",
                    brokerage_name="NW Apartments",
                    thumbnail_url="https://example.com/broker-6001.jpg",
                    number_of_assets=4,
                )
            ],
        )

    monkeypatch.setattr("vicinitideals.tasks.scraper.CrxiScraper.fetch_all", fake_fetch_all)

    result = await _scrape_crexi(triggered_by="pytest")

    assert result["upserted"] == 1
    assert result["skipped"] == 0
    assert result["brokers"] == 1
    assert result["source"] == "crexi"
    assert result["triggered_by"] == "pytest"
    assert result["records_fetched"] == 1
    assert result["records_flagged_review"] == 0
    assert UUID(result["ingest_job_id"])
    assert UUID(result["trace_id"])
    assert datetime.fromisoformat(result["started_at"])
    assert datetime.fromisoformat(result["completed_at"])
    assert int(result["duration_ms"]) >= 0


@pytest.mark.asyncio
async def test_scrape_listings_marks_matching_saved_search_criteria(
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory,
) -> None:
    listing_url = f"https://example.com/listings/{uuid4().hex}"

    monkeypatch.setattr(
        "vicinitideals.tasks.scraper.settings.lxc134_scrapling_url",
        "http://scrapling.test",
    )
    monkeypatch.setattr("vicinitideals.tasks.scraper.AsyncSessionLocal", test_session_factory)

    async with test_session_factory() as session:
        user = (await session.execute(select(User))).scalar_one()
        session.add(
            SavedSearchCriteria(
                user_id=user.id,
                name="Gresham 5-20 units",
                min_units=5,
                max_units=20,
                max_price=Decimal("1500000"),
                zip_codes=["97030"],
                sources=["loopnet"],
                active=True,
            )
        )
        await session.commit()

    async def fake_post(self, url: str, *, json=None, **kwargs):  # type: ignore[no-untyped-def]
        request = httpx.Request("POST", url, json=json)
        return httpx.Response(
            200,
            json=[
                {
                    "listing_url": listing_url,
                    "location": {
                        "address": "123 Main St",
                        "city": "Gresham",
                        "state": "OR",
                        "zip": "97030",
                    },
                    "asking_price": "1200000",
                    "unit_count": 12,
                }
            ],
            request=request,
        )

    with patch("httpx.AsyncClient.post", new=fake_post):
        job_id = await _scrape_listings(
            source="loopnet",
            search_params={"city": "Gresham"},
            triggered_by="pytest",
        )

    async with test_session_factory() as session:
        job_uuid = UUID(job_id)
        ingest_job = await session.get(IngestJob, job_uuid)
        listing = (
            await session.execute(
                select(ScrapedListing).where(ScrapedListing.ingest_job_id == job_uuid)
            )
        ).scalar_one()

        assert ingest_job is not None
        assert ingest_job.status == "completed"
        assert listing.matches_saved_criteria is True


@pytest.mark.asyncio
async def test_scrape_crexi_creates_pending_dedup_candidates_for_new_vs_existing_listings(
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory,
) -> None:
    monkeypatch.setattr("vicinitideals.tasks.scraper.AsyncSessionLocal", test_session_factory)

    async with test_session_factory() as session:
        prior_job = IngestJob(source="loopnet", triggered_by="seed", status="completed")
        session.add(prior_job)
        await session.flush()

        existing_listing = ScrapedListing(
            ingest_job_id=prior_job.id,
            source="loopnet",
            source_id="loopnet-123",
            source_url="https://example.com/listings/existing-123",
            address_normalized="123 MAIN ST GRESHAM OR 97030",
            address_raw="123 Main St, Gresham, OR 97030",
            is_new=True,
            matches_saved_criteria=False,
        )
        session.add(existing_listing)
        await session.commit()

    async def fake_fetch_all(self) -> tuple[list[ScrapedListingCreate], list[BrokerCreate]]:
        return (
            [
                ScrapedListingCreate(
                    source="crexi",
                    source_id="202",
                    source_url="https://www.crexi.com/properties/gresham-202",
                    listing_name="Gresham Duplicate Candidate",
                    status="Active",
                    raw_json={
                        "id": 202,
                        "urlSlug": "gresham-202",
                        "status": "Active",
                        "name": "Gresham Duplicate Candidate",
                        "locations": [{"address": "123 Main St", "city": "Gresham", "state": "OR"}],
                        "summaryDetails": {"Price": "$1,900,000", "Units": "12"},
                        "brokers": [],
                    },
                )
            ],
            [],
        )

    monkeypatch.setattr("vicinitideals.tasks.scraper.CrxiScraper.fetch_all", fake_fetch_all)

    result = await _scrape_crexi(triggered_by="pytest")
    ingest_job_id = UUID(result["ingest_job_id"])

    async with test_session_factory() as session:
        ingest_job = await session.get(IngestJob, ingest_job_id)
        candidates = list(
            (
                await session.execute(
                    select(DedupCandidate).where(DedupCandidate.ingest_job_id == ingest_job_id)
                )
            ).scalars()
        )

        assert ingest_job is not None
        assert ingest_job.records_flagged_review == 1
        assert len(candidates) == 1
        assert candidates[0].status == DedupStatus.pending
        assert 0.60 <= candidates[0].confidence_score < 0.85
