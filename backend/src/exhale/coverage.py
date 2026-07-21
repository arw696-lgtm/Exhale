"""Care-Coverage Engine (blueprint §7 sibling — forward-looking).

The Forgetting Engine scans a confirmed event and asks *"what prep does this
need, and is it done?"* The Coverage Engine asks the mirror question about a
child who requires constant supervision: *"what care does each day need, and is
it assigned?"* A **care gap** — a stretch where a supervised child has no
caregiver and no institution covering them — is a hard, safety-level obligation,
not a soft preference. It is the base layer the rest of the household schedule
stands on: "when can a parent work" and "when does the child need a sitter" are
the same question asked from two sides.

Inputs, each carrying its own provenance (the credibility discipline applied to
scheduling — an inferred fact must never masquerade as an observed one):

* a :class:`CareRecipient` — the child and the hours they need supervision;
* a :class:`SchoolCalendar` — in-session days, hours, and the **no-school days**
  that flip the child from school-covered to needing care (the operationally
  important part of a school calendar for a working household);
* :class:`Caregiver` s — parents/relatives/sitters, each unavailable during a
  recurring work pattern (typically *inferred* from a stated schedule) and/or
  specific calendar events they attend (*observed* from a shared calendar);
* optional :class:`CareProgram` s — e.g. a school's non-school-day care.

A gap's threat level reuses the Forgetting Engine's exact stratification bands
(§7.3): a child uncovered is inherently high-impact, so imminence drives the
band — inside 36h is CRITICAL, inside 14 days IMPORTANT, beyond that ADVISORY.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from exhale.forgetting_engine import stratify, ThreatLevel
from exhale.schemas import FactOrigin

# A young child needs an adult physically present across these hours — wide
# enough to catch evening outings (a concert runs past bedtime; a sleeping child
# still needs someone home), capped short of deep night, when both parents are
# home anyway so it never reads as a gap. Configurable per recipient.
DEFAULT_SUPERVISED_START = time(6, 0)
DEFAULT_SUPERVISED_END = time(22, 0)


# --- interval arithmetic (naive local wall-clock; care is inherently local) -------
_Interval = tuple[datetime, datetime]


def _subtract(base: list[_Interval], cuts: list[_Interval]) -> list[_Interval]:
    """Remove every ``cut`` span from the ``base`` spans."""

    result = list(base)
    for cs, ce in cuts:
        nxt: list[_Interval] = []
        for s, e in result:
            if ce <= s or cs >= e:  # disjoint
                nxt.append((s, e))
                continue
            if s < cs:
                nxt.append((s, cs))
            if ce < e:
                nxt.append((ce, e))
        result = nxt
    return [iv for iv in result if iv[0] < iv[1]]


def _union(intervals: list[_Interval]) -> list[_Interval]:
    """Merge overlapping/touching spans into a minimal covering set."""

    merged: list[_Interval] = []
    for s, e in sorted(intervals):
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def _overlaps(a: _Interval, b: _Interval) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _intersect(a: list[_Interval], b: list[_Interval]) -> list[_Interval]:
    """Every overlapping stretch shared by the two interval sets."""

    out: list[_Interval] = []
    for a0, a1 in a:
        for b0, b1 in b:
            lo, hi = max(a0, b0), min(a1, b1)
            if lo < hi:
                out.append((lo, hi))
    return _union(out)


# --- inputs -----------------------------------------------------------------------
@dataclass(frozen=True)
class CareRecipient:
    """The person who must always be supervised."""

    name: str
    supervised_start: time = DEFAULT_SUPERVISED_START
    supervised_end: time = DEFAULT_SUPERVISED_END


@dataclass
class WorkPattern:
    """A recurring block during which a caregiver cannot provide care.

    ``basis`` records whether this pattern is *observed* (read off a work
    calendar) or *inferred* (derived from a stated schedule like "M-F 7:30-4:30")
    — a gap resting on an inferred pattern is flagged as assumption-dependent.
    """

    weekdays: frozenset[int]  # 0=Mon .. 6=Sun
    start: time
    end: time
    days_off: frozenset[date] = frozenset()  # holidays / PTO exceptions
    basis: FactOrigin = FactOrigin.INFERRED

    def block_on(self, day: date) -> _Interval | None:
        if day.weekday() in self.weekdays and day not in self.days_off:
            return (datetime.combine(day, self.start), datetime.combine(day, self.end))
        return None


@dataclass(frozen=True)
class CalendarEvent:
    """A commitment pulled from a (shared) calendar.

    ``attendees`` are the caregiver names who are *out* for its duration — the
    thing that turns "both parents at a concert" into a care gap.
    """

    title: str
    start: datetime
    end: datetime
    attendees: tuple[str, ...] = ()
    source_reference: str | None = None
    origin: FactOrigin = FactOrigin.OBSERVED


@dataclass
class Caregiver:
    """Someone who can supervise the recipient when free."""

    name: str
    role: str = "PARENT"  # PARENT | RELATIVE | SITTER
    work_pattern: WorkPattern | None = None
    events: list[CalendarEvent] = field(default_factory=list)

    def _blocks(self, day: date) -> list[tuple[datetime, datetime, str, FactOrigin]]:
        """Why (and when) this caregiver is unavailable on ``day``."""

        out: list[tuple[datetime, datetime, str, FactOrigin]] = []
        if self.work_pattern is not None:
            block = self.work_pattern.block_on(day)
            if block is not None:
                out.append((block[0], block[1], "working", self.work_pattern.basis))
        for ev in self.events:
            if self.name in ev.attendees and ev.start.date() <= day <= ev.end.date():
                out.append((ev.start, ev.end, f"at {ev.title}", ev.origin))
        return out

    def available_on(self, day: date, span: _Interval) -> list[_Interval]:
        cuts = [(s, e) for s, e, _why, _origin in self._blocks(day)]
        return _subtract([span], cuts)


@dataclass
class SchoolCalendar:
    """In-session days + the no-school days that open care gaps.

    ``no_school_days`` maps each closed weekday date to a human reason so a gap
    can say *why* school isn't covering ("MEA break", "Parent-Teacher
    Conferences"). Weekends are implicitly out of session.
    """

    name: str
    first_day: date
    last_day: date
    school_start: time = time(8, 30)
    school_end: time = time(15, 30)
    no_school_days: dict[date, str] = field(default_factory=dict)
    origin: FactOrigin = FactOrigin.OBSERVED

    def in_session(self, day: date) -> bool:
        return (
            self.first_day <= day <= self.last_day
            and day.weekday() < 5
            and day not in self.no_school_days
        )

    def coverage_on(self, day: date) -> _Interval | None:
        if not self.in_session(day):
            return None
        return (datetime.combine(day, self.school_start), datetime.combine(day, self.school_end))

    def closure_reason(self, day: date) -> str | None:
        """Why school isn't covering ``day`` during term (None if in session)."""

        if self.first_day <= day <= self.last_day and day.weekday() < 5:
            return self.no_school_days.get(day)
        return None


