"""``scripts/flats_weekly_chain.py`` -- the weekly re-screen that survives the night (FOLLOWUPS 48).

What must hold: a re-launch skips every step already done and runs the rest;
a step that died for a passing reason (a signal, a lot that killed its worker
twice, a stall) runs again -- the bridge with half the processes after a
memory death -- and one that failed on its own terms does not; it gives up
after its tries with a status line that says where; only the step's own
process group is ever signalled; and a run refuses in seconds, not hours,
when the code, the snapshot, the elevation tiles or the disk are wrong.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "flats_weekly_chain.py"
LINUX = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="process groups and /proc are Linux's")


@pytest.fixture(scope="module")
def wc():
    spec = importlib.util.spec_from_file_location("flats_weekly_chain", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _chain(wc, tmp_path: Path, **more):
    return wc.Chain("2026-10-07", "2026-10-07_weekly", tmp_path / "data", tmp_path / "work",
                    tmp_path / "sources", tmp_path / "raw", **more)


# --- the commands -----------------------------------------------------------------------


def test_each_step_runs_the_command_the_runbook_names(wc, tmp_path) -> None:
    chain = _chain(wc, tmp_path, snapshot_date="2026-10-01")
    argv, env = chain.command("bridge", 8)
    assert argv[1:3] == ["-m", "flats.ingest.quadfit"]
    assert argv[argv.index("--processes") + 1] == "8" and argv[argv.index("--chunk-size") + 1] == "250"
    # the cache is named, so a tree whose bridge does not keep one unasked resumes too
    assert argv[argv.index("--cache") + 1] == str(tmp_path / "work" / "bridge_cache")
    assert argv[argv.index("--out") + 1] == str(tmp_path / "work" / "bridge_2026-10-07_weekly")
    assert argv[argv.index("--sources") + 1] == str(tmp_path / "sources" / "2026-10-07") and env == {}
    _, env = chain.command("quadfit", 8)
    assert env == {"QUADFIT_DATA_DIR": str(tmp_path / "data" / "quadfit_2026-10-07_weekly")}
    assert "--reuse" not in chain.command("transit", 8)[0]
    reuse = _chain(wc, tmp_path, transit_reuse=tmp_path / "d.parquet").command("transit", 8)[0]
    assert reuse[reuse.index("--reuse") + 1] == str(tmp_path / "d.parquet")
    assign = chain.command("assign", 8)[0]
    assert assign[assign.index("--snapshot-date") + 1] == "2026-10-01"
    assert all(chain.command(step, 8) for step in wc.STEPS)
    with pytest.raises(ValueError):
        chain.command("promote", 8)


# --- what a failed try leads to ------------------------------------------------------------


def test_a_memory_death_retries_the_bridge_with_half_the_processes(wc) -> None:
    again = wc.Attempt(1, tail="RuntimeError: bridge: lot X at 9.0 acres killed its worker again, running alone")
    assert wc.next_move("bridge", again, 16) == ("retry", 8)
    assert wc.next_move("bridge", again, 3) == ("retry", 2)
    assert wc.next_move("bridge", again, 2) == ("retry", 2)
    assert wc.next_move("bridge", wc.Attempt(-9), 16) == ("retry", 8)
    assert wc.next_move("bridge", wc.Attempt(1, oom=True), 16) == ("retry", 8)
    assert wc.next_move("quadfit", wc.Attempt(-9), 16) == ("retry", 16)


def test_a_failure_of_the_steps_own_is_not_retried(wc) -> None:
    # a run that lived through one worker death says "killed for memory?" and
    # may then fail for another reason: that is not a memory death
    tail = "bridge: a worker died (killed for memory?) screening X\nTraceback ...\nKeyError: 'rules'"
    assert wc.next_move("bridge", wc.Attempt(1, tail=tail), 16) == ("give up", 16)
    assert wc.next_move("assign", wc.Attempt(2), 16) == ("give up", 16)


def test_a_stall_retries_with_the_same_processes_and_a_clean_exit_is_done(wc) -> None:
    assert wc.next_move("bridge", wc.Attempt(-15, stalled=True), 16) == ("retry", 16)
    assert wc.next_move("bridge", wc.Attempt(0), 16) == ("done", 16)


# --- the stall watch -----------------------------------------------------------------------


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_a_step_is_stalled_only_after_a_whole_window_without_cpu(wc) -> None:
    clock, ticks = _Clock(), {(10, 1): 0}
    watch = wc.Watch(10, minutes=2, cpu_seconds=5, sample=lambda pgid: dict(ticks), clock=clock, tick=100)
    for _ in range(20):  # working: 30 CPU-seconds a minute
        clock.t += 30
        ticks[(10, 1)] += 1500
        assert not watch.stalled()
    for minute in (0.5, 1.0, 1.5):  # hung: nothing more
        clock.t += 30
        assert not watch.stalled(), minute
    clock.t += 30
    assert watch.stalled()


def test_cpu_moves_from_a_dead_worker_to_a_new_one_without_a_stall(wc) -> None:
    # a worker ends and a fresh one starts: the fresh one's CPU is progress,
    # and the dead one's vanishing is not taken as negative
    clock, ticks = _Clock(), {(10, 1): 900, (11, 5): 4000}
    watch = wc.Watch(10, minutes=1, cpu_seconds=5, sample=lambda pgid: dict(ticks), clock=clock, tick=100)
    watch.stalled()
    for step in range(10):
        clock.t += 20
        del ticks[next(k for k in ticks if k[0] != 10)]
        ticks[(12 + step, 9)] = 1000
        assert not watch.stalled()


def test_without_proc_nothing_is_ever_a_stall(wc) -> None:
    clock = _Clock()
    watch = wc.Watch(10, minutes=0, cpu_seconds=5, sample=lambda pgid: None, clock=clock)
    clock.t += 3600
    assert not watch.stalled()


# --- the chain ----------------------------------------------------------------------------


def _script(wc, tmp_path: Path, plan: dict[str, list[str]]):
    """A command per step that notes it ran (``ran``) and does what ``plan``
    says for that step's next try: an exit code, ``memory`` (the bridge's
    words and exit 1), ``kill`` (SIGKILL itself) or ``hang`` (sleep, with a
    child in its group that sleeps too, noting the child's pid)."""
    ran = tmp_path / "ran"

    def command(step: str, processes: int):
        what = plan.get(step, []).pop(0) if plan.get(step) else "0"
        code = [f"open({str(ran)!r}, 'a').write({step!r} + ' {processes}\\n')"]
        if what == "memory":
            code.append("print('RuntimeError: bridge: lot T1 at 9.0 acres killed its worker again')")
            code.append("raise SystemExit(1)")
        elif what == "kill":
            code.append("import os, signal; os.kill(os.getpid(), signal.SIGKILL)")
        elif what == "hang":
            code.append("import subprocess, time")
            code.append(f"p = subprocess.Popen(['sleep', '300']); open({str(tmp_path / 'child')!r}, 'w').write(str(p.pid))")
            code.append("time.sleep(300)")
        else:
            code.append(f"raise SystemExit({int(what)})")
        return [sys.executable, "-c", "; ".join(code) if what != "hang" else "\n".join(code)], {}

    return command


def _run(wc, tmp_path: Path, plan: dict[str, list[str]], *, sha: str = "aaaaaaa1", start_from=None,
         stall_minutes: float = 60.0, tries: int = 3, gated: bool = False) -> int:
    chain = _chain(wc, tmp_path)
    state = tmp_path / "state"
    status = wc.Status(state / "status.txt", chain, sha, every=3600)
    return wc.run_chain(chain, sha=sha, state=state, processes=16, tries=tries, start_from=start_from,
                        status=status, stall_minutes=stall_minutes, stall_cpu=0.5, poll=0.2,
                        command=_script(wc, tmp_path, plan), gate=chain.gate if gated else None)


def _ran(tmp_path: Path) -> list[str]:
    path = tmp_path / "ran"
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def _final(tmp_path: Path) -> str:
    return (tmp_path / "state" / "status.txt").read_text(encoding="utf-8").splitlines()[-1]


@pytest.mark.timeout(120)
def test_a_relaunch_runs_only_the_steps_not_yet_done(wc, tmp_path) -> None:
    assert _run(wc, tmp_path, {"bridge": ["1"]}) == 1
    assert _final(tmp_path).startswith("GAVE UP at bridge after 1 try (exit 1)")
    assert "re-launch the same command (less any --from)" in _final(tmp_path)
    assert [line.split()[0] for line in _ran(tmp_path)] == list(wc.STEPS[:6])
    assert _run(wc, tmp_path, {}) == 0
    assert [line.split()[0] for line in _ran(tmp_path)] == [*wc.STEPS[:6], *wc.STEPS[5:]]
    assert _final(tmp_path).startswith("WEEKLY CHAIN DONE")
    summary = json.loads((tmp_path / "state" / "chain.json").read_text(encoding="utf-8"))
    assert list(summary) == list(wc.STEPS) and summary["bridge"]["processes"] == 16
    assert "DONE " + " ".join(wc.STEPS) in (tmp_path / "state" / "status.txt").read_text(encoding="utf-8")
    assert _run(wc, tmp_path, {}) == 0 and len(_ran(tmp_path)) == 6 + 3  # nothing left to run


@pytest.mark.timeout(120)
def test_a_bridge_that_runs_out_of_memory_runs_again_on_half_the_processes(wc, tmp_path) -> None:
    assert _run(wc, tmp_path, {"bridge": ["memory", "memory", "0"]}) == 0
    assert [line for line in _ran(tmp_path) if line.startswith("bridge")] == ["bridge 16", "bridge 8", "bridge 4"]
    mark = json.loads((tmp_path / "state" / "bridge.done").read_text(encoding="utf-8"))
    assert mark["tries"] == 3 and mark["processes"] == 4
    assert "killed its worker again" in (tmp_path / "state" / "bridge.log").read_text(encoding="utf-8")


@pytest.mark.timeout(120)
def test_a_step_gives_up_after_its_tries(wc, tmp_path) -> None:
    assert _run(wc, tmp_path, {"bridge": ["memory"] * 3}) == 1
    assert [line for line in _ran(tmp_path) if line.startswith("bridge")] == ["bridge 16", "bridge 8", "bridge 4"]
    assert _final(tmp_path).startswith("GAVE UP at bridge after 3 tries (exit 1)")
    assert not (tmp_path / "state" / "bridge.done").exists() and (tmp_path / "state" / "transit.done").exists()


@pytest.mark.timeout(120)
def test_from_a_step_runs_it_and_every_later_one_again(wc, tmp_path) -> None:
    assert _run(wc, tmp_path, {}) == 0
    assert _run(wc, tmp_path, {}, start_from="assign") == 0
    assert [line.split()[0] for line in _ran(tmp_path)][len(wc.STEPS):] == ["assign", "export"]


@pytest.mark.timeout(120)
def test_steps_done_at_other_code_are_not_taken_unasked(wc, tmp_path) -> None:
    assert _run(wc, tmp_path, {}, sha="aaaaaaa1") == 0
    assert _run(wc, tmp_path, {}, sha="bbbbbbb2") == 2
    assert len(_ran(tmp_path)) == len(wc.STEPS) and _final(tmp_path).startswith("REFUSED")
    # the operator says which steps the change touches: the earlier ones are kept
    assert _run(wc, tmp_path, {}, sha="bbbbbbb2", start_from="bridge") == 0
    assert [line.split()[0] for line in _ran(tmp_path)][len(wc.STEPS):] == ["bridge", "assign", "export"]
    # ... and a plain re-launch takes them too; a longer or shorter form of
    # the same commit is the same commit
    assert _run(wc, tmp_path, {}, sha="bbbbbbb2c0ffee") == 0 and len(_ran(tmp_path)) == len(wc.STEPS) + 3
    assert _run(wc, tmp_path, {}, sha="ccccccc3") == 2 and _final(tmp_path).startswith("REFUSED")


# --- gates: what a kept step left ------------------------------------------------------------


def _overlay_keys(wc) -> list[str]:
    import yaml

    return [o["key"] for o in yaml.safe_load(wc.OVERLAYS.read_text(encoding="utf-8"))["overlays"]]


def _parquet(path: Path, columns) -> Path:
    import pyarrow as pa
    import pyarrow.parquet as pq

    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table({c: [1] for c in columns}), path)
    return path


