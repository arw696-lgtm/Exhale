"""Tests for the Waiting-On ledger (the Hennepin County thread problem)."""

from datetime import date

from exhale.waiting import build_waiting_watch, new_item, resolve_item

TODAY = date(2026, 7, 21)


def _item(who="Hennepin County", about="arborist follow-up", since=None):
    return new_item(who, about, since=since or TODAY, channel="email")


def test_fresh_wait_is_advisory_no_nudge():
    watch = build_waiting_watch([_item(since=date(2026, 7, 19))], now=TODAY)
    item = watch["items"][0]
    assert item["days_waiting"] == 2
    assert item["threat_level"] == "ADVISORY"
    assert "no action needed" in item["suggested_action"].lower()


def test_week_old_wait_wants_a_nudge():
    watch = build_waiting_watch([_item(since=date(2026, 7, 13))], now=TODAY)
    item = watch["items"][0]
    assert item["days_waiting"] == 8
    assert item["threat_level"] == "IMPORTANT"
    assert item["suggested_action"] == "Nudge Hennepin County"
    assert watch["summary"]["need_nudge"] == 1


def test_two_week_old_wait_is_critical():
    watch = build_waiting_watch([_item(since=date(2026, 7, 6))], now=TODAY)
    assert watch["items"][0]["threat_level"] == "CRITICAL"


def test_resolved_items_drop_from_watch_but_stay_in_list():
    items = [_item()]
    items = resolve_item(items, items[0]["id"])
    assert items[0]["resolved"] is True          # kept, marked
    assert build_waiting_watch(items, now=TODAY)["summary"]["open"] == 0


def test_resolve_unknown_raises():
    import pytest
    with pytest.raises(KeyError):
        resolve_item([_item()], "wait_nope")


def test_watch_sorts_oldest_first():
    items = [_item(since=date(2026, 7, 18)), _item(since=date(2026, 7, 1))]
    watch = build_waiting_watch(items, now=TODAY)
    assert watch["items"][0]["since"] == "2026-07-01"
