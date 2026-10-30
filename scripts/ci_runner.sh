#!/usr/bin/env bash
# Runs on the ci-runner container (LXC 138): test one commit the PC pushed to
# refs/ci/<sha> (FOLLOWUPS 128). scripts/ci_local.py calls it as
#
#   git -C /root/ci/repo show <sha>:scripts/ci_runner.sh | bash -s <sha> <base_sha> <suites>
#
# so the version under test is the version that runs. Each run gets its own
# worktree and venv (uv's cache makes that seconds), and each pytest process its
# own throwaway database in the container's Postgres, so runs do not collide.
set -uo pipefail
sha=$1 base=$2 suites=$3
export PATH=/root/.local/bin:$PATH UV_PYTHON=3.12 PYTHONUNBUFFERED=1
# The container's own throwaway Postgres (fsync off); see lxc-apps/138-ci-runner.
export TEST_DATABASE_URL=postgresql+asyncpg://test:test@localhost:5432/re_modeling_test
export CI_LOCAL_APP_WORKERS=${CI_LOCAL_APP_WORKERS:-8}
repo=/root/ci/repo
wt=/root/ci/wt/${sha:0:12}

cd "$repo" || exit 3
git fetch -q origin
git worktree remove --force "$wt" 2>/dev/null
git worktree add -q --detach "$wt" "$sha" || exit 3
cd "$wt" || exit 3
cp "$repo/.env" .env
uv sync -q --extra dev --extra api --extra flats --extra gis --extra tools || exit 3
uv run --no-sync python scripts/ci_local.py --here --base "$base" --suites "$suites"
rc=$?
cd "$repo" && git worktree remove --force "$wt" && git update-ref -d "refs/ci/$sha"
exit $rc
