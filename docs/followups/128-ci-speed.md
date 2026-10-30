# 128. CI takes an hour or more per push

128. [Claude] [Steph] [OFFERED 2026-10-30, waits on Steph's go] [scan: NO] **CI takes an hour or more per push.**

Measured 2026-10-30 from `gh run list` and step timings (.github/workflows/ci.yml):
- Light gate, on EVERY push (its comment says "<2 min"): unit tests ~3 min, FLATS tests 14-26 min, quadfit tests 16-28 min, so ~35-58 min.
- Full gate, only after the light gate passes, on code pushes: integration ~25 min, E2E ~25 min, Trivy <1 min. Whole run ~1.5 h.
- The docs-only skip covers the full gate only. A FOLLOWUPS-only commit (7d29f7b7) still ran 58 min of FLATS + quadfit tests. `.claude/agents/` is not in the docs filter either.
- No `concurrency:` block, so 5-6 runs overlap on busy nights and a superseded run is never cancelled.
- FLATS tests take 2:24 locally (16 cores, -n auto) against 14-26 min on the shared runner. The repo is PUBLIC, so minutes are free: the cost is wait time, plus a longer window where a bad change is live before CI says so (we deploy before CI finishes).

Offered, all in ci.yml, none touching what a test checks:
1. Skip FLATS/quadfit/unit tests for bookkeeping-only pushes (docs/, *.md, .claude/agents/, .gitignore).
2. Cancel an older main run when a newer push lands. Safe because the newest run tests everything before it.
3. Folder-level selection: FLATS + quadfit suites only when flats/, Lot Analysis/, data/flats/, scripts/flats_* or shared config change; app unit/integration only when app/, tests/, alembic/ change; E2E on either. The firewall already enforces the split. NOT per-test selection (testmon-style): FLATS answers depend on YAML data files a test tracker cannot see, so a missed dependency is a missed failure.
4. Run the light and full gates side by side instead of one after the other.
5. Separately (test code, not CI): the FLATS census hotspot (~63% of that suite; docs/TESTING.md) and the quadfit suite's 16-28 min.

Expected: a bookkeeping push about 0 min; a FLATS push about 30-45 min; app-only about 30 min. Must not change: no test is deleted or skipped on a code change that could reach it. The weekly/full runs keep everything.

2026-10-30 Steph: "I don't see a reason to not just crank it out local." Proposed shape: the full check (unit, FLATS -n auto, quadfit, ruff, firewall, integration) runs on the PC BEFORE every push; GitHub drops to a once-a-day clean-checkout run (catches files that exist only on the PC) plus items 1-2. NOT a GitHub self-hosted runner on the PC: the repo is public, so outside pull requests could run code on Steph's machine, and the PC must be on. Local timing being measured: the quadfit suite runs serially and took >10 min on the PC too, so it needs -n like FLATS.
