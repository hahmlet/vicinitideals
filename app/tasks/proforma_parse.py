"""Celery task: parse an uploaded pro forma / OM spreadsheet into
standardised revenue and OpEx line items via a locally-hosted Ollama LLM.

Flow
----
1. Caller (FastAPI route) stores raw file bytes in Redis under
   ``proforma:{task_id}:file`` (TTL 24 h), then queues this task.
2. Task reads the file, extracts the user-specified sheets, formats each
   as a plain-text table, and calls the local Ollama model twice (once for
   revenue, once for OpEx) via *instructor* for structured JSON output.
3. Progress is written to Redis under ``proforma:{task_id}:progress`` so
   the HTMX poller can display live step feedback.
4. Final result JSON is written to ``proforma:{task_id}:result`` (TTL 24 h).

Redis key schema
----------------
``proforma:{task_id}:file``      — raw xlsx bytes (bytes), TTL 24 h
``proforma:{task_id}:progress``  — JSON progress object, TTL 24 h
``proforma:{task_id}:result``    — JSON parse result, TTL 24 h
"""

from __future__ import annotations

import io
import json
import logging
from typing import Any

import openpyxl
from celery.utils.log import get_task_logger
from pydantic import BaseModel, Field

from app.config import settings
from app.models.deal import STANDARD_OPEX_CATEGORIES
from app.tasks.celery_app import celery_app

logger = get_task_logger(__name__)

PARSE_PROFORMA_TASK = "app.tasks.proforma_parse.parse_proforma"
_REDIS_TTL = 86_400  # 24 hours

# ---------------------------------------------------------------------------
# Structured output schemas (returned by the LLM via instructor)
# ---------------------------------------------------------------------------

class UnitTypeResult(BaseModel):
    name: str = Field(description="Descriptive unit type name, e.g. '1BR', 'Studio', 'Tower Small'")
    count: int = Field(description="Number of units of this type")
    avg_sqft: float = Field(description="Average square footage per unit")
    avg_monthly_rent: float = Field(description="Average gross monthly rent per unit in dollars")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score 0–1")


class ParsedRevenue(BaseModel):
    unit_types: list[UnitTypeResult]


