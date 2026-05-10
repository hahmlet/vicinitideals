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


async def get_current_user_id(
    request: Request,
    x_user_id: Annotated[str | None, Header(alias="X-User-ID")] = None,
) -> UUID:
    """Return user UUID from request state, X-User-ID header, or session cookie."""
    candidate = getattr(request.state, "user_id", None) or x_user_id
    if candidate:
        try:
            return UUID(str(candidate))
        except ValueError as exc:  # pragma: no cover
            raise HTTPException(status_code=400, detail="Invalid X-User-ID header") from exc

    # Browser HTMX requests carry a signed session cookie instead of the header.
    from app.api.auth import COOKIE_NAME, decode_session_token
    token = request.cookies.get(COOKIE_NAME)
    if token:
        uid = decode_session_token(token)
        if uid is not None:
            return uid

    raise HTTPException(status_code=401, detail="Authentication required")


DBSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]

__all__ = ["CurrentUserId", "DBSession", "get_current_user_id", "get_db"]
