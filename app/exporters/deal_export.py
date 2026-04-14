"""Deal-level JSON export and import — full round-trip portable format.

Export shape:
    {
        "export_version": "deal-v1",
        "exported_at": "...",
        "deal": {
            "name": "...",
            "status": "active",
            "created_at": "...",
            "opportunities": [
                {
                    "name": "...",
                    "status": "...",
                    "source": "...",
                    "parcels": [{"apn": "...", "address": "..."}],
                    "listings": [
                        {
                            "source_url": "...",
                            "source": "crexi",
                            "asking_price": ...,
                            ... (deal-relevant listing fields)
                        }
                    ]
                }
            ],
            "scenarios": [
                {
                    "name": "...",
                    "project_type": "...",
                    "projects": [
                        {
                            "name": "...",
                            "deal_type": "...",
                            "operational_inputs": {...},
                            "unit_mix": [...],
                            "use_lines": [...],
                            "expense_lines": [...],
                            "income_streams": [...]
                        }
                    ],
                    "capital_modules": [...],
                    "waterfall_tiers": [...]
                }
            ]
        }
    }

Excluded intentionally:
  - raw_json / realie_raw_json (source noise, large)
  - Computed outputs: cash_flows, waterfall_results, operational_outputs
    (recomputed by the engine on import — not inputs)
  - org_id / user_id (account-specific — assigned fresh on import)
  - priority_bucket / ingest flags (operational state, not deal data)
  - parcel geometry and GIS fields (reference by APN only)
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.capital import CapitalModule, WaterfallTier
from app.models.deal import (
    Deal,
    DealModel,
    DealOpportunity,
    DealStatus,
    IncomeStream,
    OperatingExpenseLine,
    OperationalInputs,
    UnitMix,
    UseLine,
)
from app.models.parcel import Parcel, ProjectParcel, ProjectParcelRelationship
from app.models.project import Opportunity, Project
from app.models.scraped_listing import ScrapedListing

DEAL_EXPORT_VERSION = "deal-v1"

# Listing fields that are deal-relevant (exclude raw blobs, ingest state, GIS routing)
_LISTING_FIELDS = [
    "source",
    "source_url",
    "listing_name",
    "address_raw",
    "address_normalized",
    "street",
    "city",
    "state_code",
    "zip_code",
    "lat",
    "lng",
    "property_type",
    "sub_type",
    "investment_type",
    "asking_price",
    "price_per_sqft",
    "price_per_unit",
    "price_per_sqft_land",
    "gba_sqft",
    "net_rentable_sqft",
    "lot_sqft",
    "year_built",
    "year_renovated",
    "units",
    "buildings",
    "stories",
    "parking_spaces",
    "class_",
    "zoning",
    "apn",
    "occupancy_pct",
    "cap_rate",
    "proforma_cap_rate",
    "noi",
    "proforma_noi",
    "sale_condition",
    "ownership",
    "is_in_opportunity_zone",
    "description",
    "status",
    "listed_at",
]


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _v(value: Any) -> Any:
    """Convert Decimal/Enum/UUID/datetime to JSON-safe primitives."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _dump(obj: Any, fields: list[str]) -> dict[str, Any]:
    return {f: _v(getattr(obj, f, None)) for f in fields}


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def _export_listing(listing: ScrapedListing) -> dict[str, Any]:
    d = _dump(listing, _LISTING_FIELDS)
    # Normalise synonym aliases to canonical names
    d["source_url"] = _v(listing.source_url)
    d["units"] = listing.units
    d["cap_rate"] = _v(listing.cap_rate)
    d["gba_sqft"] = _v(listing.gba_sqft)
    if listing.broker:
        d["broker"] = {
            "name": listing.broker.name,
            "email": getattr(listing.broker, "email", None),
            "phone": getattr(listing.broker, "phone", None),
        }
    return d


def _export_operational_inputs(oi: OperationalInputs) -> dict[str, Any]:
    skip = {"id", "project_id"}
    return {
        col.key: _v(getattr(oi, col.key))
        for col in oi.__table__.columns
        if col.key not in skip
    }


def _export_project(project: Project) -> dict[str, Any]:
    oi = project.operational_inputs
    return {
        "name": project.name,
        "deal_type": project.deal_type,
        "timeline_approved": project.timeline_approved,
        "operational_inputs": _export_operational_inputs(oi) if oi else None,
        "unit_mix": [
            _dump(u, ["label", "unit_count", "avg_sqft", "avg_monthly_rent", "notes"])
            for u in sorted(project.unit_mix, key=lambda u: u.label)
        ],
        "use_lines": [
            _dump(u, ["label", "phase", "amount", "timing_type", "is_deferred", "notes"])
            for u in sorted(project.use_lines, key=lambda u: (u.phase, u.label))
        ],
        "expense_lines": [
            _dump(e, [
                "label", "annual_amount", "per_value", "per_type",
                "scale_with_lease_up", "lease_up_floor_pct",
                "escalation_rate_pct_annual", "active_in_phases", "notes",
            ])
            for e in sorted(project.expense_lines, key=lambda e: e.label)
        ],
        "income_streams": [
            _dump(s, [
                "stream_type", "label", "unit_count",
                "amount_per_unit_monthly", "amount_fixed_monthly",
                "stabilized_occupancy_pct", "escalation_rate_pct_annual",
                "active_in_phases", "notes",
            ])
            for s in sorted(project.income_streams, key=lambda s: s.label)
        ],
    }


