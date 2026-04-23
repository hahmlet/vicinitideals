"""Tests for app/tasks/loopnet_ingest.py — experiment gate, sweep behavior."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import patch

import pytest

from app.tasks import loopnet_ingest


@pytest.mark.asyncio
async def test_experiment_daily_refresh_skips_when_flag_off(monkeypatch) -> None:
    monkeypatch.setattr(loopnet_ingest.settings, "loopnet_experiment_enabled", False)
    result = await loopnet_ingest._loopnet_experiment_daily_refresh()
    assert "skipped" in result
    assert "disabled" in result["skipped"]


@pytest.mark.asyncio
async def test_experiment_daily_refresh_skips_after_end_date(monkeypatch) -> None:
    monkeypatch.setattr(loopnet_ingest.settings, "loopnet_experiment_enabled", True)
    # End date in the past
    past = (datetime.now(UTC).date().replace(day=1)).isoformat()
    # Force a year-ago string
    past_date = date(2020, 1, 1).isoformat()
    monkeypatch.setattr(
        loopnet_ingest.settings, "loopnet_experiment_end_date", past_date
    )
    result = await loopnet_ingest._loopnet_experiment_daily_refresh()
    assert "skipped" in result
    assert "end_date" in result["skipped"]


@pytest.mark.asyncio
async def test_monthly_refresh_skips_while_experiment_active(monkeypatch) -> None:
    monkeypatch.setattr(loopnet_ingest.settings, "loopnet_experiment_enabled", True)
    # Future end date
    future = date(2099, 12, 31).isoformat()
    monkeypatch.setattr(loopnet_ingest.settings, "loopnet_experiment_end_date", future)
    result = await loopnet_ingest._loopnet_monthly_refresh()
    assert "skipped" in result
    assert "experiment active" in result["skipped"]


def test_parse_update_ts_handles_iso_and_us_formats() -> None:
    iso = loopnet_ingest._parse_update_ts("2026-01-06T12:00:00-05:00")
    assert iso is not None
    assert iso.tzinfo is not None

    us = loopnet_ingest._parse_update_ts("4/18/2026")
    assert us == datetime(2026, 4, 18, tzinfo=UTC)

    assert loopnet_ingest._parse_update_ts(None) is None
    assert loopnet_ingest._parse_update_ts("") is None
    assert loopnet_ingest._parse_update_ts("not-a-date") is None
