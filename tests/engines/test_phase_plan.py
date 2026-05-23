"""Unit tests for :mod:`app.engines.phase_plan`.

Covers the absolute-month boundary fold-in on top of ``_build_phase_plan``:

  - cumulative ``start_month`` / ``end_month`` indices match the duration list
  - zero-duration phases are dropped (no empty windows for downstream formulas)
  - perm-origination month = month after the last construction-side phase
  - perm-origination month is ``None`` for pure-hold projects with no
    construction-side phase
  - milestone presence (lease-up, pre-development) is forwarded into
    ``_build_phase_plan`` correctly so phase-membership stays consistent
    with the engine's existing rules
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

import pytest

from app.engines.phase_plan import (
    PhaseWindow,
    build_project_phase_windows,
    find_phase_window,
    perm_origination_month,
    total_horizon_months,
)
from app.models.cashflow import PeriodType
from app.models.deal import OperationalInputs


@dataclass
class _FakeModule:
    """Minimal stand-in for CapitalModule — only the fields
    ``_resolve_horizon_months`` reads (``vehicle_type`` + ``source``)."""

    vehicle_type: str = "debt"
    source: dict | None = None

    def __post_init__(self) -> None:
        if self.source is None:
            self.source = {"hold_term_years": 2}


def _make_inputs(**overrides) -> OperationalInputs:
    defaults = dict(
        project_id=uuid4(),
        unit_count_new=12,
        opex_per_unit_annual=Decimal("4800"),
        expense_growth_rate_pct_annual=Decimal("3"),
        mgmt_fee_pct=Decimal("4"),
        property_tax_annual=Decimal("18000"),
        insurance_annual=Decimal("7200"),
        capex_reserve_per_unit_annual=Decimal("300"),
        exit_cap_rate_pct=Decimal("5.75"),
        selling_costs_pct=Decimal("2.5"),
    )
    defaults.update(overrides)
    return OperationalInputs(**defaults)


@pytest.mark.unit
def test_windows_for_new_construction_have_cumulative_month_boundaries() -> None:
    inputs = _make_inputs(
        entitlement_months=6,
        construction_months=12,
        lease_up_months=4,
    )

    windows = build_project_phase_windows(
        "new_construction",
        inputs,
        capital_modules=[_FakeModule()],
    )

    types = [w.period_type for w in windows]
    assert types == [
        PeriodType.acquisition,
        PeriodType.pre_construction,
        PeriodType.construction,
        PeriodType.lease_up,
        PeriodType.stabilized,
        PeriodType.exit,
    ]
    durations = [w.duration_months for w in windows]
    assert durations == [1, 6, 12, 4, 24, 1]

    # Cumulative boundaries (1-based, inclusive end).
    assert [(w.start_month, w.end_month) for w in windows] == [
        (1, 1),     # acquisition: months 1..1
        (2, 7),     # pre_construction: months 2..7
        (8, 19),    # construction: months 8..19
        (20, 23),   # lease_up: months 20..23
        (24, 47),   # stabilized: months 24..47
        (48, 48),   # exit: month 48
    ]


@pytest.mark.unit
def test_perm_origination_month_is_month_after_construction_end() -> None:
    inputs = _make_inputs(entitlement_months=6, construction_months=12)
    windows = build_project_phase_windows(
        "new_construction", inputs, capital_modules=[_FakeModule()]
    )

    construction = find_phase_window(windows, PeriodType.construction)
    assert construction is not None and construction.end_month == 19
    assert perm_origination_month(windows) == 20


@pytest.mark.unit
def test_perm_origination_month_is_none_for_pure_hold_acquisition() -> None:
    inputs = _make_inputs()  # no construction, no renovation
    windows = build_project_phase_windows(
        "acquisition", inputs, capital_modules=[_FakeModule()]
    )

    # No construction-side phase → no perm origination defined.
    assert perm_origination_month(windows) is None


@pytest.mark.unit
def test_perm_origination_uses_last_construction_side_phase_for_conversion() -> None:
    inputs = _make_inputs(
        entitlement_months=3,
        construction_months=10,  # used as conversion duration
    )
    windows = build_project_phase_windows(
        "conversion", inputs, capital_modules=[_FakeModule()]
    )

    conversion = find_phase_window(windows, PeriodType.conversion)
    pre_construction = find_phase_window(windows, PeriodType.pre_construction)
    assert pre_construction is not None and pre_construction.end_month == 4
    assert conversion is not None and conversion.end_month == 14
    # Perm originates after the LAST construction-side phase (conversion),
    # not the first (pre_construction).
    assert perm_origination_month(windows) == 15


@pytest.mark.unit
def test_total_horizon_months_sums_all_durations() -> None:
    inputs = _make_inputs(
        entitlement_months=6,
        construction_months=12,
        lease_up_months=4,
    )
    windows = build_project_phase_windows(
        "new_construction", inputs, capital_modules=[_FakeModule()]
    )

    # 1 + 6 + 12 + 4 + 24 + 1 = 48
    assert total_horizon_months(windows) == 48
    # Sum equals the last window's end_month exactly (1-based inclusive).
    assert total_horizon_months(windows) == windows[-1].end_month


@pytest.mark.unit
def test_zero_duration_phases_are_dropped() -> None:
    # value_add with hold_phase_enabled=True but hold_months=0 → hold not in
    # plan to begin with; renovation_months=0 → still gets fallback=1.
    # We simulate "phase that would otherwise be zero" via the lease-up path:
    # lease_up_months=0 AND no lease-up milestone → no lease_up phase.
    inputs = _make_inputs(
        hold_phase_enabled=True,
        hold_months=0,
        renovation_months=8,
        lease_up_months=0,
    )
    windows = build_project_phase_windows(
        "value_add", inputs, capital_modules=[_FakeModule()]
    )

    types = [w.period_type for w in windows]
    # No hold (months=0), no lease_up (months=0 and no milestone).
    assert PeriodType.hold not in types
    assert PeriodType.lease_up not in types
    # All remaining windows have positive duration.
    assert all(w.duration_months > 0 for w in windows)


@pytest.mark.unit
def test_find_phase_window_returns_none_when_missing() -> None:
    inputs = _make_inputs()
    windows = build_project_phase_windows(
        "acquisition", inputs, capital_modules=[_FakeModule()]
    )

    # Pure acquisition has no construction phase.
    assert find_phase_window(windows, PeriodType.construction) is None
    # But it always has acquisition + stabilized + exit.
    assert find_phase_window(windows, PeriodType.acquisition) is not None
    assert find_phase_window(windows, PeriodType.stabilized) is not None


@pytest.mark.unit
def test_phase_window_is_frozen_dataclass() -> None:
    window = PhaseWindow(
        period_type=PeriodType.construction,
        start_month=5,
        end_month=10,
        duration_months=6,
    )
    with pytest.raises(Exception):
        window.start_month = 99  # type: ignore[misc]
