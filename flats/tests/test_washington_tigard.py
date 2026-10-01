"""Tigard: the readings a reviewer would stop on.

Title 18 of the Tigard Municipal Code, the Community Development Code, read
from eCode360 (TI5024) as twenty-two chapters, current through Ordinance
26-13. Metro's regional zoning layer prints the code's own thirteen names
(RES-A to RES-E, COM, MUC, MUE, MUR, MU-CBD, TMU, IND, PR) and no plan
district subarea. The draft is pinned here where it reads against the grain
of a quick look, so a later edit has to argue with it.

- **The pod is a rowhouse development.** 18.30 makes a "Quad" two units
  stacked over two, and a "Rowhouse" any attached dwelling sharing a
  sidewall that is not a quad. Four side-by-side units are four rowhouses.
- **Nine zones admit it, four refuse.** RES-A to RES-E, MUR, MUC, MU-CBD and
  TMU allow it; COM and MUE allow housing only in mixed use and print
  Rowhouses N; IND and PR prohibit the Residential Use.
- **A rowhouse is a state-law townhouse, each on its own lot** (18.30, by
  way of ORS 197A.420(1)(h)). Steph, 2026-10-01: "If it's split lots, then
  that's our answer." Table 18.805.1's Rowhouse rows size the rowhouses' own
  lots: the minimum is kept on the one lot (18.40.130.B, 18.280.040.B) and on
  the split path as a ``unit_lots`` variant, and the MAXIMUM lot bounds only
  the unit lots, so the one lot carries no density floor from it.
- **MUC's blank cells are no limit** (Steph, 2026-10-01: "Empty means no
  limit"): Table 18.280.1 has no MUC column and Table 18.805.1's MUC rowhouse
  cells are blank, so lot, width, yards and height are exempt. Nothing is
  borrowed from another column.
- **The sub-area refusals ride on ``inside_mapped_use_area``**, which no map
  held draws: MUR and MUC inside Washington Square, MU-CBD where the subarea
  asks a 15 ft first storey.
- **TMU's 12 ft first storey is held** as ``min_ground_story_ft``, against
  the pod's stated 12 ft ground storey (Steph, 2026-10-01: "Yes, 12 ft or
  more").
- **TMU's court is reached by one 10 ft lane** (Steph, 2026-10-01: a 10 ft
  one-lane drive works in the Triangle, cars taking turns). 18.660.070.G.2
  caps rowhouse driveways at 10 ft and prints no two-way minimum; the pod's
  own 12 ft lane breaches the cap. ``driveway_one_lane_ft`` 10 is the lane
  the screen draws there.
"""

from __future__ import annotations

import pytest

from flats.encode.dispositions import by_state, notes
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer, Status
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

TIGARD = "or/washington/tigard"

ADMITTED = ("RES-A", "RES-B", "RES-C", "RES-D", "RES-E", "MUR", "MUC", "MU-CBD", "TMU")
REFUSED = ("COM", "MUE", "IND", "PR")

#: Table 18.805.1's Rowhouse rows and Table 18.280.1's columns, per zone:
#: (min lot per rowhouse, max lot per rowhouse, width, front, street side,
#: rear, height). ``None`` is a printed "None", held as ``exempt``. The
#: maximum lot is the printed figure; it bounds each rowhouse's own lot and
#: no field holds it (the 2026-10-01 ruling).
RESIDENTIAL = {
    "RES-A": (1500, 3000, 25, 20, 20, 25, 35),
    "RES-B": (1500, 3000, 25, 20, 20, 25, 35),
    "RES-C": (1250, 1750, 20, 15, 15, 15, 35),
    "RES-D": (750, 1250, None, 15, 15, 15, 35),
    "RES-E": (None, 1000, 20, 15, 10, 15, 45),
}


@pytest.fixture(scope="module")
def tigard() -> Layer:
    return load_rules()[TIGARD]


def _text(quote: str) -> str:
    return " ".join(ProvenanceStore().quote(quote).split())


def test_every_zone_metro_prints_is_held(tigard: Layer) -> None:
    """Thirteen zone blocks and no map rulings: Metro's ZONE values for
    Tigard are the code's own names. FAR and INST, which the district
    harvest finds in the text, are ruled in test_districts."""
    assert set(tigard.zones) == {*ADMITTED, *REFUSED}
    assert dict(tigard.zone_rulings) == {}
    assert list(tigard.ingest["juris_city_codes"]) == ["TIGARD"]


def test_the_pod_is_a_rowhouse_not_a_quad() -> None:
    text = _text(f"{TIGARD}/tdc.18.30.definitions.txt#L1028-L1029,L1032-L1033")
    assert (
        '"Quad" - A type of attached housing consisting of two dwelling units on a first story'
        in text
    )
    assert (
        '"Rowhouse" - A type of attached housing that shares a common sidewall with one '
        "or more dwelling units, but excluding apartments, courtyard units, and quads"
    ) in text


