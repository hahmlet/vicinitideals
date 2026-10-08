"""The bridge's batch: costliest lots first, memory read live, a dead worker
costing one lot, and an answer cache that never changes an answer
(FOLLOWUPS 46).

What must hold: ``lots.parquet`` is the same records in the same order
whatever order the lots ran in, on whichever worker, and whichever came from
the cache; a lot is read from the cache only when its row and everything
else its answer is computed from are unchanged; a chunk starts only while
the machine's free memory covers what it and the chunks in flight may still
grow into -- without starving the biggest to the end; and a worker killed
mid-lot loses that lot alone, which then runs again with nothing heavy
beside it.
"""

from __future__ import annotations

import io
import math
import os
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import shapely

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
    assert {batch.cost(r) for r in rows} == {batch.SECONDS_FLOOR}
    assert {batch.need_gb(r) for r in rows} == {batch.NEED_BASE_GB}
    assert batch.plan([], processes=4, chunk_size=10) == []


def _book(tmp_path: Path, *timings: tuple[str, float, float, float | None]) -> batch.LotBook:
    book = batch.LotBook.open(tmp_path / "book.parquet")
    book.record({"TLID": t, "acres": a, "seconds": s, "peak_mb": p} for t, a, s, p in timings)
    return book


def test_the_book_deals_the_lots_by_what_they_took_last_time(tmp_path) -> None:
    # a small lot that took five minutes goes before a giant that took two
    # seconds; a lot the book lacks is costed from its area between them
    rows = [_row("giant", 30.0), _row("slow", 0.1), _row("new", 5.0)]
    book = _book(tmp_path, ("giant", 30.0, 2.0, 900.0), ("slow", 0.1, 300.0, 4000.0))
    chunks = batch.plan(rows, processes=1, chunk_size=1, book=book)
    assert [rows[c[0]]["TLID"] for c in chunks] == ["slow", "new", "giant"]
    assert batch.need_gb(rows[1], book) == pytest.approx(4000.0 / 1024)
    assert batch.need_gb(rows[2], book) == batch.need_gb(rows[2])


def test_a_lot_whose_area_moved_is_not_read_from_the_book(tmp_path) -> None:
    book = _book(tmp_path, ("a", 1.0, 50.0, 3000.0))
    assert book.seconds(_row("a", 1.01)) == 50.0
    assert book.seconds(_row("a", 1.2)) is None and batch.cost(_row("a", 1.2), book) == batch.cost(_row("a", 1.2))
    assert book.peak_gb(_row("a", 1.2)) is None


def test_the_book_keeps_the_newest_cost_of_each_lot_across_runs(tmp_path) -> None:
    book = _book(tmp_path, ("a", 1.0, 50.0, 3000.0), ("b", 0.2, 1.0, None))
    book.save()
    again = batch.LotBook.open(tmp_path / "book.parquet")
    assert again.seconds(_row("a", 1.0)) == 50.0 and again.peak_gb(_row("b", 0.2)) is None
    again.record([{"TLID": "a", "acres": 1.0, "seconds": 20.0, "peak_mb": 1000.0}])
    again.save()
    last = batch.LotBook.open(tmp_path / "book.parquet")
    assert last.seconds(_row("a", 1.0)) == 20.0 and last.seconds(_row("b", 0.2)) == 1.0
    assert not list(tmp_path.glob(".*.tmp"))


# --- which chunk starts next -------------------------------------------------------


def _chunk(n: int, need: float, solo: bool = False) -> batch.Chunk:
    return batch.Chunk(n, [(n, {})], need, solo)


