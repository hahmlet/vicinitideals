"""FastAPI dependencies for database access and header-based identity."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db as db_get_db
from app.models.org import User


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


async def get_current_user(user_id: CurrentUserId, session: DBSession) -> User:
    """Resolve the caller's identity to a ``User`` row that exists, or 401.

    ``get_current_user_id`` only checks that the X-User-ID header (or session
    cookie) is shaped like a UUID. A route that writes that id into a column
    with a foreign key to ``users`` must depend on this instead: an unknown id
    otherwise reaches the INSERT/UPDATE and surfaces as an unhandled 500. 401
    matches ``get_current_user_id`` (no identity) and the settings router's
    ``_get_user_or_401`` (identity that names no user).
    """
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def get_verified_user_id(user: Annotated[User, Depends(get_current_user)]) -> UUID:
    """The caller's user id, guaranteed to name an existing ``users`` row."""
    return user.id


CurrentUser = Annotated[User, Depends(get_current_user)]
VerifiedUserId = Annotated[UUID, Depends(get_verified_user_id)]

__all__ = [
    "CurrentUser",
    "CurrentUserId",
    "DBSession",
    "VerifiedUserId",
    "get_current_user",
    "get_current_user_id",
    "get_db",
    "get_verified_user_id",
]
