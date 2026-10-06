"""The bridge's batch: costliest lots first, a memory budget on the giants,
and an answer cache that never changes an answer (FOLLOWUPS 46).

What must hold: ``lots.parquet`` is the same records in the same order
whatever order the lots ran in and whichever came from the cache; a lot is
read from the cache only when its row and everything else its answer is
computed from are unchanged; and the dispatcher never puts more giants in
flight than the budget holds -- nor starves the biggest to the end.
"""

from __future__ import annotations

import io
import math
import os
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from multiprocessing.pool import ThreadPool

from flats.ingest import batch, quadfit

ACRE = batch.SQFT_PER_ACRE


def _row(tlid: str, acres: float, **more) -> dict:
    return {"TLID": tlid, "area_sqft": acres * ACRE, "edges_json": "[]", **more}


# --- the plan --------------------------------------------------------------------


def test_the_plan_deals_the_costliest_lots_first() -> None:
    rows = [_row("a", 0.1), _row("b", 30.0), _row("c", 0.2), _row("d", 5.0)]
    chunks = batch.plan(rows, processes=1, chunk_size=1)
    assert [rows[c[0]]["TLID"] for c in chunks] == ["b", "d", "c", "a"]


def test_a_lot_worth_a_chunk_runs_alone_and_the_small_ones_share() -> None:
    rows = [_row(f"s{i}", 0.1) for i in range(200)] + [_row("giant", 40.0)]
    chunks = batch.plan(rows, processes=4, chunk_size=50)
    assert chunks[0] == [200]
    assert all(len(c) <= 50 for c in chunks)
    assert sorted(i for c in chunks for i in c) == list(range(201))


def test_equal_costs_keep_the_order_they_were_read_in() -> None:
    rows = [_row(t, 1.0) for t in "pqrs"]
    chunks = batch.plan(rows, processes=1, chunk_size=10)
    assert [i for c in chunks for i in c] == [0, 1, 2, 3]


def test_a_lot_without_an_area_still_costs_its_floor() -> None:
    rows = [_row("a", 0.0), {"TLID": "b", "area_sqft": None}, {"TLID": "c", "area_sqft": float("nan")}]
    assert {batch.cost(r) for r in rows} == {batch.COST_FLOOR_SQFT}
    assert batch.extra_gb(rows[1]) == 0.0
    assert batch.plan([], processes=4, chunk_size=10) == []


# --- dispatch --------------------------------------------------------------------


class _Watch:
    """A work function for a thread pool that records what ran beside what."""

    def __init__(self, needs: list[float], seconds: float = 0.02, fail: int | None = None) -> None:
        self.needs = needs
        self.seconds = seconds
        self.fail = fail
        self.lock = threading.Lock()
        self.running: set[int] = set()
        self.started: list[int] = []
        self.most_heavy = 0.0
        self.most_running = 0

    def __call__(self, i: int) -> int:
        with self.lock:
            self.running.add(i)
            self.started.append(i)
            heavy = [self.needs[j] for j in self.running if self.needs[j] >= batch.SMALL_GB]
            if len(heavy) > 1:
                self.most_heavy = max(self.most_heavy, sum(heavy))
            self.most_running = max(self.most_running, len(self.running))
        time.sleep(self.seconds)
        with self.lock:
            self.running.discard(i)
        if i == self.fail:
            raise RuntimeError("worker fell over")
        return i * 10


def _dispatch(needs, *, slots, budget, free_gb=None, watch=None):
    watch = watch or _Watch(needs)
    with ThreadPool(slots) as pool:
        got = dict(
            batch.dispatch(pool, watch, list(range(len(needs))), needs, slots=slots, budget_gb=budget, free_gb=free_gb)
        )
    return got, watch


def test_every_payload_runs_once_and_no_more_than_the_slots_at_once() -> None:
    needs = [0.1] * 30
    got, watch = _dispatch(needs, slots=4, budget=10.0)
    assert got == {i: i * 10 for i in range(30)}
    assert watch.most_running <= 4