def _simulate(needs, *, slots, total, solo=(), ticks=None, idle=0.5, grows=1):
    """Run chunks through :func:`batch.choose` on a machine of ``total`` GB.

    An idle worker holds ``idle`` GB; a busy one holds ``idle`` until
    ``grows`` ticks after its chunk started, then the chunk's whole need --
    so a chunk is admitted before it has grown, the case the growth held
    for chunks in flight is for. A chunk runs ``ticks[i]`` ticks (2).
    Returns the start order, the most workers busy at once, and the most
    memory the busy chunks' needs and the idle workers came to while more
    than one chunk ran.
    """
    ticks = ticks or [2] * len(needs)
    waiting = [_chunk(i, need, i in solo) for i, need in enumerate(needs)]
    busy: dict[int, tuple[batch.Chunk, int]] = {}
    started: list[int] = []
    most_busy, most_memory, t = 0, 0.0, 0
    while waiting or busy:
        for slot, (c, start) in list(busy.items()):
            if t >= start + ticks[c.n]:
                del busy[slot]
        held = {slot: (c.need if t >= start + grows else idle) for slot, (c, start) in busy.items()}
        while waiting and len(busy) < slots:
            free = total - sum(held.values()) - idle * (slots - len(busy))
            running = [batch.InFlight(c.need, held[s], c.heavy, c.solo) for s, (c, _) in busy.items()]
            k = batch.choose(waiting, running, free_gb=free, idle_gb=idle)
            if k is None:
                break
            c = waiting.pop(k)
            slot = next(s for s in range(slots) if s not in busy)
            busy[slot] = (c, t)
            held[slot] = idle
            started.append(c.n)
        most_busy = max(most_busy, len(busy))
        if len(busy) > 1:
            most_memory = max(most_memory, sum(c.need for c, _ in busy.values()) + idle * (slots - len(busy)))
        t += 1
    return started, most_busy, most_memory


def test_every_chunk_starts_once_and_no_more_than_the_workers_at_once() -> None:
    started, most_busy, _ = _simulate([0.8] * 30, slots=4, total=64.0)
    assert sorted(started) == list(range(30)) and most_busy == 4


def test_chunks_in_flight_stay_inside_the_machine_even_before_they_grow() -> None:
    needs = [6.0, 5.0, 4.0, 3.0, 2.5, *[0.9] * 12]
    for grows in (0, 1, 3):
        _, _, most_memory = _simulate(needs, slots=5, total=14.0, grows=grows)
        assert most_memory <= 14.0 - batch.RESERVE_GB


def test_a_chunk_bigger_than_the_machine_still_runs_alone() -> None:
    started, _, most_memory = _simulate([20.0, 3.0, 0.8, 0.8], slots=3, total=12.0)
    assert sorted(started) == [0, 1, 2, 3] and most_memory <= 12.0 - batch.RESERVE_GB


def test_a_heavy_chunk_that_must_wait_holds_back_the_heavy_chunks_behind_it() -> None:
    # 0 starts; 1 does not fit beside it and waits; 2 would fit beside 0 but
    # must not jump the queue, or 1 is starved to the end of the run
    started, _, _ = _simulate([3.0, 7.0, 2.5], slots=3, total=12.0)
    assert started == [0, 1, 2]


def test_light_chunks_pass_a_heavy_chunk_that_waits_for_memory() -> None:
    started, _, _ = _simulate([6.0, 6.0, 0.8, 0.8, 0.8], slots=3, total=12.0, ticks=[4, 4, 1, 1, 1])
    assert started.index(1) > started.index(2)


def test_a_solo_chunk_runs_with_no_other_heavy_chunk_beside_it() -> None:
    needs = [2.5, 2.5, 3.0, 2.5, 0.8, 0.8, 0.8]
    ticks = [2, 2, 3, 2, 1, 1, 1]
    started, _, _ = _simulate(needs, slots=4, total=64.0, solo={2}, ticks=ticks)
    # 0 and 1 start, 2 waits for them and holds back 3; light ones go on
    assert started.index(2) > started.index(1) and started.index(3) > started.index(2)
    waiting = [_chunk(3, 2.5), _chunk(4, 0.8)]
    assert batch.choose(waiting, [batch.InFlight(3.0, 3.0, True, True)], free_gb=60.0) == 1


def test_a_chunks_hungriest_lot_runs_first_and_equal_needs_keep_their_order(tmp_path) -> None:
    rows = [_row("a", 0.1), _row("b", 5.0), _row("c", 0.1), _row("d", 1.0)]
    chunk = batch.make_chunk(7, [0, 1, 2, 3], rows)
    assert [r["TLID"] for _, r in chunk.items] == ["b", "d", "a", "c"]
    assert chunk.need == chunk.needs[0] == batch.need_gb(rows[1])
    assert chunk.needs == sorted(chunk.needs, reverse=True)
    # a small lot that once reached 3 GB goes before a 5-acre lot the book lacks
    book = _book(tmp_path, ("a", 0.1, 1.0, 3072.0))
    assert [r["TLID"] for _, r in batch.make_chunk(0, [0, 1], rows, book).items] == ["a", "b"]


