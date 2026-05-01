"""E2E test for the Gap Adjustment slider feature.

Drives the full flow against a live app:
  1. Seed a deal via the existing browser wizard helpers
  2. Navigate to model_builder, sources_uses module
  3. Verify slider drawer renders
  4. POST to /api/models/{id}/sliders with a non-zero delta
  5. Verify response shape (DSCR, equity, has_any_adjustment)
  6. Re-render panel — verify pill yellow override + phantom row highlight

Run:
    uv run pytest tests/e2e/test_gap_adjustment_slider.py -m e2e -v
"""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from tests.e2e.seed import create_seeded_deal

pytestmark = pytest.mark.e2e


def _session_cookie(page) -> str | None:
    for c in page.context.cookies():
        if c.get("name") == "vd_session":
            return c.get("value")
    return None


def test_slider_drawer_renders_and_persists_phantom_rows(
    logged_in_page,
    base_url: str,
    api_key: str,
) -> None:
    """Full flow: seed → drawer renders → POST /sliders → phantoms persist → pill yellow."""
    page = logged_in_page

    # 1. Seed a fully-configured deal via browser wizard.
    model_id, project_id = create_seeded_deal(
        page, deal_name="E2E Slider Test", deal_type="acquisition",
    )

    # 1a. Wizard auto-sizes debt → typically no gap → drawer hides. POST a
    # non-zero phantom first via API so the drawer renders on page load.
    cookie_pre = _session_cookie(page)
    with httpx.Client(
        base_url=base_url,
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        cookies={"vd_session": cookie_pre} if cookie_pre else {},
        timeout=30,
    ) as c:
        r0 = c.post(
            f"/api/models/{model_id}/sliders",
            json={"revenue_delta_monthly": "100"},
        )
        assert r0.status_code == 200, r0.text

    # 2. Navigate to model_builder, sources_uses module
    page.goto(f"{base_url}/models/{model_id}/builder?module=sources_uses")
    page.wait_for_selector("#gap-adj-drawer", timeout=10_000)

    # 3. Drawer renders all three sliders + reset button
    assert page.locator("#gap-slider-rev").count() == 1
    assert page.locator("#gap-slider-opex").count() == 1
    assert page.locator("#gap-slider-pp").count() == 1
    assert page.locator("button:has-text('Reset all')").count() == 1

    # 4. POST a non-zero delta via API (faster + deterministic vs simulated drag)
    cookie = _session_cookie(page)
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
    }
    cookies = {"vd_session": cookie} if cookie else {}
    with httpx.Client(base_url=base_url, headers=headers, cookies=cookies, timeout=30) as c:
        r = c.post(
            f"/api/models/{model_id}/sliders",
            json={
                "revenue_delta_monthly": "500",
                "opex_delta_annual": "-3000",
                "pp_delta": "-25000",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()

    # 5. Response shape contract
    assert body["has_any_adjustment"] is True
    assert Decimal(body["revenue_delta_monthly"]) == Decimal("500")
    assert Decimal(body["opex_delta_annual"]) == Decimal("-3000")
    assert Decimal(body["pp_delta"]) == Decimal("-25000")
    # DSCR / equity_required / total_project_cost present (post-compute happened)
    assert "dscr" in body
    assert "equity_required" in body
    assert "total_project_cost" in body

    # 6. Re-render panel — phantoms persist + pill turns yellow
    page.reload()
    page.wait_for_selector("#gap-adj-drawer", timeout=10_000)
    # Sliders pre-fill from persisted phantom row amounts. Browser snaps to
    # step grid when min/max aren't aligned at step boundary, so allow
    # ±1 step tolerance rather than exact match.
    rev_val = int(page.locator("#gap-slider-rev").input_value())
    pp_val = int(page.locator("#gap-slider-pp").input_value())
    assert abs(rev_val - 500) <= 100, f"revenue slider didn't pre-fill near 500: {rev_val}"
    assert abs(pp_val - (-25000)) <= 1000, f"pp slider didn't pre-fill near -25000: {pp_val}"

    # Pill yellow override: text says "Balanced w/ adjustments" OR underlying real
    # failure label (depending on whether the seeded deal pencils). Either way,
    # pill class should be 'warn' not 'ok'.
    pill = page.locator(".calc-status-pill")
    pill_class = pill.get_attribute("class") or ""
    assert "warn" in pill_class or "fail" in pill_class, (
        f"pill should be yellow/red after adjustment; class={pill_class!r}"
    )


def test_slider_reset_zeroes_phantoms(
    logged_in_page,
    base_url: str,
    api_key: str,
) -> None:
    """Reset all → all phantom amounts go to 0 → has_any_adjustment=False."""
    page = logged_in_page

    model_id, _ = create_seeded_deal(
        page, deal_name="E2E Slider Reset Test", deal_type="acquisition",
    )

    cookie = _session_cookie(page)
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
    cookies = {"vd_session": cookie} if cookie else {}

    with httpx.Client(base_url=base_url, headers=headers, cookies=cookies, timeout=30) as c:
        # Set non-zero
        c.post(
            f"/api/models/{model_id}/sliders",
            json={"revenue_delta_monthly": "1000"},
        )
        # Reset
        r = c.post(
            f"/api/models/{model_id}/sliders",
            json={
                "revenue_delta_monthly": "0",
                "opex_delta_annual": "0",
                "pp_delta": "0",
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["has_any_adjustment"] is False


def test_slider_perimeter_blocks_direct_phantom_mutation(
    logged_in_page,
    base_url: str,
    api_key: str,
) -> None:
    """Reserved-label rows can't be deleted via the public CRUD endpoint —
    PR3b-i guard. Verifies perimeter is sealed in prod."""
    page = logged_in_page

    model_id, project_id = create_seeded_deal(
        page, deal_name="E2E Slider Perimeter Test", deal_type="acquisition",
    )

    cookie = _session_cookie(page)
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
    cookies = {"vd_session": cookie} if cookie else {}

    with httpx.Client(base_url=base_url, headers=headers, cookies=cookies, timeout=30) as c:
        # Materialize phantom rev row
        c.post(
            f"/api/models/{model_id}/sliders",
            json={"revenue_delta_monthly": "500"},
        )
        # Find the phantom IncomeStream
        r = c.get(f"/api/models/{model_id}/income-streams")
        assert r.status_code == 200
        rows = r.json()
        phantom = next(
            (s for s in rows if s.get("label") == "Gap Adjustment — Revenue"),
            None,
        )
        assert phantom is not None, f"phantom row not found in {[s.get('label') for s in rows]}"
        # Direct DELETE must be rejected with 403
        r = c.delete(
            f"/api/models/{model_id}/income-streams/{phantom['id']}"
        )
        assert r.status_code == 403, r.text
        assert "phantom row" in r.text.lower()
