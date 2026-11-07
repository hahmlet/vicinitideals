"""Steph 2026-10-21: "Let's assume that the lots from the gis and other data
sources we have are legal. Every lot we try to purchase will go thru a legal
review." (rulings.yaml 2026-10-21-existing-taxlots-are-lots-of-record.)

Every existing taxlot is a lot of record, so where a code lets a lot of
record off its lot standards the one-lot path takes the relief
(``lot_of_record_relief``). Gresham is the first city encoded:

* 4.0431.C, the corridor districts: a lot of record that misses rows A, B or
  C (lot area, frontage, the width/depth ratio) may be developed anyway and
  is then exempt from the minimum density -- ``lot_dimensions``.
* Table 4.0130 note 2, the residential districts, on row B only: an
  undersized lot of record may be developed -- ``lot_area``. Row A (minimum
  site size) carries no such note and stays.

The unit-lots plat makes new lots, and they still meet the rows.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from flats.ingest.quadfit import townhouse
from flats.rules.loader import load_rules
from flats.score import relief, slack
from flats.score.flags import Colour
from flats.score.screen import screen
from flats.score.slack import Verdict
from flats.tests.test_round2_rulings import DESIGN, facts, fit, rules, run

pytestmark = pytest.mark.unit

GRESHAM = "or/multnomah/gresham"
DOCS = Path(__file__).resolve().parents[1] / "provenance" / "docs" / "or" / "multnomah" / "gresham"
FOOTNOTES = Path(__file__).resolve().parents[1] / "config" / "footnotes" / "or" / "multnomah" / "gresham.yaml"
RULINGS = Path(__file__).resolve().parents[1] / "config" / "rulings.yaml"


def checked(result) -> set[str]:
    return {c.check for c in result.checks}


# --- the screen ---------------------------------------------------------------


def test_an_undersized_lot_of_record_is_let_off_and_owes_no_density() -> None:
    small = rules(min_lot_sqft=7000, min_density_du_per_acre=40)
    plain = run(facts(), small)
    assert plain.colour is Colour.red
    assert "min_lot_area_sqft" in {b.check for b in plain.binds}

    got = run(facts(), rules(min_lot_sqft=7000, min_density_du_per_acre=40, lot_of_record_relief="lot_dimensions"))
    assert got.colour is Colour.green
    assert "min_lot_area_sqft" not in checked(got)
    # 4.0431.C: developed under the relief, so exempt from the density.
    assert "min_density_du_per_acre" not in checked(got)


@pytest.mark.parametrize(
    "missed",
    [
        {"min_frontage_ft": 80},  # row B's frontage; the lot has 60
        {"max_lot_depth_ratio": 0.5},  # row C, against a square lot
    ],
)
def test_lot_dimensions_lets_off_frontage_and_the_ratio(missed: dict) -> None:
    (name,) = missed
    lot = facts(lot_depth_ft=60)
    assert name in {b.check for b in run(lot, rules(**missed)).binds}
    got = run(lot, rules(lot_of_record_relief="lot_dimensions", **missed))
    assert name not in {b.check for b in got.binds}
    assert got.colour is Colour.green


def test_a_lot_that_meets_every_row_still_owes_the_density() -> None:
    """The exemption is for a lot developed under the relief. A big lot that
    clears rows A-C was not, and a minimum density it misses still holds --
    otherwise the relief would be a false GREEN on every big lot."""
    got = run(facts(), rules(min_density_du_per_acre=40, lot_of_record_relief="lot_dimensions"))
    density = next(c for c in got.checks if c.check == "min_density_du_per_acre")
    assert density.verdict is Verdict.fails


def test_lot_area_relief_reaches_lot_size_only() -> None:
    got = run(facts(), rules(min_lot_sqft=7000, min_frontage_ft=80, lot_of_record_relief="lot_area"))
    binds = {b.check for b in got.binds}
    assert "min_lot_area_sqft" not in binds
    assert "min_frontage_ft" in binds
    # Note 2 says nothing of density: a lot let off its size still owes it.
    owes = run(facts(), rules(min_lot_sqft=7000, min_density_du_per_acre=40, lot_of_record_relief="lot_area"))
    assert "min_density_du_per_acre" in checked(owes)


def test_a_passing_standard_is_still_recorded_under_the_relief() -> None:
    got = run(facts(), rules(min_lot_sqft=3000, lot_of_record_relief="lot_dimensions"))
    area = next(c for c in got.checks if c.check == "min_lot_area_sqft")
    assert area.threshold == 3000


def test_the_unit_lots_plat_makes_new_lots_and_meets_the_rows() -> None:
    got = screen(
        rules(min_lot_sqft=7000, land_division_parent_standards=True, lot_of_record_relief="lot_dimensions"),
        facts(),
        townhouse(DESIGN),
        fit(),
        policy=slack.SlackPolicy(tolerance={"fit_ft": 0.5}),
        relief=relief.load_policy(),
    )
    assert got.colour is Colour.red
    assert "min_lot_area_sqft" in {b.check for b in got.binds}


# --- Gresham's encoding -----------------------------------------------------


@pytest.fixture(scope="module")
def gresham():
    return load_rules()[GRESHAM]


@pytest.mark.parametrize("zone", ["CMF", "SC", "SC-RJ", "CMU"])
def test_the_corridor_takes_4_0431_c(gresham, zone: str) -> None:
    held = gresham.zones[zone].values["lot_of_record_relief"]
    assert held.value == "lot_dimensions"


@pytest.mark.parametrize("zone", ["LDR-5", "LDR-7", "TLDR", "TR", "MDR-12"])
def test_the_residential_districts_take_note_2(gresham, zone: str) -> None:
    held = gresham.zones[zone].values["lot_of_record_relief"]
    assert held.value == "lot_area"


@pytest.mark.parametrize("zone", ["MDR-24", "OFR"])
def test_row_a_site_size_carries_no_relief(gresham, zone: str) -> None:
    """Note 2 marks row B only. MDR-24 and OFR state their number on row A
    (minimum site size), so they take none."""
    assert "lot_of_record_relief" not in gresham.zones[zone].values


def test_the_stored_text_still_says_what_the_relief_cites() -> None:
    corridor = (DOCS / "4.0400.corridor.txt").read_text(encoding="utf-8").splitlines()
    c = " ".join(corridor[505:509]).lower()
    assert "lots of record" in c
    assert "density" in c
    residential = (DOCS / "4.0100.residential.txt").read_text(encoding="utf-8").splitlines()
    assert "lot of record" in " ".join(residential[373:375]).lower()


# --- Rockwood -----------------------------------------------------------------


def test_note_13_is_dismissed_and_its_reasons_are_still_in_the_text() -> None:
    """Steph 2026-10-21, "Yes on Rockwood setback": 7.0502(B) takes
    quadplexes out of 7.0501-7.0512, and 7.0512's "All Development" heading
    leaves townhouses out, so the pod takes Table 4.0430's setbacks."""
    entries = yaml.safe_load(FOOTNOTES.read_text(encoding="utf-8"))
    flat = entries if isinstance(entries, list) else [e for v in entries.values() if isinstance(v, list) for e in v]
    # Proof copy 4.0400.corridor.txt L480 until the cut (FOLLOWUPS 73, batch 5).
    (note,) = [e for e in flat if e.get("quote") == "or/multnomah/gresham/4/4.0430.txt#L157"]
    assert note["state"] == "dismissed"
    assert "fact" not in note

    design = (DOCS / "7.0500.rockwood-design.txt").read_text(encoding="utf-8").splitlines()
    exempt = " ".join(design[43:45]).lower()
    assert "do not apply" in exempt and "quadplexes" in exempt
    assert "except townhouses" in design[213].lower()


