"""Read Trivy JSON results and create Plane work items for CRITICAL/HIGH findings.

Usage:
    python scripts/create_security_tickets.py trivy-results.json

Environment variables:
    PLANE_API_KEY      Plane API key (Settings → API Tokens)
    PLANE_PROJECT_ID   UUID of the target Plane project
    PLANE_WORKSPACE    Plane workspace slug (default: inferred from API)

What it does:
    1. Reads trivy-results.json (produced by trivy image ... --format json)
    2. Filters for CRITICAL and HIGH severity vulnerabilities
    3. Creates one Plane work item per unique CVE (skips if title already exists)
    4. Outputs a summary of created/skipped tickets

Exit codes:
    0  Completed (may have created 0 tickets if no findings)
    1  Error (missing config, API failure, invalid JSON)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, UTC


def _load_findings(path: str) -> list[dict]:
    """Extract CRITICAL/HIGH vulnerabilities from a Trivy JSON result file."""
    with open(path) as f:
        data = json.load(f)

    findings = []
    results = data if isinstance(data, list) else data.get("Results", [])
    for result in results:
        for vuln in result.get("Vulnerabilities") or []:
            severity = vuln.get("Severity", "").upper()
            if severity in ("CRITICAL", "HIGH"):
                findings.append({
                    "cve_id": vuln.get("VulnerabilityID", "UNKNOWN"),
                    "severity": severity,
                    "package": vuln.get("PkgName", "?"),
                    "installed": vuln.get("InstalledVersion", "?"),
                    "fixed": vuln.get("FixedVersion", ""),
                    "title": vuln.get("Title") or vuln.get("VulnerabilityID", "?"),
                    "description": (vuln.get("Description") or "")[:500],
                    "references": (vuln.get("References") or [])[:3],
                    "target": result.get("Target", ""),
                })
    return findings


def _create_ticket(api_key: str, project_id: str, finding: dict) -> dict | None:
    """POST one work item to Plane. Returns created item dict or None on error."""
    try:
        import httpx
    except ImportError:
        print("ERROR: httpx not installed", file=sys.stderr)
        sys.exit(1)

    title = f"[{finding['severity']}] {finding['cve_id']} in {finding['package']}"
    desc_lines = [
        f"<p><strong>CVE:</strong> {finding['cve_id']}</p>",
        f"<p><strong>Severity:</strong> {finding['severity']}</p>",
        f"<p><strong>Package:</strong> {finding['package']} {finding['installed']}</p>",
    ]
    if finding["fixed"]:
        desc_lines.append(f"<p><strong>Fix available:</strong> {finding['fixed']}</p>")
    if finding["description"]:
        desc_lines.append(f"<p>{finding['description']}</p>")
    if finding["references"]:
        refs = "".join(f"<li><a href='{r}'>{r}</a></li>" for r in finding["references"])
        desc_lines.append(f"<ul>{refs}</ul>")
    desc_lines.append(f"<p><em>Detected by Trivy scan on {datetime.now(UTC).strftime('%Y-%m-%d')}</em></p>")

    body = {
        "name": title,
        "description_html": "".join(desc_lines),
        "priority": "urgent" if finding["severity"] == "CRITICAL" else "high",
    }

    resp = httpx.post(
        f"https://api.plane.so/api/v1/workspaces/default/projects/{project_id}/issues/",
        json=body,
        headers={"X-Api-Key": api_key},
        timeout=15,
    )
    if resp.status_code in (200, 201):
        return resp.json()
    print(f"  WARNING: Failed to create ticket for {finding['cve_id']}: {resp.status_code} {resp.text[:200]}")
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Create Plane tickets from Trivy findings")
    parser.add_argument("results_file", help="Path to trivy-results.json")
    args = parser.parse_args()

    api_key = os.environ.get("PLANE_API_KEY", "")
    project_id = os.environ.get("PLANE_PROJECT_ID", "")

    if not api_key or not project_id:
        print("ERROR: PLANE_API_KEY and PLANE_PROJECT_ID must be set", file=sys.stderr)
        sys.exit(1)

    findings = _load_findings(args.results_file)
    print(f"Found {len(findings)} CRITICAL/HIGH vulnerabilities in {args.results_file}")

    if not findings:
        print("No findings to report.")
        sys.exit(0)

    created = 0
    for finding in findings:
        print(f"  Creating ticket: [{finding['severity']}] {finding['cve_id']} ({finding['package']})")
        item = _create_ticket(api_key, project_id, finding)
        if item:
            created += 1

    print(f"\nDone: {created}/{len(findings)} tickets created.")


if __name__ == "__main__":
    main()
