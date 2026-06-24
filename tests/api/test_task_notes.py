"""Unit tests for the task-notes rich-text subset: sanitize + flatten-to-text."""

from __future__ import annotations

from app.api.routers.ui_documents import _notes_html_to_text, _sanitize_notes_html


# ── Sanitizer (stored-XSS defense + tag allow-list) ─────────────────────────

def test_sanitize_strips_scripts_and_attributes():
    out = _sanitize_notes_html('<script>alert(1)</script><b onclick="x()">hi</b>')
    assert out == "<strong>hi</strong>"


def test_sanitize_drops_unknown_tag_keeps_text():
    assert _sanitize_notes_html('<a href="http://evil">link</a>') == "link"


def test_sanitize_normalizes_tags():
    assert _sanitize_notes_html("<i>a</i><strike>b</strike>") == "<em>a</em><s>b</s>"


def test_sanitize_balances_unclosed_tags():
    assert _sanitize_notes_html("<strong>bold") == "<strong>bold</strong>"


def test_sanitize_empty_shell_is_blank():
    assert _sanitize_notes_html("<p><br></p>") == ""
    assert _sanitize_notes_html("   ") == ""
    assert _sanitize_notes_html(None) == ""


def test_sanitize_preserves_nested_lists():
    src = "<ul><li>A<ul><li>A1</li></ul></li><li>B</li></ul>"
    assert _sanitize_notes_html(src) == src


# ── HTML → plain text (for .txt downloads) ──────────────────────────────────

def test_text_flattens_nested_bullets_with_indent():
    src = "<ul><li>A<ul><li>A1</li></ul></li><li>B</li></ul>"
    assert _notes_html_to_text(src) == "- A\n    - A1\n- B"


def test_text_numbers_ordered_items_per_level():
    assert _notes_html_to_text("<ol><li>one</li><li>two</li></ol>") == "1. one\n2. two"


def test_text_drops_inline_formatting():
    assert _notes_html_to_text("<strong>bold</strong> and <em>italic</em>") == "bold and italic"


def test_text_empty_is_blank():
    assert _notes_html_to_text("") == ""
    assert _notes_html_to_text(None) == ""
