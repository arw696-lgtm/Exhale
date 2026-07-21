"""Weekly COO Briefing assembler (blueprint §9.1).

Turns the Forgetting Engine's dependency gaps into the three-section payload the
Sunday Morning Briefing UI renders: Critical Threats, Dependency Watch, and
(optionally) Calendar Conflicts. The output is a plain, JSON-serializable dict
so it can be handed straight to the React frontend as a fixture or API response.
"""

from __future__ import annotations

from datetime import datetime, timezone

from exhale.credibility import build_coverage
from exhale.forgetting_engine import DependencyGap, ForgettingEngine, ThreatLevel
from exhale.graph import KnowledgeGraph


def _gap_to_item(gap: DependencyGap) -> dict:
    return {
        "obligation_id": gap.obligation_node_id,
        "title": gap.obligation_name,
        "person": gap.target_person_name,
        "anchor_event": gap.anchor_event_name,
        "deadline": gap.deadline.date().isoformat(),
        "hours_until_deadline": round(gap.hours_until_deadline, 1),
        "risk_score": round(gap.risk_score, 3),
        "threat_level": gap.threat_level.value,
        "indicator": gap.threat_level.indicator,
    }


def build_weekly_briefing(
    graph: KnowledgeGraph,
    *,
    now: datetime | None = None,
    week_label: str | None = None,
    coverage: dict | None = None,
    care_watch: dict | None = None,
    learned_rules: list[dict] | None = None,
    waiting_on: dict | None = None,
) -> dict:
    """Assemble the Weekly COO Briefing payload from a family's graph.

    ``coverage`` is the credibility layer's source-coverage block (see
    :func:`exhale.credibility.build_coverage`); when the caller does not
    supply one, the briefing still carries the honest default ("coverage
    undeclared") rather than implying completeness.

    ``care_watch`` is the Care-Coverage Engine's payload (see
    :func:`exhale.coverage.build_care_watch`) — the child-supervision gaps for
    the week. Included when supplied; omitted (``None``) when the household has
    no coverage model configured yet.
    """

    now = now or datetime.now(timezone.utc)
    engine = ForgettingEngine(graph)
    gaps = engine.scan_all_anchors(now=now)

    critical = [_gap_to_item(g) for g in gaps if g.threat_level is ThreatLevel.CRITICAL]
    dependency_watch = [
        _gap_to_item(g) for g in gaps if g.threat_level is ThreatLevel.IMPORTANT
    ]
    advisory = [_gap_to_item(g) for g in gaps if g.threat_level is ThreatLevel.ADVISORY]

    return {
        "product": "Exhale",
        "view": "weekly_coo_briefing",
        "week_of": week_label or now.date().isoformat(),
        "generated_at": now.isoformat(),
        "summary": {
            "critical_count": len(critical),
            "dependency_watch_count": len(dependency_watch),
            "advisory_count": len(advisory),
            "total_gaps": len(gaps),
        },
        "critical_threats": critical,
        "dependency_watch": dependency_watch,
        "advisories": advisory,
        "coverage": coverage if coverage is not None else build_coverage(None),
        "care_watch": care_watch,
        # Layer-4 memory: recurring rules the ledger has taught (with evidence).
        "learned_rules": learned_rules or [],
        # Threads where the ball is in someone else's court (None = none tracked).
        "waiting_on": waiting_on,
    }
