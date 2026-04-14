"""Query BugSink for recent errors and return a JSON summary.

Agent-callable script for checking the health of the running app.

Usage:
    python -m app.scripts.check_bugsink_errors [--since 1h] [--level error]
    python -m app.scripts.check_bugsink_errors --since 24h --level warning

Environment variables (or .env):
    BUGSINK_API_URL    Base URL of your BugSink instance (e.g. https://bugsink.ketch.media)
    BUGSINK_API_TOKEN  BugSink API token (Settings → API Tokens)

Output (stdout, JSON):
    {
      "status": "ok" | "errors_found" | "unavailable",
      "since": "1h",
      "error_count": 3,
      "issues": [...],
      "checked_at": "2026-04-14T06:00:00Z"
    }

Exit codes:
    0  No errors (or monitoring unavailable)
    1  Errors found above threshold
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime, timedelta

_SINCE_MAP = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "12h": timedelta(hours=12),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}


def _parse_since(value: str) -> timedelta:
    if value in _SINCE_MAP:
        return _SINCE_MAP[value]
    raise argparse.ArgumentTypeError(f"Invalid --since value: {value!r}. Choose from {list(_SINCE_MAP)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check BugSink for recent errors")
    parser.add_argument("--since", default="1h", type=_parse_since, help="Time window (1h, 6h, 12h, 24h, 7d)")
    parser.add_argument("--level", default="error", choices=["debug", "info", "warning", "error", "fatal"])
    args = parser.parse_args()

    api_url = os.environ.get("BUGSINK_API_URL") or os.environ.get("SENTRY_DSN", "").split("@")[0]
    api_token = os.environ.get("BUGSINK_API_TOKEN", "")
    now = datetime.now(UTC)
    since_dt = now - args.since

    result: dict = {
        "status": "unavailable",
        "since": str(args.since),
        "level": args.level,
        "error_count": 0,
        "issues": [],
        "checked_at": now.isoformat(),
    }

    if not api_url or not api_token:
        result["message"] = "BUGSINK_API_URL or BUGSINK_API_TOKEN not set"
        print(json.dumps(result, indent=2))
        sys.exit(0)

    try:
        import httpx

        # BugSink REST API — compatible with Sentry API v0 endpoints
        resp = httpx.get(
            f"{api_url.rstrip('/')}/api/0/issues/",
            params={
                "level": args.level,
                "firstSeen": since_dt.isoformat(),
                "limit": 25,
            },
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=10,
        )
        resp.raise_for_status()
        issues = resp.json()

        result["status"] = "errors_found" if issues else "ok"
        result["error_count"] = len(issues)
        result["issues"] = [
            {
                "id": issue.get("id"),
                "title": issue.get("title"),
                "level": issue.get("level"),
                "count": issue.get("count"),
                "firstSeen": issue.get("firstSeen"),
                "lastSeen": issue.get("lastSeen"),
            }
            for issue in issues[:10]
        ]

    except Exception as exc:
        result["status"] = "unavailable"
        result["message"] = str(exc)

    print(json.dumps(result, indent=2))
    sys.exit(1 if result["status"] == "errors_found" else 0)


if __name__ == "__main__":
    main()
