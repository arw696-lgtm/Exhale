"""Care-Coverage Engine on the real Ward household.

Runs the coverage engine over the ISLA 2026-2027 calendar, Ali's inferred work
pattern, and the two concerts that actually sit on the shared calendar, and
prints the care gaps it surfaces.

    cd backend && PYTHONPATH=src python examples/demo_coverage.py
"""

from datetime import date, datetime, time

from exhale.coverage import (
    Caregiver,
    CalendarEvent,
    CareRecipient,
    CoverageEngine,
    SchoolCalendar,
    WorkPattern,
    build_care_watch,
)
from exhale.schemas import FactOrigin

# --- the ISLA 2026-2027 no-school days (observed from the student calendar) --------
NO_SCHOOL = {
    date(2026, 9, 7): "Labor Day",
    date(2026, 9, 21): "Yom Kippur + PD",
    date(2026, 10, 15): "MEA break",
    date(2026, 10, 16): "MEA break",
    date(2026, 10, 29): "Parent-Teacher Conferences",
    date(2026, 10, 30): "Parent-Teacher Conferences",
    date(2026, 11, 25): "Thanksgiving Break",
    date(2026, 11, 26): "Thanksgiving Break",
    date(2026, 11, 27): "Thanksgiving Break",
    date(2026, 12, 4): "Grading + PD",
}

ISLA = SchoolCalendar(
    name="ISLA",
    first_day=date(2026, 9, 1),   # Stevie is grade 1 → Sept 1, not the Aug 31 PK-K start
    last_day=date(2027, 6, 3),
    no_school_days=NO_SCHOOL,
)

# --- the two real shared-calendar concerts ----------------------------------------
CONCERTS = [
    CalendarEvent("Gary Clark Jr.",
                  datetime(2026, 9, 19, 19, 30), datetime(2026, 9, 19, 21, 0),
                  attendees=("Ali", "Andy"), source_reference="shared_cal_gcj"),
    CalendarEvent("Monrovia Concert",
                  datetime(2026, 10, 2, 19, 0), datetime(2026, 10, 2, 20, 0),
                  attendees=("Ali", "Andy"), source_reference="shared_cal_monrovia"),
]

# Ali: government job, M-F 7:30-4:30, federal holidays off (inferred pattern).
ali = Caregiver(
    name="Ali", role="PARENT",
    work_pattern=WorkPattern(
        weekdays=frozenset({0, 1, 2, 3, 4}), start=time(7, 30), end=time(16, 30),
        days_off=frozenset({date(2026, 9, 7), date(2026, 11, 26)}),  # fed holidays
        basis=FactOrigin.INFERRED),
    events=list(CONCERTS),
)
# Andy: flexible; a couple of client commitments land on no-school weekdays.
andy = Caregiver(
    name="Andy", role="PARENT",
    events=CONCERTS + [
        CalendarEvent("Client review",
                      datetime(2026, 10, 15, 9, 0), datetime(2026, 10, 15, 12, 0),
                      attendees=("Andy",)),
        CalendarEvent("Prospect meeting",
                      datetime(2026, 10, 29, 13, 0), datetime(2026, 10, 29, 15, 0),
                      attendees=("Andy",)),
    ],
)

engine = CoverageEngine(
    CareRecipient("Stevie"), [ali, andy], school=ISLA,
    now=datetime(2026, 9, 8, 8, 0),
)
watch = build_care_watch(engine, date(2026, 9, 8), date(2026, 12, 15))

s = watch["summary"]
print(f"\nCare Watch for {watch['recipient']}  ({watch['range']['from']} → {watch['range']['to']})")
print(f"  {s['total_gaps']} care gaps  "
      f"[🔴 {s['critical']}  🟡 {s['important']}  🔵 {s['advisory']}]  "
      f"· {s['assumption_dependent']} rest on an assumption\n")
for g in watch["gaps"]:
    flag = "  ⚠ assumes Ali's usual hours" if g["depends_on_inference"] else ""
    print(f"{g['indicator']} {g['date']}  {g['start'][11:16]}-{g['end'][11:16]} "
          f"({g['duration_hours']}h){flag}")
    print(f"     why:  {g['reason']}")
    print(f"     do:   {g['suggested_action']}")
