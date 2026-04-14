"""Router registry for the re-modeling FastAPI app."""

from vicinitideals.api.routers import (
    capital,
    deals,
    dedup,
    ingest,
    listings,
    models,
    parcels,
    portfolios,
    projects,
    scenarios,
    users,
)

ROUTERS = [
    users.router,
    projects.router,
    parcels.router,
    deals.router,
    models.router,
    capital.router,
    scenarios.router,
    listings.router,
    dedup.router,
    portfolios.router,
    ingest.router,
]

__all__ = ["ROUTERS"]
