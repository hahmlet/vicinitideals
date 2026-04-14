from __future__ import annotations

import argparse
import asyncio
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vicinitideals.config import settings
from vicinitideals.engines.cashflow import compute_cash_flows
from vicinitideals.engines.waterfall import compute_waterfall
from vicinitideals.models.base import Base
from vicinitideals.models.capital import CapitalModule, FunderType, WaterfallResult, WaterfallTier, WaterfallTierType
from vicinitideals.models.cashflow import CashFlow, CashFlowLineItem, OperationalOutputs
from vicinitideals.models.deal import (
    Deal,
    DealModel,
    DealOpportunity,
    IncomeStream,
    IncomeStreamType,
    OperatingExpenseLine,
    OperationalInputs,
    ProjectType,
)
from vicinitideals.models.org import Organization, User
from vicinitideals.models.portfolio import Portfolio, PortfolioProject
from vicinitideals.models.project import Opportunity, Project, ProjectCategory, ProjectSource, ProjectStatus
from vicinitideals.schemas.capital import CapitalModuleBase, WaterfallTierBase
from vicinitideals.schemas.deal import (
    DealModelBase,
    IncomeStreamBase,
    OperatingExpenseLineBase,
    OperationalInputsBase,
)

DEFAULT_PORTFOLIO_NAME = "Tower + A&P Portfolio"
DEFAULT_ORG_NAME = "Tower + A&P Imported Deals"
DEFAULT_ORG_SLUG = "tower-ap-import"
DEFAULT_USER_NAME = "Tower + A&P Importer"
DEFAULT_VALIDATION_TOLERANCE_PCT = Decimal("0.1")
MIN_ABSOLUTE_TOLERANCE = Decimal("0.01")
PROJECT_ORDER = {"tower": 0, "a&p": 1, "ap": 1, "a_and_p": 1}
SCHEMA_TABLES = [
    Organization.__table__,
    User.__table__,
    Opportunity.__table__,
    Project.__table__,
    Portfolio.__table__,
    DealModel.__table__,
    OperationalInputs.__table__,
    IncomeStream.__table__,
    OperatingExpenseLine.__table__,
    CashFlow.__table__,
    CashFlowLineItem.__table__,
    OperationalOutputs.__table__,
    CapitalModule.__table__,
    WaterfallTier.__table__,
    WaterfallResult.__table__,
    PortfolioProject.__table__,
]
CASHFLOW_METRICS = {
    "total_project_cost",
    "equity_required",
    "total_timeline_months",
    "noi_stabilized",
    "cap_rate_on_cost_pct",
    "project_irr_unlevered",
    "cash_flow_count",
    "line_item_count",
}
WATERFALL_METRICS = {
    "capital_module_count",
    "waterfall_tier_count",
    "cash_flow_count",
    "waterfall_result_count",
    "lp_irr_pct",
    "gp_irr_pct",
    "equity_multiple",
    "cash_on_cash_year_1_pct",
    "project_irr_levered",
    "dscr",
}
METRIC_ALIASES = {
    "project_cost": "total_project_cost",
    "total_cost": "total_project_cost",
    "stabilized_noi": "noi_stabilized",
    "noi": "noi_stabilized",
    "cap_rate_on_cost": "cap_rate_on_cost_pct",
    "cap_rate": "cap_rate_on_cost_pct",
    "project_irr": "project_irr_levered",
    "unlevered_irr": "project_irr_unlevered",
    "levered_irr": "project_irr_levered",
    "lp_irr": "lp_irr_pct",
    "gp_irr": "gp_irr_pct",
    "cash_on_cash": "cash_on_cash_year_1_pct",
    "cash_on_cash_year_1": "cash_on_cash_year_1_pct",
    "year_1_cash_on_cash": "cash_on_cash_year_1_pct",
}


@dataclass(frozen=True)
class DealImportSpec:
    name: str
    project_payload: dict[str, Any]
    deal_model_payload: dict[str, Any]
    operational_inputs: dict[str, Any]
    income_streams: list[dict[str, Any]]
    expense_lines: list[dict[str, Any]]
    capital_modules: list[dict[str, Any]]
    waterfall_tiers: list[dict[str, Any]]
    expected: dict[str, Any]
    portfolio_project_payload: dict[str, Any]


def load_formulas_payload(formulas_source: str | Path | dict[str, Any] | None = None) -> dict[str, Any]:
    """Load the Tower + A&P formulas payload from a JSON file or return a provided dict."""

    if isinstance(formulas_source, dict):
        return formulas_source

    path = _resolve_formulas_path(formulas_source)
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("formulas.json must contain a top-level JSON object")
    return payload


