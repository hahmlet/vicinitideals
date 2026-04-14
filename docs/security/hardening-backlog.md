# Security Hardening Backlog (`REAL-45`)

_Date: 2026-04-03_

> **Triage only:** this work item documents the current hardening backlog and mitigation plan. It does **not** implement the controls below.

---

## Scope and evidence reviewed

This triage reviewed the current API surface, background-job intake, and deployment topology using:

- `vicinitideals/api/main.py`
- `vicinitideals/config.py`
- `vicinitideals/api/routers/ingest.py`
- `vicinitideals/api/routers/scenarios.py`
- `vicinitideals/tasks/celery_app.py`
- `vicinitideals/tasks/scraper.py`
- `vicinitideals/tasks/README.md`
- `docker-compose.yml`
- `README.md`
- `personalproxmox/documentation/MCP/mcp-security.md`

### Verified baseline

A fresh regression run was completed before documenting this backlog:

```bash
python -m pytest tests/ -v
```

Result: **`73 passed, 1 skipped in 23.59s`**.

### Important triage note

No live credentials were found committed in tracked `re-modeling/` files during this review. The main risk is the **current secret handling model** (plain environment variables + insecure fallback defaults), not a confirmed secret leak in git history from this pass.

---

## Severity scale

| Priority | Meaning |
| --- | --- |
| `P0` | Must harden before broader production exposure or multi-user rollout |
| `P1` | Next-sprint security work; should be completed before external usage expands |
| `P2` | Follow-on hardening and operational maturity work |

---

## Current positive controls already present

The review also confirmed several good defaults already in place:

- `FastAPI` is **internal-only** in `docker-compose.yml` and is not published directly to the host.
- `.env.example` explicitly instructs operators to **keep `.env` out of git**.
- `scenarios.py` already rejects invalid sweep variables and bad range inputs.
- Infra docs require **HTTPS via NGINX + Let's Encrypt** for externally exposed services.

These reduce exposure, but they do not fully close the gaps below.

---

## Prioritized backlog

| Priority | Area | Finding | Evidence | Risk |
| --- | --- | --- | --- | --- |
| `P0` | API auth / identity | API access is protected by a **single shared `X-API-Key`**, and `X-User-ID` is accepted from the client once the key matches. There is no per-user token, scope, or role boundary. | `vicinitideals/api/main.py` | Any caller with the shared key can act as any UUID-shaped user identity; no granular revocation or least privilege |
| `P0` | Secrets management | The app can fall back to placeholder defaults such as `changeme` / `changeme-generate-with-openssl-rand-hex-32`, and operational secrets are expected via plain env vars. | `vicinitideals/config.py`, `.env.example` | Accidental insecure deployment, secret sprawl, weak rotation discipline |
| `P1` | NGINX / TLS posture | TLS terminates on external NGINX Proxy Manager, but the app-specific proxy hardening is not captured here as a versioned checklist for HSTS, TLS policy, renewal checks, and admin access restriction. | `README.md`, `personalproxmox/documentation/MCP/mcp-security.md` | Config drift, incomplete TLS posture, weak operational verification |
| `P1` | Celery trigger hardening | `/ingest/trigger` allows authenticated clients to enqueue expensive jobs with only partial request shaping; `search_params` is still a free-form dict and no per-user quotas are visible. | `vicinitideals/api/routers/ingest.py`, `vicinitideals/tasks/celery_app.py` | Queue exhaustion, abuse-driven cost spikes, worker saturation |
| `P2` | Proxy credential handling | ProxyOn residential credentials are static username/password values stored in env and embedded into proxy URLs passed to the scrape payload. | `vicinitideals/tasks/README.md`, `vicinitideals/tasks/scraper.py` | Credential leakage through logs/debug output, long-lived secret exposure |
| `P2` | Auditability | Current controls do not provide strong security event logging by principal/scope/job provenance. | `vicinitideals/api/main.py`, task routing flow | Harder incident response and harder abuse attribution |

---

## Mitigation plans for `P0` / `P1` items

### `P0-1` Replace shared API key auth with scoped identity

**Confirmed issue**
- `vicinitideals/api/main.py` checks one shared `X-API-Key` value and then trusts a client-provided `X-User-ID` header.
- This is acceptable for local bootstrap work, but it is not strong enough for a real multi-user or internet-facing deployment.

**Mitigation plan**
1. **Immediate containment**
   - Stop treating `X-User-ID` as authoritative unless it is derived from a server-validated identity.
   - Restrict the shared key to internal-only use while the stronger auth model is built.
   - Introduce dual-key support and a documented rotation process so the current secret can be rolled without downtime.
2. **Near-term hardening**
   - Move to per-user or per-service credentials with explicit scopes (`read:projects`, `run:scenarios`, `trigger:ingest`, etc.).
   - Prefer `OIDC` / signed JWT claims or a service-account token model over a single global secret.
   - Add route-level authorization dependencies so high-cost task triggers require narrower permissions than read-only endpoints.