def test_the_bridge_wants_a_column_for_every_overlay_quadfit_declares(wc, tmp_path) -> None:
    keys = _overlay_keys(wc)
    twins = [k for k in keys if k.endswith("_site")]
    assert twins  # FOLLOWUPS 50's water flags, the columns the 2026-10-07 weekly's s5o lacks
    s5o = _parquet(tmp_path / "s5o_lots.parquet", ["TLID", *(f"ovl_{k}" for k in keys), *(f"ovl_{k}_sqft" for k in keys)])
    assert wc.overlay_problems(s5o) == []
    _parquet(s5o, ["TLID", *(f"ovl_{k}" for k in keys if k not in twins)])
    said = wc.overlay_problems(s5o)
    assert len(said) == 1 and f"no column for {len(twins)} of the {len(keys)} overlays" in said[0]
    assert all(t in said[0] for t in twins) and "--from quadfit" in said[0]
    assert "no s5o file" in wc.overlay_problems(tmp_path / "none.parquet")[0]


def test_the_roll_rule_wants_every_county_roll_column(wc, tmp_path) -> None:
    from flats.ingest.institutional import ROLL_COLUMNS

    lots = _parquet(tmp_path / "lots.parquet", ROLL_COLUMNS)
    assert wc.roll_problems(lots) == []
    _parquet(lots, [c for c in ROLL_COLUMNS if c != "YEARBUILT"])
    said = wc.roll_problems(lots)
    assert len(said) == 1 and "no county-roll column YEARBUILT" in said[0] and "--from normalize" in said[0]
    assert "no lot table" in wc.roll_problems(tmp_path / "none.parquet")[0]


