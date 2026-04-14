"""E2E seed helpers — create minimal test fixtures via the live app's HTTP API.

Requires the app stack to be running (docker compose up) and at least one
Organization to exist in the DB (created by seed_demo_data or the wizard).

Usage:
    from tests.e2e.seed import create_e2e_scenario

    model_id = create_e2e_scenario(base_url, api_key)
    # Use model_id to navigate: /models/{model_id}/builder
"""

from __future__ import annotations

import httpx


def create_e2e_scenario(
    base_url: str,
    api_key: str,
    *,
    deal_name: str = "E2E Test Deal",
    deal_type: str = "acquisition_minor_reno",
) -> str:
    """POST /ui/deals/create and return the scenario (model) UUID.

    The create endpoint redirects to /models/{model_id}/builder on success.
    Returns the model_id UUID string.
    Raises AssertionError if creation fails.
    """
    with httpx.Client(base_url=base_url, follow_redirects=False) as client:
        resp = client.post(
            "/ui/deals/create",
            data={"name": deal_name, "deal_type": deal_type},
            headers={"X-API-Key": api_key},
        )

    if resp.status_code == 303:
        location = resp.headers.get("location", "")
        # Location: /models/{model_id}/builder or /models/{model_id}/builder?new=1
        # Parse out the model_id segment between /models/ and /builder
        parts = location.split("/models/", 1)
        assert len(parts) == 2, f"Unexpected redirect location: {location!r}"
        model_id = parts[1].split("/")[0].split("?")[0]
        assert model_id, f"Could not parse model_id from redirect: {location!r}"
        return model_id

    raise AssertionError(
        f"Deal creation expected 303 redirect, got {resp.status_code}: "
        f"{resp.text[:300]}"
    )
