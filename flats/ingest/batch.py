"""How a bridge run spends 137's cores and memory: costliest lots first, answers kept.

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

:func:`plan` deals the costliest lots first, and a lot worth a chunk on its
own runs on its own, so the giants run beside the small lots instead of
after them. What a lot costs -- its seconds, and the memory its worker
reaches -- is read from the :class:`LotBook`: what the lot cost the last
time a run screened it. A lot the book does not hold is estimated from its
area (:func:`cost`, :func:`need_gb`). Area is a poor guide to either
(FOLLOWUPS 46 proof 2, 2026-10-07: a 2-acre lot took 5.2 GB and 224 s, a
54-acre one 1.9 GB and 189 s; the slowest 1% of lots were 37% of the
work), so the book is what puts a repeat run in the right order, and an
estimate is only where a first run starts.

Started together the giants are in memory together -- two runs' worth
OOM-killed 137 on 2026-10-03 -- so a chunk starts only while the memory the
machine has free, less what the chunks in flight may still grow into,
covers what it may add and a reserve (:func:`choose`). Both are read live:
the machine's ``MemAvailable`` and each worker's resident set, every
second.

A worker the kernel kills anyway costs one lot. Each worker reports the lot
it starts and every lot it finishes, so when one dies the lots it finished
are kept, the lot it was screening runs again alone -- no other heavy chunk
beside it -- and the rest of its chunk goes back in the queue, while a fresh
worker takes its place. A lot that kills a worker a second time stops the
run with an error naming it; the finished chunks are kept, and with
``--cache`` a re-launch resumes from them. (A ``multiprocessing.Pool``
quietly replaces a dead worker and waits forever for its chunk: rank-colour
bound3, 2026-10-06, hung 2 h 20 min holding the lock. A
``ProcessPoolExecutor`` breaks and loses every chunk in flight: proof 2 ran
83 chunks again and lost ~1,500 s.) Workers offer themselves first to the
OOM killer (``oom_score_adj`` 1000), so it takes a worker, not the parent
that holds the run.

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
run that dies resumes from its last chunk. The book sits beside the cached
answers (``book.parquet`` in the cache directory) and outlives code
versions: what a lot costs barely moves when the code does.

None of it moves an answer: ``lots.parquet`` holds the same records in the
same order -- the order of the lots as read -- whatever order they ran in,
on whichever worker, and whichever came from the cache. ``timings.parquet``
beside it says what each lot cost: seconds, the worker's peak memory during
that lot alone (``peak_mb``), what the worker held after it (``rss_mb``),
and the estimate it was started under (``need_gb``).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import time
import traceback
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SQFT_PER_ACRE = 43_560.0

#: A lot's seconds when the book does not hold it: a floor (loading, the
#: sweep's setup) and its area. Loosely fitted on proof 2 (2026-10-07):
#: medians 0.2 s under 0.1 acre, 16 s at 1-2 acres, 48 s at 2-5; generous
#: above that, so an unknown giant is dealt early.
SECONDS_FLOOR = 0.3
SECONDS_PER_ACRE = 10.0

#: A lot's peak memory when the book does not hold it, as the worker's
#: resident set in GB: ``NEED_BASE_GB + NEED_LOG_GB * ln(1 + acres)``.
#: Proof 2: ~0.5 GB under 0.2 acre; 2-20 acres a median 1.7-1.9 GB, the
#: worst 5.2 GB. A lot the estimate misses badly kills its worker once and
#: is booked from then on.
NEED_BASE_GB = 1.2
NEED_LOG_GB = 0.9

#: A booked peak is taken this much larger: the code may have moved since.
BOOK_MARGIN = 1.25

#: A booked lot whose area moved by more than this share is a new lot.
BOOK_AREA_TOLERANCE = 0.02

#: A chunk that may reach this much is heavy: a heavy chunk that cannot
#: start yet holds back the heavy chunks behind it.
SMALL_GB = 2.0

#: Memory kept free beside everything in flight and what it may grow into.
RESERVE_GB = 3.0

#: A worker whose lot peaked above this hands its freed heap back after it,
#: or the high-water of that lot would stay resident for the rest of the run.
TRIM_MB = 1024.0

#: Chunks per worker the costs are cut to: the finer, the shorter the tail
#: a run ends on (its last chunks are its cheapest lots).
CHUNKS_PER_WORKER = 8

#: How often the parent re-reads memory while nothing reports, in seconds.
POLL_SECONDS = 1.0

#: Bumped when the cache's layout or the key's recipe changes.
CACHE_FORMAT = 1


# --- what a lot costs ------------------------------------------------------------


def _area(row: Mapping[str, Any]) -> float:
    try:
        area = float(row.get("area_sqft") or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return area if math.isfinite(area) and area > 0 else 0.0


def _acres(row: Mapping[str, Any]) -> float:
    return _area(row) / SQFT_PER_ACRE


@dataclass
class LotBook:
    """What each lot cost the last time a run screened it, by TLID: its
    seconds, its worker's peak memory, and the acres it had then -- a lot
    whose area has moved is a new lot."""

    path: Path | None = None
    #: TLID -> (acres, seconds, peak MB or None)
    entries: dict[str, tuple[float, float, float | None]] = field(default_factory=dict)

    @classmethod
    def open(cls, path: Path) -> LotBook:
        book = cls(Path(path))
        if book.path is not None and book.path.exists():
            import pandas as pd

            frame = pd.read_parquet(book.path)
            for tlid, acres, seconds, peak in zip(frame["TLID"], frame["acres"], frame["seconds"], frame["peak_mb"]):
                book.entries[str(tlid)] = (float(acres), float(seconds), None if pd.isna(peak) else float(peak))
        return book

    def _entry(self, row: Mapping[str, Any]) -> tuple[float, float, float | None] | None:
        got = self.entries.get(str(row.get("TLID")))
        if got is None:
            return None
        acres = _acres(row)
        if abs(got[0] - acres) > BOOK_AREA_TOLERANCE * max(got[0], acres):
            return None
        return got

    def holds(self, row: Mapping[str, Any]) -> bool:
        return self._entry(row) is not None

    def seconds(self, row: Mapping[str, Any]) -> float | None:
        got = self._entry(row)
        return got[1] if got is not None else None

    def peak_gb(self, row: Mapping[str, Any]) -> float | None:
        got = self._entry(row)
        return got[2] / 1024 if got is not None and got[2] is not None else None

    def record(self, timings: Iterable[Mapping[str, Any]]) -> None:
        """Book each timed lot, the newest timing of a lot replacing the last."""
        for t in timings:
            if t.get("TLID") is None or t.get("seconds") is None:
                continue
            peak = t.get("peak_mb")
            peak = None if peak is None or not math.isfinite(float(peak)) else float(peak)
            self.entries[str(t["TLID"])] = (float(t["acres"]), float(t["seconds"]), peak)

    def save(self) -> None:
        """Write the book, atomically."""
        if self.path is None:
            return
        import pandas as pd

        frame = pd.DataFrame.from_records(
            [(tlid, *entry) for tlid, entry in self.entries.items()],
            columns=["TLID", "acres", "seconds", "peak_mb"],
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex[:12]}.tmp")
        frame.to_parquet(tmp, index=False)
        os.replace(tmp, self.path)


def cost(row: Mapping[str, Any], book: LotBook | None = None) -> float:
    """What a lot costs to screen, in seconds: what it took the last time,
    or an estimate from its area."""
    booked = book.seconds(row) if book is not None else None
    return booked if booked is not None else SECONDS_FLOOR + SECONDS_PER_ACRE * _acres(row)


def need_gb(row: Mapping[str, Any], book: LotBook | None = None) -> float:
    """The resident memory a worker may reach screening a lot, in GB: the
    peak it reached the last time (with :data:`BOOK_MARGIN`), or an
    estimate from its area."""
    booked = book.peak_gb(row) if book is not None else None
    if booked is not None:
        return BOOK_MARGIN * booked
    return NEED_BASE_GB + NEED_LOG_GB * math.log1p(_acres(row))


def plan(
    rows: Sequence[Mapping[str, Any]], *, processes: int, chunk_size: int, book: LotBook | None = None
) -> list[list[int]]:
    """The rows' indices dealt into chunks, the costliest first.

    Lots are taken most costly first (:func:`cost`) and a chunk closes at
    ``chunk_size`` lots or at its share of the total cost
    (``CHUNKS_PER_WORKER`` per worker), whichever comes first -- so a lot
    worth a share alone is a chunk alone, and the run ends on chunks of its
    cheapest lots. Equal costs keep the order they were read in.
    """
    if not rows:
        return []
    costs = [cost(r, book) for r in rows]
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


# --- which chunk starts next -------------------------------------------------------


@dataclass
class Chunk:
    """Lots a worker screens in one go, and what it may need for them."""

    n: int
    items: list[tuple[int, Mapping[str, Any]]]
    #: The resident memory its worker may reach, in GB.
    need: float
    #: One of its lots was on a worker that died: it starts only with no
    #: other heavy chunk in flight, and none starts beside it.
    solo: bool = False

    @property
    def heavy(self) -> bool:
        return self.solo or self.need >= SMALL_GB


@dataclass
class InFlight:
    """A chunk on a worker, as :func:`choose` weighs it."""

    need: float
    #: What its worker holds now, in GB (0 when it cannot be read).
    rss: float
    heavy: bool = False
    solo: bool = False


def choose(
    waiting: Sequence[Chunk],
    running: Sequence[InFlight],
    *,
    free_gb: float | None,
    idle_gb: float = 0.0,
    reserve_gb: float = RESERVE_GB,
) -> int | None:
    """Which waiting chunk an idle worker holding ``idle_gb`` starts next:
    its position in ``waiting``, or None to wait.

    Chunks are taken in ``waiting`` order. One starts when ``free_gb`` --
    the memory the machine has free now -- less what the chunks in flight
    may still grow into (each its need less what its worker holds), covers
    what it may add (its need less ``idle_gb``) and ``reserve_gb``; or when
    nothing is in flight, so a chunk bigger than the machine still runs,
    alone. A heavy chunk that cannot start yet holds back the heavy chunks
    behind it, so the biggest is not starved to the end of the run, while
    light chunks pass it. A solo chunk starts only when no other heavy
    chunk is in flight, and while one runs no heavy chunk starts. When
    ``free_gb`` is unknown, only the number of workers limits the run.
    """
    if not waiting:
        return None
    if not running:
        return 0
    solo_running = any(r.solo for r in running)
    heavy_running = any(r.heavy for r in running)
    room = None
    if free_gb is not None:
        room = free_gb - sum(max(0.0, r.need - r.rss) for r in running) - reserve_gb
    blocked = False
    for k, chunk in enumerate(waiting):
        fits = room is None or room >= max(0.0, chunk.need - idle_gb)
        if chunk.heavy:
            if blocked or solo_running:
                continue
            if not fits or (chunk.solo and heavy_running):
                blocked = True
                continue
            return k
        if fits:
            return k
    return None


# --- memory ------------------------------------------------------------------------


def available_gb() -> float | None:
    """Memory free for new work right now (``MemAvailable``), in GB."""
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / 2**20
    except (OSError, ValueError, IndexError):
        pass
    return None


def _rss_mb(pid: int | str = "self") -> float | None:
    """What a process holds resident now, in MB."""
    try:
        pages = int(Path(f"/proc/{pid}/statm").read_text(encoding="utf-8").split()[1])
        return pages * os.sysconf("SC_PAGE_SIZE") / 2**20
    except (OSError, ValueError, IndexError, AttributeError):
        return None


def _reset_peak() -> bool:
    """Start this process's peak resident set again from what it holds now
    (Linux 4.0+), so the next reading is one lot's alone."""
    if not sys.platform.startswith("linux"):
        return False
    try:
        Path("/proc/self/clear_refs").write_text("5", encoding="ascii")
        return True
    except OSError:
        return False


