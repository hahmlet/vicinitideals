"""The design catalog.

Two contracts carry the weight. A design is immutable once run — results keyed
``id@version`` are only comparable across runs if the dimensions behind that key
cannot drift. And an archived design stays loadable, because results that name
it are still on disk and must stay readable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flats.designs.model import (
    CATALOG_ROOT,
    CatalogError,
    Design,
    DesignCatalog,
    DesignStatus,
    Orientation,
    Typology,
    load_catalog,
)

pytestmark = pytest.mark.unit

BASE = """\
version: 1
label: "Test pod"
typology: townhome_rear_court
footprint: {width_ft: 56, depth_ft: 36}
units: 4
stories: 2
height_ft: 26
parking: {stalls_per_unit: 1.5, config: rear_court}
delivery: {method: panelized}
"""


def write(root: Path, name: str, body: str = BASE, **over: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for key, value in over.items():
        body = "\n".join(
            f"{key}: {value}" if ln.startswith(f"{key}:") else ln for ln in body.splitlines()
        ) + "\n"
    p = root / f"{name}.yaml"
    p.write_text(body, encoding="utf-8")
    return p


# --- identity and immutability ---------------------------------------


def test_id_defaults_to_the_filename(tmp_path: Path) -> None:
    # Naming a design twice — in the filename and inside it — invites drift.
    write(tmp_path, "pod56x36")

    assert load_catalog(tmp_path).get("pod56x36@1").id == "pod56x36"


def test_key_is_id_at_version(tmp_path: Path) -> None:
    write(tmp_path, "pod56x36", version="3")

    assert load_catalog(tmp_path).get("pod56x36@3").key == "pod56x36@3"


def test_two_versions_of_one_design_coexist(tmp_path: Path) -> None:
    # The point of versioning: v1's results stay interpretable after v2 ships.
    write(tmp_path, "v1", version="1")
    write(tmp_path, "v2", version="2", label='"Wider"')
    for p, name in ((tmp_path / "v1.yaml", "pod"), (tmp_path / "v2.yaml", "pod")):
        p.write_text(p.read_text(encoding="utf-8") + f"id: {name}\n", encoding="utf-8")

    cat = load_catalog(tmp_path)

    assert len(cat) == 2
    assert cat.latest("pod").version == 2


def test_duplicate_id_and_version_is_refused(tmp_path: Path) -> None:
    for name in ("a", "b"):
        (tmp_path / f"{name}.yaml").write_text(BASE + "id: pod\n", encoding="utf-8")

    with pytest.raises(CatalogError, match="bump version"):
        load_catalog(tmp_path)


def test_unknown_design_key_fails_loudly(tmp_path: Path) -> None:
    write(tmp_path, "pod56x36")

    # A result row naming a design the catalog cannot produce is unreadable, so
    # a miss must raise rather than return None.
    with pytest.raises(KeyError, match="id@version"):
        load_catalog(tmp_path).get("pod56x36")


# --- status ----------------------------------------------------------


def test_archived_designs_load_but_do_not_run(tmp_path: Path) -> None:
    write(tmp_path, "live")
    write(tmp_path, "old", body=BASE + "status: archived\n")

    cat = load_catalog(tmp_path)

    assert len(cat) == 2, "archived designs stay queryable — old results name them"
    assert [d.id for d in cat.active()] == ["live"]


# --- validation ------------------------------------------------------


def test_unknown_typology_is_refused(tmp_path: Path) -> None:
    # A typology selects real geometry code. An unknown one would otherwise
    # produce a design nothing can lay out.
    write(tmp_path, "pod", body=BASE.replace("townhome_rear_court", "courtyard_block"))

    with pytest.raises(CatalogError, match="typology"):
        load_catalog(tmp_path)


@pytest.mark.parametrize(
    "line", ["footprint: {width_ft: 0, depth_ft: 36}", "units: 0", "height_ft: -1", "version: 0"]
)
def test_nonsense_dimensions_are_refused(tmp_path: Path, line: str) -> None:
    key = line.split(":")[0]
    body = "\n".join(line if ln.startswith(f"{key}:") else ln for ln in BASE.splitlines()) + "\n"
    write(tmp_path, "pod", body=body)

    with pytest.raises(CatalogError):
        load_catalog(tmp_path)


def test_crane_reach_without_a_crane_is_refused(tmp_path: Path) -> None:
    write(
        tmp_path,
        "pod",
        body=BASE.replace(
            "delivery: {method: panelized}",
            "delivery: {method: modular, crane_reach_ft: 60}",
        ),
    )

    with pytest.raises(CatalogError, match="crane"):
        load_catalog(tmp_path)


def test_every_problem_is_reported_at_once(tmp_path: Path) -> None:
    write(tmp_path, "a", body=BASE.replace("units: 4", "units: 0"))
    write(tmp_path, "b", body=BASE.replace("height_ft: 26", "height_ft: 0"))

    with pytest.raises(CatalogError) as exc:
        load_catalog(tmp_path)

    assert len(exc.value.problems) == 2


def test_a_non_mapping_file_is_a_problem_not_a_crash(tmp_path: Path) -> None:
    (tmp_path / "bad.yaml").write_text("- just\n- a list\n", encoding="utf-8")

    with pytest.raises(CatalogError, match="expected a mapping"):
        load_catalog(tmp_path)


# --- derived geometry ------------------------------------------------


def design(**over) -> Design:
    import yaml

    return Design(**{**yaml.safe_load(BASE), "id": "pod", **over})


def test_derived_areas() -> None:
    d = design()

    assert d.ground_sqft == 2016
    assert d.unit_ground_sqft == 504
    assert d.stalls_required == 6.0


def test_both_orientations_are_offered() -> None:
    assert design().oriented() == (
        (Orientation.width_facing, 56, 36),
        (Orientation.depth_facing, 36, 56),
    )


def test_axis_required_halves_the_orientations() -> None:
    # The zoning case where the building must face the street.
    assert design().oriented(axis_required=True) == ((Orientation.width_facing, 56, 36),)


def test_a_square_pod_is_not_tested_twice() -> None:
    # Rotating a square yields the same rectangle; counting it twice would
    # double-count the lot's fit.
    d = design(footprint={"width_ft": 45, "depth_ft": 45})

    assert len(d.oriented()) == 1


def test_designs_are_frozen() -> None:
    with pytest.raises(Exception):
        design().footprint.width_ft = 99


def test_duplicate_key_in_the_catalog_constructor_is_refused() -> None:
    with pytest.raises(CatalogError, match="duplicate"):
        DesignCatalog([design(), design()])


# --- the shipped catalog ---------------------------------------------


def test_shipped_catalog_loads() -> None:
    cat = load_catalog()

    assert {d.key for d in cat} == {"pod56x36@1", "pod80x25@1"}
    assert all(d.typology is Typology.townhome_rear_court for d in cat)
    assert all(d.status is DesignStatus.active for d in cat)


def test_shipped_pods_match_the_quadfit_footprints() -> None:
    # These two came from quadfit's footprints.yaml. If they drift, screening
    # results stop being comparable with the runs already on disk.
    cat = load_catalog()

    assert (cat.get("pod56x36@1").footprint.width_ft, cat.get("pod56x36@1").footprint.depth_ft) == (56, 36)
    assert (cat.get("pod80x25@1").footprint.width_ft, cat.get("pod80x25@1").footprint.depth_ft) == (80, 25)


def test_unconfirmed_values_are_declared_not_hidden() -> None:
    # Height is product intent, not a drawing. A height-binding RED must be
    # traceable to that, so every shipped design has to say so.
    for d in load_catalog():
        assert any("height_ft" in a for a in d.assumptions), f"{d.key} hides its height assumption"


def test_catalog_root_points_at_the_shipped_pods() -> None:
    assert CATALOG_ROOT.is_dir()
    assert sorted(p.stem for p in CATALOG_ROOT.glob("*.yaml")) == ["pod56x36", "pod80x25"]
