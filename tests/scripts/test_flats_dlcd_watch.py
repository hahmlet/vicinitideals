"""Argument and date-window behavior of the DLCD reading-list command."""

from __future__ import annotations

import sys
from datetime import date, timedelta

import pytest

from scripts import flats_dlcd_watch


class _Today(date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 16)


def test_future_since_is_an_argparse_error_before_output_creation(tmp_path, monkeypatch, capsys):
    out = tmp_path / "not-created"
    # Pin today: with the real clock, 2026-10-17 stopped being "the future" on that
    # date and the command went on to fetch from DLCD (CI red from 2026-10-17).
    monkeypatch.setattr(flats_dlcd_watch, "date", _Today)
    monkeypatch.setattr(sys, "argv", ["flats_dlcd_watch.py", "--since", "2026-10-17", "--out", str(out)])

    with pytest.raises(SystemExit) as exited:
        flats_dlcd_watch.main()

    assert exited.value.code == 2
    assert "--since cannot be after today" in capsys.readouterr().err
    assert not out.exists()


def test_default_since_is_a_21_day_window(tmp_path, monkeypatch):
    since_values = []
    monkeypatch.setattr(flats_dlcd_watch, "date", _Today)
    monkeypatch.setattr(flats_dlcd_watch, "load_jurisdictions", lambda: {})
    monkeypatch.setattr(flats_dlcd_watch, "load_ledger", lambda: {})
    monkeypatch.setattr(flats_dlcd_watch, "parse", lambda _path: [])
    monkeypatch.setattr(flats_dlcd_watch, "new_notices", lambda notices, _ledger: notices)
    monkeypatch.setattr(flats_dlcd_watch, "render_markdown", lambda *_args: "")

    def _fetch(_kind, since, today, path):
        since_values.append((since, today))
        path.write_text("", encoding="utf-8")
        return path

    monkeypatch.setattr(flats_dlcd_watch, "fetch", _fetch)
    monkeypatch.setattr(
        sys, "argv", ["flats_dlcd_watch.py", "--out", str(tmp_path / "output")]
    )

    flats_dlcd_watch.main()

    assert since_values == [
        (_Today(2026, 9, 25), _Today(2026, 10, 16)),
        (_Today(2026, 9, 25), _Today(2026, 10, 16)),
    ]
    assert (tmp_path / "output" / "new.json").is_file()
    assert (tmp_path / "output" / "new.md").is_file()