def test_nine_zones_admit_the_pod(tigard: Layer) -> None:
    admitted = {
        z for z, held in tigard.zones.items() if held.values["quadplex_allowed"].value
    }
    assert admitted == set(ADMITTED)


def test_the_grouping_note_is_met_by_four_units(tigard: Layer) -> None:
    """RES-A to RES-C print Rowhouses L[2]; note 2 limits a grouping to five."""
    for zone in ("RES-A", "RES-B", "RES-C"):
        use = tigard.zones[zone].values["quadplex_allowed"]
        assert "Rowhouses of up to 5 units per grouping allowed." in _text(
            use.prov.quote
        ), zone
    assert "L[2]" in _text(f"{TIGARD}/tdc.18.110.residential-zones.txt#L208")


def test_the_refusals(tigard: Layer) -> None:
    for zone in REFUSED:
        held = tigard.zones[zone]
        assert set(held.values) == {"quadplex_allowed"}, zone
        assert held.values["quadplex_allowed"].value is False, zone
    rows = _text(tigard.zones["COM"].values["quadplex_allowed"].prov.quote)
    assert "Rowhouses 18.280 N Y N Y" in rows
    for zone in ("IND", "PR"):
        assert "Residential Use P" in _text(
            tigard.zones[zone].values["quadplex_allowed"].prov.quote
        ), zone


@pytest.mark.parametrize("zone", sorted(RESIDENTIAL))
def test_the_residential_rowhouse_rows(tigard: Layer, zone: str) -> None:
    lot, most, width, front, street_side, rear, height = RESIDENTIAL[zone]
    held = tigard.zones[zone].values
    if lot is None:
        assert held["min_lot_sqft"].exempt is True
        assert held["max_density_du_per_acre"].exempt is True
    else:
        assert held["min_lot_sqft"].per_dwelling == lot
        assert held["max_density_du_per_acre"].sqft_per_unit == lot
    # The maximum lot bounds each rowhouse's own lot, not the one lot.
    assert most in (3000, 1750, 1250, 1000)
    assert "min_density_du_per_acre" not in held
    if width is None:
        assert held["min_lot_width_ft"].exempt is True
    else:
        assert held["min_lot_width_ft"].value == width
    assert held["setback_front_ft"].value == front
    assert held["setback_street_side_ft"].value == street_side
    assert held["setback_rear_ft"].value == rear
    assert held["setback_side_ft"].value == 5
    assert held["setback_front_max_ft"].value == 20
    assert held["max_height_ft"].value == height
    assert held["min_frontage_ft"].value == 15
    assert held["max_impervious_pct"].value == 80
    assert held["min_landscaped_pct"].value == 20


def test_a_rowhouse_is_a_townhouse_on_its_own_lot() -> None:
    """The 2026-10-01 ruling's two sentences. Tigard defines no townhouse or
    townhome; its Rowhouse takes the state's, and the state's puts each unit
    on an individual lot or parcel."""
    rowhouse = _text(f"{TIGARD}/tdc.18.30.definitions.txt#L1032-L1033")
    assert (
        "A rowhouse is considered the same as a townhouse within the meaning of state law."
        in rowhouse
    )
    state = _text("or/hb.2138.2025.txt#L57-L59")
    assert "each dwelling unit is located on an individual lot or parcel" in state
    lots = _text(f"{TIGARD}/tdc.18.805.lot-standards.txt#L31")
    assert (
        "Dimensional standards for lots created or configured for residential" in lots
    )


@pytest.mark.parametrize("zone", ["RES-A", "RES-B", "RES-C", "RES-D"])
def test_the_minimum_lot_is_each_rowhouses_own_on_the_split_path(
    tigard: Layer, zone: str
) -> None:
    """One lot: the per-rowhouse product (18.40.130.B, 18.280.040.B). Split:
    the per-rowhouse figure on each unit lot, Durham's pattern, which the
    screen multiplies by the four lots -- the same parent area both ways."""
    lot = RESIDENTIAL[zone][0]
    held = tigard.zones[zone].values["min_lot_sqft"]
    assert held.value == 4 * lot
    (split,) = held.variants
    assert (split.value, split.when) == (lot, ("unit_lots",))


def test_the_one_lot_carries_no_density_floor_from_the_maximum_lot(
    tigard: Layer,
) -> None:
    """Steph, 2026-10-01. The maximum lot was a cap of four times itself on
    the one lot (12,000 sq ft in RES-A); it reaches only the unit lots now,
    on the one lot and on the split path both."""
    rules = RuleSet(load_rules())
    for zone in ("RES-A", "RES-B", "RES-C", "RES-D", "RES-E", "MUR"):
        assert "min_density_du_per_acre" not in tigard.zones[zone].values, zone
        for conditions in ((), ("unit_lots",)):
            got = rules.resolve(TIGARD, zone, conditions, lot={"lot_sqft": 40_000})
            assert "min_density_du_per_acre" not in got.values, (zone, conditions)


