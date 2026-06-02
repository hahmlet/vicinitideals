"""
source_routing.py — Source-Use eligibility routing.

Default: permissive (empty tags = all sources eligible for all uses).
Non-empty whitelist activates matching: a source is eligible for a use
when either the source's eligible_use_tags OR the use's eligible_module_ids
is non-empty and the source/use ID is in that list.

Routing order: stable sort on (waterfall_position, cost_of_capital, source_id).
"""
from __future__ import annotations

from typing import Any


def eligible_sources_for_use(
    use_line: Any,
    capital_modules: list[Any],
) -> list[Any]:
    """Return capital modules eligible for this use line.

    A module is eligible if:
    - Both eligible_module_ids on use_line AND eligible_use_tags on module are empty
      (permissive), OR
    - use_line.eligible_module_ids contains this module's ID, OR
    - module.eligible_use_tags and use_line has a matching cost_category in those tags

    Always returns at least the full list when all are empty (permissive default).
    """
    use_eligible_ids = getattr(use_line, "eligible_module_ids", None) or []
    use_category = getattr(use_line, "cost_category", "") or ""

    result = []
    for m in capital_modules:
        # Float-earnings sources are never Use funders. They produce
        # side-effect outputs (debt-balloon reduction, dev fee top-up)
        # handled by `app/engines/float_earnings.py`, NOT routed through
        # the source-to-use eligibility solver. Excluding them here
        # prevents the gap-fill solver from double-counting them.
        vt = str(getattr(m, "vehicle_type", None) or "").replace("VehicleType.", "")
        if vt == "float_earnings":
            continue

        mod_tags = getattr(m, "eligible_use_tags", None) or []

        # Permissive: both empty → all eligible
        if not use_eligible_ids and not mod_tags:
            result.append(m)
            continue

        # Use-level whitelist: use specifies exact module IDs
        if use_eligible_ids:
            if str(m.id) in [str(x) for x in use_eligible_ids]:
                result.append(m)
            continue

        # Module-level tag whitelist: module restricts to certain use categories
        if mod_tags and use_category and use_category in mod_tags:
            result.append(m)
        elif mod_tags and not use_category:
            # No category on use → permissive for this use
            result.append(m)

    return result or list(capital_modules)  # fallback: never return empty


def route_use_to_sources(
    use_line: Any,
    capital_modules: list[Any],
) -> list[Any]:
    """Return eligible modules in routing order (stack_position asc, then id for stability)."""
    eligible = eligible_sources_for_use(use_line, capital_modules)
    return sorted(
        eligible,
        key=lambda m: (
            int(getattr(m, "stack_position", 0) or 0),
            str(getattr(m, "id", "")),
        ),
    )
