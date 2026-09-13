"""Tests for the work-window engine — the intent side of the coverage math.

'I want to work N times this week — when's best?' answered against the same
inputs the Care-Coverage Engine uses: a caregiver can work when they're free
AND the child is covered by someone/something else.
"""

from datetime import date, datetime, time

from exhale.coverage import (
    CareAssignment,
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



def _ali_holding(day, start, end, **kw):
    """Ali, with an explicit statement that she has Stevie for a stretch.

    Since a co-parent being off work no longer implies they have the child,
    every test that wants "Ali covers this" has to say so — which is the point:
    the engine can only report what the household actually told it.
    """
    cg = _ali(**kw)
    cg.care_assignments.append(
        CareAssignment(datetime.combine(day, start), datetime.combine(day, end),
                       note="Ali has Stevie")
    )
    return cg

def _engine(caregivers, now=BEFORE):
    return CoverageEngine(STEVIE, caregivers, school=ISLA, now=now)


# --- school-day windows -----------------------------------------------------------
def test_school_day_workable_is_exactly_the_school_block():
    """School puts Stevie somewhere. Ali being off work does not.

    This used to also assert 6:00-7:30 and 16:30-22:00 as workable, on the
    grounds that Ali was home then. She may well have been — but nothing said
    she had Stevie, and the two parents being home together is family time, not
    a window either of them can spend. Only the school block survives.
    """
    windows = _engine([_ali(), _andy()]).open_windows_on(date(2026, 9, 16), "Andy")
    spans = {(w.start.time(), w.end.time()) for w in windows}
    assert spans == {(time(8, 30), time(15, 30))}
    # The drop-off/pickup pinch was never workable and still is not.
    assert not any(s <= time(8, 0) < e for s, e in spans)


def test_a_stated_handover_does_open_a_window():
    """The feature is intact — it just has to rest on something stated."""
    ali = _ali_holding(date(2026, 9, 16), time(16, 30), time(22, 0))
    windows = _engine([ali, _andy()]).open_windows_on(date(2026, 9, 16), "Andy")
    spans = {(w.start.time(), w.end.time()) for w in windows}
    assert (time(16, 30), time(22, 0)) in spans
    evening = next(w for w in windows if w.start.time() == time(16, 30))
    assert any("Ali" in label for label in evening.child_covered_by)


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
def test_no_school_day_offers_nothing_until_someone_says_who_has_him():
    """The case that started this: a day off school is not a day off.

    10/15 is MEA break. Ali works 7:30-4:30, so she is "available" at either
    end of it — which used to be read as her having Stevie, handing Andy
    fringe windows nobody had agreed to. On a no-school day with no handover
    stated, the honest answer is that there is no window at all.
    """
    windows = _engine([_ali(), _andy()]).open_windows_on(date(2026, 10, 15), "Andy")
    assert windows == []


def test_no_school_day_with_a_handover_offers_exactly_that():
    ali = _ali_holding(date(2026, 10, 15), time(16, 30), time(22, 0))
    windows = _engine([ali, _andy()]).open_windows_on(date(2026, 10, 15), "Andy")
    spans = {(w.start.time(), w.end.time()) for w in windows}
    assert spans == {(time(16, 30), time(22, 0))}


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
    ali = _ali_holding(date(2026, 9, 16), time(16, 30), time(22, 0))
    engine = CoverageEngine(STEVIE, [ali, _andy()], school=ISLA,
                            now=_dt(2026, 9, 16, 18, 0))
    windows = engine.open_windows_on(date(2026, 9, 16), "Andy")
    evening = next(w for w in windows if w.end.time() == time(22, 0))
    assert evening.start.time() == time(18, 0)
    assert evening.duration_hours == 4.0
