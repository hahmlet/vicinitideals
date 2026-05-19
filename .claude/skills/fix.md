---
name: Fix
description: Reproduce-first bug fix with automated verification loop. Use for any UI, engine, or API bug. Enforced by stop_verify.ps1 hook.
---

# /fix <bug description>

**Discipline**: reproduce the bug FIRST, then fix, then verify with a passing test.
Never claim a bug is fixed without a test that was red before and is green now.

---

## Loop (max 3 attempts, then escalate)

### Step 0 — Initialize

Write `.claude/state/fixloop.json`:
```json
{
  "active": true,
  "attempts": 0,
  "max_attempts": 3,
  "test_cmd": "",
  "bug": "<description from user>"
}
```

### Step 1 — Reproduce

Pick or write the narrowest test that exercises the bug:

| Bug type | Test approach |
|---|---|
| Engine / math | Unit test in `tests/engines/` |
| API response | Integration test in `tests/api/` |
| UI / HTMX behavior | Playwright E2E in `tests/e2e/` against `https://viciniti.deals` |

Run the test **before touching any code**. Expected outcome: **RED**.

- If test is **already green**: bug may already be fixed, or test is wrong. Report and stop (set `active: false`).
- If test can't run (broken environment, missing seed data, wrong URL): see bail-out conditions below.
- If test is red for the right reason: proceed to Step 2.

Set `test_cmd` in `fixloop.json` to the exact command (e.g., `uv run pytest tests/engines/test_cashflow.py::test_dscr_cap -xvs`).

For E2E tests, use:
```
uv run pytest tests/e2e/test_X.py::test_name -xvs --base-url https://viciniti.deals --auth tests/e2e/auth-state.json
```

### Step 2 — Root cause

Read the relevant code. Use `mcp__code-review-graph__traverse_graph_tool` or `mcp__code-review-graph__semantic_search_nodes_tool` to trace the execution path. Identify the exact line causing the failure — don't guess.

### Step 3 — Fix

Make the **minimal** code change. Don't refactor surrounding code or add unrelated improvements.

### Step 4 — Verify

Run the same test from Step 1. It must be **GREEN**.

The stop hook (`stop_verify.ps1`) runs `test_cmd` automatically on every stop. If it fails, you are blocked from stopping — go back to Step 2.

---

## Escalation (attempt 3 failed)

The stop hook will output the escalation block automatically. Your job: write the report below and stop.

```
ESCALATION REPORT
─────────────────────────────────────
Bug:        <user's description>
Test:       <test_cmd>
Attempts:   3

Hypothesis 1: <what you tried>
Result:       <what happened>

Hypothesis 2: <what you tried>
Result:       <what happened>

Hypothesis 3: <what you tried>
Result:       <what happened>

Current failure:
  <exact error from last test run>

Blocker:
  <what human decision/information is needed to proceed>

Stale test?: <yes/no — explain if yes>
─────────────────────────────────────
```

---

## Special cases

### Stale test
If the test fails because it's outdated (wrong assertion, old data shape, removed field) — not because of the bug:
1. Update the test.
2. Flag loudly: show the test diff in your next message with `> TEST UPDATED:` header.
3. Count this as **attempt 1** (updating a stale test is a real action, not a freebie).

### Missing seed data
If a required field has no seed value:
1. Use a labeled placeholder: `"__PLACEHOLDER_FIELD_NAME__"` for strings, `-9999` for numbers.
2. Report: `> PLACEHOLDER USED: field_name in table_name — math may be incorrect.`
3. Continue with the test — broken math is acceptable if flagged.

### Bail-out conditions
Set `active: false` and report. Do NOT consume attempts:
- Test is fundamentally wrong (wrong endpoint, wrong assertion logic)
- Bug requires a human design decision (ambiguous requirements)
- Environment is broken (stack not running, DB empty, auth expired)
- Bug description is incorrect after investigation
- Fix requires a database migration (flag this, propose the migration separately)

---

## Cleanup

When fix loop ends (passed or escalated):
- `fixloop.json` has `active: false` (hook auto-sets this)
- Commit the fix: `git add <changed files> && git commit -m "fix(...): ..."`
- Push and deploy per CLAUDE.md deploy workflow
- Report result to user: test name, before/after, commit SHA
