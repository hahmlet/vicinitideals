"""Shared ID-remapping restore helpers for deal entity graphs.

Extracted from ``app/exporters/snapshot.py``'s revert logic so snapshot
revert, deal-json import (``app/exporters/json_import.py``), and template
apply (``app/exporters/template_apply.py``) all rewire cross-entity
references the same way when re-creating rows with fresh UUIDs:

- Milestone trigger chains (``trigger_milestone_id``) — two-pass create.
- CapitalModule milestone anchors (``active_from/to_milestone_id``).
- UseLine milestone FKs, ``eligible_module_ids`` whitelists, and Dev Fee
  release-schedule milestone references.
- DrawSource / WaterfallTier ``capital_module_id`` and ``project_id`` FKs.

All helpers take *dict* payloads (JSON-safe, as produced by the exporters)
and validate through the canonical Pydantic Base schemas so the restored
rows can never carry fields the schema does not know about.

``strict=False`` (snapshot revert): per-row failures are logged and the row
is skipped. ``strict=True`` (JSON import): the original exception propagates.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capital import CapitalModule, DrawSource, WaterfallTier
from app.models.deal import UseLine
from app.models.milestone import Milestone
from app.schemas.capital import CapitalModuleBase, DrawSourceBase, WaterfallTierBase
from app.schemas.deal import UseLineBase

logger = logging.getLogger(__name__)

MissingCapitalModulePolicy = Literal["keep", "error", "null", "skip"]


# ── Low-level utilities ───────────────────────────────────────────────────────

def _json_safe(obj: Any) -> Any:
    """Round-trip through json.dumps so nested values are native JSON types.

    Mirrors the helper previously private to snapshot.py: Decimal → float,
    UUID → str, date/datetime → ISO string.  Needed before feeding dicts
    into JSONB columns (the cashflow engine chokes on stringified Decimals).
    """
    def _default(o: Any) -> Any:
        if isinstance(o, Decimal):
            return float(o)
        if isinstance(o, UUID):
            return str(o)
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        raise TypeError(f"Object of type {type(o)} is not JSON serializable")
    return json.loads(json.dumps(obj, default=_default))


def _parse_iso_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _remap_uuid(value: Any, id_map: dict[str, UUID] | None) -> UUID | None:
    """Map an old entity ID to its new UUID; unmappable → None (never stale)."""
    if value is None:
        return None
    return (id_map or {}).get(str(value))


# ── Milestones (two-pass trigger-chain rewire) ────────────────────────────────

async def restore_milestones(
    session: AsyncSession,
    *,
    project_id: UUID,
    milestone_payloads: list[dict[str, Any]] | None,
    milestone_id_map: dict[str, UUID] | None = None,
    log_context: str = "restore",
    strict: bool = False,
) -> dict[str, UUID]:
    """Create milestones for *project_id* from exported dict payloads.

    Pass 1 inserts every row with ``trigger_milestone_id=None``; pass 2
    rewires triggers via the accumulated old→new map, so chains point at the
    NEW rows.  Returns (and extends, when given) the str(old_id) → new UUID
    map — pass the same dict across multiple projects to build a
    scenario-wide map.
    """
    id_map: dict[str, UUID] = milestone_id_map if milestone_id_map is not None else {}
    created: list[tuple[dict[str, Any], Milestone]] = []
    for ms_data in milestone_payloads or []:
        try:
            new_ms = Milestone(
                project_id=project_id,
                milestone_type=str(ms_data.get("milestone_type") or ""),
                duration_days=int(ms_data.get("duration_days") or 0),
                target_date=_parse_iso_date(ms_data.get("target_date")),
                sequence_order=int(ms_data.get("sequence_order") or 1),
                label=ms_data.get("label"),
                trigger_offset_days=int(ms_data.get("trigger_offset_days") or 0),
                trigger_milestone_id=None,
            )
            session.add(new_ms)
            await session.flush()
            old_id = ms_data.get("id")
            if old_id:
                id_map[str(old_id)] = new_ms.id
            created.append((ms_data, new_ms))
        except Exception:
            if strict:
                raise
            logger.warning("%s: skipped Milestone restore", log_context, exc_info=True)

    for ms_data, new_ms in created:
        old_trigger_id = ms_data.get("trigger_milestone_id")
        if old_trigger_id and str(old_trigger_id) in id_map:
            new_ms.trigger_milestone_id = id_map[str(old_trigger_id)]

    return id_map


# ── Capital modules ───────────────────────────────────────────────────────────

async def restore_capital_modules(
    session: AsyncSession,
    *,
    scenario_id: UUID,
    module_payloads: list[dict[str, Any]] | None,
    milestone_id_map: dict[str, UUID] | None = None,
    cap_id_map: dict[str, UUID] | None = None,
    log_context: str = "restore",
    strict: bool = False,
) -> tuple[dict[str, UUID], dict[str, bool]]:
    """Create CapitalModules from exported dict payloads.

    Milestone anchor FKs (``active_from/to_milestone_id``) are remapped to
    the new milestone rows; anchors that cannot be remapped become NULL so
    no dangling FK is ever written.

    Returns ``(cap_id_map, cap_auto_size)``:
    - cap_id_map: str(old module id) → new UUID
    - cap_auto_size: str(new module id) → source.auto_size flag (used by
      snapshot revert's legacy junction fallback)
    """
    id_map: dict[str, UUID] = cap_id_map if cap_id_map is not None else {}
    auto_size: dict[str, bool] = {}
    for mod_data in module_payloads or []:
        try:
            old_id = mod_data.get("id")
            _src_auto = bool((mod_data.get("source") or {}).get("auto_size"))
            payload = _json_safe(
                CapitalModuleBase.model_validate(mod_data).model_dump(exclude_unset=True)
            )
            payload.pop("id", None)
            for fk in ("active_from_milestone_id", "active_to_milestone_id"):
                if fk in payload:
                    payload[fk] = _remap_uuid(payload[fk], milestone_id_map)
            new_mod = CapitalModule(scenario_id=scenario_id, **payload)
            session.add(new_mod)
            await session.flush()
            if old_id:
                id_map[str(old_id)] = new_mod.id
                auto_size[str(new_mod.id)] = _src_auto
        except Exception:
            if strict:
                raise
            logger.warning("%s: skipped CapitalModule restore", log_context, exc_info=True)
    return id_map, auto_size


# ── Use lines ─────────────────────────────────────────────────────────────────

def _remap_release_schedule(
    schedule: dict[str, Any], milestone_id_map: dict[str, UUID] | None
) -> dict[str, Any]:
    """Remap milestone_id references inside a Dev Fee release schedule.

    Entries that cannot be remapped are left untouched (the engine
    re-validates the schedule against the live milestone graph on compute).
    """
    if not schedule or not milestone_id_map:
        return schedule
    out = dict(schedule)
    weights = []
    for entry in out.get("weights") or []:
        entry = dict(entry) if isinstance(entry, dict) else entry
        if isinstance(entry, dict):
            new_id = _remap_uuid(entry.get("milestone_id"), milestone_id_map)
            if new_id is not None:
                entry["milestone_id"] = str(new_id)
        weights.append(entry)
    if weights:
        out["weights"] = weights
    holdback = out.get("final_holdback")
    if isinstance(holdback, dict):
        new_id = _remap_uuid(holdback.get("milestone_id"), milestone_id_map)
        if new_id is not None:
            out["final_holdback"] = {**holdback, "milestone_id": str(new_id)}
    return out


async def restore_use_lines(
    session: AsyncSession,
    *,
    project_id: UUID,
    use_line_payloads: list[dict[str, Any]] | None,
    cap_id_map: dict[str, UUID] | None = None,
    milestone_id_map: dict[str, UUID] | None = None,
    log_context: str = "restore",
    strict: bool = False,
) -> None:
    """Create UseLines, remapping capital-module and milestone references.

    - ``eligible_module_ids``: each entry remapped via cap_id_map; entries
      that cannot be remapped are dropped (a stale whitelist entry would
      silently starve the Use of funding).
    - ``active_from/spread_to_milestone_id``: remapped or NULLed.
    - ``dev_fee_release_schedule``: milestone_ids remapped where possible.
    """
    for use_data in use_line_payloads or []:
        try:
            parsed = UseLineBase.model_validate(use_data)
            payload = parsed.model_dump(exclude_unset=True)
            for fk in ("active_from_milestone_id", "spread_to_milestone_id"):
                if fk in payload:
                    payload[fk] = _remap_uuid(payload[fk], milestone_id_map)
            if payload.get("eligible_module_ids"):
                remapped = [
                    _remap_uuid(module_id, cap_id_map)
                    for module_id in payload["eligible_module_ids"]
                ]
                payload["eligible_module_ids"] = [m for m in remapped if m is not None]
            if payload.get("dev_fee_release_schedule"):
                payload["dev_fee_release_schedule"] = _remap_release_schedule(
                    _json_safe(payload["dev_fee_release_schedule"]), milestone_id_map
                )
            if payload.get("dev_fee_binding_context"):
                # Engine-written display blob; keep bytes as-is (recomputed on
                # next compute pass) but ensure JSON-native types.
                payload["dev_fee_binding_context"] = _json_safe(
                    payload["dev_fee_binding_context"]
                )
            session.add(UseLine(project_id=project_id, **payload))
        except Exception:
            if strict:
                raise
            logger.warning("%s: skipped UseLine restore", log_context, exc_info=True)


# ── Draw sources ──────────────────────────────────────────────────────────────

async def restore_draw_sources(
    session: AsyncSession,
    *,
    scenario_id: UUID,
    draw_source_payloads: list[dict[str, Any]] | None,
    cap_id_map: dict[str, UUID] | None = None,
    default_project_id: UUID | None = None,
    log_context: str = "restore",
    strict: bool = False,
    on_missing_capital_module: MissingCapitalModulePolicy = "keep",
) -> None:
    """Create DrawSources, remapping ``capital_module_id`` (and project).

    ``on_missing_capital_module`` controls what happens when the payload
    references a module id absent from cap_id_map:
    - "keep": leave the original id (snapshot-revert legacy behavior).
    - "error": raise ValueError (JSON import — payload must be closed).
    - "null": clear the link.
    - "skip": drop the row.
    """
    for ds_data in draw_source_payloads or []:
        try:
            old_cap_id = ds_data.get("capital_module_id")
            payload = _json_safe(
                DrawSourceBase.model_validate(ds_data).model_dump(exclude_unset=True)
            )
            if old_cap_id is not None:
                new_cap_id = _remap_uuid(old_cap_id, cap_id_map)
                if new_cap_id is not None:
                    payload["capital_module_id"] = new_cap_id
                elif on_missing_capital_module == "error":
                    raise ValueError(
                        "draw_sources references a capital_module_id that is not present in the import payload"
                    )
                elif on_missing_capital_module == "null":
                    payload["capital_module_id"] = None
                elif on_missing_capital_module == "skip":
                    continue
            if default_project_id is not None and "project_id" in payload:
                payload["project_id"] = (
                    default_project_id if payload["project_id"] is not None else None
                )
            session.add(DrawSource(scenario_id=scenario_id, **payload))
        except Exception:
            if strict:
                raise
            logger.warning("%s: skipped DrawSource restore", log_context, exc_info=True)


# ── Waterfall tiers ───────────────────────────────────────────────────────────

async def restore_waterfall_tiers(
    session: AsyncSession,
    *,
    scenario_id: UUID,
    tier_payloads: list[dict[str, Any]] | None,
    cap_id_map: dict[str, UUID] | None = None,
    default_project_id: UUID | None = None,
    log_context: str = "restore",
    strict: bool = False,
    on_missing_capital_module: MissingCapitalModulePolicy = "keep",
) -> None:
    """Create WaterfallTiers, remapping ``capital_module_id`` (and project).

    See ``restore_draw_sources`` for the ``on_missing_capital_module``
    semantics.  "error" preserves the historical json_import ValueError.
    """
    for tier_data in tier_payloads or []:
        try:
            old_cap_id = tier_data.get("capital_module_id")
            payload = _json_safe(
                WaterfallTierBase.model_validate(tier_data).model_dump(exclude_unset=True)
            )
            payload.pop("id", None)
            if old_cap_id is not None:
                new_cap_id = _remap_uuid(old_cap_id, cap_id_map)
                if new_cap_id is not None:
                    payload["capital_module_id"] = new_cap_id
                elif on_missing_capital_module == "error":
                    raise ValueError(
                        "waterfall_tiers references a capital_module_id that is not present in the import payload"
                    )
                elif on_missing_capital_module == "null":
                    payload["capital_module_id"] = None
                elif on_missing_capital_module == "skip":
                    continue
            if default_project_id is not None and "project_id" in payload:
                payload["project_id"] = (
                    default_project_id if payload["project_id"] is not None else None
                )
            session.add(WaterfallTier(scenario_id=scenario_id, **payload))
        except Exception:
            if strict:
                raise
            logger.warning("%s: skipped WaterfallTier restore", log_context, exc_info=True)


__all__ = [
    "restore_capital_modules",
    "restore_draw_sources",
    "restore_milestones",
    "restore_use_lines",
    "restore_waterfall_tiers",
]
