"""Tests for the Care-Coverage Engine.

Fixtures use the real Ward household: Stevie (needs supervision), the ISLA
2026-2027 calendar's no-school days, Ali's inferred M-F 7:30-4:30 work pattern,
and the two actual concerts on the shared calendar (Gary Clark Jr. Sep 19,
Monrovia Oct 2) — the events that generate sitter gaps.
"""

from datetime import date, datetime, time

from exhale.coverage import (
    Caregiver,
    CalendarEvent,
    CareProgram,
    CareRecipient,
    CoverageEngine,
    SchoolCalendar,
    WorkPattern,
    _subtract,
    _union,
    build_care_watch,
)
from exhale.forgetting_engine import ThreatLevel
from exhale.schemas import FactOrigin


# --- interval arithmetic ----------------------------------------------------------
def _iv(h1, h2):
    return (datetime(2026, 9, 1, h1), datetime(2026, 9, 1, h2))


def test_subtract_removes_overlap():
    assert _subtract([_iv(6, 22)], [_iv(9, 11)]) == [_iv(6, 9), _iv(11, 22)]


def test_subtract_disjoint_is_noop():
    assert _subtract([_iv(6, 8)], [_iv(9, 11)]) == [_iv(6, 8)]


def test_subtract_full_cover_empties():
    assert _subtract([_iv(9, 11)], [_iv(6, 22)]) == []


def test_union_merges_touching_and_overlapping():
    assert _union([_iv(6, 9), _iv(8, 12), _iv(16, 22)]) == [_iv(6, 12), _iv(16, 22)]


# --- fixtures ---------------------------------------------------------------------
STEVIE = CareRecipient(name="Stevie")

ISLA = SchoolCalendar(
    name="ISLA",
    first_day=date(2026, 9, 1),
    last_day=date(2027, 6, 3),
    no_school_days={
        date(2026, 10, 15): "MEA break",
        date(2026, 10, 16): "MEA break",
    },
)


def _ali(events=()):
    return Caregiver(
        name="Ali",
        role="PARENT",
        work_pattern=WorkPattern(
            weekdays=frozenset({0, 1, 2, 3, 4}),
            start=time(7, 30),
            end=time(16, 30),
            basis=FactOrigin.INFERRED,
        ),
        events=list(events),
    )


def _andy(events=()):
    return Caregiver(name="Andy", role="PARENT", events=list(events))


BEFORE = datetime(2026, 9, 10, 8, 0)  # a fixed "now" well before the test dates


# --- school-day coverage ----------------------------------------------------------
def test_school_day_with_a_free_parent_has_no_gap():
    engine = CoverageEngine(STEVIE, [_ali(), _andy()], school=ISLA, now=BEFORE)
    assert engine.scan_day(date(2026, 9, 16)) == []  # Wed, in session, Andy free


def test_school_day_with_both_parents_working_pinches_before_and_after():
    # Ali 7:30-4:30, Andy at a job 8:00-5:00 → school covers 8:30-3:30, leaving
    # the classic drop-off and pickup gaps.
    andy = _andy([CalendarEvent(
        "Client onsite",
        datetime(2026, 9, 16, 8, 0), datetime(2026, 9, 16, 17, 0),
        attendees=("Andy",))])
    engine = CoverageEngine(STEVIE, [_ali(), andy], school=ISLA, now=BEFORE)
    gaps = engine.scan_day(date(2026, 9, 16))
    windows = [(g.start.time(), g.end.time()) for g in gaps]
    assert (time(8, 0), time(8, 30)) in windows    # morning pinch
    assert (time(15, 30), time(16, 30)) in windows  # afternoon pinch


# --- no-school-day coverage -------------------------------------------------------
def test_no_school_day_free_parent_covers_it():
    # Oct 15 MEA break: Ali works, Andy is free → Andy has Stevie, no gap.
    engine = CoverageEngine(STEVIE, [_ali(), _andy()], school=ISLA, now=BEFORE)
    assert engine.scan_day(date(2026, 10, 15)) == []


def test_no_school_day_with_both_tied_up_is_a_gap():
    andy = _andy([CalendarEvent(
        "Client call",
        datetime(2026, 10, 15, 9, 0), datetime(2026, 10, 15, 11, 0),
        attendees=("Andy",))])
    engine = CoverageEngine(STEVIE, [_ali(), andy], school=ISLA, now=BEFORE)
    gaps = engine.scan_day(date(2026, 10, 15))
    assert len(gaps) == 1
    gap = gaps[0]
    assert (gap.start.time(), gap.end.time()) == (time(9, 0), time(11, 0))
    assert "school closed (MEA break)" in gap.reason
    assert "Ali working" in gap.reason
    assert "Andy at Client call" in gap.reason
    # Rests on Ali's *inferred* work pattern → flagged assumption-dependent.
    assert gap.depends_on_inference is True


# --- the concert gaps (real shared-calendar events) -------------------------------
GARY_CLARK = CalendarEvent(
    "Gary Clark Jr.",
    datetime(2026, 9, 19, 19, 30), datetime(2026, 9, 19, 21, 0),
    attendees=("Ali", "Andy"), source_reference="cal_gcj",
)
MONROVIA = CalendarEvent(
    "Monrovia Concert",
    datetime(2026, 10, 2, 19, 0), datetime(2026, 10, 2, 20, 0),
    attendees=("Ali", "Andy"), source_reference="cal_monrovia",
)


