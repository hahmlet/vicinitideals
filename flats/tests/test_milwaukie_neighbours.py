"""Milwaukie's residential edge, MMC 19.504.4.A (FOLLOWUPS 52, 2026-10-09).

"All yards that abut, or are adjacent across a right-of-way from the R-MD
Zone shall be at least as wide as the required front yard width of the
adjacent R-MD Zone" -- 20 ft. DMU and GMU, the two zones here that reach the
building (by unit lots), carry it as 20 ft variants on `abuts_residential_zone`.

What must hold: the layer's `neighbours:` block answers the "abut" half from
the lot lines; the "across a right-of-way" half is a street line no lot-level
reading holds, so the street yards stay held open on
`faces_residential_zone_across_street` -- measuring the shared lines must
never relax a yard that faces R-MD across the street.
"""

from __future__ import annotations

import pytest

from flats.geom.neighbour import Line, observed_neighbours
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

MIL = "or/clackamas/milwaukie"
ABUTS = "abuts_residential_zone"
ACROSS = "faces_residential_zone_across_street"


@pytest.fixture(scope="module")
def corpus() -> dict:
    return load_rules()


def test_the_block_names_r_md_and_r_hd_and_puts_every_other_zone_on_the_relaxing_side(corpus) -> None:
    layer = corpus[MIL]
    r = layer.neighbours[ABUTS]
    assert set(r.true_for) == {"R-MD", "R-HD"}
    # Every zone block on the map is on one side, so no Milwaukie neighbour
    # is left unresolved by a missing code.
    assert set(r.true_for) | set(r.false_for) == set(layer.zones)
    text = ProvenanceStore().quote(r.quote)
    assert "abutting or adjacent to properties zoned R-MD" in text
    assert "at least as wide as the required front yard width" in text


def test_a_shared_line_with_r_md_settles_it_and_an_all_commercial_lot_is_clear(corpus) -> None:
    rules = corpus[MIL].neighbours
    j = "milwaukie"
    beside = [Line(zones=((j, "R-MD"),), unresolved=0), Line(zones=((j, "DMU"),), unresolved=0)]
    clear = [Line(zones=((j, "DMU"),), unresolved=0), Line(zones=((j, "C-G"),), unresolved=0)]
    unread = [Line(zones=((j, "DMU"),), unresolved=0), Line(zones=(), unresolved=3)]
    assert observed_neighbours(beside, rules, j) == {ABUTS: True}
    assert observed_neighbours(clear, rules, j) == {ABUTS: False}
    assert observed_neighbours(unread, rules, j) == {}


@pytest.mark.parametrize("zone", ["DMU", "GMU"])
def test_side_and_rear_take_twenty_beside_a_residential_zone(corpus, zone: str) -> None:
    rules = RuleSet(corpus)
    for field in ("setback_side_ft", "setback_rear_ft"):
        assert rules.resolve(MIL, zone).values[field].value == 0
        assert rules.resolve(MIL, zone, {ABUTS}).values[field].value == 20


@pytest.mark.parametrize("zone", ["DMU", "GMU"])
def test_the_street_yards_stay_held_whatever_the_shared_lines_say(corpus, zone: str) -> None:
    # A lot with nothing residential across its shared lines can still face
    # R-MD across the street; the street yards are held open on that fact,
    # with the code's own sentence, until it is read per street line.
    rules = RuleSet(corpus)
    res = rules.resolve(MIL, zone)
    assert ACROSS in res.unencoded
    for field in ("setback_front_ft", "setback_street_side_ft"):
        held = corpus[MIL].zones[zone].values[field]
        assert held.qualified_by == ACROSS, field
        assert held.qualified_quote == "or/clackamas/milwaukie/19.500.supplementary.txt#L605"
    text = ProvenanceStore().quote("or/clackamas/milwaukie/19.500.supplementary.txt#L605")
    assert "adjacent across a right-of-way from the R-MD Zone" in text


# --- through the bridge -------------------------------------------------------


def test_a_dmu_lot_reads_its_shared_lines_and_is_held_on_the_street(corpus) -> None:
    import json

    from flats.designs.model import load_catalog
    from flats.encode.load import load_trusted
    from flats.ingest.quadfit import lot_from_row, screen_lot
    from flats.score import relief, slack
    from flats.score.flags import fact_code
    from flats.tests.test_utility_easement import lot_row

    trusted = load_trusted(strict=False).rules
    j = "milwaukie"
    # Street along the south edge; DMU and C-G across the three shared lines.
    across = [None, {"z": [[j, "DMU"]]}, {"z": [[j, "C-G"]]}, {"z": [[j, "DMU"]]}]
    row = lot_row(100.0, 200.0, TLID="11E36AA00100", jurisdiction=j, zone="DMU",
                  neighbour_zones_json=json.dumps(across))
    (s,) = screen_lot(
        lot_from_row(row, trusted.layers),
        [load_catalog().latest("pod56x36")],
        rules=trusted,
        policy=slack.load_policy(),
        relief=relief.load_policy(),
        step_deg=30.0,
    )
    assert s.lot.observed.get(ABUTS) is False
    assert ACROSS not in s.lot.observed
    assert fact_code(ACROSS) in {f.code for f in s.signed.flags}
    assert fact_code(ABUTS) not in {f.code for f in s.signed.flags}
