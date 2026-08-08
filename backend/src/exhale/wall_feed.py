"""The wall feed — Exhale published as a subscribable calendar (RFC 5545).

A phone and a wall are different surfaces. The Breath Glance is read alone, by
the person carrying the load, so it may say "2 things want you this week." A
family display — Skylight, a shared Google calendar, a fridge tablet — is
ambient and read by everyone, including kids and whoever is in the kitchen.
Nobody *uses* it; they catch it while pouring coffee.

So this feed states **what is happening and who has it**, never what is owed:

* no threat bands, indicators, risk scores, or counts leave this module
* deadlines are phrased the way a person would say them out loud
* a coverage gap is published as a need ("Leo needs someone"), never as an
  accusation, an alarm, or a name attached to a failure

Everything here is derived, so nothing new is stored. The feed is consumed by
devices we cannot see or debug, so the output is deliberately strict: DTSTAMP
on every event, correct DATE vs DATE-TIME value types, RFC-5545 escaping, and
75-octet line folding.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone

PRODID = "-//Exhale//Family Feed//EN"

# A wall shows the near future. Far-off items are noise on a display that
# cannot be scrolled past.
DEADLINE_HORIZON_DAYS = 45
CARE_GAP_HORIZON_DAYS = 21


# --- RFC 5545 primitives -----------------------------------------------------
def _esc(text: str) -> str:
    """Escape TEXT values — a comma or newline must not corrupt line structure."""

    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def _fold(line: str) -> list[str]:
    """Fold to 75 octets per RFC 5545 §3.1, splitting on byte boundaries.

    Long titles are common ("West High Field Trip Permission Slip") and strict
    parsers reject overlong lines outright.
    """

    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return [line]
    chunks, start = [], 0
    while start < len(raw):
        end = min(start + (75 if start == 0 else 74), len(raw))
        # Never split a multi-byte character across a fold: back up until the
        # byte at `end` begins a new character (i.e. is not a continuation).
        while start < end < len(raw) and (raw[end] & 0xC0) == 0x80:
            end -= 1
        chunk = raw[start:end].decode("utf-8")
        chunks.append(chunk if start == 0 else " " + chunk)
        start = end
    return chunks


def _uid(kind: str, key: str) -> str:
    """Stable per-item UID so a resubscribe updates rather than duplicates."""

    digest = hashlib.sha1(f"{kind}:{key}".encode()).hexdigest()[:16]
    return f"{kind}-{digest}@exhale"


def _as_utc(value: datetime) -> datetime:
    """Naive datetimes are local wall-clock; publish them as UTC instants."""

    if value.tzinfo is None:
        return value.astimezone(timezone.utc)
    return value.astimezone(timezone.utc)


def _stamp(value: datetime) -> str:
    return _as_utc(value).strftime("%Y%m%dT%H%M%SZ")


def _parse_dt(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


# --- the copy ----------------------------------------------------------------
def deadline_summary(title: str, person: str | None) -> str:
    """Wall copy for a deadline: what it is, whose it is, that it's due.

    No band, no indicator, no "CRITICAL" — the wall never raises its voice.
    """

    text = str(title).strip().rstrip(".")
    label = text if text.lower().endswith(" due") else f"{text} due"
    return f"{label} — {person}" if person else label


def care_gap_summary(recipient: str | None) -> str:
    """Wall copy for an uncovered stretch — a need, never an accusation.

    Deliberately says nobody's name but the child's: a gap is a thing to solve
    together, not a person who dropped something.
    """

    who = str(recipient).strip() if recipient else "Someone"
    return f"{who} needs someone"


# --- assembly ----------------------------------------------------------------
def _event_lines(
    *,
    uid: str,
    summary: str,
    stamp: datetime,
    start: datetime | date,
    end: datetime | date | None = None,
    description: str | None = None,
) -> list[str]:
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{_stamp(stamp)}",
        f"SUMMARY:{_esc(summary)}",
    ]
    if isinstance(start, datetime):
        lines.append(f"DTSTART:{_stamp(start)}")
        if end is not None:
            lines.append(f"DTEND:{_stamp(end)}")
    else:
        # All-day: DATE value type, DTEND exclusive (the next day).
        lines.append(f"DTSTART;VALUE=DATE:{start.strftime('%Y%m%d')}")
        finish = end if isinstance(end, date) else start + timedelta(days=1)
        lines.append(f"DTEND;VALUE=DATE:{finish.strftime('%Y%m%d')}")
    if description:
        lines.append(f"DESCRIPTION:{_esc(description)}")
    lines.append("END:VEVENT")
    return lines


def build_wall_feed(
    *,
    scheduled_events: list[dict] | None = None,
    deadlines: list[dict] | None = None,
    care_gaps: list[dict] | None = None,
    now: datetime | None = None,
    calendar_name: str = "Exhale",
) -> str:
    """Render the family's subscribable calendar.

    ``deadlines`` are briefing gap items (title/person/deadline); ``care_gaps``
    are Care Watch gaps (recipient/start/end). Both are read-only inputs — this
    function derives, and never decides what the family owes anyone.
    """

    now = now or datetime.now(timezone.utc)
    today = _as_utc(now).date()

    body: list[str] = []

    # 1. Time the family protected — the reason the wall is worth looking at.
    for event in scheduled_events or []:
        start = _parse_dt(event.get("start", ""))
        end = _parse_dt(event.get("end", ""))
        if start is None:
            continue
        body += _event_lines(
            uid=str(event.get("uid") or _uid("kept", f"{event.get('title')}{start}")),
            summary=str(event.get("title") or "Time together"),
            stamp=now,
            start=start,
            end=end,
            description=event.get("description") or None,
        )

    # 2. Deadlines, as all-day markers. Past-due items are dropped rather than
    #    left glowing on a wall nobody can dismiss.
    for item in deadlines or []:
        due = _parse_date(item.get("deadline", ""))
        if due is None or due < today or (due - today).days > DEADLINE_HORIZON_DAYS:
            continue
        body += _event_lines(
            uid=_uid("due", str(item.get("obligation_id") or item.get("title"))),
            summary=deadline_summary(item.get("title", "Something"), item.get("person")),
            stamp=now,
            start=due,
            description=item.get("anchor_event") and f"For {item['anchor_event']}",
        )

    # 3. Coverage gaps — the wall's most useful job is answering "who's got it?"
    for gap in care_gaps or []:
        start = _parse_dt(gap.get("start", ""))
        end = _parse_dt(gap.get("end", ""))
        if start is None or end is None:
            continue
        if _as_utc(start).date() < today:
            continue
        if (_as_utc(start).date() - today).days > CARE_GAP_HORIZON_DAYS:
            continue
        body += _event_lines(
            uid=_uid("cover", f"{gap.get('recipient')}{gap.get('start')}"),
            summary=care_gap_summary(gap.get("recipient")),
            stamp=now,
            start=start,
            end=end,
        )

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_esc(calendar_name)}",
        *body,
        "END:VCALENDAR",
    ]

    folded: list[str] = []
    for line in lines:
        folded.extend(_fold(line))
    return "\r\n".join(folded) + "\r\n"
