# Security Review & Remediation Plan — vicinitideals

## Context

Comprehensive security audit across auth, authorization, input validation, config, dependencies, templates, Excel export, and infrastructure. Three parallel exploration agents covered all major attack surfaces.

**2026-05-06 update:** Cloudflare proxy + Bot Fight Mode enabled after a spam bot attack (75 bogus registrations over 3 days to burn Resend quota). CF is now the outer perimeter. Security headers and `/register` rate limiting are offloaded to CF free tier; app-side work focuses on auth bugs and IDOR fixes only.

Owner-operated internal tool, single org/user, behind NGINX reverse proxy + Cloudflare. IDOR bugs are still exploitable by any authenticated session — they're not hypothetical.

---

## Cloudflare Free Tier — Do Here, Not in App

These are handled in the CF dashboard. No app code changes needed.

| Item | CF Feature | Notes |
|---|---|---|
| `X-Frame-Options: DENY` | Transform Rule → Modify Response Header | Uses 1 of 10 free rules |
| `X-Content-Type-Options: nosniff` | Transform Rule | Uses 1 of 10 free rules |
| `X-XSS-Protection: 1; mode=block` | Transform Rule | Uses 1 of 10 free rules |
| `Content-Security-Policy` (static) | Transform Rule | `default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'` |
| `Strict-Transport-Security` | SSL/TLS → Edge Certs → HSTS toggle | No rule needed |
| Rate limit `POST /register` | WAF Custom Rule → Rate Limit | 3 req / 10 min per IP; uses 1 of 5 free WAF rules |
| Bot protection on registration | Bot Fight Mode (already enabled) | Catches commodity bots; hCaptcha option if bots return |

**CF does NOT replace:** secure cookie flag, IDOR checks, XSS JS escaping, Excel formula sanitization, is_admin logic — those must be in app.

---

## Findings Severity Summary

### CRITICAL — Fix immediately (authentication bypass)

**C1. Unsigned `vd_user_id` legacy cookie — full authentication bypass**
- File: [app/api/routers/ui.py](app/api/routers/ui.py) — `_get_user()` lines 777–798
- Raw unsigned UUID cookie. Any user can forge `vd_user_id=<any-uuid>` and log in as anyone.
- Also set without `secure=True` or `httponly=True` (~line 1140)
- Fix: Remove legacy cookie path entirely — signed `vd_session` only; force re-login

---

### HIGH — Fix before any third-party access

**H1. Missing `secure=True` on ALL session cookies**
- File: [app/api/routers/auth_routes.py](app/api/routers/auth_routes.py) lines ~127, 239, 662
- Session tokens can transmit over plain HTTP (NGINX downtime, local dev)
- Fix: Add `secure=True` to every `resp.set_cookie(...)` call

**H2. IDOR — Capital stack: any authed user can read/modify any deal's capital**
- File: [app/api/routers/capital.py](app/api/routers/capital.py) lines 109–307
- `_get_deal_model_or_404()` (lines 66–69) fetches Scenario by UUID with zero org check
- All capital/waterfall endpoints lack `current_user_id` dependency entirely
- Fix: Inject `CurrentUserId`; after fetch traverse `scenario → deal → org_id`, compare to `user.org_id`

**H3. IDOR — Scenarios: results/compare/status endpoints unscoped**
- File: [app/api/routers/scenarios.py](app/api/routers/scenarios.py) lines 161–335
- GET endpoints for sensitivity results have no org validation
- POST creation checks Opportunity exists but not that caller's org owns it
- Fix: Add org ownership check after `session.get(Opportunity, project_id)`

**H4. IDOR — Deal JSON export: zero auth check**
- File: [app/api/routers/deals.py](app/api/routers/deals.py) lines 36–45
- `GET /deals/{deal_id}/export/json` — no `current_user_id`, no org check; any session exports any deal
- Fix: Add `CurrentUserId` dep; verify `deal.org_id == user.org_id`

**H5. IDOR — Deal detail/archive/update in UI routes**
- File: [app/api/routers/ui.py](app/api/routers/ui.py) lines 2108–2264
- `GET /deals/{deal_id}`, archive, update — fetch deal, never verify org ownership
- Fix: After `session.get(Deal, deal_id)`, assert ownership before returning/modifying

---

### MEDIUM — Fix within one sprint (app-side)

**M2. XSS — incomplete JavaScript escaping in templates**
- Files: [app/templates/model_builder.html](app/templates/model_builder.html) line 740, [app/templates/opportunity_detail.html](app/templates/opportunity_detail.html) line 48, [app/templates/parcel_detail.html](app/templates/parcel_detail.html) line 30; [app/api/routers/ui.py](app/api/routers/ui.py) line 10714
- Pattern: `{{ model.name | replace("'", "\\'") | safe }}` in JS onclick handlers
- Only escapes single quotes — misses `"`, backticks, backslash
- Fix: Replace with `json.dumps(value)` for all JS string injections

**M3. Excel formula injection — cell values not sanitized**
- File: [app/exporters/investor_export.py](app/exporters/investor_export.py) lines 443+
- `deal.name`, `scenario.name`, `project.name` written directly to cells; openpyxl does NOT escape `=`, `+`, `-`, `@`
- Fix: `def _safe_cell(v: str) -> str` — prefix with `'` if first char in `=+-@\t\r`; apply to all string cell writes

