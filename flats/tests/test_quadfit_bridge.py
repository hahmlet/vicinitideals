"""The bridge from quadfit's county map into the screen (flats/ingest/quadfit.py).

Steph, 2026-09-17: "bridge from the county map for now, but we will need an
authoritative offline source." These tests pin what the bridge reads off
quadfit's stage files, how it says each fact in the registry's words, and
that what comes out the other end is the screen's own verdict with the
signed colour beside it and never in its place.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pandas as pd
import pytest
import shapely
import yaml

from flats.designs.model import Design, Orientation
from flats.encode.load import load_trusted
from flats.fit.angles import sweep
from flats.ingest.assign import ROW_COLUMNS
from flats.geom.edges import EdgeClass, Tier
from flats.ingest.quadfit import (
    OBSERVABLE,
    S4_COLUMNS,
    S5O_COLUMNS,
    SEWER_MAIN_REACH_FT,
    TIER,
    carved_rear_ft,
    compare,
    envelope_for,
    iter_rows,
    lot_edges,
    lot_from_row,
    observed_facts,
    per_lot,
    row_for,
    run,
    screen_lot,
    setbacks_for,
)
from flats.rules.conditions import CONDITIONS
from flats.score import relief, slack
from flats.score.screen import Triage

pytestmark = pytest.mark.unit

POD = """
version: 1
label: Four-plex pod
typology: townhome_rear_court
footprint: {width_ft: 56, depth_ft: 36}
units: 4
stories: 2
height_ft: 26
parking: {stalls_per_unit: 1.5, config: rear_court}
delivery: {method: modular, crane_required: true, crane_reach_ft: 60}
"""


def pod() -> Design:
    return Design(**{**yaml.safe_load(POD), "id": "pod"})


def pod4() -> Design:
    """The pod at one stall a home, the catalog's floor: a row of four."""
    spec = yaml.safe_load(POD)
    spec["parking"] = {**spec["parking"], "stalls_per_unit": 1.0}
    return Design(**{**spec, "id": "pod4"})


# A 50 x 100 lot at state-plane-sized coordinates, street along the south
# edge (bearing 0), and its envelope inset 10 / 5 / 5 the way s5 cuts it.
X0, Y0 = 7_650_000.0, 680_000.0
EDGES = [
    [X0, Y0, X0 + 50, Y0, "F"],
    [X0 + 50, Y0, X0 + 50, Y0 + 100, "S"],
    [X0 + 50, Y0 + 100, X0, Y0 + 100, "R"],
    [X0, Y0 + 100, X0, Y0, "S"],
]
ENVELOPE = shapely.box(X0 + 5, Y0 + 10, X0 + 45, Y0 + 95)


def row(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "TLID": "1S2E20AA  -15100",
        "jurisdiction": "portland",
        "zone": "R5",
        "tier": "A",
        "area_sqft": 5000.0,
        "frontage_ft": 50.0,
        "lot_width_ft": 50.0,
        "lot_depth_ft": 100.0,
        "edges_json": json.dumps(EDGES),
        "front_bearings_json": "[0.0]",
        "fronts_cul_de_sac": False,
        "split_zone": False,
        "ovl_fema_sfha": False,
        "ovl_fema_floodway": False,
        "sewer_main_dist_ft": 12.0,
        "in_sewer_district": None,
        "wkb": shapely.to_wkb(ENVELOPE),
    }
    base.update(over)
    return base


# --- the facts, in the registry's words --------------------------------------


def test_every_fact_the_bridge_observes_is_a_registered_site_fact() -> None:
    for name in OBSERVABLE:
        assert CONDITIONS[name].kind == "site_fact", name


def test_a_plain_interior_lot_on_a_main() -> None:
    got = observed_facts(row())
    assert got == {
        "abuts_alley": False,
        "alley_at_rear": False,
        "alley_at_side": False,
        "fronts_cul_de_sac": False,
        "corner_lot": False,
        "split_zone": False,
        "in_floodplain": False,
        "public_sewer": True,
    }
    # Every answer is one of the facts the module says it can observe.
    assert set(got) <= set(OBSERVABLE)


def test_an_alley_behind_a_corner_lot_on_a_bulb_in_the_floodplain() -> None:
    edges = [
        [X0, Y0, X0 + 50, Y0, "F"],
        [X0 + 50, Y0, X0 + 50, Y0 + 100, "F"],
        [X0 + 50, Y0 + 100, X0, Y0 + 100, "A"],
        [X0, Y0 + 100, X0, Y0, "S"],
    ]
    got = observed_facts(
        row(
            edges_json=json.dumps(edges),
            front_bearings_json="[0.0, 90.0]",
            alley_cover_json=json.dumps([None, None, "1" * 10, None]),
            fronts_cul_de_sac=True,
            split_zone=True,
            ovl_fema_sfha=True,
        )
    )
    assert got["alley_at_rear"] is True and got["abuts_alley"] is True
    assert got["alley_at_side"] is False
    assert got["corner_lot"] is True
    assert got["fronts_cul_de_sac"] is True
    assert got["split_zone"] is True
    assert got["in_floodplain"] is True


def test_a_corner_is_two_streets_at_least_45_degrees_apart_as_when_its_front_is_named() -> None:
    """FOLLOWUPS 4(e)(vi): the fact asks the same question as the naming
    (:func:`flats.geom.corner.two_streets`), not "two clustered directions"."""
    for bearings, fact in (("[0.0]", False), ("[0.0, 45.0]", True), ("[10.0, 100.0]", True)):
        assert observed_facts(row(front_bearings_json=bearings))["corner_lot"] is fact, bearings


def test_two_street_directions_closer_than_45_degrees_leave_the_corner_fact_unasked() -> None:
    """s4 splits a street at 20 degrees, so 20 to 45 is a bend OR a shallow
    corner. A corner variant tightens some standards and relaxes others, so
    neither answer is safe: the registry's assumption is named instead."""
    for bearings in ("[0.0, 21.0]", "[0.0, 44.9]", "[170.0, 15.0]"):
        got = observed_facts(row(front_bearings_json=bearings))
        assert "corner_lot" not in got, bearings
        assert got["abuts_alley"] is False  # the other facts still answer


