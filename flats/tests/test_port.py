"""The quadfit port and the backlog it feeds.

Two contracts. The port must lose nothing — a field quadfit encoded that FLATS
silently drops is the same class of failure as an unencoded zone, just quieter.
And nothing may arrive trusted: quadfit verified against one citation per row,
which does not carry over.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from flats.encode.port_quadfit import COUNTY, FIELD_MAP, layer_id_for, port, port_zone
from flats.rules.fields import FIELDS
from flats.rules.loader import load_rules
from flats.rules.model import Status
from flats.rules.resolver import RuleSet, Verdict

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG = REPO_ROOT / "flats" / "config" / "jurisdictions"


@pytest.fixture(scope="module")
def dry() -> dict:
    return port(write=False)


# --- the port ---------------------------------------------------------


def test_nothing_is_dropped(dry: dict) -> None:
    # Every quadfit column either maps to a registered field or is deliberately
    # skipped. An unported field is data loss, and it is silent, so it is a test.
    assert dry["unported"] == []


def test_every_quadfit_zone_arrives(dry: dict) -> None:
    assert dry["stats"]["zones"] == 96
    assert dry["stats"]["layers"] == len(COUNTY) == 18


def test_field_map_targets_are_registered() -> None:
    unknown = sorted(set(FIELD_MAP.values()) - set(FIELDS))
    assert unknown == [], f"FIELD_MAP points at unregistered fields: {unknown}"


def test_quadfit_verification_does_not_carry_over() -> None:
    # 73 of 96 rows were `verified` in quadfit against a coarser standard.
    values = [
        v
        for layer in RuleSet(load_rules()).layers.values()
        for zone in layer.zones.values()
        for v in zone.values.values()
    ]
    assert values, "no values loaded — the port did not write"
    assert {v.status for v in values} == {Status.draft}


def test_quadfit_confidence_survives_for_queue_ordering() -> None:
    # The port drops the trust but keeps the signal: rows quadfit called
    # verified are quick confirmations, the rest is real work.
    text = (CONFIG / "or" / "multnomah" / "portland.yaml").read_text(encoding="utf-8")
    assert "quadfit confidence:" in text


@pytest.mark.parametrize(
    "jurisdiction,expected",
    [
        ("portland", "or/multnomah/portland"),
        ("wood_village", "or/multnomah/wood-village"),
        ("multnomah_unincorporated", "or/multnomah/_unincorporated"),
        ("clackamas_unincorporated", "or/clackamas/_unincorporated"),
        ("oregon_city", "or/clackamas/oregon-city"),
    ],
)
def test_layer_id_mapping(jurisdiction: str, expected: str) -> None:
    assert layer_id_for(jurisdiction) == expected


def test_unmapped_jurisdiction_fails_loudly() -> None:
    with pytest.raises(KeyError):
        layer_id_for("beaverton")


def test_zone_citation_becomes_cite_default() -> None:
    row = {
        "zone": "R5",
        "source": "PCC 33.110.220",
        "source_url": "https://example.gov/33110",
        "confidence": "verified",
        "setback_front_ft": 10,
    }

    block, unported = port_zone(row, "2026-07-24")

    assert block["cite_default"]["cite"] == "PCC 33.110.220"
    assert block["setback_front_ft"] == 10
    assert unported == []


def test_unmapped_column_is_reported_not_swallowed() -> None:
    row = {"zone": "R5", "confidence": "verified", "some_new_standard": 42}

    block, unported = port_zone(row, "2026-07-24")

    assert unported == ["some_new_standard=42"]
    assert "UNPORTED" in block["notes"]


# --- what the port produced ------------------------------------------


def test_written_config_loads_through_the_real_loader() -> None:
    # The port writes YAML by hand; the loader is the only judge of whether it
    # is valid. Round-tripping is the whole point of doing this as a port.
    rules = RuleSet(load_rules())

    assert len(rules.layers) == 19  # 18 jurisdictions + the state layer
    assert sum(len(l.zones) for l in rules.layers.values()) == 102


def test_state_parking_preemption_reaches_a_city_zone() -> None:
    """The state cap reaches a city that has not spoken for itself."""
    res = RuleSet(load_rules()).resolve("or/multnomah/fairview", "R-6")

    parking = res.values["parking_min_per_unit"]
    assert parking.value == 1.0
    assert parking.layer == "or", "state cap must reach a city with no rule of its own"


def test_a_city_below_the_state_cap_keeps_its_own_number() -> None:
    """OAR 660-046-0220 bars a city from asking for MORE than one stall per
    unit. It does not oblige one to ask for any, and Portland asks for none.
    Reading the cap as a substitute would hand every Portland lot four stalls
    the city does not require -- about 1,300 sq ft of a site that has to fit
    the pod, its parking and its access."""
    res = RuleSet(load_rules()).resolve("or/multnomah/portland", "R5")

    parking = res.values["parking_min_per_unit"]
    assert parking.value == 0
    assert parking.layer == "or/multnomah/portland"
    assert not parking.preempted


def test_ported_zones_are_unverified_not_trusted() -> None:
    res = RuleSet(load_rules()).resolve("or/multnomah/portland", "R5")

    assert res.verdict is Verdict.unverified
    assert res.chain == ("or/multnomah/portland", "or")


def test_unencoded_zone_is_surfaced_not_dropped() -> None:
    # RM1 was the 14,426-lot hole this rebuild exists to close, and Chapter
    # 33.120 closed it. What the test is for outlives the example: a zone the
    # GIS reports and the rules do not carry must come back saying so, rather
    # than resolving off the state layer and reading like a thin encoding.
    res = RuleSet(load_rules()).resolve("or/multnomah/portland", "RM1")
    assert res.verdict is not Verdict.zone_not_encoded, "33.120 is encoded"

    res = RuleSet(load_rules()).resolve("or/multnomah/portland", "CM2")

    assert res.verdict is Verdict.zone_not_encoded


def test_ineligible_jurisdictions_kept_their_flag() -> None:
    off = {
        p.stem
        for p in CONFIG.rglob("*.yaml")
        if yaml.safe_load(p.read_text(encoding="utf-8")).get("eligible") is False
    }
    assert off == {"johnson-city", "lake-oswego", "rivergrove", "maywood-park"}


def test_ingest_metadata_survives_for_the_gis_stage() -> None:
    layer = yaml.safe_load((CONFIG / "or" / "multnomah" / "portland.yaml").read_text(encoding="utf-8"))

    assert layer["ingest"]["zoning_layer"]
    assert layer["ingest"]["zone_field"]


# --- corrections to what the port produced ----------------------------


def test_metro_label_zones_adopt_a_base_zone_rather_than_copying_it() -> None:
    """`RM/TOZ` and `R/SFLD` are labels in Metro's regional layer, not zones
    Fairview wrote. The port hand-copied a base zone's numbers under each of
    them with no citation on any of them. Copies stop tracking their source the
    first time the table is amended, silently, and nobody reading the derived
    zone has any way to notice — so the reference is the encoding."""
    rules = RuleSet(load_rules())

    for zone, base in (("RM/TOZ", "RM"), ("R/SFLD", "R-10")):
        res = rules.resolve("or/multnomah/fairview", zone)
        assert res.borrowed_from == (base,)
        front = res.values["setback_front_ft"]
        assert front.via == base
        assert front.prov.quote, f"{zone} front setback must cite the {base} row"


def test_wilsonville_rn_carries_no_maximum_front_setback() -> None:
    """Section 4.127 covers two unrelated things: the Frog Pond West
    residential sub-districts and the Commercial Main Street area. The port
    read RN's maximum front setback off Table 23A, the commercial one. Table
    8A, the residential table, states none — and a maximum front setback is
    not a harmless extra, it pushes every building to within twenty feet of
    the street and fails detached-house lots that comply perfectly well."""
    res = RuleSet(load_rules()).resolve("or/clackamas/wilsonville", "RN")

    assert "setback_front_max_ft" not in res.values
    assert res.values["max_coverage_pct"].value == 60, "the 90 is the commercial block"


def test_lr7_yards_all_come_from_the_row_the_zone_already_quoted() -> None:
    """MCC 39.4862(H) prints `20 5 10 15` under `Front Side Street Side Rear`.
    The port quoted that line for side and street side and overrode front and
    rear to 10 apiece, unquoted, from the state Model Code — a document that is
    not stored, in the direction that manufactures a false GREEN. OAR
    660-046-0220(2)(c) does not license the override either: it bars setbacks
    GREATER than the detached-single-family ones in the same zone, and this row
    IS that zone's single-family row."""
    res = RuleSet(load_rules()).resolve("or/multnomah/_unincorporated", "LR7")
    yards = {
        "setback_front_ft": 20,
        "setback_side_ft": 5,
        "setback_street_side_ft": 10,
        "setback_rear_ft": 15,
    }

    for name, expected in yards.items():
        got = res.values[name]
        assert got.value == expected, f"{name} is not the {expected} the row prints"
        assert got.prov.quote and got.prov.quote.endswith("#L409-L411"), (
            f"{name} must quote the header and the row together — four bare "
            f"numbers under four headers is how two of them got invented"
        )


