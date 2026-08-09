"""Tests for vacation mode (away periods).

The load-bearing rules: suppression is visible (never silent), deadlines are
NEVER suppressed (being away is when forms get forgotten), and outside the
range everything behaves exactly as before.
"""

from datetime import date, datetime, timedelta, timezone

from exhale.away import add_away, away_on, new_away, remove_away, suppress_care_gaps
from exhale.store import HouseholdStore
from exhale.wall_feed import build_wall_feed

NOW = datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc)
FAM = "fam_away"


def _watch(gap_days):
    gaps = []
    for d in gap_days:
        day = NOW.date() + timedelta(days=d)
        gaps.append({
            "recipient": "Leo",
            "date": day.isoformat(),
            "start": f"{day.isoformat()}T15:15:00",
            "end": f"{day.isoformat()}T17:00:00",
            "threat_level": "CRITICAL",
            "depends_on_inference": False,
        })
    return {
        "view": "care_watch",
        "summary": {"total_gaps": len(gaps), "critical": len(gaps),
                    "important": 0, "advisory": 0, "assumption_dependent": 0},
        "gaps": gaps,
    }


def _period(start_offset, end_offset, label="Portland"):
    return new_away(label,
                    NOW.date() + timedelta(days=start_offset),
                    NOW.date() + timedelta(days=end_offset))


# --- the store round-trip ----------------------------------------------------
def test_add_and_remove_away_period():
    store = HouseholdStore()
    period = add_away(store, FAM, label="Portland", start="2026-08-19", end="2026-08-24")
    assert store.profile(FAM)["away_periods"][0]["label"] == "Portland"
    assert remove_away(store, FAM, period["away_id"]) is True
    assert store.profile(FAM)["away_periods"] == []
    assert remove_away(store, FAM, "away_nope") is False


def test_backwards_range_rejected():
    import pytest

    with pytest.raises(ValueError):
        new_away("Oops", "2026-08-24", "2026-08-19")


def test_away_on_is_inclusive_both_ends():
    profile = {"away_periods": [new_away("Trip", "2026-08-19", "2026-08-24")]}
    assert away_on(profile, date(2026, 8, 19)) is not None
    assert away_on(profile, date(2026, 8, 24)) is not None
    assert away_on(profile, date(2026, 8, 18)) is None
    assert away_on(profile, date(2026, 8, 25)) is None


# --- care-gap suppression ----------------------------------------------------
def test_gaps_inside_away_suppressed_visibly():
    watch = _watch([1, 2, 8])          # two gaps inside the trip, one after
    out = suppress_care_gaps(watch, [_period(0, 5)])
    assert len(out["gaps"]) == 1
    assert out["away_suppressed"] == 2  # stated, never silent
    assert out["summary"]["total_gaps"] == 1
    assert out["summary"]["critical"] == 1


def test_no_away_periods_returns_watch_untouched():
    watch = _watch([1, 2])
    assert suppress_care_gaps(watch, []) is watch


def test_gaps_outside_range_unaffected():
    watch = _watch([8, 9])
    out = suppress_care_gaps(watch, [_period(0, 5)])
    assert "away_suppressed" not in out
    assert len(out["gaps"]) == 2


# --- the wall feed -----------------------------------------------------------
def test_feed_publishes_away_span_and_suppresses_gaps_inside():
    period = new_away("Portland", NOW.date() + timedelta(days=2),
                      NOW.date() + timedelta(days=6))
    gap_in = _watch([3])["gaps"][0]
    gap_out = _watch([9])["gaps"][0]
    feed = build_wall_feed(care_gaps=[gap_in, gap_out],
                           away_periods=[period], now=NOW)
    lines = feed.replace("\r\n ", "").split("\r\n")
    assert any("Family away — Portland" in x for x in lines)
    # Inclusive range → exclusive DTEND lands the day after the last day.
    assert f"DTEND;VALUE=DATE:{(NOW.date() + timedelta(days=7)).strftime('%Y%m%d')}" in lines
    # One "needs someone" survives (outside the trip); the inside one doesn't.
    assert sum("needs someone" in x for x in lines) == 1


def test_feed_deadlines_still_published_during_trip():
    """A form due mid-trip is still due — deadlines never suppress."""

    period = new_away("Portland", NOW.date(), NOW.date() + timedelta(days=6))
    deadline = {
        "obligation_id": "ob_forms", "title": "Health forms", "person": "Olivia",
        "deadline": (NOW.date() + timedelta(days=3)).isoformat(),
    }
    feed = build_wall_feed(deadlines=[deadline], away_periods=[period], now=NOW)
    assert "Health forms due — Olivia" in feed.replace("\r\n ", "")


def test_feed_past_away_periods_dropped():
    period = new_away("Spring break", NOW.date() - timedelta(days=30),
                      NOW.date() - timedelta(days=24))
    feed = build_wall_feed(away_periods=[period], now=NOW)
    assert "Family away" not in feed
