"""One-shot: rebuild the "Remove Rochelle - Add Edgemont" variant with the
fixed faithful-clone helpers.

The original variant (b22be693) was created by the pre-976b1a7 clone code and
is systematically degraded: float-earnings modules still point at Combined
Pool's bond (wrong scenario), 7 auto dev-fee + 6 auto acquisition-fee flags
were dropped (amounts frozen), ~35 use lines lost their timing milestones,
and all 8 draw sources were never copied. Two symptoms (duplicate finance-
cost rows, Office/Tower debt_sizing_mode reset) were hand-repaired on
2026-07-08; the rest is easier to rebuild than patch.

This script:
  1. renames the old variant "... (OLD — corrupt clone, superseded)"
  2. clones Combined Pool (4bc8fd71) minus Rochelle Villa via the SAME
     helpers the fixed /variant route uses (_clone_row,
     _copy_project_milestones, _copy_project_lines) — passes mirror
     create_deal_copy exactly
  3. adds Edgemont Weidler cloned from its standalone model (dbf59d85 /
     project 1e201ccd), adopting the new variant's shared Raymond James
     Bond via junction (same as add_edgemont_to_variant.py)
  4. computes the new scenario twice (float↔gap-fill needs two passes)

Run on VM 114 inside the api container, dry-run first::

    docker exec vicinitideals-api python -m app.scripts.rebuild_edgemont_variant
    docker exec vicinitideals-api python -m app.scripts.rebuild_edgemont_variant --commit
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import sys
from uuid import UUID

from sqlalchemy import select

from app.api.routers.ui_model_builder import (
    _clone_row,
    _copy_project_lines,
    _copy_project_milestones,
    _remap_id,
)
from app.db import AsyncSessionLocal
from app.models.capital import (
    CapitalModule,
    CapitalModuleProject,
    DrawSource,
    UseLineSourceFeeBasis,
    WaterfallTier,
)
from app.models.deal import Deal, Scenario
from app.models.project import Project, ProjectAnchor

CP_SCENARIO_ID = UUID("4bc8fd71-788a-47c6-b6cd-c5325e84ddd6")   # Combined Pool
OLD_VARIANT_ID = UUID("b22be693-fa53-4ced-9c8e-7be0ca52c390")   # corrupt clone
EXCLUDE_PROJECT_NAME = "Rochelle Villa"
NEW_VARIANT_NAME = "Remove Rochelle - Add Edgemont"

# Edgemont standalone source (same as add_edgemont_to_variant.py)
EDG_PROJECT_ID = UUID("1e201ccd-ab23-4432-be1a-662dc0d09b35")
EDG_BOND_ID = UUID("eaca5dce-19be-4b70-a7fe-f40c7e399a5a")
EDG_PROJECT_NAME = "Edgemont Weidler"


async def run(commit: bool, run_compute: bool) -> None:
    async with AsyncSessionLocal() as session:
        source = await session.get(Scenario, CP_SCENARIO_ID)
        old_variant = await session.get(Scenario, OLD_VARIANT_ID)
        if source is None or old_variant is None:
            print("FATAL: source or old variant scenario not found", file=sys.stderr)
            return
        deal = await session.get(Deal, source.deal_id)

        # Guard against double-run: old variant already renamed → we ran.
        if "superseded" in (old_variant.name or ""):
            print("FATAL: old variant already marked superseded — rebuilt already?",
                  file=sys.stderr)
            return

        old_variant.name = f"{old_variant.name} (OLD — corrupt clone, superseded)"
        session.add(old_variant)

        # ── New scenario via the factory, faithful Type 1 copy (mirrors the
        # fixed create_deal_copy) ──
        from app.services.scenario_factory import create_scenario as _create_scenario
        from app.settings.defaults import DEFAULT_REGISTRY
        new_scn, _, _ = await _create_scenario(
            session=session,
            deal_id=source.deal_id,
            deal_type=source.project_type,
            user_id=source.created_by_user_id,
            org_id=deal.org_id,
            name=NEW_VARIANT_NAME,
            version=source.version + 1,
            is_active=False,
            project_name=None,
            source_scenario=source,
        )
        for spec in DEFAULT_REGISTRY.values():
            if spec.type == 1 and spec.target == "scenario":
                src_val = getattr(source, spec.column, None)
                if src_val is not None:
                    setattr(new_scn, spec.column, src_val)

        # ── Pass 1: projects (minus Rochelle) + milestones ──
        source_projects = list((await session.execute(
            select(Project).where(Project.scenario_id == CP_SCENARIO_ID)
            .order_by(Project.created_at.asc())
        )).scalars())
        source_projects = [p for p in source_projects if p.name != EXCLUDE_PROJECT_NAME]
        if len(source_projects) != 7:
            print(f"FATAL: expected 7 non-Rochelle projects, got {len(source_projects)}",
                  file=sys.stderr)
            return

        project_id_map: dict = {}
        new_proj_by_old: dict = {}
        ms_id_map: dict = {}
        for src_proj in source_projects:
            new_proj = _clone_row(src_proj, scenario_id=new_scn.id)
            session.add(new_proj)
            await session.flush()
            project_id_map[src_proj.id] = new_proj.id
            new_proj_by_old[src_proj.id] = new_proj
            ms_id_map.update(await _copy_project_milestones(src_proj, new_proj, session))

        # ── Pass 2: capital modules + float JSONB remap ──
        src_modules = list((await session.execute(
            select(CapitalModule).where(CapitalModule.scenario_id == CP_SCENARIO_ID)
        )).scalars())
        module_id_map: dict = {}
        new_mod_by_old: dict = {}
        for cm in src_modules:
            new_cm = _clone_row(
                cm,
                scenario_id=new_scn.id,
                active_from_milestone_id=_remap_id(cm.active_from_milestone_id, ms_id_map),
                active_to_milestone_id=_remap_id(cm.active_to_milestone_id, ms_id_map),
            )
            session.add(new_cm)
            await session.flush()
            module_id_map[cm.id] = new_cm.id
            new_mod_by_old[cm.id] = new_cm
        for cm in src_modules:
            new_cm = new_mod_by_old[cm.id]
            src_json = new_cm.source or {}
            if str(new_cm.vehicle_type or "") != "float_earnings" or not src_json:
                continue
            new_src = copy.deepcopy(src_json)
            if src_json.get("parent_module_id"):
                new_src["parent_module_id"] = str(
                    _remap_id(UUID(str(src_json["parent_module_id"])), module_id_map))
            for ms_key in ("waterfall_milestone_id", "paydown_milestone_id"):
                old_ms = src_json.get(ms_key)
                if old_ms:
                    new_src[ms_key] = str(_remap_id(UUID(str(old_ms)), ms_id_map))
            new_cm.source = new_src

        # ── Pass 3: junctions ──
        junctions = 0
        for j in (await session.execute(
            select(CapitalModuleProject).where(
                CapitalModuleProject.capital_module_id.in_(list(module_id_map.keys())))
        )).scalars():
            new_pid = project_id_map.get(j.project_id)
            if new_pid is None:
                continue  # Rochelle's junction
            session.add(_clone_row(
                j,
                capital_module_id=module_id_map[j.capital_module_id],
                project_id=new_pid,
                active_from_milestone_id=_remap_id(j.active_from_milestone_id, ms_id_map),
                active_to_milestone_id=_remap_id(j.active_to_milestone_id, ms_id_map),
            ))
            junctions += 1

        # ── Pass 4: per-project lines ──
        ul_id_map: dict = {}
        for src_proj in source_projects:
            ul_id_map.update(await _copy_project_lines(
                src_proj, new_proj_by_old[src_proj.id], session, ms_id_map, module_id_map))

        # ── Pass 5: fee-basis rows ──
        fee_basis = 0
        if ul_id_map:
            for fb in (await session.execute(
                select(UseLineSourceFeeBasis).where(
                    UseLineSourceFeeBasis.use_line_id.in_(list(ul_id_map.keys())))
            )).scalars():
                new_mid = module_id_map.get(fb.capital_module_id)
                if new_mid is None:
                    continue
                session.add(_clone_row(
                    fb, use_line_id=ul_id_map[fb.use_line_id], capital_module_id=new_mid))
                fee_basis += 1

        # ── Pass 6: draw sources ──
        draw_sources = 0
        for ds in (await session.execute(
            select(DrawSource).where(DrawSource.scenario_id == CP_SCENARIO_ID)
        )).scalars():
            if ds.project_id is not None and ds.project_id not in project_id_map:
                continue  # Rochelle's
            session.add(_clone_row(
                ds,
                scenario_id=new_scn.id,
                project_id=_remap_id(ds.project_id, project_id_map),
                capital_module_id=_remap_id(ds.capital_module_id, module_id_map),
            ))
            draw_sources += 1

        # ── Pass 7: anchors ──
        anchors = 0
        for a in (await session.execute(
            select(ProjectAnchor).where(
                ProjectAnchor.project_id.in_(list(project_id_map.keys())))
        )).scalars():
            new_pid = project_id_map.get(a.project_id)
            new_parent = project_id_map.get(a.anchor_project_id)
            if new_pid is None or new_parent is None:
                continue
            session.add(_clone_row(
                a, project_id=new_pid, anchor_project_id=new_parent,
                anchor_milestone_id=ms_id_map.get(a.anchor_milestone_id)))
            anchors += 1

        # ── Pass 8: waterfall tiers ──
        tiers = 0
        for t in (await session.execute(
            select(WaterfallTier).where(WaterfallTier.scenario_id == CP_SCENARIO_ID)
        )).scalars():
            if t.project_id is not None and t.project_id not in project_id_map:
                continue
            session.add(_clone_row(
                t,
                scenario_id=new_scn.id,
                project_id=_remap_id(t.project_id, project_id_map),
                capital_module_id=_remap_id(t.capital_module_id, module_id_map),
            ))
            tiers += 1

        await session.flush()

        # ── Edgemont: clone standalone inputs, adopt the new variant's bond ──
        shared_bond = (await session.execute(
            select(CapitalModule).where(
                CapitalModule.scenario_id == new_scn.id,
                CapitalModule.vehicle_type == "debt",
            )
        )).scalar_one()
        edg_src = await session.get(Project, EDG_PROJECT_ID)
        if edg_src is None:
            print("FATAL: Edgemont source project not found", file=sys.stderr)
            return
        edg_module_map = {EDG_BOND_ID: shared_bond.id}
        edg_proj = _clone_row(edg_src, scenario_id=new_scn.id, name=EDG_PROJECT_NAME)
        session.add(edg_proj)
        await session.flush()
        edg_ms_map = await _copy_project_milestones(edg_src, edg_proj, session)
        edg_uls = await _copy_project_lines(
            edg_src, edg_proj, session, edg_ms_map, edg_module_map)
        # Drop the auto finance-cost clone — the engine regenerates it from
        # the shared bond (leaving it would double-count until first compute).
        from app.models.deal import UseLine
        for old_id, new_id in list(edg_uls.items()):
            ul = await session.get(UseLine, new_id)
            if ul is not None and getattr(ul, "is_auto_finance_cost", False):
                await session.delete(ul)
        src_cmp = (await session.execute(
            select(CapitalModuleProject).where(
                CapitalModuleProject.project_id == EDG_PROJECT_ID,
                CapitalModuleProject.capital_module_id == EDG_BOND_ID,
            )
        )).scalar_one()
        session.add(_clone_row(
            src_cmp,
            capital_module_id=shared_bond.id,
            project_id=edg_proj.id,
            active_from_milestone_id=_remap_id(src_cmp.active_from_milestone_id, edg_ms_map),
            active_to_milestone_id=_remap_id(src_cmp.active_to_milestone_id, edg_ms_map),
        ))
        await session.flush()

        print("── Rebuild summary ──")
        print(f"  new scenario : {new_scn.id} — {NEW_VARIANT_NAME}")
        print(f"  projects     : {len(project_id_map)} + Edgemont ({edg_proj.id})")
        print(f"  milestones   : {len(ms_id_map)} (+{len(edg_ms_map)} Edgemont)")
        print(f"  modules      : {len(module_id_map)} (Edgemont adopts {shared_bond.id})")
        print(f"  junctions    : {junctions} + 1 Edgemont")
        print(f"  use lines    : {len(ul_id_map)} (+{len(edg_uls)} Edgemont, auto-FC dropped)")
        print(f"  fee_basis    : {fee_basis}  draw_sources: {draw_sources}  "
              f"anchors: {anchors}  tiers: {tiers}")

        if not commit:
            await session.rollback()
            print("\nDRY RUN — rolled back. Re-run with --commit to persist.")
            return

        await session.commit()
        print("\nCOMMITTED.")
        new_id = new_scn.id

        if run_compute:
            from app.engines.cashflow import compute_cash_flows
            for i in (1, 2):  # two passes — float↔gap-fill convergence
                print(f"Compute pass {i} …")
                async with AsyncSessionLocal() as cs:
                    await compute_cash_flows(deal_model_id=new_id, session=cs)
                    await cs.commit()
            print("Compute complete.")
        print(f"\nOpen: /models/{new_id}/builder")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--commit", action="store_true", help="persist (default: dry-run + rollback)")
    ap.add_argument("--no-compute", action="store_true", help="skip recompute after commit")
    args = ap.parse_args()
    asyncio.run(run(commit=args.commit, run_compute=not args.no_compute))


if __name__ == "__main__":
    main()