def _peak_mb() -> float | None:
    """This process's peak resident set since :func:`_reset_peak`, in MB."""
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmHWM:"):
                return int(line.split()[1]) / 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def _trim() -> None:
    """Hand the heap glibc kept after a big lot back to the system."""
    if not sys.platform.startswith("linux"):
        return
    try:
        import ctypes

        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        pass


def _volunteer() -> None:
    """Put this process first in line for the OOM killer, ahead of the
    parent that holds the run."""
    try:
        Path("/proc/self/oom_score_adj").write_text("1000", encoding="ascii")
    except OSError:
        pass


# --- the worker ----------------------------------------------------------------------


def screen_one(index: int, row: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Screen one lot in a worker :func:`quadfit._init_worker` set up: its
    records, each carrying the row's index as ``_row``, and its timing."""
    from flats.ingest.quadfit import _work_chunk

    reset = _reset_peak()
    started = time.time()
    records = _work_chunk([dict(row)])
    ended = time.time()
    peak = _peak_mb() if reset else None
    acres = _acres(row)
    if (peak is not None and peak >= TRIM_MB) or (peak is None and acres >= 1.0):
        _trim()
    for record in records:
        record["_row"] = index
    timing = {
        "TLID": row.get("TLID"),
        "acres": acres,
        "seconds": round(ended - started, 3),
        "rss_mb": _rss_mb(),
        "peak_mb": peak,
        "pid": os.getpid(),
        "started": started,
        "ended": ended,
    }
    return records, timing


def _serve(conn: Any, init: Callable[..., None], initargs: tuple[Any, ...]) -> None:
    """A worker: set up, then screen the chunks it is sent, saying which
    lot it starts and handing back each lot as it finishes."""
    _volunteer()
    try:
        init(*initargs)
    except BaseException:
        conn.send(("error", None, None, traceback.format_exc()))
        return
    conn.send(("ready", os.getpid()))
    while True:
        try:
            job = conn.recv()
        except (EOFError, OSError):  # the parent is gone
            return
        if job is None:
            return
        n, items = job
        for index, row in items:
            conn.send(("start", n, index))
            try:
                records, timing = screen_one(index, row)
            except BaseException:
                conn.send(("error", n, index, traceback.format_exc()))
                return
            conn.send(("lot", n, index, records, timing))
        conn.send(("chunk", n))


@dataclass
class _Worker:
    proc: Any
    conn: Any
    #: Set when the worker is ready for work.
    pid: int | None = None
    chunk: Chunk | None = None
    #: The row index it is screening now.
    lot: int | None = None
    #: The lots of its chunk it has finished: (index, records, timing).
    done: list[tuple[int, list[dict[str, Any]], dict[str, Any]]] = field(default_factory=list)
    #: What it held at the last reading, in GB.
    rss: float = 0.0


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
    book: str | None = None
    #: Lots to screen whose cost was read from the book, not estimated.
    booked_lots: int = 0
    #: The lot each dead worker was screening (empty on a clean run).
    deaths: list[str] = field(default_factory=list)

    def meta(self) -> dict[str, Any]:
        return {
            "order": "costliest first",
            "chunks": self.chunks,
            "cache": self.cache,
            "cached_lots": self.cached_lots,
            "computed_lots": self.computed_lots,
            "book": self.book,
            "booked_lots": self.booked_lots,
            "worker_deaths": list(self.deaths),
        }


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
    (:func:`plan`, costs from the book beside the cache) and started as
    memory allows (:func:`choose`); each chunk is written to ``parts_dir``
    (and the cache) as it finishes, and the book takes every lot's timing.
    """
    import pandas as pd

    book = LotBook.open(Path(cache.root) / "book.parquet") if cache is not None else None
    batch = Batch(
        lots=len(rows),
        cache=str(cache.where) if cache is not None else None,
        book=str(book.path) if book is not None else None,
    )
    keys = [cache.lot_key(r) for r in rows] if cache is not None else None
    hits = cache.get(keys) if cache is not None else None
    held: set[str] = set(hits["_key"].unique()) if hits is not None else set()
    todo = [i for i in range(len(rows)) if keys is None or keys[i] not in held]
    batch.cached_lots = len(rows) - len(todo)
    batch.computed_lots = len(todo)
    batch.booked_lots = sum(book.holds(rows[i]) for i in todo) if book is not None else 0

    def chunk_of(n: int, indices: Sequence[int], solo: bool = False) -> Chunk:
        return Chunk(n, [(i, rows[i]) for i in indices], max(need_gb(rows[i], book) for i in indices), solo)

    planned = plan([rows[i] for i in todo], processes=processes, chunk_size=chunk_size, book=book)
    chunks = [chunk_of(n, [todo[j] for j in c]) for n, c in enumerate(planned)]
    batch.chunks = len(chunks)
    if cache is not None:
        log(f"bridge: {batch.cached_lots:,} lots from the cache ({cache.where}), "
            f"{batch.computed_lots:,} to screen; {batch.booked_lots:,} of them costed from the book ({book.path})")
    log(f"bridge: {batch.computed_lots:,} lots in {len(chunks)} chunks, {processes} processes, "
        f"{step_deg} deg step, costliest first")

    timings: list[dict[str, Any]] = []
    t0 = time.time()
    finished = 0
    parts = 0
    numbers = iter(range(len(chunks), 10**9))  # part numbers for chunks split after a death

    def keep(n: int, need: float, done: Sequence[tuple[int, list[dict[str, Any]], dict[str, Any]]]) -> None:
        nonlocal finished, parts
        records = [r for _, got, _ in done for r in got]
        if records:
            pd.DataFrame.from_records(records).to_parquet(parts_dir / f"{n:05d}.parquet", index=False)
            if cache is not None:
                cache.put([{**r, "_key": keys[r["_row"]]} for r in records])
        timings.extend({**t, "need_gb": round(need, 3)} for _, _, t in done)
        finished += len(done)
        parts += 1
        if parts % 10 == 1 or finished == len(todo) or processes <= 1:
            log(f"  {finished:,}/{len(todo):,}  {time.time() - t0:,.0f}s")

    try:
        if processes <= 1:
            init(*initargs)
            for chunk in chunks:
                keep(chunk.n, chunk.need, [(i, *screen_one(i, row)) for i, row in chunk.items])
        elif chunks:
            _run_workers(
                chunks, rows, min(processes, len(chunks)), init, initargs, keep, chunk_of, numbers, batch,
                where=parts_dir, resumable=cache is not None, log=log,
            )
    finally:
        if book is not None and timings:
            book.record(timings)
            book.save()

    frames = [pd.read_parquet(p) for p in sorted(parts_dir.glob("*.parquet"))]
    if hits is not None and len(hits):
        where = pd.DataFrame({"_key": keys, "_row": range(len(rows))})
        frames.append(hits.merge(where, on="_key", how="inner", sort=False).drop(columns="_key"))
    frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if len(frame):
        frame = frame.sort_values("_row", kind="stable").drop(columns="_row").reset_index(drop=True)
    return frame, pd.DataFrame.from_records(timings), batch


def _run_workers(
    chunks: list[Chunk],
    rows: Sequence[Mapping[str, Any]],
    processes: int,
    init: Callable[..., None],
    initargs: tuple[Any, ...],
    keep: Callable[[int, float, Sequence[tuple[int, list[dict[str, Any]], dict[str, Any]]]], None],
    chunk_of: Callable[..., Chunk],
    numbers: Iterable[int],
    batch: Batch,
    *,
    where: Path,
    resumable: bool,
    log: Any,
) -> None:
    """Run ``chunks`` on ``processes`` workers as memory allows; see the
    module docstring for what happens when one dies."""
    import multiprocessing
    from multiprocessing.connection import wait

    numbers = iter(numbers)
    ctx = multiprocessing.get_context()
    workers: list[_Worker] = []
    waiting = list(chunks)
    deaths: dict[int, int] = {}

    def spawn() -> None:
        here, there = ctx.Pipe()
        proc = ctx.Process(target=_serve, args=(there, init, initargs), name="bridge-worker")
        proc.start()
        there.close()
        workers.append(_Worker(proc, here))

    def lot_name(index: int) -> str:
        row = rows[index]
        return f"{row.get('TLID')} at {_acres(row):,.1f} acres"

    def died(w: _Worker) -> None:
        workers.remove(w)
        w.proc.join(timeout=10)
        w.conn.close()
        if w.pid is None:
            raise RuntimeError(f"bridge: a worker died while it was being set up (exit code {w.proc.exitcode})")
        chunk, culprit = w.chunk, w.lot
        if chunk is not None:
            if w.done:
                keep(next(numbers), chunk.need, w.done)
            ended = {i for i, _, _ in w.done}
            rest = [i for i, _ in chunk.items if i not in ended and i != culprit]
            if rest:
                waiting.insert(0, chunk_of(next(numbers), rest))
            if culprit is not None:
                deaths[culprit] = deaths.get(culprit, 0) + 1
                batch.deaths.append(str(rows[culprit].get("TLID")))
                if deaths[culprit] > 1:
                    raise RuntimeError(
                        f"bridge: lot {lot_name(culprit)} killed its worker again, running alone (killed for memory?). "
                        f"The finished chunks are in {where}"
                        + ("; re-launch the same command to resume from them." if resumable else ".")
                    )
                solo = chunk_of(next(numbers), [culprit], solo=True)
                solo.need = max(solo.need, w.rss)
                waiting.insert(0, solo)
                log(f"bridge: a worker died (killed for memory?) screening {lot_name(culprit)}; the {len(ended)} "
                    "lots it had finished are kept and the lot runs again alone")
            else:
                log(f"bridge: a worker died between lots; the {len(ended)} lots it had finished are kept")
        spawn()

    def drain(w: _Worker) -> None:
        try:
            while w.conn.poll():
                kind, *msg = w.conn.recv()
                if kind == "ready":
                    w.pid = msg[0]
                elif kind == "start":
                    w.lot = msg[1]
                elif kind == "lot":
                    w.done.append((msg[1], msg[2], msg[3]))
                    w.lot = None
                elif kind == "chunk":
                    keep(w.chunk.n, w.chunk.need, w.done)
                    w.chunk, w.lot, w.done = None, None, []
                elif kind == "error":
                    _, index, text = msg
                    what = f"lot {lot_name(index)}" if index is not None else "worker setup"
                    raise RuntimeError(f"bridge: {what} failed in a worker:\n{text}")
        except (EOFError, OSError):  # the worker is gone; its sentinel says so
            pass
        if not w.proc.is_alive():
            died(w)

    clean = False
    try:
        for _ in range(processes):
            spawn()
        while waiting or any(w.chunk is not None for w in workers):
            for w in workers:
                if w.pid is not None:
                    w.rss = (_rss_mb(w.pid) or 0.0) / 1024
            while waiting:
                idle = [w for w in workers if w.pid is not None and w.chunk is None]
                if not idle:
                    break
                w = min(idle, key=lambda x: x.rss)
                running = [InFlight(x.chunk.need, x.rss, x.chunk.heavy, x.chunk.solo) for x in workers if x.chunk]
                k = choose(waiting, running, free_gb=available_gb(), idle_gb=w.rss)
                if k is None:
                    break
                chunk = waiting.pop(k)
                try:
                    w.conn.send((chunk.n, chunk.items))
                except OSError:  # it died idle; drain() replaces it
                    waiting.insert(k, chunk)
                    break
                w.chunk, w.lot, w.done = chunk, None, []
            ready = wait([w.conn for w in workers] + [w.proc.sentinel for w in workers], timeout=POLL_SECONDS)
            for w in [w for w in workers if w.conn in ready or w.proc.sentinel in ready]:
                drain(w)
        clean = True
    finally:
        for w in workers:
            if clean:
                try:
                    w.conn.send(None)
                except OSError:
                    pass
            else:  # a giant in flight may have twenty minutes to go
                w.proc.kill()
        for w in workers:
            w.proc.join(timeout=30)
            if w.proc.is_alive():
                w.proc.kill()
                w.proc.join()
            w.conn.close()


__all__ = [
    "AnswerCache",
    "available_gb",
    "Batch",
    "choose",
    "Chunk",
    "cost",
    "InFlight",
    "LotBook",
    "need_gb",
    "plan",
    "prune",
    "row_digest",
    "run_key",
    "screen_one",
    "screen_rows",
]
