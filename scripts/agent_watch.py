"""Zero-token watcher for job markers on LXC 137 (docs/ops/parallel-agents.md).

LXC 137 cannot be reached by ssh from Windows; the proxmox MCP server is the
only way in, and it speaks plain HTTP. This script keeps a loop going so an
agent need not: it reads a watch list ON 137 -- one file per wait,
``/root/watch/<anything>.want``, holding one line::

    <who>|<done-marker-path>|<failed-glob>

Every ``--interval`` seconds it makes ONE ``ssh_exec`` call that tests each
``.want`` (done marker exists, or the failed glob matches), renames a ready one
to ``.fired`` on 137 so it never fires twice, and prints one line here::

    READY <who> <done|failed> <path> <utc time>

Nothing else goes to stdout except ``HEARTBEAT <utc>`` at most every 6 hours
(so the reader knows the loop is alive); diagnostics go to stderr. Run it
under the Monitor tool: each stdout line wakes the coordinator, which is why
stdout stays quiet. An MCP or network error is logged and retried next
interval; the loop never dies on one.

The MCP url and headers come from ``mcpServers["proxmox-mcp"]`` in
``~/.claude.json``. The headers are a credential and are never printed.

    uv run python scripts/agent_watch.py            # loop, every 10 minutes
    uv run python scripts/agent_watch.py --once     # one check, then exit
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WATCH_DIR = "/root/watch"
CONTAINER = 137
HEARTBEAT_EVERY = 6 * 3600
PROTOCOL = "2025-03-26"

#: Runs on 137: one pass over the watch list. A ready item is renamed to
#: ``.fired`` BEFORE it is reported, so it can never report twice. The failed
#: glob is expanded unquoted (nullglob: no match -> empty), so it may not
#: contain spaces.
REMOTE_SCRIPT = f"""shopt -s nullglob
mkdir -p {WATCH_DIR}
for f in {WATCH_DIR}/*.want; do
  who=; done=; failed=
  IFS='|' read -r who done failed < "$f" || true
  kind=; path=
  if [ -n "$done" ] && [ -e "$done" ]; then
    kind=done; path=$done
  elif [ -n "$failed" ]; then
    set -- $failed
    if [ -n "$1" ] && [ -e "$1" ]; then kind=failed; path=$1; fi
  fi
  if [ -n "$kind" ]; then
    mv "$f" "${{f%.want}}.fired" && echo "FIRED|$who|$kind|$path"
  fi
done
"""

FIRED = re.compile(r"FIRED\|([^|\r\n\"\\]*)\|(done|failed)\|([^\r\n\"\\]*)")


def build_command() -> str:
    """The one shell command sent to 137 (a quoted heredoc, so nothing expands locally)."""
    return f"bash <<'AGENT_WATCH_EOF'\n{REMOTE_SCRIPT}AGENT_WATCH_EOF\n"


def parse_fired(text: str) -> list[tuple[str, str, str]]:
    """``(who, done|failed, path)`` for every FIRED line in an ssh_exec answer.

    The answer may wrap stdout in JSON (newlines arrive as a literal ``\\n``),
    so escaped newlines are undone first. A line that merely echoes the script
    never matches: the script's own text has ``$kind``, not ``done``/``failed``.
    """
    text = text.replace("\\r", "\n").replace("\\n", "\n")
    return [(who.strip(), kind, path.strip()) for who, kind, path in FIRED.findall(text)]


def ready_line(who: str, kind: str, path: str, now: datetime | None = None) -> str:
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"READY {who} {kind} {path} {stamp}"


def decode_response(body: str) -> list[dict[str, Any]]:
    """JSON-RPC messages from a response body that is plain JSON or SSE ``data:`` lines."""
    body = body.strip()
    if body.startswith("{") or body.startswith("["):
        got = json.loads(body)
        return got if isinstance(got, list) else [got]
    out: list[dict[str, Any]] = []
    for line in body.splitlines():
        if line.startswith("data:") and line[5:].strip():
            try:
                out.append(json.loads(line[5:].strip()))
            except ValueError:
                continue
    return out


def result_text(messages: list[dict[str, Any]]) -> str:
    """The text of a ``tools/call`` result; raises when the server said error."""
    for m in messages:
        if "error" in m:
            raise RuntimeError(f"MCP error: {m['error']}")
        res = m.get("result")
        if isinstance(res, dict) and "content" in res:
            text = "\n".join(c.get("text", "") for c in res["content"] if isinstance(c, dict))
            if res.get("isError"):
                raise RuntimeError(f"ssh_exec failed: {text[:300]}")
            return text
    raise RuntimeError("no tools/call result in the MCP response")


def load_server(config: Path | None = None) -> tuple[str, dict[str, str]]:
    path = config or Path.home() / ".claude.json"
    server = json.loads(path.read_text(encoding="utf-8"))["mcpServers"]["proxmox-mcp"]
    return server["url"], dict(server.get("headers") or {})


def ssh_exec(url: str, headers: dict[str, str], command: str, *, timeout: int = 120) -> str:
    """One ``ssh_exec`` on 137 over MCP's streamable HTTP; returns the output text."""
    import httpx

    base = {**headers, "Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    with httpx.Client(timeout=timeout + 30) as http:
        init = http.post(
            url, headers=base,
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                  "params": {"protocolVersion": PROTOCOL, "capabilities": {},
                             "clientInfo": {"name": "agent_watch", "version": "1"}}},
        )
        init.raise_for_status()
        decode_ok = decode_response(init.text)
        if not any("result" in m for m in decode_ok):
            raise RuntimeError("MCP initialize returned no result")
        session = init.headers.get("mcp-session-id")
        sess = {**base, **({"Mcp-Session-Id": session} if session else {})}
        http.post(url, headers=sess, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        call = http.post(
            url, headers=sess,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                  "params": {"name": "ssh_exec",
                             "arguments": {"container_id": CONTAINER, "command": command, "timeout": timeout}}},
        )
        call.raise_for_status()
        return result_text(decode_response(call.text))


def check_once(url: str, headers: dict[str, str]) -> list[tuple[str, str, str]]:
    return parse_fired(ssh_exec(url, headers, build_command()))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--interval", type=int, default=600, help="seconds between checks (default 600)")
    ap.add_argument("--once", action="store_true", help="check once, then exit")
    args = ap.parse_args(argv)

    url, headers = load_server()
    last_beat = 0.0
    while True:
        try:
            for who, kind, path in check_once(url, headers):
                print(ready_line(who, kind, path), flush=True)
        except Exception as exc:  # the loop outlives any one failure
            print(f"agent_watch: check failed, retrying in {args.interval}s: {type(exc).__name__}: {exc}"[:400],
                  file=sys.stderr, flush=True)
            if args.once:
                return 1
        if args.once:
            return 0
        if time.monotonic() - last_beat >= HEARTBEAT_EVERY or last_beat == 0.0:
            print(f"HEARTBEAT {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}", flush=True)
            last_beat = time.monotonic()
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
