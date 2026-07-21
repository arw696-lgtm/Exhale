"""Scoped-caregiver ("helper") visibility — FAMILY_STRUCTURES §3.2.

A HELPER is a secondary caregiver (grandparent, aunt, regular sitter) invited
for specific care days. They are *not* full members: they see only the child
supervision that concerns them — the care gaps on their weekdays, plus any
specific obligation the household explicitly shares — and nothing else. No
briefing, no inbox-derived items, no other family data.

This module is the pure core of that scoping: the stored scope shape, weekday
filtering of a Care Watch payload, and the deliberately-narrow obligation
summaries a helper is allowed to see. Enforcement of *which endpoints* a helper
may call lives in the API (default-deny); this module decides *what the allowed
views contain*.

A design note toward §3.3 (co-parenting across households): the obligation
summary here strips provenance — a helper sees the fact ("Permission slip due
Sept 1"), never where Exhale learned it (whose inbox). That is the seam where
partitioned visibility will later plug in; the narrowing starts here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                 "Saturday", "Sunday"]


@dataclass(frozen=True)
class HelperScope:
    """A helper's household-side scope, read from the encrypted profile."""

    weekdays: frozenset[int]           # 0=Mon .. 6=Sun — the days they cover
    shared_obligation_ids: frozenset[str]  # obligations the primary shared

    def covers(self, day: date) -> bool:
        return day.weekday() in self.weekdays

    def weekday_labels(self) -> list[str]:
        return [WEEKDAY_NAMES[d] for d in sorted(self.weekdays)]


def helper_scope(profile: dict, user_id: str) -> HelperScope:
    """The scope stored for ``user_id`` in ``profile['helpers']``.

    A helper account with no stored scope yet gets an *empty* scope — they see
    the shell and nothing else. Failing closed is the safe default.
    """

    rec = (profile.get("helpers") or {}).get(user_id) or {}
    return HelperScope(
        weekdays=frozenset(int(d) for d in rec.get("weekdays", [])),
        shared_obligation_ids=frozenset(rec.get("shared_obligation_ids", [])),
    )


def set_helper_scope(profile_helpers: dict, user_id: str, *,
                     weekdays=None, shared_obligation_ids=None) -> dict:
    """Return an updated copy of the ``helpers`` map with ``user_id``'s scope
    merged. Only provided fields change (weekday edits don't wipe shares)."""

    helpers = dict(profile_helpers or {})
    rec = dict(helpers.get(user_id) or {})
    if weekdays is not None:
        rec["weekdays"] = sorted({int(d) for d in weekdays})
    if shared_obligation_ids is not None:
        rec["shared_obligation_ids"] = sorted(set(shared_obligation_ids))
    rec.setdefault("weekdays", [])
    rec.setdefault("shared_obligation_ids", [])
    helpers[user_id] = rec
    return helpers


def filter_care_watch(care_watch: dict | None, scope: HelperScope) -> dict:
    """A Care Watch narrowed to the helper's weekdays, counts recomputed.

    An empty/absent care watch (no coverage model) yields an all-clear payload
    rather than an error — the helper's empty state is a real state.
    """

    recipient = (care_watch or {}).get("recipient", "")
    gaps = [g for g in (care_watch or {}).get("gaps", [])
            if _gap_on_covered_day(g, scope)]
    bands = {"critical": 0, "important": 0, "advisory": 0}
    for g in gaps:
        band = str(g.get("threat_level", "")).lower()
        if band in bands:
            bands[band] += 1
    return {
        "view": "helper_care_watch",
        "recipient": recipient,
        "covered_weekdays": scope.weekday_labels(),
        "summary": {
            "total_gaps": len(gaps),
            **bands,
            "assumption_dependent": sum(1 for g in gaps
                                        if g.get("depends_on_inference")),
        },
        "gaps": gaps,
    }


def _gap_on_covered_day(gap: dict, scope: HelperScope) -> bool:
    raw = gap.get("date") or gap.get("start")
    if not raw:
        return False
    try:
        day = date.fromisoformat(str(raw)[:10])
    except ValueError:
        return False
    return scope.covers(day)


def shared_obligations(graph, scope: HelperScope) -> list[dict]:
    """Narrow summaries of the obligations the household shared with the helper.

    Deliberately minimal: what/who/when — never provenance (source document,
    message reference, tier). A helper sees the task, not the household's inbox.
    Silently skips ids that no longer resolve to a node.
    """

    out: list[dict] = []
    for node_id in sorted(scope.shared_obligation_ids):
        node = graph.nodes.get(node_id)
        if node is None:
            continue
        props = node.properties
        out.append({
            "obligation_id": node_id,
            "title": str(props.get("name", node_id)),
            "person": props.get("target_person_name"),
            "date": _iso_date(props.get("deadline") or props.get("event_date")),
        })
    return out


def _iso_date(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value)
    return text[:10] if text else None


def build_helper_view(profile: dict, graph, care_watch: dict | None,
                      user_id: str) -> dict:
    """The complete payload a logged-in helper sees: their days' care gaps and
    the specific obligations shared with them — the whole of their visibility."""

    scope = helper_scope(profile, user_id)
    return {
        "view": "helper_home",
        "care_watch": filter_care_watch(care_watch, scope),
        "shared_obligations": shared_obligations(graph, scope),
        "scope": {
            "covered_weekdays": scope.weekday_labels(),
            "shared_count": len(scope.shared_obligation_ids),
        },
    }
