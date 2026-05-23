"""Per-project phase plan extraction with absolute month boundaries.

Wraps :func:`app.engines.cashflow_compile._build_phase_plan` to fold the
phase-duration list into a sequence of :class:`PhaseWindow` records that
carry absolute, 1-based month indices for ``start_month``, ``end_month``
(inclusive), and ``duration_months``.

Why this exists separately from ``_build_phase_plan``:

``_build_phase_plan`` returns ``list[PhaseSpec]`` — phase + month-count
pairs. Callers that need to answer "what month does the construction
phase *end*?" had to re-walk the list and accumulate manually. The
investor Excel export wants those boundaries as named workbook cells
(``p<n>_construction_end_month``, ``p<n>_perm_origination_month``,
etc.) so future formula conversions can gate construction-to-perm loan
behavior in-sheet without round-tripping through Python. This module
is the single source of truth for that absolute-month conversion.

Stays a thin wrapper — phase-membership rules (which phases apply to
which project type) live in ``_build_phase_plan`` and are unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from app.engines.cashflow_compile import (
    PhaseSpec,
    _build_phase_plan,
    _milestone_dates_from_orm,
)
from app.models.cashflow import PeriodType
from app.models.deal import OperationalInputs
from app.models.milestone import Milestone, MilestoneType


@dataclass(frozen=True)
class PhaseWindow:
    """A single phase with absolute month boundaries (1-based, inclusive).

    A phase of ``duration_months=3`` starting at month 4 has
    ``start_month=4`` and ``end_month=6``. The month after the phase
    ends is ``end_month + 1`` (perm-origination convention).
    """

    period_type: PeriodType
    start_month: int
    end_month: int
    duration_months: int


# Phases that count as "construction-side" for perm-origination math.
# The first month AFTER the last such phase is when a construction-to-
# perm loan converts to its permanent tranche.
_CONSTRUCTION_SIDE_PHASES: tuple[PeriodType, ...] = (
    PeriodType.pre_construction,
    PeriodType.construction,
    PeriodType.conversion,
    PeriodType.major_renovation,
    PeriodType.minor_renovation,
)


def build_project_phase_windows(
    project_type: str,
    inputs: OperationalInputs,
    *,
    milestones: list[Milestone] | None = None,
    capital_modules: list | None = None,
) -> list[PhaseWindow]:
    """Build ordered :class:`PhaseWindow` list for one project.

    ``milestones`` are this project's ``Milestone`` ORM records. The
    trigger chain is resolved via ``computed_start`` on each milestone
    (relies on each milestone's ``trigger_milestone_id`` / ``target_date``).

    Zero-duration phases are dropped so a downstream formula never
    indexes an empty range.
    """
    milestone_list = list(milestones or [])
    milestone_map = {m.id: m for m in milestone_list}
    milestone_dates = (
        _milestone_dates_from_orm(milestone_list, milestone_map)
        if milestone_list
        else None
    )

    has_lease_up = _has_milestone(milestone_list, MilestoneType.operation_lease_up)
    has_pre_dev = _has_milestone(milestone_list, MilestoneType.pre_development)
    has_construction = _has_milestone(milestone_list, MilestoneType.construction)

    phases: Sequence[PhaseSpec] = _build_phase_plan(
        project_type=project_type,
        inputs=inputs,
        milestone_dates=milestone_dates,
        has_lease_up_milestone=has_lease_up,
        has_pre_development_milestone=has_pre_dev,
        has_construction_milestone=has_construction,
        capital_modules=capital_modules,
        orm_milestones=milestone_list,
    )

    windows: list[PhaseWindow] = []
    cursor = 1
    for phase in phases:
        duration = int(phase.months or 0)
        if duration <= 0:
            continue
        windows.append(
            PhaseWindow(
                period_type=phase.period_type,
                start_month=cursor,
                end_month=cursor + duration - 1,
                duration_months=duration,
            )
        )
        cursor += duration
    return windows


def find_phase_window(
    windows: Iterable[PhaseWindow], period_type: PeriodType
) -> PhaseWindow | None:
    """Return the first window matching ``period_type``, or ``None``."""
    for window in windows:
        if window.period_type == period_type:
            return window
    return None


def perm_origination_month(windows: Iterable[PhaseWindow]) -> int | None:
    """Absolute month a construction-to-perm loan converts to permanent.

    Defined as ``end_month + 1`` of the last construction-side phase
    (see :data:`_CONSTRUCTION_SIDE_PHASES`). Returns ``None`` for pure
    hold/acquisition projects that have no construction-side phase —
    perm origination is undefined there.
    """
    last_end: int | None = None
    for window in windows:
        if window.period_type in _CONSTRUCTION_SIDE_PHASES:
            last_end = window.end_month
    return (last_end + 1) if last_end is not None else None


def total_horizon_months(windows: Iterable[PhaseWindow]) -> int:
    """Sum of all phase durations. ``0`` for an empty list."""
    return sum(w.duration_months for w in windows)


def _has_milestone(milestones: list[Milestone], target: MilestoneType) -> bool:
    target_value = target.value if hasattr(target, "value") else str(target)
    for milestone in milestones:
        raw = getattr(milestone, "milestone_type", None)
        if raw is None:
            continue
        value = getattr(raw, "value", None) or str(raw).replace("MilestoneType.", "")
        if value == target_value:
            return True
    return False
