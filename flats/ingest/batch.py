"""How a bridge run spends 137's cores: costliest lots first, answers kept.

A bound runs the bridge twice over the same lots -- the code before a
change, then after it -- and 137 runs one heavy job at a time
(docs/ops/parallel-agents.md rule 5). Measured 2026-10-06 (FOLLOWUPS 46),
two things made each run cost more than its lots:

- **The BEFORE was recomputed on every retry.** A lane iterating on a fix
  re-ran the same base commit over the same lots each time (street-class:
  four times in a day), although neither had moved.
- **The lots were dealt in file order.** A 37-acre right-of-way polygon in
  the last chunk ran alone for 21 minutes after 96% of the lots were done,
  fifteen of sixteen threads idle and the next lane waiting on the lock
  (rank-colour bound A: a third of the run).

:func:`plan` deals the costliest lots first -- area is the cost -- and a lot
worth a chunk on its own runs on its own, so the giants run beside the
small lots instead of after them. Started together they would also be in
memory together, and two runs' worth of giants OOM-killed 137 (2026-10-03),
so :func:`dispatch` admits a chunk only while the memory its lots are
estimated to need fits a budget (:func:`extra_gb`); chunks of small lots
always start, so no core waits on a giant. Each worker hands its freed heap
back after a big lot (:func:`_trim`), or the high-water of its largest lot
would stay resident for the rest of the run.

:class:`AnswerCache` keeps every lot's records under a key that changes
when anything the answer is computed from changes: the lot's own row as
the worker receives it, every file under the ``flats`` package but its
tests (the code, ``flats/config`` and the provenance documents the corpus
loads -- the screen reads nothing else in the repository, audited
2026-10-06), the interpreter and installed packages, the sweep step, and
the name, size and modification time of every file in each input
directory a worker reads (corridor maps, street centrelines, curbs and
widths, elevation tiles). A key never names a stale answer; at worst it
misses. A run writes each computed chunk to the cache as it finishes, so a
run that dies resumes from its last chunk.

None of it moves an answer: ``lots.parquet`` holds the same records in the
same order -- the order of the lots as read -- whatever order they ran in
and whichever came from the cache. ``timings.parquet`` beside it says what
each lot cost (seconds, the worker's memory after it), for tuning
:data:`GB_PER_ACRE` against what 137 actually spends.

A worker the kernel kills for memory must end the run, not hang it. A
``multiprocessing.Pool`` quietly starts a replacement and the dead
worker's chunk never reports back, so the run waits forever while it
holds the lock (rank-colour bound3, 2026-10-06: hung 2 h 20 min at
chunk 548 before anyone looked). The batch runs on a
``ProcessPoolExecutor`` instead, which breaks when a worker dies. The
unfinished chunks then run once more in a fresh pool with the giants one
at a time; if a worker dies again, the run stops with an error naming
the biggest unfinished lot. Finished chunks are kept either way: with
``--cache`` a re-launch resumes from them.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import queue
import sys
import time
import uuid
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SQFT_PER_ACRE = 43_560.0

#: A lot's fixed cost in area terms (loading, the sweep's setup), so a
#: chunk of tiny lots is not planned as free.
COST_FLOOR_SQFT = 2_000.0

#: Chunks per worker the costs are cut to: the finer, the shorter the tail
#: a run ends on (its last chunks are its smallest lots).
CHUNKS_PER_WORKER = 8

#: Memory a lot needs on top of an idle worker, per acre. From one reading
#: (2026-10-06, rank-colour bound A): the 37.5-acre ``2S125BD ROW`` held
#: 9 GB against ~1 GB for a worker between small lots -- a right-of-way
#: strip, whose grid is its long bounding box, so a compact lot of that
#: area likely needs less. ``timings.parquet`` is how to replace it with
#: a fit.
GB_PER_ACRE = 0.2

#: A chunk whose largest lot needs less than this starts whatever the
#: budget holds: the giants share the budget, the small lots keep every
#: other core busy.
SMALL_GB = 1.0

#: Of the machine's memory, the share giants in flight may claim between
#: them. The rest is the workers' own (~1 GB each) and the parent's.
BUDGET_SHARE = 0.6

#: Memory left free when a giant starts beside others: a giant starts only
#: while the machine has its estimate and this much more free.
RESERVE_GB = 3.0

#: A lot this big hands its freed heap back to the system after it runs.
TRIM_ACRES = 1.0

#: Bumped when the cache's layout or the key's recipe changes.
CACHE_FORMAT = 1


# --- cost and the plan ---------------------------------------------------------


def _area(row: Mapping[str, Any]) -> float:
    try:
        area = float(row.get("area_sqft") or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return area if math.isfinite(area) and area > 0 else 0.0


def cost(row: Mapping[str, Any]) -> float:
    """What a lot costs to screen, in square feet: its area and a floor."""
    return COST_FLOOR_SQFT + _area(row)


def extra_gb(row: Mapping[str, Any]) -> float:
    """Memory a lot is estimated to need above an idle worker's."""
    return GB_PER_ACRE * _area(row) / SQFT_PER_ACRE


