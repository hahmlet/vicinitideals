"""Unit tests for app/exporters/snapshot.py.

Tests use the shared in-memory SQLite engine + seed helpers from conftest.py.
Exercises: capture, list, diff format, export_history_json shape.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.exporters.snapshot import (
    capture_snapshot,
    diff_snapshots,
    export_history_json,
    list_snapshots,
)
from app.models.deal import ScenarioSnapshot
from tests.conftest import (
    seed_deal_model,
    seed_opportunity,
    seed_org,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
async def seeded(session: AsyncSession):
    """Minimal scenario with no financials — enough to snapshot."""
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    scenario = await seed_deal_model(session, opp, user, name="Snapshot Test Deal")
    await session.commit()
    return scenario


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_capture_snapshot_increments_version(seeded, session: AsyncSession):
    """capture_snapshot should bump Scenario.version and insert a row."""
    scenario = seeded
    initial_version = scenario.version or 1

    snap = await capture_snapshot(session, scenario.id, triggered_by="compute")

    assert snap.scenario_id == scenario.id
    assert snap.version == initial_version + 1
    assert snap.triggered_by == "compute"
    assert isinstance(snap.id, uuid.UUID)
    await session.commit()


@pytest.mark.asyncio
async def test_capture_snapshot_twice_yields_sequential_versions(seeded, session: AsyncSession):
    """Two successive captures yield versions N+1, N+2."""
    scenario = seeded
    snap1 = await capture_snapshot(session, scenario.id)
    snap2 = await capture_snapshot(session, scenario.id)

    assert snap2.version == snap1.version + 1
    await session.commit()


@pytest.mark.asyncio
async def test_list_snapshots_ordering(seeded, session: AsyncSession):
    """list_snapshots returns rows in ascending version order."""
    scenario = seeded
    for _ in range(3):
        await capture_snapshot(session, scenario.id)
    await session.commit()

    snaps = await list_snapshots(session, scenario.id)
    versions = [s.version for s in snaps]
    assert versions == sorted(versions)
    assert len(snaps) >= 3


@pytest.mark.asyncio
async def test_list_snapshots_empty_for_unknown_scenario(session: AsyncSession):
    """list_snapshots returns [] when the scenario has no snapshots."""
    snaps = await list_snapshots(session, uuid.uuid4())
    assert snaps == []


@pytest.mark.asyncio
async def test_snapshot_inputs_json_is_dict(seeded, session: AsyncSession):
    """inputs_json should be a dict (may be sparse for a bare scenario)."""
    snap = await capture_snapshot(session, seeded.id)
    await session.commit()

    assert isinstance(snap.inputs_json, dict)


@pytest.mark.asyncio
async def test_snapshot_outputs_json_is_dict(seeded, session: AsyncSession):
    """outputs_json should be a dict (empty when no OperationalOutputs exist)."""
    snap = await capture_snapshot(session, seeded.id)
    await session.commit()

    assert isinstance(snap.outputs_json, dict)


# ── Diff tests ────────────────────────────────────────────────────────────────

def _make_snap(version: int, inputs: dict, outputs: dict) -> ScenarioSnapshot:
    """Build an in-memory ScenarioSnapshot object for diff testing."""
    snap = ScenarioSnapshot.__new__(ScenarioSnapshot)
    snap.version = version
    snap.inputs_json = inputs
    snap.outputs_json = outputs
    return snap


def test_diff_snapshots_identical_returns_empty_changes():
    """Diff of two identical snapshots should have no changes."""
    data = {"operational_inputs": {"unit_count_new": 8, "exit_cap_rate_pct": "5.5"}}
    snap_a = _make_snap(1, data, {"dscr": 1.2})
    snap_b = _make_snap(2, data, {"dscr": 1.2})

    result = diff_snapshots(snap_a, snap_b)

    assert result["version_before"] == 1
    assert result["version_after"] == 2
    assert result["input_changes"] == []
    assert result["output_changes"] == {}


def test_diff_snapshots_detects_scalar_input_change():
    """Diff detects changes to OperationalInputs scalars."""
    snap_a = _make_snap(1, {"operational_inputs": {"unit_count_new": 8}}, {})
    snap_b = _make_snap(2, {"operational_inputs": {"unit_count_new": 12}}, {})

    result = diff_snapshots(snap_a, snap_b)

    changes = result["input_changes"]
    unit_change = next((c for c in changes if c.get("field") == "unit_count_new"), None)
    assert unit_change is not None
    assert unit_change["before"] == 8
    assert unit_change["after"] == 12


def test_diff_snapshots_detects_output_change():
    """Diff detects changes to output metrics."""
    snap_a = _make_snap(1, {}, {"dscr": 1.1})
    snap_b = _make_snap(2, {}, {"dscr": 1.4})

    result = diff_snapshots(snap_a, snap_b)

    assert "dscr" in result["output_changes"]
    assert result["output_changes"]["dscr"]["before"] == 1.1
    assert result["output_changes"]["dscr"]["after"] == 1.4


def test_diff_snapshots_no_change_on_same_outputs():
    snap_a = _make_snap(1, {}, {"dscr": 1.2, "noi_stabilized": 50000})
    snap_b = _make_snap(2, {}, {"dscr": 1.2, "noi_stabilized": 50000})

    result = diff_snapshots(snap_a, snap_b)
    assert result["output_changes"] == {}


# ── Export history JSON tests ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_export_history_json_shape(seeded, session: AsyncSession):
    """export_history_json returns expected top-level keys and entry structure."""
    scenario = seeded
    await capture_snapshot(session, scenario.id)
    await capture_snapshot(session, scenario.id)
    await session.commit()

    payload = await export_history_json(session, scenario.id)

    assert "scenario_id" in payload
    assert "exported_at" in payload
    assert "entries" in payload
    assert isinstance(payload["entries"], list)
    assert len(payload["entries"]) >= 2

    entry = payload["entries"][0]
    assert "version" in entry
    assert "created_at" in entry
    assert "inputs_json" in entry
    assert "outputs_json" in entry


@pytest.mark.asyncio
async def test_export_history_json_raises_for_unknown_scenario(session: AsyncSession):
    """export_history_json raises ValueError when scenario not found."""
    with pytest.raises(ValueError):
        await export_history_json(session, uuid.uuid4())
