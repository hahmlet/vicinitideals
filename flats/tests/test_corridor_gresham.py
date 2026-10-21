"""Gresham's CMF corridor, read off the street network by name
(flats/geom/corridor.py NamedCorridor, flats/config/corridors.yaml).

GDC Table 4.0420 note 2 and Table 4.0430 note 14 change CMF's rules on "the
areas of CMF along the NE Glisan Street and NE 162nd Avenue corridors", and
Gresham maps no such area. Steph 2026-10-20: "Yes, map it." These tests pin
the three answers -- a street line on the corridor is True, a lot in a CMF
block that reaches neither street is False, a lot behind the frontage of a
block that does is left unanswered (the config's switch) -- and that missing
data never answers.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import shapely
from shapely.geometry import LineString, box, mapping

from flats.geom.corridor import (
    NamedCorridor,
    load_maps,
    named_specs,
    observed_corridors,
    off_corridor_lines,
)
from flats.ingest.quadfit import observed_facts

pytestmark = pytest.mark.unit

GRESHAM = "or/multnomah/gresham"
X0, Y0 = 7_700_000.0, 690_000.0

# The street network (RLIS fields). Glisan runs east-west 30 ft south of the
# corridor block; NE 162nd runs north from Burnside 30 ft east of it, and
# below Burnside the same line is SE 162nd. NE 183rd is the side street at
# the block's west end, NE Hoyt the street behind it, SE Stark is Rockwood.
STREETS = [
    ("NE", "GLISAN", "ST", LineString([(X0 - 2000, Y0 - 30), (X0 + 2000, Y0 - 30)])),
    ("NE", "162ND", "AVE", LineString([(X0 + 630, Y0 - 900), (X0 + 630, Y0 + 2000)])),
    ("SE", "162ND", "AVE", LineString([(X0 + 630, Y0 - 3000), (X0 + 630, Y0 - 900)])),
    ("NE", "183RD", "AVE", LineString([(X0 - 30, Y0 - 30), (X0 - 30, Y0 + 1000)])),
    ("NE", "HOYT", "ST", LineString([(X0 - 500, Y0 + 330), (X0 + 1000, Y0 + 330)])),
    ("SE", "STARK", "ST", LineString([(X0 + 9000, Y0 - 30), (X0 + 11000, Y0 - 30)])),
]

# CMF blocks, drawn to the lot lines: one on the corridor, one on SE 162nd
# south of Burnside, one in Rockwood. And a CMU block on Glisan, which the
# corridor does not read.
CORRIDOR_BLOCK = box(X0, Y0, X0 + 600, Y0 + 300)
SOUTH_BLOCK = box(X0 + 660, Y0 - 2500, X0 + 900, Y0 - 2000)
ROCKWOOD_BLOCK = box(X0 + 10_000, Y0, X0 + 10_300, Y0 + 300)
CMU_BLOCK = box(X0 - 600, Y0, X0 - 60, Y0 + 300)


def _lot(x: float, y: float, streets: dict[str, bool]) -> tuple[list[list[object]], bytes]:
    """A 100 x 100 lot at (x, y) and its edges; ``streets`` marks which sides
    are street lines (south, east, north, west)."""
    corners = [(x, y), (x + 100, y), (x + 100, y + 100), (x, y + 100)]
    sides = ["south", "east", "north", "west"]
    edges: list[list[object]] = []
    for i, side in enumerate(sides):
        (x1, y1), (x2, y2) = corners[i], corners[(i + 1) % 4]
        edges.append([x1, y1, x2, y2, "F" if streets.get(side) else "S"])
    return edges, shapely.to_wkb(box(x, y, x + 100, y + 100))


ON_GLISAN = _lot(X0 + 100, Y0, {"south": True})
CORNER_183RD = _lot(X0, Y0, {"south": True, "west": True})
BEHIND = _lot(X0 + 100, Y0 + 200, {"north": True})
ROCKWOOD = _lot(X0 + 10_100, Y0, {"south": True})
SE_162ND = _lot(X0 + 660, Y0 - 2300, {"west": True})


def _fc(features: list[dict[str, object]]) -> str:
    return json.dumps({"type": "FeatureCollection", "features": features})


def _snapshot(root: Path, *, streets: bool = True, names: list[tuple[str, str, str, LineString]] = STREETS) -> Path:
    blocks = [(CORRIDOR_BLOCK, "CMF"), (SOUTH_BLOCK, "CMF"), (ROCKWOOD_BLOCK, "CMF"), (CMU_BLOCK, "CMU")]
    (root / "corridor_blocks_gresham.geojson").write_text(
        _fc([{"type": "Feature", "properties": {"ZONE": z}, "geometry": mapping(g)} for g, z in blocks]),
        encoding="utf-8",
    )
    if streets:
        (root / "rlis_streets.geojson").write_text(
            _fc(
                [
                    {
                        "type": "Feature",
                        "properties": {"PREFIX": p, "STREETNAME": n, "FTYPE": t},
                        "geometry": mapping(g),
                    }
                    for p, n, t, g in names
                ]
            ),
            encoding="utf-8",
        )
    return root


def _row(lot: tuple[list[list[object]], bytes], zone: str = "CMF") -> dict[str, object]:
    edges, wkb = lot
    return {
        "TLID": "1N3E31CC  -00100",
        "jurisdiction": "gresham",
        "zone": zone,
        "tier": "A",
        "edges_json": json.dumps(edges),
        "front_bearings_json": "[0.0]",
        "fronts_cul_de_sac": False,
        "split_zone": False,
        "ovl_fema_sfha": False,
        "ovl_fema_floodway": False,
        "sewer_main_dist_ft": 12.0,
        "in_sewer_district": None,
        "lot_wkb": wkb,
    }


def _fact(lot: tuple[list[list[object]], bytes], maps: tuple[object, ...], zone: str = "CMF") -> bool | None:
    return observed_facts(_row(lot, zone), corridors=maps).get("civic_corridor")  # type: ignore[arg-type]


@pytest.fixture()
def maps(tmp_path: Path) -> tuple[object, ...]:
    return load_maps(_snapshot(tmp_path))


def test_the_registered_corridor_is_gresham_cmf_on_glisan_and_ne_162nd() -> None:
    (spec,) = named_specs()
    assert spec.condition == "civic_corridor"
    assert spec.serves == (GRESHAM,)
    assert spec.zones == {"CMF"}
    assert spec.streets == ("NE GLISAN ST", "NE 162ND AVE")
    assert spec.blocks == "corridor_blocks_gresham"
    # Open with Steph (2026-10-20): unanswered until ruled.
    assert spec.behind_frontage is None


def test_the_snapshot_builds_one_named_corridor(maps: tuple[object, ...]) -> None:
    (corridor,) = maps
    assert isinstance(corridor, NamedCorridor)
    assert corridor.covers(GRESHAM) and not corridor.covers("or/multnomah/portland")
    # Three CMF blocks (the CMU block is not CMF); only the first reaches.
    assert len(corridor.blocks) == 3
    assert sorted(corridor.reaches) == [False, False, True]


def test_a_lot_fronting_glisan_is_on_the_corridor(maps: tuple[object, ...]) -> None:
    assert _fact(ON_GLISAN, maps) is True


def test_a_corner_lot_with_its_side_street_on_183rd_and_its_front_on_glisan(maps: tuple[object, ...]) -> None:
    assert _fact(CORNER_183RD, maps) is True


def test_a_lot_behind_the_frontage_of_a_corridor_block_is_unanswered(maps: tuple[object, ...]) -> None:
    got = observed_facts(_row(BEHIND), corridors=maps)  # type: ignore[arg-type]
    assert "civic_corridor" not in got


def test_a_cmf_lot_in_rockwood_is_off_the_corridor(maps: tuple[object, ...]) -> None:
    assert _fact(ROCKWOOD, maps) is False


def test_se_162nd_south_of_burnside_is_not_the_corridor(maps: tuple[object, ...]) -> None:
    assert _fact(SE_162ND, maps) is False


def test_no_street_network_answers_nothing(tmp_path: Path) -> None:
    maps = load_maps(_snapshot(tmp_path, streets=False))
    assert maps == ()
    for lot in (ON_GLISAN, BEHIND, ROCKWOOD):
        assert "civic_corridor" not in observed_facts(_row(lot), corridors=maps)


def test_no_blocks_answers_nothing(tmp_path: Path) -> None:
    _snapshot(tmp_path)
    (tmp_path / "corridor_blocks_gresham.geojson").unlink()
    assert load_maps(tmp_path) == ()


def test_a_named_street_the_network_lacks_answers_nothing(tmp_path: Path) -> None:
    # Without NE 162nd in the network every block that reaches only 162nd
    # would read as off the corridor: a decisive False out of a data gap.
    no_162nd = [s for s in STREETS if not (s[0] == "NE" and s[1] == "162ND")]
    assert load_maps(_snapshot(tmp_path, names=no_162nd)) == ()


def test_only_cmf_lots_on_gresham_are_asked(maps: tuple[object, ...]) -> None:
    assert _fact(ON_GLISAN, maps, zone="CMU") is None
    edges, wkb = ON_GLISAN
    assert observed_corridors(edges, "or/multnomah/portland", maps, zone="CMF", lot=wkb) == {}  # type: ignore[arg-type]
    # A lot with no shape cannot be placed in a block: unanswered, unless a
    # street line already settles it.
    assert observed_corridors(BEHIND[0], GRESHAM, maps, zone="CMF", lot=None) == {}  # type: ignore[arg-type]
    assert observed_corridors(edges, GRESHAM, maps, zone="CMF", lot=None) == {"civic_corridor": True}  # type: ignore[arg-type]


def test_the_behind_frontage_switch_answers_without_code(tmp_path: Path) -> None:
    from flats.geom.corridor import NAMED_PATH

    _snapshot(tmp_path)
    text = NAMED_PATH.read_text(encoding="utf-8")
    assert "behind_frontage: null" in text
    for value, expected in (("true", True), ("false", False)):
        cfg = tmp_path / f"corridors_{value}.yaml"
        cfg.write_text(text.replace("behind_frontage: null", f"behind_frontage: {value}"), encoding="utf-8")
        maps = load_maps(tmp_path, named=str(cfg))
        assert _fact(BEHIND, maps) is expected
        # The switch moves only the lots behind the frontage.
        assert _fact(ON_GLISAN, maps) is True
        assert _fact(ROCKWOOD, maps) is False


def test_the_named_corridor_never_touches_the_per_line_setback(maps: tuple[object, ...]) -> None:
    # off_corridor_lines is Portland's Map 130-1 per-line give-back; a named
    # corridor is not a tightening map and is never read there.
    edges, _ = ON_GLISAN
    assert off_corridor_lines(edges, GRESHAM, maps) == (False,) * 4  # type: ignore[arg-type]