async def import_tower_ap_deal(
    formulas_source: str | Path | dict[str, Any] | None = None,
    *,
    session: AsyncSession | None = None,
    database_url: str | None = None,
    ensure_schema: bool = False,
    validation_tolerance_pct: Decimal | float | str = DEFAULT_VALIDATION_TOLERANCE_PCT,
) -> dict[str, Any]:
    """Import the Tower + A&P portfolio, run compute, and validate expected results.

    Parameters
    ----------
    formulas_source:
        Path to `formulas.json`, a pre-loaded payload dict, or `None` to search common locations.
    session:
        Optional existing `AsyncSession`. When omitted, the function opens its own session.
    database_url:
        Optional override for the database URL when `session` is omitted.
    ensure_schema:
        If `True`, create the required tables before importing when managing the DB connection here.
    validation_tolerance_pct:
        Default percent tolerance for validation checks against expected Excel values.
    """

    payload = load_formulas_payload(formulas_source)
    bundle = _build_import_bundle(payload)
    tolerance_pct = _to_decimal(validation_tolerance_pct, DEFAULT_VALIDATION_TOLERANCE_PCT) or DEFAULT_VALIDATION_TOLERANCE_PCT

    if session is not None:
        summary = await _import_bundle(bundle, session=session, validation_tolerance_pct=tolerance_pct)
        await session.commit()
        return summary

    engine = create_async_engine(database_url or settings.database_url, echo=False, pool_pre_ping=True)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)

    try:
        if ensure_schema:
            async with engine.begin() as conn:
                await conn.run_sync(
                    lambda sync_conn: Base.metadata.create_all(
                        sync_conn,
                        tables=cast(list[Any], SCHEMA_TABLES),
                    )
                )

        async with session_factory() as managed_session:
            summary = await _import_bundle(
                bundle,
                session=managed_session,
                validation_tolerance_pct=tolerance_pct,
            )
            await managed_session.commit()
            return summary
    finally:
        await engine.dispose()


async def _import_bundle(
    bundle: dict[str, Any],
    *,
    session: AsyncSession,
    validation_tolerance_pct: Decimal,
) -> dict[str, Any]:
    organization = await _upsert_organization(session, bundle["organization"])
    user = await _get_or_create_user(session, organization, bundle["user_name"])
    portfolio = await _upsert_portfolio(session, organization, bundle["portfolio_name"])

    project_summaries: list[dict[str, Any]] = []

    for spec in bundle["projects"]:
        project = await _upsert_project(session, organization, spec.project_payload, created_by_user_id=user.id)
        deal_model = await _upsert_deal_model(session, project, user, spec.deal_model_payload)

        await _replace_deal_children(
            session,
            deal_model=deal_model,
            operational_inputs=spec.operational_inputs,
            income_streams=spec.income_streams,
            expense_lines=spec.expense_lines,
            capital_modules=spec.capital_modules,
            waterfall_tiers=spec.waterfall_tiers,
        )

        cashflow_summary = await compute_cash_flows(deal_model.id, session)
        waterfall_summary = await compute_waterfall(deal_model.id, session)

        portfolio_project = await _upsert_portfolio_project(
            session,
            portfolio=portfolio,
            project=project,
            deal_model=deal_model,
            project_payload=spec.portfolio_project_payload,
            capital_contribution=cashflow_summary.get("equity_required"),
        )

        validation = _validate_expected_results(
            project_name=spec.name,
            expected=spec.expected,
            cashflow_summary=cashflow_summary,
            waterfall_summary=waterfall_summary,
            default_tolerance_pct=validation_tolerance_pct,
        )

        project_summaries.append(
            {
                "name": project.name,
                "project_id": str(project.id),
                "deal_model_id": str(deal_model.id),
                "portfolio_project": {
                    "portfolio_id": str(portfolio_project.portfolio_id),
                    "project_id": str(portfolio_project.project_id),
                    "capital_contribution": _json_ready_scalar(portfolio_project.capital_contribution),
                    "start_date": _json_ready_scalar(portfolio_project.start_date),
                },
                "cashflow": _json_ready(cashflow_summary),
                "waterfall": _json_ready(waterfall_summary),
                "validation": validation,
            }
        )

    return {
        "organization": {"id": str(organization.id), "name": organization.name, "slug": organization.slug},
        "portfolio": {"id": str(portfolio.id), "name": portfolio.name, "org_id": str(portfolio.org_id)},
        "projects": project_summaries,
    }


def _build_import_bundle(payload: dict[str, Any]) -> dict[str, Any]:
    organization_payload = payload.get("organization") or payload.get("org") or {}
    portfolio_payload = cast(dict[str, Any], payload.get("portfolio") or {}) if isinstance(payload.get("portfolio"), dict) else {}

    organization = {
        "name": str(organization_payload.get("name") or DEFAULT_ORG_NAME),
        "slug": _slugify(str(organization_payload.get("slug") or DEFAULT_ORG_SLUG)),
    }
    portfolio_name = str(payload.get("portfolio_name") or portfolio_payload.get("name") or DEFAULT_PORTFOLIO_NAME)
    user_name = str(
        organization_payload.get("user_name")
        or payload.get("user_name")
        or portfolio_payload.get("user_name")
        or DEFAULT_USER_NAME
    )

    projects = [_normalize_project_entry(entry) for entry in _extract_project_entries(payload)]
    projects.sort(key=lambda spec: PROJECT_ORDER.get(_normalize_key(spec.name), 99))

    return {
        "organization": organization,
        "portfolio_name": portfolio_name,
        "user_name": user_name,
        "projects": projects,
    }


