"""Tests for the work-window engine — the intent side of the coverage math.

'I want to work N times this week — when's best?' answered against the same
inputs the Care-Coverage Engine uses: a caregiver can work when they're free
AND the child is covered by someone/something else.
"""

from datetime import date, datetime, time

from exhale.coverage import (
    Caregiver,
    CalendarEvent,
    CareRecipient,
    CoverageEngine,
    SchoolCalendar,
    WorkPattern,
    build_work_plan,
    suggest_work_windows,
)
from exhale.schemas import FactOrigin

STEVIE = CareRecipient(name="Stevie")
ISLA = SchoolCalendar(
    name="ISLA", first_day=date(2026, 9, 1), last_day=date(2027, 6, 3),
    no_school_days={date(2026, 10, 15): "MEA break"},
)
BEFORE = datetime(2026, 9, 10, 6, 0)


def _ali(events=()):
    return Caregiver(
        name="Ali", role="PARENT",
        work_pattern=WorkPattern(
            weekdays=frozenset({0, 1, 2, 3, 4}), start=time(7, 30), end=time(16, 30),
            basis=FactOrigin.INFERRED),
        events=list(events),
    )


def _andy(events=()):
    return Caregiver(name="Andy", role="PARENT", events=list(events))


def _engine(caregivers, now=BEFORE):
    return CoverageEngine(STEVIE, caregivers, school=ISLA, now=now)


# --- school-day windows -----------------------------------------------------------
def test_school_day_workable_covers_school_hours_excludes_pickup_pinch():
    # Wed 9/16 in session. Andy free all day; Ali works 7:30-4:30. Andy can work
    # while Stevie's at school and while Ali's home — but NOT the drop-off/pickup
    # pinch (7:30-8:30, 3:30-4:30) when he's the only one with Stevie.
    windows = _engine([_ali(), _andy()]).open_windows_on(date(2026, 9, 16), "Andy")
    spans = {(w.start.time(), w.end.time()) for w in windows}
    assert (time(8, 30), time(15, 30)) in spans     # school block is workable
    assert (time(6, 0), time(7, 30)) in spans        # Ali home before work
    assert (time(16, 30), time(22, 0)) in spans      # Ali home after work
    # The pinch is NOT workable — it's childcare, not a gap and not free time.
    assert not any(s <= time(8, 0) < e for s, e in spans if s >= time(7, 30))


def test_school_block_names_what_covers_the_child():
    w = next(w for w in _engine([_ali(), _andy()]).open_windows_on(date(2026, 9, 16), "Andy")
             if w.start.time() == time(8, 30))
    assert any("ISLA" in label for label in w.child_covered_by)


def test_caregiver_event_removes_that_window():
    # Andy has a dentist appt 10-11 → not free then, so it's not workable.
    andy = _andy([CalendarEvent("Dentist", datetime(2026, 9, 16, 10, 0),
                                datetime(2026, 9, 16, 11, 0), attendees=("Andy",))])
    windows = _engine([_ali(), andy]).open_windows_on(date(2026, 9, 16), "Andy")
    assert not any(w.start.time() <= time(10, 30) < w.end.time() for w in windows)


# --- no-school day ----------------------------------------------------------------
def test_no_school_day_andy_can_work_only_when_ali_is_home():
    # 10/15 MEA: no school. Ali works 7:30-4:30. Andy free. Andy can work only
    # the fringes when Ali's home (before 7:30, after 4:30) — midday he's on duty.
    windows = _engine([_ali(), _andy()]).open_windows_on(date(2026, 10, 15), "Andy")
    spans = {(w.start.time(), w.end.time()) for w in windows}
    assert (time(6, 0), time(7, 30)) in spans
    assert (time(16, 30), time(22, 0)) in spans
    assert not any(s < time(12, 0) < e for s, e in spans)  # no midday work


# --- suggestion / ranking ---------------------------------------------------------
def test_min_hours_filters_short_windows():
    windows = _engine([_ali(), _andy()]).work_windows(
        "Andy", date(2026, 9, 16), date(2026, 9, 16), min_hours=3.0)
    assert all(w.duration_hours >= 3.0 for w in windows)
    # The 1.5h fringe windows are excluded; the ~7h school block remains.
    assert any(w.duration_hours >= 6 for w in windows)


def test_suggest_returns_best_n_in_time_order():
    windows = suggest_work_windows(
        _engine([_ali(), _andy()]), "Andy",
        date(2026, 9, 14), date(2026, 9, 18), count=3, min_hours=2.0)
    assert len(windows) == 3
    assert [w.start for w in windows] == sorted(w.start for w in windows)  # chronological
    # Every suggested block is a full school day (~7h), the longest available.
    assert all(w.duration_hours >= 6 for w in windows)


def test_build_work_plan_shape():
    plan = build_work_plan(
        _engine([_ali(), _andy()]), "Andy",
        date(2026, 9, 14), date(2026, 9, 18), count=2, min_hours=2.0)
    assert plan["view"] == "work_windows"
    assert plan["caregiver"] == "Andy"
    assert plan["summary"]["suggested"] == 2
    assert plan["summary"]["total_hours"] > 0
    assert len(plan["windows"]) == 2


def test_unknown_caregiver_raises():
    import pytest
    with pytest.raises(KeyError):
        _engine([_ali(), _andy()]).open_windows_on(date(2026, 9, 16), "Nobody")


def test_past_windows_are_not_suggested():
    now = datetime(2026, 9, 17, 6, 0)  # after the 16th
    windows = _engine([_ali(), _andy()], now=now).open_windows_on(date(2026, 9, 16), "Andy")
    assert windows == []


def test_live_window_is_trimmed_to_now():
    # At 6pm, the evening window that opened at 4:30 must not include the
    # 90 minutes already gone.
    from datetime import datetime as _dt
    engine = CoverageEngine(STEVIE, [_ali(), _andy()], school=ISLA,
                            now=_dt(2026, 9, 16, 18, 0))
    windows = engine.open_windows_on(date(2026, 9, 16), "Andy")
    evening = next(w for w in windows if w.end.time() == time(22, 0))
    assert evening.start.time() == time(18, 0)
    assert evening.duration_hours == 4.0
