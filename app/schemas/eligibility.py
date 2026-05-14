"""Eligibility schemas for Source-Use routing."""
from __future__ import annotations

import uuid

from pydantic import BaseModel


class UseEligibilityUpdate(BaseModel):
    eligible_module_ids: list[uuid.UUID] = []


class ModuleEligibilityUpdate(BaseModel):
    eligible_use_tags: list[str] = []
