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

from exhale.actions import ActionDraft, ActionEngine, mark_obligation_resolved
from exhale.graph import Edge, EdgeType, KnowledgeGraph, Node, NodeType
from exhale.routing import RecordStatus, RoutingDecision, route_extraction
from exhale.schemas import ExtractionPayload, FactOrigin


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
        # Set when a later user correction replaces this entry as the record.
        self.superseded_by: str | None = None

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
            # Credibility layer: how authoritative the artifact is, whether the
            # date was read or derived, the observed time window (null = the
            # honest UNKNOWN state), and the named gaps.
            "artifact_tier": self.payload.artifact_tier.value,
            "event_date_origin": self.payload.event_date_origin.value,
            "event_start_time": self.payload.event_start_time.isoformat()
            if self.payload.event_start_time
            else None,
            "event_end_time": self.payload.event_end_time.isoformat()
            if self.payload.event_end_time
            else None,
            "missing_fields": self.payload.missing_fields(),
            "corrects": self.payload.corrects,
            "superseded_by": self.superseded_by,
            "created_at": self.created_at.isoformat(),
        }


class HouseholdStore:
    """Thread-safe, per-family graph + ledger store."""

    def __init__(self) -> None:
        self._graphs: dict[str, KnowledgeGraph] = {}
        self._ledger: dict[str, list[LedgerEntry]] = {}
        self._profiles: dict[str, dict] = {}
        self._lock = threading.RLock()

    # -- graph access ---------------------------------------------------------
    def graph(self, family_id: str) -> KnowledgeGraph:
        with self._lock:
            return self._graphs.setdefault(family_id, KnowledgeGraph())

    def set_graph(self, family_id: str, graph: KnowledgeGraph) -> None:
        with self._lock:
            self._graphs[family_id] = graph

    def set_profile(self, family_id: str, **profile) -> None:
        with self._lock:
            self._profiles.setdefault(family_id, {}).update(profile)

    def profile(self, family_id: str) -> dict:
        with self._lock:
            return dict(self._profiles.get(family_id, {}))

    def family_ids(self) -> list[str]:
        """Every family known to the store (for background jobs like auto-sync)."""

        with self._lock:
            return sorted(set(self._graphs) | set(self._profiles) | set(self._ledger))

    # -- action layer (§6, §10) ----------------------------------------------
    def drafts(self, family_id: str, viewer_first_name: str | None = None) -> list[ActionDraft]:
        """Generate approvable action drafts for every open dependency gap.

        Drafts render fresh per call, so the greeting can address whoever is
        actually looking — pass the viewing member's first name; the founding
        member's stored name is only the anonymous-mode fallback.
        """

        with self._lock:
            graph = self._graphs.get(family_id)
            if graph is None:
                return []
            parent = (viewer_first_name
                      or self._profiles.get(family_id, {}).get("parent_first_name", "there"))
            return ActionEngine(graph, parent_first_name=parent).draft_all()

    def approve_action(
        self, family_id: str, obligation_node_id: str, *, resolution: str = "COMPLETED"
    ) -> None:
        """Execute an approved action by resolving its obligation in the graph."""

        with self._lock:
            graph = self._graphs.get(family_id)
            if graph is None:
                raise KeyError(f"No graph for family {family_id!r}")
            mark_obligation_resolved(graph, obligation_node_id, resolution=resolution)

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

    def correct(self, family_id: str, extraction_id: str, **fixes) -> LedgerEntry:
        """Apply a user correction — the highest tier of ground truth.

        The corrected payload re-enters the pipeline stamped USER_CONFIRMED
        (routing always commits it), the original ledger entry is marked
        superseded (kept — corrections are a logged failure signal, not an
        erasure), and any obligation the original committed is updated in
        place rather than duplicated.
        """

        with self._lock:
            entries = self._ledger.get(family_id, [])
            original = next(
                (e for e in entries if e.extraction_id == extraction_id), None
            )
            if original is None:
                raise KeyError(
                    f"No extraction {extraction_id!r} for family {family_id!r}"
                )
            if original.superseded_by is not None:
                # A second confirm/correct of the same entry would mint a second
                # obligation for the same fact — refuse instead.
                raise ValueError(
                    f"Extraction {extraction_id!r} was already superseded by "
                    f"{original.superseded_by!r}"
                )

            data = original.payload.model_dump()
            data.update(fixes)
            data["confidence_score"] = 1.0
            data["event_date_origin"] = FactOrigin.USER_CONFIRMED
            data["corrects"] = extraction_id
            payload = ExtractionPayload(**data)
            decision = route_extraction(payload)

            graph = self._graphs.setdefault(family_id, KnowledgeGraph())
            existing = (
                graph.nodes.get(original.obligation_node_id)
                if original.obligation_node_id
                else None
            )
            if existing is not None:
                props = self._obligation_properties(
                    payload, corroborated=existing.properties.get("corroborated", False)
                )
                props["status"] = existing.properties.get("status", "UNRESOLVED")
                existing.properties.update(props)
                obligation_id = existing.node_id
            else:
                obligation_id = self._commit_obligation(graph, payload)

            entry = LedgerEntry(
                extraction_id=f"ext_{uuid.uuid4().hex[:12]}",
                payload=payload,
                decision=decision,
                obligation_node_id=obligation_id,
            )
            original.superseded_by = entry.extraction_id
            self._ledger.setdefault(family_id, []).append(entry)
            return entry

    @staticmethod
    def _link_supersessions(entries: list[LedgerEntry]) -> None:
        """Rebuild superseded_by links from payload.corrects (used on hydration)."""

        by_id = {e.extraction_id: e for e in entries}
        for entry in entries:
            if entry.payload.corrects:
                target = by_id.get(entry.payload.corrects)
                if target is not None:
                    target.superseded_by = entry.extraction_id

    @staticmethod
    def _obligation_properties(payload: ExtractionPayload, *, corroborated: bool) -> dict:
        # High-impact if there is a hard deadline; easy to forget if it required
        # manual action. These are reasonable defaults the memory engine refines.
        return {
            "name": payload.extracted_event,
            "status": "UNRESOLVED",
            "deadline": (payload.deadline_date or payload.event_date).isoformat(),
            "target_person_name": payload.target_person_name,
            "likelihood_of_forgetting": 0.8 if payload.action_required else 0.4,
            "impact_of_forgetting": 0.85 if payload.deadline_date else 0.5,
            "source_document_name": payload.source_document_name,
            "source_reference": payload.source_reference,
            # Credibility layer: cite-or-gap, never a silent default.
            "artifact_tier": payload.artifact_tier.value,
            "event_date_origin": payload.event_date_origin.value,
            "event_start_time": payload.event_start_time.isoformat()
            if payload.event_start_time
            else None,
            "event_end_time": payload.event_end_time.isoformat()
            if payload.event_end_time
            else None,
            "hours_known": payload.event_start_time is not None,
            "missing_fields": payload.missing_fields(),
            "corroborated": corroborated,
        }

    def _commit_obligation(self, graph: KnowledgeGraph, payload: ExtractionPayload) -> str:
        """Create an OBLIGATION node (+ anchor EVENT link) from an extraction."""

        anchor_id, witnesses = self._ensure_event_anchor(graph, payload)
        obligation_id = f"ob_{uuid.uuid4().hex[:10]}"
        graph.add_node(
            Node(
                node_id=obligation_id,
                type=NodeType.OBLIGATION,
                sub_type="REQUIRES_ACTION" if payload.action_required else "TRACKED",
                properties=self._obligation_properties(
                    payload, corroborated=witnesses > 1
                ),
            )
        )
        graph.add_edge(
            Edge(
                edge_id=f"edge_{uuid.uuid4().hex[:10]}",
                type=EdgeType.DEPENDS_ON,
                source_node_id=anchor_id,
                target_node_id=obligation_id,
            )
        )
        return obligation_id

    def _ensure_event_anchor(
        self, graph: KnowledgeGraph, payload: ExtractionPayload
    ) -> tuple[str, int]:
        """Reuse an EVENT node for the payload's event name, or create one.

        Returns ``(anchor_id, witness_count)`` where the witness count is the
        number of distinct source artifacts attesting this event so far — the
        falsification-pass primitive: an event attested by a single artifact
        is UNCORROBORATED and downstream surfaces may say so.
        """

        for node in graph.nodes.values():
            if (
                node.type is NodeType.EVENT
                and node.properties.get("name") == payload.extracted_event
            ):
                refs = node.properties.setdefault("witness_refs", [])
                if payload.source_reference and payload.source_reference not in refs:
                    refs.append(payload.source_reference)
                return node.node_id, max(len(refs), 1)

        anchor_id = f"event_{uuid.uuid4().hex[:10]}"
        graph.add_node(
            Node(
                node_id=anchor_id,
                type=NodeType.EVENT,
                properties={
                    "name": payload.extracted_event,
                    "event_date": payload.event_date.isoformat(),
                    "witness_refs": [payload.source_reference]
                    if payload.source_reference
                    else [],
                },
            )
        )
        return anchor_id, 1
