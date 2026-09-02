"""Unit tests for the s5o overlay/slope stage geometry helpers."""

from __future__ import annotations

import pytest

pytest.importorskip("yaml")
pytest.importorskip("shapely")
pytest.importorskip("pandas")

pytestmark = pytest.mark.unit


def _lots(rows):
    import pandas as pd

    return pd.DataFrame(rows)


def _spec(**over):
    from common import OverlaySpec

    base = dict(key="t", name="test", action="carve", jurisdictions=["gresham"])
    base.update(over)
    return OverlaySpec(**base)


def test_overlay_columns_any_touch_and_area():
    from shapely.geometry import box

    from s5o_overlays import overlay_columns

    lot_a = box(0, 0, 100, 100)        # half covered by the overlay
    lot_b = box(200, 0, 300, 100)      # boundary contact only (shares an edge)
    lot_c = box(0, 0, 100, 100)        # overlapped but wrong jurisdiction
    overlay = [box(50, 0, 200, 100)]
    lots = _lots([
        {"jurisdiction": "gresham", "lot_geom": lot_a},
        {"jurisdiction": "gresham", "lot_geom": lot_b},
        {"jurisdiction": "portland", "lot_geom": lot_c},
    ])
    flags, sqft = overlay_columns(lots, _spec(), overlay)
    assert list(flags) == [True, False, False]
    assert sqft[0] == pytest.approx(50 * 100, rel=1e-6)
    assert sqft[1] == 0.0 and sqft[2] == 0.0


def test_fill_holes_recovers_the_resource_a_buffer_ring_leaves_out():
    """A lot sitting inside a wetland must not read as clear ground.

    Wilsonville publishes SROZ_ImpactArea as the 25 ft ring around each
    Significant Resource and not the resource itself, so the polygon is a
    doughnut whose hole is the thing being protected. Screened as fetched, a
    lot entirely inside the resource intersects nothing and grades clear --
    the overlay reports the opposite of the truth on exactly the worst lots.

    Filling the interior rings recovers resource + buffer, which is the extent
    WDC 4.139.02 regulates. The check on the real layer: polygon 1 fetched as a
    ring is 3.12 acres, and filled it is 27.39 -- its own ACRES attribute says
    the resource is 24.27, and 24.27 + 3.12 = 27.39 to the penny.
    """
    from shapely.geometry import MultiPolygon, Polygon, box

    from s5o_overlays import _fill_holes

    ring = Polygon(
        box(0, 0, 100, 100).exterior.coords,
        [box(25, 25, 75, 75).exterior.coords],
    )
    assert ring.area == pytest.approx(10000 - 2500)
    filled = _fill_holes(ring)
    assert filled.area == pytest.approx(10000)
    assert not filled.interiors
    # A lot wholly inside the hole -- the case the unfilled layer misses.
    assert not ring.intersects(box(40, 40, 60, 60))
    assert filled.contains(box(40, 40, 60, 60))

    # Multipart geometry keeps every part.
    multi = MultiPolygon([ring, box(200, 0, 300, 100)])
    out = _fill_holes(multi)
    assert out.area == pytest.approx(20000)

    # Anything without interior rings is returned unchanged in area.
    plain = box(0, 0, 10, 10)
    assert _fill_holes(plain).area == pytest.approx(100)


def test_carve_envelopes_subtracts_buffered_overlay():
    from shapely.geometry import box

    from s5o_overlays import carve_envelopes

    env = box(0, 0, 100, 100)
    lots = _lots([
        {"jurisdiction": "gresham", "geom": env},
        {"jurisdiction": "portland", "geom": env},  # rule doesn't apply here
    ])
    spec = _spec(buffer_ft=10)
    carved = carve_envelopes(lots, [spec], {"t": [box(90, -10, 200, 110)]})
    # overlay edge at x=90 minus 10 ft buffer -> buildable ends at x=80
    assert carved[0].area == pytest.approx(80 * 100, rel=1e-3)
    assert carved[1].area == pytest.approx(100 * 100, rel=1e-9)


def test_carve_can_empty_an_envelope():
    from shapely.geometry import box

    from s5o_overlays import carve_envelopes

    lots = _lots([{"jurisdiction": "gresham", "geom": box(0, 0, 50, 50)}])
    carved = carve_envelopes(lots, [_spec()], {"t": [box(-10, -10, 60, 60)]})
    assert carved[0].is_empty


def test_dem_stats_on_synthetic_ramp(tmp_path):
    rasterio = pytest.importorskip("rasterio")
    import math

    import numpy as np
    from rasterio.transform import from_origin
    from shapely.geometry import box

    from s5o_overlays import DemIndex

    # 10% uniform ramp: elevation rises 0.1 ft per ft of x. Tile written in
    # the working CRS so the 2913->tile transform is the identity.
    minx, maxy = 7_000_000.0, 600_100.0
    cols = np.arange(100, dtype=np.float32)
    elev = np.tile(0.1 * cols, (100, 1))
    with rasterio.open(
        tmp_path / "ramp.tif", "w", driver="GTiff", height=100, width=100,
        count=1, dtype="float32", crs="EPSG:2913",
        transform=from_origin(minx, maxy, 1, 1),
    ) as ds:
        ds.write(elev, 1)

    dem = DemIndex(tmp_path)
    poly = box(minx + 20, maxy - 80, minx + 80, maxy - 20)
    mean, p85, mx = dem.stats(poly)
    for v in (mean, p85, mx):
        assert v == pytest.approx(10.0, abs=0.5)

    # Polygon outside every tile -> NaNs, not a crash.
    far = box(7_100_000, 700_000, 7_100_010, 700_010)
    assert all(math.isnan(v) for v in dem.stats(far))

    # Sliver narrower than one pixel rounds to a zero-size window —
    # rasterio's Window.intersection raises on empty overlap; must be NaNs,
    # not a WindowError (crashed the 2026-07-27 production run 60k lots in).
    sliver = box(minx + 50.0, maxy - 50.2, minx + 50.1, maxy - 50.0)
    assert all(math.isnan(v) for v in dem.stats(sliver))

    # tile_of: inside -> 0, outside -> None (drives the tile-sorted loop).
    assert dem.tile_of(poly) == 0
    assert dem.tile_of(far) is None
