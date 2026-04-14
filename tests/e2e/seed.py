"""E2E seed helpers — create minimal test fixtures via the live app's HTTP API.

Requires the app stack to be running (docker compose up) and at least one
Organization to exist in the DB (created by seed_demo_data or the wizard).

Usage:
    from tests.e2e.seed import create_e2e_scenario, create_seeded_deal

    model_id = create_e2e_scenario(base_url, session_cookie)
    # Use model_id to navigate: /models/{model_id}/builder

    model_id, project_id = create_seeded_deal(base_url, auth_state_path)
    # Use model_id + project_id for lifecycle math-verification tests
"""

from __future__ import annotations

import json
import re

import httpx

COOKIE_NAME = "vd_session"


def load_session_cookie(auth_state_path: str) -> str:
    """Extract the vd_session cookie value from a Playwright storageState JSON file."""
    with open(auth_state_path) as f:
        state = json.load(f)
    for cookie in state.get("cookies", []):
        if cookie.get("name") == COOKIE_NAME:
            return cookie["value"]
    raise ValueError(f"No {COOKIE_NAME} cookie found in {auth_state_path!r}")


def create_e2e_scenario(
    base_url: str,
    auth_state_path: str,
    *,
    deal_name: str = "E2E Test Deal",
    deal_type: str = "acquisition_minor_reno",
) -> str:
    """POST /ui/deals/create using the saved session cookie; return scenario UUID.

    The create endpoint redirects to /models/{model_id}/builder on success.
    Returns the model_id UUID string.
    Raises AssertionError if creation fails.
    """
    session_cookie = load_session_cookie(auth_state_path)
    cookies = {COOKIE_NAME: session_cookie}

    with httpx.Client(base_url=base_url, follow_redirects=False, cookies=cookies) as client:
        resp = client.post(
            "/ui/deals/create",
            data={"name": deal_name, "deal_type": deal_type},
        )

    if resp.status_code == 303:
        location = resp.headers.get("location", "")
        # Location: /models/{model_id}/builder or /models/{model_id}/builder?new=1
        parts = location.split("/models/", 1)
        assert len(parts) == 2, f"Unexpected redirect location: {location!r}"
        model_id = parts[1].split("/")[0].split("?")[0]
        assert model_id, f"Could not parse model_id from redirect: {location!r}"
        return model_id

    raise AssertionError(
        f"Deal creation expected 303 redirect, got {resp.status_code}: "
        f"{resp.text[:300]}"
    )


def _get_project_id(base_url: str, session_cookie: str, model_id: str) -> str:
    """GET the builder page and extract the default project_id from the wizard form action."""
    cookies = {COOKIE_NAME: session_cookie}
    with httpx.Client(base_url=base_url, follow_redirects=True, cookies=cookies) as client:
        resp = client.get(f"/models/{model_id}/builder")
    assert resp.status_code == 200, f"Builder page returned {resp.status_code}: {resp.text[:200]}"
    match = re.search(r"/ui/projects/([0-9a-f-]{36})/timeline-wizard", resp.text)
    assert match, "Could not find project_id in builder page HTML (missing timeline-wizard form action)"
    return match.group(1)


