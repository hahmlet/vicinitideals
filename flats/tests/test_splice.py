"""Partial re-screen: select a scope, splice it into the last run, audit a full run against it."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from flats.ingest.quadfit import scope_mask
from flats.ingest.splice import MAX_SPLICES, audit, due, report, splice

LOTS = [("W1", "Wood Village", "TC"), ("W2", "Wood Village", "LR"), ("T1", "Troutdale", "R7"), ("G1", "Gresham", "TC")]


def bridge(path: Path, verdicts: dict[str, str], *, s4: str = "s4.parquet", **meta) -> Path:
    """A bridge directory: one row per lot x design, the lots named in ``verdicts``."""
    path.mkdir(parents=True)
    rows = [
        {"TLID": t, "jurisdiction": j, "zone": z, "design": d, "triage": verdicts[t], "if_signed": verdicts[t]}
        for t, j, z in LOTS
        if t in verdicts
        for d in ("pod56x36@2", "pod80x25@2")
    ]
    pd.DataFrame(rows).to_parquet(path / "lots.parquet", index=False)
    base = {"s4": s4, "s5o": "s5o.parquet", "sample": None, "limit": None, "jurisdictions": [], "zones": [], "tlids": []}
    (path / "meta.json").write_text(json.dumps({**base, **meta}), encoding="utf-8")
    return path


ALL_RED = {t: "red" for t, _, _ in LOTS}


def test_a_zone_is_named_with_its_city_because_the_code_repeats() -> None:
    frame = pd.DataFrame(LOTS, columns=["TLID", "jurisdiction", "zone"])

    assert scope_mask(frame) is None
    assert list(frame[scope_mask(frame, zones=["Wood Village:TC"])]["TLID"]) == ["W1"]
    assert list(frame[scope_mask(frame, jurisdictions=["Troutdale"], tlids=["G1"])]["TLID"]) == ["T1", "G1"]
    with pytest.raises(ValueError, match="jurisdiction"):
        scope_mask(frame, zones=["TC"])


def test_a_splice_replaces_only_the_lots_the_partial_run_screened(tmp_path: Path) -> None:
    base = bridge(tmp_path / "full", ALL_RED, finished_at="2026-09-25T00:00:00+00:00")
    part = bridge(tmp_path / "wv", {"W1": "green"}, zones=["Wood Village:TC"], finished_at="2026-09-26T00:00:00+00:00")

    meta = splice(base, part, tmp_path / "out", change="WV TC front 10")

    got = pd.read_parquet(tmp_path / "out" / "lots.parquet")
    assert len(got) == 8
    assert dict(zip(got["TLID"], got["if_signed"])) == {"W1": "green", "W2": "red", "T1": "red", "G1": "red"}
    assert meta["lineage"]["full"]["bridge"] == str(base.resolve())
    assert [s["change"] for s in meta["lineage"]["splices"]] == ["WV TC front 10"]
    # The spliced run is not itself partial: the loader and the next splice see a whole county.
    assert meta["zones"] == [] and meta["lots"] == 4


def test_splices_chain_on_one_full_run(tmp_path: Path) -> None:
    base = bridge(tmp_path / "full", ALL_RED)
    one = splice(base, bridge(tmp_path / "p1", {"W1": "green"}, tlids=["W1"]), tmp_path / "s1", change="one")
    two = splice(tmp_path / "s1", bridge(tmp_path / "p2", {"G1": "yellow"}, tlids=["G1"]), tmp_path / "s2", change="two")

    assert one["lineage"]["full"] == two["lineage"]["full"]
    assert [s["change"] for s in two["lineage"]["splices"]] == ["one", "two"]
    got = pd.read_parquet(tmp_path / "s2" / "lots.parquet")
    assert dict(zip(got["TLID"], got["if_signed"]))["W1"] == "green"


@pytest.mark.parametrize(
    "base_meta, part_meta, why",
    [
        ({}, {}, "no scope"),
        ({"sample": 20000}, {"tlids": ["W1"]}, "sample"),
        ({}, {"tlids": ["W1"], "limit": 10}, "sample"),
        ({"jurisdictions": ["Troutdale"]}, {"tlids": ["W1"]}, "itself partial"),
        ({"s4": "other.parquet"}, {"tlids": ["W1"]}, "s4 differs"),
    ],
)
def test_a_splice_refuses_runs_that_do_not_describe_the_same_county(tmp_path: Path, base_meta, part_meta, why) -> None:
    base = bridge(tmp_path / "full", ALL_RED, **base_meta)
    part = bridge(tmp_path / "p", {"W1": "green"}, **part_meta)

    with pytest.raises(SystemExit, match=why):
        splice(base, part, tmp_path / "out", change="x")


def test_a_full_re_screen_is_due_after_enough_splices_or_enough_days() -> None:
    fresh = "2026-09-25T00:00:00+00:00"
    now = datetime(2026, 9, 30, tzinfo=timezone.utc)

    def meta(n: int, finished: str) -> dict:
        return {"lineage": {"full": {"finished_at": finished}, "splices": [{}] * n}}

    assert due({}, now=now) == []
    assert due(meta(1, fresh), now=now) == []
    assert "partial re-screens" in due(meta(MAX_SPLICES, fresh), now=now)[0]
    assert "days ago" in due(meta(1, "2026-08-01T00:00:00+00:00"), now=now)[0]


def test_the_audit_accepts_a_move_no_change_declared_as_a_known_unknown(tmp_path: Path) -> None:
    # Steph's example: a change "only in Wood Village" also moved a Troutdale lot.
    base = bridge(tmp_path / "full", ALL_RED)
    splice(base, bridge(tmp_path / "wv", {"W1": "green"}, jurisdictions=["Wood Village"]), tmp_path / "s", change="WV")
    full = bridge(tmp_path / "next", {**ALL_RED, "W1": "green", "T1": "yellow"})

    got = audit(tmp_path / "s", full)

    assert got.changes == ("WV",)
    assert sum(got.in_scope.values()) == 0
    assert got.out_of_scope[("if_signed", "red", "yellow")] == 2
    assert {m["TLID"] for m in got.moves} == {"T1"}
    text = report(got)
    assert "known unknowns" in text and "Troutdale R7: 2" in text


def test_the_audit_flags_a_full_run_that_disagrees_with_a_splice_on_its_own_lots(tmp_path: Path) -> None:
    base = bridge(tmp_path / "full", ALL_RED)
    splice(base, bridge(tmp_path / "wv", {"W1": "green"}, tlids=["W1"]), tmp_path / "s", change="WV")
    full = bridge(tmp_path / "next", ALL_RED)

    got = audit(tmp_path / "s", full)

    assert got.in_scope[("triage", "green", "red")] == 2
    assert not got.out_of_scope


def test_the_audit_needs_a_full_run(tmp_path: Path) -> None:
    base = bridge(tmp_path / "full", ALL_RED)
    splice(base, bridge(tmp_path / "wv", {"W1": "green"}, tlids=["W1"]), tmp_path / "s", change="WV")

    with pytest.raises(SystemExit, match="not a full"):
        audit(tmp_path / "s", tmp_path / "wv")
