"""Transactional email module (Resend).

Public API:
- ``send_verification_email(to, name, verify_url)``
- ``send_password_reset_email(to, name, reset_url)``
- ``make_email_verification_token(user_id)``
- ``load_email_verification_token(token)``
- ``make_password_reset_token(user_id, password_hash_prefix)``
- ``load_password_reset_token(token)``

The sender is a thin async wrapper over Resend's REST API (no SDK
dependency — we already have httpx).  If ``settings.resend_api_key`` is
empty, sends are logged but not transmitted (safe for local dev).
"""

from app.emails.sender import (
    send_password_reset_email,
    send_verification_email,
)
from app.emails.tokens import (
    load_email_verification_token,
    load_password_reset_token,
    make_email_verification_token,
    make_password_reset_token,
)

__all__ = [
    "load_email_verification_token",
    "load_password_reset_token",
    "make_email_verification_token",
    "make_password_reset_token",
    "send_password_reset_email",
    "send_verification_email",
]
