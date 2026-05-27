# Copilot Agent Instructions — vicinitideals

## Start Here

**Read `CLAUDE.md` in the repo root before doing anything.** It is the authoritative source for:
- Tech stack, project structure, architecture
- Coding conventions (Decimal for money, SQLAlchemy 2.0 style, Pydantic v2, uv not pip)
- Deploy workflow
- Testing requirements (every change needs a test)
- Database safety rules (never `docker compose down -v`)

Everything below is Copilot-specific workflow.

---

## Branch Before Working

**Never commit to `main`.** Create a branch first:

```bash
git checkout main && git pull origin main
git checkout -b feature/<short-slug>
```

---

## Full Workflow Per Session

1. Branch from fresh `main` (above)
2. Make changes following `CLAUDE.md` conventions
3. Run tests: `uv run pytest tests/ -q --ignore=tests/e2e`
4. Lint: `uv run ruff check app/ tests/`
5. Commit with conventional prefix (`feat:`, `fix:`, `refactor:`, `docs:`, `chore:`)
6. Push branch: `git push origin feature/<slug>`
7. Merge to main: `git checkout main && git merge feature/<slug> && git push origin main`
8. Deploy: `ssh root@192.168.1.28 "bash /root/deploy-vicinitideals.sh"`
9. Verify health check passes in deploy output

---

## Package Manager

`uv`, not `pip`. Run: `uv add <pkg>` · `uv run pytest` · `uv run ruff check app/ tests/`
