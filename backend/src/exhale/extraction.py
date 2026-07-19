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
from datetime import date, datetime, timedelta

from dateutil import parser as dateparser

from exhale.connectors.base import RawMessage
from exhale.connectors.preprocess import clean
from exhale.schemas import ExtractionPayload

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
    re.compile(r"\b(?:mon|tues|wednes|thurs|fri|satur|sun)day\b", re.I),
]
_YEAR_RE = re.compile(r"\b\d{4}\b")


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

    low = token.strip().lower()
    ref_dt = datetime(reference.year, reference.month, reference.day)

    if low in ("today", "tonight"):
        return reference, False
    if low == "tomorrow":
        return reference + timedelta(days=1), False
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

    hits = _find_dates(corpus, ctx.reference_date)
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

    # --- Confidence calibration (feeds §3.3 routing) --------------------------
    score = 0.35
    score += 0.22 if event_hit.explicit else 0.05
    score += 0.15 if deadline_date is not None else 0.0
    score += 0.10 if _has_action(corpus) else 0.0
    score += 0.08 if person else 0.0
    score += 0.12 * domain_weight
    score += 0.05 if raw.subject.strip() else 0.0
    score = round(min(score, 1.0), 4)

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
    )


def _first_sentence(text: str) -> str | None:
    text = text.strip()
    if not text:
        return None
    return re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0][:120]