def plan(rows: Sequence[Mapping[str, Any]], *, processes: int, chunk_size: int) -> list[list[int]]:
    """The rows' indices dealt into chunks, the costliest first.

    Lots are taken most costly first and a chunk closes at ``chunk_size``
    lots or at its share of the total cost (``CHUNKS_PER_WORKER`` per
    worker), whichever comes first -- so a lot worth a share alone is a
    chunk alone, and the run ends on chunks of its smallest lots. Equal
    costs keep the order they were read in.
    """
    if not rows:
        return []
    costs = [cost(r) for r in rows]
    order = sorted(range(len(rows)), key=lambda i: (-costs[i], i))
    share = sum(costs) / (max(processes, 1) * CHUNKS_PER_WORKER)
    size = max(chunk_size, 1)
    chunks: list[list[int]] = []
    current: list[int] = []
    spent = 0.0
    for i in order:
        current.append(i)
        spent += costs[i]
        if len(current) >= size or spent >= share:
            chunks.append(current)
            current, spent = [], 0.0
    if current:
        chunks.append(current)
    return chunks


def memory_gb() -> float | None:
    """The memory this machine (or its container's limit) holds, in GB."""
    try:
        limit = Path("/sys/fs/cgroup/memory.max").read_text(encoding="utf-8").strip()
        if limit.isdigit():
            return int(limit) / 2**30
    except OSError:
        pass
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) / 2**20
    except (OSError, ValueError, IndexError):
        pass
    return None


# --- dispatch ------------------------------------------------------------------


def available_gb() -> float | None:
    """Memory free for new work right now (``MemAvailable``), in GB."""
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / 2**20
    except (OSError, ValueError, IndexError):
        pass
    return None


def dispatch(
    pool: Any,
    work: Callable[[Any], Any],
    payloads: Sequence[Any],
    needs_gb: Sequence[float],
    *,
    slots: int,
    budget_gb: float,
    free_gb: Callable[[], float | None] | None = None,
    reserve_gb: float = RESERVE_GB,
) -> Iterator[tuple[int, Any]]:
    """Run ``work`` over ``payloads`` on ``pool``; yield ``(index, result)``
    as each finishes.

    At most ``slots`` are in flight -- one per worker, so nothing queues
    behind a giant. Heavy payloads (a need of :data:`SMALL_GB` or more)
    start in ``payloads`` order, each once the heavy ones in flight leave
    room for it in ``budget_gb`` (or none is in flight, so a giant above
    the whole budget still runs) and ``free_gb()`` -- the memory the
    machine has free -- covers its need and ``reserve_gb`` (or nothing at
    all is in flight). A heavy one that must wait holds back the heavy ones
    behind it, so the biggest is not starved to the end of the run, while
    the small ones fill every free slot. ``pool`` is a
    :class:`concurrent.futures.Executor`; a worker's error -- a broken
    pool among them -- is raised here.
    """
    done: queue.Queue[tuple[int, Any, BaseException | None]] = queue.Queue()
    waiting = list(range(len(payloads)))
    running: dict[int, float] = {}

    def admit_heavy(need: float) -> bool:
        heavy = sum(g for g in running.values() if g >= SMALL_GB)
        if heavy and heavy + need > budget_gb:
            return False
        free = free_gb() if free_gb is not None and running else None
        return free is None or free - need >= reserve_gb

    def choose() -> int | None:
        heavy = next((i for i in waiting if needs_gb[i] >= SMALL_GB), None)
        if heavy is not None and admit_heavy(needs_gb[heavy]):
            return heavy
        return next((i for i in waiting if needs_gb[i] < SMALL_GB), None)

    def finished(future: Any, i: int) -> None:
        try:
            done.put((i, future.result(), None))
        except BaseException as error:  # re-raised by the loop below
            done.put((i, None, error))

    while waiting or running:
        while waiting and len(running) < max(slots, 1):
            pick = choose()
            if pick is None:
                break
            waiting.remove(pick)
            running[pick] = needs_gb[pick]
            pool.submit(work, payloads[pick]).add_done_callback(lambda f, i=pick: finished(f, i))
        i, result, error = done.get()
        del running[i]
        if error is not None:
            raise error
        yield i, result


