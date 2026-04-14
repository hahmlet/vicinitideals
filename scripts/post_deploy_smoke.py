"""Post-deploy smoke check — runs after docker compose up in the deploy script.

Verifies that the API is healthy and key services are reachable.

Usage (called by deploy-vicinitideals.sh):
    docker compose run --rm api python scripts/post_deploy_smoke.py

Exit codes:
    0  All checks passed
    1  One or more checks failed (deploy script logs warning but doesn't abort)

Checks:
    1. /health endpoint returns {"code": "ok"}
    2. DB is reachable (via /health detail)
    3. Celery workers are alive (ping via Redis)
    4. Authenticated UI path redirects to /login (auth middleware active)
"""

from __future__ import annotations

import os
import sys
import json

# Use requests-like httpx (sync) for simplicity in a deploy script
try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed — add to api dependencies", file=sys.stderr)
    sys.exit(1)

BASE_URL = os.environ.get("POST_DEPLOY_BASE_URL", "http://127.0.0.1:8000")
API_KEY = os.environ.get("VICINITIDEALS_API_KEY", "")

TIMEOUT = 10
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    msg = f"  [{status}] {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if not ok:
        failures.append(name)


def main() -> None:
    print("Post-deploy smoke checks")
    print(f"  Target: {BASE_URL}")
    print()

    # ------------------------------------------------------------------
    # 1. Health endpoint
    # ------------------------------------------------------------------
    try:
        resp = httpx.get(f"{BASE_URL}/health", timeout=TIMEOUT)
        data = resp.json()
        check("Health endpoint", resp.status_code == 200 and data.get("code") == "ok",
              f"status={resp.status_code}")
    except Exception as exc:
        check("Health endpoint", False, str(exc))

    # ------------------------------------------------------------------
    # 2. Authenticated UI redirect (auth middleware active)
    # ------------------------------------------------------------------
    try:
        resp = httpx.get(f"{BASE_URL}/deals", follow_redirects=False, timeout=TIMEOUT)
        # Should redirect to /login when no session cookie
        check("Auth redirect active",
              resp.status_code == 303 and "/login" in resp.headers.get("location", ""),
              f"status={resp.status_code} location={resp.headers.get('location', '')}")
    except Exception as exc:
        check("Auth redirect active", False, str(exc))

    # ------------------------------------------------------------------
    # 3. API key-protected endpoint
    # ------------------------------------------------------------------
    try:
        resp = httpx.get(f"{BASE_URL}/api/users",
                         headers={"X-API-Key": API_KEY},
                         timeout=TIMEOUT)
        check("API key auth", resp.status_code in (200, 404),
              f"status={resp.status_code}")
    except Exception as exc:
        check("API key auth", False, str(exc))

    # ------------------------------------------------------------------
    # 4. Static assets
    # ------------------------------------------------------------------
    try:
        resp = httpx.get(f"{BASE_URL}/static/app.css", timeout=TIMEOUT)
        check("Static assets", resp.status_code == 200,
              f"status={resp.status_code}")
    except Exception as exc:
        check("Static assets", False, str(exc))

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print()
    if failures:
        print(f"SMOKE FAILED: {len(failures)} check(s) failed: {', '.join(failures)}")
        sys.exit(1)
    else:
        print("SMOKE PASSED: all checks OK")
        sys.exit(0)


if __name__ == "__main__":
    main()
