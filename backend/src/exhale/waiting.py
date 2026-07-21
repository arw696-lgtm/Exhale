"""Waiting-On ledger — conversations where the ball is in someone else's court.

Born from a real thread: the family emailed Hennepin County about their
property, the county said "I'll reach out to the arborist," and then — silence.
Nothing in the household's task list was *due*, yet something real was pending:
a promised reply that could quietly die. Reactive tools have no shape for this
state; the shared brain does.

A waiting item records who owes the response, what it's about, and since when.
Staleness stratifies with the same vocabulary as everything else: fresh waits
are 🔵 ADVISORY, week-old waits are 🟡 IMPORTANT ("time for a nudge"), and
two-week-old waits are 🔴 CRITICAL ("this thread is dying"). Resolved items are
kept, marked — like dismissals, a resolved wait is signal, not erasure.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from exhale.forgetting_engine import ThreatLevel

NUDGE_AFTER_DAYS = 7      # a week of silence → worth a nudge
CRITICAL_AFTER_DAYS = 14  # two weeks → the thread is dying


def new_item(who: str, about: str, *, since: date | None = None, channel: str | None = None) -> dict:
    """A fresh waiting-on record (plain dict — stored in the encrypted profile)."""

    return {
        "id": f"wait_{uuid.uuid4().hex[:10]}",
        "who": who,
        "about": about,
        "since": (since or date.today()).isoformat(),
        "channel": channel,
        "resolved": False,
        "resolved_at": None,
    }


def _stratify(days_waiting: int) -> ThreatLevel:
    if days_waiting >= CRITICAL_AFTER_DAYS:
        return ThreatLevel.CRITICAL
    if days_waiting >= NUDGE_AFTER_DAYS:
        return ThreatLevel.IMPORTANT
    return ThreatLevel.ADVISORY


def build_waiting_watch(items: list[dict], *, now: date | None = None) -> dict:
    """Briefing-ready payload: open waits, staleness-stratified, oldest first."""

    today = now or date.today()
    open_items = []
    for item in items:
        if item.get("resolved"):
            continue
        since = date.fromisoformat(item["since"])
        days = max((today - since).days, 0)
        level = _stratify(days)
        open_items.append({
            "id": item["id"],
            "who": item["who"],
            "about": item["about"],
            "since": item["since"],
            "channel": item.get("channel"),
            "days_waiting": days,
            "threat_level": level.value,
            "indicator": level.indicator,
            "suggested_action": (
                f"Nudge {item['who']}" if days >= NUDGE_AFTER_DAYS
                else "Waiting — no action needed yet"
            ),
        })
    open_items.sort(key=lambda i: i["since"])
    return {
        "view": "waiting_on",
        "summary": {
            "open": len(open_items),
            "need_nudge": sum(1 for i in open_items
                              if i["days_waiting"] >= NUDGE_AFTER_DAYS),
        },
        "items": open_items,
    }


def resolve_item(items: list[dict], item_id: str) -> list[dict]:
    """Mark one item resolved (kept in the list). Raises KeyError if absent."""

    found = False
    out = []
    for item in items:
        if item["id"] == item_id:
            item = {**item, "resolved": True,
                    "resolved_at": datetime.now().isoformat()}
            found = True
        out.append(item)
    if not found:
        raise KeyError(f"No waiting item {item_id!r}")
    return out
