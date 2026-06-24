"""Local-disk storage for Project document-room files.

Layout on disk::

    {settings.document_storage_path}/{org_id}/{project_id}/{uuid}{ext}

The root lives under the existing ``./data:/app/data`` Docker volume (mounted on
the API and the analysis worker). Postgres owns the metadata row
(:class:`app.models.document.Document`); this module owns the bytes.

``storage_key`` is the path *relative* to the storage root and is what gets
persisted on the ``Document`` row. All public helpers take a ``storage_key`` and
resolve it against the root, guarding against path traversal.
"""

from __future__ import annotations

import hashlib
import os
import uuid as _uuid
from pathlib import Path

from app.config import settings


def _root() -> Path:
    return Path(settings.document_storage_path)


def compute_sha256(content: bytes) -> str:
    """Return the hex SHA-256 digest of ``content``."""
    return hashlib.sha256(content).hexdigest()


def build_storage_key(org_id: object, project_id: object, filename: str) -> str:
    """Build a fresh, collision-free relative storage key for a new upload.

    The original ``filename`` is used only to preserve the file extension; the
    stored name is a random UUID so user-supplied names can never cause
    collisions or path traversal.
    """
    ext = os.path.splitext(filename or "")[1].lower()[:16]
    return f"{org_id}/{project_id}/{_uuid.uuid4().hex}{ext}"


def _abs(storage_key: str) -> Path:
    """Resolve a storage key to an absolute path, refusing to escape the root."""
    root = _root().resolve()
    target = (root / storage_key).resolve()
    if not (target == root or root in target.parents):
        raise ValueError(f"storage_key escapes storage root: {storage_key!r}")
    return target


def save_document(storage_key: str, content: bytes) -> str:
    """Write ``content`` to ``storage_key`` (creating parents); return sha256."""
    target = _abs(storage_key)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return compute_sha256(content)


def open_document(storage_key: str) -> bytes:
    """Read and return the bytes stored at ``storage_key``."""
    return _abs(storage_key).read_bytes()


def document_exists(storage_key: str) -> bool:
    return _abs(storage_key).exists()


def delete_document(storage_key: str) -> None:
    """Delete the file at ``storage_key``. No-op if already gone."""
    try:
        _abs(storage_key).unlink()
    except FileNotFoundError:
        pass
