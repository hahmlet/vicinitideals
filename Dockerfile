FROM python:3.12-slim AS base

WORKDIR /app

# Install uv for fast dependency installs
RUN pip install --no-cache-dir uv

# Copy package definition first (layer-cache friendly)
COPY pyproject.toml .

# Install all api extras (superset of base deps)
RUN uv pip install --system -e ".[api]"

# Copy application source
COPY vicinitideals/ vicinitideals/

# Copy alembic for migration support in api container
COPY alembic/ alembic/
COPY alembic.ini .

# Copy tests so they're available in the image
COPY tests/ tests/

# -------------------------------------------------------------------------
# API stage
# -------------------------------------------------------------------------
FROM base AS api

EXPOSE 8000

CMD ["uvicorn", "vicinitideals.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# -------------------------------------------------------------------------
# Worker stage — same image, CMD overridden by docker-compose command:
# -------------------------------------------------------------------------
FROM base AS worker

# Install worker extras on top of base
RUN uv pip install --system -e ".[worker]"

# Default CMD is overridden per-service in docker-compose.yml
CMD ["celery", "-A", "vicinitideals.tasks.celery_app", "worker"]