@pytest.mark.timeout(120)
def test_a_measurement_kept_from_older_code_stops_the_chain_before_the_bridge(wc, tmp_path) -> None:
    from flats.ingest.institutional import ROLL_COLUMNS

    chain = _chain(wc, tmp_path)
    keys = _overlay_keys(wc)
    _parquet(chain.flats("normalized") / "lots.parquet", ROLL_COLUMNS)
    s5o = _parquet(chain.quadfit / "s5o_lots.parquet", [f"ovl_{k}" for k in keys if not k.endswith("_site")])
    assert _run(wc, tmp_path, {}, gated=True) == 2
    before = list(wc.STEPS[:wc.STEPS.index("bridge")])
    assert [line.split()[0] for line in _ran(tmp_path)] == before
    assert _final(tmp_path).startswith("REFUSED before bridge: ") and "_site" in _final(tmp_path)
    assert not (tmp_path / "state" / "bridge.done").exists()
    # quadfit run again at this code writes the columns; the same line goes on
    _parquet(s5o, [f"ovl_{k}" for k in keys])
    assert _run(wc, tmp_path, {}, gated=True) == 0
    assert [line.split()[0] for line in _ran(tmp_path)] == list(wc.STEPS)


@pytest.mark.timeout(120)
def test_a_lot_table_without_the_roll_stops_the_chain_before_institutional_land(wc, tmp_path) -> None:
    from flats.ingest.institutional import ROLL_COLUMNS

    chain = _chain(wc, tmp_path)
    _parquet(chain.flats("normalized") / "lots.parquet", [c for c in ROLL_COLUMNS if c != "PROP_CODE"])
    assert _run(wc, tmp_path, {}, gated=True) == 2
    assert [line.split()[0] for line in _ran(tmp_path)] == ["stage", "quadfit", "normalize"]
    assert _final(tmp_path).startswith("REFUSED before institutional: ") and "PROP_CODE" in _final(tmp_path)


