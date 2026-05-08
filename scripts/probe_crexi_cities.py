"""One-shot diagnostic: probe Crexi API for each candidate city, report totalCount."""
import asyncio
import json

try:
    from curl_cffi.requests import AsyncSession
except Exception:
    import httpx
    class AsyncSession(httpx.AsyncClient):
        def __init__(self, *args, impersonate=None, **kwargs):
            super().__init__(*args, **kwargs)

SEARCH_URL = "https://api.crexi.com/assets/search"
HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": "https://www.crexi.com",
    "Referer": "https://www.crexi.com/properties",
}

CANDIDATES = [
    # Portland metro east / Multnomah
    "Portland", "Gresham", "Troutdale", "Fairview", "Wood Village", "Damascus",
    # Clackamas County
    "Oregon City", "Milwaukie", "Happy Valley", "Clackamas", "Sandy", "Estacada",
    "Gladstone", "Canby", "Lake Oswego", "West Linn", "Wilsonville", "Tualatin",
    # Washington County (user said no west — included to see counts only)
    "Beaverton", "Hillsboro", "Tigard", "Sherwood", "Forest Grove",
    # Already in DB — should still show counts
    "Salem", "Eugene", "Lincoln City",
]

async def probe():
    results = []
    async with AsyncSession(impersonate="chrome110") as session:
        for city in CANDIDATES:
            try:
                r = await session.post(
                    SEARCH_URL,
                    json={
                        "types": ["MultiFamily"],
                        "subtypes": ["Apartment Building"],
                        "includeUnpriced": True,
                        "states": ["OR"],
                        "cities": [city],
                        "take": 1,
                        "skip": 0,
                    },
                    headers=HEADERS,
                    timeout=15,
                )
                if r.status_code == 200:
                    payload = r.json() or {}
                    count = int(payload.get("totalCount") or 0)
                    results.append((city, count, "ok"))
                else:
                    results.append((city, 0, f"http_{r.status_code}"))
            except Exception as e:
                results.append((city, 0, str(e)[:40]))
            await asyncio.sleep(0.5)

    print(f"\n{'City':<20} {'Total':>6}  Status")
    print("-" * 36)
    for city, count, status in sorted(results, key=lambda x: -x[1]):
        print(f"{city:<20} {count:>6}  {status}")

asyncio.run(probe())
