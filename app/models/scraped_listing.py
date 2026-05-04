"""ScrapedListing — backward-compat alias for Opportunity.

The scraped_listings table was renamed to opportunities in migration 0067.
All new code should import Opportunity from app.models.opportunity directly.
"""

from app.models.opportunity import Opportunity  # noqa: F401

# Backward-compat alias — existing imports of ScrapedListing continue to work.
ScrapedListing = Opportunity
