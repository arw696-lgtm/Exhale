"""Tests for the Layer 6 Action engine (§6, §10)."""

from datetime import datetime, timedelta, timezone

import pytest

from exhale.actions import (
    ActionEngine,
    ActionStage,
    ActionType,
    DeliveryVector,
    infer_action_type,
    mark_obligation_resolved,
)
from exhale.forgetting_engine import ThreatLevel
from exhale.graph import Edge, EdgeType, KnowledgeGraph, Node, NodeType

NOW = datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "name,sub_type,expected",
    [
        ("Field Trip Permission Slip", "REQUIRES_SIGNATURE", ActionType.SIGN_FORM),
        ("State Immunization Record", None, ActionType.REQUEST_RECORD),
        ("3rd Grade Supply List", None, ActionType.PURCHASE_SUPPLIES),
        ("Carpool overlap", None, ActionType.RESOLVE_CONFLICT),
        ("Read newsletter", None, ActionType.ACKNOWLEDGE),
    ],
)
def test_infer_action_type(name, sub_type, expected):
    assert infer_action_type(name, sub_type) is expected


def _graph_with(deadline_offset, *, status="UNRESOLVED", name="Field Trip Permission Slip",
                sub_type="REQUIRES_SIGNATURE", extra=None):
    g = KnowledgeGraph()
    g.add_node(Node(node_id="anchor", type=NodeType.EVENT,
                    properties={"name": "School Resumes", "event_date": "2026-08-25"}))
    props = {
        "name": name, "status": status,
        "deadline": (NOW + deadline_offset).isoformat(),
        "target_person_name": "Olivia",
        "likelihood_of_forgetting": 0.9, "impact_of_forgetting": 0.85,
        "source_document_name": "West High Weekly Newsletter",
    }
    props.update(extra or {})
    g.add_node(Node(node_id="ob", type=NodeType.OBLIGATION, sub_type=sub_type, properties=props))
    g.add_edge(Edge(edge_id="e", type=EdgeType.DEPENDS_ON, source_node_id="anchor", target_node_id="ob"))
    return g


def test_critical_gap_drafts_push_deadline_alarm():
    engine = ActionEngine(_graph_with(timedelta(hours=20)), parent_first_name="Andrew")
    drafts = engine.draft_all(now=NOW)
    assert len(drafts) == 1
    d = drafts[0]
    assert d.threat_level is ThreatLevel.CRITICAL
    assert d.delivery_vector is DeliveryVector.PUSH
    assert d.action_type is ActionType.SIGN_FORM
    assert d.primary_action_label == "Review & Sign Draft"
    assert d.requires_approval is True
    assert d.stage is ActionStage.EXECUTE_WITH_APPROVAL
    assert "[🚨 CRITICAL THREAT]" in d.body
    assert "Hey Andrew" in d.body


def test_important_gap_drafts_dependency_briefing_element():
    engine = ActionEngine(_graph_with(timedelta(days=7), name="3rd Grade Supply List",
                                       sub_type=None, extra={"total_items_count": 12,
                                                             "impact_of_forgetting": 0.9}))
    drafts = engine.draft_all(now=NOW)
    d = drafts[0]
    assert d.threat_level is ThreatLevel.IMPORTANT
    assert d.delivery_vector is DeliveryVector.BRIEFING_ELEMENT
    assert d.action_type is ActionType.PURCHASE_SUPPLIES
    assert "[➔ DEPENDENCY GAP DETECTED]" in d.body
    assert "Add all 12 items" in d.body


def test_confirmed_siblings_render_as_checkmarks():
    g = _graph_with(timedelta(days=7), name="3rd Grade Supply List", sub_type=None,
                    extra={"impact_of_forgetting": 0.9})
    # Add a resolved sibling under the same anchor.
    g.add_node(Node(node_id="physical", type=NodeType.OBLIGATION,
                    properties={"name": "Medical Physical Form", "status": "COMPLETED",
                                "verified_detail": "Verified July 14"}))
    g.add_edge(Edge(edge_id="e2", type=EdgeType.DEPENDS_ON,
                    source_node_id="anchor", target_node_id="physical"))
    drafts = ActionEngine(g).draft_all(now=NOW)
    body = drafts[0].body
    assert "• [✓] Medical Physical Form: Confirmed (Verified July 14)" in body


def test_autonomous_action_type_skips_approval_gate():
    engine = ActionEngine(_graph_with(timedelta(hours=20)),
                          autonomous_actions={ActionType.SIGN_FORM})
    d = engine.draft_all(now=NOW)[0]
    assert d.stage is ActionStage.AUTONOMOUS
    assert d.requires_approval is False


def test_mark_obligation_resolved_removes_gap():
    g = _graph_with(timedelta(hours=20))
    engine = ActionEngine(g)
    assert len(engine.draft_all(now=NOW)) == 1
    mark_obligation_resolved(g, "ob")
    assert engine.draft_all(now=NOW) == []


def test_mark_resolved_rejects_non_obligation():
    g = _graph_with(timedelta(hours=20))
    with pytest.raises(KeyError):
        mark_obligation_resolved(g, "anchor")
