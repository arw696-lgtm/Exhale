"""Tests for the Family Knowledge Graph models (§4)."""

import pytest

from exhale.graph import Edge, EdgeType, KnowledgeGraph, Node, NodeType


def _child_school_graph() -> KnowledgeGraph:
    g = KnowledgeGraph()
    g.add_node(
        Node(
            node_id="node_child_olivia_001",
            type=NodeType.PERSON,
            sub_type="CHILD",
            properties={"first_name": "Olivia", "grade_level": 3},
        )
    )
    g.add_node(
        Node(
            node_id="node_org_westhigh_001",
            type=NodeType.ORGANIZATION,
            sub_type="SCHOOL",
            properties={"name": "West High"},
        )
    )
    g.add_edge(
        Edge(
            edge_id="edge_rel_enrollment_002",
            type=EdgeType.ENROLLED_IN,
            source_node_id="node_child_olivia_001",
            target_node_id="node_org_westhigh_001",
            properties={"academic_year": "2026-2027", "bus_route": "Route 14"},
        )
    )
    return g


def test_node_and_edge_roundtrip():
    g = _child_school_graph()
    assert len(g.nodes) == 2
    assert len(g.edges) == 1
    neighbors = g.neighbors("node_child_olivia_001", EdgeType.ENROLLED_IN)
    assert [n.node_id for n in neighbors] == ["node_org_westhigh_001"]


def test_edge_to_missing_node_raises():
    g = KnowledgeGraph()
    g.add_node(Node(node_id="a", type=NodeType.PERSON))
    with pytest.raises(KeyError):
        g.add_edge(
            Edge(
                edge_id="e1",
                type=EdgeType.PARENT_OF,
                source_node_id="a",
                target_node_id="ghost",
            )
        )


def test_dependencies_of_filters_to_depends_on_edges():
    g = KnowledgeGraph()
    g.add_node(Node(node_id="event", type=NodeType.EVENT))
    g.add_node(Node(node_id="ob1", type=NodeType.OBLIGATION))
    g.add_node(Node(node_id="ob2", type=NodeType.OBLIGATION))
    g.add_edge(
        Edge(edge_id="d1", type=EdgeType.DEPENDS_ON, source_node_id="event", target_node_id="ob1")
    )
    g.add_edge(
        Edge(edge_id="r1", type=EdgeType.REQUIRES, source_node_id="event", target_node_id="ob2")
    )
    deps = g.dependencies_of("event")
    assert [n.node_id for n in deps] == ["ob1"]


def test_edge_metadata_confidence_bounds():
    with pytest.raises(Exception):
        Edge(
            edge_id="e",
            type=EdgeType.DEPENDS_ON,
            source_node_id="a",
            target_node_id="b",
            metadata={"confidence_score": 1.5},
        )