3. **Definition of done**
   - No shared global key for all callers.
   - No client-chosen user identity header used as the source of truth.
   - Revocation, rotation, and least-privilege scopes are documented and tested.

### `P0-2` Make secret bootstrapping fail closed

**Confirmed issue**
- `vicinitideals/config.py` still includes insecure fallback defaults for the database URL/password and API key.
- `.env.example` is fine as documentation, but the running application should not start successfully with placeholder values.

**Mitigation plan**
1. **Immediate containment**
   - Add startup validation that refuses to boot when secrets still match known placeholders (`changeme`, generated-example sentinel values, blank credentials where production requires them).
   - Inventory all runtime secrets used by `FastAPI`, `Celery`, Postgres, Redis, and ProxyOn.
2. **Near-term hardening**
   - Move sensitive values from plain compose env usage toward Docker secrets, mounted secret files, or a managed secret store.
   - Add secret scanning in CI and pre-commit for `.env`, tokens, and DSN patterns.
   - Define an operational rotation checklist for DB passwords, API keys, and ProxyOn credentials.
3. **Definition of done**
   - The app cannot start in production mode with placeholder credentials.
   - Runtime secrets are sourced from a non-git, rotation-friendly mechanism.
   - Secret scanning is automated.

### `P1-1` Version and verify the `deals.ketch.media` NGINX/TLS posture

**Confirmed issue**
- Infra docs show a solid baseline (`Let's Encrypt`, Force SSL, proxy header forwarding), but the re-modeling app does not yet have a repo-local hardening checklist tied to its public hostname.
- Because NGINX is managed in NPM UI, drift is possible unless the security posture is explicitly verified and recorded.

**Mitigation plan**
1. **Immediate containment**
   - Verify `Force SSL`, certificate renewal, websocket support, and upstream-only exposure for `deals.ketch.media`.
   - Confirm NPM admin access is restricted (VPN/Tailscale/IP allow-list) and not broadly public.
2. **Near-term hardening**
   - Add an app-specific TLS verification checklist covering: `TLS 1.2+ / 1.3`, `HSTS`, secure ciphers, redirect behavior, certificate expiry monitoring, and header hardening.
   - Record the expected NPM proxy-host configuration in versioned docs so future drift is detectable.
3. **Definition of done**
   - `deals.ketch.media` has a documented, repeatable security verification checklist and monitoring path.

### `P1-3` Harden Celery-triggering endpoints against abuse

**Confirmed issue**
- `ingest.py` limits `source` to known values, but `search_params` is still free-form and authenticated users can enqueue background work.
- There is no obvious quota, idempotency, or abuse guard at the API layer for job-trigger endpoints.

**Mitigation plan**
1. **Immediate containment**
   - Add payload-size caps and source-specific allow-lists for `search_params`.
   - Reject unknown keys rather than silently forwarding arbitrary dict content.
   - Cap job frequency per caller and add simple anti-flood throttling on trigger routes.
2. **Near-term hardening**
   - Require idempotency keys or dedupe logic for repeated ingest requests.
   - Separate scheduled internal jobs from user-triggered jobs for better queue isolation.
   - Add queue-depth monitoring and alerts for scraping/analysis backlog spikes.
3. **Definition of done**
   - Trigger routes are schema-constrained, rate-limited, and observable.
   - A single caller cannot trivially exhaust the scraping or analysis workers.

---

## `P2` follow-on items

### `P2-1` Remove long-lived proxy credentials from normal worker handling
- Replace static ProxyOn username/password handling with a more rotation-friendly secret path.
- Ensure proxy URLs are redacted from logs, exceptions, and debug payload dumps.

### `P2-2` Add security audit logging
- Record: authenticated principal, route, action, queued task id, source IP / proxy chain, and rate-limit events.
- Keep logs structured enough for incident response and abuse investigation.

---

## Recommended execution order

1. **Eliminate shared-auth impersonation risk** (`P0-1`)
2. **Fail closed on placeholder secrets and document rotation** (`P0-2`)
3. **Verify and record NGINX/TLS posture for `deals.ketch.media`** (`P1-1`)
5. **Constrain and rate-limit Celery-trigger endpoints** (`P1-3`)
6. Address credential redaction and audit logging follow-ons (`P2`)

---

## Open verification questions

These items were **not** fully verifiable from the repo alone and should be confirmed during implementation:

- Does `deals.ketch.media` already enforce `HSTS` and the desired TLS policy?
- Are VM-side `.env` files permissioned and rotated according to an operational checklist?
- Are background task trigger endpoints protected from repeated high-volume invocation at the proxy layer?

These questions do not block the backlog itself, but they should be resolved as part of the follow-on hardening work.