**M4. Hardcoded admin check by name string**
- File: [app/api/routers/ui.py](app/api/routers/ui.py) line ~806 — `user.name.strip().lower() == "stephen ketch"`
- Breaks if name changes; no audit trail
- Fix: Add `is_admin: bool = False` to `User` ORM + migration; `_require_settings_owner()` checks `user.is_admin`; seed flag for existing user

**M5. No rate limit on `POST /register` (app-side backup)**
- App has no server-side rate limit on registration — CF WAF rule is primary mitigation (see CF section above)
- Recommendation: Also add app-side Redis rate limit (3/hour per IP) as defense-in-depth behind CF
- Low urgency if CF WAF rule is in place

---

### LOW — Good-to-have

**L1. Bcrypt rounds not explicit**
- File: [app/api/auth.py](app/api/auth.py) line 39 — `bcrypt.gensalt()` no rounds param
- Fix: `bcrypt.gensalt(rounds=12)`

**L2. Soft email verification gate**
- Unverified users have full app access — registration spam creates valid-but-unverified accounts
- CF Bot Fight Mode is primary mitigation; acceptable risk for single-org tool
- If bots return: harden to hard gate on sensitive operations, or add hCaptcha to registration form

---

## Implementation Order

### Phase 0 — Cloudflare Dashboard (do first, no code)
1. Add 4 Transform Rules for security headers (X-Frame-Options, X-Content-Type-Options, X-XSS-Protection, CSP)
2. Enable HSTS in SSL/TLS → Edge Certificates
3. Add WAF Custom Rule: rate limit `POST /register` → 3 req/10 min per IP → Block

### Phase 1 — Critical + High (one PR)
4. Remove legacy `vd_user_id` cookie path from `_get_user()` (C1)
5. Add `secure=True` to all `set_cookie()` calls in auth_routes.py (H1)
6. Add `_assert_org_owner(obj_org_id, user_org_id)` helper raising 404; apply to capital.py, scenarios.py, deals.py, ui.py deal routes (H2–H5)

### Phase 2 — Medium (separate PR)
7. Fix JS escaping in templates + ui.py (M2)
8. Add `_safe_cell()` to investor_export.py (M3)
9. Add `is_admin` column + migration + update `_require_settings_owner()` (M4)
10. Optional: app-side Redis rate limit on `/register` (M5)

### Phase 3 — Low (cleanup)
11. Explicit bcrypt rounds (L1)

---

## Critical Files to Modify

| File | Changes |
|---|---|
| [app/api/routers/ui.py](app/api/routers/ui.py) | Remove legacy cookie path in `_get_user()`; org checks on deal routes; fix JS escaping |
| [app/api/routers/auth_routes.py](app/api/routers/auth_routes.py) | `secure=True` on all `set_cookie()` calls |
| [app/api/routers/capital.py](app/api/routers/capital.py) | `CurrentUserId` dep + org check in `_get_deal_model_or_404()` |
| [app/api/routers/scenarios.py](app/api/routers/scenarios.py) | Org ownership check after Opportunity fetch |
| [app/api/routers/deals.py](app/api/routers/deals.py) | `CurrentUserId` dep + org check on export endpoint |
| [app/exporters/investor_export.py](app/exporters/investor_export.py) | `_safe_cell()` helper; apply to all string cell writes |
| [app/models/](app/models/) | `is_admin: bool = False` on User ORM |
| [alembic/versions/](alembic/versions/) | Migration for `is_admin` column |
| [app/api/auth.py](app/api/auth.py) | Explicit bcrypt rounds |
| [app/templates/model_builder.html](app/templates/model_builder.html), [opportunity_detail.html](app/templates/opportunity_detail.html), [parcel_detail.html](app/templates/parcel_detail.html) | JS string escaping via `json.dumps` |

**Removed from app scope:** `app/api/main.py` security headers middleware → moved to CF Transform Rules.

## Existing Patterns to Reuse

- `CurrentUserId` dependency — already used in some capital endpoints
- `_get_user()` — returns `User` with `org_id`
- Raise `HTTPException(status_code=404)` for IDOR (404 not 403 — don't disclose existence)
- Alembic migration pattern — follow `alembic/versions/`

## Verification

After Phase 0 (CF):
1. `curl -I https://viciniti.deals` — verify `X-Frame-Options`, `X-Content-Type-Options`, `Strict-Transport-Security` present in response
2. In browser devtools: confirm HSTS header on all responses
3. Try registering 4 accounts rapidly from same IP — 4th should be blocked by CF WAF

After Phase 1:
4. `uv run pytest tests/ -q --ignore=tests/e2e` — all green
5. Attempt `GET /deals/{any-uuid}` while authenticated — expect 404 for non-owned deals
6. Attempt `GET /deals/{deal_id}/export/json` unauthenticated — expect 403
7. Browser devtools: session cookie has `Secure` flag
8. Browser devtools: `vd_user_id` cookie no longer set after login

After Phase 2:
9. Set deal name to `=1+1`, export Excel, open file — cell shows as text not formula
10. Check devtools: CSP header present

After Phase 3:
11. Full test suite green; deploy; smoke-check login + deal access
