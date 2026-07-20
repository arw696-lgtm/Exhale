"""Tests for the live Gmail connector (§1) against real Gmail API JSON shapes."""

import base64
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from exhale.connectors.gmail import GmailConnector, parse_gmail_message
from exhale.connectors.memory import FixtureConnector
from exhale.extraction import ExtractionContext
from exhale.retro_scan import run_incremental_sync
from exhale.store import HouseholdStore


def _b64url(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def _full_message(msg_id="abc123", *, html_only=False):
    """A realistic Gmail API format=full message payload."""

    plain_part = {
        "mimeType": "text/plain",
        "body": {"data": _b64url(
            "Please sign and return the permission slip for Olivia. "
            "The trip is on August 25, 2026. Forms are due by July 24, 2026."
        )},
    }
    html_part = {
        "mimeType": "text/html",
        "body": {"data": _b64url(
            "<p>Please sign and return the permission slip for Olivia.</p>"
            "<p>The trip is on August 25, 2026. Forms are due by July 24, 2026.</p>"
        )},
    }
    parts = [html_part] if html_only else [plain_part, html_part]
    received = datetime(2026, 7, 19, 17, 2, 31, tzinfo=timezone.utc)
    return {
        "id": msg_id,
        "internalDate": str(int(received.timestamp() * 1000)),
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "Subject", "value": "West High Field Trip Permission Slip"},
                {"name": "From", "value": "West High <noreply@powerschool.com>"},
            ],
            "parts": [
                {"mimeType": "multipart/alternative", "parts": parts},
                {
                    "mimeType": "application/pdf",
                    "filename": "slip.pdf",
                    "body": {"attachmentId": "att_9"},
                },
            ],
        },
    }


def test_parse_full_multipart_message():
    raw = parse_gmail_message(_full_message())
    assert raw.source_id == "gmail_abc123"
    assert raw.channel == "gmail"
    assert raw.subject == "West High Field Trip Permission Slip"
    assert raw.sender == "noreply@powerschool.com"
    assert raw.sender_domain == "powerschool.com"
    assert "permission slip for Olivia" in raw.body
    assert "<p>" not in raw.body  # text/plain preferred over html
    assert raw.received_at == datetime(2026, 7, 19, 17, 2, 31, tzinfo=timezone.utc)
    assert raw.attachments[0].filename == "slip.pdf"
    assert raw.attachments[0].reference == "att_9"


def test_html_only_message_is_stripped():
    raw = parse_gmail_message(_full_message(html_only=True))
    assert "permission slip for Olivia" in raw.body
    assert "<p>" not in raw.body


def _mock_gmail(handler):
    return GmailConnector(access_token="tok", http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_fetch_paginates_and_builds_since_query():
    seen_queries, seen_pages = [], []

    def handler(request):
        if request.url.path.endswith("/messages"):
            seen_queries.append(request.url.params.get("q"))
            page = request.url.params.get("pageToken")
            seen_pages.append(page)
            if page is None:
                return httpx.Response(200, json={
                    "messages": [{"id": "m1"}], "nextPageToken": "p2"})
            return httpx.Response(200, json={"messages": [{"id": "m2"}]})
        msg_id = request.url.path.rsplit("/", 1)[1]
        return httpx.Response(200, json=_full_message(msg_id))

    since = datetime(2026, 1, 20, tzinfo=timezone.utc)
    msgs = list(_mock_gmail(handler).fetch(since=since))
    assert [m.source_id for m in msgs] == ["gmail_m1", "gmail_m2"]
    assert seen_queries[0] == f"after:{int(since.timestamp())}"
    assert seen_pages == [None, "p2"]


def test_expired_token_refreshes_and_retries():
    calls = {"n": 0}

    def handler(request):
        if request.url.host == "oauth2.googleapis.com":
            body = dict(pair.split("=") for pair in request.content.decode().split("&"))
            assert body["grant_type"] == "refresh_token"
            return httpx.Response(200, json={"access_token": "fresh"})
        calls["n"] += 1
        if request.headers["Authorization"] == "Bearer stale":
            return httpx.Response(401)
        return httpx.Response(200, json={"messages": []})

    conn = GmailConnector(
        access_token="stale", refresh_token="r", client_id="c", client_secret="s",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert list(conn.fetch()) == []
    assert calls["n"] == 2  # 401 then success with refreshed token


def test_missing_credentials_rejected():
    with pytest.raises(ValueError):
        GmailConnector()


def test_incremental_sync_uses_and_advances_watermark():
    # "now" is after the fixture message (2026-07-19 17:02) so the second run's
    # watermark excludes it.
    now = datetime(2026, 7, 20, tzinfo=timezone.utc)
    store = HouseholdStore()
    ctx = ExtractionContext(known_children=["Olivia"], reference_date=now.date())
    old = parse_gmail_message(_full_message("old"))
    connector = FixtureConnector([old])

    first = run_incremental_sync(connector, store, "fam", ctx, now=now)
    assert first.scanned == 1
    assert store.profile("fam")["last_sync_at"] == now.isoformat()

    # Second run: watermark means the already-seen message is out of window.
    later = now + timedelta(days=1)
    second = run_incremental_sync(connector, store, "fam", ctx, now=later)
    assert second.scanned == 0
    assert store.profile("fam")["last_sync_at"] == later.isoformat()
