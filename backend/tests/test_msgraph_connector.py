"""Tests for the Microsoft Graph calendar connector against real Graph JSON."""

from datetime import datetime, time

import httpx
import pytest

from exhale.connectors.msgraph import GraphCalendarConnector, parse_graph_event
from exhale.schemas import FactOrigin

BUSY = {
    "id": "AAMkAG...",
    "subject": "Chemical Health team meeting",
    "isCancelled": False,
    "isAllDay": False,
    "showAs": "busy",
    "start": {"dateTime": "2026-09-16T09:00:00.0000000", "timeZone": "America/Chicago"},
    "end": {"dateTime": "2026-09-16T10:00:00.0000000", "timeZone": "America/Chicago"},
}
FREE = {**BUSY, "id": "free1", "subject": "Hold", "showAs": "free"}
ALLDAY = {**BUSY, "id": "ad1", "subject": "Conference", "isAllDay": True}
CANCELLED = {**BUSY, "id": "c1", "subject": "Old", "isCancelled": True}


# --- mapping ----------------------------------------------------------------------
def test_busy_event_maps_to_coverage_event():
    ev = parse_graph_event(BUSY, "Ali")
    assert ev is not None
    assert ev.title == "Chemical Health team meeting"
    assert ev.attendees == ("Ali",)
    assert (ev.start.time(), ev.end.time()) == (time(9, 0), time(10, 0))
    assert ev.start.tzinfo is None
    assert ev.origin is FactOrigin.OBSERVED
    assert ev.source_reference.startswith("msgraph_")


def test_free_allday_cancelled_are_skipped():
    assert parse_graph_event(FREE, "Ali") is None
    assert parse_graph_event(ALLDAY, "Ali") is None
    assert parse_graph_event(CANCELLED, "Ali") is None


def test_working_elsewhere_does_not_block():
    assert parse_graph_event({**BUSY, "showAs": "workingElsewhere"}, "Ali") is None


# --- fetch ------------------------------------------------------------------------
def _mock(handler):
    return GraphCalendarConnector(
        caregiver_name="Ali", access_token="tok",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_fetch_busy_uses_calendarview_and_prefers_tz():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["prefer"] = request.headers.get("Prefer")
        return httpx.Response(200, json={"value": [BUSY, FREE, ALLDAY]})

    events = _mock(handler).fetch_busy(datetime(2026, 9, 1), datetime(2026, 9, 30))
    assert [e.title for e in events] == ["Chemical Health team meeting"]  # only the busy one
    assert "calendarView" in seen["path"]
    assert 'outlook.timezone="America/Chicago"' in seen["prefer"]


def test_fetch_follows_pagination():
    def handler(request):
        if "nextpage" in str(request.url):
            return httpx.Response(200, json={"value": [{**BUSY, "id": "p2", "subject": "Second"}]})
        return httpx.Response(200, json={
            "value": [BUSY], "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/calendarView?nextpage=1"})

    events = _mock(handler).fetch_busy(datetime(2026, 9, 1), datetime(2026, 9, 30))
    assert [e.title for e in events] == ["Chemical Health team meeting", "Second"]


def test_fetch_refreshes_on_401():
    calls = {"n": 0}

    def handler(request):
        if request.url.host == "login.microsoftonline.com":
            return httpx.Response(200, json={"access_token": "fresh"})
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(401)
        return httpx.Response(200, json={"value": [BUSY]})

    conn = GraphCalendarConnector(
        caregiver_name="Ali", refresh_token="r", client_id="c", client_secret="s",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert [e.title for e in conn.fetch_busy(datetime(2026, 9, 1), datetime(2026, 9, 30))] \
        == ["Chemical Health team meeting"]


def test_connector_requires_credentials():
    with pytest.raises(ValueError):
        GraphCalendarConnector(caregiver_name="Ali")


# --- event write ------------------------------------------------------------------
def test_create_event_posts_to_graph():
    seen = {}

    def handler(request):
        if request.method == "POST" and "events" in request.url.path:
            import json
            seen["body"] = json.loads(request.content)
            return httpx.Response(201, json={"id": "AAMk_new"})
        return httpx.Response(200, json={})

    conn = GraphCalendarConnector(
        caregiver_name="Ali", access_token="tok",
        http=httpx.Client(transport=httpx.MockTransport(handler)))
    created = conn.create_event("Gym", datetime(2026, 7, 23, 9, 0),
                                datetime(2026, 7, 23, 10, 0))
    assert created["id"] == "AAMk_new"
    assert seen["body"]["subject"] == "Gym"
    assert seen["body"]["start"]["timeZone"] == "America/Chicago"