# --- the worker ----------------------------------------------------------------


def _trim() -> None:
    """Hand the heap glibc kept after a big lot back to the system."""
    if not sys.platform.startswith("linux"):
        return
    try:
        import ctypes

        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        pass


def _rss_mb() -> float | None:
    try:
        pages = int(Path("/proc/self/statm").read_text(encoding="utf-8").split()[1])
        return pages * os.sysconf("SC_PAGE_SIZE") / 2**20
    except (OSError, ValueError, IndexError, AttributeError):
        return None


def _peak_mb() -> float | None:
    try:
        import resource

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    except (ImportError, OSError):
        return None


def work(items: Sequence[tuple[int, Mapping[str, Any]]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Screen ``(index, row)`` pairs in a worker :func:`quadfit._init_worker`
    set up; each record carries its row's index as ``_row``. Returns the
    records and one timing per lot."""
    from flats.ingest.quadfit import _work_chunk

    records: list[dict[str, Any]] = []
    timings: list[dict[str, Any]] = []
    for index, row in items:
        started = time.time()
        got = _work_chunk([dict(row)])
        ended = time.time()
        for record in got:
            record["_row"] = index
        records.extend(got)
        acres = _area(row) / SQFT_PER_ACRE
        timings.append(
            {
                "TLID": row.get("TLID"),
                "acres": acres,
                "seconds": round(ended - started, 3),
                "rss_mb": _rss_mb(),
                "peak_mb": _peak_mb(),
                "pid": os.getpid(),
                "started": started,
                "ended": ended,
            }
        )
        if acres >= TRIM_ACRES:
            _trim()
    return records, timings


# --- the cache -----------------------------------------------------------------


def _canon(value: Any) -> Any:
    """A row value as JSON the same way every time it holds the same thing."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else repr(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"bytes": bytes(value).hex()}
    if isinstance(value, Mapping):
        return {str(k): _canon(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_canon(v) for v in value]
    tolist = getattr(value, "tolist", None)  # numpy arrays and scalars
    if callable(tolist):
        return _canon(tolist())
    isoformat = getattr(value, "isoformat", None)  # dates and timestamps
    if callable(isoformat):
        return {"time": isoformat()}
    return {"repr": f"{type(value).__qualname__}:{value!r}"}


def row_digest(row: Mapping[str, Any]) -> str:
    """The row as the worker receives it, as a hash."""
    text = json.dumps(_canon(row), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def _package_digest(root: Path) -> str:
    """Every file under the ``flats`` package but its tests, by path and content."""
    h = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root)
        if rel.parts[0] == "tests" or "__pycache__" in rel.parts or path.suffix == ".pyc":
            continue
        h.update(rel.as_posix().encode("utf-8") + b"\0")
        h.update(hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()


def _input_digest(path: Path | None) -> str | None:
    """A file or directory by the name, size and modification time of
    every file in it -- a copy or a touch misses, a changed file always does."""
    if path is None:
        return None
    path = Path(path)
    if path.is_file():
        st = path.stat()
        entries = [f"{path.name}\0{st.st_size}\0{st.st_mtime_ns}"]
    elif path.is_dir():
        entries = []
        for p in sorted(q for q in path.rglob("*") if q.is_file()):
            st = p.stat()
            entries.append(f"{p.relative_to(path).as_posix()}\0{st.st_size}\0{st.st_mtime_ns}")
    else:
        entries = ["(absent)"]
    return hashlib.sha256(("\n".join(entries) + f"\n{path.resolve()}").encode("utf-8")).hexdigest()


def _packages() -> list[str]:
    from importlib import metadata

    return sorted(
        f"{(d.metadata['Name'] or '?').lower()}=={d.version}" for d in metadata.distributions()
    )


def run_key(*, step_deg: float, inputs: Mapping[str, Path | None], package: Path | None = None) -> dict[str, Any]:
    """Everything a lot's answer depends on besides its own row."""
    if package is None:
        import flats

        package = Path(flats.__file__).resolve().parent
    return {
        "format": CACHE_FORMAT,
        "code": _package_digest(package),
        "python": sys.version,
        "packages": hashlib.sha256("\n".join(_packages()).encode("utf-8")).hexdigest(),
        "step_deg": float(step_deg),
        "inputs": {name: _input_digest(path) for name, path in sorted(inputs.items())},
    }


@dataclass
class AnswerCache:
    """A run's computed records, kept by lot key under ``root/<run digest>``.

    Records are stored as the worker made them, one file per chunk, with
    the lot's key in ``_key``; reading takes each key from the first file
    that holds it.
    """

    root: Path
    key: Mapping[str, Any]
    digest: str = field(init=False)
    where: Path = field(init=False)

    def __post_init__(self) -> None:
        text = json.dumps(self.key, sort_keys=True)
        self.digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        self.where = Path(self.root) / self.digest[:24]
        self.where.mkdir(parents=True, exist_ok=True)
        about = self.where / "key.json"
        if not about.exists():
            about.write_text(json.dumps(self.key, indent=2), encoding="utf-8")
        os.utime(self.where)

    def lot_key(self, row: Mapping[str, Any]) -> str:
        return hashlib.sha256(f"{self.digest}:{row_digest(row)}".encode("ascii")).hexdigest()

    def get(self, wanted: Iterable[str]) -> Any:
        """The stored records of every wanted key, as one frame with ``_key``."""
        import pandas as pd

        wanted = set(wanted)
        taken: set[str] = set()
        frames = []
        for path in sorted(self.where.glob("*.parquet")):
            if not wanted - taken:
                break
            frame = pd.read_parquet(path)
            frame = frame[frame["_key"].isin(wanted - taken)]
            if len(frame):
                taken.update(frame["_key"].unique())
                frames.append(frame)
        return pd.concat(frames, ignore_index=True) if frames else None

    def put(self, records: Sequence[Mapping[str, Any]]) -> None:
        """Keep a chunk's records (each with its ``_key``), atomically. A
        lot read twice into one run (the same row at two places) is kept
        once."""
        import pandas as pd

        first: dict[str, Any] = {}
        records = [r for r in records if first.setdefault(r["_key"], r.get("_row")) == r.get("_row")]
        records = [{k: v for k, v in r.items() if k != "_row"} for r in records]
        if not records:
            return
        name = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:12]}"
        tmp = self.where / f".{name}.tmp"
        pd.DataFrame.from_records(records).to_parquet(tmp, index=False)
        os.replace(tmp, self.where / f"{name}.parquet")


def prune(root: Path, keep_days: float = 14.0) -> list[Path]:
    """Delete the cache directories no run has used in ``keep_days``."""
    import shutil

    gone: list[Path] = []
    if not Path(root).is_dir():
        return gone
    cutoff = time.time() - keep_days * 86_400
    for where in Path(root).iterdir():
        if where.is_dir() and where.stat().st_mtime < cutoff:
            shutil.rmtree(where, ignore_errors=True)
            gone.append(where)
    return gone


# --- one run -------------------------------------------------------------------


@dataclass
class Batch:
    """What :func:`screen_rows` did, for the run's ``meta.json``."""

    lots: int = 0
    chunks: int = 0
    cached_lots: int = 0
    computed_lots: int = 0
    cache: str | None = None
    #: Chunks run again after a worker died (0 on a clean run).
    rerun_chunks: int = 0

    def meta(self) -> dict[str, Any]:
        return {
            "order": "costliest first",
            "chunks": self.chunks,
            "cache": self.cache,
            "cached_lots": self.cached_lots,
            "computed_lots": self.computed_lots,
            "rerun_chunks": self.rerun_chunks,
        }


def _close(pool: Any, clean: bool) -> None:
    """Shut ``pool`` down. After a failure its workers are stopped rather
    than waited for: a giant in flight may have twenty minutes to go."""
    if not clean:
        stop = getattr(pool, "terminate_workers", None)  # Python 3.14+
        if stop is not None:
            try:
                stop()
            except Exception:  # a broken pool may have no workers left to stop
                pass
    pool.shutdown(wait=True, cancel_futures=True)


def screen_rows(
    rows: Sequence[Mapping[str, Any]],
    parts_dir: Path,
    *,
    processes: int,
    chunk_size: int,
    init: Callable[..., None],
    initargs: tuple[Any, ...],
    cache: AnswerCache | None = None,
    step_deg: float | None = None,
    log: Any = print,
) -> tuple[Any, Any, Batch]:
    """Screen ``rows``; return their records in row order, the per-lot
    timings, and what was done.

    The lots ``cache`` holds are not screened again. The rest are planned
    (:func:`plan`) and dispatched (:func:`dispatch`); each chunk is written
    to ``parts_dir`` (and the cache) as it finishes.
    """
    import pandas as pd

    batch = Batch(lots=len(rows), cache=str(cache.where) if cache is not None else None)
    keys = [cache.lot_key(r) for r in rows] if cache is not None else None
    hits = cache.get(keys) if cache is not None else None
    held: set[str] = set(hits["_key"].unique()) if hits is not None else set()
    todo = [i for i in range(len(rows)) if keys is None or keys[i] not in held]
    batch.cached_lots = len(rows) - len(todo)
    batch.computed_lots = len(todo)

    chunks = [[todo[j] for j in c] for c in plan([rows[i] for i in todo], processes=processes, chunk_size=chunk_size)]
    batch.chunks = len(chunks)
    payloads = [[(i, rows[i]) for i in chunk] for chunk in chunks]
    needs = [max((extra_gb(rows[i]) for i in chunk), default=0.0) for chunk in chunks]
    if cache is not None:
        log(f"bridge: {batch.cached_lots:,} lots from the cache ({cache.where}), "
            f"{batch.computed_lots:,} to screen")
    log(f"bridge: {batch.computed_lots:,} lots in {len(chunks)} chunks, {processes} processes, "
        f"{step_deg} deg step, costliest first")

    timings: list[dict[str, Any]] = []
    t0 = time.time()
    done = 0
    kept: set[int] = set()

    def _keep(n: int, result: tuple[list[dict[str, Any]], list[dict[str, Any]]]) -> None:
        nonlocal done
        records, times = result
        pd.DataFrame.from_records(records).to_parquet(parts_dir / f"{n:05d}.parquet", index=False)
        if cache is not None:
            cache.put([{**r, "_key": keys[r["_row"]]} for r in records])
        timings.extend(times)
        done += len(chunks[n])
        kept.add(n)
        if len(kept) % 10 == 1 or len(kept) == len(payloads) or processes <= 1:
            log(f"  {done:,}/{len(todo):,}  {time.time() - t0:,.0f}s")

    if processes <= 1:
        init(*initargs)
        for n, payload in enumerate(payloads):
            _keep(n, work(payload))
    elif payloads:
        from concurrent.futures import ProcessPoolExecutor
        from concurrent.futures.process import BrokenProcessPool

        total = memory_gb()
        budget = BUDGET_SHARE * total if total else float("inf")
        left = list(range(len(payloads)))
        for retry in (False, True):
            pool = ProcessPoolExecutor(processes, initializer=init, initargs=initargs)
            clean = False
            try:
                for k, result in dispatch(
                    pool, work, [payloads[n] for n in left], [needs[n] for n in left],
                    slots=processes, budget_gb=0.0 if retry else budget, free_gb=available_gb,
                ):
                    _keep(left[k], result)
                clean = True
                break
            except BrokenProcessPool:
                left = [n for n in left if n not in kept]
                if not left:
                    break
                biggest = max((rows[i] for n in left for i in chunks[n]), key=_area)
                where = f"the biggest {biggest.get('TLID')} at {_area(biggest) / SQFT_PER_ACRE:,.1f} acres"
                if retry:
                    raise RuntimeError(
                        f"bridge: a worker died again (killed for memory?) with {len(left)} chunks unfinished, "
                        f"{where}. The finished chunks are in {parts_dir}"
                        + ("; re-launch the same command to resume from them." if cache is not None else ".")
                    ) from None
                batch.rerun_chunks = len(left)
                log(f"bridge: a worker died (killed for memory?) with {len(left)} chunks unfinished, {where}; "
                    "running them again with the giants one at a time")
            finally:
                _close(pool, clean)

    frames = [pd.read_parquet(p) for p in sorted(parts_dir.glob("*.parquet"))]
    if hits is not None and len(hits):
        where = pd.DataFrame({"_key": keys, "_row": range(len(rows))})
        frames.append(hits.merge(where, on="_key", how="inner", sort=False).drop(columns="_key"))
    frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if len(frame):
        frame = frame.sort_values("_row", kind="stable").drop(columns="_row").reset_index(drop=True)
    return frame, pd.DataFrame.from_records(timings), batch


__all__ = [
    "AnswerCache",
    "available_gb",
    "Batch",
    "cost",
    "dispatch",
    "extra_gb",
    "memory_gb",
    "plan",
    "prune",
    "row_digest",
    "run_key",
    "screen_rows",
    "work",
]
