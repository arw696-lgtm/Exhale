"""iCalendar (.ics / webcal) connector — the iCloud/Outlook bridge.

Google has a clean API; iCloud does not. But any iCloud **shared** calendar can
be *published* as a public ``.ics`` URL (Calendar → Share → Public Calendar),
and so can Outlook and Google. This connector fetches such a feed and maps each
*busy* block to a :class:`~exhale.coverage.CalendarEvent`, so the family's joint
calendar — where the concerts and both-parents-out events live — stops being a
blind spot.

Same honest-defaults discipline as the Google connector: only timed events
block; an event marked Free (``TRANSP:TRANSPARENT``) or an all-day entry does
not black out the day; cancelled events are skipped. A shared calendar's events
are stamped with the caregivers who are *out* for them (``attendees``) — that is
what turns "both parents at a concert" into a care gap. Everything mapped is
``origin=OBSERVED``.

A minimal, dependency-free VEVENT parser (line-unfolding + the handful of
properties coverage needs). Recurring events (``RRULE``) are not expanded — a
limitation surfaced honestly rather than silently mishandled.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from exhale.coverage import CalendarEvent
from exhale.schemas import FactOrigin

DEFAULT_TZ = "America/Chicago"


def _unfold(text: str) -> list[str]:
    """Undo RFC 5545 line folding (continuation lines start with space/tab)."""

    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _unescape(value: str) -> str:
    return (value.replace("\\n", "\n").replace("\\,", ",")
            .replace("\\;", ";").replace("\\\\", "\\"))


def _split_prop(line: str) -> tuple[str, dict[str, str], str]:
    """"NAME;PARAM=v:VALUE" → (name_upper, params, value)."""

    head, _, value = line.partition(":")
    name, *param_parts = head.split(";")
    params = {}
    for p in param_parts:
        k, _, v = p.partition("=")
        params[k.upper()] = v
    return name.upper(), params, value


def _parse_dt(value: str, params: dict[str, str], tz: ZoneInfo) -> tuple[datetime | None, bool]:
    """(datetime naive local, is_all_day). All-day → (None, True)."""

    if params.get("VALUE") == "DATE" or (len(value) == 8 and "T" not in value):
        return None, True
    try:
        if value.endswith("Z"):  # UTC → local wall-clock, then drop tz
            dt = datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=ZoneInfo("UTC"))
            return dt.astimezone(tz).replace(tzinfo=None), False
        return datetime.strptime(value, "%Y%m%dT%H%M%S"), False  # local wall-clock
    except ValueError:
        return None, False


def parse_ics(text: str, attendees: tuple[str, ...], *, tz: str = DEFAULT_TZ) -> list[CalendarEvent]:
    """Pure: an iCalendar document → busy :class:`CalendarEvent`s.

    ``attendees`` are the caregiver names who are out for these events (for a
    shared family calendar, typically both parents).
    """

    zone = ZoneInfo(tz)
    events: list[CalendarEvent] = []
    cur: dict | None = None
    for line in _unfold(text):
        name, params, value = _split_prop(line)
        if name == "BEGIN" and value == "VEVENT":
            cur = {}
        elif name == "END" and value == "VEVENT":
            if cur is not None:
                ev = _build(cur, attendees, zone)
                if ev is not None:
                    events.append(ev)
            cur = None
        elif cur is not None:
            if name == "SUMMARY":
                cur["summary"] = _unescape(value)
            elif name == "UID":
                cur["uid"] = value
            elif name == "STATUS":
                cur["status"] = value.upper()
            elif name == "TRANSP":
                cur["transp"] = value.upper()
            elif name == "DTSTART":
                cur["start"], cur["start_allday"] = _parse_dt(value, params, zone)
            elif name == "DTEND":
                cur["end"], _ = _parse_dt(value, params, zone)
    return events


def _build(vevent: dict, attendees: tuple[str, ...], zone: ZoneInfo) -> CalendarEvent | None:
    if vevent.get("status") == "CANCELLED":
        return None
    if vevent.get("transp") == "TRANSPARENT":  # marked Free
        return None
    start, end = vevent.get("start"), vevent.get("end")
    if start is None or end is None or start >= end:  # all-day or malformed
        return None
    uid = vevent.get("uid", "unknown")
    return CalendarEvent(
        title=vevent.get("summary", "(busy)").strip() or "(busy)",
        start=start,
        end=end,
        attendees=attendees,
        source_reference=f"ics_{uid}",
        origin=FactOrigin.OBSERVED,
    )


class ICSCalendarConnector:
    """Fetches and parses a published ``.ics`` calendar feed."""

    def __init__(
        self,
        url: str,
        *,
        attendees: tuple[str, ...],
        tz: str = DEFAULT_TZ,
        http: httpx.Client | None = None,
    ) -> None:
        if not attendees:
            raise ValueError("ICSCalendarConnector needs at least one attendee name")
        # webcal:// is just https:// for fetching.
        self.url = url.replace("webcal://", "https://", 1)
        self.attendees = tuple(attendees)
        self.tz = tz
        self._http = http or httpx.Client(timeout=30, follow_redirects=True)

    def fetch_busy(self) -> list[CalendarEvent]:
        resp = self._http.get(self.url)
        resp.raise_for_status()
        return parse_ics(resp.text, self.attendees, tz=self.tz)
