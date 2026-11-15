"""The set access sample script's lot picking and summary (FOLLOWUPS 145)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from scripts.flats_set_access_sample import _pick, _summary

DRAWN = json.dumps({"fits": True, "building": [[0, 0], [80, 0], [80, 25], [0, 25], [0, 0]]})
MISSED = json.dumps({"fits": False, "building": None})


def _args(**kw) -> argparse.Namespace:
    base = dict(colour="green", tlids=None, per_jurisdiction=None, sample=None, seed=0, run="RUN")
    return argparse.Namespace(**{**base, **kw})


def _lots() -> pd.DataFrame:
    rows = []
    for j in ("Portland", "Gresham"):
        for i in range(5):
            rows.append(dict(TLID=f"{j[:2]} {i}", jurisdiction=j, zone="R5", colour="green", drawing=DRAWN))
    rows.append(dict(TLID="Po 0", jurisdiction="Portland", zone="R5", colour="green", drawing=DRAWN))
    rows.append(dict(TLID="Po 9", jurisdiction="Portland", zone="R5", colour="red", drawing=DRAWN))
    rows.append(dict(TLID="Po 8", jurisdiction="Portland", zone="R5", colour="green", drawing=MISSED))
    rows.append(dict(TLID="Po 7", jurisdiction="Portland", zone="R5", colour="green", drawing=None))
    return pd.DataFrame(rows)


def test_pick_keeps_drawn_fitting_lots_once_of_the_colour() -> None:
    got = _pick(_lots(), _args())
    assert sorted(got["TLID"]) == sorted([f"Po {i}" for i in range(5)] + [f"Gr {i}" for i in range(5)])
    assert len(_pick(_lots(), _args(colour="any"))) == 11


def test_pick_stratifies_by_jurisdiction() -> None:
    got = _pick(_lots(), _args(per_jurisdiction=2))
    assert got.groupby("jurisdiction").size().to_dict() == {"Gresham": 2, "Portland": 2}


def test_summary_counts_results_and_reasons() -> None:
    rows = [
        {"jurisdiction": "Portland", "result": "IC-80 one face (front)", "binding_check": "lifts: Upper back wall",
         "hardest_lift": "Upper back wall", "pct_of_chart": 63.1, "chart_row_ft": 32.0},
        {"jurisdiction": "Portland", "result": "45 t on site", "binding_check": "lifts: Ground-wall stack (load 1)",
         "hardest_lift": "Ground-wall stack (load 1)", "pct_of_chart": 47.2, "chart_row_ft": 25.0,
         "why": "IC-80 one face (front): swing room: less than 12 ft beyond a wall end inside the lot"},
        {"jurisdiction": "Portland", "result": "not viable",
         "why": "45 t in the street: the street in front is 24 ft wide at most; the 45 t pad needs 28 ft"},
        {"jurisdiction": "Gresham", "result": "unmeasured", "why": "x"},
    ]
    text = _summary(rows, {"law_on": "2026-11-14"}, _args(), 60.0)
    assert "| IC-80 one face (front) | 1 |" in text
    assert "| jurisdiction | IC-80 front | IC-80 back | IC-80 both faces | 45 t on site |" in text
    assert "| Portland | 1 | 0 | 0 | 1 | 0 | 1 | 0 | 0 |" in text
    assert "long face" not in text  # those columns only where a front could not be told
    assert "IC-80 one face (front): lifts: Upper back wall (Upper back wall, 63.1% at 32.0 ft)" in text
    assert "the street in front is # ft wide at most" in text
    assert "less than # ft beyond a wall end" in text
    assert "overhead power lines" in text


def test_grade_is_read_by_default() -> None:
    import scripts.flats_set_access_sample as sample

    src = Path(sample.__file__).read_text(encoding="utf-8")
    assert '"--no-grade", dest="grade", action="store_false"' in src
