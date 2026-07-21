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

from dataclasses import replace
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from exhale.coverage import CalendarEvent
from exhale.schemas import FactOrigin

DEFAULT_TZ = "America/Chicago"

# How far forward to expand a recurring event when no explicit window is given.
_DEFAULT_EXPAND_DAYS = 365
_MAX_OCCURRENCES = 500  # safety cap against a runaway/unbounded rule
_WEEKDAY = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


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


def _parse_rrule(value: str) -> dict:
    parts = {}
    for token in value.split(";"):
        k, _, v = token.partition("=")
        parts[k.upper()] = v
    return parts


def _expand_recurrence(
    base: CalendarEvent, rrule: str, window_start: datetime, window_end: datetime
) -> list[CalendarEvent]:
    """Expand a recurring event into concrete occurrences within a window.

    Supports the common family cases — FREQ=DAILY/WEEKLY/MONTHLY with INTERVAL,
    COUNT, UNTIL, and (weekly) BYDAY. Anything unrecognized falls back to the
    single base occurrence rather than being silently dropped or mishandled.
    """

    rule = _parse_rrule(rrule)
    freq = rule.get("FREQ", "").upper()
    interval = max(int(rule.get("INTERVAL", "1") or "1"), 1)
    count = int(rule["COUNT"]) if rule.get("COUNT") else None
    until = None
    if rule.get("UNTIL"):
        raw = rule["UNTIL"].rstrip("Z")
        try:
            until = datetime.strptime(raw[:15], "%Y%m%dT%H%M%S") if "T" in raw \
                else datetime.combine(datetime.strptime(raw[:8], "%Y%m%d").date(), base.start.time())
        except ValueError:
            until = None

    duration = base.end - base.start
    starts: list[datetime] = []

    def _emit(dt: datetime) -> bool:
        """Record an occurrence; return False when a stop condition is hit."""
        if until is not None and dt > until:
            return False
        if dt > window_end or len(starts) >= _MAX_OCCURRENCES:
            return False
        if dt >= window_start:
            starts.append(dt)
        return count is None or len(starts) < count

    if freq == "WEEKLY" and rule.get("BYDAY"):
        targets = sorted(_WEEKDAY[d] for d in rule["BYDAY"].split(",") if d in _WEEKDAY)
        week0 = base.start - timedelta(days=base.start.weekday())
        wk = 0
        while True:
            base_week = week0 + timedelta(weeks=wk * interval)
            stop = False
            for wd in targets:
                occ = (base_week + timedelta(days=wd)).replace(
                    hour=base.start.hour, minute=base.start.minute)
                if occ < base.start:
                    continue
                if not _emit(occ):
                    stop = True
                    break
            if stop or base_week > window_end or wk > 520:
                break
            wk += 1
    elif freq in ("DAILY", "WEEKLY", "MONTHLY"):
        step_days = {"DAILY": 1, "WEEKLY": 7}.get(freq)
        occ = base.start
        guard = 0
        while guard < _MAX_OCCURRENCES * 2:
            if not _emit(occ):
                break
            if freq == "MONTHLY":
                m = occ.month - 1 + interval
                occ = occ.replace(year=occ.year + m // 12, month=m % 12 + 1)
            else:
                occ = occ + timedelta(days=step_days * interval)
            if occ > window_end:
                break
            guard += 1
    else:
        return [base]  # unrecognized rule → keep the single occurrence

    return [
        replace(base, start=s, end=s + duration,
                source_reference=f"{base.source_reference}_{s.date().isoformat()}")
        for s in starts
    ]


def parse_ics(
    text: str,
    attendees: tuple[str, ...],
    *,
    tz: str = DEFAULT_TZ,
    expand_from: datetime | None = None,
    expand_until: datetime | None = None,
) -> list[CalendarEvent]:
    """Pure: an iCalendar document → busy :class:`CalendarEvent`s.

    ``attendees`` are the caregiver names who are out for these events (for a
    shared family calendar, typically both parents). Recurring events (RRULE)
    are expanded into concrete occurrences within [``expand_from``,
    ``expand_until``] (defaults: today → +1 year).
    """

    zone = ZoneInfo(tz)
    win_start = expand_from or datetime.combine(date.today(), datetime.min.time())
    win_end = expand_until or (win_start + timedelta(days=_DEFAULT_EXPAND_DAYS))

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
                    if cur.get("rrule"):
                        events.extend(_expand_recurrence(ev, cur["rrule"], win_start, win_end))
                    else:
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
            elif name == "RRULE":
                cur["rrule"] = value
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
