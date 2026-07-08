"""Opportunity wizard E2E — verify the 2-step wizard flow.

The wizard lost its "Link Property" step with the parcel-intelligence
decommission (DC-3/DC-4, then commit a51c24b removed the step entirely):
opportunities are now created standalone. Step 1 collects name / deal type /
broker and the "Review →" submit lands directly on the Review & Create step.

Run:
    uv run pytest tests/e2e/test_opportunity_wizard.py -m e2e -v
"""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.e2e


def _fill_step1(page, base_url: str) -> str:
    """Open the wizard and fill the step-1 required fields; return the suffix."""
    page.goto(f"{base_url}/ui/opportunities/wizard")
    page.wait_for_selector('input[name="name"]', timeout=10_000)
    suffix = uuid.uuid4().hex[:6]
    page.fill('input[name="name"]', f"E2E Wizard Review Path {suffix}")
    page.select_option('select[name="deal_type"]', "value_add")
    return suffix


def test_skip_attach_advances_to_review(logged_in_page, base_url):
    """Step 1 → Review must work with no property attached (the only path now:
    the Link Property step was removed; opportunities are standalone)."""
    page = logged_in_page
    _fill_step1(page, base_url)

    page.click('button:has-text("Review")')
    page.wait_for_selector('text=Review & Create', timeout=10_000)
    assert page.locator('text=No property linked').count() > 0


def test_wizard_broker_picker_renders_and_submits(logged_in_page, base_url):
    """The broker picker on step 1 renders real brokers and the form accepts one."""
    page = logged_in_page
    page.goto(f"{base_url}/ui/opportunities/wizard")
    page.wait_for_selector('input[name="name"]', timeout=10_000)

    broker_select = page.locator('select[name="broker_id"]')
    assert broker_select.count() == 1
    # "— None —" plus at least one real broker option (prod has ~450).
    assert broker_select.locator('option').count() > 1

    suffix = uuid.uuid4().hex[:6]
    page.fill('input[name="name"]', f"E2E Wizard Broker {suffix}")
    page.select_option('select[name="deal_type"]', "value_add")
    # Select the first real broker (index 0 is the blank "— None —").
    page.select_option('select[name="broker_id"]', index=1)
    page.click('button:has-text("Review")')

    # Broker accepted → wizard advances to the review step.
    page.wait_for_selector('text=Review & Create', timeout=10_000)
