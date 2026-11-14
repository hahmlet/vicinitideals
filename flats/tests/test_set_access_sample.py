"""The set access sample script's lot picking and summary (FOLLOWUPS 145)."""

from __future__ import annotations

import argparse
import json

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


def test_summary_counts_cranes_and_reasons() -> None:
    rows = [
        {"jurisdiction": "Portland", "crane": "45 t", "setup": "site", "binding": "2 Floor cassettes"},
        {"jurisdiction": "Portland", "crane": "neither", "setup": None,
         "why": "28 t site: the street in front is 24 ft wide at most; the 28 t pad needs 26 ft"},
        {"jurisdiction": "Gresham", "crane": "unmeasured", "setup": None, "why": "x"},
    ]
    text = _summary(rows, {"law_on": "2026-11-14"}, _args(), 60.0)
    assert "| 45 t / site | 1 |" in text
    assert "| Portland | 0 | 1 | 1 | 0 | 0 |" in text
    assert "the street in front is # ft wide at most" in text
    assert "overhead power lines" in text
