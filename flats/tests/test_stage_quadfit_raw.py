"""``scripts/flats_stage_quadfit_raw.py`` -- a quadfit tree built from a snapshot.

The tree is links to the snapshot's files under quadfit's names, the elevation
tiles shared from the July tree, the two FEMA layers derived, and a
``SOURCE.json`` naming the snapshot -- and it refuses a snapshot a measurement
could not honestly be read from.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "flats_stage_quadfit_raw.py"


@pytest.fixture(scope="module")
def stager():
    spec = importlib.util.spec_from_file_location("flats_stage_quadfit_raw", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _geojson(path: Path, features: list[dict]) -> None:
    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}),
        encoding="utf-8",
    )


def _feature(**props):
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
        },
    }


@pytest.fixture
def snapshot(tmp_path: Path) -> Path:
    snap = tmp_path / "sources" / "2026-09-18"
    snap.mkdir(parents=True)
    keys = {
        "rlis_taxlots": "acquired",
        "rlis_streets": "acquired",
        "rlis_zoning_metro": "present",
        "ugb_metro": "acquired",
        "rlis_taxlot_change": "acquired",
        "zoning_portland": "acquired",
        "overlay_fema_flood": "acquired",
        "overlay_gone": "retired",
    }
    datasets = {}
    for key, status in keys.items():
        if status != "retired":
            _geojson(snap / f"{key}.geojson", [_feature(K=key)])
        datasets[key] = {
            "status": status,
            "file": f"{key}.geojson",
            "sha256": f"sha-{key}",
        }
    _geojson(
        snap / "overlay_fema_flood.geojson",
        [
            _feature(FLD_ZONE="AE", ZONE_SUBTY="FLOODWAY", SFHA_TF="T"),
            _feature(FLD_ZONE="AE", ZONE_SUBTY=None, SFHA_TF="T"),
            _feature(FLD_ZONE="X", ZONE_SUBTY="0.2 PCT ANNUAL CHANCE", SFHA_TF="F"),
        ],
    )
    (snap / "manifest.json").write_text(
        json.dumps(
            {
                "snapshot": "2026-09-18",
                "working_srid": 2913,
                "archives": {},
                "datasets": datasets,
            }
        ),
        encoding="utf-8",
    )
    return snap


@pytest.fixture
def july_raw(tmp_path: Path) -> Path:
    raw = tmp_path / "quadfit" / "raw"
    raw.mkdir(parents=True)
    for key in (
        "taxlots",
        "streets",
        "zoning_metro",
        "ugb",
        "zoning_portland",
        "overlay_fema_flood",
        "overlay_fema_floodway",
        "overlay_fema_sfha",
    ):
        _geojson(raw / f"{key}.geojson", [])
    for name in ("dem", "dem10"):
        (raw / name).mkdir()
        (raw / name / "tile.tif").write_bytes(b"tif")
    return raw


def test_stage_links_renames_derives_and_records(
    stager, snapshot: Path, july_raw: Path, tmp_path: Path
):
    tree = tmp_path / "quadfit_2026-09-18"
    doc = stager.stage(snapshot, tree, july_raw=july_raw)
    raw = tree / "raw"
    # The four renames, everything else under its own name, the change log left out.
    assert sorted(doc["layers"]) == [
        "overlay_fema_flood",
        "streets",
        "taxlots",
        "ugb",
        "zoning_metro",
        "zoning_portland",
    ]
    taxlots = doc["layers"]["taxlots"]
    assert taxlots["from"] == "rlis_taxlots" and taxlots["sha256"] == "sha-rlis_taxlots"
    assert taxlots["file"] == str(snapshot / "rlis_taxlots.geojson")
    assert taxlots["how"] in ("symlink", "hardlink", "copy")
    assert (
        not (raw / "rlis_taxlot_change.geojson").exists()
        and not (raw / "rlis_taxlots.geojson").exists()
    )
    assert (
        json.loads((raw / "taxlots.geojson").read_text())["features"][0]["properties"][
            "K"
        ]
        == "rlis_taxlots"
    )
    assert (
        json.loads((raw / "ugb.geojson").read_text())["features"][0]["properties"]["K"]
        == "ugb_metro"
    )
    # Elevation shared from July; dem10_utm absent there so absent here.
    assert (
        sorted(doc["dem"]) == ["dem", "dem10"]
        and (raw / "dem" / "tile.tif").read_bytes() == b"tif"
    )
    assert not (raw / "dem10_utm").exists()
    # FEMA split the way s0 does it: floodway by ZONE_SUBTY, fringe by SFHA_TF.
    assert doc["derived"] == ["overlay_fema_floodway", "overlay_fema_sfha"]
    fw = json.loads((raw / "overlay_fema_floodway.geojson").read_text())["features"]
    fr = json.loads((raw / "overlay_fema_sfha.geojson").read_text())["features"]
    assert len(fw) == 1 and fw[0]["properties"]["ZONE_SUBTY"] == "FLOODWAY"
    assert len(fr) == 1 and fr[0]["properties"]["ZONE_SUBTY"] is None
    # SOURCE.json says which snapshot the tree is.
    source = json.loads((raw / "SOURCE.json").read_text(encoding="utf-8"))
    assert source["snapshot"] == "2026-09-18" and source["working_srid"] == 2913
    assert source["renames"] == stager.RENAMES and source["layers"] == doc["layers"]


def test_restaging_is_idempotent(
    stager, snapshot: Path, july_raw: Path, tmp_path: Path
):
    tree = tmp_path / "t"
    first = stager.stage(snapshot, tree, july_raw=july_raw)
    second = stager.stage(snapshot, tree, july_raw=july_raw)
    assert first["layers"] == second["layers"] and first["derived"] == second["derived"]
    assert len(list((tree / "raw").glob("*.geojson"))) == 8


def test_refuses_a_failed_layer(stager, snapshot: Path, july_raw: Path, tmp_path: Path):
    doc = json.loads((snapshot / "manifest.json").read_text())
    doc["datasets"]["zoning_portland"]["status"] = "failed"
    doc["datasets"]["zoning_portland"]["error"] = "Invalid URL"
    (snapshot / "manifest.json").write_text(json.dumps(doc))
    with pytest.raises(SystemExit, match="zoning_portland: failed -- Invalid URL"):
        stager.stage(snapshot, tmp_path / "t", july_raw=july_raw)
    assert not (tmp_path / "t" / "raw").exists(), (
        "nothing is built from a snapshot that is not whole"
    )


def test_refuses_unfetched_features_and_a_missing_file(
    stager, snapshot: Path, july_raw: Path
):
    doc = json.loads((snapshot / "manifest.json").read_text())
    doc["datasets"]["zoning_portland"]["unfetched_ids"] = [1, 2, 3]
    (snapshot / "ugb_metro.geojson").unlink()
    problems = stager.check(doc, snapshot, july_raw)
    assert "zoning_portland: 3 features never fetched" in problems
    assert (
        "ugb_metro: manifest says acquired but the file is not in the snapshot"
        in problems
    )


def test_refuses_when_the_july_tree_has_a_layer_the_snapshot_lacks(
    stager, snapshot: Path, july_raw: Path
):
    _geojson(july_raw / "overlay_happy_valley_nroz.geojson", [])
    problems = stager.check(
        json.loads((snapshot / "manifest.json").read_text()), snapshot, july_raw
    )
    assert problems == [
        "overlay_happy_valley_nroz: quadfit's tree has it, the snapshot does not -- register it or retire it on purpose"
    ]


def test_refuses_without_a_core_layer(stager, snapshot: Path):
    doc = json.loads((snapshot / "manifest.json").read_text())
    del doc["datasets"]["rlis_streets"]
    problems = stager.check(doc, snapshot, None)
    assert problems == [
        "streets: not in the snapshot; a measurement run cannot start without it"
    ]


def test_cli_prints_the_env_line(
    stager, snapshot: Path, july_raw: Path, tmp_path: Path, capsys
):
    tree = tmp_path / "tree"
    rc = stager.main(
        [
            "--snapshot",
            "2026-09-18",
            "--root",
            str(snapshot.parent),
            "--data-dir",
            str(tree),
            "--dem-from",
            str(july_raw),
        ]
    )
    out = capsys.readouterr().out
    assert (
        rc == 0
        and "staged 6 layers + 2 derived" in out
        and f"QUADFIT_DATA_DIR={tree.resolve()}" in out
    )


def test_quadfit_data_dir_env_var_moves_the_tree(tmp_path: Path, monkeypatch):
    """``common.DATA_DIR`` follows ``QUADFIT_DATA_DIR`` -- the switch every stage reads."""
    monkeypatch.syspath_prepend(str(REPO_ROOT / "Lot Analysis" / "quadfit"))
    monkeypatch.setenv("QUADFIT_DATA_DIR", str(tmp_path / "elsewhere"))
    common = importlib.import_module("common")
    common = importlib.reload(common)
    assert common.DATA_DIR == (tmp_path / "elsewhere").resolve()
    monkeypatch.delenv("QUADFIT_DATA_DIR")
    common = importlib.reload(common)
    assert common.DATA_DIR == REPO_ROOT / "data" / "quadfit"