def test_a_chunk_in_flight_is_held_only_to_the_lots_it_has_left() -> None:
    chunk = batch.Chunk(0, [(i, {}) for i in range(3)], 6.0, needs=[6.0, 1.0, 0.9])
    assert [chunk.left(k).need for k in range(4)] == [6.0, 1.0, 0.9, 0.0]
    assert chunk.left(0).heavy and not chunk.left(1).heavy
    waiting = [_chunk(1, 6.0)]
    # its worker holds 1 GB: while its 6 GB lot runs, 5 GB more of the 9 free is spoken for
    assert batch.choose(waiting, [replace(chunk.left(0), rss=1.0)], free_gb=9.0, idle_gb=0.5) is None
    assert batch.choose(waiting, [replace(chunk.left(1), rss=1.0)], free_gb=9.0, idle_gb=0.5) == 0
    solo = batch.Chunk(0, [(0, {})], 4.0, solo=True, needs=[4.0])
    assert solo.left(0).solo and solo.left(0).heavy


def test_memory_a_chunk_in_flight_has_yet_to_reach_is_held_for_it() -> None:
    running = [batch.InFlight(need=10.0, rss=1.0, heavy=True)]
    # free 20, less the 9 GB the running chunk may still take, less the reserve: 8 GB of room
    assert batch.choose([_chunk(0, 8.5)], running, free_gb=20.0, idle_gb=0.5) == 0
    assert batch.choose([_chunk(0, 9.0)], running, free_gb=20.0, idle_gb=0.5) is None


def test_one_worker_takes_the_chunks_in_their_order() -> None:
    started, _, _ = _simulate([5.0, 0.8, 2.5, 0.9], slots=1, total=64.0)
    assert started == [0, 1, 2, 3]


def test_unknown_free_memory_leaves_only_the_workers_as_the_limit() -> None:
    running = [batch.InFlight(50.0, 1.0, True)]
    assert batch.choose([_chunk(0, 40.0)], running, free_gb=None) == 0
    assert batch.choose([], running, free_gb=None) is None


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


def _fake_records(row) -> list[dict]:
    """A lot's records from the fake screen: they depend on the row alone,
    with the shapes the real one writes -- two designs, a number that is
    sometimes None, an int, a string."""
    acres = row["area_sqft"] / ACRE
    return [
        {
            "TLID": row["TLID"],
            "design": design,
            "fit_slack_ft": None if acres < 0.15 else round(acres * 3.5, 6),
            "stalls_seated": int(acres * 10) if acres >= 0.2 else None,
            "colour": "green" if acres > 0.3 else "red",
            "fits": acres > 0.12,
        }
        for design in ("pod56", "pod80")
    ]


@pytest.fixture
def fake_screen(monkeypatch):
    """The worker's screen replaced by :func:`_fake_records`; returns the
    TLIDs it screened, in order."""
    calls: list[str] = []

    def work_chunk(rows):
        out = []
        for row in rows:
            calls.append(row["TLID"])
            out.extend(_fake_records(row))
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




def test_the_book_beside_the_cache_outlives_a_change_of_code(tmp_path, fake_screen) -> None:
    rows = _rows()
    cache = _cache(tmp_path)
    _, _, first = _screen(rows, tmp_path, "first", cache=cache)
    assert first.booked_lots == 0
    book = batch.LotBook.open(tmp_path / "cache" / "book.parquet")
    assert all(book.holds(r) for r in rows)
    other = batch.AnswerCache(tmp_path / "cache", {"format": 1, "code": "abd", "step_deg": 1.0})
    _, _, again = _screen(rows, tmp_path, "again", cache=other)
    assert again.cached_lots == 0 and again.booked_lots == len(rows)
    assert again.meta()["booked_lots"] == len(rows) and again.meta()["worker_deaths"] == []
    stale = time.time() - 30 * 86_400
    os.utime(cache.where, (stale, stale))
    batch.prune(tmp_path / "cache", keep_days=14)
    assert (tmp_path / "cache" / "book.parquet").exists()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="a process's peak is read from /proc")
