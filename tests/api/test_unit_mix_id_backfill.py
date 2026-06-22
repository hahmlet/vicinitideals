"""Tests for unit_mix legacy-row ID backfill helper.

Legacy unit_mix JSONB rows uploaded before stable IDs were assigned end up
missing an 'id' key, which makes the HTMX delete handler unable to target
them. `_ensure_unit_mix_ids()` assigns UUIDs in place so the rows become
deletable on the next panel render.
"""

from __future__ import annotations

import uuid

import pytest

from app.api.routers.ui_model_builder import _ensure_unit_mix_ids


class _StubProject:
    """Stand-in for an ORM Project — only the unit_mix attribute is exercised."""

    def __init__(self, unit_mix):
        self.unit_mix = unit_mix


def _is_uuid(s):
    try:
        uuid.UUID(s)
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def test_backfill_assigns_ids_to_legacy_rows(monkeypatch):
    monkeypatch.setattr(
        "sqlalchemy.orm.attributes.flag_modified",
        lambda obj, key: None,
    )
    proj = _StubProject([
        {"label": "Studio", "unit_count": 4, "id": "cd3292e2-2249-4452-9f18-e211f4b0d101"},
        {"label": "2x1", "unit_count": 6},
        {"label": "3x1.5", "unit_count": 2},
    ])
    changed = _ensure_unit_mix_ids(proj)
    assert changed is True
    assert all(_is_uuid(r["id"]) for r in proj.unit_mix)
    # existing id preserved
    assert proj.unit_mix[0]["id"] == "cd3292e2-2249-4452-9f18-e211f4b0d101"


def test_backfill_noop_when_all_rows_have_ids(monkeypatch):
    monkeypatch.setattr(
        "sqlalchemy.orm.attributes.flag_modified",
        lambda obj, key: None,
    )
    rows = [
        {"label": "Studio", "id": str(uuid.uuid4())},
        {"label": "1 BR", "id": str(uuid.uuid4())},
    ]
    proj = _StubProject(rows)
    changed = _ensure_unit_mix_ids(proj)
    assert changed is False


def test_backfill_handles_empty_and_none():
    assert _ensure_unit_mix_ids(_StubProject(None)) is False
    assert _ensure_unit_mix_ids(_StubProject([])) is False
    assert _ensure_unit_mix_ids(None) is False
