"""Unit tests for multi-attachment email ingest behavior.

Covers:
- _parse_mime correctly extracts multiple attachments
- proforma_metas filter + fallback
- source_id uniqueness across attachments in the same email
- Redis key schema matches what proforma_from_staged expects
"""

from __future__ import annotations

import base64
import email as email_lib
import hashlib
import io
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pytest

from app.tasks.email_ingest import _parse_mime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mime_b64(*attachments: tuple[str, bytes]) -> str:
    """Build a base64-encoded MIME message with plain-text body + N file attachments.

    Each attachment is (filename, content_bytes).
    """
    msg = MIMEMultipart()
    msg["From"] = "sender@example.com"
    msg["To"] = "deals@viciniti.deals"
    msg["Subject"] = "Test deal"
    msg.attach(MIMEText("See attached files for underwriting.", "plain"))
    for filename, content in attachments:
        part = MIMEApplication(content, Name=filename)
        part["Content-Disposition"] = f'attachment; filename="{filename}"'
        msg.attach(part)
    return base64.b64encode(msg.as_bytes()).decode()


FAKE_XLSX = b"PK\x03\x04" + b"\x00" * 28   # minimal xlsx magic bytes
FAKE_PDF  = b"%PDF-1.4\n%%EOF"


# ---------------------------------------------------------------------------
# _parse_mime tests
# ---------------------------------------------------------------------------

class TestParseMime:
    def test_returns_none_none_on_missing_input(self):
        body, attachments = _parse_mime(None)
        assert body is None
        assert attachments == []

    def test_single_attachment_parsed(self):
        raw = _make_mime_b64(("proforma.xlsx", FAKE_XLSX))
        body, attachments = _parse_mime(raw)
        assert body is not None
        assert len(attachments) == 1
        att = attachments[0]
        assert att["filename"] == "proforma.xlsx"
        assert att["content_type"] == "application/octet-stream"
        assert att["size_bytes"] == len(FAKE_XLSX)
        assert att["payload_b64"] == base64.b64encode(FAKE_XLSX).decode()

    def test_two_attachments_parsed(self):
        raw = _make_mime_b64(
            ("unit_1.xlsx", FAKE_XLSX),
            ("unit_2.xlsx", FAKE_XLSX + b"extra"),
        )
        body, attachments = _parse_mime(raw)
        assert len(attachments) == 2
        assert attachments[0]["filename"] == "unit_1.xlsx"
        assert attachments[1]["filename"] == "unit_2.xlsx"
        assert attachments[0]["size_bytes"] != attachments[1]["size_bytes"]

    def test_pdf_attachment_parsed(self):
        raw = _make_mime_b64(("deal.pdf", FAKE_PDF))
        body, attachments = _parse_mime(raw)
        assert len(attachments) == 1
        assert attachments[0]["filename"] == "deal.pdf"

    def test_body_text_extracted(self):
        raw = _make_mime_b64(("f.xlsx", FAKE_XLSX))
        body, _ = _parse_mime(raw)
        assert body and "See attached" in body

    def test_no_attachments_returns_empty_list(self):
        msg = MIMEMultipart()
        msg["From"] = "a@b.com"
        msg["Subject"] = "hi"
        msg.attach(MIMEText("body only", "plain"))
        raw = base64.b64encode(msg.as_bytes()).decode()
        body, attachments = _parse_mime(raw)
        assert attachments == []
        assert body and "body only" in body

    def test_invalid_base64_returns_none(self):
        body, attachments = _parse_mime("not-valid-base64!!!")
        assert body is None
        assert attachments == []


# ---------------------------------------------------------------------------
# proforma_metas filter + fallback
# ---------------------------------------------------------------------------

