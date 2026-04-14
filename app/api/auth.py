"""Authentication helpers — password hashing and session cookie management.

Uses passlib/bcrypt for password hashing and itsdangerous for signed
session tokens stored in an HttpOnly cookie.

Session flow:
  POST /login → verify password → create_session_token(user_id) →
    set HttpOnly cookie → redirect to /deals

  Every request → read cookie → decode_session_token → load User

  POST /logout → clear cookie → redirect to /login
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from passlib.context import CryptContext
from sqlalchemy import select

from app.config import settings

if TYPE_CHECKING:
    from fastapi import Request
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


# ---------------------------------------------------------------------------
# Session tokens
# ---------------------------------------------------------------------------

COOKIE_NAME = "vd_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 days


def _signer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt="session")


def create_session_token(user_id: uuid.UUID) -> str:
    """Sign a session token containing the user's UUID."""
    return _signer().dumps(str(user_id))


def decode_session_token(token: str) -> uuid.UUID | None:
    """Verify and decode a session token; returns UUID or None on failure."""
    try:
        raw = _signer().loads(token, max_age=SESSION_MAX_AGE)
        return uuid.UUID(raw)
    except (SignatureExpired, BadSignature, ValueError):
        return None


# ---------------------------------------------------------------------------
# Request-level helper
# ---------------------------------------------------------------------------

async def get_current_user_id(request: "Request") -> uuid.UUID | None:
    """Extract and verify the session cookie; return user UUID or None."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    return decode_session_token(token)


async def get_current_user(
    request: "Request",
    session: "AsyncSession",
) -> "User | None":  # type: ignore[name-defined]
    """Load the User ORM object from the session cookie, or None."""
    from app.models.org import User

    user_id = await get_current_user_id(request)
    if user_id is None:
        return None
    return await session.get(User, user_id)
