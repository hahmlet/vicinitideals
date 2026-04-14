from __future__ import annotations

import httpx
import pytest

from vicinitideals.scrapers.oregoncity import lookup_oregoncity_parcel


def _response(url: str, payload: dict, status_code: int = 200) -> httpx.Response:
    request = httpx.Request("GET", url)
    return httpx.Response(status_code, request=request, json=payload)


@pytest.mark.asyncio
async def test_lookup_oregoncity_known_address_returns_normalized_parcel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    address = "1225 JOHNSON ST"
    x = 7661234.933070868
    y = 616332.3727034181

    async def fake_get(self, url: str, *, params=None, **kwargs):
        if url.endswith("/AddressPts_PUBLIC/MapServer/0/query"):
            assert params is not None
            assert params["where"] == "UPPER(ADDRESS_Pts.SITUS) = '1225 JOHNSON ST'"
            return _response(
                url,
                {
                    "features": [
                        {
                            "attributes": {
                                "ADDRESS_Pts.SITUS": address,
                                "ADDRESS_Pts.CITY": "OREGON CITY",
                                "ADDRESS_Pts.ZIP5": 97045,
                            },
                            "geometry": {"x": x, "y": y},
                        }
                    ]
                },
            )
        if url.endswith("/Taxlots_PUBLIC/MapServer/0/query"):
            assert params is not None
            assert params["geometry"] == f"{x},{y}"
            assert params["inSR"] == 2913
            return _response(
                url,
                {
                    "features": [
                        {
                            "attributes": {
                                "APN": "3-2E-06AD-07000",
                                "PARCEL_NUMBER": "00852599",
                                "SITUS_FULL_ADDRESS": address,
                                "GIS_ACRES": 0.22956987,
                                "ZONING": "R-2",
                                "COMPREHENSIVE_PLAN": "HR",
                                "TAXLOT_IN_CITY": "Y",
                                "TAXLOT_IN_UGB": "Y",
                                "YEARBLT": 1968,
                                "LIVING_AREA": 4608,
                                "TOTALVAL": 845658,
                                "SALE_PRICE": 0,
                                "DOC_DATE": "2024-08-23 00:00",
                            }
                        }
                    ]
                },
            )
        if "/HazardsAndFloodInfo_PUBLIC/MapServer/3/query" in url:
            return _response(url, {"features": [{"attributes": {"FLD_ZONE": "AE"}}]})
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await lookup_oregoncity_parcel("1225 johnson st")

    assert result.input_address == "1225 JOHNSON ST"
    assert result.match_status == "single_match"
    assert result.situs_address == address
    assert result.apn == "3-2E-06AD-07000"
    assert result.parcel_number == "00852599"
    assert result.zoning_code == "R-2"
    assert result.comp_plan == "HR"
    assert result.in_city is True
    assert result.ugb_status == "inside"
    assert str(result.gis_acres) == "0.22956987"
    assert result.year_built == 1968
    assert str(result.living_area_sqft) == "4608"
    assert str(result.total_assessed_value) == "845658"
    assert str(result.sale_price) == "0"
    assert result.sale_date == "2024-08-23 00:00"
    assert result.flood_hazard == "AE"


@pytest.mark.asyncio
async def test_lookup_oregoncity_returns_no_match_after_exact_and_like_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_where: list[str] = []

    async def fake_get(self, url: str, *, params=None, **kwargs):
        if url.endswith("/AddressPts_PUBLIC/MapServer/0/query"):
            assert params is not None
            seen_where.append(params["where"])
            return _response(url, {"features": []})
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await lookup_oregoncity_parcel("1225 johnson st")

    assert result.input_address == "1225 JOHNSON ST"
    assert result.match_status == "no_match"
    assert seen_where == [
        "UPPER(ADDRESS_Pts.SITUS) = '1225 JOHNSON ST'",
        "UPPER(ADDRESS_Pts.SITUS) LIKE '%1225 JOHNSON ST%'",
    ]


@pytest.mark.asyncio
async def test_lookup_oregoncity_skips_optional_enrichment_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    address = "1225 JOHNSON ST"
    x = 7661234.933070868
    y = 616332.3727034181

    async def fake_get(self, url: str, *, params=None, **kwargs):
        if url.endswith("/AddressPts_PUBLIC/MapServer/0/query"):
            return _response(
                url,
                {
                    "features": [
                        {
                            "attributes": {
                                "ADDRESS_Pts.SITUS": address,
                                "ADDRESS_Pts.CITY": "OREGON CITY",
                                "ADDRESS_Pts.ZIP5": 97045,
                            },
                            "geometry": {"x": x, "y": y},
                        }
                    ]
                },
            )
        if url.endswith("/Taxlots_PUBLIC/MapServer/0/query"):
            return _response(
                url,
                {
                    "features": [
                        {
                            "attributes": {
                                "APN": "3-2E-06AD-07000",
                                "PARCEL_NUMBER": "00852599",
                                "SITUS_FULL_ADDRESS": address,
                                "GIS_ACRES": 0.22956987,
                                "ZONING": "R-2",
                                "COMPREHENSIVE_PLAN": "HR",
                                "TAXLOT_IN_CITY": "Y",
                                "TAXLOT_IN_UGB": "Y",
                                "YEARBLT": 1968,
                                "LIVING_AREA": 4608,
                                "TOTALVAL": 845658,
                                "SALE_PRICE": 0,
                                "DOC_DATE": "2024-08-23 00:00",
                            }
                        }
                    ]
                },
            )
        if "/HazardsAndFloodInfo_PUBLIC/MapServer/3/query" in url:
            request = httpx.Request("GET", url)
            raise httpx.ConnectError("hazards unavailable", request=request)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await lookup_oregoncity_parcel(address)

    assert result.match_status == "single_match"
    assert result.flood_hazard is None
