"""The street-end fact: Gresham's Minor Access Street note, and how far it reaches.

Gresham Table 4.0131 note 5 sets a 5 ft minimum and a 25 ft maximum setback
"from the end of a Minor Access Street". Neither number is encoded, so the
note caps every Gresham setback until a lot is shown not to be at a street's
end. These tests pin the three things that keep that from becoming a false
GREEN: what counts as a street ending, that the answer is only ever False,
and that the note's cap names this fact and not the street's class.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import shapely
from shapely.geometry import LineString, Point, box

from flats.geom.street_end import (
    NOT_PUBLIC,
    REACH_FT,
    STREET_END_FACT,
    end_distances,
    observed_street_end,
    street_end_column,
    street_ends,
)
from flats.ingest.quadfit import OBSERVABLE, S4_COLUMNS, iter_rows, observed_facts
from flats.rules import caps
from flats.rules.conditions import CONDITIONS

# A through street along y=0 and a 300 ft stub north off it at x=500.
MAIN = LineString([(0, 0), (500, 0)])
MAIN2 = LineString([(500, 0), (1000, 0)])
STUB = LineString([(500, 0), (500, 300)])


def test_a_stub_ends_where_it_stops_and_a_through_street_does_not() -> None:
    ends = street_ends([MAIN, MAIN2, STUB], [1500, 1500, 1500], [False] * 3)
    # The far ends of the through street are ends too (the file stops there),
    # which only ever keeps a cap; the junction at (500, 0) is not one.
    assert (500, 300) in ends
    assert (500, 0) not in ends


def test_a_public_street_that_runs_on_as_a_private_road_ends_where_the_public_part_ends() -> None:
    private = LineString([(500, 300), (500, 600)])
    ends = street_ends([MAIN, MAIN2, STUB, private], [1500, 1500, 1500, 1700], [False] * 4)
    assert (500, 300) in ends  # the public street's end
    assert (500, 600) in ends  # and the private road's own


def test_an_alley_never_carries_a_street_on() -> None:
    alley = LineString([(500, 300), (900, 300)])
    ends = street_ends([MAIN, MAIN2, STUB, alley], [1500, 1500, 1500, 1600], [False, False, False, True])
    assert (500, 300) in ends
    assert (900, 300) not in ends


def test_a_line_of_unknown_type_can_end_a_street_but_never_continue_one() -> None:
    assert 8224 in NOT_PUBLIC
    odd = LineString([(500, 300), (500, 600)])
    for kind in (8224, None, float("nan")):
        ends = street_ends([MAIN, MAIN2, STUB, odd], [1500, 1500, 1500, kind], [False] * 4)
        assert (500, 300) in ends, kind


def test_distances_are_to_the_taxlot_not_its_centre() -> None:
    lot_at_end = box(480, 300, 520, 400)
    lot_far = box(0, 50, 50, 150)
    got = end_distances([lot_at_end, lot_far, None], [(500, 300)])
    assert got[0] == 0.0
    assert got[1] > REACH_FT
    assert got[2] is None
    assert end_distances([lot_at_end], []) == [None]


def test_the_fact_is_only_ever_false_and_only_beyond_the_reach() -> None:
    assert observed_street_end(REACH_FT + 0.1) == {STREET_END_FACT: False}
    assert observed_street_end(REACH_FT) == {}
    assert observed_street_end(0.0) == {}
    assert observed_street_end(None) == {}
    assert observed_street_end(float("nan")) == {}
    for d in (0.0, 10.0, REACH_FT, REACH_FT * 10):
        assert True not in observed_street_end(d).values()


def test_the_fact_is_registered_with_no_assumption() -> None:
    fact = CONDITIONS[STREET_END_FACT]
    assert fact.kind == "site_fact"
    assert fact.assume is None
    assert STREET_END_FACT in OBSERVABLE


def test_greshams_end_of_street_note_caps_on_the_street_end_not_the_class() -> None:
    caps.reload()
    for zone in ("LDR-5", "LDR-7", "TLDR", "TR", "MDR-12", "MDR-24", "OFR"):
        fields = caps.caps_for("or/multnomah/gresham", zone)
        assert STREET_END_FACT in fields["setback_front_ft"], zone
        assert all("local_street" not in facts for facts in fields.values()), zone


def test_the_bridge_answers_false_only_on_a_lot_no_street_ends_near() -> None:
    far = observed_facts({"street_end_ft": REACH_FT * 2})
    assert far[STREET_END_FACT] is False
    for near in ({"street_end_ft": 10.0}, {"street_end_ft": None}, {}):
        assert STREET_END_FACT not in observed_facts(near)


def test_the_rows_carry_each_lots_distance_to_a_street_end(tmp_path: Path) -> None:
    lots = pd.DataFrame(
        [
            {"TLID": "end", "jurisdiction": "gresham", "zone": "LDR-5", "wkb": shapely.to_wkb(box(480, 300, 520, 400))},
            {"TLID": "far", "jurisdiction": "gresham", "zone": "LDR-5", "wkb": shapely.to_wkb(box(0, 400, 50, 500))},
        ]
    )
    s4 = tmp_path / "s4_lots.parquet"
    s5o = tmp_path / "s5o_lots.parquet"
    lots[[c for c in S4_COLUMNS if c in lots] + ["wkb"]].to_parquet(s4, index=False)
    lots[["TLID"]].to_parquet(s5o, index=False)
    streets = tmp_path / "s1_streets.parquet"
    pd.DataFrame(
        {
            "type": [1500, 1500, 1500],
            "alley": [False, False, False],
            "wkb": [shapely.to_wkb(g) for g in (MAIN, MAIN2, STUB)],
        }
    ).to_parquet(streets, index=False)

    got = {r["TLID"]: r for r in iter_rows(s4, s5o, streets=streets)}
    assert got["end"]["street_end_ft"] == 0.0
    assert got["far"]["street_end_ft"] > REACH_FT
    assert STREET_END_FACT not in observed_facts(got["end"])
    assert observed_facts(got["far"])[STREET_END_FACT] is False
    # Without the street file nothing is measured, and nothing is answered.
    plain = {r["TLID"]: r for r in iter_rows(s4, s5o)}
    assert "street_end_ft" not in plain["far"]


def test_a_street_file_without_rlis_type_measures_nothing(tmp_path: Path) -> None:
    streets = tmp_path / "s1_streets.parquet"
    pd.DataFrame({"alley": [False], "wkb": [shapely.to_wkb(STUB)]}).to_parquet(streets, index=False)
    frame = pd.DataFrame({"lot_wkb": [shapely.to_wkb(box(0, 400, 50, 500))]})
    assert street_end_column(frame, streets) == [None]
    assert json.dumps(street_end_column(pd.DataFrame({"x": [1]}), streets)) == "[null]"


def test_a_point_near_the_end_is_not_far() -> None:
    # The lot sits across the bulb from the end point: inside the reach.
    lot = Point(500, 300).buffer(REACH_FT - 1).difference(Point(500, 300).buffer(REACH_FT - 20))
    assert observed_street_end(end_distances([lot], [(500, 300)])[0]) == {}
