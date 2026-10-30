"""Local CI gate: run the test suites on this PC before anything is pushed to main.

GitHub CI took ~1.5 h per push on its shared runners (FOLLOWUPS 128); the same
suites run in minutes here. So the gate moved: every push to ``main`` must carry
a pass from this script, and GitHub runs the whole workflow once a day from a
clean checkout (it catches what only works on this PC -- an uncommitted file, a
Windows-only path).

Which suites run depends on what the push changes, at FOLDER level only. A FLATS
answer depends on YAML and text files no per-test tracker can see, so a finer
selection could skip the test that would have caught a wrong colour:

* bookkeeping only (follow-ups, ops notes, agent profiles) -> nothing;
* FLATS side (flats/, Lot Analysis/, data/flats/, scripts/flats_*) -> FLATS +
  quadfit suites + every tests/ file that mentions flats;
* app side (app/, tests/, alembic/, other scripts) -> FLATS suite (two of its
  files import app) + the whole tests/ suite, unit and integration;
* anything unclassified -> everything.

E2E is not run here: the app is not served locally, each change already runs its
E2E files against production after deploy, and the daily GitHub run covers the
full E2E suite.

Usage::

    python scripts/ci_local.py              # gate HEAD vs origin/main, stamp on pass
    python scripts/ci_local.py --all        # every suite regardless of scope
    python scripts/ci_local.py daily        # last daily GitHub run, red is loud
    python scripts/ci_local.py check-push   # git pre-push hook (reads stdin)
    python scripts/ci_local.py install-hook # write .git/hooks/pre-push

Stamps live in the shared git dir (``<git-common-dir>/ci_local/``), so every
worktree sees them. Stdlib only: the hook runs with whatever ``python`` is on PATH.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ZERO = "0" * 40

#: Paths no test reads. A push touching only these needs no gate.
BOOKKEEPING_PREFIXES: tuple[str, ...] = (
    ".claude/",
    ".github/skills/",
    "docs/",
)
#: docs/ files that tests DO read (tests/docs/, tests/engines/, tests/exporters/).
DOCS_READ_BY_TESTS: tuple[str, ...] = (
    "docs/DATA_MODEL.md",
    "docs/FINANCIAL_MODEL.md",
    "docs/feature-plans/",
)
BOOKKEEPING_FILES: tuple[str, ...] = (".gitignore", "LICENSE")

FLATS_SIDE: tuple[str, ...] = (
    "flats/",
    "Lot Analysis/",
    "data/flats/",
    "scripts/flats_",
    "scripts/check_flats_firewall.py",
)
APP_SIDE: tuple[str, ...] = (
    "app/",
    "tests/",
    "alembic/",
    "alembic.ini",
    "scripts/",
) + DOCS_READ_BY_TESTS

SUITES = ("ruff", "firewall", "flats", "quadfit", "app_flats", "app_all")


def git(*args: str, check: bool = True) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=check
    ).stdout.strip()


def repo_root() -> Path:
    return Path(git("rev-parse", "--show-toplevel"))


def stamp_dir() -> Path:
    common = Path(git("rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = (Path.cwd() / common).resolve()
    d = common / "ci_local"
    (d / "logs").mkdir(parents=True, exist_ok=True)
    return d


def _norm(p: str) -> str:
    return p.replace("\\", "/").strip().strip('"')


def side(path: str) -> str:
    """'book', 'flats', 'app' or 'shared' for one changed path."""
    p = _norm(path)
    if any(p.startswith(d) for d in DOCS_READ_BY_TESTS):
        return "app"
    if p in BOOKKEEPING_FILES or any(p.startswith(b) for b in BOOKKEEPING_PREFIXES):
        return "book"
    if "/" not in p and p.endswith(".md"):
        return "book"
    if any(p.startswith(f) for f in FLATS_SIDE):
        return "flats"
    if any(p.startswith(a) for a in APP_SIDE):
        return "app"
    return "shared"


def suites_for(files: list[str]) -> set[str]:
    sides = {side(f) for f in files}
    sides.discard("book")
    if not sides:
        return set()
    need = {"ruff", "firewall"}
    if "shared" in sides:
        return set(SUITES) - {"app_flats"}
    if "flats" in sides:
        need |= {"flats", "quadfit", "app_flats"}
    if "app" in sides:
        need |= {"flats", "app_all"}
        need.discard("app_flats")
    return need


def covers(have: set[str], need: set[str]) -> bool:
    """True if a stamp's suites satisfy what a push needs."""
    if "app_all" in have:
        have = have | {"app_flats"}
    return need <= have


def changed(base: str, head: str = "HEAD") -> list[str]:
    out = git("diff", "--name-only", f"{base}...{head}", check=False)
    if not out:
        out = git("diff", "--name-only", base, head, check=False)
    return [_norm(x) for x in out.splitlines() if x.strip()]


def flats_test_files(root: Path) -> list[str]:
    """tests/ files (not e2e) that mention flats -- the app tests a FLATS change can reach."""
    hits = []
    for path in sorted((root / "tests").rglob("test_*.py")):
        rel = path.relative_to(root).as_posix()
        if rel.startswith("tests/e2e/"):
            continue
        if "flats" in path.read_text(encoding="utf-8", errors="ignore"):
            hits.append(rel)
    return hits


