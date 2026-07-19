"""Layer 5 — Operational Forgetting Engine (blueprint §7).

The engine models household risk as directional dependency chains hanging off a
confirmed *anchor* event (e.g. "School Resumes August 25"). For each unresolved
prerequisite it computes a risk score and stratifies it into a threat band.

Risk model (blueprint §7.2)::

    Risk Score = Likelihood of Forgetting (P_f) x Impact of Forgetting (I_f)

* ``P_f`` scales *inversely* with how visible the item already is in the user's
  records (something never mentioned is easy to forget → high P_f).
* ``I_f`` scales *directly* with the penalty of missing it (a child barred from a
  trip → high I_f).

Threat stratification (blueprint §7.3):

* 🔴 CRITICAL  — high-impact deadline inside a 36-hour window.
* 🟡 IMPORTANT — missing prerequisite for an anchor inside a 14-day window.
* 🔵 ADVISORY  — contextual planning-window reminder beyond that.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from exhale.graph import EdgeType, KnowledgeGraph, NodeType

# Stratification windows (blueprint §7.3).
CRITICAL_WINDOW_HOURS = 36
IMPORTANT_WINDOW_DAYS = 14
IMPORTANT_WINDOW_HOURS = IMPORTANT_WINDOW_DAYS * 24

# An item is "high impact" when its impact index is at or above this threshold.
HIGH_IMPACT_THRESHOLD = 0.5


class ThreatLevel(str, Enum):
    """Structural threat stratification bands (blueprint §7.3)."""

    CRITICAL = "CRITICAL"
    IMPORTANT = "IMPORTANT"
    ADVISORY = "ADVISORY"

    @property
    def indicator(self) -> str:
        return {"CRITICAL": "🔴", "IMPORTANT": "🟡", "ADVISORY": "🔵"}[self.value]


def score_risk(likelihood_of_forgetting: float, impact_of_forgetting: float) -> float:
    """Compute ``Risk Score = P_f x I_f`` (blueprint §7.2).

    Both inputs are probabilities/indices in ``[0.0, 1.0]``; the product is
    therefore also bounded to ``[0.0, 1.0]``.
    """

    for name, value in (
        ("likelihood_of_forgetting", likelihood_of_forgetting),
        ("impact_of_forgetting", impact_of_forgetting),
    ):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be in [0.0, 1.0], got {value!r}")
    return likelihood_of_forgetting * impact_of_forgetting


def stratify(hours_until_deadline: float, impact_of_forgetting: float) -> ThreatLevel:
    """Assign a :class:`ThreatLevel` from time-to-deadline and impact (§7.3)."""

    high_impact = impact_of_forgetting >= HIGH_IMPACT_THRESHOLD
    if hours_until_deadline <= CRITICAL_WINDOW_HOURS and high_impact:
        return ThreatLevel.CRITICAL
    if hours_until_deadline <= IMPORTANT_WINDOW_HOURS:
        return ThreatLevel.IMPORTANT
    return ThreatLevel.ADVISORY


class DependencyGap(BaseModel):
    """An unresolved prerequisite discovered hanging off an anchor event."""

    model_config = ConfigDict(frozen=True)

    anchor_node_id: str
    anchor_event_name: str
    obligation_node_id: str
    obligation_name: str
    target_person_name: str | None = None
    deadline: datetime
    likelihood_of_forgetting: float = Field(ge=0.0, le=1.0)
    impact_of_forgetting: float = Field(ge=0.0, le=1.0)
    risk_score: float = Field(ge=0.0, le=1.0)
    threat_level: ThreatLevel
    hours_until_deadline: float


class ForgettingEngine:
    """Traverses a :class:`KnowledgeGraph` to surface unresolved dependency gaps."""

    # Obligation sub-types that mean "already handled" — such nodes are skipped.
    _RESOLVED_STATUSES = {"CLEAR", "COMPLETED", "RESOLVED", "CONFIRMED"}

    def __init__(self, graph: KnowledgeGraph) -> None:
        self.graph = graph

    def _is_resolved(self, obligation_properties: dict) -> bool:
        status = str(obligation_properties.get("status", "")).upper()
        return status in self._RESOLVED_STATUSES

    def scan_anchor(
        self, anchor_node_id: str, *, now: datetime | None = None
    ) -> list[DependencyGap]:
        """Trace an anchor event's dependency chain and return unresolved gaps.

        Follows ``DEPENDS_ON`` edges from the anchor to obligation nodes,
        skips any obligation already marked resolved, and scores/stratifies the
        rest. Results are returned sorted by descending risk score.
        """

        now = now or datetime.now(timezone.utc)
        anchor = self.graph.nodes.get(anchor_node_id)
        if anchor is None:
            raise KeyError(f"Unknown anchor node: {anchor_node_id!r}")

        gaps: list[DependencyGap] = []
        for obligation in self.graph.dependencies_of(anchor_node_id):
            props = obligation.properties
            if self._is_resolved(props):
                continue

            deadline = _coerce_deadline(props.get("deadline"), fallback=anchor.properties.get("event_date"))
            if deadline is None:
                # No deadline anywhere in the chain — cannot time-stratify.
                continue
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)

            hours = (deadline - now).total_seconds() / 3600.0
            p_f = float(props.get("likelihood_of_forgetting", 0.5))
            i_f = float(props.get("impact_of_forgetting", 0.5))

            gaps.append(
                DependencyGap(
                    anchor_node_id=anchor_node_id,
                    anchor_event_name=str(anchor.properties.get("name", anchor.node_id)),
                    obligation_node_id=obligation.node_id,
                    obligation_name=str(props.get("name", obligation.node_id)),
                    target_person_name=props.get("target_person_name"),
                    deadline=deadline,
                    likelihood_of_forgetting=p_f,
                    impact_of_forgetting=i_f,
                    risk_score=score_risk(p_f, i_f),
                    threat_level=stratify(hours, i_f),
                    hours_until_deadline=hours,
                )
            )

        gaps.sort(key=lambda g: g.risk_score, reverse=True)
        return gaps

    def scan_all_anchors(self, *, now: datetime | None = None) -> list[DependencyGap]:
        """Scan every EVENT node in the graph and aggregate dependency gaps."""

        now = now or datetime.now(timezone.utc)
        all_gaps: list[DependencyGap] = []
        for node in self.graph.nodes.values():
            if node.type is NodeType.EVENT:
                all_gaps.extend(self.scan_anchor(node.node_id, now=now))
        all_gaps.sort(key=lambda g: g.risk_score, reverse=True)
        return all_gaps


def _coerce_deadline(value, *, fallback=None) -> datetime | None:
    """Best-effort coercion of a deadline value into a datetime."""

    from datetime import date

    candidate = value if value is not None else fallback
    if candidate is None:
        return None
    if isinstance(candidate, datetime):
        return candidate
    if isinstance(candidate, date):
        return datetime(candidate.year, candidate.month, candidate.day, tzinfo=timezone.utc)
    if isinstance(candidate, str):
        try:
            return datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None
