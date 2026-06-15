"""Form-save logic for unit_mix JSONB rows (Property panel)."""
from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.utils.form_helpers import _fd, _fi


async def save_unit_mix(
    session: AsyncSession,
    project_id: UUID | None,
    item_id: str,
    form,
) -> None:
    """Persist a unit_mix JSONB row create or update from form data."""
    def _fj(v): return float(v) if v is not None else None

    data = {
        "label": form.get("label", "").strip() or "Units",
        "unit_count": _fi(form.get("unit_count"), 1) or 1,
        "avg_sqft": _fj(_fd(form.get("avg_sqft"))),
        "beds": _fj(_fd(form.get("beds"))),
        "baths": _fj(_fd(form.get("baths"))),
        "market_rent_per_unit": _fj(_fd(form.get("market_rent_per_unit"))),
        "in_place_rent_per_unit": _fj(_fd(form.get("in_place_rent_per_unit"))),
        "unit_strategy": form.get("unit_strategy") or None,
        "post_reno_rent_per_unit": _fj(_fd(form.get("post_reno_rent_per_unit"))),
        "notes": form.get("notes") or None,
    }
    if project_id:
        _um_proj = await session.get(Project, project_id)
        if _um_proj is not None:
            rows = list(_um_proj.unit_mix or [])
            if item_id:
                _uid_str = str(UUID(item_id))
                idx = next((i for i, d in enumerate(rows) if d.get("id") == _uid_str), None)
                if idx is not None:
                    rows[idx] = {**data, "id": _uid_str}
                else:
                    rows.append({**data, "id": _uid_str})
            else:
                rows.append({**data, "id": str(uuid4())})
            _um_proj.unit_mix = rows
            session.add(_um_proj)