def test_giants_in_flight_together_stay_inside_the_budget() -> None:
    needs = [6.0, 5.0, 4.0, 3.0, 2.0, *[0.1] * 12]
    _, watch = _dispatch(needs, slots=5, budget=8.0)
    assert watch.most_heavy <= 8.0


def test_a_giant_above_the_whole_budget_still_runs_alone() -> None:
    needs = [20.0, 3.0, 0.1, 0.1]
    got, watch = _dispatch(needs, slots=3, budget=8.0)
    assert sorted(got) == [0, 1, 2, 3]
    assert watch.most_heavy <= 8.0


def test_a_giant_that_must_wait_holds_back_the_smaller_giants_behind_it() -> None:
    # 3 starts; 7 does not fit beside it and waits; 2 would fit beside 3
    # but must not jump the queue, or 7 is starved to the end of the run.
    needs = [3.0, 7.0, 2.0]
    _, watch = _dispatch(needs, slots=3, budget=8.0)
    assert watch.started == [0, 1, 2]


def test_one_slot_runs_the_giants_first_then_the_small_lots() -> None:
    needs = [5.0, 0.1, 2.0, 0.2]
    _, watch = _dispatch(needs, slots=1, budget=100.0)
    assert watch.started == [0, 2, 1, 3]


def test_a_giant_waits_while_the_machine_lacks_its_memory_but_small_lots_go_on() -> None:
    needs = [2.0, 2.0, *[0.1] * 6]
    _, watch = _dispatch(needs, slots=4, budget=100.0, free_gb=lambda: 4.0)
    assert watch.most_heavy == 0.0
    assert watch.started[-1] == 1  # threads may start in any order; the giant goes last


def test_a_worker_error_is_raised() -> None:
    needs = [0.1] * 5
    with pytest.raises(RuntimeError, match="fell over"):
        _dispatch(needs, slots=2, budget=1.0, watch=_Watch(needs, fail=3))


# --- the cache keys ---------------------------------------------------------------


def test_a_row_digest_reads_values_not_their_order_or_container() -> None:
    a = {"TLID": "x", "lot_wkb": b"\x01\x02", "v": 1.5, "arr": np.array([1, 2]), "n": None}
    b = {"n": None, "arr": [1, 2], "v": 1.5, "lot_wkb": b"\x01\x02", "TLID": "x"}
    assert batch.row_digest(a) == batch.row_digest(b)
    assert batch.row_digest({**a, "v": 1.5000000001}) != batch.row_digest(a)
    assert batch.row_digest({**a, "lot_wkb": b"\x01\x03"}) != batch.row_digest(a)
    assert batch.row_digest({**a, "v": np.float64(1.5)}) == batch.row_digest(a)
    assert batch.row_digest({**a, "v": math.nan}) == batch.row_digest({**a, "v": float("nan")})


def _package(tmp_path: Path) -> Path:
    pkg = tmp_path / "flats"
    (pkg / "config").mkdir(parents=True)
    (pkg / "tests").mkdir()
    (pkg / "screen.py").write_text("X = 1\n", encoding="utf-8")
    (pkg / "config" / "rules.yaml").write_text("a: 1\n", encoding="utf-8")
    (pkg / "tests" / "test_x.py").write_text("", encoding="utf-8")
    return pkg


def test_the_run_key_changes_with_the_code_and_config_but_not_the_tests(tmp_path) -> None:
    pkg = _package(tmp_path)
    key = lambda: batch.run_key(step_deg=1.0, inputs={}, package=pkg)  # noqa: E731
    first = key()
    assert key() == first
    (pkg / "tests" / "test_x.py").write_text("assert True\n", encoding="utf-8")
    assert key() == first
    (pkg / "config" / "rules.yaml").write_text("a: 2\n", encoding="utf-8")
    second = key()
    assert second["code"] != first["code"]
    (pkg / "screen.py").write_text("X = 2\n", encoding="utf-8")
    assert key()["code"] != second["code"]
    assert batch.run_key(step_deg=0.5, inputs={}, package=pkg) != key()


