"""The bridge from quadfit's county map into the screen (flats/ingest/quadfit.py).

Steph, 2026-09-17: "bridge from the county map for now, but we will need an
authoritative offline source." These tests pin what the bridge reads off
quadfit's stage files, how it says each fact in the registry's words, and
that what comes out the other end is the screen's own verdict with the
signed colour beside it and never in its place.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import shapely
import yaml

from flats.designs.model import Design
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
    # The district flag never speaks for Multnomah, whose layer quadfit lacks.
    mult = observed_facts(row(sewer_main_dist_ft=400.0, in_sewer_district=False))
    assert "in_sewer_district" not in mult and "public_sewer" not in mult


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
    assert lot.observed["alley_at_rear"] is True
    assert lot.facts.envelope_rear_ft == 0.0
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
    written = run(out, s4=s4, s5o=s5o, results=results, step_deg=30.0, log=log.append)
    frame = pd.read_parquet(written)
    # Two lots x every catalog design, one row each.
    designs = frame["design"].nunique()
    assert designs >= 1 and len(frame) == 2 * designs
    assert set(frame["triage"]) == {"unknown"}
    assert set(frame.loc[frame["zone"] == "NOT-A-ZONE", "if_signed"]) == {"unknown"}
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta["lots"] == 2 and meta["rows"] == len(frame) and meta["step_deg"] == 30.0
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
    # and the ANY-line fact tightens every yard it governs).
    assert h.envelope.sqft == pytest.approx(30 * 90)
    assert s.envelope.sqft == pytest.approx(50 * 100)
    # The resolved rear IS the strip cut, so the court is charged against
    # the rules' own number.
    assert h.envelope.rear_cut_ft is None
    assert row_for(s)["envelope_source"] == "flats"
    assert row_for(s)["envelope_sqft"] == pytest.approx(5000)
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
    assert s.envelope.sqft == pytest.approx(50 * 70)


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


def test_a_rear_yard_the_alley_waives_is_cut_at_zero(corpus, policies) -> None:
    # Portland R5: no rear setback where the rear line is an alley. The
    # waiver resolves as an exemption, not a number; it is a yard of zero,
    # not a reason to fall back to quadfit's figure.
    lot = lot_from_row(cut_row(zone="R5", edges_json=json.dumps(BEHIND)), corpus.layers)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    assert s.envelope.source == "flats"
    assert s.envelope.setbacks.rear_ft == 0
    assert s.envelope.sqft == pytest.approx((50 - 2 * 5) * (100 - 10))


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


def test_an_alley_behind_the_lot_reaches_the_court_with_its_measured_width(corpus, policies) -> None:
    # FOLLOWUPS 4(b). s4's alley width rides into the lot's facts beside the
    # rear alley, and Portland's court behind the pod is charged as a stall
    # and the back-out room the alley's width leaves short -- not a stall and
    # a two-way aisle -- where the lot has the alley at the rear.
    fed = lot_from_row(cut_row(zone="R5", edges_json=json.dumps(BEHIND), alley_width_ft=14.0), corpus.layers)
    assert fed.facts.alley_at_rear is True and fed.facts.alley_width_ft == 14.0
    beside = lot_from_row(cut_row(zone="R5", edges_json=json.dumps(BESIDE), alley_width_ft=14.0), corpus.layers)
    assert beside.facts.rear_alley is None
    assert lot_from_row(cut_row(zone="R5")).facts.alley_width_ft is None

    def asked(lot) -> float:
        (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
        return next(c for c in s.screening.checks if c.check == "fit_ft").threshold

    wide = lot_from_row(cut_row(zone="R5", edges_json=json.dumps(BEHIND), alley_width_ft=20.0), corpus.layers)
    # Six feet of back-out paving on a 14 ft alley, none on a 20 ft one.
    assert asked(fed) - asked(wide) == pytest.approx(6.0)
