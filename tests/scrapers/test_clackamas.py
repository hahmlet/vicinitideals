from __future__ import annotations

import httpx
import pytest

from app.scrapers.clackamas import lookup_clackamas_parcel


def _response(url: str, payload: dict, status_code: int = 200) -> httpx.Response:
    request = httpx.Request("POST", url)
    return httpx.Response(status_code, request=request, json=payload)


@pytest.mark.asyncio
async def test_lookup_clackamas_county_parcel_normalizes_county_zoning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    address = "14703 S Brunner Rd, Oregon City, 97045"
    geometry = "POINT(7674149.36548556 635990.208989501)"

    async def fake_post(self, url: str, *, data=None, **kwargs):
        if url.endswith("/query/address"):
            assert data == {"q": address}
            return _response(
                url,
                {
                    "results": [
                        {
                            "name": address,
                            "point": {"coordinates": [7674149.36548556, 635990.208989501]},
                        }
                    ]
                },
            )
        if url.endswith("/select/taxlot"):
            assert data == {"geometry": geometry}
            return _response(
                url,
                {
                    "features": [
                        {
                            "properties": {
                                "primary_address": address,
                                "jurisdiction": "Clackamas County",
                                "map_number": "22E15C",
                                "taxlot_number": "22E15C 01306",
                                "parcel_number": "00486110",
                                "document_number": "2005-017371",
                                "census_tract": "022301",
                                "landclass": "551",
                            }
                        }
                    ]
                },
            )
        if url.endswith("/select/development"):
            return _response(
                url,
                {
                    "features": [
                        {
                            "properties": {
                                "classification": "Designation: EFU",
                                "web_url": "http://www.clackamas.us/planning/zdo.html",
                            }
                        },
                        {
                            "properties": {
                                "classification": "Urban Growth Boundary: OUTSIDE",
                                "web_url": "",
                            }
                        },
                    ]
                },
            )
        if url.endswith("/select/environmental"):
            return _response(
                url,
                {
                    "features": [
                        {
                            "properties": {
                                "datagroup": "Flood",
                                "hazard_value": "Likely not in a flood zone.",
                            }
                        }
                    ]
                },
            )
        if url.endswith("/select/utilities"):
            return _response(
                url,
                {
                    "features": [
                        {
                            "properties": {
                                "datagroup": "School District",
                                "service_name": "Oregon City",
                            }
                        },
                        {
                            "properties": {
                                "datagroup": "Community Planning Organization",
                                "service_name": "Clackamas County",
                            }
                        },
                    ]
                },
            )
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await lookup_clackamas_parcel(address)

    assert result.match_status == "single_match"
    assert result.primary_address == address
    assert result.jurisdiction == "Clackamas County"
    assert result.map_number == "22E15C"
    assert result.taxlot_number == "22E15C 01306"
    assert result.parcel_number == "00486110"
    assert result.zoning_label == "County Zoning"
    assert result.zoning_value == "EFU"
    assert result.zoning_url == "http://www.clackamas.us/planning/zdo.html"
    assert result.ugb_raw == "OUTSIDE"
    assert result.ugb_status == "outside"
    assert result.flood_hazard == "Likely not in a flood zone."
    assert result.school_district == "Oregon City"
    assert result.planning_org == "Clackamas County"


@pytest.mark.asyncio
async def test_lookup_clackamas_city_parcel_normalizes_city_zoning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    address = "1225 7th St, Oregon City, OR 97045"

    async def fake_post(self, url: str, *, data=None, **kwargs):
        if url.endswith("/query/address"):
            return _response(
                url,
                {
                    "results": [
                        {
                            "name": address,
                            "point": {"coordinates": [7653084.509186357, 611625.385170609]},
                        }
                    ]
                },
            )
        if url.endswith("/select/taxlot"):
            return _response(
                url,
                {
                    "features": [
                        {
                            "properties": {
                                "primary_address": "1225 7th St, Oregon City, 97045",
                                "jurisdiction": "Oregon City",
                                "map_number": "31E02BA",
                                "taxlot_number": "31E02BA 00100",
                                "parcel_number": "00567890",
                                "document_number": "2010-000123",
                                "census_tract": "020100",
                                "landclass": "541",
                            }
                        }
                    ]
                },
            )
        if url.endswith("/select/development"):
            return _response(
                url,
                {
                    "features": [
                        {
                            "properties": {
                                "classification": "Designation: Contact City",
                                "web_url": "http://www.orcity.org",
                            }
                        },
                        {
                            "properties": {
                                "classification": "Urban Growth Boundary: METRO UGB",
                                "web_url": "",
                            }
                        },
                    ]
                },
            )
        if url.endswith("/select/environmental"):
            return _response(url, {"features": []})
        if url.endswith("/select/utilities"):
            return _response(url, {"features": []})
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await lookup_clackamas_parcel(address)

    assert result.match_status == "single_match"
    assert result.jurisdiction == "Oregon City"
    assert result.zoning_label == "City Zoning"
    assert result.zoning_value == "Contact City"
    assert result.zoning_url == "http://www.orcity.org"
    assert result.ugb_raw == "METRO UGB"
    assert result.ugb_status == "inside"


@pytest.mark.asyncio
async def test_lookup_clackamas_returns_no_match_when_address_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_post(self, url: str, *, data=None, **kwargs):
        if url.endswith("/query/address"):
            return _response(url, {"results": []})
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await lookup_clackamas_parcel("404 Missing St, Oregon City, OR 97045")

    assert result.match_status == "no_match"
    assert result.primary_address is None
    assert result.zoning_label is None
    assert result.ugb_status is None


@pytest.mark.asyncio
async def test_lookup_clackamas_skips_optional_enrichment_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    address = "14703 S Brunner Rd, Oregon City, 97045"

    async def fake_post(self, url: str, *, data=None, **kwargs):
        if url.endswith("/query/address"):
            return _response(
                url,
                {
                    "results": [
                        {
                            "name": address,
                            "point": {"coordinates": [7674149.36548556, 635990.208989501]},
                        }
                    ]
                },
            )
        if url.endswith("/select/taxlot"):
            return _response(
                url,
                {"features": [{"properties": {"primary_address": address, "jurisdiction": "Clackamas County"}}]},
            )
        if url.endswith("/select/development"):
            return _response(
                url,
                {
                    "features": [
                        {"properties": {"classification": "Designation: EFU", "web_url": ""}},
                        {"properties": {"classification": "Urban Growth Boundary: OUTSIDE", "web_url": ""}},
                    ]
                },
            )
        if url.endswith("/select/environmental"):
            request = httpx.Request("POST", url)
            raise httpx.ConnectError("environmental unavailable", request=request)
        if url.endswith("/select/utilities"):
            return _response(url, {"features": []})
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await lookup_clackamas_parcel(address)

    assert result.match_status == "single_match"
    assert result.flood_hazard is None
    assert result.school_district is None
    assert result.planning_org is None
