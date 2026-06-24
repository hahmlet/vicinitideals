"""E2E: dedicated task-notes button + rich-text editor.

Creates a task, opens its Notes editor, types, saves, and verifies the notes
persist and the button shows the has-notes indicator on re-render.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.seed import _extract_project_id, create_e2e_scenario

pytestmark = pytest.mark.e2e


def test_task_notes_editor_persists(logged_in_page: Page) -> None:
    page = logged_in_page
    create_e2e_scenario(page, deal_name="E2E Notes")
    project_id = _extract_project_id(page)
    page.goto(f"/projects/{project_id}/documents?view=tasks")

    # Create a task to attach notes to.
    page.fill('input[name="title"]', "Notes Task")
    page.locator('button:has-text("+ Add Task")').click()
    card = page.locator(".task-card", has=page.locator(".task-title", has_text="Notes Task"))
    expect(card).to_be_visible(timeout=15_000)

    # Notes editor is hidden until the button is clicked.
    expect(card.locator(".task-notes-slot")).to_be_hidden()
    card.locator(".task-notes-btn").click()
    editor = card.locator(".rt-editor")
    expect(editor).to_be_visible()

    editor.click()
    page.keyboard.type("Need signed copies")
    # Apply a bullet list via the toolbar (exercises execCommand wiring).
    card.locator('.rt-toolbar button[title="Bullet list"]').click()
    card.locator('button:has-text("Save notes")').click()

    # Card re-renders; the button now flags that notes exist.
    saved = page.locator(".task-card", has=page.locator(".task-title", has_text="Notes Task"))
    expect(saved.locator(".task-notes-btn.has-notes")).to_be_visible(timeout=10_000)

    # Reopen — the text persisted.
    saved.locator(".task-notes-btn").click()
    expect(saved.locator(".rt-editor")).to_contain_text("Need signed copies")
