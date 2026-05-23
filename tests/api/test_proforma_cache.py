"""Tests for the pro forma file content-hash cache routes.

Covers preflight cache check, ``proforma-use-cached``,
``proforma-reanalyze``, and ``proforma-purge-cache``. Redis is replaced by
an in-memory stand-in so tests run without a live Redis. Celery's
``send_task`` is stubbed so doc-kind reanalyze can be asserted without
queuing real work.

The routes under test do not touch the database, so this file builds its
own ASGI client to avoid the conftest ``client`` fixture's
``Base.metadata.create_all`` (which currently fails on SQLite for tables
with JSONB columns).
"""

from __future__ import annotations

import hashlib
import io
import json
from typing import AsyncIterator
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from openpyxl import Workbook


# ---------------------------------------------------------------------------
# In-memory Redis stand-in
# ---------------------------------------------------------------------------

class _FakeRedis:
    """Minimal Redis stand-in. All values stored as bytes; views decode on
    read depending on the ``decode_responses`` flag the connection was
    created with. ``ex`` (TTL in seconds) is recorded in ``ttl_log`` per
    key so tests can assert TTL semantics without a real Redis."""

    def __init__(self, store: dict, ttl_log: dict, decode_responses: bool):
        self._store = store
        self._ttl_log = ttl_log
        self._decode = decode_responses

    def get(self, key):
        val = self._store.get(key)
        if val is None:
            return None
        if self._decode:
            return val.decode() if isinstance(val, (bytes, bytearray)) else val
        return val if isinstance(val, (bytes, bytearray)) else str(val).encode()

    def set(self, key, value, ex=None):
        if isinstance(value, str):
            value = value.encode()
        elif isinstance(value, (bytes, bytearray)):
            value = bytes(value)
        else:
            value = str(value).encode()
        self._store[key] = value
        self._ttl_log[key] = ex
        return True

    def delete(self, *keys):
        n = 0
        for k in keys:
            if k in self._store:
                del self._store[k]
                self._ttl_log.pop(k, None)
                n += 1
        return n


@pytest.fixture
def redis_store() -> dict:
    return {}


@pytest.fixture
def redis_ttls() -> dict:
    """Records the ``ex`` argument from every ``redis.set`` call, keyed by
    Redis key. Lets tests assert TTL behavior without a real Redis."""
    return {}


@pytest.fixture(autouse=True)
def _patch_redis(monkeypatch, redis_store, redis_ttls):
    """Replace ``redis.from_url`` so the routes hit the in-memory fake."""
    import redis  # type: ignore

    def _from_url(_url, decode_responses: bool = False, **_kwargs):
        return _FakeRedis(redis_store, redis_ttls, decode_responses)

    monkeypatch.setattr(redis, "from_url", _from_url)


@pytest.fixture(autouse=True)
def _patch_celery(monkeypatch):
    """Stub Celery's send_task so doc-kind paths don't enqueue real work."""
    from app.tasks.celery_app import celery_app as _celery_inst

    mock = MagicMock()
    monkeypatch.setattr(_celery_inst, "send_task", mock)
    return mock


# ---------------------------------------------------------------------------
# Local ASGI client — does NOT create DB tables (the routes under test
# don't touch the DB, and the conftest-provided client fixture is currently
# broken on SQLite for the global Base.metadata.create_all path).
# ---------------------------------------------------------------------------

