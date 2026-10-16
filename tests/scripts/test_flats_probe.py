"""The flats_probe main function honors explicit argv and transaction mode."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts import flats_probe


class _Engine:
    async def dispose(self):
        pass


class _Session:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        pass

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _db(monkeypatch):
    session = _Session()
    monkeypatch.setattr(flats_probe, "create_async_engine", lambda *a, **k: _Engine())
    monkeypatch.setattr(flats_probe, "async_sessionmaker", lambda *a, **k: lambda: session)
    return session


@pytest.mark.parametrize(("argv", "expected"), [([], (1, 0)), (["--dry-run"], (0, 1))])
async def test_main_uses_argv_and_commits_or_rolls_back(argv, expected, monkeypatch, capsys):
    session = _db(monkeypatch)
    calls = []

    async def _probe(got_session, *, log):
        calls.append((got_session, log))
        return SimpleNamespace(findings=[{"finding": "ok"}], status="ok", seconds=1, id=9)

    monkeypatch.setattr(flats_probe, "run_probe", _probe)

    assert await flats_probe.main(argv) == 0
    assert calls[0][0] is session
    assert calls[0][1] is print
    assert (session.commits, session.rollbacks) == expected
    output = capsys.readouterr().out
    if "--dry-run" in argv:
        assert "dry run, rolled back" in output
    else:
        assert "flats.probes row 9 written" in output
