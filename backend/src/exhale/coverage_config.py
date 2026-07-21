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

from pydantic import BaseModel, Field, model_validator

from exhale.coverage import (
    Caregiver,
    CalendarEvent,
    CareProgram,
    CareRecipient,
    CoverageEngine,
    FamilyCoverage,
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


class ChildIn(BaseModel):
    """One supervised child: their hours, their school, their programs."""

    recipient: CareRecipientIn
    school: SchoolCalendarIn | None = None
    care_programs: list[CareProgramIn] = Field(default_factory=list)


class CoverageModelIn(BaseModel):
    """A household's full care-coverage configuration.

    Canonical shape: ``children`` (any number of kids) over a shared
    ``caregivers`` roster. The original single-child fields (``recipient`` /
    ``school`` / ``care_programs``) remain accepted for stored profiles and
    older clients — a validator folds them into a one-entry ``children`` list
    and clears them, so every parsed model has exactly one shape.
    """

    children: list[ChildIn] = Field(default_factory=list)
    caregivers: list[CaregiverIn]
    # Legacy single-child fields — normalized into `children`, then cleared.
    recipient: CareRecipientIn | None = None
    school: SchoolCalendarIn | None = None
    care_programs: list[CareProgramIn] = Field(default_factory=list)

    @model_validator(mode="after")
    def _normalize_children(self) -> "CoverageModelIn":
        if not self.children:
            if self.recipient is None:
                raise ValueError("coverage model needs at least one child "
                                 "(children=[...] or the legacy recipient field)")
            self.children = [ChildIn(recipient=self.recipient, school=self.school,
                                     care_programs=self.care_programs)]
        self.recipient = None
        self.school = None
        self.care_programs = []
        return self


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


def build_engines(model: CoverageModelIn, *, now: datetime | None = None) -> list[CoverageEngine]:
    """One live :class:`CoverageEngine` per child, over the shared caregivers."""

    caregivers = [_caregiver(c) for c in model.caregivers]
    engines: list[CoverageEngine] = []
    for child in model.children:
        recipient = CareRecipient(
            name=child.recipient.name,
            supervised_start=child.recipient.supervised_start,
            supervised_end=child.recipient.supervised_end,
        )
        programs = tuple(
            CareProgram(name=p.name, dates={d: (w[0], w[1]) for d, w in p.dates.items()})
            for p in child.care_programs
        )
        engines.append(CoverageEngine(
            recipient,
            caregivers,
            school=_school(child.school) if child.school else None,
            care_programs=programs,
            now=now,
        ))
    return engines


def build_family(model: CoverageModelIn, *, now: datetime | None = None) -> FamilyCoverage:
    """The whole household's coverage: merged care gaps, intersected work windows."""

    return FamilyCoverage(build_engines(model, now=now))


def build_engine(model: CoverageModelIn, *, now: datetime | None = None) -> CoverageEngine:
    """The first (or only) child's engine — the single-child compatibility path."""

    return build_engines(model, now=now)[0]


def default_range(days: int = 14) -> tuple[date, date]:
    """The briefing's default care-watch horizon: today through +``days``."""

    today = date.today()
    return today, today + timedelta(days=days)


# --- merge synced calendar events back into a stored model ------------------------
# Source-reference prefixes that mark a machine-synced event (vs. a manual one),
# so re-syncing replaces rather than duplicates. gcal_ = Google, msgraph_ =
# Outlook/Office 365, ics_ = published iCloud/Outlook/Google feed.
_SYNCED_PREFIXES = ("gcal_", "msgraph_", "ics_")


def merge_events(
    model: CoverageModelIn,
    caregiver_name: str,
    events: list,
    *,
    source_prefix: str | None = None,
) -> CoverageModelIn:
    """Return a copy of ``model`` with ``events`` merged into one caregiver.

    Idempotent: previously-synced events on that caregiver are dropped before the
    fresh set is added, so re-syncing replaces rather than duplicates.
    ``source_prefix`` scopes *which* synced events are replaced — pass ``"gcal_"``
    or ``"ics_"`` so a Google re-sync doesn't disturb ICS-synced events and vice
    versa; ``None`` replaces any machine-synced event. Manual events (any other
    source_reference) are always preserved. ``events`` are engine
    :class:`~exhale.coverage.CalendarEvent` instances.

    Raises ``KeyError`` if the named caregiver isn't in the model.
    """

    prefixes = (source_prefix,) if source_prefix else _SYNCED_PREFIXES

    def _is_synced(e: dict) -> bool:
        ref = str(e.get("source_reference", ""))
        return any(ref.startswith(p) for p in prefixes)

    data = model.model_dump()
    for caregiver in data["caregivers"]:
        if caregiver["name"] != caregiver_name:
            continue
        kept = [e for e in caregiver["events"] if not _is_synced(e)]
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
