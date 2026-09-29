"""Every "start a background job" route when Redis / the Celery broker is down.

The broker being unreachable used to surface as a raw 500. Now:

  * routes that leave a row behind undo it and say so in plain words
      POST /ui/brokers/{id}/oregon-update        broker not left "pending"
      POST /api/email-ingest                     row dropped; 503 so Resend retries
      POST /ui/models/{id}/investor-export/async job marked failed, 503 {"error"}
      POST /ui/exports/{id}/resend               same
  * everything else reaches the app-wide handler (app.api.queue_errors)
      POST /api/scraper/oregon-elicense/run      JSON 503
      POST /ui/models/{id}/upload-proforma       HTMX fragment / JSON 503
      POST /ui/models/{id}/proforma-preflight    (Redis stash fails first)
  * the Crexi triggers already fall back to an in-process scrape; pinned here
      POST /api/ingest/trigger, /api/scraper/run

The failure is simulated by making the enqueue call raise the exception kombu
or redis-py raises for a dead broker.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from kombu.exceptions import OperationalError
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.queue_errors import QUEUE_UNAVAILABLE_MESSAGE
from app.config import settings
from app.models.broker import Broker
from app.models.email_ingest import InboundEmail
from app.models.export_job import ExportJob, ExportJobStatus

from tests.conftest import (
    seed_deal_model,
    seed_opportunity,
    seed_org,
    set_client_auth,
)

pytestmark = pytest.mark.asyncio

_DOWN = OperationalError("Error 111 connecting to redis:6379. Connection refused.")


def _assert_json_503(resp) -> None:
    assert resp.status_code == 503, resp.text
    body = resp.json()
    assert body["code"] == "queue_unavailable"
    assert body["message"] == QUEUE_UNAVAILABLE_MESSAGE
    assert body["error"] == QUEUE_UNAVAILABLE_MESSAGE
    assert "Traceback" not in resp.text and "6379" not in resp.text


def _assert_htmx_fragment(resp) -> None:
    # htmx 2 will not swap a 5xx body, so the fragment rides a 200.
    assert resp.status_code == 200, resp.text
    assert "data-queue-unavailable" in resp.text
    assert QUEUE_UNAVAILABLE_MESSAGE in resp.text


async def _user(session: AsyncSession):
    _org, user = await seed_org(session)
    await session.commit()
    return user


# ---------------------------------------------------------------------------
# /api/scraper/oregon-elicense/run  (the Settings "Trigger Sweep" button)
# ---------------------------------------------------------------------------


async def test_oregon_sweep_broker_down_is_a_plain_503(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: dict[str, str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    user = await _user(session)
    with (
        patch(
            "app.tasks.oregon_elicense.oregon_elicense_sweep.delay",
            side_effect=_DOWN,
        ),
        caplog.at_level(logging.ERROR, logger="app.api.queue_errors"),
    ):
        resp = await client.post(
            "/api/scraper/oregon-elicense/run",
            headers={**auth_headers, "X-User-ID": str(user.id)},
        )
    _assert_json_503(resp)
    assert any(
        "background queue unreachable" in r.getMessage()
        and "/api/scraper/oregon-elicense/run" in r.getMessage()
        for r in caplog.records
    )


async def test_oregon_sweep_from_signed_in_settings_page(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The Settings button is a plain fetch() with the session cookie."""
    user = await _user(session)
    set_client_auth(client, user.id)
    with patch(
        "app.tasks.oregon_elicense.oregon_elicense_sweep.delay", side_effect=_DOWN
    ):
        resp = await client.post("/api/scraper/oregon-elicense/run")
    _assert_json_503(resp)


# ---------------------------------------------------------------------------
# Crexi triggers: already degrade to an in-process scrape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/api/ingest/trigger", "/api/scraper/run"])
async def test_crexi_trigger_broker_refuses_falls_back_in_process(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: dict[str, str],
    path: str,
) -> None:
    user = await _user(session)
    task = MagicMock()
    task.app.control.ping.return_value = [{"w@x": "pong"}]  # worker answers ping
    task.apply_async.side_effect = _DOWN                    # but the publish fails
    scheduled: list[Any] = []

    def _grab(coro, *a, **kw):
        scheduled.append(coro)
        return MagicMock()

    with (
        patch("app.api.routers.ingest.scrape_crexi", new=task),
        patch("app.api.routers.ingest._scrape_crexi", new=AsyncMock()) as scrape,
        patch("app.api.routers.ingest.asyncio.create_task", side_effect=_grab),
    ):
        resp = await client.post(
            path, headers={**auth_headers, "X-User-ID": str(user.id)}
        )
        for coro in scheduled:
            await coro

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "queued"
    scrape.assert_awaited_once()


# ---------------------------------------------------------------------------
# /ui/brokers/{id}/oregon-update
# ---------------------------------------------------------------------------


async def test_broker_oregon_update_broker_down_leaves_status_unchanged(
    client: AsyncClient, session: AsyncSession
) -> None:
    user = await _user(session)
    set_client_auth(client, user.id)
    broker = Broker(
        id=uuid.uuid4(), first_name="Avery", last_name="Ash",
        license_number="201234567", license_state="OR",
        oregon_lookup_status="found",
    )
    session.add(broker)
    await session.commit()
    broker_id = broker.id
    session.expunge_all()

    with patch(
        "app.tasks.oregon_elicense.enrich_broker_oregon.delay", side_effect=_DOWN
    ):
        resp = await client.post(
            f"/ui/brokers/{broker_id}/oregon-update",
            headers={"hx-request": "true"},
        )

    _assert_htmx_fragment(resp)
    session.expunge_all()
    row = await session.get(Broker, broker_id)
    assert row.oregon_lookup_status == "found"  # not stuck at "pending"