def test_a_lots_peak_is_its_own_not_the_worst_its_worker_saw(tmp_path, monkeypatch) -> None:
    if not batch._reset_peak():
        pytest.skip("this kernel will not reset a process's peak")

    def work_chunk(rows):
        if rows[0]["TLID"] == "big":
            block = b"\x01" * (300 * 2**20)
            assert block[-1] == 1
            del block
        return _fake_records(rows[0])

    monkeypatch.setattr(quadfit, "_work_chunk", work_chunk)
    _, timings, _ = _screen([_row("small", 0.1), _row("big", 5.0)], tmp_path, "run", chunk_size=1)
    peak = dict(zip(timings["TLID"], timings["peak_mb"]))
    assert list(timings["TLID"]) == ["big", "small"]
    assert peak["big"] >= peak["small"] + 200


# --- a worker killed mid-run --------------------------------------------------------


def _dying_init(where: str, deaths: int, tlid: str, error: str = "") -> None:
    """Worker setup in a real process: the fake screen, noting each lot it
    starts in ``where/screened``, except that the worker screening ``tlid``
    dies outright -- as the kernel's OOM killer ends one -- the first
    ``deaths`` times (counted in ``where/died``), or raises ``error``."""

    def work_chunk(rows):
        out = []
        for row in rows:
            fd = os.open(os.path.join(where, "screened"), os.O_WRONLY | os.O_CREAT | os.O_APPEND)
            os.write(fd, f"{row['TLID']}\n".encode("ascii"))
            os.close(fd)
            if row["TLID"] == tlid:
                if error:
                    raise ValueError(error)
                path = Path(where) / "died"
                died = int(path.read_text()) if path.exists() else 0
                if died < deaths:
                    path.write_text(str(died + 1))
                    os._exit(9)
            out.extend(_fake_records(row))
        return out

    quadfit._work_chunk = work_chunk


def _screen_in_processes(rows, where: Path, deaths: int, tlid: str = "T05", cache=None, error: str = ""):
    parts = where / "parts"
    parts.mkdir(parents=True)
    said: list[str] = []
    got = batch.screen_rows(
        rows, parts, processes=2, chunk_size=2, init=_dying_init, initargs=(str(where), deaths, tlid, error),
        cache=cache, log=said.append,
    )
    return got, said


def _screened(where: Path) -> list[str]:
    return (where / "screened").read_text(encoding="ascii").split()


def _all_records(rows) -> pd.DataFrame:
    return pd.DataFrame.from_records([r for row in rows for r in _fake_records(row)])


@pytest.mark.timeout(180)
def test_a_worker_killed_mid_lot_costs_that_lot_alone(tmp_path) -> None:
    # T05 is the second lot of its chunk, after T01: T01 is kept, not
    # screened again, and T05 runs again on a fresh worker
    rows = _rows()
    (frame, timings, done), said = _screen_in_processes(rows, tmp_path, deaths=1)
    assert (tmp_path / "died").read_text() == "1"
    screened = _screened(tmp_path)
    assert screened.count("T05") == 2
    assert all(screened.count(r["TLID"]) == 1 for r in rows if r["TLID"] != "T05")
    assert done.deaths == ["T05"] and done.meta()["worker_deaths"] == ["T05"]
    assert any("a worker died" in line and "T05" in line for line in said)
    _same(frame, _all_records(rows))
    assert sorted(timings["TLID"]) == sorted(r["TLID"] for r in rows)


@pytest.mark.timeout(180)
def test_a_lot_that_kills_its_worker_again_stops_the_run_and_a_relaunch_resumes(tmp_path) -> None:
    # The smallest lot runs last, so the chunks before it are kept when it
    # stops the run: there is always something to resume from.
    rows = _rows()
    cache = _cache(tmp_path)
    with pytest.raises(RuntimeError, match="T00 at 0.1 acres killed its worker again.*re-launch"):
        _screen_in_processes(rows, tmp_path / "first", deaths=2, tlid="T00", cache=cache)
    (frame, _, done), _ = _screen_in_processes(rows, tmp_path / "again", deaths=0, tlid="T00", cache=cache)
    assert done.cached_lots >= 1 and done.computed_lots >= 1
    _same(frame, _all_records(rows))


