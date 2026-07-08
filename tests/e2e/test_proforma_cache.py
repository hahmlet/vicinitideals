"""E2E test for pro forma file content-hash cache.

Uploads the same xlsx twice and asserts the second upload skips the LLM
call: a cache hit renders the review fragment directly, with a "Cached
result" banner carrying Re-analyze / Purge cache actions. Requires:

* The LLM backend is reachable so the first parse can complete. Without
  it, the first upload times out and the test fails — rather than skip,
  since this is the path the cache protects.

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
    """From the wizard root, pick Revenue/OpEx — proforma block is on step 1.

    The file input is permanently hidden (styled drop-zone label pattern:
    ``.proforma-zone input[type="file"] { display: none; }``), so wait for
    attachment, not visibility — set_input_files works on hidden inputs.
    """
    page.click('input[value="revenue_opex"]')
    wait_for_htmx(page)
    page.wait_for_selector("#proforma-file", state="attached", timeout=10_000)


def _upload(page, xlsx_bytes: bytes) -> None:
    page.set_input_files(
        "#proforma-file",
        files=[{
            "name": "p.xlsx",
            "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "buffer": xlsx_bytes,
        }],
    )
    # PRE-DEPLOY BRIDGE: production's onProformaFile drained the FileList
    # before submit (shared-FileList bug — fixed in
    # app/templates/partials/deal_setup_wizard.html, pending deploy). When the
    # input comes back empty after the change event, re-populate it exactly as
    # the fixed handler leaves it. Self-disabling: once the fix is live,
    # input.files.length > 0 and this is a no-op. Safe to delete after deploy.
    import base64
    page.evaluate(
        """(b64) => {
            const input = document.getElementById('proforma-file');
            if (!input || input.files.length > 0) return;
            const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
            const dt = new DataTransfer();
            dt.items.add(new File([bytes], 'p.xlsx', {
                type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            }));
            input.files = dt.files;
        }""",
        base64.b64encode(xlsx_bytes).decode(),
    )
    # File selection triggers onProformaFile → _pfRebuildPills → button "Import →"
    page.click("#step1-submit")
    wait_for_htmx(page)


def _pick_sheets_and_analyze(page) -> None:
    """Drive the "Where is the Data?" sheet picker for the 2-sheet test file.

    On multi-sheet workbooks #pf-submit (Analyze →) stays disabled until every
    enabled section has a sheet chosen — select both, then click.
    """
    page.wait_for_selector("#pf-submit", timeout=15_000)
    page.select_option("#pf-rev-sheet", "Rent Roll")
    page.select_option("#pf-opex-sheet", "OpEx")
    page.click("#pf-submit")


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

    # Preflight returns the sheet picker → pick sheets, Analyze starts the parse
    _pick_sheets_and_analyze(page)

    # Progress polling resolves to the review fragment once the LLM responds.
    # Give it up to 180s (slow LLMs / cold-started Ollama).
    page.wait_for_selector("#proforma-confirm-form", timeout=180_000)

    # ── Second upload: same bytes → expect a cache hit ─────────────────────
    # Reload so the wizard restarts at step 1; income_mode is already saved
    # in the DB so Next still routes us back to the upload step.
    _open_wizard(page, base_url, model_id)
    _reach_upload_step(page)
    _upload(page, xlsx_bytes)

    # A cache hit skips BOTH the sheet picker and the LLM call: the review
    # fragment renders immediately with a "Cached result" banner carrying
    # Re-analyze / Purge cache actions.
    page.wait_for_selector("#proforma-confirm-form", timeout=15_000)
    assert page.locator("text=Cached result").count() > 0, (
        "Second upload of identical bytes should surface the cache-hit banner"
    )
    assert page.locator('button:has-text("Re-analyze")').count() > 0
    assert page.locator('button:has-text("Purge cache")').count() > 0


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
    _pick_sheets_and_analyze(page)
    page.wait_for_selector("#proforma-confirm-form", timeout=180_000)

    # Second upload of the same bytes: cache hit renders the review page
    # directly with the cached banner + Re-analyze button.
    _open_wizard(page, base_url, model_id)
    _reach_upload_step(page)
    _upload(page, xlsx_bytes)
    page.wait_for_selector('button:has-text("Re-analyze")', timeout=15_000)

    # Re-analyze swaps the review out for the xlsx sheet picker (#pf-submit
    # is its Analyze button) so the user can run a fresh parse.
    page.click('button:has-text("Re-analyze")')
    wait_for_htmx(page)
    page.wait_for_selector("#pf-submit", timeout=10_000)
