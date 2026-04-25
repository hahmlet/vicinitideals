"""Registry of per-firm contact-info scrapers.

Each broker is associated with a firm (Brokerage). Some firms publish broker
contact info on their public site in a way we can scrape (`smire.com` puts
each broker on their own profile page); others hide contact details behind
auth or simply don't publish them. This registry tracks our scraper coverage
so the UI can color firm names accordingly:

  - ``supported``   → we have an adapter; auto-enrichment runs on new brokers
  - ``unsupported`` → we've assessed this firm and there's nothing scrapable
  - ``unknown``     → never assessed (default)

The Brokerage table stores ``firm_scrape_status`` and ``firm_scrape_domain``
so the rendered UI doesn't need to import this module — but updates to
either of those columns flow from here. When you add or remove an adapter,
also add/remove the firm here and run the sync helper to push the change
to existing rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FirmScraperEntry:
    """Metadata about our scraper coverage for a single firm.

    ``domain`` is the canonical web domain (lower-case, no scheme). It's used
    both as the registry key and as the value stored in
    ``Brokerage.firm_scrape_domain`` for cross-referencing.
    """

    domain: str
    status: str  # 'supported' | 'unsupported'
    display_name: str
    note: str | None = None


# Initially empty. Adapters will be added here as we build them. Domains we
# explicitly mark as unsupported (after looking and finding nothing scrapable)
# also live here.
_REGISTRY: dict[str, FirmScraperEntry] = {
    # Examples (commented out — uncomment when we ship the adapter):
    # "smire.com": FirmScraperEntry(
    #     domain="smire.com",
    #     status="supported",
    #     display_name="SMIRE",
    #     note="Per-broker profile pages at /team/{slug}",
    # ),
}


def get_entry(domain: str | None) -> FirmScraperEntry | None:
    if not domain:
        return None
    return _REGISTRY.get(domain.lower())


def status_for(domain: str | None) -> str:
    """Return the registry-derived status for a firm domain.

    Returns 'unknown' for domains we have not assessed. The Brokerage table's
    ``firm_scrape_status`` column is the runtime source of truth — this
    function is what *populates* that column.
    """
    entry = get_entry(domain)
    return entry.status if entry else "unknown"


def all_entries() -> Iterable[FirmScraperEntry]:
    return _REGISTRY.values()


__all__ = ["FirmScraperEntry", "all_entries", "get_entry", "status_for"]