def test_shared_calendar_concert_creates_a_sitter_gap():
    engine = CoverageEngine(
        STEVIE, [_ali([GARY_CLARK]), _andy([GARY_CLARK])], school=ISLA, now=BEFORE
    )
    gaps = engine.scan_day(date(2026, 9, 19))  # Saturday
    assert len(gaps) == 1
    gap = gaps[0]
    assert (gap.start.time(), gap.end.time()) == (time(19, 30), time(21, 0))
    assert "Ali at Gary Clark Jr." in gap.reason
    assert "Andy at Gary Clark Jr." in gap.reason
    assert "sitter" in gap.suggested_action.lower()
    # Both parents' absence is OBSERVED from the shared calendar — not an
    # assumption. This gap is high-confidence.
    assert gap.depends_on_inference is False


def test_concert_gap_is_suppressed_when_one_parent_stays_home():
    # Only Andy on the ticket → Ali covers Stevie → no gap.
    solo = CalendarEvent(
        "Gary Clark Jr.",
        datetime(2026, 9, 19, 19, 30), datetime(2026, 9, 19, 21, 0),
        attendees=("Andy",))
    engine = CoverageEngine(
        STEVIE, [_ali(), _andy([solo])], school=ISLA, now=BEFORE
    )
    assert engine.scan_day(date(2026, 9, 19)) == []


# --- relatives & care programs ----------------------------------------------------
def test_relative_caregiver_changes_the_suggested_action():
    grandma = Caregiver(name="Grandma Shelley", role="RELATIVE", events=[
        CalendarEvent("Book club",
                      datetime(2026, 9, 19, 19, 0), datetime(2026, 9, 19, 21, 30),
                      attendees=("Grandma Shelley",))])  # busy this night too
    engine = CoverageEngine(
        STEVIE, [_ali([GARY_CLARK]), _andy([GARY_CLARK]), grandma],
        school=ISLA, now=BEFORE,
    )
    gap = engine.scan_day(date(2026, 9, 19))[0]
    assert gap.suggested_action == "Ask Grandma Shelley, or book a sitter"


def test_care_program_covers_a_no_school_day():
    # Aventuras runs 8-4 on the MEA day → even with both parents tied up, covered
    # across those hours.
    aventuras = CareProgram(name="Aventuras",
                            dates={date(2026, 10, 15): (time(8, 0), time(16, 0))})
    andy = _andy([CalendarEvent(
        "Client call",
        datetime(2026, 10, 15, 9, 0), datetime(2026, 10, 15, 11, 0),
        attendees=("Andy",))])
    engine = CoverageEngine(STEVIE, [_ali(), andy], school=ISLA,
                            care_programs=(aventuras,), now=BEFORE)
    # The 9-11 gap is now inside Aventuras hours → gone.
    assert engine.scan_day(date(2026, 10, 15)) == []


# --- threat stratification (reuses forgetting-engine bands) ------------------------
def _both_out(day, h1, h2):
    ev = CalendarEvent("Out", datetime(day.year, day.month, day.day, h1),
                       datetime(day.year, day.month, day.day, h2),
                       attendees=("Ali", "Andy"))
    return [_ali([ev]), _andy([ev])]


def test_gap_tomorrow_is_critical():
    now = datetime(2026, 9, 18, 8, 0)
    day = date(2026, 9, 19)
    engine = CoverageEngine(STEVIE, _both_out(day, 19, 20), now=now)
    assert engine.scan_day(day)[0].threat_level is ThreatLevel.CRITICAL


def test_gap_next_week_is_important():
    now = datetime(2026, 9, 12, 8, 0)
    day = date(2026, 9, 19)
    engine = CoverageEngine(STEVIE, _both_out(day, 19, 20), now=now)
    assert engine.scan_day(day)[0].threat_level is ThreatLevel.IMPORTANT


def test_gap_far_out_is_advisory():
    now = datetime(2026, 9, 1, 8, 0)
    day = date(2026, 10, 30)
    engine = CoverageEngine(STEVIE, _both_out(day, 19, 20), now=now)
    assert engine.scan_day(day)[0].threat_level is ThreatLevel.ADVISORY


def test_past_gaps_are_not_surfaced():
    now = datetime(2026, 9, 20, 8, 0)  # after the concert
    engine = CoverageEngine(STEVIE, _both_out(date(2026, 9, 19), 19, 20), now=now)
    assert engine.scan_day(date(2026, 9, 19)) == []


# --- care watch assembler ---------------------------------------------------------
def test_build_care_watch_summarizes_the_range():
    now = datetime(2026, 9, 10, 8, 0)
    ali = _ali([GARY_CLARK, MONROVIA])
    andy = _andy([GARY_CLARK, MONROVIA])
    andy.events.append(CalendarEvent(
        "Client call",
        datetime(2026, 10, 15, 9, 0), datetime(2026, 10, 15, 11, 0),
        attendees=("Andy",)))
    engine = CoverageEngine(STEVIE, [ali, andy], school=ISLA, now=now)
    watch = build_care_watch(engine, date(2026, 9, 10), date(2026, 10, 31))

    assert watch["view"] == "care_watch"
    assert watch["recipient"] == "Stevie"
    # Two concerts + the MEA-day work conflict = three gaps.
    assert watch["summary"]["total_gaps"] == 3
    reasons = " ".join(g["reason"] for g in watch["gaps"])
    assert "Gary Clark Jr." in reasons
    assert "Monrovia Concert" in reasons
    assert "MEA break" in reasons
    # The MEA-day gap leans on Ali's inferred hours; the concerts don't.
    assert watch["summary"]["assumption_dependent"] == 1