def test_both_rulings_are_registered() -> None:
    register = {e["id"]: e for e in yaml.safe_load(RULINGS.read_text(encoding="utf-8")) if isinstance(e, dict)}
    lor = register["2026-10-21-existing-taxlots-are-lots-of-record"]
    assert lor["scope"] == {}
    rw = register["2026-10-21-gresham-rockwood-setbacks"]
    assert rw["scope"]["city"] == "gresham"


# --- the sweep of every other layer (FOLLOWUPS 108, 2026-11-06) ---------------

SHORT = {"min_lot_sqft": 7000, "min_frontage_ft": 80, "min_lot_width_ft": 80}


@pytest.mark.parametrize(
    ("relief_name", "lifted", "kept"),
    [
        ("lot_standards", {"min_lot_area_sqft", "min_frontage_ft", "min_lot_width_ft"}, set()),
        ("lot_shape", {"min_frontage_ft", "min_lot_width_ft"}, {"min_lot_area_sqft"}),
        ("lot_area_frontage", {"min_lot_area_sqft", "min_frontage_ft"}, {"min_lot_width_ft"}),
        ("lot_area_width_depth", {"min_lot_area_sqft", "min_lot_width_ft"}, {"min_frontage_ft"}),
        ("lot_width", {"min_lot_width_ft"}, {"min_lot_area_sqft", "min_frontage_ft"}),
    ],
)
def test_each_relief_lifts_what_it_names_and_nothing_else(relief_name: str, lifted: set, kept: set) -> None:
    binds = {b.check for b in run(facts(), rules(lot_of_record_relief=relief_name, **SHORT)).binds}
    assert not lifted & binds
    assert kept <= binds


