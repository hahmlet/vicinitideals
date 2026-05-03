"""Unit tests for app/exporters/snapshot.py.

Tests use the shared in-memory SQLite engine + seed helpers from conftest.py.
Exercises: capture, list, diff format, export_history_json shape.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exporters.snapshot import (
    capture_snapshot,
    diff_snapshots,
    export_history_json,
    list_snapshots,
    revert_to_snapshot,
)
from app.models.cashflow import OperationalOutputs
from app.models.deal import ScenarioSnapshot
from app.models.deal import UnitMix, UseLine, UseLinePhase
from app.models.milestone import Milestone, MilestoneType
from app.models.project import Project
from tests.conftest import (
    seed_deal_model,
    seed_deal_model_with_financials,
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
    initial_version = scenario.version or 0

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
    return SimpleNamespace(version=version, inputs_json=inputs, outputs_json=outputs)


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


def test_diff_snapshots_detects_use_line_change():
    snap_a = _make_snap(
        1,
        {"use_lines": [{"id": "u1", "label": "Land", "phase": "acquisition", "amount": 1000000}]},
        {},
    )
    snap_b = _make_snap(
        2,
        {"use_lines": [{"id": "u1", "label": "Land", "phase": "acquisition", "amount": 1250000}]},
        {},
    )

    result = diff_snapshots(snap_a, snap_b)
    change = next((c for c in result["input_changes"] if c.get("entity") == "UseLine"), None)
    assert change is not None
    assert change["field"] == "amount"
    assert change["before"] == 1000000
    assert change["after"] == 1250000


def test_diff_snapshots_detects_capital_nested_change():
    snap_a = _make_snap(
        1,
        {
            "capital_modules": [
                {"id": "c1", "label": "Senior", "source": {"interest_rate_pct": 6.5}, "carry": {"io_rate_pct": 6.5}}
            ]
        },
        {},
    )
    snap_b = _make_snap(
        2,
        {
            "capital_modules": [
                {"id": "c1", "label": "Senior", "source": {"interest_rate_pct": 7.0}, "carry": {"io_rate_pct": 7.0}}
            ]
        },
        {},
    )

    result = diff_snapshots(snap_a, snap_b)
    assert any(
        c.get("entity") == "CapitalModule" and c.get("field") in {"source", "carry"}
        for c in result["input_changes"]
    )


def test_diff_snapshots_duplicate_labels_do_not_collide():
    before_rows = [
        {"id": "i1", "label": "Market Rent", "unit_count": 10},
        {"id": "i2", "label": "Market Rent", "unit_count": 5},
    ]
    after_rows = [
        {"id": "i1", "label": "Market Rent", "unit_count": 10},
        {"id": "i2", "label": "Market Rent", "unit_count": 7},
    ]
    snap_a = _make_snap(1, {"income_streams": before_rows}, {})
    snap_b = _make_snap(2, {"income_streams": after_rows}, {})

    result = diff_snapshots(snap_a, snap_b)
    assert any(c.get("entity") == "IncomeStream" and c.get("field") == "unit_count" for c in result["input_changes"])


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
    assert "computed_at" in entry
    assert "input_changes" in entry
    assert "outputs" in entry


@pytest.mark.asyncio
async def test_export_history_json_raises_for_unknown_scenario(session: AsyncSession):
    """export_history_json raises ValueError when scenario not found."""
    with pytest.raises(ValueError):
        await export_history_json(session, uuid.uuid4())


@pytest.mark.asyncio
async def test_revert_to_snapshot_restores_use_unitmix_and_milestones(session: AsyncSession):
    """Revert restores all key project input tables, including UnitMix and Milestones."""
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    scenario, *_ = await seed_deal_model_with_financials(session, opp, user)

    project = (
        await session.execute(
            select(Project).where(Project.scenario_id == scenario.id).order_by(Project.created_at.asc()).limit(1)
        )
    ).scalar_one()

    use_line = UseLine(project_id=project.id, label="Land", phase=UseLinePhase.acquisition, amount=1000000)
    unit_mix = UnitMix(project_id=project.id, label="1BR", unit_count=8, market_rent_per_unit=1500)
    m1 = Milestone(
        project_id=project.id,
        milestone_type=MilestoneType.pre_development,
        duration_days=30,
        target_date=date(2026, 1, 1),
        sequence_order=1,
        trigger_offset_days=0,
    )
    session.add_all([use_line, unit_mix, m1])
    await session.flush()
    m2 = Milestone(
        project_id=project.id,
        milestone_type=MilestoneType.construction,
        duration_days=180,
        target_date=None,
        sequence_order=2,
        trigger_milestone_id=m1.id,
        trigger_offset_days=0,
    )
    session.add(m2)
    await session.flush()

    snap = await capture_snapshot(session, scenario.id)

    await session.delete(use_line)
    await session.delete(unit_mix)
    await session.delete(m1)
    await session.delete(m2)
    await session.flush()

    await revert_to_snapshot(session, scenario.id, snap.id)
    await session.commit()

    restored_use = list((await session.execute(select(UseLine).where(UseLine.project_id == project.id))).scalars())
    restored_mix = list((await session.execute(select(UnitMix).where(UnitMix.project_id == project.id))).scalars())
    restored_ms = list(
        (
            await session.execute(
                select(Milestone)
                .where(Milestone.project_id == project.id)
                .order_by(Milestone.sequence_order.asc())
            )
        ).scalars()
    )

    assert any(row.label == "Land" for row in restored_use)
    assert any(row.label == "1BR" for row in restored_mix)
    assert len(restored_ms) == 2
    assert restored_ms[1].trigger_milestone_id == restored_ms[0].id


@pytest.mark.asyncio
async def test_capture_snapshot_serializes_outputs_for_all_projects(session: AsyncSession):
    """outputs_json should include per-project metrics, not just the first project row."""
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    scenario, *_ = await seed_deal_model_with_financials(session, opp, user)

    project_rows = list(
        (
            await session.execute(
                select(Project).where(Project.scenario_id == scenario.id).order_by(Project.created_at.asc())
            )
        ).scalars()
    )
    first_project = project_rows[0]
    second_project = Project(
        scenario_id=scenario.id,
        opportunity_id=opp.id,
        name="Second Project",
        deal_type=getattr(scenario.project_type, "value", scenario.project_type),
    )
    session.add(second_project)
    await session.flush()

    session.add_all(
        [
            OperationalOutputs(
                scenario_id=scenario.id,
                project_id=first_project.id,
                dscr=1.25,
                project_irr_levered=0.14,
                noi_stabilized=100000,
            ),
            OperationalOutputs(
                scenario_id=scenario.id,
                project_id=second_project.id,
                dscr=1.45,
                project_irr_levered=0.19,
                noi_stabilized=180000,
            ),
        ]
    )
    await session.flush()

    snap = await capture_snapshot(session, scenario.id)
    by_project = snap.outputs_json.get("by_project") or {}

    assert str(first_project.id) in by_project
    assert str(second_project.id) in by_project
