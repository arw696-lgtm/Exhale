"""Tests for the background auto-sync (replayed syncs, isolated failures)."""

import time as _time
from datetime import datetime

import pytest

from exhale import auto_sync
from exhale.auto_sync import AutoSyncScheduler, run_cycle, scheduler_from_env
from exhale.coverage import CalendarEvent
from exhale.extraction import extract_payload
from exhale.schemas import FactOrigin
from exhale.store import HouseholdStore


def _model():
    return {
        "recipient": {"name": "Stevie", "supervised_start": "06:00:00",
                      "supervised_end": "22:00:00"},
        "caregivers": [
            {"name": "Ali", "role": "PARENT", "work_pattern": None, "events": []},
            {"name": "Andy", "role": "PARENT", "work_pattern": None, "events": []},
        ],
        "school": None,
        "care_programs": [],
    }


def _family(store, fid, **profile):
    store.set_profile(fid, **profile)
    return fid


class _FakeICS:
    def __init__(self, url, *, attendees, tz="America/Chicago"):
        self.attendees = attendees

    def fetch_busy(self):
        return [CalendarEvent(
            "Synced concert", datetime(2026, 9, 19, 19, 0), datetime(2026, 9, 19, 21, 0),
            attendees=tuple(self.attendees), source_reference="ics_auto1",
            origin=FactOrigin.OBSERVED)]


class _BrokenICS:
    def __init__(self, *a, **k):
        pass

    def fetch_busy(self):
        raise RuntimeError("feed is down")


def test_cycle_replays_remembered_ics_sync(monkeypatch):
    monkeypatch.setattr(auto_sync, "ICSCalendarConnector", _FakeICS)
    store = HouseholdStore()
    _family(store, "fam_a", coverage_model=_model(), sync_configs={
        "ics": [{"url": "https://x/cal.ics", "attendees": ["Ali", "Andy"], "holder": "Ali"}]})

    report = run_cycle(store, extract_payload)
    assert report["families"]["fam_a"]["ics_0"] == {"synced_busy_events": 1}
    # The event landed in the stored coverage model.
    model = store.profile("fam_a")["coverage_model"]
    ali = next(c for c in model["caregivers"] if c["name"] == "Ali")
    assert any(e["source_reference"] == "ics_auto1" for e in ali["events"])


def test_one_familys_failure_does_not_stall_the_next(monkeypatch):
    # fam_bad's feed raises; fam_good must still sync.
    calls = {"n": 0}

    class _FlakyICS:
        def __init__(self, url, *, attendees, tz="America/Chicago"):
            self.url, self.attendees = url, attendees

        def fetch_busy(self):
            if "bad" in self.url:
                raise RuntimeError("boom")
            return _FakeICS("x", attendees=self.attendees).fetch_busy()

    monkeypatch.setattr(auto_sync, "ICSCalendarConnector", _FlakyICS)
    store = HouseholdStore()
    _family(store, "fam_bad", coverage_model=_model(), sync_configs={
        "ics": [{"url": "https://bad/cal.ics", "attendees": ["Ali"]}]})
    _family(store, "fam_good", coverage_model=_model(), sync_configs={
        "ics": [{"url": "https://good/cal.ics", "attendees": ["Ali"]}]})

    report = run_cycle(store, extract_payload)
    assert "error" in report["families"]["fam_bad"]["ics_0"]
    assert report["families"]["fam_good"]["ics_0"] == {"synced_busy_events": 1}


def test_gmail_skipped_when_google_not_connected():
    store = HouseholdStore()
    _family(store, "fam_nogoogle", coverage_model=_model())
    report = run_cycle(store, extract_payload)
    assert report["families"]["fam_nogoogle"]["gmail"] == {"skipped": "google not connected"}


def test_calendar_replay_skipped_without_connection():
    store = HouseholdStore()
    _family(store, "fam_c", coverage_model=_model(), sync_configs={
        "gcal": {"caregiver_name": "Andy", "calendar_id": "primary", "days": 30}})
    report = run_cycle(store, extract_payload)
    assert "skipped" in report["families"]["fam_c"]["gcal"]


# --- scheduler --------------------------------------------------------------------
def test_scheduler_runs_cycles_and_stops(monkeypatch):
    monkeypatch.setattr(auto_sync, "ICSCalendarConnector", _FakeICS)
    store = HouseholdStore()
    _family(store, "fam_s", coverage_model=_model(), sync_configs={
        "ics": [{"url": "https://x/cal.ics", "attendees": ["Ali"]}]})

    sched = AutoSyncScheduler(store, extract_payload, interval_minutes=0.001)  # ~60ms
    sched.start()
    deadline = _time.time() + 3
    while sched.cycles_run == 0 and _time.time() < deadline:
        _time.sleep(0.02)
    sched.stop()
    assert sched.cycles_run >= 1
    assert sched.last_report is not None
    assert "fam_s" in sched.last_report["families"]


def test_scheduler_rejects_nonpositive_interval():
    with pytest.raises(ValueError):
        AutoSyncScheduler(HouseholdStore(), extract_payload, interval_minutes=0)


def test_scheduler_from_env_off_by_default(monkeypatch):
    monkeypatch.delenv("EXHALE_AUTO_SYNC_MINUTES", raising=False)
    assert scheduler_from_env(HouseholdStore(), extract_payload) is None
    monkeypatch.setenv("EXHALE_AUTO_SYNC_MINUTES", "0")
    assert scheduler_from_env(HouseholdStore(), extract_payload) is None
    monkeypatch.setenv("EXHALE_AUTO_SYNC_MINUTES", "not-a-number")
    assert scheduler_from_env(HouseholdStore(), extract_payload) is None


def test_scheduler_from_env_starts_when_set(monkeypatch):
    monkeypatch.setenv("EXHALE_AUTO_SYNC_MINUTES", "30")
    sched = scheduler_from_env(HouseholdStore(), extract_payload)
    assert sched is not None
    assert sched.interval_minutes == 30
    sched.stop()
