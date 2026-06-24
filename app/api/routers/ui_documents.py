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
from datetime import date, datetime, timezone
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
from app.emails.tokens import load_doc_share_token, make_doc_share_token
from app.models.deal import Deal, Scenario
from app.models.document import (
    Document,
    DocumentPreviewStatus,
    DocumentShare,
    DocumentStatus,
    DocumentTask,
    DocumentTaskStatus,
)
from app.models.milestone import Milestone
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

# Office formats that get a server-side PDF preview (Phase 1b conversion).
_PREVIEW_EXTS = {".doc", ".docx", ".xls", ".xlsx"}

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


def _sanitize_filename(name: str) -> str:
    """Normalize an uploaded filename before persisting (defense-in-depth).

    Strips path components and any HTML/quote/control characters so a stored
    name can never carry markup into a rendered page or break headers/zip
    entries — independent of any client-side escaping at display time.
    """
    # Drop any directory parts a client may send (e.g. "../etc", "C:\\x\\y").
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    # Remove control chars and characters that enable markup/quote injection.
    base = "".join(c for c in base if c.isprintable() and c not in '<>:"\'`')
    base = base.strip(". ")  # no leading/trailing dots or spaces
    return base[:255]


def _fmt_date(d) -> str:
    """Portable 'Mon D, YYYY' (no platform-specific %-d)."""
    return f"{d:%b} {d.day}, {d.year}"


def _fmt_datetime(dt) -> str:
    """Portable 'Mon D, YYYY H:MM AM/PM' (no platform-specific %-d/%-I)."""
    hour = ((dt.hour - 1) % 12) + 1
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{dt:%b} {dt.day}, {dt.year} {hour}:{dt.minute:02d} {ampm}"


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
        "created_fmt": _fmt_datetime(doc.created_at) if doc.created_at else "—",
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


async def _save_uploads(
    session: DBSession,
    org_id: UUID,
    project_id: UUID,
    files: list[UploadFile],
    user_id: UUID | None,
    task_id: UUID | None = None,
) -> tuple[list[str], list[Document]]:
    """Validate + persist uploaded files; return (errors, docs-needing-preview).

    Does NOT commit — caller commits and enqueues previews.
    """
    allowed = settings.document_allowed_extensions_set
    max_bytes = settings.document_max_size_bytes
    errors: list[str] = []
    created_for_preview: list[Document] = []
    for up in files:
        name = _sanitize_filename(up.filename or "")
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
        if len(content) > max_bytes:
            errors.append(f"{name}: exceeds {max_bytes // (1024 * 1024)} MB limit")
            continue
        key = build_storage_key(org_id, project_id, name)
        sha = save_document(key, content)
        needs_preview = ext in _PREVIEW_EXTS
        doc = Document(
            org_id=org_id,
            project_id=project_id,
            task_id=task_id,
            filename=name[:512],
            content_type=(up.content_type or None),
            size_bytes=len(content),
            sha256=sha,
            storage_key=key,
            status=DocumentStatus.active,
            preview_status=(
                DocumentPreviewStatus.pending if needs_preview else DocumentPreviewStatus.none
            ),
            uploaded_by_user_id=user_id,
        )
        session.add(doc)
        if needs_preview:
            created_for_preview.append(doc)
    return errors, created_for_preview


def _enqueue_previews(docs: list[Document]) -> None:
    """Queue Office→PDF conversion for newly uploaded docs (best-effort).

    A broker outage must never fail the upload itself — the original file is
    already saved and downloadable; the preview is a bonus.
    """
    if not docs:
        return
    try:
        from app.tasks.document_preview import convert_document_preview

        for d in docs:
            convert_document_preview.delay(str(d.id))
    except Exception:
        pass


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
    view: str = Query(default="documents"),
    status: str = Query(default="all"),
) -> HTMLResponse:
    user, org_id, project = await _require_project(session, request, project_id)
    dedup_count, conflicts_count = await _get_counts(session)
    deal = await _deal_for_project(session, project)
    docs = await _load_docs(session, org_id, project_id, show)

    task_vms: list[dict] = []
    milestone_options: list[dict] = []
    if view == "tasks":
        mm = await _milestone_map(session, project_id)
        milestone_options = _milestone_options(mm)
        task_vms = await _build_task_vms(session, org_id, project_id, status, mm)

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
            "view": view,
            "status": status,
            "tasks": task_vms,
            "milestone_options": milestone_options,
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
    errors, created_for_preview = await _save_uploads(
        session, org_id, project_id, files, getattr(user, "id", None)
    )
    await session.commit()
    _enqueue_previews(created_for_preview)
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


