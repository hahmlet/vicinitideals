"""FastAPI dependencies for database access and header-based identity."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db as db_get_db


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield the shared async database session dependency."""
    async for session in db_get_db():
        yield session


def get_current_user_id(
    request: Request,
    x_user_id: Annotated[str | None, Header(alias="X-User-ID")] = None,
) -> UUID:
    """Return the validated user UUID from request state or the raw header."""
    candidate = getattr(request.state, "user_id", None) or x_user_id
    if not candidate:
        raise HTTPException(status_code=400, detail="Missing X-User-ID header")

    try:
        return UUID(str(candidate))
    except ValueError as exc:  # pragma: no cover - middleware blocks invalid values first
        raise HTTPException(status_code=400, detail="Invalid X-User-ID header") from exc


DBSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]

__all__ = ["CurrentUserId", "DBSession", "get_current_user_id", "get_db"]
