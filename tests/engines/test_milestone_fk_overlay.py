"""Unit tests for the milestone-FK → active_phase_start overlay helpers in
app/engines/cashflow.py.

The helpers run pre-engine on load and rewrite ``module.active_phase_start``
in memory so downstream readers (``_loan_pre_op_months``, ``_APS_TO_USE_PHASE``)
honor the FK over the legacy string field. Precedence: junction FK > module
FK > legacy string.
"""

from __future__ import annotations

import types
import uuid

import pytest

from app.engines.cashflow import (
    _apply_milestone_fk_overlay_inplace,
    _phase_string_from_milestone_id,
)
from app.models.milestone import MilestoneType


def _ms(milestone_type: MilestoneType):
    return types.SimpleNamespace(id=uuid.uuid4(), milestone_type=milestone_type)


@pytest.mark.unit
def test_phase_string_from_milestone_id_strips_enum_prefix():
    m = _ms(MilestoneType.close)
    out = _phase_string_from_milestone_id(m.id, {m.id: m})
    assert out == "close"


@pytest.mark.unit
def test_phase_string_from_milestone_id_handles_missing_inputs():
    assert _phase_string_from_milestone_id(None, {}) is None
    assert _phase_string_from_milestone_id(uuid.uuid4(), None) is None
    assert _phase_string_from_milestone_id(uuid.uuid4(), {}) is None


@pytest.mark.unit
def test_module_fk_overrides_legacy_string():
    m = _ms(MilestoneType.close)
    module = types.SimpleNamespace(
        active_phase_start="acquisition",
        active_phase_end=None,
        active_from_milestone_id=m.id,
        active_to_milestone_id=None,
    )
    junction = types.SimpleNamespace(
        active_from_milestone_id=None,
        active_to_milestone_id=None,
    )
    _apply_milestone_fk_overlay_inplace(module, junction, {m.id: m})
    assert module.active_phase_start == "close"
    assert module.active_phase_end is None  # untouched when no FK


@pytest.mark.unit
def test_junction_fk_beats_module_fk():
    m_module = _ms(MilestoneType.close)
    m_junction = _ms(MilestoneType.operation_stabilized)
    module = types.SimpleNamespace(
        active_phase_start="acquisition",
        active_phase_end=None,
        active_from_milestone_id=m_module.id,
        active_to_milestone_id=None,
    )
    junction = types.SimpleNamespace(
        active_from_milestone_id=m_junction.id,
        active_to_milestone_id=None,
    )
    _apply_milestone_fk_overlay_inplace(
        module, junction, {m_module.id: m_module, m_junction.id: m_junction}
    )
    assert module.active_phase_start == "operation_stabilized"


@pytest.mark.unit
def test_no_fk_leaves_legacy_string_untouched():
    module = types.SimpleNamespace(
        active_phase_start="acquisition",
        active_phase_end="operation_stabilized",
        active_from_milestone_id=None,
        active_to_milestone_id=None,
    )
    junction = types.SimpleNamespace(
        active_from_milestone_id=None,
        active_to_milestone_id=None,
    )
    _apply_milestone_fk_overlay_inplace(module, junction, {})
    assert module.active_phase_start == "acquisition"
    assert module.active_phase_end == "operation_stabilized"


@pytest.mark.unit
def test_overlay_handles_both_ends():
    m_from = _ms(MilestoneType.close)
    m_to = _ms(MilestoneType.operation_stabilized)
    module = types.SimpleNamespace(
        active_phase_start="acquisition",
        active_phase_end="exit",
        active_from_milestone_id=m_from.id,
        active_to_milestone_id=m_to.id,
    )
    junction = types.SimpleNamespace(
        active_from_milestone_id=None,
        active_to_milestone_id=None,
    )
    _apply_milestone_fk_overlay_inplace(
        module, junction, {m_from.id: m_from, m_to.id: m_to}
    )
    assert module.active_phase_start == "close"
    assert module.active_phase_end == "operation_stabilized"


@pytest.mark.unit
def test_stale_fk_not_in_map_falls_back_to_legacy():
    """If a FK references a milestone that's been deleted (or wasn't loaded),
    the legacy string field stays in place — the engine still has a value to
    work with rather than crashing or going silently empty."""
    module = types.SimpleNamespace(
        active_phase_start="acquisition",
        active_phase_end=None,
        active_from_milestone_id=uuid.uuid4(),  # not in map
        active_to_milestone_id=None,
    )
    junction = types.SimpleNamespace(
        active_from_milestone_id=None,
        active_to_milestone_id=None,
    )
    _apply_milestone_fk_overlay_inplace(module, junction, {})
    assert module.active_phase_start == "acquisition"
