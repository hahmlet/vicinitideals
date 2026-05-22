"""Unit tests for app/services/capital_module_milestones.py.

Covers the phase-string → MilestoneType mapping that's mirrored in the 0095
migration. The integration path (sync writes the FK against a real scenario)
is exercised by the existing API tests when they hit the wizard finalize and
capital-modules form handler.
"""

from __future__ import annotations

import pytest

from app.models.milestone import MilestoneType
from app.services.capital_module_milestones import (
    _APS_TO_MILESTONE_TYPE,
    map_aps_to_milestone_type,
)


@pytest.mark.unit
def test_map_aps_passthrough_milestone_keys():
    """Milestone-key variants the wizard writes must round-trip to their enum."""
    assert map_aps_to_milestone_type("close") == MilestoneType.close
    assert map_aps_to_milestone_type("offer_made") == MilestoneType.offer_made
    assert map_aps_to_milestone_type("under_contract") == MilestoneType.under_contract
    assert map_aps_to_milestone_type("pre_development") == MilestoneType.pre_development
    assert map_aps_to_milestone_type("construction") == MilestoneType.construction
    assert map_aps_to_milestone_type("operation_lease_up") == MilestoneType.operation_lease_up
    assert map_aps_to_milestone_type("operation_stabilized") == MilestoneType.operation_stabilized
    assert map_aps_to_milestone_type("divestment") == MilestoneType.divestment


@pytest.mark.unit
def test_map_aps_phase_synonyms():
    """Pure-phase strings ("acquisition", "stabilized") map to their canonical milestone type.

    These are the values older capital_modules rows carry from before the
    milestone-key variants were introduced.
    """
    assert map_aps_to_milestone_type("acquisition") == MilestoneType.close
    assert map_aps_to_milestone_type("pre_construction") == MilestoneType.pre_development
    assert map_aps_to_milestone_type("lease_up") == MilestoneType.operation_lease_up
    assert map_aps_to_milestone_type("stabilized") == MilestoneType.operation_stabilized
    assert map_aps_to_milestone_type("exit") == MilestoneType.divestment


@pytest.mark.unit
def test_map_aps_unknown_or_blank_returns_none():
    assert map_aps_to_milestone_type(None) is None
    assert map_aps_to_milestone_type("") is None
    assert map_aps_to_milestone_type("garbage_value") is None


@pytest.mark.unit
def test_aps_to_milestone_type_table_matches_migration():
    """Service-side table must match the migration's backfill table.

    If you change one, change both. Migration 0095 embeds the same mapping
    as a SQL-side constant so the backfill DML can match rows directly.
    """
    expected = {
        "acquisition":          MilestoneType.close,
        "close":                MilestoneType.close,
        "offer_made":           MilestoneType.offer_made,
        "under_contract":       MilestoneType.under_contract,
        "pre_construction":     MilestoneType.pre_development,
        "pre_development":      MilestoneType.pre_development,
        "construction":         MilestoneType.construction,
        "lease_up":             MilestoneType.operation_lease_up,
        "operation_lease_up":   MilestoneType.operation_lease_up,
        "stabilized":           MilestoneType.operation_stabilized,
        "operation_stabilized": MilestoneType.operation_stabilized,
        "exit":                 MilestoneType.divestment,
        "divestment":           MilestoneType.divestment,
    }
    assert _APS_TO_MILESTONE_TYPE == expected
