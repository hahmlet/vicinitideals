"""Unit tests for uploaded-filename sanitization (defense-in-depth vs XSS)."""

from __future__ import annotations

import pytest

from app.api.routers.ui_documents import _sanitize_filename

pytestmark = pytest.mark.unit


def test_strips_markup_and_quotes():
    out = _sanitize_filename('"><img src=x onerror=alert(1)>.pdf')
    for bad in ('<', '>', '"', "'"):
        assert bad not in out
    assert out.endswith(".pdf")


def test_strips_path_components():
    assert _sanitize_filename("../../etc/passwd") == "passwd"
    assert _sanitize_filename(r"C:\Users\x\secret.xlsx") == "secret.xlsx"


def test_drops_control_chars():
    assert "\x00" not in _sanitize_filename("a\x00b.pdf")
    assert "\n" not in _sanitize_filename("a\nb.pdf")


def test_keeps_normal_name():
    assert _sanitize_filename("Lease Agreement 2026.pdf") == "Lease Agreement 2026.pdf"


def test_empty_and_dotonly():
    assert _sanitize_filename("") == ""
    assert _sanitize_filename("   ") == ""
    assert _sanitize_filename("...") == ""
