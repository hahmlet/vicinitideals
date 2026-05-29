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

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select

from app.config import settings

if TYPE_CHECKING:
    from fastapi import Request
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.org import User

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ---------------------------------------------------------------------------
# Session tokens
# ---------------------------------------------------------------------------

COOKIE_NAME = "vd_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 days


def _signer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt="session")


def create_session_token(
    user_id: uuid.UUID,
    *,
    email_verified: bool | None = None,
) -> str:
    """Sign a session token containing the user's UUID.

    When email_verified is provided, the claim is embedded so the
    middleware gate can enforce verification without a DB read. Legacy
    callers that omit it produce a UUID-only token, which the middleware
    intentionally bypasses (back-compat for existing sessions).
    """
    if email_verified is None:
        return _signer().dumps(str(user_id))
    return _signer().dumps({"uid": str(user_id), "ev": bool(email_verified)})


def _decode_session_payload(token: str) -> dict | str | None:
    try:
        return _signer().loads(token, max_age=SESSION_MAX_AGE)
    except (SignatureExpired, BadSignature):
        return None


def decode_session_token(token: str) -> uuid.UUID | None:
    """Verify and decode a session token; returns UUID or None on failure."""
    raw = _decode_session_payload(token)
    if raw is None:
        return None
    try:
        if isinstance(raw, dict):
            uid_raw = raw.get("uid")
            if uid_raw is None:
                return None
            return uuid.UUID(str(uid_raw))
        return uuid.UUID(str(raw))
    except ValueError:
        return None


def decode_session_email_verified(token: str) -> bool | None:
    """Return signed email-verified claim when present, else None.

    Legacy UUID-only tokens have no claim; the caller should treat
    None as "not enforced" rather than "unverified".
    """
    raw = _decode_session_payload(token)
    if isinstance(raw, dict) and "ev" in raw:
        return bool(raw.get("ev"))
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