def commands(root: Path, base: str, need: set[str]) -> dict[str, list[str]]:
    uv = ["uv", "run", "--no-sync"]
    cmds = {
        "ruff": uv + ["ruff", "check", "app/", "tests/", "flats/", "scripts/"],
        "firewall": uv + ["python", "scripts/check_flats_firewall.py", "--base", base],
        "flats": uv + ["pytest", "flats/tests", "-q", "-n", "auto", "-p", "no:cacheprovider"],
        "quadfit": uv + ["pytest", "Lot Analysis/quadfit/tests", "-q", "-n", "auto",
                         "-p", "no:cacheprovider"],
        "app_all": uv + ["pytest", "tests/", "-q", "-rs", "--timeout=120",
                         "--ignore=tests/e2e", "-p", "no:cacheprovider"],
    }
    if "app_flats" in need:
        cmds["app_flats"] = uv + ["pytest", "-q", "-rs", "--timeout=120",
                                  "-p", "no:cacheprovider", *flats_test_files(root)]
    return {k: v for k, v in cmds.items() if k in need}


def dirty_code(root: Path) -> list[str]:
    out = git("status", "--porcelain", "--untracked-files=no", check=False)
    files = [_norm(line[3:].split(" -> ")[-1]) for line in out.splitlines() if line.strip()]
    return [f for f in files if side(f) != "book"]


def run_gate(args: argparse.Namespace) -> int:
    root = repo_root()
    os.chdir(root)
    dirty = dirty_code(root)
    if dirty:
        print("ci_local: uncommitted code changes -- commit them first, the stamp is for HEAD:")
        print("  " + "\n  ".join(dirty[:20]))
        return 2
    git("fetch", "-q", "origin", "main", check=False)
    base = args.base
    head = git("rev-parse", "HEAD")
    files = changed(base)
    need = set(SUITES) - {"app_flats"} if args.all else suites_for(files)
    if not need:
        print(f"ci_local: {len(files)} changed file(s) vs {base}, all bookkeeping -- nothing to run.")
        write_stamp(head, need, {}, base, files)
        return 0
    cmds = commands(root, base, need)
    logs = stamp_dir() / "logs"
    print(f"ci_local: {head[:8]} vs {base} -- {len(files)} file(s); running {', '.join(sorted(cmds))}")

    # The app suite is DB-bound and serial; the FLATS suites are CPU-bound and
    # sharded. Run the app suite alongside the rest instead of after it.
    results: dict[str, dict] = {}
    procs: dict[str, tuple[subprocess.Popen, float, Path]] = {}
    for name in ("app_all", "app_flats"):
        if name in cmds:
            log = logs / f"{head[:8]}-{name}.log"
            procs[name] = (subprocess.Popen(cmds[name], stdout=log.open("w", encoding="utf-8"),
                                            stderr=subprocess.STDOUT), time.time(), log)
    for name in ("ruff", "firewall", "flats", "quadfit"):
        if name not in cmds:
            continue
        log = logs / f"{head[:8]}-{name}.log"
        t0 = time.time()
        with log.open("w", encoding="utf-8") as fh:
            rc = subprocess.run(cmds[name], stdout=fh, stderr=subprocess.STDOUT).returncode
        results[name] = report(name, rc, time.time() - t0, log)
    for name, (proc, t0, log) in procs.items():
        rc = proc.wait()
        results[name] = report(name, rc, time.time() - t0, log)

    failed = [n for n, r in results.items() if r["rc"] != 0]
    if failed:
        print(f"ci_local: FAILED {', '.join(failed)} -- no stamp written; do not push.")
        for n in failed:
            tail = results[n]["log"].read_text(encoding="utf-8", errors="ignore").splitlines()[-30:]
            print(f"--- {n} (last 30 lines of {results[n]['log']}) ---")
            print("\n".join(tail))
        return 1
    write_stamp(head, need, {n: round(r["secs"]) for n, r in results.items()}, base, files)
    print(f"ci_local: PASSED -- stamp written for {head[:8]}; safe to push.")
    return 0


def report(name: str, rc: int, secs: float, log: Path) -> dict:
    last = ""
    lines = log.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
    if lines:
        last = lines[-1][:110]
    print(f"  {'ok  ' if rc == 0 else 'FAIL'} {name:<9} {secs:6.0f}s  {last}")
    return {"rc": rc, "secs": secs, "log": log}