def test_lake_oswego_coverage_is_a_height_band_not_a_number() -> None:
    """Both Lake Oswego coverage tables step down as the building gets taller,
    and both zones encoded the first row — the tallest allowance, written for
    the shortest building — as though it were the zone's one figure. The base
    has to be the row that holds at any height; the loose row is what a known
    pod height earns."""
    rules = RuleSet(load_rules())

    for zone, strict, loose in (("R-5", 35, 45), ("R-7.5", 25, 35)):
        plain = rules.resolve("or/clackamas/lake-oswego", zone)
        assert plain.values["max_coverage_pct"].value == strict

        low = rules.resolve("or/clackamas/lake-oswego", zone, conditions=["low_rise"])
        assert low.values["max_coverage_pct"].value == loose


def test_happy_valley_r20cc_adopts_r20_rather_than_copying_it() -> None:
    """R20CC is a zoning-layer code with no chapter behind it: LDC 16.22 names
    R-40, R-20 and R-15 and nothing else. Six hand-copied numbers under it were
    every Happy Valley row in the gap ledger."""
    rules = RuleSet(load_rules())
    res = rules.resolve("or/clackamas/happy-valley", "R20CC")

    assert res.borrowed_from == ("R20",)
    lot = res.values["min_lot_sqft"]
    assert lot.value == 20000 and lot.via == "R20"
    assert lot.prov.quote, "the borrowed value still cites the R-20 cell"


