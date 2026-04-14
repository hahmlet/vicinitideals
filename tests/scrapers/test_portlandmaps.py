from __future__ import annotations

import httpx
import pytest

from vicinitideals.scrapers.portlandmaps import lookup_portland_parcel


def _response(url: str, payload: dict, status_code: int = 200) -> httpx.Response:
    request = httpx.Request("GET", url)
    return httpx.Response(status_code, request=request, json=payload)


@pytest.mark.asyncio
async def test_lookup_portland_known_address_returns_enriched_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    address = "1120 SW 5TH AVE"

    async def fake_get(self, url: str, *, params=None, **kwargs):
        if "Address_Geocoding_PDX/GeocodeServer/findAddressCandidates" in url:
            assert params is not None
            assert params["SingleLine"] == address
            return _response(
                url,
                {
                    "candidates": [
                        {
                            "address": "1120 SW 5TH AVE, PORTLAND, OR 97204",
                            "score": 100,
                            "location": {"x": -122.6785, "y": 45.5152},
                            "attributes": {"X": -122.6785, "Y": 45.5152},
                        }
                    ]
                },
            )
        if url.endswith("/COP_OpenData_Property/MapServer/47/query"):
            return _response(
                url,
                {
                    "features": [
                        {
                            "attributes": {
                                "ADDRESS_ID": "410186",
                                "STATE_ID": "1S1E03BC 200",
                                "TLID": "R247355",
                                "FULL_ADDR": "1120 SW 5TH AVE, PORTLAND, OR 97204",
                            }
                        }
                    ]
                },
            )
        if url.endswith("/Public/Taxlots/MapServer/0/query"):
            return _response(
                url,
                {
                    "features": [
                        {
                            "attributes": {
                                "OWNER1": "PORTLAND CITY OF",
                                "OWNERADDR1": "1120 SW 5TH AVE",
                                "OWNERCITY": "PORTLAND",
                                "OWNERSTATE": "OR",
                                "OWNERZIP": "97204",
                                "LEGALDESC": "BLOCK 12 LOT 3",
                                "LANDVAL": 2500000,
                                "BLDGVAL": 18500000,
                                "TOTALVAL": 21000000,
                                "AREAACRES": 0.918,
                                "AREASQFT": 39988,
                                "PROPERTYUSE": "Office / Commercial",
                                "SALEDATE": "2024-05-01",
                                "SALEPRICE": 0,
                            }
                        }
                    ]
                },
            )
        if url.endswith("/Public/Zoning/MapServer/0/query"):
            return _response(
                url,
                {
                    "features": [
                        {
                            "attributes": {
                                "BASEZONE": "CX",
                                "BASEDESC": "Central Commercial",
                                "COMPLAN": "Central City",
                                "PLANDIST": "Central City",
                                "OVERLAY": "d",
                            }
                        }
                    ]
                },
            )
        if url.endswith("/Public/Zoning/MapServer/3/query"):
            return _response(
                url,
                {
                    "features": [
                        {
                            "attributes": {
                                "OVERLAY": "Design",
                            }
                        }
                    ]
                },
            )
        if url.endswith("/Public/BDS_Property/FeatureServer/0/query"):
            return _response(
                url,
                {
                    "features": [
                        {
                            "attributes": {
                                "NEIGHBORHOOD": "Portland Downtown",
                                "COUNCILDIST": "4",
                                "BUSINESSDIST": "Downtown",
                                "LIQUEFACTION": "Yes",
                                "FLOODWAY": "No",
                                "FLOODHAZARD": "No",
                                "PROPERTYSTATUS": "Active",
                            }
                        }
                    ]
                },
            )
        if url.endswith("/COP_OpenData_Property/MapServer/184/query"):
            return _response(
                url,
                {
                    "features": [
                        {
                            "attributes": {
                                "BUILDINGUSE": "Office / Commercial",
                                "STORIES": 15,
                                "BUILDINGSQFT": 362000,
                                "YEARBUILT": 1983,
                                "HEIGHTFT": 240,
                            }
                        }
                    ]
                },
            )
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await lookup_portland_parcel(address)

    assert result.input_address == address
    assert result.match_status == "single_match"
    assert result.address_match == "1120 SW 5TH AVE, PORTLAND, OR 97204"
    assert result.coordinates is not None
    assert result.coordinates.latitude == pytest.approx(45.5152)
    assert result.coordinates.longitude == pytest.approx(-122.6785)
    assert result.parcel_ids is not None
    assert result.parcel_ids.address_id == "410186"
    assert result.parcel_ids.state_id == "1S1E03BC 200"
    assert result.parcel_ids.tlid == "R247355"
    assert result.owner == "PORTLAND CITY OF"
    assert result.mailing_address is not None
    assert result.mailing_address.city == "PORTLAND"
    assert result.legal_description == "BLOCK 12 LOT 3"
    assert result.lot_metrics is not None
    assert str(result.lot_metrics.acreage) == "0.918"
    assert str(result.lot_metrics.lot_sqft) == "39988"
    assert result.valuation is not None
    assert str(result.valuation.total) == "21000000"
    assert result.zoning is not None
    assert result.zoning.code == "CX"
    assert result.zoning.description == "Central Commercial"
    assert result.zoning.comp_plan == "Central City"
    assert result.zoning.plan_district == "Central City"
    assert set(result.zoning.overlays) == {"d", "Design"}
    assert result.neighborhood == "Portland Downtown"
    assert result.council_district == "4"
    assert result.business_district == "Downtown"
    assert result.hazard_flags is not None
    assert result.hazard_flags.liquefaction is True
    assert result.hazard_flags.floodway is False
    assert result.hazard_flags.flood_hazard is False
    assert result.building_details is not None
    assert result.building_details.use == "Office / Commercial"
    assert result.building_details.stories == 15
    assert str(result.building_details.sqft) == "362000"
    assert result.building_details.year_built == 1983


@pytest.mark.asyncio
async def test_lookup_portland_returns_no_match_when_geocoder_has_no_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get(self, url: str, *, params=None, **kwargs):
        if "Address_Geocoding_PDX/GeocodeServer/findAddressCandidates" in url:
            return _response(url, {"candidates": []})
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await lookup_portland_parcel("404 UNKNOWN ST")

    assert result.input_address == "404 UNKNOWN ST"
    assert result.match_status == "no_match"
    assert result.address_match is None
    assert result.parcel_ids is None


@pytest.mark.asyncio
async def test_lookup_portland_returns_ambiguous_when_multiple_top_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get(self, url: str, *, params=None, **kwargs):
        if "Address_Geocoding_PDX/GeocodeServer/findAddressCandidates" in url:
            return _response(
                url,
                {
                    "candidates": [
                        {"address": "100 MAIN ST, PORTLAND, OR 97201", "score": 100},
                        {"address": "100 MAIN ST E, PORTLAND, OR 97201", "score": 100},
                    ]
                },
            )
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await lookup_portland_parcel("100 MAIN ST")

    assert result.input_address == "100 MAIN ST"
    assert result.match_status == "ambiguous"
    assert result.address_match is None
    assert result.parcel_ids is None