# ---------------------------------------------------------------------------
# Task view (Phase 2)
# ---------------------------------------------------------------------------

_TASK_STATUSES = ("pending", "in_progress", "complete")


async def _milestone_map(session: DBSession, project_id: UUID) -> dict:
    ms = (
        await session.execute(select(Milestone).where(Milestone.project_id == project_id))
    ).scalars().all()
    return {m.id: m for m in ms}


def _milestone_options(milestone_map: dict) -> list[dict]:
    opts = []
    for m in milestone_map.values():
        mtype = m.milestone_type.value if hasattr(m.milestone_type, "value") else m.milestone_type
        opts.append({"id": str(m.id), "label": m.label or str(mtype).replace("_", " ").title()})
    return opts


async def _task_docs(session: DBSession, org_id: UUID, project_id: UUID, task_id: UUID):
    stmt = (
        select(Document)
        .where(
            Document.org_id == org_id,
            Document.project_id == project_id,
            Document.task_id == task_id,
            Document.status == DocumentStatus.active,
        )
        .order_by(Document.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


def _task_vm(task: DocumentTask, docs: list[Document], milestone_map: dict) -> dict:
    due = task.computed_due_date(milestone_map)
    status = task.status.value if hasattr(task.status, "value") else task.status
    return {
        "id": str(task.id),
        "title": task.title,
        "status": status,
        "status_label": str(status).replace("_", " ").title(),
        "notes": task.notes or "",
        "due_fmt": _fmt_date(due) if due else "—",
        "due_is_relative": task.due_milestone_id is not None,
        "due_date_val": task.due_date.isoformat() if task.due_date else "",
        "due_milestone_id": str(task.due_milestone_id) if task.due_milestone_id else "",
        "due_offset_days": task.due_offset_days or 0,
        "doc_count": len(docs),
        "documents": [_doc_vm(d) for d in docs],
    }


async def _load_tasks(session: DBSession, org_id: UUID, project_id: UUID, status: str | None):
    stmt = select(DocumentTask).where(
        DocumentTask.org_id == org_id, DocumentTask.project_id == project_id
    )
    if status in _TASK_STATUSES:
        stmt = stmt.where(DocumentTask.status == status)
    stmt = stmt.order_by(DocumentTask.created_at.asc())
    return list((await session.execute(stmt)).scalars().all())


async def _build_task_vms(
    session: DBSession, org_id: UUID, project_id: UUID, status: str, milestone_map: dict
) -> list[dict]:
    tasks = await _load_tasks(session, org_id, project_id, status)
    vms = []
    for t in tasks:
        docs = await _task_docs(session, org_id, project_id, t.id)
        vms.append(_task_vm(t, docs, milestone_map))
    return vms


async def _require_task(session: DBSession, request: Request, task_id: UUID):
    if not settings.documents_module_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    user = await _get_user(session, request)
    task = await session.get(DocumentTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Not found")
    if settings.org_isolation_enabled:
        user_org = getattr(user, "org_id", None)
        if user_org is None or task.org_id != user_org:
            raise HTTPException(status_code=404, detail="Not found")
    return user, task


def _parse_due_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


async def _tasks_list_response(
    request: Request, session: DBSession, org_id: UUID, project_id: UUID, status: str
):
    mm = await _milestone_map(session, project_id)
    vms = await _build_task_vms(session, org_id, project_id, status, mm)
    return templates.TemplateResponse(
        request,
        "partials/task_rows.html",
        {"project_id": str(project_id), "tasks": vms, "status": status or "all"},
    )


async def _task_card_response(
    request: Request, session: DBSession, org_id: UUID, project_id: UUID, task: DocumentTask
):
    mm = await _milestone_map(session, project_id)
    docs = await _task_docs(session, org_id, project_id, task.id)
    return templates.TemplateResponse(
        request,
        "partials/task_card.html",
        {"project_id": str(project_id), "t": _task_vm(task, docs, mm)},
    )


@router.get("/ui/projects/{project_id}/tasks", response_class=HTMLResponse)
async def tasks_list(
    request: Request,
    project_id: UUID,
    session: DBSession,
    status: str = Query(default="all"),
) -> HTMLResponse:
    user, org_id, project = await _require_project(session, request, project_id)
    return await _tasks_list_response(request, session, org_id, project_id, status)


@router.post("/ui/projects/{project_id}/tasks", response_class=HTMLResponse)
async def task_create(
    request: Request,
    project_id: UUID,
    session: DBSession,
    title: str = Form(...),
    status: str = Form(default="all"),
) -> HTMLResponse:
    user, org_id, project = await _require_project(session, request, project_id)
    title = (title or "").strip()
    if title:
        session.add(
            DocumentTask(
                org_id=org_id,
                project_id=project_id,
                title=title[:512],
                status=DocumentTaskStatus.pending,
            )
        )
        await session.commit()
    return await _tasks_list_response(request, session, org_id, project_id, status)


@router.get("/ui/tasks/{task_id}/edit", response_class=HTMLResponse)
async def task_edit_drawer(
    request: Request, task_id: UUID, session: DBSession
) -> HTMLResponse:
    user, task = await _require_task(session, request, task_id)
    mm = await _milestone_map(session, task.project_id)
    docs = await _task_docs(session, task.org_id, task.project_id, task.id)
    return templates.TemplateResponse(
        request,
        "partials/task_drawer.html",
        {
            "project_id": str(task.project_id),
            "t": _task_vm(task, docs, mm),
            "milestone_options": _milestone_options(mm),
        },
    )


@router.post("/ui/tasks/{task_id}", response_class=HTMLResponse)
async def task_update(
    request: Request,
    task_id: UUID,
    session: DBSession,
    title: str | None = Form(default=None),
    status: str | None = Form(default=None),
    notes: str | None = Form(default=None),
    due_kind: str | None = Form(default=None),
    due_date: str | None = Form(default=None),
    due_milestone_id: str | None = Form(default=None),
    due_offset_days: int = Form(default=0),
) -> HTMLResponse:
    user, task = await _require_task(session, request, task_id)
    if title is not None and title.strip():
        task.title = title.strip()[:512]
    if status in _TASK_STATUSES:
        task.status = DocumentTaskStatus(status)
    if notes is not None:
        task.notes = notes.strip() or None
    # Due date: explicit kind switch (hard-coded vs relative-to-milestone).
    if due_kind == "milestone" and due_milestone_id:
        try:
            task.due_milestone_id = UUID(due_milestone_id)
            task.due_offset_days = int(due_offset_days or 0)
            task.due_date = None
        except ValueError:
            pass
    elif due_kind == "date":
        task.due_date = _parse_due_date(due_date)
        task.due_milestone_id = None
        task.due_offset_days = 0
    elif due_kind == "none":
        task.due_date = None
        task.due_milestone_id = None
        task.due_offset_days = 0
    await session.commit()
    return await _task_card_response(request, session, task.org_id, task.project_id, task)


@router.post("/ui/tasks/{task_id}/delete", response_class=HTMLResponse)
async def task_delete(
    request: Request,
    task_id: UUID,
    session: DBSession,
    status: str = Form(default="all"),
) -> HTMLResponse:
    user, task = await _require_task(session, request, task_id)
    org_id, project_id = task.org_id, task.project_id
    # Detach documents from the task (keep the files); then delete the task.
    docs = (
        await session.execute(select(Document).where(Document.task_id == task_id))
    ).scalars().all()
    for d in docs:
        d.task_id = None
    await session.delete(task)
    await session.commit()
    return await _tasks_list_response(request, session, org_id, project_id, status)


@router.post("/ui/tasks/{task_id}/upload", response_class=HTMLResponse)
async def task_upload(
    request: Request,
    task_id: UUID,
    session: DBSession,
    files: list[UploadFile] = File(default=[]),
) -> HTMLResponse:
    user, task = await _require_task(session, request, task_id)
    errors, created_for_preview = await _save_uploads(
        session, task.org_id, task.project_id, files, getattr(user, "id", None), task_id=task.id
    )
    await session.commit()
    _enqueue_previews(created_for_preview)
    return await _task_card_response(request, session, task.org_id, task.project_id, task)


@router.get("/ui/tasks/{task_id}/download")
async def task_zip(request: Request, task_id: UUID, session: DBSession) -> StreamingResponse:
    """Zip all of a task's active documents plus a notes.txt of task metadata."""
    user, task = await _require_task(session, request, task_id)
    docs = await _task_docs(session, task.org_id, task.project_id, task.id)
    mm = await _milestone_map(session, task.project_id)
    due = task.computed_due_date(mm)
    status = task.status.value if hasattr(task.status, "value") else task.status

    notes_txt = (
        f"Task: {task.title}\r\n"
        f"Status: {str(status).replace('_', ' ').title()}\r\n"
        f"Due: {due.strftime('%Y-%m-%d') if due else 'not set'}\r\n"
        f"Documents: {len(docs)}\r\n"
        f"\r\nNotes:\r\n{task.notes or '(none)'}\r\n"
    )

    buf = io.BytesIO()
    seen: dict[str, int] = {}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("notes.txt", notes_txt)
        for d in docs:
            name = d.filename or "file"
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
    safe = _safe_header_filename(task.title).replace(" ", "_") or "task"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe}.zip"'},
    )


# ---------------------------------------------------------------------------
# External sharing (Phase 3)
# ---------------------------------------------------------------------------

def _share_url(request: Request, token: str) -> str:
    return f"{str(request.base_url).rstrip('/')}/share/{token}"


def _share_vm(share: DocumentShare, request: Request) -> dict:
    token = make_doc_share_token(share.id)
    return {
        "id": str(share.id),
        "label": share.label or "",
        "url": _share_url(request, token),
        "revoked": share.revoked,
    }


async def _load_shares(session: DBSession, org_id: UUID, project_id: UUID):
    stmt = (
        select(DocumentShare)
        .where(
            DocumentShare.org_id == org_id,
            DocumentShare.project_id == project_id,
            DocumentShare.revoked.is_(False),
        )
        .order_by(DocumentShare.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def _share_panel_response(
    request: Request, session: DBSession, org_id: UUID, project_id: UUID
):
    shares = await _load_shares(session, org_id, project_id)
    return templates.TemplateResponse(
        request,
        "partials/share_panel.html",
        {"project_id": str(project_id), "shares": [_share_vm(s, request) for s in shares]},
    )


@router.get("/ui/projects/{project_id}/shares", response_class=HTMLResponse)
async def shares_list(
    request: Request, project_id: UUID, session: DBSession
) -> HTMLResponse:
    user, org_id, project = await _require_project(session, request, project_id)
    return await _share_panel_response(request, session, org_id, project_id)


@router.post("/ui/projects/{project_id}/shares", response_class=HTMLResponse)
async def share_create(
    request: Request,
    project_id: UUID,
    session: DBSession,
    label: str = Form(default=""),
) -> HTMLResponse:
    user, org_id, project = await _require_project(session, request, project_id)
    session.add(
        DocumentShare(
            org_id=org_id,
            project_id=project_id,
            label=(label.strip() or None),
            created_by_user_id=getattr(user, "id", None),
        )
    )
    await session.commit()
    return await _share_panel_response(request, session, org_id, project_id)


@router.post("/ui/shares/{share_id}/revoke", response_class=HTMLResponse)
async def share_revoke(
    request: Request, share_id: UUID, session: DBSession
) -> HTMLResponse:
    if not settings.documents_module_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    share = await session.get(DocumentShare, share_id)
    if share is None:
        raise HTTPException(status_code=404, detail="Not found")
    # Authorize via the share's project — identical ownership path as create,
    # so cross-project (and cross-org) revoke is rejected with 404.
    await _require_project(session, request, share.project_id)
    share.revoked = True
    share.revoked_at = datetime.now(timezone.utc)
    await session.commit()
    return await _share_panel_response(request, session, share.org_id, share.project_id)


# ── Guest access (token-gated, no session) ─────────────────────────────────

async def _resolve_share(session: DBSession, token: str) -> tuple[DocumentShare, Project]:
    """Resolve a share token to (share, project). 404 if invalid/revoked/gone."""
    if not settings.documents_module_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    share_id = load_doc_share_token(token)
    if share_id is None:
        raise HTTPException(status_code=404, detail="This link is invalid or expired.")
    share = await session.get(DocumentShare, share_id)
    if share is None or share.revoked:
        raise HTTPException(status_code=404, detail="This link has been turned off.")
    project = await session.get(Project, share.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Not found")
    return share, project


async def _guest_require_document(
    session: DBSession, share: DocumentShare, document_id: UUID
) -> Document:
    doc = await session.get(Document, document_id)
    if (
        doc is None
        or doc.project_id != share.project_id
        or doc.org_id != share.org_id
        or doc.status != DocumentStatus.active
    ):
        raise HTTPException(status_code=404, detail="Not found")
    return doc


@router.get("/share/{token}", response_class=HTMLResponse)
async def guest_documents_page(
    request: Request,
    token: str,
    session: DBSession,
    view: str = Query(default="documents"),
    status: str = Query(default="all"),
) -> HTMLResponse:
    share, project = await _resolve_share(session, token)
    docs = await _load_docs(session, share.org_id, project.id, "active")
    task_vms: list[dict] = []
    if view == "tasks":
        mm = await _milestone_map(session, project.id)
        task_vms = await _build_task_vms(session, share.org_id, project.id, status, mm)
    return templates.TemplateResponse(
        request,
        "share_documents.html",
        {
            "token": token,
            "project_name": project.name,
            "documents": [_doc_vm(d) for d in docs],
            "view": view,
            "status": status,
            "tasks": task_vms,
            "max_size_mb": settings.document_max_size_bytes // (1024 * 1024),
            "allowed_ext": ",".join(sorted(settings.document_allowed_extensions_set)),
        },
    )


@router.post("/share/{token}/upload", response_class=HTMLResponse)
async def guest_upload(
    request: Request,
    token: str,
    session: DBSession,
    files: list[UploadFile] = File(default=[]),
) -> HTMLResponse:
    share, project = await _resolve_share(session, token)
    errors, created_for_preview = await _save_uploads(
        session, share.org_id, project.id, files, None
    )
    await session.commit()
    _enqueue_previews(created_for_preview)
    docs = await _load_docs(session, share.org_id, project.id, "active")
    return templates.TemplateResponse(
        request,
        "partials/share_doc_rows.html",
        {"token": token, "documents": [_doc_vm(d) for d in docs], "errors": errors},
    )


@router.get("/share/{token}/documents/{document_id}/download")
async def guest_download(
    request: Request, token: str, document_id: UUID, session: DBSession
) -> StreamingResponse:
    share, project = await _resolve_share(session, token)
    doc = await _guest_require_document(session, share, document_id)
    try:
        data = open_document(doc.storage_key)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File missing")
    return StreamingResponse(
        iter([data]),
        media_type=doc.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{_safe_header_filename(doc.filename)}"'
        },
    )


@router.get("/share/{token}/documents/{document_id}/view")
async def guest_view(
    request: Request, token: str, document_id: UUID, session: DBSession
) -> StreamingResponse:
    share, project = await _resolve_share(session, token)
    doc = await _guest_require_document(session, share, document_id)
    ext = _ext(doc.filename)
    if ext in _INLINE_MEDIA:
        key, media = doc.storage_key, (doc.content_type or "application/octet-stream")
    elif doc.preview_status == DocumentPreviewStatus.ready and doc.preview_key:
        key, media = doc.preview_key, "application/pdf"
    else:
        raise HTTPException(status_code=404, detail="No preview available")
    try:
        data = open_document(key)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File missing")
    return StreamingResponse(
        iter([data]),
        media_type=media,
        headers={
            "Content-Disposition": f'inline; filename="{_safe_header_filename(doc.filename)}"'
        },
    )


@router.get("/share/{token}/zip")
async def guest_zip(request: Request, token: str, session: DBSession) -> StreamingResponse:
    share, project = await _resolve_share(session, token)
    docs = await _load_docs(session, share.org_id, project.id, "active")
    buf = io.BytesIO()
    seen: dict[str, int] = {}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for d in docs:
            name = d.filename or "file"
            if name in seen:
                seen[name] += 1
                stem, fext = os.path.splitext(name)
                name = f"{stem} ({seen[name]}){fext}"
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


@router.get("/share/{token}/tasks", response_class=HTMLResponse)
async def guest_tasks(
    request: Request, token: str, session: DBSession, status: str = Query(default="all")
) -> HTMLResponse:
    share, project = await _resolve_share(session, token)
    mm = await _milestone_map(session, project.id)
    vms = await _build_task_vms(session, share.org_id, project.id, status, mm)
    return templates.TemplateResponse(
        request,
        "partials/share_task_rows.html",
        {"token": token, "tasks": vms, "status": status or "all"},
    )


@router.post("/share/{token}/tasks/{task_id}/upload", response_class=HTMLResponse)
async def guest_task_upload(
    request: Request,
    token: str,
    task_id: UUID,
    session: DBSession,
    files: list[UploadFile] = File(default=[]),
) -> HTMLResponse:
    share, project = await _resolve_share(session, token)
    task = await session.get(DocumentTask, task_id)
    if task is None or task.project_id != project.id or task.org_id != share.org_id:
        raise HTTPException(status_code=404, detail="Not found")
    errors, created_for_preview = await _save_uploads(
        session, share.org_id, project.id, files, None, task_id=task.id
    )
    await session.commit()
    _enqueue_previews(created_for_preview)
    mm = await _milestone_map(session, project.id)
    docs = await _task_docs(session, share.org_id, project.id, task.id)
    return templates.TemplateResponse(
        request,
        "partials/share_task_card.html",
        {"token": token, "t": _task_vm(task, docs, mm)},
    )


@router.get("/share/{token}/tasks/{task_id}/download")
async def guest_task_zip(
    request: Request, token: str, task_id: UUID, session: DBSession
) -> StreamingResponse:
    share, project = await _resolve_share(session, token)
    task = await session.get(DocumentTask, task_id)
    if task is None or task.project_id != project.id or task.org_id != share.org_id:
        raise HTTPException(status_code=404, detail="Not found")
    docs = await _task_docs(session, share.org_id, project.id, task.id)
    mm = await _milestone_map(session, project.id)
    due = task.computed_due_date(mm)
    status = task.status.value if hasattr(task.status, "value") else task.status
    notes_txt = (
        f"Task: {task.title}\r\n"
        f"Status: {str(status).replace('_', ' ').title()}\r\n"
        f"Due: {due.strftime('%Y-%m-%d') if due else 'not set'}\r\n"
        f"Documents: {len(docs)}\r\n"
        f"\r\nNotes:\r\n{task.notes or '(none)'}\r\n"
    )
    buf = io.BytesIO()
    seen: dict[str, int] = {}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("notes.txt", notes_txt)
        for d in docs:
            name = d.filename or "file"
            if name in seen:
                seen[name] += 1
                stem, fext = os.path.splitext(name)
                name = f"{stem} ({seen[name]}){fext}"
            else:
                seen[name] = 0
            try:
                zf.writestr(name, open_document(d.storage_key))
            except FileNotFoundError:
                continue
    buf.seek(0)
    safe = _safe_header_filename(task.title).replace(" ", "_") or "task"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe}.zip"'},
    )
