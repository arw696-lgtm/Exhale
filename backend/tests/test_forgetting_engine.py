"""Tests for the Operational Forgetting Engine (§7)."""

from datetime import datetime, timedelta, timezone

import pytest

from exhale.forgetting_engine import (
    ForgettingEngine,
    ThreatLevel,
    score_risk,
    stratify,
)
from exhale.graph import Edge, EdgeType, KnowledgeGraph, Node, NodeType

NOW = datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)


def test_risk_score_is_product_and_bounded():
    assert score_risk(1.0, 1.0) == 1.0
    assert score_risk(0.0, 0.9) == 0.0
    assert score_risk(0.5, 0.4) == pytest.approx(0.2)


def test_risk_score_rejects_out_of_range():
    with pytest.raises(ValueError):
        score_risk(1.2, 0.5)


@pytest.mark.parametrize(
    "hours,impact,expected",
    [
        (12, 0.9, ThreatLevel.CRITICAL),   # high impact, inside 36h
        (36, 0.8, ThreatLevel.CRITICAL),   # inclusive boundary
        (12, 0.2, ThreatLevel.IMPORTANT),  # inside 36h but low impact
        (72, 0.9, ThreatLevel.IMPORTANT),  # inside 14d
        (24 * 14, 0.9, ThreatLevel.IMPORTANT),  # inclusive 14d boundary
        (24 * 20, 0.9, ThreatLevel.ADVISORY),   # beyond 14d
    ],
)
def test_stratify_bands(hours, impact, expected):
    assert stratify(hours, impact) is expected


def _anchor_with_dependency(deadline: datetime, *, status: str, p_f=0.8, i_f=0.9) -> KnowledgeGraph:
    g = KnowledgeGraph()
    g.add_node(
        Node(
            node_id="event_school",
            type=NodeType.EVENT,
            properties={"name": "School Resumes", "event_date": "2026-08-25"},
        )
    )
    g.add_node(
        Node(
            node_id="ob_supply_list",
            type=NodeType.OBLIGATION,
            sub_type="PENDING_REGISTRATION",
            properties={
                "name": "3rd Grade Supply List",
                "status": status,
                "deadline": deadline.isoformat(),
                "target_person_name": "Olivia",
                "likelihood_of_forgetting": p_f,
                "impact_of_forgetting": i_f,
            },
        )
    )
    g.add_edge(
        Edge(
            edge_id="dep_1",
            type=EdgeType.DEPENDS_ON,
            source_node_id="event_school",
            target_node_id="ob_supply_list",
        )
    )
    return g


def test_unresolved_dependency_surfaces_as_gap():
    deadline = NOW + timedelta(hours=10)
    engine = ForgettingEngine(_anchor_with_dependency(deadline, status="UNRESOLVED"))
    gaps = engine.scan_anchor("event_school", now=NOW)
    assert len(gaps) == 1
    gap = gaps[0]
    assert gap.obligation_name == "3rd Grade Supply List"
    assert gap.target_person_name == "Olivia"
    assert gap.threat_level is ThreatLevel.CRITICAL
    assert gap.risk_score == pytest.approx(0.72)


def test_resolved_dependency_is_skipped():
    deadline = NOW + timedelta(hours=10)
    engine = ForgettingEngine(_anchor_with_dependency(deadline, status="COMPLETED"))
    assert engine.scan_anchor("event_school", now=NOW) == []


def test_gaps_sorted_by_descending_risk():
    g = KnowledgeGraph()
    g.add_node(Node(node_id="ev", type=NodeType.EVENT, properties={"name": "Camp"}))
    for i, (p, imp) in enumerate([(0.2, 0.2), (0.9, 0.9), (0.5, 0.6)]):
        g.add_node(
            Node(
                node_id=f"ob{i}",
                type=NodeType.OBLIGATION,
                properties={
                    "name": f"task{i}",
                    "status": "UNRESOLVED",
                    "deadline": (NOW + timedelta(days=5)).isoformat(),
                    "likelihood_of_forgetting": p,
                    "impact_of_forgetting": imp,
                },
            )
        )
        g.add_edge(
            Edge(edge_id=f"d{i}", type=EdgeType.DEPENDS_ON, source_node_id="ev", target_node_id=f"ob{i}")
        )
    gaps = ForgettingEngine(g).scan_anchor("ev", now=NOW)
    scores = [gap.risk_score for gap in gaps]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] == pytest.approx(0.81)


def test_scan_all_anchors_aggregates():
    engine = ForgettingEngine(
        _anchor_with_dependency(NOW + timedelta(days=3), status="UNRESOLVED")
    )
    gaps = engine.scan_all_anchors(now=NOW)
    assert len(gaps) == 1
