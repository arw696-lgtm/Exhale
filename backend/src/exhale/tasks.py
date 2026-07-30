"""The Household Contributions list — the "someone needs to do this" pile, shared.

The extraction pipeline catches obligations the world sends the family (forms,
registrations, deadlines). This is the other pile — the ones the family gives
*itself*: mow the lawn, call the plumber, run that load to the dump. Either
member adds one in a sentence; anyone can claim it ("I've got this") or just
complete it; a completed task flows into the resolved log, so it shows up in
the Handled recap and in the Sunday reflection's "what you carried" — the
invisible labor of running a house, made visible and credited.

Deliberately small:

* **No due dates, no priorities, no assignment.** A chore list that needs
  management becomes another job. Tasks are a flat pile; claiming is a
  *volunteer* act, never an assignment — nobody can put a task on someone
  else's plate, only on the household's.
* **Completion is the only celebration path.** A completed task is logged
  once (idempotent) with who did it; deleting a task ("let it go") logs
  nothing — deciding not to do something is a release, not an achievement.
* **Suggestion, never nag.** The UI may lay open tasks next to a found window
  ("Saturday morning is open — want to knock one out?"); the engine never
  schedules a chore into someone's time on its own.
* **Weekly contributions come back.** The word is the family's own — everyone
  *contributes*, so the recurring ones (clean the house, vacuum) are framed as
  contributions, not obligations. A weekly contribution completed this week is
  credited this week and quietly returns next week; each week's completion is
  credited exactly once.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

MAX_OPEN_TASKS = 100

CADENCES = ("once", "weekly")


def week_key(when: datetime | None = None) -> str:
    """ISO year-week of ``when`` — the idempotency unit for weekly credit."""

    iso = (when or datetime.now()).isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def new_task(description: str, *, created_by: str, cadence: str = "once") -> dict:
    if cadence not in CADENCES:
        raise ValueError(f"cadence must be one of {CADENCES}")
    return {
        "id": f"task_{uuid.uuid4().hex[:10]}",
        "description": description.strip(),
        "created_by": created_by,
        "created_at": datetime.now().isoformat(),
        "cadence": cadence,
        "claimed_by": None,
        "status": "open",          # open | done (one-offs only; weeklies stay open)
        "completed_by": None,
        "completed_at": None,
        # Weekly bookkeeping: which week was last credited, and by whom.
        "last_completed_week": None,
        "last_completed_by": None,
    }


def add_task(
    items: list[dict], description: str, *, created_by: str, cadence: str = "once"
) -> tuple[list[dict], dict]:
    """Append a new task. Raises ``ValueError`` on an empty description, a bad
    cadence, or a pile already at the cap (a 100-item chore list is a
    different problem)."""

    if not description.strip():
        raise ValueError("A task needs a description")
    if sum(1 for t in items if t.get("status") == "open") >= MAX_OPEN_TASKS:
        raise ValueError(f"Too many open tasks (max {MAX_OPEN_TASKS})")
    task = new_task(description, created_by=created_by, cadence=cadence)
    return [*items, task], task


def claim_task(items: list[dict], task_id: str, *, who: str) -> list[dict]:
    """"I've got this" — volunteer for a task. Re-claiming by someone else is
    allowed (plans change); claiming is a signal, never a lock."""

    return _update(items, task_id, lambda t: {**t, "claimed_by": who})


def unclaim_task(items: list[dict], task_id: str) -> list[dict]:
    return _update(items, task_id, lambda t: {**t, "claimed_by": None})


def complete_task(
    items: list[dict], task_id: str, *, who: str, now: datetime | None = None
) -> tuple[list[dict], dict]:
    """Mark a task done (kept in the list, marked — same as resolved waits).

    A one-off closes for good. A **weekly contribution** is credited for this
    week (stamped with the week and the contributor) and stays open — it
    returns next week on its own. Raises ``KeyError`` for an unknown id,
    ``ValueError`` on a double-complete (per week, for weeklies) — a
    double-tap must not double-credit.
    """

    now = now or datetime.now()
    target = next((t for t in items if t["id"] == task_id), None)
    if target is None:
        raise KeyError(f"No task {task_id!r}")

    if target.get("cadence") == "weekly":
        this_week = week_key(now)
        if target.get("last_completed_week") == this_week:
            raise ValueError(f"Task {task_id!r} was already done this week")
        done = {**target, "last_completed_week": this_week,
                "last_completed_by": who, "claimed_by": None,
                "completed_at": now.isoformat()}
    else:
        if target.get("status") == "done":
            raise ValueError(f"Task {task_id!r} is already done")
        done = {**target, "status": "done", "completed_by": who,
                "completed_at": now.isoformat()}
    return [done if t["id"] == task_id else t for t in items], done


def drop_task(items: list[dict], task_id: str) -> list[dict]:
    """Let a task go — removed without ceremony, and never logged as a win."""

    if not any(t["id"] == task_id for t in items):
        raise KeyError(f"No task {task_id!r}")
    return [t for t in items if t["id"] != task_id]


def open_tasks(items: list[dict], *, now: datetime | None = None) -> list[dict]:
    """The pile as a member should see it, oldest first.

    A weekly contribution already done this week steps out of the pile (its
    week is covered) and returns when the week turns — no re-adding, no nag.
    """

    this_week = week_key(now or datetime.now())
    visible = []
    for t in items:
        if t.get("status") != "open":
            continue
        if t.get("cadence") == "weekly" and t.get("last_completed_week") == this_week:
            continue
        visible.append(t)
    return sorted(visible, key=lambda t: t.get("created_at", ""))


def done_this_week(items: list[dict], *, now: datetime | None = None) -> list[dict]:
    """Weekly contributions already covered this week — shown as quiet credit."""

    this_week = week_key(now or datetime.now())
    return [t for t in items
            if t.get("cadence") == "weekly"
            and t.get("last_completed_week") == this_week]


def _update(items: list[dict], task_id: str, fn) -> list[dict]:
    found = False
    out = []
    for t in items:
        if t["id"] == task_id:
            if t.get("status") == "done":
                raise ValueError(f"Task {task_id!r} is already done")
            t = fn(t)
            found = True
        out.append(t)
    if not found:
        raise KeyError(f"No task {task_id!r}")
    return out
