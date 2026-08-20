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
    assert sum(len(l.zones) for l in rules.layers.values()) == 123


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

    # Portland states no minimum at all, so the field is exempted rather than
    # set to zero -- and the state ceiling does not fill the hole, because a
    # cap on what a city may require is not itself a requirement.
    assert "parking_min_per_unit" in res.exempted
    assert "parking_min_per_unit" not in res.values


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

    # Two Portland examples have been used here and both got encoded out from
    # under the test -- CM2 by Chapter 33.130, CI2 by 33.150. Portland now
    # carries every zone its GIS reports, so the example has to come from
    # somewhere else: Gresham's MDR-PV is 340 lots in a plan district whose
    # chapter is not fetched.
    res = RuleSet(load_rules()).resolve("or/multnomah/gresham", "MDR-PV")

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
    assert res.values["max_coverage_pct"].value != 90, "the 90 is the commercial block"


def test_wilsonville_rn_takes_the_binding_frog_pond_sub_district() -> None:
    """RN's numbers come from Table 8A, which is three rows — R-10 Large Lot,
    R-7 Medium Lot, R-5 Small Lot — and 4.127(.05)A.1 makes Figure 6 of the
    Frog Pond West Master Plan the official map of which row a lot is in.
    Figure 6 is a PDF: the city's Zoning layer serves a flat RN with only
    ZONE_CODE on it, the Comprehensive Plan layer a flat "Residential
    Neighborhood", and SA_FrogPondWest one attribute-free polygon. So the row
    that cannot turn a lot green by mistake governs, and R-10 is that row on
    every column the three disagree on.

    These are the four the spread is widest on. If somebody digitises Figure 6
    and carries the sub-district through, this test is what they change."""
    res = RuleSet(load_rules()).resolve("or/clackamas/wilsonville", "RN")

    strictest = {
        "max_coverage_pct": 40,  # against 45 and 60
        "min_lot_sqft": 8000,  # against 6,000 and 4,000
        "setback_front_ft": 20,  # against 15 and 12
        "min_lot_width_ft": 40,  # against 35 and 35
    }
    for name, value in strictest.items():
        got = res.values[name]
        assert got.value == value, f"{name} is not the binding sub-district row"
        assert got.prov.quote, f"{name} must quote Table 8A"

    # 4.113(.02), the citywide setback section, applies "unless otherwise
    # provided for by the Code or a legislative master plan". Table 8A is that
    # provision, so its townhouse zero does not reach into this zone: an RN pod
    # owes a side yard on the wall it shares.
    attached = RuleSet(load_rules()).resolve(
        "or/clackamas/wilsonville", "RN", conditions=("attached_wall",), lot={"lot_sqft": 6000}
    )
    assert attached.values["setback_side_ft"].value == 5


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

    # The one genuinely two-different-values row is still unreadable by
    # position, and Table 315-3 is still not where either zone's minimum lot
    # size comes from. Section 845.01 states one figure for a quadplex in
    # every district -- 7,000 square feet -- so the field is filled from there
    # and the merged cell above is simply not the evidence.
    for zone in ("VR45", "VR57"):
        res = rules.resolve("or/clackamas/_unincorporated", zone)
        held = res.values["min_lot_sqft"]
        assert held.value == 7000
        assert held.prov.quote.startswith("or/clackamas/_unincorporated/zdo.845.txt")


def test_the_three_derived_numbers_now_come_from_documents() -> None:
    """Three values reached the ledger's `unsourced` bucket -- no stored
    document stated them and they named no chapter that would. Each was a
    number somebody worked out rather than read, and each was loose:

      LR-7's 7,000 was the OAR 660-046-0220 cap, from an unstored rule that
      governs "Large Cities" while this layer is unincorporated county. MCC
      39.4862(C) states 5,000 sq ft per multiplex unit -- 20,000 for the pod.

      Fairview VSF's 4.5 was the average of a four-foot side and a five-foot
      side. The field holds one number for both sides, so 4.5 puts a wall six
      inches inside the five-foot line.

      Gresham MDR-24's 7,200 was four units divided by the 24.2-per-acre
      maximum density. Table 4.0130 states an 11,000 sq ft minimum site size.

    All three were answerable from documents already in the store. The
    assertion that matters is not the number but the quote beside it."""
    rules = RuleSet(load_rules())

    for layer, zone, field, value in (
        ("or/multnomah/_unincorporated", "LR7", "min_lot_sqft", 20000),
        ("or/multnomah/fairview", "VSF", "setback_side_ft", 5),
        ("or/multnomah/gresham", "MDR-24", "min_lot_sqft", 11000),
    ):
        got = rules.resolve(layer, zone).values[field]
        assert got.value == value, f"{zone}.{field}"
        assert got.prov.quote, f"{zone}.{field} is back to a bare number"


