"""E2E: a file refused by a task upload says why on the task card.

Uploading into a task used to drop a refused file (wrong type, empty, too big)
without a word — the card redrew as if it had worked. The card now carries the
same reason line the main document panel shows.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.seed import _extract_project_id, create_e2e_scenario

pytestmark = pytest.mark.e2e


def test_task_upload_shows_refusal_reason(logged_in_page: Page, tmp_path) -> None:
    page = logged_in_page
    create_e2e_scenario(page, deal_name="E2E Task Upload Refusal")
    project_id = _extract_project_id(page)
    page.goto(f"/projects/{project_id}/documents?view=tasks")

    page.fill('input[name="title"]', "Refusal Task")
    page.locator('button:has-text("+ Add Task")').click()
    card = page.locator(".task-card", has=page.locator(".task-title", has_text="Refusal Task"))
    expect(card).to_be_visible(timeout=15_000)

    empty = tmp_path / "blank.pdf"
    empty.write_bytes(b"")
    with page.expect_file_chooser() as fc:
        card.locator('button:has-text("Add files")').click()
    fc.value.set_files(str(empty))
    expect(page.locator("#vdup-modal")).to_be_visible()
    page.click("#vdup-submit")

    redrawn = page.locator(".task-card", has=page.locator(".task-title", has_text="Refusal Task"))
    expect(redrawn.locator(".doc-errors")).to_contain_text("blank.pdf", timeout=15_000)
    expect(redrawn.locator(".doc-errors")).to_contain_text("empty file skipped")
    expect(redrawn.locator(".task-meta")).to_contain_text("0 files")
