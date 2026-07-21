"""Layer 2 — Extraction engine (Blueprint §3).

Turns a normalized :class:`~exhale.connectors.base.RawMessage` into a
schema-validated :class:`~exhale.schemas.ExtractionPayload`, deriving:

* the event title, event date, and any hard deadline,
* whether manual action is required,
* which family member it concerns, and
* a calibrated ``confidence_score`` that drives the routing matrix (§3.3).

This reference implementation is fully deterministic (regex + ``dateutil`` +
keyword heuristics), so extraction is testable and reproducible. It is designed
as a drop-in interface: an LLM-backed extractor can implement the same
``extract_payload`` signature without touching the rest of the pipeline. Entities
that cannot be derived with baseline proof fail cleanly to ``None`` (§3.2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from dateutil import parser as dateparser

from exhale.connectors.base import RawMessage
from exhale.connectors.preprocess import clean
from exhale.credibility import TIER_SCORE_ADJUSTMENT, classify_artifact
from exhale.schemas import ExtractionPayload, FactOrigin

# --- Signal vocabularies ------------------------------------------------------
_DEADLINE_CUES = (
    "due", "deadline", "return by", "rsvp", "no later than", "payment due",
    "sign by", "submit by", "respond by", "register by", "before",
)
_ACTION_VERBS = (
    "sign", "submit", "return", "pay", "rsvp", "register", "bring", "complete",
    "upload", "confirm", "renew", "schedule", "fill out", "send in", "permission",
)
# Cues that mark the *authoritative* event date when a message carries several
# (e.g. a reschedule notice: an old canceled date and a new confirmed one). A
# date preceded by one of these wins over other event dates. (Data-driven: real
# appointment-reschedule emails list the canceled date first.)
_EVENT_CONFIRM_CUES = (
    "confirmed for", "rescheduled", "new appointment", "moved to", "now on",
    "new time", "new date", "reschedule to",
)
# Sender domains that strongly imply a real household obligation (§6).
DEFAULT_TRUSTED_DOMAINS: dict[str, float] = {
    "powerschool.com": 1.0,
    "teamsnap.com": 1.0,
    "classdojo.com": 0.9,
    "schoology.com": 0.9,
    "remind.com": 0.8,
    "konstella.com": 0.8,
    "signupgenius.com": 0.8,
}

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# Date-like substrings, most specific first.
_MONTHS = ("january|february|march|april|may|june|july|august|september|october|"
           "november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec")
_DATE_PATTERNS = [
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),                                 # ISO
    re.compile(rf"\b(?:{_MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+\d{{4}})?\b", re.I),
    re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b"),                      # 8/25 or 8/25/2026
    re.compile(r"\b(?:tomorrow|today|tonight)\b", re.I),
    re.compile(r"\b(?:next|this)\s+week(?:end)?\b", re.I),                # next week / this weekend
    re.compile(r"\bnext\s+month\b", re.I),
    re.compile(r"\b(?:mon|tues|wednes|thurs|fri|satur|sun)day\b", re.I),
]
_YEAR_RE = re.compile(r"\b\d{4}\b")

# A time *range* like "1pm-4pm", "1 p.m. to 4 p.m.", "12:30-1:00 pm". The end
# must carry an am/pm marker so date fragments ("2026-07-19", "Jul 20-23")
# can never masquerade as a time window. Extraction is range-only on purpose:
# a lone "4:15 p.m." is as likely a pickup cutoff as a start time, and the
# credibility rule is that an unknown window stays UNKNOWN rather than being
# filled with a plausible guess.
_TIME_RANGE_RE = re.compile(
    r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?\s*(?:-|–|—|to|until)\s*"
    r"(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)\b",
    re.I,
)


def _to_24h(hour: int, minute: int, meridiem: str | None) -> time | None:
    mer = meridiem.replace(".", "").lower() if meridiem else None
    if mer and not 1 <= hour <= 12:
        return None
    if mer == "pm" and hour != 12:
        hour += 12
    elif mer == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)


def _find_time_window(text: str) -> tuple[time | None, time | None]:
    """First observed start/end time range in the text, or ``(None, None)``."""

    for m in _TIME_RANGE_RE.finditer(text):
        sh, sm, smer, eh, em, emer = m.groups()
        end = _to_24h(int(eh), int(em or 0), emer)
        if end is None:
            continue
        if smer:
            start = _to_24h(int(sh), int(sm or 0), smer)
        else:
            # "1-4pm": the start inherits the end's half of the day unless
            # that would run the window backwards ("11-1pm" → 11am).
            start = _to_24h(int(sh), int(sm or 0), emer)
            if start is not None and start > end:
                start = _to_24h(int(sh), int(sm or 0), "am" if "p" in emer.lower() else "pm")
        if start is None or start > end:
            continue
        return start, end
    return None, None


@dataclass
class ExtractionContext:
    """Household-specific priors that sharpen extraction."""

    known_children: list[str] = field(default_factory=list)
    trusted_domains: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_TRUSTED_DOMAINS))
    reference_date: date = field(default_factory=date.today)


@dataclass
class _DateHit:
    value: date
    is_deadline: bool
    explicit: bool  # a real calendar date (vs a fuzzy weekday/relative token)
    confirmed: bool = False  # preceded by an authoritative-date cue (§ reschedules)


def _resolve_token(token: str, reference: date) -> tuple[date, bool] | None:
    """Parse a single date token → (date, explicit?) or None."""

    low = re.sub(r"\s+", " ", token.strip().lower())
    ref_dt = datetime(reference.year, reference.month, reference.day)

    if low in ("today", "tonight", "this week"):
        return reference, False
    if low == "tomorrow":
        return reference + timedelta(days=1), False
    if low == "next week":
        # The Monday of the following week.
        return reference + timedelta(days=7 - reference.weekday()), False
    if low in ("this weekend", "next weekend"):
        saturday = reference + timedelta(days=(5 - reference.weekday()) % 7)
        return saturday + (timedelta(days=7) if low.startswith("next") else timedelta()), False
    if low == "next month":
        year, month = (reference.year + 1, 1) if reference.month == 12 else (reference.year, reference.month + 1)
        return date(year, month, 1), False
    if low in _WEEKDAYS:
        target = _WEEKDAYS.index(low)
        delta = (target - reference.weekday()) % 7
        delta = delta or 7  # next occurrence, never "today"
        return reference + timedelta(days=delta), False

    try:
        parsed = dateparser.parse(token, default=ref_dt, dayfirst=False)
    except (ValueError, OverflowError):
        return None
    if parsed is None:
        return None

    result = parsed.date()
    explicit = bool(_YEAR_RE.search(token)) or bool(re.search(r"\d", token))
    # No explicit year and already in the past → assume the coming year (§ recurring cadences).
    if not _YEAR_RE.search(token) and result < reference:
        try:
            result = result.replace(year=result.year + 1)
        except ValueError:  # Feb 29 guard
            result = result + timedelta(days=365)
    return result, explicit


def _find_dates(text: str, reference: date) -> list[_DateHit]:
    hits: list[_DateHit] = []
    seen: set[tuple[date, int]] = set()
    for pattern in _DATE_PATTERNS:
        for m in pattern.finditer(text):
            resolved = _resolve_token(m.group(0), reference)
            if resolved is None:
                continue
            value, explicit = resolved
            window = text[max(0, m.start() - 40): m.start()].lower()
            confirmed = any(cue in window for cue in _EVENT_CONFIRM_CUES)
            # A confirmed/authoritative date is an event, never a deadline.
            is_deadline = (not confirmed) and any(cue in window for cue in _DEADLINE_CUES)
            key = (value, int(is_deadline))
            if key in seen:
                continue
            seen.add(key)
            hits.append(_DateHit(value=value, is_deadline=is_deadline,
                                 explicit=explicit, confirmed=confirmed))
    return hits


def _match_child(text: str, children: list[str]) -> str | None:
    for name in children:
        if re.search(rf"\b{re.escape(name)}\b", text, re.I):
            return name
    return None


def _has_action(text: str) -> bool:
    low = text.lower()
    return any(re.search(rf"\b{re.escape(v)}", low) for v in _ACTION_VERBS)


def extract_payload(raw: RawMessage, ctx: ExtractionContext | None = None) -> ExtractionPayload | None:
    """Extract a validated payload from a raw message, or ``None`` if untrackable.

    Returns ``None`` when no event date can be derived — there is nothing to
    track — leaving it to the caller/routing to handle low-signal input (§3.3).
    """

    ctx = ctx or ExtractionContext()
    body = clean(raw.body)
    attachment_text = " ".join(a.text or a.filename for a in raw.attachments)
    corpus = "\n".join(filter(None, [raw.subject, body, attachment_text]))
    if not corpus.strip():
        return None

    # Resolve dates on the *message's* timeline: "tomorrow" in an email sent
    # last week means the day after it was sent, not the day after the scan.
    reference = raw.received_at.date() if raw.received_at else ctx.reference_date
    hits = _find_dates(corpus, reference)
    if not hits:
        return None

    deadlines = sorted((h for h in hits if h.is_deadline), key=lambda h: h.value)
    # Prefer a confirmed/authoritative date, then an explicit calendar date, then earliest.
    events = sorted(
        (h for h in hits if not h.is_deadline),
        key=lambda h: (not h.confirmed, not h.explicit, h.value),
    )

    if events:
        event_hit = events[0]
    else:  # only deadline dates found → the deadline *is* the event date
        event_hit = deadlines[0]
    deadline_date = deadlines[0].value if deadlines else None

    person = _match_child(corpus, ctx.known_children)
    action_required = _has_action(corpus) or deadline_date is not None
    domain_weight = ctx.trusted_domains.get((raw.sender_domain or "").lower(), 0.0)
    tier = classify_artifact(raw)
    start_time, end_time = _find_time_window(corpus)

    # --- Confidence calibration (feeds §3.3 routing) --------------------------
    score = 0.35
    score += 0.22 if event_hit.explicit else 0.05
    score += 0.15 if deadline_date is not None else 0.0
    score += 0.10 if _has_action(corpus) else 0.0
    score += 0.08 if person else 0.0
    score += 0.12 * domain_weight
    score += 0.05 if raw.subject.strip() else 0.0
    score += TIER_SCORE_ADJUSTMENT[tier]
    score = round(min(max(score, 0.0), 1.0), 4)

    title = (raw.subject or "").strip() or _first_sentence(body) or "Untitled item"

    return ExtractionPayload(
        extracted_event=title,
        target_person_name=person,
        event_date=event_hit.value,
        deadline_date=deadline_date,
        action_required=action_required,
        confidence_score=score,
        source_document_name=raw.display_name,
        source_reference=raw.source_id,
        artifact_tier=tier,
        # A fuzzy token ("next week", a bare weekday) is the pipeline's
        # arithmetic, not the artifact's text — that is an inference.
        event_date_origin=FactOrigin.OBSERVED if event_hit.explicit else FactOrigin.INFERRED,
        event_start_time=start_time,
        event_end_time=end_time,
    )


def _first_sentence(text: str) -> str | None:
    text = text.strip()
    if not text:
        return None
    return re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0][:120]
