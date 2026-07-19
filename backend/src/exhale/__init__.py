"""Exhale — The Trusted Second Brain and Predictive Chief of Staff for Modern Households.

This package implements the core, testable layers of the Exhale production
blueprint (v2.0):

* ``schemas``           — Layer 2 extraction data contract (§3).
* ``routing``           — Confidence routing matrix (§3.3).
* ``graph``             — Layer 3 Family Knowledge Graph node/edge models (§4).
* ``forgetting_engine`` — Layer 5 risk scoring & threat stratification (§7).

The modules are deliberately dependency-light (Pydantic only) so the analytical
core can be exercised, tested, and embedded independently of any transport,
persistence, or LLM provider.
"""

from exhale.forgetting_engine import (
    DependencyGap,
    ForgettingEngine,
    ThreatLevel,
    score_risk,
)
from exhale.graph import Edge, EdgeType, KnowledgeGraph, Node, NodeType
from exhale.routing import ConfidenceBand, RoutingDecision, route_extraction
from exhale.schemas import ExtractionPayload

__version__ = "2.0.0"

__all__ = [
    "__version__",
    # schemas
    "ExtractionPayload",
    # routing
    "ConfidenceBand",
    "RoutingDecision",
    "route_extraction",
    # graph
    "Node",
    "NodeType",
    "Edge",
    "EdgeType",
    "KnowledgeGraph",
    # forgetting engine
    "ThreatLevel",
    "DependencyGap",
    "ForgettingEngine",
    "score_risk",
]
