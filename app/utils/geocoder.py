"""Oregon address geocoding via the state Navigator GeocodeServer.

Uses Oregon's own authoritative address locator — no API key required, and
handles Oregon address formats (range addresses, rural routes, etc.) better
than generic geocoders.

Usage:
    from app.utils.geocoder import geocode_oregon_address

    result = await geocode_oregon_address("100 Main St, Gresham, OR")
    if result:
        lat, lon, score = result["lat"], result["lon"], result["score"]
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.utils.proxy_pool import gis_proxy

logger = logging.getLogger(__name__)

_GEOCODER_URL = "https://navigator.state.or.us/arcgis/rest/services/Locators/OregonAddress/GeocodeServer/findAddressCandidates"

# Minimum match score to accept a geocode result (0–100)
MIN_SCORE = 80


async def geocode_oregon_address(
    address: str,
    *,
    min_score: int = MIN_SCORE,
    timeout: float = 15.0,
) -> dict[str, Any] | None:
    """Geocode a single address string using Oregon's Navigator geocoder.

    Returns a dict with keys: lat, lon, score, match_addr, addr_type
    or None if no result meets the minimum score threshold.
    """
    params = {
        "SingleLine": address,
        "outFields": "Match_addr,Addr_type,Score",
        "outSR": "4326",
        "maxLocations": "1",
        "f": "json",
    }
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            proxy=gis_proxy(),
        ) as client:
            response = await client.get(_GEOCODER_URL, params=params)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.warning("Geocode request failed for %r: %s", address, exc)
        return None

    candidates = payload.get("candidates") or []
    if not candidates:
        logger.debug("No geocode candidates for %r", address)
        return None

    best = candidates[0]
    score = best.get("score", 0)
    if score < min_score:
        logger.debug("Geocode score %s below threshold %s for %r", score, min_score, address)
        return None

    location = best.get("location") or {}
    attrs = best.get("attributes") or {}
    return {
        "lat": location.get("y"),
        "lon": location.get("x"),
        "score": score,
        "match_addr": attrs.get("Match_addr") or best.get("address"),
        "addr_type": attrs.get("Addr_type"),
    }


async def geocode_many(
    addresses: list[str],
    *,
    min_score: int = MIN_SCORE,
    timeout: float = 15.0,
) -> list[dict[str, Any] | None]:
    """Geocode a list of addresses sequentially. Returns one result per input."""
    results = []
    for address in addresses:
        result = await geocode_oregon_address(address, min_score=min_score, timeout=timeout)
        results.append(result)
    return results
