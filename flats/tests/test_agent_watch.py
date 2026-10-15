"""``scripts/agent_watch.py`` -- the zero-token watcher for 137 job markers.

No network: the command it sends, the way it reads the answer (plain JSON or SSE,
newlines raw or escaped) and the one line it prints. The shell script it sends is
also run here, on a temp directory, where bash exists.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "agent_watch.py"


@pytest.fixture(scope="module")
def aw():
    spec = importlib.util.spec_from_file_location("agent_watch", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_the_answer_is_read_whatever_wraps_it(aw) -> None:
    raw = "FIRED|e0|done|/root/r2r_work/done.ALL\nFIRED|ad|failed|/root/x/FAILED.1\n"
    want = [("e0", "done", "/root/r2r_work/done.ALL"), ("ad", "failed", "/root/x/FAILED.1")]

    assert aw.parse_fired(raw) == want
    assert aw.parse_fired(raw.replace("\n", "\n")) == want  # JSON-escaped stdout
    assert aw.parse_fired("nothing ready\n") == []
    assert aw.parse_fired(aw.build_command()) == []  # an echo of the script is not an event


def test_sse_and_json_bodies_both_decode(aw) -> None:
    sse = 'event: message\ndata: {"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"hi"}]}}\n\n'
    plain = '{"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"hi"}]}}'

    assert aw.result_text(aw.decode_response(sse)) == "hi"
    assert aw.result_text(aw.decode_response(plain)) == "hi"
    with pytest.raises(RuntimeError):
        aw.result_text(aw.decode_response('{"jsonrpc":"2.0","id":2,"error":{"code":-1}}'))
    with pytest.raises(RuntimeError):
        aw.result_text(aw.decode_response('{"result":{"isError":true,"content":[{"type":"text","text":"boom"}]}}'))


def test_one_line_per_event(aw) -> None:
    now = datetime(2026, 10, 14, 21, 0, 5, tzinfo=timezone.utc)
    assert aw.ready_line("e0", "done", "/root/d", now) == "READY e0 done /root/d 2026-10-14T21:00:05Z"


@pytest.mark.skipif(not sys.platform.startswith("linux") or shutil.which("bash") is None, reason="the script runs on 137 (Linux); Windows bash resolves C: paths differently")
def test_the_remote_script_fires_each_wait_once(aw, tmp_path: Path) -> None:
    watch = tmp_path / "watch"
    watch.mkdir()
    (tmp_path / "done.ALL").write_text("")
    (tmp_path / "FAILED.2").write_text("")
    (watch / "a.want").write_text(f"alice|{tmp_path}/done.ALL|{tmp_path}/FAILED.*")
    (watch / "b.want").write_text(f"bob|{tmp_path}/never|{tmp_path}/NOPE.*\n")
    (watch / "c.want").write_text(f"carol|{tmp_path}/never|{tmp_path}/FAILED.*\n")
    script = aw.REMOTE_SCRIPT.replace(aw.WATCH_DIR, watch.as_posix())

    def run() -> list:
        out = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True).stdout
        return aw.parse_fired(out)

    assert run() == [("alice", "done", f"{tmp_path.as_posix()}/done.ALL"),
                     ("carol", "failed", f"{tmp_path.as_posix()}/FAILED.2")]
    assert sorted(p.name for p in watch.iterdir()) == ["a.fired", "b.want", "c.fired"]
    assert run() == []  # never twice
