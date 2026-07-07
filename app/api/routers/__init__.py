"""Router registry for the re-modeling FastAPI app."""

from app.api.routers import (
    capital,
    deals,
    dedup,
    email_ingest,
    ingest,
    listings,
    milestones,
    models,
    portfolios,
    projects,
    scenarios,
    settings,
    users,
)

ROUTERS = [
    users.router,
    projects.router,
    deals.router,
    models.router,
    milestones.router,
    capital.router,
    scenarios.router,
    listings.router,
    dedup.router,
    portfolios.router,
    ingest.router,
    settings.router,
    email_ingest.router,
]

__all__ = ["ROUTERS"]