def test_the_lot_table_reads_as_printed() -> None:
    """The minimum and maximum Rowhouse rows, RES-A to MUR (MUC's blank cell
    is dropped by the extractor -- a reader doubt in the handoff)."""
    text = _text(f"{TIGARD}/tdc.18.805.lot-standards.txt#L93-L100,L139-L146")
    assert "Rowhouse 1,500 1,500 1,250 750 None None None" in text
    assert "Rowhouse 3,000 3,000 1,750 1,250 1,000 None 870" in text


def test_the_common_wall_and_the_alley_lift_the_yards(tigard: Layer) -> None:
    for zone in ("RES-A", "RES-B", "RES-C", "RES-D", "RES-E", "MUR"):
        held = tigard.zones[zone].values
        (wall,) = held["setback_side_ft"].variants
        assert (wall.value, wall.when) == (0, ("attached_wall",)), zone
        (alley,) = held["setback_rear_ft"].variants
        assert (alley.value, alley.when) == (0, ("alley_at_rear",)), zone
    text = _text(f"{TIGARD}/tdc.18.280.rowhouses.txt#L87-L89")
    assert "This standard does not apply to a common wall lot line" in text
    assert (
        "There is no rear setback requirement when the rear property line abuts an alley"
        in text
    )


def test_mur_holds_the_stricter_of_its_two_printed_columns(tigard: Layer) -> None:
    held = tigard.zones["MUR"].values
    assert held["setback_front_ft"].value == 10
    assert held["setback_street_side_ft"].value == 10
    assert held["max_height_ft"].value == 45
    assert held["min_lot_sqft"].exempt is True
    assert "min_density_du_per_acre" not in held
    assert held["min_lot_width_ft"].value == 16


def test_mucs_blank_cells_are_no_limit(tigard: Layer) -> None:
    """Steph, 2026-10-01: "Empty means no limit." Exempt, each cite naming
    the ruling, and nothing carried across from another column (Happy Valley
    MURX). The frontage is stated for every rowhouse lot and is kept."""
    held = tigard.zones["MUC"].values
    for field in (
        "max_height_ft",
        "min_lot_sqft",
        "min_lot_width_ft",
        "setback_front_ft",
        "setback_street_side_ft",
        "setback_side_ft",
        "setback_rear_ft",
    ):
        assert held[field].exempt is True, field
        assert "Steph's ruling 2026-10-01" in held[field].prov.cite, field
    assert held["min_frontage_ft"].value == 15
    header = _text(f"{TIGARD}/tdc.18.280.rowhouses.txt#L74")
    assert "MUR-2" in header
    assert "MUC" not in header
    lot_row = _text(f"{TIGARD}/tdc.18.805.lot-standards.txt#L93-L100")
    assert lot_row == "Rowhouse 1,500 1,500 1,250 750 None None None"


def test_the_sub_area_refusals_wait_on_a_map(tigard: Layer) -> None:
    for zone in ("MUR", "MUC", "MU-CBD"):
        (inside,) = tigard.zones[zone].values["quadplex_allowed"].variants
        assert (inside.value, inside.when) == (False, ("inside_mapped_use_area",)), zone
    assert tigard.zones["TMU"].values["quadplex_allowed"].variants == ()


def test_mu_cbd_holds_the_strictest_subarea(tigard: Layer) -> None:
    held = tigard.zones["MU-CBD"].values
    assert held["setback_front_ft"].value == 5
    assert held["setback_front_max_ft"].value == 10
    assert held["setback_rear_ft"].value == 5
    assert held["max_height_ft"].value == 45
    assert held["min_building_height_ft"].value == 20
    assert held["min_density_du_per_acre"].value == 25
    assert held["max_density_du_per_acre"].value == 50
    assert held["parking_street_setback_ft"].value == 10
    assert "driveway_min_width_two_way_ft" not in held


