"""The deploy waits for the api's healthcheck before it smokes (FOLLOWUPS 56).

The stub ``docker`` answers ``compose ps -q api`` with a container id and
``inspect`` with the next line of a script of health statuses, repeating the
last line once the script runs out.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "wait-for-api.sh"
DEPLOY = Path(__file__).resolve().parents[2] / "scripts" / "deploy-vicinitideals.sh"

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash"),
]

STUB_DOCKER = """#!/bin/bash
dir="$(dirname "$0")"
if [ "$1" = "compose" ]; then
  echo "${STUB_CONTAINER-abc123}"
  exit 0
fi
if [ "$1" = "inspect" ]; then
  n=$(cat "$dir/calls" 2>/dev/null || echo 0)
  n=$((n + 1))
  echo "$n" > "$dir/calls"
  line=$(sed -n "${n}p" "$dir/statuses")
  [ -z "$line" ] && line=$(tail -n 1 "$dir/statuses")
  echo "$line"
  exit 0
fi
exit 1
"""


def _run(tmp_path: Path, statuses: list[str], *, timeout: int, container: str = "abc123"):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "docker").write_bytes(STUB_DOCKER.replace("\r\n", "\n").encode())
    # Linux skips a non-executable file on PATH and finds the real docker.
    (bindir / "docker").chmod(0o755)
    (bindir / "statuses").write_text("\n".join(statuses) + "\n")
    script = tmp_path / "wait-for-api.sh"
    script.write_bytes(SCRIPT.read_bytes().replace(b"\r\n", b"\n"))
    env = {
        **os.environ,
        "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
        "WAIT_TIMEOUT": str(timeout),
        "WAIT_INTERVAL": "1",
        "STUB_CONTAINER": container,
    }
    result = subprocess.run(
        [shutil.which("bash"), str(script)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    calls = int((bindir / "calls").read_text()) if (bindir / "calls").exists() else 0
    return result, calls


def test_waits_through_starting_then_goes_on(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, ["starting", "starting", "healthy"], timeout=30)
    assert result.returncode == 0, result.stderr
    assert calls == 3
    assert "api is healthy" in result.stdout


def test_gives_up_with_a_clear_message_when_never_healthy(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, ["starting"], timeout=3)
    assert result.returncode == 1
    assert "api not healthy after 3s" in result.stderr
    assert calls >= 3


def test_stops_at_once_when_the_healthcheck_says_unhealthy(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, ["starting", "unhealthy"], timeout=30)
    assert result.returncode == 1
    assert "unhealthy" in result.stderr
    assert calls == 2


def test_waits_when_the_container_does_not_exist_yet(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, ["healthy"], timeout=2, container="")
    assert result.returncode == 1
    assert "no container yet" in result.stderr
    assert calls == 0


def test_deploy_script_waits_instead_of_sleeping() -> None:
    text = DEPLOY.read_text()
    assert "wait-for-api.sh" in text
    assert "sleep 5" not in text
    assert text.index("docker compose up -d") < text.index("wait-for-api.sh")
    assert text.index("wait-for-api.sh") < text.index("post_deploy_smoke.py")
