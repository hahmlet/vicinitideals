"""The data-source registry.

Its job is to make coverage claimable and checkable. An enabled city with no
zoning source must be a named finding rather than an empty result set that
reads like an answer — the same failure, one layer up, that put 88,947 lots in
a bucket nobody looked at.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flats.ingest.sources import (
    CONFIG_PATH,
    Dataset,
    PipelineError,
    Provides,
    describe,
    load_pipeline,
)

pytestmark = pytest.mark.unit


def config(body: str, tmp_path: Path) -> Path:
    p = tmp_path / "pipeline.yaml"
    p.write_text(body, encoding="utf-8")
    return p


MINIMAL = """
working_srid: 2913
display_srid: 4326
jurisdictions:
  or/multnomah/portland: true
datasets:
  zoning_portland:
    kind: arcgis
    label: Portland zoning
    provides: zoning
    url: https://example.gov/zoning/0
    zone_field: ZONE
    fields: [ZONE]
    serves: [or/multnomah/portland]
"""


# --- the shipped registry ---------------------------------------------


def test_the_shipped_registry_loads() -> None:
    p = load_pipeline()

    assert p.working_srid == 2913, "the working CRS is in feet; every measurement depends on it"
    assert p.display_srid == 4326
    assert CONFIG_PATH.is_file()


def test_every_enabled_jurisdiction_has_a_zoning_source() -> None:
    # The check the registry exists for.
    assert load_pipeline().unserved(Provides.zoning) == ()


def test_a_city_with_its_own_service_does_not_fall_back() -> None:
    p = load_pipeline()

    assert p.for_layer("or/multnomah/portland", Provides.zoning)[0].key == "zoning_portland"


def test_a_jurisdiction_that_publishes_nothing_falls_back_to_the_region() -> None:
    # Neither county publishes unincorporated zoning, and Fairview's code is
    # PDF only. The Metro layer is what stands in — a legitimate choice, but
    # one that has to be visible.
    p = load_pipeline()

    assert p.for_layer("or/multnomah/_unincorporated", Provides.zoning)[0].key == "rlis_zoning_metro"
    assert p.for_layer("or/multnomah/fairview", Provides.zoning)[0].key == "rlis_zoning_metro"


def test_a_county_wide_dataset_reaches_a_city_with_no_local_layer() -> None:
    # Happy Valley is WES-served and publishes no sanitary mains. The county
    # district polygons are what keep it from reading as unsewered.
    p = load_pipeline()

    keys = [d.key for d in p.for_layer("or/clackamas/happy-valley", Provides.utility)]
    assert keys == ["util_sewer_district_clackamas"]


def test_switching_a_jurisdiction_off_removes_it_from_the_run() -> None:
    p = load_pipeline()

    assert not p.enabled("or/multnomah/maywood-park")
    assert "or/multnomah/maywood-park" not in p.active()
    assert p.enabled("or/multnomah/portland")


def test_a_jurisdiction_nobody_declared_is_off() -> None:
    # Coverage is claimed, never assumed. Defaulting an unknown city to "on"
    # would have it screened against nothing.
    assert not load_pipeline().enabled("or/washington/beaverton")


def test_every_source_lands_in_the_working_crs() -> None:
    # A service publishing something else declares native_srid and is
    # reprojected on the way in. A mismatch that slipped through would put
    # every lot in the wrong place without raising anything.
    p = load_pipeline()

    for ds in p.datasets.values():
        assert ds.native_srid != p.working_srid


def test_the_registry_can_be_read_aloud() -> None:
    lines = describe(load_pipeline())

    assert any(line.startswith("or/multnomah/portland: Portland Maps zoning") for line in lines)
    assert not any("NOTHING" in line for line in lines)


# --- what the loader refuses ------------------------------------------


def test_a_minimal_registry_is_enough(tmp_path: Path) -> None:
    p = load_pipeline(config(MINIMAL, tmp_path))

    assert p.active() == ("or/multnomah/portland",)


def test_an_arcgis_layer_without_fields_is_refused(tmp_path: Path) -> None:
    bad = MINIMAL.replace("    fields: [ZONE]\n", "")

    with pytest.raises(PipelineError, match="geometry nobody can use"):
        load_pipeline(config(bad, tmp_path))


def test_zoning_without_a_zone_field_is_refused(tmp_path: Path) -> None:
    # The field is called ZONE, zonecode, DESIGNATION and PLANDIST.CZONE across
    # fourteen cities. Guessing is not a strategy.
    bad = MINIMAL.replace("    zone_field: ZONE\n", "")

    with pytest.raises(PipelineError, match="must name the field"):
        load_pipeline(config(bad, tmp_path))


def test_a_zone_field_missing_from_its_own_field_list_is_refused(tmp_path: Path) -> None:
    bad = MINIMAL.replace("zone_field: ZONE", "zone_field: ZONECODE")

    with pytest.raises(PipelineError, match="not among its fields"):
        load_pipeline(config(bad, tmp_path))


def test_a_dataset_that_serves_nothing_is_refused(tmp_path: Path) -> None:
    bad = MINIMAL.replace("    serves: [or/multnomah/portland]\n", "")

    with pytest.raises(PipelineError, match="serves nothing"):
        load_pipeline(config(bad, tmp_path))


def test_an_rlis_member_is_required(tmp_path: Path) -> None:
    bad = MINIMAL.replace("kind: arcgis", "kind: rlis_zip")

    with pytest.raises(PipelineError, match="must name the member"):
        load_pipeline(config(bad, tmp_path))


def test_a_pointless_reprojection_is_refused(tmp_path: Path) -> None:
    # Declaring native_srid equal to the working CRS implies a reprojection
    # that never happens, which is worse than saying nothing.
    bad = MINIMAL.replace("    serves:", "    native_srid: 2913\n    serves:")

    with pytest.raises(PipelineError, match="drop it rather than"):
        load_pipeline(config(bad, tmp_path))


def test_a_jurisdiction_no_dataset_covers_is_refused(tmp_path: Path) -> None:
    bad = MINIMAL.replace(
        "  or/multnomah/portland: true\n",
        "  or/multnomah/portland: true\n  or/multnomah/gresham: true\n",
    )

    with pytest.raises(PipelineError, match="no dataset covers it"):
        load_pipeline(config(bad, tmp_path))


def test_a_registry_without_a_working_crs_is_refused(tmp_path: Path) -> None:
    with pytest.raises(PipelineError, match="working_srid"):
        load_pipeline(config("display_srid: 4326\n", tmp_path))


def test_every_problem_is_reported_at_once(tmp_path: Path) -> None:
    # Fixing config one error per run is how a fourteen-city registry takes an
    # afternoon instead of ten minutes.
    bad = MINIMAL.replace("    fields: [ZONE]\n", "").replace(
        "  or/multnomah/portland: true\n",
        "  or/multnomah/portland: true\n  or/multnomah/gresham: true\n",
    )

    with pytest.raises(PipelineError) as exc:
        load_pipeline(config(bad, tmp_path))

    assert "geometry nobody can use" in str(exc.value)
    assert "no dataset covers it" in str(exc.value)


# --- coverage semantics -----------------------------------------------


def test_a_county_serves_every_jurisdiction_under_it() -> None:
    ds = Dataset(
        key="x",
        kind="arcgis",
        label="regional",
        provides="overlay",
        url="https://example.gov/x/0",
        fields=["A"],
        serves=["or/multnomah"],
    )

    assert ds.covers("or/multnomah")
    assert ds.covers("or/multnomah/portland")
    assert not ds.covers("or/clackamas/milwaukie")


def test_a_similar_name_is_not_the_same_jurisdiction() -> None:
    ds = Dataset(
        key="x",
        kind="arcgis",
        label="city",
        provides="overlay",
        url="https://example.gov/x/0",
        fields=["A"],
        serves=["or/multnomah/wood"],
    )

    assert not ds.covers("or/multnomah/wood-village")
