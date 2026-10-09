"""Net area is the lot less what each city's own list takes off it.

Steph's option A (2026-10-02, FOLLOWUPS 30): an ordinary existing lot
dedicates nothing and sets nothing aside, so its net area is the lot less the
deductions its city lists that something here measures -- floodplain and the
mapped resource overlays -- and everything else the list names is assumed
absent, by name. Overlaps between the measured areas are unknown, so net area
is a range; a rate that agrees with itself at both ends is settled.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from flats.encode.port_quadfit import layer_id_for
from flats.rules.loader import RuleLoadError, load_rules
from flats.rules.model import Layer
from flats.rules.net_area import (
    DEDUCTIONS,
    DRIVE_AISLE,
    FLOODPLAIN,
    MEASURED,
    SHOWN,
    SLOPES,
    NetArea,
    measured_deductions,
    net_span,
)

pytestmark = pytest.mark.unit

OVERLAYS = Path(__file__).resolve().parents[2] / "Lot Analysis" / "quadfit" / "config" / "overlays.yaml"


@pytest.fixture(scope="module")
def layers() -> dict[str, Layer]:
    return load_rules()


def _rates(layers: dict[str, Layer]):
    for layer_id, layer in sorted(layers.items()):
        for zone_code, zone in sorted(layer.zones.items()):
            for name, value in sorted(zone.values.items()):
                if value.measured_on is not None:
                    yield layer_id, zone_code, name, value


# --- the range ----------------------------------------------------------


def test_a_list_that_takes_nothing_measurable_is_the_lot() -> None:
    """Fairview subtracts street right-of-way, which is already outside an
    existing tax lot: net area is the lot, and the rate simply runs."""
    assert net_span(NetArea(), 8_000, {}) == (8_000, 8_000)


def test_one_certain_deduction_is_exact() -> None:
    assert net_span(NetArea(less=(FLOODPLAIN,)), 8_000, {FLOODPLAIN: 2_000}) == (6_000, 6_000)


def test_two_certain_deductions_are_a_range_because_they_may_overlap() -> None:
    """Floodplain and a stream overlay usually lie on the same ground. The
    most the lot keeps is the lot less the larger of the two; the least, the
    lot less both."""
    net = NetArea(less=(FLOODPLAIN, "oregon_city_nrod"))

    assert net_span(net, 8_000, {FLOODPLAIN: 1_000, "oregon_city_nrod": 1_500}) == (5_500, 6_500)


def test_a_deduction_on_a_reading_not_yet_ruled_only_lowers_the_floor_of_the_range() -> None:
    net = NetArea(may_less=(FLOODPLAIN,))

    assert net_span(net, 8_000, {FLOODPLAIN: 2_000}) == (6_000, 8_000)


def test_a_deduction_nobody_measured_on_this_lot_settles_nothing() -> None:
    """A lot with no s5o row, or a bundle older than the column: never read as
    "none here"."""
    net = NetArea(less=(FLOODPLAIN,))

    assert net_span(net, 8_000, None) is None
    assert net_span(net, 8_000, {}) is None


def test_the_pods_own_drive_counts_only_where_the_plan_drew_it() -> None:
    net = NetArea(may_less=(DRIVE_AISLE,))

    assert net_span(net, 8_000, {}, drive_aisle_sqft=None) is None
    assert net_span(net, 8_000, {}, drive_aisle_sqft=2_500) == (5_500, 8_000)


def test_an_overlay_reported_larger_than_the_lot_takes_the_lot_and_no_more() -> None:
    """s5o sums each polygon's intersection, so overlapping polygons in one
    layer can report more than the lot holds."""
    least, most = net_span(NetArea(less=(FLOODPLAIN,)), 8_000, {FLOODPLAIN: 9_000})

    assert least == most == 1.0  # no land at all, not a negative acre


# --- what the bridge reads ------------------------------------------------


def test_the_floodplain_is_the_floodway_and_the_fringe_together() -> None:
    """quadfit splits FEMA's floodplain into a carved floodway and a flagged
    fringe that excludes it; the city's "100-year floodplain" is both."""
    got = measured_deductions({"ovl_fema_sfha_sqft": 1_200.0, "ovl_fema_floodway_sqft": 300.0})

    assert got[FLOODPLAIN] == 1_500.0
    assert got["fema_floodway"] == 300.0