def write_stamp(head: str, suites: set[str], secs: dict, base: str, files: list[str]) -> None:
    rec = {
        "sha": head,
        "suites": sorted(suites),
        "seconds": secs,
        "base": base,
        "base_sha": git("rev-parse", base, check=False),
        "files": len(files),
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (stamp_dir() / f"{head}.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")


def load_stamp(sha: str) -> dict | None:
    p = stamp_dir() / f"{sha}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None


def check_push(_: argparse.Namespace) -> int:
    """pre-push hook: a push to main needs a passing stamp covering its changes."""
    blocked = False
    for line in sys.stdin.read().splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        _local_ref, local_sha, remote_ref, remote_sha = parts
        if remote_ref != "refs/heads/main" or local_sha == ZERO:
            continue
        base = remote_sha if remote_sha != ZERO else "origin/main"
        need = suites_for(changed(base, local_sha))
        if not need:
            print("ci_local: push is bookkeeping only -- no tests needed.")
            continue
        # The newest stamped commit on the pushed line, with only bookkeeping after it.
        stamped = None
        for sha in git("rev-list", "--max-count=40", local_sha).splitlines():
            st = load_stamp(sha)
            if st is not None:
                stamped = st
                break
        ok = False
        if stamped is not None:
            after = suites_for(changed(stamped["sha"], local_sha))
            before = suites_for(changed(base, stamped["sha"]))
            ok = not after and covers(set(stamped["suites"]), before)
        if ok:
            print(f"ci_local: push covered by the local pass on {stamped['sha'][:8]} "
                  f"({', '.join(stamped['suites']) or 'bookkeeping'}).")
        else:
            blocked = True
            print("ci_local: PUSH TO MAIN BLOCKED -- no local test pass covers it.")
            print(f"  needs: {', '.join(sorted(need))}")
            print("  run:   uv run python scripts/ci_local.py   (then push again)")
    daily(argparse.Namespace(session=False), quiet_green=True)
    return 1 if blocked else 0


def daily(args: argparse.Namespace, quiet_green: bool = False) -> int:
    """Report the newest finished daily (or manual) GitHub run. Red is loud."""
    if shutil.which("gh") is None:
        print("Daily GitHub CI: status unknown (gh not installed).")
        return 0
    try:
        out = subprocess.run(
            ["gh", "run", "list", "--workflow", "ci.yml", "--limit", "20", "--json",
             "databaseId,event,status,conclusion,headSha,createdAt,url"],
            capture_output=True, text=True, timeout=12,
        ).stdout
        runs = json.loads(out or "[]")
    except (subprocess.TimeoutExpired, ValueError, OSError):
        print("Daily GitHub CI: status unknown (gh did not answer).")
        return 0
    runs = [r for r in runs if r.get("event") in ("schedule", "workflow_dispatch")]
    done = [r for r in runs if r.get("status") == "completed"]
    if not done:
        print("Daily GitHub CI: no daily run has finished yet.")
        return 0
    r = done[0]
    when = datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00"))
    age_h = (datetime.now(timezone.utc) - when).total_seconds() / 3600
    stamp = f"{r['headSha'][:8]}, {when:%Y-%m-%d %H:%M} UTC"
    if r.get("conclusion") != "success":
        jobs = ""
        try:
            j = subprocess.run(["gh", "run", "view", str(r["databaseId"]), "--json", "jobs"],
                               capture_output=True, text=True, timeout=12).stdout
            bad = [x["name"] for x in json.loads(j).get("jobs", [])
                   if x.get("conclusion") not in ("success", "skipped")]
            jobs = "; failed: " + ", ".join(bad) if bad else ""
        except (subprocess.TimeoutExpired, ValueError, OSError):
            pass
        print(f"!!! DAILY GITHUB CI IS RED ({r.get('conclusion')}, {stamp}{jobs}).")
        print(f"!!! Fix it before other work, then re-run: gh workflow run ci.yml. {r['url']}")
        return 0
    if age_h > 30:
        print(f"!!! Daily GitHub CI has not finished a run since {stamp} ({age_h:.0f} h). "
              "Check the schedule: gh workflow view ci.yml")
        return 0
    if not quiet_green:
        print(f"Daily GitHub CI: green ({stamp}).")
    return 0


HOOK = """#!/bin/sh
# Installed by scripts/ci_local.py install-hook (FOLLOWUPS 128): a push to main
# needs a local test pass. Older worktrees without the script use main's copy.
script=scripts/ci_local.py
[ -f "$script" ] || script="$(git rev-parse --git-common-dir)/../scripts/ci_local.py"
exec python "$script" check-push "$@"
"""


def install_hook(_: argparse.Namespace) -> int:
    hooks = git("config", "--get", "core.hooksPath", check=False) or str(
        Path(git("rev-parse", "--git-common-dir")) / "hooks")
    path = Path(hooks) / "pre-push"
    if path.exists() and "ci_local" not in path.read_text(encoding="utf-8", errors="ignore"):
        print(f"ci_local: {path} exists and is not ours -- not overwriting.")
        return 1
    path.write_text(HOOK, encoding="utf-8", newline="\n")
    path.chmod(0o755)
    print(f"ci_local: pre-push hook written to {path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="origin/main", help="What the push is compared against.")
    ap.add_argument("--all", action="store_true", help="Run every suite regardless of scope.")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("check-push")
    d = sub.add_parser("daily")
    d.add_argument("--session", action="store_true")
    sub.add_parser("install-hook")
    args = ap.parse_args()
    if args.cmd == "check-push":
        return check_push(args)
    if args.cmd == "daily":
        return daily(args)
    if args.cmd == "install-hook":
        return install_hook(args)
    return run_gate(args)


if __name__ == "__main__":
    sys.exit(main())
