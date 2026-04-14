"""Datacenter proxy pool — round-robin across N proxies for all GIS requests.

Usage
-----
from vicinitideals.utils.proxy_pool import gis_proxy

async with httpx.AsyncClient(timeout=t, proxy=gis_proxy()) as client:
    ...

``gis_proxy()`` returns None when no datacenter proxies are configured so
every call site degrades gracefully to a direct connection.
"""

from __future__ import annotations

import itertools
import threading
from typing import Any


class _ProxyPool:
    """Thread-safe round-robin proxy pool."""

    def __init__(self, proxy_urls: list[str]) -> None:
        self._urls = [u.strip() for u in proxy_urls if u.strip()]
        self._cycle = itertools.cycle(self._urls) if self._urls else None
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return self._cycle is not None

    def next_url(self) -> str | None:
        if self._cycle is None:
            return None
        with self._lock:
            return next(self._cycle)

    def next_proxy(self) -> str | None:
        """Return the next proxy URL string (httpx 0.28+ API), or None if pool is empty."""
        return self.next_url()

    def __len__(self) -> int:
        return len(self._urls)

    def __repr__(self) -> str:
        return f"<ProxyPool proxies={len(self._urls)} available={self.available}>"


# ---------------------------------------------------------------------------
# Module-level singleton — initialised once from settings at import time
# ---------------------------------------------------------------------------

_pool: _ProxyPool | None = None
_pool_lock = threading.Lock()


def _get_pool() -> _ProxyPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                from vicinitideals.config import settings
                raw = settings.proxyon_datacenter_proxies or ""
                urls = [p.strip() for p in raw.split(",") if p.strip()]
                _pool = _ProxyPool(urls)
    return _pool


def gis_proxy() -> str | None:
    """Return the next proxy URL from the datacenter pool, or None if unconfigured."""
    return _get_pool().next_proxy()


def pool_info() -> dict[str, Any]:
    """Return a status dict for health/admin endpoints."""
    p = _get_pool()
    return {"available": p.available, "count": len(p)}


__all__ = ["gis_proxy", "pool_info"]