def test_tmu_is_its_own_chapter(tigard: Layer) -> None:
    held = tigard.zones["TMU"].values
    assert held["min_lot_sqft"].exempt is True
    assert held["setback_front_ft"].value == 1
    assert held["setback_front_max_ft"].value == 12
    assert held["setback_side_ft"].value == 0
    assert held["setback_rear_ft"].value == 0
    assert held["max_height_stories"].value == 4
    assert "max_height_ft" not in held
    assert held["min_ground_story_ft"].value == 12
    assert "First story 12 feet (min.)" in _text(held["min_ground_story_ft"].prov.quote)
    assert held["parking_min_per_unit"].value == 0
    assert (
        held["parking_stall_width_ft"].value,
        held["parking_stall_depth_ft"].value,
    ) == (
        7.5,
        17.5,
    )
    assert held["parking_street_setback_ft"].value == 35
    assert held["driveway_approach_max_width_ft"].value == 10
    assert (
        "Driveways for rowhouses and small form residential development must be 10 feet or less in width."
        in _text(held["driveway_approach_max_width_ft"].prov.quote)
    )


def test_the_triangle_court_is_reached_by_one_ten_foot_lane(tigard: Layer) -> None:
    """Steph, 2026-10-01: a 10 ft one-lane drive works in the Triangle.

    G.2 is a ceiling on every rowhouse driveway, and the pod's lane (12 ft)
    is wider than it; TMU prints no two-way or one-way minimum to raise it.
    The ruling is held as the lane itself, the G.2 figure, and the screen
    draws it: 10 beside the building and 10 at the street, never the pod's
    12 and never a 20 ft two-way borrowed from 18.280, which TMU does not
    apply."""
    from flats.designs.model import load_catalog
    from flats.score.paper import court_across, drive_at_street

    held = tigard.zones["TMU"].values
    one = held["driveway_one_lane_ft"]
    assert one.value == held["driveway_approach_max_width_ft"].value == 10
    assert "Steph's ruling 2026-10-01" in one.prov.cite
    assert "must be 10 feet or less in width" in _text(one.prov.quote)
    for absent in ("driveway_min_width_two_way_ft", "driveway_min_width_one_way_ft"):
        assert absent not in held
        assert absent not in tigard.defaults
    rules = RuleSet(load_rules())
    zone = rules.resolve(TIGARD, "TMU", ())
    for design in load_catalog().active():
        assert design.parking.lane_ft > 10, design.key
        across = court_across(design, zone)
        assert across.lane_ft == 10, design.key
        assert "driveway_one_lane_ft" in across.from_code
        assert drive_at_street(design, zone) == 10, design.key
    # Nowhere else in Tigard: the 18.280 zones keep their 20 ft shared access.
    for name in ("RES-A", "MUR", "MUC"):
        assert "driveway_one_lane_ft" not in tigard.zones[name].values, name


def test_the_shared_access_is_twenty_feet(tigard: Layer) -> None:
    for zone in ("RES-A", "RES-B", "RES-C", "RES-D", "RES-E", "MUR", "MUC"):
        held = tigard.zones[zone].values
        assert held["driveway_min_width_two_way_ft"].value == 20, zone
        assert held["driveway_min_width_one_way_ft"].value == 20, zone
        assert held["parking_street_setback_ft"].value == 20, zone
    text = _text(f"{TIGARD}/tdc.18.280.rowhouses.txt#L121-L123")
    assert "the minimum paved width of the shared access is 20 feet" in text


def test_parking_is_zero_required_and_no_maximum(tigard: Layer) -> None:
    assert tigard.defaults["parking_min_per_unit"].value == 0
    assert tigard.defaults["parking_max_per_unit"].exempt is True


def test_the_corner_and_the_private_road(tigard: Layer) -> None:
    corner = tigard.definitions["corner_lot"]
    assert corner.test == "intersecting_frontages"
    assert corner.max_intersection_angle_deg == 135.0
    assert corner.drives_count is True
    assert corner.alleys_count is False
    assert tigard.private_drives.street is True
    assert tigard.defaults["front_lot_line_corner"].value == "shortest"
    assert "the shortest of the two property lines that abut the street" in _text(
        tigard.defaults["front_lot_line_corner"].prov.quote
    )
    assert tigard.defaults["corner_access_street"].value == "any"


def test_the_footnotes_are_all_ruled() -> None:
    rows = notes(TIGARD)
    assert by_state(rows) == {"encoded": 5, "dismissed": 5}
    encoded = {(n.doc.rsplit("/", 1)[-1], n.line) for n in rows if n.state == "encoded"}
    assert encoded == {
        ("tdc.18.110.residential-zones.txt", 215),
        ("tdc.18.280.rowhouses.txt", 88),
        ("tdc.18.280.rowhouses.txt", 89),
        ("tdc.18.650.downtown.txt", 481),
        ("tdc.18.650.downtown.txt", 483),
    }


def test_nothing_in_the_draft_is_verified(tigard: Layer) -> None:
    for zone, held in tigard.zones.items():
        for field, value in held.values.items():
            assert value.status is not Status.verified, (zone, field)
            for variant in value.variants:
                assert variant.status is not Status.verified, (zone, field)
    for field, value in tigard.defaults.items():
        assert value.status is not Status.verified, field
