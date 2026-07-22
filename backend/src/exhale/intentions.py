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
"""

from __future__ import annotations

import uuid
from datetime import datetime

TYPES = ("standing", "one_off")
STATUSES = ("open", "matched", "dismissed")


def new_intention(
    family_id: str,
    created_by: str,
    description: str,
    *,
    type_: str = "standing",
    target_deadline: str | None = None,
) -> dict:
    """A new open intention. Raises ``ValueError`` on empty/invalid input."""

    description = description.strip()
    if not description:
        raise ValueError("An intention needs a description")
    if type_ not in TYPES:
        raise ValueError(f"type must be one of {TYPES}")
    return {
        "intention_id": f"int_{uuid.uuid4().hex[:10]}",
        "family_id": family_id,
        "created_by": created_by,
        "description": description,
        "type": type_,
        "target_deadline": target_deadline,
        "status": "open",
        "created_at": datetime.now().isoformat(),
    }


def set_status(items: list[dict], intention_id: str, status: str) -> list[dict]:
    """Return a copy of ``items`` with one intention's status changed.

    ``matched`` = the human scheduled it; ``dismissed`` = no longer relevant;
    ``open`` = back on the list (a standing intent naturally reopens).
    Raises ``ValueError`` for a bad status, ``KeyError`` for an unknown id.
    """

    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    out = []
    found = False
    for item in items:
        if item.get("intention_id") == intention_id:
            item = {**item, "status": status}
            found = True
        out.append(item)
    if not found:
        raise KeyError(f"No intention {intention_id!r}")
    return out


def open_items(items: list[dict]) -> list[dict]:
    return [i for i in items if i.get("status") == "open"]


def build_time_for_what_matters(windows: list[dict], items: list[dict]) -> dict:
    """The briefing block: real open windows next to open intentions.

    ``windows`` are already-computed work-window dicts (the engine's own
    output — this layer never recalculates them). Both lists may be empty;
    the UI renders each combination honestly (a windowless week, a week with
    time but nothing logged) without nagging or fabricating.
    """

    open_now = open_items(items)
    return {
        "view": "time_for_what_matters",
        "windows": windows,
        "open_intentions": open_now,
        "counts": {
            "windows": len(windows),
            "open": len(open_now),
            "matched": sum(1 for i in items if i.get("status") == "matched"),
            "dismissed": sum(1 for i in items if i.get("status") == "dismissed"),
        },
    }
