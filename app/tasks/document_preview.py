"""Celery task: convert an uploaded Office document to a PDF preview.

PDFs and images render natively in the browser; Office formats
(.doc/.docx/.xls/.xlsx) do not. This task POSTs the original bytes to a
headless Gotenberg (LibreOffice) service, stores the resulting PDF alongside
the original under the doc-room storage root, and flips the Document's
``preview_status`` to ``ready`` (or ``failed``). The /view route serves the
preview PDF inline once ready. Download of the original always works
regardless of conversion outcome.

Runs on the ``analysis`` queue (see celery_app.py task_routes).
"""

from __future__ import annotations

import asyncio
import os
from uuid import UUID

import httpx

from app.config import settings
from app.db import AsyncSessionLocal, engine as _db_engine
from app.models.document import Document, DocumentPreviewStatus
from app.storage.documents import open_document, save_document
from app.tasks.celery_app import celery_app

CONVERT_PREVIEW_TASK = "app.tasks.document_preview.convert_document_preview"

# Extensions Gotenberg/LibreOffice converts to PDF.
_CONVERTIBLE = {".doc", ".docx", ".xls", ".xlsx"}


@celery_app.task(bind=True, name=CONVERT_PREVIEW_TASK)
def convert_document_preview(self, document_id: str) -> str:
    """Entry point: build a PDF preview for the given document."""
    del self
    return asyncio.run(_with_fresh_loop(_convert_async, document_id))


async def _with_fresh_loop(fn, *args):
    """Dispose the shared engine around the task body so its pool stays bound
    to this task's event loop (Celery prefork reuses the process)."""
    try:
        await _db_engine.dispose()
        return await fn(*args)
    finally:
        await _db_engine.dispose()


async def _convert_async(document_id: str) -> str:
    doc_uuid = UUID(document_id)

    async with AsyncSessionLocal() as session:
        doc = await session.get(Document, doc_uuid)
        if doc is None:
            return "missing"
        ext = os.path.splitext(doc.filename or "")[1].lower()
        if ext not in _CONVERTIBLE:
            doc.preview_status = DocumentPreviewStatus.none
            await session.commit()
            return "skipped"
        storage_key = doc.storage_key
        filename = doc.filename or "document"

    try:
        source = open_document(storage_key)
        pdf_bytes = await _gotenberg_convert(filename, source)
        preview_key = f"{storage_key}.preview.pdf"
        save_document(preview_key, pdf_bytes)
        status = DocumentPreviewStatus.ready
    except Exception:  # conversion is best-effort; download still works
        preview_key = None
        status = DocumentPreviewStatus.failed

    async with AsyncSessionLocal() as session:
        doc = await session.get(Document, doc_uuid)
        if doc is None:
            return "missing"
        doc.preview_status = status
        if preview_key:
            doc.preview_key = preview_key
        await session.commit()
    return status.value


async def _gotenberg_convert(filename: str, content: bytes) -> bytes:
    """POST the file to Gotenberg's LibreOffice route; return PDF bytes."""
    url = f"{settings.gotenberg_url.rstrip('/')}/forms/libreoffice/convert"
    files = {"files": (filename, content)}
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(url, files=files)
        resp.raise_for_status()
        return resp.content
