# 152 [Claude] [Steph] ci-runner: optional OOM protection for its Postgres

2026-11-08: four runs at once on LXC 138 got Postgres OOM-killed. Fixed in
scripts/ci_runner.sh (2-slot run cap, Postgres check/restart before testing).

Left, Steph's call (changes a systemd unit on 138, so not done by an agent): give
the postgres unit `OOMScoreAdjust=-900` in lxc-apps/138-ci-runner. With the 2-run
cap it should not be needed; do it only if Postgres is OOM-killed again.