def test_a_column_the_row_does_not_carry_is_not_a_zero() -> None:
    got = measured_deductions({"ovl_fema_sfha_sqft": 1_200.0, "ovl_oregon_city_nrod_sqft": float("nan")})

    assert FLOODPLAIN not in got  # the floodway half is missing
    assert "oregon_city_nrod" not in got  # NaN is not a measurement
    assert "gresham_hcra" not in got


def test_every_measured_deduction_is_a_column_the_bridge_reads() -> None:
    from flats.ingest.quadfit import S5O_COLUMNS

    for columns in MEASURED.values():
        for column in columns:
            assert column in S5O_COLUMNS, column


# --- the rule files -------------------------------------------------------


def test_every_rate_on_a_net_acre_states_its_citys_list(layers: dict[str, Layer]) -> None:
    """A new density row per net acre that nobody taught its list would quietly
    keep the old gross-area bound and hold lots option A settles."""
    rows = list(_rates(layers))

    assert len(rows) >= 170
    untaught = [f"{lid}/{zone}.{name}" for lid, zone, name, value in rows if value.net_area is None]
    assert untaught == []


def test_a_list_names_only_maps_laid_over_its_own_city(layers: dict[str, Layer]) -> None:
    """quadfit measures an overlay only on the jurisdictions overlays.yaml
    lists for it, and writes 0 -- not nothing -- everywhere else. A layer that
    named a map never laid over its city would read every lot as clear of it."""
    specs = yaml.safe_load(OVERLAYS.read_text(encoding="utf-8"))["overlays"]
    covers: dict[str, set[str] | None] = {}
    for spec in specs:
        reach = spec.get("jurisdictions")
        covers[spec["key"]] = None if reach == "all" else {layer_id_for(j) for j in reach}
    wrong = []
    for lid, zone, name, value in _rates(layers):
        for key in (*value.net_area.less, *value.net_area.may_less):
            if key == DRIVE_AISLE or key in SLOPES:
                continue  # the plan's own drive; lidar, laid over every lot
            overlay = "fema_sfha" if key == FLOODPLAIN else key
            reach = covers[overlay]
            if reach is not None and lid not in reach:
                wrong.append(f"{lid}/{zone}.{name}: {key}")
    assert wrong == []


def test_beaverton_and_cornelius_take_the_drive_and_the_floodplain_for_certain(
    layers: dict[str, Layer],
) -> None:
    """Steph, 2026-10-02: the pod's drive is a common driveway (neither code
    defines one), and constrained land comes off whether or not anyone set it
    aside in a tract -- "very few will have done that"."""
    lists = [
        value.net_area
        for lid, _zone, _name, value in _rates(layers)
        if lid in {"or/washington/beaverton", "or/washington/cornelius"}
        and value.net_area is not None
        and DRIVE_AISLE in (*value.net_area.less, *value.net_area.may_less)
    ]

    assert len(lists) >= 30
    assert all({DRIVE_AISLE, FLOODPLAIN} <= set(net.less) for net in lists)


