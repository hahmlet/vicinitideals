---
applyTo: "**"
---

# Agent Setup — vicinitideals

## Step 1 — Read CLAUDE.md

Read `CLAUDE.md` in the repo root before doing anything. It covers the full tech stack, architecture, coding conventions, testing requirements, and database safety rules. Follow it exactly.

## Step 2 — Branch Before Any Changes

**Never commit directly to `main`.** Create a branch first, every session:

```bash
git checkout main
git pull origin main
git checkout -b feature/<short-slug>
```

Use a slug describing the work: `feature/csrf-middleware`, `fix/cashflow-dscr`, `chore/update-docs`.

## Step 3 — Make Changes, Run Tests

Follow the conventions in `CLAUDE.md`. Every change needs a test:

```bash
uv run pytest tests/ -q --ignore=tests/e2e   # unit + integration
uv run ruff check app/ tests/                 # lint
```

## Step 4 — Commit and Push to Your Branch

```bash
git add -p                             # stage intentionally
git commit -m "feat: <description>"   # conventional prefix
git push origin feature/<slug>
```

Never `git push origin main`.

## Step 5 — Merge and Deploy

When changes are ready and tests pass:

```bash
git checkout main
git merge feature/<slug>
git push origin main
```

Then deploy to production using SSH:

```bash
ssh root@192.168.1.28 "bash /root/deploy-vicinitideals.sh"
```

Deploy script runs: `git pull → docker compose build → alembic upgrade head → docker compose up -d → health check`. Confirm health check passes in output before stopping.

## Package Manager

`uv` not `pip`. Examples: `uv add <pkg>` · `uv run pytest` · `uv run ruff check app/ tests/`
