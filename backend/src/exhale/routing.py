"""Pipeline Confidence Routing Matrix (blueprint §3.3).

Once an :class:`~exhale.schemas.ExtractionPayload` is produced, its
``confidence_score`` decides how it flows through the rest of the system:

* **High** (``>= 0.92``)  — bypass human triage; write to the graph and schedule
  downstream tracking immediately.
* **Medium** (``0.70`` – ``0.91``) — set status ``PENDING_VERIFICATION`` and
  surface a UI review state anchored to the source fragment.
* **Low** (``< 0.70``) — reject from the graph; prompt the user for a
  higher-clarity artifact or native manual entry.

The band boundaries are defined once here so the whole system agrees on them.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict

from exhale.schemas import ExtractionPayload

# Band boundaries (inclusive lower bounds), straight from §3.3.
HIGH_CONFIDENCE_THRESHOLD = 0.92
MEDIUM_CONFIDENCE_THRESHOLD = 0.70


class ConfidenceBand(str, Enum):
    """The three confidence bands defined by the routing matrix."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class RecordStatus(str, Enum):
    """Lifecycle status assigned to a record as a result of routing."""

    COMMITTED = "COMMITTED"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    REJECTED = "REJECTED"


class RoutingDecision(BaseModel):
    """The outcome of routing a single extraction payload."""

    model_config = ConfigDict(frozen=True)

    band: ConfidenceBand
    status: RecordStatus
    commits_to_graph: bool
    requires_user_review: bool
    rationale: str


def classify_confidence(score: float) -> ConfidenceBand:
    """Map a raw confidence score onto a :class:`ConfidenceBand`."""

    if score >= HIGH_CONFIDENCE_THRESHOLD:
        return ConfidenceBand.HIGH
    if score >= MEDIUM_CONFIDENCE_THRESHOLD:
        return ConfidenceBand.MEDIUM
    return ConfidenceBand.LOW


def route_extraction(payload: ExtractionPayload) -> RoutingDecision:
    """Route an extraction payload according to the §3.3 matrix."""

    band = classify_confidence(payload.confidence_score)

    if band is ConfidenceBand.HIGH:
        return RoutingDecision(
            band=band,
            status=RecordStatus.COMMITTED,
            commits_to_graph=True,
            requires_user_review=False,
            rationale=(
                "High-confidence band (>= 0.92): bypasses human triage; record "
                "populates the graph and schedules downstream tracking immediately."
            ),
        )

    if band is ConfidenceBand.MEDIUM:
        return RoutingDecision(
            band=band,
            status=RecordStatus.PENDING_VERIFICATION,
            commits_to_graph=False,
            requires_user_review=True,
            rationale=(
                "Medium-confidence band (0.70-0.91): record held as "
                "PENDING_VERIFICATION with a UI review state anchored to the "
                "source fragment."
            ),
        )

    return RoutingDecision(
        band=band,
        status=RecordStatus.REJECTED,
        commits_to_graph=False,
        requires_user_review=False,
        rationale=(
            "Low-confidence band (< 0.70): rejected from the graph; user is asked "
            "for a higher-clarity artifact or native manual entry."
        ),
    )
