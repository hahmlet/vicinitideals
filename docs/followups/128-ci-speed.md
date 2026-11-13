# 128. CI takes an hour or more per push

[Claude] [BUILT 2026-10-30; open: quadfit 7 min] [scan: NO]

BUILT 2026-10-30: pushes are tested before the push by `scripts/ci_local.py` + pre-push hook on LXC 138 `ci-runner` (~16 min door to door: FLATS ~5, quadfit ~7, app ~4; falls back to the PC), GitHub runs once a day from a clean checkout, session-start readout (commits 4ceb7542, a2493daa; runner config personalproxmox 8eaf80b3). Reference: docs/TESTING.md.

Open (optional): quadfit (363 tests, ~7 min) is the long pole on the runner -- look at what it spends time on. Watching the daily GitHub run is the standing "red daily CI is fixed first" rule.