@LINUX
@pytest.mark.timeout(120)
def test_a_step_killed_by_a_signal_runs_again(wc, tmp_path) -> None:
    assert _run(wc, tmp_path, {"normalize": ["kill"], "bridge": ["kill"]}) == 0
    ran = _ran(tmp_path)
    assert ran.count("normalize 16") == 2 and [r for r in ran if r.startswith("bridge")] == ["bridge 16", "bridge 8"]


def _gone(pid: int) -> bool:
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except OSError:
        return True
    return state == "Z"


@LINUX
@pytest.mark.timeout(120)
def test_a_stalled_step_is_ended_with_its_whole_group_and_run_again(wc, tmp_path) -> None:
    t0 = time.monotonic()
    assert _run(wc, tmp_path, {"institutional": ["hang", "0"]}, stall_minutes=0.05) == 0
    assert _ran(tmp_path).count("institutional 16") == 2 and time.monotonic() - t0 < 60
    child = int((tmp_path / "child").read_text())
    for _ in range(50):
        if _gone(child):
            break
        time.sleep(0.1)
    assert _gone(child), "the step's child outlived the stall"


@LINUX
@pytest.mark.timeout(60)
def test_the_groups_cpu_is_read_from_proc(wc) -> None:
    busy = subprocess.Popen([sys.executable, "-c", "while True: pass"], start_new_session=True)
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            got = wc.group_cpu(busy.pid)
            if got and sum(got.values()) > 0:
                break
            time.sleep(0.2)
        assert got and {pid for pid, _ in got} == {busy.pid} and sum(got.values()) > 0
        assert wc.group_cpu(os.getpgrp()) and busy.pid not in {pid for pid, _ in wc.group_cpu(os.getpgrp())}
    finally:
        t0 = time.monotonic()
        wc.end_group(busy.pid, grace=5)
        ended = time.monotonic() - t0
        busy.wait(timeout=10)
    # busy is a zombie until the wait: end_group must not take it for alive
    assert busy.returncode < 0 and not wc.group_cpu(busy.pid) and ended < 3


