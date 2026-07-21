"""Serializable configuration for the Care-Coverage Engine.

The engine (:mod:`exhale.coverage`) works in native ``date``/``time``/``datetime``
dataclasses. To persist a household's coverage model and drive it over HTTP we
need a JSON-friendly mirror: these Pydantic models parse ISO strings from the
API, round-trip cleanly through the encrypted profile store (``model_dump(mode=
"json")``), and rebuild the engine on the way out. Keeping the wire contract in
its own module leaves the engine pure and free of serialization concerns.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from pydantic import BaseModel, Field

from exhale.coverage import (
    Caregiver,
    CalendarEvent,
    CareProgram,
    CareRecipient,
    CoverageEngine,
    SchoolCalendar,
    WorkPattern,
)
from exhale.schemas import FactOrigin


class WorkPatternIn(BaseModel):
    weekdays: list[int] = Field(description="0=Mon .. 6=Sun")
    start: time
    end: time
    days_off: list[date] = Field(default_factory=list)
    basis: FactOrigin = FactOrigin.INFERRED


class CalendarEventIn(BaseModel):
    title: str
    start: datetime
    end: datetime
    attendees: list[str] = Field(default_factory=list)
    source_reference: str | None = None
    origin: FactOrigin = FactOrigin.OBSERVED


class CaregiverIn(BaseModel):
    name: str
    role: str = "PARENT"
    work_pattern: WorkPatternIn | None = None
    events: list[CalendarEventIn] = Field(default_factory=list)


class SchoolCalendarIn(BaseModel):
    name: str
    first_day: date
    last_day: date
    school_start: time = time(8, 30)
    school_end: time = time(15, 30)
    # Map of closed weekday -> human reason ("MEA break").
    no_school_days: dict[date, str] = Field(default_factory=dict)
    origin: FactOrigin = FactOrigin.OBSERVED


class CareProgramIn(BaseModel):
    name: str
    dates: dict[date, tuple[time, time]] = Field(default_factory=dict)


class CareRecipientIn(BaseModel):
    name: str
    supervised_start: time = time(6, 0)
    supervised_end: time = time(22, 0)


class CoverageModelIn(BaseModel):
    """A household's full care-coverage configuration."""

    recipient: CareRecipientIn
    caregivers: list[CaregiverIn]
    school: SchoolCalendarIn | None = None
    care_programs: list[CareProgramIn] = Field(default_factory=list)


# --- Pydantic -> engine dataclasses -----------------------------------------------
def _naive(dt: datetime) -> datetime:
    """Coverage math is naive local wall-clock; drop any tz a client sent."""

    return dt.replace(tzinfo=None)


def _work_pattern(w: WorkPatternIn) -> WorkPattern:
    return WorkPattern(
        weekdays=frozenset(w.weekdays),
        start=w.start,
        end=w.end,
        days_off=frozenset(w.days_off),
        basis=w.basis,
    )


def _event(e: CalendarEventIn) -> CalendarEvent:
    return CalendarEvent(
        title=e.title,
        start=_naive(e.start),
        end=_naive(e.end),
        attendees=tuple(e.attendees),
        source_reference=e.source_reference,
        origin=e.origin,
    )


def _caregiver(c: CaregiverIn) -> Caregiver:
    return Caregiver(
        name=c.name,
        role=c.role,
        work_pattern=_work_pattern(c.work_pattern) if c.work_pattern else None,
        events=[_event(e) for e in c.events],
    )


def _school(s: SchoolCalendarIn) -> SchoolCalendar:
    return SchoolCalendar(
        name=s.name,
        first_day=s.first_day,
        last_day=s.last_day,
        school_start=s.school_start,
        school_end=s.school_end,
        no_school_days=dict(s.no_school_days),
        origin=s.origin,
    )


def build_engine(model: CoverageModelIn, *, now: datetime | None = None) -> CoverageEngine:
    """Reconstruct a live :class:`CoverageEngine` from stored config."""

    recipient = CareRecipient(
        name=model.recipient.name,
        supervised_start=model.recipient.supervised_start,
        supervised_end=model.recipient.supervised_end,
    )
    programs = tuple(
        CareProgram(name=p.name, dates={d: (w[0], w[1]) for d, w in p.dates.items()})
        for p in model.care_programs
    )
    return CoverageEngine(
        recipient,
        [_caregiver(c) for c in model.caregivers],
        school=_school(model.school) if model.school else None,
        care_programs=programs,
        now=now,
    )


def default_range(days: int = 14) -> tuple[date, date]:
    """The briefing's default care-watch horizon: today through +``days``."""

    today = date.today()
    return today, today + timedelta(days=days)


# --- merge synced calendar events back into a stored model ------------------------
_SYNCED_PREFIX = "gcal_"


def merge_events(
    model: CoverageModelIn, caregiver_name: str, events: list
) -> CoverageModelIn:
    """Return a copy of ``model`` with ``events`` merged into one caregiver.

    Idempotent: any previously-synced events (source_reference starting
    ``gcal_``) on that caregiver are dropped first, so re-syncing replaces rather
    than duplicates. ``events`` are engine :class:`~exhale.coverage.CalendarEvent`
    instances (e.g. from the Google Calendar connector).

    Raises ``KeyError`` if the named caregiver isn't in the model.
    """

    data = model.model_dump()
    for caregiver in data["caregivers"]:
        if caregiver["name"] != caregiver_name:
            continue
        kept = [
            e for e in caregiver["events"]
            if not str(e.get("source_reference", "")).startswith(_SYNCED_PREFIX)
        ]
        synced = [
            CalendarEventIn(
                title=ev.title, start=ev.start, end=ev.end,
                attendees=list(ev.attendees), source_reference=ev.source_reference,
                origin=ev.origin,
            ).model_dump()
            for ev in events
        ]
        caregiver["events"] = kept + synced
        return CoverageModelIn(**data)
    raise KeyError(f"No caregiver named {caregiver_name!r} in the coverage model")
