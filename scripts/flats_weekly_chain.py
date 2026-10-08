"""The weekly re-screen on 137, start to finish, that survives the night (FOLLOWUPS 48).

Steph, 2026-10-07: "we're moving quick and stacking a lot of changes between
runs. Don't want to lose time to avoidable problems." Until this script the
chain was a shell file written by hand each week on 137: a failure at the
bridge re-ran the 75 minutes before it, a hung step held heavy.lock until
someone looked, and a missing input surfaced hours in. This one:

* **checks first** (``preflight``), in seconds: the code is at ``--sha`` and
  clean; every dataset ``flats/config/pipeline.yaml`` names is in the snapshot
  as it is registered today (the 2026-10-07 copy lacked 15); the 1 m elevation
  tiles, the institutional-land and curb datasets are there; 137 (and the app
  host, given ``--app-host``) has the disk. Anything wrong refuses the run.
* **marks each step done** (``<state>/<step>.done``), so launching the same
  command again skips what finished; the bridge itself resumes from its
  answer cache, so a bridge that died at hour five loses minutes, not hours.
* **restarts a step that died for a passing reason**: killed by a signal (the
  kernel's OOM killer), a lot that killed its worker twice (with half the
  processes), or a stall -- no CPU used by the step's processes for
  ``--stall-minutes``. It watches CPU, not new parts: a 40-acre lot takes
  twenty minutes and writes nothing while it works, and a hung run uses
  none. A step that fails on its own terms (an exit code, a traceback) is
  not retried: the same code fails the same way. After ``--tries`` it gives
  up and says where.
* **kills only its own**: each step runs in its own process group, and only
  that group is ever signalled; a step outlives the supervisor by no more
  than its first process (``PR_SET_PDEATHSIG``).
* **writes a status file** every ``--status-every`` seconds (step, try,
  processes, memory, the kernel's OOM-kill count, the bridge's parts, the
  log's tail), copied to ``--status-to`` by scp, so any session can watch
  without logging in. Its last line is ``WEEKLY CHAIN DONE`` or ``GAVE UP``.

Launch on 137 from a plain shell, never chained from a script that holds the
lock (it waits on itself)::

    cd /root/code/vicinitideals && nohup flock -o /root/heavy.lock \\
      .venv/bin/python scripts/flats_weekly_chain.py --snapshot 2026-10-07 --sha <commit> \\
        --dem-from data/quadfit_demw/raw --snapshot-date 2026-10-01 \\
        --transit-reuse data/flats/transit/2026-10-01/distances.parquet \\
        --status-to root@<vm114>:/root/weekly137/status.txt --app-host root@<vm114> \\
      > /root/weekly_chain.log 2>&1 < /dev/null &

Re-launch the same line after anything. ``--preflight-only`` checks and
prints the commands without running them; ``--from STEP`` runs that step and
every one after it again. Load, drift and promote stay by hand (runbook §4b).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

STEPS = ("stage", "quadfit", "normalize", "institutional", "transit", "bridge", "assign", "export")
#: The bridge's own words when a lot killed its worker twice and ended the run
#: (flats.ingest.batch). Not "killed for memory?": a run that survived one death
#: says that too, and may then fail for a reason more tries will not cure.
MEMORY_WORDS = ("killed its worker again",)
#: Read from the snapshot by the institutional-land step (FOLLOWUPS 47).
INSTITUTIONAL_KEYS = ("osm_land_use", "rlis_orca")
FEWEST_PROCESSES = 2


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def say(text: str) -> None:
    print(f"[{_now()}] {text}", flush=True)


# --- the chain ------------------------------------------------------------------------


@dataclass
class Chain:
    """Where one weekly re-screen reads and writes, and each step's command."""

    snapshot: str
    tag: str
    data: Path
    work: Path
    sources_root: Path
    dem_from: Path
    transit_reuse: Path | None = None
    snapshot_date: str | None = None
    chunk_size: int = 250
    bridge_args: Sequence[str] = ()
    python: str = sys.executable

    @property
    def sources(self) -> Path:
        return self.sources_root / self.snapshot

    @property
    def quadfit(self) -> Path:
        return self.data / f"quadfit_{self.tag}"

    def flats(self, stage: str) -> Path:
        return self.data / "flats" / stage / self.tag

    @property
    def bridge(self) -> Path:
        return self.work / f"bridge_{self.tag}"

    @property
    def cache(self) -> Path:
        return self.work / "bridge_cache"

    def command(self, step: str, processes: int) -> tuple[list[str], dict[str, str]]:
        """The argv and extra environment of ``step``."""
        py, q = self.python, self.quadfit
        lots = str(self.flats("normalized") / "lots.parquet")
        if step == "stage":
            return [py, "scripts/flats_stage_quadfit_raw.py", "--snapshot", self.snapshot,
                    "--root", str(self.sources_root), "--data-dir", str(q), "--dem-from", str(self.dem_from)], {}
        if step == "quadfit":
            return [py, "Lot Analysis/quadfit/run_all.py", "--stage", "s1", "--force"], {"QUADFIT_DATA_DIR": str(q)}
        if step == "normalize":
            return [py, "-m", "flats.ingest.normalize", "--snapshot", self.snapshot, "--root", str(self.sources_root),
                    "--out", str(self.flats("normalized"))], {}
        if step == "institutional":
            return [py, "-m", "flats.ingest.institutional", "--lots", lots, "--sources", str(self.sources),
                    "--out", str(self.flats("institutional"))], {}
        if step == "transit":
            reuse = ["--reuse", str(self.transit_reuse)] if self.transit_reuse else []
            return [py, "-m", "flats.ingest.transit", "--lots", lots, "--sources", str(self.sources),
                    "--out", str(self.flats("transit")), *reuse], {}
        if step == "bridge":
            return [py, "-m", "flats.ingest.quadfit", "--s4", str(q / "s4_lots.parquet"),
                    "--s5o", str(q / "s5o_lots.parquet"), "--results", str(q / "lots_results.csv"),
                    "--out", str(self.bridge), "--processes", str(processes), "--chunk-size", str(self.chunk_size),
                    "--sources", str(self.sources), "--dem", str(q / "raw"),
                    "--transit", str(self.flats("transit") / "distances.parquet"),
                    "--institutional", str(self.flats("institutional")), "--cache", str(self.cache),
                    *self.bridge_args], {}
        if step == "assign":
            date = ["--snapshot-date", self.snapshot_date] if self.snapshot_date else []
            return [py, "-m", "flats.ingest.assign", "--normalized", str(self.flats("normalized")),
                    "--bridge", str(self.bridge), "--quadfit-dir", str(q),
                    "--out", str(self.work / f"assign_{self.tag}"), *date], {}
        if step == "export":
            return [py, "scripts/flats_load_bridge.py", "export", "--run-dir", str(self.work / f"assign_{self.tag}"),
                    "--out", str(self.work / f"bundle_{self.tag}")], {}
        raise ValueError(f"no step {step!r}")


