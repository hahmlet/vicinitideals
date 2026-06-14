"""Opportunities list E2E — the three row sections load without 500s.

Regression guard for the parcel decommission (DC-5c): the Active Deals section
fetches ``/ui/opportunities/rows/deals`` into ``#deals-tbody``. Manual deals have
NULL units/sqft, which used to fall through to a ``self.parcel`` lazy load on an
async session and 500 — the partial then injected an ``internal_server_error``
JSON blob into the table. This test asserts all three sections render real rows
(or an empty state) with no error payload.

Run:
    uv run pytest tests/e2e/test_opportunities_list.py -m e2e -v
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e


def test_opportunities_sections_load_without_error(logged_in_page, base_url):
    page = logged_in_page
    page.goto(f"{base_url}/opportunities")

    # Each section's tbody is populated by a JS fetch; wait for the counts to
    # resolve off the "—" placeholder, then assert no error payload landed.
    for section in ("deals", "offmarket", "onmarket"):
        tbody = page.locator(f"#{section}-tbody")
        count = page.locator(f"#{section}-count")
        page.wait_for_function(
            "id => document.getElementById(id) && "
            "document.getElementById(id).textContent.trim() !== '—'",
            arg=f"{section}-count",
            timeout=15_000,
        )
        assert "internal_server_error" not in tbody.inner_text()
        assert "unexpected server error" not in tbody.inner_text()
        # Count badge is a number once loaded (may be 0), never the placeholder.
        assert count.inner_text().strip().isdigit()
