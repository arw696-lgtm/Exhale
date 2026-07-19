"""Demo household seed — the "Household Assessment Snapshot" (Blueprint §6).

Populates a store with a realistic family graph so the API returns a meaningful
Weekly COO Briefing on first load, mirroring Exhale's cold-start promise of
surfacing forgotten obligations within the first session.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from exhale.graph import Edge, EdgeType, KnowledgeGraph, Node, NodeType
from exhale.store import HouseholdStore

DEMO_FAMILY_ID = "family_demo_001"


def build_demo_graph(now: datetime | None = None) -> KnowledgeGraph:
    now = now or datetime.now(timezone.utc)
    g = KnowledgeGraph()

    # People
    g.add_node(Node(node_id="olivia", type=NodeType.PERSON, sub_type="CHILD",
                    properties={"first_name": "Olivia", "grade_level": 3}))
    g.add_node(Node(node_id="leo", type=NodeType.PERSON, sub_type="CHILD",
                    properties={"first_name": "Leo"}))

    # Anchor events
    g.add_node(Node(node_id="school_start", type=NodeType.EVENT,
                    properties={"name": "School Resumes", "event_date": "2026-08-25"}))
    g.add_node(Node(node_id="soccer_league", type=NodeType.EVENT,
                    properties={"name": "Soccer League Start", "event_date": "2026-07-24"}))

    # Obligations hanging off anchors
    obligations = [
        ("permission_slip", "School_start_dep", "school_start", {
            "name": "West High Field Trip Permission Slip", "status": "UNRESOLVED",
            "deadline": (now + timedelta(hours=20)).isoformat(), "target_person_name": "Olivia",
            "likelihood_of_forgetting": 0.9, "impact_of_forgetting": 0.85,
            "source_document_name": "West High Weekly Newsletter"}),
        ("immunization", "soccer_dep", "soccer_league", {
            "name": "State Immunization Record", "status": "UNRESOLVED",
            "deadline": (now + timedelta(hours=30)).isoformat(), "target_person_name": "Leo",
            "likelihood_of_forgetting": 0.8, "impact_of_forgetting": 0.9,
            "source_document_name": "Soccer League Onboarding Packet"}),
        ("supply_list", "supply_dep", "school_start", {
            "name": "3rd Grade Classroom Supply List", "status": "UNRESOLVED",
            "deadline": (now + timedelta(days=20)).isoformat(), "target_person_name": "Olivia",
            "likelihood_of_forgetting": 0.6, "impact_of_forgetting": 0.4}),
        ("physical", "physical_dep", "school_start", {
            "name": "Medical Physical Form", "status": "COMPLETED"}),
    ]
    for node_id, edge_id, anchor, props in obligations:
        g.add_node(Node(node_id=node_id, type=NodeType.OBLIGATION, properties=props))
        g.add_edge(Edge(edge_id=edge_id, type=EdgeType.DEPENDS_ON,
                        source_node_id=anchor, target_node_id=node_id))

    return g


def seed_demo(store: HouseholdStore, now: datetime | None = None) -> str:
    """Load the demo household into ``store`` and return its family id."""

    store.set_graph(DEMO_FAMILY_ID, build_demo_graph(now))
    return DEMO_FAMILY_ID
