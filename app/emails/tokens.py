"""Signed tokens for email verification, password reset, and org invites.

Reuses ``itsdangerous.URLSafeTimedSerializer`` (same library the session
cookie uses) so there's no new crypto dependency.  Each token type has a
distinct salt so tokens cannot be cross-used — a verify token cannot be
replayed as a reset token and vice-versa.

### Email verification token
- Payload: ``str(user_id)``
- Max age: ``settings.email_verify_token_max_age_seconds`` (24h default)
- Idempotent: clicking the link twice just shows "already verified"

### Password reset token
- Payload: ``f"{user_id}:{password_hash_prefix}"`` where prefix is the first
  16 chars of the current ``hashed_password``.  Binding the token to the
  password hash makes the token single-use: once the user resets their
  password, the hash changes, the prefix no longer matches, and the old
  token is rejected even if replayed within its expiry window.
- Max age: ``settings.password_reset_token_max_age_seconds`` (30 min default)

### Org invite token
- Payload: ``f"{org_id}:{email}"`` — binds the invite to a specific org and email.
- Max age: ``settings.invite_token_max_age_seconds`` (7 days default)
"""

from __future__ import annotations

import uuid

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings

_VERIFY_SALT = "email-verify"
_RESET_SALT = "password-reset"
_INVITE_SALT = "org-invite"
_DOC_SHARE_SALT = "doc-share"


def _signer(salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt=salt)


# ── Email verification ───────────────────────────────────────────────────────

def make_email_verification_token(user_id: uuid.UUID) -> str:
    return _signer(_VERIFY_SALT).dumps(str(user_id))


def load_email_verification_token(token: str) -> uuid.UUID | None:
    """Return the user_id if the token is valid and not expired, else None."""
    try:
        raw = _signer(_VERIFY_SALT).loads(
            token,
            max_age=settings.email_verify_token_max_age_seconds,
        )
        return uuid.UUID(raw)
    except (SignatureExpired, BadSignature, ValueError):
        return None


# ── Password reset ───────────────────────────────────────────────────────────

def make_password_reset_token(
    user_id: uuid.UUID,
    hashed_password: str,
) -> str:
    """Bind the token to the current password hash so it's single-use.

    Once the user resets, ``hashed_password`` changes and the old token's
    embedded prefix stops matching.
    """
    prefix = (hashed_password or "")[:16]
    payload = f"{user_id}:{prefix}"
    return _signer(_RESET_SALT).dumps(payload)


def load_password_reset_token(
    token: str,
    current_hashed_password: str,
) -> uuid.UUID | None:
    """Validate a reset token against the current user password hash.

    Returns the user_id only if:
    - the signature is valid (not tampered)
    - the token has not expired
    - the embedded password hash prefix still matches the user's current hash
      (i.e. the password hasn't been changed since the token was issued)
    """
    try:
        raw = _signer(_RESET_SALT).loads(
            token,
            max_age=settings.password_reset_token_max_age_seconds,
        )
    except (SignatureExpired, BadSignature):
        return None

    if ":" not in raw:
        return None
    user_id_str, prefix = raw.split(":", 1)
    current_prefix = (current_hashed_password or "")[:16]
    if prefix != current_prefix:
        return None
    try:
        return uuid.UUID(user_id_str)
    except ValueError:
        return None


# ── Org invite ────────────────────────────────────────────────────────────────

def make_invite_token(org_id: uuid.UUID, email: str) -> str:
    payload = f"{org_id}:{email.lower().strip()}"
    return _signer(_INVITE_SALT).dumps(payload)


def load_invite_token(token: str) -> tuple[uuid.UUID, str] | None:
    """Return (org_id, email) if token is valid and not expired, else None."""
    try:
        raw = _signer(_INVITE_SALT).loads(
            token,
            max_age=settings.invite_token_max_age_seconds,
        )
    except (SignatureExpired, BadSignature):
        return None
    if ":" not in raw:
        return None
    org_id_str, email = raw.split(":", 1)
    try:
        return uuid.UUID(org_id_str), email
    except ValueError:
        return None


# ── Document share ────────────────────────────────────────────────────────────

def make_doc_share_token(share_id: uuid.UUID) -> str:
    return _signer(_DOC_SHARE_SALT).dumps(str(share_id))


def load_doc_share_token(token: str) -> uuid.UUID | None:
    """Return the DocumentShare id if the token is valid + unexpired, else None.

    Signature/expiry only — revocation is checked against the DB row by the
    caller, so a revoked share fails even within the token's expiry window.
    """
    try:
        raw = _signer(_DOC_SHARE_SALT).loads(
            token,
            max_age=settings.doc_share_token_max_age_seconds,
        )
        return uuid.UUID(raw)
    except (SignatureExpired, BadSignature, ValueError):
        return None
