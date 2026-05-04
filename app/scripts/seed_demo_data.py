"""Seed demo data: parcels, brokerages, brokers, scraped listings.

Run inside the api container:
  python -m app.scripts.seed_demo_data
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models.broker import Broker, Brokerage
from app.models.org import Organization, User
from app.models.parcel import Parcel
from app.models.project import Project
from app.models.scraped_listing import ScrapedListing


async def seed() -> None:
    async with AsyncSessionLocal() as session:

        # ------------------------------------------------------------------
        # Resolve org + user
        # ------------------------------------------------------------------
        org = (await session.execute(
            select(Organization).order_by(Organization.created_at)
        )).scalars().first()
        if org is None:
            org = Organization(name="Ketch Media", slug="ketch-media")
            session.add(org)
            await session.flush()

        user = (await session.execute(
            select(User).where(User.org_id == org.id).limit(1)
        )).scalars().first()

        # ------------------------------------------------------------------
        # Parcels  (skip if APN already exists)
        # ------------------------------------------------------------------
        parcel_data = [
            dict(
                apn="R123400010",
                address_normalized="N Interstate Ave, Portland, OR 97217",
                address_raw="N INTERSTATE AVE, PORTLAND OR 97217",
                owner_name="Tower Holdings LLC",
                lot_sqft=22450,
                zoning_code="CM2",
                zoning_description="Central Mixed Use 2",
                current_use="Hotel / Motel",
                assessed_value_land=1400000,
                assessed_value_improvements=700000,
                total_assessed_value=2100000,
                year_built=1968,
                building_sqft=33636,
                unit_count=65,
            ),
            dict(
                apn="R698400130",
                address_normalized="619 NE 190th Ave, Gresham, OR 97030",
                address_raw="619 NE 190TH AVE, GRESHAM OR 97030",
                owner_name="Oak Street Properties LLC",
                lot_sqft=8500,
                zoning_code="R2",
                zoning_description="Low-Density Residential",
                current_use="Multifamily Residential",
                assessed_value_land=210000,
                assessed_value_improvements=275000,
                total_assessed_value=485000,
                year_built=1962,
                building_sqft=6200,
                unit_count=12,
            ),
            dict(
                apn="R245600044",
                address_normalized="4821 SE Powell Blvd, Portland, OR 97206",
                address_raw="4821 SE POWELL BLVD, PORTLAND OR 97206",
                owner_name="Powell Street Ventures",
                lot_sqft=4200,
                zoning_code="CM1",
                zoning_description="Central Mixed Use 1",
                current_use="Retail Storefront",
                assessed_value_land=420000,
                assessed_value_improvements=300000,
                total_assessed_value=720000,
                year_built=1978,
                building_sqft=4800,
                unit_count=0,
            ),
            dict(
                apn="R889100033",
                address_normalized="16111 E Burnside St, Portland, OR 97233",
                address_raw="16111 E BURNSIDE ST, PORTLAND OR 97233",
                owner_name="Burnside Holdings Inc",
                lot_sqft=5800,
                zoning_code="R2",
                zoning_description="Low-Density Residential",
                current_use="Single Family Residential",
                assessed_value_land=180000,
                assessed_value_improvements=140000,
                total_assessed_value=320000,
                year_built=1951,
                building_sqft=1800,
                unit_count=1,
            ),
            dict(
                apn="R567800012",
                address_normalized="4405 SE Woodstock Blvd, Portland, OR 97206",
                address_raw="4405 SE WOODSTOCK BLVD, PORTLAND OR 97206",
                owner_name="Woodstock Land Partners",
                lot_sqft=6100,
                zoning_code="CM2",
                zoning_description="Central Mixed Use 2",
                current_use="Vacant Land",
                assessed_value_land=360000,
                assessed_value_improvements=150000,
                total_assessed_value=510000,
                year_built=1938,
                building_sqft=5100,
                unit_count=0,
            ),
        ]

        parcels: dict[str, Parcel] = {}
        for pd in parcel_data:
            existing = (await session.execute(
                select(Parcel).where(Parcel.apn == pd["apn"])
            )).scalars().first()
            if existing:
                parcels[pd["apn"]] = existing
                print(f"  parcel {pd['apn']} already exists, skipping")
                continue
            p = Parcel(**pd, scraped_at=datetime.now(UTC))
            session.add(p)
            await session.flush()
            parcels[pd["apn"]] = p
            print(f"  created parcel {pd['apn']}")

        # ------------------------------------------------------------------
        # Brokerages + Brokers
        # ------------------------------------------------------------------
        brokerage_data = [
            dict(name="Pacific NW Commercial", city="Portland", state_code="OR"),
            dict(name="Norris & Stevens", city="Portland", state_code="OR"),
            dict(name="Marcus & Millichap", city="Portland", state_code="OR"),
        ]
        brokerages: dict[str, Brokerage] = {}
        for bd in brokerage_data:
            existing = (await session.execute(
                select(Brokerage).where(Brokerage.name == bd["name"])
            )).scalars().first()
            if existing:
                brokerages[bd["name"]] = existing
                continue
            b = Brokerage(**bd)
            session.add(b)
            await session.flush()
            brokerages[bd["name"]] = b
            print(f"  created brokerage {bd['name']}")

        broker_data = [
            dict(first_name="David", last_name="Seto", email="dseto@pacificnwcommercial.com",
                 phone="503-555-0101", brokerage_name="Pacific NW Commercial",
                 license_number="200512345", license_state="OR", number_of_assets=24),
            dict(first_name="Rachel", last_name="Kim", email="rkim@norrisstevens.com",
                 phone="503-555-0202", brokerage_name="Norris & Stevens",
                 license_number="200678901", license_state="OR", number_of_assets=17),
            dict(first_name="Marcus", last_name="Huang", email="mhuang@marcusmillichap.com",
                 phone="503-555-0303", brokerage_name="Marcus & Millichap",
                 license_number="200734567", license_state="OR", number_of_assets=41,
                 is_platinum=True),
        ]
        brokers: dict[str, Broker] = {}
        for bd in broker_data:
            bname = bd.pop("brokerage_name")
            full_name = f"{bd['first_name']} {bd['last_name']}"
            existing = (await session.execute(
                select(Broker)
                .where(Broker.first_name == bd["first_name"])
                .where(Broker.last_name == bd["last_name"])
            )).scalars().first()
            if existing:
                brokers[full_name] = existing
                continue
            br = Broker(**bd, brokerage_id=brokerages[bname].id)
            session.add(br)
            await session.flush()
            brokers[full_name] = br
            print(f"  created broker {full_name}")

        # ------------------------------------------------------------------
        # Scraped Listings
        # ------------------------------------------------------------------
        listing_data = [
            dict(
                source="crexi", source_id="4f2a8e1c-b3d0", source_url="https://www.crexi.com/properties/4f2a8e1c",
                address_raw="N Interstate Ave, Portland, OR 97217",
                address_normalized="N Interstate Ave, Portland, OR 97217",
                street="N Interstate Ave", city="Portland", state_code="OR", zip_code="97217",
                property_type="Multifamily", asking_price=4200000, units=65,
                gba_sqft=33636, year_built=1968, status="Active",
                listing_name="N Interstate Ave — 65-Unit Hotel Conversion",
                first_seen_at=datetime(2026, 3, 10, 9, 14, tzinfo=UTC),
                last_seen_at=datetime(2026, 4, 3, 6, 0, tzinfo=UTC),
                is_new=False, apn="R123400010",
                broker_key="David Seto",
            ),
            dict(
                source="loopnet", source_id="8b3c1d22-aa01", source_url="https://www.loopnet.com/listing/8b3c1d22",
                address_raw="619 NE 190th Ave, Gresham, OR 97030",
                address_normalized="619 NE 190th Ave, Gresham, OR 97030",
                street="619 NE 190th Ave", city="Gresham", state_code="OR", zip_code="97030",
                property_type="Multifamily", asking_price=825000, units=12,
                gba_sqft=6200, year_built=1962, cap_rate=6.2, status="Active",
                listing_name="619 NE 190th Ave — 12-Unit Apartment",
                first_seen_at=datetime(2026, 3, 14, 11, 2, tzinfo=UTC),
                last_seen_at=datetime(2026, 4, 3, 6, 0, tzinfo=UTC),
                is_new=False, apn="R698400130",
                broker_key="Rachel Kim",
            ),
            dict(
                source="crexi", source_id="a1b2c3d4-e5f6", source_url="https://www.crexi.com/properties/a1b2c3d4",
                address_raw="2211 NE Broadway, Portland, OR 97232",
                address_normalized="2211 NE Broadway, Portland, OR 97232",
                street="2211 NE Broadway", city="Portland", state_code="OR", zip_code="97232",
                property_type="Multifamily", asking_price=1950000, units=18,
                gba_sqft=11200, year_built=1955, cap_rate=5.8, status="Active",
                listing_name="2211 NE Broadway — 18-Unit Apartment",
                first_seen_at=datetime(2026, 4, 3, 8, 0, tzinfo=UTC),
                last_seen_at=datetime(2026, 4, 3, 8, 0, tzinfo=UTC),
                is_new=True, apn=None,
                broker_key="Marcus Huang",
            ),
            dict(
                source="crexi", source_id="d4e5f6a7-b8c9", source_url="https://www.crexi.com/properties/d4e5f6a7",
                address_raw="4444 N Williams Ave, Portland, OR 97217",
                address_normalized="4444 N Williams Ave, Portland, OR 97217",
                street="4444 N Williams Ave", city="Portland", state_code="OR", zip_code="97217",
                property_type="Multifamily", asking_price=2400000, units=22,
                gba_sqft=14300, year_built=1948, cap_rate=5.1, status="Active",
                listing_name="4444 N Williams Ave — 22-Unit",
                first_seen_at=datetime(2026, 4, 3, 10, 0, tzinfo=UTC),
                last_seen_at=datetime(2026, 4, 3, 10, 0, tzinfo=UTC),
                is_new=True, apn=None,
                broker_key="David Seto",
            ),
            dict(
                source="loopnet", source_id="f9e8d7c6-b5a4", source_url="https://www.loopnet.com/listing/f9e8d7c6",
                address_raw="4821 SE Powell Blvd, Portland, OR 97206",
                address_normalized="4821 SE Powell Blvd, Portland, OR 97206",
                street="4821 SE Powell Blvd", city="Portland", state_code="OR", zip_code="97206",
                property_type="Retail", asking_price=875000, units=None,
                gba_sqft=4800, year_built=1978, status="Under Contract",
                listing_name="4821 SE Powell Blvd — Retail Conversion Opportunity",
                first_seen_at=datetime(2026, 3, 1, 9, 0, tzinfo=UTC),
                last_seen_at=datetime(2026, 4, 2, 6, 0, tzinfo=UTC),
                is_new=False, apn="R245600044",
                broker_key="Rachel Kim",
            ),
        ]

        listings: list[ScrapedListing] = []
        for ld in listing_data:
            broker_key = ld.pop("broker_key")
            existing = (await session.execute(
                select(ScrapedListing)
                .where(ScrapedListing.source == ld["source"])
                .where(ScrapedListing.source_id == ld["source_id"])
            )).scalars().first()
            if existing:
                listings.append(existing)
                print(f"  listing {ld['source_id']} already exists, skipping")
                continue
            # Map aliased fields
            lobj = ScrapedListing(
                source=ld["source"],
                source_id=ld["source_id"],
                source_url=ld["source_url"],
                address_raw=ld.get("address_raw"),
                address_normalized=ld.get("address_normalized"),
                street=ld.get("street"),
                city=ld.get("city"),
                state_code=ld.get("state_code"),
                zip_code=ld.get("zip_code"),
                property_type=ld.get("property_type"),
                asking_price=ld.get("asking_price"),
                units=ld.get("units"),
                gba_sqft=ld.get("gba_sqft"),
                year_built=ld.get("year_built"),
                cap_rate=ld.get("cap_rate"),
                status=ld.get("status"),
                listing_name=ld.get("listing_name"),
                first_seen_at=ld.get("first_seen_at"),
                last_seen_at=ld.get("last_seen_at"),
                is_new=ld.get("is_new", True),
                apn=ld.get("apn"),
                broker_id=brokers[broker_key].id if broker_key in brokers else None,
            )
            session.add(lobj)
            await session.flush()
            listings.append(lobj)
            print(f"  created listing {ld['source_id']}")

        await session.commit()
        print("\nDone.")


if __name__ == "__main__":
    asyncio.run(seed())
