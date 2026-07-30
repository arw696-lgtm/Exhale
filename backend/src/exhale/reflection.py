"""The Weekly Reflection — Exhale's exhale.

Every other surface points forward and asks something of you: what's due, who's
uncovered, whose turn it is. That's the inhale — bracing for the week. This is
the other half of the breath, and the half the product is named for: on Sunday,
when people are already thinking about the week, Exhale looks *back* and
*sideways* instead of ahead.

Three movements, each built only from things Exhale can actually see (no
manufactured warmth):

* **What you carried** — the real work that got done this week: gaps covered,
  loops closed, time you protected and honored. Mental load is heavy partly
  because it's invisible; this is where the invisible labor gets *seen*.
* **Hard-won** — the subset that had been slipping and finally happened. The
  quiet pride of doing the thing you kept meaning to do.
* **What's still waiting** — the long-running things that didn't get their time,
  each with a way to *make a call*: put time on it this week (the intention
  engine), or nudge the person who owes you. Closing a loop — even by choosing
  to let it go — is its own release.

And an honest **tenor** over the top: a full week gets a lift; a hard week gets
named as hard, gently. This surface must never wear a party hat on a week where
things slipped — the same quiet-week discipline the Handled recap already holds.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from exhale.waiting import CRITICAL_AFTER_DAYS, NUDGE_AFTER_DAYS

REFLECT_DAYS = 7

# An intention that has surfaced this many times and still isn't matched is a
# genuine long-running want, not a passing whim — worth putting time on.
LINGERING_SURFACE_COUNT = 3
# A honored want that had surfaced before it happened was hard-won, not routine.
HARD_WON_SURFACE_COUNT = 2


def build_weekly_reflection(
    profile: dict, care_watch: dict | None = None, *, now: datetime | None = None
) -> dict:
    """Assemble the Sunday reflection from the family's own resolved signals."""

    now = now or datetime.now()
    cutoff = now - timedelta(days=REFLECT_DAYS)

    carried, hard_won = _carried(profile, cutoff)
    lingering = _lingering(profile, now=now)

    return {
        "view": "weekly_reflection",
        "range": {
            "from": (now - timedelta(days=REFLECT_DAYS)).date().isoformat(),
            "to": now.date().isoformat(),
        },
        "tenor": _tenor(len(carried), len(lingering), care_watch),
        "carried": {"count": len(carried), "items": carried, "hard_won": hard_won},
        "lingering": {"count": len(lingering), "items": lingering},
    }


def _carried(profile: dict, cutoff: datetime) -> tuple[list[dict], list[dict]]:
    """The week's real wins: resolved items + honored intentions."""

    carried: list[dict] = []

    # Resolved obligations and closed loops (the Handled log, read as *ours*).
    for e in profile.get("resolved_log") or []:
        when = _parse(e.get("resolved_at"))
        if when is None or when < cutoff:
            continue
        carried.append({
            "kind": e.get("resolved_type", "resolved"),
            "text": e.get("brief_description", ""),
            "when": e["resolved_at"],
        })

    # Time you set aside for something that matters, and actually took.
    hard_won: list[dict] = []
    for it in profile.get("intentions") or []:
        matched = _parse(it.get("matched_at"))
        if matched is None or matched < cutoff:
            continue
        outcome = it.get("follow_up_outcome")
        if outcome == "didnt_happen":
            continue  # honesty: a window you set but missed isn't a win
        carried.append({
            "kind": "intention",
            "text": it["description"],
            "context": it.get("context"),
            "confirmed": outcome == "happened",
            "when": it["matched_at"],
        })
        # Hard-won: it had been surfacing before you finally made the time.
        if (it.get("surfaced_count") or 0) >= HARD_WON_SURFACE_COUNT:
            hard_won.append({"text": it["description"], "context": it.get("context")})

    carried.sort(key=lambda i: i["when"], reverse=True)
    return carried, hard_won


def _lingering(profile: dict, *, now: datetime) -> list[dict]:
    """Long-running things that didn't get their time — each with a next move."""

    items: list[dict] = []
    today = now.date()

    # Waits gone quiet: the ball's in someone else's court, and it's been a while.
    for w in profile.get("waiting_on") or []:
        if w.get("resolved"):
            continue
        since = _parse_date(w.get("since"))
        if since is None:
            continue
        days = max((today - since).days, 0)
        if days < NUDGE_AFTER_DAYS:
            continue
        items.append({
            "kind": "waiting",
            "id": w["id"],
            "text": f"{w['who']} — {w['about']}",
            "days_waiting": days,
            "dying": days >= CRITICAL_AFTER_DAYS,
            "action": "nudge",
            "suggestion": f"Nudge {w['who']}",
        })

    # Personal wants that keep coming up and never get the time — offer to
    # actually put a block on the week (the exact loop: "schedule some time").
    for it in profile.get("intentions") or []:
        if it.get("status") not in ("open", "stale"):
            continue
        if (it.get("surfaced_count") or 0) < LINGERING_SURFACE_COUNT:
            continue
        items.append({
            "kind": "intention",
            "id": it["intention_id"],
            "text": it["description"],
            "context": it.get("context"),
            "surfaced_count": it.get("surfaced_count", 0),
            "action": "schedule",
            "suggestion": "Make time this week",
        })

    # Dying threads first, then longest-standing, then schedulable wants.
    items.sort(key=lambda i: (i.get("action") != "nudge", -i.get("days_waiting", 0)))
    return items


def _tenor(carried: int, lingering: int, care_watch: dict | None) -> dict:
    """An honest read of the week — a lift when earned, hard named gently."""

    open_urgent = 0
    if care_watch:
        summary = care_watch.get("summary") or {}
        open_urgent = (summary.get("critical") or 0) + (summary.get("important") or 0)
    pressure = lingering + open_urgent

    if carried == 0 and pressure == 0:
        key, headline, subhead = (
            "quiet",
            "A genuinely quiet week.",
            "Nothing urgent slipped, and nothing needed rescuing. That counts.",
        )
    elif carried == 0 and pressure > 0:
        key, headline, subhead = (
            "hard",
            "Last week was a hard one.",
            "A few things didn't get the time they needed — that's not a failure, "
            "it's a week. Here's where to put your energy next.",
        )
    elif pressure > carried:
        key, headline, subhead = (
            "mixed",
            "You got real things done — and a few slipped.",
            "Worth seeing both: what you carried, and what's still waiting.",
        )
    elif carried >= 3:
        key, headline, subhead = (
            "full",
            "You did a lot this week.",
            "Take the lift — this is the labor that usually goes unseen.",
        )
    else:
        key, headline, subhead = (
            "steady",
            "A steady week.",
            "A few real things handled, nothing on fire.",
        )
    return {"key": key, "headline": headline, "subhead": subhead}


def _parse(value) -> datetime | None:
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def _parse_date(value) -> date | None:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None
