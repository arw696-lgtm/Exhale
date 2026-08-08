"""Tests for the wall feed — Exhale published as a subscribable calendar.

The feed is consumed by devices we cannot see or debug (a Skylight on a
kitchen wall), so these tests hold two lines: the output is strictly valid
RFC 5545, and the *tone* rules of a shared screen are enforced in code —
nothing that shames, alarms, or scores may cross this boundary.
"""

from datetime import datetime, timedelta, timezone

from exhale.wall_feed import (
    build_wall_feed,
    care_gap_summary,
    deadline_summary,
)

NOW = datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)


def _lines(feed: str) -> list[str]:
    """Unfold continuation lines, then split (RFC 5545 §3.1)."""

    return feed.replace("\r\n ", "").split("\r\n")


def _deadline(title="Field Trip Permission Slip", person="Olivia", days=3, **extra):
    item = {
        "obligation_id": "ob_1",
        "title": title,
        "person": person,
        "deadline": (NOW + timedelta(days=days)).date().isoformat(),
        "threat_level": "CRITICAL",
        "indicator": "🔴",
        "risk_score": 0.94,
        "why": "deadline in 3 days",
    }
    item.update(extra)
    return item


def _care_gap(recipient="Leo", day=2, start_h=15, end_h=17):
    start = (NOW + timedelta(days=day)).replace(hour=start_h, minute=15)
    return {
        "recipient": recipient,
        "date": start.date().isoformat(),
        "start": start.isoformat(),
        "end": start.replace(hour=end_h, minute=0).isoformat(),
        "threat_level": "CRITICAL",
        "indicator": "🔴",
        "reason": "school ends before either parent is free",
    }


# --- structure ---------------------------------------------------------------
def test_feed_is_wellformed_and_wraps_events():
    feed = build_wall_feed(deadlines=[_deadline()], now=NOW)
    lines = _lines(feed)
    assert lines[0] == "BEGIN:VCALENDAR"
    assert "VERSION:2.0" in lines
    assert "END:VCALENDAR" in lines
    assert lines.count("BEGIN:VEVENT") == lines.count("END:VEVENT") == 1
    assert feed.endswith("\r\n")


def test_every_event_carries_dtstamp():
    """Strict parsers reject a VEVENT without DTSTAMP — the old inline
    builder omitted it entirely."""

    feed = build_wall_feed(
        deadlines=[_deadline()],
        care_gaps=[_care_gap()],
        scheduled_events=[{
            "uid": "kept-1", "title": "Dinner, just us",
            "start": (NOW + timedelta(days=1)).isoformat(),
            "end": (NOW + timedelta(days=1, hours=2)).isoformat(),
        }],
        now=NOW,
    )
    lines = _lines(feed)
    assert lines.count("BEGIN:VEVENT") == 3
    assert sum(1 for line in lines if line.startswith("DTSTAMP:")) == 3


def test_deadlines_are_all_day_with_exclusive_end():
    feed = build_wall_feed(deadlines=[_deadline(days=3)], now=NOW)
    lines = _lines(feed)
    assert "DTSTART;VALUE=DATE:20260804" in lines
    # DTEND is exclusive — the next day, or the event renders as two days.
    assert "DTEND;VALUE=DATE:20260805" in lines


def test_care_gap_keeps_its_hours():
    feed = build_wall_feed(care_gaps=[_care_gap(day=2, start_h=15, end_h=17)], now=NOW)
    lines = _lines(feed)
    assert any(line.startswith("DTSTART:20260803T1515") for line in lines)
    assert any(line.startswith("DTEND:20260803T1700") for line in lines)


def test_uids_are_stable_across_renders():
    """A resubscribe must update the same events, not duplicate them."""

    first = build_wall_feed(deadlines=[_deadline()], care_gaps=[_care_gap()], now=NOW)
    later = build_wall_feed(
        deadlines=[_deadline()], care_gaps=[_care_gap()],
        now=NOW + timedelta(hours=6),
    )
    uids = lambda f: sorted(x for x in _lines(f) if x.startswith("UID:"))
    assert uids(first) == uids(later)