def _extract_project_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("projects", "deals", "models"):
        section = payload.get(key)
        if isinstance(section, list):
            return [item for item in section if isinstance(item, dict)]
        if isinstance(section, dict):
            return [_inject_name_if_needed(name, value) for name, value in section.items() if isinstance(value, dict)]

    if isinstance(payload.get("portfolio"), dict):
        section = payload["portfolio"].get("projects") or payload["portfolio"].get("deals")
        if isinstance(section, list):
            return [item for item in section if isinstance(item, dict)]
        if isinstance(section, dict):
            return [_inject_name_if_needed(name, value) for name, value in section.items() if isinstance(value, dict)]

    fallback_entries = []
    for name, value in payload.items():
        if not isinstance(value, dict):
            continue
        normalized = _normalize_key(name)
        if normalized in {"tower", "a&p", "ap", "a_and_p"}:
            fallback_entries.append(_inject_name_if_needed(name, value))

    if fallback_entries:
        return fallback_entries

    raise ValueError("formulas.json did not contain any project/deal definitions for Tower and A&P")


def _inject_name_if_needed(name: str, value: dict[str, Any]) -> dict[str, Any]:
    entry = dict(value)
    project_payload = dict(entry.get("project") or {})
    project_payload.setdefault("name", _canonical_project_name(name))
    entry["project"] = project_payload
    return entry


def _normalize_project_entry(entry: dict[str, Any]) -> DealImportSpec:
    raw_project = cast(dict[str, Any], entry.get("project") or {}) if isinstance(entry.get("project"), dict) else {}
    name = str(
        raw_project.get("name")
        or entry.get("name")
        or entry.get("project_name")
        or entry.get("label")
        or "Tower"
    )
    canonical_name = _canonical_project_name(name)

    project_payload = {
        "name": canonical_name,
        "status": _enum_value(ProjectStatus, raw_project.get("status") or entry.get("status"), ProjectStatus.active),
        "project_category": _enum_value(
            ProjectCategory,
            raw_project.get("project_category") or entry.get("project_category"),
            ProjectCategory.historical,
        ),
        "source": _enum_value(
            ProjectSource,
            raw_project.get("source") or entry.get("source"),
            ProjectSource.manual,
        ),
    }

    raw_deal_model = entry.get("deal_model") or entry.get("model") or entry.get("deal") or {}
    if not isinstance(raw_deal_model, dict):
        raw_deal_model = {}
    inferred_project_type = _infer_project_type(entry)
    deal_model_payload = DealModelBase.model_validate(
        {
            "name": str(raw_deal_model.get("name") or canonical_name),
            "version": int(raw_deal_model.get("version") or 1),
            "is_active": bool(raw_deal_model.get("is_active", True)),
            "project_type": _enum_value(ProjectType, raw_deal_model.get("project_type"), inferred_project_type),
        }
    ).model_dump(mode="python")

    raw_inputs = (
        entry.get("operational_inputs")
        or entry.get("inputs")
        or entry.get("assumptions")
        or entry.get("operations")
        or {}
    )
    operational_inputs = _normalize_operational_inputs(raw_inputs)

    income_streams = _normalize_income_streams(
        entry.get("income_streams")
        or entry.get("income")
        or entry.get("revenues")
        or entry.get("rent_roll"),
        canonical_name=canonical_name,
        operational_inputs=operational_inputs,
        whole_entry=entry,
    )
    expense_lines = _normalize_expense_lines(
        entry.get("expense_lines")
        or entry.get("operating_expense_lines")
        or entry.get("operating_expenses")
        or entry.get("expenses"),
        canonical_name=canonical_name,
    )
    capital_modules = _normalize_capital_modules(
        entry.get("capital_modules") or entry.get("capital_stack") or entry.get("capital"),
        canonical_name=canonical_name,
        operational_inputs=operational_inputs,
        whole_entry=entry,
    )
    waterfall_tiers = _normalize_waterfall_tiers(
        entry.get("waterfall_tiers") or entry.get("waterfall") or entry.get("distribution"),
        canonical_name=canonical_name,
        capital_modules=capital_modules,
    )

    expected = entry.get("expected") or entry.get("validation") or entry.get("excel_expected") or {}
    if not isinstance(expected, dict):
        expected = {}

    portfolio_project_payload = dict(entry.get("portfolio_project") or {})
    if "start_date" not in portfolio_project_payload:
        milestone_dates = operational_inputs.get("milestone_dates") or {}
        if isinstance(milestone_dates, dict):
            portfolio_project_payload["start_date"] = (
                milestone_dates.get("acquisition_start")
                or milestone_dates.get("start_date")
                or milestone_dates.get("close_date")
            )

    return DealImportSpec(
        name=canonical_name,
        project_payload=project_payload,
        deal_model_payload=deal_model_payload,
        operational_inputs=operational_inputs,
        income_streams=income_streams,
        expense_lines=expense_lines,
        capital_modules=capital_modules,
        waterfall_tiers=waterfall_tiers,
        expected=expected,
        portfolio_project_payload=portfolio_project_payload,
    )


def _normalize_operational_inputs(raw_inputs: Any) -> dict[str, Any]:
    if not isinstance(raw_inputs, dict):
        raw_inputs = {}

    data: dict[str, Any] = {}
    for field_name in OperationalInputsBase.model_fields:
        if field_name in raw_inputs:
            value = raw_inputs[field_name]
        else:
            value = _find_alias_value(raw_inputs, field_name)
        if value is None:
            continue
        data[field_name] = _clean_value(value)

    return OperationalInputsBase.model_validate(data).model_dump(mode="python")


