"""Tests for deterministic pre-parsing (§3.1)."""

from exhale.connectors.preprocess import clean, strip_footer, strip_quoted_reply


def test_strip_footer_removes_unsubscribe_block():
    text = "Field trip on Aug 25.\nUnsubscribe here to stop emails.\nFooter junk"
    assert "Field trip on Aug 25." in strip_footer(text)
    assert "Unsubscribe" not in strip_footer(text)
    assert "Footer junk" not in strip_footer(text)


def test_strip_quoted_reply():
    text = "Please sign the form.\nOn Mon, Jul 6 2026, School wrote:\n> old content"
    cleaned = strip_quoted_reply(text)
    assert "Please sign the form." in cleaned
    assert "old content" not in cleaned


def test_clean_collapses_whitespace_and_keeps_signal():
    text = "Permission    slip   due   Friday.\n\n\n\nThanks\ncopyright 2026 School"
    cleaned = clean(text)
    assert "Permission slip due Friday." in cleaned
    assert "copyright" not in cleaned
    assert "\n\n\n" not in cleaned