# --- preflight ------------------------------------------------------------------------------


def _snapshot(tmp_path: Path):
    from flats.ingest.acquire import _spec_sha
    from flats.ingest.sources import load_pipeline

    pipeline = load_pipeline()
    snap = tmp_path / "sources" / "2026-10-07"
    snap.mkdir(parents=True)
    datasets = {}
    for key, ds in pipeline.datasets.items():
        path = snap / f"{key}.geojson"
        path.write_text('{"type": "FeatureCollection", "features": []}', encoding="utf-8")
        datasets[key] = {"status": "acquired", "file": path.name, "bytes": path.stat().st_size,
                         "spec_sha256": _spec_sha(ds)}
    (snap / "manifest.json").write_text(json.dumps({"snapshot": snap.name, "datasets": datasets}), encoding="utf-8")
    dem = tmp_path / "raw"
    (dem / "dem").mkdir(parents=True)
    (dem / "dem" / "tile.tif").write_bytes(b"\0")
    (dem / "dem10_utm").mkdir()
    return snap, dem, pipeline, datasets


def test_a_snapshot_holding_every_registered_dataset_passes(wc, tmp_path) -> None:
    snap, dem, pipeline, _ = _snapshot(tmp_path)
    assert wc.snapshot_problems(snap, dem, pipeline) == []


def test_the_preflight_names_what_the_snapshot_lacks(wc, tmp_path) -> None:
    from flats.geom import curbs

    snap, dem, pipeline, datasets = _snapshot(tmp_path)
    spare = [k for k in sorted(datasets) if k not in {*wc.INSTITUTIONAL_KEYS, *curbs.CURB_KEYS, *curbs.WIDTH_KEYS}
             and not k.startswith(("rlis_taxlots", "rlis_streets", "rlis_zoning", "ugb"))]
    gone, older = spare[:2], spare[2]
    for key in gone:
        del datasets[key]
    datasets[older]["spec_sha256"] = "0" * 64
    datasets["osm_land_use"]["status"] = "failed"
    (snap / datasets[curbs.CURB_KEYS[0]]["file"]).unlink()
    (snap / "manifest.json").write_text(json.dumps({"snapshot": snap.name, "datasets": datasets}), encoding="utf-8")
    for tile in (dem / "dem").glob("*.tif"):
        tile.unlink()
    notes: list[str] = []
    said = "\n".join(wc.snapshot_problems(snap, dem, pipeline, notes=notes))
    assert "2 registered datasets are not in the snapshot: python -m flats.ingest.acquire --snapshot 2026-10-07" in said
    assert ",".join(gone) in said
    # a dataset fetched under an older registry entry is noted, not refused:
    # a re-screen reads the ground the copy in use was measured from
    assert "older pipeline.yaml" not in said and len(notes) == 1
    assert notes[0].endswith(f"--snapshot 2026-10-07 --root {snap.parent} --keys {older} --force")
    assert "osm_land_use: institutional land needs it" in said
    assert f"curb datasets missing (the bridge refuses without them): {curbs.CURB_KEYS[0]}" in said
    assert "no 1 m elevation tiles" in said
    assert wc.snapshot_problems(tmp_path / "sources" / "2026-10-08", dem, pipeline) == [
        f"{tmp_path / 'sources' / '2026-10-08'}: no snapshot"]


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def test_the_preflight_wants_the_code_at_the_sha_and_clean(wc, tmp_path) -> None:
    repo = tmp_path / "repo"
    (repo / "flats").mkdir(parents=True)
    (repo / "flats" / "x.py").write_text("x = 1\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "x")
    head = _git(repo, "rev-parse", "HEAD")
    assert wc.code_problems(repo, head[:8]) == []
    assert "not deadbee" in wc.code_problems(repo, "deadbeef")[0]
    assert "at least 7" in wc.code_problems(repo, head[:5])[0]
    (repo / "flats" / "x.py").write_text("x = 2\n", encoding="utf-8")
    (repo / "notes.txt").write_text("not the screen's\n", encoding="utf-8")
    said = wc.code_problems(repo, head[:8])
    assert len(said) == 1 and "uncommitted" in said[0] and "x.py" in said[0] and "notes" not in said[0]


def test_the_preflight_wants_the_disk(wc, tmp_path) -> None:
    assert wc.disk_problems([("here", tmp_path / "not" / "yet", 0.0)]) == []
    said = wc.disk_problems([("here", tmp_path, 1e9)])
    assert len(said) == 1 and said[0].startswith("disk: ") and "1e+09 GB wanted" in said[0]
