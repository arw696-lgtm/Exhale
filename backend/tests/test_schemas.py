"""Tests for the Layer 2 extraction contract (§3.2)."""

from datetime import date

import pytest
from pydantic import ValidationError

from exhale.schemas import ExtractionPayload


def test_minimal_required_payload_validates():
    payload = ExtractionPayload(
        extracted_event="West High Field Trip Permission Slip",
        event_date=date(2026, 7, 20),
        action_required=True,
        confidence_score=0.97,
    )
    assert payload.target_person_name is None
    assert payload.deadline_date is None


def test_optional_entities_default_to_none_not_guessed():
    payload = ExtractionPayload(
        extracted_event="Soccer practice",
        event_date=date(2026, 8, 1),
        action_required=False,
        confidence_score=0.5,
    )
    assert payload.target_person_name is None
    assert payload.source_reference is None


def test_confidence_score_is_bounded():
    with pytest.raises(ValidationError):
        ExtractionPayload(
            extracted_event="x",
            event_date=date(2026, 8, 1),
            action_required=True,
            confidence_score=1.5,
        )
    with pytest.raises(ValidationError):
        ExtractionPayload(
            extracted_event="x",
            event_date=date(2026, 8, 1),
            action_required=True,
            confidence_score=-0.1,
        )


def test_missing_required_field_fails():
    with pytest.raises(ValidationError):
        ExtractionPayload(
            extracted_event="x",
            action_required=True,
            confidence_score=0.9,
        )


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        ExtractionPayload(
            extracted_event="x",
            event_date=date(2026, 8, 1),
            action_required=True,
            confidence_score=0.9,
            rogue_field="nope",
        )


def test_payload_is_immutable():
    payload = ExtractionPayload(
        extracted_event="x",
        event_date=date(2026, 8, 1),
        action_required=True,
        confidence_score=0.9,
    )
    with pytest.raises(ValidationError):
        payload.confidence_score = 0.1
