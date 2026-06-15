"""Pattern-scoped purge of accumulated E2E / regression **test deals**.

Shared by the one-shot CLI (``app.scripts.cleanup_test_deals``) and the daily
Celery janitor (``app.tasks.maintenance.purge_test_deals_task``) so both use the
exact same FK-ordered delete graph and the exact same match predicate.

What counts as a test deal
--------------------------
The same predicate the ``hide_test`` UI filter uses, applied to the row ``name``::

    name ILIKE '%e2e%'  OR  name ~* 'phase\\s+\\w+\\s+test\\s+\\w+'

so "anything Hide Test hides" is exactly what gets deleted and nothing else.
(NULL names coalesce to '' so they never match.)

A wizard "deal" is an ``Opportunity`` + a top-level ``Deal`` + a ``Scenario``
(``scenarios.deal_id`` -> ``deals.id``) + one or more ``Project`` rows
(``projects.opportunity_id`` and ``projects.scenario_id``) and their financial
children. All of that gets removed.

Safety
------
* **Scenario / Deal guard.** A scenario (or top-level deal) is deleted only when
  every project/scenario that references it is itself in the delete set — a row
  shared with a non-test record is never touched.
* **Optional age guard.** ``max_age_hours`` restricts deletion to rows older than
  that many hours (the daily janitor passes a few hours so an in-flight test
  run's freshly-created deal is never swept mid-run). ``None`` = no age limit
  (the one-shot CLI default).
* **Caller-chosen commit.** ``execute=False`` rolls everything back (dry-run);
  ``execute=True`` commits. Every statement runs in one transaction, so any
  unforeseen FK failure rolls the whole thing back and deletes ZERO rows.

Delete order (deepest child -> root), derived from the live FK graph::

    sensitivity_results, cash_flow_line_items, waterfall_results, waterfall_tiers
    -> use_lines, income_streams, operating_expense_lines, operational_inputs
    -> capital_modules, cash_flows, operational_outputs, portfolio_projects,
       sensitivities, workflow_run_manifests
    -> projects -> scenarios -> deals -> opportunities
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Matches the hide_test UI filter exactly (app/api/routers/ui.py:_apply_opp_filters).
# Unqualified ``name`` resolves to the table of each enclosing query (opportunities
# or deals — both have a ``name`` column).
_MATCH = (
    r"coalesce(name, '') ILIKE '%e2e%' "
    r"OR coalesce(name, '') ~* 'phase\s+\w+\s+test\s+\w+'"
)


def _setup_statements(max_age_hours: int | None) -> list[str]:
    """Build the temp-table scaffolding, optionally age-restricted.

    ``opportunities.scraped_at`` is the creation/last-seen stamp (NOT NULL,
    DEFAULT now()); test deals are never re-scraped so it == creation time.
    ``deals.created_at`` guards the already-orphaned-deal branch. ``max_age_hours``
    is an int we control (never user input), so inline interpolation is safe.
    """
    opp_age = deal_age = ""
    if max_age_hours is not None:
        h = int(max_age_hours)
        opp_age = f" AND scraped_at < now() - make_interval(hours => {h})"
        deal_age = f" AND created_at < now() - make_interval(hours => {h})"
    return [
        # Matched opportunities.
        f"CREATE TEMP TABLE _t_opps ON COMMIT DROP AS "
        f"SELECT id FROM opportunities WHERE ({_MATCH}){opp_age}",
        # Their projects.
        "CREATE TEMP TABLE _t_projs ON COMMIT DROP AS "
        "SELECT id, scenario_id FROM projects WHERE opportunity_id IN (SELECT id FROM _t_opps)",
        # Scenarios owned *exclusively* by those projects (never a shared scenario).
        "CREATE TEMP TABLE _t_scens ON COMMIT DROP AS "
        "SELECT c.s_id FROM (SELECT DISTINCT scenario_id AS s_id FROM _t_projs WHERE scenario_id IS NOT NULL) c "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM projects p WHERE p.scenario_id = c.s_id "
        "  AND p.id NOT IN (SELECT id FROM _t_projs))",
        # Top-level deals: either reachable from a matched scenario (the normal
        # forward graph), OR an already-orphaned test-named deal (a leftover whose
        # scenario was removed by an earlier, incomplete cleanup). Either way, only
        # when every scenario referencing the deal is itself being deleted.
        f"CREATE TEMP TABLE _t_deals ON COMMIT DROP AS "
        f"SELECT d.id FROM deals d WHERE ("
        f"  d.id IN (SELECT deal_id FROM scenarios WHERE id IN (SELECT s_id FROM _t_scens) AND deal_id IS NOT NULL)"
        f"  OR (({_MATCH}) AND NOT EXISTS (SELECT 1 FROM scenarios s WHERE s.deal_id = d.id){deal_age})"
        f") AND NOT EXISTS ("
        f"  SELECT 1 FROM scenarios s WHERE s.deal_id = d.id AND s.id NOT IN (SELECT s_id FROM _t_scens))",
    ]


# Ordered deletes. Each entry: (label, SQL). Order matters — see module docstring.
_DELETES = [
    # --- deepest leaves that block NO ACTION parents ---
    ("sensitivity_results",
     "DELETE FROM sensitivity_results WHERE sensitivity_id IN ("
     " SELECT id FROM sensitivities WHERE scenario_id IN (SELECT s_id FROM _t_scens)"
     " OR opportunity_id IN (SELECT id FROM _t_opps))"),
    ("cash_flow_line_items",
     "DELETE FROM cash_flow_line_items WHERE scenario_id IN (SELECT s_id FROM _t_scens)"
     " OR project_id IN (SELECT id FROM _t_projs)"),
    ("waterfall_results",
     "DELETE FROM waterfall_results WHERE scenario_id IN (SELECT s_id FROM _t_scens)"
     " OR project_id IN (SELECT id FROM _t_projs)"),
    ("waterfall_tiers",
     "DELETE FROM waterfall_tiers WHERE scenario_id IN (SELECT s_id FROM _t_scens)"
     " OR project_id IN (SELECT id FROM _t_projs)"),
    # --- project NO ACTION children ---
    ("use_lines",
     "DELETE FROM use_lines WHERE project_id IN (SELECT id FROM _t_projs)"),
    ("income_streams",
     "DELETE FROM income_streams WHERE project_id IN (SELECT id FROM _t_projs)"),
    ("operating_expense_lines",
     "DELETE FROM operating_expense_lines WHERE project_id IN (SELECT id FROM _t_projs)"),
    ("operational_inputs",
     "DELETE FROM operational_inputs WHERE project_id IN (SELECT id FROM _t_projs)"),
    # --- scenario NO ACTION children ---
    ("capital_modules",
     "DELETE FROM capital_modules WHERE scenario_id IN (SELECT s_id FROM _t_scens)"),
    ("cash_flows",
     "DELETE FROM cash_flows WHERE scenario_id IN (SELECT s_id FROM _t_scens)"
     " OR project_id IN (SELECT id FROM _t_projs)"),
    ("operational_outputs",
     "DELETE FROM operational_outputs WHERE scenario_id IN (SELECT s_id FROM _t_scens)"
     " OR project_id IN (SELECT id FROM _t_projs)"),
    ("portfolio_projects",
     "DELETE FROM portfolio_projects WHERE scenario_id IN (SELECT s_id FROM _t_scens)"
     " OR project_id IN (SELECT id FROM _t_opps)"),
    ("sensitivities",
     "DELETE FROM sensitivities WHERE scenario_id IN (SELECT s_id FROM _t_scens)"
     " OR opportunity_id IN (SELECT id FROM _t_opps)"),
    ("workflow_run_manifests",
     "DELETE FROM workflow_run_manifests WHERE scenario_id IN (SELECT s_id FROM _t_scens)"),
    # --- the roots (cascade handles their remaining children) ---
    ("projects",
     "DELETE FROM projects WHERE id IN (SELECT id FROM _t_projs)"),
    ("scenarios",
     "DELETE FROM scenarios WHERE id IN (SELECT s_id FROM _t_scens)"),
    # deals must follow scenarios: scenarios.deal_id references deals.id.
    ("deals",
     "DELETE FROM deals WHERE id IN (SELECT id FROM _t_deals)"),
    ("opportunities",
     "DELETE FROM opportunities WHERE id IN (SELECT id FROM _t_opps)"),
]


async def purge_test_deals(
    session: AsyncSession,
    *,
    execute: bool,
    max_age_hours: int | None = None,
) -> dict[str, Any]:
    """Delete every test deal (and its full graph) matched by the predicate.

    Returns a summary dict: ``matched`` (root row counts), ``rows_affected``
    (per-table delete counts), ``total_rows``, ``executed``, ``max_age_hours``.
    Commits when ``execute`` is True, otherwise rolls back (dry-run).
    """
    for stmt in _setup_statements(max_age_hours):
        await session.execute(text(stmt))

    matched: dict[str, int] = {}
    for label, tbl in (
        ("opportunities", "_t_opps"),
        ("projects", "_t_projs"),
        ("scenarios", "_t_scens"),
        ("deals", "_t_deals"),
    ):
        matched[label] = (await session.execute(text(f"SELECT count(*) FROM {tbl}"))).scalar_one()

    rows_affected: dict[str, int] = {}
    total = 0
    # Run the deletes when there is anything to remove — note orphan deals can
    # exist even with zero matched opportunities (a leftover from a prior cleanup).
    if matched["opportunities"] or matched["deals"]:
        for label, stmt in _DELETES:
            res = await session.execute(text(stmt))
            n = res.rowcount or 0
            rows_affected[label] = n
            total += n

    if execute:
        await session.commit()
    else:
        await session.rollback()

    return {
        "matched": matched,
        "rows_affected": rows_affected,
        "total_rows": total,
        "executed": execute,
        "max_age_hours": max_age_hours,
    }
