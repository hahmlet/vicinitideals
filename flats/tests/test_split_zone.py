"""A lot in more than one zoning district (FOLLOWUPS 76(b)).

Steph 2026-10-14: "first check if the city has a rule on this. If no, I would
say yellow." The contracts:

* a city's own rule, where the code has one, is applied -- and stands on a
  line of stored code text the test reads back;
* where none was found a green plan that stands on another district's ground
  is YELLOW and the flag names that district;
* a map code the corpus spells another way is the SAME district, not a second
  one, and a lot whose own district the maps cannot find is the worst case;
* only a plan that reaches the other ground is moved.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

shapely = pytest.importorskip("shapely")

from flats.geom import split_zone as sz  # noqa: E402
import dataclasses  # noqa: E402
import json  # noqa: E402

from flats.ingest.quadfit import lot_from_row, screen_lot, split_zone_checked  # noqa: E402
from flats.score import flags as flag_plan  # noqa: E402
from flats.score.screen import CLOSER_LOOK_SPLIT_ZONE, Triage  # noqa: E402
from flats.tests.test_quadfit_bridge import (  # noqa: E402
    X0,
    Y0,
    corpus,  # noqa: F401  (fixture)
    pod,
    row,
    policies,  # noqa: F401  (fixture)
)

pytestmark = pytest.mark.unit

DOCS = Path(__file__).resolve().parents[1] / "provenance" / "docs"


def lot_100() -> shapely.Polygon:
    return shapely.box(0, 0, 100, 100)


def zones(*pairs):
    """Polygons and codes: ``(code, (x0, x1))`` strips of the 100 x 100 lot."""
    return (
        [shapely.box(x0, -10, x1, 110) for _, (x0, x1) in pairs],
        [code for code, _ in pairs],
    )


def split_of(*pairs, own_codes=("R5",), spell=lambda c: c):
    polys, codes = zones(*pairs)
    return sz.pieces_of(lot_100(), polys, codes, lambda c: spell(c) in own_codes, spell)


# --- reading the maps ---------------------------------------------------


def test_the_ground_of_another_district_is_a_piece_and_says_how_far_it_reaches() -> None:
    got = split_of(("R5", (0, 70)), ("CM2", (70, 200)))

    assert got.own_sqft == pytest.approx(7000)
    (piece,) = got.pieces
    assert piece.zone == "CM2"
    assert piece.sqft == pytest.approx(3000)
    # The zone line would have to move 30 ft to take it in.
    assert piece.reach_ft == pytest.approx(30, abs=0.01)
    assert not got.unresolved


def test_a_code_the_corpus_spells_another_way_is_the_same_district() -> None:
    # The map writes R-5 beside R5 and the corpus holds R5: one district.
    spell = lambda c: c.replace("-", "")  # noqa: E731
    got = split_of(("R5", (0, 60)), ("R-5", (60, 100)), spell=spell)

    assert got.pieces == ()
    assert not got


def test_a_noise_sliver_of_another_district_is_not_a_piece() -> None:
    got = split_of(("R5", (0, 99)), ("CM2", (99, 200)))  # 100 sq ft is the line
    assert [p.zone for p in got.pieces] == ["CM2"]
    thin = split_of(("R5", (0, 99.5)), ("CM2", (99.5, 200)))
    assert thin.pieces == ()


def test_a_lot_whose_own_district_the_maps_do_not_show_is_the_worst_case() -> None:
    # Nothing on the map matches the zone the lot screens under: the maps and
    # the corpus disagree about what the lot is (the unmatched spellings).
    got = split_of(("XX", (0, 60)), ("CM2", (60, 100)))

    assert got.unresolved
    assert got
    assert not sz.governed(got, sz.Ruling("majority", cite="x"))


# --- what a city's code says --------------------------------------------


def piece(zone: str, reach: float, sqft: float = 1000.0) -> sz.Piece:
    return sz.Piece(zone, sqft, shapely.box(0, 0, 1, 1), reach)


@pytest.mark.parametrize(
    ("inclusive", "reach", "governed"),
    [
        (True, 19.9, True),
        (True, 20.0, True),  # "20 feet or less" (Beaverton, Milwaukie)
        (True, 20.1, False),
        (False, 19.9, True),
        (False, 20.0, False),  # "less than 20 feet" (Cornelius, Hillsboro, Canby)
    ],
)
def test_a_majority_rule_with_a_distance_holds_only_within_it(inclusive, reach, governed) -> None:
    ruling = sz.Ruling("majority_within", ft=20.0, inclusive=inclusive, cite="x")
    got = sz.Split((piece("CM2", reach),), own_sqft=9000)

    assert sz.governed(got, ruling) is governed


def test_a_majority_rule_with_no_distance_always_holds() -> None:
    # Sandy 17.04.80.B.6.
    got = sz.Split((piece("CM2", 80.0),), own_sqft=9000)
    assert sz.governed(got, sz.Ruling("majority", cite="x"))


def test_a_rule_that_keeps_each_district_to_its_own_part_never_holds_the_lot_whole() -> None:
    got = sz.Split((piece("CM2", 5.0),), own_sqft=9000)
    assert not sz.governed(got, sz.Ruling("each_zone", cite="x"))
    assert not sz.governed(got, sz.SILENT)


def test_the_screens_district_has_to_be_the_one_covering_most_of_the_lot() -> None:
    # An alias can make the screened district the smaller one; the code's
    # "greater area" then names another district, so nothing is governed.
    ruling = sz.Ruling("majority", cite="x")
    assert not sz.governed(sz.Split((piece("CM2", 5.0, sqft=6000),), own_sqft=4000), ruling)


def test_every_listed_city_is_ruled_or_silent_once_and_the_file_loads() -> None:
    got = sz.rulings()
    assert got["or/washington/beaverton"].rule == "majority_within"
    assert got["or/clackamas/sandy"].rule == "majority"
    assert got["or/multnomah/portland"].rule == "each_zone"
    assert got["or/clackamas/estacada"] is sz.SILENT
    assert sz.ruling_for("or/never/heard-of-it") is sz.SILENT
    assert sz.ruling_for(None) is sz.SILENT


def _words(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xad", "")).strip()


@pytest.mark.parametrize("layer", sorted(k for k, v in sz.rulings().items() if v is not sz.SILENT))
def test_each_rule_stands_on_the_line_of_code_it_cites(layer: str) -> None:
    """The quote is on the cited lines of the stored text -- a rule nobody can
    find in the code is not a rule (a URL cite is checked by hand)."""
    r = sz.rulings()[layer]
    if r.cite.startswith("http"):
        pytest.skip("cited from the city's online code; the text is not stored")
    path, _, span = r.cite.partition("#")
    start, _, end = span.removeprefix("L").partition("-L")
    lines = (DOCS / path).read_text(encoding="utf-8").splitlines()
    cited = _words(" ".join(lines[int(start) - 1 : int(end)]))
    assert _words(r.quote) in cited, f"{layer}: {r.quote!r} is not on {r.cite}"


# --- the plan on the other ground ---------------------------------------


def test_only_a_plan_that_stands_on_the_other_ground_reaches_it() -> None:
    got = sz.Split((sz.Piece("CM2", 3000, shapely.box(70, 0, 100, 100), 30.0),), own_sqft=7000)

    assert sz.reached(got, [shapely.box(10, 10, 50, 60)]) == ()
    assert sz.reached(got, [shapely.box(10, 10, 50, 60), shapely.box(60, 0, 80, 40)]) == ("CM2",)
    # Ten square feet of the plan on it is the map failing to meet the fence.
    assert sz.reached(got, [shapely.box(65, 0, 70.5, 20)]) == ()
    assert sz.reached(got, []) == ()


def test_the_split_survives_the_row() -> None:
    got = split_of(("R5", (0, 70)), ("CM2", (70, 200)))
    back = sz.decode(sz.encode(got))

    assert [p.zone for p in back.pieces] == ["CM2"]
    assert back.pieces[0].reach_ft == pytest.approx(got.pieces[0].reach_ft, abs=0.1)
    assert back.own_sqft == pytest.approx(got.own_sqft, abs=0.1)
    assert not sz.decode(None)


def test_the_join_reads_the_zoning_map_quadfit_s1_stores_under_its_real_name(tmp_path) -> None:
    # quadfit s1 writes ``s1_<zoning_layer>.parquet`` where the layer is itself
    # named ``zoning_<city>`` (so ``s1_zoning_zoning_beaverton``). The first
    # bound read ``s1_zoning_beaverton`` -- no such file -- joined nothing, and
    # no unit test reached the file.
    import pandas as pd

    from flats.encode.port_quadfit import QUADFIT_RULES

    layers = sz.zoning_layers(QUADFIT_RULES)
    layer = layers["beaverton"]
    polys, codes = zones(("R5", (0, 70)), ("CM2", (70, 200)))
    pd.DataFrame({"zone_raw": codes, "wkb": [shapely.to_wkb(p) for p in polys]}).to_parquet(
        tmp_path / f"s1_zoning_{layer}.parquet"
    )
    split_row = {
        "jurisdiction": "beaverton",
        "split_zone": True,
        "lot_wkb": shapely.to_wkb(lot_100()),
    }
    one_zone = {"jurisdiction": "beaverton", "split_zone": False, "lot_wkb": shapely.to_wkb(lot_100())}
    rows = [split_row, one_zone]

    taken = sz.with_split_zones(rows, tmp_path, layers, own=lambda r, c: c == "R5", name=lambda r, c: c)

    assert taken == 1
    assert [p.zone for p in sz.decode(split_row[sz.ROW_KEY]).pieces] == ["CM2"]
    assert sz.ROW_KEY not in one_zone


# --- the screen ---------------------------------------------------------

W, D = 100, 150


def big_row(**over):
    """A 100 x 150 lot, street along the south, with the taxlot on the row."""
    edges = [
        [X0, Y0, X0 + W, Y0, "F"],
        [X0 + W, Y0, X0 + W, Y0 + D, "S"],
        [X0 + W, Y0 + D, X0, Y0 + D, "R"],
        [X0, Y0 + D, X0, Y0, "S"],
    ]
    return row(
        area_sqft=W * D,
        frontage_ft=W,
        lot_width_ft=W,
        lot_depth_ft=D,
        edges_json=json.dumps(edges),
        lot_wkb=shapely.to_wkb(shapely.box(X0, Y0, X0 + W, Y0 + D)),
        **over,
    )


#: 40 ft of the east side in another district, where the pod's 56-ft-wide
#: plan stands (the street end, from the west).
EAST = sz.Piece("CM2", 40 * D, shapely.box(X0 + 60, Y0, X0 + W, Y0 + D), 40.0)
#: ... and a piece in the far rear corner the plan never reaches.
CORNER = sz.Piece("CM2", 15 * 15 * 1.0, shapely.box(X0 + 85, Y0 + 135, X0 + W, Y0 + D), 15.0)


def screened(corpus, policies, *, jurisdiction="oregon_city", zone="R-6", split=None):  # noqa: F811
    """The bridge's answer for the lot, made GREEN as it would be with every
    fact observed (the bare row leaves facts open, which is a flag of its own)
    and then run through the split-zone check."""
    over = {} if split is None else {sz.ROW_KEY: sz.encode(split)}
    lot = lot_from_row(big_row(jurisdiction=jurisdiction, zone=zone, **over), corpus.layers)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)

    def green(x):
        return dataclasses.replace(
            x, triage=Triage.green, reasons=(), flags=(), binds=()
        )

    plain = dataclasses.replace(s, screening=green(s.screening), signed=green(s.signed))
    return lot, plain, split_zone_checked(plain, lot)


def zone_flags(s):
    return [f for f in s.signed.flags if f.code == "ZONE-SPLIT"]


def test_a_lot_in_one_district_is_untouched(corpus, policies) -> None:  # noqa: F811
    _, plain, got = screened(corpus, policies)
    assert got is plain
    assert plain.signed.colour is flag_plan.Colour.green


def test_a_plan_across_the_line_where_the_city_has_no_rule_is_yellow_and_names_the_district(
    corpus, policies  # noqa: F811
) -> None:
    _, plain, s = screened(corpus, policies, split=sz.Split((EAST,), own_sqft=60 * D))

    assert plain.signed.colour is flag_plan.Colour.green
    (flag,) = zone_flags(s)
    assert s.signed.colour is flag_plan.Colour.yellow
    assert s.signed.triage is Triage.yellow
    assert CLOSER_LOOK_SPLIT_ZONE in s.signed.reasons
    assert "CM2" in flag.source
    assert "no rule" in flag.source
    assert flag_plan.severity_of(flag) >= flag_plan.load_rules().yellow_at_severity
    # The verdict the screen gave under the rules is unchanged by it.
    assert s.screening.checks == plain.screening.checks


def test_a_plan_that_never_reaches_the_other_ground_stays_green(corpus, policies) -> None:  # noqa: F811
    _, _, s = screened(corpus, policies, split=sz.Split((CORNER,), own_sqft=W * D - 225))

    assert zone_flags(s) == []
    assert s.signed.colour is flag_plan.Colour.green


def test_a_citys_majority_rule_within_its_distance_leaves_the_lot_as_screened(
    corpus, policies  # noqa: F811
) -> None:
    # Beaverton BDC 10.35.2.C: 20 ft or less and the whole lot is the larger
    # district. The same ground 20.1 ft out is not, and the flag cites the rule.
    wide = shapely.box(X0 + 20, Y0, X0 + W, Y0 + D)  # under the plan wherever it stands
    near = dataclasses.replace(EAST, geom=wide, reach_ft=20.0)
    far = dataclasses.replace(EAST, geom=wide, reach_ft=20.1)
    _, _, within = screened(
        corpus, policies, jurisdiction="beaverton", zone="R5", split=sz.Split((near,), own_sqft=60 * D)
    )
    _, _, beyond = screened(
        corpus, policies, jurisdiction="beaverton", zone="R5", split=sz.Split((far,), own_sqft=60 * D)
    )

    assert zone_flags(within) == []
    assert within.signed.colour is flag_plan.Colour.green
    (flag,) = zone_flags(beyond)
    assert "BDC 10.35.2.C" in flag.source
    assert "bdc.10.general-provisions.txt#L274-L278" in flag.source
    assert beyond.signed.colour is flag_plan.Colour.yellow


def test_each_district_for_its_own_part_is_yellow_and_cites_the_city(corpus, policies) -> None:  # noqa: F811
    _, _, s = screened(
        corpus, policies, jurisdiction="portland", zone="R5", split=sz.Split((EAST,), own_sqft=60 * D)
    )

    (flag,) = zone_flags(s)
    assert "33.110" in flag.source
    assert s.signed.colour is flag_plan.Colour.yellow


def test_a_lot_whose_own_district_the_maps_cannot_find_is_flagged_wherever_the_plan_stands(
    corpus, policies  # noqa: F811
) -> None:
    # Even the corner the plan never reaches: nothing says where its own
    # ground ends (the lots whose map code the corpus spells another way).
    _, _, s = screened(corpus, policies, split=sz.Split((CORNER,), unresolved=True))

    assert [f.code for f in zone_flags(s)] == ["ZONE-SPLIT"]
    assert s.signed.colour is flag_plan.Colour.yellow


def test_a_lot_with_no_drawing_is_the_worst_case(corpus, policies) -> None:  # noqa: F811
    lot, plain, _ = screened(corpus, policies, split=sz.Split((CORNER,), own_sqft=W * D - 225))
    undrawn = dataclasses.replace(plain, drawing=None)

    assert [f.code for f in zone_flags(split_zone_checked(undrawn, lot))] == ["ZONE-SPLIT"]


def test_a_red_lot_keeps_the_flag_and_stays_red(corpus, policies) -> None:  # noqa: F811
    lot, plain, _ = screened(corpus, policies, split=sz.Split((EAST,), own_sqft=60 * D))
    bind = flag_plan.Bind("min_lot_area_sqft", 4999.5, 5000.0, 0.5, relief="variance")
    red = dataclasses.replace(
        plain,
        screening=dataclasses.replace(plain.screening, binds=(bind,)),
        signed=dataclasses.replace(plain.signed, binds=(bind,)),
    )
    s = split_zone_checked(red, lot)

    assert zone_flags(s)
    assert s.signed.colour is flag_plan.Colour.red