@dataclass
class CareProgram:
    """Optional non-school-day care (e.g. a school's "Aventuras" program)."""

    name: str
    dates: dict[date, tuple[time, time]] = field(default_factory=dict)

    def coverage_on(self, day: date) -> _Interval | None:
        window = self.dates.get(day)
        if window is None:
            return None
        return (datetime.combine(day, window[0]), datetime.combine(day, window[1]))


# --- output -----------------------------------------------------------------------
@dataclass(frozen=True)
class CareGap:
    """An unassigned stretch of supervision for the recipient."""

    recipient_name: str
    start: datetime
    end: datetime
    threat_level: ThreatLevel
    hours_until: float
    duration_hours: float
    reason: str
    basis: tuple[str, ...]
    depends_on_inference: bool
    suggested_action: str

    def to_dict(self) -> dict:
        return {
            "recipient": self.recipient_name,
            "date": self.start.date().isoformat(),
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "duration_hours": round(self.duration_hours, 2),
            "threat_level": self.threat_level.value,
            "indicator": self.threat_level.indicator,
            "reason": self.reason,
            "basis": list(self.basis),
            "depends_on_inference": self.depends_on_inference,
            "suggested_action": self.suggested_action,
        }


@dataclass(frozen=True)
class WorkWindow:
    """A stretch a caregiver could use for their own work — an INTENT match.

    The forward, want-driven side of the coverage math: the child is covered by
    someone/something else, so this caregiver is free to work.
    """

    caregiver_name: str
    start: datetime
    end: datetime
    duration_hours: float
    child_covered_by: tuple[str, ...]  # what frees the caregiver (school, other parent…)

    def to_dict(self) -> dict:
        return {
            "caregiver": self.caregiver_name,
            "date": self.start.date().isoformat(),
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "duration_hours": round(self.duration_hours, 2),
            "child_covered_by": list(self.child_covered_by),
        }


