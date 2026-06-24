"""Document-room UI router — per-project file upload / download / view.

Phase 1 of the document-room module: a project-scoped "document view" (an
Explorer-style list) with multi-file upload, single + bulk download (zipped),
inline view of PDFs/images, archive + recover, and hard delete.

Mounted without an ``/api`` prefix (like the other ``ui_*`` routers). The
full-page route lives under ``/projects/...`` (added to ``_UI_PATH_PREFIXES`` in
``app/api/main.py`` so it bypasses the API-key gate but still requires a
session); HTMX partials + file streams live under ``/ui/...``.

Org isolation: ``projects`` has no ``org_id`` of its own — it is resolved
through Scenario→Deal. Each :class:`Document` denormalizes ``org_id`` so
document-level routes can scope directly. All access funnels through
``_require_project`` / ``_require_document`` which 404 on any cross-org attempt.
"""

from __future__ import annotations

import io
import os
import zipfile
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy import select

from app.api.deps import DBSession
from app.api.routers.ui_helpers import (
    _base_ctx,
    _get_counts,
    _get_user,
    templates,
)
from app.config import settings
from app.models.deal import Deal, Scenario
from app.models.document import Document, DocumentPreviewStatus, DocumentStatus
from app.models.project import Project
from app.storage.documents import (
    build_storage_key,
    delete_document,
    open_document,
    save_document,
)

router = APIRouter(include_in_schema=False)

# Extensions the browser can render inline without conversion.
_INLINE_MEDIA: dict[str, str] = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}