def _normalize_income_streams(
    raw_streams: Any,
    *,
    canonical_name: str,
    operational_inputs: dict[str, Any],
    whole_entry: dict[str, Any],
) -> list[dict[str, Any]]:
    entries = _normalize_list_of_dicts(raw_streams, label_key="label")
    if not entries:
        fallback_amount = _first_present(
            whole_entry,
            "amount_per_unit_monthly",
            "rent_per_unit_monthly",
            "monthly_rent_per_unit",
            "monthly_rent",
        )
        if fallback_amount is not None:
            entries = [
                {
                    "stream_type": "residential_rent",
                    "label": f"{canonical_name} Residential",
                    "unit_count": operational_inputs.get("unit_count_after_conversion")
                    or operational_inputs.get("unit_count_existing")
                    or 1,
                    "amount_per_unit_monthly": fallback_amount,
                    "stabilized_occupancy_pct": whole_entry.get("stabilized_occupancy_pct", 95),
                    "escalation_rate_pct_annual": whole_entry.get("escalation_rate_pct_annual", 0),
                    "active_in_phases": ["lease_up", "stabilized", "exit"],
                }
            ]

    normalized: list[dict[str, Any]] = []
    for item in entries:
        cleaned = {
            "stream_type": _enum_value(
                IncomeStreamType,
                item.get("stream_type") or item.get("type"),
                IncomeStreamType.residential_rent,
            ),
            "label": str(item.get("label") or item.get("name") or f"{canonical_name} Income"),
            "unit_count": _clean_value(item.get("unit_count")),
            "amount_per_unit_monthly": _clean_value(item.get("amount_per_unit_monthly") or item.get("monthly_amount")),
            "amount_fixed_monthly": _clean_value(item.get("amount_fixed_monthly") or item.get("fixed_monthly_amount")),
            "stabilized_occupancy_pct": _clean_value(item.get("stabilized_occupancy_pct") or item.get("occupancy_pct") or 95),
            "escalation_rate_pct_annual": _clean_value(item.get("escalation_rate_pct_annual") or item.get("escalation_pct") or 0),
            "active_in_phases": _normalize_phase_list(item.get("active_in_phases") or item.get("active_phases")),
            "notes": item.get("notes"),
        }
        normalized.append(IncomeStreamBase.model_validate(cleaned).model_dump(mode="python"))

    return normalized


def _normalize_expense_lines(
    raw_lines: Any,
    *,
    canonical_name: str,
) -> list[dict[str, Any]]:
    entries = _normalize_list_of_dicts(raw_lines, label_key="label")
    if isinstance(raw_lines, dict):
        for key, value in raw_lines.items():
            if isinstance(value, dict):
                continue
            entries.append({"label": key, "annual_amount": value})

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(entries, start=1):
        cleaned = {
            "label": str(item.get("label") or item.get("name") or f"{canonical_name} Expense {index}"),
            "annual_amount": _clean_value(
                item.get("annual_amount") or item.get("amount") or item.get("annual") or 0
            ),
            "escalation_rate_pct_annual": _clean_value(
                item.get("escalation_rate_pct_annual") or item.get("escalation_pct") or 3
            ),
            "active_in_phases": _normalize_phase_list(
                item.get("active_in_phases") or item.get("active_phases")
            ),
            "notes": item.get("notes"),
        }
        normalized.append(OperatingExpenseLineBase.model_validate(cleaned).model_dump(mode="python"))

    return normalized


def _normalize_capital_modules(
    raw_modules: Any,
    *,
    canonical_name: str,
    operational_inputs: dict[str, Any],
    whole_entry: dict[str, Any],
) -> list[dict[str, Any]]:
    entries = _normalize_list_of_dicts(raw_modules, label_key="label")
    if not entries:
        purchase_price = _to_decimal(operational_inputs.get("purchase_price"), Decimal("0")) or Decimal("0")
        loan_amount = _to_decimal(
            _first_present(whole_entry, "senior_loan_amount", "loan_amount", "debt_amount"),
            purchase_price * Decimal("0.65") if purchase_price else Decimal("0"),
        ) or Decimal("0")
        entries = []
        if loan_amount > Decimal("0"):
            entries.append(
                {
                    "label": f"{canonical_name} Senior Loan",
                    "funder_type": "senior_debt",
                    "stack_position": 1,
                    "source": {"amount": float(loan_amount), "interest_rate_pct": 6.0},
                    "carry": {"carry_type": "io_only", "payment_frequency": "monthly"},
                    "exit_terms": {"exit_type": "full_payoff", "trigger": "sale"},
                    "active_phase_start": "acquisition",
                    "active_phase_end": "exit",
                }
            )
        entries.append(
            {
                "label": f"{canonical_name} Common Equity",
                "funder_type": "common_equity",
                "stack_position": max(len(entries) + 1, 2),
                "source": {"pct_of_total_cost": 100},
                "carry": {"carry_type": "none", "payment_frequency": "at_exit"},
                "exit_terms": {"exit_type": "profit_share", "trigger": "sale", "profit_share_pct": 100},
                "active_phase_start": "acquisition",
                "active_phase_end": "exit",
            }
        )

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(entries, start=1):
        cleaned = {
            "label": str(item.get("label") or item.get("name") or f"{canonical_name} Capital {index}"),
            "funder_type": _enum_value(FunderType, item.get("funder_type") or item.get("type"), FunderType.other),
            "stack_position": int(_clean_value(item.get("stack_position") or index) or index),
            "source": _json_safe(item.get("source") or item.get("terms") or {}),
            "carry": _json_safe(item.get("carry") or {"carry_type": "none", "payment_frequency": "monthly"}),
            "exit_terms": _json_safe(
                item.get("exit_terms") or {"exit_type": "full_payoff", "trigger": "sale"}
            ),
            "active_phase_start": item.get("active_phase_start") or "acquisition",
            "active_phase_end": item.get("active_phase_end") or "exit",
        }
        validated = CapitalModuleBase.model_validate(cleaned).model_dump(mode="python")
        validated["source"] = _json_safe(validated.get("source"))
        validated["carry"] = _json_safe(validated.get("carry"))
        validated["exit_terms"] = _json_safe(validated.get("exit_terms"))
        normalized.append(validated)

    return normalized


