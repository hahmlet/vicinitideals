# 217. Spend the monthly Claude API credit in three tiers (Steph 2026-11-27: $200/month now, this month's expires ~2026-11-30)

217. [Claude] [Steph: API key] [scan: NO (nothing written reaches a rule or an answer without the normal lane)]
   **Spend the monthly API credit in three tiers, never over the credit.** Steph 2026-11-27:
   the credit is now $200/month (item 54 assumed $100), this month's expires in 3 days, and
   nothing built for 54/55 was live (no code, no ANTHROPIC key in VM 114 .env -- checked).

   Steph's picks 2026-11-27 (strongest model, claude-opus-5-5, for everything):
   1. **Sure thing -- code-change check (item 54 core).** Free sweep first
      (`fetch --all --check`, started 11-27, log in gitignored data/flats/credit/); only
      documents whose cited lines changed are read by the model: unchanged / changed (new
      number) / removed / cannot_tell with a verbatim quote. Findings -> agent work list.
   2. **Maybe -- "do we have everything?"** Three completeness questions per encoded place,
      most greens first: (a) an overlay / special district / plan district the code or maps
      name that we have not read; (b) a cross-reference inside the code we have not
      followed; (c) a defined word used somewhere we have not found. Start from the existing
      ledgers (crossrefs/uncited/reach, hidden glossaries, overlay inventory) and report only
      what they miss, with path#line.
   3. **Bottomless, but aim $20 short -- development work the coordinator hands off**,
      billed to the API instead of the subscription; the last ~$20 goes to a green
      double-check (lot report + cited code + rulings -> right / wrong / can't tell with a
      quote; quote-backed wrongs read by Claude as a false-GREEN round). Declined for now:
      statewide scouting (item 55) as tier 3.

   **Tier 3 job #1 (Steph 2026-11-27 "no one is doing security patches"):** clear the open
   Dependabot alerts -- 123 on 11-27, all in uv.lock, ~12 packages (Pillow/pillow, pypdf,
   aiohttp, PyJWT, tornado, soupsieve, urllib3, mcp, certifi, multidict, Mako); 4 critical
   are Pillow, certifi, PyJWT. Last cleared 2026-07-29 (memory
   project_dependabot_cleanup_2026_07: keep the mcp<2 pin unless fastapi-mcp supports 2.x;
   `uv sync --all-extras`; the image installs from uv.lock). Worker bumps on a branch and
   runs the full suite; the coordinator runs ci_local, deploys, checks smoke. Close stale
   dependabot PR #4. Proposed standing rule: every month, after the code-change check,
   the security pass has the next claim on the credit.

   How it runs (no build needed -- speed): headless Claude Code workers on Steph's PC,
   `claude -p --bare --model claude-opus-5-5 --max-budget-usd N --output-format json`, key
   in the worker's environment only (never global settings, so the subscription session
   is never billed to it and vice versa), no MCP (cannot touch 114/137/production), dev
   work on worktree branches only -- the coordinator reviews, tests and ships. Ledger:
   gitignored data/flats/credit/ledger.jsonl, one row per worker with its reported cost;
   a worker is not launched if spent + its budget > $190. Steph also sets a $200 limit in
   the console. Last launch ~12 h before expiry.
   Waiting on: Steph creates the API key in the account holding the credit and pastes it.