def _export_scenario(scenario: DealModel) -> dict[str, Any]:
    return {
        "name": scenario.name,
        "version": scenario.version,
        "is_active": scenario.is_active,
        "project_type": _v(scenario.project_type),
        "created_at": _v(scenario.created_at),
        "projects": [
            _export_project(p)
            for p in sorted(scenario.projects, key=lambda p: p.created_at)
        ],
        "capital_modules": [
            {
                "label": m.label,
                "funder_type": _v(m.funder_type),
                "stack_position": m.stack_position,
                "source": m.source,
                "carry": m.carry,
                "exit_terms": m.exit_terms,
                "active_phase_start": m.active_phase_start,
                "active_phase_end": m.active_phase_end,
                "_export_id": str(m.id),  # used to remap waterfall_tier references on import
            }
            for m in sorted(scenario.capital_modules, key=lambda m: m.stack_position)
        ],
        "waterfall_tiers": [
            {
                "priority": t.priority,
                "tier_type": _v(t.tier_type),
                "irr_hurdle_pct": _v(t.irr_hurdle_pct),
                "lp_split_pct": _v(t.lp_split_pct),
                "gp_split_pct": _v(t.gp_split_pct),
                "description": t.description,
                "max_pct_of_distributable": _v(t.max_pct_of_distributable),
                "interest_rate_pct": _v(t.interest_rate_pct),
                "_capital_module_export_id": str(t.capital_module_id) if t.capital_module_id else None,
            }
            for t in sorted(scenario.waterfall_tiers, key=lambda t: t.priority)
        ],
    }


def _export_opportunity(opp: Opportunity) -> dict[str, Any]:
    parcels = [
        {
            "apn": pp.parcel.apn,
            "address": pp.parcel.address_normalized or pp.parcel.address_raw,
        }
        for pp in opp.project_parcels
        if pp.parcel is not None
    ]
    listings = [_export_listing(l) for l in opp.scraped_listings]
    return {
        "name": opp.name,
        "status": _v(opp.status),
        "source": _v(opp.source),
        "created_at": _v(opp.created_at),
        "parcels": parcels,
        "listings": listings,
    }


async def export_deal_json(session: AsyncSession, deal_id: UUID) -> dict[str, Any]:
    """Return the full portable JSON export for a Deal."""
    result = await session.execute(
        select(Deal)
        .options(
            selectinload(Deal.deal_opportunities).selectinload(DealOpportunity.opportunity).options(
                selectinload(Opportunity.project_parcels).selectinload(ProjectParcel.parcel),
                selectinload(Opportunity.scraped_listings).selectinload(ScrapedListing.broker),
            ),
            selectinload(Deal.scenarios).options(
                selectinload(DealModel.projects).options(
                    selectinload(Project.operational_inputs),
                    selectinload(Project.unit_mix),
                    selectinload(Project.use_lines),
                    selectinload(Project.expense_lines),
                    selectinload(Project.income_streams),
                ),
                selectinload(DealModel.capital_modules),
                selectinload(DealModel.waterfall_tiers),
            ),
        )
        .where(Deal.id == deal_id)
    )
    deal = result.scalar_one_or_none()
    if deal is None:
        raise ValueError(f"Deal {deal_id} not found")

    return {
        "export_version": DEAL_EXPORT_VERSION,
        "exported_at": datetime.now(UTC).isoformat(),
        "deal": {
            "name": deal.name,
            "status": _v(deal.status),
            "created_at": _v(deal.created_at),
            "opportunities": [
                _export_opportunity(do.opportunity)
                for do in deal.deal_opportunities
                if do.opportunity is not None
            ],
            "scenarios": [
                _export_scenario(s)
                for s in sorted(deal.scenarios, key=lambda s: s.created_at)
            ],
        },
    }


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