def test_the_run_key_changes_with_any_file_in_an_input(tmp_path) -> None:
    pkg = _package(tmp_path)
    snap = tmp_path / "snapshot"
    snap.mkdir()
    (snap / "streets.geojson").write_text("{}", encoding="utf-8")
    key = lambda: batch.run_key(step_deg=1.0, inputs={"sources": snap}, package=pkg)  # noqa: E731
    first = key()
    assert key() == first
    (snap / "curbs.geojson").write_text("{}", encoding="utf-8")
    second = key()
    assert second != first
    (snap / "streets.geojson").write_text('{"a": 1}', encoding="utf-8")
    assert key() != second
    st = (snap / "curbs.geojson").stat()
    third = key()
    os.utime(snap / "curbs.geojson", ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
    assert key() != third


# --- one run, cached and not --------------------------------------------------------


@pytest.fixture
def fake_screen(monkeypatch):
    """The worker's screen replaced by one whose records depend on the row
    alone, with the shapes the real one writes: two designs, a number that
    is sometimes None, an int, a string."""
    calls: list[str] = []

    def work_chunk(rows):
        out = []
        for row in rows:
            calls.append(row["TLID"])
            acres = row["area_sqft"] / ACRE
            for design in ("pod56", "pod80"):
                out.append(
                    {
                        "TLID": row["TLID"],
                        "design": design,
                        "fit_slack_ft": None if acres < 0.15 else round(acres * 3.5, 6),
                        "stalls_seated": int(acres * 10) if acres >= 0.2 else None,
                        "colour": "green" if acres > 0.3 else "red",
                        "fits": acres > 0.12,
                    }
                )
        return out

    monkeypatch.setattr(quadfit, "_work_chunk", work_chunk)
    return calls


def _rows() -> list[dict]:
    acres = [0.11, 0.5, 12.0, 0.14, 0.2, 0.31, 3.0, 0.12, 0.25, 0.18, 7.5, 0.13]
    return [_row(f"T{i:02d}", a, zone="R5") for i, a in enumerate(acres)]


def _screen(rows, tmp_path: Path, name: str, cache=None, chunk_size=2):
    parts = tmp_path / name / "parts"
    parts.mkdir(parents=True)
    frame, timings, done = batch.screen_rows(
        rows, parts, processes=1, chunk_size=chunk_size, init=lambda *a: None, initargs=(),
        cache=cache, log=lambda *a: None,
    )
    return frame, timings, done


def _cache(tmp_path: Path) -> batch.AnswerCache:
    return batch.AnswerCache(tmp_path / "cache", {"format": 1, "code": "abc", "step_deg": 1.0})


def _file_order(rows) -> pd.DataFrame:
    """What the bridge wrote before the batch: one chunk, lots in file order."""
    return pd.DataFrame.from_records(quadfit._work_chunk(rows))


def _written(frame: pd.DataFrame) -> pd.DataFrame:
    """The frame as ``lots.parquet`` holds it and every reader reads it.

    In memory a missing number is None in one chunk's frame and NaN in
    another's, as it always was; the file holds a null either way.
    """
    buf = io.BytesIO()
    frame.to_parquet(buf, index=False)
    buf.seek(0)
    return pd.read_parquet(buf)


def _same(a: pd.DataFrame, b: pd.DataFrame) -> None:
    pd.testing.assert_frame_equal(_written(a), _written(b))


def test_the_records_come_out_in_file_order_whatever_order_they_ran(tmp_path, fake_screen) -> None:
    rows = _rows()
    want = _file_order(rows)
    fake_screen.clear()
    frame, timings, done = _screen(rows, tmp_path, "run")
    assert fake_screen[:2] == ["T02", "T10"]  # the 12- and 7.5-acre lots ran first
    assert list(frame["TLID"]) == [r["TLID"] for r in rows for _ in range(2)]
    _same(frame, want)
    assert len(timings) == len(rows) and set(timings["TLID"]) == {r["TLID"] for r in rows}
    assert done.computed_lots == len(rows) and done.cached_lots == 0


def test_a_cached_run_is_the_uncached_run(tmp_path, fake_screen) -> None:
    rows = _rows()
    plain, _, _ = _screen(rows, tmp_path, "plain")
    cache = _cache(tmp_path)
    first, _, _ = _screen(rows, tmp_path, "first", cache=cache)
    fake_screen.clear()
    again, timings, done = _screen(rows, tmp_path, "again", cache=cache)
    assert fake_screen == [] and done.cached_lots == len(rows) and len(timings) == 0
    _same(first, plain)
    _same(again, plain)


def test_part_from_the_cache_and_part_screened_is_the_uncached_run(tmp_path, fake_screen) -> None:
    rows = _rows()
    plain, _, _ = _screen(rows, tmp_path, "plain", chunk_size=5)
    cache = _cache(tmp_path)
    _screen(rows[::3], tmp_path, "some", cache=cache)
    fake_screen.clear()
    mixed, _, done = _screen(rows, tmp_path, "mixed", cache=cache, chunk_size=3)
    assert done.cached_lots == len(rows[::3])
    assert sorted(fake_screen) == sorted(r["TLID"] for i, r in enumerate(rows) if i % 3)
    _same(mixed, plain)


def test_a_changed_row_is_screened_again(tmp_path, fake_screen) -> None:
    rows = _rows()
    cache = _cache(tmp_path)
    _screen(rows, tmp_path, "first", cache=cache)
    moved = [dict(r) for r in rows]
    moved[4]["zone"] = "R2.5"
    fake_screen.clear()
    _, _, done = _screen(moved, tmp_path, "again", cache=cache)
    assert fake_screen == ["T04"] and done.cached_lots == len(rows) - 1


def test_a_cache_under_another_run_key_holds_nothing(tmp_path, fake_screen) -> None:
    rows = _rows()
    _screen(rows, tmp_path, "first", cache=_cache(tmp_path))
    other = batch.AnswerCache(tmp_path / "cache", {"format": 1, "code": "abd", "step_deg": 1.0})
    fake_screen.clear()
    _, _, done = _screen(rows, tmp_path, "again", cache=other)
    assert done.cached_lots == 0 and len(fake_screen) == len(rows)


def test_a_lot_read_twice_comes_out_twice_cached_or_not(tmp_path, fake_screen) -> None:
    rows = _rows()
    twice = [*rows, dict(rows[1])]
    plain, _, _ = _screen(twice, tmp_path, "plain")
    cache = _cache(tmp_path)
    first, _, _ = _screen(twice, tmp_path, "first", cache=cache)
    again, _, _ = _screen(twice, tmp_path, "again", cache=cache)
    assert (plain["TLID"] == "T01").sum() == 4
    _same(first, plain)
    _same(again, plain)


def test_a_run_writes_each_chunk_to_the_cache_as_it_finishes(tmp_path, fake_screen) -> None:
    rows = _rows()
    cache = _cache(tmp_path)
    _, _, done = _screen(rows, tmp_path, "run", cache=cache)
    assert len(list(cache.where.glob("*.parquet"))) == done.chunks
    assert not list(cache.where.glob(".*.tmp"))
    assert (cache.where / "key.json").exists()


def test_prune_drops_the_caches_no_run_has_used(tmp_path) -> None:
    root = tmp_path / "cache"
    old = batch.AnswerCache(root, {"code": "old"}).where
    new = batch.AnswerCache(root, {"code": "new"}).where
    stale = time.time() - 30 * 86_400
    os.utime(old, (stale, stale))
    assert batch.prune(root, keep_days=14) == [old]
    assert new.exists() and not old.exists()
