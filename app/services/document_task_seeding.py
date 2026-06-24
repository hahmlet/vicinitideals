"""Seed org-default document tasks onto a newly-created Project.

Called at each Project-creation site (deal creation, add-project). Templates
are name-only (see :class:`DocumentTaskTemplate`): each produces one pending
``DocumentTask`` with no due date. No-op when the org has no templates. Does
NOT commit — the caller's transaction owns the flush/commit.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import DocumentTask, DocumentTaskStatus, DocumentTaskTemplate


async def seed_default_tasks(
    session: AsyncSession, org_id: uuid.UUID, project_id: uuid.UUID
) -> int:
    """Create a DocumentTask per org template for this project. Returns count.

    Best-effort and side-effect-light: never raises on an empty template set,
    and adds rows to the session without committing.
    """
    if org_id is None or project_id is None:
        return 0
    templates = list(
        (
            await session.execute(
                select(DocumentTaskTemplate)
                .where(DocumentTaskTemplate.org_id == org_id)
                .order_by(
                    DocumentTaskTemplate.sort_order.asc(),
                    DocumentTaskTemplate.created_at.asc(),
                )
            )
        ).scalars()
    )
    for tmpl in templates:
        session.add(
            DocumentTask(
                org_id=org_id,
                project_id=project_id,
                title=tmpl.title,
                status=DocumentTaskStatus.pending,
            )
        )
    return len(templates)