# --- preflight ------------------------------------------------------------------------


def code_problems(repo: Path, sha: str) -> list[str]:
    """The checkout is at ``sha`` and the screen's files are as committed."""
    if len(sha) < 7:
        return [f"--sha {sha!r}: give at least 7 characters of the commit"]

    def git(*args: str) -> str:
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout

    try:
        head = git("rev-parse", "HEAD").strip()
        dirty = git("status", "--porcelain", "--", "flats", "Lot Analysis", "scripts").strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        return [f"{repo}: cannot read the checkout ({exc})"]
    problems = []
    if not head.startswith(sha):
        problems.append(f"code: the checkout is at {head[:12]}, not {sha} -- git checkout {sha} first")
    if dirty:
        problems.append(f"code: uncommitted changes under flats/, Lot Analysis/ or scripts/:\n    {dirty[:600]}")
    return problems


def snapshot_problems(
    snapshot: Path, dem_from: Path, pipeline: Any = None, notes: list[str] | None = None
) -> list[str]:
    """The snapshot holds every registered dataset. A dataset fetched under an
    older registry entry is a note, not a problem: a re-screen reads the
    ground the copy in use was measured from, and the 2026-10-07 copy, which
    screened clean, held 71 such (most entries changed in ways that do not
    touch the file, and re-fetching would move the ground)."""
    from flats.geom import curbs
    from flats.ingest.acquire import _spec_sha, read_manifest
    from flats.ingest.sources import load_pipeline
    from flats_stage_quadfit_raw import check

    if not snapshot.is_dir():
        return [f"{snapshot}: no snapshot"]
    manifest = read_manifest(snapshot)
    datasets = manifest.get("datasets", {})
    if not datasets:
        return [f"{snapshot}: no manifest.json, or it lists nothing"]
    problems = check(manifest, snapshot, dem_from if dem_from.is_dir() else None)
    fetch = f"python -m flats.ingest.acquire --snapshot {snapshot.name} --root {snapshot.parent} --keys"
    pipeline = pipeline or load_pipeline()
    absent, stale = [], []
    for key, ds in sorted(pipeline.datasets.items()):
        entry = datasets.get(key)
        if entry is None:
            absent.append(key)
            continue
        if entry.get("status") not in ("acquired", "present"):
            continue
        if entry.get("spec_sha256") != _spec_sha(ds):
            stale.append(key)
        elif (path := snapshot / str(entry.get("file") or "")).is_file() and path.stat().st_size != entry.get("bytes"):
            problems.append(f"{key}: the file changed size since it was fetched ({path})")
    if absent:
        problems.append(f"{len(absent)} registered datasets are not in the snapshot: {fetch} {','.join(absent)}")
    if stale and notes is not None:
        notes.append(f"{len(stale)} datasets were fetched under an older pipeline.yaml entry; for a new copy of "
                     f"the ground: {fetch} {','.join(stale)} --force")
    for key in INSTITUTIONAL_KEYS:
        if datasets.get(key, {}).get("status") not in ("acquired", "present"):
            problems.append(f"{key}: institutional land needs it and the snapshot does not hold it")
    lacking = curbs.missing(snapshot)
    if lacking:
        problems.append(f"curb datasets missing (the bridge refuses without them): {', '.join(lacking)}")
    if not any((dem_from / "dem").glob("*.tif")):
        problems.append(f"no 1 m elevation tiles in {dem_from / 'dem'}")
    if not (dem_from / "dem10_utm").is_dir():
        problems.append(f"no 10 m elevation tiles in {dem_from / 'dem10_utm'}")
    return problems