def test_the_three_floor_only_places_net_their_floors_and_nothing_else(
    layers: dict[str, Layer],
) -> None:
    """King City, Wood Village and Washington County state a minimum on the net
    acre and no maximum on it (FOLLOWUPS 30, 2026-10-04). Washington County's
    300-2.8 counts the same land "when calculating maximum allowed densities"
    and switches itself off in North Bethany, so those stay on the whole lot.
    King City's and the county's lists say "may" or "natural resources" with
    no map named, so nothing comes off them for certain; Wood Village names
    floodplains outright."""
    netted = {
        (lid, zone, name): value.net_area
        for lid, zone, name, value in _rates(layers)
        if lid
        in {
            "or/washington/king-city",
            "or/multnomah/wood-village",
            "or/washington/_unincorporated",
        }
    }

    assert sorted((lid.rsplit("/", 1)[1], zone) for lid, zone, _ in netted) == sorted(
        [
            ("king-city", "KTTC"), ("king-city", "KTBB"), ("king-city", "KTC"), ("king-city", "KTRC"),
            ("wood-village", "LR 7.5"), ("wood-village", "LR 12"),
            ("wood-village", "MR 2"), ("wood-village", "MR 4"),
            ("_unincorporated", "TO:R24-40"), ("_unincorporated", "TO:R40-80"),
            ("_unincorporated", "NMU"), ("_unincorporated", "CCMU"), ("_unincorporated", "CBD"),
        ]
    )
    assert {name for _, _, name in netted} == {"min_density_du_per_acre"}
    for (lid, _zone, _name), net in netted.items():
        if lid == "or/multnomah/wood-village":
            assert net.less == (FLOODPLAIN,)
        else:
            assert net.less == () and FLOODPLAIN in net.may_less
        assert net.assumed_none


def test_a_deduction_nothing_measures_is_refused_by_name(tmp_path: Path) -> None:
    layer = tmp_path / "or" / "x" / "y.yaml"
    layer.parent.mkdir(parents=True)
    layer.write_text(
        """
layer: or/x/y
kind: city
label: Y
zones:
  R:
    cite_default: {cite: "Y 1", url: "https://example.invalid", retrieved: "2026-10-02"}
    max_density_du_per_acre:
      value: 20
      measured_on:
        fact: net_developable_area
        cite: Y 2
        quote: "or/x/y/2.txt#L1"
        less: [slopes_over_25_percent]
""",
        encoding="utf-8",
    )
    with pytest.raises(RuleLoadError, match="not a deduction anything here measures"):
        load_rules(tmp_path)


def test_the_vocabulary_is_the_measured_maps_the_slopes_and_the_drive() -> None:
    assert DEDUCTIONS == {*MEASURED, *SLOPES, DRIVE_AISLE}


def test_each_citys_slope_takes_the_grade_its_sentence_names(layers: dict[str, Layer]) -> None:
    """FOLLOWUPS 30(e)/38(b), read 2026-10-04: a certain sentence is
    ``less``; Oregon City's 25-35% band is the director's call, West Linn
    names the RLIS layer the lidar stands in for, and Washington County
    says "may be excluded" -- those are ``may_less``. Beaverton's and Wood
    Village's slopes count only inside a landslide area nothing maps yet."""
    want = {
        "or/washington/hillsboro": ({"slope_25"}, set()),
        "or/clackamas/milwaukie": ({"slope_25"}, set()),
        "or/clackamas/gladstone": ({"slope_25"}, set()),
        "or/clackamas/oregon-city": ({"slope_35"}, {"slope_25"}),
        "or/clackamas/west-linn": (set(), {"slope_25"}),
        "or/washington/cornelius": ({"slope_25"}, set()),
        "or/washington/_unincorporated": (set(), {"slope_20"}),
    }
    seen: dict[str, set[tuple[frozenset[str], frozenset[str]]]] = {}
    for lid, _zone, _name, value in _rates(layers):
        net = value.net_area
        sure = frozenset(k for k in net.less if k in SLOPES)
        maybe = frozenset(k for k in net.may_less if k in SLOPES)
        left = [i for i in net.assumed_none if "slope" in i.lower() and "landslide" not in i.lower()]
        if lid in want:
            if sure or maybe:
                seen.setdefault(lid, set()).add((sure, maybe))
            assert left == [], f"{lid}: a slope still assumed absent"
        else:
            assert not (sure or maybe), f"{lid}: a slope no sentence names"
    assert set(seen) == set(want)
    for lid, got in seen.items():
        assert got == {(frozenset(want[lid][0]), frozenset(want[lid][1]))}, lid


def test_every_deduction_has_a_name_the_lot_page_can_show() -> None:
    assert set(SHOWN) == DEDUCTIONS
