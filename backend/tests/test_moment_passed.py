"""A deadline that has passed must stop presenting itself as urgent.

Andy opened the app on 13 September and the Calendar read "The week ahead —
what's coming", then listed 28 July, 30 July, 1 August. The Today tab claimed
35 things needed him. Nothing was stale in the data sense; the arithmetic was
simply running the wrong way.

``hours_until_deadline`` goes negative once a deadline is behind us, and the
stratification windows are upper bounds — ``hours <= 36`` is *more* true the
longer ago something was due. So every past-due obligation was promoted to
CRITICAL and stayed there, and the further past it got, the more certainly it
outranked everything real. A form due in July was the loudest thing on the
screen in September.

The review queue had carried the right rule since it was written (14 days, in
:mod:`exhale.retriage`) — it had just never been applied to the obligations
that made it into the graph. These tests hold both halves of the fix: the
moot fall out of every count, and the merely-overdue stay urgent.
"""

from datetime import datetime, timedelta, timezone

from exhale.briefing import build_weekly_briefing
from exhale.forgetting_engine import (
    HIGH_IMPACT_THRESHOLD,
    MOMENT_PASSED_DAYS,
    ThreatLevel,
    stratify,
)
from exhale.graph import Edge, EdgeType, KnowledgeGraph, Node, NodeType

NOW = datetime(2026, 9, 13, 8, 0, tzinfo=timezone.utc)
HIGH = HIGH_IMPACT_THRESHOLD + 0.2


def test_long_past_deadline_is_not_critical():
    """The exact shape of the bug: negative hours cleared the window."""

    six_weeks_ago = -42 * 24
    assert stratify(six_weeks_ago, HIGH) is ThreatLevel.PAST


def test_recently_overdue_is_still_urgent():
    """Overdue by days is the case the product exists for — never drop it."""

    assert stratify(-2 * 24, HIGH) is ThreatLevel.CRITICAL
    assert stratify(-2 * 24, 0.1) is ThreatLevel.IMPORTANT


def test_the_boundary_belongs_to_the_living():
    """At exactly the cutoff the item is still live; past it, it is not."""

    edge = -MOMENT_PASSED_DAYS * 24
    assert stratify(edge, HIGH) is ThreatLevel.CRITICAL
    assert stratify(edge - 1, HIGH) is ThreatLevel.PAST


def _graph_with_obligation_due(days_from_now: int) -> KnowledgeGraph:
    """One open obligation hanging off one anchor — the shape Andy's graph had."""

    deadline = NOW + timedelta(days=days_from_now)
    graph = KnowledgeGraph()
    graph.add_node(
        Node(
            node_id="event_camp",
            type=NodeType.EVENT,
            properties={"name": "Summer Camp", "event_date": deadline.date().isoformat()},
        )
    )
    graph.add_node(
        Node(
            node_id="ob_camp",
            type=NodeType.OBLIGATION,
            sub_type="PENDING_REGISTRATION",
            properties={
                "name": "Re: Around the World - ISLA Summer Camp",
                "status": "OPEN",
                "deadline": deadline.isoformat(),
                "target_person_name": "Stevie",
                "likelihood_of_forgetting": 0.8,
                "impact_of_forgetting": HIGH,
            },
        )
    )
    graph.add_edge(
        Edge(
            edge_id="dep_camp",
            type=EdgeType.DEPENDS_ON,
            source_node_id="event_camp",
            target_node_id="ob_camp",
        )
    )
    return graph


def test_briefing_keeps_past_items_out_of_every_count():
    briefing = build_weekly_briefing(_graph_with_obligation_due(-47), now=NOW)

    assert briefing["summary"]["critical_count"] == 0
    assert briefing["summary"]["dependency_watch_count"] == 0
    assert briefing["summary"]["advisory_count"] == 0
    assert briefing["summary"]["total_gaps"] == 0, (
        "total_gaps drives 'nothing needs you' — a moot item must not hold it open"
    )
    assert briefing["summary"]["passed_count"] == 1


def test_briefing_still_carries_past_items():
    """Out of the counts, never out of the record — nothing vanishes quietly."""

    briefing = build_weekly_briefing(_graph_with_obligation_due(-47), now=NOW)

    titles = [item["title"] for item in briefing["passed"]]
    assert titles == ["Re: Around the World - ISLA Summer Camp"]


def test_a_live_obligation_is_untouched():
    briefing = build_weekly_briefing(_graph_with_obligation_due(1), now=NOW)

    assert briefing["summary"]["critical_count"] == 1
    assert briefing["summary"]["passed_count"] == 0
    assert briefing["passed"] == []


def test_the_queue_and_the_graph_agree_on_when_a_moment_has_passed():
    """Two rules with two numbers is the same bug waiting to come back."""

    from exhale import retriage

    assert retriage.STALE_DAYS == MOMENT_PASSED_DAYS
