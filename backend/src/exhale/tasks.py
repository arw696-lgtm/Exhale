"""The Household Task List — the "someone needs to do this" pile, shared.

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
"""

from __future__ import annotations

import uuid
from datetime import datetime

MAX_OPEN_TASKS = 100


def new_task(description: str, *, created_by: str) -> dict:
    return {
        "id": f"task_{uuid.uuid4().hex[:10]}",
        "description": description.strip(),
        "created_by": created_by,
        "created_at": datetime.now().isoformat(),
        "claimed_by": None,
        "status": "open",          # open | done
        "completed_by": None,
        "completed_at": None,
    }


def add_task(items: list[dict], description: str, *, created_by: str) -> tuple[list[dict], dict]:
    """Append a new task. Raises ``ValueError`` on an empty description or a
    pile already at the cap (a 100-item chore list is a different problem)."""

    if not description.strip():
        raise ValueError("A task needs a description")
    if sum(1 for t in items if t.get("status") == "open") >= MAX_OPEN_TASKS:
        raise ValueError(f"Too many open tasks (max {MAX_OPEN_TASKS})")
    task = new_task(description, created_by=created_by)
    return [*items, task], task


def claim_task(items: list[dict], task_id: str, *, who: str) -> list[dict]:
    """"I've got this" — volunteer for a task. Re-claiming by someone else is
    allowed (plans change); claiming is a signal, never a lock."""

    return _update(items, task_id, lambda t: {**t, "claimed_by": who})


def unclaim_task(items: list[dict], task_id: str) -> list[dict]:
    return _update(items, task_id, lambda t: {**t, "claimed_by": None})


def complete_task(items: list[dict], task_id: str, *, who: str) -> tuple[list[dict], dict]:
    """Mark a task done (kept in the list, marked — same as resolved waits).

    Returns the updated list and the completed task. Raises ``KeyError`` for
    an unknown id, ``ValueError`` if it was already completed — a double-tap
    must not double-credit.
    """

    target = next((t for t in items if t["id"] == task_id), None)
    if target is None:
        raise KeyError(f"No task {task_id!r}")
    if target.get("status") == "done":
        raise ValueError(f"Task {task_id!r} is already done")
    done = {**target, "status": "done", "completed_by": who,
            "completed_at": datetime.now().isoformat()}
    return [done if t["id"] == task_id else t for t in items], done


def drop_task(items: list[dict], task_id: str) -> list[dict]:
    """Let a task go — removed without ceremony, and never logged as a win."""

    if not any(t["id"] == task_id for t in items):
        raise KeyError(f"No task {task_id!r}")
    return [t for t in items if t["id"] != task_id]


def open_tasks(items: list[dict]) -> list[dict]:
    """Open tasks, oldest first — the pile as a member should see it."""

    return sorted(
        (t for t in items if t.get("status") == "open"),
        key=lambda t: t.get("created_at", ""),
    )


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
