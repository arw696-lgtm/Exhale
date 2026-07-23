"""Personal intentions — the things a person is *trying* to find time for.

The thesis made concrete: Exhale's coverage math already finds the windows
("you're free and the kids are looked after"); this module remembers what the
family actually wanted that time *for* — seeing a friend, the dermatology
appointment, getting back to the gym — and lays the two side by side.

Deliberately not a task manager: an intention is a sentence and a type
(standing vs one-off), under 30 seconds to enter. Matching is deliberately
human: v1 surfaces open intentions alongside open windows and lets the person
decide — no auto-assignment, no scheduling logic, no change to the window
calculation itself.

Two disciplines keep the list from turning on its owner:

* **Anti-guilt staleness.** An intention surfaced ~4 weeks without being
  matched or dismissed stops appearing in the main list and gets one gentle
  check-in ("still want this here, or should we let it go?"). Reconfirm
  resets the clock; dismiss retires it; ignoring the check-in for a week
  marks it ``stale`` and it stops surfacing until revisited manually. An old
  intention is retired or reconfirmed — never left to nag.
* **One honest follow-up.** A week after an intention is matched, the
  briefing asks once whether it actually happened; the answer (or a week of
  silence → ``no_response``) is logged and the question never repeats. This
  is the only place the system checks whether found time is *landing* rather
  than just being displayed. Stored, not yet aggregated — by design.

Surfacing is debounced to once per 7 days: the briefing endpoint fires on
every page load, and four refreshes in a minute must never count as four
weeks.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

TYPES = ("standing", "one_off")
STATUSES = ("open", "matched", "dismissed", "stale")
FOLLOW_UP_OUTCOMES = ("happened", "didnt_happen", "no_response")
# What kind of time an intention needs (routes it to the right window):
#   alone    — this person free, kids covered (a solo lift, an appointment)
#   together — every parent free at once (a class as a couple, a date)
#   on_duty  — you've got the kid but aren't slammed (email the teacher,
#              clean the bathrooms) — the things that don't need you child-free
# A workout isn't inherently solitary; a chore doesn't need the kids gone.
CONTEXTS = ("alone", "together", "on_duty")

# An open intention surfaced this many times (weekly-debounced) gets the
# check-in instead of another quiet appearance.
CHECK_IN_AFTER_SURFACINGS = 4
# Both the surfacing debounce and the "ignored for a week" windows.
SURFACE_INTERVAL_DAYS = 7


def new_intention(
    family_id: str,
    created_by: str,
    description: str,
    *,
    type_: str = "standing",
    target_deadline: str | None = None,
    context: str = "alone",
) -> dict:
    """A new open intention. Raises ``ValueError`` on empty/invalid input."""

    description = description.strip()
    if not description:
        raise ValueError("An intention needs a description")
    if type_ not in TYPES:
        raise ValueError(f"type must be one of {TYPES}")
    if context not in CONTEXTS:
        raise ValueError(f"context must be one of {CONTEXTS}")
    return {
        "intention_id": f"int_{uuid.uuid4().hex[:10]}",
        "family_id": family_id,
        "created_by": created_by,
        "description": description,
        "type": type_,
        # Whose time this belongs to matters for "together": it's a shared want.
        "context": context,
        "target_deadline": target_deadline,
        "status": "open",
        "created_at": datetime.now().isoformat(),
        # Surfacing / staleness state.
        "surfaced_count": 0,
        "last_surfaced_at": None,
        "check_in_at": None,
        # Outcome tracking (set when matched / followed up).
        "matched_at": None,
        "matched_window": None,
        "follow_up_surfaced_at": None,
        "follow_up_outcome": None,
    }


def set_status(
    items: list[dict],
    intention_id: str,
    status: str,
    *,
    matched_window: dict | None = None,
    now: datetime | None = None,
) -> list[dict]:
    """Return a copy of ``items`` with one intention's status changed.

    ``matched`` = the human scheduled it (stamps ``matched_at`` and the
    window it was matched to, arming the one-week follow-up); ``dismissed``
    = no longer relevant; ``open`` = back on the list (a standing intent
    naturally reopens — surfacing counters reset so it starts fresh).
    Raises ``ValueError`` for a bad status, ``KeyError`` for an unknown id.
    """

    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    now = now or datetime.now()
    out = []
    found = False
    for item in items:
        if item.get("intention_id") == intention_id:
            item = {**item, "status": status}
            if status == "matched":
                item["matched_at"] = now.isoformat()
                item["matched_window"] = matched_window
                item["follow_up_surfaced_at"] = None
                item["follow_up_outcome"] = None
            elif status == "open":
                item["surfaced_count"] = 0
                item["check_in_at"] = None
            found = True
        out.append(item)
    if not found:
        raise KeyError(f"No intention {intention_id!r}")
    return out


def reconfirm(items: list[dict], intention_id: str) -> list[dict]:
    """"Still want this here" — keep the intention, reset its staleness clock."""

    return set_status(items, intention_id, "open")


def record_follow_up(
    items: list[dict], intention_id: str, outcome: str
) -> list[dict]:
    """Answer the one follow-up ("did that happen?"). Once, then done.

    Raises ``ValueError`` for a bad outcome or an unmatched/already-answered
    intention, ``KeyError`` for an unknown id.
    """

    if outcome not in ("happened", "didnt_happen"):
        raise ValueError("outcome must be 'happened' or 'didnt_happen'")
    out = []
    found = False
    for item in items:
        if item.get("intention_id") == intention_id:
            if item.get("matched_at") is None:
                raise ValueError("Only a matched intention has a follow-up")
            if item.get("follow_up_outcome") is not None:
                raise ValueError("Follow-up already answered")
            item = {**item, "follow_up_outcome": outcome}
            found = True
        out.append(item)
    if not found:
        raise KeyError(f"No intention {intention_id!r}")
    return out


def open_items(items: list[dict]) -> list[dict]:
    return [i for i in items if i.get("status") == "open"]


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def _week_elapsed(ts: str | None, now: datetime) -> bool:
    parsed = _parse(ts)
    return parsed is not None and now - parsed >= timedelta(days=SURFACE_INTERVAL_DAYS)


def surface(items: list[dict], *, now: datetime | None = None) -> tuple[list[dict], dict]:
    """One briefing-build pass over the intentions: who shows where, honestly.

    Returns ``(updated_items, groups)`` where groups carries:

    * ``active`` — open intentions for the main list (surfacing stamped, at
      most once per :data:`SURFACE_INTERVAL_DAYS`);
    * ``check_ins`` — open intentions surfaced ≥4 times awaiting a
      keep-or-let-go answer (ignored ≥7 days → auto-``stale``, dropped);
    * ``follow_ups`` — matched intentions a week past their match awaiting
      the one "did that happen?" (ignored ≥7 days → ``no_response``, done).

    The caller persists ``updated_items`` — surfacing is state, not styling.
    """

    now = now or datetime.now()
    updated: list[dict] = []
    active: list[dict] = []
    check_ins: list[dict] = []
    follow_ups: list[dict] = []

    for item in items:
        item = dict(item)
        status = item.get("status")

        if status == "open":
            due_for_stamp = (item.get("last_surfaced_at") is None
                             or _week_elapsed(item.get("last_surfaced_at"), now))
            if (item.get("surfaced_count") or 0) >= CHECK_IN_AFTER_SURFACINGS:
                # Check-in territory. Shown once; a week of silence retires it.
                if item.get("check_in_at") is None:
                    item["check_in_at"] = now.isoformat()
                    check_ins.append(item)
                elif _week_elapsed(item.get("check_in_at"), now):
                    item["status"] = "stale"  # ignored — let it go quietly
                else:
                    check_ins.append(item)  # still within its week — keep asking once
            else:
                if due_for_stamp:
                    item["surfaced_count"] = (item.get("surfaced_count") or 0) + 1
                    item["last_surfaced_at"] = now.isoformat()
                active.append(item)

        elif status == "matched" and item.get("follow_up_outcome") is None:
            if _week_elapsed(item.get("matched_at"), now):
                if item.get("follow_up_surfaced_at") is None:
                    item["follow_up_surfaced_at"] = now.isoformat()
                    follow_ups.append(item)
                elif _week_elapsed(item.get("follow_up_surfaced_at"), now):
                    item["follow_up_outcome"] = "no_response"  # asked once; done
                else:
                    follow_ups.append(item)

        updated.append(item)

    return updated, {"active": active, "check_ins": check_ins, "follow_ups": follow_ups}


def build_time_for_what_matters(
    windows: list[dict],
    groups: dict,
    items: list[dict],
    *,
    together_windows: list[dict] | None = None,
    on_duty_windows: list[dict] | None = None,
    show_add_nudge: bool = True,
) -> dict:
    """The briefing block: real open windows next to what's genuinely current.

    Three kinds of time, each matched to the intentions that need it: personal
    ``windows`` (alone), ``together_windows`` (both parents free), and
    ``on_duty_windows`` (you've got the kid but aren't slammed). All are
    already-computed engine output — this layer never recalculates them.
    """

    together_windows = together_windows or []
    on_duty_windows = on_duty_windows or []
    active = groups["active"]
    together = [i for i in active if i.get("context") == "together"]
    on_duty = [i for i in active if i.get("context") == "on_duty"]
    alone = [i for i in active if i.get("context", "alone") not in ("together", "on_duty")]
    return {
        "view": "time_for_what_matters",
        "windows": windows,
        "together_windows": together_windows,
        "on_duty_windows": on_duty_windows,
        "open_intentions": active,               # full list (back-compat)
        "alone_intentions": alone,
        "together_intentions": together,
        "on_duty_intentions": on_duty,
        "check_ins": groups["check_ins"],
        "follow_ups": follow_up_payload(groups["follow_ups"]),
        "show_add_nudge": show_add_nudge,
        "counts": {
            "windows": len(windows),
            "together_windows": len(together_windows),
            "on_duty_windows": len(on_duty_windows),
            "open": len(active),
            "alone": len(alone),
            "together": len(together),
            "on_duty": len(on_duty),
            "check_ins": len(groups["check_ins"]),
            "follow_ups": len(groups["follow_ups"]),
            "matched": sum(1 for i in items if i.get("status") == "matched"),
            "dismissed": sum(1 for i in items if i.get("status") == "dismissed"),
            "stale": sum(1 for i in items if i.get("status") == "stale"),
        },
    }


def follow_up_payload(follow_ups: list[dict]) -> list[dict]:
    """The follow-up question's display shape (no internal bookkeeping)."""

    return [{
        "intention_id": i["intention_id"],
        "description": i["description"],
        "matched_at": i.get("matched_at"),
        "matched_window": i.get("matched_window"),
    } for i in follow_ups]
