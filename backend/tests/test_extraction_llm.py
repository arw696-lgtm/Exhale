"""Tests for the LLM-backed extractor and the hybrid composition (§3)."""

from datetime import date, datetime, timezone

import pytest

from exhale.connectors.base import RawMessage
from exhale.extraction import ExtractionContext, extract_payload
from exhale.extraction_llm import (
    DEFAULT_MODEL,
    HybridExtractor,
    LLMExtractor,
    LLMUnavailable,
    _LLMExtraction,
    extractor_from_env,
)


# --- stub Anthropic client ------------------------------------------------------
class _StubResponse:
    def __init__(self, parsed_output, stop_reason="end_turn"):
        self.parsed_output = parsed_output
        self.stop_reason = stop_reason


class _StubMessages:
    def __init__(self, outcome):
        self._outcome = outcome
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


class _StubClient:
    def __init__(self, outcome):
        self.messages = _StubMessages(outcome)


def _msg(subject="Re: pickup", body="", received=None, domain=None):
    return RawMessage(
        source_id="m1",
        channel="gmail",
        subject=subject,
        body=body,
        received_at=received or datetime(2026, 7, 19, tzinfo=timezone.utc),
        sender=f"x@{domain}" if domain else None,
        sender_domain=domain,
    )


def _llm_result(**over):
    base = dict(
        contains_trackable_item=True,
        extracted_event="Swim Meet",
        target_person_name="Olivia",
        event_date=date(2026, 8, 2),
        deadline_date=date(2026, 7, 28),
        action_required=True,
        confidence_score=0.9,
    )
    base.update(over)
    return _LLMExtraction(**base)


CTX = ExtractionContext(known_children=["Olivia", "Leo"])


# --- LLMExtractor ---------------------------------------------------------------
def test_llm_extraction_maps_to_payload_with_pipeline_provenance():
    client = _StubClient(_StubResponse(_llm_result()))
    payload = LLMExtractor(client=client).extract(_msg(), CTX)

    assert payload is not None
    assert payload.extracted_event == "Swim Meet"
    assert payload.event_date == date(2026, 8, 2)
    assert payload.deadline_date == date(2026, 7, 28)
    assert payload.target_person_name == "Olivia"
    # Provenance is stamped by the pipeline, never trusted from the model.
    assert payload.source_reference == "m1"
    assert payload.source_document_name == "Re: pickup"


def test_llm_request_shape():
    client = _StubClient(_StubResponse(_llm_result()))
    LLMExtractor(client=client).extract(
        _msg(body="Hi Olivia's swim meet is Aug 2. Sign up by July 28."), CTX
    )
    call = client.messages.calls[0]
    assert call["model"] == DEFAULT_MODEL
    assert call["thinking"] == {"type": "adaptive"}
    assert call["output_format"] is _LLMExtraction
    prompt = call["messages"][0]["content"]
    assert "Message sent: 2026-07-19" in prompt      # relative dates anchor here
    assert "Olivia, Leo" in prompt                   # household context provided
    assert "swim meet is Aug 2" in prompt


def test_not_trackable_returns_none():
    client = _StubClient(_StubResponse(_llm_result(
        contains_trackable_item=False, extracted_event=None, event_date=None)))
    assert LLMExtractor(client=client).extract(_msg(), CTX) is None


def test_missing_event_date_returns_none_not_guess():
    client = _StubClient(_StubResponse(_llm_result(event_date=None)))
    assert LLMExtractor(client=client).extract(_msg(), CTX) is None


def test_confidence_is_clamped():
    client = _StubClient(_StubResponse(_llm_result(confidence_score=1.7)))
    payload = LLMExtractor(client=client).extract(_msg(), CTX)
    assert payload.confidence_score == 1.0


def test_api_error_raises_llm_unavailable():
    client = _StubClient(RuntimeError("connection reset"))
    with pytest.raises(LLMUnavailable):
        LLMExtractor(client=client).extract(_msg(), CTX)


def test_refusal_or_parse_failure_raises_llm_unavailable():
    client = _StubClient(_StubResponse(None, stop_reason="refusal"))
    with pytest.raises(LLMUnavailable, match="refusal"):
        LLMExtractor(client=client).extract(_msg(), CTX)


# --- HybridExtractor --------------------------------------------------------------
HIGH_CONFIDENCE_BODY = (
    "Please sign and return the permission slip for Olivia's field trip. "
    "The trip is on August 25, 2026. Forms are due by July 24, 2026."
)


def test_hybrid_high_confidence_deterministic_skips_llm():
    client = _StubClient(_StubResponse(_llm_result()))
    hybrid = HybridExtractor(LLMExtractor(client=client))
    raw = _msg(subject="Field Trip Permission Slip",
               body=HIGH_CONFIDENCE_BODY, domain="powerschool.com")

    payload = hybrid.extract(raw, CTX)
    assert payload is not None
    assert payload.extracted_event == "Field Trip Permission Slip"  # deterministic
    assert client.messages.calls == []  # no API cost for the easy case


def test_hybrid_consults_llm_when_deterministic_finds_nothing():
    client = _StubClient(_StubResponse(_llm_result()))
    hybrid = HybridExtractor(LLMExtractor(client=client))
    # No date the regex engine can find → deterministic returns None.
    raw = _msg(body="Coach says the season opener got moved to the first "
                    "Sunday of next month — sign Leo up before it fills.")

    payload = hybrid.extract(raw, CTX)
    assert payload is not None
    assert payload.extracted_event == "Swim Meet"  # came from the LLM
    assert len(client.messages.calls) == 1


def test_hybrid_llm_judgment_wins_over_low_confidence_guess():
    # LLM says "not trackable"; the deterministic LOW-band guess is dropped.
    client = _StubClient(_StubResponse(_llm_result(
        contains_trackable_item=False, extracted_event=None, event_date=None)))
    hybrid = HybridExtractor(LLMExtractor(client=client))
    raw = _msg(subject="Reminder", body="See you on Monday.")

    assert extract_payload(raw, CTX) is not None  # deterministic had a guess
    assert hybrid.extract(raw, CTX) is None       # LLM overrides it


def test_hybrid_falls_back_to_deterministic_when_llm_down():
    client = _StubClient(RuntimeError("api down"))
    hybrid = HybridExtractor(LLMExtractor(client=client))
    raw = _msg(subject="Reminder", body="See you on Monday.")

    payload = hybrid.extract(raw, CTX)
    assert payload is not None                    # deterministic result survives
    assert payload == extract_payload(raw, CTX)


# --- env factory -------------------------------------------------------------------
def test_extractor_from_env_defaults_to_deterministic(monkeypatch):
    monkeypatch.delenv("EXHALE_LLM_EXTRACTOR", raising=False)
    assert extractor_from_env() is extract_payload


def test_extractor_from_env_enables_hybrid(monkeypatch):
    monkeypatch.setenv("EXHALE_LLM_EXTRACTOR", "1")
    monkeypatch.setenv("EXHALE_LLM_MODEL", "claude-opus-4-8")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")  # client construction only
    extractor = extractor_from_env()
    assert extractor is not extract_payload
    assert extractor.__self__.__class__ is HybridExtractor