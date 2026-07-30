FROM python:3.12-slim AS base

WORKDIR /app

# Install uv for fast dependency installs
RUN pip install --no-cache-dir uv

# Copy package definition + lockfile first (layer-cache friendly)
COPY pyproject.toml uv.lock ./

# Install the locked dependency set — the exact versions the test suite ran
# against. Never fresh-resolve here: a rebuild once pulled a brand-new mcp 2.0
# and crash-looped the API (fastapi-mcp 0.4.x incompatibility, 2026-07-29).
RUN uv export --frozen --no-dev --no-emit-project --extra api -o /tmp/requirements-api.txt \
    && uv pip install --system -r /tmp/requirements-api.txt \
    && uv pip install --system --no-deps -e .

# Copy application source
COPY app/ app/

# Copy alembic for migration support in api container
COPY alembic/ alembic/
COPY alembic.ini .

# Copy tests so they're available in the image
COPY tests/ tests/

# Copy deploy/ops scripts
COPY scripts/ scripts/

# Copy the financial-model doc — source of truth for the investor export's
# Glossary sheet (parsed at request time by app/exporters/_doc_validator.py).
# Without this, GET /ui/models/{id}/investor-export.xlsx 500s with
# FileNotFoundError on /app/docs/FINANCIAL_MODEL.md.
COPY docs/FINANCIAL_MODEL.md docs/FINANCIAL_MODEL.md

# -------------------------------------------------------------------------
# API stage
# -------------------------------------------------------------------------
FROM base AS api

EXPOSE 8000

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# -------------------------------------------------------------------------
# Worker stage — same image, CMD overridden by docker-compose command:
# -------------------------------------------------------------------------
FROM base AS worker

# Install worker extras on top of base, locked versions only (includes
# Playwright for ASP.NET WebForms scrapers like Oregon eLicense)
RUN uv export --frozen --no-dev --no-emit-project --extra api --extra worker -o /tmp/requirements-worker.txt \
    && uv pip install --system -r /tmp/requirements-worker.txt

# Install Chromium + OS deps for Playwright. Adds ~250MB to the image but is
# required for any scraper that needs JS execution (Oregon eLicense uses a
# CurrentFilter/UpdatePanel pattern that won't run server-side off a plain
# form POST). install-deps uses apt-get under the hood.
RUN playwright install-deps chromium && playwright install chromium

# Default CMD is overridden per-service in docker-compose.yml
CMD ["celery", "-A", "app.tasks.celery_app", "worker"]
