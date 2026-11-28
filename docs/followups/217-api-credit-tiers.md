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

   **TIER 1, ahead of everything (Steph 2026-11-27: "this should be tier 1 before everything else"; "no one is doing security patches"):** clear the open
   Dependabot alerts -- 123 on 11-27, all in uv.lock, ~12 packages (Pillow/pillow, pypdf,
   aiohttp, PyJWT, tornado, soupsieve, urllib3, mcp, certifi, multidict, Mako); 4 critical
   are Pillow, certifi, PyJWT. Last cleared 2026-07-29 (memory
   project_dependabot_cleanup_2026_07: keep the mcp<2 pin unless fastapi-mcp supports 2.x;
   `uv sync --all-extras`; the image installs from uv.lock). Worker bumps on a branch and
   runs the full suite; the coordinator runs ci_local, deploys, checks smoke. Close stale
   dependabot PR #4. Steph 2026-11-27: this month the security pass has NO cap of its own, only the credit;
   it outranks tiers 2/3 for the money (a capped-out worker is continued, tier 3 waits).
   Standing order every month: security pass first, then the code-change
   check (now tier 1b), then tier 2, then tier 3.

   How it runs (no build needed -- speed): headless Claude Code workers on Steph's PC,
   `claude -p --bare --model claude-opus-5-5 --max-budget-usd N --output-format json`, key
   in the worker's environment only (never global settings, so the subscription session
   is never billed to it and vice versa), no MCP (cannot touch 114/137/production), dev
   work on worktree branches only -- the coordinator reviews, tests and ships. Ledger:
   gitignored data/flats/credit/ledger.jsonl, one row per worker with its reported cost;
   a worker is not launched if spent + its budget > $190. Steph also sets a $200 limit in
   the console. Last launch ~12 h before expiry.
   Status 11-27 night: key in (~/.anthropic-credit-key, this PC only). t1 security worker
   running (worktree security-deps). t1b done -> 218 ($2.77). t2 done -> 222 ($31.0).
   t3 build queue (data/flats/credit/run-t3.sh, $15 cap each, 3 at a time, worktrees
   ../vicinitideals-worktrees/credit-*): milwaukie-vegetation, clack-1009,
   gresham-far-buffer, oregon-city-thimble, hillsboro-stub, west-linn-38030, beaverton-cm;
   each leaves HANDOFF.md in its worktree; the coordinator reviews, merges and bounds them
   as ONE package. Green check (3 x $7): 30 live greens, seed 68, round-5 lots excluded,
   reports dumped read-only from 114 to data/flats/credit/greens/.
   11-28: t1 security SHIPPED -- 0fc9e926 + abd9367b (soupsieve 4.1.3, pypdf capped <6.20 ->
   item 224), ci_local green on 138, deployed, smoke PASS. Open alerts went 123 -> 18, all
   pypdf. PR #4 closed. t3 three branches finished, handed to the FLATS Primary Development
   Agent (item 222). Workers now test at -n 4 at most (13af421d).
   **BEFORE NEXT MONTH -- worker isolation (security review 11-28, MEDIUM):** the allowlist
   lets a worker Write a file and then run it (`uv run python scripts/`, `uv run pytest`,
   git hooks via `git commit`), as Steph's Windows user with HOME inherited. A worker
   steered by hostile text in a fetched document could therefore run code on this PC. Fix
   options, cheapest first:
   - HOME/USERPROFILE set to an empty temp directory.
   - `git -c core.hooksPath=` on commits.
   - Deny Write/Edit outside the worktree and to .git/, scripts/, conftest.py.
   - Best: run workers in a container or VM with egress to api.anthropic.com only.
   Not done this month: 2 days left, and only repo-internal briefs remain.
