"""In-memory household store (development / reference implementation).

This is the volatile stand-in for the encrypted persistence engine described in
``db/schema.sql``. It keeps one :class:`~exhale.graph.KnowledgeGraph` per family
plus an append-only extraction ledger, and applies the confidence-routing rules
(§3.3) when an extraction is ingested: HIGH-confidence records are committed to
the graph as OBLIGATION nodes, MEDIUM are held pending, LOW are rejected.

Swap this for a Postgres-backed repository (see ``db/schema.sql``) in production;
the public method surface is intentionally small so the API layer does not care
which implementation backs it.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone

from exhale.graph import Edge, EdgeType, KnowledgeGraph, Node, NodeType
from exhale.routing import RecordStatus, RoutingDecision, route_extraction
from exhale.schemas import ExtractionPayload


class LedgerEntry:
    """One row of the extraction ledger (§3.3 routing outcome + provenance)."""

    def __init__(
        self,
        extraction_id: str,
        payload: ExtractionPayload,
        decision: RoutingDecision,
        obligation_node_id: str | None,
    ) -> None:
        self.extraction_id = extraction_id
        self.payload = payload
        self.decision = decision
        self.obligation_node_id = obligation_node_id
        self.created_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        return {
            "extraction_id": self.extraction_id,
            "extracted_event": self.payload.extracted_event,
            "target_person_name": self.payload.target_person_name,
            "event_date": self.payload.event_date.isoformat(),
            "deadline_date": self.payload.deadline_date.isoformat()
            if self.payload.deadline_date
            else None,
            "confidence_score": self.payload.confidence_score,
            "confidence_band": self.decision.band.value,
            "record_status": self.decision.status.value,
            "obligation_node_id": self.obligation_node_id,
            "source_document_name": self.payload.source_document_name,
            "source_reference": self.payload.source_reference,
            "created_at": self.created_at.isoformat(),
        }


class HouseholdStore:
    """Thread-safe, per-family graph + ledger store."""

    def __init__(self) -> None:
        self._graphs: dict[str, KnowledgeGraph] = {}
        self._ledger: dict[str, list[LedgerEntry]] = {}
        self._lock = threading.RLock()

    # -- graph access ---------------------------------------------------------
    def graph(self, family_id: str) -> KnowledgeGraph:
        with self._lock:
            return self._graphs.setdefault(family_id, KnowledgeGraph())

    def set_graph(self, family_id: str, graph: KnowledgeGraph) -> None:
        with self._lock:
            self._graphs[family_id] = graph

    def ledger(self, family_id: str) -> list[LedgerEntry]:
        with self._lock:
            return list(self._ledger.get(family_id, []))

    # -- ingestion ------------------------------------------------------------
    def ingest(self, family_id: str, payload: ExtractionPayload) -> LedgerEntry:
        """Route an extraction and, if HIGH-confidence, commit it to the graph.

        Returns the resulting ledger entry (which carries the routing decision).
        """

        decision = route_extraction(payload)
        obligation_id: str | None = None

        with self._lock:
            graph = self._graphs.setdefault(family_id, KnowledgeGraph())

            if decision.status is RecordStatus.COMMITTED:
                obligation_id = self._commit_obligation(graph, payload)

            entry = LedgerEntry(
                extraction_id=f"ext_{uuid.uuid4().hex[:12]}",
                payload=payload,
                decision=decision,
                obligation_node_id=obligation_id,
            )
            self._ledger.setdefault(family_id, []).append(entry)
            return entry

    def _commit_obligation(self, graph: KnowledgeGraph, payload: ExtractionPayload) -> str:
        """Create an OBLIGATION node (+ anchor EVENT link) from an extraction."""

        obligation_id = f"ob_{uuid.uuid4().hex[:10]}"
        # High-impact if there is a hard deadline; easy to forget if it required
        # manual action. These are reasonable defaults the memory engine refines.
        impact = 0.85 if payload.deadline_date else 0.5
        likelihood = 0.8 if payload.action_required else 0.4

        graph.add_node(
            Node(
                node_id=obligation_id,
                type=NodeType.OBLIGATION,
                sub_type="REQUIRES_ACTION" if payload.action_required else "TRACKED",
                properties={
                    "name": payload.extracted_event,
                    "status": "UNRESOLVED",
                    "deadline": (payload.deadline_date or payload.event_date).isoformat(),
                    "target_person_name": payload.target_person_name,
                    "likelihood_of_forgetting": likelihood,
                    "impact_of_forgetting": impact,
                    "source_document_name": payload.source_document_name,
                    "source_reference": payload.source_reference,
                },
            )
        )

        anchor_id = self._ensure_event_anchor(graph, payload)
        graph.add_edge(
            Edge(
                edge_id=f"edge_{uuid.uuid4().hex[:10]}",
                type=EdgeType.DEPENDS_ON,
                source_node_id=anchor_id,
                target_node_id=obligation_id,
            )
        )
        return obligation_id

    def _ensure_event_anchor(self, graph: KnowledgeGraph, payload: ExtractionPayload) -> str:
        """Reuse an EVENT node for the payload's event name/date, or create one."""

        for node in graph.nodes.values():
            if (
                node.type is NodeType.EVENT
                and node.properties.get("name") == payload.extracted_event
            ):
                return node.node_id

        anchor_id = f"event_{uuid.uuid4().hex[:10]}"
        graph.add_node(
            Node(
                node_id=anchor_id,
                type=NodeType.EVENT,
                properties={
                    "name": payload.extracted_event,
                    "event_date": payload.event_date.isoformat(),
                },
            )
        )
        return anchor_id
