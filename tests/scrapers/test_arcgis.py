from __future__ import annotations

import httpx
import pytest

from vicinitideals.scrapers.arcgis import ArcGISLookupError, lookup_gresham_parcels


def _response(url: str, payload: dict, status_code: int = 200) -> httpx.Response:
    request = httpx.Request("GET", url)
    return httpx.Response(status_code, request=request, json=payload)


@pytest.mark.asyncio
async def test_lookup_gresham_parcels_normalizes_and_returns_single_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_where: list[str] = []

    async def fake_get(self, url: str, *, params=None, **kwargs):
        assert params is not None
        requested_where.append(params["where"])
        assert url.endswith("/Taxlots/MapServer/0/query")
        assert params["outFields"] == (
            "RNO,STATEID,SITEADDR,OWNER1,OWNERADDR,OWNERCITY,OWNERSTATE,OWNERZIP,"
            "LANDVAL,BLDGVAL,TOTALVAL,BLDGSQFT,YEARBUILT,TAXCODE,GIS_ACRES,SQFT,LEGAL,ZONE,LANDUSE"
        )
        assert params["returnGeometry"] == "true"
        return _response(
            url,
            {
                "features": [
                    {
                        "attributes": {
                            "STATEID": "1N3E33DC 06300",
                            "RNO": "R943330370",
                            "SITEADDR": "21255 SE STARK ST",
                            "OWNER1": "ABBY'S RE LLC",
                            "OWNERADDR": "2722 NE STEPHENS ST",
                            "OWNERCITY": "ROSEBURG",
                            "OWNERSTATE": "OR",
                            "OWNERZIP": "97470-1357",
                            "ZONE": "CMU",
                            "LANDUSE": "CJ",
                            "GIS_ACRES": 0.91601707,
                            "SQFT": 39902,
                            "BLDGSQFT": 3840,
                            "YEARBUILT": 1971,
                            "LANDVAL": 1012720,
                            "BLDGVAL": 526570,
                            "TOTALVAL": 1539290,
                            "TAXCODE": "137",
                            "LEGAL": "SECTION 33 1N 3E, TL 6300 0.92 ACRES",
                        },
                        "geometry": {"rings": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    results = await lookup_gresham_parcels([" 21255 se   stark st "])

    assert requested_where == ["SITEADDR = '21255 SE STARK ST'"]
    assert len(results) == 1
    result = results[0]
    assert result.input_address == "21255 SE STARK ST"
    assert result.match_status == "single_match"
    assert len(result.parcels) == 1

    parcel = result.parcels[0]
    assert parcel.state_id == "1N3E33DC 06300"
    assert parcel.rno == "R943330370"
    assert parcel.site_address == "21255 SE STARK ST"
    assert parcel.owner_name == "ABBY'S RE LLC"
    assert parcel.owner_street == "2722 NE STEPHENS ST"
    assert parcel.owner_city == "ROSEBURG"
    assert parcel.owner_state == "OR"
    assert parcel.owner_zip == "97470-1357"
    assert str(parcel.gis_acres) == "0.91601707"
    assert str(parcel.sqft) == "39902"
    assert str(parcel.total_value) == "1539290"
    assert parcel.tax_code == "137"
    assert parcel.geometry == {"rings": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}


@pytest.mark.asyncio
async def test_lookup_gresham_parcels_returns_multiple_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get(self, url: str, *, params=None, **kwargs):
        assert params is not None
        return _response(
            url,
            {
                "features": [
                    {"attributes": {"STATEID": "1", "RNO": "R1", "SITEADDR": "400 MULTI MATCH AVE"}},
                    {"attributes": {"STATEID": "2", "RNO": "R2", "SITEADDR": "400 MULTI MATCH AVE"}},
                ]
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    results = await lookup_gresham_parcels(["400 multi match ave"])

    assert len(results) == 1
    assert results[0].input_address == "400 MULTI MATCH AVE"
    assert results[0].match_status == "multiple_matches"
    assert [parcel.rno for parcel in results[0].parcels] == ["R1", "R2"]


@pytest.mark.asyncio
async def test_lookup_gresham_parcels_returns_no_match_after_like_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_where: list[str] = []

    async def fake_get(self, url: str, *, params=None, **kwargs):
        assert params is not None
        requested_where.append(params["where"])
        return _response(url, {"features": []})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    results = await lookup_gresham_parcels(["404 missing st"])

    assert requested_where == [
        "SITEADDR = '404 MISSING ST'",
        "UPPER(SITEADDR) LIKE '%404 MISSING ST%'",
    ]
    assert len(results) == 1
    assert results[0].input_address == "404 MISSING ST"
    assert results[0].match_status == "no_match"
    assert results[0].parcels == []


@pytest.mark.asyncio
async def test_lookup_gresham_parcels_preserves_batch_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get(self, url: str, *, params=None, **kwargs):
        assert params is not None
        where = params["where"]
        if where == "SITEADDR = '1 FIRST ST'":
            return _response(url, {"features": [{"attributes": {"RNO": "R1", "SITEADDR": "1 FIRST ST"}}]})
        if where == "SITEADDR = '2 SECOND ST'":
            return _response(url, {"features": []})
        if where == "UPPER(SITEADDR) LIKE '%2 SECOND ST%'":
            return _response(url, {"features": []})
        if where == "SITEADDR = '3 THIRD ST'":
            return _response(
                url,
                {"features": [
                    {"attributes": {"RNO": "R3A", "SITEADDR": "3 THIRD ST"}},
                    {"attributes": {"RNO": "R3B", "SITEADDR": "3 THIRD ST"}},
                ]},
            )
        raise AssertionError(f"Unexpected where clause: {where}")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    results = await lookup_gresham_parcels(["1 first st", "2 second st", "3 third st"])

    assert [result.input_address for result in results] == [
        "1 FIRST ST",
        "2 SECOND ST",
        "3 THIRD ST",
    ]
    assert [result.match_status for result in results] == [
        "single_match",
        "no_match",
        "multiple_matches",
    ]


@pytest.mark.asyncio
async def test_lookup_gresham_parcels_raises_arcgis_error_on_request_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get(self, url: str, *, params=None, **kwargs):
        request = httpx.Request("GET", url, params=params)
        raise httpx.ConnectError("boom", request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    with pytest.raises(ArcGISLookupError, match="boom"):
        await lookup_gresham_parcels(["21255 SE STARK ST"])
