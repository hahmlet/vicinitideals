# Claude AI Assistant Instructions - vicinitideals

**Purpose**: Context for Claude when working on the vicinitideals real estate financial modeling platform.

## Quick Context

- **Product**: Self-hosted real estate deal modeling platform (FastAPI + HTMX + Celery)
- **Live domain**: `viciniti.deals` (NGINX on LXC 109 proxies to VM 114 port 8001)
- **Deploy**: `git push origin main` → VM 114 `/root/deploy-vicinitideals.sh` auto-runs
- **Docs**: See `docs/` for full project documentation
- **Infrastructure docs**: `../personalproxmox/documentation/MCP/` for Proxmox/networking

## Key Directories

- `app/` — Python package (FastAPI app, engines, scrapers, tasks, models)
- `app/api/routers/ui.py` — HTMX UI routes (~6800 lines, most active file)
- `app/engines/` — Financial computation (cashflow, draw_schedule, waterfall, etc.)
- `app/models/` — SQLAlchemy ORM models
- `alembic/` — Database migrations
- `tests/` — Unit + integration tests
- `docs/` — Project documentation

## Tech Stack

FastAPI 0.110+ · SQLAlchemy 2.0 async · asyncpg · Alembic · Celery 5.3+ · Redis · PostgreSQL · Jinja2 + HTMX · pyxirr · openpyxl

## Deploy Workflow

```bash
git push origin main
# VM 114 runs /root/deploy-vicinitideals.sh:
# git pull → docker compose build → alembic upgrade head → docker compose up -d → health check
```

## Database Safety

- PostgreSQL data lives in Docker named volume `re-modeling-postgres-data`
- **NEVER run `docker compose down -v`** — this deletes the volume and all data
- DB name and user remain `re_modeling` (intentional — renaming requires dump/restore)

## Critical Do-Nots

- **NEVER use `sudo`** — use Proxmox MCP for system operations
- **NEVER commit credentials** (.env, API keys, secrets)
- **NEVER hardcode infrastructure IPs/ports** — reference docs
- **NEVER run `docker compose down -v`** — destroys database
