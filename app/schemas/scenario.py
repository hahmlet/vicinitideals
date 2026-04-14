"""Sensitivity (sensitivity analysis sweep) and SensitivityResult schemas.

Previously named Scenario/ScenarioResult — renamed to match the ORM rename.
Backward-compat aliases (ScenarioCreate, ScenarioRead, etc.) are kept so
existing code continues to import without immediate churn.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from app.models.scenario import SensitivityStatus


# ---------------------------------------------------------------------------
# Sensitivity (was Scenario)
# ---------------------------------------------------------------------------

class SensitivityBase(BaseModel):
    variable: str
    range_min: Decimal
    range_max: Decimal
    range_steps: int = 10
    status: SensitivityStatus = SensitivityStatus.pending
    celery_task_id: str | None = None


class SensitivityCreate(SensitivityBase):
    opportunity_id: uuid.UUID
    scenario_id: uuid.UUID
    created_by_user_id: uuid.UUID | None = None


class SensitivityRead(SensitivityBase):
    id: uuid.UUID
    opportunity_id: uuid.UUID
    scenario_id: uuid.UUID
    created_by_user_id: uuid.UUID | None = None
    run_count: int = 1
    model_version_snapshot: dict[str, Any] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# Backward-compat aliases
ScenarioCreate = SensitivityCreate
ScenarioRead = SensitivityRead
ScenarioStatus = SensitivityStatus


# ---------------------------------------------------------------------------
# SensitivityResult (was ScenarioResult)
# ---------------------------------------------------------------------------

class SensitivityResultBase(BaseModel):
    run_number: int = 1
    variable_value: Decimal
    project_irr_pct: Decimal | None = None
    lp_irr_pct: Decimal | None = None
    gp_irr_pct: Decimal | None = None
    equity_multiple: Decimal | None = None
    cash_on_cash_year1_pct: Decimal | None = None


class SensitivityResultCreate(SensitivityResultBase):
    sensitivity_id: uuid.UUID


class SensitivityResultRead(SensitivityResultBase):
    id: uuid.UUID
    sensitivity_id: uuid.UUID

    model_config = {"from_attributes": True}


# Backward-compat aliases
ScenarioResultCreate = SensitivityResultCreate
ScenarioResultRead = SensitivityResultRead


# ---------------------------------------------------------------------------
# Comparison / analysis views (unchanged except field names)
# ---------------------------------------------------------------------------

class ScenarioVariableDescriptorRead(BaseModel):
    key: str
    label: str
    unit: str


class ScenarioMetricDeltaRead(BaseModel):
    value: Decimal | None = None
    delta: Decimal | None = None
    delta_pct: Decimal | None = None


class ScenarioAttributionRead(BaseModel):
    driver: str
    label: str
    unit: str
    baseline_value: Decimal | None = None
    compared_value: Decimal
    delta: Decimal | None = None
    direction: str


class ScenarioComparisonPointRead(BaseModel):
    variable_value: Decimal
    attribution: ScenarioAttributionRead
    project_irr_pct: ScenarioMetricDeltaRead
    lp_irr_pct: ScenarioMetricDeltaRead
    gp_irr_pct: ScenarioMetricDeltaRead
    equity_multiple: ScenarioMetricDeltaRead
    cash_on_cash_year1_pct: ScenarioMetricDeltaRead


class ScenarioComparisonRead(BaseModel):
    sensitivity_id: uuid.UUID
    opportunity_id: uuid.UUID
    scenario_id: uuid.UUID
    status: SensitivityStatus
    variable: ScenarioVariableDescriptorRead
    baseline: SensitivityResultRead | None = None
    comparisons: list[ScenarioComparisonPointRead]