@pytest.mark.parametrize(
    "relief_name",
    ["lot_area", "lot_standards", "lot_shape", "lot_area_frontage", "lot_area_width_depth", "lot_width"],
)
def test_only_the_gresham_corridor_lifts_a_minimum_density(relief_name: str) -> None:
    got = run(facts(), rules(min_lot_sqft=7000, min_lot_width_ft=80, min_density_du_per_acre=40, lot_of_record_relief=relief_name))
    assert "min_density_du_per_acre" in checked(got)


def test_a_printed_floor_stops_the_area_and_only_the_area() -> None:
    wide = {"min_lot_sqft": 7000, "min_lot_width_ft": 80, "lot_of_record_relief": "lot_standards"}
    under = run(facts(), rules(lot_of_record_floor_sqft=6500, **wide))
    assert under.colour is Colour.red
    assert {b.check for b in under.binds} == {"min_lot_area_sqft"}
    over = run(facts(), rules(lot_of_record_floor_sqft=6000, **wide))
    assert over.colour is Colour.green
    assert not over.binds


@pytest.mark.parametrize("condition", ["creation_date", "adjoining_ownership", "per_dwelling_area"])
def test_a_condition_nobody_measured_is_never_green(condition: str) -> None:
    got = run(facts(), rules(min_lot_sqft=7000, lot_of_record_relief="lot_area", lot_of_record_condition=condition))
    assert got.colour is Colour.yellow
    assert not got.binds
    assert any(f.code == "MEASURE-LOT-OF-RECORD" for f in got.flags)


def test_a_lot_that_needs_no_relief_owes_no_condition() -> None:
    got = run(facts(), rules(min_lot_sqft=3000, lot_of_record_relief="lot_area", lot_of_record_condition="creation_date"))
    assert got.colour is Colour.green
    assert not any(f.code == "MEASURE-LOT-OF-RECORD" for f in got.flags)


def test_a_condition_does_not_save_a_lot_it_does_not_lift() -> None:
    got = run(facts(), rules(min_frontage_ft=80, lot_of_record_relief="lot_width", lot_of_record_condition="creation_date"))
    assert got.colour is Colour.red
    assert "min_frontage_ft" in {b.check for b in got.binds}


