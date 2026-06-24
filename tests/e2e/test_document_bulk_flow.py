"""E2E: bulk document actions — selection-gated action bar + bulk Move.

Covers both the Document View (table checkboxes) and Task View (per-card
checkboxes + a select-all) paths, and that the action bar only appears once at
least one document is selected.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.seed import _extract_project_id, create_e2e_scenario

pytestmark = pytest.mark.e2e


def _upload_two(page: Page, tmp_path) -> None:
    """Drop two PDFs into the doc-view modal and submit with defaults (Misc)."""
    a = tmp_path / "a.pdf"
    a.write_bytes(b"%PDF-1.4 a\n")
    b = tmp_path / "b.pdf"
    b.write_bytes(b"%PDF-1.4 b\n")
    with page.expect_file_chooser() as fc:
        page.click("#doc-dropzone")
    fc.value.set_files([str(a), str(b)])
    expect(page.locator("#vdup-modal")).to_be_visible()
    page.click("#vdup-submit")
    expect(page.locator(".doc-check")).to_have_count(2, timeout=15_000)


def test_bulk_bar_hidden_until_checked_then_move(logged_in_page: Page, tmp_path) -> None:
    page = logged_in_page
    create_e2e_scenario(page, deal_name="E2E Bulk Move")
    project_id = _extract_project_id(page)
    page.goto(f"/projects/{project_id}/documents")
    _upload_two(page, tmp_path)

    # Action bar stays hidden with nothing selected (delete-with-none is a no-op).
    expect(page.locator("#doc-bulk")).to_be_hidden()

    page.locator(".doc-check").nth(0).check()
    page.locator(".doc-check").nth(1).check()
    expect(page.locator("#doc-bulk")).to_be_visible()

    # Bulk-move both into a brand-new task.
    page.locator("#doc-bulk button", has_text="Move").click()
    expect(page.locator("#vdmove-modal")).to_be_visible()
    page.locator("#vdmove-task").select_option("__new__")
    page.locator("#vdmove-newtask").fill("Closing")
    page.click("#vdmove-submit")

    moved = page.locator(".doc-table .doc-name", has_text="- Closing -")
    expect(moved).to_have_count(2, timeout=15_000)
    # Bar resets (selection cleared) after the swap.
    expect(page.locator("#doc-bulk")).to_be_hidden()


def test_task_view_select_all_and_bulk_move(logged_in_page: Page, tmp_path) -> None:
    page = logged_in_page
    create_e2e_scenario(page, deal_name="E2E Task Bulk")
    project_id = _extract_project_id(page)
    page.goto(f"/projects/{project_id}/documents")
    _upload_two(page, tmp_path)

    page.goto(f"/projects/{project_id}/documents?view=tasks")
    expect(page.locator("#task-select-all")).to_be_visible()
    expect(page.locator(".task-check")).to_have_count(2)
    expect(page.locator("#task-bulk")).to_be_hidden()

    # Select-all reveals the bar and ticks both docs.
    page.locator("#task-select-all").check()
    expect(page.locator("#task-bulk")).to_be_visible()
    expect(page.locator(".task-check:checked")).to_have_count(2)

    page.locator("#task-bulk button", has_text="Move").click()
    expect(page.locator("#vdmove-modal")).to_be_visible()
    page.locator("#vdmove-task").select_option("__new__")
    page.locator("#vdmove-newtask").fill("Diligence")
    page.click("#vdmove-submit")

    # Task list re-renders with a new Diligence card holding both files.
    card = page.locator(".task-card", has=page.locator(".task-title", has_text="Diligence"))
    expect(card).to_be_visible(timeout=15_000)
    expect(card.locator(".task-doc")).to_have_count(2)