class CoverageEngine:
    """Computes care gaps for a recipient across a date range."""

    def __init__(
        self,
        recipient: CareRecipient,
        caregivers: list[Caregiver],
        *,
        school: SchoolCalendar | None = None,
        care_programs: tuple[CareProgram, ...] = (),
        now: datetime | None = None,
    ) -> None:
        self.recipient = recipient
        self.caregivers = caregivers
        self.school = school
        self.care_programs = care_programs
        self.now = now or datetime.now()

    def scan_day(self, day: date) -> list[CareGap]:
        span_start = datetime.combine(day, self.recipient.supervised_start)
        span_end = datetime.combine(day, self.recipient.supervised_end)
        span: _Interval = (span_start, span_end)

        covered: list[_Interval] = []
        school_cov = self.school.coverage_on(day) if self.school else None
        if school_cov is not None:
            covered.append(school_cov)
        for program in self.care_programs:
            pc = program.coverage_on(day)
            if pc is not None:
                covered.append(pc)
        for cg in self.caregivers:
            covered.extend(cg.available_on(day, span))

        gaps_iv = _subtract([span], _union(covered))

        gaps: list[CareGap] = []
        for gs, ge in gaps_iv:
            if ge <= self.now:  # don't surface gaps already in the past
                continue
            gaps.append(self._build_gap(day, gs, ge))
        return gaps

    def scan_range(self, start_day: date, end_day: date) -> list[CareGap]:
        gaps: list[CareGap] = []
        day = start_day
        while day <= end_day:
            gaps.extend(self.scan_day(day))
            day += timedelta(days=1)
        gaps.sort(key=lambda g: g.start)
        return gaps

    # -- open work windows (the intent side of the same math) ----------------------
    def _caregiver(self, name: str) -> Caregiver:
        for cg in self.caregivers:
            if cg.name == name:
                return cg
        raise KeyError(f"No caregiver named {name!r}")

    def _coverers_on(self, day: date, span: _Interval, exclude: str) -> list[tuple[_Interval, str]]:
        """Who/what covers the recipient on ``day``, other than ``exclude``."""

        out: list[tuple[_Interval, str]] = []
        if self.school is not None:
            cov = self.school.coverage_on(day)
            if cov is not None:
                out.append((cov, f"{self.recipient.name} at {self.school.name}"))
        for program in self.care_programs:
            pc = program.coverage_on(day)
            if pc is not None:
                out.append((pc, program.name))
        for cg in self.caregivers:
            if cg.name == exclude:
                continue
            for iv in cg.available_on(day, span):
                out.append((iv, f"{cg.name} has {self.recipient.name}"))
        return out

    def open_windows_on(self, day: date, caregiver_name: str) -> list["WorkWindow"]:
        """When ``caregiver_name`` is free *and* the child is covered by others.

        The mirror of a care gap: a stretch this caregiver could use for work,
        because they have no commitment and someone/something else has the child.
        The drop-off/pickup pinch (child home, no one else covering) is correctly
        excluded — that time is childcare, not workable.
        """

        target = self._caregiver(caregiver_name)
        span_start = datetime.combine(day, self.recipient.supervised_start)
        span_end = datetime.combine(day, self.recipient.supervised_end)
        span: _Interval = (span_start, span_end)

        free = target.available_on(day, span)
        coverers = self._coverers_on(day, span, exclude=caregiver_name)
        workable = _intersect(free, _union([iv for iv, _ in coverers]))

        windows: list[WorkWindow] = []
        for ws, we in workable:
            if we <= self.now:  # skip windows already in the past
                continue
            labels = tuple(sorted({
                label for iv, label in coverers if _overlaps((ws, we), iv)
            }))
            windows.append(WorkWindow(
                caregiver_name=caregiver_name,
                start=ws, end=we,
                duration_hours=(we - ws).total_seconds() / 3600.0,
                child_covered_by=labels,
            ))
        return windows

    def work_windows(
        self, caregiver_name: str, start_day: date, end_day: date, *, min_hours: float = 1.0
    ) -> list["WorkWindow"]:
        """Every workable window ≥ ``min_hours`` across the range, by start time."""

        out: list[WorkWindow] = []
        day = start_day
        while day <= end_day:
            out.extend(
                w for w in self.open_windows_on(day, caregiver_name)
                if w.duration_hours >= min_hours
            )
            day += timedelta(days=1)
        out.sort(key=lambda w: w.start)
        return out

    # -- gap explanation -----------------------------------------------------------
    def _build_gap(self, day: date, gs: datetime, ge: datetime) -> CareGap:
        window = (gs, ge)
        factors: list[str] = []
        basis: list[str] = []
        inferred = False

        # Why isn't school covering this stretch?
        if self.school is not None:
            reason = self.school.closure_reason(day)
            school_window = (
                datetime.combine(day, self.school.school_start),
                datetime.combine(day, self.school.school_end),
            )
            if reason and _overlaps(window, school_window):
                factors.append(f"school closed ({reason})")
                basis.append(f"school closure OBSERVED — {self.school.name} calendar")

        # Which caregivers are blocked across this stretch, and why?
        for cg in self.caregivers:
            for bs, be, why, origin in cg._blocks(day):
                if _overlaps(window, (bs, be)):
                    factors.append(f"{cg.name} {why}")
                    basis.append(f"{cg.name} {why} — {origin.value}")
                    if origin is FactOrigin.INFERRED:
                        inferred = True

        reason = "; ".join(factors) if factors else "no caregiver assigned"

        # Prefer asking a known relative before hiring out.
        relatives = [c.name for c in self.caregivers if c.role == "RELATIVE"]
        if relatives:
            action = f"Ask {relatives[0]}, or book a sitter"
        else:
            action = "Book a sitter"

        hours_until = (gs - self.now).total_seconds() / 3600.0
        # A child uncovered is inherently high-impact; imminence sets the band.
        threat = stratify(hours_until, impact_of_forgetting=1.0)
        return CareGap(
            recipient_name=self.recipient.name,
            start=gs,
            end=ge,
            threat_level=threat,
            hours_until=round(hours_until, 1),
            duration_hours=(ge - gs).total_seconds() / 3600.0,
            reason=reason,
            basis=tuple(basis),
            depends_on_inference=inferred,
            suggested_action=action,
        )