def disk_problems(places: Sequence[tuple[str, Path, float]]) -> list[str]:
    out = []
    for label, path, need in places:
        probe = path
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        free = shutil.disk_usage(probe).free / 2**30
        if free < need:
            out.append(f"disk: {free:.1f} GB free at {label} ({path}), {need:g} GB wanted")
    return out


def app_disk_problems(host: str, path: str, need: float) -> list[str]:
    try:
        got = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", host, "df", "-Pk", path],
                             capture_output=True, text=True, timeout=60)
        free = int(got.stdout.splitlines()[-1].split()[3]) / 2**20
    except (OSError, subprocess.SubprocessError, IndexError, ValueError):
        return [f"disk: cannot read free disk on {host} ({path}); drop --app-host to skip the check"]
    return [f"disk: {free:.1f} GB free on {host} ({path}), {need:g} GB wanted"] if free < need else []


# --- watching a step ------------------------------------------------------------------


def group_cpu(pgid: int, proc: Path = Path("/proc")) -> dict[tuple[int, int], int] | None:
    """CPU ticks each live process of group ``pgid`` has used, keyed by (pid,
    start time); None where there is no /proc to read."""
    if not proc.is_dir():
        return None
    out: dict[tuple[int, int], int] = {}
    for d in proc.iterdir():
        if not d.name.isdigit():
            continue
        try:
            text = (d / "stat").read_text()
        except OSError:
            continue
        rest = text[text.rindex(")") + 2:].split()  # the name may hold spaces; fields from the state on
        # A zombie (Z) has ended but is not yet reaped -- the step itself is
        # one until attempt() waits on it -- so counting it held end_group a
        # whole grace period per signal after the step was gone.
        if int(rest[2]) == pgid and rest[0] not in ("Z", "X"):
            out[(int(d.name), int(rest[19]))] = int(rest[11]) + int(rest[12])
    return out


