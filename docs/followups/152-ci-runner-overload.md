# 152 [Claude] ci-runner: cap concurrent runs, keep Postgres up

2026-11-08: four branches ran `scripts/ci_local.py` on LXC 138 at once (load ~38,
12 GB box). The kernel OOM-killed Postgres's checkpointer at 09:16 UTC, and the
cluster then shut down and stayed down (`systemctl is-active postgresql` still
said "active"; `pg_lsclusters` said down). Every later run then failed app_all
with 1834 "connection refused" errors. Restarted by hand with
`pg_ctlcluster 16 main start`.

To do (small):
- `scripts/ci_runner.sh`: take a counting lock (e.g. `flock` on one of 2 slot
  files under /root/ci/) so at most 2 runs test at once; others wait.
- Start of each run: `pg_isready` and, if it's down, `pg_ctlcluster 16 main start`
  (or fail fast with a clear message rather than 1834 errors).
- Optional: give the postgres unit `OOMScoreAdjust=-900` in lxc-apps/138-ci-runner.