# ---------------------------------------------------------------------------
# /api/email-ingest  (Resend webhook)
# ---------------------------------------------------------------------------

_KEY = b"test-webhook-key-0123456789abcdef"


def _signed(body: bytes) -> dict[str, str]:
    svix_id = f"msg_{uuid.uuid4().hex}"
    stamp = str(int(time.time()))
    sig = base64.b64encode(
        hmac.new(_KEY, f"{svix_id}.{stamp}.".encode() + body, hashlib.sha256).digest()
    ).decode()
    return {
        "svix-id": svix_id,
        "svix-timestamp": stamp,
        "svix-signature": f"v1,{sig}",
        "content-type": "application/json",
    }


async def test_email_webhook_broker_down_drops_row_and_asks_for_retry(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings, "resend_webhook_secret", "whsec_" + base64.b64encode(_KEY).decode()
    )
    monkeypatch.setattr(settings, "inbound_email_org_id", None)
    await seed_org(session)
    await session.commit()
    body = json.dumps({
        "type": "email.received",
        "data": {"email_id": "re_123", "from": "broker@example.com", "subject": "OM"},
    }).encode()

    with patch(
        "app.tasks.email_ingest.process_inbound_email.delay", side_effect=_DOWN
    ):
        resp = await client.post("/api/email-ingest", content=body, headers=_signed(body))

    _assert_json_503(resp)
    session.expunge_all()
    rows = (await session.execute(select(InboundEmail))).scalars().all()
    assert rows == []  # Resend's retry will not create a duplicate


# ---------------------------------------------------------------------------
# /ui/models/{id}/investor-export/async  +  /ui/exports/{id}/resend
# ---------------------------------------------------------------------------


async def _model_and_user(session: AsyncSession):
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    model = await seed_deal_model(session, opp, user)
    await session.commit()
    return model.id, user.id


@pytest.fixture
def send_task_down(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.tasks.celery_app import celery_app

    def _raise(*_a, **_kw):
        raise _DOWN

    monkeypatch.setattr(celery_app, "send_task", _raise)


async def test_async_export_broker_down_marks_job_failed(
    client: AsyncClient, session: AsyncSession, send_task_down: None
) -> None:
    model_id, user_id = await _model_and_user(session)
    set_client_auth(client, user_id)

    resp = await client.post(
        f"/ui/models/{model_id}/investor-export/async", json={"profile": "lp"}
    )

    _assert_json_503(resp)
    session.expire_all()
    jobs = (
        await session.execute(select(ExportJob).where(ExportJob.scenario_id == model_id))
    ).scalars().all()
    assert len(jobs) == 1
    assert jobs[0].status == ExportJobStatus.failed  # never stuck at "queued"
    assert jobs[0].error_message == QUEUE_UNAVAILABLE_MESSAGE


async def test_export_resend_broker_down_marks_copy_failed(
    client: AsyncClient, session: AsyncSession, send_task_down: None
) -> None:
    model_id, user_id = await _model_and_user(session)
    src = ExportJob(
        scenario_id=model_id, user_id=user_id, recipient_email="lp@example.com",
        status=ExportJobStatus.sent, xlsx_bytes=b"PK-cached", filename="d.xlsx",
    )
    session.add(src)
    await session.commit()
    src_id = src.id
    set_client_auth(client, user_id)

    resp = await client.post(f"/ui/exports/{src_id}/resend")

    _assert_json_503(resp)
    session.expire_all()
    jobs = (
        await session.execute(
            select(ExportJob).where(
                ExportJob.scenario_id == model_id, ExportJob.id != src_id
            )
        )
    ).scalars().all()
    assert [j.status for j in jobs] == [ExportJobStatus.failed]
    source = await session.get(ExportJob, src_id)
    assert source.status == ExportJobStatus.sent  # the original is untouched


# ---------------------------------------------------------------------------
# Pro forma import: the app-wide handler (no per-route code)
# ---------------------------------------------------------------------------


async def test_upload_proforma_broker_down_htmx_and_json(
    client: AsyncClient, session: AsyncSession, send_task_down: None
) -> None:
    model_id, user_id = await _model_and_user(session)
    set_client_auth(client, user_id)
    url = f"/ui/models/{model_id}/upload-proforma"
    form = {"task_id": "t-1", "revenue_sheet": "Revenue"}

    htmx = await client.post(url, data=form, headers={"hx-request": "true"})
    _assert_htmx_fragment(htmx)

    plain = await client.post(url, data=form)
    _assert_json_503(plain)


async def test_proforma_preflight_redis_down(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    import redis

    model_id, user_id = await _model_and_user(session)
    set_client_auth(client, user_id)
    dead = MagicMock()
    dead.set.side_effect = RedisConnectionError("Error 111 connecting to redis:6379.")
    monkeypatch.setattr(redis, "from_url", lambda *_a, **_kw: dead)

    resp = await client.post(
        f"/ui/models/{model_id}/proforma-preflight",
        files={"file": ("om.docx", b"not really a docx", "application/octet-stream")},
        headers={"hx-request": "true"},
    )
    _assert_htmx_fragment(resp)