async def import_deal_json(
    session: AsyncSession,
    *,
    org_id: UUID,
    payload: dict[str, Any],
    created_by_user_id: UUID | None = None,
) -> Deal:
    """Create a full Deal from an exported JSON payload. Returns the new Deal."""
    version = payload.get("export_version")
    if version != DEAL_EXPORT_VERSION:
        raise ValueError(f"Unsupported export_version '{version}'. Expected '{DEAL_EXPORT_VERSION}'.")

    deal_data = payload["deal"]

    deal = Deal(
        org_id=org_id,
        name=deal_data["name"],
        status=DealStatus(deal_data.get("status", "active")),
        created_by_user_id=created_by_user_id,
    )
    session.add(deal)
    await session.flush()

    # Opportunities
    opp_map: dict[int, Opportunity] = {}
    for idx, opp_data in enumerate(deal_data.get("opportunities") or []):
        opp = Opportunity(
            org_id=org_id,
            name=opp_data["name"],
            status=opp_data.get("status", "hypothetical"),
            source=opp_data.get("source"),
            created_by_user_id=created_by_user_id,
        )
        session.add(opp)
        await session.flush()
        opp_map[idx] = opp

        session.add(DealOpportunity(deal_id=deal.id, opportunity_id=opp.id))

        # Parcels — look up by APN, create stub if not found
        for p_data in opp_data.get("parcels") or []:
            apn = (p_data.get("apn") or "").strip()
            if not apn:
                continue
            parcel = (
                await session.execute(select(Parcel).where(Parcel.apn == apn))
            ).scalar_one_or_none()
            if parcel is None:
                parcel = Parcel(apn=apn, address_normalized=p_data.get("address"))
                session.add(parcel)
                await session.flush()
            session.add(
                ProjectParcel(
                    project_id=opp.id,
                    parcel_id=parcel.id,
                    relationship_type=ProjectParcelRelationship.unchanged,
                )
            )

        # Listings — create stubs with deal-relevant fields; source_url is the canonical ref
        for l_data in opp_data.get("listings") or []:
            source_url = l_data.get("source_url") or ""
            source = l_data.get("source") or "manual"
            if not source_url:
                continue
            listing = ScrapedListing(
                source=source,
                source_url=source_url,
                linked_project_id=opp.id,
                **{
                    k: l_data.get(k)
                    for k in _LISTING_FIELDS
                    if k not in ("source", "source_url") and l_data.get(k) is not None
                },
            )
            session.add(listing)

        await session.flush()

    # Scenarios
    for s_data in deal_data.get("scenarios") or []:
        scenario = DealModel(
            deal_id=deal.id,
            name=s_data["name"],
            version=s_data.get("version", 1),
            is_active=s_data.get("is_active", True),
            project_type=s_data["project_type"],
            created_by_user_id=created_by_user_id,
        )
        session.add(scenario)
        await session.flush()

        # Capital modules — build export_id → new DB id map for waterfall remapping
        cap_id_map: dict[str, UUID] = {}
        for cm_data in s_data.get("capital_modules") or []:
            export_id = cm_data.get("_export_id")
            mod = CapitalModule(
                scenario_id=scenario.id,
                label=cm_data["label"],
                funder_type=cm_data["funder_type"],
                stack_position=cm_data.get("stack_position", 0),
                source=cm_data.get("source"),
                carry=cm_data.get("carry"),
                exit_terms=cm_data.get("exit_terms"),
                active_phase_start=cm_data.get("active_phase_start"),
                active_phase_end=cm_data.get("active_phase_end"),
            )
            session.add(mod)
            await session.flush()
            if export_id:
                cap_id_map[export_id] = mod.id

        # Waterfall tiers
        for t_data in s_data.get("waterfall_tiers") or []:
            cap_ref = t_data.get("_capital_module_export_id")
            session.add(WaterfallTier(
                scenario_id=scenario.id,
                priority=t_data["priority"],
                tier_type=t_data["tier_type"],
                irr_hurdle_pct=t_data.get("irr_hurdle_pct"),
                lp_split_pct=t_data.get("lp_split_pct", 0),
                gp_split_pct=t_data.get("gp_split_pct", 0),
                description=t_data.get("description"),
                max_pct_of_distributable=t_data.get("max_pct_of_distributable"),
                interest_rate_pct=t_data.get("interest_rate_pct"),
                capital_module_id=cap_id_map.get(cap_ref) if cap_ref else None,
            ))

        # Projects (dev efforts)
        for p_data in s_data.get("projects") or []:
            project = Project(
                scenario_id=scenario.id,
                name=p_data.get("name", "Default Project"),
                deal_type=p_data["deal_type"],
                timeline_approved=p_data.get("timeline_approved", False),
            )
            session.add(project)
            await session.flush()

            oi_data = p_data.get("operational_inputs")
            if oi_data:
                session.add(OperationalInputs(project_id=project.id, **{
                    k: v for k, v in oi_data.items()
                    if hasattr(OperationalInputs, k) and v is not None
                }))

            for u_data in p_data.get("unit_mix") or []:
                session.add(UnitMix(project_id=project.id, **{
                    k: v for k, v in u_data.items() if v is not None
                }))

            for u_data in p_data.get("use_lines") or []:
                session.add(UseLine(project_id=project.id, **{
                    k: v for k, v in u_data.items() if v is not None
                }))

            for e_data in p_data.get("expense_lines") or []:
                session.add(OperatingExpenseLine(project_id=project.id, **{
                    k: v for k, v in e_data.items() if v is not None
                }))

            for s_data_inner in p_data.get("income_streams") or []:
                session.add(IncomeStream(project_id=project.id, **{
                    k: v for k, v in s_data_inner.items() if v is not None
                }))

        await session.flush()

    await session.refresh(deal)
    return deal


__all__ = ["DEAL_EXPORT_VERSION", "export_deal_json", "import_deal_json"]