def test_happy_valley_side_yard_goes_to_zero_on_an_attached_wall() -> None:
    """Table 16.22.020-2 prints the interior side cell as `10/04` — ten, or
    nought, the trailing 4 being footnote 4 run up against the number. The
    footnote is what lets four units share three walls, and the port kept the
    ten and dropped the nought."""
    rules = RuleSet(load_rules())

    plain = rules.resolve("or/clackamas/happy-valley", "R20")
    assert plain.values["setback_side_ft"].value == 10, "the base is the wider half"

    attached = rules.resolve(
        "or/clackamas/happy-valley", "R20", conditions=["attached_wall"]
    )
    assert attached.values["setback_side_ft"].value == 0


def test_wilsonville_r_coverage_bands_on_lot_area() -> None:
    """4.122(.06)F is five rows on lot area, 50 percent at the small end
    falling to 20 at 20,000 sq ft, and the port held the loosest row as the
    zone's one figure. Lot area is a measurement the screen always has, so
    unlike a height band this one can be encoded exactly."""
    rules = RuleSet(load_rules())
    steps = {6000: 50, 7000: 50, 7500: 45, 10000: 40, 15000: 25, 19999: 25, 20000: 20, 40000: 20}

    for area, expected in steps.items():
        res = rules.resolve("or/clackamas/wilsonville", "R", lot={"lot_sqft": area})
        assert res.values["max_coverage_pct"].value == expected, f"{area} sq ft"

    # An unmeasured lot must not quietly take the loosest row. The base is the
    # table's last column, and the standard comes back ambiguous besides.
    blind = RuleSet(load_rules()).resolve("or/clackamas/wilsonville", "R")
    assert blind.values["max_coverage_pct"].value == 20
    assert blind.values["max_coverage_pct"].ambiguous


def test_wilsonville_townhouses_owe_no_setback_where_they_are_attached() -> None:
    """4.113(.02) says it twice, once in each lot-size block: "No setback is
    required along property lines where townhouses are attached." That
    sentence is what lets four units share three walls. Written as one
    band-less variant it collides with the 10 ft band on a large lot — two
    variants match, neither narrows the other, and the standard resolves
    ambiguous back to the base."""
    rules = RuleSet(load_rules())

    for area in (6000, 15000):
        plain = rules.resolve("or/clackamas/wilsonville", "R", lot={"lot_sqft": area})
        assert plain.values["setback_side_ft"].value > 0, "the base keeps the yard"

        attached = rules.resolve(
            "or/clackamas/wilsonville", "R", conditions=["attached_wall"],
            lot={"lot_sqft": area},
        )
        side = attached.values["setback_side_ft"]
        assert side.value == 0 and not side.ambiguous, f"{area} sq ft"


def test_clackamas_vr_rows_are_read_by_counting_their_values() -> None:
    """Table 315-3 merges cells across three zone columns, and the port read
    that as "no column can be attributed by position" and left six values
    unquoted. How many values a row prints settles it: three values under
    three headers is positional, and two identical values give the same answer
    whichever column the merge covers."""
    rules = RuleSet(load_rules())

    for zone in ("VR45", "VR57"):
        res = rules.resolve("or/clackamas/_unincorporated", zone)
        for name in (
            "setback_front_ft",
            "setback_front_max_ft",
            "setback_side_ft",
            "setback_rear_ft",
            "max_coverage_pct",
        ):
            assert res.values[name].prov.quote, f"{zone}.{name} is unquoted"

    # The one genuinely two-different-values row stays out of both zones.
    for zone in ("VR45", "VR57"):
        res = rules.resolve("or/clackamas/_unincorporated", zone)
        assert "min_lot_sqft" not in res.values
