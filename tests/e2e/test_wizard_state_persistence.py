"""E2E tests for Deal Setup wizard localStorage state persistence.

Verifies the Option A wizard-state persistence wired into
``deal_setup_wizard.html``:

* Changing an input writes ``wizard:{model_id}:{step}`` to localStorage
* A successful step submit removes that step's localStorage key
* When a step's fragment renders with a saved state pre-populated, the
  restore JS re-applies it to the form inputs
* Storage keys are scoped per ``model_id`` so two deals don't collide

These tests run against the live app (skipped if unreachable, per
``_require_live_app`` in :mod:`tests.e2e.conftest`). They require that
``feature/wizard-state-and-proforma-cache`` is deployed.

Run:
    uv run pytest tests/e2e/test_wizard_state_persistence.py -m e2e -v
"""

from __future__ import annotations

import json
import uuid

import pytest

from tests.e2e.helpers import wait_for_htmx
from tests.e2e.seed import (
    _extract_project_id,
    create_e2e_scenario,
    submit_timeline_wizard,
)

pytestmark = pytest.mark.e2e


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_wizard_deal(page) -> str:
    """Create a deal with an approved timeline so the deal-setup wizard is
    reachable. Returns the model_id."""
    suffix = uuid.uuid4().hex[:6]
    model_id = create_e2e_scenario(page, deal_name=f"E2E Persist {suffix}")
    project_id = _extract_project_id(page)
    submit_timeline_wizard(
        page, model_id, project_id,
        milestone_types=["close", "construction", "operation_stabilized", "divestment"],
        phase_durations={"construction": 180, "operation_stabilized": 730},
    )
    return model_id


def _open_wizard(page, base_url: str, model_id: str) -> None:
    page.goto(f"{base_url}/models/{model_id}/builder?module=deal_setup")
    page.wait_for_selector("#deal-setup-wizard", timeout=10_000)
    wait_for_htmx(page)


def _get_storage(page, key: str):
    return page.evaluate("(k) => localStorage.getItem(k)", key)


def _set_storage(page, key: str, value: str) -> None:
    page.evaluate("([k, v]) => localStorage.setItem(k, v)", [key, value])


def _clear_wizard_storage(page, model_id: str) -> None:
    page.evaluate(
        "(prefix) => { Object.keys(localStorage)"
        ".filter(k => k.startsWith(prefix))"
        ".forEach(k => localStorage.removeItem(k)); }",
        f"wizard:{model_id}:",
    )


# ---------------------------------------------------------------------------
# Save behavior
# ---------------------------------------------------------------------------

def test_step1_radio_change_saves_to_localstorage(_seed_page, base_url):
    """Changing the Income Mode radio writes wizard:{model_id}:1."""
    page = _seed_page
    model_id = _fresh_wizard_deal(page)
    _open_wizard(page, base_url, model_id)
    _clear_wizard_storage(page, model_id)

    assert _get_storage(page, f"wizard:{model_id}:1") is None

    page.click('input[value="noi"]')
    wait_for_htmx(page)

    raw = _get_storage(page, f"wizard:{model_id}:1")
    assert raw is not None, "expected step-1 state in localStorage after radio change"
    state = json.loads(raw)
    assert state.get("radios", {}).get("income_mode") == "noi"


def test_step2_checkbox_saves_to_localstorage(_seed_page, base_url):
    """Checking a debt type in step 2 populates wizard:{model_id}:2."""
    page = _seed_page
    model_id = _fresh_wizard_deal(page)
    _open_wizard(page, base_url, model_id)

    page.click('input[value="revenue_opex"]')
    page.click('#deal-setup-wizard button:has-text("Next")')
    wait_for_htmx(page)
    page.wait_for_selector("#debt-type-grid", timeout=5000)

    _clear_wizard_storage(page, model_id)
    page.locator('#debt-type-grid input[value="construction_loan"]').check()
    wait_for_htmx(page)

    raw = _get_storage(page, f"wizard:{model_id}:2")
    assert raw is not None
    state = json.loads(raw)
    assert state.get("checkboxes", {}).get("debt_types::construction_loan") is True


# ---------------------------------------------------------------------------
# Clear-on-submit behavior
# ---------------------------------------------------------------------------

def test_successful_step_submit_clears_localstorage_key(_seed_page, base_url):
    """A 2xx HTMX response should remove the submitted step's storage key."""
    page = _seed_page
    model_id = _fresh_wizard_deal(page)
    _open_wizard(page, base_url, model_id)
    _clear_wizard_storage(page, model_id)

    page.click('input[value="revenue_opex"]')
    wait_for_htmx(page)
    assert _get_storage(page, f"wizard:{model_id}:1") is not None

    page.click('#deal-setup-wizard button:has-text("Next")')
    wait_for_htmx(page)
    page.wait_for_selector("#debt-type-grid", timeout=5000)

    assert _get_storage(page, f"wizard:{model_id}:1") is None


# ---------------------------------------------------------------------------
# Restore behavior
# ---------------------------------------------------------------------------

def test_step2_restores_from_localstorage_on_swap_in(_seed_page, base_url):
    """Pre-seed step-2 state in localStorage, advance from step 1, and assert
    the step-2 partial's restore JS re-checks the right debt-type boxes."""
    page = _seed_page
    model_id = _fresh_wizard_deal(page)
    _open_wizard(page, base_url, model_id)

    state = {
        "radios": {},
        "checkboxes": {
            "debt_types::construction_loan": True,
            "debt_types::permanent_debt": True,
        },
        "fields": {},
    }
    _set_storage(page, f"wizard:{model_id}:2", json.dumps(state))

    page.click('input[value="revenue_opex"]')
    page.click('#deal-setup-wizard button:has-text("Next")')
    wait_for_htmx(page)
    page.wait_for_selector("#debt-type-grid", timeout=5000)

    cl = page.locator('#debt-type-grid input[value="construction_loan"]')
    pd = page.locator('#debt-type-grid input[value="permanent_debt"]')
    assert cl.is_checked(), "construction_loan should be restored from localStorage"
    assert pd.is_checked(), "permanent_debt should be restored from localStorage"


# ---------------------------------------------------------------------------
# Per-model keying
# ---------------------------------------------------------------------------

def test_storage_is_scoped_per_model_id(_seed_page, base_url):
    """Two deals must not share each other's wizard storage."""
    page = _seed_page
    model_a = _fresh_wizard_deal(page)
    _open_wizard(page, base_url, model_a)
    _clear_wizard_storage(page, model_a)

    page.click('input[value="noi"]')
    wait_for_htmx(page)
    assert _get_storage(page, f"wizard:{model_a}:1") is not None

    model_b = _fresh_wizard_deal(page)
    _open_wizard(page, base_url, model_b)

    # Different model_id → no inherited step-1 state from model_a
    assert _get_storage(page, f"wizard:{model_b}:1") is None
    # And model_a's state is still intact (keys are isolated, not global)
    assert _get_storage(page, f"wizard:{model_a}:1") is not None
