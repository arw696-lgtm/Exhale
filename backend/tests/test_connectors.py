"""Tests for connectors (§2 Layer 1)."""

from datetime import datetime, timedelta, timezone

from exhale.connectors.base import RawMessage
from exhale.connectors.imap import message_from_bytes
from exhale.connectors.memory import FixtureConnector


def _msg(source_id, days_ago):
    return RawMessage(
        source_id=source_id,
        channel="fixture",
        subject=f"Item {source_id}",
        body="body",
        received_at=datetime(2026, 7, 19, tzinfo=timezone.utc) - timedelta(days=days_ago),
    )


def test_fixture_connector_filters_by_since():
    conn = FixtureConnector([_msg("a", 200), _msg("b", 30), _msg("c", 5)])
    since = datetime(2026, 7, 19, tzinfo=timezone.utc) - timedelta(days=180)
    ids = [m.source_id for m in conn.fetch(since=since)]
    assert ids == ["b", "c"]  # 'a' is older than 180 days; sorted ascending


def test_fixture_connector_fetch_all_when_no_since():
    conn = FixtureConnector([_msg("a", 200), _msg("b", 5)])
    assert len(list(conn.fetch())) == 2


def test_imap_message_parsing_is_pure_and_normalized():
    raw_bytes = (
        b"From: West High <noreply@powerschool.com>\r\n"
        b"Subject: Field Trip\r\n"
        b"Date: Mon, 06 Jul 2026 09:00:00 +0000\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"Please sign the permission slip.\r\n"
    )
    msg = message_from_bytes(raw_bytes, source_id="imap_42")
    assert msg.subject == "Field Trip"
    assert msg.sender == "noreply@powerschool.com"
    assert msg.sender_domain == "powerschool.com"
    assert "permission slip" in msg.body
    assert msg.received_at.year == 2026
