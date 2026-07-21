"""Tests for the Google Calendar connector against real Calendar API JSON shapes.

Fixtures are the actual events read off Andy's calendar: a timed "Series 65
Study Block" (busy), the 112 Eatery reservation (marked Free), and the all-day
"Shot Day" marker — the three cases the busy/free/all-day rules must separate.
"""

from datetime import datetime, time

import httpx
import pytest

from exhale.connectors.gcal import GoogleCalendarConnector, parse_calendar_event
from exhale.coverage_config import CoverageModelIn, merge_events
from exhale.schemas import FactOrigin

# --- real event shapes ------------------------------------------------------------
STUDY_BLOCK = {
    "id": "v4alsornqb5tcc0j5dlc7k1s7c_20260708T190000Z",
    "summary": "Series 65 Study Block",
    "status": "confirmed",
    "start": {"dateTime": "2026-07-08T14:00:00-05:00", "timeZone": "America/Chicago"},
    "end": {"dateTime": "2026-07-08T15:00:00-05:00", "timeZone": "America/Chicago"},
}
EATERY_FREE = {
    "id": "36qq9uoggue21pb3fcsqtnfbok",
    "summary": "Reservation at 112 Eatery",
    "status": "confirmed",
    "transparency": "transparent",  # marked Free
    "start": {"dateTime": "2026-07-18T18:45:00-05:00"},
    "end": {"dateTime": "2026-07-18T19:45:00-05:00"},
}
SHOT_DAY_ALLDAY = {
    "id": "_711kcci_20260703",
    "summary": "Shot Day",
    "status": "confirmed",
    "start": {"date": "2026-07-03"},
    "end": {"date": "2026-07-04"},
}
CANCELLED = {"id": "x", "summary": "Old", "status": "cancelled",
             "start": {"dateTime": "2026-07-08T09:00:00-05:00"},
             "end": {"dateTime": "2026-07-08T10:00:00-05:00"}}


# --- mapping ----------------------------------------------------------------------
def test_timed_busy_event_becomes_a_coverage_event():
    ev = parse_calendar_event(STUDY_BLOCK, "Andy")
    assert ev is not None
    assert ev.title == "Series 65 Study Block"
    assert ev.attendees == ("Andy",)
    assert (ev.start.time(), ev.end.time()) == (time(14, 0), time(15, 0))
    assert ev.start.tzinfo is None                 # naive local wall-clock
    assert ev.origin is FactOrigin.OBSERVED        # read off a calendar
    assert ev.source_reference.startswith("gcal_")


def test_free_marked_event_does_not_block_care():
    assert parse_calendar_event(EATERY_FREE, "Andy") is None


def test_all_day_marker_is_not_a_blackout():
    assert parse_calendar_event(SHOT_DAY_ALLDAY, "Andy") is None


def test_cancelled_event_is_skipped():
    assert parse_calendar_event(CANCELLED, "Andy") is None


# --- fetch ------------------------------------------------------------------------
def _mock(handler):
    return GoogleCalendarConnector(
        caregiver_name="Andy", access_token="tok",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_fetch_busy_filters_and_expands():
    seen = {}

    def handler(request):
        seen["singleEvents"] = request.url.params.get("singleEvents")
        seen["orderBy"] = request.url.params.get("orderBy")
        page = request.url.params.get("pageToken")
        if page is None:
            return httpx.Response(200, json={
                "items": [STUDY_BLOCK, EATERY_FREE, SHOT_DAY_ALLDAY],
                "nextPageToken": "p2"})
        return httpx.Response(200, json={"items": [CANCELLED]})

    events = _mock(handler).fetch_busy(
        datetime(2026, 7, 1), datetime(2026, 7, 31))
    # Only the timed busy block survives; Free/all-day/cancelled are dropped.
    assert [e.title for e in events] == ["Series 65 Study Block"]
    assert seen["singleEvents"] == "true"   # recurring events expanded to instances
    assert seen["orderBy"] == "startTime"


def test_fetch_refreshes_on_401():
    calls = {"n": 0}

    def handler(request):
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "fresh"})
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(401)
        return httpx.Response(200, json={"items": [STUDY_BLOCK]})

    conn = GoogleCalendarConnector(
        caregiver_name="Andy", refresh_token="r", client_id="c", client_secret="s",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    events = conn.fetch_busy(datetime(2026, 7, 1), datetime(2026, 7, 31))
    assert [e.title for e in events] == ["Series 65 Study Block"]


def test_connector_requires_credentials():
    with pytest.raises(ValueError):
        GoogleCalendarConnector(caregiver_name="Andy")


# --- merge into a stored coverage model -------------------------------------------
def _model():
    return CoverageModelIn(**{
        "recipient": {"name": "Stevie"},
        "caregivers": [
            {"name": "Andy", "role": "PARENT",
             "events": [{"title": "Gary Clark Jr.", "start": "2026-09-19T19:30:00",
                         "end": "2026-09-19T21:00:00", "attendees": ["Ali", "Andy"],
                         "source_reference": "shared_cal_gcj"}]},
        ],
    })


def test_merge_events_adds_synced_and_preserves_manual():
    fetched = [parse_calendar_event(STUDY_BLOCK, "Andy")]
    merged = merge_events(_model(), "Andy", fetched)
    andy = next(c for c in merged.caregivers if c.name == "Andy")
    refs = [e.source_reference for e in andy.events]
    assert "shared_cal_gcj" in refs                       # manual event preserved
    assert any(r and r.startswith("gcal_") for r in refs)  # synced event added


def test_merge_events_is_idempotent():
    fetched = [parse_calendar_event(STUDY_BLOCK, "Andy")]
    once = merge_events(_model(), "Andy", fetched)
    twice = merge_events(once, "Andy", fetched)
    andy = next(c for c in twice.caregivers if c.name == "Andy")
    synced = [e for e in andy.events if (e.source_reference or "").startswith("gcal_")]
    assert len(synced) == 1  # re-sync replaced, did not duplicate


def test_merge_unknown_caregiver_raises():
    with pytest.raises(KeyError):
        merge_events(_model(), "Nobody", [])


# --- event write (the write half of controlled autonomy) --------------------------
def test_create_event_posts_and_returns_resource():
    seen = {}

    def handler(request):
        if request.method == "POST":
            import json
            seen["path"] = request.url.path
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={"id": "evt_1", "htmlLink": "https://cal/evt_1"})
        return httpx.Response(200, json={})

    conn = GoogleCalendarConnector(
        caregiver_name="Andy", access_token="tok",
        http=httpx.Client(transport=httpx.MockTransport(handler)))
    created = conn.create_event("Gym", datetime(2026, 7, 23, 9, 0),
                                datetime(2026, 7, 23, 10, 0))
    assert created["id"] == "evt_1"
    assert seen["path"].endswith("/calendars/primary/events")
    assert seen["body"]["summary"] == "Gym"
    assert seen["body"]["start"]["dateTime"] == "2026-07-23T09:00:00"
    assert seen["body"]["description"] == "Added by Exhale"


def test_create_event_refreshes_on_401():
    calls = {"n": 0}

    def handler(request):
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "fresh"})
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(401)
        return httpx.Response(200, json={"id": "evt_2"})

    conn = GoogleCalendarConnector(
        caregiver_name="Andy", refresh_token="r", client_id="c", client_secret="s",
        http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert conn.create_event("Gym", datetime(2026, 7, 23, 9), datetime(2026, 7, 23, 10))["id"] == "evt_2"
