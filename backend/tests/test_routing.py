"""Tests for the Confidence Routing Matrix (§3.3)."""

from datetime import date

import pytest

from exhale.routing import (
    ConfidenceBand,
    RecordStatus,
    classify_confidence,
    route_extraction,
)
from exhale.schemas import ExtractionPayload


def _payload(score: float) -> ExtractionPayload:
    return ExtractionPayload(
        extracted_event="Permission slip",
        event_date=date(2026, 8, 1),
        action_required=True,
        confidence_score=score,
    )


@pytest.mark.parametrize(
    "score,band",
    [
        (1.0, ConfidenceBand.HIGH),
        (0.92, ConfidenceBand.HIGH),  # inclusive lower bound
        (0.9199, ConfidenceBand.MEDIUM),
        (0.70, ConfidenceBand.MEDIUM),  # inclusive lower bound
        (0.6999, ConfidenceBand.LOW),
        (0.0, ConfidenceBand.LOW),
    ],
)
def test_band_boundaries(score, band):
    assert classify_confidence(score) is band


def test_high_confidence_commits_without_review():
    decision = route_extraction(_payload(0.95))
    assert decision.band is ConfidenceBand.HIGH
    assert decision.status is RecordStatus.COMMITTED
    assert decision.commits_to_graph is True
    assert decision.requires_user_review is False


def test_medium_confidence_pends_for_verification():
    decision = route_extraction(_payload(0.80))
    assert decision.band is ConfidenceBand.MEDIUM
    assert decision.status is RecordStatus.PENDING_VERIFICATION
    assert decision.commits_to_graph is False
    assert decision.requires_user_review is True


def test_low_confidence_rejected_from_graph():
    decision = route_extraction(_payload(0.42))
    assert decision.band is ConfidenceBand.LOW
    assert decision.status is RecordStatus.REJECTED
    assert decision.commits_to_graph is False
    assert decision.requires_user_review is False
