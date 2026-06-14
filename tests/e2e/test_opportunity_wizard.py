"""Opportunity wizard E2E — verify the wizard's skip-property path works.

The parcel-attach test was removed with the parcel-intelligence decommission
(DC-3/DC-4); the skip path is the remaining regression guard for the
step 2 → step 3 flow.

Run:
    uv run pytest tests/e2e/test_opportunity_wizard.py -m e2e -v
"""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.e2e


def _start_wizard_at_step2(page, base_url: str) -> str:
    """Drive the wizard through step 1; return on step 2 ready to search."""
    page.goto(f"{base_url}/ui/opportunities/wizard")
    page.wait_for_selector('input[name="name"]', timeout=10_000)
    suffix = uuid.uuid4().hex[:6]
    page.fill('input[name="name"]', f"E2E Wizard Skip Path {suffix}")
    page.select_option('select[name="deal_type"]', "value_add")
    page.click('button:has-text("Next: Link Property")')
    page.wait_for_selector('#prop-search', timeout=10_000)
    return suffix


def test_skip_attach_advances_to_review(logged_in_page, base_url):
    """Skip link must still work — no regression in the skip path."""
    page = logged_in_page
    _start_wizard_at_step2(page, base_url)

    page.click('#skip-link')
    page.wait_for_selector('text=Review & Create', timeout=10_000)
    assert page.locator('text=No property linked').count() > 0
