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
