"""Unit tests for the document-room disk storage layer.

Covers the save/open/delete roundtrip, the sha256 digest, idempotent delete,
and the path-traversal guard.
"""

from __future__ import annotations

import hashlib

import pytest

from app.storage import documents as storage


pytestmark = pytest.mark.unit


@pytest.fixture
def storage_root(tmp_path, monkeypatch):
    """Point the storage layer at a throwaway tmp dir for the test."""
    monkeypatch.setattr(
        "app.config.settings.document_storage_path", str(tmp_path), raising=True
    )
    return tmp_path


def test_save_open_roundtrip_and_sha256(storage_root):
    content = b"%PDF-1.4 fake lease bytes"
    key = storage.build_storage_key("org1", "proj1", "Lease.PDF")
    digest = storage.save_document(key, content)

    assert key.endswith(".pdf")  # extension preserved + lowercased
    assert digest == hashlib.sha256(content).hexdigest()
    assert storage.document_exists(key) is True
    assert storage.open_document(key) == content


def test_build_storage_key_is_unique_per_call(storage_root):
    a = storage.build_storage_key("o", "p", "x.png")
    b = storage.build_storage_key("o", "p", "x.png")
    assert a != b
    assert a.startswith("o/p/") and b.startswith("o/p/")


def test_delete_is_idempotent(storage_root):
    key = storage.build_storage_key("org", "proj", "a.png")
    storage.save_document(key, b"img")
    storage.delete_document(key)
    assert storage.document_exists(key) is False
    # Deleting again must not raise.
    storage.delete_document(key)


def test_path_traversal_is_blocked(storage_root):
    with pytest.raises(ValueError):
        storage.open_document("../../etc/passwd")
    with pytest.raises(ValueError):
        storage.save_document("../escape.txt", b"nope")
