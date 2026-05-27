"""CSRF protection — stateless signed-token approach.

Token = itsdangerous.URLSafeSerializer(secret_key, salt="csrf-v1").dumps(user_id).
No second cookie required; the session cookie is the credential and the
CSRF token proves the request originated from a page rendered by this
server (a cross-origin attacker cannot forge the token without knowing
secret_key).

Flow:
  1. On every authenticated request, middleware sets
     ``request.state.csrf_token = make_csrf_token(user_id_str)``.
  2. The base Jinja2 template injects the token into every HTMX request
     via ``hx-headers='{"X-CSRF-Token": "{{ request.state.csrf_token }}"}'``
     on the ``<body>`` tag.
  3. On every state-mutating request (POST/PUT/PATCH/DELETE) to a
     non-exempt path, middleware validates the ``X-CSRF-Token`` header
     against the session user ID.

Exempt paths (login, register, forgot-password, etc.) skip validation
because they are either unauthenticated flows or handle their own
protection.
"""

from __future__ import annotations

import logging

from itsdangerous import BadSignature, URLSafeSerializer

from app.config import settings

logger = logging.getLogger(__name__)

CSRF_HEADER = "x-csrf-token"   # HTTP header name (lowercase, canonical form)
CSRF_FIELD = "csrf_token"      # HTML form field name (fallback)
_SALT = "csrf-v1"

_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _signer() -> URLSafeSerializer:
    return URLSafeSerializer(settings.secret_key, salt=_SALT)


def make_csrf_token(user_id: str) -> str:
    """Return a signed CSRF token bound to *user_id*."""
    return _signer().dumps(user_id)


def validate_csrf_token(token: str | None, user_id: str) -> bool:
    """Return True iff *token* is a valid CSRF token for *user_id*.

    Logs a warning on failure (bad/missing token) for ops visibility.
    """
    if not token:
        logger.warning("csrf_token_missing user_id=%s", user_id)
        return False
    try:
        payload = _signer().loads(token)
        if payload == user_id:
            return True
        logger.warning("csrf_token_mismatch expected=%s got_payload=%s", user_id, payload)
        return False
    except BadSignature:
        logger.warning("csrf_token_bad_signature user_id=%s", user_id)
        return False
