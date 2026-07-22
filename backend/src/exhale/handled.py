"""The resolved-items log — what Exhale handled, so the family didn't have to.

Every system that marks something resolved already exists (Forgetting Engine
obligations via approved drafts / confirmed facts, the Waiting-On ledger);
this module only adds the memory of it: a small append-only log in the
encrypted profile, and a read-only weekly recap for the briefing's closing
note. No detection or resolution logic changes.

Honesty rules:

* Entries are logged only at the moment a real resolution happens — the recap
  can never fabricate a catch to fill space. A quiet week reads as a quiet
  week.
* ``pattern_catch`` is in the schema for the day the memory layer actively
  pre-fills something; today it only *displays* learned rules, so no code
  path emits that type yet. The type existing is not the same as pretending
  it fires.
* Descriptions reuse the human-readable text the source system already
  generated — no new description logic.
"""

from __future__ import annotations

from datetime import datetime, timedelta

# The log is capped so the profile blob doesn't grow without bound; the recap
# only ever reads the last week anyway.
MAX_LOG_ENTRIES = 200
RECAP_DAYS = 7

RESOLVED_TYPES = ("dependency_gap", "waiting_on", "pattern_catch")


def log_resolved(
    store,
    family_id: str,
    *,
    item_id: str,
    resolved_type: str,
    brief_description: str,
    resolved_at: datetime | None = None,
) -> dict | None:
    """Append one resolution to the family's log (idempotent per item+type).

    Returns the entry written, or ``None`` when this item+type was already
    logged — re-approving or double-tapping never inflates the recap.
    """

    if resolved_type not in RESOLVED_TYPES:
        raise ValueError(f"unknown resolved_type {resolved_type!r}")
    entries = list(store.profile(family_id).get("resolved_log") or [])
    if any(e["item_id"] == item_id and e["resolved_type"] == resolved_type
           for e in entries):
        return None
    entry = {
        "item_id": item_id,
        "family_id": family_id,
        "resolved_type": resolved_type,
        "resolved_at": (resolved_at or datetime.now()).isoformat(),
        "brief_description": brief_description,
    }
    entries.append(entry)
    store.set_profile(family_id, resolved_log=entries[-MAX_LOG_ENTRIES:])
    return entry


def handled_this_week(profile: dict, *, now: datetime | None = None) -> dict:
    """The briefing's closing-note payload: what resolved in the last 7 days.

    ``count == 0`` is a real state the UI must render honestly ("a quiet
    week"), never pad.
    """

    now = now or datetime.now()
    cutoff = now - timedelta(days=RECAP_DAYS)
    items = []
    for e in profile.get("resolved_log") or []:
        try:
            resolved_at = datetime.fromisoformat(e["resolved_at"])
        except (KeyError, ValueError):
            continue
        if resolved_at.tzinfo is not None:
            resolved_at = resolved_at.replace(tzinfo=None)
        if resolved_at >= cutoff:
            items.append(e)
    items.sort(key=lambda e: e["resolved_at"], reverse=True)
    return {
        "view": "handled_recap",
        "days": RECAP_DAYS,
        "count": len(items),
        "items": items,
    }
