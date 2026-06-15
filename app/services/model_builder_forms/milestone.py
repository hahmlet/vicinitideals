"""Form-save logic for Milestone rows (Timeline panel)."""
from __future__ import annotations

from datetime import date as _date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.milestone import Milestone, MilestoneType
from app.utils.form_helpers import _fi


def _parse_date(v: str | None) -> _date | None:
    if not v or not v.strip():
        return None
    try:
        return _date.fromisoformat(v.strip()[:10])
    except ValueError:
        return None


async def save_milestone(
    session: AsyncSession,
    model_id: UUID,
    project_id: UUID | None,
    item_id: str,
    form,
) -> None:
    """Persist a Milestone create or update from form data."""
    mtype_raw = form.get("milestone_type", "construction")
    try:
        mtype = MilestoneType(mtype_raw)
    except ValueError:
        mtype = MilestoneType.construction

    trigger_raw = str(form.get("trigger_milestone_id") or "").strip()
    try:
        trigger_id = UUID(trigger_raw) if trigger_raw else None
    except ValueError:
        trigger_id = None

    # Guard: reject a trigger that belongs to a different project.
    # This prevents the cross-project trigger corruption that caused
    # milestones on project 2 to point at milestones on project 1.
    if trigger_id is not None:
        _trigger_ms = await session.get(Milestone, trigger_id)
        _ms_project_id: UUID | None = project_id
        if item_id:
            try:
                _existing_for_check = await session.get(Milestone, UUID(item_id))
                if _existing_for_check:
                    _ms_project_id = _existing_for_check.project_id
            except (ValueError, AttributeError):
                pass
        if _trigger_ms is None or (_ms_project_id is not None and _trigger_ms.project_id != _ms_project_id):
            trigger_id = None

    data = {
        "duration_days": _fi(form.get("duration_days"), 0),
        "milestone_type": mtype,
        "trigger_milestone_id": trigger_id,
        "trigger_offset_days": _fi(form.get("trigger_offset_days"), 0),
        # anchor: keep target_date only when no trigger; clear it when trigger set
        "target_date": _parse_date(str(form.get("target_date") or "")) if not trigger_id else None,
    }
    if item_id:
        row = await session.get(Milestone, UUID(item_id))
        if row:
            for k, v in data.items():
                setattr(row, k, v)
    elif project_id:
        session.add(Milestone(
            project_id=project_id,
            sequence_order=0,
            **data,
        ))