@pytest.mark.timeout(180)
def test_a_lot_that_fails_stops_the_run_naming_it(tmp_path) -> None:
    with pytest.raises(RuntimeError, match=r"lot T06 at 3\.0 acres failed in a worker(.|\n)*bad geometry"):
        _screen_in_processes(_rows(), tmp_path, deaths=0, tlid="T06", error="bad geometry")


def _note_oom_score(where: str) -> None:
    Path(where, f"oom_score_adj.{os.getpid()}").write_text(Path("/proc/self/oom_score_adj").read_text())
    _dying_init(where, 0, "")


@pytest.mark.timeout(180)
@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="oom_score_adj is Linux's")
def test_workers_offer_themselves_to_the_oom_killer_before_the_parent(tmp_path) -> None:
    parts = tmp_path / "parts"
    parts.mkdir()
    batch.screen_rows(
        _rows(), parts, processes=2, chunk_size=2, init=_note_oom_score, initargs=(str(tmp_path),),
        log=lambda *a: None,
    )
    noted = [p.read_text().strip() for p in tmp_path.glob("oom_score_adj.*")]
    assert noted and set(noted) == {"1000"}
    assert Path("/proc/self/oom_score_adj").read_text().strip() != "1000"


# --- the command as LXC 137 runs it --------------------------------------------------


@pytest.mark.timeout(300)
def test_the_command_screens_in_workers_set_up_by_the_module_that_screens(tmp_path) -> None:
    # `python -m flats.ingest.quadfit` runs the file as __main__, a second
    # copy of the module beside the flats.ingest.quadfit the workers screen
    # with. A run that set up __main__'s workers answered every lot with
    # KeyError 'rules' (the 2026-10-07 proof on 137); a test calling run()
    # in-process imports one copy only and never sees it.
    from flats.tests.dem import plane, write_dem
    from flats.tests.test_quadfit_bridge import X0, Y0, _stage_files, row

    s4, s5o = _stage_files(tmp_path, [row(), row(TLID="1S2E20AA  -15200")])
    pd.DataFrame(
        {"TLID": ["1S2E20AA  -15100", "1S2E20AA  -15200"], "triage": ["green", "red"],
         "binding_constraint": ["", "pod_no_fit"], "policy_exclusion": ["", ""]}
    ).to_csv(tmp_path / "lots_results.csv", index=False)
    pd.DataFrame(
        {"name": ["SE TEST ST"], "type": ["1500"], "ftype": ["ST"], "alley": [False],
         "wkb": [shapely.to_wkb(shapely.LineString([(X0 - 100, Y0 - 20), (X0 + 150, Y0 - 20)]))]}
    ).to_parquet(tmp_path / "s1_streets.parquet")
    write_dem(tmp_path / "raw" / "dem" / "flat.tif", (X0 - 50, Y0 - 50, X0 + 200, Y0 + 200), plane(1.0))
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    for key in ("curbs_portland", "pave_width_portland", "road_width_multnomah", "street_width_wilsonville",
                "osm_land_use", "rlis_orca"):
        (snapshot / f"{key}.geojson").write_text('{"type": "FeatureCollection", "features": []}', encoding="utf-8")
    out = tmp_path / "bridge"
    got = subprocess.run(
        [sys.executable, "-m", "flats.ingest.quadfit", "--s4", str(s4), "--s5o", str(s5o),
         "--results", str(tmp_path / "lots_results.csv"), "--out", str(out), "--processes", "2",
         "--chunk-size", "1", "--step-deg", "30", "--dem", str(tmp_path / "raw"), "--curbs", str(snapshot),
         "--institutional", str(snapshot), "--cache", str(tmp_path / "cache")],
        cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert got.returncode == 0, got.stderr[-3000:]
    frame = pd.read_parquet(out / "lots.parquet")
    assert set(frame["TLID"]) == {"1S2E20AA  -15100", "1S2E20AA  -15200"}
