"""E2E seed helpers — create minimal test fixtures via the live app's HTTP API.

Requires the app stack to be running (docker compose up) and at least one
Organization to exist in the DB (created by seed_demo_data or the wizard).

Usage:
    from tests.e2e.seed import create_e2e_scenario

    model_id = create_e2e_scenario(base_url, session_cookie)
    # Use model_id to navigate: /models/{model_id}/builder
"""

from __future__ import annotations

import json

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
