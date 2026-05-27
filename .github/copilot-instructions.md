# Copilot Agent Instructions — vicinitideals

## Start Here

**Read `CLAUDE.md` in the repo root before doing anything.** It is the authoritative source for:
- Tech stack, project structure, architecture
- Coding conventions (Decimal for money, SQLAlchemy 2.0 style, Pydantic v2, uv not pip)
- Deploy workflow
- Testing requirements (every change needs a test)
- Database safety rules (never `docker compose down -v`)

Everything below is Copilot-specific and **overrides** the Claude Code-specific parts of CLAUDE.md.

---

## Branch-First — Always

**Never work directly on `main`.** Before any changes:

```bash
git checkout main && git pull origin main
git checkout -b feature/<short-slug>
```

Slug examples: `feature/csrf-middleware`, `fix/cashflow-dscr`, `refactor/waterfall-helpers`.

**Why:** Claude Code agents work in isolated git worktrees on their own branches. Committing to `main` causes push conflicts that overwrite in-flight Claude Code work.

---

## Commit → Push → PR (never merge yourself)

1. Commit with conventional prefix: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`
2. Push to your branch: `git push origin feature/<slug>`
3. Open a PR — do **not** merge it yourself and do **not** push to `main`

---

## No Deploys

Do not trigger deploys. Claude Code agents handle deployment after PR merge via SSH to VM 114. See `CLAUDE.md` deploy section for the exact steps if context is needed.

---

## Package Manager

`uv`, not `pip`. Run: `uv add <pkg>` · `uv run pytest` · `uv run ruff check app/ tests/`
