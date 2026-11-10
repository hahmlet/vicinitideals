"""FOLLOWUPS 105 round 5 (2026-11-10): the chapters fetched on 2026-11-08 with
Steph's OK, read with every reference into and out of them.

* Tigard 18.420 (landscaping and screening). The S-3 row was encoded in round
  3. Its S-4 row (8 ft) reaches the pod in MU-CBD, where 18.650.070.B.3 screens
  parking "When abutting a public right-of-way, pedestrian paths and trails in
  a public easement, or a public park". The street line is already 10 ft; the
  alley, park and trail lines now carry the 8 ft strip, the park read from ORCA
  through a Tigard ``parks:`` block and the trail from Metro's regional trails
  layer (``rlis_trails``, :mod:`flats.geom.trail`).
* Canby 16.41.070 (DCO design standards), fetched 2026-11-10 as the next layer
  of 16.41.050 and 16.41.060: measurable design details and commercial-only
  rows. Nothing encoded; a flat roof is allowed.
* Gladstone 17.76 (exceptions): re-read with the references into it. Nothing
  encoded.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import shapely

from flats.encode.load import load_trusted
from flats.geom import trail
from flats.ingest.quadfit import observed_facts, with_trails
from flats.ingest.sources import load_pipeline
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.conditions import CONDITIONS
from flats.rules.model import ORCA_UNIT_TYPES
from flats.rules.resolver import RuleSet
from flats.tests.test_quadfit_bridge import EDGES, X0, Y0, row

pytestmark = pytest.mark.unit

TIGARD = "or/washington/tigard"
CANBY = "or/clackamas/canby"
GLADSTONE = "or/clackamas/gladstone"
FIELD = "parking_lot_line_buffer_ft"
DOCS = Path(__file__).resolve().parents[1] / "provenance" / "docs"


@pytest.fixture(scope="module")
def corpus() -> RuleSet:
    return RuleSet(load_rules(strict=True))


def lines(path: str) -> list[str]:
    return (DOCS / path).read_text(encoding="utf-8").splitlines()


# --- Tigard MU-CBD, the S-4 strip ----------------------------------------------------


@pytest.mark.parametrize(
    "held",
    (
        ("abuts_alley",),
        ("abuts_park",),
        ("abuts_trail",),
        ("abuts_alley", "abuts_park"),
        ("abuts_alley", "abuts_trail"),
        ("abuts_park", "abuts_trail"),
        ("abuts_alley", "abuts_park", "abuts_trail"),
    ),
)
def test_mu_cbd_keeps_parking_8_ft_off_an_alley_a_park_or_a_trail(corpus: RuleSet, held: tuple) -> None:
    resolved = corpus.resolve(TIGARD, "MU-CBD", held)
    value = resolved.values[FIELD]
    assert value.value == 8
    assert not value.ambiguous


def test_mu_cbd_owes_no_strip_on_an_ordinary_lot_line(corpus: RuleSet) -> None:
    resolved = corpus.resolve(TIGARD, "MU-CBD", ())
    assert resolved.get(FIELD) is None
    # Each fact moves it, so a lot where any is unanswered is not certified --
    # a lot read without the trails layer holds out of GREEN.
    assert {"abuts_alley", "abuts_park", "abuts_trail"} <= resolved.levers


def test_the_street_line_already_holds_the_8_ft(corpus: RuleSet) -> None:
    assert corpus.resolve(TIGARD, "MU-CBD", ()).get("parking_street_setback_ft") >= 8


def test_the_8_is_the_s4_row_and_b3_sends_mu_cbd_parking_there() -> None:
    table = lines(f"{TIGARD}/tdc.18.420.landscaping.txt")
    assert table[255] == "S-4" and table[256] == "8 feet"
    b3 = lines(f"{TIGARD}/18.650/18.650.070.txt")[52]
    assert b3.startswith("When abutting a public right-of-way, pedestrian paths and trails")
    assert "a public park" in b3 and "S-4 standard" in b3


def test_the_variants_quote_the_printed_8_and_carry_b3_as_via(corpus: RuleSet) -> None:
    value = corpus.layers[TIGARD].zones["MU-CBD"].values[FIELD]
    assert value.exempt
    store = ProvenanceStore()
    for variant in value.variants:
        assert variant.value == 8
        assert "8 feet" in store.quote(variant.prov.quote)
        assert "a public park" in store.quote(variant.prov.via)
        assert "trails in a public easement" in store.quote(variant.prov.via)


def test_no_other_tigard_zone_reads_the_park_or_the_trail(corpus: RuleSet) -> None:
    for zone in corpus.layers[TIGARD].zones:
        if zone != "MU-CBD":
            levers = corpus.resolve(TIGARD, zone, ()).levers
            assert not {"abuts_park", "abuts_trail"} & levers, zone


def test_only_the_layers_the_trails_serve_have_a_trail_lever(corpus: RuleSet) -> None:
    reading = {
        layer_id
        for layer_id, layer in corpus.layers.items()
        for zone in layer.zones
        if "abuts_trail" in corpus.resolve(layer_id, zone, ()).levers
    }
    assert reading == set(trail.SERVES)


def test_bridgeport_s4_sits_inside_the_20_ft_street_setback(corpus: RuleSet) -> None:
    resolved = corpus.resolve(TIGARD, "MUC", ("tigard_bridgeport_village",))
    assert resolved.get("parking_street_setback_ft") >= 8


# --- Tigard's park -------------------------------------------------------------------


def test_tigards_park_is_land_set_apart_for_the_general_public(corpus: RuleSet) -> None:
    rule = corpus.layers[TIGARD].parks["abuts_park"]
    assert rule.true_for == ("Park",)
    assert set(rule.false_for) == {"Home Owners Association", "School Land"}
    # A cemetery, a golf course, a natural area or a trail parcel may be public
    # parkland or may not: a line across one stays unresolved.
    assert ORCA_UNIT_TYPES - set(rule.true_for) - set(rule.false_for) == {
        "Cemetery",
        "Golf Course",
        "Natural Area",
        "Other",
    }
    text = ProvenanceStore().quote(rule.quote)
    assert "for the general public" in text


@pytest.fixture(scope="module")
def layers():
    return load_trusted(strict=False).rules.layers


def mu_cbd(across: list) -> dict:
    return row(jurisdiction="tigard", zone="MU-CBD", park_across_json=json.dumps(across))


def seen(*kinds: str, none: int = 0) -> dict:
    return {"k": sorted(kinds), "none": none}


def test_the_bridge_reads_a_park_behind_a_downtown_lot(layers) -> None:
    got = observed_facts(mu_cbd([None, seen(none=5), seen("Park", none=2), seen(none=5)]), layers)
    assert got["abuts_park"] is True


def test_the_bridge_clears_a_downtown_lot_with_nothing_across(layers) -> None:
    got = observed_facts(mu_cbd([None, seen(none=5), seen("School Land"), seen(none=5)]), layers)
    assert got["abuts_park"] is False


def test_the_bridge_leaves_a_trail_parcel_unstated(layers) -> None:
    got = observed_facts(mu_cbd([None, seen(none=5), seen("Other", none=1), seen(none=5)]), layers)
    assert "abuts_park" not in got


# --- Canby 16.41.070 and Gladstone 17.76 ---------------------------------------------


def test_canby_16_41_070_is_held_and_declared(corpus: RuleSet) -> None:
    path = DOCS / CANBY / "cmc.16.41.070.txt"
    meta = json.loads(Path(f"{path}.meta.json").read_text(encoding="utf-8"))
    assert meta["url"].endswith("0-0-0-39463")
    ids = {doc.id for doc in corpus.layers[CANBY].code}
    assert "cmc.16.41.070" in ids


def test_canby_dco_allows_the_flat_roof_and_keeps_its_ground_floor_rule_commercial() -> None:
    text = lines(f"{CANBY}/cmc.16.41.070.txt")
    assert text[260].startswith("a. Roof forms may be flat or sloped.")
    assert text[206].startswith("a. The ground floor of the building shall range from 12 feet to 16 feet")
    assert text[209] == "(commercial and mixed use buildings only)"


def test_canby_entries_were_already_held_to_the_street(corpus: RuleSet) -> None:
    assert corpus.resolve(CANBY, "C-1", ()).get("entrance_faces_street") == "required"


def test_gladstone_17_76_holds_four_sections_and_no_height_exception() -> None:
    text = lines(f"{GLADSTONE}/17.76.exceptions.txt")
    assert [t for t in text[6:13] if t] == [
        "17.76.010 Exceptions—Generally.",
        "17.76.020 Nonconforming uses and nonconforming developments.",
        "17.76.030 Lot size requirements.",
        "17.76.040 Setback requirements.",
    ]


# --- Tigard's trail ------------------------------------------------------------------


def test_the_trails_layer_is_registered_from_the_rlis_bundle() -> None:
    ds = load_pipeline().datasets[trail.TRAILS_KEY]
    assert ds.member == "TRANSIT/trails.shp"
    assert ds.kind.value == "rlis_zip"
    assert {"STATUS", "SYSTEMTYPE"} <= set(ds.fields)
    assert set(trail.SERVES) <= set(ds.serves)


def test_abuts_trail_is_a_registered_site_fact() -> None:
    assert CONDITIONS[trail.TRAIL_FACT].kind == "site_fact"


@pytest.mark.parametrize(
    ("status", "kind", "counted"),
    (
        ("Open", "Community", True),
        ("Open_Fee", "Local", True),
        ("Planned", "Regional", True),
        ("Restricted_Private", "Local", True),
        ("Under construction", "Local", True),
        ("Unknown", "Local", True),
        ("On-Street", "Regional", True),
        ("Conceptual", "Regional", False),
        ("Decommissioned", "Local", False),
        ("Open", "Other", False),
    ),
)
def test_which_trail_records_count(status: str, kind: str, counted: bool) -> None:
    assert trail.counts({"STATUS": status, "SYSTEMTYPE": kind}) is counted


LOT = shapely.box(X0, Y0, X0 + 50, Y0 + 100)


def along_rear(offset: float):
    """A trail running along the rear line (y = Y0 + 100), ``offset`` ft out."""
    y = Y0 + 100 + offset
    return shapely.LineString([(X0 - 100, y), (X0 + 150, y)])


def along_front(offset: float):
    """A trail in the street, ``offset`` ft in front of the street line."""
    y = Y0 - offset
    return shapely.LineString([(X0 + 20, y), (X0 + 30, y)])


@pytest.mark.parametrize(
    ("line", "expected"),
    (
        (along_rear(10.0), True),
        (along_rear(trail.REACH_FT), True),
        (along_rear(trail.REACH_FT + 5.0), False),
        (shapely.LineString([(X0 + 25, Y0 - 20), (X0 + 25, Y0 + 120)]), True),  # crosses the lot
        (along_front(10.0), False),  # in the street: the street setback holds it
    ),
)
def test_a_trail_abuts_where_it_crosses_or_runs_beside_a_non_street_line(line, expected: bool) -> None:
    assert trail.abuts(LOT, EDGES, trail.build([line])) is expected


def test_a_lot_without_outline_or_edges_is_not_answered() -> None:
    lines_ = trail.build([along_rear(5.0)])
    assert trail.abuts(None, EDGES, lines_) is None
    assert trail.abuts(LOT, [], lines_) is None


def snapshot(tmp_path: Path, *features: tuple) -> Path:
    fc = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"STATUS": status, "SYSTEMTYPE": "Local"},
             "geometry": shapely.geometry.mapping(geom)}
            for geom, status in features
        ],
    }
    (tmp_path / "rlis_trails.geojson").write_text(json.dumps(fc), encoding="utf-8")
    return tmp_path


def downtown(**over) -> dict:
    return row(jurisdiction="tigard", zone="MU-CBD", lot_wkb=shapely.to_wkb(LOT), **over)


def test_the_bridge_reads_a_trail_behind_a_downtown_lot(tmp_path: Path, layers) -> None:
    rows = [downtown(), row(lot_wkb=shapely.to_wkb(LOT))]  # a Portland lot is not asked
    assert with_trails(rows, snapshot(tmp_path, (along_rear(6.0), "Open"))) == 1
    assert rows[0]["trail_abuts_obs"] is True
    assert "trail_abuts_obs" not in rows[1]
    assert observed_facts(rows[0], layers)["abuts_trail"] is True


def test_a_conceptual_trail_leaves_the_lot_clear(tmp_path: Path, layers) -> None:
    rows = [downtown()]
    assert with_trails(rows, snapshot(tmp_path, (along_rear(6.0), "Conceptual"))) == 1
    assert observed_facts(rows[0], layers)["abuts_trail"] is False


def test_without_the_trails_layer_the_lot_is_not_answered(tmp_path: Path, layers) -> None:
    rows = [downtown()]
    assert with_trails(rows, tmp_path) == 0  # a snapshot without rlis_trails
    assert with_trails(rows, None) == 0  # no snapshot at all
    assert "abuts_trail" not in observed_facts(rows[0], layers)