def test_commas_and_newlines_are_escaped():
    feed = build_wall_feed(
        deadlines=[_deadline(title="Bring: forms, cash; and a note\nby Friday")],
        now=NOW,
    )
    summary = next(x for x in _lines(feed) if x.startswith("SUMMARY:"))
    assert "\\," in summary and "\\;" in summary and "\\n" in summary
    # The escaping must not have leaked a raw newline into the line structure.
    assert len([x for x in _lines(feed) if x.startswith("SUMMARY:")]) == 1


def test_long_titles_are_folded_to_75_octets():
    long_title = "West High School Annual Overnight Field Trip Permission And Medical Release Slip"
    feed = build_wall_feed(deadlines=[_deadline(title=long_title)], now=NOW)
    assert all(len(line.encode()) <= 75 for line in feed.split("\r\n"))
    # …and unfolds back to the whole title.
    assert long_title in "".join(_lines(feed))


def test_multibyte_titles_survive_folding():
    feed = build_wall_feed(
        deadlines=[_deadline(title="Fête d'école — permission " + "é" * 60)], now=NOW
    )
    assert all(len(line.encode()) <= 75 for line in feed.split("\r\n"))
    assert "é" * 60 in "".join(_lines(feed))  # no character split across a fold


# --- horizon -----------------------------------------------------------------
def test_past_due_items_drop_off_the_wall():
    """A wall can't be scrolled past or dismissed — a stale red item would
    just sit there shaming the kitchen."""

    feed = build_wall_feed(deadlines=[_deadline(days=-2)], now=NOW)
    assert "BEGIN:VEVENT" not in feed


def test_far_future_items_are_not_published():
    feed = build_wall_feed(deadlines=[_deadline(days=200)], now=NOW)
    assert "BEGIN:VEVENT" not in feed


def test_todays_deadline_still_shows():
    feed = build_wall_feed(deadlines=[_deadline(days=0)], now=NOW)
    assert "DTSTART;VALUE=DATE:20260801" in _lines(feed)


# --- tone: the rails, enforced at the boundary -------------------------------
def test_no_threat_language_reaches_the_wall():
    feed = build_wall_feed(
        deadlines=[_deadline()], care_gaps=[_care_gap()], now=NOW
    )
    lowered = feed.lower()
    for banned in ("critical", "threat", "urgent", "overdue", "risk", "🔴", "🟡"):
        assert banned not in lowered, f"{banned!r} must not reach a shared screen"


def test_no_scores_or_counts_reach_the_wall():
    feed = build_wall_feed(deadlines=[_deadline(), _deadline(title="Immunization")],
                           now=NOW)
    assert "0.94" not in feed
    assert "risk_score" not in feed


def test_deadline_copy_reads_like_a_person():
    assert deadline_summary("Field Trip Permission Slip", "Olivia") == (
        "Field Trip Permission Slip due — Olivia"
    )
    assert deadline_summary("Tuition payment", None) == "Tuition payment due"
    # Doesn't stutter when the title already ends in "due".
    assert deadline_summary("Library books due", None) == "Library books due"


def test_care_gap_copy_names_the_child_not_the_adult():
    """A gap is a thing to solve together, never a person who dropped it."""

    assert care_gap_summary("Leo") == "Leo needs someone"
    assert care_gap_summary(None) == "Someone needs someone"
    assert "Ali" not in care_gap_summary("Leo")


# --- empty states ------------------------------------------------------------
def test_empty_family_still_returns_a_valid_calendar():
    feed = build_wall_feed(now=NOW)
    lines = _lines(feed)
    assert lines[0] == "BEGIN:VCALENDAR"
    assert "END:VCALENDAR" in lines
    assert "BEGIN:VEVENT" not in lines


def test_malformed_rows_are_skipped_not_fatal():
    """A device subscribing at the wrong moment must not get a 500."""

    feed = build_wall_feed(
        deadlines=[{"title": "No date here"}, _deadline()],
        care_gaps=[{"recipient": "Leo"}],
        scheduled_events=[{"title": "no start"}],
        now=NOW,
    )
    assert _lines(feed).count("BEGIN:VEVENT") == 1
