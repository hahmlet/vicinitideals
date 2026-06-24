"""Unit tests for DocumentTask.computed_due_date (relational vs hard-coded)."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.document import DocumentTask

pytestmark = pytest.mark.unit


class _FakeMilestone:
    def __init__(self, end: date | None):
        self._end = end

    def computed_end(self, milestone_map=None):
        return self._end


def test_hardcoded_due_date_used_when_no_milestone():
    t = DocumentTask(due_date=date(2026, 3, 1))
    assert t.computed_due_date() == date(2026, 3, 1)
    assert t.computed_due_date({}) == date(2026, 3, 1)


def test_relative_due_resolves_milestone_end_plus_offset():
    mid = uuid.uuid4()
    t = DocumentTask(due_milestone_id=mid, due_offset_days=5, due_date=None)
    mm = {mid: _FakeMilestone(date(2026, 1, 1))}
    assert t.computed_due_date(mm) == date(2026, 1, 6)


def test_relative_due_falls_back_to_due_date_when_milestone_unresolved():
    mid = uuid.uuid4()
    t = DocumentTask(due_milestone_id=mid, due_offset_days=5, due_date=date(2026, 2, 2))
    # Milestone end unresolved → fall back to hard-coded due_date.
    assert t.computed_due_date({mid: _FakeMilestone(None)}) == date(2026, 2, 2)
    # No map → fall back too.
    assert t.computed_due_date() == date(2026, 2, 2)


def test_no_due_at_all_returns_none():
    assert DocumentTask().computed_due_date() is None
