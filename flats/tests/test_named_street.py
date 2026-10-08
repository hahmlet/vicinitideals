"""The named-street fact: Estacada's NCR fourplex path, "within 200 feet of Eagle
Creek Rd, Hinman Rd, or a major collector". These tests pin what is measured
(only the two named streets, matched on RLIS name and type), that the answer is
True or False by the code's own 200 ft, and that nothing measured is nothing
answered."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import shapely
from shapely.geometry import LineString, box

from flats.geom.named_street import (
    NAMED_STREET_FACT,
    REACH_FT,
    named_street_column,
    named_street_lines,
    observed_named_street,
    street_distances,
)
from flats.ingest.quadfit import OBSERVABLE, S4_COLUMNS, iter_rows, observed_facts
from flats.rules.conditions import CONDITIONS

EAGLE = LineString([(0, 0), (1000, 0)])
HINMAN = LineString([(0, 1000), (1000, 1000)])
EAGLE_LANE = LineString([(0, 500), (1000, 500)])


def test_only_the_two_named_streets_are_origins() -> None:
    lines = named_street_lines(
        ["EAGLE CREEK", "HINMAN", "EAGLE CREEK", "CURRIN", None],
        ["RD", "RD", "LN", "RD", None],
        [EAGLE, HINMAN, EAGLE_LANE, LineString([(0, 2000), (10, 2000)]), None],
    )
    assert lines == [EAGLE, HINMAN]


def test_the_answer_is_the_codes_own_two_hundred_feet() -> None:
    assert REACH_FT == 200.0
    assert observed_named_street(200.0) == {NAMED_STREET_FACT: True}
    assert observed_named_street(0.0) == {NAMED_STREET_FACT: True}
    assert observed_named_street(200.5) == {NAMED_STREET_FACT: False}
    assert observed_named_street(None) == {}
    assert observed_named_street(float("nan")) == {}


def test_distance_to_the_nearest_named_street() -> None:
    near = box(100, 150, 150, 190)
    far = box(100, 400, 150, 450)
    got = street_distances([near, far, None], [EAGLE, HINMAN])
    assert got[0] == 150.0
    assert got[1] == 400.0
    assert got[2] is None
    assert street_distances([near], []) == [None]


def test_the_fact_is_registered_and_observable() -> None:
    assert NAMED_STREET_FACT in CONDITIONS
    assert NAMED_STREET_FACT in OBSERVABLE


def test_the_rows_carry_each_lots_distance(tmp_path: Path) -> None:
    lots = pd.DataFrame(
        [
            {"TLID": "near", "jurisdiction": "estacada", "zone": "NCR", "wkb": shapely.to_wkb(box(100, 50, 150, 100))},
            {"TLID": "far", "jurisdiction": "estacada", "zone": "NCR", "wkb": shapely.to_wkb(box(100, 400, 150, 450))},
        ]
    )
    s4 = tmp_path / "s4_lots.parquet"
    s5o = tmp_path / "s5o_lots.parquet"
    lots[[c for c in S4_COLUMNS if c in lots] + ["wkb"]].to_parquet(s4, index=False)
    lots[["TLID"]].to_parquet(s5o, index=False)
    streets = tmp_path / "s1_streets.parquet"
    pd.DataFrame(
        {
            "name": ["EAGLE CREEK", "OTHER"],
            "ftype": ["RD", "ST"],
            "type": [1400, 1500],
            "alley": [False, False],
            "wkb": [shapely.to_wkb(EAGLE), shapely.to_wkb(LineString([(0, 420), (1000, 420)]))],
        }
    ).to_parquet(streets, index=False)

    got = {r["TLID"]: r for r in iter_rows(s4, s5o, streets=streets)}
    assert got["near"]["named_street_ft"] == 50.0
    assert got["far"]["named_street_ft"] == 400.0
    assert observed_facts(got["near"])[NAMED_STREET_FACT] is True
    assert observed_facts(got["far"])[NAMED_STREET_FACT] is False
    plain = {r["TLID"]: r for r in iter_rows(s4, s5o)}
    assert "named_street_ft" not in plain["far"]
    assert NAMED_STREET_FACT not in observed_facts(plain["far"])


def test_a_street_file_without_names_measures_nothing(tmp_path: Path) -> None:
    streets = tmp_path / "s1_streets.parquet"
    pd.DataFrame({"type": [1500], "alley": [False], "wkb": [shapely.to_wkb(EAGLE)]}).to_parquet(streets, index=False)
    frame = pd.DataFrame({"lot_wkb": [shapely.to_wkb(box(0, 0, 10, 10))]})
    assert named_street_column(frame, streets) == [None]