_EXT_ICONS: dict[str, str] = {
    ".pdf": "📕",
    ".doc": "📘", ".docx": "📘",
    ".xls": "📗", ".xlsx": "📗",
    ".jpg": "🖼️", ".jpeg": "🖼️", ".png": "🖼️",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ext(filename: str) -> str:
    return os.path.splitext(filename or "")[1].lower()


def _safe_header_filename(name: str) -> str:
    """Sanitize a filename for use in a Content-Disposition header."""
    cleaned = (name or "file").replace("\r", "").replace("\n", "").replace('"', "")
    return cleaned[:255] or "file"


def _human_size(num: int) -> str:
    size = float(num or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def _doc_vm(doc: Document) -> dict:
    ext = _ext(doc.filename)
    return {
        "id": str(doc.id),
        "filename": doc.filename,
        "ext": ext,
        "icon": _EXT_ICONS.get(ext, "📄"),
        "size_human": _human_size(doc.size_bytes),
        "created_fmt": doc.created_at.strftime("%b %-d, %Y %-I:%M %p") if doc.created_at else "—",
        "viewable": ext in _INLINE_MEDIA or doc.preview_status == DocumentPreviewStatus.ready,
        "status": doc.status.value if hasattr(doc.status, "value") else doc.status,
    }


async def _project_org_id(session: DBSession, project_id: UUID) -> UUID | None:
    """Resolve a project's owning org via Scenario→Deal."""
    stmt = (
        select(Deal.org_id)
        .join(Scenario, Scenario.deal_id == Deal.id)
        .join(Project, Project.scenario_id == Scenario.id)
        .where(Project.id == project_id)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _require_project(session: DBSession, request: Request, project_id: UUID):
    """Return (user, org_id, project) or raise 404 (also for cross-org access)."""
    if not settings.documents_module_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    user = await _get_user(session, request)
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Not found")
    org_id = await _project_org_id(session, project_id)
    if settings.org_isolation_enabled:
        user_org = getattr(user, "org_id", None)
        if user_org is None or org_id is None or org_id != user_org:
            raise HTTPException(status_code=404, detail="Not found")
    return user, org_id, project


async def _require_document(session: DBSession, request: Request, document_id: UUID):
    """Return (user, document) or raise 404 (also for cross-org access)."""
    if not settings.documents_module_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    user = await _get_user(session, request)
    doc = await session.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Not found")
    if settings.org_isolation_enabled:
        user_org = getattr(user, "org_id", None)
        if user_org is None or doc.org_id != user_org:
            raise HTTPException(status_code=404, detail="Not found")
    return user, doc


async def _load_docs(session: DBSession, org_id: UUID, project_id: UUID, show: str):
    status = DocumentStatus.archived if show == "archived" else DocumentStatus.active
    stmt = (
        select(Document)
        .where(
            Document.org_id == org_id,
            Document.project_id == project_id,
            Document.status == status,
        )
        .order_by(Document.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def _deal_for_project(session: DBSession, project: Project) -> Deal | None:
    stmt = (
        select(Deal)
        .join(Scenario, Scenario.deal_id == Deal.id)
        .where(Scenario.id == project.scenario_id)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


def _rows_response(
    request: Request,
    project_id: UUID,
    docs: list[Document],
    show: str,
    errors: list[str] | None = None,
):
    return templates.TemplateResponse(
        request,
        "partials/document_rows.html",
        {
            "project_id": str(project_id),
            "documents": [_doc_vm(d) for d in docs],
            "show": show,
            "upload_errors": errors or [],
            "oob": True,
        },
    )


# ---------------------------------------------------------------------------
# Full page
# ---------------------------------------------------------------------------

@router.get("/projects/{project_id}/documents", response_class=HTMLResponse)
async def documents_page(
    request: Request,
    project_id: UUID,
    session: DBSession,
    show: str = Query(default="active"),
) -> HTMLResponse:
    user, org_id, project = await _require_project(session, request, project_id)
    dedup_count, conflicts_count = await _get_counts(session)
    deal = await _deal_for_project(session, project)
    docs = await _load_docs(session, org_id, project_id, show)
    return templates.TemplateResponse(
        request,
        "documents.html",
        {
            **_base_ctx(user, dedup_count, active_nav="deals", conflicts_count=conflicts_count),
            "project": project,
            "project_id": str(project_id),
            "project_name": project.name,
            "deal_id": str(deal.id) if deal else None,
            "deal_name": deal.name if deal else "Deal",
            "documents": [_doc_vm(d) for d in docs],
            "show": show,
            "max_size_mb": settings.document_max_size_bytes // (1024 * 1024),
            "allowed_ext": ",".join(sorted(settings.document_allowed_extensions_set)),
        },
    )


# ---------------------------------------------------------------------------
# HTMX partials
# ---------------------------------------------------------------------------

@router.get("/ui/projects/{project_id}/documents/rows", response_class=HTMLResponse)
async def documents_rows(
    request: Request,
    project_id: UUID,
    session: DBSession,
    show: str = Query(default="active"),
) -> HTMLResponse:
    user, org_id, project = await _require_project(session, request, project_id)
    docs = await _load_docs(session, org_id, project_id, show)
    return _rows_response(request, project_id, docs, show)


@router.post("/ui/projects/{project_id}/documents/upload", response_class=HTMLResponse)
async def documents_upload(
    request: Request,
    project_id: UUID,
    session: DBSession,
    files: list[UploadFile] = File(default=[]),
    show: str = Form(default="active"),
) -> HTMLResponse:
    user, org_id, project = await _require_project(session, request, project_id)
    allowed = settings.document_allowed_extensions_set
    errors: list[str] = []
    for up in files:
        name = (up.filename or "").strip()
        if not name:
            continue
        ext = _ext(name)
        if ext not in allowed:
            errors.append(f"{name}: file type not allowed")
            continue
        content = await up.read()
        if not content:
            errors.append(f"{name}: empty file skipped")
            continue
        if len(content) > settings.document_max_size_bytes:
            errors.append(f"{name}: exceeds {settings.document_max_size_bytes // (1024 * 1024)} MB limit")
            continue
        key = build_storage_key(org_id, project_id, name)
        sha = save_document(key, content)
        session.add(
            Document(
                org_id=org_id,
                project_id=project_id,
                filename=name[:512],
                content_type=(up.content_type or None),
                size_bytes=len(content),
                sha256=sha,
                storage_key=key,
                status=DocumentStatus.active,
                preview_status=DocumentPreviewStatus.none,
                uploaded_by_user_id=getattr(user, "id", None),
            )
        )
    await session.commit()
    docs = await _load_docs(session, org_id, project_id, show)
    return _rows_response(request, project_id, docs, show, errors)


@router.post("/ui/projects/{project_id}/documents/bulk", response_class=HTMLResponse)
async def documents_bulk(
    request: Request,
    project_id: UUID,
    session: DBSession,
    action: str = Form(...),
    ids: list[UUID] = Form(default=[]),
    show: str = Form(default="active"),
) -> HTMLResponse:
    """Archive / recover / delete the selected documents (mutating, swaps rows).

    Bulk *download* is a separate GET (``/documents/zip``) so the browser
    handles the file save instead of HTMX trying to swap a binary body.
    """
    user, org_id, project = await _require_project(session, request, project_id)
    selected: list[Document] = []
    if ids:
        stmt = select(Document).where(
            Document.id.in_(ids),
            Document.org_id == org_id,
            Document.project_id == project_id,
        )
        selected = list((await session.execute(stmt)).scalars().all())

    now = datetime.now(timezone.utc)
    if action == "archive":
        for d in selected:
            d.status = DocumentStatus.archived
            d.archived_at = now
    elif action == "recover":
        for d in selected:
            d.status = DocumentStatus.active
            d.archived_at = None
    elif action == "delete":
        for d in selected:
            delete_document(d.storage_key)
            if d.preview_key:
                delete_document(d.preview_key)
            await session.delete(d)
    else:
        raise HTTPException(status_code=400, detail="Unknown bulk action")

    await session.commit()
    docs = await _load_docs(session, org_id, project_id, show)
    return _rows_response(request, project_id, docs, show)


# ---------------------------------------------------------------------------
# File streams (download / view / zip)
# ---------------------------------------------------------------------------

@router.get("/ui/documents/{document_id}/download")
async def document_download(
    request: Request, document_id: UUID, session: DBSession
) -> StreamingResponse:
    user, doc = await _require_document(session, request, document_id)
    content = open_document(doc.storage_key)
    return StreamingResponse(
        iter([content]),
        media_type=doc.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{_safe_header_filename(doc.filename)}"'
        },
    )


@router.get("/ui/documents/{document_id}/view")
async def document_view(request: Request, document_id: UUID, session: DBSession):
    user, doc = await _require_document(session, request, document_id)
    # Converted Office preview (Phase 1b) takes precedence when ready.
    if doc.preview_status == DocumentPreviewStatus.ready and doc.preview_key:
        content = open_document(doc.preview_key)
        return StreamingResponse(
            iter([content]),
            media_type="application/pdf",
            headers={"Content-Disposition": 'inline; filename="preview.pdf"'},
        )
    ext = _ext(doc.filename)
    if ext in _INLINE_MEDIA:
        content = open_document(doc.storage_key)
        return StreamingResponse(
            iter([content]),
            media_type=_INLINE_MEDIA[ext],
            headers={
                "Content-Disposition": f'inline; filename="{_safe_header_filename(doc.filename)}"'
            },
        )
    # No native preview (Office formats before Phase 1b conversion lands).
    return HTMLResponse(
        "<div style='padding:32px;font-family:system-ui,sans-serif;color:#374151'>"
        "<p style='font-size:15px'>In-browser preview isn't available for this file type yet.</p>"
        f"<p><a href='/ui/documents/{document_id}/download' "
        "style='color:#2563EB'>⬇ Download the file instead</a></p></div>"
    )


@router.get("/ui/projects/{project_id}/documents/zip")
async def documents_zip(
    request: Request,
    project_id: UUID,
    session: DBSession,
    ids: list[UUID] = Query(default=[]),
) -> StreamingResponse:
    """Zip the selected documents and stream the archive back to the browser."""
    user, org_id, project = await _require_project(session, request, project_id)
    if not ids:
        raise HTTPException(status_code=400, detail="No documents selected")
    stmt = select(Document).where(
        Document.id.in_(ids),
        Document.org_id == org_id,
        Document.project_id == project_id,
    )
    docs = list((await session.execute(stmt)).scalars().all())
    if not docs:
        raise HTTPException(status_code=404, detail="Not found")

    buf = io.BytesIO()
    seen: dict[str, int] = {}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for d in docs:
            name = d.filename or "file"
            # De-collide identical names within the archive.
            if name in seen:
                seen[name] += 1
                stem, ext = os.path.splitext(name)
                name = f"{stem} ({seen[name]}){ext}"
            else:
                seen[name] = 0
            try:
                zf.writestr(name, open_document(d.storage_key))
            except FileNotFoundError:
                continue
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="documents.zip"'},
    )
