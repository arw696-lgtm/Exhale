"""End-to-end demo of the Exhale analytical core.

Runs the full path from a raw extraction through routing, into the Family
Knowledge Graph, and out as a Weekly COO Briefing (blueprint §3 → §4 → §7 → §9).

Usage::

    cd backend && PYTHONPATH=src python examples/demo_pipeline.py
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from exhale.briefing import build_weekly_briefing
from exhale.graph import Edge, EdgeType, KnowledgeGraph, Node, NodeType
from exhale.routing import route_extraction
from exhale.schemas import ExtractionPayload

NOW = datetime(2026, 7, 19, 8, 0, tzinfo=timezone.utc)


def main() -> None:
    # --- Layer 2: an extraction the pipeline produced from a school email ------
    payload = ExtractionPayload(
        extracted_event="West High Field Trip Permission Slip",
        target_person_name="Olivia",
        event_date=date(2026, 7, 24),
        deadline_date=date(2026, 7, 20),
        action_required=True,
        confidence_score=0.97,
        source_document_name="West High Weekly Newsletter",
        source_reference="msg_id_gmail_987234",
    )
    decision = route_extraction(payload)
    print(f"Routing: {decision.band.value} -> {decision.status.value}")

    # --- Layer 3: seed the Family Knowledge Graph -----------------------------
    g = KnowledgeGraph()
    g.add_node(Node(node_id="olivia", type=NodeType.PERSON, sub_type="CHILD",
                    properties={"first_name": "Olivia", "grade_level": 3}))
    g.add_node(Node(node_id="leo", type=NodeType.PERSON, sub_type="CHILD",
                    properties={"first_name": "Leo"}))

    g.add_node(Node(node_id="school_start", type=NodeType.EVENT,
                    properties={"name": "School Resumes", "event_date": "2026-08-25"}))
    g.add_node(Node(node_id="soccer_league", type=NodeType.EVENT,
                    properties={"name": "Soccer League Start", "event_date": "2026-07-24"}))

    # Obligations hanging off the anchors.
    g.add_node(Node(node_id="permission_slip", type=NodeType.OBLIGATION,
                    sub_type="REQUIRES_SIGNATURE",
                    properties={"name": "Field Trip Permission Slip", "status": "UNRESOLVED",
                                "deadline": (NOW + timedelta(hours=20)).isoformat(),
                                "target_person_name": "Olivia",
                                "likelihood_of_forgetting": 0.9, "impact_of_forgetting": 0.85}))
    g.add_node(Node(node_id="immunization", type=NodeType.OBLIGATION,
                    sub_type="REQUIRES_PAYMENT",
                    properties={"name": "State Immunization Record", "status": "UNRESOLVED",
                                "deadline": (NOW + timedelta(days=5)).isoformat(),
                                "target_person_name": "Leo",
                                "likelihood_of_forgetting": 0.7, "impact_of_forgetting": 0.8}))
    g.add_node(Node(node_id="supply_list", type=NodeType.OBLIGATION,
                    sub_type="PENDING_REGISTRATION",
                    properties={"name": "3rd Grade Supply List", "status": "UNRESOLVED",
                                "deadline": (NOW + timedelta(days=20)).isoformat(),
                                "target_person_name": "Olivia",
                                "likelihood_of_forgetting": 0.6, "impact_of_forgetting": 0.4}))
    g.add_node(Node(node_id="physical", type=NodeType.OBLIGATION,
                    properties={"name": "Medical Physical Form", "status": "COMPLETED"}))

    g.add_edge(Edge(edge_id="e1", type=EdgeType.DEPENDS_ON,
                    source_node_id="school_start", target_node_id="supply_list"))
    g.add_edge(Edge(edge_id="e2", type=EdgeType.DEPENDS_ON,
                    source_node_id="school_start", target_node_id="physical"))
    g.add_edge(Edge(edge_id="e3", type=EdgeType.DEPENDS_ON,
                    source_node_id="soccer_league", target_node_id="immunization"))
    g.add_edge(Edge(edge_id="e4", type=EdgeType.DEPENDS_ON,
                    source_node_id="school_start", target_node_id="permission_slip"))

    # --- Layers 5+9: Forgetting Engine -> Weekly COO Briefing -----------------
    briefing = build_weekly_briefing(g, now=NOW, week_label="Week of July 19, 2026")
    print(json.dumps(briefing, indent=2))


if __name__ == "__main__":
    main()
