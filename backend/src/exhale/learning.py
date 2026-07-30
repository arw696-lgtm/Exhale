"""The Learning Scoreboard — is Exhale learning how this family works?

Every other surface measures the household (what's due, who's covered, whose
turn it is). This one measures *Exhale itself*: the honest instrument for the
one claim the whole product rests on — "just connect your stuff and I'll learn
how your family works." Engagement is the wrong scoreboard here; if Exhale is
working, the family opens it *less* over time, not more. So the number that
matters is not clicks — it's whether the model of the family is getting better.

Four questions, answered only from signals that already exist:

* **Time to first pattern** — how long, and how many emails/events, until the
  first recurring rhythm became *knowable* (the memory engine's own threshold).
* **Patterns held** — the rules standing now, plus the ones still emerging
  (short of the evidence bar), so "still learning" reads as motion, not a blank.
* **Coverage foresight** — how far ahead the soonest care gap was seen, and how
  many caught gaps the family actually acted on.
* **Surprises confirmed** — observations Exhale surfaced that a member marked as
  *new to them*. The magic metric; the only one it must never fabricate.

Honesty rules (inherited from :mod:`exhale.handled`):

* Nothing is asserted from a single sample — the memory engine's ``min_samples``
  bar governs every "pattern," and this module never lowers it.
* A cold start reads as a cold start. No patterns yet is a real, valid state
  ("Exhale is still listening"), never padded with a manufactured win.
* **Surprises move only on a real acknowledgement.** The count is 0 until a
  member confirms one; the type existing is not the same as pretending it fired.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from exhale.memory import _stem, learn_rules

# A member can confirm a surfaced observation as "new to us"; the log is capped
# so the profile blob stays bounded, and the recap only reads the recent slice.
MAX_ACK_ENTRIES = 200
RECENT_DAYS = 7

ACK_TYPES = ("learned_rule", "coverage_gap")


# -- surprises: the one metric that must never be fabricated ----------------------
def record_learning_ack(
    store,
    family_id: str,
    *,
    observation_id: str,
    observation_type: str,
    note: str = "",
    acknowledged_at: datetime | None = None,
) -> dict | None:
    """Log that a member found a surfaced observation *new to them* (idempotent).

    Returns the entry written, or ``None`` when this observation was already
    acknowledged — tapping twice never inflates the surprise count.
    """

    if observation_type not in ACK_TYPES:
        raise ValueError(f"unknown observation_type {observation_type!r}")
    with store.family_lock(family_id):  # RMW must not race a concurrent writer
        entries = list(store.profile(family_id).get("learning_acks") or [])
        if any(e["observation_id"] == observation_id for e in entries):
            return None
        entry = {
            "observation_id": observation_id,
            "observation_type": observation_type,
            "note": note,
            "acknowledged_at": (acknowledged_at or _now()).isoformat(),
        }
        entries.append(entry)
        store.set_profile(family_id, learning_acks=entries[-MAX_ACK_ENTRIES:])
        return entry


# -- the scoreboard ---------------------------------------------------------------
def build_learning_scoreboard(
    entries,
    profile: dict,
    care_watch: dict | None = None,
    *,
    min_samples: int = 3,
    now: datetime | None = None,
) -> dict:
    """Assemble the learning scoreboard from the family's own signals.

    ``entries`` are :class:`~exhale.store.LedgerEntry` items (the extractions
    mined from connected email/calendar). Everything here is derived — there is
    no separate learning state to drift — so the board can never claim a pattern
    the memory engine wouldn't also show.
    """

    now = now or _now()
    ordered = sorted(entries, key=lambda e: e.created_at)

    return {
        "view": "learning_scoreboard",
        "data": _data_seen(ordered, now=now),
        "time_to_first_pattern": _time_to_first_pattern(ordered, min_samples),
        "patterns_held": _patterns_held(ordered, min_samples),
        "coverage_foresight": _coverage_foresight(care_watch, profile, now=now),
        "surprises": _surprises(profile, now=now),
        "trust": _trust(ordered, profile),
    }


def _data_seen(ordered, *, now: datetime) -> dict:
    """The fuel: how much has actually flowed in, and over how long."""

    if not ordered:
        return {"signals_seen": 0, "first_seen": None, "last_seen": None, "days_observed": 0}
    first, last = ordered[0].created_at, ordered[-1].created_at
    return {
        "signals_seen": len(ordered),
        "first_seen": first.isoformat(),
        "last_seen": last.isoformat(),
        # Age of the record, not first→last, so a single-day family still reads
        # as "listening since today," which is what a member would expect.
        "days_observed": max((now - first).days, 0),
    }


def _time_to_first_pattern(ordered, min_samples: int) -> dict:
    """Replay ingestion until the memory engine would first hold a rule.

    Reuses :func:`~exhale.memory.learn_rules` on growing prefixes, so the moment
    reported is exactly the moment a pattern became displayable — never earlier.
    """

    for i, entry in enumerate(ordered, start=1):
        rules = learn_rules(ordered[:i], min_samples=min_samples)
        if rules:
            first_at = ordered[0].created_at
            return {
                "achieved": True,
                "learned_at": entry.created_at.isoformat(),
                "days": max((entry.created_at - first_at).days, 0),
                "signals_needed": i,
                "first_pattern": rules[0].to_dict(),
            }
    return {"achieved": False}


def _patterns_held(ordered, min_samples: int) -> dict:
    """Rules standing now, plus ones still gathering evidence (honest 'almost')."""

    rules = learn_rules(ordered, min_samples=min_samples)

    # Emerging: a stem with real repetition but short of the evidence bar. This
    # is what makes "still learning" legible — motion the member can watch, not a
    # claim we haven't earned.
    groups: dict[str, set] = defaultdict(set)
    for e in ordered:
        if e.decision.status.value == "REJECTED":
            continue
        stem = _stem(e.payload.extracted_event)
        if stem:
            groups[stem].add(e.payload.event_date)

    held_subjects = {r.subject for r in rules}
    emerging = [
        {"subject": stem, "samples": len(dates), "needs": min_samples - len(dates)}
        for stem, dates in sorted(groups.items())
        if stem not in held_subjects and 2 <= len(dates) < min_samples
    ]

    return {
        "count": len(rules),
        "rules": [r.to_dict() for r in rules],
        "emerging": emerging,
    }


def _coverage_foresight(care_watch: dict | None, profile: dict, *, now: datetime) -> dict | None:
    """How far ahead care gaps are seen, and how many caught gaps were acted on.

    ``None`` when no coverage model is configured — nothing to measure yet, and
    a zero would read as a false "no foresight."
    """

    if not care_watch:
        return None

    gaps = care_watch.get("gaps") or []
    leads = [g["hours_until"] for g in gaps if isinstance(g.get("hours_until"), (int, float))]
    earliest_lead_hours = min(leads) if leads else None

    # Caught gaps the family then resolved this week — the foresight that
    # converted into action, read straight from the already-logged handled slice.
    cutoff = _as_utc(now) - timedelta(days=RECENT_DAYS)
    acted_on = 0
    for e in profile.get("resolved_log") or []:
        if e.get("resolved_type") != "dependency_gap":
            continue
        try:
            when = datetime.fromisoformat(e["resolved_at"])
        except (KeyError, ValueError):
            continue
        if _as_utc(when) >= cutoff:
            acted_on += 1

    return {
        "gaps_ahead": len(gaps),
        "earliest_lead_hours": round(earliest_lead_hours, 1) if earliest_lead_hours is not None else None,
        "acted_on_this_week": acted_on,
    }


def _trust(ordered, profile: dict) -> dict:
    """The Trust Ledger — is Exhale *right*, not just learning?

    The Milo lesson made a number: one confidently wrong assertion costs more
    trust than ten right ones earn. Two sides, measured separately because
    they answer different questions:

    * **Confident side** — of everything Exhale auto-committed without asking
      (HIGH band, not user-originated), what fraction did a human later have to
      *correct with actual changes*? A confirmation-without-changes is
      agreement, not a failure. ``confident_accuracy`` is the reliability score
      for the founding-family run; ``None`` until there's something to score.
    * **Ask side** — reuses :func:`exhale.autonomy.trust_record`: of the items
      held for review, how often was surfacing them the right call?
    """

    from exhale.autonomy import trust_record
    from exhale.schemas import FactOrigin

    by_id = {e.extraction_id: e for e in ordered}
    asserted = corrected = 0
    for e in ordered:
        if e.decision.status.value != "COMMITTED":
            continue
        if e.payload.event_date_origin is FactOrigin.USER_CONFIRMED:
            continue  # user-originated ground truth isn't Exhale asserting
        asserted += 1
        successor_id = e.superseded_by
        successor = by_id.get(successor_id) if successor_id else None
        if successor is None:
            continue
        changed = successor.payload.model_dump(
            exclude={"corrects", "confidence_score", "event_date_origin"}
        ) != e.payload.model_dump(
            exclude={"corrects", "confidence_score", "event_date_origin"}
        )
        if changed:
            corrected += 1

    dismissed = set(profile.get("dismissed_extractions") or [])
    return {
        "asserted": asserted,
        "corrected": corrected,
        "confident_accuracy": (
            round(1 - corrected / asserted, 3) if asserted else None
        ),
        "review": trust_record(ordered, dismissed),
    }


def _surprises(profile: dict, *, now: datetime) -> dict:
    """Confirmed 'I didn't know that' observations — 0 until one is real."""

    cutoff = _as_utc(now) - timedelta(days=RECENT_DAYS)
    acks = profile.get("learning_acks") or []
    recent = 0
    latest = None
    for e in acks:
        try:
            when = datetime.fromisoformat(e["acknowledged_at"])
        except (KeyError, ValueError):
            continue
        if _as_utc(when) >= cutoff:
            recent += 1
        if latest is None or e["acknowledged_at"] > latest.get("acknowledged_at", ""):
            latest = e
    return {
        "confirmed": len(acks),
        "this_week": recent,
        "latest": latest,
    }


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Timestamp convention: the ledger stamps aware-UTC; household-domain profile
# entries (resolved log, tasks, waits) stamp naive LOCAL time — the right frame
# for family semantics like "this week". When the two meet in a comparison,
# normalize through here: naive means local, and everything compares in UTC.
_LOCAL_TZ = datetime.now().astimezone().tzinfo


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_LOCAL_TZ)
    return dt.astimezone(timezone.utc)
