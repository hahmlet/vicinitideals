"""E2E test for pro forma file content-hash cache.

Uploads the same xlsx twice and asserts the second upload triggers the
cache-hit fragment (skipping the LLM call). Requires:

* The branch is deployed to the live app (``feature/wizard-state-and-proforma-cache``).
* Ollama (or whatever the configured LLM backend is) is reachable so the
  first parse can complete. Without it, the first upload times out and
  the test fails — rather than skip, since this is the path the cache
  protects.

Marked ``slow`` because the first parse takes up to ~120s. Run:

    uv run pytest tests/e2e/test_proforma_cache.py -m "e2e and slow" -v
"""

from __future__ import annotations

import io
import uuid

import pytest

from tests.e2e.helpers import wait_for_htmx
from tests.e2e.seed import (
    _extract_project_id,
    create_e2e_scenario,
    submit_timeline_wizard,
)

pytestmark = [pytest.mark.e2e, pytest.mark.slow]


def _minimal_xlsx() -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Rent Roll"
    ws.append(["Unit Type", "Units", "Avg SF", "Monthly Rent"])
    ws.append(["1BR", 10, 700, 1500])
    ws.append(["2BR", 5, 950, 2000])

    ws2 = wb.create_sheet("OpEx")
    ws2.append(["Line", "Annual"])
    ws2.append(["Insurance", 5000])
    ws2.append(["Property Tax", 30000])
    ws2.append(["Utilities", 8000])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _open_wizard(page, base_url: str, model_id: str) -> None:
    page.goto(f"{base_url}/models/{model_id}/builder?module=deal_setup")
    page.wait_for_selector("#deal-setup-wizard", timeout=10_000)
    wait_for_htmx(page)


def _reach_upload_step(page) -> None:
    """From the wizard root, pick Revenue/OpEx — proforma block is on step 1."""
    page.click('input[value="revenue_opex"]')
    wait_for_htmx(page)
    page.wait_for_selector("#proforma-file", timeout=10_000)


def _upload(page, xlsx_bytes: bytes) -> None:
    page.set_input_files(
        "#proforma-file",
        files=[{
            "name": "p.xlsx",
            "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "buffer": xlsx_bytes,
        }],
    )
    # File selection triggers onProformaFile → _pfRebuildPills → button "Import →"
    page.click("#step1-submit")
    wait_for_htmx(page)


def test_second_upload_of_same_file_hits_cache(_seed_page, base_url):
    page = _seed_page
    suffix = uuid.uuid4().hex[:6]
    model_id = create_e2e_scenario(page, deal_name=f"E2E Proforma Cache {suffix}")
    project_id = _extract_project_id(page)
    submit_timeline_wizard(
        page, model_id, project_id,
        milestone_types=["close", "construction", "operation_stabilized", "divestment"],
        phase_durations={"construction": 180, "operation_stabilized": 730},
    )

    xlsx_bytes = _minimal_xlsx()

    # ── First upload: real LLM parse ───────────────────────────────────────
    _open_wizard(page, base_url, model_id)
    _reach_upload_step(page)
    _upload(page, xlsx_bytes)

    # Preflight returns the sheet picker → Analyze kicks off the Celery parse
    page.wait_for_selector('button:has-text("Analyze")', timeout=15_000)
    page.click('button:has-text("Analyze")')

    # Progress polling resolves to the review fragment once the LLM responds.
    # Give it up to 180s (slow LLMs / cold-started Ollama).
    page.wait_for_selector("#proforma-confirm-form", timeout=180_000)

    # ── Second upload: same bytes → expect cache-hit fragment ──────────────
    # Reload so the wizard restarts at step 1; income_mode is already saved
    # in the DB so Next still routes us back to the upload step.
    _open_wizard(page, base_url, model_id)
    _reach_upload_step(page)
    _upload(page, xlsx_bytes)

    # Cache-hit fragment surfaces "Use Cached Result" and "Re-analyze".
    page.wait_for_selector('button:has-text("Use Cached Result")', timeout=15_000)
    assert page.locator('button:has-text("Re-analyze")').count() > 0

    # Clicking Use Cached Result skips the parse and jumps straight to review.
    page.click('button:has-text("Use Cached Result")')
    page.wait_for_selector("#proforma-confirm-form", timeout=10_000)


def test_reanalyze_button_goes_to_sheet_picker(_seed_page, base_url):
    """Cache-hit path with Re-analyze: should land back on the sheet picker
    (xlsx) so the user can pick sheets and run a fresh parse. The cached
    result is left intact."""
    page = _seed_page
    suffix = uuid.uuid4().hex[:6]
    model_id = create_e2e_scenario(page, deal_name=f"E2E Proforma Reanalyze {suffix}")
    project_id = _extract_project_id(page)
    submit_timeline_wizard(
        page, model_id, project_id,
        milestone_types=["close", "construction", "operation_stabilized", "divestment"],
        phase_durations={"construction": 180, "operation_stabilized": 730},
    )

    xlsx_bytes = _minimal_xlsx()

    _open_wizard(page, base_url, model_id)
    _reach_upload_step(page)
    _upload(page, xlsx_bytes)
    page.click('button:has-text("Analyze")')
    page.wait_for_selector("#proforma-confirm-form", timeout=180_000)

    _open_wizard(page, base_url, model_id)
    _reach_upload_step(page)
    _upload(page, xlsx_bytes)
    page.wait_for_selector('button:has-text("Re-analyze")', timeout=15_000)

    page.click('button:has-text("Re-analyze")')
    wait_for_htmx(page)
    page.wait_for_selector('button:has-text("Analyze")', timeout=10_000)
