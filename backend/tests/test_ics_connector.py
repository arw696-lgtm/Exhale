"""Tests for the iCalendar (.ics) connector — the iCloud/Outlook bridge.

The fixture is a published-calendar feed shaped like the "Ali and Andy Shared"
iCloud calendar: the real Gary Clark Jr. concert (both parents out), a Free-
marked block, an all-day marker, and a cancelled event.
"""

from datetime import datetime, time

import httpx
import pytest

from exhale.connectors.ics import ICSCalendarConnector, parse_ics
from exhale.schemas import FactOrigin

# A concert stored in local time via TZID, plus the three should-be-ignored cases.
ICS_FEED = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCloud Calendar//EN
BEGIN:VEVENT
UID:gcj-001
SUMMARY:Gary Clark Jr.
DTSTART;TZID=America/Chicago:20260919T193000
DTEND;TZID=America/Chicago:20260919T210000
STATUS:CONFIRMED
END:VEVENT
BEGIN:VEVENT
UID:free-002
SUMMARY:Tentative hold
TRANSP:TRANSPARENT
DTSTART;TZID=America/Chicago:20260920T120000
DTEND;TZID=America/Chicago:20260920T130000
END:VEVENT
BEGIN:VEVENT
UID:allday-003
SUMMARY:Anniversary
DTSTART;VALUE=DATE:20260921
DTEND;VALUE=DATE:20260922
END:VEVENT
BEGIN:VEVENT
UID:cancelled-004
SUMMARY:Old plan
STATUS:CANCELLED
DTSTART;TZID=America/Chicago:20260922T190000
DTEND;TZID=America/Chicago:20260922T200000
END:VEVENT
END:VCALENDAR
"""


def test_parses_shared_concert_with_both_parents_out():
    events = parse_ics(ICS_FEED, ("Ali", "Andy"))
    assert len(events) == 1  # only the confirmed timed concert
    ev = events[0]
    assert ev.title == "Gary Clark Jr."
    assert ev.attendees == ("Ali", "Andy")            # shared → both out
    assert (ev.start.time(), ev.end.time()) == (time(19, 30), time(21, 0))
    assert ev.origin is FactOrigin.OBSERVED
    assert ev.source_reference == "ics_gcj-001"


def test_free_allday_and_cancelled_are_dropped():
    titles = [e.title for e in parse_ics(ICS_FEED, ("Ali", "Andy"))]
    assert "Tentative hold" not in titles   # Free
    assert "Anniversary" not in titles      # all-day marker
    assert "Old plan" not in titles         # cancelled


def test_utc_times_convert_to_local_wallclock():
    feed = (
        "BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:z1\nSUMMARY:UTC event\n"
        # 00:30Z on Sep 20 == 19:30 CDT on Sep 19 (America/Chicago, -05:00)
        "DTSTART:20260920T003000Z\nDTEND:20260920T013000Z\nEND:VEVENT\nEND:VCALENDAR\n"
    )
    ev = parse_ics(feed, ("Ali",))[0]
    assert ev.start == datetime(2026, 9, 19, 19, 30)


def test_line_folding_is_unfolded():
    feed = (
        "BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:f1\nSUMMARY:Long title that got\n"
        "  folded across lines\nDTSTART;TZID=America/Chicago:20260919T193000\n"
        "DTEND;TZID=America/Chicago:20260919T210000\nEND:VEVENT\nEND:VCALENDAR\n"
    )
    assert parse_ics(feed, ("Ali",))[0].title == "Long title that got folded across lines"


def test_connector_fetches_and_parses():
    def handler(request):
        assert request.url.path.endswith(".ics")
        return httpx.Response(200, text=ICS_FEED)

    conn = ICSCalendarConnector(
        "https://p12-caldav.icloud.com/published/shared.ics",
        attendees=("Ali", "Andy"),
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    events = conn.fetch_busy()
    assert [e.title for e in events] == ["Gary Clark Jr."]


def test_webcal_scheme_is_rewritten_to_https():
    conn = ICSCalendarConnector("webcal://example.com/cal.ics", attendees=("Ali",))
    assert conn.url.startswith("https://")


def test_connector_requires_attendees():
    with pytest.raises(ValueError):
        ICSCalendarConnector("https://x/cal.ics", attendees=())


# --- recurring events (RRULE) — the Google/iCloud secret-feed case -----------------
from datetime import date as _d  # noqa: E402

WIN = (datetime(2026, 9, 1), datetime(2026, 9, 30))


def _recurring(rrule, dtstart="20260907T173000", dtend="20260907T190000"):
    return (
        "BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:rec1\nSUMMARY:Soccer practice\n"
        f"DTSTART;TZID=America/Chicago:{dtstart}\n"
        f"DTEND;TZID=America/Chicago:{dtend}\n"
        f"RRULE:{rrule}\nEND:VEVENT\nEND:VCALENDAR\n"
    )


def test_weekly_recurrence_expands_across_window():
    evs = parse_ics(_recurring("FREQ=WEEKLY"), ("Andy",),
                    expand_from=WIN[0], expand_until=WIN[1])
    dates = [e.start.date() for e in evs]
    # Sep 7 is a Monday → weekly Mondays in September.
    assert dates == [_d(2026, 9, 7), _d(2026, 9, 14), _d(2026, 9, 21), _d(2026, 9, 28)]
    assert all(e.start.time() == time(17, 30) for e in evs)


def test_weekly_byday_expands_multiple_weekdays():
    evs = parse_ics(_recurring("FREQ=WEEKLY;BYDAY=MO,WE"), ("Andy",),
                    expand_from=WIN[0], expand_until=WIN[1])
    dates = [e.start.date() for e in evs]
    assert _d(2026, 9, 7) in dates and _d(2026, 9, 9) in dates   # Mon + Wed
    assert _d(2026, 9, 16) in dates                               # following Wed


def test_count_limits_occurrences():
    evs = parse_ics(_recurring("FREQ=WEEKLY;COUNT=2"), ("Andy",),
                    expand_from=WIN[0], expand_until=WIN[1])
    assert len(evs) == 2


def test_until_limits_occurrences():
    evs = parse_ics(_recurring("FREQ=WEEKLY;UNTIL=20260915T000000Z"), ("Andy",),
                    expand_from=WIN[0], expand_until=WIN[1])
    assert [e.start.date() for e in evs] == [_d(2026, 9, 7), _d(2026, 9, 14)]


def test_daily_interval():
    evs = parse_ics(_recurring("FREQ=DAILY;INTERVAL=2;COUNT=3"), ("Andy",),
                    expand_from=WIN[0], expand_until=WIN[1])
    assert [e.start.date() for e in evs] == [_d(2026, 9, 7), _d(2026, 9, 9), _d(2026, 9, 11)]


def test_unrecognized_rule_falls_back_to_single():
    evs = parse_ics(_recurring("FREQ=YEARLY"), ("Andy",),
                    expand_from=WIN[0], expand_until=WIN[1])
    assert len(evs) == 1


def test_recurring_occurrences_have_unique_source_refs():
    evs = parse_ics(_recurring("FREQ=WEEKLY;COUNT=3"), ("Andy",),
                    expand_from=WIN[0], expand_until=WIN[1])
    refs = [e.source_reference for e in evs]
    assert len(set(refs)) == 3 and all(r.startswith("ics_rec1") for r in refs)