@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:  # type: ignore[override]
    from app.api.main import create_app

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        # hx-request: true exempts the auth-redirect middleware (HTMX
        # fragment requests are allowed through so partial swaps work).
        headers={"X-User-ID": str(uuid4()), "hx-request": "true"},
    ) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_xlsx_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Revenue"
    ws.append(["Unit Type", "Count", "Rent"])
    ws.append(["1BR", 10, 1500])
    ws2 = wb.create_sheet("OpEx")
    ws2.append(["Label", "Amount"])
    ws2.append(["Insurance", 5000])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# proforma-preflight: cache miss vs cache hit
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_preflight_cache_miss_returns_sheet_picker(client):
    model_id = uuid4()
    xlsx_bytes = _minimal_xlsx_bytes()

    resp = await client.post(
        f"/ui/models/{model_id}/proforma-preflight",
        files={"file": ("p.xlsx", xlsx_bytes,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code == 200
    body = resp.text
    assert "Which sheets?" in body
    assert "Use Cached Result" not in body


@pytest.mark.integration
async def test_preflight_cache_hit_returns_cached_template(client, redis_store):
    model_id = uuid4()
    xlsx_bytes = _minimal_xlsx_bytes()
    file_hash = hashlib.sha256(xlsx_bytes).hexdigest()

    cached = {
        "unit_types": [{"name": "1BR"}],
        "expense_lines": [{"label": "Insurance"}, {"label": "Taxes"}],
        "warnings": ["one warning"],
    }
    redis_store[f"proforma:filehash:{file_hash}:result"] = json.dumps(cached).encode()
    redis_store[f"proforma:filehash:{file_hash}:parsed_at"] = b"2026-05-12T10:00:00Z"

    resp = await client.post(
        f"/ui/models/{model_id}/proforma-preflight",
        files={"file": ("p.xlsx", xlsx_bytes, "application/octet-stream")},
    )
    assert resp.status_code == 200
    body = resp.text
    assert "Use Cached Result" in body
    assert "Re-analyze" in body
    # The hash and counts come through the template
    assert file_hash in body
    assert "1" in body  # 1 unit type
    assert "2" in body  # 2 expense lines


@pytest.mark.integration
async def test_preflight_writes_file_hash_to_task_key(client, redis_store):
    """Preflight should store SHA-256 hex under proforma:{task_id}:file_hash
    so the Celery task can later write the hash cache."""
    model_id = uuid4()
    xlsx_bytes = _minimal_xlsx_bytes()
    expected_hash = hashlib.sha256(xlsx_bytes).hexdigest()

    resp = await client.post(
        f"/ui/models/{model_id}/proforma-preflight",
        files={"file": ("p.xlsx", xlsx_bytes, "application/octet-stream")},
    )
    assert resp.status_code == 200

    hash_keys = [k for k in redis_store if k.endswith(":file_hash")]
    assert len(hash_keys) == 1
    stored = redis_store[hash_keys[0]]
    if isinstance(stored, (bytes, bytearray)):
        stored = stored.decode()
    assert stored == expected_hash


@pytest.mark.integration
async def test_preflight_empty_file_returns_400(client):
    model_id = uuid4()
    resp = await client.post(
        f"/ui/models/{model_id}/proforma-preflight",
        files={"file": ("p.xlsx", b"", "application/octet-stream")},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# proforma-use-cached
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_use_cached_renders_review_and_mirrors_task_key(client, redis_store):
    model_id = uuid4()
    task_id = str(uuid4())
    file_hash = "a" * 64

    cached = {
        "unit_types": [{
            "name": "1BR", "count": 10, "avg_sqft": 700,
            "avg_monthly_rent": 1500, "confidence": 0.9,
        }],
        "expense_lines": [],
        "warnings": [],
    }
    redis_store[f"proforma:filehash:{file_hash}:result"] = json.dumps(cached).encode()

    resp = await client.post(
        f"/ui/models/{model_id}/proforma-use-cached",
        data={"task_id": task_id, "file_hash": file_hash},
    )
    assert resp.status_code == 200
    # Review template renders with the confirm form
    assert "proforma-confirm" in resp.text
    # Mirrored to task-keyed result key for downstream confirm flow
    assert f"proforma:{task_id}:result" in redis_store


@pytest.mark.integration
async def test_use_cached_returns_410_when_expired(client):
    """If the cache key is gone (or never existed), respond 410 Gone."""
    model_id = uuid4()
    resp = await client.post(
        f"/ui/models/{model_id}/proforma-use-cached",
        data={"task_id": str(uuid4()), "file_hash": "f" * 64},
    )
    assert resp.status_code == 410


@pytest.mark.integration
async def test_use_cached_rejects_malformed_hash(client):
    model_id = uuid4()
    resp = await client.post(
        f"/ui/models/{model_id}/proforma-use-cached",
        data={"task_id": str(uuid4()), "file_hash": "too-short"},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# proforma-reanalyze
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_reanalyze_xlsx_returns_sheet_picker(client, redis_store):
    model_id = uuid4()
    task_id = str(uuid4())
    redis_store[f"proforma:{task_id}:file"] = _minimal_xlsx_bytes()
    redis_store[f"proforma:{task_id}:kind"] = b"xlsx"

    resp = await client.post(
        f"/ui/models/{model_id}/proforma-reanalyze",
        data={"task_id": task_id},
    )
    assert resp.status_code == 200
    assert "Which sheets?" in resp.text


@pytest.mark.integration
async def test_reanalyze_returns_410_when_file_missing(client):
    model_id = uuid4()
    resp = await client.post(
        f"/ui/models/{model_id}/proforma-reanalyze",
        data={"task_id": str(uuid4())},
    )
    assert resp.status_code == 410


@pytest.mark.integration
async def test_reanalyze_doc_queues_celery_and_returns_progress(client, redis_store, _patch_celery):
    model_id = uuid4()
    task_id = str(uuid4())
    redis_store[f"proforma:{task_id}:file"] = b"%PDF-1.4 fake bytes"
    redis_store[f"proforma:{task_id}:kind"] = b"doc"

    resp = await client.post(
        f"/ui/models/{model_id}/proforma-reanalyze",
        data={"task_id": task_id},
    )
    assert resp.status_code == 200
    assert _patch_celery.called
    # Progress template renders a polling hook
    assert "proforma-status" in resp.text


# ---------------------------------------------------------------------------
# proforma-purge-cache
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_purge_cache_deletes_keys_and_returns_picker(client, redis_store):
    model_id = uuid4()
    task_id = str(uuid4())
    file_hash = "b" * 64

    redis_store[f"proforma:{task_id}:file"] = _minimal_xlsx_bytes()
    redis_store[f"proforma:{task_id}:kind"] = b"xlsx"
    redis_store[f"proforma:filehash:{file_hash}:result"] = b'{"unit_types":[]}'
    redis_store[f"proforma:filehash:{file_hash}:parsed_at"] = b"2026-05-12T10:00:00Z"

    resp = await client.post(
        f"/ui/models/{model_id}/proforma-purge-cache",
        data={"task_id": task_id, "file_hash": file_hash},
    )
    assert resp.status_code == 200
    assert f"proforma:filehash:{file_hash}:result" not in redis_store
    assert f"proforma:filehash:{file_hash}:parsed_at" not in redis_store
    # And the user is dropped back into the sheet picker for a fresh parse
    assert "Which sheets?" in resp.text


@pytest.mark.integration
async def test_purge_cache_ignores_malformed_hash(client, redis_store):
    """A bad hash should not 500; should still attempt reanalyze (which 410s
    if there's nothing to reanalyze)."""
    model_id = uuid4()
    task_id = str(uuid4())
    redis_store[f"proforma:filehash:{'c' * 64}:result"] = b"{}"

    resp = await client.post(
        f"/ui/models/{model_id}/proforma-purge-cache",
        data={"task_id": task_id, "file_hash": "short"},
    )
    # Reanalyze can't find the file → 410. Important: cache key is left intact.
    assert resp.status_code == 410
    assert f"proforma:filehash:{'c' * 64}:result" in redis_store


# ---------------------------------------------------------------------------
# Celery task: hash cache write
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_celery_task_writes_hash_cache_after_parse(redis_store, monkeypatch):
    """The parse_proforma task should write
    proforma:filehash:{hash}:result and :parsed_at after a successful parse."""
    from app.tasks import proforma_parse as pp_mod

    task_id = str(uuid4())
    model_id = str(uuid4())
    file_hash = "d" * 64
    xlsx_bytes = _minimal_xlsx_bytes()

    redis_store[f"proforma:{task_id}:file"] = xlsx_bytes
    redis_store[f"proforma:{task_id}:filename"] = b"p.xlsx"
    redis_store[f"proforma:{task_id}:kind"] = b"xlsx"
    redis_store[f"proforma:{task_id}:file_hash"] = file_hash.encode()

    # Stub the LLM client so we don't hit Ollama
    class _FakeRev:
        unit_types: list = []

    class _FakeExp:
        expense_lines: list = []

    class _FakeCompletions:
        def create(self, *_a, **_kw):
            # Return whichever shape the caller's response_model expects
            rm = _kw.get("response_model")
            if rm is None:
                return _FakeRev()
            return rm(unit_types=[]) if rm.__name__ == "ParsedRevenue" else rm(expense_lines=[])

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    monkeypatch.setattr(pp_mod, "_llm_client", lambda: _FakeClient())

    # Run the underlying function directly (not via Celery)
    pp_mod.parse_proforma.run(
        task_id=task_id,
        model_id=model_id,
        revenue_sheet="Revenue",
        opex_sheet="OpEx",
        property_column=None,
        file_kind="xlsx",
    )

    # The hash cache should now be populated
    assert f"proforma:filehash:{file_hash}:result" in redis_store
    assert f"proforma:filehash:{file_hash}:parsed_at" in redis_store
    cached_raw = redis_store[f"proforma:filehash:{file_hash}:result"]
    cached = json.loads(cached_raw.decode() if isinstance(cached_raw, (bytes, bytearray)) else cached_raw)
    assert "unit_types" in cached
    assert "expense_lines" in cached


# ---------------------------------------------------------------------------
# TTL semantics — hash cache should outlive the per-task cache
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_hash_cache_keys_have_seven_day_ttl(redis_store, redis_ttls, monkeypatch):
    """The Celery task must write the content-hash cache with a 7-day TTL
    (604_800 seconds) — significantly longer than the per-task 24-hour TTL
    used for ephemeral upload state. A regression here would silently make
    cached parses expire after one day."""
    from app.tasks import proforma_parse as pp_mod

    task_id = str(uuid4())
    model_id = str(uuid4())
    file_hash = "e" * 64

    redis_store[f"proforma:{task_id}:file"] = _minimal_xlsx_bytes()
    redis_store[f"proforma:{task_id}:filename"] = b"p.xlsx"
    redis_store[f"proforma:{task_id}:kind"] = b"xlsx"
    redis_store[f"proforma:{task_id}:file_hash"] = file_hash.encode()

    class _FakeCompletions:
        def create(self, *_a, **_kw):
            rm = _kw.get("response_model")
            return rm(unit_types=[]) if rm.__name__ == "ParsedRevenue" else rm(expense_lines=[])

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    monkeypatch.setattr(pp_mod, "_llm_client", lambda: _FakeClient())

    pp_mod.parse_proforma.run(
        task_id=task_id,
        model_id=model_id,
        revenue_sheet="Revenue",
        opex_sheet="OpEx",
        property_column=None,
        file_kind="xlsx",
    )

    seven_days = 7 * 86_400
    assert redis_ttls.get(f"proforma:filehash:{file_hash}:result") == seven_days
    assert redis_ttls.get(f"proforma:filehash:{file_hash}:parsed_at") == seven_days
    # Sanity: the per-task result keeps the shorter 24-hour TTL
    assert redis_ttls.get(f"proforma:{task_id}:result") == 86_400


# ---------------------------------------------------------------------------
# Filename surfaced in cache-hit template
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_cache_hit_template_includes_uploaded_filename(client, redis_store):
    """When the preflight detects a cache hit, the rendered template should
    show the filename the user just uploaded so they can confirm it's the
    file they thought it was (file content can match across renames)."""
    model_id = uuid4()
    xlsx_bytes = _minimal_xlsx_bytes()
    file_hash = hashlib.sha256(xlsx_bytes).hexdigest()
    expected_filename = "Q4-2026-actuals-final-FINAL.xlsx"

    redis_store[f"proforma:filehash:{file_hash}:result"] = json.dumps(
        {"unit_types": [], "expense_lines": [], "warnings": []}
    ).encode()
    redis_store[f"proforma:filehash:{file_hash}:parsed_at"] = b"2026-05-12T10:00:00Z"

    resp = await client.post(
        f"/ui/models/{model_id}/proforma-preflight",
        files={"file": (expected_filename, xlsx_bytes, "application/octet-stream")},
    )
    assert resp.status_code == 200
    assert expected_filename in resp.text
