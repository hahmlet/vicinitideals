---
applyTo: "**"
---

# Agent Setup — vicinitideals

## Read CLAUDE.md First

Before doing anything, read `CLAUDE.md` in the repo root. It has all project conventions, architecture, testing requirements, and database safety rules.

## Branch Before Working

**Never commit to `main`.** Create a branch first:

```bash
git checkout main && git pull origin main
git checkout -b feature/<short-slug>
```

Claude Code agents run in isolated git worktrees. Working on `main` causes push conflicts that overwrite their in-flight changes.

## Workflow

1. Branch from fresh `main`
2. Make changes on the branch
3. `git push origin feature/<slug>` — never `git push origin main`
4. Open a PR — do not merge yourself

## No Deploys

Do not SSH to VM 114 or trigger deploys. Claude Code handles deployment after PR merge.

## Package Manager

`uv` not `pip`. Run tests: `uv run pytest`. Lint: `uv run ruff check app/ tests/`.