def test_troutdale_reads_the_quadplex_table_not_the_duplex_one() -> None:
    """3.130 is four tables -- duplex, triplex-and-quadplex, townhouse,
    cottage cluster -- printing nearly the same standards in nearly the same
    order. Three quotes pointed at the duplex table and agreed with the
    quadplex one by coincidence of layout. Six more values were bare, and the
    gap ledger read them as conditional because the driveway-access notes sit
    a few lines below the row. They are not: 3.130.B is six columns and both
    notes attach to the Town Center ones, which print "10 or 20" where these
    columns print a bare 10."""
    rules = RuleSet(load_rules())

    for zone, depth in (("LDR-1", 100), ("LDR-2", 80), ("MDR", 70)):
        res = rules.resolve("or/multnomah/troutdale", zone)
        assert res.values["setback_front_ft"].value == 10
        assert res.values["setback_street_side_ft"].value == 10
        assert res.values["min_lot_depth_ft"].value == depth
        for name in ("setback_front_ft", "setback_side_ft", "setback_street_side_ft"):
            assert res.values[name].prov.quote, f"{zone}.{name} is a bare number"

        # 3.130.C, the townhouse table, is the one-lot-per-unit path: lot
        # size, width and depth go away and the rear yard zeroes on an alley.
        split = rules.resolve("or/multnomah/troutdale", zone, conditions=("unit_lots",))
        assert "min_lot_sqft" not in split.values
        assert "min_lot_depth_ft" not in split.values
        assert split.values["setback_side_ft"].value == 5

        alley = rules.resolve(
            "or/multnomah/troutdale", zone, conditions=("unit_lots", "abuts_alley")
        )
        assert alley.values["setback_rear_ft"].value == 0


def test_wood_village_second_numbers_are_corner_lots_and_townhouses() -> None:
    """Five values stated two numbers each and one of them got written down.
    Neither number was wrong; the second was a different kind of lot. Table
    210-3 prints a Corner Lots block under the ordinary setbacks, and Table
    220-3's 75 percent coverage is the Townhouse column rather than the
    Duplex-Triplex-Quadplex one the pod is measured in."""
    rules = RuleSet(load_rules())

    plain = rules.resolve("or/multnomah/wood-village", "LR 7.5")
    corner = rules.resolve("or/multnomah/wood-village", "LR 7.5", conditions=("corner_lot",))
    assert (plain.values["setback_side_ft"].value, plain.values["setback_rear_ft"].value) == (5, 15)
    assert (corner.values["setback_side_ft"].value, corner.values["setback_rear_ft"].value) == (
        10,
        20,
    )

    for zone in ("MR 2", "MR 4"):
        res = rules.resolve("or/multnomah/wood-village", zone)
        assert res.values["max_coverage_pct"].value == 45
        split = rules.resolve("or/multnomah/wood-village", zone, conditions=("unit_lots",))
        assert split.values["max_coverage_pct"].value == 75

    # Both tables state a lot depth and a garage setback that nothing carried.
    for zone, depth in (("LR 7.5", 100), ("LR 12", 120), ("MR 2", 80), ("MR 4", 80)):
        res = rules.resolve("or/multnomah/wood-village", zone)
        assert res.values["min_lot_depth_ft"].value == depth
        assert res.values["setback_garage_entrance_ft"].value == 22


def test_the_flag_that_ends_a_screen_is_quoted_everywhere_it_resolves() -> None:
    """`quadplex_allowed` false makes every lot in a zone RED before a single
    dimension is measured, and it was a bare boolean in ten layers — the one
    value with the most authority and the least provenance. Anything that
    resolves now carries a document behind it."""
    rules = RuleSet(load_rules())

    bare = [
        f"{layer}/{zone}"
        for layer, layer_rules in rules.layers.items()
        for zone in layer_rules.zones
        if (value := rules.resolve(layer, zone).values.get("quadplex_allowed"))
        and not value.prov.quote
    ]
    assert bare == []


