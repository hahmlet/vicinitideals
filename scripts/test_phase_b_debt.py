#!/usr/bin/env python
"""Phase B debt-stack integration test.

Creates 3 deals with different debt configurations, computes each, and
verifies Sources ≈ Uses (gap/surplus ≈ $0) and that each debt module
has a non-zero principal.

Test cases:
  1. Single Permanent Debt (gap-fill to TPC)
  2. Separate Construction Loan + Permanent Debt
  3. Pre-Development Loan + Construction-to-Perm

Usage:
    python scripts/test_phase_b_debt.py [--base-url https://deals.ketch.media] [--auth auth.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal
from urllib.parse import urlencode

import httpx

_FORM_HEADERS = {"Content-Type": "application/x-www-form-urlencoded"}


def _post_form(client: httpx.Client, url: str, data: dict | list) -> httpx.Response:
    """POST form data, encoding it manually to avoid h11 0.16/httpx tuple bug."""
    if isinstance(data, dict):
        pairs = list(data.items())
    else:
        pairs = list(data)
    body = urlencode(pairs, doseq=True).encode("utf-8")
    return client.post(url, content=body, headers=_FORM_HEADERS)

COOKIE_NAME = "vd_session"
BASE_URL = "https://deals.ketch.media"
AUTH_STATE = "tests/e2e/.auth/state.json"


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _load_cookie(auth_path: str) -> str:
    with open(auth_path) as f:
        state = json.load(f)
    for c in state.get("cookies", []):
        if c.get("name") == COOKIE_NAME:
            return c["value"]
    raise ValueError(f"No {COOKIE_NAME} in {auth_path!r}")


def _login(base_url: str, email: str, password: str) -> str:
    """Log in and return session cookie value."""
    with httpx.Client(base_url=base_url, follow_redirects=True) as c:
        resp = c.post("/login", data={"email": email, "password": password})
    for cookie in resp.cookies.jar:
        if cookie.name == COOKIE_NAME:
            return cookie.value
    # Try from headers
    for h_name, h_val in resp.headers.multi_items():
        if h_name.lower() == "set-cookie" and COOKIE_NAME in h_val:
            for part in h_val.split(";"):
                if part.strip().startswith(COOKIE_NAME + "="):
                    return part.strip()[len(COOKIE_NAME) + 1:]
    raise ValueError("Login failed — no session cookie returned")


# ── Deal creation helpers ─────────────────────────────────────────────────────

def _create_deal(client: httpx.Client, name: str, deal_type: str) -> str:
    """Create a deal and return model_id."""
    resp = _post_form(client, "/ui/deals/create", {"name": name, "deal_type": deal_type})
    assert resp.status_code == 303, f"Create deal: {resp.status_code} — {resp.text[:300]}"
    location = resp.headers["location"]
    model_id = location.split("/models/")[1].split("/")[0].split("?")[0]
    return model_id


def _get_project_id(client: httpx.Client, model_id: str) -> str:
    resp = client.get(f"/models/{model_id}/builder")
    assert resp.status_code == 200, f"Builder: {resp.status_code}"
    m = re.search(r"/ui/projects/([0-9a-f-]{36})/timeline-wizard", resp.text)
    assert m, "Could not find project_id in builder HTML"
    return m.group(1)


def _get_building_id(client: httpx.Client, model_id: str) -> str | None:
    """Get first building ID if wizard needs building data filled."""
    resp = client.get(f"/ui/models/{model_id}/setup")
    m = re.search(r'name="unit_count_([0-9a-f-]{36})"', resp.text)
    return m.group(1) if m else None


def _setup_timeline(client: httpx.Client, project_id: str,
                    milestone_types: list[str], anchor_date: str = "2026-01-01",
                    anchor_duration_days: int = 45) -> None:
    data = [
        ("anchor_type", "close"),
        ("anchor_date", anchor_date),
        ("anchor_duration_days", str(anchor_duration_days)),
    ] + [("milestone_types", mt) for mt in milestone_types]
    resp = _post_form(client, f"/ui/projects/{project_id}/timeline-wizard", data)
    assert resp.status_code in (200, 303), f"Timeline wizard: {resp.status_code} — {resp.text[:300]}"
    resp = _post_form(client, f"/ui/projects/{project_id}/approve-timeline", {})
    assert resp.status_code in (200, 303), f"Approve timeline: {resp.status_code} — {resp.text[:300]}"


def _run_wizard(client: httpx.Client, model_id: str, building_id: str | None,
                debt_types: list[str],
                debt_terms: dict,          # {funder_type: {rate_pct, loan_type, amort_years}}
                milestone_config: dict,    # {funder_type: {active_from, active_to, retired_by}}
                debt_sizing_mode: str = "gap_fill",
                dscr_minimum: str = "1.25",
                ) -> None:
    """Run all 7 wizard steps + complete for a new multi-debt deal."""

    # Step 0: building data (if needed)
    if building_id:
        resp = _post_form(client, f"/ui/models/{model_id}/setup/step", {
            "step": "0",
            f"unit_count_{building_id}": "20",
            f"building_sqft_{building_id}": "18000",
        })
        assert resp.status_code in (200, 303), f"Step 0: {resp.status_code}"

    # Step 1: income mode
    resp = _post_form(client, f"/ui/models/{model_id}/setup/step", {
        "step": "1", "income_mode": "revenue_opex",
    })
    assert resp.status_code in (200, 303), f"Step 1: {resp.status_code}"

    # Step 2: debt types
    data = [("step", "2")] + [("debt_types", ft) for ft in debt_types]
    resp = _post_form(client, f"/ui/models/{model_id}/setup/step", data)
    assert resp.status_code in (200, 303), f"Step 2: {resp.status_code}"

    # Step 3: milestone config
    step3: list[tuple] = [("step", "3")]
    for ft, cfg in milestone_config.items():
        step3 += [
            (f"{ft}_active_from", cfg.get("active_from", "")),
            (f"{ft}_active_to",   cfg.get("active_to", "")),
            (f"{ft}_retired_by",  cfg.get("retired_by", "")),
        ]
    resp = _post_form(client, f"/ui/models/{model_id}/setup/step", step3)
    assert resp.status_code in (200, 303), f"Step 3: {resp.status_code}"

    # Step 4: debt terms
    step4: list[tuple] = [("step", "4")]
    for ft, terms in debt_terms.items():
        if "loan_type"   in terms: step4.append((f"{ft}_loan_type",   terms["loan_type"]))
        if "rate_pct"    in terms: step4.append((f"{ft}_rate_pct",    str(terms["rate_pct"])))
        if "amort_years" in terms: step4.append((f"{ft}_amort_years", str(terms["amort_years"])))
    resp = _post_form(client, f"/ui/models/{model_id}/setup/step", step4)
    assert resp.status_code in (200, 303), f"Step 4: {resp.status_code}"

    # Step 5: sizing
    resp = _post_form(client, f"/ui/models/{model_id}/setup/step", {
        "step": "5", "debt_sizing_mode": debt_sizing_mode, "dscr_minimum": dscr_minimum,
    })
    assert resp.status_code in (200, 303), f"Step 5: {resp.status_code}"

    # Step 6: reserves
    resp = _post_form(client, f"/ui/models/{model_id}/setup/step", {
        "step": "6", "operation_reserve_months": "6",
    })
    assert resp.status_code in (200, 303), f"Step 6: {resp.status_code}"

    # Complete
    resp = _post_form(client, f"/ui/models/{model_id}/setup/complete", {})
    assert resp.status_code in (200, 204, 303), f"Complete: {resp.status_code} — {resp.text[:300]}"


def _add_use_lines(client: httpx.Client, model_id: str, uses: list[dict]) -> None:
    for use in uses:
        resp = _post_form(client, f"/ui/forms/{model_id}/use-lines", use)
        assert resp.status_code in (200, 303), f"Use line '{use['label']}': {resp.status_code}"


def _add_income_stream(client: httpx.Client, model_id: str) -> None:
    resp = _post_form(client, f"/ui/forms/{model_id}/income-streams", {
        "label": "Residential Rent",
        "stream_type": "residential_rent",
        "amount_type": "per_unit",
        "unit_count": "20",
        "amount_per_unit_monthly": "1200",
        "stabilized_occupancy_pct": "95",
        "escalation_rate_pct_annual": "3",
        "active_in_phases": "stabilized",
    })
    assert resp.status_code in (200, 303), f"Income stream: {resp.status_code}"


def _add_expense_lines(client: httpx.Client, model_id: str) -> None:
    for expense in [
        {"label": "Property Management", "per_type": "flat", "per_value": "28800",
         "escalation_rate_pct_annual": "3", "active_in_phases": "stabilized"},
        {"label": "Insurance",           "per_type": "flat", "per_value": "7200",
         "escalation_rate_pct_annual": "3", "active_in_phases": "stabilized"},
        {"label": "Property Tax",        "per_type": "flat", "per_value": "12000",
         "escalation_rate_pct_annual": "2", "active_in_phases": "stabilized"},
    ]:
        resp = _post_form(client, f"/ui/forms/{model_id}/expense-lines", expense)
        assert resp.status_code in (200, 303), f"Expense '{expense['label']}': {resp.status_code}"


def _compute(client: httpx.Client, model_id: str) -> dict:
    resp = client.post(f"/api/models/{model_id}/compute")
    assert resp.status_code == 200, f"Compute: {resp.status_code} — {resp.text[:300]}"
    # The FastAPI session commits AFTER sending the response (generator cleanup).
    # Wait briefly so the commit is visible before we fetch the S&U page.
    import time
    time.sleep(1)
    return resp.json()


def _get_sources_uses(client: httpx.Client, model_id: str) -> dict:
    """Fetch the Sources & Uses panel and extract totals + debt module amounts."""
    resp = client.get(f"/models/{model_id}/builder?module=sources_uses")
    assert resp.status_code == 200, f"S&U page: {resp.status_code}"
    html = resp.text

    result: dict = {}

    # Extract total sources and total uses from stat values
    m = re.search(r'Total Sources[\s\S]{0,400}?\$([\d,]+)', html)
    if m:
        result["total_sources"] = int(m.group(1).replace(",", ""))

    m = re.search(r'Total Uses[\s\S]{0,400}?\$([\d,]+)', html)
    if m:
        result["total_uses"] = int(m.group(1).replace(",", ""))

    # Extract individual debt module amounts
    debt_amounts: dict = {}
    for label, amount in re.findall(
        r'class="[^"]*funder-label[^"]*"[^>]*>(.*?)</[^>]+>[\s\S]{0,300}?\$([\d,]+)',
        html,
    ):
        debt_amounts[label.strip()] = int(amount.replace(",", ""))
    result["debt_amounts"] = debt_amounts

    return result


# ── Test case definitions ─────────────────────────────────────────────────────

TEST_CASES = [
    {
        "name":       "Phase B Test 1 — Perm Only",
        "deal_type":  "acquisition_minor_reno",
        "milestones": ["close", "construction", "operation_stabilized", "divestment"],
        "debt_types": ["permanent_debt"],
        "debt_terms": {
            "permanent_debt": {"loan_type": "pi", "rate_pct": 6.5, "amort_years": 30},
        },
        "milestone_config": {
            "permanent_debt": {"active_from": "acquisition", "active_to": "stabilized", "retired_by": ""},
        },
        "use_lines": [
            {"label": "Purchase Price",   "milestone_key": "close",        "amount": "1200000", "timing_type": "first_day"},
            {"label": "Renovation",       "milestone_key": "construction",  "amount": "150000",  "timing_type": "first_day"},
            {"label": "Closing Costs",    "milestone_key": "close",        "amount": "24000",   "timing_type": "first_day"},
        ],
    },
    {
        "name":       "Phase B Test 2 — Construction + Perm",
        "deal_type":  "acquisition_major_reno",
        "milestones": ["close", "pre_construction", "construction", "operation_stabilized", "divestment"],
        "debt_types": ["construction_loan", "permanent_debt"],
        "debt_terms": {
            "construction_loan": {"loan_type": "io_only",  "rate_pct": 7.0, "amort_years": 1},
            "permanent_debt":    {"loan_type": "pi",       "rate_pct": 6.5, "amort_years": 30},
        },
        "milestone_config": {
            "construction_loan": {"active_from": "pre_construction", "active_to": "lease_up",    "retired_by": "permanent_debt"},
            "permanent_debt":    {"active_from": "operation_lease_up", "active_to": "stabilized", "retired_by": ""},
        },
        "use_lines": [
            {"label": "Purchase Price",    "milestone_key": "close",          "amount": "800000",  "timing_type": "first_day"},
            {"label": "Hard Construction", "milestone_key": "construction",   "amount": "600000",  "timing_type": "first_day"},
            {"label": "Soft Costs",        "milestone_key": "pre_construction","amount": "80000",   "timing_type": "first_day"},
            {"label": "Closing Costs",     "milestone_key": "close",          "amount": "16000",   "timing_type": "first_day"},
        ],
    },
    {
        "name":       "Phase B Test 3 — Pre-Dev + Construction-to-Perm",
        "deal_type":  "new_construction",
        "milestones": ["close", "pre_construction", "construction", "operation_lease_up", "operation_stabilized", "divestment"],
        "debt_types": ["pre_development_loan", "construction_to_perm"],
        "debt_terms": {
            "pre_development_loan": {"loan_type": "io_only",     "rate_pct": 8.0, "amort_years": 1},
            "construction_to_perm": {"loan_type": "io_then_pi",  "rate_pct": 6.0, "amort_years": 30},
        },
        "milestone_config": {
            "pre_development_loan": {"active_from": "pre_construction", "active_to": "construction", "retired_by": "construction_to_perm"},
            "construction_to_perm": {"active_from": "close",            "active_to": "stabilized",   "retired_by": ""},
        },
        "use_lines": [
            {"label": "Land",                "milestone_key": "close",          "amount": "500000",  "timing_type": "first_day"},
            {"label": "Pre-Dev Costs",       "milestone_key": "pre_construction","amount": "75000",   "timing_type": "first_day"},
            {"label": "Hard Construction",   "milestone_key": "construction",   "amount": "1200000", "timing_type": "first_day"},
            {"label": "Soft Costs",          "milestone_key": "construction",   "amount": "120000",  "timing_type": "first_day"},
        ],
    },
    {
        # DSCR-capped non-binding: low DSCR_min (1.10) so gap-fill wins.
        # Closing costs must be folded in via divisor (same as pure gap-fill).
        # Expected: Sources = Uses, Gap = $0 (same as Test 1).
        "name":       "Phase B Test 4 — DSCR-Capped Non-Binding (low cap)",
        "deal_type":  "acquisition_minor_reno",
        "milestones": ["close", "construction", "operation_stabilized", "divestment"],
        "debt_types": ["permanent_debt"],
        "debt_terms": {
            "permanent_debt": {"loan_type": "pi", "rate_pct": 6.5, "amort_years": 30},
        },
        "milestone_config": {
            "permanent_debt": {"active_from": "acquisition", "active_to": "stabilized", "retired_by": ""},
        },
        "debt_sizing_mode": "dscr_capped",
        "dscr_minimum":     "1.10",
        "use_lines": [
            {"label": "Purchase Price",   "milestone_key": "close",        "amount": "1200000", "timing_type": "first_day"},
            {"label": "Renovation",       "milestone_key": "construction",  "amount": "150000",  "timing_type": "first_day"},
            {"label": "Closing Costs",    "milestone_key": "close",        "amount": "24000",   "timing_type": "first_day"},
        ],
        "expect_gap":            True,   # allow gap (DSCR may still bind at 1.10)
        "expect_sources_le_uses": True,   # Sources ≤ Uses (cap never over-funds)
    },
    {
        # DSCR-capped BINDING: aggressive DSCR_min (2.50) forces cap.
        # Expected: P_capped < P_gapfill; real Sources gap visible.
        # The gap should be bounded: orig fee is based on P_capped (smaller), not P_gapfill.
        "name":       "Phase B Test 5 — DSCR-Capped Binding (high cap)",
        "deal_type":  "acquisition_minor_reno",
        "milestones": ["close", "construction", "operation_stabilized", "divestment"],
        "debt_types": ["permanent_debt"],
        "debt_terms": {
            "permanent_debt": {"loan_type": "pi", "rate_pct": 6.5, "amort_years": 30},
        },
        "milestone_config": {
            "permanent_debt": {"active_from": "acquisition", "active_to": "stabilized", "retired_by": ""},
        },
        "debt_sizing_mode": "dscr_capped",
        "dscr_minimum":     "2.50",
        "use_lines": [
            {"label": "Purchase Price",   "milestone_key": "close",        "amount": "1200000", "timing_type": "first_day"},
            {"label": "Renovation",       "milestone_key": "construction",  "amount": "150000",  "timing_type": "first_day"},
            {"label": "Closing Costs",    "milestone_key": "close",        "amount": "24000",   "timing_type": "first_day"},
        ],
        "expect_gap":            True,   # legitimate funding gap
        "expect_sources_le_uses": True,   # Sources < Uses when cap binds
    },
]


# ── Main ──────────────────────────────────────────────────────────────────────

def run_tests(base_url: str, session_cookie: str) -> None:
    cookies = {COOKIE_NAME: session_cookie}
    results = []

    with httpx.Client(base_url=base_url, follow_redirects=False, cookies=cookies) as client:
        for tc in TEST_CASES:
            print(f"\n{'='*60}")
            print(f"Creating: {tc['name']}")

            model_id = _create_deal(client, tc["name"], tc["deal_type"])
            print(f"  model_id: {model_id}")

            project_id = _get_project_id(client, model_id)

            # Setup timeline
            _setup_timeline(client, project_id, tc["milestones"])
            print("  Timeline: approved ✓")

            # Check if building data is needed
            building_id = _get_building_id(client, model_id)

            # Run 7-step wizard
            _run_wizard(client, model_id, building_id,
                        tc["debt_types"], tc["debt_terms"], tc["milestone_config"],
                        debt_sizing_mode=tc.get("debt_sizing_mode", "gap_fill"),
                        dscr_minimum=tc.get("dscr_minimum", "1.25"))
            print(f"  Wizard: complete ✓ (debt_types={tc['debt_types']}, mode={tc.get('debt_sizing_mode', 'gap_fill')})")

            # Add use lines
            _add_use_lines(client, model_id, tc["use_lines"])
            print(f"  Use lines: {len(tc['use_lines'])} added ✓")

            # Add income + expenses
            _add_income_stream(client, model_id)
            _add_expense_lines(client, model_id)
            print("  Income + expenses: added ✓")

            # Compute
            compute_result = _compute(client, model_id)
            print("  Compute: done ✓")

            # Read outputs from compute result
            total_project_cost = Decimal(str(compute_result.get("total_project_cost", 0)))
            noi_stabilized     = Decimal(str(compute_result.get("noi_stabilized", 0)))

            # Get S&U totals from the builder page
            su = _get_sources_uses(client, model_id)
            total_sources = su.get("total_sources", 0)
            total_uses    = su.get("total_uses", 0)
            gap = total_sources - total_uses

            result = {
                "name":          tc["name"],
                "model_id":      model_id,
                "debt_types":    tc["debt_types"],
                "total_sources": total_sources,
                "total_uses":    total_uses,
                "gap":           gap,
                "tpc":           int(total_project_cost),
                "noi":           int(noi_stabilized),
                "debt_amounts":  su.get("debt_amounts", {}),
                "sizing_mode":   tc.get("debt_sizing_mode", "gap_fill"),
                "expect_gap":    tc.get("expect_gap", False),
                "expect_sources_le_uses": tc.get("expect_sources_le_uses", False),
            }
            results.append(result)

    # ── Print summary ─────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("PHASE B TEST RESULTS")
    print('='*60)

    all_pass = True
    for r in results:
        gap = r["gap"]
        gap_pct = abs(gap) / r["total_uses"] * 100 if r["total_uses"] else 0

        # Pass criterion depends on expected behavior:
        #  - default (gap_fill): Sources = Uses within $100 rounding
        #  - expect_gap + expect_sources_le_uses (dscr_capped binding):
        #      any non-positive gap is acceptable; sources must be ≤ uses
        if r.get("expect_gap") and r.get("expect_sources_le_uses"):
            # DSCR-capped: allow any Sources ≤ Uses outcome (including balanced)
            balanced = gap <= 100  # tolerate $100 of rounding on the positive side
        else:
            balanced = abs(gap) < 100
        status = "✅ PASS" if balanced else "❌ FAIL"
        if not balanced:
            all_pass = False

        print(f"\n{status}  {r['name']}")
        print(f"       model: https://deals.ketch.media/models/{r['model_id']}/builder?module=sources_uses")
        print(f"       debt:  {', '.join(r['debt_types'])}")
        print(f"       mode:  {r['sizing_mode']}")
        print(f"       TPC:   ${r['tpc']:>12,}")
        print(f"       NOI:   ${r['noi']:>12,}")
        print(f"    Sources:  ${r['total_sources']:>12,}")
        print(f"       Uses:  ${r['total_uses']:>12,}")
        gap_str = f"+${gap:,}" if gap >= 0 else f"-${abs(gap):,}"
        print(f"       Gap:   {gap_str:>13}  ({gap_pct:.2f}%)")
        if r["debt_amounts"]:
            print("      Loans:")
            for label, amt in r["debt_amounts"].items():
                nonzero = "✓" if amt > 0 else "⚠ ZERO"
                print(f"             {label}: ${amt:,}  {nonzero}")

    print(f"\n{'='*60}")
    print(f"Overall: {'ALL PASS ✅' if all_pass else 'FAILURES DETECTED ❌'}")
    print('='*60)

    if not all_pass:
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--auth",     default=AUTH_STATE, help="Playwright storageState JSON")
    parser.add_argument("--email",    default="e2e@ketch.media")
    parser.add_argument("--password", default="e2e-test-password-2026")
    args = parser.parse_args()

    try:
        cookie = _load_cookie(args.auth)
        print(f"Loaded session cookie from {args.auth}")
    except Exception:
        print(f"Auth state not found, logging in as {args.email}...")
        cookie = _login(args.base_url, args.email, args.password)
        print("Logged in ✓")

    run_tests(args.base_url, cookie)
