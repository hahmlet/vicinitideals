"""OpenStreetMap through Overpass: the query, the shapes, and the acquire path (FOLLOWUPS 47)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

pytest.importorskip("shapely")
pytest.importorskip("pyproj")

from flats.ingest import acquire as stage  # noqa: E402
from flats.ingest import overpass  # noqa: E402
from flats.ingest.sources import load_pipeline  # noqa: E402

pytestmark = pytest.mark.unit

INTERPRETER = "https://overpass.example/api/interpreter"

OVERPASS_ONLY = f"""
jurisdictions:
  or/multnomah/portland: true
datasets:
  osm_land_use:
    kind: overpass
    label: OSM institutional land
    provides: land_use
    url: {INTERPRETER}
    geometry: mixed
    bbox_4326: [-122.8, 45.4, -122.5, 45.6]
    serves: [or/multnomah]
    fields: [name, amenity, railway]
    query: |
      nwr["amenity"="school"]({{bbox}});
      nwr["railway"="rail"]({{bbox}});
"""


def registry(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "pipeline.yaml"
    p.write_text("working_srid: 2913\ndisplay_srid: 4326\n" + body, encoding="utf-8")
    return p


def _ring(lon: float, lat: float, d: float = 0.001) -> list[dict[str, float]]:
    pts = [(lon, lat), (lon + d, lat), (lon + d, lat + d), (lon, lat + d), (lon, lat)]
    return [{"lon": x, "lat": y} for x, y in pts]


SCHOOL = {"type": "way", "id": 1, "tags": {"amenity": "school", "name": "Westview", "wikidata": "Q1"}, "geometry": _ring(-122.7, 45.5)}
TRACK = {"type": "way", "id": 2, "tags": {"railway": "rail"}, "geometry": [{"lon": -122.7, "lat": 45.5}, {"lon": -122.69, "lat": 45.5}]}
LOOP = {"type": "way", "id": 3, "tags": {"railway": "rail"}, "geometry": _ring(-122.6, 45.5)}
NODE = {"type": "node", "id": 4, "lat": 45.5, "lon": -122.7, "tags": {"amenity": "school"}}
CAMPUS = {
    "type": "relation",
    "id": 5,
    "tags": {"type": "multipolygon", "amenity": "school"},
    "members": [
        # The outer ring in two halves, the way OSM often draws it.
        {"type": "way", "role": "outer", "geometry": _ring(-122.65, 45.5, 0.01)[:3]},
        {"type": "way", "role": "outer", "geometry": _ring(-122.65, 45.5, 0.01)[2:]},
        {"type": "way", "role": "inner", "geometry": _ring(-122.648, 45.502, 0.002)},
    ],
}
ROUTE = {"type": "relation", "id": 6, "tags": {"type": "route"}, "members": []}


def test_the_query_puts_the_box_in_overpass_order() -> None:
    q = overpass.compose('nwr["amenity"="school"]({bbox});', (-123.0, 45.0, -122.0, 46.0))
    # Overpass asks south, west, north, east; the registry stores west, south, east, north.
    assert 'nwr["amenity"="school"](45.0,-123.0,46.0,-122.0);' in q
    assert q.startswith("[out:json]") and q.rstrip().endswith("out geom;")


def test_a_selector_without_a_box_is_refused() -> None:
    with pytest.raises(ValueError):
        overpass.compose('nwr["amenity"="school"];', (-123.0, 45.0, -122.0, 46.0))


def test_a_cut_short_answer_is_refused() -> None:
    with pytest.raises(overpass.OverpassError):
        overpass.check({"elements": [SCHOOL], "remark": "runtime error: Query timed out in \"query\" at line 3"})
    overpass.check({"elements": []})


def test_shapes_by_element_kind() -> None:
    assert overpass.shape_of(NODE).geom_type == "Point"
    assert overpass.shape_of(SCHOOL).geom_type == "Polygon"
    assert overpass.shape_of(TRACK).geom_type == "LineString"
    # A track that closes on itself is still a track, not a yard.
    assert overpass.shape_of(LOOP).geom_type == "LineString"
    campus = overpass.shape_of(CAMPUS)
    assert campus.geom_type == "Polygon" and len(campus.interiors) == 1
    assert overpass.shape_of(ROUTE) is None


def test_features_keep_only_the_named_tags_and_say_where_they_came_from() -> None:
    skipped: dict[str, int] = {}
    got = list(overpass.features([SCHOOL, ROUTE], ["name", "amenity"], overpass.reprojector(2913), skipped))
    assert len(got) == 1
    assert got[0]["properties"] == {"osm": "way/1", "name": "Westview", "amenity": "school"}
    assert skipped == {"relation:route": 1}
    # Degrees in, the working CRS (feet) out: Portland is millions of feet east.
    x, y = got[0]["geometry"]["coordinates"][0][0]
    assert 7_500_000 < x < 7_700_000 and 600_000 < y < 750_000


class Interpreter:
    def __init__(self, answers: list[httpx.Response]) -> None:
        self.answers = answers
        self.queries: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert str(request.url) == INTERPRETER and request.method == "POST"
        self.queries.append(dict(httpx.QueryParams(request.content.decode()))["data"])
        return self.answers.pop(0)


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stage, "_sleep", lambda _s: None)


def _features(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))["features"]


def test_the_extract_lands_in_the_working_crs_after_a_busy_interpreter(tmp_path: Path) -> None:
    server = Interpreter(
        [httpx.Response(504, text="busy"), httpx.Response(200, json={"elements": [SCHOOL, TRACK, NODE, ROUTE]})]
    )
    pipeline = load_pipeline(registry(tmp_path, OVERPASS_ONLY))
    out = tmp_path / "2026-10-06"

    doc = stage.acquire(pipeline, out, client=httpx.Client(transport=httpx.MockTransport(server)), log=lambda _m: None)

    entry = doc["datasets"]["osm_land_use"]
    assert entry["status"] == "acquired" and entry["features"] == 3
    assert entry["fields"]["present"] == ["amenity", "name", "railway"]
    assert len(server.queries) == 2 and "(45.4,-122.8,45.6,-122.5)" in server.queries[-1]
    assert {f["properties"]["osm"] for f in _features(out / "osm_land_use.geojson")} == {"way/1", "way/2", "node/4"}


def test_a_remark_fails_the_dataset_and_writes_no_file(tmp_path: Path) -> None:
    server = Interpreter([httpx.Response(200, json={"elements": [SCHOOL], "remark": "runtime error: out of memory"})])
    pipeline = load_pipeline(registry(tmp_path, OVERPASS_ONLY))
    out = tmp_path / "2026-10-06"

    doc = stage.acquire(pipeline, out, client=httpx.Client(transport=httpx.MockTransport(server)), log=lambda _m: None)

    assert doc["datasets"]["osm_land_use"]["status"] == "failed"
    assert "cut the answer short" in doc["datasets"]["osm_land_use"]["error"]
    assert not (out / "osm_land_use.geojson").exists()
    assert not list(out.glob("*.part"))


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda b: b.replace("    query: |\n", "    query_was: |\n"), "needs its query and its box"),
        (lambda b: b.replace("({bbox});\n      nwr", "();\n      nwr"), "must hold {bbox}"),
        (lambda b: b.replace("geometry: mixed", "geometry: polygon"), "geometry: mixed"),
    ],
)
def test_an_overpass_entry_must_be_whole(tmp_path: Path, change: Any, message: str) -> None:
    from flats.ingest.sources import PipelineError

    body = change(OVERPASS_ONLY)
    assert body != OVERPASS_ONLY
    with pytest.raises((PipelineError, ValueError), match=message):
        load_pipeline(registry(tmp_path, body))


def test_the_real_registry_declares_the_extract() -> None:
    ds = load_pipeline().datasets["osm_land_use"]
    q = overpass.compose(str(ds.query), ds.bbox_4326)  # type: ignore[arg-type]
    assert q.count("({bbox})") == 0 and "out geom" in q
    # Churches and charities stay screened (Steph 2026-10-06): never fetched.
    assert "place_of_worship" not in str(ds.query)