def test_a_gresham_lot_on_a_bend_leans_on_the_corner_assumption_it_used_to_answer(
    corpus, policies
) -> None:
    """Gresham LDR-7 states a corner lot width; a lot whose street bends is
    no longer certified on either reading of it."""
    bend = lot_from_row(row(jurisdiction="gresham", zone="LDR-7", front_bearings_json="[0.0, 30.0]"))
    (s,) = screen_lot(bend, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    assert "corner_lot" in s.rules.levers
    assert "corner_lot" in s.config.leans_on(s.rules.levers)
    assert "corner_lot" in s.config.assumed and "corner_lot" not in s.config.conditions
    assert "FACT_ASSUMED" in s.signed.reasons

    corner = lot_from_row(row(jurisdiction="gresham", zone="LDR-7", front_bearings_json="[0.0, 90.0]"))
    (s,) = screen_lot(corner, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    assert "corner_lot" in s.config.conditions
    assert "corner_lot" not in s.config.leans_on(s.rules.levers)


#: A 50 x 100 lot with a street across each end: s4 clusters the two ends
#: mod 180 into ONE street direction.
THROUGH = json.dumps(
    [
        [X0, Y0, X0 + 50, Y0, "F"],
        [X0 + 50, Y0, X0 + 50, Y0 + 100, "S"],
        [X0 + 50, Y0 + 100, X0, Y0 + 100, "F"],
        [X0, Y0 + 100, X0, Y0, "S"],
    ]
)


def test_a_through_lot_is_a_corner_where_the_code_counts_streets_and_nowhere_else(layers) -> None:
    """Gresham 3.0100: "Corner Lot. A lot that has frontage on two or more
    streets" -- nothing about the streets meeting, so a through lot is one.
    Portland 33.910 asks for frontages that intersect, which a street front
    and back do not; the 45-degree reading stands there."""
    gresham = row(jurisdiction="gresham", zone="LDR-5", edges_json=THROUGH)
    assert observed_facts(gresham, layers)["corner_lot"] is True
    # The question is the layer's: without the corpus it is not asked.
    assert observed_facts(gresham)["corner_lot"] is False
    for other in ("portland", "troutdale", "wood-village"):
        got = observed_facts(row(jurisdiction=other, edges_json=THROUGH), layers)
        assert got["corner_lot"] is False, other
    # A plain interior lot is no corner in Gresham either.
    assert observed_facts(row(jurisdiction="gresham", zone="LDR-5"), layers)["corner_lot"] is False
    # A through lot in the 20-45 degree band is two streets whichever way it bends.
    bent = row(jurisdiction="gresham", zone="LDR-5", edges_json=THROUGH, front_bearings_json="[0.0, 30.0]")
    assert observed_facts(bent, layers)["corner_lot"] is True


def test_a_gresham_through_lot_is_measured_against_the_corner_row(corpus, policies) -> None:
    """Table 4.0130 E.2: 40 ft of width on a corner lot in LDR-5 where the
    interior row asks 35. Read as an interior lot, the through lot was
    certified against the number the code does not state for it."""
    lot = lot_from_row(row(jurisdiction="gresham", zone="LDR-5", edges_json=THROUGH), corpus.layers)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    assert "corner_lot" in s.config.conditions
    assert "corner_lot" not in s.config.leans_on(s.rules.levers)
    assert s.rules.get("min_lot_width_ft") == 40
    assert s.rules.get("min_frontage_ft") == 40


def test_a_lot_mapped_flx_screens_as_vc_inside_the_vc_flex_area(corpus, policies) -> None:
    """FOLLOWUPS 10(a): the map code feeds the variant VC's use line names."""
    flx = lot_from_row(row(jurisdiction="fairview", zone="FLX"), corpus.layers)
    assert flx.zone == "VC"
    assert flx.observed["inside_mapped_use_area"] is True
    (s,) = screen_lot(flx, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    assert s.rules.verdict.value != "zone_not_encoded"
    assert "inside_mapped_use_area" in s.config.conditions
    assert "inside_mapped_use_area" not in s.config.unknown

    # A VC lot is not thereby outside the area: the fact stays unasked.
    vc = lot_from_row(row(jurisdiction="fairview", zone="VC"), corpus.layers)
    assert vc.zone == "VC" and "inside_mapped_use_area" not in vc.observed
    # And without the corpus nothing is read off the map code at all.
    assert "inside_mapped_use_area" not in lot_from_row(row(jurisdiction="fairview", zone="FLX")).observed


def test_a_lot_s4_could_not_trace_answers_no_alley_and_no_corner() -> None:
    """Tier D has no edges. The registry's assumption is named on those
    facts rather than a False that reads as a measurement; the bulb flag
    is still answered because False is the conservative row."""
    got = observed_facts(row(tier="D", edges_json="[]", front_bearings_json="[]"))
    assert "abuts_alley" not in got and "corner_lot" not in got
    assert got["fronts_cul_de_sac"] is False


def test_sewer_is_confirmed_by_a_main_and_denied_only_outside_every_clackamas_district() -> None:
    # A main in reach confirms it anywhere.
    assert observed_facts(row(sewer_main_dist_ft=SEWER_MAIN_REACH_FT))["public_sewer"] is True
    # Beyond reach in Multnomah: unconfirmed, so unasked -- the registry
    # refuses to guess sewer and the lot goes to UNKNOWN where it matters.
    far = observed_facts(row(sewer_main_dist_ft=SEWER_MAIN_REACH_FT + 1))
    assert "public_sewer" not in far and "in_sewer_district" not in far
    none = observed_facts(row(sewer_main_dist_ft=None))
    assert "public_sewer" not in none
    # Beyond reach in Clackamas, inside a district: connectable, unconfirmed.
    inside = observed_facts(
        row(jurisdiction="milwaukie", sewer_main_dist_ft=400.0, in_sewer_district=True)
    )
    assert inside["in_sewer_district"] is True and "public_sewer" not in inside
    # Beyond reach in Clackamas, outside every district: quadfit's
    # no_public_sewer, the one case the bridge answers False.
    outside = observed_facts(
        row(jurisdiction="milwaukie", sewer_main_dist_ft=400.0, in_sewer_district=False)
    )
    assert outside == {**outside, "in_sewer_district": False, "public_sewer": False}
    # The district flag never speaks for a Multnomah city.
    mult = observed_facts(row(sewer_main_dist_ft=400.0, in_sewer_district=False))
    assert "in_sewer_district" not in mult and "public_sewer" not in mult


def test_unincorporated_multnomah_answers_the_district_and_nothing_about_sewer() -> None:
    """ORS 197A.015(12)(c): inside a sanitary district is part of what urban
    unincorporated land is. A main in reach does not answer it, and outside
    every district does not mean no sewer -- a city may serve the lot."""
    for dist in (SEWER_MAIN_REACH_FT, 400.0):
        outside = observed_facts(row(jurisdiction="multnomah_unincorporated", sewer_main_dist_ft=dist, in_sewer_district=False))
        assert outside["in_sewer_district"] is False
        assert outside.get("public_sewer") is (True if dist <= SEWER_MAIN_REACH_FT else None)
    inside = observed_facts(row(jurisdiction="multnomah_unincorporated", sewer_main_dist_ft=10.0, in_sewer_district=True))
    assert inside["in_sewer_district"] is True and inside["public_sewer"] is True
    unread = observed_facts(row(jurisdiction="multnomah_unincorporated", sewer_main_dist_ft=400.0, in_sewer_district=None))
    assert "in_sewer_district" not in unread


def test_a_stage_file_from_before_a_column_leaves_the_fact_unasked() -> None:
    old = row()
    for column in ("split_zone", "ovl_fema_sfha", "ovl_fema_floodway"):
        old.pop(column)
    got = observed_facts(old)
    assert "split_zone" not in got and "in_floodplain" not in got


def across(*edges: dict | None) -> str:
    """s4's ``neighbour_zones_json`` for the four-edge fixture lot: the street
    edge first (never asked), then east side, rear, west side."""
    return json.dumps([None, *edges])


def zoned(*pairs: tuple[str, str], split: int = 0, none: int = 0) -> dict:
    return {"z": [list(p) for p in pairs], "split": split, "none": none}


@pytest.fixture(scope="module")
def layers():
    return load_trusted(strict=False).rules.layers


def test_without_the_corpus_the_neighbour_facts_are_left_unasked() -> None:
    got = observed_facts(row(zone="CM2", neighbour_zones_json=across(zoned(("portland", "R5")))))
    assert not any(name.startswith("abuts_") and name.endswith("_zone") for name in got)


def test_a_commercial_lot_with_a_house_behind_it_keeps_its_ten_feet(layers) -> None:
    # Portland 33.130.215.B.2: one R5 point on the rear line settles it.
    got = observed_facts(
        row(
            zone="CM2",
            neighbour_zones_json=across(
                zoned(("portland", "CM2")), zoned(("portland", "R5a")), zoned(("portland", "CM2"))
            ),
        ),
        layers,
    )
    assert got["abuts_nonresidential_zone"] is False
    # The map's lowercase suffix was stripped before the lookup: R5a is R5.
    assert "abuts_residential_zone" not in got, "Portland declares only the one condition"


def test_a_commercial_lot_walled_in_by_commercial_lots_owes_no_setback(layers) -> None:
    got = observed_facts(
        row(
            zone="CM2",
            neighbour_zones_json=across(
                zoned(("portland", "CM2")), zoned(("portland", "EG1"), ("portland", "OS")), zoned(("portland", "CX"))
            ),
        ),
        layers,
    )
    assert got["abuts_nonresidential_zone"] is True


def test_a_park_or_a_split_neighbour_or_another_city_leaves_the_relaxation_unstated(layers) -> None:
    park = across(zoned(("portland", "CM2")), zoned(none=5), zoned(("portland", "CM2")))
    split = across(zoned(("portland", "CM2")), zoned(("portland", "CM2"), split=1), zoned(("portland", "CM2")))
    gresham = across(zoned(("portland", "CM2")), zoned(("gresham", "CC")), zoned(("portland", "CM2")))
    for record in (park, split, gresham):
        got = observed_facts(row(zone="CM2", neighbour_zones_json=record), layers)
        assert "abuts_nonresidential_zone" not in got, record


def test_a_whole_block_reads_as_walled_in_by_nothing(layers) -> None:
    """Every edge a street edge: Portland's "every lot line that is not a
    street lot line" holds of a lot with none (434 downtown blocks sat
    UNKNOWN on it). An untraced lot and an irregular one stay unanswered."""
    block = json.dumps([None, None, None, None])
    got = observed_facts(row(zone="CX", tier="B", neighbour_zones_json=block), layers)
    assert got["abuts_nonresidential_zone"] is True
    for tier, record in (("B", "[]"), ("C", block)):
        got = observed_facts(row(zone="CX", tier=tier, neighbour_zones_json=record), layers)
        assert "abuts_nonresidential_zone" not in got, (tier, record)


def test_a_neighbours_alias_is_spelled_as_the_block_it_screens_under(layers) -> None:
    # Fairview's map prints FLX where the rules hold VC; VC is on the
    # true_for side, so the alias reads as commercial.
    got = observed_facts(
        row(
            jurisdiction="fairview",
            zone="TCC",
            neighbour_zones_json=across(
                zoned(("fairview", "FLX")), zoned(("fairview", "CC")), zoned(("fairview", "VC"))
            ),
        ),
        layers,
    )
    assert got["abuts_nonresidential_zone"] is True
    # And VA, the Village apartment zone, is residential in every sense.
    got = observed_facts(
        row(
            jurisdiction="fairview",
            zone="TCC",
            neighbour_zones_json=across(zoned(("fairview", "FLX")), zoned(("fairview", "VA")), zoned(("fairview", "VC"))),
        ),
        layers,
    )
    assert got["abuts_nonresidential_zone"] is False


def test_a_layer_that_declares_no_list_answers_nothing_however_the_fabric_reads(layers) -> None:
    # Gresham has the fact registered and no list: silence, as before.
    got = observed_facts(
        row(
            jurisdiction="gresham",
            zone="CC",
            neighbour_zones_json=across(zoned(("gresham", "CC")), zoned(("gresham", "CC")), zoned(("gresham", "CC"))),
        ),
        layers,
    )
    assert not any(name.startswith("abuts_") and name.endswith("_zone") for name in got)


def test_a_stage_file_from_before_the_neighbour_column_leaves_the_facts_unasked(layers) -> None:
    old = row(zone="CM2")
    assert "neighbour_zones_json" not in old
    got = observed_facts(old, layers)
    assert not any(name.startswith("abuts_") and name.endswith("_zone") for name in got)


# --- the lot -----------------------------------------------------------------


def test_the_tier_letters_map_onto_the_screens_four_states() -> None:
    assert TIER == {
        "A": Tier.clean,
        "B": Tier.corner,
        "C": Tier.irregular,
        "D": Tier.landlocked,
    }
    assert lot_from_row(row(tier="D", edges_json="[]", frontage_ft=0.0)).facts.landlocked


def test_the_lot_carries_quadfits_measurements_and_the_corpus_layer() -> None:
    lot = lot_from_row(row())
    assert lot.layer_id == "or/multnomah/portland"
    assert lot.facts.lot_sqft == 5000.0
    assert lot.facts.frontage_ft == 50.0
    assert lot.facts.lot_width_ft == 50.0 and lot.facts.lot_depth_ft == 100.0
    assert lot.front_bearings == (0.0,)
    assert lot.envelope.equals(ENVELOPE)
    assert lot.observed["public_sewer"] is True


def test_the_strip_s5_cut_off_the_rear_rides_along_for_the_court_charge() -> None:
    # s5 writes down what it cut per edge class; the screen charges the court
    # against the strip behind the building -- the rear edge's, or the
    # alley's where the alley IS the rear lot line and took its own cut.
    cuts = json.dumps({"F": 10.0, "R": 10.0, "S": 5.0, "A": 0.0})
    assert lot_from_row(row(env_setbacks_json=cuts)).facts.envelope_rear_ft == 10.0
    alley_behind = [
        [X0, Y0, X0 + 50, Y0, "F"],
        [X0 + 50, Y0, X0 + 50, Y0 + 100, "S"],
        [X0 + 50, Y0 + 100, X0, Y0 + 100, "A"],
        [X0, Y0 + 100, X0, Y0, "S"],
    ]
    lot = lot_from_row(row(edges_json=json.dumps(alley_behind), env_setbacks_json=cuts))
    assert lot.facts.envelope_rear_ft == 0.0
    # s5 filed that cut under s4's letter, so the key is s4's reading of the
    # line -- not the rules' stricter one, which a record with no cover
    # leaves False (FOLLOWUPS 3(e)).
    assert lot.observed["alley_at_rear"] is False and lot.facts.alley_at_rear is True
    # A stage file from before s5 recorded its cuts, or a lot s5 never
    # traced: nothing is claimed, and the screen charges as it always did.
    assert lot_from_row(row()).facts.envelope_rear_ft is None
    assert lot_from_row(row(env_setbacks_json=None)).facts.envelope_rear_ft is None
    assert carved_rear_ft({"env_setbacks_json": "null"}, {}) is None
    assert "env_setbacks_json" in S5O_COLUMNS


def test_a_width_nobody_measured_is_none_not_zero() -> None:
    lot = lot_from_row(row(lot_width_ft=None, lot_depth_ft=float("nan"), frontage_ft=None))
    assert lot.facts.lot_width_ft is None and lot.facts.lot_depth_ft is None
    assert lot.facts.frontage_ft == 0.0


def test_a_jurisdiction_the_port_never_mapped_has_no_layer() -> None:
    lot = lot_from_row(row(jurisdiction="sandy"))
    assert lot.layer_id is None


# --- the stage files ---------------------------------------------------------


def _stage_files(tmp_path: Path, rows: list[dict[str, object]]) -> tuple[Path, Path]:
    frame = pd.DataFrame(rows)
    s4 = tmp_path / "s4_lots.parquet"
    s5o = tmp_path / "s5o_lots.parquet"
    frame[[c for c in S4_COLUMNS if c in frame]].to_parquet(s4, index=False)
    # s5o carries the envelope and the overlay columns, not the bulb flag --
    # s4 was re-run alone after s5o was written, as it is on LXC 137.
    frame[[c for c in S5O_COLUMNS if c in frame]].to_parquet(s5o, index=False)
    return s4, s5o


def test_s4s_columns_carry_the_neighbour_record() -> None:
    assert "neighbour_zones_json" in S4_COLUMNS
    assert "abuts_nonresidential_zone" in OBSERVABLE and "abuts_residential_zone" in OBSERVABLE


def test_the_rows_join_s4s_facts_to_s5os_envelope_on_tlid(tmp_path: Path) -> None:
    s4, s5o = _stage_files(
        tmp_path,
        [
            row(),
            row(TLID="1S2E20AA  -15200", fronts_cul_de_sac=True, sewer_main_dist_ft=None),
        ],
    )
    got = {r["TLID"]: r for r in iter_rows(s4, s5o)}
    assert set(got) == {"1S2E20AA  -15100", "1S2E20AA  -15200"}
    second = got["1S2E20AA  -15200"]
    assert second["fronts_cul_de_sac"] is True  # from s4
    assert second["wkb"] is not None  # from s5o
    # Every null leaves as None, whatever dtype pandas gave the column.
    assert second["sewer_main_dist_ft"] is None
    assert second["in_sewer_district"] is None
    assert list(iter_rows(s4, s5o, limit=1))[0]["TLID"] == "1S2E20AA  -15100"
    assert [r["TLID"] for r in iter_rows(s4, s5o, jurisdictions=["gresham"])] == []


# --- the screen --------------------------------------------------------------


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


def test_the_verdict_is_the_screens_own_and_the_signed_colour_stands_beside_it(
    corpus, policies
) -> None:
    lot = lot_from_row(row())
    got = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    assert len(got) == 1
    s = got[0]
    # Nothing in the corpus is signed: the verdict is UNKNOWN for that reason
    # and no other, on every lot whose zone the corpus holds.
    assert s.rules.verdict.value == "unverified"
    assert s.screening.triage is Triage.unknown
    assert s.screening.reasons == ("RULE_UNVERIFIED",)
    # The signed colour is a real answer, reached by the same checks.
    assert s.signed.triage in (Triage.green, Triage.yellow, Triage.red)
    assert "RULE_UNVERIFIED" not in s.signed.reasons
    # Portland states no parking minimum (`exempt: true`), and the code
    # saying so is an answer: the signed colour may not call it a hole.
    assert "STANDARD_NOT_ENCODED" not in s.signed.reasons
    assert s.signed.checks == s.screening.checks
    assert s.signed.head == s.screening.head
    # The fit was searched at the width the zone's parking asks, never the
    # bare footprint -- the screen would otherwise refuse to score it.
    assert s.fit.across_ft is not None and s.fit.across_ft >= 56
    assert "fit_across_ft" not in s.screening.unchecked
    # Portland does not make the pod face the street, so the sweep ran with
    # the frontage bearing folded in.
    assert s.angles == len(sweep(30.0)) and s.step_deg == 30.0
    # The observed facts reached the configuration.
    assert "public_sewer" in s.config.conditions
    assert "public_sewer" not in s.config.unknown


def test_a_zone_the_corpus_does_not_hold_stays_unknown_signed_or_not(corpus, policies) -> None:
    lot = lot_from_row(row(zone="NOT-A-ZONE"))
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    assert s.rules.verdict.value == "zone_not_encoded"
    assert s.screening.triage is Triage.unknown
    assert s.signed is s.screening


def test_a_jurisdiction_without_a_layer_is_reported_not_raised(corpus, policies) -> None:
    lot = lot_from_row(row(jurisdiction="sandy"))
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    assert s.rules.verdict.value == "jurisdiction_not_encoded"
    assert s.screening.triage is Triage.unknown


def test_a_lot_with_no_envelope_fits_nothing_and_still_answers(corpus, policies) -> None:
    lot = lot_from_row(row(tier="D", edges_json="[]", front_bearings_json="[]", wkb=None))
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    assert s.fit.fits is False and s.fit.best_depth_ft == 0.0
    assert s.screening.triage is Triage.unknown
    # No street direction: swept anyway, and the lot is named landlocked.
    assert s.angles == len(sweep(30.0))
    assert "NO_FRONTAGE" in s.signed.reasons


def test_the_flat_row_carries_the_verdict_the_signed_colour_and_what_leaned(
    corpus, policies
) -> None:
    lot = lot_from_row(row())
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    r = row_for(s)
    assert r["TLID"] == lot.tlid and r["design"] == "pod@1"
    assert r["triage"] == "unknown" and r["reasons"] == "RULE_UNVERIFIED"
    assert r["if_signed"] == s.signed.triage.value
    assert r["if_signed_reasons"] == ",".join(s.signed.reasons)
    # The flag plan's colour is the signed one (Steph 2026-10-02, Q4): the
    # unsigned screening's RULE-UNSIGNED flag is not on the row, and every
    # flag names this lot, not the screen's placeholder.
    assert r["colour"] == s.signed.colour.value
    assert "RULE-UNSIGNED" in {f.code for f in s.screening.flags}
    written = json.loads(r["flags"]) if r["flags"] else []
    assert "RULE-UNSIGNED" not in {f["code"] for f in written}
    assert all("@" not in f["key"].split("|") for f in written)
    assert r["binds"] == (json.dumps([b.as_json() for b in s.signed.binds], separators=(",", ":")) if s.signed.binds else "")
    assert r["fit_across_ft"] == s.fit.across_ft
    # The stall count beside the colour, in the county map's own three
    # columns: what the row was charged at, how many the lot seats, which
    # band that is. This pod is one band (1.5, six stalls) and the 40 ft
    # envelope holds no row of six, so it seats none and has no band.
    assert r["stalls_charged"] == s.screening.stalls_charged == 6
    assert r["stalls_seated"] == s.screening.stalls_seated == 0
    assert r["parking_band"] is None
    assert json.loads(r["observed"]) == dict(lot.observed)
    # Only the guesses a standard here turns on are reported as leaning.
    leaning = set(s.config.leans_on(s.rules.levers))
    assert set(filter(None, r["assumed_leaning"].split(","))) == leaning & set(s.config.assumed)
    assert set(filter(None, r["unknown_leaning"].split(","))) == leaning & set(s.config.unknown)


# --- the batch and the comparison --------------------------------------------


def test_per_lot_keeps_the_best_design() -> None:
    frame = pd.DataFrame(
        [
            {"TLID": "a", "design": "d1", "if_signed": "red"},
            {"TLID": "a", "design": "d2", "if_signed": "yellow"},
            {"TLID": "b", "design": "d1", "if_signed": "unknown"},
            {"TLID": "b", "design": "d2", "if_signed": "green"},
            {"TLID": "c", "design": "d1", "if_signed": "unknown"},
            {"TLID": "c", "design": "d2", "if_signed": "red"},
        ]
    )
    got = per_lot(frame).set_index("TLID")["if_signed"].to_dict()
    assert got == {"a": "yellow", "b": "green", "c": "unknown"}


def test_the_batch_writes_the_rows_the_meta_and_the_comparison(tmp_path: Path) -> None:
    s4, s5o = _stage_files(
        tmp_path,
        [row(), row(TLID="1S2E20AA  -15200", zone="NOT-A-ZONE")],
    )
    results = tmp_path / "lots_results.csv"
    pd.DataFrame(
        {
            "TLID": ["1S2E20AA  -15100", "1S2E20AA  -15200"],
            "triage": ["green", "red"],
            "binding_constraint": ["", "pod_no_fit"],
            "policy_exclusion": ["", ""],
            "parking_tier": ["minimum", ""],
            "stalls_provided": ["4", ""],
            "layout_method": ["one_row_rear", ""],
        }
    ).to_csv(results, index=False)
    out = tmp_path / "bridge"
    log: list[str] = []
    # The fire route is measured to the street centrelines beside s4, and a
    # run without them is refused: from the lot line the route comes out
    # shorter than the hose's (FOLLOWUPS 28).
    with pytest.raises(FileNotFoundError, match="street centrelines"):
        run(out, s4=s4, s5o=s5o, results=results, step_deg=30.0, log=log.append)
    street = shapely.LineString([(X0 - 100, Y0 - 20), (X0 + 150, Y0 - 20)])
    pd.DataFrame(
        {"name": ["SE TEST ST"], "type": ["1500"], "ftype": ["ST"], "alley": [False],
         "wkb": [shapely.to_wkb(street)]}
    ).to_parquet(s4.parent / "s1_streets.parquet")
    written = run(out, s4=s4, s5o=s5o, results=results, step_deg=30.0, log=log.append)
    frame = pd.read_parquet(written)
    # Two lots x every catalog design, one row each.
    designs = frame["design"].nunique()
    assert designs >= 1 and len(frame) == 2 * designs
    assert set(frame["triage"]) == {"unknown"}
    assert set(frame.loc[frame["zone"] == "NOT-A-ZONE", "if_signed"]) == {"unknown"}
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta["lots"] == 2 and meta["rows"] == len(frame) and meta["step_deg"] == 30.0
    assert meta["roads"] == str(s4.parent / "s1_streets.parquet")
    assert "fire_route_ft" in frame.columns
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert "| unknown |" in summary and "RULE_UNVERIFIED" in summary
    assert "against quadfit" in summary
    assert "Stalls seated, where both are green" in summary
    assert {"stalls_charged", "stalls_seated", "parking_band"} <= set(frame.columns)
    assert log and log[-1].startswith("bridge: wrote")
    # The comparison can be re-run from the parquet alone.
    assert compare(frame, results).startswith("# FLATS screen from the county map")
    # And against a results file from before quadfit reported its stalls:
    # the colours still compare, the band table just has nothing in it.
    older = tmp_path / "older_results.csv"
    pd.read_csv(results).drop(columns=["parking_tier", "stalls_provided", "layout_method"]).to_csv(
        older, index=False
    )
    assert "Stalls seated, where both are green" in compare(frame, older)


# --- the envelope FLATS cuts (FOLLOWUPS 12) ----------------------------------

LOT = shapely.box(X0, Y0, X0 + 50, Y0 + 100)


def cut_row(**over: object) -> dict[str, object]:
    """A row with the taxlot on it, so the bridge cuts its own envelope."""
    return row(lot_wkb=shapely.to_wkb(LOT), **over)


class Rules:
    """A resolution stub: the numbers, and the yards the code exempts."""

    def __init__(self, *exempted: str, **values: object) -> None:
        self.values = values
        self.exempted = exempted

    def get(self, name: str) -> object:
        return self.values.get(name)


def walled(*rear: tuple[str, str]) -> str:
    """Commercial neighbours both sides, ``rear`` behind."""
    return across(zoned(("portland", "CM2")), zoned(*rear), zoned(("portland", "CM2")))


def test_the_envelope_is_cut_with_the_yards_the_corpus_resolved(corpus, policies) -> None:
    # Portland CM2 owes 10 ft side and rear against a house and nothing
    # walled in by commercial lots. quadfit cuts one figure for both; the
    # bridge cuts the one this lot resolves.
    layers = corpus.layers
    house = lot_from_row(cut_row(zone="CM2", neighbour_zones_json=walled(("portland", "R5"))), layers)
    shops = lot_from_row(cut_row(zone="CM2", neighbour_zones_json=walled(("portland", "CX"))), layers)
    (h,) = screen_lot(house, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    (s,) = screen_lot(shops, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    assert h.envelope.source == s.envelope.source == "flats"
    # The side edge takes 10 on both lines (the R5 is on the rear line only,
    # and the ANY-line fact tightens every yard it governs). The street line
    # keeps CM2's across-the-street 5 (33.130.215.B.1.b): nothing here read
    # what faces it across the street.
    assert h.envelope.sqft == pytest.approx(30 * 85)
    assert s.envelope.sqft == pytest.approx(50 * 95)
    # The resolved rear IS the strip cut, so the court is charged against
    # the rules' own number.
    assert h.envelope.rear_cut_ft is None
    assert row_for(s)["envelope_source"] == "flats"
    assert row_for(s)["envelope_sqft"] == pytest.approx(4750)
    # assign trims a bridge frame to ROW_COLUMNS; a column row_for writes and
    # the list lacks never reaches the database (run 18 lost the envelope).
    assert list(row_for(s)) == list(ROW_COLUMNS)


def test_without_the_taxlot_or_a_street_the_envelope_stays_quadfits(corpus, policies) -> None:
    for lot in (
        lot_from_row(row()),  # a stage file from before the lot polygon rode along
        lot_from_row(cut_row(tier="D", edges_json="[]", front_bearings_json="[]")),
    ):
        (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
        assert s.envelope.source == "quadfit"
        assert s.envelope.geom is lot.envelope


def test_a_yard_the_rules_leave_without_a_number_keeps_quadfits_envelope(corpus) -> None:
    lot = lot_from_row(cut_row(zone="NOT-A-ZONE"))
    got = corpus.resolve("or/multnomah/portland", "NOT-A-ZONE", frozenset())
    assert envelope_for(lot, got).source == "quadfit"


def test_the_carve_overlays_come_off_the_envelope_flats_cuts(corpus, policies) -> None:
    greenway = shapely.box(X0, Y0 + 70, X0 + 50, Y0 + 100)
    lot = lot_from_row(
        cut_row(zone="CM2", neighbour_zones_json=walled(("portland", "CX")), carve_wkb=shapely.to_wkb(greenway)),
        corpus.layers,
    )
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    assert s.envelope.source == "flats"
    # Less the across-the-street 5 on the street line.
    assert s.envelope.sqft == pytest.approx(50 * 65)


def test_an_irregular_lot_is_inset_at_its_largest_yard_and_charged_so() -> None:
    lot = lot_from_row(cut_row(tier="C"))
    got = Rules(setback_front_ft=10, setback_side_ft=5, setback_rear_ft=15)
    env = envelope_for(lot, got)  # type: ignore[arg-type]
    assert env.source == "flats"
    assert env.sqft == pytest.approx(20 * 70)
    assert env.rear_cut_ft == 15


def test_an_alley_edge_is_named_rear_or_side_by_its_bearing() -> None:
    behind = [*EDGES[:2], [X0 + 50, Y0 + 100, X0, Y0 + 100, "A"], EDGES[3]]
    beside = [EDGES[0], [X0 + 50, Y0, X0 + 50, Y0 + 100, "A"], *EDGES[2:]]
    rear = lot_edges(cut_row(edges_json=json.dumps(behind)), LOT)
    side = lot_edges(cut_row(edges_json=json.dumps(beside)), LOT)
    assert [(e.cls, e.alley) for e in rear.edges][2] == (EdgeClass.rear, True)
    assert [(e.cls, e.alley) for e in side.edges][1] == (EdgeClass.side, True)
    assert not any(e.alley for e in lot_edges(cut_row(), LOT).edges)
    assert lot_edges(cut_row(edges_json="[]")) is None


def test_a_combined_side_yard_is_split_evenly_between_the_two_sides() -> None:
    got = setbacks_for(Rules(setback_front_ft=10, setback_side_ft=5, setback_rear_ft=10, setback_side_total_ft=15))  # type: ignore[arg-type]
    assert got is not None and got.side_ft == 7.5
    assert setbacks_for(Rules(setback_front_ft=10, setback_rear_ft=10)) is None  # type: ignore[arg-type]


def test_the_rows_carry_the_taxlot_under_its_own_name(tmp_path: Path) -> None:
    frame = pd.DataFrame([row()])
    s4 = tmp_path / "s4_lots.parquet"
    s5o = tmp_path / "s5o_lots.parquet"
    s4_frame = frame[[c for c in S4_COLUMNS if c in frame]].assign(wkb=[shapely.to_wkb(LOT)])
    s4_frame.to_parquet(s4, index=False)
    frame[[c for c in S5O_COLUMNS if c in frame]].to_parquet(s5o, index=False)
    (got,) = iter_rows(s4, s5o)
    assert shapely.from_wkb(got["lot_wkb"]).equals(LOT)
    assert shapely.from_wkb(got["wkb"]).equals(ENVELOPE)


BEHIND = [*EDGES[:2], [X0 + 50, Y0 + 100, X0, Y0 + 100, "A"], EDGES[3]]
BESIDE = [EDGES[0], [X0 + 50, Y0, X0 + 50, Y0 + 100, "A"], *EDGES[2:]]
#: s4's ``alley_cover_json`` for BESIDE: twenty rays along the 100 ft side
#: line, every one finding the alley -- or only the front ten, the alley a
#: stub that dead-ends halfway along the line (FOLLOWUPS 3(c)).
BESIDE_WHOLE = json.dumps([None, "1" * 20, None, None])
BESIDE_STUB = json.dumps([None, "1" * 10 + "0" * 10, None, None])
#: The same for BEHIND's 50 ft rear line (ten rays, run east to west): the
#: alley the whole way, or a stub behind the eastern 30 ft that dead-ends
#: there (FOLLOWUPS 3(d)/(e)).
BEHIND_WHOLE = json.dumps([None, None, "1" * 10, None])
BEHIND_STUB = json.dumps([None, None, "1" * 6 + "0" * 4, None])


def test_a_rear_yard_the_alley_waives_is_cut_at_zero(corpus, policies) -> None:
    # Portland R5: no rear setback where the rear line is an alley. The
    # waiver resolves as an exemption, not a number; it is a yard of zero,
    # not a reason to fall back to quadfit's figure.
    lot = lot_from_row(cut_row(zone="R5", edges_json=json.dumps(BEHIND), alley_cover_json=BEHIND_WHOLE), corpus.layers)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    assert s.envelope.source == "flats"
    assert s.envelope.setbacks.rear_ft == 0
    assert s.envelope.sqft == pytest.approx((50 - 2 * 5) * (100 - 10))


def test_a_rear_line_the_alley_runs_part_of_keeps_its_rear_setback(corpus, policies) -> None:
    # FOLLOWUPS 3(e). The waiver is one number for the rear line; where the
    # alley stops 20 ft short, that 20 ft faces the neighbour's yard, so the
    # rules resolve the line's ordinary rear setback -- and so does a record
    # with no cover, which measured nothing. The lot still abuts the alley.
    for cover in (BEHIND_STUB, None):
        lot = lot_from_row(
            cut_row(zone="R5", edges_json=json.dumps(BEHIND), alley_cover_json=cover), corpus.layers
        )
        assert lot.observed["abuts_alley"] is True and lot.observed["alley_at_rear"] is False
        (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
        assert s.envelope.source == "flats"
        assert s.envelope.setbacks.rear_ft == 5
        assert s.envelope.sqft == pytest.approx((50 - 2 * 5) * (100 - 10 - 5))


def test_an_exempt_rear_with_a_rear_line_off_the_alley_keeps_quadfits_envelope() -> None:
    got = Rules("setback_rear_ft", setback_front_ft=10, setback_side_ft=5)
    both = [*EDGES[:3], [X0, Y0 + 100, X0 + 20, Y0 + 100, "A"]]
    assert envelope_for(lot_from_row(cut_row(edges_json=json.dumps(BEHIND))), got).source == "flats"  # type: ignore[arg-type]
    assert envelope_for(lot_from_row(cut_row(edges_json=json.dumps(both))), got).source == "quadfit"  # type: ignore[arg-type]


def test_a_side_line_on_an_alley_takes_the_rear_unless_the_code_says_otherwise() -> None:
    # Gresham, Oregon City and Wilsonville call the alley line a rear lot line.
    lot = lot_from_row(cut_row(edges_json=json.dumps(BESIDE)))
    got = Rules(setback_front_ft=10, setback_side_ft=0, setback_rear_ft=15)
    env = envelope_for(lot, got)  # type: ignore[arg-type]
    assert env.setbacks.alley_side_ft == 15
    assert env.sqft == pytest.approx((50 - 15) * (100 - 10 - 15))
    waived = Rules(setback_front_ft=10, setback_side_ft=0, setback_rear_ft=15, setback_alley_side_ft=0)
    assert envelope_for(lot, waived).sqft == pytest.approx(50 * 75)  # type: ignore[arg-type]


def test_a_side_alley_waiver_reaches_only_the_stretch_the_alley_runs() -> None:
    # FOLLOWUPS 3(e). Portland waives the side setback on "a lot line
    # abutting an alley"; where the alley runs the front half of the east
    # line and stops, the rear half faces the neighbour and keeps its 5 ft.
    # Rays 2.5 ft in and 5 ft apart: the last one on the alley is 47.5 ft
    # up the line, and the 5 ft strip beyond it runs a square cap 5 ft back.
    waived = Rules(setback_front_ft=10, setback_side_ft=5, setback_rear_ft=15, setback_alley_side_ft=0)

    def area(cover: str | None) -> float:
        lot = lot_from_row(cut_row(edges_json=json.dumps(BESIDE), alley_cover_json=cover))
        return envelope_for(lot, waived).sqft  # type: ignore[arg-type]

    assert area(BESIDE_WHOLE) == pytest.approx(45 * 75)
    assert area(BESIDE_STUB) == pytest.approx(45 * (42.5 - 10) + 40 * (85 - 42.5))
    # Nothing measured the stretch: none of it is vouched for.
    assert area(None) == pytest.approx(40 * 75)
    # A city with no alley-side number (the alley line is a rear lot line)
    # cuts the whole line at the deeper yard, measured or not.
    rear_line = Rules(setback_front_ft=10, setback_side_ft=5, setback_rear_ft=15)
    lot = lot_from_row(cut_row(edges_json=json.dumps(BESIDE), alley_cover_json=BESIDE_STUB))
    assert envelope_for(lot, rear_line).sqft == pytest.approx((50 - 5 - 15) * 75)  # type: ignore[arg-type]


def test_an_alley_behind_the_lot_reaches_the_court_with_its_measured_width(corpus, policies) -> None:
    # FOLLOWUPS 4(b). s4's alley width rides into the lot's facts beside the
    # rear alley, and Portland's court behind the pod is charged as a stall
    # and the back-out room the alley's width leaves short -- not a stall and
    # a two-way aisle -- where the lot has the alley at the rear.
    fed = lot_from_row(
        cut_row(zone="R5", edges_json=json.dumps(BEHIND), alley_width_ft=14.0, alley_cover_json=BEHIND_WHOLE),
        corpus.layers,
    )
    assert fed.facts.alley_at_rear is True and fed.facts.alley_width_ft == 14.0
    assert fed.facts.alley_rear_whole is True
    beside = lot_from_row(
        cut_row(zone="R5", edges_json=json.dumps(BESIDE), alley_width_ft=14.0, alley_cover_json=BESIDE_WHOLE),
        corpus.layers,
    )
    assert beside.facts.alley_at_rear is False and beside.facts.alley_at_side is True
    assert lot_from_row(cut_row(zone="R5")).facts.alley_width_ft is None

    def asked(lot) -> float:
        (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
        return next(c for c in s.screening.checks if c.check == "fit_ft").threshold

    wide = lot_from_row(
        cut_row(zone="R5", edges_json=json.dumps(BEHIND), alley_width_ft=20.0, alley_cover_json=BEHIND_WHOLE),
        corpus.layers,
    )
    # Six feet of back-out paving on a 14 ft alley, none on a 20 ft one.
    assert asked(fed) - asked(wide) == pytest.approx(6.0)

    # FOLLOWUPS 3(d), Steph's ruling 2026-09-28. An alley along only part
    # of the rear line is the court's aisle only where the stretch it runs,
    # with the envelope behind it, is as long as the row of stalls: four at
    # 9 ft, 36 ft. BEHIND_STUB covers the eastern 27.5 ft, 22.5 of it past
    # the 5 ft side yard -- too short, and a record with no cover is no
    # stretch at all: the court keeps its own aisle, and the lot asks what
    # the same lot with no alley asks.
    plain = lot_from_row(cut_row(zone="R5"), corpus.layers)
    for cover in (BEHIND_STUB, None):
        stub = lot_from_row(
            cut_row(zone="R5", edges_json=json.dumps(BEHIND), alley_width_ft=14.0, alley_cover_json=cover),
            corpus.layers,
        )
        assert stub.facts.alley_at_rear is True and stub.facts.alley_rear_whole is False
        assert asked(stub) == pytest.approx(asked(plain))
        assert asked(stub) > asked(fed)
    # Nine rays of ten: the alley runs 42.5 ft from the east corner, 37
    # of it with the envelope behind -- long enough for a row of four at
    # 9 ft (the pod at one stall a home, the catalog's floor), which backs
    # out into it. The rear yard is still owed (the alley does not run the
    # whole line, 3(e)), so the court is charged 29 ft less that 5 ft strip
    # where the same lot with no cover on record is charged 47 less 5: 18 ft
    # shallower. One ray fewer leaves 32 ft, and the row keeps its aisle; so
    # does the 1.5-a-home pod's 54 ft row on the longer stretch.
    unmeasured = lot_from_row(
        cut_row(zone="R5", edges_json=json.dumps(BEHIND), alley_width_ft=14.0, alley_cover_json=None),
        corpus.layers,
    )
    def asked4(lot, design=None) -> float:
        (s,) = screen_lot(
            lot, [design or pod4()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0
        )
        return next(c for c in s.screening.checks if c.check == "fit_ft").threshold

    long = lot_from_row(
        cut_row(zone="R5", edges_json=json.dumps(BEHIND), alley_width_ft=14.0,
                alley_cover_json=json.dumps([None, None, "1" * 9 + "0", None])),
        corpus.layers,
    )
    # Portland's court aisle is 20 ft (Table 266-4, adopted by Steph
    # 2026-09-30): the 14 ft alley standing in for it saves 14 ft of depth.
    assert asked4(unmeasured) - asked4(long) == pytest.approx(14.0)
    assert asked4(long, pod()) == pytest.approx(asked4(unmeasured, pod()))
    short = lot_from_row(
        cut_row(zone="R5", edges_json=json.dumps(BEHIND), alley_width_ft=14.0,
                alley_cover_json=json.dumps([None, None, "1" * 8 + "00", None])),
        corpus.layers,
    )
    assert asked4(short) == pytest.approx(asked4(unmeasured))


#: 1S2E05AB -11900, Portland R5, at real coordinates (EPSG:2913; fixture
#: Lot Analysis/quadfit/tests/fixtures/alley_stops_short_1S2E05AB_11900.json).
#: The street is east; the 13 ft alley behind the lot is drawn only as far
#: north as its south-west corner, and ten of the 88.7 ft rear line's
#: eighteen cover rays, from the south, find it.
REAL_LOT = shapely.from_wkt(
    "POLYGON ((7667287.71 682039.1, 7667286.58 681994.75, 7667186.62 681997.77, "
    "7667187.75 682042.11, 7667188.88 682086.49, 7667288.85 682083.46, 7667287.71 682039.1))"
)
REAL_EDGES = [
    [7667288.85, 682083.46, 7667286.58, 681994.75, "F"],
    [7667286.58, 681994.75, 7667186.62, 681997.77, "S"],
    [7667186.62, 681997.77, 7667188.88, 682086.49, "A"],
    [7667188.88, 682086.49, 7667288.85, 682083.46, "S"],
]


def real_row(cover: str | None) -> dict[str, object]:
    return row(
        TLID="1S2E05AB  -11900",
        area_sqft=float(REAL_LOT.area),
        frontage_ft=88.7,
        lot_width_ft=88.7,
        lot_depth_ft=100.0,
        edges_json=json.dumps(REAL_EDGES),
        front_bearings_json="[88.54]",
        alley_width_ft=13.0,
        alley_cover_json=None if cover is None else json.dumps([None, None, cover, None]),
        lot_wkb=shapely.to_wkb(REAL_LOT),
        wkb=shapely.to_wkb(REAL_LOT.buffer(-5, join_style="mitre")),
    )


def test_a_real_alley_stub_long_enough_for_the_row_is_its_aisle(corpus, policies) -> None:
    # Steph's ruling 2026-09-28: "we can use the portion the alley abuts for
    # our travel lane only if the lane is actually long enough to
    # accommodate". The measured stub runs 46.8 ft north from the south
    # corner, 41 ft of it past the 5 ft side yard with the envelope behind:
    # long enough for a row of four at 9 ft, which backs out into the
    # alley. The alley does not run the whole line, so the rear yard is not
    # waived (3(e)) -- and a stub of six rays (27 ft, 22 past the yard) is
    # too short, and the court keeps its own two-way aisle, exactly as on
    # the same lot with no cover on record.
    def screened(cover: str | None, design=None):
        lot = lot_from_row(real_row(cover), corpus.layers)
        (s,) = screen_lot(
            lot, [design or pod4()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0
        )
        return lot, s

    def asked(s) -> float:
        return next(c for c in s.screening.checks if c.check == "fit_ft").threshold

    measured, got = screened("1" * 10 + "0" * 8)
    assert measured.facts.alley_at_rear is True and measured.facts.alley_rear_whole is False
    assert measured.observed["alley_at_rear"] is False, "the rear yard is owed"
    assert got.envelope.setbacks is not None and got.envelope.setbacks.rear_ft == 5.0
    _, short = screened("1" * 6 + "0" * 12)
    _, plain = screened(None)
    # A 13 ft alley leaves 7 ft of the 20 ft back-out room to pave, where
    # the court's own aisle is Portland's 20: the stretch long enough is 13 ft
    # shallower.
    assert asked(plain) - asked(got) == pytest.approx(13.0)
    assert asked(short) == pytest.approx(asked(plain))
    # The 1.5-a-home pod's six stalls are a 54 ft row: longer than the stub.
    _, six = screened("1" * 10 + "0" * 8, pod())
    _, six_plain = screened(None, pod())
    assert asked(six) == pytest.approx(asked(six_plain))


def test_an_alley_beside_the_lot_drops_the_street_lane(corpus, policies) -> None:
    # Steph, 2026-09-25: "Alleys along side yards is important." Portland R5,
    # the 50 x 100 lot with its alley along a side line: the code sends the
    # driveway to the alley (33.266.120.C.3), and the court behind the pod
    # meets that alley at its end, so the envelope is searched at the pod's
    # own side in whichever orientation won -- not that side plus a 12 ft
    # lane, as it is with no alley.
    def screened(lot):
        (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
        return s

    street = screened(lot_from_row(cut_row(zone="R5"), corpus.layers))
    beside = screened(
        lot_from_row(
            cut_row(zone="R5", edges_json=json.dumps(BESIDE), alley_width_ft=14.0, alley_cover_json=BESIDE_WHOLE),
            corpus.layers,
        )
    )
    def side(s) -> float:
        return 56.0 if s.fit.orientation is Orientation.width_facing else 36.0

    assert street.fit.across_ft - side(street) == pytest.approx(12.0)
    assert beside.fit.across_ft == pytest.approx(side(beside))
    assert "fit_across_ft" not in beside.screening.unchecked


def test_a_side_alley_that_stops_halfway_along_the_line_keeps_the_street_lane(corpus, policies) -> None:
    # FOLLOWUPS 3(c). s4 names the line an alley line on three rays of five,
    # so a stub along the front half of it classes the whole line A. The
    # court stands behind the pod, somewhere along that line, and the fit
    # does not say where: only a line the alley runs end to end feeds it.
    # A record with no ``alley_cover_json`` (s4 before the column) measured
    # nothing, and is read the same way.
    def screened(lot):
        (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
        return s

    def side(s) -> float:
        return 56.0 if s.fit.orientation is Orientation.width_facing else 36.0

    for cover in (BESIDE_STUB, None):
        lot = lot_from_row(
            cut_row(zone="R5", edges_json=json.dumps(BESIDE), alley_width_ft=14.0, alley_cover_json=cover),
            corpus.layers,
        )
        # The line still abuts an alley -- the registry's fact, which the
        # setbacks read, is s4's -- but the court is not handed the alley.
        assert lot.observed["alley_at_side"] is True
        assert lot.facts.alley_at_side is False and lot.facts.alley is None
        s = screened(lot)
        assert s.fit.column is False
        assert s.fit.across_ft - side(s) == pytest.approx(12.0), "the lane down the flank is back"


# --- which street is the front of a corner lot (FOLLOWUPS 4(e)) ----------------

#: The 50 x 100 lot with a second street along its west line: s4 names both
#: street lines F and both interior lines R.
CORNER = [
    [X0, Y0, X0 + 50, Y0, "F"],
    [X0 + 50, Y0, X0 + 50, Y0 + 100, "R"],
    [X0 + 50, Y0 + 100, X0, Y0 + 100, "R"],
    [X0, Y0 + 100, X0, Y0, "F"],
]


def corner_row(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "tier": "B",
        "edges_json": json.dumps(CORNER),
        "front_bearings_json": "[90.0, 0.0]",
        "frontage_ft": 150.0,
    }
    return cut_row(**{**base, **over})


def test_a_portland_corner_lot_fronts_its_shorter_street_and_parks_off_the_other(
    corpus, policies
) -> None:
    # Steph, 2026-09-26: "we need to abide if Portland has guidance on which
    # is front and which is side." 33.910: the 50 ft south line is the
    # front, though s4 listed the 100 ft west street first; the west street
    # takes the street-side yard and the east line, beside the front, the
    # side yard -- not the front and the rear yards both took before.
    # Portland names no street for the driveway (33.266.120.C.3), so the
    # court is reached off the west street and no lane runs beside the pod.
    lot = lot_from_row(corner_row(zone="R5"), corpus.layers)
    assert lot.facts.corner is True
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    assert s.front_deg == 0.0
    classes = [e.cls for e in s.lot.edges.edges]
    assert classes == [EdgeClass.front, EdgeClass.side, EdgeClass.rear, EdgeClass.street_side]
    yards = s.envelope.setbacks
    street_side = yards.front_ft if yards.street_side_ft is None else yards.street_side_ft
    assert s.envelope.sqft == pytest.approx(
        (50 - street_side - yards.side_ft) * (100 - yards.front_ft - yards.rear_ft)
    )
    side = 56.0 if s.fit.orientation is Orientation.width_facing else 36.0
    assert s.fit.across_ft == pytest.approx(max(side, s.screening.stalls_charged * 9.0))
    got = row_for(s)
    assert got["front_deg"] == 0.0 and got["side_street_lane"] is True
    assert list(got) == list(ROW_COLUMNS)


def test_an_owners_choice_city_keeps_the_better_front(corpus, policies) -> None:
    # Gresham 3.0100 leaves the front to the owner: both streets are tried
    # and the answer kept is one of them.
    lot = lot_from_row(corner_row(jurisdiction="gresham", zone="LDR-7"), corpus.layers)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    assert s.rules.get("front_lot_line_corner") == "owner"
    assert s.front_deg in (0.0, 90.0)


def test_a_street_that_bends_is_not_a_corner(corpus, policies) -> None:
    lot = lot_from_row(corner_row(zone="R5", front_bearings_json="[0.0, 30.0]"), corpus.layers)
    assert lot.facts.corner is False
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    assert s.front_deg is None
    assert row_for(s)["side_street_lane"] is False


# --- the drawing (FOLLOWUPS 5) -------------------------------------------------


def test_the_winner_is_drawn_on_the_lot_with_the_building_at_the_street(corpus, policies) -> None:
    # Walled in by commercial lots, CM2 owes no side or rear yard; the street
    # line keeps the across-the-street 5 (nothing read across the street).
    lot = lot_from_row(cut_row(zone="CM2", neighbour_zones_json=walled(("portland", "CX"))), corpus.layers)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    drawn = s.drawing
    assert drawn is not None
    assert {"fits", "room", "building", "lane", "court", "envelope"} <= set(drawn)
    # "Fits" is the building AND the court, as the fit check charges them --
    # not the bare footprint (which clears this lot by 44 ft).
    check = next(c for c in s.screening.checks if c.check == "fit_ft")
    assert drawn["fits"] == (check.slack >= 0)
    building = shapely.Polygon(drawn["building"])
    assert LOT.buffer(0.1).contains(building)
    # The pod stands at the street end: its nearest point on the 5 ft yard.
    assert building.bounds[1] == pytest.approx(Y0 + 5, abs=0.6)
    # The flat row carries it as JSON, the same shapes.
    assert json.loads(row_for(s)["drawing"])["building"] == drawn["building"]


def test_a_lot_the_search_found_no_room_on_draws_nothing(corpus, policies) -> None:
    lot = lot_from_row(row(wkb=None), corpus.layers)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    assert s.drawing is None
    assert row_for(s)["drawing"] is None


# --- a street line only a private drive makes ------------------------------

#: The 50 x 100 lot with its rear line read as a street: the only road within
#: 50 ft of it is the school's drive across the fence (Wilsonville
#: 31W13BD01800). ``BEHIND_SANS`` is s4's reading of the same lot without it.
DRIVE_BEHIND = [[*e[:4], "F" if e[4] == "R" else e[4]] for e in EDGES]
DRIVE_BEHIND_KINDS = ["street", None, "drive_off_lot", None]


def _sans(edges=EDGES, **over: object) -> str:
    alt = {
        "tier": "A", "edges": edges, "front_bearings": [0.0], "frontage_ft": 50.0,
        "alley_cover": [None] * len(edges), "alley_width_ft": None,
        "lot_width_ft": 50.0, "lot_depth_ft": 100.0, "fronts_cul_de_sac": False,
        "neighbour_zones": [None, *[{"z": [["portland", "R5"]], "split": 0, "none": 0}] * 3],
        "park_across": None,
    }
    alt.update(over)
    return json.dumps({"doubtful": alt})


def behind(**over: object) -> dict[str, object]:
    base = dict(
        edges_json=json.dumps(DRIVE_BEHIND),
        street_kind_json=json.dumps(DRIVE_BEHIND_KINDS),
        sans_drive_json=_sans(),
        lot_wkb=shapely.to_wkb(shapely.box(X0, Y0, X0 + 50, Y0 + 100)),
    )
    return row(**{**base, **over})


def test_a_street_line_only_a_schools_drive_makes_is_read_both_ways() -> None:
    """s4 fronts any line within 50 ft of a road in the street file, and the
    file carries private roads and unnamed drives (RLIS 1700 / 1800). A
    drive across the school behind the rear fence is a street by no code,
    but the reading is s4's and could be wrong either way: the lot carries
    s4's reading of itself without the line, rear again, to be screened
    beside the first."""
    from flats.geom.edges import EdgeClass

    lot = lot_from_row(behind())
    assert lot.second is not None
    assert not lot.facts.street_unconfirmed
    rear = [e for e in lot.second.edges.edges if e.cls is EdgeClass.rear]
    assert len(rear) == 1 and not lot.second.facts.street_unconfirmed
    assert lot.second.second is None
    # s4 before the column, or a lot with no drive line: one reading.
    assert lot_from_row(row(edges_json=json.dumps(DRIVE_BEHIND))).second is None
    assert lot_from_row(row(street_kind_json=json.dumps(["street", None, None, None]))).second is None


def test_the_worse_of_the_two_readings_is_kept(corpus, policies) -> None:
    lot = lot_from_row(behind())
    kw = dict(rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    (both,) = screen_lot(lot, [pod()], **kw)
    (first,) = screen_lot(dataclasses.replace(lot, second=None), [pod()], **kw)
    (second,) = screen_lot(lot.second, [pod()], **kw)
    rank = {Triage.green: 0, Triage.yellow: 1, Triage.unknown: 2, Triage.red: 3}
    assert rank[both.signed.triage] == max(rank[first.signed.triage], rank[second.signed.triage])
    assert both.signed.triage in (first.signed.triage, second.signed.triage)


def test_no_second_reading_or_no_street_without_the_drive_is_a_question(
    corpus, policies
) -> None:
    """Where s4 wrote no reading without the drive, or the lot has no street
    left without it, nobody can say the lot fronts a street: never green."""
    for over in ({"sans_drive_json": None}, {"sans_drive_json": _sans(tier="D", edges=[])}):
        lot = lot_from_row(behind(**over))
        assert lot.second is None and lot.facts.street_unconfirmed
        (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
        assert "STREET_UNCONFIRMED" in s.signed.reasons
        assert s.signed.triage is not Triage.green


def test_a_second_reading_on_s5s_envelope_was_never_computed(corpus, policies) -> None:
    """s5 cut its envelope with the drive as a street; a second reading
    fitted on it is the first reading again, and the lot is a question."""
    from flats.ingest.quadfit import _worse

    lot = lot_from_row(behind())
    kw = dict(rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    (a,) = screen_lot(dataclasses.replace(lot, second=None), [pod()], **kw)
    (b,) = screen_lot(lot.second, [pod()], **kw)
    green = dataclasses.replace(a, signed=dataclasses.replace(a.signed, triage=Triage.green, reasons=()))
    fell_back = dataclasses.replace(b, envelope=dataclasses.replace(b.envelope, source="quadfit"))
    got = _worse(green, fell_back)
    assert got.signed.triage is Triage.unknown
    assert "STREET_UNCONFIRMED" in got.signed.reasons
    assert _worse(green, b).signed.triage is b.signed.triage or b.signed.triage is Triage.green


class _Ruled:
    def __init__(self, street: bool, access_choice: bool = False) -> None:
        self.private_drives = type(
            "R", (), {"street": street, "access_choice": access_choice}
        )()


def test_what_the_code_says_of_a_private_drive_the_lot_abuts_decides_the_readings() -> None:
    """A private drive on its own tract that the lot abuts: a street where
    the code counts it (one reading, s4's), an ordinary lot line where the
    code says a street is a public way (the reading without it, alone), and
    both ways where the code is silent, and both ways with the better kept
    where the line is a front only if the car comes in from it (Clackamas
    ZDO 202). A drive on other land is read both ways whatever the code
    says of drives."""
    from flats.ingest.quadfit import drive_reading

    tract = row(street_kind_json=json.dumps(["street", None, "drive", None]))
    school = row(street_kind_json=json.dumps(DRIVE_BEHIND_KINDS))
    mixed = row(street_kind_json=json.dumps(["drive", None, "drive_off_lot", None]))
    where = "or/multnomah/portland"
    counts, excluded, silent = {where: _Ruled(True)}, {where: _Ruled(False)}, {}
    chosen = {where: _Ruled(True, access_choice=True)}
    assert drive_reading(tract, counts) == (None, None)
    assert drive_reading(tract, excluded) == ("drives", "replace")
    assert drive_reading(tract, silent) == ("drives", "worse")
    assert drive_reading(tract, None) == ("drives", "worse")
    assert drive_reading(tract, chosen) == ("drives", "better")
    for layers in (counts, excluded, silent, chosen):
        assert drive_reading(school, layers) == ("doubtful", "worse")
    assert drive_reading(mixed, counts) == ("doubtful", "worse")
    assert drive_reading(mixed, excluded) == ("drives", "worse")


def test_where_the_code_says_a_street_is_public_the_drive_line_is_an_ordinary_line(layers) -> None:
    """Gresham 3.0100: a street is "the portion of a public right-of-way";
    Table 4.0131 note 2 makes a private accessway frontage the rear yard. A
    lot there whose rear line s4 read off a private drive on its own tract
    is screened on s4's reading without it, alone."""
    from flats.geom.edges import EdgeClass
    from flats.ingest.quadfit import drive_reading

    assert layers["or/multnomah/gresham"].private_drives.street is False
    assert layers["or/clackamas/wilsonville"].private_drives.street is True
    tract = dict(
        jurisdiction="gresham", zone="LDR-7",
        street_kind_json=json.dumps(["street", None, "drive", None]),
        sans_drive_json=json.dumps({"drives": json.loads(_sans())["doubtful"]}),
    )
    assert drive_reading(row(**tract), layers) == ("drives", "replace")
    alone = lot_from_row(behind(**tract), layers)
    assert alone.second is None and not alone.facts.street_unconfirmed
    assert sum(1 for e in alone.edges.edges if e.cls is EdgeClass.front) == 1
    # The yards read the drive as an ordinary line, but the car may still
    # come in off it (Steph 2026-09-30): both street lines are ways in.
    assert len(alone.access) == 2 and alone.access_bearings == (0.0,)
    # In Wilsonville the same drive is a street, and s4's reading stands.
    wilsonville = lot_from_row(behind(**{**tract, "jurisdiction": "wilsonville", "zone": "R"}), layers)
    assert wilsonville.second is None
    assert sum(1 for e in wilsonville.edges.edges if e.cls is EdgeClass.front) == 2


def test_every_private_drive_ruling_quotes_the_line_it_points_at(layers) -> None:
    """``private_drives.says`` is held verbatim by the line ``quote`` points
    at, in the store; and the codes the 2026-09-29 reading left undecided
    declare nothing, so their drive lines are read both ways."""
    from pathlib import Path

    store = Path(__file__).resolve().parents[1] / "provenance" / "docs"

    def norm(t: str) -> str:
        return " ".join(t.replace("–", "-").replace("- ", "-").split())

    ruled = {k: v.private_drives for k, v in layers.items() if v.private_drives is not None}
    # 13 on 2026-09-29; the six Washington layers ruled street: true 2026-09-30.
    # 20 on 2026-10-01: Cornelius (draft worktree) rules street: false -- its
    # "Street" is a way "which provides for public use" (CMC 18.195,
    # definitions L705-L706), and a private access is not in public control.
    # 21 the same day: Tigard (draft, 2026-10-01) street: true on 18.30 "Street" (three or more lots).
    assert len(ruled) == 21
    for layer_id, r in ruled.items():
        doc, _, rng = r.quote.partition("#L")
        a, _, b = rng.partition("-L")
        lines = (store / doc).read_text(encoding="utf-8").split("\n")
        assert norm(r.says) in norm(" ".join(lines[int(a) - 1 : int(b or a)])), layer_id
    assert {k for k, r in ruled.items() if not r.street} == {
        "or/multnomah/gresham", "or/clackamas/tualatin", "or/washington/cornelius",
    }
    assert {k for k, r in ruled.items() if r.access_choice} == {"or/clackamas/_unincorporated"}
    assert layers["or/multnomah/fairview"].private_drives is None


def test_where_the_car_chooses_the_front_the_better_reading_is_kept(layers, corpus, policies) -> None:
    """Clackamas ZDO 202 exception 2: a private road line is a front only
    where the car comes in from it, else a side line. The applicant
    chooses, so the lot is read both ways and the better kept; a lot the
    drive alone reaches has no exception to take and is read as s4 read it,
    no question asked (Steph 2026-09-30)."""
    from flats.ingest.quadfit import _better

    tract = dict(
        jurisdiction="clackamas_unincorporated", zone="R7",
        street_kind_json=json.dumps(["street", None, "drive", None]),
        sans_drive_json=json.dumps({"drives": json.loads(_sans())["doubtful"]}),
    )
    lot = lot_from_row(behind(**tract), layers)
    assert lot.second is not None and lot.second_better
    assert not lot.facts.street_unconfirmed
    # The drive-less reading is the car in off the public road: no way in
    # off the drive rides with it.
    assert lot.second.access == ()
    only = lot_from_row(
        behind(**{**tract, "sans_drive_json": json.dumps(
            {"drives": json.loads(_sans(tier="D", edges=[]))["doubtful"]}
        )}),
        layers,
    )
    assert only.second is None and not only.facts.street_unconfirmed
    kw = dict(rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    (a,) = screen_lot(dataclasses.replace(lot, second=None), [pod()], **kw)
    (b,) = screen_lot(lot.second, [pod()], **kw)
    (both,) = screen_lot(lot, [pod()], **kw)
    rank = {Triage.green: 0, Triage.yellow: 1, Triage.unknown: 2, Triage.red: 3}
    assert rank[both.signed.triage] == min(rank[a.signed.triage], rank[b.signed.triage])
    red = dataclasses.replace(a, signed=dataclasses.replace(a.signed, triage=Triage.red))
    green = dataclasses.replace(b, signed=dataclasses.replace(b.signed, triage=Triage.green))
    assert _better(red, green) is green and _better(green, red) is green
    # A second reading fitted on s5o's envelope was never computed.
    assert _better(red, dataclasses.replace(green, envelope=dataclasses.replace(
        green.envelope, source="quadfit"))) is red


def test_where_the_code_is_silent_the_drive_is_still_a_way_in(layers) -> None:
    """Fairview, silent: the lot is read with the drive a street and with
    it an ordinary line, the worse kept -- and on the second reading the
    car may still come in off the drive (Steph 2026-09-30). A drive on other
    land gives no way in."""
    from flats.ingest.quadfit import _street_lines

    tract = dict(
        jurisdiction="fairview", zone="R-7.5",
        street_kind_json=json.dumps(["street", None, "drive", None]),
        sans_drive_json=json.dumps({"drives": json.loads(_sans())["doubtful"]}),
    )
    lot = lot_from_row(behind(**tract), layers)
    assert lot.second is not None and not lot.second_better
    assert len(_street_lines(lot.second)) == 2
    assert len(_street_lines(lot)) == 2
    school = lot_from_row(behind(), layers)
    assert school.second is not None and school.second.access == ()


def test_an_s4_that_never_read_road_types_keeps_every_street_a_street() -> None:
    """A stage file written before ``street_kind_json`` existed, or an s1
    with no TYPE column, reads as absent: the old treatment."""
    assert "street_kind_json" in S4_COLUMNS and "sans_drive_json" in S4_COLUMNS
    for absent in (None, "", "null", "not json"):
        lot = lot_from_row(row(street_kind_json=absent))
        assert lot.second is None and not lot.facts.street_unconfirmed
def test_the_outdoor_square_is_measured_on_the_lots_own_ground(corpus, policies) -> None:
    # FOLLOWUPS 7(b1). Portland R5 asks a 12 ft outdoor square. On this 50 ft
    # lot the pod stands end-on, 36 ft across, with its row of four behind it
    # off the alley: the window proves nothing, so the bridge measures the
    # lot -- less its 10 ft front yard, the building and the paved court --
    # and finds 9 ft at most beside the building. A real miss, scored as one.
    lot = lot_from_row(
        cut_row(zone="R5", edges_json=json.dumps(BEHIND), alley_width_ft=14.0,
                alley_cover_json=json.dumps([None, None, "1" * 9 + "0", None])),
        corpus.layers,
    )
    (s,) = screen_lot(lot, [pod4()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)

    got = next(c for c in s.screening.checks if c.check == "open_space_shape")
    assert got.threshold == 12.0
    assert got.observed == pytest.approx(9.0, abs=0.5)
    assert got.verdict is slack.Verdict.fails
    assert "open_space_shape" not in s.screening.unchecked


def test_a_court_fed_from_the_side_street_is_measured_with_its_drive_band_paved(
    corpus, policies
) -> None:
    # FOLLOWUPS 7(b1). The Portland corner lot parks off its west street: no
    # lane beside the pod, and the drive to the court runs across the street
    # side yard at a point the drawing does not place. The court's whole
    # depth band is taken as paved, lot line to lot line -- every place the
    # drive could run -- and the square is measured on what is left rather
    # than left unasked.
    from flats.fit.draw import draw
    from flats.fit.rectangle import Fitter
    from flats.ingest.quadfit import outdoor_square
    from flats.score.paper import court_across, court_depth

    lot = lot_from_row(corner_row(zone="R5"), corpus.layers)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    assert row_for(s)["side_street_lane"] is True
    across = court_across(s.design, s.rules, s.lot.facts.alley, corner=s.lot.facts.corner)
    assert across.stalls and not across.lane_ft

    fitter = Fitter(s.envelope.geom, [s.fit.angle_deg])
    square = outdoor_square(s.lot, s.design, s.rules, s.fit, fitter, s.envelope)
    assert square is not None

    drawn = draw(
        fitter, s.fit, width_ft=56.0, depth_ft=36.0, lane_ft=0.0,
        court_depth_ft=court_depth(s.design, s.rules, s.lot.facts.alley)[0], court_beyond_ft=0.0,
        street=tuple((e.x1, e.y1, e.x2, e.y2) for e in s.lot.edges.of_class(EdgeClass.front)),
        paved_across_ft=across.width_ft, side_drive=True,
    )
    (band,) = drawn.paved
    on_lot = band.intersection(LOT)
    # Whichever way the plan stands, the band crosses the lot from one lot
    # line to the one opposite: over the street side yard to the street.
    x0, y0, x1, y1 = on_lot.bounds
    assert (x1 - x0 == pytest.approx(50.0)) or (y1 - y0 == pytest.approx(100.0))


def test_a_front_chosen_by_the_car_needs_the_drive_to_be_a_street() -> None:
    """``access_choice`` says the drive line is a front where the car comes
    in from it; on a code that says a private drive is no street at all it
    means nothing, and the loader refuses it."""
    from flats.rules.loader import _parse_private_drives

    base = {
        "quote": "or/clackamas/_unincorporated/zdo.202.definitions.txt#L289",
        "says": "from which motor vehicle access is taken is a front lot line",
        "note": "x" * 200,
    }
    problems: list[str] = []
    got = _parse_private_drives(
        {**base, "street": True, "access_choice": True}, where="t", problems=problems
    )
    assert got is not None and got.access_choice and not problems
    for bad in ({"street": False, "access_choice": True}, {"street": True, "access_choice": "yes"}):
        problems = []
        assert _parse_private_drives({**base, **bad}, where="t", problems=problems) is None
        assert problems and "access_choice" in problems[0]


def test_the_court_s_ground_is_the_lot_less_every_yard_but_the_rear() -> None:
    # FOLLOWUPS 33. The screen lets the court stand in the rear yard; the
    # ground it may run onto is the envelope plus that yard -- never a side
    # yard, a front yard or past the lot line.
    got = Rules(setback_front_ft=10, setback_side_ft=5, setback_rear_ft=15)
    env = envelope_for(lot_from_row(cut_row()), got)  # type: ignore[arg-type]
    assert env.sqft == pytest.approx(40 * 75)
    assert env.ground.area == pytest.approx(40 * 90)
    assert env.ground.buffer(1e-6).contains(env.geom)
    # No line is known as the rear on an irregular lot: inset by the largest
    # of the other yards.
    irregular = envelope_for(lot_from_row(cut_row(tier="C")), got)  # type: ignore[arg-type]
    assert irregular.ground.area == pytest.approx(30 * 80)
    # s5o's envelope knows no yard: the court at least stays on the lot.
    unread = envelope_for(lot_from_row(cut_row()), Rules(setback_front_ft=10, setback_rear_ft=10))  # type: ignore[arg-type]
    assert unread.source == "quadfit"
    assert unread.ground.area == pytest.approx(LOT.area)


def test_a_planted_strip_off_the_lot_lines_keeps_the_court_off_the_rear_line() -> None:
    # `parking_lot_line_buffer_ft`: the court still uses the rear yard, all
    # but the strip along the line.
    got = Rules(
        setback_front_ft=10, setback_side_ft=5, setback_rear_ft=15, parking_lot_line_buffer_ft=5
    )
    env = envelope_for(lot_from_row(cut_row()), got)  # type: ignore[arg-type]
    assert env.sqft == pytest.approx(40 * 75)
    assert env.ground.area == pytest.approx(40 * 85)
    # s5o's envelope names no line: the strip comes off every one.
    unread = envelope_for(  # type: ignore[arg-type]
        lot_from_row(cut_row()),
        Rules(setback_front_ft=10, setback_rear_ft=10, parking_lot_line_buffer_ft=5),
    )
    assert unread.source == "quadfit"
    assert unread.ground.area == pytest.approx(40 * 90)
