"""Unit tests for app/scrapers/loopnet.py — polygon clip, field mapping,
MF classification, budget guard.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.scrapers import loopnet
from app.scrapers.loopnet import (
    BudgetExhausted,
    BudgetGuard,
    _is_last_day_of_month,
    classify_categories,
    classify_from_bulk,
    classify_lease_from_bulk,
    classify_multifamily,
    clip_to_polygon,
    load_polygons,
    map_lease_to_scraped_listing,
    map_to_scraped_listing,
    parse_target_ed_categories,
    point_in_polygon,
    polygon_bbox,
    polygon_tags_for_point,
    should_fetch_extended_details,
    should_fetch_sale_details_after_bulk,
    should_ingest_lease_after_bulk,
)


# ---------------------------------------------------------------------------
# Polygon tests
# ---------------------------------------------------------------------------

SQUARE = [[0.0, 0.0], [0.0, 10.0], [10.0, 10.0], [10.0, 0.0], [0.0, 0.0]]


def test_polygon_bbox_order() -> None:
    assert polygon_bbox(SQUARE) == (0.0, 0.0, 10.0, 10.0)


def test_point_in_polygon_inside() -> None:
    assert point_in_polygon(SQUARE, 5.0, 5.0) is True


def test_point_in_polygon_outside() -> None:
    assert point_in_polygon(SQUARE, 15.0, 5.0) is False
    assert point_in_polygon(SQUARE, -1.0, 5.0) is False
    assert point_in_polygon(SQUARE, 5.0, 15.0) is False


def test_clip_to_polygon_filters_rows() -> None:
    rows = [
        {"listingId": "in", "coordinations": [[5.0, 5.0]]},
        {"listingId": "out", "coordinations": [[15.0, 5.0]]},
        {"listingId": "mixed_first_in", "coordinations": [[3.0, 3.0], [15.0, 5.0]]},
        {"listingId": "no_coords", "coordinations": []},
    ]
    kept = clip_to_polygon(rows, SQUARE)
    assert {r["listingId"] for r in kept} == {"in", "mixed_first_in"}


def test_load_polygons_reads_file(tmp_path: Path) -> None:
    p = tmp_path / "polys.json"
    p.write_text(
        json.dumps([
            {"name": "active", "is_active": True, "points": SQUARE},
            {"name": "inactive", "is_active": False, "points": SQUARE},
        ])
    )
    polygons = load_polygons(str(p))
    assert len(polygons) == 1
    assert polygons[0]["name"] == "active"


# ---------------------------------------------------------------------------
# MF classification
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"propertyFacts": {"propertyType": "Multifamily"}}, True),
        ({"propertyFacts": {"propertyType": "Multi-Family"}}, True),
        ({"propertyFacts": {"propertyType": "multifamily"}}, True),
        ({"propertyFacts": {"propertyType": "MULTI-FAMILY"}}, True),
        ({"propertyFacts": {"propertyType": "Retail"}}, False),
        ({"propertyFacts": {"propertyType": "Office"}}, False),
        ({"propertyFacts": {"propertyType": None}}, False),
        ({}, False),
    ],
)
def test_classify_multifamily(raw: dict, expected: bool) -> None:
    assert classify_multifamily(raw) is expected


# ---------------------------------------------------------------------------
# Full category classifier — multifamily, land, mixed_use (zoning-only), etc.
# ---------------------------------------------------------------------------

def test_classify_categories_multifamily() -> None:
    assert classify_categories(
        {"propertyFacts": {"propertyType": "Multifamily"}}
    ) == {"multifamily"}


def test_classify_categories_land() -> None:
    assert classify_categories({"propertyFacts": {"propertyType": "Land"}}) == {"land"}


def test_classify_categories_mixed_use_from_zoning() -> None:
    # Real zoning string from Halsey St listing
    tags = classify_categories({
        "propertyFacts": {
            "propertyType": "Retail",
            "propertySubtype": "Storefront Retail/Residential",
            "zoning": "CM2d(MU-U) - Commercial mixed-use",
        }
    })
    assert "retail" in tags
    assert "mixed_use" in tags


def test_classify_categories_subtype_alone_does_not_trigger_mixed_use() -> None:
    """Per user direction: subtype-only hints don't trigger mixed_use;
    only zoning does. Protects against noisy subtype classifications."""
    tags = classify_categories({
        "propertyFacts": {
            "propertyType": "Retail",
            "propertySubtype": "Storefront Retail/Residential",
            # no zoning MU signal
        }
    })
    assert "mixed_use" not in tags
    assert "retail" in tags


def test_classify_categories_explicit_mixed_use_primary() -> None:
    tags = classify_categories(
        {"propertyFacts": {"propertyType": "Mixed-Use"}}
    )
    assert "mixed_use" in tags


def test_classify_categories_unknown_falls_back_to_other() -> None:
    assert classify_categories({"propertyFacts": {"propertyType": "Weird Type"}}) == {"other"}


def test_classify_categories_empty_returns_other() -> None:
    assert classify_categories({}) == {"other"}


# ---------------------------------------------------------------------------
# Polygon tagging + ED fetch policy
# ---------------------------------------------------------------------------

def test_polygon_tags_for_point_matches_active_polygons() -> None:
    polygons = [
        {"name": "a", "is_active": True, "points": SQUARE},
        {"name": "b", "is_active": True, "points": [[5, 5], [5, 20], [20, 20], [20, 5], [5, 5]]},
        {"name": "c_inactive", "is_active": False, "points": SQUARE},
    ]
    # Point (7,7) is inside a AND b, but not c (inactive even though shape would match)
    assert set(polygon_tags_for_point(polygons, 7.0, 7.0)) == {"a", "b"}
    assert polygon_tags_for_point(polygons, 100.0, 100.0) == []
    assert polygon_tags_for_point(polygons, None, None) == []


def test_should_fetch_extended_details_target_widening() -> None:
    targets = {"multifamily", "land", "mixed_use"}
    # Target polygon + MF → yes
    assert should_fetch_extended_details({"multifamily"}, {"target"}, targets) is True
    # Target polygon + Land → yes (widened)
    assert should_fetch_extended_details({"land"}, {"target"}, targets) is True
    # Target polygon + Retail alone → no
    assert should_fetch_extended_details({"retail"}, {"target"}, targets) is False
    # Target polygon + Retail + mixed_use → yes (mixed_use qualifies)
    assert should_fetch_extended_details({"retail", "mixed_use"}, {"target"}, targets) is True


def test_should_fetch_extended_details_comp_only_is_strict() -> None:
    targets = {"multifamily", "land", "mixed_use"}
    # Comp-only + MF → yes
    assert should_fetch_extended_details({"multifamily"}, {"comp_only"}, targets) is True
    # Comp-only + Land → NO (comps stay MF-focused)
    assert should_fetch_extended_details({"land"}, {"comp_only"}, targets) is False
    # Comp-only + Mixed-Use → NO
    assert should_fetch_extended_details({"mixed_use"}, {"comp_only"}, targets) is False


def test_should_fetch_extended_details_in_both_tiers() -> None:
    targets = {"multifamily", "land", "mixed_use"}
    # In both target and comp polygons + Land → yes (target rule wins)
    assert should_fetch_extended_details(
        {"land"}, {"target", "comp_only"}, targets
    ) is True


def test_parse_target_ed_categories() -> None:
    assert parse_target_ed_categories("multifamily,land,mixed_use") == {
        "multifamily", "land", "mixed_use"
    }
    assert parse_target_ed_categories("  multifamily , LAND ") == {"multifamily", "land"}
    assert parse_target_ed_categories("") == set()


# ---------------------------------------------------------------------------
# Bulk-triage classifier (classify_from_bulk)
# ---------------------------------------------------------------------------

def _mk_bulk_row(listing_type: str, subtype: str) -> dict:
    """Build a bulkDetails-shaped row with the given listingType and subtype label."""
    return {
        "listingId": "test",
        "listingType": listing_type,
        "shortPropertyFacts": [
            ["Built in 2000", "10,000 SF"],            # display text block
            [[subtype], ["10K", "SF"], ["5", "Units"]],  # structured block
        ],
    }


def test_classify_from_bulk_apartments_is_multifamily() -> None:
    assert classify_from_bulk(_mk_bulk_row("PropertyForSale", "Apartments")) == {"multifamily"}


def test_classify_from_bulk_land_from_listing_type() -> None:
    assert classify_from_bulk(_mk_bulk_row("LandForSale", "Commercial")) == {"land"}


@pytest.mark.parametrize(
    ("subtype", "expected"),
    [
        ("Office", "office"),
        ("Warehouse", "industrial"),
        ("Manufacturing", "industrial"),
        ("Freestanding Retail", "retail"),
        ("Storefront", "retail"),
        ("Restaurant", "retail"),
        ("Medical", "healthcare"),
        ("Hotel", "hospitality"),
        ("Flex", "flex"),
    ],
)
def test_classify_from_bulk_property_for_sale_subtypes(subtype: str, expected: str) -> None:
    assert expected in classify_from_bulk(_mk_bulk_row("PropertyForSale", subtype))


def test_classify_from_bulk_unknown_returns_other() -> None:
    assert classify_from_bulk(_mk_bulk_row("PropertyForSale", "Weird Subtype")) == {"other"}


def test_classify_from_bulk_missing_structured_block() -> None:
    # Response with only the text block (malformed / partial row)
    row = {"listingType": "PropertyForSale", "shortPropertyFacts": [["a", "b"]]}
    # Should not crash; returns "other"
    assert classify_from_bulk(row) == {"other"}


def test_should_fetch_sale_details_after_bulk_in_target_checks_zoning_for_mu() -> None:
    targets = {"multifamily", "land", "mixed_use"}
    # Retail in target polygon → might be MU via zoning → fetch SD
    assert should_fetch_sale_details_after_bulk(
        {"retail"}, {"target"}, targets
    ) is True
    # Office in target polygon → same
    assert should_fetch_sale_details_after_bulk(
        {"office"}, {"target"}, targets
    ) is True
    # Industrial in target → NOT fetched (zoning won't rescue)
    assert should_fetch_sale_details_after_bulk(
        {"industrial"}, {"target"}, targets
    ) is False


def _mk_lease_bulk_row(listing_type: str, subtype: str) -> dict:
    return {
        "listingId": "test",
        "listingType": listing_type,
        "shortPropertyFacts": [
            ["text"],
            [[subtype], ["10K", "SF"]],
        ],
    }


@pytest.mark.parametrize(
    ("subtype", "expected_tag"),
    [
        ("Apartments", "multifamily"),
        ("Office/Residential", "mixed_use"),  # residential hint
        ("Mixed", "mixed_use"),
        ("Office", "office"),
        ("Strip Center", "retail"),
        ("Warehouse", "industrial"),
        ("Medical", "healthcare"),
    ],
)
def test_classify_lease_from_bulk_subtypes(subtype: str, expected_tag: str) -> None:
    tags = classify_lease_from_bulk(
        _mk_lease_bulk_row("PropertyDirectSpaceForLease", subtype)
    )
    assert expected_tag in tags


def test_should_ingest_lease_after_bulk_keeps_mf_and_mixed_use() -> None:
    assert should_ingest_lease_after_bulk({"multifamily"}) is True
    assert should_ingest_lease_after_bulk({"mixed_use"}) is True
    assert should_ingest_lease_after_bulk({"multifamily", "office"}) is True
    # Commercial-only leases → skip
    assert should_ingest_lease_after_bulk({"retail"}) is False
    assert should_ingest_lease_after_bulk({"office"}) is False
    assert should_ingest_lease_after_bulk({"industrial"}) is False


def test_should_fetch_sale_details_after_bulk_comp_only_skips_non_mf() -> None:
    targets = {"multifamily", "land", "mixed_use"}
    # Comp-only + Land → skip (comp library is MF-focused)
    assert should_fetch_sale_details_after_bulk(
        {"land"}, {"comp_only"}, targets
    ) is False
    # Comp-only + Retail → skip
    assert should_fetch_sale_details_after_bulk(
        {"retail"}, {"comp_only"}, targets
    ) is False
    # Comp-only + MF → fetch
    assert should_fetch_sale_details_after_bulk(
        {"multifamily"}, {"comp_only"}, targets
    ) is True


# ---------------------------------------------------------------------------
# Lease mapping
# ---------------------------------------------------------------------------

def test_map_lease_to_scraped_listing_extracts_first_space_rent() -> None:
    lease = {
        "listingId": 28774897,
        "title": "Gresham Station Medical Plaza",
        "location": {
            "streetAddress": "831 NW Council Dr",
            "addressLocality": "Gresham",
            "addressRegion": "OR",
            "zipCode": "97030",
        },
        "category": "Retail",
        "spaces": [
            {"totalSpace": "2,005 SF", "sfPerYear": "$28.00"},
            {"totalSpace": "4,020 SF", "sfPerYear": "$26.00"},
        ],
    }
    mapped = map_lease_to_scraped_listing(
        lease, listing_id="28774897", lat=45.51, lng=-122.44,
    )
    assert mapped["source"] == "loopnet_lease"
    assert mapped["source_id"] == "28774897"
    assert mapped["investment_type"] == "Lease"
    assert mapped["price_per_sqft"] == Decimal("28.00")
    assert mapped["street"] == "831 NW Council Dr"


# ---------------------------------------------------------------------------
# Field mapping: SaleDetails + ExtendedDetails → dict
# ---------------------------------------------------------------------------

SAMPLE_SALE_DETAILS = {
    "title": "2816 NE Halsey St",
    "subTitle": "3,020 SF 100% Leased Retail Building",
    "location": {
        "addressCountry": "US",
        "addressLocality": "Portland",
        "addressRegion": "OR",
        "streetAddress": "2816 NE Halsey St",
        "zipCode": "97232",
        "city": "Portland",
        "state": "OR",
    },
    "propertyFacts": {
        "saleType": "Investment",
        "propertyType": "Multifamily",
        "propertySubtype": "Apartment",
        "buildingSize": "3,020 SF",
        "buildingClass": "C",
        "yearBuiltRenovated": "1956/2014",
        "price": "$1,240,000",
        "pricePer": "$410.60",
        "capRate": "7%",
        "nOI": "$86,800",
        "occupancyPercentage": "100%",
        "tenancy": "Multiple",
        "zoning": "CM2d(MU-U)",
        "parking": "2 Spaces",
    },
    "description": "Turnkey multifamily.",
}

SAMPLE_EXTENDED_DETAILS = {
    "saleSummary": {
        "apn": "R313810",
        "capRate": "7.00%",
        "lotSize": "0.12 AC",
        "numberOfStories": "2",
        "createdAt": "2026-01-06T12:00:00-05:00",
        "lastUpdated": "4/18/2026",
        "opportunityZone": None,
    }
}


def test_map_to_scraped_listing_basic_fields() -> None:
    mapped = map_to_scraped_listing(
        SAMPLE_SALE_DETAILS, SAMPLE_EXTENDED_DETAILS,
        listing_id="38985870", lat=45.53, lng=-122.64,
    )
    assert mapped["source"] == "loopnet"
    assert mapped["source_id"] == "38985870"
    assert mapped["apn"] == "R313810"
    assert mapped["asking_price"] == Decimal("1240000")
    assert mapped["cap_rate"] == Decimal("7")
    assert mapped["noi"] == Decimal("86800")
    assert mapped["gba_sqft"] == Decimal("3020")
    assert mapped["year_built"] == 1956
    assert mapped["year_renovated"] == 2014
    assert mapped["property_type"] == "Multifamily"
    assert mapped["sub_type"] == ["Apartment"]
    assert mapped["lat"] == Decimal("45.53")
    assert mapped["lng"] == Decimal("-122.64")
    assert mapped["stories"] == 2
    assert mapped["updated_at_source"] == datetime(2026, 4, 18, tzinfo=UTC)


def test_map_to_scraped_listing_handles_missing_extended() -> None:
    mapped = map_to_scraped_listing(
        SAMPLE_SALE_DETAILS, None, listing_id="123", lat=None, lng=None,
    )
    assert mapped["apn"] is None
    assert mapped["lat"] is None
    assert mapped["asking_price"] == Decimal("1240000")


def test_map_falls_back_to_extended_year_built() -> None:
    """When SaleDetails lacks yearBuiltRenovated, ED.saleSummary.yearBuilt wins."""
    sd = {**SAMPLE_SALE_DETAILS,
          "propertyFacts": {**SAMPLE_SALE_DETAILS["propertyFacts"],
                            "yearBuiltRenovated": None}}
    ed = {"saleSummary": {"yearBuilt": 1972, "yearRenovated": 2018}}
    mapped = map_to_scraped_listing(sd, ed, listing_id="x", lat=None, lng=None)
    assert mapped["year_built"] == 1972
    assert mapped["year_renovated"] == 2018


def test_map_converts_acres_to_sqft() -> None:
    sd = SAMPLE_SALE_DETAILS
    ed = {"saleSummary": {"lotSize": "2.17 AC"}}
    mapped = map_to_scraped_listing(sd, ed, listing_id="x", lat=None, lng=None)
    # 2.17 AC × 43,560 SF/AC = 94,525.2 SF
    assert mapped["lot_sqft"] == Decimal("2.17") * Decimal("43560")


def test_map_lot_sqft_handles_already_sf_value() -> None:
    sd = {**SAMPLE_SALE_DETAILS,
          "propertyFacts": {**SAMPLE_SALE_DETAILS["propertyFacts"],
                            "landArea": "5,000 SF"}}
    mapped = map_to_scraped_listing(sd, None, listing_id="x", lat=None, lng=None)
    assert mapped["lot_sqft"] == Decimal("5000")


def test_map_handles_single_year() -> None:
    sd = {**SAMPLE_SALE_DETAILS,
          "propertyFacts": {**SAMPLE_SALE_DETAILS["propertyFacts"],
                            "yearBuiltRenovated": "1956"}}
    mapped = map_to_scraped_listing(sd, None, listing_id="x", lat=None, lng=None)
    assert mapped["year_built"] == 1956
    assert mapped["year_renovated"] is None


# ---------------------------------------------------------------------------
# BudgetGuard tests
# ---------------------------------------------------------------------------

def test_is_last_day_of_month() -> None:
    assert _is_last_day_of_month(date(2026, 1, 31)) is True
    assert _is_last_day_of_month(date(2026, 1, 30)) is False
    assert _is_last_day_of_month(date(2026, 2, 28)) is True   # non-leap
    assert _is_last_day_of_month(date(2024, 2, 29)) is True   # leap
    assert _is_last_day_of_month(date(2026, 12, 31)) is True


@pytest.mark.asyncio
async def test_budget_guard_short_circuits_when_exhausted(session) -> None:
    # Pre-populate api_call_log at the budget cap for today's month
    from app.models.api_call_log import ApiCallLog
    today = datetime.now(UTC).date()
    billing_month = date(today.year, today.month, 1)
    # Default cap = 100, margin = 5 → effective_cap = 95 unless last day of month
    cap = 95 if not _is_last_day_of_month(today) else 100
    for _ in range(cap):
        session.add(ApiCallLog(
            source="loopnet",
            endpoint="SaleDetails",
            billing_month=billing_month,
        ))
    await session.flush()

    async with BudgetGuard(session, today=today) as guard:
        assert guard.remaining == 0
        with pytest.raises(BudgetExhausted):
            await guard.call("/loopnet/property/SaleDetails", {"listingId": "1"})


@pytest.mark.asyncio
async def test_budget_guard_releases_margin_on_last_day(session) -> None:
    from app.models.api_call_log import ApiCallLog
    last_day = date(2026, 1, 31)
    billing_month = date(2026, 1, 1)
    # 95 calls: would exhaust on a non-last-day but margin releases on last day → cap is 100
    for _ in range(95):
        session.add(ApiCallLog(
            source="loopnet",
            endpoint="SaleDetails",
            billing_month=billing_month,
        ))
    await session.flush()

    async with BudgetGuard(session, today=last_day) as guard:
        # effective_cap = full 100 on last day
        assert guard.effective_cap == 100
        assert guard.remaining == 5


@pytest.mark.asyncio
async def test_budget_guard_logs_and_increments(session, monkeypatch) -> None:
    """call() logs a row and increments calls_used even when the HTTP layer is mocked."""
    from app.models.api_call_log import ApiCallLog
    from sqlalchemy import func, select

    class _FakeResp:
        def __init__(self, status=200, payload=None):
            self.status_code = status
            self._payload = payload or {"status": "success", "data": []}
        def raise_for_status(self): return None
        def json(self): return self._payload

    class _FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
        async def post(self, path, json=None): return _FakeResp()
        async def aclose(self): return None

    monkeypatch.setattr(loopnet.httpx, "AsyncClient", _FakeClient)

    async with BudgetGuard(session) as guard:
        before = guard.calls_used
        await guard.call("/loopnet/property/SaleDetails", {"listingId": "x"},
                         listing_source_id="x")
        assert guard.calls_used == before + 1

    # Log persisted
    result = await session.execute(select(func.count(ApiCallLog.id)))
    assert result.scalar_one() >= 1