def create_seeded_deal(
    base_url: str,
    auth_state_path: str,
    *,
    deal_name: str = "E2E Lifecycle Test Deal",
    deal_type: str = "acquisition_minor_reno",
) -> tuple[str, str]:
    """Create a fully seeded deal ready for structural math-verification tests.

    Steps performed:
      1. Create deal (POST /ui/deals/create)
      2. Submit timeline wizard (acquisition anchor with construction + exit)
      3. Approve timeline
      4. Complete deal setup wizard (steps 1–4 + complete)
      5. Add 3 use lines: Purchase Price, Renovation, Operating Reserve
      6. Add 1 income stream: Residential Rent (10 units × $1,200/mo, 95% occ)
      7. Add 3 expense lines: Property Mgmt, Insurance, Property Tax
      8. POST /api/models/{model_id}/compute

    Returns:
        (model_id, project_id) — both as UUID strings
    """
    model_id = create_e2e_scenario(
        base_url, auth_state_path, deal_name=deal_name, deal_type=deal_type
    )
    session_cookie = load_session_cookie(auth_state_path)
    cookies = {COOKIE_NAME: session_cookie}
    project_id = _get_project_id(base_url, session_cookie, model_id)

    with httpx.Client(base_url=base_url, follow_redirects=False, cookies=cookies) as client:

        # ── 1. Timeline wizard ───────────────────────────────────────────────
        # Anchor: close (acquisition close), 45-day duration.
        # Milestones: close → construction → operation_stabilized → divestment
        resp = client.post(
            f"/ui/projects/{project_id}/timeline-wizard",
            data=[
                ("anchor_type", "close"),
                ("anchor_date", "2026-09-01"),
                ("anchor_duration_days", "45"),
                ("milestone_types", "close"),
                ("milestone_types", "construction"),
                ("milestone_types", "operation_stabilized"),
                ("milestone_types", "divestment"),
            ],
        )
        assert resp.status_code in (200, 303), (
            f"Timeline wizard: {resp.status_code} — {resp.text[:300]}"
        )

        # ── 2. Approve timeline ──────────────────────────────────────────────
        resp = client.post(f"/ui/projects/{project_id}/approve-timeline", data={})
        assert resp.status_code in (200, 303), (
            f"Approve timeline: {resp.status_code} — {resp.text[:300]}"
        )

        # ── 3. Deal setup wizard (steps 1–4) ─────────────────────────────────
        # Step 1: perm-only debt structure
        resp = client.post(
            f"/ui/models/{model_id}/setup/step",
            data={"step": "1", "debt_structure": "perm_only"},
        )
        assert resp.status_code in (200, 303), f"Setup step 1: {resp.status_code}"

        # Step 2: permanent loan terms
        resp = client.post(
            f"/ui/models/{model_id}/setup/step",
            data={"step": "2", "perm_rate_pct": "6.5", "perm_amort_years": "30"},
        )
        assert resp.status_code in (200, 303), f"Setup step 2: {resp.status_code}"

        # Step 3: gap-fill sizing, DSCR floor 1.25
        resp = client.post(
            f"/ui/models/{model_id}/setup/step",
            data={"step": "3", "debt_sizing_mode": "gap_fill", "dscr_minimum": "1.25"},
        )
        assert resp.status_code in (200, 303), f"Setup step 3: {resp.status_code}"

        # Step 4: reserves
        resp = client.post(
            f"/ui/models/{model_id}/setup/step",
            data={"step": "4", "construction_floor_pct": "0", "operation_reserve_months": "3"},
        )
        assert resp.status_code in (200, 303), f"Setup step 4: {resp.status_code}"

        # Complete wizard — returns 204 with HX-Redirect (not a 303)
        # setup/complete auto-seeds 19 OpEx lines at $0 and creates the debt CapitalModule
        resp = client.post(f"/ui/models/{model_id}/setup/complete", data={})
        assert resp.status_code in (200, 204, 303), (
            f"Setup complete: {resp.status_code} — {resp.text[:300]}"
        )

        # ── 4. Use lines ─────────────────────────────────────────────────────
        for use in [
            {
                "label": "Purchase Price",
                "milestone_key": "close",
                "amount": "800000",
                "timing_type": "first_day",
            },
            {
                "label": "Renovation",
                "milestone_key": "construction",
                "amount": "50000",
                "timing_type": "first_day",
            },
            # Note: setup/complete also creates a $0 "Operating Reserve" placeholder.
            # We add our own non-zero one here; the engine will use the non-zero value.
            {
                "label": "Closing Costs",
                "milestone_key": "close",
                "amount": "15000",
                "timing_type": "first_day",
            },
        ]:
            resp = client.post(f"/ui/forms/{model_id}/use-lines", data=use)
            assert resp.status_code in (200, 303), (
                f"Use line '{use['label']}': {resp.status_code}"
            )

        # ── 5. Income stream ─────────────────────────────────────────────────
        # 10 units × $1,200/unit/month × 95% occupancy = $136,800/yr gross EGI
        resp = client.post(
            f"/ui/forms/{model_id}/income-streams",
            data={
                "label": "Residential Rent",
                "stream_type": "residential_rent",
                "amount_type": "per_unit",
                "unit_count": "10",
                "amount_per_unit_monthly": "1200",
                "stabilized_occupancy_pct": "95",
                "escalation_rate_pct_annual": "3",
                "active_in_phases": "stabilized",
            },
        )
        assert resp.status_code in (200, 303), f"Income stream: {resp.status_code}"

        # ── 6. Expense lines ─────────────────────────────────────────────────
        # These are NEW lines on top of the 19 seeded $0 lines.
        # Using flat per_type so annual_amount is unambiguous.
        for expense in [
            {
                "label": "Property Management",
                "per_type": "flat",
                "per_value": "14400",
                "escalation_rate_pct_annual": "3",
                "active_in_phases": "stabilized",
            },
            {
                "label": "Insurance",
                "per_type": "flat",
                "per_value": "6000",
                "escalation_rate_pct_annual": "3",
                "active_in_phases": "stabilized",
            },
            {
                "label": "Property Tax",
                "per_type": "flat",
                "per_value": "9600",
                "escalation_rate_pct_annual": "2",
                "active_in_phases": "stabilized",
            },
        ]:
            resp = client.post(f"/ui/forms/{model_id}/expense-lines", data=expense)
            assert resp.status_code in (200, 303), (
                f"Expense line '{expense['label']}': {resp.status_code}"
            )

    # ── 7. Compute ────────────────────────────────────────────────────────────
    # /api/ paths are UI-path-exempt (no API key required, session cookie sufficient).
    with httpx.Client(base_url=base_url, follow_redirects=False, cookies=cookies) as client:
        resp = client.post(f"/api/models/{model_id}/compute")
    assert resp.status_code == 200, (
        f"Compute returned {resp.status_code}: {resp.text[:300]}"
    )

    return model_id, project_id