def _normalize_waterfall_tiers(
    raw_tiers: Any,
    *,
    canonical_name: str,
    capital_modules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    entries = _normalize_list_of_dicts(raw_tiers, label_key="description")
    if not entries:
        debt_module_label = next(
            (
                module["label"]
                for module in capital_modules
                if _normalize_key(module.get("funder_type")) in {"senior_debt", "mezzanine_debt", "bridge", "construction_loan", "soft_loan", "bond"}
            ),
            None,
        )
        entries = []
        if debt_module_label:
            entries.append(
                {
                    "priority": 1,
                    "tier_type": "debt_service",
                    "description": f"{canonical_name} debt service",
                    "capital_module_label": debt_module_label,
                }
            )
        entries.extend(
            [
                {
                    "priority": len(entries) + 1,
                    "tier_type": "return_of_equity",
                    "lp_split_pct": 100,
                    "gp_split_pct": 0,
                    "description": "Return LP capital",
                },
                {
                    "priority": len(entries) + 2,
                    "tier_type": "residual",
                    "lp_split_pct": 90,
                    "gp_split_pct": 10,
                    "description": "Residual split",
                },
            ]
        )

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(entries, start=1):
        cleaned = {
            "priority": int(_clean_value(item.get("priority") or index) or index),
            "tier_type": _enum_value(
                WaterfallTierType,
                item.get("tier_type") or item.get("type"),
                WaterfallTierType.residual,
            ),
            "irr_hurdle_pct": _clean_value(item.get("irr_hurdle_pct")),
            "lp_split_pct": _clean_value(item.get("lp_split_pct") or 0),
            "gp_split_pct": _clean_value(item.get("gp_split_pct") or 0),
            "description": item.get("description") or item.get("label"),
            "capital_module_id": item.get("capital_module_id"),
            "capital_module_label": item.get("capital_module_label") or item.get("module_label") or item.get("capital_module"),
        }
        validated = WaterfallTierBase.model_validate(
            {k: v for k, v in cleaned.items() if k != "capital_module_label"}
        ).model_dump(mode="python")
        validated["capital_module_label"] = cleaned["capital_module_label"]
        normalized.append(validated)

    return normalized


async def _upsert_organization(session: AsyncSession, payload: dict[str, Any]) -> Organization:
    slug = _slugify(str(payload.get("slug") or DEFAULT_ORG_SLUG))
    organization = (
        await session.execute(select(Organization).where(Organization.slug == slug))
    ).scalar_one_or_none()
    if organization is None:
        organization = Organization(name=str(payload.get("name") or DEFAULT_ORG_NAME), slug=slug)
        session.add(organization)
        await session.flush()
    else:
        organization.name = str(payload.get("name") or organization.name)
        await session.flush()
    return organization


async def _get_or_create_user(session: AsyncSession, organization: Organization, user_name: str) -> User:
    user = (
        await session.execute(
            select(User).where(User.org_id == organization.id, User.name == user_name)
        )
    ).scalar_one_or_none()
    if user is None:
        user = User(org_id=organization.id, name=user_name, display_color="#3B82F6")
        session.add(user)
        await session.flush()
    return user


async def _upsert_portfolio(session: AsyncSession, organization: Organization, portfolio_name: str) -> Portfolio:
    portfolio = (
        await session.execute(
            select(Portfolio).where(Portfolio.org_id == organization.id, Portfolio.name == portfolio_name)
        )
    ).scalar_one_or_none()
    if portfolio is None:
        portfolio = Portfolio(org_id=organization.id, name=portfolio_name)
        session.add(portfolio)
        await session.flush()
    else:
        portfolio.name = portfolio_name
        await session.flush()
    return portfolio


async def _upsert_project(
    session: AsyncSession,
    organization: Organization,
    payload: dict[str, Any],
    *,
    created_by_user_id: UUID,
) -> Opportunity:
    project = (
        await session.execute(
            select(Opportunity).where(Opportunity.org_id == organization.id, Opportunity.name == payload["name"])
        )
    ).scalar_one_or_none()
    if project is None:
        project = Opportunity(org_id=organization.id, created_by_user_id=created_by_user_id, **payload)
        session.add(project)
    else:
        project.status = payload["status"]
        project.project_category = payload["project_category"]
        project.source = payload["source"]
        project.created_by_user_id = created_by_user_id

    await session.flush()
    return project


async def _upsert_deal_model(
    session: AsyncSession,
    opportunity: Opportunity,
    user: User,
    payload: dict[str, Any],
) -> DealModel:
    deal_model = (
        await session.execute(
            select(DealModel)
            .join(Deal, Deal.id == DealModel.deal_id)
            .join(DealOpportunity, DealOpportunity.deal_id == Deal.id)
            .where(DealOpportunity.opportunity_id == opportunity.id, DealModel.name == payload["name"])
            .order_by(DealModel.version.desc())
        )
    ).scalars().first()

    if deal_model is None:
        # New architecture: create top-level Deal + DealOpportunity + Scenario
        top_deal_result = await session.execute(
            select(Deal)
            .join(DealOpportunity, DealOpportunity.deal_id == Deal.id)
            .where(DealOpportunity.opportunity_id == opportunity.id)
            .limit(1)
        )
        top_deal = top_deal_result.scalar_one_or_none()
        if top_deal is None:
            top_deal = Deal(
                org_id=opportunity.org_id,
                name=payload.get("name", "Import"),
                created_by_user_id=user.id,
            )
            session.add(top_deal)
            await session.flush()
            session.add(DealOpportunity(deal_id=top_deal.id, opportunity_id=opportunity.id))
            await session.flush()

        deal_model = DealModel(deal_id=top_deal.id, created_by_user_id=user.id, **payload)
        session.add(deal_model)
        await session.flush()
        # Ensure a default dev Project exists for this scenario
        existing_proj = (
            await session.execute(
                select(Project).where(Project.scenario_id == deal_model.id).limit(1)
            )
        ).scalar_one_or_none()
        if existing_proj is None:
            session.add(Project(
                scenario_id=deal_model.id,
                opportunity_id=opportunity.id,
                name="Default Project",
                deal_type=deal_model.project_type,
            ))
    else:
        deal_model.created_by_user_id = user.id
        deal_model.version = payload["version"]
        deal_model.is_active = payload["is_active"]
        deal_model.project_type = payload["project_type"]

    await session.flush()
    return deal_model


async def _replace_deal_children(
    session: AsyncSession,
    *,
    deal_model: DealModel,
    operational_inputs: dict[str, Any],
    income_streams: list[dict[str, Any]],
    expense_lines: list[dict[str, Any]],
    capital_modules: list[dict[str, Any]],
    waterfall_tiers: list[dict[str, Any]],
) -> None:
    # Subquery for this deal's default dev Project (for line-item deletes/inserts)
    dev_proj_id_subq = select(Project.id).where(Project.scenario_id == deal_model.id)

    await session.execute(delete(WaterfallResult).where(WaterfallResult.scenario_id == deal_model.id))
    await session.execute(delete(CashFlowLineItem).where(CashFlowLineItem.scenario_id == deal_model.id))
    await session.execute(delete(CashFlow).where(CashFlow.scenario_id == deal_model.id))
    await session.execute(delete(OperationalOutputs).where(OperationalOutputs.scenario_id == deal_model.id))
    await session.execute(delete(WaterfallTier).where(WaterfallTier.scenario_id == deal_model.id))
    await session.execute(delete(CapitalModule).where(CapitalModule.scenario_id == deal_model.id))
    await session.execute(delete(IncomeStream).where(IncomeStream.project_id.in_(dev_proj_id_subq)))
    await session.execute(delete(OperatingExpenseLine).where(OperatingExpenseLine.project_id.in_(dev_proj_id_subq)))
    await session.execute(delete(OperationalInputs).where(OperationalInputs.project_id.in_(dev_proj_id_subq)))
    await session.flush()

    # Get (or create) the default dev Project for line item inserts
    dev_project = (
        await session.execute(select(Project).where(Project.scenario_id == deal_model.id).limit(1))
    ).scalar_one_or_none()
    if dev_project is None:
        raise ValueError(f"No dev Project found for deal {deal_model.id} — run _upsert_deal_model first")

    session.add(OperationalInputs(project_id=dev_project.id, **operational_inputs))
    for stream_payload in income_streams:
        session.add(IncomeStream(project_id=dev_project.id, **stream_payload))
    for expense_payload in expense_lines:
        session.add(OperatingExpenseLine(project_id=dev_project.id, **expense_payload))

    await session.flush()

    label_to_id: dict[str, UUID] = {}
    for module_payload in capital_modules:
        module = CapitalModule(scenario_id=deal_model.id, **module_payload)
        session.add(module)
        await session.flush()
        label_to_id[str(module.label)] = module.id

    for tier_payload in waterfall_tiers:
        tier_data = dict(tier_payload)
        module_label = tier_data.pop("capital_module_label", None)
        if module_label and tier_data.get("capital_module_id") is None:
            tier_data["capital_module_id"] = label_to_id.get(str(module_label))
        session.add(WaterfallTier(scenario_id=deal_model.id, **tier_data))

    await session.flush()


async def _upsert_portfolio_project(
    session: AsyncSession,
    *,
    portfolio: Portfolio,
    project: Opportunity,
    deal_model: DealModel,
    project_payload: dict[str, Any],
    capital_contribution: Any,
) -> PortfolioProject:
    portfolio_project = await session.get(
        PortfolioProject,
        {"portfolio_id": portfolio.id, "project_id": project.id},
    )
    start_date = _coerce_date(project_payload.get("start_date"))
    contribution_value = _to_decimal(capital_contribution, Decimal("0")) if capital_contribution is not None else None

    if portfolio_project is None:
        portfolio_project = PortfolioProject(
            portfolio_id=portfolio.id,
            project_id=project.id,
            scenario_id=deal_model.id,
            start_date=start_date,
            capital_contribution=contribution_value,
        )
        session.add(portfolio_project)
    else:
        portfolio_project.scenario_id = deal_model.id
        portfolio_project.start_date = start_date
        portfolio_project.capital_contribution = contribution_value

    await session.flush()
    return portfolio_project


def _validate_expected_results(
    *,
    project_name: str,
    expected: dict[str, Any],
    cashflow_summary: dict[str, Any],
    waterfall_summary: dict[str, Any],
    default_tolerance_pct: Decimal,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    failures: list[str] = []

    cashflow_expected, waterfall_expected = _split_expected_sections(expected)

    for metric_name, spec in cashflow_expected.items():
        result = _check_metric(
            section="cashflow",
            metric_name=metric_name,
            spec=spec,
            actual_value=cashflow_summary.get(metric_name),
            default_tolerance_pct=default_tolerance_pct,
        )
        checks.append(result)
        if not result["passed"]:
            failures.append(f"cashflow.{metric_name}")

    for metric_name, spec in waterfall_expected.items():
        result = _check_metric(
            section="waterfall",
            metric_name=metric_name,
            spec=spec,
            actual_value=waterfall_summary.get(metric_name),
            default_tolerance_pct=default_tolerance_pct,
        )
        checks.append(result)
        if not result["passed"]:
            failures.append(f"waterfall.{metric_name}")

    if failures:
        failed_metrics = ", ".join(failures)
        raise ValueError(f"Validation against Excel values failed for {project_name}: {failed_metrics}")

    return {
        "checked_metrics": len(checks),
        "passed": True,
        "checks": checks,
    }


def _split_expected_sections(expected: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if not expected:
        return {}, {}

    cashflow_expected = dict(
        expected.get("cashflow")
        or expected.get("cash_flow")
        or expected.get("operational_outputs")
        or {}
    )
    waterfall_expected = dict(expected.get("waterfall") or expected.get("capital_stack") or {})

    for key, value in expected.items():
        if key in {"cashflow", "cash_flow", "operational_outputs", "waterfall", "capital_stack"}:
            continue
        canonical_key = _canonical_metric_name(key)
        if canonical_key in WATERFALL_METRICS:
            waterfall_expected[canonical_key] = value
        else:
            cashflow_expected[canonical_key] = value

    return cashflow_expected, waterfall_expected


def _check_metric(
    *,
    section: str,
    metric_name: str,
    spec: Any,
    actual_value: Any,
    default_tolerance_pct: Decimal,
) -> dict[str, Any]:
    expected_value = spec
    tolerance_pct: Decimal = default_tolerance_pct
    tolerance_abs: Decimal | None = None

    if isinstance(spec, dict):
        if "value" in spec:
            expected_value = spec["value"]
        elif "expected" in spec:
            expected_value = spec["expected"]
        if spec.get("tolerance_pct") is not None:
            tolerance_pct = _to_decimal(spec["tolerance_pct"], default_tolerance_pct) or default_tolerance_pct
        if spec.get("tolerance_abs") is not None:
            tolerance_abs = _to_decimal(spec["tolerance_abs"], MIN_ABSOLUTE_TOLERANCE)

    actual_decimal = _to_decimal(actual_value, None)
    expected_decimal = _to_decimal(expected_value, None)

    if actual_decimal is None or expected_decimal is None:
        passed = actual_value == expected_value
        difference = None if passed else str(actual_value)
        allowed = tolerance_abs or MIN_ABSOLUTE_TOLERANCE
    else:
        difference_decimal = abs(actual_decimal - expected_decimal)
        allowed = tolerance_abs or max(abs(expected_decimal) * tolerance_pct / Decimal("100"), MIN_ABSOLUTE_TOLERANCE)
        passed = difference_decimal <= allowed
        difference = _json_ready_scalar(difference_decimal)

    return {
        "section": section,
        "metric": metric_name,
        "expected": _json_ready_scalar(expected_decimal if expected_decimal is not None else expected_value),
        "actual": _json_ready_scalar(actual_decimal if actual_decimal is not None else actual_value),
        "tolerance": _json_ready_scalar(allowed),
        "passed": passed,
        "difference": difference,
    }


def _resolve_formulas_path(formulas_source: str | Path | None) -> Path:
    if formulas_source is not None:
        path = Path(formulas_source).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Could not find formulas file: {path}")
        return path

    candidates = [
        Path.cwd() / "formulas.json",
        Path.cwd() / "data" / "formulas.json",
        Path(__file__).resolve().parent / "formulas.json",
        Path(__file__).resolve().parents[2] / "formulas.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise FileNotFoundError("Could not find formulas.json in the working directory or default import paths")


def _normalize_list_of_dicts(raw_value: Any, *, label_key: str) -> list[dict[str, Any]]:
    if raw_value is None:
        return []
    if isinstance(raw_value, list):
        return [dict(item) for item in raw_value if isinstance(item, dict)]
    if isinstance(raw_value, dict):
        result = []
        for key, value in raw_value.items():
            if not isinstance(value, dict):
                continue
            item = dict(value)
            item.setdefault(label_key, key)
            result.append(item)
        return result
    return []


def _enum_value(enum_type: Any, raw_value: Any, default: Any) -> Any:
    if raw_value is None or raw_value == "":
        return default
    if isinstance(raw_value, enum_type):
        return raw_value
    try:
        return enum_type(str(raw_value))
    except Exception:
        return default


def _infer_project_type(entry: dict[str, Any]) -> ProjectType:
    raw_inputs = (
        entry.get("operational_inputs")
        or entry.get("inputs")
        or entry.get("assumptions")
        or {}
    )
    if not isinstance(raw_inputs, dict):
        raw_inputs = {}

    if raw_inputs.get("conversion_cost_per_unit") is not None or raw_inputs.get("unit_count_after_conversion") is not None:
        return ProjectType.acquisition_conversion
    if raw_inputs.get("hard_cost_per_unit") is not None and raw_inputs.get("construction_months") is not None:
        return ProjectType.new_construction
    if raw_inputs.get("renovation_cost_total") is not None:
        renovation_months = _to_decimal(raw_inputs.get("renovation_months"), Decimal("0")) or Decimal("0")
        if renovation_months >= Decimal("6"):
            return ProjectType.acquisition_major_reno
        return ProjectType.acquisition_minor_reno
    return ProjectType.acquisition_minor_reno


def _normalize_phase_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [chunk.strip() for chunk in value.split(",") if chunk.strip()]
    return ["lease_up", "stabilized", "exit"]


def _find_alias_value(raw_inputs: dict[str, Any], field_name: str) -> Any:
    aliases = {
        "purchase_price": ["acquisition_price", "price"],
        "closing_costs_pct": ["closing_cost_pct"],
        "opex_per_unit_annual": ["operating_expense_per_unit_annual"],
        "expense_growth_rate_pct_annual": ["opex_growth_rate_pct_annual", "expense_growth_pct"],
        "mgmt_fee_pct": ["management_fee_pct"],
        "property_tax_annual": ["property_taxes_annual"],
        "insurance_annual": ["insurance_cost_annual"],
        "capex_reserve_per_unit_annual": ["capex_reserve_annual_per_unit"],
        "hold_period_years": ["hold_years"],
        "exit_cap_rate_pct": ["exit_cap_pct"],
        "selling_costs_pct": ["sale_cost_pct"],
    }
    for alias in aliases.get(field_name, []):
        if alias in raw_inputs:
            return raw_inputs[alias]
    return None


def _canonical_project_name(name: str) -> str:
    normalized = _normalize_key(name)
    if normalized == "tower":
        return "Tower"
    if normalized in {"a&p", "ap", "a_and_p"}:
        return "A&P"
    return name.strip() or "Tower"


def _canonical_metric_name(name: str) -> str:
    normalized = _normalize_key(name)
    return METRIC_ALIASES.get(normalized, normalized)


def _normalize_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _slugify(value: str) -> str:
    return _normalize_key(value).replace("_", "-") or DEFAULT_ORG_SLUG


def _clean_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _clean_value(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_clean_value(item) for item in value]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return stripped
        lowered = stripped.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", stripped):
            return stripped

        percent = stripped.endswith("%")
        numeric_text = stripped[:-1] if percent else stripped
        numeric_text = numeric_text.replace(",", "").replace("$", "")
        try:
            if re.search(r"[.eE]", numeric_text):
                return float(numeric_text)
            return int(numeric_text)
        except ValueError:
            return stripped
    return value


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return _json_ready_scalar(value)


def _json_ready_scalar(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    return json.loads(json.dumps(_json_ready(value)))


def _to_decimal(value: Any, default: Decimal | None) -> Decimal | None:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return Decimal(int(value))
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        stripped = stripped.replace(",", "").replace("$", "")
        if stripped.endswith("%"):
            stripped = stripped[:-1]
        try:
            return Decimal(stripped)
        except (InvalidOperation, ValueError):
            return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default


def _first_present(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in source and source[key] is not None:
            return source[key]
    return None


def _coerce_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import the Tower + A&P Excel model into re-modeling")
    parser.add_argument("formulas", nargs="?", default=None, help="Path to formulas.json")
    parser.add_argument(
        "--formulas",
        dest="formulas_option",
        type=str,
        default=None,
        help="Path to formulas.json (same as the positional argument)",
    )
    parser.add_argument("--database-url", type=str, default=None, help="Override the target database URL")
    parser.add_argument(
        "--ensure-schema",
        action="store_true",
        help="Create the required tables before importing when managing the DB connection here",
    )
    parser.add_argument(
        "--validation-tolerance-pct",
        type=str,
        default=str(DEFAULT_VALIDATION_TOLERANCE_PCT),
        help="Default percent tolerance when validating against known Excel values",
    )
    return parser


async def _async_main(args: argparse.Namespace) -> int:
    formulas_source = args.formulas_option or args.formulas
    summary = await import_tower_ap_deal(
        formulas_source=formulas_source,
        database_url=args.database_url,
        ensure_schema=args.ensure_schema,
        validation_tolerance_pct=args.validation_tolerance_pct,
    )
    print(json.dumps(_json_ready(summary), indent=2))
    return 0


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    return asyncio.run(_async_main(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
