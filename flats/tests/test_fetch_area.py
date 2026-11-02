from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs

import httpx

from scripts.flats_fetch_area import fetch_area


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_area_pages_filters_fields_and_records_source(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    object_ids = list(range(401))
    attributes = [
        {"name": "OBJECTID"},
        {"name": "Shape"},
        {"name": "Shape_Length"},
        {"name": "ZONE"},
        {"name": "MAP_NOTE"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/1278"):
            return httpx.Response(
                200,
                json={
                    "geometryType": "esriGeometryPolygon",
                    "fields": attributes,
                },
            )
        if request.method == "GET":
            assert request.url.params["where"] == "MAP_ID = '120-2'"
            return httpx.Response(
                200,
                json={"objectIdFieldName": "OBJECTID", "objectIds": object_ids},
            )
        form = parse_qs(request.content.decode())
        assert form["outSR"] == ["2913"]
        assert form["outFields"] == ["ZONE,MAP_NOTE"]
        batch = [int(value) for value in form["objectIds"][0].split(",")]
        return httpx.Response(
            200,
            json={
                "features": [
                    {
                        "attributes": {"ZONE": "R5", "MAP_NOTE": str(oid)},
                        "geometry": {
                            "rings": [
                                [[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]
                            ]
                        },
                    }
                    for oid in batch
                ]
            },
        )

    output = tmp_path / "area.geojson"
    with _client(handler) as http:
        document = fetch_area(
            "https://maps.example/MapServer",
            1278,
            "MAP_ID = '120-2'",
            output,
            "Zoning Code Map 120-2",
            client=http,
        )

    assert len([request for request in requests if request.method == "POST"]) == 2
    assert document["name"] == "pdx_area"
    assert document["crs"]["properties"]["name"] == "urn:ogc:def:crs:EPSG::2913"
    assert document["source"] == {
        "url": "https://maps.example/MapServer/1278",
        "where": "MAP_ID = '120-2'",
        "fields": "ZONE,MAP_NOTE",
        "fetched": document["source"]["fetched"],
        "note": "Zoning Code Map 120-2",
        "count": 401,
    }
    assert document["features"][0]["properties"] == {
        "ZONE": "R5",
        "MAP_NOTE": "0",
        "source": document["features"][0]["properties"]["source"],
    }
    assert document["features"][0]["geometry"]["type"] == "MultiPolygon"
    assert json.loads(output.read_text(encoding="utf-8")) == document


def test_fetch_area_converts_polyline_layers(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/5"):
            return httpx.Response(
                200,
                json={
                    "geometryType": "esriGeometryPolyline",
                    "fields": [{"name": "OBJECTID"}, {"name": "ROUTE"}],
                },
            )
        if request.method == "GET":
            return httpx.Response(
                200,
                json={"objectIdFieldName": "OBJECTID", "objectIds": [1]},
            )
        return httpx.Response(
            200,
            json={
                "features": [
                    {
                        "attributes": {"ROUTE": "Streetcar"},
                        "geometry": {"paths": [[[0, 0], [1, 1]]]},
                    }
                ]
            },
        )

    output = tmp_path / "streetcar-lines.geojson"
    with _client(handler) as http:
        document = fetch_area(
            "https://maps.example/Transit/MapServer",
            5,
            "1=1",
            output,
            "Zoning Code Map 510-13",
            client=http,
        )

    feature = document["features"][0]
    assert feature["geometry"] == {
        "type": "MultiLineString",
        "coordinates": [[[0, 0], [1, 1]]],
    }
    assert "Zoning Code Map 510-13" in feature["properties"]["source"]
    assert document["source"]["fields"] == "ROUTE"