class Watch:
    """Says a step has stalled when its processes used under ``cpu_seconds``
    of CPU between them over the last ``minutes``."""

    def __init__(self, pgid: int, minutes: float, cpu_seconds: float, *,
                 sample: Callable[[int], Mapping[tuple[int, int], int] | None] = group_cpu,
                 clock: Callable[[], float] = time.monotonic, tick: float | None = None) -> None:
        self.pgid, self.window, self.floor = pgid, minutes * 60, cpu_seconds
        self.sample, self.clock = sample, clock
        self.tick = tick or (os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100)
        self.seen: dict[tuple[int, int], int] = {}
        self.used = 0.0
        self.history: deque[tuple[float, float]] = deque()

    def stalled(self) -> bool:
        got = self.sample(self.pgid)
        if got is None:
            return False
        now = self.clock()
        self.used += sum(max(0, t - self.seen.get(k, 0)) for k, t in got.items()) / self.tick
        self.seen = dict(got)
        self.history.append((now, self.used))
        while len(self.history) > 1 and self.history[1][0] <= now - self.window:
            self.history.popleft()
        since, used = self.history[0]
        return now - since >= self.window and self.used - used < self.floor


def end_group(pgid: int, grace: float = 30.0) -> None:
    """TERM then KILL every process left in group ``pgid`` -- the step's own."""
    if not hasattr(os, "killpg"):
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError):
            return
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            if not group_cpu(pgid):
                return
            time.sleep(0.5)


def oom_kills() -> int | None:
    """The kernel's OOM-kill count for this container (cgroup v2)."""
    try:
        for line in Path("/sys/fs/cgroup/memory.events").read_text().splitlines():
            name, _, count = line.partition(" ")
            if name == "oom_kill":
                return int(count)
    except (OSError, ValueError):
        pass
    return None


def _die_with_parent() -> None:
    try:
        import ctypes

        ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGKILL)  # PR_SET_PDEATHSIG
    except (OSError, AttributeError):
        pass


@dataclass
class Attempt:
    rc: int
    stalled: bool = False
    oom: bool = False
    tail: str = ""
    seconds: float = 0.0


