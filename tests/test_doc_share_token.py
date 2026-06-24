"""Unit tests for document-share signed tokens."""

from __future__ import annotations

import uuid

import pytest

from app.emails.tokens import load_doc_share_token, make_doc_share_token

pytestmark = pytest.mark.unit


def test_roundtrip():
    sid = uuid.uuid4()
    assert load_doc_share_token(make_doc_share_token(sid)) == sid


def test_garbage_rejected():
    assert load_doc_share_token("not-a-real-token") is None


def test_cross_salt_rejected():
    # A token minted for a different purpose must not load as a share token.
    from app.emails.tokens import make_email_verification_token

    other = make_email_verification_token(uuid.uuid4())
    assert load_doc_share_token(other) is None