OUTRIGHT = [
    ("or/clackamas/milwaukie", ["R-MD", "R-HD", "DMU", "NMU", "GMU", "SMU"], "lot_standards"),
    ("or/clackamas/oregon-city", ["R-10", "R-8", "R-6", "R-5", "R-2", "R-3.5"], "lot_standards"),
    ("or/clackamas/west-linn", ["MU"], "lot_area"),
    ("or/multnomah/troutdale", ["LDR-1", "LDR-2", "MDR", "HDR", "MU-1", "MU-2", "MU-3"], "lot_shape"),
    ("or/washington/hillsboro", ["R-6", "R-4.5", "SCR-LD", "SCR-DNC", "MR-1", "SCR-MD", "MU-N"], "lot_standards"),
    ("or/washington/hillsboro", ["R-10", "R-8.5", "R-7", "MR-2", "MR-3", "SCR-HD"], "lot_shape"),
]
CONDITIONAL = [
    ("or/clackamas/estacada", ["C-2", "CMU", "NCR", "R-3"], "lot_area", "per_dwelling_area"),
    ("or/clackamas/tualatin", ["RL", "RML", "CO", "CC", "RMH", "RH", "RH/HR"], "lot_standards", "creation_date"),
    ("or/washington/beaverton", ["MR", "RMA", "RMB", "RMC", "CM-RM", "CM-MR", "NS"], "lot_width", "adjoining_ownership"),
    ("or/clackamas/happy-valley", ["R40", "R20", "R15", "R10", "R8.5", "R7", "R5", "MURS", "SFA", "MURA", "VTH"], "lot_area_width_depth", "creation_date"),
    ("or/clackamas/canby", ["R-1.5", "R-2", "C-R", "C-1"], "lot_width", "creation_date"),
    ("or/multnomah/portland", ["RM1", "RM2", "RM3", "RM4", "RMP", "RX"], "lot_standards", "adjoining_ownership"),
    ("or/multnomah/_unincorporated", ["LR5", "LR7", "LR10", "MR4"], "lot_area_frontage", "creation_date"),
]
#: Read and left: the code's words reach no four-unit building on an existing lot.
LEFT = [
    ("or/washington/hillsboro", "SCR-OTC"),  # 12.62.300 A.1 is dated and bars the pod
    ("or/multnomah/portland", "R5"),  # the row is Table 110-7's, not Table 110-3's
    ("or/multnomah/_unincorporated", "R5"),  # the same copy
    ("or/clackamas/west-linn", "R-7"),  # 68.040 A.4 asks a variance; 2026-10-02-no-variances
    ("or/clackamas/wilsonville", "R"),  # 4.192 .01-.02 keeps the lot size and standards
    ("or/washington/tigard", "RES-A"),  # 18.50.040 A.2: small form development only
]


@pytest.fixture(scope="module")
def corpus():
    return load_rules()


@pytest.mark.parametrize(("layer", "zones", "value"), OUTRIGHT)
def test_the_reliefs_taken_outright(corpus, layer: str, zones: list[str], value: str) -> None:
    for zone in zones:
        held = corpus[layer].zones[zone].values
        assert held["lot_of_record_relief"].value == value, zone
        assert "lot_of_record_condition" not in held, zone


@pytest.mark.parametrize(("layer", "zones", "value", "condition"), CONDITIONAL)
def test_the_reliefs_held_to_a_condition(corpus, layer: str, zones: list[str], value: str, condition: str) -> None:
    for zone in zones:
        held = corpus[layer].zones[zone].values
        assert held["lot_of_record_relief"].value == value, zone
        assert held["lot_of_record_condition"].value == condition, zone


@pytest.mark.parametrize(("layer", "zone"), LEFT)
def test_the_reliefs_read_and_left(corpus, layer: str, zone: str) -> None:
    assert "lot_of_record_relief" not in corpus[layer].zones[zone].values


@pytest.mark.parametrize(
    ("layer", "zone", "floor"),
    [
        ("or/washington/hillsboro", "R-6", 6000),
        ("or/washington/hillsboro", "R-4.5", 4500),
        ("or/washington/hillsboro", "SCR-LD", 3600),
        ("or/washington/hillsboro", "SCR-DNC", 3000),
        ("or/washington/hillsboro", "MR-1", 4500),
        ("or/washington/hillsboro", "SCR-MD", 2000),
        ("or/washington/hillsboro", "MU-N", 4000),
        ("or/clackamas/estacada", "C-2", 5000),
        ("or/clackamas/estacada", "CMU", 4000),
        ("or/clackamas/estacada", "NCR", 5000),
        ("or/multnomah/_unincorporated", "LR5", 3000),
    ],
)
def test_the_printed_floors(corpus, layer: str, zone: str, floor: int) -> None:
    assert corpus[layer].zones[zone].values["lot_of_record_floor_sqft"].value == floor


def test_the_ruling_records_the_sweep() -> None:
    assert "MEASURE-LOT-OF-RECORD" in RULINGS.read_text(encoding="utf-8")