def next_move(step: str, attempt: Attempt, processes: int) -> tuple[str, int]:
    """``done``, ``retry`` or ``give up``, and the processes for the next try."""
    if attempt.rc == 0 and not attempt.stalled:
        return "done", processes
    if attempt.stalled:
        return "retry", processes
    memory = attempt.oom or attempt.rc < 0 or attempt.rc == 128 + 9 or any(w in attempt.tail for w in MEMORY_WORDS)
    if not memory:
        return "give up", processes
    return "retry", max(FEWEST_PROCESSES, processes // 2) if step == "bridge" else processes


# --- the status file ------------------------------------------------------------------


@dataclass
class Status:
    path: Path
    chain: Chain
    sha: str
    every: float = 120.0
    to: str | None = None
    fields: dict[str, Any] = field(default_factory=dict)
    last: float = 0.0

    def set(self, **more: Any) -> None:
        self.fields.update(more)
        self.write()

    def due(self) -> None:
        if time.monotonic() - self.last >= self.every:
            self.write()

    def text(self) -> str:
        f = self.fields
        lines = [f"AT {_now()}  WEEKLY {self.chain.tag} at {self.sha}  supervisor pid {os.getpid()}"]
        if f.get("step"):
            lines.append(f"STEP {f['step']} ({STEPS.index(f['step']) + 1}/{len(STEPS)}) try {f.get('try', 1)}/"
                         f"{f.get('tries', '?')}, {f.get('processes', '?')} processes, since {f.get('since', '?')}")
        lines.append(f"DONE {' '.join(f.get('done', [])) or '-'}")
        try:
            mem = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
            avail = int(mem["MemAvailable"].split()[0]) // 1024
            total = int(mem["MemTotal"].split()[0]) // 1024
            load = Path("/proc/loadavg").read_text().split()[:3]
            lines.append(f"MEM avail {avail:,}/{total:,} MB  OOM_KILL {oom_kills()}  LOAD {' '.join(load)}")
        except (OSError, KeyError, ValueError):
            pass
        parts = self.chain.bridge / "parts"
        if f.get("step") == "bridge" and parts.is_dir():
            got = sorted(parts.glob("*.parquet"), key=lambda p: p.stat().st_mtime)
            newest = datetime.fromtimestamp(got[-1].stat().st_mtime, timezone.utc).strftime("%H:%M:%S") if got else "-"
            lines.append(f"BRIDGE parts {len(got)}, newest {newest}")
        log = f.get("log")
        if log and Path(log).is_file():
            lines.append(f"== {log}")
            lines += _tail(Path(log), 4).splitlines()
        if f.get("final"):
            lines.append(f["final"])
        return "\n".join(lines) + "\n"

    def write(self) -> None:
        self.last = time.monotonic()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(self.text(), encoding="utf-8")
        tmp.replace(self.path)
        if self.to:
            try:
                subprocess.run(["scp", "-q", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", str(self.path), self.to],
                               capture_output=True, timeout=30)
            except (OSError, subprocess.SubprocessError):
                pass


def _tail(path: Path, lines: int, start: int = 0) -> str:
    with path.open("rb") as fh:
        fh.seek(0, os.SEEK_END)
        end = fh.tell()
        fh.seek(max(start, end - 16_384))
        return "\n".join(fh.read().decode("utf-8", "replace").splitlines()[-lines:])


# --- running --------------------------------------------------------------------------


def attempt(argv: Sequence[str], env: Mapping[str, str], log: Path, status: Status, *, cwd: Path,
            stall_minutes: float, stall_cpu: float, poll: float = 15.0) -> Attempt:
    """Run one try of a step in its own process group, watched."""
    t0, before = time.monotonic(), oom_kills()
    with log.open("ab") as out:
        out.write(f"\n=== {_now()} {' '.join(argv)}\n".encode())
        out.flush()
        start = out.tell()
        posix = os.name == "posix"
        proc = subprocess.Popen(list(argv), cwd=cwd, env={**os.environ, **env}, stdout=out, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, start_new_session=posix,
                                preexec_fn=_die_with_parent if sys.platform.startswith("linux") else None)
    watch, stalled = Watch(proc.pid, stall_minutes, stall_cpu), False
    try:
        while proc.poll() is None:
            try:
                proc.wait(timeout=poll)
            except subprocess.TimeoutExpired:
                pass
            if proc.poll() is None and watch.stalled():
                say(f"no CPU used for {stall_minutes:g} min: ending the step's processes")
                stalled = True
                end_group(proc.pid)
                proc.wait()
            status.due()
    finally:
        if proc.poll() is None:
            end_group(proc.pid)
            proc.wait()
        end_group(proc.pid, grace=10.0)  # a dead parent's workers, if any were left
    after = oom_kills()
    return Attempt(proc.returncode, stalled, before is not None and after is not None and after > before,
                   _tail(log, 30, start), time.monotonic() - t0)


def _same_commit(a: str, b: str) -> bool:
    return bool(a and b) and (a.startswith(b) or b.startswith(a))


def run_chain(chain: Chain, *, sha: str, state: Path, processes: int, tries: int, start_from: str | None,
              status: Status, stall_minutes: float, stall_cpu: float, poll: float = 15.0,
              command: Callable[[str, int], tuple[list[str], dict[str, str]]] | None = None) -> int:
    """Run every step not yet marked done; 0 when the chain finished."""
    command = command or chain.command
    state.mkdir(parents=True, exist_ok=True)
    if start_from:
        for step in STEPS[STEPS.index(start_from):]:
            (state / f"{step}.done").unlink(missing_ok=True)
    marks = {s: json.loads((state / f"{s}.done").read_text(encoding="utf-8"))
             for s in STEPS if (state / f"{s}.done").is_file()}
    if start_from:
        # the steps before it are kept for this code, on the operator's word,
        # so a plain re-launch after this one takes them too
        for step, mark in marks.items():
            if not any(_same_commit(mark.get(k) or "", sha) for k in ("sha", "kept_for")):
                mark["kept_for"] = sha
                (state / f"{step}.done").write_text(json.dumps(mark, indent=2), encoding="utf-8")
    other = {s: m["sha"][:12] for s, m in marks.items()
             if not any(_same_commit(m.get(k) or "", sha) for k in ("sha", "kept_for"))}
    if other:
        say(f"REFUSED: steps finished at other code: {other}. Re-run from the first step the change touches "
            f"(--from STEP; the steps before it are kept), or use a fresh --state")
        status.set(final=f"REFUSED: steps finished at other code {other}")
        return 2
    done = [s for s in STEPS if s in marks]
    status.set(done=done)
    for step in STEPS:
        if step in marks:
            say(f"{step}: done at {marks[step]['finished_at']}, skipped")
            continue
        p, log = processes, state / f"{step}.log"
        for n in range(1, tries + 1):
            argv, env = command(step, p)
            say(f"{step}: try {n}/{tries}" + (f", {p} processes" if step == "bridge" else ""))
            status.set(step=step, **{"try": n}, tries=tries, processes=p if step == "bridge" else "-",
                       since=_now(), log=str(log))
            got = attempt(argv, env, log, status, cwd=REPO_ROOT, stall_minutes=stall_minutes,
                          stall_cpu=stall_cpu, poll=poll)
            move, p = next_move(step, got, p)
            say(f"{step}: exit {got.rc} after {got.seconds / 60:.1f} min"
                + (", stalled" if got.stalled else "") + (", the kernel killed for memory" if got.oom else "")
                + f" -> {move}")
            if move == "done":
                mark = {"step": step, "sha": sha, "finished_at": _now(), "minutes": round(got.seconds / 60, 1),
                        "tries": n, "processes": p if step == "bridge" else None, "argv": argv}
                (state / f"{step}.done").write_text(json.dumps(mark, indent=2), encoding="utf-8")
                done.append(step)
                status.set(done=done)
                break
            if move == "give up" or n == tries:
                why = "stalled" if got.stalled else f"exit {got.rc}"
                final = (f"GAVE UP at {step} after {n} {'try' if n == 1 else 'tries'} ({why}); see {log}. "
                         "Fix it, then re-launch the same command (less any --from) to resume.")
                say(final)
                say(got.tail)
                status.set(final=final)
                return 1
    final = f"WEEKLY CHAIN DONE {_now()}"
    (state / "chain.json").write_text(json.dumps(
        {s: json.loads((state / f"{s}.done").read_text(encoding="utf-8")) for s in STEPS}, indent=2),
        encoding="utf-8")
    say(final)
    status.set(step=None, final=final)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    from flats.ingest.acquire import SNAPSHOTS

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    ap.add_argument("--snapshot", required=True, help="the acquire snapshot screened, YYYY-MM-DD")
    ap.add_argument("--sha", required=True, help="the commit the run must be on (7+ characters)")
    ap.add_argument("--tag", help="names every output (default: <snapshot>_weekly)")
    ap.add_argument("--root", type=Path, default=SNAPSHOTS, help="where snapshots live")
    ap.add_argument("--data", type=Path, default=REPO_ROOT / "data", help="the data tree")
    ap.add_argument("--work", type=Path, default=Path.home(), help="where bridge/assign/bundle dirs go (default ~)")
    ap.add_argument("--dem-from", type=Path, default=REPO_ROOT / "data" / "quadfit" / "raw",
                    help="raw dir whose elevation tiles are linked in")
    ap.add_argument("--transit-reuse", type=Path, help="an earlier distances.parquet to start from")
    ap.add_argument("--snapshot-date", help="assign's --snapshot-date (the ground date of the copy in use)")
    ap.add_argument("--processes", type=int, default=16, help="bridge processes (halved after a memory death)")
    ap.add_argument("--chunk-size", type=int, default=250)
    ap.add_argument("--bridge-arg", action="append", default=[], help="one more bridge argument (repeatable)")
    ap.add_argument("--state", type=Path, help="done markers, logs, status (default: <work>/weekly_<tag>)")
    ap.add_argument("--from", dest="start_from", choices=STEPS, help="run this step and every later one again")
    ap.add_argument("--tries", type=int, default=3)
    ap.add_argument("--stall-minutes", type=float, default=20.0)
    ap.add_argument("--stall-cpu-seconds", type=float, default=60.0)
    ap.add_argument("--status-every", type=float, default=120.0)
    ap.add_argument("--status-to", help="scp destination for the status file, user@host:/path")
    ap.add_argument("--min-free-gb", type=float, default=10.0, help="free disk wanted here (a weekly writes ~3.5 GB)")
    ap.add_argument("--app-host", help="ssh destination of the app host, for its free disk")
    ap.add_argument("--app-path", default="/var/lib/docker", help="where the app host keeps the database")
    ap.add_argument("--app-min-free-gb", type=float, default=5.0)
    ap.add_argument("--preflight-only", action="store_true", help="check and print the commands; run nothing")
    args = ap.parse_args(argv)

    tag = args.tag or f"{args.snapshot}_weekly"
    chain = Chain(args.snapshot, tag, args.data.resolve(), args.work.resolve(), args.root.resolve(),
                  args.dem_from.resolve(), args.transit_reuse, args.snapshot_date, args.chunk_size,
                  tuple(args.bridge_arg))
    state = args.state or chain.work / f"weekly_{tag}"
    status = Status(state / "status.txt", chain, args.sha, args.status_every, args.status_to)

    notes: list[str] = []
    problems = code_problems(REPO_ROOT, args.sha)
    problems += snapshot_problems(chain.sources, chain.dem_from, notes=notes)
    for note in notes:
        say(f"note: {note}")
    if args.transit_reuse and not args.transit_reuse.is_file():
        problems.append(f"--transit-reuse {args.transit_reuse}: no such file")
    problems += disk_problems([("the data tree", chain.data, args.min_free_gb), ("--work", chain.work, args.min_free_gb)])
    if args.app_host:
        problems += app_disk_problems(args.app_host, args.app_path, args.app_min_free_gb)
    if problems:
        say("REFUSED before starting:\n  " + "\n  ".join(problems))
        status.set(final=f"REFUSED before starting: {len(problems)} problems; see the chain's log")
        return 2
    sha = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], capture_output=True, text=True,
                         check=True).stdout.strip()
    say(f"preflight OK: {sha[:12]} on {chain.sources}")
    if args.preflight_only:
        for step in STEPS:
            argv_, env = chain.command(step, args.processes)
            print(f"{step}:", *(f"{k}={v}" for k, v in env.items()), *argv_)
        return 0

    def stop(signum: int, _frame: Any) -> None:
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, stop)
    os.environ.update(PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1", OPENBLAS_NUM_THREADS="1")
    return run_chain(chain, sha=sha, state=state, processes=args.processes, tries=args.tries,
                     start_from=args.start_from, status=status, stall_minutes=args.stall_minutes,
                     stall_cpu=args.stall_cpu_seconds)


if __name__ == "__main__":
    sys.exit(main())