class ExpenseLineResult(BaseModel):
    original_label: str = Field(description="Exact label as it appeared in the spreadsheet")
    annual_amount: float = Field(description="Annual dollar amount (sum of monthly columns if source is monthly)")
    mapped_category: str | None = Field(
        default=None,
        description="One of the STANDARD_OPEX_CATEGORIES, or null if unable to map",
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score 0–1 for the category mapping")
    is_operating_expense: bool = Field(
        description=(
            "True for real operating expenses. False for below-the-line items that should be "
            "excluded: debt service, interest, depreciation, loan fees, amortization of financing costs."
        )
    )


class ParsedExpenses(BaseModel):
    expense_lines: list[ExpenseLineResult]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _redis_client() -> Any:
    import redis  # type: ignore
    return redis.from_url(settings.redis_url, decode_responses=False)


def _set_progress(r: Any, task_id: str, step: int, total: int, message: str) -> None:
    payload = json.dumps({"step": step, "total": total, "message": message, "status": "running"})
    r.set(f"proforma:{task_id}:progress", payload, ex=_REDIS_TTL)


def _set_error(r: Any, task_id: str, message: str) -> None:
    payload = json.dumps({"status": "error", "message": message})
    r.set(f"proforma:{task_id}:progress", payload, ex=_REDIS_TTL)


def _set_done(r: Any, task_id: str) -> None:
    payload = json.dumps({"step": 3, "total": 3, "message": "Done", "status": "done"})
    r.set(f"proforma:{task_id}:progress", payload, ex=_REDIS_TTL)


def _sheet_to_text(ws: Any, property_column: str | None = None, max_rows: int = 200) -> str:
    """Convert an openpyxl worksheet to a plain-text table for the LLM.

    If *property_column* is set (e.g. "Ash & Pine"), only the label column
    and that specific numeric column are included, dropping others.  This
    keeps the prompt focused when a sheet has multiple property sub-columns.
    """
    rows: list[list[str]] = []
    col_indices: list[int] | None = None

    for i, row in enumerate(ws.iter_rows(max_row=min(ws.max_row, max_rows), values_only=True)):
        if not any(c is not None for c in row):
            continue

        cells = [str(c).strip() if c is not None else "" for c in row]

        # On the first non-empty row (assumed header), determine column filter
        if col_indices is None and property_column:
            col_indices = [0]  # always keep the label column
            for idx, cell in enumerate(cells):
                if property_column.lower() in cell.lower():
                    col_indices.append(idx)

        if col_indices is not None:
            cells = [cells[idx] for idx in col_indices if idx < len(cells)]

        rows.append(cells)

    return "\n".join("\t".join(row) for row in rows)


def _llm_client() -> Any:
    """Return an instructor-patched OpenAI client pointed at local Ollama."""
    import instructor  # type: ignore
    from openai import OpenAI  # type: ignore

    raw = OpenAI(base_url=settings.ollama_base_url, api_key="ollama")
    return instructor.from_openai(raw, mode=instructor.Mode.JSON)


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, name=PARSE_PROFORMA_TASK)
def parse_proforma(
    self,
    task_id: str,
    model_id: str,  # noqa: ARG001  — reserved for future per-model context
    revenue_sheet: str,
    opex_sheet: str,
    property_column: str | None = None,
) -> None:
    """Parse a pro forma spreadsheet and write structured results to Redis."""
    r = _redis_client()
    warnings: list[str] = []

    try:
        # ------------------------------------------------------------------
        # Step 1 — Read file from Redis
        # ------------------------------------------------------------------
        _set_progress(r, task_id, 1, 3, "Reading spreadsheet…")
        file_bytes: bytes | None = r.get(f"proforma:{task_id}:file")
        if not file_bytes:
            _set_error(r, task_id, "Upload expired or not found. Please upload the file again.")
            return

        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)

        if revenue_sheet not in wb.sheetnames:
            warnings.append(f"Revenue sheet '{revenue_sheet}' not found — skipping revenue parse.")
            revenue_text = ""
        else:
            revenue_text = _sheet_to_text(wb[revenue_sheet])

        if opex_sheet not in wb.sheetnames:
            warnings.append(f"OpEx sheet '{opex_sheet}' not found — skipping expense parse.")
            opex_text = ""
        else:
            opex_text = _sheet_to_text(wb[opex_sheet], property_column=property_column)

        client = _llm_client()

        # ------------------------------------------------------------------
        # Step 2 — Parse revenue
        # ------------------------------------------------------------------
        _set_progress(r, task_id, 2, 3, "Parsing revenue / unit mix…")
        unit_types: list[dict] = []

        if revenue_text:
            try:
                rev_prompt = (
                    "You are a real estate financial analyst. The following is tabular data from a "
                    "spreadsheet's revenue or rent-roll sheet. Group the units into distinct unit types "
                    "(e.g. Studio, 1BR, 2BR, or developer-named types like 'Tower Small'). "
                    "For each type, return the count, average square footage, and average gross monthly rent. "
                    "If the sheet is a unit-by-unit roll (individual unit numbers), group similar-sized units. "
                    "Only return actual residential or commercial units — exclude parking, storage, laundry, "
                    "and ancillary income rows.\n\n"
                    f"SHEET DATA:\n{revenue_text}"
                )
                parsed_rev: ParsedRevenue = client.chat.completions.create(
                    model=settings.ollama_model,
                    response_model=ParsedRevenue,
                    messages=[{"role": "user", "content": rev_prompt}],
                )
                unit_types = [u.model_dump() for u in parsed_rev.unit_types]
            except Exception as exc:
                logger.warning("Revenue parse failed: %s", exc)
                warnings.append(f"Revenue parsing failed: {exc}")

        # ------------------------------------------------------------------
        # Step 3 — Parse OpEx
        # ------------------------------------------------------------------
        _set_progress(r, task_id, 3, 3, "Mapping expense categories…")
        expense_lines: list[dict] = []

        if opex_text:
            categories_str = "\n".join(f"- {c}" for c in STANDARD_OPEX_CATEGORIES)
            try:
                opex_prompt = (
                    "You are a real estate financial analyst. The following is tabular data from a "
                    "spreadsheet's operating expense sheet. For each expense line item:\n"
                    "1. Extract the annual dollar amount. If the sheet shows monthly columns, sum them.\n"
                    "2. Map the label to exactly one of the STANDARD CATEGORIES below. "
                    "Use null if you cannot confidently map it.\n"
                    "3. Set is_operating_expense=false for below-the-line items: debt service, interest, "
                    "depreciation, loan fee amortization, principal payments — these are NOT OpEx.\n"
                    "4. Set confidence to 0.0–1.0 based on how certain you are about the mapping.\n\n"
                    f"STANDARD CATEGORIES:\n{categories_str}\n\n"
                    "Mapping hints:\n"
                    "- 'LIFT Monitoring', 'OHCS', 'bond compliance', 'HUD monitoring' → Source Compliance\n"
                    "- 'Prop Mgmt', 'Property Management', 'On-Site', 'Off-Site' → Property Management\n"
                    "- 'RE Taxes', 'Real Estate Tax', 'Property Tax', 'Prop. Tax' → Real Estate Taxes\n"
                    "- 'Police and Fire', 'Municipal' → Real Estate Taxes (if annual assessment) or Other\n"
                    "- 'Accounting', 'CPA', 'Audit', 'Professional Fees', 'Legal' → Compliance & Legal\n"
                    "- 'Bank', 'NSF', 'Financing charges' → Bank/Software Fees\n"
                    "- 'AR Writeoffs', 'Bad Debt', 'Receivables' → is_operating_expense=false "
                    "(non-cash, excluded from underwriting)\n\n"
                    f"SHEET DATA:\n{opex_text}"
                )
                parsed_exp: ParsedExpenses = client.chat.completions.create(
                    model=settings.ollama_model,
                    response_model=ParsedExpenses,
                    messages=[{"role": "user", "content": opex_prompt}],
                )
                expense_lines = [e.model_dump() for e in parsed_exp.expense_lines]
            except Exception as exc:
                logger.warning("OpEx parse failed: %s", exc)
                warnings.append(f"OpEx parsing failed: {exc}")

        # ------------------------------------------------------------------
        # Write result
        # ------------------------------------------------------------------
        result = {
            "unit_types": unit_types,
            "expense_lines": expense_lines,
            "warnings": warnings,
        }
        r.set(f"proforma:{task_id}:result", json.dumps(result), ex=_REDIS_TTL)
        _set_done(r, task_id)

    except Exception as exc:
        logger.exception("proforma_parse task failed: %s", exc)
        _set_error(r, task_id, f"Unexpected error: {exc}")
