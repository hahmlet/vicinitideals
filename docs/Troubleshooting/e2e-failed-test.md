# Failed E2E test — diagnostic runbook

Work through in order. Stop when the cause is found.

## 1. Read the assertion failure

- Exact assertion text + line number in pytest output
- Expected vs. actual value
- Which parametrized variant (browser, scenario name)

## 2. Check the browser console dump

Auto-captured in pytest output on failure.

- `[ERROR]` — JS exceptions, HTMX failures, network errors
- `[PAGE ERROR]` — uncaught exceptions that crashed the page
- `[WARNING]` — degraded behavior (missing elements, failed fetches)

## 3. Check the screenshot

Saved to `/tmp/e2e-fail-<test_name>.png` on the test runner.

- What did the page actually show when the assertion ran?
- Is the UI in the right state (correct URL, correct panel open)?

## 4. Check app logs for 5xx

```bash
mcp__proxmox-mcp__ssh_exec container_id=114 command="docker logs vicinitideals-api --tail 100 --since 10m"
```

- `500` → crash in route handler; stack trace here
- `422` → Pydantic validation failure; check request payload

## 5. Match error type to cause

| Symptom | Where to look |
|---|---|
| Element not found / timeout | Template changed — grep `app/templates/` for the selector |
| Wrong computed value | Engine unit tests in `tests/engines/`; run isolated |
| 500 on compute | `app/engines/cashflow.py` — check recent changes |
| HTMX swap didn't fire | Check `hx-target`, `hx-swap`, response Content-Type in logs |
| Auth redirect / 403 | Session stale — re-run `seed_e2e_user.py`, regenerate auth-state.json |
| Feature "broken" but endpoint is merely slow | `wait_for_htmx` swallows its own 8s timeout — assert on a value that cannot be true of the old DOM |

## 6. Reproduce in isolation before fixing

```powershell
$env:E2E_BASE_URL="https://viciniti.deals"
uv run pytest tests/e2e/<file>.py::<test_name> -v -s
```

`-s` disables capture so console dumps print immediately.

## Related guides

- [htmx-table-loading.md](htmx-table-loading.md) — opportunities page tables blank after deploy
- [settings-save-not-persisting.md](settings-save-not-persisting.md)
- [user-preferences-not-populating-deals.md](user-preferences-not-populating-deals.md)
