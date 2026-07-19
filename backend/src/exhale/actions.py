"""Layer 6 — Action engine (Blueprint §6, §10).

Advances household management along the controlled autonomy path::

    Observe -> Recommend -> Draft -> Execute with Approval -> Autonomous

Given the Forgetting Engine's dependency gaps, this engine *recommends* an action
type, *drafts* the appropriate §10 communication, and — on user approval —
*executes* it (resolving the obligation in the graph). Every draft stops at the
``EXECUTE_WITH_APPROVAL`` gate unless the household has opted a class of action
into ``AUTONOMOUS``.
"""

from __future__ import annotations

import uuid
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from exhale import templates
from exhale.forgetting_engine import DependencyGap, ForgettingEngine, ThreatLevel
from exhale.graph import EdgeType, KnowledgeGraph, NodeType

_RESOLVED = {"CLEAR", "COMPLETED", "RESOLVED", "CONFIRMED"}


class ActionStage(str, Enum):
    """Controlled autonomy path (§6)."""

    OBSERVE = "OBSERVE"
    RECOMMEND = "RECOMMEND"
    DRAFT = "DRAFT"
    EXECUTE_WITH_APPROVAL = "EXECUTE_WITH_APPROVAL"
    AUTONOMOUS = "AUTONOMOUS"
    EXECUTED = "EXECUTED"


class ActionType(str, Enum):
    SIGN_FORM = "SIGN_FORM"
    REQUEST_RECORD = "REQUEST_RECORD"
    PURCHASE_SUPPLIES = "PURCHASE_SUPPLIES"
    RESOLVE_CONFLICT = "RESOLVE_CONFLICT"
    ACKNOWLEDGE = "ACKNOWLEDGE"


class DeliveryVector(str, Enum):
    PUSH = "PUSH"
    BRIEFING_ELEMENT = "BRIEFING_ELEMENT"
    EMAIL = "EMAIL"
    SMS = "SMS"


# Keyword → action-type inference and its presentation.
_ACTION_LABELS = {
    ActionType.SIGN_FORM: "Review & Sign Draft",
    ActionType.REQUEST_RECORD: "Text Doctor for Record",
    ActionType.PURCHASE_SUPPLIES: "Add to Household Cart",
    ActionType.RESOLVE_CONFLICT: "Auto-draft Coverage Text",
    ActionType.ACKNOWLEDGE: "Mark Handled",
}


def infer_action_type(obligation_name: str, sub_type: str | None) -> ActionType:
    """Choose the action a gap calls for from its name / obligation sub-type."""

    text = f"{obligation_name} {sub_type or ''}".lower()
    if "signature" in text or "permission" in text or "slip" in text:
        return ActionType.SIGN_FORM
    if any(k in text for k in ("immuniz", "record", "physical", "medical", "doctor", "health")):
        return ActionType.REQUEST_RECORD
    if any(k in text for k in ("supply", "supplies", "list", "cart", "equipment", "gear")):
        return ActionType.PURCHASE_SUPPLIES
    if "conflict" in text or "carpool" in text or "overlap" in text:
        return ActionType.RESOLVE_CONFLICT
    return ActionType.ACKNOWLEDGE


class ActionDraft(BaseModel):
    """A recommended, rendered, approvable action for one obligation."""

    model_config = ConfigDict(frozen=True)

    draft_id: str = Field(default_factory=lambda: f"draft_{uuid.uuid4().hex[:10]}")
    obligation_node_id: str
    action_type: ActionType
    delivery_vector: DeliveryVector
    stage: ActionStage
    threat_level: ThreatLevel
    title: str
    body: str
    primary_action_label: str
    requires_approval: bool


class ActionEngine:
    """Generates :class:`ActionDraft`s from a graph's dependency gaps."""

    def __init__(
        self,
        graph: KnowledgeGraph,
        *,
        parent_first_name: str = "there",
        autonomous_actions: set[ActionType] | None = None,
    ) -> None:
        self.graph = graph
        self.parent_first_name = parent_first_name
        self.autonomous_actions = autonomous_actions or set()

    # -- prerequisite context -------------------------------------------------
    def _confirmed_siblings(self, anchor_node_id: str) -> list[tuple[str, str]]:
        """Resolved obligations under the same anchor, as [✓] confirmed rows."""

        confirmed: list[tuple[str, str]] = []
        for edge in self.graph.outgoing(anchor_node_id, EdgeType.DEPENDS_ON):
            node = self.graph.nodes[edge.target_node_id]
            if str(node.properties.get("status", "")).upper() in _RESOLVED:
                name = str(node.properties.get("name", node.node_id))
                detail = node.properties.get("verified_detail", "Verified")
                confirmed.append((name, detail))
        return confirmed

    # -- drafting -------------------------------------------------------------
    def draft_for_gap(self, gap: DependencyGap) -> ActionDraft:
        obligation = self.graph.nodes[gap.obligation_node_id]
        action_type = infer_action_type(gap.obligation_name, obligation.sub_type)
        days_until = max(0, int(gap.hours_until_deadline // 24))
        is_tomorrow = gap.hours_until_deadline <= 36

        if gap.threat_level is ThreatLevel.CRITICAL:
            vector = DeliveryVector.PUSH
            body = templates.critical_deadline_alarm(
                parent_first_name=self.parent_first_name,
                extracted_event=gap.obligation_name,
                target_person_name=gap.target_person_name,
                deadline_date=gap.deadline.date(),
                source_document_name=obligation.properties.get("source_document_name"),
                source_document_date=obligation.properties.get("source_document_date"),
                is_tomorrow=is_tomorrow,
            )
            title = f"Critical: {gap.obligation_name}"
        else:
            vector = DeliveryVector.BRIEFING_ELEMENT
            body = templates.dependency_gap_alarm(
                anchor_event_name=gap.anchor_event_name,
                days_until_event=days_until,
                target_person_name=gap.target_person_name,
                missing_item_name=gap.obligation_name,
                confirmed_prerequisites=self._confirmed_siblings(gap.anchor_node_id),
                total_items_count=obligation.properties.get("total_items_count"),
            )
            title = f"Dependency gap: {gap.obligation_name}"

        autonomous = action_type in self.autonomous_actions
        return ActionDraft(
            obligation_node_id=gap.obligation_node_id,
            action_type=action_type,
            delivery_vector=vector,
            stage=ActionStage.AUTONOMOUS if autonomous else ActionStage.EXECUTE_WITH_APPROVAL,
            threat_level=gap.threat_level,
            title=title,
            body=body,
            primary_action_label=_ACTION_LABELS[action_type],
            requires_approval=not autonomous,
        )

    def draft_all(self, *, now=None) -> list[ActionDraft]:
        """Draft an action for every open dependency gap in the graph."""

        gaps = ForgettingEngine(self.graph).scan_all_anchors(now=now)
        return [self.draft_for_gap(g) for g in gaps]


def mark_obligation_resolved(
    graph: KnowledgeGraph, obligation_node_id: str, *, resolution: str = "COMPLETED"
) -> None:
    """Execute an approved action by resolving its obligation in the graph."""

    node = graph.nodes.get(obligation_node_id)
    if node is None or node.type is not NodeType.OBLIGATION:
        raise KeyError(f"No obligation node {obligation_node_id!r}")
    node.properties["status"] = resolution