def test_two_zones_answer_differently_than_they_used_to() -> None:
    """Quoting the flag was supposed to be bookkeeping. Two zones read the
    other way once somebody opened the section."""
    rules = RuleSet(load_rules())

    # Wilsonville RN carried `true` on the argument that ORS 197A.420 preempts
    # the city. 4.127(.02)B.1.a.ii: "triplexes are permitted only on corner
    # lots, and quadplexes are not permitted."
    rn = rules.resolve("or/clackamas/wilsonville", "RN")
    assert rn.values["quadplex_allowed"].value is False
    assert "4.127" in rn.values["quadplex_allowed"].prov.cite

    # The rest of Wilsonville permits it by naming Middle Housing, which
    # 4.096(181) defines as the class containing quadplexes.
    for zone in ("R", "OTR", "PDR1", "PDR6"):
        res = rules.resolve("or/clackamas/wilsonville", zone)
        assert res.values["quadplex_allowed"].value is True

    # Multnomah LR-7 is neither permitted nor prohibited: MCC 39.4856 is the
    # CONDITIONAL USES section and (C) is the multiplex. An LR-7 lot is not
    # RED, it is a lot whose pod needs a hearing — which the traffic light can
    # only say if base and relief stay apart.
    lr7 = rules.resolve("or/multnomah/_unincorporated", "LR7")
    assert lr7.values["quadplex_allowed"].value is False
    with_hearing = rules.resolve(
        "or/multnomah/_unincorporated", "LR7", conditions=("conditional_use",)
    )
    assert with_hearing.values["quadplex_allowed"].value is True


def test_what_the_loader_still_drops_is_named() -> None:
    """An unquoted value does not resolve. It is not a wrong answer, it is a
    value the engine cannot see, which reads as encoded and behaves as absent —
    so the ones left have to be listed rather than counted."""
    debt = {
        (layer_id, w.zone, w.field)
        for layer_id, layer in load_rules(strict=False).items()
        for w in layer.wanted
    }
    # It reached empty once, and it took three different endings to get there.
    # Rivergrove's four were read: the RLDO is one stored document and 5.080
    # states all of them. Johnson City's was withdrawn — a prohibition inferred
    # from a statute that exempts the city rather than one printed anywhere, and
    # an uncited value is not a smaller debt than a missing one. Multnomah RR's
    # was quoted once the Rural Residential article was sliced out of the
    # chapter PDF the LR-7 slice already comes from.
    #
    # Then Portland's IR zone put two back, and they are a different kind of
    # debt from any of those three. Nothing is unread: Table 150-2 states the
    # standard plainly, as "1 ft. for every 2 ft. of building height but not
    # less than 10 ft." It is the file that cannot say it. A Value holds a
    # number and this one is a function of the design, so 13 ft is the answer
    # for a 26 ft pod and appears in no sentence anyone could cite for it.
    # Listing them is the point of the list.
    assert debt == {
        ("or/multnomah/portland", "IR", "setback_side_ft"),
        ("or/multnomah/portland", "IR", "setback_rear_ft"),
    }


def test_a_schedule_and_an_enum_are_values_too() -> None:
    """Neither is a number, and both spent the port unquoted — invisible for
    the same reason the booleans were."""
    rules = RuleSet(load_rules())

    # Portland writes coverage as a schedule: Table 110-5, RF through R2.5.
    for zone in ("R7", "R10", "R20"):
        curve = rules.resolve("or/multnomah/_unincorporated", zone).values["coverage_curve"]
        assert curve.value[0] == [0, 0, 50]
        assert curve.value[-1] == [20000, 4500, 7.5]
        assert "33.110.txt#L781-L786" in curve.prov.quote

    # Gresham's design districts require half the frontage built out in the
    # band between the minimum and maximum front setback, which is an axis.
    for zone in ("DRL-1", "DRL-2", "CMF"):
        axis = rules.resolve("or/multnomah/gresham", zone).values["orientation_constraint"]
        assert axis.value == "axis_required"
        assert "7.0400.middle-housing-design.txt#L410-L418" in axis.prov.quote