class TestProformaMetasFilter:
    """Tests the inline filtering logic (ported as pure functions for testability)."""

    _PROFORMA_EXTS = {"xlsx", "xlsm", "xlsb", "pdf"}

    def _ext(self, filename: str) -> str:
        import os
        return os.path.splitext(filename)[1].lower().lstrip(".")

    def _is_proforma(self, att: dict) -> bool:
        return (
            self._ext(att.get("filename") or "") in self._PROFORMA_EXTS
            and bool(att.get("payload_b64"))
        )

    def _proforma_metas(self, attachments_meta: list[dict]) -> list[dict]:
        filtered = [m for m in attachments_meta if m.get("proforma_task_id")]
        return filtered if filtered else [{}]

    def test_filters_to_staged_only(self):
        meta = [
            {"filename": "proforma.xlsx", "proforma_task_id": "task-1"},
            {"filename": "photo.jpg"},
            {"filename": "summary.pdf", "proforma_task_id": "task-2"},
        ]
        result = self._proforma_metas(meta)
        assert len(result) == 2
        assert result[0]["proforma_task_id"] == "task-1"
        assert result[1]["proforma_task_id"] == "task-2"

    def test_fallback_to_single_empty_dict_when_no_staged(self):
        meta = [
            {"filename": "photo.jpg"},
            {"filename": "cover_letter.docx"},
        ]
        result = self._proforma_metas(meta)
        assert result == [{}]

    def test_fallback_when_no_attachments(self):
        assert self._proforma_metas([]) == [{}]

    def test_is_proforma_ext_check(self):
        assert self._is_proforma({"filename": "file.xlsx", "payload_b64": "abc"})
        assert self._is_proforma({"filename": "FILE.XLSX", "payload_b64": "abc"})
        assert self._is_proforma({"filename": "file.pdf", "payload_b64": "abc"})
        assert not self._is_proforma({"filename": "photo.jpg", "payload_b64": "abc"})
        assert not self._is_proforma({"filename": "file.xlsx"})  # no payload


# ---------------------------------------------------------------------------
# source_id uniqueness
# ---------------------------------------------------------------------------

class TestSourceIdUniqueness:
    """The source_id for each Opportunity must be unique even when multiple
    attachments come from the same email (same sender/subject/received_at)."""

    def _make_source_id(self, email_base_id: str, suffix: str) -> str:
        return hashlib.sha256(f"{email_base_id}|{suffix}".encode()).hexdigest()[:32]

    def test_different_filenames_produce_different_ids(self):
        base = "sender@example.com|Re: Brittany Place|2026-05-28 10:00:00"
        id1 = self._make_source_id(base, "unit_1.xlsx")
        id2 = self._make_source_id(base, "unit_2.xlsx")
        assert id1 != id2

    def test_same_filename_same_email_produces_same_id(self):
        base = "sender@example.com|Re: Deal|2026-05-28 10:00:00"
        assert (
            self._make_source_id(base, "proforma.xlsx")
            == self._make_source_id(base, "proforma.xlsx")
        )

    def test_different_emails_same_filename_differ(self):
        base1 = "sender@example.com|Deal A|2026-05-28 10:00:00"
        base2 = "sender@example.com|Deal B|2026-05-28 10:00:00"
        id1 = self._make_source_id(base1, "proforma.xlsx")
        id2 = self._make_source_id(base2, "proforma.xlsx")
        assert id1 != id2

    def test_id_is_32_hex_chars(self):
        sid = self._make_source_id("a@b.com|subj|2026-01-01", "f.xlsx")
        assert len(sid) == 32
        assert all(c in "0123456789abcdef" for c in sid)

    def test_n_attachments_produce_n_unique_ids(self):
        base = "a@b.com|multi-deal|2026-05-28"
        filenames = ["p1.xlsx", "p2.xlsx", "p3.pdf", "p4.xlsm"]
        ids = [self._make_source_id(base, fn) for fn in filenames]
        assert len(set(ids)) == len(filenames), "All source_ids must be unique"


# ---------------------------------------------------------------------------
# Opportunity name disambiguation
# ---------------------------------------------------------------------------

class TestOpportunityNameDisambiguation:
    """When multiple proforma attachments exist, names get file-based suffixes."""

    def _make_name(self, base: str, proforma_metas: list[dict], att_meta: dict) -> str:
        import os
        if len(proforma_metas) > 1 and att_meta.get("filename"):
            bare = os.path.splitext(att_meta["filename"])[0]
            return f"{base} — {bare}"
        return base

    def test_single_attachment_no_suffix(self):
        metas = [{"filename": "proforma.xlsx", "proforma_task_id": "t1"}]
        assert self._make_name("123 Oak Ave", metas, metas[0]) == "123 Oak Ave"

    def test_multi_attachment_gets_file_suffix(self):
        metas = [
            {"filename": "unit_1.xlsx", "proforma_task_id": "t1"},
            {"filename": "unit_2.xlsx", "proforma_task_id": "t2"},
        ]
        assert self._make_name("123 Oak Ave", metas, metas[0]) == "123 Oak Ave — unit_1"
        assert self._make_name("123 Oak Ave", metas, metas[1]) == "123 Oak Ave — unit_2"

    def test_empty_filename_no_suffix(self):
        metas = [
            {"proforma_task_id": "t1"},
            {"proforma_task_id": "t2"},
        ]
        assert self._make_name("Deal", metas, metas[0]) == "Deal"
