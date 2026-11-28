"""Run one headless Claude Code worker billed to the monthly API credit (FOLLOWUPS 217).

The subscription pays for the coordinator's own session; this pays for work the
coordinator hands off, from the Anthropic API credit, and never lets the month's
spend pass the stop line::

    uv run python scripts/credit_worker.py --name t2-gresham --tier 2 \\
        --budget 8 --brief briefs/t2-gresham.md --cwd ../vicinitideals-worktrees/x

The key is read from ``ANTHROPIC_CREDIT_KEY`` or ``~/.anthropic-credit-key`` and
put into the worker's environment only, so nothing else on the machine is billed
to it. ``--bare`` makes the worker authenticate strictly by that key (no OAuth,
no keychain) and load no MCP servers, so it cannot reach 114, 137 or production.

The ledger (gitignored ``data/flats/credit/ledger.jsonl``) is append-only: a
``start`` row reserves the worker's whole budget, a ``done`` row records what it
really cost. Committed spend = done costs + budgets of workers still running. A
worker whose budget would take committed spend past the stop line is refused.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CREDIT_DIR = ROOT / "data" / "flats" / "credit"
LEDGER = CREDIT_DIR / "ledger.jsonl"
OUT = CREDIT_DIR / "out"
RULES = Path(__file__).with_name("credit_worker_rules.md")
STOP_LINE_USD = 190.0
MODEL = "claude-opus-5-5"
# An allowlist, not a denylist: in print mode anything not listed is refused, so a
# worker cannot push, ssh, deploy or reach the network beyond the model API.
ALLOWED = [
    "Read", "Grep", "Glob", "Edit", "Write",
    "Bash(uv run pytest:*)", "Bash(uv run ruff:*)", "Bash(uv run python -m flats.provenance.fetch:*)", "Bash(uv run python -m flats.encode.crossrefs:*)",
    "Bash(uv run python -m flats.encode.uncited:*)", "Bash(uv run python -m flats.encode.definitions:*)",
    "Bash(uv run python -m flats.encode.glossary:*)", "Bash(uv run python -m flats.encode.words:*)",
    "Bash(uv run python scripts/:*)", "Bash(uv lock:*)", "Bash(uv sync:*)", "Bash(uv tree:*)",
    "Bash(uv pip list:*)",
    "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)", "Bash(git show:*)",
    "Bash(git add:*)", "Bash(git commit:*)", "Bash(git grep:*)",
    "Bash(grep:*)", "Bash(rg:*)", "Bash(ls:*)", "Bash(wc:*)", "Bash(head:*)", "Bash(sed -n:*)",
    "Bash(diff:*)", "Bash(mkdir:*)",
]
# Only what a Windows process needs to start; no tokens, keys or agent sockets inherited.
ENV_KEEP = ("PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "COMSPEC", "WINDIR", "TEMP", "TMP",
            "USERPROFILE", "HOME", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA",
            "PROGRAMDATA", "PROGRAMFILES", "USERNAME", "UV_CACHE_DIR", "LANG")


def _rows() -> list[dict]:
    if not LEDGER.exists():
        return []
    return [json.loads(line) for line in LEDGER.read_text(encoding="utf-8").splitlines() if line.strip()]


def committed(rows: list[dict] | None = None) -> float:
    rows = _rows() if rows is None else rows
    done = {r["id"]: r for r in rows if r["event"] == "done"}
    total = 0.0
    for r in rows:
        if r["event"] == "start":
            total += done[r["id"]]["cost_usd"] if r["id"] in done else r["budget_usd"]
        elif r["event"] == "spend":  # batch jobs or anything billed outside a worker
            total += r["cost_usd"]
    return round(total, 4)


def _append(row: dict) -> None:
    CREDIT_DIR.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def _key() -> str:
    key = os.environ.get("ANTHROPIC_CREDIT_KEY", "").strip()
    if not key:
        path = Path.home() / ".anthropic-credit-key"
        key = path.read_text(encoding="utf-8").strip() if path.exists() else ""
    if not key:
        sys.exit("no credit key: set ANTHROPIC_CREDIT_KEY or write ~/.anthropic-credit-key")
    return key


def status() -> None:
    rows = _rows()
    print(f"committed ${committed(rows):.2f} of stop line ${STOP_LINE_USD:.2f}")
    done = {r["id"]: r for r in rows if r["event"] == "done"}
    for r in rows:
        if r["event"] == "start":
            d = done.get(r["id"])
            state = f"${d['cost_usd']:.2f} {d['outcome']}" if d else f"RUNNING (reserved ${r['budget_usd']:.2f})"
            print(f"  t{r['tier']} {r['name']}: {state}")
        elif r["event"] == "spend":
            print(f"  t{r.get('tier', '?')} {r['name']}: ${r['cost_usd']:.2f} (spend row)")


def run(name: str, tier: int, budget: float, brief: Path, cwd: Path) -> int:
    hold = CREDIT_DIR / "HOLD"  # one worker name per line: refused until the line is removed
    if hold.exists() and name in hold.read_text(encoding="utf-8").split():
        print(f"HELD {name}: listed in {hold}")
        return 4
    spent = committed()
    if spent + budget > STOP_LINE_USD:
        print(f"REFUSED {name}: committed ${spent:.2f} + budget ${budget:.2f} > ${STOP_LINE_USD:.2f}")
        return 3
    claude = shutil.which("claude")
    if not claude:
        sys.exit("claude CLI not on PATH")
    env = {k: v for k, v in os.environ.items() if k.upper() in ENV_KEEP}
    env["ANTHROPIC_API_KEY"] = _key()
    run_id = uuid.uuid4().hex[:12]
    _append({"event": "start", "id": run_id, "name": name, "tier": tier, "budget_usd": budget,
             "brief": str(brief), "cwd": str(cwd), "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    # --bare skips CLAUDE.md discovery, so the project rules travel in the system prompt.
    system = CREDIT_DIR / "system-prompt.md"
    system.write_text((ROOT / "CLAUDE.md").read_text(encoding="utf-8") + "\n\n"
                      + RULES.read_text(encoding="utf-8"), encoding="utf-8")
    cmd = [claude, "-p", "--bare", "--model", MODEL, "--max-budget-usd", str(budget),
           "--output-format", "json", "--permission-mode", "default",
           "--append-system-prompt-file", str(system),
           "--allowedTools", *ALLOWED]
    started = time.time()
    proc = subprocess.run(cmd, input=brief.read_text(encoding="utf-8"), cwd=cwd, env=env,
                          capture_output=True, text=True, encoding="utf-8")
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError:
        result = {"result": proc.stdout[-4000:], "is_error": True, "total_cost_usd": budget}
    # A crash before the cost is known keeps the whole budget reserved: never under-count.
    cost = float(result.get("total_cost_usd", budget))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.md").write_text(str(result.get("result", "")) + "\n\n---\nstderr:\n" + proc.stderr[-4000:],
                                     encoding="utf-8")
    outcome = "error" if result.get("is_error") or proc.returncode else result.get("subtype", "ok")
    _append({"event": "done", "id": run_id, "name": name, "cost_usd": cost, "outcome": outcome,
             "turns": result.get("num_turns"), "minutes": round((time.time() - started) / 60, 1)})
    print(f"{name}: ${cost:.2f} {outcome}; committed now ${committed():.2f}")
    return 0 if outcome != "error" else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--status", action="store_true", help="print the ledger and exit")
    p.add_argument("--name")
    p.add_argument("--tier", type=int, default=3)
    p.add_argument("--budget", type=float, help="USD cap for this worker (--max-budget-usd)")
    p.add_argument("--brief", type=Path)
    p.add_argument("--cwd", type=Path, default=ROOT)
    a = p.parse_args()
    if a.status:
        status()
        return 0
    if not (a.name and a.budget and a.brief):
        p.error("--name, --budget and --brief are required")
    return run(a.name, a.tier, a.budget, a.brief.resolve(), a.cwd.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
