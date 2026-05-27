# Copilot Agent Instructions — vicinitideals

## Branch-First Rule

**Never work directly on `main`.** Before making any changes, create a dedicated branch:

```bash
git checkout main
git pull origin main
git checkout -b feature/<slug>
```

Use a short slug describing the work (e.g. `feature/csrf-middleware`, `fix/cashflow-dscr`).

## Why This Matters

Claude Code agents run in separate git worktrees on their own branches. If you work on `main` and push, your changes can overwrite or conflict with in-flight Claude Code branch work. Each agent session must own its own branch.

## Workflow

1. **Start**: `git checkout -b feature/<slug>` from fresh `main`
2. **Work**: make all changes on that branch
3. **Commit**: conventional commits (`feat:`, `fix:`, `refactor:`, `docs:`)
4. **Push**: `git push origin feature/<slug>` — never `git push origin main`
5. **PR**: open a pull request; do not merge yourself

## Deploy

Do **not** trigger deploys. Claude Code agents handle deployment after PR merge per the CLAUDE.md deploy workflow.

## Key Files

- `CLAUDE.md` — full project context, architecture, conventions (read this)
- `docs/FINANCIAL_MODEL.md` — financial engine math reference
- `docs/DATA_MODEL.md` — ORM schema reference

## Package Manager

Use `uv`, not `pip`. Example: `uv add <package>`, `uv run pytest`.