def build_care_watch(
    engine: CoverageEngine, start_day: date, end_day: date
) -> dict:
    """Assemble a briefing-ready Care Watch payload from computed gaps."""

    gaps = engine.scan_range(start_day, end_day)
    by_band = {level: 0 for level in ThreatLevel}
    for g in gaps:
        by_band[g.threat_level] += 1
    return {
        "view": "care_watch",
        "recipient": engine.recipient.name,
        "range": {"from": start_day.isoformat(), "to": end_day.isoformat()},
        "summary": {
            "total_gaps": len(gaps),
            "critical": by_band[ThreatLevel.CRITICAL],
            "important": by_band[ThreatLevel.IMPORTANT],
            "advisory": by_band[ThreatLevel.ADVISORY],
            "assumption_dependent": sum(1 for g in gaps if g.depends_on_inference),
        },
        "gaps": [g.to_dict() for g in gaps],
    }


def suggest_work_windows(
    engine: CoverageEngine,
    caregiver_name: str,
    start_day: date,
    end_day: date,
    *,
    count: int = 3,
    min_hours: float = 2.0,
) -> list[WorkWindow]:
    """The best ``count`` workable windows: longest first, then back in time order.

    Answers "I want to work N times this week — when's best?" by picking the
    longest qualifying blocks (the most useful stretches) and returning them in
    chronological order for the schedule.
    """

    windows = engine.work_windows(caregiver_name, start_day, end_day, min_hours=min_hours)
    best = sorted(windows, key=lambda w: w.duration_hours, reverse=True)[:count]
    return sorted(best, key=lambda w: w.start)


def build_work_plan(
    engine: CoverageEngine,
    caregiver_name: str,
    start_day: date,
    end_day: date,
    *,
    count: int = 3,
    min_hours: float = 2.0,
) -> dict:
    """Briefing-ready payload: the caregiver's suggested best work windows."""

    windows = suggest_work_windows(
        engine, caregiver_name, start_day, end_day, count=count, min_hours=min_hours
    )
    total = round(sum(w.duration_hours for w in windows), 2)
    return {
        "view": "work_windows",
        "caregiver": caregiver_name,
        "range": {"from": start_day.isoformat(), "to": end_day.isoformat()},
        "criteria": {"count": count, "min_hours": min_hours},
        "summary": {"suggested": len(windows), "total_hours": total},
        "windows": [w.to_dict() for w in windows],
    }
