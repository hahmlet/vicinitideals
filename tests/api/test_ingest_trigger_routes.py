"""The listing-ingest trigger routes (app/api/routers/ingest.py).

    POST /api/ingest/trigger              POST /api/scraper/run
    GET  /api/ingest/latest               POST /api/scraper/oregon-elicense/run
    GET  /api/realie/status               POST /api/realie/enrich

test_routers.py covers /api/scraper/run with a live worker. Everything else is
here. No test reaches Crexi, the Oregon eLicense site, Realie or Redis: the
Celery tasks, the in-process scrape fallback and the Realie enricher are all
replaced before the request is sent.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ingestion import IngestJob
from app.models.realie_usage import RealieUsage
from app.scrapers.realie import _current_month

pytestmark = pytest.mark.asyncio


class _FakeTask:
    """Stands in for the scrape_crexi Celery task; records what was queued."""

    def __init__(self, *, workers: bool, task_id: str = "celery-abc") -> None:
        self.calls: list[dict[str, Any]] = []
        self._task_id = task_id
        self.app = MagicMock()
        self.app.control.ping.return_value = [{"w@x": "pong"}] if workers else []

    def apply_async(self, *, kwargs=None, queue=None):
        self.calls.append({"kwargs": kwargs, "queue": queue})
        result = MagicMock()
        result.id = self._task_id
        return result


_real_create_task = asyncio.create_task


def _capture_create_task():
    """Hold back the router's fire-and-forget coroutines so the test can await
    them itself; anything else (driver internals) is scheduled as normal."""
    scheduled: list = []

    def _grab(coro, *args, **kwargs):
        if getattr(coro, "__qualname__", "").startswith(
            ("_queue_scrape_task.", "run_realie_enrichment.")
        ):
            scheduled.append(coro)
            return MagicMock()
        return _real_create_task(coro, *args, **kwargs)

    return scheduled, patch("app.api.routers.ingest.asyncio.create_task", side_effect=_grab)


@pytest.fixture
async def hdr(session: AsyncSession, auth_headers: dict[str, str]) -> dict[str, str]:
    """API headers naming a real user -- every trigger route requires one."""
    from tests.conftest import seed_org

    _org, user = await seed_org(session)
    await session.commit()
    return {**auth_headers, "X-User-ID": str(user.id)}


# ---------------------------------------------------------------------------
# /api/ingest/trigger
# ---------------------------------------------------------------------------

async def test_trigger_queues_crexi_on_scraping_queue(
    client: AsyncClient, hdr: dict[str, str]
) -> None:
    fake = _FakeTask(workers=True)
    with patch("app.api.routers.ingest.scrape_crexi", new=fake):
        resp = await client.post("/api/ingest/trigger", json={}, headers=hdr)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert body["task_id"] == "celery-abc"
    assert body["source"] == "crexi"
    assert body["trace_id"] == resp.headers["X-Trace-ID"]
    assert datetime.fromisoformat(body["queued_at"])
    assert len(fake.calls) == 1
    assert fake.calls[0]["queue"] == "scraping"
    # The caller is recorded as the trigger, not a hard-coded label.
    assert fake.calls[0]["kwargs"] == {
        "triggered_by": hdr["X-User-ID"],
        "trace_id": body["trace_id"],
    }


async def test_trigger_without_body_defaults_to_crexi(
    client: AsyncClient, hdr: dict[str, str]
) -> None:
    fake = _FakeTask(workers=True)
    with patch("app.api.routers.ingest.scrape_crexi", new=fake):
        resp = await client.post("/api/ingest/trigger", headers=hdr)
    assert resp.status_code == 200
    assert resp.json()["source"] == "crexi"
    assert len(fake.calls) == 1


async def test_trigger_no_worker_runs_scrape_in_process(
    client: AsyncClient, hdr: dict[str, str]
) -> None:
    fake = _FakeTask(workers=False)
    scrape = AsyncMock()
    scheduled, create_task = _capture_create_task()
    with (
        patch("app.api.routers.ingest.scrape_crexi", new=fake),
        patch("app.api.routers.ingest._scrape_crexi", new=scrape),
        create_task,
    ):
        resp = await client.post("/api/ingest/trigger", json={}, headers=hdr)
        assert resp.status_code == 200
        assert len(scheduled) == 1
        await scheduled[0]

    body = resp.json()
    assert fake.calls == []  # nothing handed to a dead broker
    assert body["task_id"].startswith("ingest-crexi-")
    scrape.assert_awaited_once_with(
        triggered_by=hdr["X-User-ID"], trace_id=body["trace_id"]
    )


async def test_trigger_fallback_swallows_scrape_failure(
    client: AsyncClient, hdr: dict[str, str]
) -> None:
    """A crash inside the in-process scrape is logged, never raised into the loop."""
    scheduled, create_task = _capture_create_task()
    with (
        patch("app.api.routers.ingest.scrape_crexi", new=_FakeTask(workers=False)),
        patch(
            "app.api.routers.ingest._scrape_crexi",
            new=AsyncMock(side_effect=RuntimeError("crexi down")),
        ),
        create_task,
    ):
        resp = await client.post("/api/ingest/trigger", headers=hdr)
        await scheduled[0]  # must not raise
    assert resp.status_code == 200


async def test_trigger_rejects_unknown_source(
    client: AsyncClient, hdr: dict[str, str]
) -> None:
    fake = _FakeTask(workers=True)
    with patch("app.api.routers.ingest.scrape_crexi", new=fake):
        bad = await client.post(
            "/api/ingest/trigger", json={"source": "loopnet"}, headers=hdr
        )
    assert bad.status_code == 422
    assert fake.calls == []


# ---------------------------------------------------------------------------
# /api/ingest/latest
# ---------------------------------------------------------------------------

async def test_latest_idle_then_most_recent_job(
    client: AsyncClient, session: AsyncSession, hdr: dict[str, str]
) -> None:
    idle = await client.get("/api/ingest/latest", headers=hdr)
    assert idle.status_code == 200
    assert idle.json() == {"status": "idle"}

    now = datetime.now(UTC)
    session.add_all([
        IngestJob(source="crexi", status="completed", records_fetched=10,
                  started_at=now - timedelta(days=1), completed_at=now - timedelta(hours=23)),
        IngestJob(source="crexi", status="running", records_fetched=3, records_new=2,
                  records_duplicate_exact=1, source_total=40, started_at=now),
    ])
    await session.commit()

    resp = await client.get("/api/ingest/latest", headers=hdr)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "running"
    assert body["records_fetched"] == 3
    assert body["records_new"] == 2
    assert body["records_duplicate"] == 1
    assert body["source_total"] == 40
    assert body["completed_at"] is None
    started = datetime.fromisoformat(body["started_at"])
    assert started.utcoffset() == timedelta(0)  # always UTC, never a bare local time


# ---------------------------------------------------------------------------
# /api/scraper/run (no-worker path + bad input)
# ---------------------------------------------------------------------------

async def test_scraper_run_passes_max_results_to_fallback(
    client: AsyncClient, hdr: dict[str, str]
) -> None:
    scrape = AsyncMock()
    scheduled, create_task = _capture_create_task()
    with (
        patch("app.api.routers.ingest.scrape_crexi", new=_FakeTask(workers=False)),
        patch("app.api.routers.ingest._scrape_crexi", new=scrape),
        create_task,
    ):
        resp = await client.post(
            "/api/scraper/run", params={"max_results": 5}, headers=hdr
        )
        await scheduled[0]
    assert resp.status_code == 200
    body = resp.json()
    assert body["task_id"].startswith("scrape-crexi-")
    scrape.assert_awaited_once_with(triggered_by="ui", trace_id=body["trace_id"], max_results=5)


async def test_scraper_run_bad_max_results_422(
    client: AsyncClient, hdr: dict[str, str]
) -> None:
    fake = _FakeTask(workers=True)
    with patch("app.api.routers.ingest.scrape_crexi", new=fake):
        resp = await client.post(
            "/api/scraper/run", params={"max_results": "lots"}, headers=hdr
        )
    assert resp.status_code == 422
    assert fake.calls == []


# ---------------------------------------------------------------------------
# /api/scraper/oregon-elicense/run
# ---------------------------------------------------------------------------

async def test_oregon_sweep_queues_with_optional_cap(
    client: AsyncClient, hdr: dict[str, str]
) -> None:
    with patch("app.tasks.oregon_elicense.oregon_elicense_sweep.delay") as delay:
        delay.return_value.id = "oregon-1"
        capped = await client.post(
            "/api/scraper/oregon-elicense/run",
            params={"max_brokers": 7},
            headers=hdr,
        )
        uncapped = await client.post("/api/scraper/oregon-elicense/run", headers=hdr)
        bad = await client.post(
            "/api/scraper/oregon-elicense/run",
            params={"max_brokers": "all"},
            headers=hdr,
        )

    assert capped.status_code == 200 and uncapped.status_code == 200
    assert capped.json()["task_id"] == "oregon-1"
    assert capped.json()["source"] == "oregon_elicense"
    assert capped.json()["status"] == "queued"
    assert delay.call_args_list[0].kwargs == {"max_brokers": 7}
    assert delay.call_args_list[1].kwargs == {}
    assert bad.status_code == 422
    assert delay.call_count == 2


# ---------------------------------------------------------------------------
# /api/realie/status + /api/realie/enrich
# ---------------------------------------------------------------------------

async def test_realie_status_default_and_recorded(
    client: AsyncClient, session: AsyncSession, hdr: dict[str, str]
) -> None:
    fresh = await client.get("/api/realie/status", headers=hdr)
    assert fresh.status_code == 200
    assert fresh.json() == {
        "month": _current_month(), "calls_used": 0, "call_limit": 25,
        "calls_remaining": 25, "locked": False, "last_call_at": None,
    }

    session.add(RealieUsage(
        month=_current_month(), calls_used=25, call_limit=25, locked=False,
        last_call_at=datetime(2026, 9, 1, 12, tzinfo=UTC),
    ))
    await session.commit()
    used = (await client.get("/api/realie/status", headers=hdr)).json()
    assert used["calls_remaining"] == 0
    assert used["locked"] is True  # at the limit counts as locked
    assert used["last_call_at"].startswith("2026-09-01T12:00:00")


async def test_realie_enrich_refused_when_quota_spent(
    client: AsyncClient, session: AsyncSession, hdr: dict[str, str]
) -> None:
    session.add(RealieUsage(month=_current_month(), calls_used=3, call_limit=25, locked=True))
    await session.commit()
    enricher = MagicMock()
    with patch("app.api.routers.ingest.RealieEnricher", enricher):
        resp = await client.post("/api/realie/enrich", headers=hdr)
    assert resp.status_code == 429
    assert resp.json()["detail"]["error"] == "realie_quota_exceeded"
    enricher.assert_not_called()


async def test_realie_enrich_starts_background_batch(
    client: AsyncClient, hdr: dict[str, str]
) -> None:
    summary = {
        "enriched_count": 2, "not_found_count": 1, "calls_used": 3,
        "call_limit": 25, "locked": False,
    }
    instance = MagicMock()
    instance.enrich_batch = AsyncMock(return_value=summary)
    enricher_cls = MagicMock(return_value=instance)
    scheduled, create_task = _capture_create_task()
    with patch("app.api.routers.ingest.RealieEnricher", enricher_cls), create_task:
        resp = await client.post("/api/realie/enrich", headers=hdr)
        assert resp.status_code == 200
        assert len(scheduled) == 1
        await scheduled[0]

    body = resp.json()
    assert body["status"] == "started"
    assert body["trace_id"] == resp.headers["X-Trace-ID"]
    instance.enrich_batch.assert_awaited_once()


async def test_realie_enrich_background_failure_is_contained(
    client: AsyncClient, hdr: dict[str, str]
) -> None:
    instance = MagicMock()
    instance.enrich_batch = AsyncMock(side_effect=RuntimeError("realie 500"))
    scheduled, create_task = _capture_create_task()
    with (
        patch("app.api.routers.ingest.RealieEnricher", MagicMock(return_value=instance)),
        create_task,
    ):
        resp = await client.post("/api/realie/enrich", headers=hdr)
        await scheduled[0]  # must not raise
    assert resp.status_code == 200


TRIGGERS = (
    "/api/ingest/trigger",
    "/api/scraper/run",
    "/api/scraper/oregon-elicense/run",
    "/api/realie/enrich",
)


@pytest.mark.parametrize("path", TRIGGERS)
async def test_anonymous_caller_cannot_start_paid_work(
    client: AsyncClient, session: AsyncSession, path: str
) -> None:
    """/api/* passes neither the API-key gate nor the login gate, so these
    routes answered anyone on the internet: a stranger could start a
    residential-proxy scrape or spend the monthly Realie budget. With no
    identity, or an identity that names no user, nothing may be queued."""
    fake = _FakeTask(workers=True)
    enricher = MagicMock()
    client.headers.pop("X-User-ID", None)
    scheduled, create_task = _capture_create_task()
    with (
        patch("app.api.routers.ingest.scrape_crexi", new=fake),
        patch("app.tasks.oregon_elicense.oregon_elicense_sweep.delay") as delay,
        patch("app.api.routers.ingest.RealieEnricher", enricher),
        create_task,
    ):
        nobody = await client.post(path)
        stranger = await client.post(path, headers={"X-User-ID": str(uuid4())})

    assert nobody.status_code == 401, nobody.text
    assert stranger.status_code == 401, stranger.text
    assert fake.calls == []
    delay.assert_not_called()
    enricher.assert_not_called()
    assert scheduled == []


async def test_signed_in_browser_session_can_trigger(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The Listings page buttons post with the session cookie, no API key."""
    from tests.conftest import seed_org, set_client_auth

    _org, user = await seed_org(session)
    await session.commit()
    client.headers.pop("X-User-ID", None)
    set_client_auth(client, user.id)
    fake = _FakeTask(workers=True)
    with patch("app.api.routers.ingest.scrape_crexi", new=fake):
        resp = await client.post("/api/scraper/run", headers={"hx-request": "true"})
    assert resp.status_code == 200, resp.text
    assert len(fake.calls) == 1
