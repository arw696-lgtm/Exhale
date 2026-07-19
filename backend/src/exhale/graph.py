"""Layer 3 — Family Knowledge Graph (blueprint §4).

A graph-relational map of a household: typed :class:`Node` entities connected by
directional :class:`Edge` relationships. This module provides the in-memory
model and taxonomy (§4.3); persistence is handled separately by the encrypted
storage layer (``db/schema.sql``, blueprint §5.3).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class NodeType(str, Enum):
    """Top-level node taxonomy (blueprint §4.3)."""

    PERSON = "PERSON"
    ORGANIZATION = "ORGANIZATION"
    EVENT = "EVENT"
    DOCUMENT = "DOCUMENT"
    OBLIGATION = "OBLIGATION"


class EdgeType(str, Enum):
    """Directional relationship taxonomy (blueprint §3, §4.2)."""

    PARENT_OF = "PARENT_OF"
    ENROLLED_IN = "ENROLLED_IN"
    COACHES = "COACHES"
    DEPENDS_ON = "DEPENDS_ON"
    ATTENDS = "ATTENDS"
    REQUIRES = "REQUIRES"


class NodeMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    created_at: datetime = Field(default_factory=_utcnow)
    updated_by: str | None = None
    source_provenance: str | None = None


class EdgeMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    verified_by_user: bool = False


class Node(BaseModel):
    """A single entity in the Family Knowledge Graph (blueprint §4.1)."""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    type: NodeType
    sub_type: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
    metadata: NodeMetadata = Field(default_factory=NodeMetadata)


class Edge(BaseModel):
    """A directional relationship between two nodes (blueprint §4.2)."""

    model_config = ConfigDict(extra="forbid")

    edge_id: str
    type: EdgeType
    source_node_id: str
    target_node_id: str
    properties: dict[str, Any] = Field(default_factory=dict)
    metadata: EdgeMetadata = Field(default_factory=EdgeMetadata)


class KnowledgeGraph(BaseModel):
    """An in-memory Family Knowledge Graph with basic traversal helpers.

    This is intentionally a lightweight adjacency model — enough to drive the
    Forgetting Engine's dependency-chain traversal (§7.1) and to validate the
    node/edge contracts — not a full graph database.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    nodes: dict[str, Node] = Field(default_factory=dict)
    edges: dict[str, Edge] = Field(default_factory=dict)

    def add_node(self, node: Node) -> Node:
        self.nodes[node.node_id] = node
        return node

    def add_edge(self, edge: Edge) -> Edge:
        if edge.source_node_id not in self.nodes:
            raise KeyError(f"Unknown source node: {edge.source_node_id!r}")
        if edge.target_node_id not in self.nodes:
            raise KeyError(f"Unknown target node: {edge.target_node_id!r}")
        self.edges[edge.edge_id] = edge
        return edge

    def outgoing(self, node_id: str, edge_type: EdgeType | None = None) -> list[Edge]:
        """Return edges originating from ``node_id`` (optionally filtered by type)."""

        return [
            e
            for e in self.edges.values()
            if e.source_node_id == node_id
            and (edge_type is None or e.type is edge_type)
        ]

    def neighbors(self, node_id: str, edge_type: EdgeType | None = None) -> list[Node]:
        """Return target nodes reachable in one hop from ``node_id``."""

        return [self.nodes[e.target_node_id] for e in self.outgoing(node_id, edge_type)]

    def dependencies_of(self, node_id: str) -> list[Node]:
        """Return nodes that ``node_id`` DEPENDS_ON (dependency-chain edges)."""

        return self.neighbors(node_id, EdgeType.DEPENDS_ON)
