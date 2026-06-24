"""E2E: the wizard-style document upload modal.

Exercises the real path — click the dropzone (which runs VDUP.open and opens the
file chooser), fill per-file Name / Status / Task, submit, and assert the new
document shows its computed scheme name with the original filename retained.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.seed import _extract_project_id, create_e2e_scenario

pytestmark = pytest.mark.e2e


def test_upload_modal_creates_named_document(logged_in_page: Page, tmp_path) -> None:
    page = logged_in_page

    # Light fixture: a deal/scenario/project, no full wizard needed for the room.
    model_id = create_e2e_scenario(page, deal_name="E2E Docs Deal")
    project_id = _extract_project_id(page)

    page.goto(f"/projects/{project_id}/documents")
    expect(page.locator("#doc-panel")).to_be_visible()

    upload = tmp_path / "rentroll.pdf"
    upload.write_bytes(b"%PDF-1.4 e2e upload\n")

    # Clicking the dropzone runs VDUP.open(cfg) -> input.click() -> file chooser.
    with page.expect_file_chooser() as fc:
        page.click("#doc-dropzone")
    fc.value.set_files(str(upload))

    # Modal opens with exactly one row.
    expect(page.locator("#vdup-modal")).to_be_visible()
    row = page.locator(".vdup-row").first
    expect(row).to_be_visible()

    # Per-file metadata: name + Final + a brand-new task.
    row.locator(".vdup-name").fill("Rent Roll")
    row.locator(".vdup-stage").select_option("final")
    row.locator(".vdup-task").select_option("__new__")
    row.locator(".vdup-newtask").fill("Leases")

    page.click("#vdup-submit")

    # Upload is an XHR (not htmx); wait for the swapped row's scheme name.
    named = page.locator(".doc-table .doc-name", has_text="Leases - Rent Roll - Final")
    expect(named.first).to_be_visible(timeout=15_000)

    # Original filename retained as the audit caption.
    expect(
        page.locator(".doc-orig", has_text="rentroll.pdf").first
    ).to_be_visible()

    # Modal closed after a successful upload.
    expect(page.locator("#vdup-modal")).to_be_hidden()

    # Status reflected in the row's stage dropdown.
    stage_sel = page.locator(".doc-table .doc-stage-sel").first
    expect(stage_sel).to_have_value("final")


def test_upload_status_toggle_renames_without_reupload(
    logged_in_page: Page, tmp_path
) -> None:
    page = logged_in_page
    model_id = create_e2e_scenario(page, deal_name="E2E Docs Toggle")
    project_id = _extract_project_id(page)
    page.goto(f"/projects/{project_id}/documents")

    upload = tmp_path / "survey.pdf"
    upload.write_bytes(b"%PDF-1.4 survey\n")
    with page.expect_file_chooser() as fc:
        page.click("#doc-dropzone")
    fc.value.set_files(str(upload))
    expect(page.locator("#vdup-modal")).to_be_visible()
    page.locator(".vdup-row").first.locator(".vdup-name").fill("Survey")
    page.click("#vdup-submit")

    draft = page.locator(".doc-table .doc-name", has_text="Survey - Draft")
    expect(draft.first).to_be_visible(timeout=15_000)

    # Flip to Final from the row — name recomputes, no re-upload.
    page.locator(".doc-table .doc-stage-sel").first.select_option("final")
    final = page.locator(".doc-table .doc-name", has_text="Survey - Final")
    expect(final.first).to_be_visible(timeout=10_000)
